#!/usr/bin/env python3
"""Diff examples/*.out against the pre-ruling snapshot (golden_before_float/).

Used to prove the float=double re-registration only moved float-derived digits: every changed
line is reported side by side so a human can see there is no unrelated churn, and so the count
of changed files is recomputable rather than asserted in prose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")
BEFORE = HERE / "golden_before_float"


def main() -> int:
    rows, changed = [], []
    for out in sorted((ROOT / "examples").glob("*.out")):
        old = BEFORE / out.name
        new = out.read_text(encoding="utf-8", errors="replace")
        if not old.exists():
            rows.append({"file": out.name, "state": "NEW-golden（快照里没有）"})
            changed.append(out.name)
            continue
        before = old.read_text(encoding="utf-8", errors="replace")
        if before == new:
            rows.append({"file": out.name, "state": "unchanged"})
            continue
        bl, nl = before.splitlines(), new.splitlines()
        diffs = [(i + 1, bl[i] if i < len(bl) else "<缺行>", nl[i] if i < len(nl) else "<缺行>")
                 for i in range(max(len(bl), len(nl)))
                 if (bl[i] if i < len(bl) else None) != (nl[i] if i < len(nl) else None)]
        rows.append({"file": out.name, "state": f"changed {len(diffs)} 行", "lines": diffs})
        changed.append(out.name)
    gone = sorted(p.name for p in BEFORE.glob("*.out") if not (ROOT / "examples" / p.name).exists())
    print(json.dumps({"changed_files": changed, "changed_count": len(changed),
                      "vanished": gone, "rows": [r for r in rows if r["state"] != "unchanged"]},
                     ensure_ascii=False, indent=1))
    (HERE / "golden_float_diff.json").write_text(
        json.dumps({"changed": changed, "gone": gone, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"changed={len(changed)} vanished={len(gone)} -> {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
