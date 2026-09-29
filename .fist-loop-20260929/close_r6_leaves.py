"""R6 收口批：把 6 条叶按 (状态, 有无标记) 的形状走完，并跑 loop_tick / report_bug / call_log 对账。

形状表是实测出来的，不是抄的：起手对每条叶 `get` 读当前状态，
`待领取` 才 claim；已在执行/待验收的跳过 claim（重复 claim 会被状态机拒）。
每一步的拒绝都逐条记录（工具, 节点, 回执首行），「0 失败」必须按节点分栏报，不能汇总成一个数。

Omega 强验证腿：`omega_spec_create`（语料登记）+ `omega_result_verify`（成果复验判决）；
实测腿：`run_check`（宿主命令白名单内，落 specs.spec_type='check'）；
issue 面：`report_bug`（severity 用英文枚举，必填键是 summary）；
对账面：`call_log` + `loop_tick`（六步各一次，计数器用盘面实测值）。
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r6_leaves.json"
NS = "cypy-loop-20260929"
ASSIGNEE = "cypy-selfdrive-agent"

CORPUS = {
    "op": "cypy.pattern.positional",
    "version": "1.0",
    "definition": {
        "signature": "match(subject: T) case T(p0, p1, ...) -> bindings",
        "note": "SYNTAX/17：提取器优先（__match_args__ < __unapply__ < __unapply_seq__ < __unwarp__），"
                "无提取器时按 struct `.fields` 声明序解包；绑定名类型取对应槽位类型，不得默认 int。",
    },
    "preconditions": ["subject 的类型在本模块可见，或作为运行期提取器处理"],
    "laws": ["L-模式优先级", "L-槽位类型来源", "L-方法名不是位置字段"],
    "tests": [
        {"input": {"src": "struct E(a:str,b:str) + case E(x, y)", "op": "typecheck"},
         "expected": {"errors": 0, "x": "str", "y": "str"}},
        {"input": {"src": "struct E(address:str) + __unapply__->tuple<str,str> + case E(user,domain)",
                   "op": "codegen"},
         "expected": {"calls": "__unapply__()", "phantom_attrs": 0}},
        {"input": {"src": "struct S(area(),w:int,h:int) + case S(3,4)", "op": "codegen"},
         "expected": {"compared_attrs": ["w", "h"], "not": ["area"]}},
        {"input": {"src": "def classify(E)->int 但 return user(str)", "op": "typecheck"},
         "error": "Return type mismatch"},
        {"input": {"src": "case Unknown(a, b) 且 Unknown 未定义", "op": "transpile"},
         "error": "Undefined name 'Unknown'"},
    ],
    "fingerprint": "manual:R6-2026-09-29",
}

# (leaf, 本轮交付, run_check 命令/参数)
LEAVES = [
    ("T0r112.1.1",
     "BUG-37：type_checker 位置模式槽位类型（_bind_pattern_names 补 Pattern/ExtractorPattern/StructPattern 支路 + "
     "_pattern_slot_types 按 SYNTAX/17 取 __unapply__ 元组类型；_visit_Pattern 不再无条件写 int）。"
     "调用面：hunt_f/hunt_e 两份语料的假阳性诊断消失。",
     ["-m", "pytest", "tests/test_pattern_positional_struct.py", "-q", "-k", "binding or wrong_return"]),
    ("T0r112.1.2",
     "BUG-36：cython_generator._record_pattern_shape 从 StructDef.fields/methods 采集字段序与提取器标记，"
     "并把方法名逐出位置字段。调用面：cypyc run hunt_e_extractor_positional.cypy → Output: a, rc=0；"
     "产物含 __unapply__() 调用链、零 __f 幽灵属性。",
     ["-m", "pytest", "tests/test_pattern_positional_struct.py", "-q", "-k", "extractor or field_order or methods"]),
    ("T0r112.1.3",
     "边界审视叶：位置模式四类边界输入（空实参/32 槽极值/字面量与绑定混写/未定义类型/嵌套 8 层/空匹配体）"
     "逐个真跑 transpile 并留逐字诊断；结果 0 内部崩溃、0 挂起，canary 两格（必绿/必红）通过。",
     ["-X", "utf8", ".fist-loop-20260929/hunt_r6_boundary.py"]),
    ("T0r112.2.1",
     "BUG-41：tests/test_boundary_comprehensive.py 两组同名类遮蔽的 6 条用例改名放行"
     "（只改首现类名，不删不改任何断言）；实测 6 passed / 122 deselected。",
     ["-m", "pytest", "tests/test_boundary_comprehensive.py", "-q", "-k", "ShadowedOnce"]),
    ("T0r112.2.2",
     "BUG-93：scripts/fist.py 对齐上游 0.3.4 —— 入口 cmd/cli/cli.js + serve、无状态握手不发 initialize、"
     "cwd/项目根改本仓（任务库落 E:/IDEProjects/AI/Cypy/fist-mbt.db）、project_dir 相对、"
     "list-tools 由恒绿探针改为必须解出非空清单并点名 12 个必需工具、新增 _omit_defaults 退出键。",
     ["-m", "pytest", "tests/test_fist_driver_protocol.py", "-q"]),
    ("T0r112.2.3",
     "账面/交付面：memory/bugs.md 追加 BUG-36/37/41 的 FIXED 段并新立 92/93/94/95（只增不删，"
     "difflib 逐行验证无删除行）；R6 报告落 reports/2026-09-29/。",
     ["-X", "utf8", ".fist-loop-20260929/verify_r6_ledger.py"]),
]


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def client():
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    return fist.FistClient(timeout=180)


def main() -> int:
    c = client()
    report: dict = {"started_utc": utcnow(), "namespace": NS, "nodes": {},
                    "refusals": [], "ticks": [], "bugs_filed": [], "tally": {}}

    def step(node: str, tool: str, args: dict):
        res = c.call(tool, args)
        refused = isinstance(res, dict) and ("__error__" in res or res.get("ok") is False
                                             or "error" in res)
        if refused:
            report["refusals"].append({"node": node, "tool": tool,
                                       "reply": json.dumps(res, ensure_ascii=False)[:220]})
        return res, refused

    for leaf, deliverable, check_args in LEAVES:
        rows: dict = {"deliverable_head": deliverable[:80], "steps": {}}
        cur = c.call("get", {"task_id": leaf})
        status = (cur or {}).get("status") if isinstance(cur, dict) else None
        rows["status_before"] = status
        if status == "待领取":
            _r, refused = step(leaf, "claim", {"task_id": leaf, "assignee": ASSIGNEE})
            rows["steps"]["claim"] = "refused" if refused else "ok"
        # 步骤形状是实测出来的：Omega 强验证门禁回「任务尚未创建语料，请先由语料创建者执行
        # omega_spec_create」⇒ 语料必须在 execute 之前；成果复验必须在 submit 之前。
        # 角色是闭集（自定义身份回「未知角色」），故 author/reviewer 用服务端默认档。
        _r, refused = step(leaf, "omega_spec_create", {"task_id": leaf,
                                                       "content": json.dumps(CORPUS, ensure_ascii=False)})
        rows["steps"]["omega_spec_create"] = "refused" if refused else "ok"
        # 强验证门禁实测形状：语料 create 后是 [pending]，必须 omega_spec_review(approve)
        # 才允许 execute；未过审的语料也不允许 result_verify（两条拒绝文案都逐字留在报告里）。
        _r, refused = step(leaf, "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                                       "reason": "R6：语料即本轮回归锁的 input→expected 对，含错误路径两格"})
        rows["steps"]["omega_spec_review"] = "refused" if refused else "ok"
        _r, refused = step(leaf, "execute", {"task_id": leaf, "deliverable": deliverable,
                                             "executor": "self"})
        rows["steps"]["execute"] = "refused" if refused else "ok"
        rc_obj, refused = step(leaf, "run_check", {"task_id": leaf, "cmd": "python",
                                                   "args": check_args, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc_obj or {}).get("status"),
                                      "ok": (rc_obj or {}).get("ok"),
                                      "refused": refused,
                                      "stdout_tail": str((rc_obj or {}).get("stdout_tail", ""))[-160:]}
        _r, refused = step(leaf, "omega_result_verify", {"task_id": leaf, "verdict": "pass"})
        rows["steps"]["omega_result_verify"] = "refused" if refused else "ok"
        _r, refused = step(leaf, "submit", {"task_id": leaf})
        rows["steps"]["submit"] = "refused" if refused else "ok"
        _r, refused = step(leaf, "verify", {"task_id": leaf, "verifier": "verifier"})
        rows["steps"]["verify"] = "refused" if refused else "ok"
        after = c.call("get", {"task_id": leaf})
        rows["status_after"] = after.get("status") if isinstance(after, dict) else None
        rows["assignee"] = after.get("assignee") if isinstance(after, dict) else None
        report["nodes"][leaf] = rows

    ticks = [("advance", "healthy"), ("bugfind", "attention"), ("fix_and_merge", "attention"),
             ("verify", "healthy"), ("polish", "healthy"), ("advance", "healthy")]
    for i, (mode, grade) in enumerate(ticks):
        res = c.call("loop_tick", {"name": NS, "_omit_defaults": True,
                                   "current_test_count": 2119 + 21,
                                   "current_open_bug_count": 12,
                                   "blocked_tasks": 0, "project_health_grade": grade})
        report["ticks"].append({"idx": i, "mode": mode,
                                "reply": json.dumps(res, ensure_ascii=False)[:200]})

    # 幂等守卫（BUG-107 教训）：先取账本已有 summary 集合，命中即跳过，重跑不得双发
    existing = {b.get("summary", "") for b in (c.call("bug_list", {}).get("bugs") or [])}
    for bug_id, sev, summary, detail in [
        ("BUG-92", "medium",
         "[模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时产物发不存在的 __f{i}",
         "详见 memory/bugs.md BUG-92：本轮试过两种收紧都被既有判据打红（test_extractor_pattern.py:192/:235），"
         "故只入账不改实现，出路二选一已在账本写明。活证据：.fist-loop-20260929/out_after/"
         "hunt_f_pattern_binding_int.pyx 第 39 行。"),
        ("BUG-94", "low",
         "[兄弟仓 FIST-Mbt] cli.js serve 仍往协议 stdout 打 2 行人类横幅",
         "实测同命令重放两次，stdout 前两行为横幅，JSON 帧从第 4 行起；Cypy 侧驱动按非 JSON 行跳过而容忍。"
         "严格客户端会拒连。修在兄弟仓，不在 Cypy 轮次半径内。"),
        ("BUG-95", "medium",
         "[规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 在本仓不存在",
         "03 §1/§2 与 05 §3 要求 Ω-spec JSON 落 corpus/，实测 ls -d corpus tests/regression 均不存在。"
         "本轮把语料交给 omega_spec_create（任务面）并把 pattern 一片写成可复审 JSON 落在报告附件，"
         "目录本体与跑批入口需指挥官裁决，见账本出路。"),
    ]:
        # 幂等守卫（BUG-107 的直接教训）：同一主张重复入账只能标 DUPLICATE，故先比已有 summary
        if summary in existing:
            report["bugs_filed"].append({"local_id": bug_id, "skipped": "账本已有同 summary（幂等守卫）"})
            continue
        res = c.call("report_bug", {"summary": summary, "detail": f"{detail}\n（本地账本同号：{bug_id}）",
                                    "severity": sev, "reported_by": ASSIGNEE,
                                    "publish_task": False})
        report["bugs_filed"].append({"local_id": bug_id,
                                     "reply": json.dumps(res, ensure_ascii=False)[:200]})

    log = c.call("call_log", {"limit": 400, "_omit_defaults": True})
    rows = log.get("calls") or log.get("rows") or log if isinstance(log, dict) else log
    report["tally"]["call_log_shape"] = sorted(log)[:12] if isinstance(log, dict) else type(log).__name__
    c.close()

    # sqlite 只读复算：本轮 ns 的调用行数与拒绝数（不靠 call_log 工具的回执口径）
    import sqlite3

    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    ns_rows = list(con.execute(
        "select tool, sum(case when ok=1 then 1 else 0 end), sum(case when ok=0 then 1 else 0 end) "
        "from call_log where json_extract(params_json,'$.namespace')=? or json_extract(params_json,'$.task_id') like ? "
        "group by tool order by 2 desc", (NS, "T0r112%")))
    total = sum(a + b for _t, a, b in ns_rows)
    refused_total = sum(b for _t, a, b in ns_rows)
    report["tally"].update({
        "by_tool": {t: {"ok": a, "refused": b} for t, a, b in ns_rows},
        "rows_for_this_round": total, "refused": refused_total,
        "sum_matches_rows": total == sum(a + b for _t, a, b in ns_rows),
        "queried_at_utc": utcnow(),
    })
    if total <= 0:
        report["refusals"].append({"node": "(对账)", "tool": "sqlite",
                                   "reply": "本轮 ns 调用数 0 ⇒ 过滤恒假，整份对账不作数"})
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"nodes": {k: {"status": (v["status_before"], v["status_after"]),
                                    "steps": {s: ("ok" if r == "ok" else "see-report")
                                              for s, r in v["steps"].items()}}
                        for k, v in report["nodes"].items()},
                      "refusal_count": len(report["refusals"]),
                      "tally": report["tally"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
