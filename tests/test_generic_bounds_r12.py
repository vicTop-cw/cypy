"""R12 回归锁：泛型声明界在使用侧的判定（SYNTAX/11「类型约束」+「泛型类的判定口径」规则 3/4，BUG-129）。

钉住四件产品事实：
1. 注解位与显式类型实参构造位的类型实参要过声明界 —— 联合界 / 单名界 / trait 界三类各配
   "违界必红 + 合界必绿"的成对半边（只验正例的话，把界判定整个删掉也能全绿）；
2. **一份判定三处用**：三处使用位都走 `TypeChecker._check_generic_constraint`，
   结构体字面量位原来自带一份只认单名界的窄复制 ⇒ 摘掉，且用源码针盯住它不许长回来；
3. 违界与元数是两条独立判据，同时出现时都要在册，不许一条遮一条；
4. 构造位**没写**类型实参时不做推断 ⇒ 必须 0 诊断（那一面挂在 BUG-135，不许冒充已完成）。
"""

from __future__ import annotations

import inspect
import re

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

NUM_CLASS = (
    "class Num<T: int | float>:\n    v: T\n\n" "    def get(self) -> T:\n        return self.v\n\n"
)
NUM_STRUCT = "struct NumS<T: int | float>:\n    v: T\n\n"
INT_ONLY = "struct One<T: int>:\n    v: T\n\n"
SHOW_TRAIT = "trait Show:\n    def show(self) -> int\n\n"
IMPL_SHOW = (
    "class Impl:\n    v: int\n\n\n"
    "impl Show for Impl:\n    def show(self) -> int:\n        return 1\n\n"
)
ONLY_TRAIT = (
    "class Only<T: Show>:\n    v: T\n\n" "    def pick(self) -> T:\n        return self.v\n\n"
)


def wrap(decl: str, body: str) -> str:
    return decl + "\n\n" + body


def errors(src: str) -> list[str]:
    tc = TypeChecker()
    tc.check(Parser(list(Lexer(src).tokenize())).parse())
    return list(tc.errors)


def violations(src: str) -> list[str]:
    return [e for e in errors(src) if "Generic constraint violation" in e]


