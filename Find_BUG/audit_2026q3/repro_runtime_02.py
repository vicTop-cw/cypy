"""OMEGA repro T0r61.3.1 / defect 2
cypy_bridge/defer.py:57-72 (defer_context) + :94-114 (defer_scope), singleton at :20-25

Claim under test: DeferManager is a process-wide singleton and its _defer_stack is shared
by every defer_context()/defer_scope(). The inner scope's __exit__ runs execute_all() +
clear() on the SHARED stack (:71-72, :111-112), so defers registered by an enclosing scope
are consumed by the inner scope.

AUDIT WORDING CORRECTION (measured in section 5 below): the outer deferred action is not
"never runs" -- it runs PREMATURELY, at inner exit, while the outer body is still executing.
What is observable and damaging: (a) wrong ordering, (b) a resource released while the outer
scope is still using it, (c) the outer scope then exits with an empty stack, i.e. its own
teardown point is gone.

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
Writes only inside Find_BUG/audit_2026q3/scratch_runtime/.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.defer import DeferManager, defer, defer_context, defer_scope  # noqa: E402

SCRATCH = os.path.join(REPO, "Find_BUG", "audit_2026q3", "scratch_runtime")
failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


def mgr():
    return DeferManager.get_instance()


print("=== 1. nested defer_context: WHEN does the outer action fire? ===")
mgr().clear()
events = []
# HARNESS-FIX (T0r61.3.2): the original had `mgr().clear()` as the LAST statement of the
# outer scope ("keep the process clean"). Once the shared-stack defect is fixed the outer
# action is still pending at that point, so clear() deleted the very deferred action whose
# ordering this section measures and `oi` became None -> the section could never pass.
# Moving the hygiene clear() to AFTER the outer scope closes removes the harness
# interference without touching any assertion.
with defer_context():                                    # outer scope (user code)
    defer(events.append, "OUTER-ACTION")
    events.append("outer-registered")
    with defer_context():                                # inner scope (a library helper)
        events.append("inner-enter")
        defer(events.append, "INNER-ACTION")
        events.append("inner-body")
    events.append("inner-exited")
    events.append("outer-still-working")
mgr().clear()                                            # keep the process clean
print("  trace: %s" % " -> ".join(events))
oi = events.index("OUTER-ACTION") if "OUTER-ACTION" in events else None
ii = events.index("inner-exited") if "inner-exited" in events else None
wi = events.index("outer-still-working") if "outer-still-working" in events else None
print("  OUTER-ACTION index=%s  inner-exited index=%s  outer-still-working index=%s" % (oi, ii, wi))
check(oi is not None and ii is not None and oi > ii,
      "outer action fires only when the OUTER scope exits",
      "outer action fired at trace index %s, i.e. during the outer body: the inner exit "
      "drained the shared stack" % (oi,))
check(oi is not None and wi is not None and oi > wi,
      "outer action fires after the outer body finished",
      "outer action had already run before 'outer-still-working' (index %s < %s)" % (oi, wi))

print("=== 2. pending-defer count as seen from the outer scope ===")
seen = {}
with defer_context():
    defer(events.append, "pending")
    seen["in_outer"] = mgr().count
    with defer_context():
        pass
    seen["after_inner"] = mgr().count
print("  DeferManager.count: outer body=%s   after inner exit=%s" % (seen["in_outer"], seen["after_inner"]))
check(seen["after_inner"] >= seen["in_outer"],
      "inner scope leaves the outer scope's pending defers alone",
      "outer had %d pending defer(s); after the inner scope exited the shared stack held %d"
      % (seen["in_outer"], seen["after_inner"]))
mgr().clear()

print("=== 3. real damage: an outer defer closes a resource the outer body still uses ===")
path = os.path.join(SCRATCH, "_defer_probe.txt")
os.makedirs(SCRATCH, exist_ok=True)
outcome = {}
with defer_context():
    fh = open(path, "w")
    defer(fh.close)                                      # "close when MY scope is done"
    fh.write("head\n")
    with defer_context():                                # unrelated helper using defer
        defer(lambda: None)
    try:
        fh.write("tail-written-after-inner-scope\n")
        outcome["late_write"] = "succeeded"
    except Exception as e:
        outcome["late_write"] = "%s: %s" % (type(e).__name__, e)
outcome["on_disk"] = open(path).read()
print("  write after the inner scope -> %r" % (outcome["late_write"],))
print("  file contents               -> %r" % (outcome["on_disk"],))
check(outcome["late_write"] == "succeeded",
      "resource opened in the outer scope stays open until the outer scope ends",
      "the inner scope executed the outer's fh.close -> %r; the outer body's remaining "
      "output is lost" % (outcome["late_write"],))
check("tail" in outcome["on_disk"], "outer body output is present",
      "contents=%r" % (outcome["on_disk"],))

print("=== 4. same shape with defer_scope (:94-114) ===")
mgr().clear()
seq = []
with defer_scope():
    defer(seq.append, "outer")
    with defer_scope():
        defer(seq.append, "inner")
    seq_at_inner_exit = list(seq)          # sampled while the OUTER scope is still open
    seq.append("outer-scope-exiting")
print("  execution order: %s" % (seq,))
print("  pending at inner exit: %s" % (seq_at_inner_exit,))
# HARNESS-FIX (T0r61.3.2): this asserted `seq_at_inner_exit == []`, i.e. that NOTHING runs
# at the inner exit. That contradicts defer_scope's own contract (and this script's own
# section 6 control, which requires each scope to run its own defers at its exit): the
# inner scope's OWN action must fire when the inner scope ends. What must not fire there is
# the OUTER action, so the assertion is now exact instead of over-strict.
check(seq_at_inner_exit == ["inner"],
      "defer_scope nests without consuming the outer stack",
      "at the inner exit the stack had run %r; only 'inner' may run there, 'outer' belongs "
      "to the outer scope" % (seq_at_inner_exit,))
check(seq.index("outer") > seq.index("outer-scope-exiting"),
      "outer defer_scope action runs at outer exit",
      "order %s" % (seq,))
mgr().clear()

print("=== 5. literal audit claim: 'outer deferred action never runs' ===")
mgr().clear()
ran = []
with defer_context():
    defer(ran.append, "outer")
    with defer_context():
        pass
    ever_at_inner_exit = list(ran)
    mgr().clear()                       # remove any residue so we can ask "would it run again?"
print("  ran during the outer body (at inner exit): %s" % (ever_at_inner_exit,))
print("  ran at all:                                %s" % (bool(ran),))
print("  -> literal wording 'never runs' is %s" % ("FALSE (it runs early)" if ran else "TRUE"))
if ran:
    notes.append("audit wording is inaccurate: the shared-stack defect makes the outer defer "
                 "run PREMATURELY at inner exit (and the outer exit then drains nothing), "
                 "not 'never'.")
mgr().clear()

print("=== 6. control: two sequential (non-nested) scopes are correct ===")
mgr().clear()
ctl = []
with defer_context():
    defer(ctl.append, 1)
with defer_context():
    defer(ctl.append, 2)
check(ctl == [1, 2], "sequential scopes work", "got %s" % (ctl,))

print("=== 7. control: DeferGuard (per-instance stack, :117-151) nests correctly ===")
from cypy_bridge.defer import DeferGuard
g1, g2 = DeferGuard(), DeferGuard()
gseq = []
g1.defer(gseq.append, "outer")
g2.defer(gseq.append, "inner")
g2.execute()
early = "outer" in gseq
g1.execute()
print("  order: %s   (guard leaked? %s)" % (gseq, early))
check((not early) and gseq == ["inner", "outer"],
      "per-instance DeferGuard is the correct model", "got %s early=%s" % (gseq, early))
mgr().clear()

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (defer scopes are isolated)")
sys.exit(0)
