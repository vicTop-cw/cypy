#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.2.1 / subtype 01 -- declaration form.

Clauses: S-1.1/S-1.2/S-1.4, S-7.3, S-3.1 (upcast), C-7.1 (reserved word).

Lexing note: the `<:` operator ALREADY exists -- cypyc/parser/lexer.py:32 defines
TokenType.SUBTYPE and lexer.py:786 emits it -- but no parser rule ever consumes it, so
`subtype Meter <: int` dies with "Unexpected token SUBTYPE at 1:15" while
`subtype Meter` (without `<:`) is silently swallowed into two ExprStmt, exactly like
the constraint form.  Both shapes are pinned below.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL = "subtype Meter <: float\n"
report = F.Report("PROBE feat_subtype_01", "SYNTAX/33 S-1.1, S-1.2, S-1.4, S-3.1, S-7.3")


def body(rep):
    rep.banner("subtype 01: 'subtype Name <: Base' must become a declaration")

    # ---- verbatim current behaviour ----------------------------------------
    mod, perr = F.parse(DECL + "def use(m: Meter) -> float:\n    return m\n")
    rep.raw("parse('subtype Meter <: float' + use)", perr or [s.kind for s in mod.body])
    kinds_nocolon = F.top_kinds("subtype Meter\ndef f() -> int:\n    return 1\n")
    rep.raw("parse('subtype Meter' WITHOUT '<:') -> kinds", kinds_nocolon)
    out, err, rc, artifact = F.cli("subtype_decl", DECL + "print(1)\n")
    rep.raw("python -m cypyc transpile <subtype decl>", (out + "\n" + err).strip())

    toks = [F.token_type(t) for t in F.Lexer("subtype Meter <: float\n").tokenize()][:5]
    rep.raw("tokens of 'subtype Meter <: float'", toks)

    # ---- controls -----------------------------------------------------------
    # S-1 的实现目标就是把 :40/:43/:45 三条现状反转（keyword 化 + parser 产出 SubtypeDef），
    # 所以它们是**取证**而不是前提：写成 control 会让修好的树直接 exit 2。
    rep.note("pre-fix 形态：'subtype' 尚未进 KEYWORDS（当前 %d 个关键字，含它=%s）"
             % (len(F.Lexer.KEYWORDS), "subtype" in F.Lexer.KEYWORDS))
    rep.control("'<:' already lexes as a dedicated SUBTYPE token (S-1.4 free lunch)",
                "SUBTYPE" in toks, "tokens seen: %s" % toks)
    rep.note("pre-fix 形态：带 '<:' 的声明 %s（S-1 要它解析成 SubtypeDef）"
             % ("parser 硬失败" if mod is None else "已能解析"))
    rep.note("pre-fix 形态：不带 '<:' 时整段被吞成裸语句 kinds=%s" % kinds_nocolon[:2])
    upcast_ok = F.transpile("alias_upcast",
                            "type Meter = float\nlet m: Meter = 1.0\nlet v: float = m\n"
                            "print(v)\n")
    rep.control("alias substitute upcasts today (S-3.1 baseline)", upcast_ok["success"],
                F.error_summary(upcast_ok))

    # ---- expectations -------------------------------------------------------
    rep.expect("S-1.4/C-7.1 'subtype' becomes a keyword", "subtype" in F.Lexer.KEYWORDS)
    rep.expect("S-1.1 parser yields a single SubtypeDef/Decl node",
               F.has_node_kind(mod, "SubtypeDef") or F.has_node_kind(mod, "SubtypeDecl"),
               "parse error=%r" % perr)
    node = (F.find_nodes(mod, "SubtypeDef") or F.find_nodes(mod, "SubtypeDecl")
            or [None])[0] if mod is not None else None
    got = (getattr(node, "name", None), getattr(node, "base", None)) if node else (None, None)
    rep.expect("S-1.1/S-1.2 node carries name='Meter' and base resolving to 'float'",
               got[0] == "Meter" and str(getattr(got[1], "id", got[1])) == "float",
               "name=%r base=%r" % got)
    rep.expect("S-1.4 'subtype Meter' without '<:' is a syntax error (not swallowed)",
               F.parse("subtype Meter\ndef f() -> int:\n    return 1\n")[0] is None,
               "kinds=%s" % kinds_nocolon)

    decl_only = F.transpile("decl_only", DECL + "def use(m: Meter) -> float:\n    return m\n\n"
                            "let m: Meter = 1.5\nprint(use(m))\n")
    rep.raw("decl + upcast use (compile target)", F.error_summary(decl_only))
    rep.expect("S-3.1 'subtype' compiles and Meter values pass to float parameters",
               decl_only["success"], F.error_summary(decl_only))

    unknown = F.transpile("unknown_base", "subtype Meter <: Flaot\nprint(1)\n")
    rep.expect("S-7.3 unknown base type gets a naming diagnostic (not a token error)",
               any("unknown base" in e.lower() or "not declared" in e.lower()
                   for e in unknown["errors"]),
               F.error_summary(unknown))

    union_base = F.transpile("union_base", "subtype N <: int | float\nprint(1)\n")
    rep.expect("S-1.2 a union may not be a subtype base (rejected with a reason)",
               not union_base["success"]
               and any("union" in e.lower() or "not allowed" in e.lower()
                       for e in union_base["errors"]),
               F.error_summary(union_base))


if __name__ == "__main__":
    sys.exit(F.run_probe(report, body))
