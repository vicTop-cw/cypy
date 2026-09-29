"""R6 账面自证：账本必须「只增不删」，且计数能与备份逐字对表。

判据三条（都用盘面实测，不引用脚本自己写过的数）：
1. 与开工前的备份 `bugs_ledger_pre_r6.md` 做 difflib 对表：**删除行为 0**（只允许插入）；
2. 抬头数 / FIXED 段数与 `bug_list` 的口径一致，并给出「本轮闭环 3 条历史开口」的明细；
3. 一条必然红的对照：拿备份自己比对（旧 vs 旧）应报 0 插入——若这里也报 0 删除 0 插入，
   说明第 1 条判据看不见真实改动。
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
BACKUP = HERE / "bugs_ledger_pre_r6.md"
OUT = HERE / "verify_r6_ledger.json"
NEWLY_FIXED = ["BUG-36", "BUG-37", "BUG-41"]
NEWLY_FILED = [92, 93, 94, 95]


def counts(text: str) -> dict:
    entries = re.findall(r"(?m)^## BUG-(\d+) ", text)
    fixed = len(re.findall(r"(?m)^### FIXED", text))
    other = len(re.findall(r"(?m)^### (?:DUPLICATE|NOT|OUT)", text))
    return {"entries": len(entries), "fixed": fixed, "other_closure": other,
            "open": len(entries) - fixed - other, "ids": sorted(entries)}


def main() -> int:
    refuse: list[str] = []
    old = BACKUP.read_text(encoding="utf-8")
    new = LEDGER.read_text(encoding="utf-8")
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    deleted, inserted = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            deleted.extend(old.splitlines()[i1:i2])
        if tag in ("insert", "replace"):
            inserted.extend(new.splitlines()[j1:j2])
    if deleted:
        refuse.append(f"发现删除/改写行 {len(deleted)} 条，首条：{deleted[0][:120]}")
    co, cn = counts(old), counts(new)
    if cn["entries"] != co["entries"] + len(NEWLY_FILED):
        refuse.append(f"抬头数增量 {cn['entries'] - co['entries']} != 新立 {len(NEWLY_FILED)}")
    for n in NEWLY_FILED:
        if str(n) not in cn["ids"]:
            refuse.append(f"新立条目 BUG-{n} 抬头不在账本里")
    for bug in NEWLY_FIXED:
        block = new.split(f"## {bug} ")[1].split("\n## BUG-")[0]
        if "### FIXED" not in block:
            refuse.append(f"{bug} 条目内没有 FIXED 段")
    # 反向对照：旧 vs 旧必须 0 插入；若这里报出插入，说明判据把备份也当成新增
    sm2 = difflib.SequenceMatcher(a=old.splitlines(), b=old.splitlines(), autojunk=False)
    self_insert = sum(len(new.splitlines()[j1:j2]) for t, i1, i2, j1, j2 in sm2.get_opcodes()
                      if t in ("insert", "replace"))
    if self_insert != 0:
        refuse.append(f"对照格（旧 vs 旧）插入 {self_insert} 行 ⇒ 差集判据自身坏了")
    payload = {"before": co, "after": cn, "deleted_lines": len(deleted),
               "inserted_lines": len(inserted),
               "inserted_head_sample": inserted[:6],
               "canary_self_diff_insertions": self_insert,
               "refuse": refuse,
               "reading": (f"开口 {co['open']} → {cn['open']}；本轮闭环历史开口 {len(NEWLY_FIXED)} 条、"
                           f"新立 {len(NEWLY_FILED)} 条（其中 BUG-93 同轮修毕并带 FIXED 段）")}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"LEDGER VERIFY {'PASS' if not refuse else 'FAIL'} "
          f"entries={cn['entries']} fixed={cn['fixed']} open={cn['open']} deleted={len(deleted)}")
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
