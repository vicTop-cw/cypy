"""R11 基线：现盘上所有 .cypy 源里的「泛型注解 / 泛型调用」元数实测。

用途：在写 SYNTAX/11 泛型类条款之前，先量清「元数门一旦开，会不会打红既有源」——
门要开到哪一格（class / struct / 两者）是**测量决定**的，不是拍的。
尺子与 Ω-gate 同源（同一个 Parser / TypeChecker）。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import omega_gate as og  # noqa: E402
from cypyc.parser.parser import (  # noqa: E402
    Call,
    ClassDef,
    GenericType,
    StructDef,
)

FILES = sorted(
    p for d in ("examples", "tests", "corpus") for p in (ROOT / d).rglob("*.cypy")
) + [p for p in ROOT.rglob("*.cypy") if "node_modules" not in str(p)]
FILES = sorted(set(FILES))


def walk(node, out):
    seen = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        out.append(cur)
        for val in list(vars(cur).values()) if hasattr(cur, "__dict__") else []:
            if isinstance(val, (list, tuple)):
                stack.extend([v for v in val if hasattr(v, "__dict__")])
            elif hasattr(val, "__dict__") and type(val).__name__.endswith(("Def", "Stmt", "Expr", "Type", "Param", "Node")):
                stack.append(val)


def main() -> int:
    decls: dict = {}
    ann_rows, call_rows = [], []
    parse_fail: list = []
    for path in FILES:
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            ast = og.compile_src(src)
        except Exception as exc:  # noqa: BLE001
            # 不只捕 ValueError：解析器在真实文件上抛别的异常类型本身就是观测量
            parse_fail.append((path, type(exc).__name__, str(exc)[:80]))
            continue
        nodes: list = []
        walk(ast, nodes)
        local: dict = {}
        for n in nodes:
            if isinstance(n, (ClassDef, StructDef)):
                params = list(getattr(n, "generic_params", []) or [])
                local[n.name] = (type(n).__name__, params)
        decls.update({k: v for k, v in local.items() if k not in decls})
        for n in nodes:
            if isinstance(n, GenericType) and n.name in local:
                kind, params = local[n.name]
                ann_rows.append((path, n.name, kind, len(params), len(n.args or [])))
            if isinstance(n, Call):
                fname = getattr(n.func, "id", None) or getattr(n.func, "name", None)
                targs = list(getattr(n, "type_args", []) or [])
                if fname in local and targs:
                    kind, params = local[fname]
                    call_rows.append((path, fname, kind, len(params), len(targs)))
    mismatch_ann = [r for r in ann_rows if r[3] != r[4]]
    mismatch_call = [r for r in call_rows if r[3] != r[4]]
    print(f"files_scanned={len(FILES)} parse_fail={len(parse_fail)} "
          f"generic_decls={len(decls)}")
    print("parse_fail_kinds=" + str(Counter(t for _, t, _ in parse_fail)))
    for p, t, m in parse_fail[:12]:
        print(f"  FAIL {p.relative_to(ROOT)} [{t}] {m}")
    print("decl_kinds=" + str(Counter(v[0] for v in decls.values())))
    print(f"ann_sites={len(ann_rows)} ann_arity_mismatch={len(mismatch_ann)}")
    for r in mismatch_ann[:12]:
        print(f"  ANN {r[0].relative_to(ROOT)} {r[1]} ({r[2]}) declares={r[3]} got={r[4]}")
    print(f"call_sites={len(call_rows)} call_arity_mismatch={len(mismatch_call)}")
    for r in mismatch_call[:12]:
        print(f"  CALL {r[0].relative_to(ROOT)} {r[1]} ({r[2]}) declares={r[3]} got={r[4]}")
    print("declared_names=" + ", ".join(sorted(decls)[:20]))
    print("CONCLUSION ann=%d ann_bad=%d call=%d call_bad=%d "
          % (len(ann_rows), len(mismatch_ann), len(call_rows), len(mismatch_call)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
