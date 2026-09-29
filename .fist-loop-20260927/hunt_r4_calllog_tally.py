"""R4-寻虫 的 call_log 对账：按 `params_json.task_id` 前缀分组数，不按标签、不按回忆。

三条自证（缺一条这栏就是装饰）：
① 每个前缀的逐工具计数之和 == 该前缀总行数（分组不许吞行）；
② `refused` 计数 == `refused_detail` 条数（拒收清单不是手数出来的）；
③ 拿一个**必然不存在**的前缀当对照，必须数出 0 行——否则这个过滤是恒真的。
另开一栏如实回答"规格点名的工具在这个 build 里到底存不存在"：`laya`/`issue_up` 若在 call_log
里 0 命中，就不许假装开过，要写明等价能力由哪一步承担。
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
PREFIXES = {"T0r74": "R4-寻虫（16 叶 × omega 全链 + 8 支 + 根上卷）"}
NEEDLE_ABSENT = "T0r9ZZZ-not-a-task"
NAMED_TOOLS = ["laya", "issue_up", "omega_spec_create", "omega_result_verify", "report_bug",
               "output_validate", "submit", "claim", "verify"]
# 规格点名的工具名在本 build 里不一定存在——承担同一能力的是这些实际工具名
CARRIERS = {"laya": ["laya_decide"], "issue_up": ["publish", "report_bug"], "call_log": ["call_log"]}
STAGE_SEED = "%[loop:20260927-loop:R4-%"
OUT = HERE / "hunt_r4_calllog_tally.json"


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    refuse, out = [], {}
    total_all = con.execute("select count(*) from call_log").fetchone()[0]
    stages = {}
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
            tid = pj.get("task_id") or "?"
            leaf_ids.add(tid)
            slot = by_tool.setdefault(tool, {"ok": 0, "refused": 0})
            slot["ok" if ok else "refused"] += 1
            if not ok:
                refused_detail.append({"task": tid, "tool": tool, "ts": ts,
                                       "err": (result or "")[:500]})
        summed = sum(v["ok"] + v["refused"] for v in by_tool.values())
        if summed != len(rows):
            refuse.append(f"{prefix}：逐工具合计 {summed} ≠ 该前缀行数 {len(rows)} ⇒ 分组吞了行")
        n_refused = sum(v["refused"] for v in by_tool.values())
        structured = [d for d in refused_detail if isinstance(d, dict)]
        if n_refused != len(structured):
            refuse.append(f"{prefix}：refused 计数 {n_refused} ≠ 明细条数 {len(structured)}")
        stages[prefix] = {"label": label, "rows": len(rows), "distinct_tasks": len(leaf_ids),
                          "by_tool": by_tool, "refused": n_refused,
                          "refused_total": n_refused,
                          "refused_detail": refused_detail}
    # 环种子那一档：laya/publish/report_bug 的 params 里没有 task_id，只按前缀数必然数到 0
    seed_rows = list(con.execute(
        "select tool, ok, ts, substr(result_json,1,300) from call_log "
        "where params_json like ? order by id", (STAGE_SEED,)))
    seed_by_tool = {}
    for tool, ok, ts, result in seed_rows:
        slot = seed_by_tool.setdefault(tool, {"ok": 0, "refused": 0, "examples": []})
        slot["ok" if ok else "refused"] += 1
        if not ok and len(slot["examples"]) < 3:
            slot["examples"].append({"ts": ts, "err": result})
    carriers = {}
    # 真打一次客户端的 call_log 工具：自读 sqlite 不等于『开过 call_log』
    call = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "lfist.py"), "call_log",
         json.dumps({"limit": 2500, "namespace": "cypy-loop-20260927", "project_dir": "."},
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
    client_prefix = (sum(1 for c in client_rows if "T0r74" in (c.get("params") or ""))
                     if client_rows is not None else 0)
    if client_rows is None:
        refuse.append(f"call_log 工具没调通：{client_err}")
    elif client_prefix < stages["T0r74"]["rows"]:
        refuse.append(f"call_log 工具只回 {client_prefix} 行含 T0r74（sqlite 同口径 "
                      f"{stages['T0r74']['rows']} 行）⇒ 工具面看不到这些调用")
    client_ok = 1 if (client_rows is not None and client_prefix >= stages["T0r74"]["rows"]) else 0
    for spec_name, real_tools in CARRIERS.items():
        per = {}
        for t in real_tools:
            per[t] = {
                "whole_db": con.execute("select count(*) from call_log where tool=?", (t,)).fetchone()[0],
                "this_stage_seed": sum(v["ok"] + v["refused"] for k, v in seed_by_tool.items() if k == t),
                "this_stage_prefix": sum(v["ok"] + v["refused"]
                                         for k, v in stages["T0r74"]["by_tool"].items() if k == t),
            }
        if spec_name == "call_log":
            per["call_log"]["this_stage_prefix"] = client_ok
            per["call_log"]["client_visible_T0r74_rows"] = client_prefix
            per["call_log"]["client_rows_returned"] = (len(client_rows) if client_rows is not None else 0)
            if client_err:
                per["call_log"]["error"] = client_err
        hit = sum(v["whole_db"] for v in per.values())
        in_stage = sum(v["this_stage_seed"] + v["this_stage_prefix"] for v in per.values())
        carriers[spec_name] = {"carriers": per, "whole_db_total": hit, "this_stage_total": in_stage}
        if in_stage == 0:
            refuse.append(f"规格点名的 {spec_name} 本轮（R4 种子 + T0r74 前缀）0 次调用 ⇒ 不许写『已开启』")
    absent = con.execute("select count(*) from call_log where "
                         "json_extract(params_json,'$.task_id') like ?",
                         (f"{NEEDLE_ABSENT}%",)).fetchone()[0]
    if absent != 0:
        refuse.append(f"对照前缀 {NEEDLE_ABSENT} 数出 {absent} 行（应为 0）⇒ 过滤器恒真")
    named = {}
    for t in NAMED_TOOLS:
        n = con.execute("select count(*) from call_log where tool=?", (t,)).fetchone()[0]
        like = con.execute("select count(*) from call_log where tool like ?",
                           (f"%{t}%",)).fetchone()[0]
        named[t] = {"exact": n, "substring": like}
    con.close()
    # 被拒原文逐字：按错误文本去重分组，每组给次数 + 一个 task/ts 见证（不进表格单元，纯文本行）
    groups, order = {}, []
    for d in stages["T0r74"]["refused_detail"]:
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
    refusals_md = "\n".join(lines)
    distinct_refusals = len(order)
    if sum(g["count"] for g in groups.values()) != stages["T0r74"]["refused"]:
        refuse.append(f"逐字分组次数合计 {sum(g['count'] for g in groups.values())} ≠ refused 计数 "
                      f"{stages['T0r74']['refused']} ⇒ 分组漏行")
    doc = {"grouped_by": "params_json.task_id 前缀（不按标签、不按回忆）",
           "stages": stages, "control_absent_prefix_rows": absent,
           "total_call_log_rows": total_all,
           "stage_seed_rows": {"needle": STAGE_SEED, "total": len(seed_rows), "by_tool": seed_by_tool},
           "named_tools_in_this_build": named,
           "spec_named_carriers": carriers,
           "distinct_refusal_texts": distinct_refusals,
           "refusals_md": refusals_md,
           "note": "规格点名的 laya / issue_up 若在 call_log 里 0 命中，说明本 build 没有这两个工具名；"
                   "等价能力由谁承担要写在报告里，不许写『已开启』",
           "refuse": sorted(set(refuse)),
           "queried_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"],
                      "rows_T0r74": stages["T0r74"]["rows"],
                      "distinct_tasks": stages["T0r74"]["distinct_tasks"],
                      "refused_T0r74": stages["T0r74"]["refused"],
                      "stage_seed_total": len(seed_rows),
                      "carriers": {k: v["this_stage_total"] for k, v in carriers.items()},
                      "by_tool": stages["T0r74"]["by_tool"],
                      "named": {k: v["exact"] for k, v in named.items()}},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
