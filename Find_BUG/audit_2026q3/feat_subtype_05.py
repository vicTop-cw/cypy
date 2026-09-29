#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.2.1 / subtype 05 -- the trait / impl / duck boundary.

Clauses: S-5.1 ('impl Trait for <subtype>' is refused in v1), S-5.2 (trait bounds do not
pick a subtype up for free), S-5.3 (duck constraints are structural, so a subtype MUST
satisfy whatever its base satisfies).

S-5.1 is not taste, it is forced by the existing runtime: trait identity is resolved by
cython_generator.py:527 _emit_trait_isinstance_support, which keys on
type(obj).__name__ (see :550).  A subtype has no distinct runtime __name__ (S-4.2), so
registering 'Meter' would never match, while registering its base 'float' would make
every float look like it implements the trait.  Case 1 pins that mechanism as a control.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

report = F.Report("PROBE feat_subtype_05", "SYNTAX/33 S-5.1, S-5.2, S-5.3")

TRAIT = ("trait Show:\n    def show(self) -> str\n\n"
         "struct Dollar:\n    amount: int\n\n"
         "impl Show for Dollar:\n    pass\n\n")
DUCK = ("meta:\n    duck Numeric:\n        a + b -> Self\n\n")


def body(rep):
    rep.banner("subtype 05: what a subtype may and may not inherit from trait/duck")

    # ---- control: the trait runtime mechanism the spec leans on -------------
    base = F.transpile("trait_base", TRAIT + "def f(x) -> str:\n"
                       "    if isinstance(x, Show):\n        return 'yes'\n"
                       "    return 'no'\nprint(f(Dollar()))\n")
    rep.raw("control: trait + impl + runtime identity (exists today)",
            F.error_summary(base))
    rep.control("impl/trait/runtime registry all work today", base["success"]
                and "_cypy_trait_registry" in base["code"], F.error_summary(base))
    rep.control("the registry keys on type(obj).__name__ (the reason S-5.1 refuses "
                "impl-on-subtype)",
                "type(obj).__name__" in base["code"], "")

    # ---- S-5.2: trait bound does not accept a subtype for free --------------
    sub_only = F.transpile("s5_bound",
                           TRAIT + "subtype Cent <: int\n"
                           "def render<T: Show>(v: T) -> str:\n    return 'x'\n\n"
                           "let c: Cent = 5\nprint(render(c))\n")
    rep.expect("S-5.2 a subtype does not satisfy its base's trait bound automatically",
               not sub_only["success"] and any("Show" in e for e in sub_only["errors"]),
               F.error_summary(sub_only))

    # ---- S-5.3: duck constraints are structural -> must be inherited --------
    duck_base = F.transpile("s5_duck_int",
                            DUCK + "def add<T: Numeric>(a: T, b: T) -> T:\n    return a\n\n"
                            "print(add(1, 2))\n")
    rep.raw("control: int satisfies 'duck Numeric' today (structural path works)",
            F.error_summary(duck_base))
    rep.control("control: the duck registry really is emitted today "
                "(so S-5.3 has a mechanism to inherit from)",
                duck_base["success"] and "_duck_registry" in duck_base["code"],
                F.error_summary(duck_base))

    duck_sub = F.transpile("s5_duck_subtype",
                           DUCK + "subtype Cents <: int\n"
                           "def add<T: Numeric>(a: T, b: T) -> T:\n    return a\n\n"
                           "let x: Cents = 1\nprint(add(x, x))\n")
    rep.raw("duck bound applied to a subtype value", F.error_summary(duck_sub))
    rep.expect("S-5.3 a subtype satisfies every duck constraint its base satisfies",
               duck_sub["success"], F.error_summary(duck_sub))

    # ---- S-5.1: impl on a subtype is refused --------------------------------
    impl_on_sub = F.transpile("s5_impl",
                              TRAIT + "subtype Cent <: Dollar\n"
                              "impl Show for Cent:\n    pass\n\nprint(1)\n")
    rep.raw("impl Show for Cent  (Cent <: Dollar)", F.error_summary(impl_on_sub))
    rep.expect("S-5.1 'impl Show for <subtype>' is refused with a runtime-identity reason",
               not impl_on_sub["success"]
               and any(("runtime" in e.lower()) or ("no runtime identity" in e.lower())
                       for e in impl_on_sub["errors"]),
               F.error_summary(impl_on_sub))

    # ---- S-5.4: a subtype of a builtin may not impl a trait at all ----------
    impl_builtin = F.transpile("s5_impl_builtin",
                               TRAIT + "subtype Cent <: int\nimpl Show for Cent:\n    pass\n\n"
                               "print(1)\n")
    rep.expect("S-5.1 same refusal on an int-based subtype",
               not impl_builtin["success"] and any("runtime" in e.lower()
                                                   for e in impl_builtin["errors"]),
               F.error_summary(impl_builtin))

    # ---- end-to-end: the refused program must not produce an artifact -------
    out, err, rc, artifact = F.cli("s5_cli", TRAIT + "subtype Cent <: Dollar\n"
                                   "impl Show for Cent:\n    pass\n\nprint(1)\n")
    rep.raw("python -m cypyc transpile <impl-on-subtype>", (out + err).strip()[-400:])
    rep.expect("S-5.1 refusal happens at compile time: no .pyx artifact",
               not artifact, "artifact=%s rc=%s" % (artifact, rc))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
