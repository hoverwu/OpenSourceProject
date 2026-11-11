# -*- coding: utf-8 -*-
"""ss_axisplan.py - 由**源工程归档 + 目标轴网格实测转储**生成逐行写计划（离线、只读）。

作者：hoverwu ｜ 版本：0.1.0

一份计划 = 每行 `{"label": "28. Positive limit switch", "device": "节点:20 伺服轴1(轴1)",
"pdkey": "60FDh-00.1"}`，交给 `ss_axpdo.py apply` 逐行写。两个来源各管一半，**谁也代替不了谁**：

* `pdkey` 只能来自**源归档**：`NexAxisGeneralSetting/PDO<i>PDOPathName`（`0x60FD:00`）+
  `PDO<i>ODBitLocation`（`1`）拼成 `'60FDh-00.1'`——界面 `过程数据` 下拉是**一位一项**
  （257 项），键必须按位，否则匹配不到（control-tree §17.3）。
* `label` 和 `device` 只能来自**目标工程自己那张网格**（`ss_axpdo.py collect` 的转储）：
  功能名里的编号是 FunctionNumber，两工程一致，用它对齐；`设备` 选项文本
  （`节点:20 伺服轴1(轴1)`）是目标工程的从站命名，源工程里根本没有这个字符串。

  python ss_axisplan.py <源.smc2> <轴号> <collect.txt> [-o logs/plan_axis<N>.json]

默认输出写到 **当前工作目录**/logs/plan_axis<N>.json（运行时产物，可删；不往脚本目录写），
`-o` 可显式指定其它路径。

collect.txt 行格式（`ss_axpdo.py collect` 落盘的就是这个）：
`功能名 \t IsEnabled \t "设备当前文本" \t "过程数据当前文本"`，制表符分隔、后两列是 JSON 串。

注意：**换 `输出设备` 会清空该轴所有 PDO 映射**（pitfalls §61），所以绑定要先把
`ss_axtable.py set` 跑对，再 collect，再 plan，再 apply；顺序反了 collect 到的 `device`
会是 `＜未分配＞`，写进去就是错的。
"""
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss_axisparams as X                                                   # noqa: E402


def cur(el):
    return (el.findtext('CurrentValue') or '').strip() if el is not None else ''


def axis_rows(z, fn):
    """[(FunctionNumber, pdkey)] for the mapped PDO entries of one axis XML."""
    root = ET.fromstring(z.read(fn).decode('utf-8-sig'))
    gen = root.find('NexAxisGeneralSetting')
    if gen is None:
        return []
    out = []
    for i in range(256):
        dev = cur(gen.find('PDO%dMappedDevice' % i))
        if not dev:
            continue
        path = cur(gen.find('PDO%dPDOPathName' % i))
        bit = cur(gen.find('PDO%dODBitLocation' % i))
        fnum = cur(gen.find('PDO%dFunctionNumber' % i))
        m = re.match(r'0x([0-9A-Fa-f]+):(\d+)', path)
        key = '' if not m else '%sh-%s.%s' % (m.group(1).upper(), m.group(2), bit)
        out.append((fnum, key, path, bit, dev))
    return out


def parse_collect(path):
    """{FunctionNumber: (label, device_text)} out of an `ss_axpdo.py collect` dump."""
    labels, dev_cap = {}, ''
    for line in io.open(path, encoding='utf-8', errors='replace'):
        f = line.rstrip('\n').split('\t')
        if len(f) != 4 or f[1] not in ('True', 'False'):
            continue                       # header / expand notes
        label = f[0].strip()
        try:
            dev = json.loads(f[2])
        except ValueError:
            dev = ''
        m = re.match(r'\s*(\d+)\.', label)
        if m:
            labels[m.group(1)] = label
        if dev and dev != '＜未分配＞' and not dev_cap:
            dev_cap = dev
    return labels, dev_cap


def main():
    src, num, collect = sys.argv[1], sys.argv[2], sys.argv[3]
    out = (sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv
           else os.path.join(os.getcwd(), 'logs', 'plan_axis%s.json' % num))
    labels, dev_cap = parse_collect(collect)
    if not labels:
        print('!! %s 里没有可读行——先跑 `ss_axpdo.py collect <pid> %s <轴树路径>`'
              % (collect, collect))
        return 2
    if not dev_cap:
        print('!! collect 里所有 `设备` 都是 ＜未分配＞：绑定还没落进模型（§59/§61），'
              '先 `ss_axtable.py set` 改对输出设备再 collect')
        return 3
    z = zipfile.ZipFile(src)
    plan = miss = 0
    data = []
    for name, eid, fn in X.load(z):
        if not fn:
            continue
        rows = list(X.params(z.read(fn)))
        if X.num_of(rows) != num:
            continue
        print('# 源轴 %s %s' % (num, name))
        for fnum, key, path, bit, dev in axis_rows(z, fn):
            lab = labels.get(fnum)
            if lab is None:
                print('  !! FunctionNumber=%s (%s %s.%s) 在目标网格里没有对应行'
                      % (fnum, path, bit, dev[:8]))
                miss += 1
                continue
            row = {'label': lab, 'device': dev_cap, 'pdkey': key}
            if not key:
                del row['pdkey']
            print('  %-46s %-12s %s' % (lab, key, path))
            plan += 1
            if plan == 1:
                data = []
            data.append(row)
    d = os.path.dirname(os.path.abspath(out))
    if not os.path.isdir(d):
        os.makedirs(d)
    json.dump(data, io.open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('#### rows=%d miss=%d -> %s' % (plan, miss, out))
    print('下一步：ss_axpdo.py apply <pid> logs/axpdo_apply%s.txt <轴树路径> %s'
          % (num, out))
    return 0 if plan and not miss else 1


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main())