def line_of(src: str, needle: str) -> int:
    lines = src.splitlines()
    hits = [i + 1 for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, f"锚点在源里必须唯一命中，实际 {hits}"
    return hits[0]


# —— 规则 1：注解位（class 与 struct 两形同源）——


def test_annotation_position_rejects_union_bound_violation():
    src = wrap(NUM_CLASS, "def f():\n    let x: Num<str> = Num(1)\n    return 0\n")
    v = violations(src)
    assert len(v) == 1, src
    assert "does not satisfy constraint 'int | float'" in v[0]
    assert "(allowed: int | float)" in v[0] and "for parameter 'T'" in v[0]


def test_annotation_position_accepts_union_bound_member():
    for arg in ("int", "float"):
        src = wrap(NUM_CLASS, f"def f():\n    let x: Num<{arg}> = Num(1)\n    return 0\n")
        assert violations(src) == [], (arg, errors(src))


def test_annotation_position_rejects_on_struct_form_too():
    src = wrap(NUM_STRUCT, "def f():\n    let x: NumS<str> = NumS(1)\n    return 0\n")
    assert len(violations(src)) == 1, src


def test_struct_annotation_bound_pair_accepts_declared_member():
    src = wrap(NUM_STRUCT, "def f():\n    let x: NumS<float> = NumS(1)\n    return 0\n")
    assert violations(src) == [], errors(src)


def test_bound_diagnostic_points_at_the_annotation_site():
    """诊断的行列要指向写下类型实参那一行 —— 不钉死字面值，按源文本反解（行号偏移另有 BUG-126 的账）。"""
    src = wrap(NUM_CLASS, "def f():\n    let x: Num<str> = Num(1)\n    return 0\n")
    want = line_of(src, "let x: Num<str>")
    got = [
        int(m.group(1))
        for m in re.finditer(r"reported at line (\d+), col (\d+)", " ".join(violations(src)))
    ]
    assert got == [want], (want, got)


def test_multi_parameter_bounds_judge_each_position():
    decl = "class Two<T: int | float, U: str>:\n    a: T\n    b: U\n\n"
    bad = wrap(decl, 'def f():\n    let x: Two<int, int> = Two(1, "s")\n    return 0\n')
    v = violations(bad)
    assert len(v) == 1 and "for parameter 'U'" in v[0], (v, errors(bad))
    ok = wrap(decl, 'def f():\n    let x: Two<float, str> = Two(1, "s")\n    return 0\n')
    assert violations(ok) == [], errors(ok)


# —— 规则 1b：显式类型实参的构造位 ——


def test_explicit_type_args_at_constructor_reject_violation():
    src = wrap(INT_ONLY, 'def f():\n    b = One<str>(v="s")\n    return 0\n')
    v = violations(src)
    assert len(v) == 1 and "in call to 'One'" in v[0], (v, errors(src))


def test_explicit_type_args_at_constructor_accept_member():
    src = wrap(INT_ONLY, "def f():\n    b = One<int>(v=1)\n    return 0\n")
    assert violations(src) == [], errors(src)


# —— 规则 1c：trait 界（实现要显式 `impl … for …` 才算）——


def test_trait_bound_rejects_type_without_impl():
    src = wrap(
        SHOW_TRAIT + IMPL_SHOW + ONLY_TRAIT,
        "def f():\n    let x: Only<int> = Only(1)\n    return 0\n",
    )
    v = violations(src)
    assert len(v) == 1 and "does not implement trait 'Show'" in v[0], (v, errors(src))


def test_trait_bound_accepts_registered_impl():
    src = wrap(
        SHOW_TRAIT + IMPL_SHOW + ONLY_TRAIT,
        "def f():\n    let x: Only<Impl> = Only(1)\n    return 0\n",
    )
    assert violations(src) == [], errors(src)


# —— 规则 2：一份判定三处用（窄复制不许长回来）——


def test_struct_literal_path_reuses_the_shared_checker():
    src = "def f():\n    return 0\n"
    lit = inspect.getsource(TypeChecker._visit_StructLiteral)
    assert "_check_declared_bounds" in lit, "字面量位又用回本地窄判定 ⇒ 联合界会静默放行"
    assert "does not satisfy constraint" not in lit, "窄复制的消息合成点不许留在字面量位"
    assert errors(src) == []  # 顺带确认探针没有把源污染成诊断


def test_union_bound_now_rejects_at_literal_inference_too():
    """字面量位经注解参与判定的那半边：`let a: NumS<str> = NumS(v="s")` 必须红。"""
    src = wrap(NUM_STRUCT, 'def f():\n    let a: NumS<str> = NumS(v="s")\n    return 0\n')
    assert len(violations(src)) == 1, errors(src)


def test_struct_literal_position_rejects_union_bound():
    """`Name {field: value}` 形态走 `_visit_StructLiteral`：窄复制时期联合界静默放行，现在必红。"""
    bad = wrap(NUM_STRUCT, 'def f():\n    a = NumS {v: "s"}\n    return 0\n')
    v = violations(bad)
    assert len(v) == 1 and "does not satisfy constraint 'int | float'" in v[0], errors(bad)
    ok = wrap(NUM_STRUCT, "def f():\n    a = NumS {v: 1}\n    return 0\n")
    assert violations(ok) == [], errors(ok)


def test_struct_literal_position_single_name_bound_pair():
    bad = wrap(INT_ONLY, 'def f():\n    a = One {v: "s"}\n    return 0\n')
    assert len(violations(bad)) == 1, errors(bad)
    ok = wrap(INT_ONLY, "def f():\n    a = One {v: 1}\n    return 0\n")
    assert violations(ok) == [], errors(ok)


# —— 规则 3：违界与元数各归各账，同时出现都要在册 ——


def test_arity_and_bound_diagnostic_coexist():
    src = wrap(NUM_CLASS, "def f():\n    let x: Num<str, int> = Num(1)\n    return 0\n")
    errs = errors(src)
    assert len(errs) == 2, errs
    assert any("Type argument count mismatch" in e for e in errs)
    assert any("Generic constraint violation" in e for e in errs)


def test_violation_does_not_hide_downstream_substitution():
    src = wrap(NUM_CLASS, "def f() -> int:\n    let x: Num<str> = Num(1)\n    return x.get()\n")
    errs = errors(src)
    assert len(errs) == 2, errs
    assert any("Return type mismatch: expected int, got str" in e for e in errs)


# —— 规则 4：未写类型实参的构造位不做推断（BUG-135 的活证据，不许冒充已完成）——


def test_inferred_constructor_position_still_unjudged():
    src = wrap(INT_ONLY, 'def f():\n    b = One(v="s")\n    return 0\n')
    assert violations(src) == [], errors(src)


def test_codegen_ignores_type_arguments_with_bound_violation():
    """产物面：违界不改出码形状 —— 类型实参仍被擦除，不许把界判定漏进产物。"""
    src = wrap(INT_ONLY, 'def f():\n    b = One<str>(v="s")\n    return 0\n')
    ast = Parser(list(Lexer(src).tokenize())).parse()
    code = CythonGenerator().generate(ast)
    assert "struct One" not in code
    assert "<str>" not in code and "One<str>" not in code
    assert re.search(r"\bOne\b", code)
