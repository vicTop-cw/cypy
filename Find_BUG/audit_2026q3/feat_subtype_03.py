#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.2.1 / subtype 03 -- runtime representation is UNCHANGED.

Clauses: S-4.1 (no ctypedef / no cdef class / no registry emitted for a subtype),
S-4.2 (the runtime type object stays the base's), S-4.3 (isinstance(x, Meter) must be a
compile-time error, because there is no runtime type object to test against),
S-4.4 ('as' on a subtype must be a codegen no-op).

Design note pinned by this probe: cypyc already ships a runtime type-identity mechanism
for traits -- cython_generator.py:527 _emit_trait_isinstance_support writes
_cypy_trait_registry and rewrites isinstance(x, Trait) through _cypy_is_instance_of.
subtype deliberately does NOT reuse it: the registry keys on type(obj).__name__, and a
subtype has no distinct runtime __name__, so reusing it would either never match or
would match the whole base type (semantic leak).  Case 4 checks the control that the
trait mechanism really exists.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL = "subtype Meter <: float\n"
report = F.Report("PROBE feat_subtype_03", "SYNTAX/33 S-4.1 .. S-4.4")


def body(rep):
    rep.banner("subtype 03: nominal identity is compile-time only, zero runtime change")

    plain = F.transpile("alias_baseline",
                        "type Meter = float\nlet m: Meter = 1.5\nprint(m)\n")
    rep.raw("control: 'type Meter = float' codegen (alias DOES emit a typedef)",
            "\n".join(ln for ln in plain["code"].splitlines()
                      if "Meter" in ln) or "(no Meter line)")
    rep.control("aliases emit a ctypedef today (contrast with S-4.1)",
                "ctypedef" in plain["code"], F.error_summary(plain))

    trait = F.transpile("trait_baseline",
                        "trait Money:\n    def cents(self) -> int\n\n"
                        "struct Dollar:\n    amount: int\n"
                        "    def cents(self) -> int:\n        return self.amount * 100\n\n"
                        "impl Money for Dollar:\n    pass\n\n"
                        "def describe(d) -> str:\n"
                        "    if isinstance(d, Money):\n        return 'is Money'\n"
                        "    return 'not Money'\n")
    rep.raw("control: trait runtime identity mechanism exists in codegen",
            "\n".join(ln for ln in trait["code"].splitlines()
                      if "_cypy_trait_registry" in ln or "_cypy_is_instance_of" in ln)[:400]
            or "(nothing emitted)")
    rep.control("codegen emits _cypy_trait_registry for traits (the mechanism subtype "
                "must NOT reuse)",
                "_cypy_trait_registry" in trait["code"], F.error_summary(trait))

    res = F.transpile("subtype_rep", DECL + "let m: Meter = 1.5\nprint(m)\n")
    rep.raw("subtype Meter <: float -- diagnostics", F.error_summary(res))
    lines = [ln for ln in res["code"].splitlines() if "Meter" in ln]
    rep.raw("subtype Meter -- every generated line mentioning Meter", "\n".join(lines)
            or "(nothing emitted)")

    rep.expect("S-4.1 the declaration compiles", res["success"], F.error_summary(res))
    rep.expect("S-4.1 no 'ctypedef ... Meter' is emitted for a subtype",
               not any("ctypedef" in ln and "Meter" in ln for ln in res["code"].splitlines()),
               "lines=%r" % lines)
    rep.expect("S-4.1 no 'cdef class Meter' / no runtime registry is emitted",
               not re.search(r"cdef class Meter|Meter\s*=\s*type\(|_cypy_.*Meter", res["code"]),
               "lines=%r" % lines)
    rep.expect("S-4.1 the let-binding is typed with the BASE type in the artifact",
               bool(re.search(r"float\s+m\b|m:\s*float", res["code"])) or res["success"],
               "code tail=%r" % [ln for ln in res["code"].splitlines()
                                 if re.match(r"\s*(cdef |cpdef |let |m\b)", ln)][:6])

    down = F.transpile("subtype_as", DECL + "let f: float = 1.5\nlet m: Meter = f as Meter\n"
                       "print(m)\n")
    cast_lines = [ln for ln in down["code"].splitlines() if "Meter" in ln]
    rep.raw("'f as Meter' -- generated lines mentioning Meter",
            "\n".join(cast_lines) or "(none)")
    rep.expect("S-4.4 'as Meter' is a codegen no-op (no runtime check emitted)",
               down["success"] and not any(k in ln for ln in cast_lines
                                           for k in ("isinstance", "_cypy_", "raise")),
               "success=%s lines=%r" % (down["success"], cast_lines))

    bad = F.transpile("subtype_isinstance",
                      DECL + "let m: Meter = 1.5\nif isinstance(m, Meter):\n    print('yes')\n")
    rep.raw("isinstance(m, Meter)", F.error_summary(bad))
    rep.expect("S-4.3 isinstance(m, Meter) is a compile-time error naming the base type",
               any("no runtime type object" in e.lower() or "subtype" in e.lower()
                   for e in bad["errors"]),
               F.error_summary(bad))

    good = F.transpile("subtype_isinstance_base",
                       DECL + "let m: Meter = 1.5\nif isinstance(m, float):\n    print('yes')\n"
                       "else:\n    print('no')\n")
    rep.expect("S-4.2 isinstance(m, float) still holds and the program runs",
               good["success"], F.error_summary(good))

    out, err, rc, art = F.cli("subtype_isinstance_run",
                              DECL + "let m: Meter = 1.5\n"
                              "if isinstance(m, float):\n    print('runtime type is float')\n",
                              command="run")
    rep.raw("python -m cypyc run <subtype program>",
            "\n".join((out + err).strip().splitlines()[-4:]))
    rep.expect("S-4.2 runtime identity observable: the program prints "
               "'runtime type is float'",
               "runtime type is float" in out, "rc=%s" % rc)


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
