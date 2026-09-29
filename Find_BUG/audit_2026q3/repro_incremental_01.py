"""OMEGA repro T0r61.1.1 / defect 1
cypyc/incremental/dependency_graph.py:31 -- dead `kind == 'Identifier'` check.

Claim: the parser never emits a node whose `.kind` is 'Identifier'; identifiers are
represented by `Name` nodes (cypyc/parser/parser.py:498-501, kind set to "Name").
Therefore `_extract_identifier_usage` harvests nothing and `DependencyGraph.build_from_ast`
produces a graph with zero edges for any real parsed module.

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
Reads only; writes nothing.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ASTNode, Parser
from cypyc.incremental.dependency_graph import DependencyGraph

TARGET = os.path.join(REPO, "examples", "functions.cypy")


def parse_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return Parser(Lexer(fh.read()).tokenize()).parse()


def reference_identifier_usage(node, out):
    """What dependency_graph.py *should* collect: parser emits `Name` nodes."""
    if isinstance(node, ASTNode):
        for attr in dir(node):
            if attr.startswith("_"):
                continue
            value = getattr(node, attr)
            if hasattr(value, "kind") and value.kind == "Name" and hasattr(value, "id"):
                out.add(value.id)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    reference_identifier_usage(item, out)
            elif isinstance(value, ASTNode):
                reference_identifier_usage(value, out)
    return out


def main():
    if not os.path.exists(TARGET):
        print("HARNESS ERROR: missing %s" % TARGET)
        return 2

    ast = parse_file(TARGET)
    print("module parsed: %s (%d top-level statements)" % (os.path.relpath(TARGET, REPO), len(ast.body)))

    # 1. what the shipped extractor sees
    graph = DependencyGraph()
    graph.build_from_ast(ast)
    actual = {name: sorted(graph.get_dependencies(name)) for name in sorted(graph.get_all_definitions())}

    # 2. independent oracle: same walk, but matching the kind the parser really emits
    expected_defs = {}
    for stmt in ast.body:
        if type(stmt).__name__ == "FuncDef":
            usage = reference_identifier_usage(stmt, set())
            expected_defs[stmt.name] = sorted(usage - {stmt.name})
    top_level_names = set(expected_defs)
    expected = {n: sorted(set(d) & top_level_names) for n, d in expected_defs.items()}

    print("ACTUAL   (dependency_graph.py as shipped):")
    for name in sorted(actual):
        print("    %-20s -> %s" % (name, actual[name] or "(none)"))
    print("EXPECTED (same walk against kind == 'Name'):")
    for name in sorted(expected):
        print("    %-20s -> %s" % (name, expected[name] or "(none)"))

    actual_edges = sum(len(v) for v in actual.values())
    expected_edges = sum(len(v) for v in expected.values())
    print("edge count: actual=%d expected=%d" % (actual_edges, expected_edges))

    # 3. positive control: an `Identifier`-kinded node IS harvested -> only the kind string differs
    probe = ASTNode("Probe")
    ref = ASTNode("Identifier")
    ref.id = "a_name_kind_never_produced_by_the_parser"
    probe.expr = ref
    control = DependencyGraph()._extract_identifier_usage(probe)
    print("control (synthetic kind='Identifier' node): %s" % (sorted(control) or "EMPTY"))

    # 4. the universe of kinds the parser actually produced for this module
    kinds = set()

    def walk(n):
        if isinstance(n, ASTNode):
            kinds.add(n.kind)
            for a in dir(n):
                if a.startswith("_"):
                    continue
                v = getattr(n, a)
                if isinstance(v, ASTNode):
                    walk(v)
                elif isinstance(v, (list, tuple)):
                    for i in v:
                        walk(i)

    walk(ast)
    print("kinds containing 'Ident': %s" % (sorted(k for k in kinds if "ident" in k.lower()) or "NONE"))
    print("'Name' in parsed kind set: %s" % ("Name" in kinds))

    if actual_edges == 0 and expected_edges > 0 and control:
        print("RESULT: REPRODUCED -- graph is empty for a real module that has %d true edges"
              % expected_edges)
        return 1
    print("RESULT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
