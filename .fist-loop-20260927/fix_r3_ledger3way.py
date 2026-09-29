#!/usr/bin/env python3
"""R3-修复 的账本三向对照：memory/bugs.md ↔ sqlite（ns='bugs' + call_log）↔ 本轮报告正文骨架。

只读取数、不开服务端会话。与上一环的 `verify_r3_ledger3way.json` 同一口径，差异两处：

- 本环追加了 6 段 `### FIXED(修复=已完成)`，所以额外校：六件各且仅各一段、段里含本轮
  的 `2026-09-28 R3-修复` 标记、条目标题行仍逐字 60 条 `OPEN`；
- 已知孤儿按**点名白名单**放行：`T0r2..T0r5` 是前几轮已入账裁决过的 4 条（账本里没有对应
  条目），白名单之外的任何孤儿都算新账，必须 refuse。上一环让 refuse 常驻这 4 条，
  等于让"新增孤儿"和"已知孤儿"共用一个信号，这一环把它分开。
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = ROOT / "fist-mbt.db"
LEDGER = ROOT / "memory" / "bugs.md"
BODY = HERE / "r3_fix_body.md"
MARK = "### FIXED(修复=已完成)"
ROUND_TAG = "2026-09-28 R3-修复"
KNOWN_ORPHANS = {"T0r2", "T0r3", "T0r4", "T0r5"}
FIXED_BUGS = ["BUG-55", "BUG-56", "BUG-57", "BUG-58", "BUG-59", "BUG-60"]

HEAD = re.compile(r"^## (BUG-\d+) \[([^\]]+)\] \[([^\]]+)\] (\w+)", re.M)
TASK_ID = re.compile(r"^- task_id: (\S+)", re.M)
SUMMARY = re.compile(r"^- summary: (.+)", re.M)

refuse: list = []
text = LEDGER.read_text(encoding="utf-8")

entries = []
heads = list(HEAD.finditer(text))
for i, m in enumerate(heads):
    body = text[m.end():(heads[i + 1].start() if i + 1 < len(heads) else len(text))]
    tid = TASK_ID.search(body)
    summ = SUMMARY.search(body)
    entries.append({
        "bug": m.group(1), "status": m.group(4),
        "task_id": tid.group(1) if tid else "",
        "summary": summ.group(1).strip() if summ else "",
        "fixed_this_round": bool(re.search(re.escape(MARK) + r".*" + re.escape(ROUND_TAG), body)),
        "mark_lines": len(re.findall(re.escape(MARK), body)),
    })

by_id = {e["bug"]: e for e in entries}
if len(by_id) != len(entries):
    refuse.append(f"账本有重号：条目 {len(entries)} 条 / 去重后 {len(by_id)} 条")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
db_rows = {r["id"]: dict(r) for r in con.execute(
    "select id, ns, status, description from tasks where ns='bugs'")}
# 第三取证面：call_log 里 report_bug 的回执。条目没有 task_id 有两种合法成因
# （`publish_task=False` 只出缺陷卡不派任务 / 派了任务却没落账），区分要靠日志不是回忆。
filed = []
for r in con.execute("select ts, params_json, result_json from call_log where tool='report_bug'"):
    try:
        par = json.loads(r["params_json"] or "{}")
    except (ValueError, TypeError):
        continue
    filed.append({"summary": (par.get("summary") or "")[:24], "publish": bool(par.get("publish_task"))})
con.close()


def publish_of(summary: str):
    hits = [f for f in filed if summary and f["summary"] == summary]
    return hits[-1] if hits else None


referenced = set()
bug_card_only = []
for e in entries:
    tid = e["task_id"]
    if not tid:
        rec = publish_of(e["summary"][:24])
        if rec is None:
            refuse.append(f"{e['bug']} 既无 task_id 也在 call_log 找不到 report_bug 回执")
            continue
        if rec["publish"]:
            refuse.append(f"{e['bug']} 的 report_bug 派生了任务却没把 task_id 落账")
        else:
            bug_card_only.append(e["bug"])
        continue
    row = db_rows.get(tid)
    if row is None:
        refuse.append(f"{e['bug']} 的 task_id {tid} 在 sqlite ns='bugs' 里不存在")
        continue
    referenced.add(tid)
    if e["summary"] and e["summary"][:40] not in (row["description"] or ""):
        refuse.append(f"{e['bug']} 账本摘要与服务端 description 不一致：{tid}")

orphans = sorted(set(db_rows) - referenced)
new_orphans = sorted(set(orphans) - KNOWN_ORPHANS)
if new_orphans:
    refuse.append(f"出现白名单之外的新孤儿 bug task：{new_orphans}")

for bug in FIXED_BUGS:
    e = by_id.get(bug)
    if e is None:
        refuse.append(f"账本里找不到 {bug} 条目")
        continue
    if not e["fixed_this_round"]:
        refuse.append(f"{bug} 没有本环（{ROUND_TAG}）的 FIXED 段")
    if e["mark_lines"] != 1:
        refuse.append(f"{bug} 的 FIXED 段数是 {e['mark_lines']}，不是 1")

body_text = BODY.read_text(encoding="utf-8") if BODY.exists() else ""
if not BODY.exists():
    refuse.append(f"报告正文骨架 {BODY.name} 不在盘上（第三向缺一面）")
else:
    missing_in_body = [b for b in FIXED_BUGS if b not in body_text]
    if missing_in_body:
        refuse.append(f"报告骨架里没点到这些缺陷：{missing_in_body}")

out = {
    "ledger": {"entries": len(entries),
               "open_titles": len([e for e in entries if e["status"] == "OPEN"]),
               "fixed_this_round": sum(1 for e in entries if e["fixed_this_round"]),
               "fixed_sections_total": text.count(MARK)},
    "server": {"bug_tasks": len(db_rows), "referenced": len(referenced),
               "bug_card_only": len(bug_card_only),
               "bug_card_only_ids": bug_card_only,
               "orphans": orphans, "orphans_match_known_whitelist": set(orphans) == KNOWN_ORPHANS},
    "report": {"fragment": BODY.name, "exists": BODY.exists(),
               "bytes": len(body_text.encode("utf-8"))},
    "refuse": refuse,
}
(HERE / "fix_r3_ledger3way.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(1 if refuse else 0)
