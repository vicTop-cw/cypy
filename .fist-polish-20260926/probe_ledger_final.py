#!/usr/bin/env python3
"""Close the loop with a source the driver cannot fake: read the live task DB directly.

Every closure claim in the report so far rests on my own call logs (close_fixes*.out.json).
This probe queries the same rows out of fist-mbt.db in mode=ro and dumps them, so the report can
assert 11/11 fix tickets are 已完成 / root 已归档 / nothing left actionable without trusting itself.
"""
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"E:\IDEProjects\AI\Cypy"
HERE = os.path.dirname(os.path.abspath(__file__))

led = open(os.path.join(ROOT, "memory", "bugs.md"), encoding="utf-8").read()
pairs = re.findall(r"^## (BUG-(\d+)).*?^- task_id: (\S+)$", led, re.M | re.S)

con = sqlite3.connect("file:" + os.path.join(ROOT, "fist-mbt.db").replace("\\", "/") + "?mode=ro",
                      uri=True)
con.row_factory = sqlite3.Row
ids = [t for _, _, t in pairs] + ["T0", "T0r1"]
q = ("select id, ns, status, parent_id, length(coalesce(deliverable,'')) as dl_len "
     "from tasks where id in (%s)" % ",".join("?" * len(ids)))
rows = {r["id"]: dict(r) for r in con.execute(q, ids)}
status_counts = {r["status"]: r["n"] for r in con.execute(
    "select status, count(*) as n from tasks group by status")}
ns_counts = {r["ns"]: r["n"] for r in con.execute(
    "select ns, count(*) as n from tasks group by ns")}
con.close()

tickets = [{"bug": f"BUG-{n}", "task_id": t, **(rows.get(t) or {"status": "<缺行>"})}
           for _, n, t in sorted(pairs, key=lambda x: int(x[1]))]
out = {
    "db": "E:/IDEProjects/AI/Cypy/fist-mbt.db",
    "read_mode": "sqlite3 mode=ro",
    "tickets": tickets,
    "tickets_done": sum(1 for x in tickets if x.get("status") == "已完成"),
    "tickets_total": len(tickets),
    "root": rows.get("T0") or {"status": "<缺行>"},
    "ghost_T0r1": rows.get("T0r1"),
    "status_counts": status_counts,
    "ns_counts": ns_counts,
}
json.dump(out, open(os.path.join(HERE, "probe_ledger_final.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"tickets_done={out['tickets_done']}/{out['tickets_total']} root={out['root'].get('status')}")
print("status_counts:", status_counts)
print("ns_counts:", ns_counts)
print("T0r1 present:", out["ghost_T0r1"] is not None)
