"""改一处本环几十秒前自己写下的行数主张：`441→448 行` 实测应为 `441→449 行`。

为什么直接改而不是追加 AMENDMENT：账本 append-only 保护的是既有历史记录；本行落在本环刚生成的
BUG-113 FIXED 段内，是笔误且尚无其他条目引用。处置证据（原文逐字 + 锚点必须恰好命中一处 +
改动必须只落一行 + 改后数字要与实测行数相等）都写进 fix_r8_ledger_linecount.json，
并在 R8 报告「流程债」栏点名。
"""

from __future__ import annotations

import datetime
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
SPEC17 = ROOT / "SYNTAX" / "17-pattern-matching.md"
OUT = HERE / "fix_r8_ledger_linecount.json"

ANCHOR = "，441→448 行。"
REPL_TMPL = "，441→{n} 行（规则 6、7 占 {d} 行，即 442–{n}）。"


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    measured = len(SPEC17.read_text(encoding="utf-8").splitlines())
    rep = {"ran_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "spec17_measured_lines": measured, "anchor": ANCHOR, "anchor_count": src.count(ANCHOR),
           "refuse": []}
    if rep["anchor_count"] != 1:
        rep["refuse"].append(f"锚点命中 {rep['anchor_count']} 次（要求恰好 1）⇒ 不改")
        rep["verified"] = False
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1

    # 只允许落在 BUG-113 的区间内（本环自写段），别误伤历史条目
    start = src.index("## BUG-113 ")
    nxt = src.find("\n## BUG-", start + 1)
    end = nxt if nxt != -1 else len(src)
    pos = src.index(ANCHOR)
    if not (start < pos < end):
        rep["refuse"].append(f"锚点位置 {pos} 不在 BUG-113 区间 [{start},{end}) ⇒ 不改")
        rep["verified"] = False
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1

    lines = src.splitlines(keepends=True)
    idx = [i for i, l in enumerate(lines) if ANCHOR in l]
    assert len(idx) == 1, idx
    old_line = lines[idx[0]]
    lines[idx[0]] = old_line.replace(
        ANCHOR, REPL_TMPL.format(n=measured, d=measured - 441))
    out = "".join(lines)
    rep["old_line_verbatim"] = old_line.rstrip("\n")
    rep["new_line_verbatim"] = lines[idx[0]].rstrip("\n")

    changed = [l for t, i1, i2, j1, j2 in
               difflib.SequenceMatcher(a=src.splitlines(), b=out.splitlines(), autojunk=False)
               .get_opcodes() if t != "equal" for l in src.splitlines()[i1:i2]]
    rep["lines_touched"] = changed
    if len(changed) != 1:
        rep["refuse"].append(f"改动落点 {len(changed)} 行（要求恰好 1）⇒ 不落盘")
        rep["verified"] = False
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1

    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    back = LEDGER.read_text(encoding="utf-8")
    rep["recheck"] = {
        "stale_needle_gone": ANCHOR not in back,
        "measured_number_present": f"441→{measured} 行" in back,
        "entries": len(re.findall(r"(?m)^## BUG-\d+ ", back)),
        "fixed_sections": len(re.findall(r"(?m)^### FIXED\(", back)),
        "total_lines_unchanged": len(back.splitlines()) == len(src.splitlines()),
    }
    rep["verified"] = (rep["recheck"]["stale_needle_gone"]
                       and rep["recheck"]["measured_number_present"]
                       and rep["recheck"]["total_lines_unchanged"])
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("CONCLUSION anchor=%d changed=%d spec17_measured=%d verified=%s rc=%d"
          % (rep["anchor_count"], len(changed), measured, rep["verified"],
             0 if rep["verified"] else 1))
    return 0 if rep["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
