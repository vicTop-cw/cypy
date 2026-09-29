"""R3-推进 的 call_log 对账：按 `params_json.task_id` 前缀分组，不按标签、不按回忆。

自证三件：① 每个前缀的逐工具计数之和 == 该前缀总行数（分组没吞行）；
② `refused` 计数 == `refused_detail` 条数（拒收清单不是手数）；
③ 拿一个**必然不存在**的前缀当对照，必须数出 0 行 —— 否则这个过滤是恒真的。
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREFIXES = {"T0r73": "R3-推进（含 16 叶 + 8 支 + 根上卷）"}
NEEDLE_ABSENT = "T0r9ZZZ"


def main() -> int:
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    refuse: list = []
    out = {"grouped_by": "params_json.task_id 前缀（不按标签、不按回忆）", "stages": {},
           "queried_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    total_all = con.execute("select count(*) from call_log").fetchone()[0]
    for prefix, label in PREFIXES.items():
        rows = list(con.execute(
            "select tool, ok, ts, params_json from call_log where json_extract(params_json,'$.task_id') "
            "like ? order by id", (f"{prefix}%",)))
        by_tool: dict = {}
        refused_detail = []
        for tool, ok, ts, params in rows:
            try:
                tid = json.loads(params).get("task_id") or "?"
            except (TypeError, json.JSONDecodeError):
                tid = "?（params_json 不是合法 JSON）"
            slot = by_tool.setdefault(tool, {"ok": 0, "refused": 0})
            if ok:
                slot["ok"] += 1
            else:
                slot["refused"] += 1
                refused_detail.append({"tool": tool, "ts": ts, "task": tid})
        summed = sum(v["ok"] + v["refused"] for v in by_tool.values())
        if summed != len(rows):
            refuse.append(f"{prefix}：逐工具求和 {summed} != 总行数 {len(rows)}")
        refused_n = sum(v["refused"] for v in by_tool.values())
        if refused_n != len(refused_detail):
            refuse.append(f"{prefix}：refused 计数 {refused_n} != 明细条数 {len(refused_detail)}")
        out["stages"][f"{prefix} {label}"] = {
            "total": len(rows), "ok": len(rows) - refused_n, "refused": refused_n,
            "by_tool": by_tool, "refused_detail": refused_detail}
    absent = con.execute("select count(*) from call_log where json_extract(params_json,'$.task_id') "
                         "like ?", (f"{NEEDLE_ABSENT}%",)).fetchone()[0]
    if absent != 0:
        refuse.append(f"必然不存在的前缀 {NEEDLE_ABSENT} 数出 {absent} 行 ⇒ 过滤恒真，整份对账不作数")
    ns_rows = list(con.execute("select ns, count(*) from call_log group by ns order by 2 desc"))
    issue_up = con.execute("select count(*) from call_log where tool like '%issue_up%'").fetchone()[0]
    out.update({"log_rows_total": total_all, "control_absent_prefix_rows": absent,
                "by_ns": {r[0]: r[1] for r in ns_rows},
                "issue_up_tool_rows": issue_up,
                "issue_up_note": "本构建里 issue_up 不是工具名（0 行）：开单走 tasks 表，如实上报而不是谎称已用",
                "refuse": refuse})
    con.close()
    (HERE / "r3_advance_calllog_tally.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse,
                      "stages": {k: {"total": v["total"], "ok": v["ok"], "refused": v["refused"],
                                     "tools": len(v["by_tool"])} for k, v in out["stages"].items()},
                      "total_all": total_all, "control": absent,
                      "issue_up_rows": issue_up}, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
