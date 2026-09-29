#!/usr/bin/env python3
"""R2-打磨 的作用域化 lint：只判**本轮亲笔行**，存量债不记在本单名下（口径同 R2-修复）。

本环的形状是"只删不加"，所以判据也照这个形状来：
- 新增档 `tests/test_polish_20260927_r2.py` 全文是亲笔 ⇒ 整档判（E501>100 / 尾随空白 / 制表符）；
- 两档产品码：与仓库外快照逐行对齐后**新增行数必须为 0**，存量违例只许减不许增；
- 配一条"必然违例"自检：120 列的赋值行必须被抓到（恒绿判据不算判据）。
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
SNAP = Path(r"E:/IDEProjects/AI/_cypy_snapshots/pre_polish_r2")
OUT = ROOT / ".fist-loop-20260927" / "polish_r2_lint.json"
LIMIT = 100


def violations(text: str) -> list:
    out = []
    for i, ln in enumerate(text.split("\n"), 1):
        stripped = ln.rstrip("\r")
        if len(stripped) > LIMIT:
            out.append(f"E501@{i}:{len(stripped)}")
        if stripped.endswith(" "):
            out.append(f"W291@{i}")
        if "\t" in stripped:
            out.append(f"W191@{i}")
        if stripped.strip() == "" and stripped:
            out.append(f"W293@{i}")
    return out


def main() -> int:
    refuse: list = []
    doc: dict = {"limit": LIMIT, "refuse": refuse}

    authored = "tests/test_polish_20260927_r2.py"
    v = violations((ROOT / authored).read_text(encoding="utf-8"))
    doc["authored_file"] = {"rel": authored, "violations": v, "lines_checked": len(
        (ROOT / authored).read_text(encoding="utf-8").split("\n"))}
    if v:
        refuse.append(f"亲笔新档违例：{v[:8]}")

    for rel in ("cypyc/codegen/cython_generator.py", "cypyc/analyzer/scope_analyzer.py"):
        before = (SNAP / rel).read_text(encoding="utf-8").split("\n")
        after = (ROOT / rel).read_text(encoding="utf-8").split("\n")
        added = removed = 0
        for line in difflib.ndiff(before, after):
            if line.startswith("+ "):
                added += 1
            elif line.startswith("- "):
                removed += 1
        v_before = violations("\n".join(before))
        v_after = violations("\n".join(after))
        doc.setdefault("product_files", {})[rel] = {
            "added_lines": added,
            "removed_lines": removed,
            "debt_before": len(v_before),
            "debt_after": len(v_after),
        }
        if added != 0:
            refuse.append(f"{rel} 本环声称只删不加，实测新增 {added} 行")
        if len(v_after) > len(v_before):
            refuse.append(f"{rel} 存量违例数上升：{len(v_before)} -> {len(v_after)}")

    probe = "x = 1\n" + "a = '" + "y" * 130 + "'\n"
    caught = violations(probe)
    doc["selftest"] = "selfprobe-caught" if any(t.startswith("E501@2:") for t in caught) else "SELFPROBE-MISSED"
    if doc["selftest"] != "selfprobe-caught":
        refuse.append("lint 自检没抓到必然违例（120 列赋值行）⇒ 判据恒绿")
    clean = violations("x = 1\ny = 2\n")
    doc["selftest_negative"] = "clean-not-flagged" if not clean else f"FALSE-POSITIVE:{clean}"
    if clean:
        refuse.append(f"lint 自检误抓干净样例：{clean}")

    doc["authored_lines_checked"] = doc["authored_file"]["lines_checked"]
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(doc, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    raise SystemExit(main())
