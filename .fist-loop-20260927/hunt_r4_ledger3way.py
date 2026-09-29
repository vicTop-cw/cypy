"""R4-寻虫 法 7：账本三向对照（md 条目 / sqlite bug 任务 / call_log 里的 report_bug 回执）。

只有一张单在**三个取证面都能数到**才算"入账"。三面的连接键：
- md 与 sqlite：本环 summary 以 `[<根因键>]` 开头，sqlite 的 description 是 `修复 bug: <summary>`，
  所以按根因键连；两面各数一遍，不许只数一面。
- call_log：`tool='report_bug'` 且 params 里带同一根因键；**回执必须 ok=1**，
  被拒的调用单独一栏，不许混进"已入账"。
- 本环不修 ⇒ 新单下不应出现 `### FIXED` 段；出现了说明流程串了道。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
from pathlib import Path

from hunt_r4_dedup import PLAN

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
OUT = HERE / "hunt_r4_ledger3way.json"
FILED = json.loads((HERE / "hunt_r4_filed.json").read_text(encoding="utf-8"))
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why,
                   "ok": (got == want) if ok is None else bool(ok)})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    text = LEDGER.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (BUG-\d+) ", text)
    entries = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    bug_rows = db.execute("select id, status, description from tasks where ns='bugs'").fetchall()
    logs = db.execute("select ts, params_json, result_json, ok from call_log where tool='report_bug' "
                      "order by id desc limit 400").fetchall()
    stage_rows = db.execute("select id, status from tasks where ns=? order by id",
                            ("cypy-loop-20260927",)).fetchall()
    db.close()

    rows = []
    for card in PLAN:
        key = card["key"]
        md_hits = [n for n, b in entries.items() if f"[{key}]" in b]
        sq_hits = [i for i, st, d in bug_rows if key in (d or "")]
        lg_hits = [(ts, json.loads(p).get("summary", "")[:70], int(ok))
                   for ts, p, _r, ok in logs if key in (p or "")]
        fixed = [n for n in md_hits if "### FIXED" in entries[n]]
        rows.append({"key": key, "bug_numbers": sorted(md_hits), "md_entries": len(md_hits),
                     "sqlite_task_ids": sq_hits, "sqlite_rows": len(sq_hits),
                     "call_log_report_bug": len(lg_hits),
                     "call_log_refused": [l for l in lg_hits if l[2] != 1],
                     "fixed_sections": fixed,
                     "agree": len(md_hits) == 1 and len(sq_hits) == 1 and len(lg_hits) >= 1
                     and lg_hits[0][2] == 1 and not fixed})
    agreed = [r["key"] for r in rows if r["agree"]]
    check("三向一致：每张计划单在 md/sqlite/call_log 各数到一次",
          [r["key"] for r in rows if not r["agree"]], [], "不一致的单")
    check("入账数 == 计划单数 == filed.json 的号数",
          [len(agreed), len(PLAN), FILED["filed_total"], len(FILED["filed"])],
          [len(PLAN)] * 4, "四栏同数")
    check("号段与 filed.json 逐一对应", sorted({n for r in rows for n in r["bug_numbers"]}),
          sorted(FILED["filed"]), "md 号 vs 入账回执号")
    check("寻虫环不得留下 FIXED 段", sum(len(r["fixed_sections"]) for r in rows), 0,
          "新单里的 FIXED 段总数")
    check("call_log 里 report_bug 全部 ok=1",
          [f"{r['key']}:{l[0]}" for r in rows for l in r["call_log_refused"]], [], "被拒的入账调用")
    check("账本总数 = 上一环 60 + 本环 10", len(entries), 70, "md `## BUG-NN` 计数")
    check("阶段任务树里根 T0r74 存在", any(i == "T0r74" for i, _s in stage_rows), True,
          f"ns=cypy-loop-20260927 共 {len(stage_rows)} 行")
    doc = {"started": started, "rows": rows, "agree": agreed, "agree_total": len(agreed),
           "ledger_total": len(entries),
           "fixed_sections_total": sum(len(r["fixed_sections"]) for r in rows), "sqlite_bug_rows": len(bug_rows),
           "stage_task_rows": len(stage_rows),
           "stage_task_status": {s: sum(1 for _i, st in stage_rows if st == s)
                                 for s in sorted({st for _i, st in stage_rows})},
           "join_key": "summary 前缀 [<根因键>]，sqlite description = '修复 bug: ' + summary",
           "refuse": sorted(set(REFUSE)) + [
               f"判据自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:160]}）"
               for c in CHECKS if not c["ok"]],
           "self_checks": CHECKS,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "agree_total": len(agreed),
                      "ledger_total": doc["ledger_total"], "sqlite_bug_rows": doc["sqlite_bug_rows"],
                      "per_card": {r["key"]: {"md": r["md_entries"], "sqlite": r["sqlite_rows"],
                                              "log": r["call_log_report_bug"], "agree": r["agree"]}
                                   for r in rows}}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(json.dumps({"refuse": [f"崩在 {type(exc).__name__}: {exc}"]},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(2)
