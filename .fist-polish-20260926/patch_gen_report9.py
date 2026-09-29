#!/usr/bin/env python3
"""Add an mtime-attribution guard: the terminal pytest numbers must still describe this worktree.

The final sweep was run before the ledger/report work of this session, and every later step touched
only `.fist-polish-20260926/` + `memory/`. Instead of burning another 18-minute full run to prove
that, compare mtimes: if any .py under cypyc/, cypy_bridge/, cypy_hook/, tests/ is newer than
pytest_final_sweep6.log, the terminal figures no longer describe the tree -> refuse to generate.
"""
import os
import py_compile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

OLD_CODE = 'CAT_LOC_D = "、".join(_locs(cat, "D_lock_no_finally"))'
NEW_CODE = OLD_CODE + """
LOG = "pytest_final_sweep6.log"
_log_ts = os.path.getmtime(os.path.join(HERE, LOG))
_trees = ("cypyc", "cypy_bridge", "cypy_hook", "tests")
_py = [os.path.join(dp, fn)
       for t in _trees for dp, dn, fns in os.walk(os.path.join(ROOT, t))
       for fn in fns if fn.endswith(".py") and "__pycache__" not in dp]
if len(_py) < 80:
    sys.exit(f"[gen_report] 新鲜度守卫只看到 {len(_py)} 个 .py，四棵树路径不对——不生成报告")
_newest = max((os.path.getmtime(p), p) for p in _py)
if _newest[0] > _log_ts:
    sys.exit("[gen_report] {} 晚于终态日志 {} —— 终态数字不再描述当前工作区，"
             "必须先重跑 `python -m pytest tests/ -q` 再出报告".format(
                 os.path.relpath(_newest[1], ROOT).replace("\\\\", "/"), LOG))
NEWEST_PATH = os.path.relpath(_newest[1], ROOT).replace("\\\\", "/")
NEWEST_LAG = int(_log_ts - _newest[0])
GUARD_FILES = len(_py)"""

OLD_HEAD = "## 三、基线前后对照\n"
NEW_HEAD = OLD_HEAD + """
本报告引用的终态数字仍描述当前工作区，按 mtime 归因而非口头保证：新鲜度守卫扫了四棵树的
{GUARD_FILES} 个 `.py`（`cypyc/`、`cypy_bridge/`、`cypy_hook/`、`tests/`），最新修改是
`{NEWEST_PATH}`，它比终态日志 `{LOG}` 早 {NEWEST_LAG} 秒；任何晚于该日志的产品/测试文件都会让
`gen_report.py` 直接 `sys.exit` 拒绝出报告（本轮之后的改动只落在 `.fist-polish-20260926/` 与
`memory/` 两处，故未重跑 18 分钟的全量）。

"""
EDITS = [(OLD_CODE, NEW_CODE), (OLD_HEAD, NEW_HEAD)]


def main() -> int:
    src = open(TARGET, encoding="utf-8").read()
    hits = [(src.count(old), old[:40].replace("\n", "\\n")) for old, _ in EDITS]
    for n, tag in hits:
        print(f"count={n} :: {tag}")
    if any(n != 1 for n, _ in hits):
        sys.exit("[patch9] 锚点匹配异常 —— 未写文件")
    if "新鲜度守卫" in src:
        print("[patch9] 已打过，no-op")
        return 0
    for old, new in EDITS:
        src = src.replace(old, new, 1)
    open(TARGET, "w", encoding="utf-8", newline="").write(src)
    compile(src, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    print(f"[patch9] applied={len(EDITS)} bytes={len(src.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
