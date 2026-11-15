# -*- coding: utf-8 -*-
"""ss_verify.py - 离线**结构检查** .smc2 归档（只读，纯标准库，普通权限即可）。

作者：hoverwu ｜ 版本：0.1.2 ｜ 非官方。

为什么需要它：一次性验收脚本常只查"程序存在 + 任务 XML 命中"就报 PASS，
漏掉配套文件缺失、引用悬空、归档损坏这些客观硬伤。本工具把每一项检查独立
判定，**任一客观失败 → 退出码 1**，全部通过才 0。它只是**结构检查**，不是
"完整强校验"：文件 hash 变化 / CPU 增长只是"发生过写入"的启发式佐证，不能当
功能正确的证明（offline-surgery §8.4）。

  ss_verify.py <archive.smc2> [--program NAME] [--report out.txt]

检查项（依据 offline-surgery §1 / §8.1 / §8.3 的实测格式）：
  zip         能打开、有条目、testzip() 无 CRC 错（testzip 抛异常也判 FAIL）
  oem         存在 <GUID>.oem、utf-8-sig 解析成功、根是 <sysmac> 且实体非空、
              实体 id 不重复（重复 id 会让索引静默覆盖 → FAIL）
  companions  Variables / PouBody / PouBodySourceHolder / DebugProgramSetting /
              NexTask 这些"必有配套文件"的实体，在 **.oem 所在根目录**下确有
              <id>.xml（不再按任意目录/任意扩展名前缀命中，避免库目录里的同 id
              文件或 id.txt 掩盖主工程缺文件）。**只对已验证的普通 NJ/NX 格式**：
              安全 CPU 的 subtype（Safety* / FBDExtended）不适用这条规则，原件本就
              没有同 id 的 .xml，工具只记 INFO 标 unsupported，既不判 FAIL 也不
              算通过
  program     （给了 --program 时）该 Program 实体存在且**唯一**（同名多命中报
              歧义 FAIL，不盲取第一个）；子实体配套齐全，但 SourceHolder 这类
              文档允许无配套文件的豁免类型不算缺文件
  tasks       每个 NexTask 配套 XML 里 AssociatedProgramData 的 ProgramName
              必须能在实体索引里找到对应 Program（悬空引用 = FAIL）
  assoc       [INFO] 任务 XML 有关联、但 .oem 任务子树里没有 *AssociatedProgram*
              实体时如实报告。实测（原生保存后只读 ZIP 核对）任务子树会挂与
              AssociatedProgramData 对应的 NexAssociatedProgram（+ AssociatedProgramModel
              配套），结构持久化已观察；但是否运行时必需**仍未验证**，故只记 INFO
              不判 FAIL，**这条 INFO 不算"任务关联通过"**，见 extending.md 待验证清单。

退出码：0 = 全部客观结构检查通过；1 = 有 FAIL（含文件打不开/损坏）；2 = 用法错误。
INFO 是观察项，不参与判定。本工具不证明"软件能打开/能编译/运行时正确"，
那些仍须按 offline-surgery §7 在软件里复验。
"""
import argparse
import sys
import zipfile
import xml.etree.ElementTree as ET

REQUIRED_COMPANION_TYPES = ('Variables', 'PouBody', 'PouBodySourceHolder',
                            'DebugProgramSetting', 'NexTask')
# 文档（offline-surgery §8.1）里 SourceHolder 是源名链接占位，允许没有自己的
# 配套文件；--program 子实体检查不要把这类豁免类型当成缺文件。
EXEMPT_COMPANION_TYPES = ('SourceHolder',)


def is_safety_scoped(i):
    """True for safety-CPU entity formats whose on-disk shape was never verified.

    Observed in real archives (original project and a native-saved copy alike):
    safety program Variables/s subtype=SafetyExtendedProgramLocal and
    PouBody/subtype=FBDExtended have no per-entity file at all, while
    Variables/subtype=SafetyGlobal has only .bin/.BookmarkGroup/.meta/.model.
    Applying the normal NJ/NX companion rule to these produces false FAILs, so
    they are reported as unsupported instead - not as missing and not as a pass.
    """
    sub = i['subtype']
    return sub.startswith('Safety') or sub == 'FBDExtended'


def load_oem(z):
    """(name, root) of the entity-tree .oem; (None, None) when absent/bad."""
    oems = [n for n in z.namelist() if n.lower().endswith('.oem')]
    if not oems:
        return None, None
    oems.sort(key=len)                      # 根 .oem 是 <GUID>/<GUID>.oem，取最短
    name = oems[0]
    try:
        return name, ET.fromstring(z.read(name).decode('utf-8-sig'))
    except Exception:
        return name, None


def entities(root):
    """(idx, dups): id -> {type, subtype, name, elem}, plus ids seen more than once.

    A repeated id would silently overwrite the index, so duplicates are surfaced
    for the caller to FAIL on rather than hidden.
    """
    idx, seen, dups = {}, set(), []
    for e in root.iter('Entity'):
        eid = e.get('id')
        if not eid:
            continue
        if eid in seen and eid not in dups:
            dups.append(eid)
        seen.add(eid)
        idx[eid] = {'type': e.get('type') or '', 'subtype': e.get('subtype') or '',
                    'name': e.get('name') or '', 'elem': e}
    return idx, dups


def child_entities(e):
    c = e.find('ChildEntities')
    return c.findall('Entity') if c is not None else []


def has_companion(names, oem_dir, eid):
    """True iff <oem_dir>/<eid>.xml exists — the entity's own file in the project
    root, not a same-id file in some library folder or an <eid>.txt lookalike."""
    return ('%s/%s.xml' % (oem_dir, eid)) in names


