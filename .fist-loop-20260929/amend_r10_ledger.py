"""账本更正：给 BUG-123 追加 `### AMENDMENT` 段，把「单跑绿」的读数指认到有文件证据的那一次。

只增不改（原正文与标题行逐字保留）；写后校验前缀一致 + 锚点计数。
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
OUT = HERE / "amend_r10_ledger.json"
NEEDLE = "- reported_key: R10-JUDGE-GETSOURCE-SKew"
MARK = "### AMENDMENT — 追加更正"

SECTION = (
    "\n" + MARK + "（本条目正文与标题行一字未改）\n"
    "- 更正对象：本条 detail 里那句「同一条单跑 `1 passed in 0.08s`」—— 那次读数只出现在终端，"
    "没有落盘证据件，按本项目口径不可复核，故不作为证据引用。\n"
    "- 替代证据（有文件）：`python -X utf8 -m pytest "
    "tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions "
    "-p no:cacheprovider` ⇒ 逐字 `1 passed in 0.34s`，见 "
    "`.fist-loop-20260929/logs/r10_bug26_single_a1.log`（该次 rc=0）。\n"
    "- 结论不变：缺陷仍成立（a2 的 `assert ([])` 与冻结后的 2235/2241 passed 两轮全量都在 "
    "`logs/r10_pytest_a2.log`、`logs/r10_pytest_a3.log`、`logs/r10_pytest_a4.log`），"
    "本条只改「用哪份件作证」，不改定性与严重度。\n"
    "- 报告同处已同步：`reports/2026-09-29/T0r116-cypy-selfdrive-r10-report.md` §5.5。\n"
)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = LEDGER.read_text(encoding="utf-8")
    rep = {"started_z": started, "needle_count": before.count(NEEDLE)}
    if rep["needle_count"] != 1:
        rep["refused"] = f"锚点命中 {rep['needle_count']} 次（必须恰好 1）⇒ 不改账本"
    else:
        block_start = before.index(NEEDLE)
        nxt = before.find("\n## BUG-", block_start)
        insert_at = nxt if nxt != -1 else len(before)
        seg = before[block_start:insert_at]
        if MARK in seg:
            rep["skipped"] = "AMENDMENT 段已在盘上（幂等守卫）"
        else:
            out = before[:insert_at] + SECTION + before[insert_at:]
            tmp = LEDGER.with_suffix(".md.tmp_amend")
            tmp.write_text(out, encoding="utf-8", newline="\n")
            os.replace(tmp, LEDGER)
            after = LEDGER.read_text(encoding="utf-8")
            rep.update({
                "appended": True,
                "header_untouched": bool(re.search(r"(?m)^## BUG-123 \[[^\]]+\] \[medium\] OPEN$", after)),
                "prefix_identical": after[:block_start] == before[:block_start],
                "grew_by": len(after.encode("utf-8")) - len(before.encode("utf-8")),
                "amendment_sections_now": len(re.findall(r"(?m)^### AMENDMENT", after)),
                "headers_now": len(re.findall(r"(?m)^## BUG-\d+ ", after)),
            })
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CONCLUSION", json.dumps(rep, ensure_ascii=False))
    return 0 if rep.get("appended") or rep.get("skipped") else 1


if __name__ == "__main__":
    main()
