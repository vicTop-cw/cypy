#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 04 -- violation diagnostic template.

Clause: C-5 (exact diagnostic shape), C-5.1 (real position, never 'at 0:0'),
C-5.2 (member list expanded), C-5.3 (the *inferred* argument type, not object),
C-5.4 (keeps the greppable 'does not satisfy constraint' substring), C-5.5 (one
diagnostic per call site).

Current wording (already greppable, but position-less and members-only-for-inline):
    Generic constraint violation: type 'str' does not satisfy constraint 'int | float'
    for parameter 'T' at 0:0
The 'at 0:0' is produced by cypyc/analyzer/type_checker.py:2456-2457 -- the call node
carries no line/col on that path -- so IDE jump and incremental reporting both fail.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL = "constraint Numeric = int | float\n"
PROGRAM = (DECL + "\n"
           "def clamp<T: Numeric>(v: T) -> T:\n"
           "    return v\n"
           "\n"
           "let bad_value = 'oops'\n"
           "print(clamp(bad_value))\n")

# C-5 template, per field.  Anchored loosely enough to allow the 'Generic' prefix the
# spec keeps for grep compatibility (C-5.4), strict enough to reject today's message.
TEMPLATE = re.compile(
    r"constraint violation:.*type 'str' does not satisfy constraint 'Numeric'"
    r".*allowed: int \| float", re.I | re.S)
POSITION = re.compile(r"at \S*[\w.]+\.cypy:(\d+):(\d+)|(?:at )(\d+):(\d+)")

report = F.Report("PROBE feat_constraint_04", "SYNTAX/33 C-5.1 .. C-5.5")


def first_error(res):
    return res["errors"][0] if res["errors"] else "(no diagnostic)"


def body(rep):
    rep.banner("constraint 04: violation diagnostic carries members + real position")

    inline = F.transpile("inline_pos",
                         "def clamp<T: int | float>(v: T) -> T:\n    return v\n\n"
                         "let bad_value = 'oops'\nprint(clamp(bad_value))\n")
    rep.raw("today (inline bound, no constraint declaration)", F.error_summary(inline))
    rep.control("the negative path already produces a diagnostic at all",
                not inline["success"] and bool(inline["errors"]), F.error_summary(inline))
    # C-5.1 要消灭的就是 `at 0:0`（内联界与命名界同义，见 C-4.1），所以「今天没有位置」
    # 是**待反转的缺陷**而不是前提 —— 记成 note，否则修完 self-kill 成 exit 2。
    rep.note("pre-fix 形态：内联界的诊断 %s（C-5.1 要转正的方向）"
             % ("带 'at 0:0'（无可定位位置）"
                if any("at 0:0" in e for e in inline["errors"])
                else "已带真实位置"))

    res = F.transpile("named_pos", PROGRAM)
    rep.raw("specified behaviour target (named constraint, violation on line 7)",
            F.error_summary(res))
    msg = first_error(res)

    rep.expect("C-5 message matches the constraint-violation template",
               bool(TEMPLATE.search(" ".join(res["errors"]))), "first=%r" % msg)
    rep.expect("C-5.4 keeps the greppable substring 'does not satisfy constraint'",
               any("does not satisfy constraint" in e for e in res["errors"]),
               "first=%r" % msg)
    rep.expect("C-5.1 position is a real line:col (never 'at 0:0')",
               bool(res["errors"]) and not any("at 0:0" in e for e in res["errors"]),
               "first=%r" % msg)
    rep.expect("C-5.1 reported line is the call site (line 7 of the probe corpus)",
               any(re.search(r":7\b|at \d+:7\b|line 7", e) for e in res["errors"]),
               "first=%r" % msg)
    rep.expect("C-5.2 members of the constraint are expanded (int | float)",
               any(("int" in e and "float" in e) for e in res["errors"]),
               "first=%r" % msg)
    rep.expect("C-5.2 the constraint NAME appears (not only the flattened union)",
               any("Numeric" in e for e in res["errors"]), "first=%r" % msg)
    rep.expect("C-5.3 the inferred argument type 'str' is named",
               any("'str'" in e for e in res["errors"]), "first=%r" % msg)
    rep.expect("C-5.5 exactly one diagnostic for the single violating call site "
               "(excluding unrelated messages)",
               len([e for e in res["errors"] if "onstraint" in e]) == 1,
               "count=%d errors=%r" % (len(res["errors"]), res["errors"]))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
