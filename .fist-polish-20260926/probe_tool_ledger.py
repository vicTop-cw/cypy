#!/usr/bin/env python3
"""Turn the server's own `call_log` table into the §四 tool-row reconciliation.

The report should not claim "工具都用上了" from my memory. `call_log` is written by the server for
every tools/call it accepts, so per-tool counts (and per-tool failures) come from there instead —
read-only, and rows are bounded by this isolated DB (server cwd = Cypy root).
Rows the server never logs (client-side JSON-RPC errors such as the empty-artifacts -32000) are
counted separately from my own probe artifacts, so a 0 in this table is not read as "never attempted".
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DB = os.path.join(ROOT, "fist-mbt.db")
BRIEF_ROWS = ["publish", "claim", "task_plan_deep", "execute", "submit", "verify", "archive",
              "heartbeat", "report_bug", "bug_list", "output_validate", "list", "get", "issue_scan"]

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True)
con.row_factory = sqlite3.Row
rows = list(con.execute("select tool, ok, ns, ts from call_log"))
ns_seen = sorted({r["ns"] for r in rows if r["ns"]})
con.close()

per = {}
for r in rows:
    d = per.setdefault(r["tool"], {"calls": 0, "failed": 0, "ns": set()})
    d["calls"] += 1
    d["failed"] += 0 if str(r["ok"]) == "1" else 1
    d["ns"].add(r["ns"] or "")
for d in per.values():
    d["ns"] = sorted(d["ns"])

out = {
    "db": "E:/IDEProjects/AI/Cypy/fist-mbt.db",
    "read_mode": "sqlite3 mode=ro",
    "table": "call_log",
    "total_rows": len(rows),
    "first_ts": min(r["ts"] for r in rows) if rows else None,
    "last_ts": max(r["ts"] for r in rows) if rows else None,
    "ns_seen": ns_seen,
    "per_tool": {k: per[k] for k in sorted(per, key=lambda x: (-per[x]["calls"], x))},
    "brief_rows_used": [t for t in BRIEF_ROWS if t in per],
    "brief_rows_zero": [t for t in BRIEF_ROWS if t not in per],
    "not_in_brief_table": sorted(set(per) - set(BRIEF_ROWS)),
}
json.dump(out, open(os.path.join(HERE, "tool_usage_ledger.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"rows={out['total_rows']} {out['first_ts']} .. {out['last_ts']} ns={out['ns_seen']}")
for k, v in out["per_tool"].items():
    print(f"  {k:20s} calls={v['calls']:3d} failed={v['failed']:2d} ns={v['ns']}")
print("\nbrief 表内 0 调用:", out["brief_rows_zero"])
print("brief 表未列但调用过:", out["not_in_brief_table"])
