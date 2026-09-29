"""OMEGA repro T0r61.3.1 / defect 8
cypy_bridge/union.py:89-104 (value setter) and :106-117 (set_value)

Claims under test: the member-selection loop builds `ctype(new_value)` (:96 / :113) and
writes `cval.value` back (:98 / :114). ctypes integer types *wrap* out-of-range values
instead of raising, and the only exceptions caught are TypeError/ValueError -- so
`cdef_union("unsigned char", "float").value = 300` silently stores 44 (300 & 0xFF) in the
c_ubyte member rather than rejecting the value or widening to the float member.

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import ctypes
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.union import CUnion, UnionTypeError, cdef_union  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


def assign(u, value):
    """Returns (outcome, stored) where outcome is 'accepted' / 'rejected:<Exc>'."""
    try:
        u.value = value
        return "accepted", u.value
    except (UnionTypeError, ValueError, TypeError) as e:
        return "rejected:%s" % type(e).__name__, None


print("=== 1. unsigned char member, out-of-range source value ===")
u = cdef_union("unsigned char", "float")
print("  members: %s   size=%d" % ([t.__name__ for t in u.member_types], u.size))
print("  reference: ctypes.c_ubyte(300).value == %r  (silent 8-bit wrap)"
      % (ctypes.c_ubyte(300).value,))
for value, lo, hi in [(300, 0, 255), (-1, 0, 255), (256, 0, 255), (999999, 0, 255)]:
    outcome, stored = assign(u, value)
    print("  u.value = %-8d -> %-22s stored=%r" % (value, outcome, stored))
    if outcome == "accepted":
        exact = stored == value
        check(exact, "u.value = %d" % value,
              "accepted but truncated to %r -- %d does not fit any member type "
              "((unsigned char, float) widened into c_ubyte at :96-98)" % (stored, value))
    else:
        check(True, "u.value = %d" % value, "")

print("=== 2. signed member wrap (c_byte) ===")
try:
    v = CUnion(ctypes.c_byte, ctypes.c_double)
    outcome, stored = assign(v, 200)
    print("  CUnion(c_byte, c_double).value = 200 -> %-16s stored=%r" % (outcome, stored))
    check(outcome != "accepted" or stored == 200, "c_byte(200) out-of-range handled",
          "wrapped to %r (200-256) instead of selecting the c_double member" % (stored,))
except Exception as e:  # noqa: BLE001
    print("  probe failed: %s: %s" % (type(e).__name__, e))

print("=== 3. set_value() with an explicit index (:106-117) ===")
u2 = cdef_union("unsigned char", "float")
outcome, stored = "accepted", None
try:
    u2.set_value(777, 0)
    stored = u2.get_value_as(0)
    print("  set_value(777, index=0) -> get_value_as(0) = %r" % (stored,))
except (UnionTypeError, ValueError, TypeError) as e:
    outcome = "rejected:%s" % type(e).__name__
    print("  set_value(777, index=0) -> %s" % outcome)
check(outcome != "accepted" or stored == 777, "set_value honours the range of member 0",
      "777 silently became %r (777 & 0xFF == 9) -- :113-114 have the same wrap" % (stored,))

print("=== 4. active_type after an out-of-range assignment ===")
u3 = cdef_union("unsigned char", "float")
try:
    u3.value = 300
    print("  after value=300: value=%r active_type=%s get_value_as(1)(float)=%r"
          % (u3.value, u3.active_type.__name__, u3.get_value_as(1)))
    # 修复前这里只会写进 1 个字节，float 成员读到的是垃圾值（6.1657e-44）。
    # 修复后 300 被"提升到"能容纳它的 float 成员，两个成员读到的是同一个值。
    notes.append("kept for the record: pre-fix this printed value=44 with "
                 "get_value_as(1) == 6.165713243029195e-44 (only 1 of the 4 bytes "
                 "ever written)")
except Exception as e:  # noqa: BLE001
    print("  after value=300: rejected (%s)" % type(e).__name__)

print("=== 5. regression guards: valid usage must keep working ===")
u4 = cdef_union("int", "float")
for value, want in [(42, 42), (2.5, 2.5), (-7, -7)]:
    outcome, stored = assign(u4, value)
    ok = outcome == "accepted" and stored == want
    print("  cdef_union('int','float').value = %-5r -> %-16s stored=%r %s"
          % (value, outcome, stored, "" if ok else "<== BROKEN BY FIX?"))
    check(ok, "invariant value=%r" % (value,), "got %s %r" % (outcome, stored))
try:
    u4.value = "not a number"
    check(False, "invariant: non-numeric still rejected", "accepted a string")
except UnionTypeError:
    print("  u.value = 'not a number' -> UnionTypeError (correct, tests/test_bridge_library.py:677)")
check(u4.active_type.__name__ in ("c_int", "c_long"), "invariant active_type after int",
      "active_type=%s" % (u4.active_type.__name__,))
u4.value = 3.14
check(abs(u4.value - 3.14) < 1e-4, "invariant float member still selected",
      "value=%r active=%s" % (u4.value, u4.active_type.__name__))

print("=== 6. guard: bad indices still rejected (:108-109, :121-122) ===")
for idx in (5, -1):
    try:
        u4.set_value(1, idx)
        check(False, "index %d rejected" % idx, "accepted")
    except UnionTypeError:
        print("  set_value(1, %d) -> UnionTypeError (correct)" % idx)

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (out-of-range union values are rejected or widened)")
sys.exit(0)
