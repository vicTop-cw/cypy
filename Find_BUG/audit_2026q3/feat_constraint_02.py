#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 02 -- named bound is a real bound.

Clauses: C-2.2 (satisfaction), C-2.3 (transitive member union), C-4.1 (naming an
inline union must be synonymous with writing it inline), C-4.4 (violation is a
compile-time error, never a silent downgrade to object).

Why the substitute documented in SYNTAX_IMPLEMENTATION_STATUS.md:91 does not work:
``type Numeric = int | float`` used as ``def f<T: Numeric>`` is rejected for *every*
argument, including int -- cypyc/analyzer/type_checker.py:2550-2559 compares the raw
type name against the single constraint token 'Numeric' and never resolves the alias.
Case 4 below pins that as measured current behaviour.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL = "constraint Numeric = int | float\n"
CALL = "def clamp<T: Numeric>(v: T) -> T:\n    return v\n\nprint(clamp(%s))\n"
INLINE = ("def clamp<T: int | float>(v: T) -> T:\n    return v\n\nprint(clamp(%s))\n")

report = F.Report("PROBE feat_constraint_02",
                  "SYNTAX/33 C-2.2, C-2.3, C-4.1, C-4.4")


def named(src, tag):
    res = F.transpile(tag, DECL + src)
    return res


def body(rep):
    rep.banner("constraint 02: 'T: Name' accepts members, rejects non-members")

    ok_int = F.transpile("inline_int_ok", INLINE % "1")
    ok_float = F.transpile("inline_float_ok", INLINE % "1.5")
    bad_str = F.transpile("inline_str_bad", INLINE % "'a'")
    rep.raw("baseline: inline bound 'T: int | float' with clamp('a')",
            F.error_summary(bad_str))
    rep.control("inline union bound already accepts int", ok_int["success"],
                F.error_summary(ok_int))
    rep.control("inline union bound already accepts float", ok_float["success"],
                F.error_summary(ok_float))
    rep.control("inline union bound already rejects str (negative path exists)",
                not bad_str["success"]
                and any("constraint violation" in e for e in bad_str["errors"]),
                F.error_summary(bad_str))

    alias = F.transpile("alias_substitute", "type Numeric = int | float\n" + CALL % "1")
    rep.raw("current substitute 'type Numeric = int | float' used as bound T: Numeric, "
            "called clamp(1)", F.error_summary(alias))
    # 「别名当界今天被拒」是**本探针的动机取证**，不是前提：C-2.2 把判定收敛到唯一的
    # `_is_subtype` 入口后，这条路可能顺时被修好（INV-2 的副作用），当 control 会自我处决。
    rep.note("pre-fix 形态：别名当界 %s（B2；探针因它而存在，但允许被 INV-2 顺带修掉）"
             % ("被拒绝" if not alias["success"] else "已可通过"))

    r_int = named(CALL % "1", "named_int")
    r_float = named(CALL % "1.5", "named_float")
    r_str = named(CALL % "'a'", "named_str")
    rep.raw("constraint Numeric = int | float ; clamp(1)", F.error_summary(r_int))
    rep.raw("... ; clamp(1.5)", F.error_summary(r_float))
    rep.raw("... ; clamp('a')", F.error_summary(r_str))

    rep.expect("C-2.2 clamp(1) against 'T: Numeric' compiles", r_int["success"],
               F.error_summary(r_int))
    rep.expect("C-2.2 clamp(1.5) against 'T: Numeric' compiles", r_float["success"],
               F.error_summary(r_float))
    rep.expect("C-4.4 clamp('a') against 'T: Numeric' fails at compile time",
               not r_str["success"], F.error_summary(r_str))
    rep.expect("C-4.1 the failure names the offending argument type 'str'",
               any("str" in e for e in r_str["errors"]), F.error_summary(r_str))
    rep.expect("C-4.1 naming the constraint is synonymous with the inline union "
               "(same accept/reject partition)",
               (r_int["success"] == ok_int["success"]
                and r_float["success"] == ok_float["success"]
                and r_str["success"] == bad_str["success"] == False),
               "named=%s/%s/%s inline=%s/%s/%s" % (
                   r_int["success"], r_float["success"], r_str["success"],
                   ok_int["success"], ok_float["success"], bad_str["success"]))

    # C-2.3 transitive member union: `constraint Numeric = int | float` +
    # `constraint Small = Numeric | str`  ==>  Small 的成员摊平成 int|float|str。
    # 夹具必须先声明 Numeric：漏掉 DECL 时先撞的是 C-2.5「成员必须是本模块已定义的名字」，
    # 探针就在测「未定义成员被拒」（那是 06 的范围），C-2.3 从来没被观察到 —— 实测改前
    # 三条 transpile 全部报 `references undefined type 'Numeric' ... at 1:20`。
    union_src = (DECL + "constraint Small = Numeric | str\n"
                 + CALL.replace("Numeric", "Small"))
    u_int = F.transpile("union_int", union_src % "1")
    u_float = F.transpile("union_float", union_src % "1.5")
    u_str = F.transpile("union_str", union_src % "'a'")
    u_list = F.transpile("union_list", union_src % "[1, 2]")
    rep.raw("constraint Small = Numeric | str ; clamp(1) / clamp(1.5) / clamp('a') / clamp([1, 2])",
            "%s || %s || %s || %s" % (F.error_summary(u_int), F.error_summary(u_float),
                                      F.error_summary(u_str), F.error_summary(u_list)))
    rep.expect("C-2.3 nested constraint members are flattened (int/float/str all pass)",
               u_int["success"] and u_float["success"] and u_str["success"],
               "int=%s float=%s str=%s :: %s" % (
                   u_int["success"], u_float["success"], u_str["success"],
                   F.error_summary(u_str)))
    # 上面三条全绿只有在界仍然是「界」时才算数：摊平若把 Small 摊成来者不拒，
    # list 也会通过 —— 这条负例钉住「摊平不放宽」。
    rep.expect("C-2.3 flattening still binds: a non-member (list) is rejected",
               not u_list["success"]
               and any("constraint violation" in e for e in u_list["errors"]),
               F.error_summary(u_list))

    # the end-to-end call-site requirement: produced artifact + observable output
    out_cli, err_cli, rc, artifact = F.cli("named_call",
                                           DECL + CALL % "1", command="run")
    rep.raw("python -m cypyc run <named-bound program> (stdout tail)",
            "\n".join(out_cli.strip().splitlines()[-4:]))
    rep.expect("unit-2 acceptance must reach the call site: program runs and prints 1",
               "1" in out_cli and "Execution successful" in out_cli,
               "rc=%s stderr=%s" % (rc, err_cli.strip()[:120]))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
