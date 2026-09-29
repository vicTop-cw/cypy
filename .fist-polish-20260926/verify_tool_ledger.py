#!/usr/bin/env python3
"""Audit §五.11's tool-reconciliation table against call_log (recomputed independently).

The generator reads tool_usage_ledger.json; this re-reads the sqlite table itself, so a stale or
hand-edited ledger cannot slip a wrong count into the report.
"""
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("file:" + os.path.join(ROOT, "fist-mbt.db").replace("\\", "/") + "?mode=ro",
                      uri=True)
live = {}
for tool, ok in con.execute("select tool, ok from call_log"):
    d = live.setdefault(tool, [0, 0])
    d[0] += 1
    d[1] += 0 if str(ok) == "1" else 1
con.close()

led = json.load(open(os.path.join(HERE, "tool_usage_ledger.json"), encoding="utf-8"))
REV = os.path.join(ROOT, "memory", "reviews")
files = [f for f in os.listdir(REV) if f.endswith(".md")]
if len(files) != 1:
    sys.exit(f"[verify_tools] memory/reviews 应有 1 份报告，实得 {files}")
text = open(os.path.join(REV, files[0]), encoding="utf-8").read()
print(f"report: memory/reviews/{files[0]}   live call_log rows={sum(v[0] for v in live.values())}")

reds = []


def chk(cond, msg):
    print(("  OK  " if cond else "  RED ") + msg)
    if not cond:
        reds.append(msg)


chk(sum(v[0] for v in live.values()) == led["total_rows"],
    f"ledger 行数与 call_log 实时一致（{led['total_rows']}）")
for t, (n, f) in live.items():
    chk([n, f] == [led["per_tool"][t]["calls"], led["per_tool"][t]["failed"]],
        f"ledger 计数 {t} = {n}/{f}（calls/failed）")

for t in led["brief_rows_used"] + led["brief_rows_zero"]:
    n, f = live.get(t, [0, 0])
    chk(f"| `{t}` | {n} | {f} |" in text, f"§五.11 表 {t} 行等于 call_log 实时计数 {n}/{f}")

rows = [ln for ln in text.splitlines()
        if re.match(r"^\| `(publish|claim|task_plan_deep|execute|submit|verify|archive|heartbeat|"
                    r"report_bug|bug_list|output_validate|list|get|issue_scan)` \|", ln)]
chk(len(rows) == 14, f"§四 的 14 行全部进表（实得 {len(rows)}）")
chk({ln.count("|") for ln in rows} == {5}, f"表行竖线数={sorted({ln.count('|') for ln in rows})}")

d = led["detail"]
chk(f"`heartbeat` 实际只有 {d['heartbeat']['calls']} 次" in text, "heartbeat 计数按 call_log 写（未美化为周期上报）")
chk(f"`archive` {d['archive']['calls']} 次里 {d['archive']['failed']} 次被服务端拒" in text,
    "archive 拒绝次数按 call_log 写")
chk(f"确实用了 {len(d['run_check'])} 次" in text, "run_check 次数按 call_log 写（不写「本轮没用」）")
chk(d["run_check_inside_project_tests"] is True, "run_check 全部只跑项目内 tests/ 路径")
chk(f"（{led['total_rows']} 行" in text, "报告引用了 call_log 总行数")

print(f"\nverify_tools: {'全项通过' if not reds else 'RED ' + str(len(reds)) + ' 项 ' + str(reds)}")
sys.exit(0 if not reds else 1)
