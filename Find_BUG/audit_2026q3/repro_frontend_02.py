#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 02.

Target: cypyc/parser/macro_expander.py:71-77  (MacroExpander._expand_node,
MacroCall branch)

Claim: the expansion result is never fed back through the expander, so a macro
whose body contains another macro name (object-like macro -> nested macro call)
is only expanded one level deep.  Expected: full (recursive) expansion.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer                          # noqa: E402
from cypyc.parser.parser import Parser                        # noqa: E402
from cypyc.parser.macro_expander import expand_macros          # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator     # noqa: E402
from cypyc.utils.ast_utils import ASTUtils                     # noqa: E402


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def demo_body(ast):
    code = CythonGenerator('m').generate(ast)
    return "\n".join(l for l in code.splitlines()
                     if l.startswith('def demo') or l.startswith('    '))


INNER_DEF = 'macro inner() -> Tokens =\n    f```\n    print("INNER")\n    ```\n\n'

CASES = {
    "A nested @inner!() in outer body": (
        INNER_DEF
        + "macro outer() -> Tokens =\n    f```\n    @inner!()\n    ```\n\n"
        + "def demo():\n    @outer!()\n    return 0\n",
        "print('INNER')"),
    "B nested inner!() in outer body": (
        INNER_DEF
        + "macro outer() -> Tokens =\n    f```\n    inner!()\n    ```\n\n"
        + "def demo():\n    @outer!()\n    return 0\n",
        "print('INNER')"),
    "C 3-level a->b->c": (
        INNER_DEF.replace('print("INNER")', 'print("C")').replace('inner', 'ccc')
        + 'macro b() -> Tokens =\n    f```\n    @ccc!()\n    ```\n\n'
        + 'macro a() -> Tokens =\n    f```\n    @b!()\n    ```\n\n'
        + "def demo():\n    @a!()\n    return 0\n",
        "print('C')"),
    "D parametric outer->inner": (
        "macro inner(x: Tokens) -> Tokens =\n    f```\n    log($x)\n    ```\n\n"
        + "macro outer(x: Tokens) -> Tokens =\n    f```\n    @inner!($x)\n    ```\n\n"
        + "def demo():\n    @outer!(v)\n    return 0\n",
        "log(v)"),
}
CONTROL = (INNER_DEF
           + "def demo():\n    @inner!()\n    return 0\n")


def main():
    print("=" * 78)
    print("T0r61.2.1 / defect 02 - cypyc/parser/macro_expander.py:71-77 "
          "non-recursive macro expansion")
    print("=" * 78)
    print("CONTROL  nested macro alone (must expand, proves the macro itself works):")
    print(demo_body(expand_macros(parse(CONTROL))))
    ctrl_ok = "print('INNER')" in demo_body(expand_macros(parse(CONTROL)))
    print("     -> inner!() alone expands: %s" % ctrl_ok)
    print()

    reproduced = []
    for label, (src, expected) in CASES.items():
        expanded = expand_macros(parse(src))
        code = demo_body(expanded)
        leftovers = [m.name for m in ASTUtils.collect_nodes(expanded, 'MacroCall')]
        # a second full pass is what a recursive implementation would effectively do
        second = demo_body(expand_macros(expanded))
        ok = expected in code and not leftovers
        print("%-34s" % label)
        print("     macro body source  : %s" %
              [l for l in src.splitlines() if '@' in l and 'macro' not in l and 'demo' not in l])
        print("     expected in output : %s" % expected)
        print("     unexpanded left in AST (MacroCall): %s" % (leftovers or '-'))
        print("     1-pass generated   :\n%s" % "\n".join("       " + l for l in code.splitlines()))
        print("     2nd expand pass    :\n%s" %
              "\n".join("       " + l for l in second.splitlines()))
        print("     -> FULL EXPANSION: %s" % ("YES" if ok else "NO"))
        print()
        if not ok:
            reproduced.append(label)

    print("root cause: _expand_node returns the result of _expand_macro_call() "
          "(macro_expander.py:71-77) without re-walking it, so nested macro "
          "calls produced by the backtick re-parse are never visited; the "
          "MacroDef nodes are also dropped from the AST during the same walk, so "
          "a later pass cannot resolve the leftover calls.")
    if reproduced:
        print("VERDICT: REPRODUCED - %d/%d nested-macro cases not fully expanded."
              % (len(reproduced), len(CASES)))
        return 1
    print("VERDICT: NOT-REPRODUCED - nested macros expand recursively.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
