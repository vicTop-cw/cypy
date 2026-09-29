"""R10 回归锁：调用点类型实参（SYNTAX/11「调用点的类型实参」规则 1-5）。

钉住的三件产品事实（都是本轮实测从"坏形态"翻过来的）：
1. 产物必须**擦除**类型实参 —— 旧形态 `(类型名(), f(x))[1]` 的运行期含义是把类型名当零参函数调用，
   对带必填字段的 struct/class 必抛 TypeError，而类型检查与生成阶段都不报错（静默错误产物）；
2. 多项类型实参 `pair<int, str>(…)` 必须能解析（旧形态是 `Unexpected token COMMA`）；
3. 元数与"非泛型被调方挂实参"要有诊断，且显式实参参与代入（`identity<int>("Alice")` 必须报错）。
"""

from __future__ import annotations

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

IDENT = """def identity<T>(x: T) -> T:
    return x


def f() -> int:
    n: int = identity<int>(42)
    return n
"""
PAIR = """def pair<T, U>(first: T, second: U) -> tuple<T, U>:
    return (first, second)


def f() -> int:
    p: tuple<int, str> = pair<int, str>(42, "a")
    return 0
"""
USER_TYPE = """struct Foo:
    value: int


def identity<T>(x: T) -> T:
    return x


def f():
    v = Foo(value=1)
    return identity<Foo>(v)
"""
BOX_CTOR = """struct Box<T>:
    value: T


def f():
    b = Box<int>(value=100)
    return b.value
"""


def _parse(src: str):
    return Parser(list(Lexer(src).tokenize())).parse()


def _check(src: str) -> list:
    tc = TypeChecker()
    tc.check(_parse(src))
    return [e for e in tc.errors if e.strip()]


def _gen(src: str) -> str:
    return CythonGenerator().generate(_parse(src))


def test_callsite_type_arg_is_erased_in_product():
    code = _gen(IDENT)
    assert "n: int = identity(42)" in code
    # 反面：旧形态对类型名插一次零参调用，运行期才会炸
    assert "(int(), identity" not in code


def test_callsite_type_arg_on_user_type_is_erased():
    code = _gen(USER_TYPE)
    assert "return identity(v)" in code
    assert "(Foo()," not in code
    assert "identity[Foo]" not in code


def test_multiple_type_arguments_parse_and_erase():
    code = _gen(PAIR)
    assert "pair(42, 'a')" in code
    assert "pair<int" not in code
    assert _check(PAIR) == []


def test_generic_struct_ctor_type_arg_erased():
    code = _gen(BOX_CTOR)
    assert "b = Box(value=100)" in code
    assert "(int()," not in code


def test_type_argument_count_mismatch_is_reported_with_location():
    src = ('def pair<T, U>(first: T, second: U) -> tuple<T, U>:\n    return (first, second)\n\n\n'
           'def f() -> int:\n    return pair<int>(42)\n')
    errs = _check(src)
    assert any("Type argument count mismatch: 'pair' declares 2 type parameter(s), got 1" in e for e in errs)
    assert any("at 6:12" in e for e in errs), errs


def test_type_arguments_on_non_generic_are_reported():
    src = 'def mk(a: int) -> int:\n    return a\n\n\ndef f() -> int:\n    return mk<int>(1)\n'
    errs = _check(src)
    assert any("Type arguments on non-generic 'mk'" in e for e in errs), errs


def test_explicit_type_arg_overrides_inference():
    src = ('def identity<T>(x: T) -> T:\n    return x\n\n\n'
           'def f() -> str:\n    s: str = identity<int>("Alice")\n    return s\n')
    errs = _check(src)
    assert any("Type mismatch: expected str, got int" in e for e in errs), errs


def test_explicit_type_arg_still_checked_against_constraint():
    src = ('def process<T: int | float>(value: T) -> T:\n    return value\n\n\n'
           'def f() -> str:\n    return process<str>("hello")\n')
    errs = _check(src)
    assert any("Generic constraint violation" in e for e in errs), errs


def test_less_than_operator_is_not_swallowed_by_type_arg_lookahead():
    # 对照半边：`len(xs) < len(ys)` 里的 `<` 不是类型实参表，新前视必须原样交回比较运算
    src = ('def f(xs: list<int>, ys: list<int>) -> int:\n'
           '    if len(xs) < len(ys):\n        return 1\n    return 0\n')
    assert _check(src) == []
    assert "len(xs) < len(ys)" in _gen(src)
