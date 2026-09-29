"""R4-修复 的 call_log 对账：本环真实发生过哪些调用、被拒的原文逐字是什么。

与上一环同口径，但本环的账面分**两栏**（这是上一环被指出的掩盖形状）：
- `T0r85` 前缀 = 本环任务树（16 叶 + 8 支 + 根）；
- `bugs` 树六张修复单（T0r75/76/77/78/80/81）—— 它们不在本环 ns 里，只按前缀数就会漏。

三条自证照旧：逐工具合计 == 行数、refused 计数 == 明细条数、必然不存在的前缀必须数出 0。
另外必须**真打一次** `call_log` 工具：只读 sqlite 不等于"开过 call_log"。
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
NS = "cypy-loop-20260927"
STAGE_SEED = "%[loop:20260927-loop:R4-修复]%"
SCOPES = {"T0r85": "R4-修复 任务树（根＋8 支＋16 叶）",
          "T0r75": "修复单 RC1（BUG-61）", "T0r76": "修复单 RC2（BUG-62）",
          "T0r77": "修复单 RC3（BUG-63）", "T0r78": "修复单 RC4（BUG-64）",
          "T0r80": "修复单 DOC_cli（BUG-66）", "T0r81": "修复单 DOC_example（BUG-67）"}
NEEDLE_ABSENT = "T0r9ZZZ-not-a-task"
NAMED_TOOLS = ["laya", "issue_up", "omega_spec_create", "omega_spec_review",
               "omega_result_verify", "report_bug", "output_validate", "submit",
               "claim", "verify", "call_log", "run_check"]
CARRIERS = {"laya": ["laya_decide"], "issue_up": ["publish", "report_bug"],
            "call_log": ["call_log"], "omega": ["omega_spec_create", "omega_spec_review",
                                                "omega_result_verify"]}
OUT = HERE / "fix_r4_calllog_tally.json"
FINAL_OUT = HERE / "fix_r4_calllog_tally_final.json"


def main() -> int:
    final = "--final" in sys.argv
    out_path = FINAL_OUT if final else OUT
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    refuse, scopes = [], {}
    total_all = con.execute("select count(*) from call_log").fetchone()[0]
    # omega 标记面（库侧正面测）：链在渲染之后才执行，但标记此刻就该已经在库里
    leaves_total = con.execute("select count(*) from tasks where ns=? and id like ? and depth=1",
                               (NS, "T0r85.%")).fetchone()[0]
    leaves_marked = con.execute(
        "select count(*) from tasks where ns=? and id like ? and depth=1 "
        "and description like '%[omega:required]%'", (NS, "T0r85.%")).fetchone()[0]
    root_marked = con.execute(
        "select count(*) from tasks where id=? and description like '%[omega:required]%'",
        ("T0r85",)).fetchone()[0]
    if leaves_total != 16:
        refuse.append(f"本环树反解到 {leaves_total} 张叶（应为 16）")
    if leaves_marked != 16 or not root_marked:
        refuse.append(f"omega 标记缺失：叶 {leaves_marked}/16、根 {root_marked}/1")
    all_detail = []
    for prefix, label in SCOPES.items():
        if prefix == "T0r85":
            # 根自己的调用（publish / claim / laya_decide / task_plan_deep）也必须入账：
            # 只用 `like 'T0r85.%'` 会把根吞掉，"树有账"就只剩叶子那半截
            rows = list(con.execute(
                "select tool, ok, ts, params_json, result_json from call_log "
                "where json_extract(params_json,'$.task_id') in ('T0r85') "
                "or json_extract(params_json,'$.task_id') like 'T0r85.%' order by id"))
        else:
            rows = list(con.execute(
                "select tool, ok, ts, params_json, result_json from call_log "
                "where json_extract(params_json,'$.task_id') = ? order by id", (prefix,)))
        by_tool, refused_detail, tids = {}, [], set()
        for tool, ok, ts, params, result in rows:
            try:
                pj = json.loads(params)
            except (TypeError, json.JSONDecodeError):
                pj = {}
                refused_detail.append(f"{prefix}: params_json 不是合法 JSON（{ts}）")
            tid = pj.get("task_id") or "?"
            tids.add(tid)
            slot = by_tool.setdefault(tool, {"ok": 0, "refused": 0})
            slot["ok" if ok else "refused"] += 1
            if not ok:
                d = {"scope": prefix, "task": tid, "tool": tool, "ts": ts,
                     "err": (result or "")[:500]}
                refused_detail.append(d)
                all_detail.append(d)
        summed = sum(v["ok"] + v["refused"] for v in by_tool.values())
        if summed != len(rows):
            refuse.append(f"{prefix}：逐工具合计 {summed} ≠ 行数 {len(rows)} ⇒ 分组吞了行")
        n_refused = sum(v["refused"] for v in by_tool.values())
        structured = [d for d in refused_detail if isinstance(d, dict)]
        if n_refused != len(structured):
            refuse.append(f"{prefix}：refused 计数 {n_refused} ≠ 明细条数 {len(structured)}")
        scopes[prefix] = {"label": label, "rows": len(rows), "distinct_tasks": len(tids),
                          "by_tool": by_tool, "refused": n_refused,
                          "refused_detail": refused_detail}
    tree_rows = scopes["T0r85"]["rows"]
    card_rows = sum(v["rows"] for k, v in scopes.items() if k != "T0r85")
    tree_refused = scopes["T0r85"]["refused"]
    card_refused = sum(v["refused"] for k, v in scopes.items() if k != "T0r85")

    seed_rows = list(con.execute(
        "select tool, ok, ts, substr(result_json,1,300) from call_log "
        "where params_json like ? order by id", (STAGE_SEED,)))
    seed_by_tool: dict = {}
    for tool, ok, ts, result in seed_rows:
        slot = seed_by_tool.setdefault(tool, {"ok": 0, "refused": 0, "examples": []})
        slot["ok" if ok else "refused"] += 1
        if not ok and len(slot["examples"]) < 3:
            slot["examples"].append({"ts": ts, "err": result})

    call = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "lfist.py"), "call_log",
         json.dumps({"limit": 5000, "namespace": NS, "project_dir": "."}, ensure_ascii=False)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    client_rows, client_err = None, ""
    if call.returncode == 0:
        try:
            client_rows = json.loads(call.stdout)["calls"]
        except Exception as exc:
            client_err = f"回包解析失败：{type(exc).__name__}: {exc}"
            client_err += f" / stdout 前 200：{(call.stdout or '')[:200]!r}"
    else:
        client_err = f"rc={call.returncode} {(call.stderr or call.stdout)[:240]}"
    vis = {}
    if client_rows is None:
        refuse.append(f"call_log 工具没调通：{client_err}")
    else:
        for prefix in SCOPES:
            n = sum(1 for c in client_rows
                    if (f'"{prefix}' in (c.get("params") or ""))
                    or (prefix in (c.get("task_id") or "")))
            vis[prefix] = n
        if vis.get("T0r85", 0) < tree_rows:
            refuse.append(f"call_log 工具只回 {vis.get('T0r85')} 行含 T0r85（sqlite 同口径 "
                          f"{tree_rows} 行）⇒ 工具面看不到这些调用")

    carriers = {}
    for spec_name, real in CARRIERS.items():
        per = {}
        for t in real:
            per[t] = {
                "whole_db": con.execute(
                    "select count(*) from call_log where tool=?", (t,)).fetchone()[0],
                "this_stage_seed": sum(v["ok"] + v["refused"]
                                       for k, v in seed_by_tool.items() if k == t),
                "in_tree": scopes["T0r85"]["by_tool"].get(t, {"ok": 0})["ok"],
                "in_bug_cards": sum(v["by_tool"].get(t, {"ok": 0})["ok"]
                                    for k, v in scopes.items() if k != "T0r85"),
            }
        if spec_name == "call_log":
            client_ok = 1 if (client_rows is not None
                              and vis.get("T0r85", 0) >= tree_rows) else 0
            per["call_log"]["in_tree"] = client_ok
            per["call_log"]["client_rows_returned"] = (len(client_rows)
                                                       if client_rows is not None else 0)
            per["call_log"]["client_visible_T0r85_rows"] = vis.get("T0r85", 0)
            per["call_log"]["client_visible_bug_rows"] = sum(
                v for k, v in vis.items() if k != "T0r85")
            if client_err:
                per["call_log"]["error"] = client_err
        in_stage = sum(v["this_stage_seed"] + v["in_tree"] + v["in_bug_cards"]
                       for v in per.values())
        carriers[spec_name] = {"carriers": per, "this_stage_total": in_stage}
        if in_stage == 0:
            if spec_name == "omega" and not final:
                # 预渲染快照：Omega 链在"报告渲染之后"的收口批里才执行（法 ⑥ 的顺序），
                # 此刻 0 次是顺序使然而非漏做 ⇒ 用库侧标记数替代，并写明边界。
                carriers[spec_name]["deferred_to_closure"] = True
                carriers[spec_name]["marked_leaves"] = leaves_marked
                carriers[spec_name]["marked_branches"] = con.execute(
                    "select count(*) from tasks where ns=? and id like 'T0r85.%.%' and depth=2 "
                    "and description like '%[omega:required]%'", (NS,)).fetchone()[0]
            else:
                refuse.append(f"规格点名的 {spec_name} 本环 0 次调用 ⇒ 不许写『已开启』")

    absent = con.execute("select count(*) from call_log where "
                         "json_extract(params_json,'$.task_id') like ?",
                         (f"{NEEDLE_ABSENT}%",)).fetchone()[0]
    if absent != 0:
        refuse.append(f"对照前缀 {NEEDLE_ABSENT} 数出 {absent} 行（应为 0）⇒ 过滤器恒真")
    named = {t: {"exact": con.execute("select count(*) from call_log where tool=?",
                                      (t,)).fetchone()[0],
                 "substring": con.execute("select count(*) from call_log where tool like ?",
                                          (f"%{t}%",)).fetchone()[0]} for t in NAMED_TOOLS}
    con.close()

    groups, order = {}, []
    for d in all_detail:
        key = d["err"] or "(空 result_json)"
        if key not in groups:
            groups[key] = {"count": 0, "first": f'{d["task"]} @ {d["ts"]}',
                           "tool": d["tool"]}
            order.append(key)
        groups[key]["count"] += 1
    lines = ["| 被拒原文（逐字） | 工具 | 次数 | 首个见证 |", "| --- | --- | --- | --- |"]
    for key in order:
        g = groups[key]
        quoted = key.replace("|", "\\|").replace("\n", "⏎")
        lines.append(f'| `{quoted}` | {g["tool"]} | {g["count"]} | {g["first"]} |')
    refusals_md = "\n".join(lines) if order else "（本环 0 条被拒调用，故无原文可引）"
    if sum(g["count"] for g in groups.values()) != tree_refused + card_refused:
        refuse.append(f"逐字分组合计 {sum(g['count'] for g in groups.values())} ≠ refused 合计 "
                      f"{tree_refused + card_refused} ⇒ 分组漏行")
    if order and len(order) < 2:
        refuse.append(f"被拒原文只有 {len(order)} 种而 refused 有 {tree_refused + card_refused} 条 "
                      "⇒ 检查是否把不同拒因折叠成了一条")

    doc = {"mode": "final_after_closure" if final else "pre_render_snapshot",
           "grouped_by": "params_json.task_id（树按 T0r85.% 前缀，六张修复单按整号）",
           "stage_seed_needle": STAGE_SEED, "stage_seed_rows": len(seed_rows),
           "stage_seed_by_tool": seed_by_tool,
           "omega_marked": {"leaves": leaves_marked, "leaves_total": leaves_total,
                            "root": root_marked},
           "scopes": scopes, "tree_rows": tree_rows, "bug_card_rows": card_rows,
           "tree_refused": tree_refused, "bug_card_refused": card_refused,
           "client_visible": vis, "total_call_log_rows": total_all,
           "spec_named_carriers": carriers, "named_tools_in_this_build": named,
           "distinct_refusal_texts": len(order), "refusals_md": refusals_md,
           "note": ("收口后的终账：含 16 叶 + 8 支 + 根的 Omega/门禁链逐调用" if final else
                    "报数分栏：任务树与 bugs 树的修复单是两套 ns，只报其一就是掩盖。"
                    "本件是**渲染前快照**，叶/根收口链在渲染之后执行 ⇒ 其逐调用看 "
                    "fix_r4_calllog_tally_final.json 与 close_r4_fix*.out.json"),
           "refuse": sorted(set(refuse)),
           "queried_at_utc": datetime.datetime.now(
               datetime.timezone.utc).isoformat(timespec="seconds")}
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "tree_rows": tree_rows,
                      "tree_refused": tree_refused, "bug_card_rows": card_rows,
                      "bug_card_refused": card_refused,
                      "distinct_refusal_texts": len(order),
                      "carriers": {k: v["this_stage_total"] for k, v in carriers.items()},
                      "stage_seed_rows": len(seed_rows),
                      "by_tool_tree": scopes["T0r85"]["by_tool"]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
