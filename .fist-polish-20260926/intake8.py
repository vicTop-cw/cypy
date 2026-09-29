#!/usr/bin/env python3
"""File BUG-30, confirmed while re-registering the goldens under the float=double ruling.

Same ledger contract as passes 1-6 (server cwd = Cypy root, project_dir=".", publish_task=True).
Dedup is by exact summary against `bug_list` before filing, and the reply's bug_id/task_id are the
only accepted evidence of a new entry -- the map file is written from the replies, not by hand.
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
 {"sev": "high", "summary": "[codegen-coercion] cypyc/codegen/cython_generator.py:1170 声明式局部变量走 "
  "`name: <ctype> = value` 注解形式且不补隐式转换，于是 `let e: float = <int 表达式>` 的 e 在编译产物里"
  "仍是 Python int（type() 回 <class 'int'>），float 路径在 BUG-14 裁决落地后由 42.0 退化成了 42",
  "detail": "现象（repro_pass8.py 实跑，产物是真 .pyd：tmp_float/out8/repro_pass8.cp313-win_amd64.pyd）："
  "同一份源里 `let a: int = 42` + `let e: float = a` + `let d: double = a` → 运行期打印 "
  "`float-from-int: value=42 type=<class 'int'>` 与 `double-from-int: value=42 type=<class 'int'>`，"
  "而 `let g: float = 1.5` 正常是 `<class 'float'>`。生成物对应三行 `e: double = a` / `d: double = a` / "
  "`g: double = 1.5`（见 repro_pass8.out.json 的 generated_declarations）。"
  "机制: 声明带初值时 :1161-1170 只在 `needs_implicit_conversion`（:1142，查 `_pending_conversions`）命中时"
  "插入转换，未命中就直接写注解形式；本例没有登记到转换记录，也没有走 :1168 的 `cdef <ctype> name = value`"
  "分支（那条才会强制 C 层窄化/浮点化）。"
  "定性与危害面: [真缺陷] —— examples/basic_types.cypy:17 自己的注释就写着「隐式转换 (int -> float)」，"
  "而产物里该变量的身份仍是 int：声明类型对可赋值性不起作用，`type(e)`、整数除法/取模一类的行为都会随"
  "「源表达式恰好是 int」而变。"
  "与指挥官 2026-09-26 的 BUG-14 裁决直接相关：裁决把 cypy_to_cython[\"float\"] 从 \"float\" 改成 \"double\"，"
  "于是 float 路径继承了这个既有缺口 —— 落地前该例打印 42.0，落地后打印 42（"
  "本单是裁决落地暴露出的回归面，不是裁决本身的取舍；已按裁决重注册的 examples/basic_types.out 第 5 行"
  "把这个现状固化了下来）。"
  "建议（不在本单内擅自做）: 声明带初值且类型是浮点/整型 C 类型时改走 :1168 的 cdef 形式，"
  "或在 _pending_conversions 未命中时按 SYNTAX 的隐式转换表补一条 <double>/<int> 强转；"
  "两种改法都会改动生成码形态，需重注册端到端基准并全量复跑，故交指挥官定口径后再动。"
  "留待下一轮的子问题: 为什么注解形式对 `float` 曾能浮点化而对 `double` 不能（Cython annotation_typing 的"
  "类型识别面），本轮未证。"},
]


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake8", "version": "1"}})

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
    if not os.path.exists(os.path.join(HERE, "repro_pass8.out.json")):
        sys.exit("REFUSE: 没有 repro_pass8.out.json，本单没有活证据")
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map8.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} {m.get('severity',''):6s} fired={m['fired']} "
              f"{m['summary'][:52]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
