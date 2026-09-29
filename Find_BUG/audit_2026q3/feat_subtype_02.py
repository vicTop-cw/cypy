#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.2.1 / subtype 02 -- assignability direction (the point of the feature).

Clauses: S-3.1 (upcast implicit), S-3.2 (downcast needs 'as'), S-3.2.1 (missing 'as'
is an error), S-3.3 (sibling subtypes are never directly interchangeable), S-7.1
(chains), S-3.4 (why 'type X = base' is not a substitute).

Measured today: with the documented substitute `type Meter = int` BOTH directions
silently pass, because an alias is transparent to assignability -- i.e. the substitute
gives no nominality at all.  That baseline is pinned as a control below.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

PAIR = ("subtype Meter <: float\n"
        "subtype Kilometer <: float\n")
report = F.Report("PROBE feat_subtype_02", "SYNTAX/33 S-3.1, S-3.2, S-3.2.1, S-3.3, S-7.1")


def check(rep, clause, label, src, want_ok, want_sub=None):
    res = F.transpile(label, src)
    ok = res["success"] == want_ok
    if ok and want_ok is False and want_sub:
        ok = any(want_sub.lower() in e.lower() for e in res["errors"])
    rep.expect("%-10s %-46s" % (clause, label), ok, F.error_summary(res))
    return res


def body(rep):
    rep.banner("subtype 02: Meter->float implicit, float->Meter requires 'as'")

    # ---- control: the alias substitute gives no nominality at all -----------
    both_ways = F.transpile("alias_both_ways",
                            "type Meter = float\nlet m: Meter = 1.0\nlet v: float = m\n"
                            "let back: Meter = v\nprint(back)\n")
    rep.raw("'type Meter = float': assigning a plain float to a Meter variable",
            F.error_summary(both_ways))
    rep.control("the alias substitute lets float flow INTO Meter silently "
                "(why 'type' cannot stand in for 'subtype')",
                both_ways["success"], F.error_summary(both_ways))

    struct_one_way = F.transpile("struct_nominal",
                                 "struct Meter:\n    value: float\n\n"
                                 "let i: float = Meter(value=1.0)\nprint(i)\n")
    rep.control("a struct wrapper is nominal but has NO assignability to its field type",
                not struct_one_way["success"], F.error_summary(struct_one_way))

    # ---- upcast: implicit, must compile ------------------------------------
    up = check(rep, "S-3.1", "Meter value passed to a float parameter",
               PAIR + "def show(v: float) -> float:\n    return v\n\n"
               "let m: Meter = 2.5\nprint(show(m))\n", True)

    # ---- downcast: needs 'as' ----------------------------------------------
    check(rep, "S-3.2", "plain float assigned to Meter is rejected",
          PAIR + "let f: float = 1.0\nlet m: Meter = f\nprint(m)\n",
          False, want_sub="nominal")
    check(rep, "S-3.2.1", "the rejection names the required 'as' cast",
          PAIR + "let f: float = 1.0\nlet m: Meter = f\nprint(m)\n",
          False, want_sub="as Meter")
    check(rep, "S-3.2", "'x as Meter' is accepted",
          PAIR + "let f: float = 1.0\nlet m: Meter = f as Meter\nprint(m)\n", True)

    # ---- siblings -----------------------------------------------------------
    check(rep, "S-3.3", "sibling cast Meter->Kilometer rejected outright",
          PAIR + "let m: Meter = 1.0\nlet k: Kilometer = m as Kilometer\nprint(k)\n",
          False, want_sub="mutually")
    check(rep, "S-3.3", "explicit two-step through the base is allowed",
          PAIR + "let m: Meter = 1.0\nlet k: Kilometer = (m as float) as Kilometer\n"
          "print(k)\n", True)

    # ---- chains -------------------------------------------------------------
    chain = ("subtype A <: B\nsubtype B <: float\n")
    check(rep, "S-7.1", "chain A<:B<:float upcasts implicitly",
          chain + "let a: A = 1.0\nlet b: B = a\nlet f: float = b\nprint(f)\n", True)
    check(rep, "S-7.1", "chain downcast needs 'as'",
          chain + "let f: float = 1.0\nlet a: A = f\nprint(a)\n",
          False, want_sub="as A")

    # ---- S-2.3: constraint interaction -------------------------------------
    check(rep, "S-2.3", "a Meter satisfies a constraint whose member is the base",
          "constraint F = float\nsubtype Meter <: float\n"
          "def keep<T: F>(v: T) -> T:\n    return v\n\n"
          "let m: Meter = 1.0\nprint(keep(m))\n", True)
    check(rep, "S-2.3", "a float does NOT satisfy a constraint listing only Meter",
          "constraint M = Meter\nsubtype Meter <: float\n"
          "def keep<T: M>(v: T) -> T:\n    return v\n\n"
          "let f: float = 1.0\nprint(keep(f))\n", False)

    out, err, rc, artifact = F.cli("subtype_run",
                                   PAIR + "def show(v: float) -> float:\n    return v + 1.0\n\n"
                                   "let m: Meter = 2.5\nprint(show(m))\n", command="run")
    rep.raw("python -m cypyc run <upcast program>", "\n".join((out + err).strip().splitlines()[-4:]))
    rep.expect("S-3.1 end-to-end: upcast program compiles, runs and prints 3.5",
               "3.5" in out, "rc=%s" % rc)


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
