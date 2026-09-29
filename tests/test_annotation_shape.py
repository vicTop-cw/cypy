"""注解形态闭集的调用面锁（SYNTAX/02 R7 补条款；缺陷账本 BUG-34 / BUG-108）。

BUG-108 的原始形态：`xs: [int]` 被 parser 编成 `Constant(value=[Name(int)])`，分析器不认，
生成器末路 `str(node)` 于是把 `xs: Constant(line=2, col=9) = [1, 2, 3]` 写进 .pyx，
产物必编译失败而 CLI 仍回 rc=0（零诊断）。

本文件把三件事分开锁住，避免「只是把门拆了」式的假绿：
1. 文档给出的合法形态一律 **无诊断**（否则收紧会误伤真实语料）；
2. 三种字面量形态一律 **必诊断**，且文案带行列并点名正确写法；
3. 产物字节里永不得出现 AST 节点 repr（`line=` 片段），未知形态退化为 `object`；
4. 对照组：`comptime: [1, 2]` 的行内形式携带的是表达式而不是注解，必须仍然零诊断。
"""

from __future__ import annotations

import re

import pytest

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

VALID_FORMS = {
    "list_int": "def f() -> int:\n    xs: list<int> = [1, 2, 3]\n    return 0\n",
    "dict_str_int": "def f() -> int:\n    m: dict<str, int> = {\"a\": 1}\n    return 0\n",
    "tuple_int_str": "def f() -> int:\n    p: tuple<int, str> = (1, \"a\")\n    return 0\n",
    "pointer_char": "def f() -> int:\n    buf: *char = malloc(8)\n    return 0\n",
    "union": "def f(v: int) -> int:\n    u: int | str = v\n    return 0\n",
    "plain_name": "def f() -> int:\n    n: int = 1\n    return 0\n",
}

INVALID_FORMS = {
    "bracket_list": ("def f() -> int:\n    xs: [int] = [1, 2, 3]\n    return 0\n", 2),
    "paren_tuple": ("def f() -> int:\n    p: (int, str) = (1, \"a\")\n    return 0\n", 2),
    "brace_dict": ("def f() -> int:\n    m: {str: int} = {\"a\": 1}\n    return 0\n", 2),
    "bare_literal": ("def f() -> int:\n    n: 5 = 5\n    return 0\n", 2),
}


def parse(source: str):
    return Parser(list(Lexer(source).tokenize())).parse()


def errors_of(source: str):
    checker = TypeChecker()
    checker.check(parse(source))
    return checker.errors


@pytest.mark.parametrize("name", sorted(VALID_FORMS))
def test_documented_forms_are_clean(name):
    assert errors_of(VALID_FORMS[name]) == [], name


@pytest.mark.parametrize("name", sorted(INVALID_FORMS))
def test_literal_forms_are_diagnosed_with_position(name):
    source, line = INVALID_FORMS[name]
    errs = errors_of(source)
    assert errs, f"{name} 未产生任何诊断（BUG-108 的静默形态复发）"
    assert any("Invalid type annotation" in e for e in errs), errs
    assert any(re.search(rf"at {line}:\d+", e) for e in errs), f"诊断行列不对：{errs}"
    assert any("list<int>" in e or "tuple<int, int>" in e or "dict<str, int>" in e
               or "类型名" in e for e in errs), f"诊断没点名正确写法：{errs}"


def test_product_never_carries_ast_repr():
    """生成器末路不得把节点 repr 写进 .pyx（原缺陷的直接指纹）。"""
    gen = CythonGenerator()
    code = gen.generate(parse(INVALID_FORMS["bracket_list"][0]))
    assert "line=" not in code, [ln for ln in code.splitlines() if "line=" in ln]
    assert "Constant(" not in code, code[:200]


def test_unknown_annotation_degrades_to_object():
    gen = CythonGenerator()
    code = gen.generate(parse(INVALID_FORMS["brace_dict"][0]))
    assert any("m: object" in ln for ln in code.splitlines()), code


def test_comptime_inline_form_is_not_an_annotation():
    """对照组：`comptime: [1, 2]` 是表达式不是注解，闭集校验必须整类跳过。"""
    assert errors_of("def f() -> int:\n    comptime: [1, 2]\n    return 1\n") == []


def test_this_file_collects_its_locks():
    import inspect

    collected = [n for n, f in globals().items() if n.startswith("test_") and inspect.isfunction(f)]
    assert len(collected) >= 6, f"只收集到 {len(collected)} 条：{sorted(collected)}"
