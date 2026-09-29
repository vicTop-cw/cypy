#!/usr/bin/env python3
"""Widen the freshness guard from one log to the whole evidence set §三/§一 cite.

patch9 only pinned `pytest_final_sweep6.log`; the suite result and the marker rescan that the report
also presents as 终态 were fresh by luck, not by check. And nothing enforced the ordering invariant
that makes the before/after table meaningful at all: a baseline newer than the terminal run would
silently invert the comparison. Both are now sys.exit conditions, and the per-file deltas go into the
report as a table instead of prose.
"""
import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

OLD_CODE = """NEWEST_PATH = os.path.relpath(_newest[1], ROOT).replace("\\\\", "/")
NEWEST_LAG = int(_log_ts - _newest[0])
GUARD_FILES = len(_py)"""
NEW_CODE = '''NEWEST_PATH = os.path.relpath(_newest[1], ROOT).replace("\\\\", "/")
NEWEST_LAG = int(_log_ts - _newest[0])
GUARD_FILES = len(_py)
TERMINAL_EVIDENCE = [("pytest 全量终态", "pytest_final_sweep6.log"),
                     ("test_suite 自研套件终态", "test_suite_after_sweep4.log"),
                     ("标记盘点复扫终态", "markers_after_sweep4.json")]
BASELINE_EVIDENCE = [("pytest 全量基线", "pytest_baseline.log"),
                     ("标记盘点基线", "markers_baseline.json")]
_fresh_rows = []
for _label, _name in TERMINAL_EVIDENCE:
    _ts = os.path.getmtime(os.path.join(HERE, _name))
    if _ts < _newest[0]:
        sys.exit(f"[gen_report] 终态证据 {_name} 早于 {NEWEST_PATH} —— 该行数字作废，必须重跑后再出报告")
    _fresh_rows.append("| {} | `{}` | 晚 {} 分钟 | 有效 |".format(
        _label, _name, int((_ts - _newest[0]) / 60)))
for _label, _name in BASELINE_EVIDENCE:
    _ts = os.path.getmtime(os.path.join(HERE, _name))
    if _ts >= _log_ts:
        sys.exit(f"[gen_report] 基线 {_name} 不早于终态日志 —— 前后对照口径反了，不生成报告")
    _fresh_rows.append("| {} | `{}` | 早 {} 分钟 | 作对照锚 |".format(
        _label, _name, int((_log_ts - _ts) / 60)))
FRESH_ROWS = "\\n".join(_fresh_rows)'''

OLD_PROSE = """`gen_report.py` 直接 `sys.exit` 拒绝出报告（本轮之后的改动只落在 `.fist-polish-20260926/` 与
`memory/` 两处，故未重跑 18 分钟的全量）。"""
NEW_PROSE = OLD_PROSE + """

守卫盯的不是那一份日志，而是本报告当作**终态**与**基线**引用的全部证据；任一条终态早于最新源码即
`sys.exit`（数字作废），任一条基线不早于终态也 `sys.exit`（前后对照口径反了同样是缺陷）：

| 证据 | 文件 | 与最新源码的 mtime 差 | 判定 |
|---|---|---|---|
{FRESH_ROWS}"""

EDITS = [(OLD_CODE, NEW_CODE), (OLD_PROSE, NEW_PROSE)]


def main() -> int:
    src = open(TARGET, encoding="utf-8").read()
    for old, _ in EDITS:
        n = src.count(old)
        print("count={} :: {}".format(n, old[:46].replace("\n", "\\n")))
        if n != 1:
            sys.exit("[patch11] 锚点匹配异常 —— 未写文件")
    if "TERMINAL_EVIDENCE" in src:
        print("[patch11] 已打过，no-op")
        return 0
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    compile(src, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    print("[patch11] applied={} bytes={}".format(len(EDITS), len(src.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
