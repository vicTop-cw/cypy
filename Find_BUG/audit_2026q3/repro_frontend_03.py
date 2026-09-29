#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 03.

Target: cypyc/parser/macro_expander.py:366 (MacroExpander._arg_to_code) and
        cypyc/parser/macro_expander.py:391 (MacroExpander._ast_to_code)

Claim: a string macro argument is rendered back to source text by naive string
formatting - f'"{value.value}"'.  Constant.value already holds the *decoded*
literal text, so quotes are added but the content is never re-escaped (and the
f-string prefix is dropped).  Any argument that is not quote-safe produces
invalid code; _reparse_code() then swallows the failure
(macro_expander.py:298-300) and the macro call silently vanishes from output.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import ast
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer                                    # noqa: E402
from cypyc.parser.parser import Parser                                  # noqa: E402
from cypyc.parser.macro_expander import expand_macros, MacroExpander    # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator              # noqa: E402
from cypyc.utils.ast_utils import ASTUtils                              # noqa: E402

BODY_TMPL = ("macro G(x: Tokens) -> Tokens =\n"
             "    f```\n"
             "    f($x)\n"
             "    ```\n"
             "\n"
             "def demo():\n"
             "    @G!(%s)\n"
             "    return 0\n")


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def first_arg(src):
    return ASTUtils.collect_nodes(parse(src), 'MacroCall')[0].args[0]


def generated_call_arg(src):
    """Return (raw_emitted_arg, value_after_roundtrip) for `f(<arg>)` in demo(),
    or (None, None) when the statement disappeared / no longer parses."""
    code = CythonGenerator('m').generate(parse(src))
    for line in code.splitlines():
        m = re.match(r"^    f\((.*)\)$", line)
        if m:
            raw = m.group(1)
            body = raw[1:] if raw[:1].lower() == 'f' else raw
            try:
                return raw, ast.literal_eval(body)
            except Exception as exc:                                      # noqa: BLE001
                return raw, "<emitted text is not a valid literal: %s>" % exc
    return None, None


def remnants(src):
    """BacktickBlock nodes left over = text that could not be re-parsed."""
    return [b.content for b in ASTUtils.collect_nodes(expand_macros(parse(src)), 'BacktickBlock')]


def main():
    print("=" * 78)
    print("T0r61.2.1 / defect 03 - cypyc/parser/macro_expander.py:366 / :391 "
          "unescaped string arguments")
    print("=" * 78)
    ex = MacroExpander()
    reproduced = []

    cases = [
        ('audit example   "a,b"',            '"a,b"',                False),
        ('embedded quote  "say \\"hi\\""',   '"say \\"hi\\""',       False),
        ('backslash       "c:\\\\path"',     '"c:\\\\path"',         False),
        ('f-string arg    f"v={x}"',         'f"v={x}"',             False),
        ('via :391 _ast_to_code  f("a\\"b")', 'f("a\\"b")',          True),
    ]

    for label, arg_src, use_ast_to_code in cases:
        src = BODY_TMPL % arg_src
        try:
            arg = first_arg(src)
        except Exception as exc:                                          # noqa: BLE001
            print("%-38s -> source does not parse: %s: %s" % (label, type(exc).__name__, exc))
            continue
        rendered = ex._ast_to_code(arg) if use_ast_to_code else ex._arg_to_code(arg)
        emitted_raw, roundtrip = generated_call_arg(src)
        bad_bb = remnants(src)
        original = getattr(arg, 'value', None)
        prefix_lost = bool(getattr(arg, 'prefix', None)) and \
            not (emitted_raw or '').lower().startswith('f')
        faithful = emitted_raw is not None and not prefix_lost and (
            roundtrip == original if isinstance(original, str) else True)
        print("%-38s" % label)
        print("     source argument        : %s" % arg_src)
        print("     parsed argument        : kind=%s value=%r prefix=%r"
              % (arg.kind, original, getattr(arg, 'prefix', None)))
        print("     %s rendering  : %r" % (":391" if use_ast_to_code else ":366", rendered))
        print("     faithful literal would be : %r"
              % (json.dumps(original) if isinstance(original, str) else '<n/a>'))
        print("     un-parseable remnant    : %r" % bad_bb)
        print("     emitted in demo()       : %r -> re-reads as %r" % (emitted_raw, roundtrip))
        print("     -> argument value preserved end-to-end: %s" % faithful)
        if (not faithful) or bad_bb:
            reproduced.append(label)
        print()

    print("-" * 78)
    print("f-string prefix handling (:366 ignores Constant.prefix):")
    fs = BODY_TMPL % 'f"v={x}"'
    print("     input  f\"v={x}\"  ->  rendered %r  (interpolation silently lost)"
          % ex._arg_to_code(first_arg(fs)))
    print()
    print("latent sibling, same function, :377 `return str(arg)`: a bare str "
          "argument is substituted with NO quotes at all:")
    raw = ex._arg_to_code("a,b")
    print("     MacroExpander()._arg_to_code('a,b') -> %r ==> f(%s) is 2 arguments"
          % (raw, raw))
    print()
    print("root cause: :366/:391 re-quote the already-decoded Constant.value with "
          "f'\"{value}\"' - no escaping, no prefix - so the substituted text is "
          "only valid for quote-free strings; _reparse_code() (:298-300) turns "
          "the resulting syntax breakage into a silently dropped statement.")
    if reproduced:
        print("VERDICT: REPRODUCED - %d/%d string-argument cases mangled or lost: %s"
              % (len(reproduced), len(cases), [r.split()[0] for r in reproduced]))
        return 1
    print("VERDICT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                  # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
