"""R6 收口第二批：环步骤 tick（用真名）、剩余叶按账面处置、根上卷读数、双向对账。

为什么要它：上一批把 6 条叶走完 Omega 链后，`loop_tick` 全被拒（`loop not found:
cypy-loop-20260929`）—— 那是我传错了身份键：环注册名是 `cypy-selfdrive-20260929`，
而 ns 是 `cypy-loop-20260929`。两个键混用会静默留下「环从没走过」的账面。
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r6_ring2.json"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-20260929"
DONE_LEAVES = {"T0r112.1.1", "T0r112.1.2", "T0r112.1.3", "T0r112.2.1", "T0r112.2.2", "T0r112.2.3"}
REJECT_REASON = ("R6 半径内无对应交付。账本剩余开口 BUG-34/40/43/49/50/52/54/65/70/92/94/95 交下一轮"
                 "按同一组合环继续；本叶不留悬空指派，故打回而非静默保留。")


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=180)
    report: dict = {"started_utc": utcnow(), "ticks": [], "rejections": {}, "root": {},
                    "refusals": [], "tree": {}}

    for mode in ("advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"):
        res = c.call("loop_tick", {"name": LOOP_NAME, "_omit_defaults": True,
                                   "current_test_count": 2119 + 21,
                                   "current_open_bug_count": 12,
                                   "blocked_tasks": 0,
                                   "project_health_grade": "attention"})
        ok = isinstance(res, dict) and "error" not in json.dumps(res)[:40] and "__error__" not in res
        if not ok:
            report["refusals"].append({"node": LOOP_NAME, "tool": "loop_tick",
                                       "reply": json.dumps(res, ensure_ascii=False)[:200]})
        report["ticks"].append({"mode": mode, "ok": ok,
                                "reply": json.dumps(res, ensure_ascii=False)[:240]})

    tree = c.call("list", {"namespace": NS, "limit": 200})
    rows = tree if isinstance(tree, list) else (tree.get("tasks") or [])
    by_status: dict = {}
    pending_leaves = []
    for t in rows:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        if t["status"] == "待领取" and t.get("is_leaf"):
            pending_leaves.append(t["id"])
    report["tree"] = {"rows": len(rows), "by_status": by_status, "pending_leaves": len(pending_leaves)}

    for leaf in pending_leaves:
        res = c.call("reject", {"task_id": leaf, "reason": REJECT_REASON, "by": "verifier"})
        refused = isinstance(res, dict) and "__error__" in res
        report["rejections"][leaf] = "refused" if refused else "ok"
        if refused:
            report["refusals"].append({"node": leaf, "tool": "reject",
                                       "reply": json.dumps(res, ensure_ascii=False)[:200]})

    for node in ("T0r112",):
        res = c.call("get", {"task_id": node})
        report["root"][node] = {"status": (res or {}).get("status"),
                                "assignee": (res or {}).get("assignee"),
                                "reply_keys": sorted(res) if isinstance(res, dict) else None}
    # 根上卷成「待验收」后才有可能归档；归档是人类面工具（archive），代理面不越权 ⇒ 只读数。
    c.close()

    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    ns_counts = list(con.execute(
        "select status, count(*) from tasks where ns=? group by status", (NS,)))
    tools = list(con.execute(
        "select tool, sum(ok=1), sum(ok=0) from call_log "
        "where json_extract(params_json,'$.task_id') like 'T0r112%' or json_extract(params_json,'$.name')=? "
        "group by tool", (LOOP_NAME,)))
    report["recheck"] = {
        "tasks_by_status": dict(ns_counts),
        "call_log_this_round": {t: {"ok": a, "refused": b} for t, a, b in tools},
        "call_log_rows": sum(a + b for _t, a, b in tools),
        "queried_at_utc": utcnow(),
    }
    if report["recheck"]["call_log_rows"] <= 0:
        report["refusals"].append({"node": "(对账)", "tool": "sqlite",
                                   "reply": "本轮 T0r112% 调用数 0 ⇒ 过滤恒假"})
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("ticks", "tree", "root", "recheck")},
                     ensure_ascii=False, indent=1)[:2200])
    print("REFUSALS", len(report["refusals"]))
    for r in report["refusals"][:6]:
        print("  -", r["tool"], r["reply"][:130])
    return 0



if __name__ == "__main__":
    sys.exit(main())
