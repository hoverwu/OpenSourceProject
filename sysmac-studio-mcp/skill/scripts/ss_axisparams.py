# -*- coding: utf-8 -*-
"""ss_axisparams.py - read the axis parameter table out of a .smc2 (offline, read-only).

作者：hoverwu ｜ 版本：0.1.0 ｜ 不打开 Sysmac，只读文件

一个 `.smc2` 是 zip，轴实体在 `<GUID>.oem` 里是
`type="AxisSettingEntity" id=… name=… DN="轴名 (轴号,MC1)"`，它的**参数正文在同名
`<GUID>.xml`**。本文件把那张 XML 摊平成 `(段, 参数, 当前值, 默认值, 可用, 可见, 选项)`，
这就是"界面上那些格子"的真值来源——界面读不到的（灰置、折叠、只显不写的框）都以这里为准。
实测背景见 references/control-tree.md §17.4、pitfalls.md §59/§65。

  python ss_axisparams.py <file.smc2>                       摘要：轴号/轴名/段与参数数
  python ss_axisparams.py <file.smc2> --num 0 --num 5       只看这些轴号
  python ss_axisparams.py <file.smc2> --diff                只打印 当前值 != 默认值 的项
  python ss_axisparams.py <file.smc2> --all                 打印全部项
  python ss_axisparams.py <file.smc2> --all --csv f.csv     另存长表 csv

每次运行还会把同样内容写到 **当前工作目录**/logs/axisparams_last.txt（运行时产物，可删；
不往脚本目录写）。`--csv` 的路径也由调用方给定。

用法提示：`--diff` 的对照物是**软件自己的默认值**，不是"另一份工程"；要比较两份工程请用
`ss_axcmp.py`。`IsEnabled=False` 的项（轴0 的 5 个、每轴的 `NexAxisStartDirection`）在界面
上改不动，别当成漏做。
"""
import csv
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
LEAF_TAGS = ('CurrentValue', 'IsEnabled', 'IsVisible', 'DefaultValue')


def load(z):
    """[(轴名, 实体id, 数据文件名 or None)] for every AxisSettingEntity in the archive."""
    oname = [n for n in z.namelist() if n.lower().endswith('.oem')][0]
    root = ET.fromstring(z.read(oname).decode('utf-8-sig'))
    by_base = {}
    for n in z.namelist():
        by_base.setdefault(os.path.basename(n).split('.')[0].upper(), []).append(n)
    axes = []
    for e in root.iter('Entity'):
        if e.get('type') != 'AxisSettingEntity':
            continue
        eid = (e.get('id') or '').upper()
        fn = next((f for f in by_base.get(eid, []) if f.endswith('.xml')), None)
        axes.append((e.get('name'), eid, fn))
    return axes


def params(xml_bytes):
    """yield (section, path, current, default, enabled, visible, options)."""
    root = ET.fromstring(xml_bytes.decode('utf-8-sig'))
    for sec in list(root):
        if sec.tag in ('PdoInfo',):
            continue
        for leaf in sec.iter():
            kids = [c for c in leaf if c.tag not in LEAF_TAGS and c.tag != 'Options']
            if leaf.tag in LEAF_TAGS or len(list(leaf)) == 0:
                continue
            if kids:
                continue
            cur = leaf.findtext('CurrentValue')
            dft = leaf.findtext('DefaultValue')
            en = leaf.findtext('IsEnabled')
            vi = leaf.findtext('IsVisible')
            opts = [o.text for o in (leaf.find('Options') or [])]
            yield (sec.tag, leaf.tag, cur, dft, en, vi, opts)


def num_of(rows):
    for r in rows:
        if r[1] == 'NexAxisAxisNumber':
            return r[2]
    return '?'


def table_of(f):
    """[(轴号, 轴名, 实体id, 数据文件, rows)] 按轴号排序——打印与对比都从这里出发。"""
    z = zipfile.ZipFile(f)
    table = []
    for name, eid, fn in sorted(load(z)):
        rows = list(params(z.read(fn))) if fn else []
        table.append((num_of(rows), name, eid, fn, rows))
    table.sort(key=lambda t: (int(t[0]) if t[0].isdigit() else 999, t[1]))
    return table


def main():
    f = sys.argv[1]
    nums = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--num']
    mode = 'diff' if '--diff' in sys.argv else ('all' if '--all' in sys.argv else 'summary')
    csvp = sys.argv[sys.argv.index('--csv') + 1] if '--csv' in sys.argv else None
    z = zipfile.ZipFile(f)
    out, table = [], []
    for name, eid, fn in sorted(load(z)):
        if not fn:
            out.append('# MISSING DATA FILE %s %s' % (name, eid))
            continue
        rows = list(params(z.read(fn)))
        table.append((num_of(rows), name, eid, fn, rows))
    table.sort(key=lambda t: (int(t[0]) if t[0].isdigit() else 999, t[1]))
    out.append('# archive=%s  axes=%d' % (os.path.basename(f), len(table)))
    out.append('# 轴号  名称  实体id  参数数  非默认数')
    for axnum, name, eid, fn, rows in table:
        nd = sum(1 for r in rows if (r[2] or '') != (r[3] or ''))
        out.append('%-6s %-16s %s  params=%-4d nondefault=%d' % (axnum, name, eid, len(rows), nd))
    if mode != 'summary':
        for axnum, name, eid, fn, rows in table:
            if nums and axnum not in nums:
                continue
            out.append('\n===== 轴号 %s  %s  (%s) =====' % (axnum, name, eid))
            cur_sec = None
            for sec, key, cur, dft, en, vi, opts in rows:
                if mode == 'diff' and (cur or '') == (dft or ''):
                    continue
                if sec != cur_sec:
                    out.append('  [%s]' % sec)
                    cur_sec = sec
                o = ('  options=' + '|'.join(opts)) if len(opts) > 1 else ''
                out.append('    %-42s cur=%-24s def=%-22s en=%s vis=%s%s'
                           % (key, cur, dft, en, vi, o))
    if csvp:
        with open(csvp, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow(['轴号', '轴名', '实体id', '段', '参数', '当前值', '默认值', '可用', '可见', '选项'])
            for axnum, name, eid, fn, rows in table:
                if nums and axnum not in nums:
                    continue
                for sec, key, cur, dft, en, vi, opts in rows:
                    w.writerow([axnum, name, eid, sec, key, cur, dft, en, vi, '|'.join(opts)])
        out.append('# csv=%s' % csvp)
    txt = '\n'.join(out) + '\n'
    sys.stdout.buffer.write(txt.encode('utf-8'))
    d = os.path.join(os.getcwd(), 'logs')   # 运行时产物：相对当前工作目录，不写脚本目录
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(os.path.join(d, 'axisparams_last.txt'), 'wb') as fh:
        fh.write(txt.encode('utf-8'))


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
