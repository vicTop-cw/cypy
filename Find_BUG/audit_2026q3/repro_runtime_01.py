"""OMEGA repro T0r61.3.1 / defect 1
cypy_bridge/pointer.py:271 (Owned weakref) + :147-148, :154-156, :169 (ptr()/base_type)

Claims under test:
  A. Owned.__init__ (:271) uses weakref.ref(value) unconditionally -> TypeError for
     non-weakref-able builtins (int/float/str/tuple/list/dict/bool/None).
  B. Owned(ctypes.c_int(42)) on a temporary does NOT raise but yields an already-dead
     weak reference -> Owned(NULL), i.e. a silently empty ownership handle.
  C. ptr(obj) (:147-148) sets base_type from obj._type_, which is a *string* ('i'/'l'),
     so .deref() (:60-61) and .offset() (:94) blow up.
  D. ptr(5) (:167-169) raises PointerError because base_type = type(5) = int and
     ctypes.byref(int) is invalid.
  E. ptr() returns Pointer(ctypes.byref(obj), ...) (:154-156); _get_address() (:39-47)
     cannot handle a CArgObject, so .offset()/:113 __eq__/130 __repr__ raise TypeError
     even when base_type is a real ctypes type.
  F. End-to-end impact: codegen emits `x = own(10)` for `owned x: int = 10`
     (tests/test_ownership.py:146 asserts exactly that), so every owned scalar crashes
     at import of the generated module.

Exit: 1 = at least one claim reproduced, 0 = all fixed, 2 = harness problem.
Reads only; writes nothing.
"""

import ctypes
import gc
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.pointer import Borrowed, Owned, Pointer, own, ptr  # noqa: E402
from cypy_bridge.types import _type_mapper  # noqa: E402

failures = []
notes = []


# HARNESS-FIX (T0r61.3.2): `ctypes._CData` is not exported by ctypes/_ctypes on this
# CPython (3.13.14) -- `hasattr(ctypes, '_CData')` is False, so the original helper raised
# AttributeError and section C reported "ptr(c_int(42)) constructs FAILED" even though the
# Pointer constructed fine. Judging "is this a usable ctypes type" through the PUBLIC
# ctypes.sizeof() is equivalent and version-proof (a non-ctypes type gives
# TypeError: this type has no size). Assertion strength is unchanged.
def is_ctypes_type(t):
    if not isinstance(t, type):
        return False
    try:
        ctypes.sizeof(t)
    except TypeError:
        return False
    return True


def check(cond, label, detail):
    if cond:
        print("  PASS %s" % label)
    else:
        print("  FAIL %s" % label)
        print("       %s" % detail)
        failures.append(label)
    return cond


print("=== A. Owned.__init__ on non-weakref-able builtins (pointer.py:271) ===")
for value in (5, 3.14, "text", (1, 2), [1], {1: 2}, True, None):
    label = "Owned(%r)" % (value,)
    try:
        o = Owned(value)
        ok = o.is_valid
        print("  %-18s -> constructed, is_valid=%s, take()=%r" % (label, ok, o.take() if ok else None))
        check(ok, label, "constructed but is_valid=False (ownership handle is empty)")
    except TypeError as e:
        print("  %-18s -> RAISES TypeError: %s" % (label, e))
        check(False, label, "weakref.ref() on a built-in raises TypeError -> Owned/own/borrow unusable for scalars")
    except Exception as e:  # pragma: no cover
        print("  %-18s -> RAISES %s: %s" % (label, type(e).__name__, e))
        check(False, label, "unexpected exception type %s" % type(e).__name__)

print("  control: Owned of a weakref-able user object")
class Holder:
    def __init__(self, d):
        self.data = d

h = Holder(7)
o = Owned(h)
check(o.is_valid and o.take() is h, "Owned(Holder) control", "even the supported case fails")

print("=== A2. own()/borrow() convenience wrappers ===")
try:
    got = own(42).take()
    print("  own(42).take() -> %r" % (got,))
    check(got == 42, "own(42)", "wrong value")
except Exception as e:
    print("  own(42) -> RAISES %s: %s" % (type(e).__name__, e))
    check(False, "own(42)", "%s: %s" % (type(e).__name__, e))
try:
    b = Owned(42).borrow() if False else None
except Exception as e:
    notes.append("Owned(42).borrow() also unreachable: %s" % e)

print("=== B. Owned() on a temporary ctypes object ===")
try:
    tmp_owned = Owned(ctypes.c_int(42))
    print("  Owned(ctypes.c_int(42)) -> repr=%s is_valid=%s" % (repr(tmp_owned), tmp_owned.is_valid))
    check(tmp_owned.is_valid, "Owned(temporary c_int)",
          "silently dead weak reference: %r (no exception, no owner)" % (repr(tmp_owned),))
except Exception as e:
    print("  Owned(ctypes.c_int(42)) -> RAISES %s: %s" % (type(e).__name__, e))
    check(False, "Owned(temporary c_int)", "%s: %s" % (type(e).__name__, e))

print("=== C. ptr(ctypes.c_int(42)): base_type taken from _type_ (:147-148) ===")
p = None
try:
    p = ptr(ctypes.c_int(42))
    print("  ptr(c_int(42)).base_type = %r  (type %s)" % (p.base_type, type(p.base_type).__name__))
    check(is_ctypes_type(p.base_type), "base_type is a ctypes type",
          "base_type is the *string* %r taken from obj._type_ -> deref/offset/sizeof break" % (p.base_type,))
