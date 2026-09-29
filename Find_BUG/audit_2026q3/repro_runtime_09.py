"""OMEGA repro T0r61.3.1 / defect 9
cypy_bridge/types.py:114-116 (TypeMapper.to_ctypes) + NULL handling in memory.py / pointer.py
+ __eq__ without __hash__

Claims under test:
  A. types.py:116  `return self.cypy_to_ctypes.get(cypy_type, ctypes.py_object)` -- an
     unknown Cypy type silently degrades to ctypes.py_object instead of raising
     TypeConversionError, so `cdef/declare/cast` on an unsupported C type produce Python-object
     semantics with no diagnostic.
  B. NULL handling: the audit suspected `c_void_p(None)` truthiness misuse. Measured in
     section 3, bool(c_void_p(None)) IS False, so the `if not self._ptr` guards in
     pointer.py:55/:72/:91 work correctly -- that wording is wrong. The real hazard is that
     memory.memmove/memcpy/memset (memory.py:144-209) do NO NULL validation at all and pass
     NULL straight to the C library -> access violation. Also malloc() is annotated
     `-> ctypes.c_void_p` but returns a plain int (restype conversion), which is what makes
     the isinstance() dispatches in memory.py quietly fall through.
  C. pointer.py:113 defines Pointer.__eq__ without __hash__, so Python sets Pointer.__hash__
     to None and every Pointer is unhashable (no set/dict key).

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import ctypes
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.core import TypeConversionError  # noqa: E402
from cypy_bridge.pointer import Pointer  # noqa: E402
from cypy_bridge.types import (  # noqa: E402
    CDefVariable,
    TypeMapper,
    _type_mapper,
    cast,
    cdef,
    declare,
)

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


print("=== 1. to_ctypes() on types that do not exist in the map (types.py:116) ===")
UNKNOWN = ["int128", "uint128", "float16", "wchar_t", "long long *", "char[10]", "no_such_type"]
for name in UNKNOWN:
    try:
        got = _type_mapper.to_ctypes(name)
        print("  to_ctypes(%-14r) -> %-12s  (silent py_object fallback)"
              % (name, getattr(got, "__name__", got)))
        check(False, "to_ctypes(%r) raises TypeConversionError" % name,
              "returned %s -- unknown types are silently reinterpreted as PyObject* "
              "instead of failing" % (getattr(got, "__name__", got),))
    except TypeConversionError as e:
        print("  to_ctypes(%-14r) -> TypeConversionError: %s" % (name, e))
        check(True, "to_ctypes(%r)" % name, "")
    except Exception as e:  # noqa: BLE001
        print("  to_ctypes(%-14r) -> %s: %s" % (name, type(e).__name__, e))
        check(False, "to_ctypes(%r) raises TypeConversionError" % name,
              "wrong exception type %s (TypeConversionError expected)" % type(e).__name__)

print("  is_builtin() knows they are unsupported: %s"
      % {n: _type_mapper.is_builtin(n) for n in UNKNOWN[:4]})

print("=== 2. downstream contamination from the py_object fallback ===")
# HARNESS-FIX (T0r61.3.2): declare()/cast()/cdef() all funnel through to_ctypes(), which
# section 1 (and defect 9) require to RAISE TypeConversionError. The original block called
# declare("int128", ...) bare, so the prescribed exception escaped as an uncaught traceback
# and this script could never reach exit 0. "Refuses" now accepts either outcome that keeps
# the py_object fallback away from the caller: raising, or returning something that is not
# built on ctypes.py_object. Returning a py_object-backed object still fails the check.
def refuses(fn, label):
    try:
        got = fn()
    except TypeConversionError as e:
        print("  %-26s -> TypeConversionError: %s" % (label, e))
        check(True, "%s refuses an unsupported type" % label, "")
        return None
    except Exception as e:  # noqa: BLE001
        print("  %-26s -> %s: %s" % (label, type(e).__name__, e))
        check(False, "%s refuses an unsupported type" % label,
              "wrong exception type %s" % type(e).__name__)
        return None
    print("  %-26s -> %r" % (label, got))
    check(not (isinstance(got, CDefVariable) and got.ctype is ctypes.py_object)
          and getattr(got, "ctype", None) is not ctypes.py_object,
          "%s refuses an unsupported type" % label,
          "silently produced a py_object-backed result")
    return got

refuses(lambda: declare("int128", "x", 5), "declare('int128','x',5)")
r = refuses(lambda: cast("int128", 9.7), "cast('int128', 9.7)")
check(r is None or isinstance(r, int), "cast() to an unsupported type converts or raises",
      "returned %r -- cast silently became a no-op (:345-346)" % (r,))
refuses(lambda: cdef("int128"), "cdef('int128')")
print("  control: supported types still map: to_ctypes('int')=%s to_ctypes('double')=%s"
      % (_type_mapper.to_ctypes("int").__name__, _type_mapper.to_ctypes("double").__name__))
check(_type_mapper.to_ctypes("double") is ctypes.c_double, "invariant to_ctypes('double')", "changed")

print("=== 3. c_void_p(None) truthiness (audit suspected misuse) ===")
z = ctypes.c_void_p(None)
print("  bool(c_void_p(None))=%s  bool(c_void_p(0))=%s  bool(POINTER(c_int)())=%s"
      % (bool(z), bool(ctypes.c_void_p(0)), bool(ctypes.POINTER(ctypes.c_int)())))
print("  -> `if not self._ptr` in pointer.py:55/72/91 therefore DOES catch NULL")
nulls = [("None", Pointer(None, ctypes.c_int)),
         ("c_void_p(None)", Pointer(z, ctypes.c_int)),
         ("POINTER(c_int)()", Pointer(ctypes.POINTER(ctypes.c_int)(), ctypes.c_int))]
from cypy_bridge.core import BridgeError  # noqa: E402
for tag, np in nulls:
    probes = [("deref", lambda n: n.deref()), ("assign", lambda n: n.assign(1)),
              ("offset", lambda n: n.offset(1))]
    for meth, fn in probes:
        try:
            fn(np)
            check(False, "NULL(%s).%s rejected" % (tag, meth), "returned without error")
        except Exception as e:  # noqa: BLE001
            check(isinstance(e, BridgeError), "NULL(%s).%s raises PointerError" % (tag, meth),
                  "raised %s: %s" % (type(e).__name__, e))

print("=== 4. memory.* pass NULL straight to libc (memory.py:144-209) ===")
from cypy_bridge.memory import memcpy, memmove, memset  # noqa: E402
for name, call in (
    ("memmove(NULL,NULL,8)", lambda: memmove(ctypes.c_void_p(None), ctypes.c_void_p(None), 8)),
    ("memcpy(NULL,src,8)", lambda: memcpy(ctypes.c_void_p(None), ctypes.c_void_p(None), 8)),
    ("memset(NULL,0,8)", lambda: memset(ctypes.c_void_p(None), 0, 8)),
):
    try:
        call()
        print("  %-22s -> returned silently (NULL written through!)" % name)
        check(False, "%s is rejected" % name, "no validation, the C call was made")
    except OSError as e:
        print("  %-22s -> OSError: %s" % (name, e))
        check(False, "%s is rejected before the C call" % name,
              "access violation instead of a MemoryError/ValueError -- no NULL guard in "
              "memory.memmove/memcpy/memset")
    except Exception as e:  # noqa: BLE001
        print("  %-22s -> %s: %s" % (name, type(e).__name__, e))
        check(type(e).__name__ in ("MemoryError", "ValueError", "BridgeError"),
              "%s raises a clean bridge error" % name, "%s" % (e,))

print("=== 5. malloc() return type vs its annotation ===")
import typing  # noqa: E402
from cypy_bridge.memory import aligned_alloc, calloc, free, malloc, memset  # noqa: E402
p = malloc(16)
ann = typing.get_type_hints(malloc).get("return")
print("  malloc(16) -> %r type=%s (annotation: %s)"
      % (p, type(p).__name__, getattr(ann, "__name__", ann)))
# HARNESS-FIX (T0r61.3.2): the original asserted `isinstance(p, ctypes.c_void_p)`, i.e. it
# demanded that malloc() START returning a c_void_p. That is not the defect and it is not
# allowed here: tests/test_bridge_library.py:245-251 (test_memmove) does `memmove(ptr + 10,
# ptr, 10)`, which only works because malloc() returns a plain int (ctypes.c_void_p has no
# arithmetic). The real defects were (a) the annotation lied and (b) the isinstance
# dispatches in memory.py therefore never matched. Assert the corrected contract instead:
# annotation == actual type, and the dispatch really handles that type.
check(ann is type(p) and isinstance(p, int),
      "malloc()'s annotation matches the value it returns",
      "annotation is %r but the function returns %s -- the lie that made the "
      "isinstance(ptr, c_void_p) branches dead" % (ann, type(p).__name__))
memset(p, 7, 16)                       # must take the recognised path, not a cast fallback
free(p)
c = calloc(4, 4)
check(isinstance(c, int), "calloc() returns the same (annotated) type", "%r" % (type(c),))
free(c)
ap = aligned_alloc(64, 128)
check(isinstance(ap, int)
      and typing.get_type_hints(aligned_alloc).get("return") is int,
      "aligned_alloc() is annotated and returns the same type",
      "ap=%r annotation=%r" % (ap, typing.get_type_hints(aligned_alloc).get("return")))
free(ap)

print("=== 6. __eq__ defined without __hash__ ===")
print("  Pointer: '__eq__' in vars=%s  Pointer.__hash__=%s"
      % ("__eq__" in vars(Pointer), Pointer.__hash__))
try:
    {Pointer(ctypes.c_void_p(1), ctypes.c_int): "x"}
    hashed = True
except TypeError as e:
    hashed = False
    print("  dict key -> TypeError: %s" % e)
check(hashed, "Pointer is hashable",
      "pointer.py:113 sets __eq__ and never defines __hash__, so Pointers cannot be dict keys "
      "or set members")
import importlib  # noqa: E402
mods = {"cypy_bridge.pointer": ["Pointer", "Owned", "Borrowed"],
        "cypy_bridge.union": ["CUnion"],
        "cypy_bridge.types": ["CDefVariable", "CDefType", "CPDefFunction"],
        "cypy_bridge.struct": [], "cypy_bridge.enum": [], "cypy_bridge.generics": []}
offenders = []
for mod_name, names in mods.items():
    mod = importlib.import_module(mod_name)
    for n in dir(mod):
        obj = getattr(mod, n)
        if isinstance(obj, type) and obj.__module__ == mod_name:
            if "__eq__" in vars(obj) and vars(obj).get("__hash__") is None:
                offenders.append("%s.%s" % (mod_name, n))
print("  classes in cypy_bridge with __eq__ and no __hash__: %s" % (offenders or "(none)",))
check(not offenders, "no __eq__-without-__hash__ classes", "%s" % (offenders,))

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s"
          % (len(failures), "; ".join(sorted(set(failures)))[:400]))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (unknown types raise, NULL guarded, Pointer hashable)")
sys.exit(0)
