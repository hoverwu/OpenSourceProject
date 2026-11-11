# -*- coding: utf-8 -*-
"""ss_ecat_archive.py - 从 .smc2 归档里读 EtherCAT 组态真值（只读）。

作者：hoverwu ｜ 版本：0.2.0 ｜ 建立：2026-11-08 ｜ 非官方。普通权限即可，不需要提权。
本版更新（0.2.0）：新增 cmp 模式——只比 (subtype, 节点标签)、不比实体 name，
用于跨工程验收（name 是每工程各自分配的，diff 模式因此天然全红）。

为什么另写：界面（拓扑树 / 工程树 / `从设备数量`）都会滞后或语义不稳，
验收只能看归档。归档里的坑：

* `.oem` 是 **UTF-8 with BOM**，必须 `utf-8-sig` 解码，否则首元素读不到；
* `SlaveProxy` 的节点标签在 **DN**（`节点1 : GX-JC06(IN,X2,X3) Main device (设备名示例1)`）；
* `NXBusCoupler`（NX-ECC203 等）**没有 DN**，节点标签在 **SDName**
  （`节点3 : NX-ECC203 (耦合器1)`）——只读 DN 会把耦合器当成 None；
* `NexEcatMdpSlave`（Festo 阀岛等）也是 `SDName`。

  ss_ecat_archive.py <archive.smc2> [tree|flat|diff <other.smc2>] [--sub 关键字]
        tree  按实体嵌套缩进打印 EtherCAT 子树（含 subtype / name / DN / SDName）
        flat  只打印一条链：序号 | subtype | name | 节点标签 | 设备名
        diff  与另一个归档逐条对比节点标签序列，打印首个差异
  ss_ecat_archive.py <A.smc2> cmp <B.smc2>
        只比 (subtype, 节点标签)（节点标签用 tag()：DN 优先、其次 SDName），
        **不比实体 name**。逐位比较，缺行按 ('', '<missing>')。
        完全一致打印 RESULT EXACT 退出 0；有差异打印 RESULT DIFF <n> 退出 1。
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

ECAT_TYPES = ('SlaveProxy', 'NXBusCoupler', 'NexECAT', 'NexEcatMdpSlave',
              'EcatConfigurationProxy', 'EcatConfigurationSubstance')


def load(path):
    with zipfile.ZipFile(path) as z:
        oem = [n for n in z.namelist() if n.lower().endswith('.oem')]
        if not oem:
            raise SystemExit('no .oem in %s' % path)
        # 根 .oem 是 <GUID>/<GUID>.oem；取字节最短的那个（实体树）
        oem.sort(key=len)
        raw = z.read(oem[0])
    return ET.fromstring(raw.decode('utf-8-sig')), oem[0]


def tag(e):
    """节点标签：DN 优先，其次 SDName。"""
    for k in ('DN', 'SDName'):
        v = e.get(k)
        if v:
            return v
    return ''


def ecat_root(root):
    for e in root.iter('Entity'):
        if e.get('subtype') == 'EcatConfigurationProxy':
            return e
    return None


def kids(e):
    """子实体挂在 <ChildEntities><Entity .../></ChildEntities> 下面，
    不是 <Entity> 的直接子元素（直接 findall('Entity') 会得到 0 条）。"""
    c = e.find('ChildEntities')
    if c is None:
        return []
    return c.findall('Entity')


def walk(e, depth, out, sub=''):
    st = e.get('subtype') or e.get('type') or ''
    nm = e.get('name') or ''
    tg = tag(e)
    line = '%s%-28s %-18s %s' % ('  ' * depth, st, nm, tg)
    if not sub or sub.lower() in line.lower():
        out.append(line)
    for ch in kids(e):
        walk(ch, depth + 1, out, sub)


def flat(proxy):
    rows = []
    for e in kids(proxy):
        rows.append((e.get('subtype') or '', e.get('name') or '', tag(e)))
    return rows


def cmp_rows(path):
    """cmp 模式的行序列：只取 (subtype, 节点标签)，不含实体 name。"""
    root, _ = load(path)
    proxy = ecat_root(root)
    if proxy is None:
        raise SystemExit('no EcatConfigurationProxy in %s' % path)
    return [((e.get('subtype') or e.get('type') or ''), tag(e)) for e in kids(proxy)]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else 'flat'
    sub = ''
    if '--sub' in sys.argv:
        sub = sys.argv[sys.argv.index('--sub') + 1]
    if mode == 'cmp':
        if len(sys.argv) < 4:
            print('cmp needs <B.smc2>')
            return 2
        a = cmp_rows(path)
        b = cmp_rows(sys.argv[3])
        print('# A=%d rows  B=%d rows' % (len(a), len(b)))
        diff = 0
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else ('', '<missing>')
            y = b[i] if i < len(b) else ('', '<missing>')
            if x != y:
                diff += 1
                print('>>> %3d A: %s %s / B: %s %s' % (i, x[0], x[1], y[0], y[1]))
        print('# differing rows = %d' % diff)
        print('RESULT EXACT' if diff == 0 else 'RESULT DIFF %d' % diff)
        return 0 if diff == 0 else 1
    root, oem = load(path)
    proxy = ecat_root(root)
    if proxy is None:
        print('no EcatConfigurationProxy in', oem)
        return 1
    print('# archive=%s' % path)
    print('# oem=%s' % oem)
    if mode == 'tree':
        out = []
        walk(proxy, 0, out, sub)
        print('\n'.join(out))
        return 0
    if mode == 'flat':
        rows = flat(proxy)
        print('# flat children of Proxy = %d' % len(rows))
        for i, (st, nm, tg) in enumerate(rows):
            print('%3d %-16s %-20s %s' % (i, st, nm, tg))
        return 0
    if mode == 'diff':
        other, _ = load(sys.argv[3])
        a = flat(proxy)
        b = flat(ecat_root(other))
        print('# A=%d rows  B=%d rows' % (len(a), len(b)))
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else ('', '', '<missing>')
            y = b[i] if i < len(b) else ('', '', '<missing>')
            flag = '   ' if x == y else '>>>'
            print('%s %3d A: %-16s %-40s | B: %-16s %s' % (flag, i, x[0], x[2][:44], y[0], y[2][:44]))
        same = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
        print('# differing rows = %d %s' % (len(same), same[:20]))
        return 0
    print('unknown mode', mode)
    return 2


if __name__ == '__main__':
    sys.exit(main())