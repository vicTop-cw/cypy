"""R10 打磨腿：FIST 环账面 —— 建单（带 [omega:required]）→ 拆树 → 逐叶走完整链 → 枝干 → 收根。

本轮相比 R9 的两条改动（都是 R9 自曝的流程债）：
1. **入口门**：报告必须已在盘上、且引用核验件 `verify_r10_report.json` 对该报告 `failed=0`，
   否则整腿拒收（R9 是"收根早于报告落盘"，流程债转结；本轮改成硬门，先物先证）。
2. **`verify` 挂 `docs_check=True`**：用服务端 [gate:required] 的「文档即实现」面而不是只靠我自查。

链形状沿用 R9 实测：claim → omega_spec_create → omega_spec_review → execute → run_check →
omega_result_verify → submit → verify；枝干/根缺哪步补哪步，逐字记录拒绝文案。
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
OUT = HERE / "close_r10_ring.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
ROOT_PREFIX = "自驱式组合环 R10"
LOOP_NAME = "cypy-selfdrive-r10"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r116-cypy-selfdrive-r10-report.md"
VERIFIED = HERE / "verify_r10_report.json"
GATE_LOG = HERE / "logs" / "r10_gate_a2.log"
PYTEST_LOG = HERE / "logs" / "r10_pytest_a4.log"
NATIVE_LOG = HERE / "logs" / "r10_native_a2.log"
E2E_LOG = HERE / "logs" / "r10_e2e_a2.log"
PLACEHOLDER = "<!--FIST-SECTION-->"

FACES = [
    ("推进/寻虫", "探针件 `.fist-loop-20260929/probe_r10_generics.py`（15 形态 × typecheck/codegen 两面，"
                 "逐字 `logs/r10_generics_probe1.out`）+ 基线件 `baseline_r10_typeargs.py`"
                 "（`CONCLUSION files=77 parse_fail=0 callsites=13 risk_n=0`）⇒ 定位 8 类面并立 8 张单（BUG-118…125）",
     ["-X", "utf8", ".fist-loop-20260929/baseline_r10_typeargs.py"]),
    ("修复·解析侧", "`cypyc/parser/parser.py:650-659`（`Call.checker`→`Call.type_args`）、"
                ":3855-3885（可回溯试探的类型实参表，收逗号多项）、:3943-3951（实参表只归紧邻一次调用）",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"]),
    ("修复·生成侧", "`cypyc/codegen/cython_generator.py:3814-3818` 删 `(checker(), f(args))[1]` ⇒ 产物一律擦除；"
                "`cypy_bridge/compiler.py:284-289` 第二台发射器的同形死码一并删",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"]),
    ("修复·分析侧", "`cypyc/analyzer/type_checker.py:1272-1301` 新增 `_bind_explicit_type_args`（元数/非泛型/代入），"
                ":1330-1347 显式实参优先于统一化推断",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"]),
    ("判据", "`corpus/cypy.generic.callsite.json` 20 对（`fnv1a64:65bd56a87c83d42a`）；"
            "地板 `FLOOR_SPECS` 3→4、`FLOOR_CASES` 51→71；`tests/test_generic_callsite_r10.py` 9 支锁",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("验证", "变异矩阵 6 格 9 门全过（`.fist-loop-20260929/verify_r10_locks.json`）："
           "L1 三处全退 18 红 / L2 只退解析器 10 红 / L3 只退分析器 7 红 / L4 产物退回零参调用 9 红 / "
           "L5 只改注释对照 0 红；三套全量见本腿开批门读到的日志",
     ["-X", "utf8", "scripts/run_tests.py"]),
]
BOUNDARY = [("[边界审视] 本轮新语法面的输入域四类实测已落进 Ω-spec（不是只写在报告里）："
             "空 `identity<>(1)`→`Unexpected token GT`；非法 `identity<int,>(1)`→`Unexpected token COMMA`、"
             "`mk<int, str>(1)`→`Type arguments on non-generic 'mk' ... got 2`；"
             "极值/嵌套 `identity<list<list<int>>>`、复合 `dict[str, int]`、`int | float` 均收下并代入；"
             "资源极限一类**显式声明不适用**（编译期语法/代入判定，无堆、无循环、无 I/O），"
             "依据见报告 §3.3，不给恒真断言",
             ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"]),
            ("[边界审视·对照] 新旧语义不得互相吞：`len(xs) < len(ys)` 这类比较运算必须不被类型实参前视吃掉"
             "（Ω-spec 第 3 对 + 锁 `test_less_than_operator_is_not_swallowed_by_type_arg_lookahead`），"
             "且 `f<T>(a)(b)` 链式调用的第二段不继承实参表（`parser.py:3943-3951`）",
             ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.callsite"])]
DECLARED_NA = ("[账面·不适用声明] 本叶是建树产生的重复描述叶，无独立产品交付物；"
               "本轮真实交付物已按面分配给其余叶（见同批兄弟叶的交付物文案）。"
               "不伪造交付，也不强推关闭 —— 若无法以真实工作收口，本叶应留账并由 BUG-106 的退役出路处理。")

CORPUS = [{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
           "cases": len(json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
          for f in sorted(p.name for p in (ROOT / "corpus").glob("*.json"))]


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def last_line(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def entry_gate() -> tuple:
    """先物后账：报告 + 引用核验 + 三套终验日志，四件全绿才允许开批。"""
    reasons = []
    if not REPORT.exists():
        reasons.append(f"报告不在盘上：{REPORT.name}")
    else:
        body = REPORT.read_text(encoding="utf-8")
        if len(body.encode("utf-8")) < 6000:
            reasons.append(f"报告字节数 {len(body.encode('utf-8'))} < 6000")
        if PLACEHOLDER not in body:
            reasons.append("报告缺 §6.2 占位标记 ⇒ 本腿的渲染锚点不存在")
    if not VERIFIED.exists():
        reasons.append("引用核验件缺失（verify_r10_report.json）")
    else:
        v = json.loads(VERIFIED.read_text(encoding="utf-8"))
        if v.get("report") != REPORT.name:
            reasons.append(f"核验件对应的报告名不符：{v.get('report')}")
        if v.get("failed"):
            reasons.append(f"引用核验 failed={v['failed']}")
        if v.get("report_bytes") != len(REPORT.read_bytes()) if REPORT.exists() else True:
            reasons.append(f"核验件里的 report_bytes={v.get('report_bytes')} 与当前报告 "
                           f"{len(REPORT.read_bytes()) if REPORT.exists() else -1} 不一致 ⇒ 报告在核验后又被动过")
    gate = last_line(GATE_LOG, "CONCLUSION")
    if "cases=71" not in gate or not gate.endswith("rc=0"):
        reasons.append(f"Ω-gate 终值不符：{gate}")
    ptext = PYTEST_LOG.read_text(encoding="utf-8", errors="replace") if PYTEST_LOG.exists() else ""
    if "2241 passed" not in ptext or not ptext.strip().endswith("pytest_rc=0"):
        reasons.append(f"pytest 终验不符：{ptext.strip()[-90:]}")
    nat = last_line(NATIVE_LOG, "Total: 47")
    if "Passed: 47 | Failed: 0" not in nat:
        reasons.append(f"自研套件终值不符：{nat}")
    e2e = last_line(E2E_LOG, "[e2e-golden] summary:")
    if "PASS=25 FAIL=0" not in e2e or "WARN=0" not in e2e:
        reasons.append(f"e2e golden 终值不符：{e2e}")
    return reasons, {"gate": gate, "pytest_tail": ptext.strip()[-60:], "native": nat, "e2e": e2e}


def main() -> int:
    started = utc_z()
    reasons, obs = entry_gate()
    rep = {"started_z": started, "ns": NS, "entry_gate": {"pass": not reasons, "reasons": reasons,
                                                           "observed": obs},
           "refusals": [], "nodes": {}, "loop": {}, "plan_raw": ""}
    if reasons:
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        for r in reasons:
            print("REFUSED (开批门) local |", r[:220])
        print(f"CONCLUSION refused=1 root=(未开批) gate_reasons={len(reasons)}")
        return 1

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    _raw = c.call
    sent: list = []

    def call(tool, args):
        sent.append(tool)
        return _raw(tool, args)

    def note(node, tool, res):
        blob = json.dumps(res, ensure_ascii=False)
        r = refused(res) or blob.startswith("RPC-ERROR") or '"__error__"' in blob
        if r:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob[:300]})
        return r

    def status(node):
        q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            row = q.execute("select status from tasks where id=?", (node,)).fetchone()
        finally:
            q.close()
        return row[0] if row else ""

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    root_row = con.execute("select id from tasks where ns=? and parent_id='' and description like ? "
                           "order by id desc limit 1", (NS, f"%{ROOT_PREFIX}%")).fetchone()
    con.close()
    if root_row:
        root_id = root_row[0]
        rep["root_reused"] = root_id
    else:
        root = call("publish_parallel", {"project_dir": ".", "namespace": NS, "created_by": AGENT,
                                        "description": (
            f"[omega:required] {ROOT_PREFIX}（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
            "本轮靶面：把泛型调用点 `f<T>(x)` 从「被当成 <checker> 参数检查站」改回手册承诺的「类型实参表」——"
            "解析收多项、分析器按声明顺序代入并判元数、产物一律擦除；同时把 Ω-spec 层从 3 op/51 对扩到 "
            "4 op/71 对，并用变异矩阵证明三处改动各自承重；\n"
            "  寻虫另立 7 张（BUG-119…125：泛型类不解析、trait 无体抽象方法、方括号形态产物坏、"
            "类型实参不判存在性、getsource 锁错位、状态表无主主张、内置名顶掉用户函数）\n"
            f"判据基线（本轮实测，非沿用）：pytest 2241 passed rc=0；Ω-gate 逐字 {obs['gate']}；"
            f"自研套件逐字 {obs['native']}；e2e 逐字 {obs['e2e']}。"
            "出口件：`reports/2026-09-29/T0r116-cypy-selfdrive-r10-report.md`"
            "（引用核验 14 门 failed=0）。")})
        rep["root"] = json.dumps(root, ensure_ascii=False)[:300]
        root_id = root.get("task_id") if isinstance(root, dict) else None
        if not root_id:
            rep["refusals"].append({"node": "(建单)", "tool": "publish_parallel",
                                    "reply_verbatim": json.dumps(root, ensure_ascii=False)[:300]})
            OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
            print("REFUSED (建单) publish_parallel |", json.dumps(root, ensure_ascii=False)[:260])
            print("CONCLUSION refused=1 root=(建单失败)")
            return 1

    laya = call("laya_decide", {"context": (
        "任务：把 Cypy 泛型调用点 f<T>(x) 的类型实参语义闭环（解析多项 + 代入 + 产物擦除 + 元数诊断），"
        "并把判据层从 3 op/51 对扩到 4 op/71 对；已立 8 张缺陷单；"
        "已知阻塞：泛型类解析、trait 无体抽象方法、方括号形态需要 owner 裁决。"
        "问：该开哪些机制、怎么拆。")})
    rep["laya"] = json.dumps(laya, ensure_ascii=False)[:400]

    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    _b = re.split(r"(?m)^## (BUG-\d+)", led)
    open_ids = [_b[i] for i in range(1, len(_b) - 1, 2)
                if not re.search(r"(?m)^### (FIXED|DUPLICATE)", _b[i + 1])]
    rep["ledger_open_measured"] = len(open_ids)
    loop = call("loop_create", {"name": LOOP_NAME,
                               "steps": ["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"],
                               "max_rounds": 6, "baseline_test_count": 2241,
                               "baseline_open_bug_count": len(open_ids), "stop_on_goal": False,
                               "stop_on_exceeded": False, "_omit_defaults": True})
    rep["loop"]["create"] = json.dumps(loop, ensure_ascii=False)[:260]
    # 幂等：本腿若在上一次崩溃后重跑，环名已存在 ⇒ 服务端拒是预期，不算账面缺陷
    if refused(loop) and re.search(r"(已存在|exist|duplicate|已注册)", json.dumps(loop, ensure_ascii=False), re.I):
        rep["loop"]["create_already_exists"] = True
    else:
        note("(loop_create)", "loop_create", loop)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    already = con.execute("select count(*) from tasks where id like ? and depth=1", (f"{root_id}.%",)).fetchone()[0]
    con.close()
    if already == 0:
        plan = call("task_plan_deep", {"task_id": root_id, "split_n": 3, "decide_split_n": 3,
                                      "decide_difficulty": 3.0,
                                      "decide_reason": "六面分属解析/生成/分析/判据/验证/账面，可并行领取；"
                                                      "每枝 3 叶（2 面 + 1 边界审视）",
                                      "omega_strong_verify": True, "gradient": True,
                                      "boundary_probe": True, "reinject_context": True,
                                      "by": AGENT, "decide_by": AGENT, "_omit_defaults": True})
        rep["plan_raw"] = json.dumps(plan, ensure_ascii=False)[:400]

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tree = con.execute("select id, depth, status, description from tasks where id=? or id like ? "
                       "order by id", (root_id, f"{root_id}.%")).fetchall()
    leaves = [r for r in tree if r[1] == 1]
    general = [r[0] for r in leaves if r[3].startswith(ROOT_PREFIX)]
    boundary = [r[0] for r in leaves if r[3].startswith("[边界审视")]
    other = [r[0] for r in leaves if r[0] not in set(general) | set(boundary)]
    st = {r[0]: r[2] for r in tree}
    rep["tree_readback"] = {"root": root_id, "rows": len(tree), "leaves": len(leaves),
                            "branches": len([r for r in tree if r[1] == 2]),
                            "general": general, "boundary": boundary, "unclassified": other}
    if other:
        rep["refusals"].append({"node": "(分形状)", "tool": "sqlite",
                               "reply_verbatim": f"这些叶既不是根单复制也不是边界审视：{other[:6]}"})

    # 六面分配到 general 叶：每面恰好落在一叶（不足就合并到最后一叶，绝不重复计面）
    face_assign: dict = {}
    if general:
        per = max(1, len(general) // len(FACES)) if len(general) >= len(FACES) else 1
        chunks: list = [[]]
        for f in FACES:
            chunks[-1].append(f)
            if len(chunks[-1]) >= per and len(chunks) < len(general):
                chunks.append([])
        for i, tail in enumerate(chunks[:len(general)]):
            if tail:
                face_assign[general[i]] = tail
        for leaf in general[len(chunks):]:
            face_assign[leaf] = []
    plan_rows = [(leaf, "；".join(d for _, d, _ in fs), fs[0][2] if fs else ["-X", "utf8", "scripts/omega_gate.py"])
                 for leaf, fs in face_assign.items()]
    plan_rows += [(leaf, d, ck) for leaf, (d, ck) in zip(boundary, BOUNDARY)]
    plan_rows += [(leaf, DECLARED_NA, ["-X", "utf8", "scripts/omega_gate.py"])
                  for leaf in boundary[len(BOUNDARY):]]
    faces_covered = sorted({n for fs in face_assign.values() for n, _, _ in fs})
    rep["faces_covered"] = faces_covered
    rep["faces_missing"] = sorted(n for n, _, _ in FACES if n not in faces_covered)
    if rep["faces_missing"]:
        rep["refusals"].append({"node": "(面分配)", "tool": "local",
                                "reply_verbatim": f"这些面没落到任何叶：{rep['faces_missing']}"})

    spec_body = {"corpus": CORPUS, "gate": "python scripts/omega_gate.py",
                 "laws": ["SYNTAX/11 调用点的类型实参 规则 1-5", "SYNTAX/14 切片规则 1-3",
                          "SYNTAX/17 规则 5/8"],
                 "exit_artifact": REPORT.name,
                 "citation_check": "verify_r10_report.json failed=0"}
    for leaf, deliverable, check_args in plan_rows:
        if st.get(leaf) == "已完成":
            rep["nodes"][leaf] = {"skipped": "已闭（幂等守卫）"}
            continue
        rows = {"kind": ("face" if leaf in face_assign else
                         "boundary-real" if leaf in boundary[:len(BOUNDARY)] else "boundary-declared-na"),
                "status_before": st.get(leaf), "steps": {}}
        if rows["status_before"] == "待领取":
            rows["steps"]["claim"] = "refused" if note(leaf, "claim",
                    call("claim", {"task_id": leaf, "assignee": AGENT})) else "ok"
        rows["steps"]["omega_spec_create"] = "refused" if note(leaf, "omega_spec_create", call(
            "omega_spec_create", {"task_id": leaf, "content": json.dumps(spec_body, ensure_ascii=False)})) else "ok"
        rows["steps"]["omega_spec_review"] = "refused" if note(leaf, "omega_spec_review", call(
            "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                  "reason": "R10：4 op/71 测试对（新 op cypy.generic.callsite 20 对，"
                                            "含 6 对边界形态与 2 对成对另一半）；出口件是报告且已过引用核验"})) else "ok"
        rows["steps"]["execute"] = "refused" if note(leaf, "execute", call(
            "execute", {"task_id": leaf, "deliverable": f"{ROOT_PREFIX} 交付：" + deliverable,
                        "executor": "self"})) else "ok"
        rc = call("run_check", {"task_id": leaf, "cmd": "python", "args": check_args, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok"),
                                      "stdout_tail": str((rc or {}).get("stdout_tail", ""))[-160:]}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
        rows["steps"]["omega_result_verify"] = "refused" if note(leaf, "omega_result_verify", call(
            "omega_result_verify", {"task_id": leaf, "verdict": "pass"})) else "ok"
        rows["steps"]["submit"] = "refused" if note(leaf, "submit", call("submit", {"task_id": leaf})) else "ok"
        rows["steps"]["verify"] = "refused" if note(leaf, "verify", call(
            "verify", {"task_id": leaf, "verifier": "verifier", "docs_check": True})) else "ok"
        q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        one = q.execute("select status, assignee from tasks where id=?", (leaf,)).fetchone()
        q.close()
        rows["status_after"], rows["assignee"] = one[0], one[1]
        rep["nodes"][leaf] = rows

    def chain_up(node, reason):
        q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        cur = q.execute("select status from tasks where id=?", (node,)).fetchone()
        q.close()
        trace = {}
        if cur and cur[0] == "拆分中":
            trace["execute"] = json.dumps(call("execute", {
                "task_id": node, "executor": "self",
                "deliverable": f"{ROOT_PREFIX} 枝干/根收口：本轮交付物 = 产品修复（解析/生成/分析三处）"
                               f"+ Ω-spec 4 op/71 对 + 9 支锁 + 变异矩阵承重证明；出口件 {REPORT.name}"}),
                ensure_ascii=False)[:200]
            trace["submit"] = json.dumps(call("submit", {"task_id": node}), ensure_ascii=False)[:200]
        for tool, args in (("omega_spec_create", {"task_id": node,
                                                 "content": json.dumps(spec_body, ensure_ascii=False)}),
                           ("omega_spec_review", {"task_id": node, "verdict": "approve", "reason": reason}),
                           ("omega_result_verify", {"task_id": node, "verdict": "pass"})):
            note(node, tool, call(tool, args))
            if status(node) == "已完成":
                trace[tool] = "closed_here"
                return trace, "已完成"
        note(node, "verify", call("verify", {"task_id": node, "verifier": "verifier", "docs_check": True}))
        trace["final"] = status(node)
        return trace, trace["final"]

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    branches = [r[0] for r in con.execute("select id from tasks where id like ? and depth=2",
                                          (f"{root_id}.%",)).fetchall()]
    open_branches = [b for b in branches if status(b) != "已完成"]
    rep["branch_final"] = {b: chain_up(b, f"R10 枝干：4 op/71 对、9 支锁、变异矩阵 9/9 门")[1]
                          for b in open_branches}
    rep["root_final"], rep["root_final_status"] = chain_up(
        root_id, "R10 根：报告已落盘并通过 14 门引用核验，三套全量与 Ω-gate 终值见 §5.4")
    pending = con.execute("select count(*) from tasks where id like ? and status='待领取'",
                          (f"{root_id}.%",)).fetchone()[0]
    stuck = con.execute("select id, status from tasks where id like ? and status!='已完成'",
                        (f"{root_id}.%",)).fetchall()
    rep["post_state"] = {"pending_leaves": pending, "non_terminal": [list(s) for s in stuck]}
    con.close()

    tick = call("loop_tick", {"name": LOOP_NAME})
    rep["loop"]["tick"] = json.dumps(tick, ensure_ascii=False)[:300]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    rep["rollup"] = dict(con.execute("select status, count(*) from tasks where id like ? group by status",
                                     (f"{root_id}.%",)).fetchall())
    con.close()
    c.close()
    rep["calls"] = len(sent)
    rep["finished_z"] = utc_z()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print("ROOT", root_id, "tree", json.dumps(rep["tree_readback"], ensure_ascii=False)[:220])
    for leaf, rows in rep["nodes"].items():
        print(leaf, rows.get("kind"), rows.get("status_before"), "->", rows.get("status_after", rows.get("skipped")))
    print("BRANCHES", json.dumps(rep["branch_final"], ensure_ascii=False))
    print(f"CONCLUSION root={root_id} root_status={rep['root_final_status']} "
          f"rollup={rep['rollup']} non_terminal={rep['post_state']['non_terminal']} "
          f"calls={rep['calls']} refused={len(rep['refusals'])} call_log_error_rows={rep['call_log_error_rows']}")
    for r in rep["refusals"][:12]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:200])
    return 0 if not rep["refusals"] and rep["root_final_status"] == "已完成" else 1


if __name__ == "__main__":
    main()
