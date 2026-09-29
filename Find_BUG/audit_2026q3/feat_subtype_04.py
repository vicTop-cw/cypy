#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.2.1 / subtype 04 -- chains, cycles, namespace, and the
class-inheritance boundary.

Clauses: S-1.3 (self reference / cycle), S-7.2 (chain depth cap), S-7.4 + C-3.1 (one
declaration namespace), S-6 (why 'class' is not a substitute: a class gets a runtime
type object, a subtype must not).

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

report = F.Report("PROBE feat_subtype_04", "SYNTAX/33 S-1.3, S-6, S-7.2, S-7.4, C-3.1")


def expect_reject(rep, clause, label, source, needles, tag):
    res = F.transpile(tag, source)
    ok = (not res["success"]) and any(any(n.lower() in e.lower() for n in needles)
                                       for e in res["errors"])
    rep.expect("%s %-54s needles=%s" % (clause, label, needles), ok, F.error_summary(res))


def body(rep):
    rep.banner("subtype 04: cycle/depth/namespace guards and the class boundary")

    # ---- control: class inheritance DOES create a runtime type object ------
    cls = F.transpile("class_runtime",
                      "class Base:\n    pass\n\nclass Derived(Base):\n    pass\n\n"
                      "let d: Derived = Derived()\nprint(isinstance(d, Base))\n")
    rep.raw("control: class/inheritance program", F.error_summary(cls))
    rep.control("class inheritance compiles today and produces a real isinstance pair",
                cls["success"], F.error_summary(cls))
    rep.control("... and codegen emits a cdef class for it (S-6's contrast)",
                "cdef class" in cls["code"] or "class Derived" in cls["code"],
                "artifact lines=%r" % [ln for ln in cls["code"].splitlines()
                                       if "class" in ln][:6])

    # ---- S-1.3 self reference / cycle --------------------------------------
    expect_reject(rep, "S-1.3", "self-referencing subtype",
                  "subtype X <: X\nprint(1)\n", ["circular", "self"], "s4_self")
    expect_reject(rep, "S-1.3", "two-node subtype cycle",
                  "subtype A <: B\nsubtype B <: A\nprint(1)\n", ["circular", "cycle"], "s4_cyc")

    # ---- S-7.1/S-7.2 chain works, then is capped ---------------------------
    nine = "".join("subtype S%d <: %s\n" % (i, "S%d" % (i - 1) if i else "float")
                   for i in range(1, 10))
    rep.raw("9-link chain corpus (must be refused by the depth cap)", nine.strip())
    expect_reject(rep, "S-7.2", "chain deeper than the documented limit 8",
                  nine + "print(1)\n", ["deep", "limit"], "s4_deep")

    three = ("subtype A1 <: B1\nsubtype B1 <: C1\nsubtype C1 <: float\n")
    chain_ok = F.transpile("s4_chain3",
                           three + "let a: A1 = 1.0\nlet f: float = a\nprint(f)\n")
    rep.expect("S-7.1 a 3-link chain upcasts implicitly", chain_ok["success"],
               F.error_summary(chain_ok))

    # ---- S-7.4 / C-3.1 one namespace ---------------------------------------
    expect_reject(rep, "S-7.4", "subtype name already used by a class",
                  "class Meter:\n    pass\n\nsubtype Meter <: float\nprint(1)\n",
                  ["redefinition", "already declared"], "s4_class")
    expect_reject(rep, "S-7.4", "subtype name already used by a type alias",
                  "type Meter = float\n\nsubtype Meter <: float\nprint(1)\n",
                  ["redefinition", "already declared"], "s4_alias")
    expect_reject(rep, "S-7.4", "duplicate subtype of the same name",
                  "subtype Meter <: float\nsubtype Meter <: int\nprint(1)\n",
                  ["redefinition", "already declared"], "s4_dup")

    # ---- S-1.2 base kinds: class/struct/enum allowed, trait/constraint not --
    ok_class = F.transpile("s4_base_class",
                           "class Money:\n    pass\n\nsubtype Coins <: Money\n"
                           "let c: Coins = Coins()\nprint(1)\n")
    rep.expect("S-1.2 a class may be a subtype base", ok_class["success"],
               F.error_summary(ok_class))
    expect_reject(rep, "S-1.2", "a trait may NOT be a subtype base",
                  "trait Show:\n    def show(self) -> str\n\nsubtype M <: Show\nprint(1)\n",
                  ["trait", "not allowed"], "s4_base_trait")
    expect_reject(rep, "S-1.2", "an object/Any base is refused (no information)",
                  "subtype M <: object\nprint(1)\n", ["object", "not allowed"], "s4_base_obj")

    # ---- S-4.3 consequence check: subtype must NOT create an isinstance pair
    pair = F.transpile("s4_isinstance_pair",
                       "class Base2:\n    pass\n\nsubtype Sub <: Base2\n"
                       "let s: Sub = Sub()\nprint(isinstance(s, Sub))\n")
    rep.raw("isinstance(value, <subtype name>) -- must be a compile-time error",
            F.error_summary(pair))
    rep.expect("S-4.3 isinstance(x, Sub) is refused (a subtype has no runtime type)",
               not pair["success"] and any("runtime" in e.lower() for e in pair["errors"]),
               F.error_summary(pair))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
