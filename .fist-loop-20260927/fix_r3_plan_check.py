#!/usr/bin/env python3
"""R3-修复：把台账里的"每条都有 X"型主张算成可门禁的布尔值。

`report_kit` 的门禁只会解析点路径 + min/equals/truthy，看不懂"per_bug 里每一行都含某字段"。
与其把这类主张写成恒真的 `per_bug >= 6`（那正是"判据空转"的形状），不如先把它算成一个键：

- `all_have_rejected_alternative`：六件都记了被放弃的替代修法（且不是空话，长度阈值一起给）；
- `all_have_pos_lock` / `all_paired`：每组都有正例锁与配对对照（对照可以是同一条锁里的双向断言）；
- `task_ids_match_filed`：台账里的 task_id 与 R3-寻虫 入账件 `hunt_r3_filed.json` 双向相等
  （防我手打错号——本轮真的打穿过一次 `T0e66`）；
- `flip_flags_match_evidence`：台账自报的 flipped 与 `fix_r3_evidence.json` 的 ok 旗逐件一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "fix_r3_plan.json"
MIN_ALT_CHARS = 24

CASE_OF = {"BUG-55": "C1", "BUG-56": "C3", "BUG-57": "C4",
           "BUG-58": "C5", "BUG-59": "C6", "BUG-60": "C8"}


def main() -> int:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    rows = plan["per_bug"]
    filed = json.loads((HERE / "hunt_r3_filed.json").read_text(encoding="utf-8"))
    ev = json.loads((HERE / "fix_r3_evidence.json").read_text(encoding="utf-8"))

    refuse: list = []
    pairs = {x["rpc_bug_id"]: x["task_id"] for x in filed["filed"]}
    plan_pairs = {r["bug"]: r["task_id"] for r in rows}
    task_ids_match_filed = plan_pairs == pairs
    if not task_ids_match_filed:
        refuse.append(f"台账 task_id 与入账件不等价：台账={plan_pairs} 入账={pairs}")

    all_have_rejected = all(len(r.get("rejected_alternative", "")) >= MIN_ALT_CHARS for r in rows)
    if not all_have_rejected:
        refuse.append(f"有缺陷没写『被放弃的替代修法』（阈值 {MIN_ALT_CHARS} 字）")
    all_have_declared = all(r.get("declared_face") for r in rows)
    all_have_pos = all(len(r.get("pos_locks", [])) >= 1 for r in rows)
    all_paired = all(len(r.get("ctl_locks", [])) >= 1 or r.get("paired_inside") for r in rows)
    flip_flags_match = all(
        # 台账的 flipped 只看"原主张的现形判据还成不成立"；C5/C8 的 ok 是"声明侧复算形状对"，
        # 两者不是一回事（那两件刻意仍现形），所以这里只与 after_rc==1 对齐。
        bool(r.get("flipped")) == (ev["flips"][CASE_OF[r["bug"]]]["after_rc"] == 1)
        for r in rows
    )
    if not flip_flags_match:
        refuse.append("台账自报的 flipped 与翻转复算件不一致（要么台账撒谎要么判据漂移）")

    plan["derived"] = {
        "task_ids_match_filed": task_ids_match_filed,
        "all_have_rejected_alternative": all_have_rejected,
        "all_have_declared_face": all_have_declared,
        "all_have_pos_lock": all_have_pos,
        "all_paired": all_paired,
        "flip_flags_match_evidence": flip_flags_match,
        "rejected_alternative_min_chars": MIN_ALT_CHARS,
    }
    plan["refuse"] = refuse
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8", newline="\n")
    print(json.dumps({"derived": plan["derived"], "refuse": refuse}, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
