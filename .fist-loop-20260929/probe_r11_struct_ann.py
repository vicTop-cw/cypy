import sys, json
from pathlib import Path
ROOT = Path(".").resolve(); sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og

SRC = """struct Wrap<T>:
    value: T


def f() -> int:
    let w: Wrap<int> = Wrap(1)
    return 0
"""
ast = og.compile_src(SRC)
print("kinds", [type(n).__name__ for n in ast.body])
fn = ast.body[1]
stmt = fn.body[0] if hasattr(fn, "body") else None
print("let kind", type(stmt).__name__ if stmt is not None else None)
if stmt is not None:
    ann = getattr(stmt, "type_annotation", None)
    print("ann kind", type(ann).__name__, "repr-fields", {k: v for k, v in vars(ann).items() if k in ("kind","name","id","args","slice")} if ann is not None else None)
    if ann is not None and getattr(ann, "args", None):
        a0 = ann.args[0]
        print("ann arg0", type(a0).__name__, getattr(a0, "id", getattr(a0, "name", None)), getattr(a0, "args", None))
ch = og.TypeChecker(); ch.check(ast)
print("checker.errors", ch.errors)
print("type_map has T?", "T" in ch.type_map, "struct_defs keys", list(ch.struct_defs))