def verify(path, program=None):
    """Run all checks; return (report_lines, fail_messages)."""
    lines, fails = [], []

    def rec(level, msg):
        lines.append('[%s] %s' % (level, msg))
        if level == 'FAIL':
            fails.append(msg)

    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        rec('FAIL', 'zip open: %r' % (e,))
        return lines, fails
    with z:
        names = z.namelist()
        if not names:
            rec('FAIL', 'zip: empty archive')
            return lines, fails
        try:
            bad = z.testzip()
        except Exception as e:
            rec('FAIL', 'zip: testzip raised %r' % (e,))
            return lines, fails
        if bad is not None:
            rec('FAIL', 'zip: CRC error at %s' % bad)
            return lines, fails
        rec('PASS', 'zip: %d entries, testzip ok' % len(names))

        oem_name, root = load_oem(z)
        if root is None:
            rec('FAIL', 'oem: missing or unparseable (%s)' % oem_name)
            return lines, fails
        rec('PASS', 'oem: %s parsed' % oem_name)
        oem_dir = oem_name.rsplit('/', 1)[0] if '/' in oem_name else ''

        if root.tag != 'sysmac':
            rec('FAIL', 'oem: root <%s> is not <sysmac> - not an entity tree' % root.tag)
            return lines, fails
        idx, dups = entities(root)
        if not idx:
            rec('FAIL', 'oem: <sysmac> has no Entity - empty entity tree')
            return lines, fails
        if dups:
            rec('FAIL', 'oem: %d duplicate entity id(s): %s'
                % (len(dups), '; '.join(dups[:8])))
            return lines, fails
        rec('PASS', 'entities: %d indexed, ids unique' % len(idx))

        judged = [(eid, i) for eid, i in idx.items()
                  if i['type'] in REQUIRED_COMPANION_TYPES and not is_safety_scoped(i)]
        unverified = [i for i in idx.values()
                      if i['type'] in REQUIRED_COMPANION_TYPES and is_safety_scoped(i)]
        missing = ['%s(%s)' % (i['name'] or eid, i['type'])
                   for eid, i in judged if not has_companion(names, oem_dir, eid)]
        if missing:
            rec('FAIL', 'companions: %d required entities without <id>.xml in %s/: %s'
                % (len(missing), oem_dir or '.', '; '.join(missing[:8])))
        else:
            rec('PASS', 'companions: all required-type entities have <id>.xml')
        if unverified:
            rec('INFO', 'safety: %d entity(ies) in unverified safety formats, companion '
                'rule not applied (NOT a pass): %s'
                % (len(unverified), '; '.join('%s/%s' % (i['type'], i['subtype'])
                                              for i in unverified[:8])))

        if program:
            hits = [i for i in idx.values()
                    if i['type'] == 'Program' and i['name'] == program]
            if not hits:
                rec('FAIL', 'program %r: not found' % program)
            elif len(hits) > 1:
                rec('FAIL', 'program %r: ambiguous - %d entities share this name'
                    % (program, len(hits)))
            else:
                p = hits[0]
                rec('PASS', 'program %r: subtype=%s' % (program, p['subtype']))
                kids = child_entities(p['elem'])
                rec('INFO', 'program children: %s'
                    % ', '.join('%s/%s' % (k.get('type'), k.get('subtype')) for k in kids))
                for k in kids:
                    kid, ktype = k.get('id'), k.get('type') or ''
                    if ktype in EXEMPT_COMPANION_TYPES or is_safety_scoped(
                            {'type': ktype, 'subtype': k.get('subtype') or ''}):
                        continue
                    if kid and not has_companion(names, oem_dir, kid):
                        rec('FAIL', 'program child %s(%s): companion missing'
                            % (ktype, kid))

        tasks = [(eid, i) for eid, i in idx.items() if i['type'] == 'NexTask']
        rec('INFO', 'tasks: %d NexTask entities' % len(tasks))
        for eid, t in tasks:
            label = t['name'] or eid
            xml_name = '%s/%s.xml' % (oem_dir, eid)
            if xml_name not in names:
                rec('FAIL', 'task %r: no companion xml' % label)
                continue
            try:
                tr = ET.fromstring(z.read(xml_name).decode('utf-8-sig'))
            except Exception as e:
                rec('FAIL', 'task %r: companion parse %r' % (label, e))
                continue
            assocs = list(tr.iter('AssociatedProgramData'))
            if not assocs:
                rec('INFO', 'task %r: no AssociatedProgramData' % label)
            for a in assocs:
                pn = a.get('ProgramName') or ''
                if any(i['type'] == 'Program' and i['name'] == pn for i in idx.values()):
                    rec('PASS', 'task %r -> program %r: exists' % (label, pn))
                else:
                    rec('FAIL', 'task %r -> program %r: dangling reference' % (label, pn))
            if assocs and not any('AssociatedProgram' in (e.get('type') or '')
                                  for e in t['elem'].iter('Entity')):
                rec('INFO', 'task %r: XML association present but no *AssociatedProgram* '
                    'entity in .oem subtree (NexAssociatedProgram observed after native '
                    'save; runtime-required UNVERIFIED; this INFO is NOT a task-association pass)' % label)
    return lines, fails


def main(argv=None):
    ap = argparse.ArgumentParser(description='离线结构检查 .smc2 归档（只读，不证明能打开/能编译）。')
    ap.add_argument('archive', help='目标 .smc2 路径')
    ap.add_argument('--program', help='额外校验该名字的 Program 实体及其配套文件')
    ap.add_argument('--report', help='把报告写到该文件（UTF-8）')
    args = ap.parse_args(argv)
    lines, fails = verify(args.archive, args.program)
    lines.append('RESULT = %s (%d fail)' % ('FAIL' if fails else 'PASS', len(fails)))
    txt = '\n'.join(lines)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as fh:
            fh.write(txt + '\n')
    print(txt)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())