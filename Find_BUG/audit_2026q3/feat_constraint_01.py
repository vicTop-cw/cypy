#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 unit-1 probe  T0r258.1.1 / constraint 01 -- declaration form & reserved word.

Clauses (SYNTAX/33-type-constraints-subtypes-dispatch.md): C-1.1/C-1.2/C-1.3, C-7.1
Expectation: ``constraint Numeric = int | float`` is a *type-level declaration* that
produces one ConstraintDef node holding the name and the member list, and
``constraint`` becomes a reserved word so ``constraint = 5`` is a syntax error.

Measured today (see the verbatim dump below): ``constraint`` is not in
cypyc/parser/lexer.py:160-223 KEYWORDS, so the source is silently swallowed into

    ExprStmt(Name('constraint'))  +  Assign(Name('Numeric'), BinOp('|', int, float))

i.e. a bare statement plus a *runtime* bitwise-or assignment -- the dangerous shape the
task pack asks to probe specifically.

Exit: 1 = not implemented, 0 = implemented, 2 = the judge itself broke.
Read-only: corpora go to a temp dir (see _feat_typesys_lib).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _feat_typesys_lib as F                                   # noqa: E402

DECL_SRC = "constraint Numeric = int | float\n\ndef main() -> int:\n    return 0\n"
RESERVED_SRC = "constraint = 5\nprint(constraint)\n"


def body(report):
    report.banner("constraint 01: declaration AST node + reserved word (C-1, C-7)")

    # ---- verbatim current behaviour ------------------------------------------
    mod, perr = F.parse(DECL_SRC)
    report.raw("parse(%r) -> top-level AST kinds" % "constraint Numeric = int | float",
               perr or [s.kind for s in mod.body])
    toks = [F.token_type(t) for t in F.Lexer(DECL_SRC).tokenize()][:3]
    report.raw("first 3 token types (KEYWORDS lookup result for 'constraint')", toks)

    cli_out, cli_err, cli_rc, cli_artifact = F.cli("constraint_kw", DECL_SRC)
    report.raw("python -m cypyc transpile <constraint decl>",
               (cli_out + "\n" + cli_err).strip())
    report.note("CLI returncode = %d and artifact written = %s "
                "(returncode 自 T0r258.4.2 的 LINK-1 起可信：cypyc/__main__.py 传播 main() 的返回值)"
                % (cli_rc, cli_artifact))

    # ---- controls: premises of the probe -------------------------------------
    alias_mod, _ = F.parse("type Numeric = int | float\n")
    report.control("type-alias declaration still yields TypeAlias",
                   F.top_kinds("type Numeric = int | float\n") == ["TypeAlias"],
                   "kinds=%s" % F.top_kinds("type Numeric = int | float\n"))
    # 下面两条是**缺陷现状取证**，不是判据前提：实现单元把它们转正之后必然不再成立，
    # 若写成 control 就会在修复完成后抛 HarnessError -> exit 2（既不是「未实现」也不是
    # 「判据坏了」，而是探针自杀）。因此按 note 记录，判据只看 expect 段。
    swallowed = (mod is not None
                 and [s.kind for s in mod.body][:2] == ["ExprStmt", "Assign"])
    report.note("pre-fix 形态：%s（本条转正后消失，故不作 control）"
                % ("constraint 声明被吞成 ExprStmt+Assign" if swallowed
                   else "声明未被吞成 ExprStmt+Assign（说明 C-1.1 已落地或语料被改动）"))
    report.note("pre-fix 形态：'constraint' 仍在 KEYWORDS 之外（可用 %d 个关键字，含它=%s）"
                % (len(F.Lexer.KEYWORDS), "constraint" in F.Lexer.KEYWORDS))

    # ---- expectations of the specified behaviour -----------------------------
    report.expect("C-7.1 lexer: 'constraint' is a reserved keyword",
                  "constraint" in F.Lexer.KEYWORDS,
                  "KEYWORDS[%r] missing -> IDENTIFIER" % "constraint")
    report.expect("C-1.1 parser: exactly one ConstraintDef at top level",
                  mod is not None and [s.kind for s in mod.body][:1] == ["ConstraintDef"],
                  "kinds=%s" % ([] if mod is None else [s.kind for s in mod.body]))
    defs = F.find_nodes(mod, "ConstraintDef") if mod is not None else []
    node = defs[0] if defs else None
    report.expect("C-1.1 ConstraintDef.name == 'Numeric'",
                  node is not None and getattr(node, "name", None) == "Numeric",
                  "name=%r" % (getattr(node, "name", None) if node else None))
    members = list(getattr(node, "members", []) or []) if node is not None else []
    report.expect("C-1.2/C-1.3 ConstraintDef keeps the 2 member type names in order",
                  [getattr(m, "id", getattr(m, "name", m)) for m in members] == ["int", "float"],
                  "members=%r" % (members,))
    report.expect("C-1.1 no stray ExprStmt/Assign left over from the swallowed form",
                  mod is not None and "Assign" not in [s.kind for s in mod.body],
                  "kinds=%s" % ([] if mod is None else [s.kind for s in mod.body]))
    report.expect("C-7.1 'constraint = 5' is now a syntax error",
                  F.parse(RESERVED_SRC)[0] is None,
                  "still parses as %s" % F.top_kinds(RESERVED_SRC))

    res = F.transpile("constraint_kw_decl", DECL_SRC)
    report.expect("C-1 declaration accepted without any diagnostic",
                  res["success"], F.error_summary(res))


if __name__ == "__main__":
    sys.exit(F.run_probe(F.Report("PROBE feat_constraint_01",
                                  "SYNTAX/33 C-1.1, C-1.2, C-1.3, C-7.1"), body))
