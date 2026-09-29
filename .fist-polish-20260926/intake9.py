#!/usr/bin/env python3
"""File BUG-31: the bridge type map still gives Cypy `float` a 32-bit width after the ruling.

Discovered by asking the BUG-14 ruling's own question ("one declared type, one width?") of the
other package that claims to map Cypy types. Filed, not fixed: closing it changes FFI widths and
would contradict tests/test_bridge_library.py:646-649, which asserts the single-precision
behaviour -- that is a decision for the commander, not a顺手改.
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
 {"sev": "medium", "summary": "[type-width-divergence] cypy_bridge/types.py:43 仍把 Cypy 的 `float` 映射到 "
  "ctypes.c_float（4 字节），而 BUG-14 裁决后 cypyc 的两张表都出 double（8 字节）——同一个声明类型在"
  "两个包里仍然两种宽度，经 cypy_bridge 存取时出现 float32 精度损失",
  "detail": "现象（repro_pass9.py 实跑，repro_pass9.out.json）: `_type_mapper.to_ctypes(\"float\")` 是 "
  "`c_float`、sizeof 4，`to_ctypes(\"double\")` 是 `c_double`、sizeof 8；按 cypy_bridge/union.py:164 自己"
  "文档里的用法 `cdef_union(\"int\", \"float\")` 存 0.1，读回 `0.10000000149011612`，"
  "而 `cdef_union(\"double\")` 存同一个 0.1 读回 `0.1`。"
  "机制: 模块自述口径是「Cypy 类型到 ctypes/C 类型的映射」（types.py:12 类 docstring、:16 字段名 "
  "cypy_to_ctypes），消费面 :80/:86（`float*`）、:114（`f` 单字符表）、:211（`float_ = c_float`），"
  "以及 union.py:50 / generics.py:51 / pointer.py:101 三处 to_ctypes 调用。"
  "定性: [真缺陷，且是 BUG-14 同根因的未覆盖面] —— 指挥官 2026-09-26 裁定「float 与 double 在数值宽度上一致」，"
  "该裁定落在 cypyc/codegen/type_mapper.py 的两张表上；本包那一张没被覆盖，于是「一个声明类型两种宽度」"
  "在跨包路径上依旧成立。"
  "危害面: 凡把 Cypy 侧的 float 值经 bridge 的 union/pointer/generics 存取（或据 :114 的单字符表解析签名），"
  "静默按 32 位截断；与 SYNTAX/01-basic-types.md 更新后的措辞（与 Python float 同宽）直接冲突。"
  "为什么不顺手改: `tests/test_bridge_library.py:646-649` 明确断言 bridge union 的 `float` 成员是单精度、"
  "有精度损失（`assertAlmostEqual(..., places=5)`）——把它改成 c_double 等于弱化/推翻既有用例，"
  "参数卡红线不允许；且这会改变 FFI 宽度口径（跨 ABI），属裁决面。"
  "建议交指挥官二选一：① 裁定 bridge 的 `cypy_to_ctypes[\"float\"]` 也跟 double，并同步改写那条既有测试"
  "（需一轮专门改判据）；② 裁定本包是「按 C/FFI 类型名取宽度的底层工具」，那么请把它自述里的 "
  "「Cypy 类型」措辞改掉（:12/:16/:211 三处），并给 `float_` 起个不冲突的名字。本轮只入账不改。"},
]


def main() -> int:
    if not os.path.exists(os.path.join(HERE, "repro_pass9.out.json")):
        sys.exit("REFUSE: 没有 repro_pass9.out.json，本单没有活证据")
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake9", "version": "1"}})

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
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map9.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} {m.get('severity',''):6s} fired={m['fired']} "
              f"{m['summary'][:52]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
