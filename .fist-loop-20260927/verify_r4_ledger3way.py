"""R4-验证 法⑧之一：账本三向对照（md 卡片 / sqlite 任务库 / call_log）+ FIXED 段里的复跑命令当场再跑。

上一环写下的 `### FIXED` 段是**主张**，不是事实。本件做两件事：
① 三向对齐：卡片里有 FIXED 段 ⇔ 库里该修复单 `status=已完成` ⇔ `call_log` 里确有该单的调用行；
② 把卡片正文里的「复跑」命令原样再执行一次——修完的缺陷必须**不再现形**（退出码 1），
   仍现形（0）的只能是卡片自己写明「挂账/交人工/转结」的那几张，逐条点名，不并入绿。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
DB = (ROOT / "fist-mbt.db").as_posix()
OUT = HERE / "verify_r4_ledger3way.json"
R4_FIX_WINDOW = "2026-09-27T21:16"          # R4-修复 开环时刻（FIXED 段留档窗口起点）
ANALYZER_KEYS = ["RC1_func_symbol_typed_as_return", "RC2_no_argument_type_check",
                 "RC3_struct_field_type_unresolved", "RC4_internal_repr_in_message"]
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def parse_cards(md: str) -> list:
    """按标题切片读卡片：读少了自己不会报错，所以条目数要与标题数双向对账。"""
    heads = list(re.finditer(r"^## BUG-(\d+) [^\n]*\n", md, re.M))
    cards = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        body = md[m.end():end]
        num = int(m.group(1))
        s = re.search(r"^- summary: (.*)$", body, re.M)
        fixed = re.search(r"^### FIXED[^\n]*", body, re.M)
        tid = re.search(r"^- task_id: (\S+)$", body, re.M)
        repros = re.findall(r"复跑（[^）]*）：(python -X utf8 \S+\.py \S+)", body)
        # 有 FIXED 段的卡片只认 FIXED 段自己的交代：正文里的「挂账」是寻虫环写的修属，不算过
        scope = body[fixed.start():] if fixed else body
        half_open = re.search(r"half-open|冻结面|转结|挂账|交人工", scope)
        cards.append({"num": num, "title_line": m.group(0).strip(),
                      "summary": (s.group(1) if s else None),
                      "fixed_header": fixed.group(0) if fixed else None,
                      "fixed_in_r4_window": bool(fixed and "R4-修复" in fixed.group(0)),
                      "task_id": tid.group(1) if tid else None,
                      "repro_cmd": repros[0] if repros else None,
                      "half_open_disclosed": bool(half_open),
                      "half_open_needle": (half_open.group(0) if half_open else None),
                      "reported_by": (re.search(r"^- reported_by: (\S+)$", body, re.M) or
                                      [None, None])[1]})
    return heads, cards


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    md = LEDGER.read_text(encoding="utf-8")
    heads, cards = parse_cards(md)
    check("反解条目数必须等于盘上标题数（读少了我不知道）", len(cards), len(heads),
          f"{len(heads)} 个标题")

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bug_rows = {r[0]: {"status": r[1], "updated_at": r[2], "completed_by": r[3]} for r in
                con.execute("select id, status, updated_at, completed_by from tasks "
                            "where ns='bugs'")}
    n_bugs_sqlite = len(bug_rows)
    call_counts = {r[0]: r[1] for r in con.execute(
        "select json_extract(params_json,'$.task_id'), count(*) from call_log "
        "where json_extract(params_json,'$.task_id') is not null group by 1")}
    omega_rows = {r[0]: {"ok": r[1], "total": r[2]} for r in con.execute(
        "select json_extract(params_json,'$.task_id'), "
        "sum(case when ok=1 then 1 else 0 end), count(*) from call_log "
        "where tool like 'omega_%' group by 1")}
    control_absent = con.execute("select count(*) from call_log where "
                                 "json_extract(params_json,'$.task_id') like ?",
                                 ("T0rZZZ-not-a-task%",)).fetchone()[0]
    con.close()
    if control_absent != 0:
        REFUSE.append(f"对照 task_id 数出 {control_absent} 行（应为 0）⇒ call_log 过滤器恒真")

    r4_fixed = [c for c in cards if c["fixed_in_r4_window"]]
    filed_r4 = [c for c in cards if c["num"] >= 71]
    three_way = []
    for c in r4_fixed:
        tid = c["task_id"]
        dbrow = bug_rows.get(tid) or {}
        n_log = call_counts.get(tid, 0)
        agree = bool(c["fixed_header"]) and dbrow.get("status") == "已完成" and n_log > 0
        three_way.append({"card": f"BUG-{c['num']}", "task_id": tid,
                          "md_fixed": bool(c["fixed_header"]),
                          "sqlite_status": dbrow.get("status"),
                          "sqlite_completed_by": dbrow.get("completed_by"),
                          "call_log_rows": n_log,
                          "agree": agree})
    agreed = [t for t in three_way if t["agree"]]
    if len(r4_fixed) >= 6:
        check("R4-修复 留档的 FIXED 卡片必须三向都对上", len(agreed), len(r4_fixed),
              json.dumps([t for t in three_way if not t["agree"]], ensure_ascii=False)[:300])
    else:
        REFUSE.append(f"只反解到 {len(r4_fixed)} 张 R4-修复 的 FIXED 卡片（上一环实测 6 张）"
                      f"⇒ 读卡器或窗口口径变了")
    for t in three_way:
        if not t["task_id"]:
            REFUSE.append(f"{t['card']}：FIXED 段指向的修复单号为空")

    recheck = []
    for c in cards:
        if not c["repro_cmd"]:
            continue
        if c["num"] < 61 or c["num"] > 73:
            continue
        r = subprocess.run(c["repro_cmd"].split(), cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1800)
        code = r.returncode
        at = md.find(c["title_line"])
        handoff = bool(re.search(r"修属：(人工|挂账|交)", md[at:at + 6000]))
        recheck.append({"card": f"BUG-{c['num']}", "command": c["repro_cmd"],
                        "exit_code": code, "key_present": code == 0,
                        "expectation": ("fixed-must-not-recur" if c["num"] in (61, 62, 63, 64)
                                        else ("handoff-may-still-recur" if handoff else "report")),
                        "stdout_tail": (r.stdout or "")[-260:],
                        "stderr_tail": (r.stderr or "")[-160:]})
    still = [x for x in recheck if x["key_present"]]
    fixed_not_recurring = [x["card"] for x in recheck
                           if x["expectation"] == "fixed-must-not-recur" and not x["key_present"]]
    broken = [x for x in recheck if x["exit_code"] == 2]
    check("四个分析器根因的复跑件必须「不再现形」",
          sorted(fixed_not_recurring), ["BUG-61", "BUG-62", "BUG-63", "BUG-64"],
          "退出码 1=不现形")
    check("复跑件不许有夹具坏（退出码 2）", broken, [], "2=夹具坏，结论不可用")
    check("本环新入账单必须「现形」（否则是空卡）",
          sorted({x["card"] for x in still if x["card"] in ("BUG-71", "BUG-72", "BUG-73")}),
          ["BUG-71", "BUG-72", "BUG-73"], "退出码 0=现形")
    fixed_nums = {c["num"] for c in r4_fixed}
    disclosed = {c["num"]: c["half_open_disclosed"] for c in cards}
    fixed_still_recurring = [x["card"] for x in recheck
                             if x["key_present"] and int(x["card"].split("-")[1]) in fixed_nums]
    undisclosed = [c for c in fixed_still_recurring
                   if not disclosed.get(int(c.split("-")[1]), False)]
    check("FIXED 卡片若缺陷仍现形，必须在 FIXED 段里自己交代 half-open/冻结面/转结",
          undisclosed, [], f"仍现形且未交代：{fixed_still_recurring}")
    for c in filed_r4:
        row = bug_rows.get(c["task_id"] or "")
        if not row:
            REFUSE.append(f"{c['card']}：账本已落卡但 sqlite ns='bugs' 查不到该单（双轨不同步）")
        if not c["task_id"]:
            REFUSE.append(f"{c['card']}：卡片缺 `- task_id` 行（#55 那类隐形账）")

    md_cards_missing_tid = [f"BUG-{c['num']}" for c in cards if not c["task_id"]]
    md_only_cards = [f"BUG-{c['num']}" for c in cards if c["task_id"] not in bug_rows]
    matched_ids = {c["task_id"] for c in cards if c["task_id"] in bug_rows}
    sqlite_only_rows = sorted(set(bug_rows) - matched_ids)
    check("md 与 sqlite 两个口径的差必须逐张对上（有卡无行 − 有行无卡 == 总数差）",
          len(md_only_cards) - len(sqlite_only_rows), len(cards) - n_bugs_sqlite,
          f"卡 {len(cards)} / 行 {n_bugs_sqlite} / 有卡无行 {len(md_only_cards)} "
          f"/ 有行无卡 {len(sqlite_only_rows)}")
    doc = {"started": started, "window": R4_FIX_WINDOW,
           "cards": cards, "cards_total": len(cards), "headings_total": len(heads),
           "sqlite_bug_rows": n_bugs_sqlite,
           "ledger_delta": len(cards) - n_bugs_sqlite,
           "md_only_cards": md_only_cards, "sqlite_only_rows": sqlite_only_rows,
           "md_only_cards_len": len(md_only_cards),
           "sqlite_only_rows_len": len(sqlite_only_rows),
           "three_way": three_way, "three_way_agreed": len(agreed),
           "r4_fixed_cards": [f"BUG-{c['num']}" for c in r4_fixed],
           "filed_this_round": [f"BUG-{c['num']}" for c in filed_r4],
           "recheck": recheck, "still_recurring": [x["card"] for x in still],
           "fixed_still_recurring": fixed_still_recurring,
           "undisclosed_half_open": undisclosed,
           "fixed_not_recurring": sorted(fixed_not_recurring),
           "cards_missing_task_id": md_cards_missing_tid,
           "cards_missing_task_id_len": len(md_cards_missing_tid),
           "recheck_keys": [x["card"] for x in recheck],
           "call_log_counts_sample": {t["task_id"]: t["call_log_rows"] for t in three_way},
           "omega_rows_by_task": {k: v for k, v in omega_rows.items()
                                  if k and k.startswith("T0r86")},
           "note": "「仍现形」不等于违例：卡片自己写明交人工/挂账的那些（BUG-65/69/70/71/72/73）"
                   "本环不修，现形是事实；违例是「修完还现形」或「没落库却留档」",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"cards_total": len(cards), "sqlite_bug_rows": n_bugs_sqlite,
                      "r4_fixed": doc["r4_fixed_cards"], "three_way_agreed": len(agreed),
                      "filed_this_round": doc["filed_this_round"],
                      "recheck_codes": {x["card"]: x["exit_code"] for x in recheck},
                      "cards_missing_task_id": len(md_cards_missing_tid),
                      "fixed_still_recurring": fixed_still_recurring,
                      "undisclosed_half_open": undisclosed,
                      "refuse": doc["refuse"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
