# -*- coding: utf-8 -*-
"""ss_axcmp.py - 逐参数比较两份 .smc2 里同名轴的轴参数（离线、只读，不开 Sysmac）。

作者：hoverwu ｜ 版本：0.1.1（2026-11-07 改掉头注释里被证伪的"折叠态"结论，逻辑未变）

这是"界面抄参数"这类活的**唯一验收口**：屏幕上的组合框会说谎（只显不写，见
pitfalls §59、折叠组行不实化，见 §64），但 `文件>保存` 之后的归档不会。键 =
`(轴号, 段, 参数)`，值 = `CurrentValue`（数据来自 ss_axisparams.py）。

  python ss_axcmp.py A.smc2 B.smc2                 两份工程共有的全部轴号
  python ss_axcmp.py A.smc2 B.smc2 0 1 2 3 4 5     只看这些轴号

输出：每轴一段 `shared=/diff=/onlyA=/onlyB=`，随后逐条 `DIFF/ONLY-A/ONLY-B`，
最后一行 `#### total shared=N differing=M`。退出码恒 0（差异是数据，不是错误）。

读结果时先分类，再动手：
1. `PDO<i>PDOPathName` / `ODBitLocation` / `MappedDevice` 空 → 过程数据没写进去，回
   recipes §R 第 4 步（**编译不会把它们补出来**，§65.1）。
2. `NexAxisPDOMappingTable`（`''` vs `output=True,input=True,digital input=True,`）→ **不要试图
   对齐它**：2026-11-07 实测，真折叠 / 真展开 / 关掉页签再保存，三种做法之后归档那串**一字
   不变**；它只在"该轴的 PDO 单元格被界面提交过"时出现，**只增不减、界面无清除通道**
   （§65.2，旧结论"= 折叠态快照"已作废）。和 `en=False` 那类并列，归到"如实报告"。
3. `en=False` 的项（`NexAxisStartDirection`、未使用轴的类型/单位/速度）→ 界面无开关，
   如实报告，不要手改归档（§65.3）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss_axisparams as P                                                   # noqa: E402


def maph(arch):
    """({(轴号, 段, 参数): 当前值}, {轴号: 轴名})"""
    d, names = {}, {}
    for num, name, eid, fn, rows in P.table_of(arch):
        names[num] = name
        for sec, key, cur, dft, en, vi, opts in rows:
            d[(num, sec, key)] = cur if cur is not None else ''
    return d, names


def main():
    a, b = sys.argv[1], sys.argv[2]
    nums = set(sys.argv[3:])
    da, na = maph(a)
    db, nb = maph(b)
    shared = sorted(set(k[0] for k in da) & set(k[0] for k in db),
                    key=lambda s: int(s) if s.isdigit() else 999)
    if nums:
        shared = [n for n in shared if n in nums]
    print('# A=%s\n# B=%s\n# shared 轴号=%s' % (
        os.path.basename(a), os.path.basename(b), ','.join(shared)))
    tot = bad = 0
    for n in shared:
        keys = [k for k in sorted(set(da) & set(db)) if k[0] == n]
        only_a = [k for k in da if k[0] == n and k not in db]
        only_b = [k for k in db if k[0] == n and k not in da]
        diffs = [k for k in keys if da[k] != db[k]]
        tot += len(keys)
        bad += len(diffs)
        print('==== 轴号 %-3s A=%-14s B=%-14s shared=%-4d diff=%-4d onlyA=%d onlyB=%d'
              % (n, na[n], nb[n], len(keys), len(diffs), len(only_a), len(only_b)))
        for k in only_a:
            print('   ONLY-A %-40s = %r' % ('/'.join(k[1:]), da[k]))
        for k in only_b:
            print('   ONLY-B %-40s = %r' % ('/'.join(k[1:]), db[k]))
        for k in diffs:
            print('   DIFF   %-40s A=%-28r B=%r' % ('/'.join(k[1:]), da[k], db[k]))
    print('#### total shared=%d differing=%d' % (tot, bad))
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    sys.exit(main())
