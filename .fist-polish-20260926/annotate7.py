#!/usr/bin/env python3
"""Append the `### FIXED(verify=已完成)` sections for BUG-15..29 to memory/bugs.md.

Same contract as passes 1-6: the bug ledger has no close API and `report_bug` only appends, so
closure is recorded as an appended section per entry. Entry bodies and their `OPEN` title lines
are never rewritten -- this script inserts after the last line of the target entry only, and
refuses to run twice on the same entry.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")

BUGS_MD = ROOT / "memory" / "bugs.md"
LEDGER_NOTE = ("- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段追加留档、"
               "以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。")

BOUNDARY = {
 "BUG-20": "本段只把 Attribute 调用接到既有方法表上；表里没有的属性仍按旧口径降级为「不成值」，未加诊断。",
 "BUG-21": "只改登记处 :432；同族写法 :1280 与 :2005 未动（前者喂 _check_impl_on_subtype，"
           "后者的默认分支被 2002-2003 行注释当作刻意保留的失败面），各需独立证据。",
 "BUG-24": "只修目录匹配判据；cypyc/cli.py:384 仍无条件打印 [OK] cleared，「清了几个文件」未回传。",
 "BUG-26": "只放到产物发现（.so/.dll）；后续复制与 ctypes 加载在 Linux 上未实测（本机无该环境）。",
 "BUG-25": "只补两处写盘 encoding；同函数其余按本地编码读写的环节未扩面。",
 "BUG-18": "比对依赖 file_hash；dependencies 图本身的召回缺口（前一轮已登记的结构性项）不在本单内。",
 "BUG-16": "改动使被错编译的语料回到 SYNTAX/05-struct.md 承诺的行为；未新增任何语法或语义。",
 "BUG-19": "只调整插入点；不改变指令集合本身。",
 "BUG-15": "只把判定长度对齐消费长度；三反引号宏块语义不变。",
 "BUG-17": "返回 None 后上层走既有「No .pyd file generated」分支，未新增诊断文案。",
 "BUG-22": "组合前缀只承认 rf/fr 两种，rr/ff 仍按标识符处理（对照用例锁死）。",
 "BUG-23": "只调整分支次序；标量对象仍返回其存储地址。",
 "BUG-27": "只保证空批次不再抛 TypeError；「回调错误」归因口径未扩到其它 except 分支。",
 "BUG-28": "normalize 现在保留原风格宽度（2 空格进 2 空格出），不做跨风格换算；缺陷面是结构被压平。",
 "BUG-29": "只补 None 守卫并给出用法提示；hook 参数校验的其它分支未动。",
}


def main() -> int:
    intake = json.loads((HERE / "intake_map7.json").read_text(encoding="utf-8"))["mapping"]
    close = {r["bug"]: r for r in
             json.loads((HERE / "close_fixes7.out.json").read_text(encoding="utf-8"))}
    reg = (ROOT / "tests" / "test_polish_20260926_pass7.py").read_text(encoding="utf-8")
    pairs = {m["bug_id"]: m["task_id"] for m in intake if m.get("task_id")}

    # Split into entry blocks on the `## BUG-N` heads; everything before the first head is a
    # preamble and is left alone. Appending inside a block keeps earlier blocks byte-identical.
    text = BUGS_MD.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=## BUG-\d+ )", text)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    appended, skipped, out = [], [], [parts[0]]
    seen = set()
    for block in parts[1:]:
        bug = re.match(r"## (BUG-\d+) ", block).group(1)
        seen.add(bug)
        if bug not in pairs:
            out.append(block)
            continue
        if "### FIXED(verify=已完成)" in block:
            skipped.append(bug)
            out.append(block)
            continue
        if bug not in close or not close[bug]["green"]:
            sys.exit(f"REFUSE: {bug} 未走完 verify，不能追加 FIXED 段")
        n = int(re.search(r"BUG-(\d+)", bug).group(1))
        tests = re.findall(r"(?m)^def (test_bug%d_\w+)" % n, reg)
        if not tests:
            sys.exit(f"REFUSE: {bug} 没有反解到回归测试")
        tid = pairs[bug]
        section = ["", f"### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）",
                   f"- 修复单：`{tid}`（ns `bugs`），`claim → execute → submit → verify` 原始回复见 "
                   f"`.fist-polish-20260926/close_fixes7.out.json`；入账回复与 bug id 配对见 `intake_map7.json`",
                   f"- 锁死回归（{len(tests)} 个函数"
                   + ("，BUG-22 另有 7 条参数化展开" if n == 22 else "") + "）："
                   + "、".join(f"`tests/test_polish_20260926_pass7.py::{t}`" for t in tests),
                   f"- 复现依据：`repro_pass7.py` / `repro_pass7b.py` / `repro_pass7c.py` 与各自 `.out.json`；"
                   f"全量终态 `.fist-polish-20260926/pytest_final_sweep7.log`",
                   f"- 修复边界：{BOUNDARY.get(bug, '本单未声明额外边界。')}",
                   f"- 登记时间：{stamp}", ""]
        head, _, body = block.partition("\n")
        out.append(block.rstrip("\n") + "\n" + "\n".join(section[1:]))
        appended.append(bug)
    missing = sorted(set(pairs) - seen)
    if missing:
        sys.exit(f"REFUSE: bugs.md 里找不到这些条目: {missing}")
    BUGS_MD.write_text("".join(out), encoding="utf-8", newline="\n")
    print(f"appended={len(appended)} skipped_already={len(skipped)} -> {appended}")
    check = BUGS_MD.read_text(encoding="utf-8")
    print("FIXED sections now:", check.count("### FIXED(verify=已完成)"),
          "entries:", len(re.findall(r"(?m)^## BUG-\d+ ", check)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
