#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 03 -- constraint vs type-alias division.

Clauses: C-2.1 (a constraint name is NOT a type and must be rejected in value
position), C-3.1/C-3.2 (one declaration namespace for type/subtype/constraint).

Measured today: the only thing standing between `constraint X = ...` and a *runtime*
assignment is the accidental `Undefined name 'constraint'` diagnostic; and cypyc has no
redefinition guard for type-level names at all -- two `type N = ...` in one module are
both accepted (cypyc/analyzer/scope_analyzer.py:54 _user_def_kinds omits 'type').

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL = "constraint Numeric = int | float\n"
report = F.Report("PROBE feat_constraint_03", "SYNTAX/33 C-2.1, C-3.1, C-3.2")


def body(rep):
    rep.banner("constraint 03: a constraint is a bound, not a type; one namespace")

    # ---------- controls: what cypyc does today ------------------------------
    dup_alias = F.transpile("dup_alias", "type N = int\n\ntype N = str\n\nprint(1)\n")
    rep.raw("two 'type N = ...' in one module", F.error_summary(dup_alias))
    # B9 现状取证：`_user_def_kinds`（scope_analyzer.py:54）不含 'type' 时它静默通过。
    # C-3.1/裁决 D-1 落地的**正是要把它变成拒绝**，所以这条不能当 control（否则修完必 exit 2）。
    rep.note("pre-fix 形态：重复 type 别名 %s（B9；C-3.1 要反转的正是这个结论）"
             % ("静默通过" if dup_alias["success"] else "已被拒绝（说明 C-3.1 已落地）"))

    let_alias = F.transpile("let_alias", "type N = int | float\n\nlet x: N = 1\nprint(x)\n")
    rep.control("a type ALIAS is usable in value position (that is its purpose)",
                let_alias["success"], F.error_summary(let_alias))

    # ---------- C-2.1: constraint name in value position ---------------------
    for label, src in (
            ("let x: Numeric = 1", DECL + "\nlet x: Numeric = 1\nprint(x)\n"),
            ("def f(v: Numeric) -> int", DECL + "\ndef f(v: Numeric) -> int:\n    return 1\nprint(f(1))\n"),
            ("as Numeric", DECL + "\nlet y = 1 as Numeric\nprint(y)\n"),
            ("list<Numeric>", DECL + "\nlet z: list<Numeric> = [1]\nprint(z)\n"),
    ):
        res = F.transpile("valpos_" + label.split()[0], src)
        ok = (not res["success"]) and any("Numeric" in e and "constraint" in e.lower()
                                          for e in res["errors"])
        rep.expect("C-2.1 %-24s rejected, naming it as a constraint" % label, ok,
                   F.error_summary(res))

    # ---------- C-3.1: same name for alias and constraint --------------------
    clash = F.transpile("clash", DECL + "\ntype Numeric = int | float\nprint(1)\n")
    rep.raw("constraint Numeric = ... then type Numeric = ...", F.error_summary(clash))
    rep.expect("C-3.1 constraint-then-alias under one name is a redefinition error",
               not clash["success"] and any("redefinition" in e or "already declared" in e
                                            for e in clash["errors"]),
               F.error_summary(clash))

    clash2 = F.transpile("clash2", "type Numeric = int | float\n\n" + DECL + "print(1)\n")
    rep.expect("C-3.1 alias-then-constraint under one name is also rejected "
               "(the second declaration loses)",
               not clash2["success"] and any("redefinition" in e or "already declared" in e
                                             for e in clash2["errors"]),
               F.error_summary(clash2))

    clash3 = F.transpile("clash3", DECL + "\n" + DECL + "print(1)\n")
    rep.expect("C-3.1 duplicate 'constraint Numeric' twice is a redefinition error",
               not clash3["success"] and any("redefinition" in e or "already declared" in e
                                             for e in clash3["errors"]),
               F.error_summary(clash3))

    # ---------- C-3.2: distinct names, both kinds, no interference -----------
    both = F.transpile("both",
                       "type Numeric = int | float\n"
                       "constraint Small = int | float\n"
                       "def pick<T: Small>(a: T, b: T) -> T:\n    return a\n\n"
                       "let v: Numeric = 2\nprint(v)\nprint(pick(1, 2))\n")
    rep.raw("type Numeric + constraint Small (different names) used both ways",
            F.error_summary(both))
    rep.expect("C-3.2 alias and constraint may coexist under different names",
               both["success"], F.error_summary(both))

    # ---------- C-3.1 (D-1 pending): duplicate alias must also be caught -----
    rep.expect("C-3.1/D-1 duplicate 'type N' becomes a redefinition error "
               "(same namespace, no silent overwrite)",
               not dup_alias["success"], F.error_summary(dup_alias))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
