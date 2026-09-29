#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 05 -- the satisfaction relation, case by case.

Clause: C-2.2 (and the table under it), 2.2.1.

The relation is written as:  A satisfies N  <=>  exists m in members(N): _is_subtype(A, m)
i.e. it MUST reuse cypyc/analyzer/type_checker.py:1985 _is_subtype.  Today
_check_generic_constraint's fall-back branch (:2550-2559) compares bare strings
(`inferred_type.name in constraint_names`), which is why rows 2/3/5 below disagree with
the rest of the compiler.  Those rows are probed through an INLINE union bound
(`T: int`, `T: A`, `T: list<int>`), which works today and needs no new syntax --
so this probe measures the *semantics*, not the surface, and stays valid before and
after the `constraint` keyword lands.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

report = F.Report("PROBE feat_constraint_05", "SYNTAX/33 C-2.2 table, 2.2.1")

CASES = [
    # (clause, label, bound, argument literal/expr, expected_satisfies, extra decl)
    ("C-2.2", "int vs member int",                    "int",        "1",       True,  ""),
    ("C-2.2", "str vs member int",                    "int",        "'a'",     False, ""),
    ("C-2.2", "bool vs member int (numeric widening)", "int",       "True",    True,  ""),
    ("C-2.2", "float vs member int (no narrowing)",   "int",        "1.5",     False, ""),
    ("C-2.2", "int vs member float (widening up)",    "float",      "1",       True,  ""),
    ("C-2.2", "list[int] vs member list",             "list",       "[1, 2]",  True,  ""),
    ("C-2.2", "list[int] vs member list<int>",        "list<int>",  "[1, 2]",  True,  ""),
    ("C-2.2", "list[str] vs member list<int>",        "list<int>",  "['a']",   True,  ""),   # 2.2.1: element type NOT checked
    ("C-2.2", "dict vs member list",                  "list",       "{1: 2}",  False, ""),
    ("C-2.2", "None vs member int | None",            "int | None", "None",    True,  ""),
    ("C-2.2", "class member itself",                  "Pet",        "Pet()",   True,  "class Pet:\n    pass\n\n"),
    ("C-2.2", "subclass satisfies class member",      "Pet",        "Dog()",   True,
     "class Pet:\n    pass\n\nclass Dog(Pet):\n    pass\n\n"),
    ("C-2.2", "unrelated class does not satisfy",     "Pet",        "Rock()",  False,
     "class Pet:\n    pass\n\nclass Rock:\n    pass\n\n"),
    ("C-2.2", "int does not satisfy class member",    "Pet",        "3",       False,
     "class Pet:\n    pass\n\n"),
]


def program(bound, arg, decl=""):
    return (decl
            + "def keep<T: %s>(v: T) -> T:\n    return v\n\n" % bound
            + "print(keep(%s))\n" % arg)


def body(rep):
    rep.banner("constraint 05: satisfaction must go through _is_subtype, not string compare")

    tc_src = ("def keep<T: int>(v: T) -> T:\n    return v\n\n"
              "let x: int = 1\nprint(keep(x))\n")
    ctrl = F.transpile("ctrl_exact", tc_src)
    rep.control("exact-name match path works today (int vs member int)",
                ctrl["success"], F.error_summary(ctrl))
    widening = F.transpile("ctrl_assign", "let x: int = True\nprint(x)\n")
    rep.control("the ASSIGNMENT path already widens bool -> int via _is_subtype "
                "(the inconsistency C-2.2 removes)", widening["success"],
                F.error_summary(widening))

    for idx, (clause, label, bound, arg, want, decl) in enumerate(CASES):
        res = F.transpile("sat_%d" % idx, program(bound, arg, decl))
        got = res["success"]
        rep.expect("%s %-42s arg %-8s -> satisfies=%-5s" % (clause, label, arg, want),
                   got == want, F.error_summary(res))

    # and the same partition expressed through a NAMED constraint (C-4.1 synonymy)
    named = F.transpile("named_bool",
                        "constraint N = int\n"
                        "def keep<T: N>(v: T) -> T:\n    return v\n\nprint(keep(True))\n")
    rep.raw("named form: constraint N = int ; keep(True)", F.error_summary(named))
    rep.expect("C-4.1 named constraint gives the same verdict as 'T: int' for bool",
               named["success"], F.error_summary(named))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
