#!/usr/bin/env python3
"""Third sweep intake: project-mode type checking drops ScopeAnalyzer diagnostics.

Same contract as intake.py / intake2.py — server cwd is the Cypy root so
`project_dir="."` writes `memory/bugs.md`; reconcile by `summary` first so a re-run never
double-books; read the id with the `bug_id`-or-`id` fallback.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

FINDINGS = [
    {
        "summary": "[silent-fail] cypyc/project/project_compiler.py:539 "
                   "项目模式 type_check_module 只上送 TypeChecker 诊断，ScopeAnalyzer 已报出的"
                   "重名/类型级冲突（SYNTAX/33 C-3.1）被静默丢弃——同一份源码在单文件模式 "
                   "cypy_hook/hook.py:250 会报错，两个入口给出相反裁决",
        "severity": "medium",
        "detail": (
            "现象: type_check_module() 调用 ScopeAnalyzer().analyze(ast) 后从不读 "
            "scope_analyzer.errors（:539-540），只把 type_checker.errors 收进返回值；"
            "而单文件管线 cypy_hook/hook.py:250-257 两处都收。因此作用域通道独有的诊断"
            "（重名定义、类型级名字冲突、非模块级定义）在项目模式整个消失，"
            "cypyc/cli.py:737-744 的 --check-only 会打印 'type check passed' 并以 0 退出。\n"
            "复现（确定性，零依赖）: 三份源文件各建一次性项目，"
            "python .fist-polish-20260926/probe_scope_drop.py 打印三行 DROPPED —— "
            "ScopeAnalyzer 有诊断、TypeChecker 为空、type_check_module 返回 ok=True errors=[]："
            "dup_func（def f 写两次）、dup_subtype_class（subtype Money <: int 撞 class Money）、"
            "dup_type_constraint（type Thing = int 撞 constraint Thing）。"
            "对照：uses_undefined 一条不丢，因为 TypeChecker 自己会报同一句 Undefined name —— "
            "丢的正是作用域独有的那一类。\n"
            "锁死回归: tests/test_polish_20260926.py::"
            "test_bug11_project_type_check_reports_scope_errors + ::"
            "test_bug11_type_level_name_collision_is_reported；改前 "
            ".fist-polish-20260926/pytest_third_sweep_red.log → 2 failed, 20 deselected"
            "（两条都红在 ok=True errors=[]，且用例里的前提自证断言先确认 ScopeAnalyzer "
            "确实报出了这个名字）。\n"
            "影响: 项目/多模块构建带着重复定义继续编译，codegen 按后写覆盖前写产出 .pyd，"
            "用户拿到的模块身份与源码不一致；与本轮 BUG-3（同一文件的重解析异常被吞）同族。\n"
            "建议: 在 type_check_module 里 errors.extend(scope_analyzer.errors)，"
            "并对两条通道逐字重复的诊断按序去重（dict.fromkeys），不改任何判定规则、不新增诊断文案。"
        ),
    },
]


def bug_id_of(row):
    return row.get("bug_id") or row.get("id")


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake3", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {}
    for r in before:
        known[(r.get("summary") or "").strip()] = bug_id_of(r)
    mapping, failures = [], []
    for spec in FINDINGS:
        summary = spec["summary"]
        if summary in known:
            mapping.append({"bug_id": known[summary], "task_id": None,
                            "summary": summary, "fired": False, "note": "already in ledger"})
            continue
        out = c.call("report_bug", {
            "project_dir": ".", "summary": summary, "detail": spec["detail"],
            "severity": spec["severity"], "publish_task": True,
            "reported_by": "cypy-polisher", "now": utc_now()})
        if not isinstance(out, dict) or not out.get("bug_id"):
            failures.append({"summary": summary, "reply": out})
            continue
        mapping.append({"bug_id": out["bug_id"], "task_id": out.get("task_id"),
                        "summary": summary, "fired": True})

    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip(): bug_id_of(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    for m in mapping:
        if not m["fired"]:
            continue
        m["task_id"] = m["task_id"] or None
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map3.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} fired={m['fired']} "
              f"{m['summary'][:60]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
