#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 06 -- declaration diagnostics and the
combination forms that the spec explicitly does NOT support.

Clauses: C-1.2 (member must be a type name), C-2.4 (cycle), C-2.5 (undefined member),
C-6 (multi-bound A + B / A & B / (A, B) are unsupported but must be diagnosed),
2.6.1 (the diagnostic must name the alternative).

Highest-value case: ``def f<T: (Numeric, Real)>(x: T)`` -- the parser eats the
parenthesised form into a Constant node today (measured), the fall-back branch at
type_checker.py:2508-2513 then stringifies it and the bound is effectively unchecked:
a silent-accept path, strictly worse than a crash.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

report = F.Report("PROBE feat_constraint_06", "SYNTAX/33 C-1.2, C-2.4, C-2.5, C-6, 2.6.1")

DECL = "constraint Numeric = int | float\nconstraint Real = int | float | double\n"
FNN = "def f<T: %s>(x: T) -> T:\n    return x\n\nprint(f(1))\n"


def expect_reject(rep, clause, label, source, needle, tag):
    res = F.transpile(tag, source)
    ok = (not res["success"]) and any(needle.lower() in e.lower() for e in res["errors"])
    rep.expect("%s %-52s (diagnostic must contain %r)" % (clause, label, needle),
               ok, F.error_summary(res))
    return res


def body(rep):
    rep.banner("constraint 06: bad declarations and unsupported bound combinations")

    # ---- controls: today's parser really does eat the tuple form ------------
    swallowed = F.parse(FNN % "(Numeric, Real)")
    rep.raw("parse('def f<T: (Numeric, Real)>') -> kinds / constraint node",
            "kinds=%s err=%s" % (F.top_kinds(FNN % "(Numeric, Real)"), swallowed[1]))
    # 下面两条都是「静默接受」的**现状取证**，C-6/裁决 D-3 的目标就是把它们反转成硬拒绝，
    # 因此不能当 control（修完即 exit 2 的自杀式前提）。结构性前提留给上面的 parse 原文。
    rep.note("pre-fix 形态：括号界 %s（2.6.1 要钉的静默吞）"
             % ("被静默解析" if swallowed[0] is not None else "已被拒绝"))

    plus = F.parse(FNN % "Numeric + Real")
    rep.raw("parse('def f<T: Numeric + Real>')", plus[1] or "parsed (unexpected)")
    amp = F.parse(FNN % "Numeric & Real")
    rep.raw("parse('def f<T: Numeric & Real>')", amp[1] or "parsed (unexpected)")
    # 同上：实现后 `+`/`&` 要么仍在 parse 期失败（带定向诊断），要么改由 analyzer 拒绝
    # （parse 成功但整体失败）——两种都是合规形态，所以这里只取证，不做 control。
    rep.note("pre-fix 形态：'+'/'&' 界在泛型参数循环里以词法错误死亡"
             "（plus_parsed=%s amp_parsed=%s，非语言诊断）"
             % (plus[0] is not None, amp[0] is not None))

    # ---- C-6: combination forms must be refused with a reason --------------
    for label, bound in (("T: A + B", "Numeric + Real"),
                         ("T: A & B", "Numeric & Real"),
                         ("T: (A, B)", "(Numeric, Real)")):
        res = F.transpile("c6_" + bound.replace(" ", "").replace("(", "").replace(")", ""),
                          DECL + FNN % bound)
        mentions_alt = any(("union" in e.lower() or "constraint" in e.lower()
                            or "not supported" in e.lower()) for e in res["errors"])
        rep.expect("C-6/2.6.1 %-10s rejected with a diagnostic naming an alternative" % label,
                   (not res["success"]) and mentions_alt, F.error_summary(res))

    # ---- C-1.3 independent bounds on different parameters still work -------
    two = F.transpile("c6_two",
                      DECL + "def f<T: Numeric, U: Real>(a: T, b: U) -> T:\n    return a\n\n"
                      "print(f(1, 2.0))\n")
    rep.expect("C-6 per-parameter independent bounds keep working",
               two["success"], F.error_summary(two))

    # ---- C-1.2 / C-2.5 member well-formedness ------------------------------
    expect_reject(rep, "C-2.5", "member that is not a declared type",
                  "constraint Bad = int | NotAThing\nprint(1)\n", "NotAThing", "c6_undef")
    expect_reject(rep, "C-1.2", "pointer member '*int'",
                  "constraint Bad = int | *int\nprint(1)\n", "constraint", "c6_ptr")
    expect_reject(rep, "C-1.1", "empty member list",
                  "constraint Bad =\nprint(1)\n", "constraint", "c6_empty")
    expect_reject(rep, "C-2.4", "self-recursive constraint",
                  "constraint Bad = int | Bad\nprint(1)\n", "circular", "c6_self")
    expect_reject(rep, "C-2.4", "two-constraint cycle",
                  "constraint A = B | int\nconstraint B = A | float\nprint(1)\n",
                  "circular", "c6_cycle")

    # ---- C-2.1 shadowing rule vs the duck registry (SYNTAX/27 division) ----
    duck_shadow = F.transpile("c6_duck",
                              "meta:\n    duck Numeric:\n        a + b -> Self\n\n"
                              "constraint Numeric = int | float\n"
                              "def f<T: Numeric>(x: T) -> T:\n    return x\n\n"
                              "print(f('ab'))\n")
    rep.raw("constraint name shadowing a duck constraint of the same name",
            F.error_summary(duck_shadow))
    rep.expect("2.6 nominal constraint wins over the same-named duck constraint "
               "(so a string argument must be rejected here)",
               not duck_shadow["success"]
               and any("Numeric" in e for e in duck_shadow["errors"]),
               F.error_summary(duck_shadow))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
