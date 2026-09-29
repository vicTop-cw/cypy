"""R12 探针：构造位的三种写法各自的实测形态（BUG-129 关闭面 / BUG-135 空档面的分界证据）。

写这张件的目的是**不让自己把空档说成已完成**：`One(v="s")` 这类"不写类型实参"的构造位
到底判不判、成员类型代不代入，必须用实测的三种写法并排钉住，而不是凭 `_visit_StructLiteral`
的存在就假定"字面量位会推断"。同时把 AST 形状一起打出来，说明为什么它是 `Call` 而不是 StructLiteral。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402

DECL_S = "struct One<T: int>:\n    v: T\n\n"
DECL_C = "class OneC<T: int>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"
SHAPES = [
    ("S1 构造位不写类型实参（struct）", DECL_S + 'def f():\n    b = One(v="s")\n    return 0\n', "b = One(v="),
    ("S2 构造位不写类型实参（class）", DECL_C + 'def f():\n    b = OneC(v="s")\n    return 0\n', "b = OneC(v="),
    ("S3 注解位写违界实参", DECL_S + 'def f():\n    let a: One<str> = One(v="s")\n    return 0\n',
     "let a: One<str>"),
    ("S4 构造位写显式违界实参", DECL_S + 'def f():\n    b = One<str>(v="s")\n    return 0\n', "b = One<str>("),
    ("S5 成员读取的类型代入（class）", DECL_C + 'def f() -> int:\n    let b: OneC<str> = OneC(v="s")\n'
                                            "    return b.get()\n", "let b: OneC<str>"),
    ("S6 合界的对照面（struct，必须 0 诊断）", DECL_S + 'def f():\n    let a: One<int> = One(v=1)\n'
                                                    "    return 0\n", "let a: One<int>"),
]


def ast_shape(src: str, needle: str) -> str:
    """按源码行定位那条语句，打出它的值节点形状（说明构造位是 Call 而不是 StructLiteral）。"""
    lines = src.splitlines()
    want = next((i for i, ln in enumerate(lines) if needle in ln), None)
    if want is None:
        return "(锚点在源里找不到)"
    lineno = want + 1
    ast = Parser(list(Lexer(src).tokenize())).parse()
    for st in ast.body:
        for inner in getattr(st, "body", []) or []:
            if getattr(inner, "line", None) != lineno:
                continue
            v = getattr(inner, "value", None)
            if v is None:
                continue
            fn = getattr(v, "func", None)
            return (f"{inner.__class__.__name__}@{lineno} -> {v.__class__.__name__}"
                    f"(func={getattr(fn, 'kind', fn and fn.__class__.__name__)}."
                    f"{getattr(fn, 'id', None)}, args={_brief(getattr(v, 'args', None))},"
                    f" type_args={getattr(v, 'type_args', None)!r})")
    return f"(没找到行号 {lineno} 的语句节点)"


def _brief(args) -> str:
    out = []
    for a in args or []:
        if isinstance(a, tuple):
            out.append(f"kw {a[0]}={a[1].__class__.__name__}")
        else:
            out.append(a.__class__.__name__)
    return ",".join(out)


def main() -> int:
    bad = 0
    for name, src, needle in SHAPES:
        ast = Parser(list(Lexer(src).tokenize())).parse()
        tc = TypeChecker()
        tc.check(ast)
        errs = list(tc.errors)
        v = [e for e in errs if "constraint" in e]
        print(f"=== {name}")
        print(f"    AST: {ast_shape(src, needle)}")
        print(f"    errors={len(errs)} 违界={len(v)}")
        for e in errs:
            print(f"      - {e}")
        if name.startswith("S6") and errs:
            bad += 1
        if name.startswith(("S1", "S2")) and v:
            bad += 1  # 这两条是 BUG-135 的"当前不判"证据，若哪天判了要改单，不能悄悄漂
        if name.startswith(("S3", "S4")) and len(v) != 1:
            bad += 1
    print(f"CONCLUSION probe=r12_ctor shapes={len(SHAPES)} 与预期形态不符={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
