#!/usr/bin/env python3
"""按号复现 R3-寻虫 入账的缺陷：`hunt_r3_repro.py <C1|C3|C4|C5|C6|C7|C8|C2>`。

退出码口径（与"缺陷现形"绑定，不打印成功就退 0 的那种）：
- `0` = 缺陷**现形**（打印的 observed 与主张一致）；
- `1` = 缺陷**不现形**（已修好，或本来就没有）；
- `2` = 复现脚本自己跑不动（夹具坏了，不能拿来当"已修"的证据）。

写这个独立件的原因：入账 detail 里的"复跑"若是一长串嵌套引号的 `python -c "..."`，
在 Windows/Git Bash 上多半根本跑不起来（也正因为这样 v1 的探针把 C6 判成了假绿）。
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def _parse(src):
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser
    return Parser(Lexer(src).tokenize()).parse()


def _walk(node):
    seen, stack = set(), [node]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        yield cur
        for val in list(vars(cur).values()) if hasattr(cur, "__dict__") else []:
            if isinstance(val, list):
                stack.extend(v for v in val if hasattr(v, "__dict__"))
            elif hasattr(val, "__dict__") and not isinstance(val, type):
                stack.append(val)


def c1():
    from cypyc.transformer.generic_transformer import GenericTransformer

    tree = _parse("generic struct Box<T>:\n    value: T\n")
    holders = [n for n in _walk(tree) if getattr(n, "generic_params", None)]
    tr = GenericTransformer()
    tr.transform(tree)
    got = {"generic_nodes": len(holders), "collected": len(tr.generic_defs)}
    return got, bool(holders) and len(tr.generic_defs) == 0


def c2():
    from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator

    tree = _parse("comptime def add2(a: int, b: int = 10) -> int:\n    return a + b\n")
    fn = [n for n in _walk(tree) if getattr(n, "kind", "") in ("ComptimeFuncDef", "FuncDef")][0]
    ev = ComptimeEvaluator()
    ev.functions["add2"] = fn
    try:
        got = {"one_arg": repr(ev._call_comptime_function("add2", [1]))[:60], "raised": None}
        present = got["one_arg"] != "11"
    except Exception as exc:  # noqa: BLE001
        got = {"one_arg": None, "raised": f"{type(exc).__name__}: {exc}"[:80]}
        present = True
    return got, present


def c3():
    import ast

    tree = ast.parse((ROOT / "cypyc" / "cli.py").read_text(encoding="utf-8"))
    flags = ("check_only", "emit_ast", "generate_setup", "emit_cython")
    readers = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        used = sorted({a for a in flags if any(isinstance(x, ast.Attribute) and x.attr == a
                                               for x in ast.walk(fn))})
        if used:
            readers[fn.name] = used
    return ({"flag_readers": readers}, readers.get("run_transpile", []) == [])


def c4():
    from cypy_bridge.union import CUnion

    try:
        CUnion(int, float)
        return ({"raised": None}, False)
    except Exception as exc:  # noqa: BLE001
        return ({"raised": f"{type(exc).__name__}: {exc}"[:100]}, "no size" in str(exc))


def c5():
    from cypy_bridge import memory as mem

    got = mem.realloc(0, 0)
    ann = mem.realloc.__annotations__.get("return")
    return ({"returned": repr(got), "annotation": getattr(ann, "__name__", str(ann))}, got is None)


_SNIPPET = (
    "import sys;sys.path.insert(0,%r)\n"
    "from cypyc.project.module_dependency_graph import ModuleDependencyGraph as G\n"
    "g=G()\n"
    "for a,b in (('a','b'),('b','c'),('c','a'),('d','e'),('e','d')): g.add_dependency(a,b)\n"
    "print(g.get_compilation_order())\n"
) % str(ROOT)


def c6():
    orders = {}
    for seed in ("0", "1", "7", "42", "99"):
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", _SNIPPET], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONHASHSEED": seed}, timeout=180)
        orders[seed] = r.stdout.strip() or f"ERR {r.stderr.strip()[-60:]}"
    uniq = {v for v in orders.values()}
    return ({"per_seed_orders": orders, "distinct": len(uniq)}, len(uniq) > 1)


def c7():
    import ast

    src = (ROOT / "cypyc" / "project" / "module_dependency_graph.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "topological_sort")
    passes = [ast.unparse(n) for n in ast.walk(fn)
              if isinstance(n, ast.For) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)]
    return ({"pass_only_loops": passes, "in_degree_loads":
             sum(1 for x in ast.walk(fn) if isinstance(x, ast.Name) and x.id == "in_degree"
                 and isinstance(x.ctx, ast.Load))}, len(passes) >= 1)


def c8():
    from cypyc.analyzer.build_block_checker import BuildBlockChecker

    tree = _parse("def f() -> int:\n    p: *int = 0\n    return 0\n")
    kinds = [getattr(n, "kind", type(n).__name__) for n in _walk(tree)]
    ch = BuildBlockChecker()
    ch.check(tree)
    return ({"node_kinds": [k for k in kinds if k in ("PointerType", "DerefExpr")],
             "errors": list(ch.errors)},
            "PointerType" in kinds and list(ch.errors) == [])


CASES = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6, "C7": c7, "C8": c8}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1].upper() not in CASES:
        print(json.dumps({"usage": "hunt_r3_repro.py <C1..C8>", "available": sorted(CASES)},
                         ensure_ascii=False))
        return 2
    cid = sys.argv[1].upper()
    try:
        observed, present = CASES[cid]()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"id": cid, "probe_error": f"{type(exc).__name__}: {exc}"[:240]},
                         ensure_ascii=False))
        return 2
    print(json.dumps({"id": cid, "observed": observed, "defect_present": bool(present)},
                     ensure_ascii=False, default=str))
    return 0 if present else 1


if __name__ == "__main__":
    sys.exit(main())
