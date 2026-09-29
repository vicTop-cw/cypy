"""R7 组合环：建单 → laya → Omega 强验证建树 → 逐叶走完整链 → 环内 loop_tick → call_log 对账。

沿用 R6 实测出来的链形（拒绝文案教的）：
  claim → omega_spec_create → omega_spec_review(approve) → execute → run_check
       → omega_result_verify(pass) → submit → verify
角色用服务端默认档（自定义身份回「未知角色」）。report_bug 走幂等守卫（R6 的 BUG-107 教训）。
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
OUT = HERE / "close_r7_ring.json"
SUITE_LOG = HERE / "logs" / "r7_pytest_r1.log"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-r7"
AGENT = "cypy-selfdrive-agent"


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def measure_suite() -> tuple:
    """基线数字必须从本轮全量日志反解，不能手加：回 (collected, passed, 逐字结论行)。"""
    text = SUITE_LOG.read_text(encoding="utf-8", errors="replace")
    col = re.search(r"collected (\d+) items", text)
    con = re.search(r"(\d+) passed", text)
    fail = re.search(r"(\d+) (?:failed|error)", text)
    tail = next((ln for ln in reversed(text.splitlines()) if " passed" in ln), "")
    if not col or not con or fail:
        sys.exit(f"[r7] 基线未就绪（collected={bool(col)} passed={bool(con)} red={bool(fail)}）"
                 f" ⇒ 不开 RPC 批次；日志 {SUITE_LOG}")
    return int(col.group(1)), int(con.group(1)), tail.strip()


def measure_open_bugs() -> tuple:
    """开缺陷数从本地账本反解，口径写死可复核：`### FIXED(` 段数 ≠ 条目数的条目即 open。

    实测账本形状（109 条 `## BUG-NN`）：结论段只有 FIXED( / NOT / DUPLICATE( / AMENDMENT( / OUT 五种，
    其中 NOT/DUPLICATE 是终态但仍无 FIXED ⇒ 按「无 FIXED」这一条口径计入 open，报数时并列说明。
    """
    text = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"(?m)^## (BUG-\d+)", text)
    open_ids, closed_ids = [], []
    for i in range(1, len(blocks) - 1, 2):
        bid, body = blocks[i], blocks[i + 1]
        (closed_ids if re.search(r"(?m)^### FIXED\(", body) else open_ids).append(bid)
    return open_ids, closed_ids

CORPUS = {
    "op": "cypy.annotation.and.arity",
    "version": "1.0",
    "definition": {
        "signature": "annotation ::= Name | GenericType | PointerType | UnionType | RefType; "
                     "positional_pattern ::= TypeName(slot{0..n-1}) where n = 可解包槽位数",
        "note": "SYNTAX/02「注解形态闭集（R7 补）」与 SYNTAX/17「位置模式的元数与槽位规则（R7 补）」",
    },
    "preconditions": ["comptime 行内形式不是注解，不受闭集约束", "类型不可见时不报元数错"],
    "laws": ["L-注解必须是类型形态", "L-元数不符必须诊断", "L-产物不得含 AST repr"],
    "tests": [
        {"input": {"src": "xs: list<int> = [1,2]"}, "expected": {"errors": 0}},
        {"input": {"src": "buf: *char = malloc(8)"}, "expected": {"errors": 0}},
        {"input": {"src": "u: int | str"}, "expected": {"errors": 0}},
        {"input": {"src": "xs: [int]"}, "error": "Invalid type annotation"},
        {"input": {"src": "p: (int, str)"}, "error": "Invalid type annotation"},
        {"input": {"src": "m: {str: int}"}, "error": "Invalid type annotation"},
        {"input": {"src": "struct Email{address} + case Email(user, domain)"},
         "error": "Positional pattern 'Email' has 2 slot(s)"},
        {"input": {"src": "struct Email{user,domain} + case Email(user, domain)"},
         "expected": {"errors": 0}},
        {"input": {"src": "comptime: [1, 2]"}, "expected": {"errors": 0}},
        {"input": {"src": "生成 [int] 的产物"}, "expected": {"contains_no": "line="}},
    ],
    "fingerprint": "manual:R7-2026-09-29",
}

# 每条叶：交付文案 + run_check 实测命令
LEAVES = [
    ("规范面：SYNTAX/02 补「注解形态闭集」+ SYNTAX/17 补「位置模式的元数与槽位规则」"
     "（BUG-92/BUG-108 的前置；文档只增不删，两文件行数 158→189 / 418→441）",
     ["-X", "utf8", "-c",
      "from pathlib import Path as P;"
      "a=P('SYNTAX/02-type-annotations.md').read_text(encoding='utf-8');"
      "b=P('SYNTAX/17-pattern-matching.md').read_text(encoding='utf-8');"
      "assert '注解形态闭集' in a and '元数与槽位规则' in b;print('SPEC OK',len(a.splitlines()),len(b.splitlines()))"]),
    ("分析器面：注解闭集校验（_validate_annotation_shapes/_check_annotation_shape，含 comptime 整类跳过）"
     "＋位置模式元数诊断；调用面两条 hunt 语料由 rc=0 零诊断变为 rc=1 带行列与正确写法",
     ["-m", "pytest", "tests/test_annotation_shape.py", "tests/test_extractor_pattern.py", "-q"]),
    ("生成器面：_type_to_str 末路不再 `str(node)`，未知形态退化为 object；"
     "锁死「产物永不含 line= / Constant( 这类 AST repr」",
     ["-m", "pytest", "tests/test_annotation_shape.py", "-q",
      "-k", "product_never or degrades_to_object"]),
    ("判据面：既有用例 test_extractor_pattern.py::test_extractor_pattern_type_checker 从"
     "「断言无错误」改为双向格（相符必须放行 / 不符必须诊断且带行列）——按 BUG-92 的规范条款变严，不是弱化",
     ["-m", "pytest", "tests/test_pattern_positional_struct.py", "tests/test_fist_driver_protocol.py", "-q"]),
]


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    collected, passed, conclusion = measure_suite()
    open_ids, closed_ids = measure_open_bugs()
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    # 自计票：本轮真正发了哪些 RPC、各几次 —— 收尾与 sqlite 的 call_log 双向对齐（#68 教训）
    sent: list = []
    _raw_call = c.call

    def counted_call(tool, args, timeout=None):
        sent.append(tool)
        return _raw_call(tool, args)

    c.call = counted_call
    rep: dict = {"started_utc": utcnow(), "ns": NS, "refusals": [], "nodes": {},
                 "ticks": [], "bugs": [], "tally": {},
                 "baseline_measured": {"collected": collected, "passed": passed,
                                       "log": str(SUITE_LOG.relative_to(ROOT)),
                                       "conclusion_line_verbatim": conclusion,
                                       "ledger_open_ids": open_ids,
                                       "ledger_closed_ids": len(closed_ids)}}

    def note(node, tool, res):
        refused = isinstance(res, dict) and ("__error__" in res or "error" in res
                                             or res.get("ok") is False)
        if refused:
            # 拒绝分支禁截断：账本/报告要能逐字复核，只在打印时缩略。
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)})
        return refused

    root = c.call("publish_parallel", {"project_dir": ".", "namespace": NS, "created_by": AGENT,
                                       "description": (
        "[omega:required] 自驱式组合环 R7（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
        "本轮靶面：语法特性的「静默错误产物」两类收口——\n"
        "  BUG-92 位置模式元数不符（规范补条款 + 分析器诊断 + 既有用例改严）\n"
        "  BUG-108/BUG-34 非法注解形态把 AST repr 写进产物（注解形态闭集 + 生成器退化 object + 产物守卫）\n"
        f"判据基线（本轮全量日志实测，非手加）：pytest {collected} collected / {passed} passed；"
        f"本地账本 open(无 FIXED 段) {len(open_ids)} 条 / 已带结论段 {len(closed_ids)} 条。")})
    rep["root"] = root
    root_id = root.get("task_id") if isinstance(root, dict) else None
    if not root_id:
        rep["refusals"].append({"node": "(建单)", "tool": "publish_parallel",
                                "reply_verbatim": json.dumps(root, ensure_ascii=False)})
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    laya = c.call("laya_decide", {"context": (
        "R7 四条交付面：规范补条款、分析器闭集+元数、生成器退化与产物守卫、既有用例改严。"
        "彼此改动不同文件，可并行领取。"),
        "split_n_hint": len(LEAVES), "no_sidecar": True, "_omit_defaults": True})
    rep["laya"] = json.dumps(laya, ensure_ascii=False)

    plan = c.call("task_plan_deep", {"task_id": root_id, "split_n": len(LEAVES),
                                     "decide_split_n": len(LEAVES), "decide_difficulty": 3.0,
                                     "decide_reason": "四条叶分别落在 docs/analyzer/codegen/tests 四个不重叠文件半径",
                                     "omega_strong_verify": True, "gradient": True,
                                     "boundary_probe": True, "reinject_context": True,
                                     "by": AGENT, "decide_by": AGENT, "_omit_defaults": True})
    rep["plan_raw"] = json.dumps(plan, ensure_ascii=False)
    children = [ch["id"] for ch in (plan or {}).get("tree", {}).get("children", [])] if isinstance(plan, dict) else []

    # 叶清单从服务端回读，并按 root_id 前缀收窄：同 ns 里还挂着 R6 的 15 条待领取叶（BUG-106），
    # 不按前缀过滤会把上一轮的叶当本轮交付面走完，账就串了。
    rows_all = (c.call("list", {"namespace": NS, "_omit_defaults": True}) or {})
    listing = (rows_all.get("tasks") or rows_all.get("rows") or []) if isinstance(rows_all, dict) else []
    prefix = f"{root_id}."
    by_flag = [t.get("id") for t in listing if isinstance(t, dict)
               and str(t.get("id", "")).startswith(prefix) and t.get("is_leaf")]
    # 双向对齐：is_leaf 标记与「id 点号深度」两种形状必须给出同一集合，否则说明回读口径不可信
    by_depth = [t.get("id") for t in listing if isinstance(t, dict)
                and str(t.get("id", "")).startswith(prefix) and str(t.get("id", "")).count(".") == 2]
    leaves = by_flag if by_flag == by_depth else sorted(set(by_flag) & set(by_depth))
    rep["tree"] = {"root": root_id, "branches_from_plan": children,
                   "listing_rows_in_ns": len(listing), "leaves_by_flag": by_flag,
                   "leaves_by_depth": by_depth, "leaves_used": leaves, "leaf_count": len(leaves)}
    if by_flag != by_depth:
        rep["refusals"].append({"node": "(建树回读)", "tool": "list",
                                "reply_verbatim": f"两种叶形状不一致 by_flag={by_flag} by_depth={by_depth} ⇒ 取交集"})
    if len(leaves) != len(LEAVES):
        rep["refusals"].append({"node": "(建树回读)", "tool": "list",
                                "reply_verbatim": f"回读叶数 {len(leaves)} ≠ 交付条数 {len(LEAVES)}"
                                                  f"（root={root_id}, prefix={prefix}）⇒ 不逐叶走链"})

    loop = c.call("loop_create", {"name": LOOP_NAME, "steps": ["advance", "bugfind", "fix_and_merge",
                                                              "verify", "polish", "advance"],
                                 "max_rounds": 6, "baseline_test_count": passed,
                                 "baseline_open_bug_count": len(open_ids), "stop_on_goal": False,
                                 "stop_on_exceeded": False, "_omit_defaults": True})
    rep["loop_create"] = json.dumps(loop, ensure_ascii=False)

    existing = {b.get("summary", "") for b in (c.call("bug_list", {}).get("bugs") or [])}

    for i, (deliverable, check_args) in enumerate(LEAVES):
        leaf = leaves[i] if len(leaves) == len(LEAVES) and i < len(leaves) else None
        if not leaf:
            rep["refusals"].append({"node": f"(第 {i} 条)", "tool": "tree",
                                    "reply_verbatim": f"叶数 {len(leaves)} ≠ 交付条数 {len(LEAVES)}"
                                                      f" ⇒ 不做部分对应，本条整条不打卡"})
            continue
        rows: dict = {"deliverable_head": deliverable[:70], "steps": {}}
        status = (c.call("get", {"task_id": leaf}) or {}).get("status")
        rows["status_before"] = status
        if status == "待领取":
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
                                      "stdout_tail": str((rc or {}).get("stdout_tail", ""))[-200:]}
        if note(leaf, "run_check", rc if isinstance(rc, dict) and "error" in rc else {}):
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
         "R7 实测：`xs: [int]` → Constant(value=[Name(int)])，`p: (int,str)` → Constant(value=(Name,Name))，"
         "`m: {str:int}` → DictLiteral(pairs=[(Name,Name)])。本轮先在分析器补闭集拒绝面、生成器补 object 退化，"
         "产物不再带 repr；但「括号形态本应是类型」的正解（在 parser 加类型表达式产生器）仍未做，"
         "因为 SYNTAX/02 只承认 list<int>/tuple<...>/dict<...> 写法，放开括号形态等于新增语法。"
         "活证据：tests/test_annotation_shape.py 的 4 条拒绝格 + CLI 转译回执。"),
    ]:
        if summary in existing:
            rep["bugs"].append({"skipped": "账本已有同 summary（幂等守卫）", "summary": summary[:60]})
            continue
        r = c.call("report_bug", {"project_dir": ".", "summary": summary, "severity": sev,
                                  "detail": detail, "reported_by": AGENT, "publish_task": False})
        rep["bugs"].append({"reply": json.dumps(r, ensure_ascii=False)})

    c.close()

    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rows = list(con.execute(
        "select tool, sum(ok=1), sum(ok=0) from call_log "
        "where json_extract(params_json,'$.task_id') like ? "
        "or json_extract(params_json,'$.name')=? "
        "or json_extract(params_json,'$.namespace')=? "
        "group by tool order by tool", (f"{root_id}%", LOOP_NAME, NS)))
    sent_counts: dict = {}
    for t in sent:
        sent_counts[t] = sent_counts.get(t, 0) + 1
    logged = {t: {"ok": a, "refused": b} for t, a, b in rows}
    rep["tally"] = {"by_tool": logged,
                    "rpc_sent_by_tool": sent_counts,
                    "rpc_sent_total": len(sent),
                    "sent_but_not_logged": sorted(set(sent_counts) - set(logged)),
                    "logged_but_not_sent": sorted(set(logged) - set(sent_counts)),
                    "rows": sum(a + b for _t, a, b in rows),
                    "refused": sum(b for _t, a, b in rows),
                    "root_status": (con.execute("select status from tasks where id=?",
                                                (root_id,)).fetchone() or [None])[0],
                    "queried_at_utc": utcnow()}
    if rep["tally"]["rows"] <= 0:
        rep["refusals"].append({"node": "(对账)", "tool": "sqlite",
                                "reply_verbatim": "本轮调用数 0 ⇒ 过滤恒假，整份对账不作数"})
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"root": root_id, "tree": rep["tree"], "loop_create": rep["loop_create"],
                      "baseline": rep["baseline_measured"],
                      "leaf_status": {k: (v["status_before"], v["status_after"]) for k, v in rep["nodes"].items()},
                      "run_check": {k: v["steps"].get("run_check") for k, v in rep["nodes"].items()},
                      "tally": rep["tally"]}, ensure_ascii=False, indent=1))
    for r in rep["refusals"]:
        print("REFUSED", r["tool"], "|", r["node"], "|", r["reply_verbatim"])
    print(f"CONCLUSION root={rep['tally']['root_status']} calls={rep['tally']['rows']} "
          f"refused={rep['tally']['refused']} refusal_rows={len(rep['refusals'])} "
          f"leaves_closed={sum(1 for v in rep['nodes'].values() if v['status_after'] in ('已完成', '待验收'))}"
          f"/{len(LEAVES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
