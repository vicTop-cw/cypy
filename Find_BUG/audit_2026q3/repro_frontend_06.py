#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 06.

Target: cypyc/analyzer/type_checker.py:15-21  (Type.__eq__)
        union_members are built at :2740 (UnionType) and :2752 (Optional[...]).

Claim: Type.__eq__ compares name / is_pointer / is_ref / generic_params but NOT
union_members, so every union type collapses onto the plain `object` type:
Optional[int] == Optional[str] == Union[int, str] == object == Any -> True.
Expected: unions with different member lists are not equal.
Also pinned: whether __hash__ exists and stays consistent with __eq__.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer                             # noqa: E402
from cypyc.parser.parser import Parser                          # noqa: E402
from cypyc.analyzer.type_checker import Type, TypeChecker        # noqa: E402

ORIGINAL_EQ = Type.__eq__


def fixed_eq(self, other):
    """The candidate fix: same four fields + union_members (process-local only)."""
    return (isinstance(other, Type) and self.name == other.name
            and self.is_pointer == other.is_pointer and self.is_ref == other.is_ref
            and self.generic_params == other.generic_params
            and self.union_members == other.union_members)


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def type_of(annotation_src):
    """Build the Type through the real construction sites (:2740 / :2752)."""
    tc = TypeChecker()
    fn = parse("def f(x: %s):\n    return 0\n" % annotation_src).body[0]
    return tc._get_type_from_node(fn.params[0].type_annotation)


def errors(src, eq=None):
    Type.__eq__ = eq or ORIGINAL_EQ
    try:
        tc = TypeChecker()
        tc.check(parse(src))
        return list(tc.errors)
    except Exception as exc:                                       # noqa: BLE001
        return ["<checker raised %s: %s>" % (type(exc).__name__, exc)]
    finally:
        Type.__eq__ = ORIGINAL_EQ


SAMPLES = {
    "let a: Optional[int] = 1; let b: Optional[str] = a":
        "def f():\n    let a: Optional[int] = 1\n    let b: Optional[str] = a\n    return b\n",
    "control: let a: int = 1; let b: str = a":
        "def f():\n    let a: int = 1\n    let b: str = a\n    return b\n",
    "def g() -> Optional[str]: return an Optional[int] value":
        "def g() -> Optional[str]:\n    let a: Optional[int] = 1\n    return a\n",
    "control: def g() -> str: return an int value":
        "def g() -> str:\n    let a: int = 1\n    return a\n",
    "sanity: let x: Optional[int] = \"no\" (must error)":
        "def f():\n    let x: Optional[int] = \"no\"\n    return x\n",
    "sanity: let x: Optional[int] = 5 (must be clean)":
        "def f():\n    let x: Optional[int] = 5\n    return x\n",
}


def main():
    print("=" * 78)
    print("T0r61.2.1 / defect 06 - cypyc/analyzer/type_checker.py:15-21 "
          "Type.__eq__ ignores union_members")
    print("=" * 78)

    opt_int = type_of("Optional[int]")
    opt_str = type_of("Optional[str]")
    u_is = type_of("Union[int, str]")
    plain_obj = type_of("object")
    any_t = type_of("Any")
    int_t = type_of("int")

    print("types built by the real pipeline (_get_type_from_node):")
    for label, t in (("Optional[int]", opt_int), ("Optional[str]", opt_str),
                     ("Union[int,str]", u_is), ("object", plain_obj), ("Any", any_t),
                     ("int", int_t)):
        print("  %-16s name=%-7r union_members=%-22s repr=%r   __dict__ keys=%s"
              % (label, t.name, [str(m) for m in t.union_members], str(t),
                 sorted(t.__dict__)))
    print()

    # (label, actual comparison, should be equal after a correct __eq__)
    checks = [
        ("Optional[int] == Optional[str]", opt_int == opt_str, False),
        ("Union[int,str] == Optional[int]", u_is == opt_int, False),
        ("Optional[int] == object", opt_int == plain_obj, False),
        ("Optional[int] == Any", opt_int == any_t, False),
        ("int == int  (must stay equal)", int_t == type_of("int"), True),
        ("Optional[int] == int (audit wording)", opt_int == int_t, False),
    ]
    unsound = []
    for label, got, should in checks:
        bad = got and not should
        if bad:
            unsound.append(label)
        print("  %-38s -> %-9s %s" % (label, "EQUAL" if got else "not equal",
                                      "UNSOUND (members differ)" if bad
                                      else "ok" if got == should else "unexpected"))
    print("  note: the audit's literal wording 'Optional[int] == int' does NOT hold "
          "as stated\n        (names are 'object' vs 'int'); what collapses is every "
          "union with object/Any\n        and with every other union.")
    print()

    print("__hash__ contract:")
    print("  Type.__hash__ is %r -> instances are %s"
          % (Type.__hash__, "hashable" if Type.__hash__ else "UNHASHABLE"))
    try:
        {opt_int: 1}
        print("  usable as a dict key: YES")
    except TypeError as exc:
        print("  usable as a dict key: NO (%s)" % exc)
    print("  defining __eq__ without __hash__ makes Type unhashable, so there is no "
          "eq/hash\n  inconsistency today; but a fix that adds union_members to __eq__ "
          "must not add a\n  __hash__ that forgets them.")
    print()

    print("end-to-end: same sources checked with the current __eq__ vs the "
          "process-local fixed __eq__")
    for label, src in SAMPLES.items():
        cur = errors(src)
        fix = errors(src, fixed_eq)
        delta = "" if cur == fix else "   <<< DIFFERS under fixed __eq__"
        print("  %-52s current=%s%s" % (label, cur or "NONE", delta))
        if cur != fix:
            unsound.append("end-to-end: " + label)
    print()

    print("sweep over shipped sources (%s/*.cypy) for __eq__-observable differences:"
          % os.path.relpath(os.path.join(REPO, "examples"), REPO))
    scanned, changed = 0, []
    for dirpath, _dirs, files in os.walk(os.path.join(REPO, "examples")):
        if scanned >= 20:
            break
        for fn in sorted(files):
            if not fn.endswith(".cypy"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                src = open(path, encoding="utf-8").read()
                parse(src)
            except Exception:                                       # noqa: BLE001
                continue
            scanned += 1
            cur, fix = errors(src), errors(src, fixed_eq)
            if cur != fix:
                changed.append(os.path.relpath(path, REPO))
            if scanned >= 20:
                break
    print("  %d file(s) scanned, %d change their diagnostics under the fixed __eq__%s"
          % (scanned, len(changed), (": " + str(changed[:5])) if changed else ""))

    print()
    print("root cause: :15-21 enumerates four comparison fields and omits "
          "self.union_members == other.union_members, while :2740/:2752 encode "
          "every union as Type('object', union_members=[...]) - the member list is "
          "the only thing that distinguishes unions, and it is ignored. __repr__ "
          "(:23-32) hides it too, which is why the sanity diagnostic above reads "
          "'expected object' for an Optional[int].")
    if unsound:
        print("VERDICT: REPRODUCED - %d unsound comparisons / effects: %s"
              % (len(unsound), unsound))
        return 1
    print("VERDICT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
