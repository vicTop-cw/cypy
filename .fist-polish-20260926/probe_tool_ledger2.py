#!/usr/bin/env python3
"""Add a `detail` block to tool_usage_ledger.json: the facts a per-tool count cannot carry.

Read-only sqlite again. What gets pinned down: which tools touched ns `default` (reads vs writes),
why `archive` failed 11 of 12 times (the server's own message), which two tickets used `run_check`
and whether those calls stayed inside project tests, how many `heartbeat` signals were actually
sent (the brief says "周期上报" — one is not periodic, and the report should say so), and the exact
`report_bug` rejection text behind the 落点契约 section.
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LEDGER = os.path.join(HERE, "tool_usage_ledger.json")

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("file:" + os.path.join(ROOT, "fist-mbt.db").replace("\\", "/") + "?mode=ro",
                      uri=True)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("select tool, ok, ns, ts, params_json, result_json from call_log")]
con.close()


def js(blob, key, default=None):
    try:
        return json.loads(blob).get(key, default)
    except Exception:
        return default


led = json.load(open(LEDGER, encoding="utf-8"))

default_tools = {}
for r in rows:
    if r["ns"] == "default":
        default_tools[r["tool"]] = default_tools.get(r["tool"], 0) + 1

arc = [r for r in rows if r["tool"] == "archive"]
arc_fail_msgs = sorted({js(r["result_json"], "error") or (r["result_json"] or "")[:80]
                        for r in arc if str(r["ok"]) != "1"})
rc = []
for r in rows:
    if r["tool"] != "run_check":
        continue
    p = json.loads(r["params_json"])
    rc.append({"ts": r["ts"], "task_id": p.get("task_id"), "ok": str(r["ok"]) == "1",
               "cmd_basename": os.path.basename(str(p.get("cmd", ""))),
               "workdir": p.get("workdir"), "args": p.get("args") or []})
hb = [r for r in rows if r["tool"] == "heartbeat"]
rb_fail = {}
for r in rows:
    if r["tool"] == "report_bug" and str(r["ok"]) != "1":
        msg = js(r["result_json"], "error") or (r["result_json"] or "")[:100]
        rb_fail[msg] = rb_fail.get(msg, 0) + 1

led["detail"] = {
    "default_ns_tools": default_tools,
    "default_ns_is_read_only": set(default_tools) <= {"list", "get", "bug_list"},
    "archive": {"calls": len(arc), "failed": sum(1 for r in arc if str(r["ok"]) != "1"),
                "failure_msgs": arc_fail_msgs,
                "succeeded_for": [js(r["params_json"], "task_id") for r in arc if str(r["ok"]) == "1"],
                "succeeded_by": sorted({js(r["params_json"], "by") for r in arc if str(r["ok"]) == "1"})},
    "run_check": rc,
    "run_check_inside_project_tests": all(any(a.startswith("tests/") for a in x["args"]) for x in rc),
    "heartbeat": {"calls": len(hb), "tasks": sorted({js(r["params_json"], "task_id") for r in hb}),
                  "first_ts": min([r["ts"] for r in hb], default=None),
                  "last_ts": max([r["ts"] for r in hb], default=None)},
    "report_bug_rejections": rb_fail,
    "pause_calls": sum(1 for r in rows if r["tool"] == "pause"),
    "reopen_task_calls": sum(1 for r in rows if r["tool"] == "reopen_task"),
}
json.dump(led, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(led["detail"], ensure_ascii=False, indent=1)[:1600])
print("\nzero-call brief rows:", led["brief_rows_zero"])
