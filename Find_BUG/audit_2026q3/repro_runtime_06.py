"""OMEGA repro T0r61.3.1 / defect 6
cypy_bridge/meta.py:167-203 -- meta(cls=None, *, base=CypyMetaClass)

Claim under test: the two branches are inverted with respect to the documented usage in the
same docstring (:172-183).
  * bare `@meta class M`  -- documented as "define a metaclass" -- takes the ELSE branch
    (:197-199) and returns an ordinary class whose metaclass is `base`; M is NOT a metaclass.
  * `@meta(base=SomeMeta) class C` -- documented as "assign a metaclass to C" -- takes the
    IF branch (:186-196) and returns a NEW metaclass `NewMeta(SomeMeta)`; C's own identity
    (`__name__`, its class-ness, its instantiability) is lost, and `base` is applied as a
    SUPERCLASS of NewMeta rather than as C's metaclass.
The only call shape that reaches the else branch, `meta(SomeClass)` positionally, ignores the
caller's `base` entirely and applies the default CypyMetaClass (literally "losing the base").

Exit: 1 = reproduced, 0 = fixed, 2 = harness problem.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypy_bridge.meta import CypyMetaClass, SingletonMeta, meta  # noqa: E402

failures = []
notes = []


def check(cond, label, detail):
    print("  %s %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        print("       %s" % detail)
        failures.append(label)


print("=== 1. bare `@meta class M` must make M a metaclass marker ===")


@meta
class MyMeta:
    def __new__(cls, name, bases, attrs):
        attrs["custom"] = True
        return type(name, bases, attrs)


print("  MyMeta                 = %r" % (MyMeta,))
print("  type(MyMeta)           = %r   (expected: <class 'type'> -- i.e. MyMeta is a metaclass)"
      % (type(MyMeta),))
print("  issubclass(MyMeta,type)= %s   (expected: True)" % issubclass(MyMeta, type))


class UsesMeta(metaclass=MyMeta):
    pass


print("  class UsesMeta(metaclass=MyMeta):")
print("     type(UsesMeta)      = %r   (expected: MyMeta)" % (type(UsesMeta),))
print("     UsesMeta.custom     = %r" % (getattr(UsesMeta, "custom", "MISSING"),))
check(issubclass(MyMeta, type), "bare @meta yields a real metaclass",
      "MyMeta is an ordinary class (bases=%s, type=%s); the bare branch fell into the "
      "else-branch at :197-199" % (MyMeta.__bases__, type(MyMeta).__name__))
if type(UsesMeta) is not MyMeta:
    notes.append("observational: type(UsesMeta) is %r not MyMeta. This body's own __new__ "
                 "returns type(name, bases, attrs), so the metaclass link cannot be installed "
                 "by this particular example even once @meta is fixed -- it is offered as "
                 "evidence of the inversion, not as an exit-code criterion."
                 % (type(UsesMeta).__name__,))
else:
    check(True, "metaclass=MyMeta actually installs MyMeta", "")
# invariant asserted by tests/test_bridge_library.py::test_meta_decorator -- a fix must keep it
check(getattr(UsesMeta, "custom", None) is True, "existing test invariant: UsesMeta.custom is True",
      "a correct fix must still run the user's __new__ body (tests/test_bridge_library.py:827)")

print("  bare @meta with NO custom __new__ (pure marker form, docstring wording '元类标记'):")


@meta
class MarkerOnly:
    def inject(cls, name, bases, attrs):
        attrs["injected"] = True
        return type(name, bases, attrs)


print("     issubclass(MarkerOnly, type) = %s   type(MarkerOnly) = %s"
      % (issubclass(MarkerOnly, type), type(MarkerOnly).__name__))
marker_inst = None
try:
    class UsesMarker(metaclass=MarkerOnly):
        pass

    marker_inst = UsesMarker
    print("     class C(metaclass=MarkerOnly) -> C.injected=%r  type(C)=%s"
          % (getattr(UsesMarker, "injected", "MISSING"), type(UsesMarker).__name__))
except Exception as e:  # noqa: BLE001
    print("     class C(metaclass=MarkerOnly) -> RAISES %s: %s" % (type(e).__name__, e))
check(marker_inst is not None and type(marker_inst) is MarkerOnly,
      "bare @meta class is usable as a metaclass",
      "MarkerOnly is not a metaclass (issubclass(MarkerOnly, type) is %s), so the marker form "
      "of the documented `@meta` branch does not work" % issubclass(MarkerOnly, type))

print("=== 2. `@meta(base=SingletonMeta) class C` must give C that metaclass ===")


@meta(base=SingletonMeta)
class Config:
    x = 1


print("  Config                 = %r" % (Config,))
print("  Config.__name__        = %r   (expected: 'Config')" % (Config.__name__,))
print("  type(Config)           = %r   (expected: SingletonMeta)" % (type(Config),))
print("  issubclass(Config,type)= %s   (expected: False -- C is a class, not a metaclass)"
      % issubclass(Config, type))
print("  issubclass(Config,SingletonMeta) = %s  <-- `base` landed in the SUPERCLASS slot"
      % issubclass(Config, SingletonMeta))
print("  Config.x               = %r" % (getattr(Config, "x", "MISSING"),))
inst_ok = False
try:
    a, b = Config(), Config()
    inst_ok = True
    print("  Config() singleton      = %s" % (a is b,))
except Exception as e:  # noqa: BLE001
    print("  Config()               -> RAISES %s: %s" % (type(e).__name__, e))
check(type(Config) is SingletonMeta, "base= installs the metaclass on the decorated class",
      "the decorated name was replaced by %r -- a metaclass -- instead of a class with "
      "metaclass=SingletonMeta (:186-196)" % (Config,))
check(Config.__name__ == "Config", "the decorated class keeps its identity",
      "__name__ is %r" % (Config.__name__,))
check(inst_ok, "the decorated class is still instantiable",
      "Config() raised -- every user class decorated with @meta(base=...) is unusable")
check(not issubclass(Config, type), "base= does not turn the class into a metaclass",
      "issubclass(Config, type) is True")

print("=== 3. positional `meta(SomeClass)` ignores the caller's base ===")
try:
    R = meta(SingletonMeta)
    print("  meta(SingletonMeta) -> %r  type=%r" % (R, type(R)))
    check(type(R) is SingletonMeta or issubclass(type(R), SingletonMeta),
          "positional form honours base", "type(R) is %s (default CypyMetaClass) -- base LOST"
          % (type(R).__name__,))
except Exception as e:  # noqa: BLE001
    print("  meta(SingletonMeta) -> RAISES %s: %s" % (type(e).__name__, e))
    check(False, "positional form does not crash", "%s: %s" % (type(e).__name__, e))

print("=== 4. control: the correct semantics exist via metaclass= ===")


class Config2(metaclass=SingletonMeta):
    x = 1


c1, c2 = Config2(), Config2()
print("  type(Config2)=%r  Config2.x=%r  singleton=%s" % (type(Config2), Config2.x, c1 is c2))
check(type(Config2) is SingletonMeta and c1 is c2, "control (metaclass= path) works",
      "reference semantics themselves are broken")

print("=== 5. control: CypyMetaClass marker attributes still installed ===")
print("  Config2.__cypy_class__ = %r" % (getattr(Config2, "__cypy_class__", "MISSING"),))
check(getattr(Config2, "__cypy_class__", False) is True, "control: CypyMetaClass marker", "missing")

print()
if notes:
    for n in notes:
        print("NOTE: %s" % n)
if failures:
    print("RESULT: REPRODUCED (%d checks failed): %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("RESULT: NOT-REPRODUCED (both @meta branches behave as documented)")
sys.exit(0)
