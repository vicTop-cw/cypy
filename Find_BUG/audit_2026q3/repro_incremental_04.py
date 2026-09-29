"""OMEGA repro T0r61.1.1 / defect 4
cypyc/project/project_compiler.py:339 -- the same dead `kind == 'Identifier'` test as
dependency_graph.py:31, in `_get_type_str()`. Two proofs:

  (A) static  : the parser's whole AST-kind universe (examples/ corpus + a scratch project)
                contains 'Name' but never 'Identifier' -- the token type IDENTIFIER exists in
                the lexer but is lowered into Name nodes, so no AST node can ever carry it.
  (B) dynamic : a line tracer over project_compiler.py counts how often line 339 (the test)
                executes vs. line 340 (the branch body) while ProjectCompiler collects type
                exports for a real project. Body never runs -> branch is dead.

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
Scratch project lives under Find_BUG/audit_2026q3/scratch/proj04/.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(HERE, "scratch", "proj04")
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ASTNode, Parser
from cypyc.project.project_compiler import ProjectCompiler
import cypyc.project.project_compiler as pc_module

PC_FILE = os.path.abspath(pc_module.__file__)


def locate_branch_lines():
    """Anchor on source text instead of hard-coded numbers, so that both valid fixes
    (kind literal changed to 'Name', or the dead branch deleted) are recognised."""
    lines = open(PC_FILE, encoding="utf-8").read().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("def _get_type_str")), None)
    if start is None:
        return {}
    found = {}
    for i in range(start, min(start + 20, len(lines))):
        text = lines[i]
        if "'Identifier'" in text and text.rstrip().endswith(":"):
            found["test"] = i + 1
        elif "'TypeAnnotation'" in text:
            found["elif"] = i + 1
        elif "hasattr(type_node, 'id')" in text:
            found["fallback"] = i + 1
        elif "test" in found and "body" not in found and "return" in text:
            found["body"] = i + 1
    return found


BRANCH = locate_branch_lines()

# every kind of type position the project path feeds into _get_type_str
# (struct field annotations, function params/return, type-alias target)
PROJ = {
    "types.cypy": (
        "struct Point:\n"
        "    x: int\n"
        "    y: int\n"
        "\n"
        "type Distance = float\n"
        "\n"
        "def make_point(x: int, y: int) -> Point:\n"
        "    return Point(x=x, y=y)\n"
        "\n"
        "def scale(p: Point, k: Distance) -> Point:\n"
        "    return Point(x=0, y=0)\n"
    ),
    "geometry.cypy": (
        "from types import Point\n"
        "from types import make_point\n"
        "\n"
        "def norm(p: Point) -> float:\n"
        "    return 1.0\n"
    ),
}


def collect_kinds(node, sink, depth=0):
    if isinstance(node, ASTNode):
        sink.add(node.kind)
        for attr in dir(node):
            if attr.startswith("_"):
                continue
            value = getattr(node, attr)
            if isinstance(value, ASTNode):
                collect_kinds(value, sink, depth + 1)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect_kinds(item, sink, depth + 1)


def parse_source(src):
    return Parser(Lexer(src).tokenize()).parse()


def main():
    # ---------- (A) static: kind universe ----------
    kinds = set()
    corpus = []
    for name in sorted(os.listdir(os.path.join(REPO, "examples"))):
        if name.endswith(".cypy"):
            corpus.append(os.path.join(REPO, "examples", name))
    # a couple of richer syntax corpora, read-only
    for extra in ("SYNTAX", "Find_BUG/beartype"):
        base = os.path.join(REPO, extra)
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.endswith(".cypy"):
                        corpus.append(os.path.join(root, f))

    parsed = 0
    for path in corpus[:40]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ast = parse_source(fh.read())
        except Exception:
            continue
        parsed += 1
        collect_kinds(ast, kinds)

    print("(A) parsed %d/%d corpus files; AST kind universe size = %d" % (parsed, len(corpus), len(kinds)))
    print("    'Name' in kind universe        : %s" % ("Name" in kinds))
    print("    'Identifier' in kind universe  : %s" % ("Identifier" in kinds))
    print("    kinds containing 'ident'       : %s" % (sorted(k for k in kinds if "ident" in k.lower()) or "NONE"))
    print("    kinds containing 'TypeAnnot'   : %s" % (sorted(k for k in kinds if "typeannot" in k.lower().replace("_", "")) or "NONE"))
    # the literal string also appears nowhere in the parser sources:
    parser_src = open(os.path.join(REPO, "cypyc", "parser", "parser.py"), encoding="utf-8").read()
    lexer_src = open(os.path.join(REPO, "cypyc", "parser", "lexer.py"), encoding="utf-8").read()
    print("    occurrences of \"'Identifier'\" in cypyc/parser/parser.py : %d" % parser_src.count("'Identifier'"))
    print("    occurrences of \"'TypeAnnotation'\" in cypyc/parser/parser.py : %d" % parser_src.count("'TypeAnnotation'"))
    print("    lexer defines IDENTIFIER as a *token* type only : %s"
          % ('IDENTIFIER = "IDENTIFIER"' in lexer_src))

    # ---------- (B) dynamic: line tracer over project_compiler.py ----------
    os.makedirs(SCRATCH, exist_ok=True)
    for fname, body in PROJ.items():
        with open(os.path.join(SCRATCH, fname), "w", encoding="utf-8") as fh:
            fh.write(body)

    hits = {}
    fed_kinds = []

    def tracer(frame, event, arg):
        if event != "call":
            return None
        fname = frame.f_code.co_filename
        if fname != PC_FILE:
            return None
        if frame.f_code.co_name == "_get_type_str":
            tn = frame.f_locals.get("type_node")
            fed_kinds.append(getattr(tn, "kind", "<no kind attr>:%s" % type(tn).__name__))

        def local(frame2, event2, arg2):
            if event2 == "line" and frame2.f_code.co_filename == PC_FILE:
                hits[frame2.f_lineno] = hits.get(frame2.f_lineno, 0) + 1
            return local
        return local

    compiler = ProjectCompiler(project_root=SCRATCH,
                               output_dir=os.path.join(SCRATCH, "output"),
                               verbose=False)
    sys.settrace(tracer)
    try:
        compiler.discover_modules()
        compiler.parse_all_modules()
        registry = compiler.collect_type_exports()
    finally:
        sys.settrace(None)

    dropped = sorted(set(compiler._source_files) - set(compiler._ast_cache))
    if dropped:
        print("HARNESS ERROR: scratch modules failed to parse and were skipped: %s" % dropped)
        return 2

    print("(B) project modules: %s" % sorted(compiler._source_files))
    print("    _get_type_str called %d times, type_node kinds observed: %s"
          % (len(fed_kinds), sorted(set(fed_kinds))))
    if not BRANCH.get("test"):
        print("    no `kind == 'Identifier'` test found inside _get_type_str anymore -> branch deleted")
    for key, label in (("test", "kind == 'Identifier' test"),
                       ("body", "branch BODY (return from the Identifier test)"),
                       ("elif", "elif kind == 'TypeAnnotation' test"),
                       ("fallback", "fallback `if hasattr(type_node,'id')`")):
        ln = BRANCH.get(key)
        if ln is None:
            print("    line %-4s n/a  (%s)" % ("n/a", label))
        else:
            print("    line %-4d executed %-4s  (%s)" % (ln, hits.get(ln, 0), label))

    # what the registry actually holds, i.e. is the fallback masking the dead branch?
    exports = []
    for mod in sorted(getattr(registry, "_modules", {}) or {}):
        info = registry._modules[mod]
        for exp in (getattr(info, "exports", {}) or {}).values():
            exports.append("%s.%s ret=%s params=%s fields=%s"
                           % (mod, exp.name, exp.return_type, exp.param_types, exp.field_types))
    print("    collected type exports (proof the values still come out right via the fallback):")
    for e in sorted(exports):
        print("      " + e)

    test_hits = hits.get(BRANCH.get("test", -1), 0)
    body_hits = hits.get(BRANCH.get("body", -1), 0)
    static_dead = "Identifier" not in kinds and "Name" in kinds
    branch_present = bool(BRANCH.get("test"))
    dynamic_dead = branch_present and test_hits > 0 and body_hits == 0
    if static_dead and dynamic_dead:
        print("RESULT: REPRODUCED -- line %d runs %d time(s), line %d runs 0 times; branch is dead"
              % (BRANCH["test"], test_hits, BRANCH.get("body")))
        return 1
    print("RESULT: NOT-REPRODUCED (static_dead=%s branch_present=%s test_hits=%d body_hits=%d)"
          % (static_dead, branch_present, test_hits, body_hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
