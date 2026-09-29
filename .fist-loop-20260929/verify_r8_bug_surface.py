"""R8 账面三向对照：memory/bugs.md 的条目 ↔ FIST `bug_list` 回读 ↔ sqlite `call_log` 的 report_bug 行。

为什么要这一层：本环 report_bug 走的是 `publish_task=False`，实测 `tasks` 表 ns='bugs' 里
09-29 一行都没有（最新行是 09-28），也就是说「建单」只落了 md 账本。若我不证明服务端
自己的读路径（bug_list）也看得见 BUG-112..116，就等于把本地文件当成了账面。
结论行最后打，逐字引用不截断。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
DB = ROOT / "fist-mbt.db"
OUT = HERE / "verify_r8_bug_surface.json"
NS = "cypy-loop-20260929"
TARGETS = ["BUG-112", "BUG-113", "BUG-114", "BUG-115", "BUG-116"]


def ledger_blocks() -> dict:
    src = LEDGER.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"(?m)^## (BUG-\d+) ", src):
        start = m.end()
        nxt = src.find("\n## BUG-", start)
        out["BUG-" + m.group(1).split("-")[1]] = src[start: nxt if nxt != -1 else len(src)]
    return out


def main() -> int:
    rep: dict = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"), "ns": NS, "targets": TARGETS}
    blocks = ledger_blocks()
    rep["ledger_seen"] = {b: bool(blocks.get(b)) for b in TARGETS}
    rep["ledger_summaries"] = {}
    for b in TARGETS:
        m = re.search(r"^- summary: (.*)$", blocks.get(b, ""), re.M)
        rep["ledger_summaries"][b] = m.group(1).strip() if m else ""

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    r = c.call("bug_list", {"project_dir": "."})
    blob = json.dumps(r, ensure_ascii=False)
    rep["bug_list_reply_chars"] = len(blob)
    # 服务端的 bug 行用什么键承载身份，不预设：先把两种形状都数一遍
    rep["bug_list_rows_total"] = len(re.findall(r'"bug_id"', blob))
    rep["bug_list_hits"] = {}
    for b in TARGETS:
        summary = rep["ledger_summaries"].get(b, "")
        key = summary[:24]
        rep["bug_list_hits"][b] = {"by_id": b in blob,
                                   "by_summary_prefix": bool(key) and key in blob}

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["tasks_ns_bugs_rows_0929"] = con.execute(
        "select count(*) from tasks where ns='bugs' and created_at>=?",
        ("2026-09-29T00:00:00Z",)).fetchone()[0]
    rows = con.execute(
        "select ts,tool,substr(params_json,1,400),length(result_json) from call_log "
        "where tool='report_bug' and ts>=? order by ts", (rep["started_utc"][:10] + "T00:00:00Z",)
    ).fetchall()
    rep["report_bug_rows_today"] = len(rows)
    rep["report_bug_rows_in_window"] = [x[0] for x in rows if x[0] >= "2026-09-29T04:3"]
    rep["report_bug_target_summaries"] = []
    for ts, tool, params, rlen in rows:
        if not params:
            continue
        m = re.search(r'"summary":\s*"([^"]{0,80})', params or "")
        rep["report_bug_target_summaries"].append({"ts": ts, "summary": m.group(1) if m else "",
                                                   "result_json_bytes": rlen})
    rep["result_json_shape"] = sorted({x[3] for x in rows})

    ok = all(rep["ledger_seen"].values()) and all(
        v["by_id"] and v["by_summary_prefix"] for v in rep["bug_list_hits"].values())
    rep["three_way_ok"] = ok
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("CONCLUSION ledger=%d/%d bug_list_by_id=%d/%d bug_list_by_summary=%d/%d "
          "report_bug_rows=%d tasks_ns_bugs_rows_0929=%d three_way_ok=%s rc=%d"
          % (sum(rep["ledger_seen"].values()), len(TARGETS),
             sum(v["by_id"] for v in rep["bug_list_hits"].values()), len(TARGETS),
             sum(v["by_summary_prefix"] for v in rep["bug_list_hits"].values()), len(TARGETS),
             rep["report_bug_rows_today"], rep["tasks_ns_bugs_rows_0929"], ok, 0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
