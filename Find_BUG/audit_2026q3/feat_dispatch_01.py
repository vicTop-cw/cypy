#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.3.1 / dispatch 01 -- declaration form and the silent-swallow
shape.  **FEATURE IS DEFERRED** (SYNTAX/33 section 4 is a proposal, not a norm); this
probe exists so the next round has a red line to turn green and so the current
silent-accept hazard is on record.

Clauses: P-1 (dispatch block), C-7.1 (reserved word), plus the "must specifically probe
silent swallowing" requirement of the task pack.

Measured today:
  dispatch name(x: int) -> int   -> parser dies with "Expected RPAREN, got COLON at 1:16"
  dispatch name(x)               -> TWO harmless-looking ExprStmt (Name + Call): the
                                    declaration is eaten as an expression statement
                                    followed by a function call.
  def dispatch(...) / dispatch = 7 -> accepted: 'dispatch' is not a keyword
                                     (cypyc/parser/lexer.py:160-223 KEYWORDS).

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

BLOCK = ("dispatch area(x: Shape) -> float:\n"
         "    arm Circle:\n        return 3.14 * x.r * x.r\n"
         "    arm Square:\n        return x.a * x.a\n")
report = F.Report("PROBE feat_dispatch_01", "SYNTAX/33 P-1, C-7.1 (DEFERRED cluster)")


def body(rep):
    rep.banner("dispatch 01: 'dispatch' must be a declaration, never a swallowed call")

    # ---- verbatim current behaviour ----------------------------------------
    for label, src in (
            ("dispatch area(x: int) -> int", "dispatch area(x: int) -> int\nprint(1)\n"),
            ("dispatch area(x)", "dispatch area(x)\nprint(1)\n"),
            ("def dispatch(x: int)", "def dispatch(x: int) -> int:\n    return x\nprint(dispatch(2))\n"),
            ("dispatch = 7", "dispatch = 7\nprint(dispatch)\n"),
    ):
        mod, err = F.parse(src)
        rep.raw("parse(%r)" % label, err or ("kinds=%s" % [s.kind for s in mod.body]))

    out, err, rc, artifact = F.cli("dispatch_head", BLOCK + "print(1)\n")
    rep.raw("python -m cypyc transpile <dispatch block>", (out + "\n" + err).strip()[-350:])

    # ---- controls -----------------------------------------------------------
    # 这两条是**现状取证**而不是前提：R3 实现 dispatch 时它们必然反转（关键字化 + 不再被吞）。
    # 留成 control 会让那轮修好后探针 self-kill 成 exit 2 —— 同 R2 已在 constraint/subtype
    # 探针上修过的坑（见 reports/2026-09-26 §2.5）。
    rep.note("pre-fix 形态：'dispatch' 是否在 KEYWORDS 里 = %s（S1 片要把它变成 True）"
             % ("dispatch" in F.Lexer.KEYWORDS))
    rep.note("pre-fix 形态：无注解的 `dispatch area(x)` 头把整句吞成前两个 %s"
             "（本探针专门钉的静默吞；S2 片要把它变成定向语法诊断）"
             % (F.top_kinds("dispatch area(x)\nprint(1)\n")[:2],))
    dup = F.transpile("dup_def", "def f(x: int) -> int:\n    return 1\n\n"
                      "def f(x: str) -> int:\n    return 2\n\nprint(f(1))\n")
    rep.raw("same-name 'def' overload today (P-1' cost evidence)", F.error_summary(dup))
    rep.control("overloading by parameter type is refused today by "
                "scope_analyzer._check_redefinition",
                not dup["success"] and any("already declared" in e for e in dup["errors"]),
                F.error_summary(dup))

    # ---- expectations -------------------------------------------------------
    mod, err = F.parse(BLOCK)
    rep.expect("C-7.1 'dispatch' becomes a keyword", "dispatch" in F.Lexer.KEYWORDS)
    rep.expect("P-1 'arm' becomes a keyword", "arm" in F.Lexer.KEYWORDS)
    rep.expect("P-1 the block parses to a single DispatchDecl",
               mod is not None and mod.body[0].kind == "DispatchDecl",
               "err=%r" % err)
    decl = (F.find_nodes(mod, "DispatchDecl") or [None])[0] if mod is not None else None
    rep.expect("P-1 DispatchDecl keeps name/params/return type",
               decl is not None and getattr(decl, "name", None) == "area"
               and getattr(decl, "ret_type", None) is not None,
               "node=%r" % (getattr(decl, "__dict__", None) if decl else None))
    arms = getattr(decl, "arms", []) if decl is not None else []
    rep.expect("P-1 the block carries 2 arms", len(arms) == 2, "arms=%r" % (arms,))
    rep.expect("P-1 the un-annotated form 'dispatch area(x)' is now a syntax error "
               "(must never be swallowed again)",
               F.parse("dispatch area(x)\nprint(1)\n")[0] is None,
               "kinds=%s" % F.top_kinds("dispatch area(x)\nprint(1)\n"))
    res = F.transpile("dispatch_block", BLOCK + "print(1)\n")
    rep.expect("P-1 the whole block transpiles without diagnostics", res["success"],
               F.error_summary(res))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
