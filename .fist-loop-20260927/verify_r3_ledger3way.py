#!/usr/bin/env python3
"""R2-验证 账本三向对照：memory/bugs.md ↔ sqlite ns='bugs' 的 task 行 ↔ 环节报告正文。

只读取数（不开服务端会话）。任何一格对不上就进 refuse，并把逐字差异留在 JSON 里。
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
REVIEWS = ROOT / "memory" / "reviews"

HEAD = re.compile(r"^## (BUG-\d+) \[([^\]]+)\] \[([^\]]+)\] (\w+)", re.M)
TASK_ID = re.compile(r"^- task_id: (\S+)", re.M)
SUMMARY = re.compile(r"^- summary: (.+)", re.M)

refuse: list = []

text = LEDGER.read_text(encoding="utf-8")
entries = []
heads = list(HEAD.finditer(text))
for i, m in enumerate(heads):
    start = m.end()
    end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
    body = text[start:end]
    tid = TASK_ID.search(body)
    summ = SUMMARY.search(body)
    entries.append(
        {
            "bug": m.group(1),
            "status": m.group(4),
            "task_id": tid.group(1) if tid else "",
            "summary": (summ.group(1).strip() if summ else ""),
            "fixed": "### FIXED(" in body,
            "duplicate": "### DUPLICATE" in body,
        }
    )

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
db_rows = {
    r["id"]: dict(r)
    for r in con.execute("select id, ns, status, description from tasks where ns='bugs'")
}
con.close()

by_id = {e["bug"]: e for e in entries}
if len(by_id) != len(entries):
    refuse.append(
        f"账本有重号：条目 {len(entries)} 条 / 去重后 {len(by_id)} 条"
    )

# 第三取证面：call_log 里 report_bug 的实际回执。没有 task_id 栏只有两种合法成因
# （发了卡但没派生任务 / 派生了任务却没落账），区分它们要靠日志而不是回忆。
filed = []
con2 = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con2.row_factory = sqlite3.Row
for r in con2.execute("select ts, params_json, result_json from call_log where tool='report_bug'"):
    try:
        par = json.loads(r["params_json"] or "{}")
    except Exception:
        continue
    filed.append(
        {
            "ts": r["ts"],
            "summary": (par.get("summary") or "")[:24],
            "publish": bool(par.get("publish_task")),
            "res": (r["result_json"] or "")[:40],
        }
    )
con2.close()


def publish_of(summary: str):
    best = [f for f in filed if summary and f["summary"] == summary]
    return best[-1] if best else None


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
            refuse.append(
                f"{e['bug']} 的 report_bug 派生了任务（{rec['ts']}）却没把 task_id 落账"
            )
        else:
            bug_card_only.append(e["bug"])
        continue
    row = db_rows.get(tid)
    if row is None:
        refuse.append(f"{e['bug']} 的 task_id {tid} 在 sqlite ns='bugs' 里不存在")
        continue
    referenced.add(tid)
    if e["summary"] and e["summary"][:40] not in (row["description"] or ""):
        refuse.append(
            f"{e['bug']} 账本摘要与服务端 description 不一致：{tid} "
            f"md={e['summary'][:40]!r} db={(row['description'] or '')[:60]!r}"
        )

orphans = sorted(set(db_rows) - referenced)
if orphans:
    refuse.append(
        f"服务端有 {len(orphans)} 条 bug task 未被账本任何条目引用（可能是隐形标题或漏记）："
        + ",".join(orphans[:12])
    )

fixed_but_open = [e["bug"] for e in entries if e["fixed"] and e["status"] == "OPEN"]

# 双发检测：同一 summary 出现多次就是重跑/重发的痕迹；未标 `### DUPLICATE` 的不放行
buckets: dict = {}
for e in entries:
    key = e["summary"]  # 整条 summary 才是同一主张；截断会把同文件不同行号的缺陷并成双发
    if key:
        buckets.setdefault(key, []).append(e["bug"])
dups = {k: v for k, v in buckets.items() if len(v) > 1}
for key, group in dups.items():
    unmarked = [b for b in group[1:] if not next(e for e in entries if e["bug"] == b)["duplicate"]]
    if unmarked:
        refuse.append(
            f"summary 双发未处置：{group}（未标 DUPLICATE 的：{unmarked}）｜{key[:28]}"
        )


report_ids = sorted(
    {
        p.name
        for p in REVIEWS.glob("*.md")
        if p.stat().st_size > 4000
    }
)
mentions: dict = {}
for name in report_ids:
    body = (REVIEWS / name).read_text(encoding="utf-8", errors="replace")
    for b in set(HEAD.pattern and re.findall(r"BUG-(\d+)", body)):
        mentions.setdefault(int(b), []).append(name)
in_ledger = {int(e["bug"].split("-")[1]) for e in entries}
in_reports = set(mentions)
missing_in_ledger = sorted(in_reports - in_ledger)
if missing_in_ledger:
    refuse.append(
        "报告里出现但账本没有条目的编号："
        + ",".join(f"BUG-{n}" for n in missing_in_ledger[:12])
    )

doc = {
    "refuse": refuse,
    "ledger": {
        "entries": len(entries),
        "distinct": len(by_id),
        "with_task_id": sum(1 for e in entries if e["task_id"]),
        "fixed_sections": sum(1 for e in entries if e["fixed"]),
        "status_counts": {
            s: sum(1 for e in entries if e["status"] == s)
            for s in sorted({e["status"] for e in entries})
        },
    },
    "server": {
        "bug_tasks": len(db_rows),
        "orphans": orphans,
        "status_counts": {},
    },
    "cross": {
        "fixed_but_still_marked_OPEN": fixed_but_open,
        "numbers_only_in_reports": missing_in_ledger,
        "bug_card_only_no_task": bug_card_only,
        "duplicate_summaries": {k: v for k, v in dups.items()},
    },
}
for row in db_rows.values():
    sc = doc["server"]["status_counts"]
    sc[row["status"]] = sc.get(row["status"], 0) + 1

out = HERE / "hunt_r3_ledger3way.json"
out.write_text(
    json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps({"refuse": refuse[:6], "count": len(refuse)}, ensure_ascii=False))
sys.exit(1 if refuse else 0)
