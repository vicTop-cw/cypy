"""R4-验证 的 call_log 对账：按 `params_json.task_id` 前缀分组数，不按标签、不按回忆。

四条自证（缺一条这栏就是装饰）：
① 每个前缀的逐工具计数之和 == 该前缀总行数（分组不许吞行）；
② `refused` 计数 == 明细条数（拒收清单不是手数出来的）；
③ 拿一个**必然不存在**的前缀当对照，必须数出 0 行——否则这个过滤器是恒真的；
④ 真打一次客户端的 `call_log` 工具：自己读 sqlite 不等于「开过 call_log」。
另立一栏回答「本环报的缺陷单在库里有没有行」：report_bug 的 params 不带 task_id，
只按前缀数必然数到 0 ⇒ 用环节种子那一档单独数，并给出条数与回执号。
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = (ROOT / "fist-mbt.db").as_posix()
PREFIXES = {"T0r86": "R4-验证（16 叶 × omega 全链 + 8 支 + 根上卷）"}
NEEDLE_ABSENT = "T0r9ZZZ-not-a-task"
STAGE_SEED = "%[loop:20260927-loop:R4-验证]%"
LOOP_NS = "cypy-loop-20260927"
BUG_KEYS = [
    "SLICE_typed_as_element", "CODEGEN_named_conditions_unreachable",
    "PYD_incremental_cache_not_reused"]
NAMED_TOOLS = ["laya", "issue_up", "omega_spec_create", "omega_result_verify", "report_bug",
               "output_validate", "submit", "claim", "verify", "run_check", "publish"]
CARRIERS = {"laya": ["laya_decide"], "issue_up": ["publish", "report_bug"],
            "call_log": ["call_log"]}
OUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "verify_r4_calllog_tally.json")


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    refuse, out = [], {}
    total_all = con.execute("select count(*) from call_log").fetchone()[0]
    for prefix, label in PREFIXES.items():
        rows = list(con.execute(
            "select tool, ok, ts, params_json, result_json from call_log "
            "where json_extract(params_json,'$.task_id') like ? order by id", (f"{prefix}%",)))
        by_tool, refused_detail, leaf_ids = {}, [], set()
        for tool, ok, ts, params, result in rows:
            try:
                pj = json.loads(params)
            except (TypeError, json.JSONDecodeError):
                pj = {}
                refused_detail.append(f"{prefix}: params_json 不是合法 JSON（{ts}）")
            leaf_ids.add(pj.get("task_id") or "?")
            slot = by_tool.setdefault(tool, {"ok": 0, "refused": 0})
            slot["ok" if ok else "refused"] += 1
            if not ok:
                refused_detail.append({"task": pj.get("task_id"), "tool": tool, "ts": ts,
                                       "err": (result or "")[:500]})
        summed = sum(v["ok"] + v["refused"] for v in by_tool.values())
        if summed != len(rows):
            refuse.append(f"{prefix}：逐工具合计 {summed} ≠ 该前缀行数 {len(rows)} ⇒ 分组吞了行")
        n_refused = sum(v["refused"] for v in by_tool.values())
        structured = [d for d in refused_detail if isinstance(d, dict)]
        if n_refused != len(structured):
            refuse.append(f"{prefix}：refused 计数 {n_refused} ≠ 明细条数 {len(structured)}")
        out[prefix] = {"label": label, "rows": len(rows), "distinct_tasks": len(leaf_ids),
                       "by_tool": by_tool, "refused": n_refused,
                       "refused_detail": refused_detail}

    seed_rows = list(con.execute(
        "select tool, ok, ts, substr(result_json,1,300) from call_log where params_json like ? "
        "order by id", (STAGE_SEED,)))
    seed_by_tool = {}
    for tool, ok, ts, result in seed_rows:
        slot = seed_by_tool.setdefault(tool, {"ok": 0, "refused": 0, "examples": []})
        slot["ok" if ok else "refused"] += 1
        if not ok and len(slot["examples"]) < 3:
            slot["examples"].append({"ts": ts, "err": result})
    bug_rows = list(con.execute(
        "select id, substr(description,1,60), status from tasks where ns='bugs' "
        "and description like ? order by id desc limit 6", ('%SLICE_typed_as_element%',)))
    bug_rows_all = []
    for key in BUG_KEYS:
        n = con.execute("select count(*) from tasks where ns='bugs' and description like ?",
                        (f"%{key}%",)).fetchone()[0]
        bug_rows_all.append({"key": key, "sqlite_rows": n})

    call = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "lfist.py"), "call_log",
         json.dumps({"limit": 3000, "namespace": "cypy-loop-20260927", "project_dir": "."},
                    ensure_ascii=False)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    client_rows, client_err = None, ""
    if call.returncode == 0:
        try:
            client_rows = json.loads(call.stdout)["calls"]
        except Exception as exc:
            client_err = f"回包解析失败：{type(exc).__name__}: {exc}"
    else:
        client_err = f"rc={call.returncode} {(call.stderr or call.stdout)[:240]}"
    client_prefix = (sum(1 for c in client_rows if "T0r86" in (c.get("params") or "")
                         if client_rows) if client_rows is not None else 0)
    if client_rows is None:
        refuse.append(f"call_log 工具没调通：{client_err}")
    elif client_prefix < out["T0r86"]["rows"]:
        refuse.append(f"call_log 工具只回 {client_prefix} 行含 T0r86（sqlite 同口径 "
                      f"{out['T0r86']['rows']} 行）⇒ 工具面看不到这些调用")
    client_ok = 1 if (client_rows is not None and client_prefix >= out["T0r86"]["rows"]) else 0

    carriers = {}
    for spec_name, real_tools in CARRIERS.items():
        per = {}
        for t in real_tools:
            per[t] = {
                "whole_db": con.execute("select count(*) from call_log where tool=?",
                                        (t,)).fetchone()[0],
                "this_stage_seed": sum(v["ok"] + v["refused"] for k, v in seed_by_tool.items()
                                       if k == t),
                "this_stage_prefix": sum(v["ok"] + v["refused"] for k, v in
                                         out["T0r86"]["by_tool"].items() if k == t)}
        if spec_name == "call_log":
            per["call_log"]["this_stage_prefix"] = client_ok
            per["call_log"]["client_visible_T0r86_rows"] = client_prefix
            per["call_log"]["client_rows_returned"] = (len(client_rows)
                                                       if client_rows is not None else 0)
            if client_err:
                per["call_log"]["error"] = client_err
        in_stage = sum(v["this_stage_seed"] + v["this_stage_prefix"] for v in per.values())
        carriers[spec_name] = {"carriers": per, "this_stage_total": in_stage}
        if in_stage == 0 and spec_name != "issue_up":
            refuse.append(f"规格点名的 {spec_name} 本轮 0 次调用 ⇒ 不许写『已开启』")
        if spec_name == "issue_up" and carriers.get("issue_up", {}).get("this_stage_total", 0) == 0:
            refuse.append("issue_up 等价能力（publish/report_bug）本轮 0 次 ⇒ 缺陷没入账就别报开过")
    absent = con.execute("select count(*) from call_log where "
                         "json_extract(params_json,'$.task_id') like ?",
                         (f"{NEEDLE_ABSENT}%",)).fetchone()[0]
    if absent != 0:
        refuse.append(f"对照前缀 {NEEDLE_ABSENT} 数出 {absent} 行（应为 0）⇒ 过滤器恒真")
    named = {t: {"exact": con.execute("select count(*) from call_log where tool=?", (t,))
                 .fetchone()[0],
                 "substring": con.execute("select count(*) from call_log where tool like ?",
                                          (f"%{t}%",)).fetchone()[0]} for t in NAMED_TOOLS}
    groups, order = {}, []
    for d in out["T0r86"]["refused_detail"]:
        if not isinstance(d, dict):
            continue
        key = d["err"] or "(空 result_json)"
        if key not in groups:
            groups[key] = {"count": 0, "first": f'{d["task"]} @ {d["ts"]}', "tool": d["tool"]}
            order.append(key)
        groups[key]["count"] += 1
    lines = ["| 被拒原文（逐字） | 工具 | 次数 | 首个见证 |", "| --- | --- | --- | --- |"]
    for key in order:
        g = groups[key]
        quoted = key.replace("|", "\\|").replace("\n", "⏎")
        lines.append(f'| `{quoted}` | {g["tool"]} | {g["count"]} | {g["first"]} |')
    if sum(g["count"] for g in groups.values()) != out["T0r86"]["refused"]:
        refuse.append(f"逐字分组次数合计 {sum(g['count'] for g in groups.values())} ≠ refused 计数 "
                      f"{out['T0r86']['refused']} ⇒ 分组漏行")
    omega = {}
    for tool in ("omega_spec_create", "omega_spec_review", "omega_result_verify"):
        row = con.execute(
            "select count(*) from call_log where tool=? and "
            "json_extract(params_json,'$.task_id') like ?",
            (tool, "T0r86%")).fetchone()
        omega[tool] = row[0]

    # 整条 5×5 循环的账面：逐根任务（depth=0）点名其前缀下的行数/被拒数。
    # 这是「omega/laya/issue_up/call_log 到底开没开」的轮次级见证，不是靠回忆数出来的。
    root_ids = list(con.execute(
        "select id, substr(description,1,52), status from tasks where ns=? and "
        "(parent_id='' or parent_id is null) order by id", (LOOP_NS,)))
    loop_roots, roots_without_calls, loop_rows = [], [], 0
    for rid, desc, status in root_ids:
        # 前缀要精确：裸 like 'T0r8%' 会把 T0r80/T0r86 一起捞进来 ⇒ 只认「等于根号」或「根号.子号」
        n, bad = con.execute(
            "select count(*), coalesce(sum(case when ok then 0 else 1 end),0) from call_log "
            "where json_extract(params_json,'$.task_id') = ? or "
            "json_extract(params_json,'$.task_id') like ?", (rid, f"{rid}.%")).fetchone()
        loop_rows += n
        if n == 0:
            roots_without_calls.append(rid)
        loop_roots.append({"root": rid, "stage": desc, "status": status,
                           "rows": n, "refused": bad})
    if len(root_ids) < 5:
        refuse.append(f"循环根任务只反解到 {len(root_ids)} 个（ns={LOOP_NS}）⇒ 口径可疑")
    if loop_rows > total_all:
        refuse.append(f"逐根合计 {loop_rows} 行 > call_log 总行数 {total_all} ⇒ 前缀互相吞并/重复计数")
    con.close()
    doc = {"grouped_by": "params_json.task_id 前缀（不按标签、不按回忆）",
           "stages": out, "rows": out["T0r86"]["rows"],
           "rows_T0r86": out["T0r86"]["rows"],
           "distinct_tasks": out["T0r86"]["distinct_tasks"],
           "control_absent_prefix_rows": absent, "total_call_log_rows": total_all,
           "stage_seed_rows": {"needle": STAGE_SEED, "total": len(seed_rows),
                               "by_tool": seed_by_tool},
           "bug_intake_rows": bug_rows_all, "bug_sample": [list(r) for r in bug_rows],
           "named_tools_in_this_build": named, "spec_named_carriers": carriers,
           "omega_chain_by_tool": omega,
           "loop_roots": loop_roots, "loop_roots_total_rows": loop_rows,
           "loop_roots_without_calls": roots_without_calls,
           "distinct_refusal_texts": len(order),
           "refusals_md": "\n".join(lines),
           "note": "规格点名的 laya / issue_up 不是本 build 的工具名；承担同一能力的实际工具名"
                   "在 spec_named_carriers 里逐条给数",
           "refuse": sorted(set(refuse)),
           "queried_at_utc": now_iso()}
    Path(OUT).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8", newline="\n")
    print(json.dumps({"rows_T0r86": doc["rows"], "distinct_tasks": doc["distinct_tasks"],
                      "refused": out["T0r86"]["refused"], "seed_total": len(seed_rows),
                      "carriers": {k: v["this_stage_total"] for k, v in carriers.items()},
                      "omega": omega, "bug_intake": bug_rows_all,
                      "by_tool": out["T0r86"]["by_tool"], "refuse": doc["refuse"]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
