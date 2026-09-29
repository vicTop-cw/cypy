#!/usr/bin/env python3
"""Append `### FIXED(verify=已完成)` sections for the two commander-ruling tickets (BUG-13/14).

Contract is the same as annotate7.py: the ledger has no close API, so closure is an appended
section; the entry body and its `OPEN` title line are never rewritten; a section that already
exists means REFUSE (never a silent skip), because this script runs exactly once per pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")

BUGS_MD = ROOT / "memory" / "bugs.md"
SWEEP = os.environ.get("SWEEP", "pytest_final_sweep11.log")

BOUNDARY = {
 "BUG-13": "本段只把摘要判据的量纲从墙钟换成 CPU 时间，阈值数字一个没动（`< 2.0`、"
           "`< small*12+0.5` 原样，parse/compare 两条时限仍是墙钟）；被测的产品码性能未改变，"
           "「CPU 时间能代表摘要代价」这一前提由裁决本身背书，不在本单内再证。",
 "BUG-14": "裁决面只到类型表与 `SYNTAX/01-basic-types.md` 的措辞：`float` 与 `double` 现在同为 "
           "`double`，因此 `as float` 不再是窄化转换。除端到端基准按裁决重注册外，未改任何"
           "其它语义（subtype 检查、约束求解、数值字面量宽度推导均不动）。",
 "BUG-32": "只改约束这一行注释的渲染：新增 `_constraint_member_name()`——标量成员取声明原名逐字回显，"
           "`subtype`/`type` 成员仍递归化成基类型**名字**（`Meter`→`float`，S-4.1 不许子类型名出现在产物里），"
           "复合形态才退回 `_type_to_str`。第一版只做「一律逐字回显」，被下一次全量按 S-4.1 打回"
           "（`tests/test_nominal_subtypes.py::TestShippedExample::test_example_artifact_mentions_no_subtype_name` "
           "1 条红）。`# type alias:` 与 `ctypedef` 两处**故意保留**过映射——别名是真声明，必须吃到裁决宽度"
           "（对照锁钉住）。同族面已排查：codegen 里 17 处 `# ` 注释产出只有这一处过 type_mapper，"
           "analyzer/诊断面完全不调用它（实测 grep 零命中）。",
}
EVIDENCE = {
 "BUG-13": "判据前后分离测量：`.fist-polish-20260926/meas_digest_cost.out.txt`（入账时，同一夹具 "
           "wall/cpu 比 1.26–1.74）与 `meas_digest_after.out.txt`（落地后，两条判据各自 verdict）；"
           "回退树证红 `lockproof_pass7.json`",
 "BUG-14": "端到端基准重注册：before 快照 `.fist-polish-20260926/golden_before_float/`（25 份），"
           "逐行差 `golden_float_diff.json`（生成器 `_digits_only()` 对每处差异要求「只有数字变」），"
           "注册日志 `e2e_golden_reregister_float.log`；回退树证红 `lockproof_pass7.json`",
 "BUG-32": "红证据：`.fist-polish-20260926/pytest_final_sweep9.log` 里 `tests/test_named_constraints.py` "
           "三条失败原文（`assert '# constraint Numeric = int | float' in '...int | double...'`）；"
           "该次全量为 9 failed / 1842 passed，其中另 6 条是钉住旧宽度拼写的测试断言，已按裁决改指 "
           "`double`（逐条清单见打磨报告）；回退树证红 `lockproof_pass7.json`",
}
# 入账映射文件与来源说明：裁决单来自指挥官裁定，BUG-32 来自本轮终态全量实跑。
INTAKE_FILE = {"BUG-13": "intake_map5.json", "BUG-14": "intake_map6.json",
               "BUG-32": "intake_map10.json"}
ORIGIN = {"BUG-13": "指挥官对本轮 §七 三项待裁决第①项的裁定",
          "BUG-14": "指挥官对本轮 §七 三项待裁决第②项的裁定",
          "BUG-32": "指挥官 float=double 裁决落地后，本轮终态全量实跑自己抓出来的副作用"}


def main() -> int:
    close = {r["bug"]: r for r in
             json.loads((HERE / "close_fixes8.out.json").read_text(encoding="utf-8"))}
    reg = (ROOT / "tests" / "test_polish_20260926_pass7.py").read_text(encoding="utf-8")
    for name in (SWEEP, "meas_digest_after.out.txt", "golden_float_diff.json"):
        if not (HERE / name).exists():
            sys.exit(f"REFUSE: 缺证据件 {name}")

    text = BUGS_MD.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=## BUG-\d+ )", text)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    appended, out, seen = [], [parts[0]], set()
    for block in parts[1:]:
        bug = re.match(r"## (BUG-\d+) ", block).group(1)
        seen.add(bug)
        if bug not in close:
            out.append(block)
            continue
        if "### FIXED(verify=已完成)" in block:
            sys.exit(f"REFUSE: {bug} 已有 FIXED 段，本脚本一轮只跑一次（重复追加会伪造留档）")
        if not close[bug]["green"]:
            sys.exit(f"REFUSE: {bug} 未走完 verify，不能追加 FIXED 段")
        n = int(bug.split("-")[1])
        tests = re.findall(r"(?m)^def (test_bug%d_\w+)" % n, reg)
        if not tests:
            sys.exit(f"REFUSE: {bug} 没有反解到回归测试")
        reds = next((r["red_on_prefix_code"] for r in
                     json.loads((HERE / "lockproof_pass7.json").read_text(encoding="utf-8"))["rows"]
                     if r["bug"] == bug), [])
        if not reds:
            sys.exit(f"REFUSE: {bug} 的回归在回退树上没有转红，锁不可信")
        tid = close[bug]["task_id"]
        section = [f"### FIXED(verify=已完成) — 2026-09-26 追加留档（裁决落地段工作，本条目正文与标题行 `OPEN` 一字未改）",
                   f"- 修复单：`{tid}`（ns `bugs`），`execute → submit → verify` 原始回复见 "
                   f"`.fist-polish-20260926/close_fixes8.out.json`；入账映射见 "
                   f"`{INTAKE_FILE[bug]}`；来源：{ORIGIN[bug]}",
                   f"- 锁死回归（{len(tests)} 个函数）："
                   + "、".join(f"`tests/test_polish_20260926_pass7.py::{t}`" for t in tests)
                   + f"；每条在回退树上转红过：{'、'.join('`' + r + '`' for r in reds)}",
                   f"- 证据：{EVIDENCE[bug]}；全量终态 `.fist-polish-20260926/{SWEEP}`",
                   f"- 修复边界：{BOUNDARY[bug]}",
                   f"- 登记时间：{stamp}", ""]
        out.append(block.rstrip("\n") + "\n" + "\n".join(section))
        appended.append(bug)
    missing = sorted(set(close) - seen)
    if missing:
        sys.exit(f"REFUSE: bugs.md 里找不到这些条目: {missing}")
    BUGS_MD.write_text("".join(out), encoding="utf-8", newline="\n")
    print(f"appended={len(appended)} -> {appended}")
    check = BUGS_MD.read_text(encoding="utf-8")
    print("FIXED sections now:", check.count("### FIXED(verify=已完成)"),
          "entries:", len(re.findall(r"(?m)^## BUG-\d+ ", check)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
