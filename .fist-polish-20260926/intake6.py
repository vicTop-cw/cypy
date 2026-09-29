#!/usr/bin/env python3
"""Sixth-pass intake: Cypy `float` has two widths inside one artifact.

Found while registering the missing golden `examples/subtype_units.out` (the commander
authorized "补 golden" to close gate ①). Two of the nine printed lines in that one artifact
cannot both be right under SYNTAX/01-basic-types.md "单精度浮点数": the value that passed an
explicit subtype cast is single-precision, the value computed inside a function whose declared
signature is `float` is double-precision.

This is a semantics-level finding, so per this round's red lines it is booked and NOT fixed:
every remedy (emitting typed signatures, or storing `let x: float` as a C float) changes
existing float semantics. The golden is kept because the pairing judge requires a paired
baseline, and it is annotated here as pinning current behavior, not a ruling.

Evidence, all re-runnable without a C toolchain (transpile only):
  python -c "import sys; sys.path.insert(0,'tests'); from test_nominal_subtypes import _transpile;
             print(_transpile(open('examples/subtype_units.cypy',encoding='utf-8').read())
             .cython_code)"
    -> "def area(side):"                     (declared "def area(side: Meter) -> float")
    -> "print(<float>m / <float>1000.0)"     (explicit cast really is a C float)
  cypyc/codegen/type_mapper.py:8   "float": "float"    (cypy_to_cython  -> C float,  32 bit)
  cypyc/codegen/type_mapper.py:23  "float": "double"   (cypy_to_c       -> 64 bit)
  SYNTAX/01-basic-types.md:19      "# 单精度浮点数"
  examples/subtype_units.out  line 2 = 0.0016
                                 line 9 = 0.0024999999441206455
  python -c "import struct; f=lambda x: struct.unpack('f',struct.pack('f',x))[0];
             print(repr(f(0.0025)), repr(f(f(0.04)*f(0.04))))"
    -> 0.0024999999441206455 0.0015999999595806003
       line 9 equals the single-precision value exactly; line 2 equals the double value,
       i.e. the same declared type produced both widths in one run.
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
        "summary": "[float-width] cypyc/codegen/type_mapper.py:8 与 :23 对同一声明类型 float "
                   "给出两种宽度（cypy_to_cython 出 C float=32 位、cypy_to_c 出 double=64 位），"
                   "且 def 签名与 let 绑定的注解在 Cython 产物里被整段丢弃 —— "
                   "examples/subtype_units.cypy 一次运行内第 2 行与第 9 行互相矛盾",
        "severity": "medium",
        "detail": (
            "现象: 注册 golden 时读到 examples/subtype_units.out 的 9 行输出里，"
            "第 9 行是 0.0024999999441206455，而 struct 单精度校准给 "
            "float32(0.0025) = 0.0024999999441206455（逐字相等），说明 "
            "print((m as float) / 1000.0 as Kilometer) 走的是 C 单精度；"
            "同一文件第 2 行是 0.0016，而 float32(0.04)*float32(0.04)  widen 后是 "
            "0.0015999999595806003，0.0016 只有双精度才能得到 —— 即 print(area(c)) 全程是 "
            "double。同一个声明类型 float 在同一份产物里两种宽度。\n"
            "机制（transpile 即可复现，不需要 C 工具链）: 源文件写 def area(side: Meter) -> float，"
            "产物出成 \"def area(side):\"（参数与返回注解全部丢弃，函数体是 Python 语义的 "
            "double 运算）；而显式转换出成 \"print(<float>m / <float>1000.0)\"，是真 C 单精度。"
            "两张映射表本身就分叉：cypyc/codegen/type_mapper.py:8 的 cypy_to_cython 把 float "
            "映成 \"float\"（Cython 里即 C float，32 位），同文件 :23 的 cypy_to_c 把 float "
            "映成 \"double\"。\n"
            "定性: [真缺陷]，语义级。SYNTAX/01-basic-types.md:19 明确把 float 写成"
            "「单精度浮点数」，并与 double 并列成两种类型（:23 e: double），所以「注解被丢弃、"
            "运算退回 Python double」这一路不符合冻结文档；反过来，把 float 全改成 32 位又会改变"
            "现有全部数值输出的最后一位表示。两种修法都要动既有语义，本轮不顺手落地。\n"
            "危害面: 数值可移植性与精度承诺。当前形态下，同一个 x: float 是否单精度取决于它是否"
            "恰好经过一次显式 as 转换——用户无法从类型推出宽度，也无法从 golden 之外预测末位数字。"
            "examples/ 里已注册的其它 .out 若含 float 运算，同样在 pin 这种混合宽度。\n"
            "建议（择一，均需指挥官裁定后落到 R2/语义轮）: "
            "① 裁定 float 为单精度，则让被标注的 def 签名与 let 绑定生成 cdef double/float 静态"
            "存储（注解不许丢），并统一 type_mapper 两表；"
            "② 裁定 float 跟随 Python（双精度），则 cypy_to_cython:8 改成 \"double\"、"
            "显式转换不再出 <float>，SYNTAX/01 §浮点数类型 的「单精度」措辞随之下修；"
            "③ 最小止血：先让两张映射表一致（都 double），把单精度只留给显式写的 double/float32 "
            "标注，再另开语义轮处理静态签名缺失。\n"
            "本轮处置: 入账不修（红线：语义级问题只入账不顺手改；PROJECT-SPEC/、SYNTAX/ 为界）。"
            "examples/subtype_units.out 按指挥官「补 golden」授权注册，pin 的是**现状输出**，"
            "不是对第 2 行的正确性裁定；一旦上面 ①②③ 任一裁定落地，该 golden 第 2 行与所有含 "
            "float 运算的基准必须重注册（重注册前先留 before 快照）。"
        ),
    },
]


def bug_id_of(row):
    return row.get("bug_id") or row.get("id")


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake6", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {(r.get("summary") or "").strip(): bug_id_of(r) for r in before}
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
        if not isinstance(out, dict) or not (out.get("bug_id") or out.get("id")):
            failures.append({"summary": summary, "reply": out})
            continue
        mapping.append({"bug_id": bug_id_of(out), "task_id": out.get("task_id"),
                        "summary": summary, "fired": True})

    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip(): bug_id_of(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map6.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} fired={m['fired']} "
              f"{m['summary'][:60]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