except Exception as e:
    print("  ptr(c_int(42)) -> RAISES %s: %s" % (type(e).__name__, e))
    check(False, "ptr(c_int(42)) constructs", "%s: %s" % (type(e).__name__, e))

if p is not None:
    try:
        v = p.deref()
        print("  .deref() -> %r" % (v,))
        check(v == 42, "ptr(c_int(42)).deref()", "returned %r" % (v,))
    except Exception as e:
        print("  .deref() -> RAISES %s: %s" % (type(e).__name__, e))
        check(False, "ptr(c_int(42)).deref()", "%s: %s" % (type(e).__name__, e))
    try:
        o2 = p.offset(1)
        print("  .offset(1) -> %r" % (o2,))
        check(isinstance(o2, Pointer), "ptr(c_int(42)).offset(1)", "not a Pointer")
    except Exception as e:
        print("  .offset(1) -> RAISES %s: %s" % (type(e).__name__, e))
        check(False, "ptr(c_int(42)).offset(1)", "%s: %s" % (type(e).__name__, e))

print("=== D. ptr(5) on a plain Python int (:167-169) ===")
try:
    p5 = ptr(5)
    print("  ptr(5) -> %r" % (p5,))
    try:
        dv = p5.deref()
        print("  ptr(5).deref() -> %r" % (dv,))
        check(dv == 5, "ptr(5).deref()", "returned %r" % (dv,))
    except Exception as e:
        print("  ptr(5).deref() -> RAISES %s: %s" % (type(e).__name__, e))
        check(False, "ptr(5).deref()", "%s: %s" % (type(e).__name__, e))
except Exception as e:
    print("  ptr(5) -> RAISES %s: %s" % (type(e).__name__, e))
    check(False, "ptr(5)", "%s: %s" % (type(e).__name__, e))

print("=== E. byref()-based Pointer cannot compute its own address (:154-156 vs :39-47) ===")
arr = (ctypes.c_int * 4)(10, 20, 30, 40)
byref_p = Pointer(ctypes.byref(arr), ctypes.c_int)          # what ptr() builds, with a GOOD base_type
cast_p = Pointer(ctypes.cast(ctypes.byref(arr), ctypes.POINTER(ctypes.c_int)), ctypes.c_int)
print("  control POINTER-based: deref=%r offset(1).deref=%r" % (cast_p.deref(), (cast_p + 1).deref()))
try:
    print("  byref-based: deref=%r" % (byref_p.deref(),))
except Exception as e:
    print("  byref-based: deref RAISES %s: %s" % (type(e).__name__, e))
try:
    r = (byref_p + 1).deref()
    print("  byref-based: (p + 1).deref()=%r  -> address arithmetic works" % (r,))
    check(r == 20, "byref-based offset arithmetic", "wrong value %r" % (r,))
except Exception as e:
    print("  byref-based: (p + 1) RAISES %s: %s" % (type(e).__name__, e))
    check(False, "byref-based offset arithmetic",
          "_get_address() cannot handle ctypes.byref() CArgObject -> every ptr()-derived "
          "Pointer fails on offset()/__eq__/__repr__ (%s)" % (e,))

print("=== F. end-to-end: `owned x: int = 10` codegen -> own(10) ===")
try:
    from cypyc.codegen.cython_generator import CythonGenerator
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser

    code = CythonGenerator().generate(Parser(Lexer("owned counter: int = 10\n").tokenize()).parse())
    emitted = [l.strip() for l in code.splitlines() if "counter" in l]
    print("  generated statement(s): %s" % (emitted,))
    if any("own(10)" in l for l in emitted):
        try:
            ns = {}
            exec("from cypy_bridge.pointer import own\ncounter = own(10)\nresult = counter.take()", ns)
            print("  exec of the generated statement -> counter=%r" % (ns.get("result"),))
            check(ns.get("result") == 10, "generated own(10) executes", "wrong value")
        except Exception as e:
            print("  exec of the generated statement -> RAISES %s: %s" % (type(e).__name__, e))
            check(False, "generated own(10) executes",
                  "every `owned <int>` in user code becomes a module-level TypeError")
    else:
        notes.append("codegen no longer emits own(10); F skipped (emitted=%s)" % emitted)
except ImportError as e:
    notes.append("F skipped, cypyc import failed: %s" % e)

print()
print("=== type-mapper cross-check (why base_type must be resolved through to_ctypes) ===")
print("  c_int._type_ = %r  -> to_ctypes(%r) = %s" % (ctypes.c_int(1)._type_, ctypes.c_int(1)._type_,
                                                     getattr(_type_mapper.to_ctypes(ctypes.c_int(1)._type_), "__name__", "?")))
print("  pointer.type_name supported? %s" % ("i" in _type_mapper.cypy_to_ctypes or "l" in _type_mapper.cypy_to_ctypes))

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d/%d checks failed): %s"
          % (len(failures), len(failures) + 1, "; ".join(sorted(set(failures)))))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (all pointer.py / Owned checks pass)")
sys.exit(0)
