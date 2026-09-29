"""把台账里 4 个畸形 UTC 段落戳（`2026-09-29T2026-09-29T08:25:31ZZ`）修回合法形状。

成因：`amend_r11_ledger_bugs.py` 的段落模板写的是 `2026-09-29T{ts}Z）`，而 `{ts}` 本身已是
完整 `…T…Z` ⇒ 日期被裹两层、尾巴两个 Z。这既是"段落戳别手敲本地钟点"的同族失误，
也是 R12 那次 `--refresh` 自证被整档脏检打红的真因（门看见的是别轮的坏戳，不是自己的）。

纪律：只动戳串，别的字节一律不许变 —— 自证是「逐行 diff 只落在含坏戳的那几行」＋
「抬头/开口/FIXED 三个计数不变」＋「修完全档坏戳与未插值占位归零」，任一条不符就不落盘。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
BAD = re.compile(r"(\d{4}-\d\d-\d\dT)\1(\d{2}:\d\d:\d\d)ZZ")
RESIDUE = re.compile(r"\{(?:CASES|FP|LOCKS|CONS_SRC|CONS_DECL)\}")


def counts(text: str) -> dict:
    blocks = [b for b in re.split(r"(?m)^(?=## BUG-)", text) if b.startswith("## BUG-")]
    open_blocks = [b for b in blocks if not re.search(r"(?m)^### (FIXED|DUPLICATE)", b)]
    return {"headers": len(blocks), "open": len(open_blocks),
            "fixed": len(re.findall(r"(?m)^### FIXED", text))}


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    bad_lines = [ln for ln in src.splitlines() if BAD.search(ln)]
    out, n = BAD.subn(r"\1\2Z", src)
    rep = {"before_counts": counts(src), "after_counts": counts(out),
           "bad_occurrences": len(BAD.findall(src)), "replaced": n,
           "bad_lines_before": len(bad_lines), "distinct_stamps": sorted({m.group(2) for m in BAD.finditer(src)})}
    # 逐行 diff 必须只落在坏戳行上
    a, b = src.splitlines(), out.splitlines()
    assert len(a) == len(b), f"行数变了 {len(a)}→{len(b)} ⇒ 停手"
    changed = [i for i, (x, y) in enumerate(zip(a, b), 1) if x != y]
    rep["changed_lines"] = changed
    rep["changed_all_bad"] = all(BAD.search(a[i - 1]) for i in changed)
    rep["after_bad"] = len(BAD.findall(out))
    rep["after_residue"] = len(RESIDUE.findall(out))
    ok = (rep["changed_all_bad"] and rep["after_bad"] == 0 and rep["before_counts"] == rep["after_counts"]
          and rep["after_residue"] == 0 and rep["bad_occurrences"] == rep["replaced"] == n)
    if not ok:
        (HERE / "logs" / "r12_stamp_repair.refused.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print("REFUSED", json.dumps(rep, ensure_ascii=False)[:600])
        return 1
    LEDGER.with_name("bugs.md.pre_stamp_repair").write_text(src, encoding="utf-8", newline="\n")
    tmp = LEDGER.with_name("bugs.md.stamp.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    assert tmp.read_text(encoding="utf-8") == out, "回读不一致 ⇒ 停手"
    tmp.replace(LEDGER)
    rep["after_file_verified"] = (BAD.findall(LEDGER.read_text(encoding="utf-8")),
                                  RESIDUE.findall(LEDGER.read_text(encoding="utf-8")))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"CONCLUSION replaced={n} changed_lines={changed} after_bad=0 after_residue=0 "
          f"counts={json.dumps(rep['after_counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
