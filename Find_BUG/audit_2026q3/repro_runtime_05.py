"""OMEGA repro T0r61.3.1 / defect 5
cypyc/analyzer/comptime_evaluator.py:136-140 (eager BinOp) with the operators at :481-484

Claim under test: evaluate() unconditionally evaluates BOTH operands of a BinOp before
dispatching, and _evaluate_bin_op then runs Python's `left and right` / `left or right`.
Since Python's `and`/`or` short-circuit only on the already-computed values, the right-hand
side is always computed at compile time: `comptime: False and (1/0)` raises ZeroDivisionError
instead of yielding False.

Also measured: what the public entry point evaluate_comptime() (:631-649) and the code
generator (cypyc/codegen/cython_generator.py:2353-2379) do with that failure.

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator, evaluate_comptime  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


def comptime_expr(source):
    module = Parser(Lexer(source).tokenize()).parse()
    for stmt in module.body:
        if hasattr(stmt, "expr"):
            return stmt
    raise AssertionError("no comptime statement found in %r -> %s"
                         % (source, [s.kind for s in module.body]))


def direct(source):
    """Evaluate through ComptimeEvaluator.evaluate (the internal entry)."""
    node = comptime_expr(source)
    try:
        return "ok", ComptimeEvaluator().evaluate(node.expr)
    except Exception as e:  # noqa: BLE001
        return "raised", "%s: %s" % (type(e).__name__, e)


def public(source):
    """Evaluate through evaluate_comptime (what codegen uses)."""
    node = comptime_expr(source)
    try:
        return "ok", evaluate_comptime(node.expr)
    except Exception as e:  # noqa: BLE001
        return "raised", "%s: %s" % (type(e).__name__, e)


print("=== 1. `comptime: False and (1/0)` must be False ===")
k, v = direct("comptime: False and (1/0)")
print("  ComptimeEvaluator.evaluate  -> %s %r" % (k, v))
check(k == "ok" and v is False, "evaluate('False and (1/0)') is False",
      "got %s %r -- the RHS was evaluated even though the LHS is falsy (:136-140)" % (k, v))
k2, v2 = public("comptime: False and (1/0)")
print("  evaluate_comptime (public)  -> %s %r" % (k2, v2))
check(v2 is False, "evaluate_comptime('False and (1/0)') is False (not None)",
      "got %r -- the ZeroDivisionError is swallowed at :646-649 and reported as "
      "'not a constant', so the constant folds to nothing" % (v2,))

print("=== 2. `comptime: True or (1/0)` must be True ===")
k, v = direct("comptime: True or (1/0)")
print("  evaluate -> %s %r" % (k, v))
check(k == "ok" and v is True, "evaluate('True or (1/0)') is True", "got %s %r" % (k, v))
k2, v2 = public("comptime: True or (1/0)")
check(v2 is True, "evaluate_comptime('True or (1/0)') is True", "got %r" % (v2,))

print("=== 3. short-circuit must not evaluate an undefined RHS ===")
k, v = direct("comptime: False and undefined_symbol")
print("  evaluate('False and undefined_symbol') -> %s %r" % (k, v))
check(k == "ok" and v is False, "RHS of a short-circuited `and` is never touched",
      "got %s %r -- RHS evaluation is not deferred" % (k, v))
k, v = direct("comptime: True or undefined_symbol")
print("  evaluate('True or undefined_symbol')   -> %s %r" % (k, v))
check(k == "ok" and v is True, "RHS of a short-circuited `or` is never touched",
      "got %s %r" % (k, v))

print("=== 4. end-to-end: what does codegen emit? ===")
try:
    from cypyc.codegen.cython_generator import CythonGenerator
    module = Parser(Lexer("comptime: False and (1/0)\n").tokenize()).parse()
    code = CythonGenerator().generate(module)
    line = [l for l in code.splitlines() if l.strip() and ("False" in l or "comptime" in l)]
    print("  generated: %s" % (line or ["(nothing)"]))
    folded = any(l.strip() == "False" for l in code.splitlines())
    check(folded, "codegen constant-folds the expression to `False`",
          "codegen emitted %s -- the failed fold degraded into a comment "
          "(cython_generator.py:2378), silently dropping the statement" % (line,))
except ImportError as e:
    notes.append("section 4 skipped: %s" % e)

print("=== 5. regression guards: values that must NOT change ===")
for src, want in [("comptime: True and 5", 5),
                  ("comptime: False or 7", 7),
                  ("comptime: 1 + 2", 3),
                  ("comptime: not False", True),
                  ("comptime: 1 == 1 and 2 == 2", True),
                  ("comptime: False and True", False),
                  ("comptime: True or False", True)]:
    k, v = direct(src)
    ok = (k == "ok" and v == want and type(v) == type(want))
    print("  %-36s -> %s %r (want %r) %s" % (src, k, v, want, "" if ok else "<== WRONG"))
    check(ok, "invariant %s" % src, "got %s %r want %r" % (k, v, want))

print("=== 6. guard: a genuinely failing RHS must still fail ===")
k, v = direct("comptime: True and (1/0)")
print("  evaluate('True and (1/0)') -> %s %r" % (k, v))
check(k == "raised" and "ZeroDivisionError" in str(v),
      "non-short-circuited `and` still raises", "got %s %r" % (k, v))
k, v = direct("comptime: False or (1/0)")
print("  evaluate('False or (1/0)') -> %s %r" % (k, v))
check(k == "raised" and "ZeroDivisionError" in str(v),
      "non-short-circuited `or` still raises", "got %s %r" % (k, v))

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (and/or are lazily evaluated)")
sys.exit(0)
