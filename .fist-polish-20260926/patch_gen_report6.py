#!/usr/bin/env python3
"""Patch gen_report.py so the report reflects the bugs.md `### FIXED` 留档 pass.

Match-once discipline as before: every anchor must hit exactly once or nothing is written, the
file is rewritten at byte level with its own newline style, and the result must compile.
"""
import os
import py_compile
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "gen_report.py")

EDITS = [
    # 1. load the annotator's own output so the report cites a measured artifact, not prose
    (
        'intake5 = load("intake_map5.json")',
        'intake5 = load("intake_map5.json")\n'
        'annot = load("annotate_bugs_fixed.out.json")',
    ),
    # 2. bind the FIXED appendix count to the ledger itself (and pin BUG-13 as un-annotated)
    (
        'led = read(os.path.join("..", "memory", "bugs.md")).replace("\\\\", "/")',
        'led = read(os.path.join("..", "memory", "bugs.md")).replace("\\\\", "/")\n'
        'FIXED_BLOCKS = led.count("### FIXED(")\n'
        'if FIXED_BLOCKS != FIXED_TOTAL:\n'
        '    sys.exit(f"[gen_report] bugs.md 里的 ### FIXED 追加段 {FIXED_BLOCKS} 条 != 已闭环单 '
        '{FIXED_TOTAL} 条")\n'
        'if annot["annotated_count"] != FIXED_BLOCKS:\n'
        '    sys.exit(f"[gen_report] annotate_bugs_fixed.out.json 记 {annot[\'annotated_count\']} '
        '条，账本实测 {FIXED_BLOCKS} 条")\n'
        'if "### FIXED(" in led[led.index("## BUG-13"):]:\n'
        '    sys.exit("[gen_report] BUG-13 入账未修却在账本里带了 FIXED 段")\n'
        'annot_cases = annot["regression_cases_annotated"]',
    ),
    # 3. gate ④ evidence line gains the ledger-side留档
    (
        '（bugs.md 标题 ↔ 库内 task 行的配对核账） |',
        '（bugs.md 标题 ↔ 库内 task 行的配对核账）+ `annotate_bugs_fixed.out.json`'
        '（{FIXED_BLOCKS}/{FIXED_TOTAL} 条已闭环条目各带一段追加式 `### FIXED(verify=已完成)`，'
        'BUG-13 无该段） |',
    ),
    # 4. §二 gains the留档 sentence + the record that three truncated用例名 were caught
    (
        '回归文件：`tests/test_polish_20260926.py`，本轮收集 {regress_cases} 条用例（每单 ≥1 条）。',
        '回归文件：`tests/test_polish_20260926.py`，本轮收集 {regress_cases} 条用例'
        '（{annot["annotated_count"]} 个已闭环单对应 {annot_cases} 条，逐单在 §二 表内点名）。\n\n'
        '账本侧留档（归档口径要求「报告与 bugs.md 增量留档」）：`memory/bugs.md` 的 '
        '{FIXED_BLOCKS} 条已闭环条目各追加了一段 `### FIXED(verify=已完成)`，写明任务 id、库里状态、'
        '改动文件与锁死回归；条目正文与标题行的 `OPEN` 一字未改（追加脚本 '
        '`.fist-polish-20260926/annotate_bugs_fixed.py` 自带「回剥插入段 == 原文」的逐字节自证，'
        'BUG-13 那段没有写）。\n\n'
        '本表用例名的口径修正：`TESTS` 是手写文案，之前有三处写成了截断形态'
        '（`test_bug5_state_snapshot`、`test_bug5_state_restore`、`test_bug6_cypy_file_with_bom`），'
        'pytest 按这些名字根本收集不到——是报告的错，不是产品的错。现已改为真实 `def` 全名，'
        '并在生成器里双向绑定：表里出现的名字必须是真实函数，真实函数也必须全部出现在表里，'
        '否则 `sys.exit`（本轮实测 20 个 `def` / {regress_cases} 条收集用例，BUG-4 那 1 个函数 '
        'parametrize 展开 5 条）。',
    ),
]


def main() -> int:
    raw = open(TARGET, "rb").read()
    crlf = b"\r\n" in raw
    nl = "\r\n" if crlf else "\n"
    s = raw.decode("utf-8").replace("\r\n", "\n")
    bad = []
    for old, new in EDITS:
        old = old.replace("\r\n", "\n")
        new = new.replace("\r\n", "\n")
        hits = s.count(old)
        if hits != 1:
            bad.append((hits, old[:70]))
    if bad:
        for hits, frag in bad:
            print(f"MATCH-ONCE 失败 hits={hits} anchor={frag!r}")
        print("未写盘")
        return 1
    for old, new in EDITS:
        s = s.replace(old.replace("\r\n", "\n"), new.replace("\r\n", "\n"), 1)
    for stale in ("(+timeout 常量共用一条)",
                  '"test_bug5_state_snapshot / test_bug5_state_restore"',
                  '"test_bug6_cypy_file_with_bom / '):
        if stale in s:
            print(f"残留旧文案未替换：{stale}")
            return 1
    data = s.replace("\n", nl).encode("utf-8")
    open(TARGET, "wb").write(data)
    compile(data, TARGET, "exec")
    py_compile.compile(TARGET, doraise=True)
    m = re.search(r"回归文件", s)
    print(f"applied={len(EDITS)} newline={'CRLF' if crlf else 'LF'} "
          f"bytes={len(raw)}->{len(data)} anchor@{m.start() if m else -1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
