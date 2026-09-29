"""OMEGA repro T0r61.1.1 / defect 2
cypyc/incremental/ast_differ.py:69-77 (`_node_to_hash`) -- statement hash is built from
`node.kind` + `str(node)`, and `ASTNode.__repr__` (cypyc/parser/parser.py:92-93) only prints
`kind(line=..., col=...)`. Body *content* never reaches the definition hash
(ast_differ.py:26-29), so an in-place expression edit that keeps line/col is reported as
"unchanged" and the function is dropped from `changed_definitions`.

Scratch modules are written under Find_BUG/audit_2026q3/scratch/ (examples/ is never touched).

Exit code: 1 = bug reproduced, 0 = not reproduced, 2 = harness problem.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(HERE, "scratch")
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ASTNode, Parser
from cypyc.incremental.ast_differ import ASTDiffer

V1 = "def add(x: int, y: int) -> int:\n    return x + y\n\ndef keep(z: int) -> int:\n    return z\n"
# only the expression inside `add` changes; every token stays on the same line/column
V2 = "def add(x: int, y: int) -> int:\n    return x - y\n\ndef keep(z: int) -> int:\n    return z\n"
# sanity pair: same edit but body length changes -> the differ DOES see this one
V3 = "def add(x: int, y: int) -> int:\n    return x + y\n    return x - y\n\ndef keep(z: int) -> int:\n    return z\n"


def write(name, text):
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def parse_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return Parser(Lexer(fh.read()).tokenize()).parse()


def show_body_nodes(ast, func_name):
    for stmt in ast.body:
        if isinstance(stmt, ASTNode) and stmt.kind == "FuncDef" and stmt.name == func_name:
            out = []
            for s in stmt.body:
                out.append("      %s" % ASTDiffer()._node_to_hash(s))
                out.append("        repr=str() -> %r ; kind=%r ; line=%r ; col=%r"
                           % (str(s), s.kind, s.line, s.col))
                for a in sorted(dir(s)):
                    if not a.startswith("_") and isinstance(getattr(s, a), ASTNode):
                        out.append("        child attr %-8s -> %r" % (a, str(getattr(s, a))))
            return "\n".join(out)
    return "      <not found>"


def main():
    p1 = write("repro02_v1.cypy", V1)
    p2 = write("repro02_v2_same_lines.cypy", V2)
    p3 = write("repro02_v3_extra_line.cypy", V3)

    a1, a2, a3 = parse_file(p1), parse_file(p2), parse_file(p3)

    print("v1 body of add:                %r" % V1.splitlines()[1])
    print("v2 body of add (semantic edit):%r  (identical line/col layout)" % V2.splitlines()[1])
    print("v1 statement hash fragments:")
    print(show_body_nodes(a1, "add"))
    print("v2 statement hash fragments:")
    print(show_body_nodes(a2, "add"))

    differ = ASTDiffer()
    h1 = differ._compute_definition_hash(a1.body[0])
    h2 = differ._compute_definition_hash(a2.body[0])
    changed = differ.compare(a1, a2)
    print("definition hash v1 = %s" % h1)
    print("definition hash v2 = %s" % h2)
    print("hashes equal      = %s" % (h1 == h2))
    print("OBSERVED  compare(v1, v2): returns=%s changed_definitions=%s"
          % (changed, sorted(differ.changed_definitions)))
    print("EXPECTED  compare(v1, v2): returns=True changed_definitions=['add']")

    differ2 = ASTDiffer()
    changed2 = differ2.compare(a1, a3)
    print("control   compare(v1, v3 body-length edit): returns=%s changed_definitions=%s"
          % (changed2, sorted(differ2.changed_definitions)))

    same = sorted(differ.changed_definitions) == ["add"]
    ctrl_ok = "add" in differ2.changed_definitions  # ('keep' shifts down too, as expected)
    if (not same) and ctrl_ok:
        print("RESULT: REPRODUCED -- expression edit invisible to the differ, while a "
              "line-count-changing edit of the same function IS detected")
        return 1
    if not same:
        print("RESULT: REPRODUCED -- 'add' missing from changed_definitions after a body edit")
        return 1
    print("RESULT: NOT-REPRODUCED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
