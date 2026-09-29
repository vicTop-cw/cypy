"""R7 寻虫：对「注解形态闭集 + 位置模式元数」两个新收口面做边界审视（空输入/极值/非法/资源极限）。

尺子的形状（R6 边界叶的实测教训，逐条落在代码里）：
1. 判定只看「本面」的诊断 —— 闭集面数 `Invalid type annotation`，元数面数 `Positional pattern`；
   同一条源码里的其它诊断（如赋值类型不符）单列为 other，不算本面假阳性。
   （第一版拿总错误数当判据，被 `x: list<int> = 1` 的正确报错误判成产品假阳性。）
2. 两根 canary 必须成对生效：合法格在本面必须零诊断、非法格必须带 `行:列`；不成对即整份结论作废（rc=1）。
3. parse 阶段抛 ValueError 是该产品的设计错误路径（CLI 打印「编译错误: …」并 rc=1，实测见
   logs/r7_empty_annot_cli.txt），归 SYNTAX-CAUGHT；只有越过 analyze 入口逃逸的异常才算 CRASH。
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r7_boundary.json"

sys.path.insert(0, str(ROOT))

from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

ANNOT_NEEDLE = "Invalid type annotation"
ARITY_NEEDLE = "Positional pattern"

CASES = [
    # (分组, 用例名, 本面期望, 源码)
    ("annotation", "empty_after_colon", "n/a", "def f():\n    x: = 1\n    return x\n"),
    ("annotation", "plain_valid", "silent", "def f():\n    x: int = 1\n    return x\n"),
    ("annotation", "generic_valid", "silent", "def f():\n    x: list<int> = [1, 2]\n    return x\n"),
    ("annotation", "tuple_valid", "silent", "def f():\n    x: tuple<int, int> = (1, 2)\n    return x\n"),
    ("annotation", "dict_valid", "silent", "def f():\n    m: dict<str, int> = {}\n    return m\n"),
    ("annotation", "pointer_valid", "silent", "def f():\n    buf: *char = 0\n    return buf\n"),
    ("annotation", "union_valid", "silent", "def f():\n    u: int | str = 1\n    return u\n"),
    ("annotation", "bracket_illegal", "diagnose", "def f():\n    x: [int] = [1, 2]\n    return x\n"),
    ("annotation", "paren_illegal", "diagnose", "def f():\n    x: (int, str) = 1\n    return x\n"),
    ("annotation", "brace_illegal", "diagnose", "def f():\n    m: {str: int} = 1\n    return m\n"),
    ("annotation", "nested_bracket_extreme", "diagnose",
     "def f():\n    x: " + "[" * 12 + "int" + "]" * 12 + " = 1\n    return x\n"),
    ("annotation", "huge_tuple_extreme", "diagnose",
     "def f():\n    x: (" + ",".join(["int"] * 200) + ") = 1\n    return x\n"),
    ("annotation", "non_type_literal_extreme", "diagnose", "def f():\n    x: 5 = 1\n    return x\n"),
    ("annotation", "comptime_inline_not_annotation", "silent", "comptime: [1, 2]\n"),
    ("annotation", "param_and_return_valid", "silent", "def add(a: int, b: int) -> int:\n    return a + b\n"),
    ("arity", "zero_slots", "n/a",
     "struct E:\n    a: int\n\ndef g(e):\n    match e:\n        case E():\n            print(1)\n"),
    ("arity", "exact_slots", "silent",
     "struct E:\n    a: int\n    b: str\n\ndef g(e):\n    match e:\n        case E(x, y):\n            print(x, y)\n"),
    ("arity", "under_slots", "n/a",
     "struct E:\n    a: int\n    b: str\n\ndef g(e):\n    match e:\n        case E(x):\n            print(x)\n"),
    ("arity", "over_slots", "diagnose",
     "struct E:\n    a: int\n\ndef g(e):\n    match e:\n        case E(x, y):\n            print(x, y)\n"),
    ("arity", "extreme_32_slots", "diagnose",
     "struct E:\n    a: int\n\ndef g(e):\n    match e:\n        case E("
     + ", ".join(f"v{i}" for i in range(32)) + "):\n            print(1)\n"),
    ("arity", "undefined_type", "n/a",
     "def g(e):\n    match e:\n        case Unknown(x):\n            print(x)\n"),
    ("arity", "mixed_literal_and_binding", "silent",
     "struct E:\n    a: int\n    b: int\n\ndef g(e):\n    match e:\n        case E(3, y):\n            print(y)\n"),
    ("arity", "nested_pattern", "silent",
     "struct I:\n    v: int\n\ndef g(e):\n    match e:\n        case E(I(z)):\n            print(z)\n"),
]


def run(src: str) -> dict:
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
    except ValueError as exc:
        return {"stage": "parse-raise", "crash": None, "syntax": str(exc), "errors": []}
    except Exception as exc:  # noqa: BLE001
        return {"stage": "parse", "crash": f"{type(exc).__name__}: {exc}", "syntax": "", "errors": []}
    try:
        checker = TypeChecker()
        checker.check(ast)
    except Exception as exc:  # noqa: BLE001
        fr = traceback.extract_stack()[-1]
        return {"stage": "analyze", "crash": f"{type(exc).__name__}: {exc}",
                "syntax": "", "at": f"{fr.name}:{fr.lineno}",
                "errors": list(getattr(checker, "errors", []))}
    return {"stage": "ok", "crash": None, "syntax": "", "errors": list(checker.errors)}


def surface_needle(group: str) -> str:
    return ANNOT_NEEDLE if group == "annotation" else ARITY_NEEDLE


def main() -> int:
    rows = []
    for group, name, expect, src in CASES:
        res = run(src)
        needle = surface_needle(group)
        hits = [e for e in res["errors"] if needle in e]
        others = [e for e in res["errors"] if needle not in e and e.strip()]
        rows.append({"group": group, "case": name, "expect": expect, "stage": res["stage"],
                     "crash": res["crash"], "syntax_caught": res["syntax"],
                     "n_surface": len(hits), "n_other": len(others),
                     "surface_first": hits[0] if hits else "",
                     "other_first": others[0] if others else ""})

    by = {f"{r['group']}/{r['case']}": r for r in rows}

    def classified(r):
        if r["crash"]:
            return "CRASH"
        if r["stage"] == "parse-raise":
            return "SYNTAX-CAUGHT"
        if r["expect"] == "silent":
            return "ok" if r["n_surface"] == 0 else "FALSE-POSITIVE"
        if r["expect"] == "diagnose":
            return "ok" if r["n_surface"] >= 1 else "SILENT"
        return "observed"

    for r in rows:
        r["verdict"] = classified(r)

    canary_clean = by["annotation/plain_valid"]["n_surface"] == 0
    canary_diag = by["annotation/bracket_illegal"]["n_surface"] >= 1 and \
        "at " in by["annotation/bracket_illegal"]["surface_first"]
    canary_arity = by["arity/over_slots"]["n_surface"] >= 1 and \
        "at " in by["arity/over_slots"]["surface_first"]
    judge_ok = canary_clean and canary_diag and canary_arity
    out = {"judge_canary": {"valid_must_be_silent_on_surface": canary_clean,
                            "illegal_must_diagnose_with_position": canary_diag,
                            "over_arity_must_diagnose_with_position": canary_arity,
                            "judge_ok": judge_ok},
           "rows": rows, "n_cases": len(rows),
           "crash_cases": [f"{r['group']}/{r['case']}" for r in rows if r["crash"]],
           "verdicts": {v: sum(1 for r in rows if r["verdict"] == v)
                        for v in ("ok", "SILENT", "FALSE-POSITIVE", "CRASH", "SYNTAX-CAUGHT", "observed")}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"probe_self=OK cases={len(rows)}/{len(CASES)} canary_silent={canary_clean} "
          f"canary_diag={canary_diag} canary_arity={canary_arity} judge_ok={judge_ok}")
    for r in rows:
        print(f"{r['group']}/{r['case']:<32} exp={r['expect']:<9} surf={r['n_surface']:<2} "
              f"other={r['n_other']:<2} {r['verdict']:<14} "
              f"{r['crash'] or r['syntax_caught'] or r['surface_first'][:88] or r['other_first'][:60]}")
    print(f"CONCLUSION judge_ok={judge_ok} crashes={out['verdicts']['CRASH']} "
          f"silent={out['verdicts']['SILENT']} false_positive={out['verdicts']['FALSE-POSITIVE']} "
          f"syntax_caught={out['verdicts']['SYNTAX-CAUGHT']} observed={out['verdicts']['observed']} "
          f"rows_json={OUT.relative_to(ROOT).as_posix()}")
    return 0 if judge_ok else 1


if __name__ == "__main__":
    sys.exit(main())
