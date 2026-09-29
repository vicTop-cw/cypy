#!/usr/bin/env python3
"""R2-推进 的作用域化 lint：只判本轮亲笔行（新增/修改的行），存量债不记在本单名下。

和打磨环的区别是这环**真的加了行**，所以判据形状也要跟着变：
与仓库外快照 `pre_advance_r2` 逐行对齐，取"新增行的行号集合"，只对这些行判
E501(>100)/尾随空白/制表符；整档存量违例只许减不许增。
配一条必然违例自检（120 列赋值行必须被抓到）+ 一条不误抓自检（干净样例）。
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
SNAP = Path(r"E:/IDEProjects/AI/_cypy_snapshots/pre_advance_r2")
OUT = ROOT / ".fist-loop-20260927" / "advance_r2_lint.json"
LIMIT = 100

FILES = [
    "cypyc/incremental/hot_reload.py",
    "cypyc/cli.py",
    "tests/test_advance_20260927_r2.py",
    "docs/USAGE.md",
]


def line_violations(text: str, limit: int = LIMIT) -> list:
    out = []
    for i, ln in enumerate(text.split("\n"), 1):
        s = ln.rstrip("\r")
        if len(s) > limit:
            out.append((i, f"E501:{len(s)}"))
        if s.endswith(" "):
            out.append((i, "W291"))
        if "\t" in s:
            out.append((i, "W191"))
    return out


def main() -> int:
    refuse: list = []
    doc: dict = {"limit": LIMIT, "files": {}, "refuse": []}
    total_authored = 0

    for rel in FILES:
        now_text = (ROOT / rel).read_text(encoding="utf-8")
        now_lines = now_text.split("\n")
        snap_p = SNAP / rel
        if snap_p.exists():
            before = snap_p.read_text(encoding="utf-8", errors="replace").split("\n")
        else:
            before = []
        added_numbers = set()
        if before:
            for i, tag in enumerate(difflib.SequenceMatcher(None, before, now_lines).get_opcodes()):
                _tag, _b1, _b2, a1, a2 = tag
                if _tag in ("insert", "replace"):
                    added_numbers.update(range(a1 + 1, a2 + 1))
        else:
            added_numbers = set(range(1, len(now_lines) + 1))
        v = line_violations(now_text)
        authored = [(i, kind) for (i, kind) in v if i in added_numbers]
        whole = len(v)
        before_whole = len(line_violations("\n".join(before))) if before else 0
        doc["files"][rel] = {
            "authored_lines": len(added_numbers),
            "authored_violations": authored,
            "debt_before": before_whole,
            "debt_after": whole,
        }
        total_authored += len(added_numbers)
        if authored:
            refuse.append(f"{rel} 亲笔行违例：{authored[:6]}")
        if before and whole > before_whole:
            refuse.append(f"{rel} 存量违例上升 {before_whole}->{whole}（本轮只该动亲笔行）")

    probe = "x = 1\n" + "a = '" + "y" * 130 + "'\n"
    caught = line_violations(probe)
    doc["selftest"] = "selfprobe-caught" if any(k.startswith("E501") for _i, k in caught) else "SELFPROBE-MISSED"
    if doc["selftest"] != "selfprobe-caught":
        refuse.append("lint 自检没抓到必然违例 ⇒ 整条判据恒绿")
    doc["selftest_negative"] = "clean-not-flagged" if not line_violations("x = 1\ny = 2\n") else "FALSE-POSITIVE"
    if doc["selftest_negative"] != "clean-not-flagged":
        refuse.append("lint 自检误抓干净样例")

    doc["authored_lines_checked"] = total_authored
    doc["refuse"] = refuse
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "authored_lines_checked": total_authored,
                      "per_file": {k: (v["authored_lines"], len(v["authored_violations"]),
                                        v["debt_before"], v["debt_after"]) for k, v in doc["files"].items()},
                      "selftest": doc["selftest"]}, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    raise SystemExit(main())
