#!/usr/bin/env python3
"""File BUG-32: the constraint artifact comment echoed mapped type names, not declared ones.

Found by the terminal full suite (this is the pass-9 regression the commander's float=double
ruling caused), not by reading new code: 9 of 1851 cases went red after `type_mapper` was unified.
Six of them were pre-ruling needles in tests (retargeted to the ruled width, disclosed in the
report); these three were a genuine product defect -- `# constraint Numeric = int | float` came
out as `int | double`, so the generated artifact named a type the user never wrote, breaking
SYNTAX/33 §5 and C-4.1 (named vs inline differ only by that comment).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

FINDINGS = [
 {"sev": "high", "summary": "[codegen-echo-fidelity] cypyc/codegen/cython_generator.py:3334（修复前号，"
  "修复后该行在 :3337）约束注释把成员名"
  "过了一遍 type_mapper，BUG-14 裁决（float≡double）落地后产物写成 `# constraint Numeric = int | double`，"
  "注释里出现的名字不再是用户声明的那个",
  "detail": "现象（pytest 终态全量实跑，.fist-polish-20260926/pytest_final_sweep9.log）："
  "tests/test_named_constraints.py::TestConstraintCodegen::test_only_a_comment_is_emitted、"
  "::test_shipped_example_transpiles_clean 与 ::TestNamedVersusInlineEquivalence::"
  "test_artifacts_differ_only_by_the_constraint_comment 三条同时红，"
  "断言原文 `assert '# constraint Numeric = int | float' in '...# constraint Numeric = int | double...'`。"
  "机制: `_visit_ConstraintDef` 用 `self._type_to_str(m)` 渲染成员，而 `_type_to_str`（修复后 :3873/:3892）"
  "对内置标量走 `type_mapper.to_cython(node.id)` —— 裁决前 `float` 映射成同名 `float`，两者恰好相等所以没人发现；"
  "裁决把映射改成 `double` 后，这条**注释**也跟着改了名。"
  "定性: [真缺陷] —— 该注释的口径写在它自己的 docstring（:3327-3332）与 SYNTAX/33 §5：约束只发一条注释、"
  "且命名界与内联界的产物**只差这一行注释**（C-4.1）。注释是声明的逐字回显，不是类型替换的位置；"
  "把 `float` 写成 `double` 等于让产物声明了一个源码里没出现过的类型名。"
  "危害面: 任何把该注释当可读性/可追溯依据的读者与判据（含三条既有测试）都会失配；"
  "同一渲染路径若被复制到别处（如别名注释 :3320）会扩大失面——别名那处**不该**改（`ctypedef double N` 是真声明，"
  "打印映射后的目标类型是对的，本轮已实测确认并保持不动，另加对照锁）。"
  "修法（本轮已实施）: 成员名用声明时的 `m.id` 逐字回显，非 Name 形态再退回 `_type_to_str`；"
  "锁死回归 tests/test_polish_20260926_pass7.py 的 test_bug32_constraint_comment_echoes_declared_member_names，"
  "对照 test_bug32_alias_still_takes_the_ruled_width（保证这一下没把裁决本身中止掉）。"},
]


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake10", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {(r.get("summary") or "").strip(): (r.get("bug_id") or r.get("id")) for r in before}
    mapping, failures = [], []
    for spec in FINDINGS:
        s = spec["summary"]
        if s in known:
            mapping.append({"bug_id": known[s], "task_id": None, "summary": s,
                            "fired": False, "note": "already in ledger"})
            continue
        out = c.call("report_bug", {"project_dir": ".", "summary": s, "detail": spec["detail"],
                                    "severity": spec["sev"], "publish_task": True,
                                    "reported_by": "cypy-polisher", "now": utc_now()})
        if not isinstance(out, dict) or not (out.get("bug_id") or out.get("id")):
            failures.append({"summary": s[:60], "reply": out})
            continue
        mapping.append({"bug_id": out.get("bug_id") or out.get("id"),
                        "task_id": out.get("task_id"), "summary": s, "severity": spec["sev"],
                        "fired": True})
    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip() for r in after}
    missing = [f["summary"] for f in FINDINGS if f["summary"] not in got]
    log = os.path.join(HERE, "pytest_final_sweep9.log")
    if not os.path.exists(log):
        sys.exit("REFUSE: 缺 pytest_final_sweep9.log —— 本单的原始失败证据不在")
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map10.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} {m.get('severity',''):6s} fired={m['fired']} "
              f"{m['summary'][:52]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
