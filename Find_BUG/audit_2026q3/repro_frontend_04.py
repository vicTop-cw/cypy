#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 04.

Targets:
  cypyc/parser/preprocessor.py:52-55   Preprocessor._process_macros
      -> `for name, value in self.macros.items(): source = source.replace(...)`
  cypyc/parser/macro_expander.py:339 / :348  _substitute_interpolations
      -> two blind re.sub passes over the macro body text

Claim: macro / define substitution is plain text, so it corrupts string literals
and comments that merely *contain* the macro name (and re-interpolates data that
was just substituted in).  Expected: identifiers inside strings and comments are
left untouched.

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer                                    # noqa: E402
from cypyc.parser.parser import Parser                                  # noqa: E402
from cypyc.parser.preprocessor import Preprocessor                      # noqa: E402
from cypyc.parser.macro_expander import expand_macros, MacroExpander    # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator              # noqa: E402
from cypyc.utils.ast_utils import ASTUtils                              # noqa: E402


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def demo_body(src):
    code = CythonGenerator('m').generate(parse(src))
    return [l for l in code.splitlines() if l.startswith('def demo') or l.startswith('    ')]


# --------------------------------------------------------------------------
# part A - preprocessor.py:52-55
# --------------------------------------------------------------------------
PP_SRC = (
    'def report():\n'
    '    print("BUFF bytes allocated")   # note: BUFF is the default\n'
    '    let BUFF_SIZE: int = 8\n'
    '    let BUFFSIZE: int = 9\n'
    '    let name: str = "BUFF"\n'
    '    return 0\n'
)


def part_a():
    print("-" * 78)
    print("PART A  Preprocessor.add_macro('BUFF','1024') + process()  "
          "[preprocessor.py:52-55]")
    print("input source:")
    for l in PP_SRC.splitlines():
        print("    |" + l)
    pp = Preprocessor()
    pp.add_macro("BUFF", "1024")
    out = pp.process(PP_SRC)
    print("output of _process_macros (blind str.replace, one pass per macro):")
    for l in out.splitlines():
        print("    |" + l)
    hits = []
    if '"1024 bytes allocated"' in out:
        hits.append("string literal rewritten: \"BUFF bytes allocated\" -> "
                    "\"1024 bytes allocated\"")
    if "# note: 1024" in out:
        hits.append("comment rewritten: # note: BUFF -> # note: 1024")
    if "let 1024_SIZE" in out:
        hits.append("identifier *substring* rewritten: BUFF_SIZE -> 1024_SIZE "
                    "(no word-boundary test)")
    if "let 1024SIZE" in out:
        hits.append("identifier *substring* rewritten: BUFFSIZE -> 1024SIZE")
    try:
        parse(out)
        parses = "still parses"
    except Exception as exc:                                          # noqa: BLE001
        parses = "%s: %s" % (type(exc).__name__, exc)
    print("downstream consequence: the preprocessed text %s" % parses)
    for h in hits:
        print("  * %s" % h)
    return hits, parses


# --------------------------------------------------------------------------
# part B - macro_expander.py:339 / :348
# --------------------------------------------------------------------------
NEST_SRC = ("macro t(x: Tokens) -> Tokens =\n"
            "    f```\n"
            "    print($(x))\n"
            "    ```\n"
            "\n"
            "def demo():\n"
            '    @t!("a$x")\n'
            "    return 0\n")

BODYSTR_SRC = ("macro p(x: Tokens) -> Tokens =\n"
               "    f```\n"
               "    # note about $x\n"
               '    label = "value=$x"\n'
               "    print(label)\n"
               "    ```\n"
               "\n"
               "def demo():\n"
               "    @p!(9)\n"
               "    return 0\n")


def part_b():
    print("-" * 78)
    print("PART B  f```...``` interpolation is blind text substitution  "
          "[macro_expander.py:339/:348]")
    ex = MacroExpander()
    hits = []

    arg = ASTUtils.collect_nodes(parse(NEST_SRC), 'MacroCall')[0].args[0]
    print("B1: body text 'print($(x))', argument = the string  \"a$x\"")
    step1 = re.sub(r'\$\(([^)]+)\)', lambda m: ex._arg_to_code(arg), "print($(x))")
    print("    :339 pass ($(...) -> argument source text) gives  %r" % step1)
    final = re.sub(r'\$(\w+)', lambda m: ex._arg_to_code(arg), step1)
    print("    :348 pass then RE-substitutes inside that data     gives %r" % final)
    print("    expander result (_substitute_interpolations)        : %r"
          % ex._substitute_interpolations("print($(x))", [arg], [{"name": "x"}]))
    remnant = [b.content for b in ASTUtils.collect_nodes(expand_macros(parse(NEST_SRC)),
                                                         'BacktickBlock')]
    print("    un-parseable BacktickBlock remnant                 : %r" % remnant)
    print("    generated demo()                                   : %s" % demo_body(NEST_SRC))
    if remnant and demo_body(NEST_SRC) == ['def demo():', '    return 0']:
        hits.append("data re-interpolated as code -> statement silently deleted")

    print()
    print("B2: macro body containing a comment and a string literal that mention $x")
    out = ex._substitute_interpolations("# note about $x\nlabel = \"value=$x\"",
                                        [ASTUtils.collect_nodes(parse(BODYSTR_SRC),
                                                                 'MacroCall')[0].args[0]],
                                        [{"name": "x"}])
    print("    body text before : %r" % "# note about $x\nlabel = \"value=$x\"")
    print("    body text after  : %r" % out)
    print("    generated demo() : %s" % demo_body(BODYSTR_SRC))
    if "# note about 9" in out:
        hits.append("comment text rewritten by the interpolator")
    if '"value=9"' in out:
        hits.append("string literal rewritten by the interpolator")
    return hits


def main():
    print("=" * 78)
    print("T0r61.2.1 / defect 04 - plain-text macro substitution corrupts strings "
          "and comments")
    print("=" * 78)
    hits_a, parses_a = part_a()
    hits_b = part_b()
    hits = hits_a + hits_b
    print()
    print("root cause: both substitution engines work on the raw character stream "
          "instead of on tokens - Preprocessor._process_macros (:52-55) does one "
          "unbounded str.replace per macro (no word boundary, no lexer), and "
          "MacroExpander._substitute_interpolations (:339, :348) runs two "
          "sequential re.sub passes over the body text, so freshly substituted "
          "argument text is scanned again.")
    if hits:
        print("VERDICT: REPRODUCED - %d corruptions observed "
              "(A: %d, B: %d); preprocessed text %s."
              % (len(hits), len(hits_a), len(hits_b), parses_a))
        return 1
    print("VERDICT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                 # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
