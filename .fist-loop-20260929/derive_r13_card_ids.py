"""反解本轮四张卡的「主张 → 编号 → 状态」对照，并落一份可复跑的证据。

编号只能从台账的 `reported_key` 行反解：入账回执 json 会被复跑覆盖（本轮就发生过一次），
而 `^## BUG-NN` 的正则计数与按 id 建字典的计数还差 1（重复号，另立 BUG-140）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
CARDS = [
    ("R13-CONTAINER-ELEMENT-NO-CHECK", "BUG-137"),
    ("R13-NESTED-ALIAS-NOT-EXPANDED", "BUG-138"),
    ("R13-UNION-SHAPED-ALIAS-NO-SUBST", "BUG-139"),
    ("R13-GENERIC-TYPE-ALIAS-NO-SUBST", "BUG-136"),
    ("R13-LEDGER-DUPLICATE-BUG-ID", "BUG-140"),
]


def main() -> int:
    led = LEDGER.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=## BUG-\d+)", led)
    blocks = {}
    for b in parts:
        if b.startswith("## BUG-"):
            bid = re.match(r"## (BUG-\d+)", b).group(1)
            blocks.setdefault(bid, b)  # 重复号取第一条：本件同时把"重复"这件事印出来
    bad = []
    for key, want in CARDS:
        hit = [bid for bid, body in blocks.items() if f"reported_key: {key}" in body]
        one = hit == [want]
        body = blocks.get(want, "")
        closed = bool(re.search(r"(?m)^### FIXED", body))
        amended = bool(re.search(r"(?m)^### 改判", body))
        state = "FIXED" if closed else ("AMENDED-OPEN" if amended else "OPEN")
        print(f"{key} -> {want} {state} (one_block={one})")
        if not one or want not in hit:
            bad.append(f"{key} 反解到 {hit}")
    ids_all = re.findall(r"(?m)^## (BUG-\d+)", led)
    dup = sorted({i for i in ids_all if ids_all.count(i) > 1})
    print(f"HEADERS {len(ids_all)} UNIQUE {len(set(ids_all))} DUP {dup}")
    print(
        f"CONCLUSION r13_card_ids cards={len(CARDS)} mismatches={bad} "
        f"duplicate_ids={dup} rc={0 if not bad else 1}"
    )
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
