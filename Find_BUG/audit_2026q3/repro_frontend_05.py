#!/usr/bin/env python3
"""OMEGA-verified repro unit T0r61.2.1 / defect 05.

Target: cypyc/utils/indent_detector.py:46-48  (IndentDetector.normalize, tab branch)

Claim: for tab-indented sources `normalize()` counts *characters* in the leading
whitespace run and then divides by 4 (`original_indent // 4`), although 1 tab is
1 character.  Therefore 1-3 leading tabs compute to indent level 0 and the whole
indentation of the file is erased.  Expected: 1 tab == 1 level, or a documented
consistent expansion (the lexer at cypyc/parser/lexer.py:419-420 expands 1 tab to
4 columns, which is also what detect() reports as indent_size).

Exit codes: 1 = defect REPRODUCED, 0 = not reproduced, 3 = harness error.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer                            # noqa: E402
from cypyc.parser.parser import Parser                          # noqa: E402
from cypyc.utils.indent_detector import IndentDetector          # noqa: E402

T = "\t"

# 1 tab per nesting level - the natural tab convention, and what the bug is about
SRC_1TAB = ("def add(a, b):\n"
            + T + "let s = a + b\n"
            + T + "if s > 0:\n"
            + T * 2 + "return s\n"
            + T + "return 0\n")

# 2 tabs per level (also common) - same collapse
SRC_2TAB = ("def f():\n" + T * 2 + "let x = 1\n" + T * 2 + "if x:\n" + T * 4 + "return 1\n")

# space-indented equivalent, used as the structural baseline
SRC_SPACES = ("def add(a, b):\n"
              "    let s = a + b\n"
              "    if s > 0:\n"
              "        return s\n"
              "    return 0\n")


def show(label, src):
    print("%s:" % label)
    for i, line in enumerate(src.split("\n"), 1):
        if line.strip():
            lead = line[:len(line) - len(line.lstrip())]
            print("   line %d  leading-whitespace=%r  chars=%d  -> level after //4 = %d"
                  % (i, lead.replace("\t", "<TAB>"), len(lead), len(lead) // 4))


def parse_result(src):
    try:
        ast = Parser(list(Lexer(src).tokenize())).parse()
    except Exception as exc:                                      # noqa: BLE001
        return "%s: %s" % (type(exc).__name__, exc), None
    fn = [s for s in ast.body if getattr(s, 'kind', None) == 'FuncDef']
    body = [getattr(s, 'kind', None) for s in (fn[0].body if fn else [])]
    return "parsed OK, %d top-level stmt(s) %s" % (len(ast.body), body), ast


def main():
    print("=" * 78)
    print("T0r61.2.1 / defect 05 - cypyc/utils/indent_detector.py:46-48 "
          "tab indentation collapsed")
    print("=" * 78)
    det = IndentDetector()
    print("detect() contract on the tab sample: %r  "
          "(indent_size==4 == '1 tab expands to 4 columns', lexer.py:419-420)"
          % (det.detect(SRC_1TAB),))
    print()
    show("input (1 tab per level)", SRC_1TAB)
    norm = IndentDetector().normalize(SRC_1TAB)
    print("normalize() output:")
    for line in norm.split("\n"):
        print("   |" + line.replace("\t", "<TAB>"))
    print()
    base, _ = parse_result(SRC_SPACES)
    print("baseline  space-indented equivalent : %s" % base)
    raw, _ = parse_result(SRC_1TAB)
    print("input     raw tab source (no normalize): %s" % raw)
    after, _ = parse_result(norm)
    print("AFTER     normalize() output          : %s" % after)
    print()
    levels_in = [len(l) - len(l.lstrip()) for l in SRC_1TAB.split("\n") if l.strip()]
    levels_out = [len(l) - len(l.lstrip()) for l in norm.split("\n") if l.strip()]
    print("indentation chars per line, in -> out: %s -> %s" % (levels_in, levels_out))

    hits = []
    if norm.count("\t") == 0:
        hits.append("every leading tab removed: 1-3 tabs -> chars//4 == 0 -> level 0")
    if isinstance(after, str) and after.startswith(("ValueError", "SyntaxError", "IndexError")):
        hits.append("normalized source no longer parses: %s" % after)
    if raw.startswith("parsed") and not after.startswith("parsed"):
        hits.append("source the lexer accepts is destroyed by normalize()")

    print()
    show("second sample (2 tabs per level)", SRC_2TAB)
    norm2 = IndentDetector().normalize(SRC_2TAB)
    print("normalize() -> %r" % norm2)
    print("            -> parse: %s" % parse_result(norm2)[0])
    if norm2.count("\t") < SRC_2TAB.count("\t"):
        hits.append("2-tab indentation also flattened (%d tab chars -> %d)"
                    % (SRC_2TAB.count("\t"), norm2.count("\t")))

    # 4 tabs per level is the accidental "sweet spot" - show it, to pin the //4 unit
    src4 = "def f():\n" + T * 4 + "let x = 1\n" + T * 4 + "if x:\n" + T * 8 + "return 1\n"
    norm4 = IndentDetector().normalize(src4)
    print()
    print("control: 4-tabs-per-level survives: %r -> %s"
          % (norm4.replace("\t", "<TAB>"), parse_result(norm4)[0]))
    print("   (proof that the divisor is a *character* count: 4 tab-chars -> 1 level)")

    print()
    print("root cause: line 46-48 mixes units - `original_indent` is a character "
          "count of the whitespace prefix while the divisor 4 is the tab->column "
          "expansion; the correct level for a tab run is len(tabs) (1 tab = 1 level) "
          "or, to match lexer.py, the expansion must be applied before the //4.")
    if hits:
        print("VERDICT: REPRODUCED - %s" % "; ".join(hits))
        return 1
    print("VERDICT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        sys.exit(3)
