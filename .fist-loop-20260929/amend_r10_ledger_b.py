"""账本更正（第二批）：本轮卡片正文里的 file:line 锚漂移，逐条指认实测行号。

只增不改；锚点必须恰好命中一次，否则拒绝动账本。
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "amend_r10_ledger_b.json"
NEEDLE = "- reported_key: R10-CALLSITE-CHECKER"
MARK = "### AMENDMENT — 锚点更正"

SECTION = (
    "\n" + MARK + "（本条目正文与标题行一字未改）\n"
    "- 本单 detail 与本轮 `### FIXED` 段里写的三处行号是落码前的心算值，实测漂移如下"
    "（定位方式：按代码文本 needle 在全文件里取行号，核验件 "
    "`.fist-loop-20260929/verify_r10_report.json` 的 `anchors` 栏）：\n"
    "  · `cypyc/parser/parser.py` 的 `Call.type_args` ⇒ 实测 **650-659**（原写 650-658）；\n"
    "  · `cypyc/analyzer/type_checker.py` 的 `_bind_explicit_type_args` ⇒ 实测 **1272-1301**（原写 1273-1303）；\n"
    "  · 被引用的 `SYNTAX/33-type-constraints-subtypes-dispatch.md` P-1.8 ⇒ 实测 **:518**（原写 :519）。\n"
    "- 同批更正 BUG-120 卡片正文：`trait` 抽象方法范例的实测行号是 `SYNTAX/11-generics.md:47`（`trait Container<T>:`）"
    "与 **:93**（`def sort<T: Comparable>`，原写 :89-91）。\n"
    "- 定性、严重度、判据与结论均不变；本段只改「锚到哪一行」，报告 §4.2 已同步为实测区间。\n"
)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = LEDGER.read_text(encoding="utf-8")
    rep = {"started_z": started, "needle_count": before.count(NEEDLE)}
    if rep["needle_count"] != 1:
        rep["refused"] = "锚点命中数不是 1 ⇒ 不动账本"
    else:
        bs = before.index(NEEDLE)
        nxt = before.find("\n## BUG-", bs)
        insert_at = nxt if nxt != -1 else len(before)
        if MARK in before[bs:insert_at]:
            rep["skipped"] = "已在盘上（幂等守卫）"
        else:
            out = before[:insert_at] + SECTION + before[insert_at:]
            tmp = LEDGER.with_suffix(".md.tmp_amend_b")
            tmp.write_text(out, encoding="utf-8", newline="\n")
            os.replace(tmp, LEDGER)
            after = LEDGER.read_text(encoding="utf-8")
            rep.update({
                "appended": True,
                "prefix_identical": after[:bs] == before[:bs],
                "header_untouched": bool(re.search(r"(?m)^## BUG-118 \[[^\]]+\] \[high\] OPEN$", after)),
                "grew_by": len(after.encode("utf-8")) - len(before.encode("utf-8")),
                "amendment_sections_now": len(re.findall(r"(?m)^### AMENDMENT", after)),
                "headers_now": len(re.findall(r"(?m)^## BUG-\d+ ", after)),
            })
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CONCLUSION", json.dumps(rep, ensure_ascii=False))
    return 0 if rep.get("appended") or rep.get("skipped") else 1


if __name__ == "__main__":
    main()
