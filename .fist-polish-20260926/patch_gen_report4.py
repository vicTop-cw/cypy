#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wire the fourth pass (BUG-12 / T0r17) into gen_report.py's prose.

Data sources were already swapped; this only rewrites the sentences and file lists that
still name third-round artifacts. Every replacement must match exactly once, otherwise the
patch aborts before writing (the generator is the sole producer of the terminal report --
a half-patched template would print prose that no longer matches the logs it cites).
gen_report.py is CRLF: read as text, write back with newline="\\r\\n".
"""
import io
import sys

PATH = ".fist-polish-20260926/gen_report.py"

EDITS = [
    # --- parsed snapshots: sweep4 becomes an intermediate, sweep5 the terminal ---
    ('mid3 = suite("pytest_final_sweep3.log")\n',
     'mid3 = suite("pytest_final_sweep3.log")\nmid4 = suite("pytest_final_sweep4.log")\n'),
    ('                   ("pytest_final_sweep2.log", prev), ("pytest_final_sweep3.log", mid3)):',
     '                   ("pytest_final_sweep2.log", prev), ("pytest_final_sweep3.log", mid3),\n'
     '                   ("pytest_final_sweep4.log", mid4)):'),
    ('_failed = [l.strip() for l in read("pytest_final_sweep4.log").splitlines()',
     '_failed = [l.strip() for l in read("pytest_final_sweep5.log").splitlines()'),

    # --- nogil.py md5, same style as project_compiler.py ---
    ('with open(os.path.join(ROOT, "cypyc", "project", "project_compiler.py"), "rb") as _f:\n'
     '    pc_md5 = hashlib.md5(_f.read()).hexdigest()\n',
     'with open(os.path.join(ROOT, "cypyc", "project", "project_compiler.py"), "rb") as _f:\n'
     '    pc_md5 = hashlib.md5(_f.read()).hexdigest()\n'
     'with open(os.path.join(ROOT, "cypy_bridge", "nogil.py"), "rb") as _f:\n'
     '    ng_md5 = hashlib.md5(_f.read()).hexdigest()\n'),

    # --- fourth-pass RED / switch-off / GREEN evidence lines ---
    ('red_switch11 = summary_line("pytest_switchoff_bug11.log")\n',
     'red_switch11 = summary_line("pytest_switchoff_bug11.log")\n'
     'red_fourth = summary_line("pytest_fourth_sweep_red.log")\n'
     'red_switch12 = summary_line("pytest_switchoff_bug12.log")\n'
     'green12 = summary_line("pytest_green_bug12.log", r"\\d+ passed")\n'
     '_m_red4 = re.search(r"(\\d+) failed, (\\d+) passed, (\\d+) deselected", red_fourth)\n'
     'if not _m_red4:\n'
     '    sys.exit(f"[gen_report] 第四遍 RED 日志不是定点跑形态（要 N failed, M passed, K deselected）："\n'
     '             f"{red_fourth!r}")\n'
     'if int(re.match(r"(\\d+)", green12).group(1)) != sum(int(x) for x in _m_red4.groups()):\n'
     '    sys.exit(f"[gen_report] BUG-12 定点绿（{green12}）与 RED 用例面 "\n'
     '             f"({red_fourth}) 不是同一批用例，拒绝拿它当 GREEN 证据")\n'),

    # --- gate ① / ③ / ④ cells ---
    ('| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | {g1}；用例 {base[\'collected\']} → '
     '{final[\'collected\']} | `.fist-polish-20260926/pytest_final_sweep4.log` 末行原文：',
     '| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | {g1}；用例 {base[\'collected\']} → '
     '{final[\'collected\']} | `.fist-polish-20260926/pytest_final_sweep5.log` 末行原文：'),
    ('`markers_baseline.json` vs `markers_after_sweep3.json`（同脚本同范围，与 '
     '`markers_after_sweep3b.json` 两次复扫计数完全一致） |',
     '`markers_baseline.json` vs `markers_after_sweep4.json`（同脚本同范围，与 '
     '`markers_after_sweep4b.json` 两次复扫计数完全一致） |'),
    ('| ④ 确诊缺陷 100% 入账 | 绿（{BUG_TOTAL}/{BUG_TOTAL}，无口头发现未入账；误报 2 条按红线不刷账） | '
     '`memory/bugs.md`（`## BUG-1..BUG-{BUG_TOTAL}`）+ `bug_list` count={intake3[\'ledger_after\']} + '
     '`intake_map.json`/`intake_map2.json`/`intake_map3.json` +',
     '| ④ 确诊缺陷 100% 入账 | 绿（{BUG_TOTAL}/{BUG_TOTAL}，无口头发现未入账；误报 4 条按红线不刷账） | '
     '`memory/bugs.md`（`## BUG-1..BUG-{BUG_TOTAL}`）+ `bug_list` count={intake4[\'ledger_after\']} + '
     '`intake_map.json`/`intake_map2.json`/`intake_map3.json`/`intake_map4.json` +'),

    # --- §一 lane ③ + the false-positive ledger sentence ---
    ('第三遍把上一轮在途未验收的 subtype/analyzer 面与 project 装配面重读一遍 | '
     '确诊 4 条（BUG-2/BUG-7 + 复查时补的 BUG-8 + 第三遍补的 BUG-11）+ 误报 2 条 |',
     '第三遍把上一轮在途未验收的 subtype/analyzer 面与 project 装配面重读一遍；第四遍专读 '
     'bridge 面（GIL/线程/资源三类），并用 `.fist-polish-20260926/sweep4_classes.py` 的 AST 站点表'
     '把可疑处逐条复验 | '
     '确诊 5 条（BUG-2/BUG-7 + 复查时补的 BUG-8 + 第三遍补的 BUG-11 + 第四遍补的 BUG-12）+ 误报 4 条 |'),
    ('''确诊 {BUG_TOTAL} 条 → 全部 `report_bug(publish_task=true)` 入账；
误报 2 条不刷账：`cypyc/cli.py:36`（sys.stdout.reconfigure 是启动期防御）、
`cypy_bridge/pointer.py:142/412`（多策略取址的刻意 fallthrough，非吞错）；
待定 1 条（subtype golden，转结）。审查推理零付费 API。''',
     '''确诊 {BUG_TOTAL} 条 → 全部 `report_bug(publish_task=true)` 入账；
误报 4 条不刷账：`cypyc/cli.py:36`（sys.stdout.reconfigure 是启动期防御）、
`cypy_bridge/pointer.py:142/412`（多策略取址的刻意 fallthrough，非吞错）、第四遍的
`nogil_thread` 线程池「未关闭」疑点（`nogil_pool.__exit__` 已 `shutdown(wait=True)`，
`.fist-polish-20260926/repro_sweep4_nogil.py` 复现不出，判 B not reproduced）与
`GilState.acquire()` 三处站点（:80/:102/:153 是本模块模拟 GIL 的标志位读写，不是真 GIL 调用）；
待定 1 条（subtype golden，转结）。审查推理零付费 API。'''),

    # --- §二 RED evidence chain ---
    ('''（`.fist-polish-20260926/pytest_third_sweep_red.log`）。
GREEN 证据：''',
     '''（`.fist-polish-20260926/pytest_third_sweep_red.log`）。第四遍改前
`pytest tests/test_polish_20260926.py -q -k bug12` → `{red_fourth}`
（`.fist-polish-20260926/pytest_fourth_sweep_red.log`）。
GREEN 证据：'''),

    # --- §二 BUG-12 narrative, appended after the BUG-11 call-site probe paragraph ---
    ('''`probe_cli_check_e2e.out`）——源文件与输出目录都在临时目录，仓库 `output/`、`dist/` 未被写。

## 三、基线前后对照''',
     '''`probe_cli_check_e2e.out`）——源文件与输出目录都在临时目录，仓库 `output/`、`dist/` 未被写。
第四遍（BUG-12，收口后转读 bridge 面时补入）：`cypy_bridge/nogil.py` 的
`GilState.__exit__` 无条件 `self.acquire()`，而 `acquire()` 在 `not self._released` 时抛
`NoGilError`——于是**区域内已经自行 acquire、或语句自身正在抛异常**时，退出上下文会把用户的
`ValueError` 顶成 `NoGilError('GIL is not released')`，原始异常连同 traceback 一起消失
（与本模块 `NoGilContext` 修过的嵌套覆盖同族）。复现器
`.fist-polish-20260926/repro_sweep4_nogil.py` 打 A REPRODUCED / B not reproduced，
其中 B（`nogil_thread` 线程池未关闭）判**误报**、不入账。修法一行守卫 `if self._released:`，
`return False` 保持不变（不吞异常）。反向用例 `test_bug12_gilstate_exit_still_restores_state`
锁住「不许过度修成不再 acquire」。开关对照：把守卫退回改前形态 → `{red_switch12}`
（`.fist-polish-20260926/pytest_switchoff_bug12.log`，红的正是替换异常那一条，恢复态那条仍 pass），
恢复后 `pytest tests/test_polish_20260926.py -q` → `{green12}`，产品文件 md5 `{ng_md5}`。

## 三、基线前后对照'''),

    # --- §三 terminal reproduction narrative ---
    ('终态复现说明：修完之后共跑过 5 次全量。',
     '终态复现说明：修完之后共跑过 6 次全量。'),
    ('''加固后 `pytest_final_sweep3.log` → `{mid3['line']}`；第三遍（BUG-11）落地后终态
`pytest_final_sweep4.log` → `{final['line']}`，
「唯一红 = subtype golden」这一不变量保持，且五次收集数与通过数只增不减
（{mid1['collected']}、{mid2['collected']} → {prev['collected']} → {mid3['collected']} → {final['collected']}）。''',
    '''加固后 `pytest_final_sweep3.log` → `{mid3['line']}`；第三遍（BUG-11）落地后
`pytest_final_sweep4.log` → `{mid4['line']}`；第四遍（BUG-12）落地后终态
`pytest_final_sweep5.log` → `{final['line']}`，
「唯一红 = subtype golden」这一不变量保持，且六次收集数与通过数只增不减
（{mid1['collected']}、{mid2['collected']} → {prev['collected']} → {mid3['collected']} →
{mid4['collected']} → {final['collected']}）。'''),
    ('''标记面同理：`markers_after_sweep3.json` 与 `markers_after_sweep3b.json` 两次独立复扫的
counts 字典逐项相等（脚本已在不等时 `sys.exit`）；`test_suite_after_sweep3.log` 与 BUG-8 之前的
`test_suite_final.log` 同为 {ts['passed']}/{ts['total']}——BUG-9/BUG-10 只补 stderr 告警、
未改控制流，第二套自研体系（{ts['total']} 条、{ts['elapsed']}s）因此无需重跑基线。''',
    '''标记面同理：`markers_after_sweep4.json` 与 `markers_after_sweep4b.json` 两次独立复扫的
counts 字典逐项相等（脚本已在不等时 `sys.exit`）；`test_suite_after_sweep4.log` 与 BUG-8 之前的
`test_suite_final.log` 同为 {ts['passed']}/{ts['total']}——BUG-9..BUG-12 只补告警或只加一行守卫、
未改对外控制流，第二套自研体系（{ts['total']} 条、{ts['elapsed']}s）因此无需重跑基线。'''),

    # --- §四 product file list ---
    ('产品代码：`cypy_bridge/compiler.py`、`cypy_hook/hook.py`、',
     '产品代码：`cypy_bridge/compiler.py`、`cypy_bridge/nogil.py`、`cypy_hook/hook.py`、'),

    # --- §六: the fourth pass joins the after-archive list ---
    ('''6. **第三遍（BUG-11）同样在根 `T0` 已归档之后补入**：其修复单 `{tid_by_bug.get('BUG-11')}`
   单独走完 claim→execute→submit→verify（原始回复见 `close_fixes3.out.json`），
   根任务不回退重开——原因与 §五.5/§六.1 相同：修复单本就落在 ns `bugs`。''',
     '''6. **第三遍（BUG-11）与第四遍（BUG-12）同样在根 `T0` 已归档之后补入**：其修复单
   `{tid_by_bug.get('BUG-11')}` / `{tid_by_bug.get('BUG-12')}` 各自单独走完
   claim→execute→submit→verify（原始回复见 `close_fixes3.out.json` / `close_fixes4.out.json`，
   第四遍另在单面上挂了 `run_check` 实跑 `tests/test_polish_20260926.py` 的机器校验），
   根任务不回退重开——原因与 §五.5/§六.1 相同：修复单本就落在 ns `bugs`。
7. **第四遍的判据自纠（写进报告，不当已解决）**：AST 站点表 `sweep4_classes.json` 最初把
   `hook.run()`/`self.run()` 也当成「无 timeout 的子进程」报了 2 处，属规则太宽（凡是名为
   `run` 的调用都收）。加上接收者限定 `subprocess.` 后同一遍的类 C 归零，之后才用它做排查面。
   这与 §二「判据不bind」是同一类错误：**判据报出的站点数必须先证明它能报出现行的真缺陷**，
   否则「0 处」和「2 处」都不能当结论。'''),

    # --- §七 lists ---
    ('''`.fist-polish-20260926/{{pfist,intake,intake2,intake3,marker_scan''',
     '''`.fist-polish-20260926/{{pfist,intake,intake2,intake3,intake4,sweep4_classes,repro_sweep4_nogil,switchoff_bug12,marker_scan'''),
    ('''markers_after_sweep3,markers_after_sweep3b,intake_map,intake_map2,intake_map3,close_fixes.out''',
     '''markers_after_sweep4,markers_after_sweep4b,intake_map,intake_map2,intake_map3,intake_map4,sweep4_classes,close_fixes.out'''),
    ('''close_fixes2.out,close_fixes3.out,report_fist_findings.out''',
     '''close_fixes2.out,close_fixes3.out,close_fixes4.out,report_fist_findings.out'''),
    ('''`.fist-polish-20260926/{{pytest_baseline,pytest_final_sweep4,test_suite_after_sweep3,pytest_testsuite_final}}.log`''',
     '''`.fist-polish-20260926/{{pytest_baseline,pytest_final_sweep5,test_suite_after_sweep4,pytest_testsuite_final}}.log`'''),
    ('''`{{pytest_second_sweep_red,pytest_switchoff_bug10,pytest_third_sweep_red,pytest_switchoff_bug11}}.log`''',
     '''`{{pytest_second_sweep_red,pytest_switchoff_bug10,pytest_third_sweep_red,pytest_switchoff_bug11,pytest_fourth_sweep_red,pytest_switchoff_bug12,pytest_green_bug12}}.log`'''),
    ('''`markers_after_sweep2.json`、`markers_after_sweep2b.json`、
  `test_suite_final.log`''',
     '''`markers_after_sweep2.json`、`markers_after_sweep2b.json`、
  `markers_after_sweep3.json`、`markers_after_sweep3b.json`、`test_suite_after_sweep3.log`、
  `test_suite_final.log`'''),
    ('''`pytest_final.log`、`pytest_final_after_bug8.log`、`pytest_final_sweep2.log`、`pytest_final_sweep3.log`——''',
     '''`pytest_final.log`、`pytest_final_after_bug8.log`、`pytest_final_sweep2.log`、
  `pytest_final_sweep3.log`、`pytest_final_sweep4.log`（终态为 `pytest_final_sweep5.log`）——'''),
]


def main():
    with io.open(PATH, encoding="utf-8") as f:
        text = f.read()
    for i, (old, new) in enumerate(EDITS):
        n = text.count(old)
        if n != 1:
            sys.exit(f"edit #{i} matched {n} times (want 1), refusing to patch:\n{old[:200]!r}")
        if old == new:
            sys.exit(f"edit #{i} is a no-op")
        text = text.replace(old, new)
    with io.open(PATH, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
    raw = open(PATH, "rb").read()
    crlf = raw.count(b"\r\n")
    print(f"applied {len(EDITS)} edits; CRLF {crlf} LF-only "
          f"{raw.count(chr(10).encode()) - crlf}")
    for tok in ("pytest_final_sweep4.log` → `{final", "markers_after_sweep3.json`（同脚本",
                "误报 2 条", "共跑过 5 次"):
        if tok in text:
            sys.exit(f"stale third-round wording still present: {tok!r}")
    print("stale-token check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
