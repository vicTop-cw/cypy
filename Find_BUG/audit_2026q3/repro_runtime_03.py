"""OMEGA repro T0r61.3.1 / defect 3
cypy_bridge/nogil.py:126 (module-level singleton `nogil = NoGilContext()`) + :106-115

Claim under test: NoGilContext stores its per-entry state in the shared attribute
self._state (:108). Nested use of the singleton -- `with nogil:` inside `with nogil:`, a
`@nogil`-decorated call or nogil_exec() inside a nogil region -- overwrites it, so the
inner __exit__ releases the outer's GilState and the outer __exit__ then calls acquire()
on an already-acquired state -> NoGilError("GIL is not released") at nogil.py:59, and the
region is mis-released (outer no-protected while still executing).

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.nogil import NoGilContext, NoGilError, nogil, nogil_exec  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


print("=== 1. nested `with nogil:` on the singleton ===")
reached_inner_body = []
try:
    with nogil:
        with nogil:
            reached_inner_body.append(True)
    nested_ok = True
    err = None
except Exception as e:
    nested_ok = False
    err = e
print("  nested region completed without error: %s" % nested_ok)
if err is not None:
    print("  RAISES %s: %s   (inner body reached: %s)"
          % (err.__class__.__name__, err, bool(reached_inner_body)))
else:
    print("  no exception")
check(nested_ok, "with nogil: { with nogil: }",
      "nesting the public nogil context manager raises %s: %s" % (err.__class__.__name__, err))

print("=== 2. mis-release: outer region loses its release while still inside ===")
observed = {}
outer_exit_error = None
try:
    with nogil:
        try:
            with nogil:
                pass
        except NoGilError as e:
            observed["inner_error"] = str(e)
        st = getattr(nogil, "_state", None)
        observed["released"] = getattr(st, "released", "n/a")
        print("  inside outer, after inner exit: nogil._state.released = %r (inner error: %r)"
              % (observed.get("released"), observed.get("inner_error")))
except NoGilError as e:
    outer_exit_error = str(e)
    print("  outer __exit__ raised: %s" % e)
label2 = "outer nogil region is still released after the inner region exits"
if observed.get("released") == "n/a":
    check(False, label2, "nogil._state no longer exists (implementation changed); "
          "verify re-entrancy via sections 1/6/8 instead")
elif outer_exit_error is not None:
    check(False, label2, "region torn down early -- outer __exit__ reported %r" % outer_exit_error)
else:
    check(observed.get("released") is True, label2,
          "the inner __exit__ (:114) acquired the state object the outer is still using")

print("=== 3. @nogil decorated function called inside a `with nogil:` region ===")
@nogil
def cpu_bound(x):
    return x * 2


try:
    with nogil:
        got = cpu_bound(21)
    print("  result=%r" % (got,))
    check(got == 42, "@nogil callable nested in with nogil:", "unexpected result")
except Exception as e:
    print("  RAISES %s: %s" % (type(e).__name__, e))
    check(False, "@nogil callable nested in with nogil:",
          "nogil.__call__ (:117-122) reuses `with self:` on the same singleton -> %s" % (e,))

print("=== 4. nogil_exec() (:202-209) composed inside a `with nogil:` region ===")
try:
    with nogil:
        got = nogil_exec(lambda: 7)
    print("  result=%r" % (got,))
    check(got == 7, "nogil_exec nested in with nogil:", "unexpected result")
except Exception as e:
    print("  RAISES %s: %s" % (type(e).__name__, e))
    check(False, "nogil_exec nested in with nogil:", str(e))

print("=== 5. exception masking inside a nested region ===")
escaped = None
try:
    with nogil:
        with nogil:
            raise ValueError("user error")
except BaseException as e:  # noqa: BLE001
    escaped = e
print("  exception that escaped: %s: %s" % (escaped.__class__.__name__, escaped))
check(isinstance(escaped, ValueError), "user exception propagates unchanged",
      "NoGilError raised by the outer __exit__ replaced the user's ValueError")

print("=== 6. control: two INDEPENDENT NoGilContext instances nest fine ===")
try:
    with NoGilContext():
        with NoGilContext():
            pass
    ctrl = True
    print("  OK -> the defect is the shared singleton's `self._state`, not nesting per se")
except Exception as e:
    ctrl = False
    print("  RAISES %s: %s" % (type(e).__name__, e))
check(ctrl, "independent NoGilContext instances nest",
      "unexpected: even independent instances fail (%s)" % (ctrl,))

print("=== 7. recovery: single-level use after a failed nested use ===")
try:
    with nogil:
        pass
    ok2 = True
except Exception as e:
    ok2 = False
    print("  RAISES %s: %s" % (type(e).__name__, e))
check(ok2, "singleton still usable after the failure", "permanent state corruption")

print("=== 8. three-deep nesting ===")
try:
    with nogil:
        with nogil:
            with nogil:
                pass
    ok3 = True
except Exception as e:
    ok3 = False
    print("  RAISES %s: %s" % (type(e).__name__, e))
check(ok3, "three-deep nesting", "raises on the outermost exits")

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (nogil is re-entrant)")
sys.exit(0)
