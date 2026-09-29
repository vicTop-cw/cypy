"""OMEGA repro T0r61.3.1 / defect 4
cypyc/analyzer/pointer_checker.py:21-25 (per-checker state) + :103-108 (_check_owned_vars_cleanup)

Claim under test: owned_vars / moved_vars / defer_cleaned_vars are plain sets created in
__init__ and NEVER reset in _visit_FuncDef (:86-101), so ownership state recorded while
checking function A leaks into every later function of the same module.

The observable symptom is at :107 -- `if var_name not in self.defer_cleaned_vars and
var_name not in self.moved_vars` -- a variable name moved in one function suppresses the
"must be cleaned" diagnostic for an identically named owned variable in a LATER function
(false NEGATIVE). The audit wording predicted the opposite direction (a false "use-after-move"
positive in function B); that direction is probed in section 4 and reported honestly.

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.analyzer.pointer_checker import PointerChecker  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


def run(source):
    """Return (errors, checker) for a full-module check."""
    module = Parser(Lexer(source).tokenize()).parse()
    checker = PointerChecker()
    try:
        checker.check(module)
    except Exception as e:  # noqa: BLE001
        return ("RAISED %s: %s" % (type(e).__name__, e), list(checker.errors), checker)
    return "ok", list(checker.errors), checker


FUNC_A = """def produce() -> None:
    owned buf: int = 10
    moved = transfer_ownership(buf)
"""

FUNC_B = """def consume() -> None:
    owned buf: int = 20
"""

print("=== 1. function B checked on its own (ground truth) ===")
st, errs_b, cb = run(FUNC_B)
print("  status=%s" % st)
for e in errs_b:
    print("  error: %s" % e)
check(st == "ok" and any("must be cleaned" in e for e in errs_b),
      "B alone reports its uncleaned owned 'buf'",
      "expected the diagnostic; got %s" % (errs_b,))

print("=== 2. function A checked on its own (legal transfer, no diagnostic) ===")
st, errs_a, ca = run(FUNC_A)
print("  status=%s  errors=%s" % (st, errs_a))
print("  checker state after A: owned_vars=%s moved_vars=%s" % (sorted(ca.owned_vars), sorted(ca.moved_vars)))
check(st == "ok" and errs_a == [], "A alone is clean", "got %s" % (errs_a,))
check(ca.moved_vars == {"buf"}, "A records 'buf' as moved", "moved_vars=%s" % (ca.moved_vars,))

print("=== 3. A followed by B in ONE module (the leak) ===")
st, errs_ab, cab = run(FUNC_A + "\n" + FUNC_B)
print("  status=%s" % st)
print("  errors: %s" % (errs_ab or ["(none)"]))
print("  checker state after A+B: owned_vars=%s moved_vars=%s defer_cleaned_vars=%s"
      % (sorted(cab.owned_vars), sorted(cab.moved_vars), sorted(cab.defer_cleaned_vars)))
check(st == "ok" and any("must be cleaned" in e for e in errs_ab),
      "B's diagnostic survives A's moved 'buf'",
      "B's genuine uncleaned-owned error was SUPPRESSED because 'buf' is still in the "
      "module-wide moved_vars set (:107)")
check(len(errs_ab) == len(errs_a) + len(errs_b),
      "module result == concatenation of per-function results",
      "per-function %d + %d, whole-module %d" % (len(errs_a), len(errs_b), len(errs_ab)))
check(cab.moved_vars == set() and cab.owned_vars == set(),
      "ownership sets are reset at each _visit_FuncDef",
      "sets persist across functions: owned_vars=%s moved_vars=%s"
      % (sorted(cab.owned_vars), sorted(cab.moved_vars)))

print("=== 4. direction probe: does the leak produce a false use-after-move in B? ===")
st, errs_ba, _ = run(FUNC_B + "\n" + FUNC_A)
print("  B-then-A errors: %s" % (errs_ba or ["(none)"]))
leak_fp = [e for e in errs_ba if "moved owned variable" in e or "already moved" in e]
print("  use-after-move style false positives: %s" % (leak_fp or "(none)"))
if not leak_fp:
    notes.append("audit wording 'function B is reported as use-after-move' is the wrong "
                 "direction: _visit_Name/_visit_Assign read the per-scope is_moved flag, so the "
                 "leak manifests as a MISSED diagnostic at :107 (false negative), and the "
                 "result is order-dependent.")
print("  order dependence: A-then-B -> %d error(s); B-then-A -> %d error(s)"
      % (len(errs_ab), len(errs_ba)))
check(len(errs_ab) == len(errs_ba),
      "diagnostics do not depend on function order",
      "A-then-B gave %s but B-then-A gave %s" % (errs_ab, errs_ba))

print("=== 5. same leak via defer_cleaned_vars (:25 / :298) ===")
DEF_A = """def leaks() -> None:
    owned res: int = 1
    defer:
        free(res)
"""
DEF_B = """def forgets() -> None:
    owned res: int = 2
"""
st, e1, c1 = run(DEF_A)
print("  A(defer free(res)) errors: %s" % (e1 or ["(none)"]))
print("  A defer_cleaned_vars: %s" % (sorted(c1.defer_cleaned_vars),))
st, e2, _ = run(DEF_B)
print("  B alone errors: %s" % (e2 or ["(none)"]))
st, e12, c12 = run(DEF_A + "\n" + DEF_B)
print("  A+B errors: %s   defer_cleaned_vars=%s" % (e12 or ["(none)"], sorted(c12.defer_cleaned_vars)))
if not c1.defer_cleaned_vars:
    notes.append("separate finding: `defer: free(x)` never populates defer_cleaned_vars "
                 "(:291 tests stmt.kind == 'Call' but the parser wraps it in ExprStmt), so the "
                 "defer branch of :107 is dead code today -- a fix that only resets the sets "
                 "will not make defer-cleaned owned vars legal.")

print("=== 6. secondary: transfer_ownership() of a typed PARAMETER crashes the checker ===")
st, errs_p, _ = run("""def take_away(v: int) -> None:
    w = transfer_ownership(v)
""")
print("  status=%s" % st)
print("  errors=%s" % (errs_p,))
check(st == "ok", "checker does not raise on a moved parameter",
      ":232 does {**scope[var]} on the raw type-name *string* stored at :92 -> %s" % (st,))

print("=== 7. control: distinct names in distinct functions are clean ===")
st, errs_c, _ = run("""def one() -> None:
    owned a: int = 1
    x = transfer_ownership(a)

def two() -> None:
    owned b: int = 2
    defer:
        free(b)
""")
print("  status=%s errors=%s" % (st, errs_c))

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
failures = [f for f in failures if f != "order dependence measured"]
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (ownership state is per-function)")
sys.exit(0)
