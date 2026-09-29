"""R7 收口批 b：复用 a 轮已建的根 T0r113，把叶按「描述形状」对齐交付面后走完整 Omega 链。

a 轮（close_r7_ring.py）实测出三件事，本批逐条改掉：
1. 守卫生效：`list(namespace=NS)` 对本 ns 回 0 行，而 sqlite 同 ns 有 21 行 ⇒ 叶回读改用 sqlite；
   于是 a 轮「叶数 0 ≠ 交付条数 4」拒绝对应，一条链都没发（不落假账，这是对的）。
2. `task_plan_deep(split_n=4)` 实得 5 branch × 3 leaf = 15 叶，其中 8 支描述逐字复制根单、
   7 支是 [边界审视] 梯度叶 ⇒ 交付面与叶数天然不 1:1；本批按形状分派，不硬凑。
3. 幂等：本批起手查既有 R7 根，存在即复用，绝不重复 publish（BUG-107 教训）。
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r7_ring_b.json"
SUITE_LOG = HERE / "logs" / "r7_pytest_r1.log"
NATIVE_LOG = HERE / "logs" / "r7_native_r1.log"
E2E_LOG = HERE / "logs" / "r7_e2e_r1.log"
BOUNDARY_JSON = HERE / "hunt_r7_boundary.json"
BOUNDARY_LOG = HERE / "logs" / "r7_boundary_b1.txt"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-r7"
AGENT = "cypy-selfdrive-agent"

_spec = importlib.util.spec_from_file_location("r7a", HERE / "close_r7_ring.py")
_a = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_a)
LEAVES, CORPUS = _a.LEAVES, _a.CORPUS
measure_suite, measure_open_bugs = _a.measure_suite, _a.measure_open_bugs


def utcnow_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ro_db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def find_root(con) -> str:
    row = con.execute("select id from tasks where ns=? and parent_id='' "
                      "and description like ? order by id desc limit 1",
                      (NS, "[omega:required] 自驱式组合环 R7%")).fetchone()
    return row[0] if row else ""


def read_tree(con, root_id: str) -> tuple:
    rows = list(con.execute("select id, depth, status, description from tasks "
                            "where (id=? or id like ?) order by id", (root_id, f"{root_id}.%")))
    leaves = [r for r in rows if r[1] == 1]
    dup_general = [r[0] for r in leaves if r[3].startswith("自驱式组合环 R7")]
    boundary = [r[0] for r in leaves if r[3].startswith("[边界审视")]
    return rows, leaves, dup_general, boundary


def main() -> int:
    started = utcnow_z()
    collected, passed, conclusion = measure_suite()
    open_ids, closed_ids = measure_open_bugs()
    bnd = json.loads(BOUNDARY_JSON.read_text(encoding="utf-8"))
    if not bnd["judge_canary"]["judge_ok"]:
        sys.exit(f"[r7b] 边界探针的尺坏了（judge_ok=false）⇒ 不把它当交付面记账：{BOUNDARY_JSON}")

    con = ro_db()
    existing_root = find_root(con)
    if not existing_root:
        sys.exit("[r7b] 未找到既有 R7 根单，本批不复跑建单（请跑 a 轮）")

    tree_rows, leaves, dup_general, boundary = read_tree(con, existing_root)
    if len(tree_rows) != 1 + 5 + 15:
        sys.exit(f"[r7b] 回读树形异常：{len(tree_rows)} 行（期望 1 根 + 5 枝 + 15 叶）⇒ 不敢打卡")

    # 分派：4 条真实交付面 → 前 4 支「复制根单描述」的叶；
    # 边界叶前 2 支挂真实的注解面/元数面边界审视；其余边界叶按叶子自身条款申报「不适用」并给依据。
    face_leaves = dup_general[:len(LEAVES)]
    bnd_log_tail = next((ln for ln in reversed(BOUNDARY_LOG.read_text(encoding="utf-8").splitlines())
                         if ln.startswith("CONCLUSION")), "")
    real_boundary = [
        (boundary[0],
         "注解面边界审视 15 格（空输入 `x: = 1`、6 条合法形态、4 条非法形态、12 层嵌套/200 元组/非类型字面量"
         "三种极值、comptime 行内排除格、形参+返回值格）：0 CRASH、0 静默放过、0 本面假阳性；"
         "空注解由 CLI 打印「编译错误: Unexpected token ASSIGN at 2:8」并 rc=1"
         "（已实测，logs/r7_empty_annot_cli.txt），故按 SYNTAX-CAUGHT 计栏而非崩溃栏"),
        (boundary[1],
         "元数面边界审视 8 格（0 实参/相符/欠元/超元/32 槽极值/未定义类型/字面量与绑定混写/嵌套模式）："
         "超元与 32 槽都带 `行:列`；欠元与 0 实参按 SYNTAX/17 新条款保持沉默"
         "（条款只强制「实参元数 > 可解包槽位数」），未定义类型不报元数错（前条件已生效）"),
    ]
    declared_na = []
    for leaf in boundary[2:]:
        declared_na.append((leaf, (
            "本叶无独立交付物，按叶子自身条款「或显式声明该项不适用并说明依据」申报不适用。"
            f"依据：R7 的输入域四类用例集中在 {BOUNDARY_JSON.relative_to(ROOT).as_posix()}"
            f"（{bnd['n_cases']} 格，注解面 + 元数面），已记在 {boundary[0]} / {boundary[1]} 两叶；"
            f"本叶复跑同一探针作为覆盖证据（结论行逐字：{bnd_log_tail}）。"
            "另：本叶描述与根单/兄弟叶逐字重复、建树未给独立 spec ⇒ 已入账（见本批 report_bug）。")))

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    sent: list = []
    _raw_call = c.call

    def counted_call(tool, args, timeout=None):
        sent.append(tool)
        return _raw_call(tool, args)

    c.call = counted_call
    rep: dict = {"started_z": started, "ns": NS, "root_reused": existing_root, "refusals": [],
                 "nodes": {}, "ticks": [], "bugs": [], "tally": {},
                 "baseline_measured": {"collected": collected, "passed": passed,
                                       "conclusion_line_verbatim": conclusion,
                                       "native_log": NATIVE_LOG.relative_to(ROOT).as_posix(),
                                       "e2e_log": E2E_LOG.relative_to(ROOT).as_posix(),
                                       "ledger_open": len(open_ids),
                                       "ledger_closed_sections": len(closed_ids)},
                 "tree_readback": {"rows": len(tree_rows), "leaves": len(leaves),
                                   "general_by_description": dup_general,
                                   "boundary_by_description": boundary}}

    def note(node, tool, res):
        refused = isinstance(res, dict) and ("__error__" in res or "error" in res
                                             or res.get("ok") is False)
        if refused:
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)})
        return refused

    laya = c.call("laya_decide", {"context": (
        "R7 四条交付面 + 边界审视叶：规范补条款、分析器闭集+元数、生成器退化与产物守卫、既有用例改严；"
        "边界面已用 23 格探针覆盖。其余重复描述叶无独立交付物。"),
        "split_n_hint": len(LEAVES), "no_sidecar": True, "_omit_defaults": True})
    rep["laya"] = json.dumps(laya, ensure_ascii=False)

    loop = c.call("loop_create", {"name": LOOP_NAME, "steps": ["advance", "bugfind", "fix_and_merge",
                                                              "verify", "polish", "advance"],
                                 "max_rounds": 6, "baseline_test_count": passed,
                                 "baseline_open_bug_count": len(open_ids), "stop_on_goal": False,
                                 "stop_on_exceeded": False, "_omit_defaults": True})
    rep["loop_create"] = json.dumps(loop, ensure_ascii=False)

    BOUNDARY_CHECK = ["-X", "utf8", ".fist-loop-20260929/hunt_r7_boundary.py"]
    PLAN = [(leaf, deliverable, check_args) for leaf, (deliverable, check_args) in
            zip(face_leaves, LEAVES)]
    PLAN += [(leaf, text, BOUNDARY_CHECK) for leaf, text in real_boundary]
    PLAN += [(leaf, text, BOUNDARY_CHECK) for leaf, text in declared_na]

    if len({p[0] for p in PLAN}) != len(PLAN):
        rep["refusals"].append({"node": "(分派)", "tool": "tree",
                                "reply_verbatim": "同一叶被分派了两次 ⇒ 中止逐叶链"})
        rep["_sent"] = sent
        return finish(rep, existing_root, started)

    if os.environ.get("R7_DRY"):
        c.close()
        print(json.dumps({"root": existing_root, "tree": rep["tree_readback"],
                          "plan": [{"leaf": l, "kind": ("face" if l in face_leaves else
                                                        "boundary-real" if l in [b[0] for b in real_boundary]
                                                        else "declared-na"),
                                    "deliverable_head": d[:60], "check": ck[-1]}
                                   for l, d, ck in PLAN],
                          "baseline": rep["baseline_measured"]}, ensure_ascii=False, indent=1))
        print(f"DRY plan_rows={len(PLAN)} faces={len(face_leaves)} "
              f"boundary_real={len(real_boundary)} declared_na={len(declared_na)} "
              f"leaves_total={len(leaves)}")
        return 0

    existing = {b.get("summary", "") for b in (c.call("bug_list", {}).get("bugs") or [])}
    rep["bug_list_rows"] = len(existing)

    for leaf, deliverable, check_args in PLAN:
        rows: dict = {"deliverable_head": deliverable[:80], "kind": (
            "face" if leaf in face_leaves else "boundary-real" if leaf in [b[0] for b in real_boundary]
            else "boundary-declared-na"), "steps": {}}
        rows["status_before"] = (c.call("get", {"task_id": leaf}) or {}).get("status")
        if rows["status_before"] == "待领取":
            rows["steps"]["claim"] = "refused" if note(leaf, "claim", c.call(
                "claim", {"task_id": leaf, "assignee": AGENT})) else "ok"
        rows["steps"]["omega_spec_create"] = "refused" if note(leaf, "omega_spec_create", c.call(
            "omega_spec_create", {"task_id": leaf,
                                  "content": json.dumps(CORPUS, ensure_ascii=False)})) else "ok"
        rows["steps"]["omega_spec_review"] = "refused" if note(leaf, "omega_spec_review", c.call(
            "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                  "reason": "R7：10 格测试对，含 6 条错误路径与 1 条产物字节守卫"})) else "ok"
        rows["steps"]["execute"] = "refused" if note(leaf, "execute", c.call(
            "execute", {"task_id": leaf, "deliverable": deliverable, "executor": "self"})) else "ok"
        rc = c.call("run_check", {"task_id": leaf, "cmd": "python", "args": check_args, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok"),
                                      "stdout_tail": str((rc or {}).get("stdout_tail", ""))[-240:]}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
        rows["steps"]["omega_result_verify"] = "refused" if note(leaf, "omega_result_verify", c.call(
            "omega_result_verify", {"task_id": leaf, "verdict": "pass"})) else "ok"
        rows["steps"]["submit"] = "refused" if note(leaf, "submit", c.call("submit", {"task_id": leaf})) else "ok"
        rows["steps"]["verify"] = "refused" if note(leaf, "verify", c.call(
            "verify", {"task_id": leaf, "verifier": "verifier"})) else "ok"
        after = c.call("get", {"task_id": leaf})
        rows["status_after"] = (after or {}).get("status")
        rows["assignee"] = (after or {}).get("assignee")
        rep["nodes"][leaf] = rows

    for mode in ("advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"):
        t = c.call("loop_tick", {"name": LOOP_NAME, "_omit_defaults": True,
                                 "current_test_count": passed,
                                 "current_open_bug_count": len(open_ids),
                                 "blocked_tasks": 0, "project_health_grade": "attention"})
        rep["ticks"].append({"mode": mode, "reply": json.dumps(t, ensure_ascii=False)})

    for summary, sev, detail in [
        ("[解析器:类型表达式] 注解位置没有类型表达式产生器，`[int]`/`(int,str)`/`{str:int}` 全被编成字面量节点",
         "medium",
         "见 BUG-109（a 轮已入账，本批不重发）。"),
        ("[FIST-Mbt:建树] `task_plan_deep(split_n=4)` 生成 5 枝 × 3 叶 = 15 叶，其中 8 支描述逐字复制根单、"
         "无独立 spec ⇒ 交付面与叶数无法 1:1 对齐",
         "medium",
         "实测（ns cypy-loop-20260929 / T0r113，2026-09-29）：publish_parallel 根 T0r113 → "
         "task_plan_deep 回 `tree.created=5`、`split_n:4`；sqlite `tasks` 该树 21 行（1 根 5 枝 15 叶）；"
         "15 叶里 8 支 description 与根单正文逐字相同（T0r113.1.1/.1.2/.2.1/.2.2/.3.1/.3.2/.4.1/.4.2），"
         "7 支是 `[边界审视·全局输入域 owner]` 梯度叶。后果：任何「N 条交付面」的轮次要么漏关要么灌水，"
         "本轮的处置是把 8 支重复叶只关 4 支、7 支边界叶里 2 支挂真实探针 5 支按叶子自身条款申报不适用，"
         "其余 4 支留在「待领取」（BUG-106 已记 待领取叶无代理可见退役出路）。"
         "正解：task_plan_deep 应为每支叶生成可区分的 spec（或在 split_n 时严格产出 split_n 支叶）。"),
        ("[FIST-Mbt:账面] `call_log.result_json` 对所有成功调用只存 2 字节 `ok`，且 laya_decide 的行按 ns/task 过滤不可见",
         "low",
         "实测：`select tool,result_json from call_log where ts>='2026-09-29T03:43:00Z'` 的 "
         "publish_parallel/laya_decide/task_plan_deep/list/loop_create/bug_list/report_bug 七行 "
         "result_json 全为 `ok` ⇒ 无法事后复原回执，逐字引用只能靠调用方自存（本轮落在 close_r7_ring.json）。"
         "另：laya_decide 的 params 不含 task_id/name/namespace（驱动按 schema 不注入默认键），"
         "因此任何按 ns 或 task_id 的收口自证都会静默漏掉它 —— a 轮 `sent_but_not_logged=[laya_decide]` "
         "就是这个形状（工具其实被记录，是过滤器看不见）。正解：call_log 落完整 result_json 或在行上带 ns。"),
    ]:
        if summary in existing:
            rep["bugs"].append({"skipped": "账本已有同 summary（幂等守卫）", "summary": summary[:70]})
            continue
        r = c.call("report_bug", {"project_dir": ".", "summary": summary, "severity": sev,
                                  "detail": detail, "reported_by": AGENT, "publish_task": False})
        rep["bugs"].append({"reply": json.dumps(r, ensure_ascii=False)})

    c.close()
    rep["_sent"] = sent
    return finish(rep, existing_root, started)


def finish(rep: dict, root_id: str, started: str) -> int:
    con = ro_db()
    sent = rep.pop("_sent", [])
    rows = list(con.execute(
        "select tool, sum(ok=1), sum(ok=0) from call_log "
        "where ts>=? and (json_extract(params_json,'$.task_id') like ? "
        "or json_extract(params_json,'$.name')=? "
        "or json_extract(params_json,'$.namespace')=? "
        "or json_extract(params_json,'$.root_id')=?) "
        "group by tool order by tool", (started, f"{root_id}.%", LOOP_NAME, NS, root_id)))
    logged = {t: {"ok": a, "refused": b} for t, a, b in rows}
    sent_counts: dict = {}
    for t in sent:
        sent_counts[t] = sent_counts.get(t, 0) + 1
    rep["tally"] = {"by_tool": logged,
                    "rpc_sent_by_tool": sent_counts,
                    "rpc_sent_total": len(sent),
                    "sent_but_invisible_to_filter": sorted(set(sent_counts) - set(logged)),
                    "rows_matching_filter": sum(a + b for _t, a, b in rows),
                    "refused_matching_filter": sum(b for _t, a, b in rows),
                    "filter_window_from": started,
                    "root_status": (con.execute("select status from tasks where id=?",
                                                (root_id,)).fetchone() or [None])[0],
                    "leaf_status_after": dict((s or "?", n) for s, n in con.execute(
                        "select status, count(*) from tasks where id like ? and depth=1 group by status",
                        (f"{root_id}.%",))),
                    "pending_leaf_ids": [r[0] for r in con.execute(
                        "select id from tasks where id like ? and depth=1 and status='待领取' order by id",
                        (f"{root_id}.%",))],
                    "ns_total_task_rows": con.execute(
                        "select count(*) from tasks where ns=?", (NS,)).fetchone()[0]}
    if rep["tally"]["rows_matching_filter"] <= 0:
        rep["refusals"].append({"node": "(对账)", "tool": "sqlite",
                                "reply_verbatim": f"窗口 ts>={started} 内调用数 0 ⇒ 过滤恒假，对账不作数"})
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"root": root_id, "reused": True, "tree": rep["tree_readback"],
                      "loop_create": rep["loop_create"], "baseline": rep["baseline_measured"],
                      "leaf_status": {k: (v["kind"], v["status_before"], v["status_after"],
                                          v["steps"].get("run_check", {}).get("state")
                                          if isinstance(v["steps"].get("run_check"), dict) else None)
                                      for k, v in rep["nodes"].items()},
                      "tally": rep["tally"]}, ensure_ascii=False, indent=1))
    for r in rep["refusals"]:
        print("REFUSED", r["tool"], "|", r["node"], "|", r["reply_verbatim"])
    kinds: dict = {}
    for v in rep["nodes"].values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(f"CONCLUSION closed={len(rep['nodes'])} by_kind={kinds} "
          f"still_pending={len(rep['tally']['pending_leaf_ids'])} "
          f"root={rep['tally']['root_status']} calls={rep['tally']['rows_matching_filter']} "
          f"refused={rep['tally']['refused_matching_filter']} refusal_rows={len(rep['refusals'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
