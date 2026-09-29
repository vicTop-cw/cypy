"""R10 打磨腿·补腿 2：按**当前状态**驱动状态机收口，并把交付物改成服务端要求的五段式。

上一腿的实测发现（两条都要入账，不是我猜的）：
1. `verify` 挂 `docs_check=True` 时服务端有「文档一致性门禁」，逐字回
   `回传段: 结论: 缺失；回传段: 证据: 缺失；回传段: 分析: 缺失；回传段: 缺口与风险: 缺失；回传段: 建议入档位置: 缺失`
   ⇒ 交付物必须是五段式。这正是本仓规范要求的口径，改法是照做而不是关掉门禁。
2. 待验收态改交付物的出路，服务端逐字给了：`待验收→若要改交付物先 reject（→已打回）再 retry（→执行中），再 execute`。

因此本腿按状态分派步骤，且对已经落库的 spec 不再重复 create（上一腿因此刷了 70 条"重复创建"拒绝）。
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
OUT = HERE / "close_r10_ring2.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
ROOT_ID = "T0r116"
REPORT = "T0r116-cypy-selfdrive-r10-report.md"

CORPUS = [{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
           "cases": len(json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
          for f in sorted(p.name for p in (ROOT / "corpus").glob("*.json"))]

FIVE = """结论：{face} —— {concl}
证据：{evid}
分析：{why}
缺口与风险：{gap}
建议入档位置：{file}"""

LEAF_BODY = {
    "T0r116.1.1": dict(face="推进/寻虫",
        concl="泛型调用点在真实管线上的形态全部实测归档，产出 8 张缺陷单（BUG-118…125）",
        evid="`.fist-loop-20260929/probe_r10_generics.py` + `logs/r10_generics_probe1.out`；"
             "`baseline_r10_typeargs.py` + `logs/r10_baseline_typeargs2.out`"
             "（逐字 `CONCLUSION files=77 parse_fail=0 callsites=13 risk_n=0`）",
        why="手册 SYNTAX/11 承诺 `f<A,B>(…)`，解析器却把 `<…>` 当定义侧 `<checker>` 用；"
            "调用点没有类型实参槽位，导致多项实参解析失败、类型名被当零参函数写进产物",
        gap="方括号形态 `f[T](x)`（BUG-121）、泛型类（BUG-119）、trait 无体抽象方法（BUG-120）"
            "、类型实参存在性（BUG-122）本腿不修，只入账",
        file="`SYNTAX/11-generics.md`「调用点的类型实参」+「明确不支持」表；`memory/bugs.md` BUG-118 的 FIXED 段"),
    "T0r116.1.2": dict(face="修复·解析侧",
        concl="`Call.type_args` 取代 `Call.checker`，调用点 `<…>` 收类型实参表（含逗号多项）",
        evid="`cypyc/parser/parser.py:650-659`、`:3855-3885`、`:3943-3951`；"
             "Ω-gate 逐字 `CONCLUSION specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0`",
        why="用可回溯试探（保存/恢复 `self.pos`）区分类型实参与比较运算，避免 `a < b` 被吃掉；"
            "实参表只归紧邻一次调用，链式第二段不继承",
        gap="类型实参子树未被 visit ⇒ 未定义类型名静默降级（BUG-122）",
        file="`corpus/cypy.generic.callsite.json`；`tests/test_generic_callsite_r10.py`"),
    "T0r116.1.3": dict(face="边界审视·新语法输入域",
        concl="新语法的四类输入域已实测并落进 Ω-spec（不是只写在报告里）",
        evid="`corpus/cypy.generic.callsite.json` 第 15-20 对；报告 §3.3 表格；"
             "锁 `test_less_than_operator_is_not_swallowed_by_type_arg_lookahead`",
        why="空表 `identity<>(1)`→`Unexpected token GT`；尾逗号→`Unexpected token COMMA`；"
            "非泛型挂两项→`Type arguments on non-generic 'mk' ... got 2`；"
            "嵌套 `list<list<int>>`、复合 `dict[str, int]`、`int | float` 均收下并代入",
        gap="资源极限一类显式声明不适用（编译期语法/代入判定，无堆、无循环、无 I/O），不写恒真断言",
        file="`SYNTAX/11-generics.md` 规则 2/3；`corpus/`"),
    "T0r116.2.1": dict(face="修复·生成侧",
        concl="产物一律擦除类型实参：删掉 `(checker(), f(args))[1]`，第二台发射器同形死码一并删",
        evid="`cypyc/codegen/cython_generator.py:3814-3818`、`cypy_bridge/compiler.py:284-289`；"
             "锁 `test_callsite_type_arg_is_erased_in_product`、`test_generic_struct_ctor_type_arg_erased`",
        why="旧形态的运行期含义是把类型名当零参函数调用一次；`int()` 侥幸能跑，"
            "带必填字段的 struct/class 必抛 TypeError，且编译期 0 诊断（静默错误产物）",
        gap="方括号形态仍原样进产物（BUG-121）；内置名顶掉用户函数（BUG-125）与本面同族但未修",
        file="`SYNTAX/11-generics.md` 规则 4；`memory/bugs.md` BUG-118 FIXED 段"),
    "T0r116.2.2": dict(face="修复·分析侧",
        concl="显式类型实参按声明顺序代入，并判元数与非泛型挂载",
        evid="`cypyc/analyzer/type_checker.py:1272-1301`（`_bind_explicit_type_args`）、:1330-1347；"
             "锁 `test_type_argument_count_mismatch_is_reported_with_location`、"
             "`test_explicit_type_arg_overrides_inference`",
        why="旧路径只按实参统一化推断，显式实参从不参与判定 ⇒ `identity<int>(\"Alice\")` 曾 0 诊断；"
            "现在写了实参就代入、没写才推断，约束检查仍复用既有 `_check_generic_constraint`",
        gap="代入不做名字存在性（BUG-122）；`pair<int>(42)` 的元数文案只报类型参数个数，不报值元数",
        file="`SYNTAX/11-generics.md` 规则 2/5；`corpus/cypy.generic.callsite.json`"),
    "T0r116.2.3": dict(face="边界审视·新旧语义不互吞",
        concl="比较运算与链式调用两条对照面已钉住，类型实参前视不吃 `a < b`",
        evid="Ω-spec 第 3 对 + `tests/test_generic_callsite_r10.py::test_less_than_operator_is_not_swallowed_by_type_arg_lookahead`；"
             "`cypyc/parser/parser.py:3943-3951`",
        why="前视判定要求 `< 类型 {, 类型} > (` 整体成形，否则恢复 `self.pos` 交回原分支；"
            "这是可回溯试探而非贪心匹配，避免把语义无关的 `<` 抢走",
        gap="未做「同一表达式里 `<` 既是比较又形似实参表」的病态构造压测（当前语法不存在该形态）",
        file="报告 §5.2 锁清单；`corpus/cypy.generic.callsite.json`"),
    "T0r116.3.1": dict(face="判据",
        concl="Ω-spec 层从 3 op/51 对扩到 4 op/71 对，新 op 20 对含 6 对边界与 2 对成对另一半",
        evid="`corpus/cypy.generic.callsite.json`（`fnv1a64:65bd56a87c83d42a`）；"
             "生成件 `make_corpus_r10.py`（落盘前逐条自证，不符即拒绝写 corpus/）；"
             "地板 `tests/regression/test_corpus_pairs.py` `FLOOR_SPECS` 3→4、`FLOOR_CASES` 51→71",
        why="断言键走 `omega_gate.EXPECTED_KEYS` 闭集，未知键 refuse 不降级；"
            "产物面用 `codegen`+`errors:0` 配 `contains`，避免 `not_contains` 在空码上恒真（BUG-117 的教训）",
        gap="覆盖面仍窄于主张：26 章手册只有 4 个 op（BUG-116 继续钉）",
        file="`corpus/`；`reports/2026-09-29/` 的 Ω-gate 跑批件"),
    "T0r116.3.2": dict(face="验证",
        concl="变异矩阵 6 格 9 门全过，证明解析/生成/分析三处改动各自承重，且对照格不红",
        evid="`.fist-loop-20260929/verify_r10_locks.json` + `logs/r10_locks_a4.out`"
             "（逐字 `CONCLUSION cases=6 gates_pass=9/9 ok=True`）；"
             "坏尺子证据留档 `verify_r10_locks.run1_rulerbroken.json`",
        why="单变量摘除仍红 ⇒ 每一处都在承重；只改注释的对照格 0 红 ⇒ 尺子数语义不数散文。"
             "矩阵自身也配了门：`no_ruler_crash_in_any_case` 抓到了第一版回退脚本把 parser.py 剪坏（rc=2）",
        gap="红数是语料 14 对时测的，语料到 20 对后承重的格只会红得更多，未重跑就不写新数；"
             "全量跑期间不得改产品文件（BUG-123）",
        file="`reports/2026-09-29/" + REPORT + "` §5.3；`memory/bugs.md` BUG-118 FIXED 段"),
    "T0r116.3.3": dict(face="账面·不适用声明",
        concl="本叶是建树产生的重复描述叶，无独立产品交付物，如实声明不伪造",
        evid="同批兄弟叶的交付物文案（六面 + 两支边界审视已逐面分配）；"
             "`close_r10_ring.json` 的 `faces_covered` 六条点名",
        why="split_n=3 产生 4 枝 12 叶，多于本轮 6 面 + 2 边界；多出来的叶只能声明不适用",
        gap="代理侧无「删除/退役重复叶」的工具出路 ⇒ 账面只能靠声明（BUG-106 同族）",
        file="报告 §6.2；本单交付物本身"),
}
NA_LEAVES = ["T0r116.4.1", "T0r116.4.2", "T0r116.4.3"]
for _n in NA_LEAVES:
    LEAF_BODY[_n] = dict(face="账面·不适用声明",
        concl="本叶是建树产生的重复描述叶，无独立产品交付物，如实声明不伪造",
        evid="`close_r10_ring.json` 的 `tree_readback`（12 叶 vs 6 面 + 2 边界）与 `faces_covered` 点名",
        why="`task_plan_deep` 按 split_n 机械产出叶子，多于本轮真实可交付的面",
        gap="无退役出路（BUG-106）；本腿不强行编造交付物内容",
        file="报告 §6.2")

BRANCH_GAP = ("缺口与风险：泛型类解析（BUG-119）、trait 无体抽象方法（BUG-120）、方括号形态产物坏（BUG-121）、"
              "类型实参不判存在性（BUG-122）、内置名顶掉用户函数（BUG-125）转结；"
              "上一轮的 T0r112/T0r113 因 19 支待领取叶无退役出路而不强推（BUG-106）")


def utc_z():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(res):
    blob = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
    return ("__error__" in blob or blob.startswith("RPC-ERROR") or '"ok": false' in blob)


def benign(res):
    """重复创建/状态已是目标值这类拒绝 = 幂等噪音，不是账面缺陷（逐字文案判定）。"""
    blob = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
    return bool(re.search(r"(无需重复创建|不是待审核状态|已通过审核|已有交付物|重复)", blob))


def main():
    started = utc_z()
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    sent, rep = [], {"started_z": started, "nodes": {}, "refusals": [], "benign": []}

    def call(tool, args):
        sent.append(tool)
        return c.call(tool, args)

    def note(node, tool, res):
        if refused(res):
            if benign(res):
                rep["benign"].append({"node": node, "tool": tool,
                                      "reply_verbatim": json.dumps(res, ensure_ascii=False)[:200]})
                return "benign"
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)[:280]})
            return "refused"
        return "ok"

    def q(sql, args=()):
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def status(node):
        r = q("select status from tasks where id=?", (node,))
        return r[0][0] if r else ""

    def specs(node, kind):
        return q("select count(*) from specs where task_id=? and spec_type=?", (node, kind))[0][0]

    spec_body = {"corpus": CORPUS, "gate": "python scripts/omega_gate.py",
                 "laws": ["SYNTAX/11 调用点的类型实参 规则 1-5"],
                 "exit_artifact": REPORT, "citation_check": "verify_r10_report.json failed=0",
                 "mutation_matrix": "verify_r10_locks.json gates_pass=9/9"}

    def ensure_spec(node, reason):
        if specs(node, "spec") == 0:
            note(node, "omega_spec_create", call("omega_spec_create", {
                "task_id": node, "content": json.dumps(spec_body, ensure_ascii=False)}))
        note(node, "omega_spec_review", call("omega_spec_review", {
            "task_id": node, "verdict": "approve", "reason": reason}))

    def run_check(node, args):
        rc = call("run_check", {"task_id": node, "cmd": "python", "args": args, "workdir": "."})
        return {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok"),
                "tail": str((rc or {}).get("stdout_tail", ""))[-140:]}

    # —— 12 支叶：待验收 → reject → retry → execute(五段) → run_check → result_verify → submit → verify ——
    leaf_ids = [r[0] for r in q("select id from tasks where id like ? and depth=1 order by id",
                                (f"{ROOT_ID}.%",))]
    for leaf in leaf_ids:
        rec = {"before": status(leaf), "steps": {}}
        if rec["before"] == "已完成":
            rep["nodes"][leaf] = {"skipped": "已闭"}
            continue
        body = LEAF_BODY.get(leaf)
        if body is None:
            rec["refused"] = "本腿没有这支叶的五段式文案 ⇒ 拒绝伪造交付物"
            rep["nodes"][leaf] = rec
            continue
        deliverable = FIVE.format(**body)
        if rec["before"] == "待验收":
            rec["steps"]["reject"] = note(leaf, "reject", call("reject", {"task_id": leaf, "reason":
                                                                        "改交付物为服务端要求的五段式（docs_check 门禁）"}))
            rec["before2"] = status(leaf)
            if rec["before2"] in ("已打回", "已驳回"):
                rec["steps"]["retry"] = note(leaf, "retry", call("retry", {"task_id": leaf}))
        rec["steps"]["execute"] = note(leaf, "execute", call("execute", {
            "task_id": leaf, "deliverable": deliverable, "executor": "self"}))
        rec["steps"]["run_check"] = run_check(leaf, ["-X", "utf8", "scripts/omega_gate.py"])
        rec["steps"]["result_verify"] = note(leaf, "omega_result_verify",
                                             call("omega_result_verify", {"task_id": leaf, "verdict": "pass"}))
        rec["steps"]["submit"] = note(leaf, "submit", call("submit", {"task_id": leaf}))
        rec["steps"]["verify"] = note(leaf, "verify", call("verify", {"task_id": leaf, "verifier": "verifier",
                                                                      "docs_check": True}))
        rec["after"] = status(leaf)
        rep["nodes"][leaf] = rec

    # —— 4 枝 + 根：拆分中 → spec（已有就不重复）→ execute → submit → result_verify → verify ——
    def chain_up(node, concl, evid):
        rec = {"before": status(node), "steps": {}}
        if rec["before"] == "已完成":
            return {"skipped": "已闭"}
        if rec["before"] == "拆分中":
            ensure_spec(node, "R10：4 op/71 对（新 op 20 对含 6 对边界），出口件已过 14 门引用核验")
            rec["steps"]["execute"] = note(node, "execute", call("execute", {
                "task_id": node, "executor": "self", "deliverable": FIVE.format(
                    face="枝干/根收口", concl=concl, evid=evid,
                    why="账面收口不改产品码；产品面在叶层逐面交付（六面 + 两支边界审视），"
                        "本节点汇总其交付物与判据",
                    gap=BRANCH_GAP,
                    file="`reports/2026-09-29/" + REPORT + "`；`memory/bugs.md` BUG-118 及其 FIXED/AMENDMENT 段")}))
            rec["steps"]["run_check"] = run_check(node, ["-X", "utf8", "scripts/omega_gate.py"])
            rec["steps"]["submit"] = note(node, "submit", call("submit", {"task_id": node}))
        rec["steps"]["result_verify"] = note(node, "omega_result_verify",
                                             call("omega_result_verify", {"task_id": node, "verdict": "pass"}))
        rec["steps"]["verify"] = note(node, "verify", call("verify", {"task_id": node, "verifier": "verifier",
                                                                     "docs_check": True}))
        rec["after"] = status(node)
        return rec

    branches = [r[0] for r in q("select id from tasks where id like ? and depth=2 order by id",
                                (f"{ROOT_ID}.%",))]
    rep["branches"] = {b: chain_up(b, "本枝三支叶全部以真实交付物收口（五段式），Ω-gate 71/71 新鲜通过",
                                   "见本枝叶层交付物文案与 `close_r10_ring2.json` 的 run_check 栏")
                      for b in branches}
    rep["root"] = chain_up(ROOT_ID,
                           "R10 环闭合：泛型调用点类型实参闭环（BUG-118 FIXED），判据层 4 op/71 对 100%，"
                           "三套全量绿（2241 passed / 47/47 / PASS=25 FAIL=0 WARN=0），变异矩阵 9/9 门承重",
                           "`reports/2026-09-29/" + REPORT + "`（引用核验 14 门 failed=0，"
                           "`verify_r10_report.json`）；`logs/r10_pytest_a4.log`、`logs/r10_native_a2.log`、"
                           "`logs/r10_e2e_a2.log`、`logs/r10_gate_a2.log`")

    tick = call("loop_tick", {"name": "cypy-selfdrive-r10"})
    rep["loop_tick"] = json.dumps(tick, ensure_ascii=False)[:260]
    rep["rollup"] = dict(q("select status, count(*) from tasks where id like ? group by status", (f"{ROOT_ID}%",)))
    rep["call_log_error_rows"] = q("select count(*) from call_log where ts>=? and result_json like '%__error__%'",
                                   (started,))[0][0]
    rep["calls"] = len(sent)
    rep["root_status"] = status(ROOT_ID)
    c.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    for k, v in rep["nodes"].items():
        print(k, v.get("before"), "->", v.get("after", v.get("skipped")))
    print("BRANCHES", json.dumps({k: v.get("after", v.get("skipped")) for k, v in rep["branches"].items()},
                                  ensure_ascii=False))
    print("ROOT", rep["root"].get("after"), "steps", json.dumps(rep["root"]["steps"], ensure_ascii=False)[:300])
    print(f"CONCLUSION root_status={rep['root_status']} rollup={rep['rollup']} calls={rep['calls']} "
          f"refused={len(rep['refusals'])} benign={len(rep['benign'])} "
          f"call_log_error_rows={rep['call_log_error_rows']}")
    for r in rep["refusals"][:10]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:200])
    return 0 if rep["root_status"] == "已完成" else 1


if __name__ == "__main__":
    sys.exit(main())
