#!/usr/bin/env python3
"""Seventh-pass reproduction harness, part C — codegen/analyzer candidates.

Each probe states what the frozen docs / the file's own comments promise and what the
generated output actually does, so the ledger entry can cite an observed artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from cypyc.codegen.cython_generator import CythonGenerator      # noqa: E402
from cypyc.parser.lexer import Lexer                            # noqa: E402
from cypyc.parser.parser import Parser                          # noqa: E402


def gen(src):
    code = CythonGenerator().generate(Parser(Lexer(src).tokenize()).parse())
    return code if isinstance(code, str) else getattr(code, "cython_code", "")


R = []


def probe(key, fn):
    try:
        v = fn()
    except Exception as exc:
        v = {"crashed": f"{type(exc).__name__}: {exc}"}
    R.append({"probe": key, **v})
    print(f"[{key}] " + json.dumps(v, ensure_ascii=False)[:420])


def p_match_fields():
    src = ('class Rect:\n'
           '    let w: int\n'
           '    let h: int\n'
           '    def __init__(self) -> None:\n'
           '        return\n'
           '    def area(self) -> int:\n'
           '        return 0\n'
           'def classify(r: Rect) -> int:\n'
           '    match r:\n'
           '        case Rect(a, b):\n'
           '            return a\n'
           '        case _:\n'
           '            return 0\n')
    try:
        code = gen(src)
    except Exception as exc:
        return {"generate_raised": f"{type(exc).__name__}: {exc}", "defect": None}
    lines = [ln.strip() for ln in code.splitlines() if "__init__ ==" in ln or "isinstance(_match" in ln]
    return {"match_arm_lines": lines[:3], "mentions_dunder_init_as_field": "__init__ ==" in code,
            "defect": "__init__ ==" in code}


def p_owned_import():
    src = 'def f() -> None:\n    owned p = malloc(8)\n    return\n'
    code = gen(src)
    head = code.splitlines()[:6]
    directive_first = bool(head) and head[0].lstrip().startswith("#")
    return {"first_six_lines": head,
            "cython_directive_still_on_line_1": directive_first,
            "defect": not directive_first}


def p_comptime_attribute():
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator, evaluate_comptime
    ev = ComptimeEvaluator()
    out = {}
    for expr_src, label in [('let a = "abc".upper()', 'str_upper'),
                            ('let b = [1,2].append(3)', 'list_append'),
                            ('let c = "a,b".split(",")', 'str_split'),
                            ('let d = len("abc")', 'len')]:
        try:
            ast = Parser(Lexer(expr_src).tokenize()).parse()
            node = ast.body[0]
            val = evaluate_comptime(node, {}) if node.kind in ("ComptimeEval",) else None
            # dig the value expression out of a Let statement and evaluate it directly
            value_node = getattr(node, "value", None)
            direct = ev.evaluate(value_node) if value_node is not None else "no-value-attr"
            out[label] = {"evaluate": repr(direct)}
        except Exception as exc:
            out[label] = {"error": f"{type(exc).__name__}: {exc}"}
    tbl = sorted(getattr(ev, "functions", {}).keys())[:6]
    reachable = any(not ("(" in k) for k in out.values().__class__ and [])
    vals = {k: v.get("evaluate") for k, v in out.items()}
    return {"per_expr": out, "function_table_sample": tbl,
            "attribute_calls_all_none": all(vals.get(k) in ("None",) for k in
                                            ("str_upper", "list_append", "str_split")),
            "len_still_works": vals.get("len") not in (None, "None"),
            "defect": None}


def p_comptime_stmt_disappears():
    src = ('def f() -> None:\n'
           '    comptime:\n'
           '        "abc".upper()\n'
           '    return\n')
    code = gen(src)
    body = [ln for ln in code.splitlines() if ln.startswith("    ") or ln.startswith("\t")]
    comment_only = all((not ln.strip()) or ln.strip().startswith("#") for ln in body)
    return {"generated_body_lines": body[:6], "def_body_is_comment_only": comment_only,
            "defect": comment_only}


def p_trait_generic_key():
    from cypyc.analyzer.type_checker import TypeChecker
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    src = ('trait Show:\n'
           '    def show(self) -> str\n'
           'struct Box:\n'
           '    let v: int\n'
           'impl Show for Box:\n'
           '    def show(self) -> str:\n'
           '        return "b"\n'
           'def make() -> Box:\n'
           '    return Box(v = 1)\n')
    ast = Parser(Lexer(src).tokenize()).parse()
    tc = TypeChecker()
    tc.check(ast)
    impls = {k: v for k, v in getattr(tc, "trait_impls", {}).items()}
    weird = {k: v for k, v in impls.items() if any("(" in str(x) for x in v)}
    return {"trait_impls": {k: list(map(str, v)) for k, v in impls.items()},
            "keys_containing_repr_of_node": list(weird), "defect": bool(weird)}


for k, f in [("match_fields", p_match_fields), ("owned_import", p_owned_import),
             ("comptime_attribute", p_comptime_attribute),
             ("comptime_stmt_disappears", p_comptime_stmt_disappears),
             ("trait_generic_key", p_trait_generic_key)]:
    probe(k, f)

bad = [r["probe"] for r in R if r.get("defect")]
print(f"\nprobes={len(R)} defect_confirmed={len(bad)} -> {bad}")
Path(__file__).resolve().with_name("repro_pass7c.out.json").write_text(
    json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote repro_pass7c.out.json")
