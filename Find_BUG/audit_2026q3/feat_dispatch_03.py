#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.3.1 / dispatch 03 -- specialisation precedence and ambiguity
must be decided at COMPILE time.

Clauses: P-3 (most specific wins), P-4 (ambiguity is a hard error), P-4b (an arm that is
a non-descendant of the header parameter type is rejected).
**DEFERRED cluster**: the shapes below are the acceptance set for the next round.

Why this cannot be cheap: cypyc has no overload set today.  Two `def f` with different
parameter types are refused by scope_analyzer.py:132-142 _check_redefinition
('Name 'f' is already declared in this scope'), and the analyzer keeps one FuncDef per
name in type_checker.py:102 func_defs (written at :342).  A dispatch table needs a
many-to-one signature registry plus the most-specific/ambiguity algorithm on top of it.
Case 4 records exactly that blocker.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

HEADER = ("class Shape:\n    pass\n\nclass Circle(Shape):\n    r: float\n\n"
          "class Square(Shape):\n    a: float\n\n")
report = F.Report("PROBE feat_dispatch_03", "SYNTAX/33 P-3, P-4, P-4b (DEFERRED cluster)")


def body(rep):
    rep.banner("dispatch 03: most-specific-wins + compile-time ambiguity rejection")

    dup = F.transpile("dup_def", "def f(x: int) -> int:\n    return 1\n\n"
                      "def f(x: str) -> int:\n    return 2\n\nprint(f(1))\n")
    rep.raw("control: two same-named 'def' (no dispatch at all today)",
            F.error_summary(dup))
    rep.control("cypyc refuses same-name functions today (P-1' cost evidence)",
                not dup["success"] and any("already declared" in e for e in dup["errors"]),
                F.error_summary(dup))

    # P-3: specific arm wins over the general one
    spec = F.transpile("d3_spec", HEADER +
                       "dispatch describe(s: Shape) -> str:\n"
                       "    arm Circle:\n        return 'circle'\n"
                       "    arm Shape:\n        return 'shape'\n"
                       "\nprint(describe(Circle()))\n")
    rep.raw("P-3 specialised-arm program", F.error_summary(spec))
    out, err, rc, art = F.cli("d3_spec_run", HEADER +
                              "dispatch describe(s: Shape) -> str:\n"
                              "    arm Circle:\n        return 'circle'\n"
                              "    arm Shape:\n        return 'shape'\n"
                              "\nprint(describe(Circle()))\n", command="run")
    rep.raw("python -m cypyc run <P-3 program>",
            "\n".join((out + "\n" + err).strip().splitlines()[-4:]))
    rep.expect("P-3 the Circle arm beats the Shape arm ('circle' is printed)",
               "circle" in out, "rc=%s" % rc)

    # P-4: two equally specific sibling arms -> compile-time error
    ambig = F.transpile("d3_ambig", HEADER +
                        "class Left(Shape):\n    pass\n\nclass Right(Shape):\n    pass\n\n"
                        "dispatch g(s: Shape) -> str:\n"
                        "    arm Left:\n        return 'L'\n"
                        "    arm Right:\n        return 'R'\n"
                        "    arm Shape:\n        return 'S'\n"
                        "\nlet x = g(Left())\n")
    rep.raw("P-4 sibling arms (Left/Right are unrelated)", F.error_summary(ambig))
    rep.expect("P-4 sibling arms for a SINGLE call are not themselves ambiguous "
               "(each is chosen only when its own type arrives)",
               ambig["success"], F.error_summary(ambig))

    overlap = F.transpile("d3_overlap", HEADER +
                          "class Left(Shape):\n    pass\n\nclass Right(Shape):\n    pass\n\n"
                          "class Both(Left, Right):\n    pass\n\n"
                          "dispatch g(s: Shape) -> str:\n"
                          "    arm Left:\n        return 'L'\n"
                          "    arm Right:\n        return 'R'\n"
                          "\nprint(1)\n")
    rep.raw("P-4 genuinely ambiguous diamond (Both <: Left and Right)",
            F.error_summary(overlap))
    rep.expect("P-4 an ambiguous arm set is a compile-time error naming both arms",
               not overlap["success"]
               and any(("ambiguous" in e.lower()) for e in overlap["errors"]),
               F.error_summary(overlap))

    # P-4b: an arm that is not a descendant of the header parameter type
    bad_arm = F.transpile("d3_badarm", HEADER +
                          "struct NotAShape:\n    v: int\n\n"
                          "dispatch g(s: Shape) -> str:\n"
                          "    arm NotAShape:\n        return 'x'\n"
                          "    arm Shape:\n        return 'S'\n"
                          "\nprint(1)\n")
    rep.expect("P-4b a non-descendant arm is rejected with a naming diagnostic",
               not bad_arm["success"]
               and any(("not a subtype" in e.lower()) or ("descendant" in e.lower())
                       or ("unreachable" in e.lower()) for e in bad_arm["errors"]),
               F.error_summary(bad_arm))

    # no-fallback (P-4b tail): arms cover only subclasses, header accepts any Shape
    nofb = F.transpile("d3_nofb", HEADER +
                       "dispatch g(s: Shape) -> str:\n"
                       "    arm Circle:\n        return 'C'\n"
                       "    arm Square:\n        return 'S'\n"
                       "\nprint(1)\n")
    rep.expect("P-4b a dispatch header without a fallback arm is rejected at declaration time",
               not nofb["success"] and any(("fallback" in e.lower())
                                           or ("not exhaustive" in e.lower())
                                           or ("no arm" in e.lower())
                                           for e in nofb["errors"]),
               F.error_summary(nofb))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
