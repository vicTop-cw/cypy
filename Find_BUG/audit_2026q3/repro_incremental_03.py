"""OMEGA repro T0r61.1.1 / defect 3
cypyc/incremental/ast_differ.py:108 -- `compare()` does `self.changed_definitions.add(name)`
but only *reassigns* `added_definitions`/`removed_definitions` (lines 99/101); the
`changed_definitions` set created at line 12 is never cleared. Because
`IncrementalCompiler` holds ONE long-lived ASTDiffer (cypyc/incremental/incremental_manager.py:59)
and `analyze_changes_with_old_ast` reads it back at :361, every later comparison replays the
first round's changed set.

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
Scratch modules live under Find_BUG/audit_2026q3/scratch/.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(HERE, "scratch")
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.incremental.ast_differ import ASTDiffer
from cypyc.incremental.incremental_manager import IncrementalCompiler

# NOTE: the body edit is a line-count-changing one so that the differ *does* see it in round 1
# (defect 2 is pinned separately by repro_incremental_02).
V1 = "def add(x: int, y: int) -> int:\n    return x + y\n"
V2 = "def add(x: int, y: int) -> int:\n    return x + y\n    print(x)\n"


def write(name, text):
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def parse_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return Parser(Lexer(fh.read()).tokenize()).parse()


def main():
    p1 = write("repro03_v1.cypy", V1)
    p2 = write("repro03_v2.cypy", V2)
    a1, a2 = parse_file(p1), parse_file(p2)

    print("--- direct ASTDiffer state ---")
    differ = ASTDiffer()
    r1 = differ.compare(a1, a2)
    print("round1 compare(v1, v2) -> changed=%s added=%s removed=%s returns=%s"
          % (sorted(differ.changed_definitions), sorted(differ.added_definitions),
             sorted(differ.removed_definitions), r1))

    fresh = ASTDiffer()
    clean = fresh.compare(a1, a1)
    print("reference   compare(v1, v1) on a FRESH instance -> changed=%s returns=%s"
          % (sorted(fresh.changed_definitions), clean))

    r2 = differ.compare(a1, a1)
    print("OBSERVED  round2 compare(v1, v1) on the SAME instance -> changed=%s added=%s removed=%s returns=%s"
          % (sorted(differ.changed_definitions), sorted(differ.added_definitions),
             sorted(differ.removed_definitions), r2))
    print("EXPECTED  round2 compare(v1, v1)                    -> changed=[] added=[] removed=[] returns=False")

    r3 = differ.compare(a1, a1)
    print("round3 compare(v1, v1) again                       -> changed=%s returns=%s"
          % (sorted(differ.changed_definitions), r3))

    leaked_direct = differ.changed_definitions == {"add"} and r2 is True

    print("--- through IncrementalCompiler.analyze_changes_with_old_ast (the real call path) ---")
    inc = IncrementalCompiler(cache_dir=os.path.join(SCRATCH, "cache"))
    res1 = inc.analyze_changes_with_old_ast(a1, a2)
    print("call1 (v1 -> v2): need_recompile=%s changed=%s affected=%s reused=%s cache_hit=%s"
          % (res1.need_recompile, sorted(res1.changed_definitions), sorted(res1.affected_definitions),
             sorted(res1.reused_definitions), res1.cache_hit))
    res2 = inc.analyze_changes_with_old_ast(a1, a1)
    print("call2 (v1 -> v1): need_recompile=%s changed=%s affected=%s reused=%s cache_hit=%s"
          % (res2.need_recompile, sorted(res2.changed_definitions), sorted(res2.affected_definitions),
             sorted(res2.reused_definitions), res2.cache_hit))
    print("EXPECTED call2 (v1 -> v1): need_recompile=False changed=[] affected=[] reused=['add'] cache_hit=True")
    leaked_manager = res2.need_recompile is True and res2.changed_definitions == {"add"}

    # added/removed are re-assigned each call (lines 99/101) -> they do NOT leak; state it precisely
    a3 = parse_file(write("repro03_v3_added_def.cypy", V1 + "\ndef sub(x: int) -> int:\n    return x\n"))
    differ2 = ASTDiffer()
    differ2.compare(a1, a3)
    before = (sorted(differ2.added_definitions), sorted(differ2.removed_definitions))
    differ2.compare(a1, a1)
    after = (sorted(differ2.added_definitions), sorted(differ2.removed_definitions))
    print("added/removed leak check: round1 added=%s removed=%s -> round2(v1,v1) added=%s removed=%s"
          % (before[0], before[1], after[0], after[1]))
    no_other_leak = after == ([], [])

    if leaked_direct and leaked_manager:
        print("RESULT: REPRODUCED -- stale changed_definitions survives into every later compare()%s"
              % ("" if no_other_leak else " (NOTE: added/removed leak too)"))
        return 1
    if leaked_direct or leaked_manager:
        print("RESULT: REPRODUCED (partial: %s)" % ("direct differ" if leaked_direct else "manager path"))
        return 1
    print("RESULT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
