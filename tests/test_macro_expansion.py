"""反引号编译期宏（@name!(...)）展开回归测试。

这些测试覆盖此前宏展开器的缺陷：
1. 多语句反引号宏展开后整段丢失（被错误塞入单个表达式语句）；
2. 默认 Cython 编译器路径不支持反引号宏（仅 bridge 模式可用）；
3. 接入 expand_macros 后字符串模板宏（macro name = f"..."）仍应正常工作。
"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.parser.macro_expander import expand_macros
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.utils.ast_utils import ASTUtils


def _parse(src: str):
    return Parser(Lexer(src).tokenize()).parse()


def test_backtick_macro_multistmt_not_dropped():
    """回归：多语句反引号宏展开后不应整段丢失"""
    src = (
        "macro twice(input: Tokens) -> Tokens =\n"
        "    f```\n"
        "    print('twice: $input')\n"
        "    print('again: $input')\n"
        "    ```\n"
        "\n"
        "def demo(name: str):\n"
        "    @twice!(name)\n"
        "    return 0\n"
    )
    ast = _parse(src)
    code = CythonGenerator('mtest').generate(ast)
    assert "print('twice: name')" in code
    assert "print('again: name')" in code


def test_backtick_macro_interpolation_name():
    """$name 形式的简单插值"""
    src = (
        "macro wrap(input: Tokens) -> Tokens =\n"
        "    f```\n"
        "    log($input)\n"
        "    ```\n"
        "\n"
        "def demo():\n"
        "    @wrap!(value)\n"
        "    return 0\n"
    )
    ast = _parse(src)
    east = expand_macros(ast)
    # 反引号块应被替换为真实 AST（无残留 BacktickBlock）
    assert ASTUtils.collect_nodes(east, 'BacktickBlock') == []
    code = CythonGenerator('mtest').generate(east)
    assert 'log(value)' in code


def test_backtick_macro_expression_interpolation():
    """$(expr) 形式的表达式插值"""
    src = (
        "macro show(expr: Tokens) -> Tokens =\n"
        "    f```\n"
        "    print($(expr))\n"
        "    ```\n"
        "\n"
        "def demo():\n"
        "    @show!(a + b)\n"
        "    return 0\n"
    )
    ast = _parse(src)
    east = expand_macros(ast)
    code = CythonGenerator('mtest').generate(east)
    assert 'print(a + b)' in code


def test_string_template_macro_still_works():
    """接入 expand_macros 后，字符串模板宏（块形式）不应受影响"""
    src = (
        "macro dbl(ts: Tokens) =\n"
        "    f\"({ts} * 2)\"\n"
        "\n"
        "def demo(x: int) -> int:\n"
        "    let y: int = dbl(x)\n"
        "    return y\n"
    )
    ast = _parse(src)
    code = CythonGenerator('mtest').generate(ast)
    assert 'y: int = (x * 2)' in code


def test_plain_code_not_affected_by_macro_expansion():
    """不含宏的普通代码不应被宏展开器改动"""
    src = (
        "def add(a: int, b: int) -> int:\n"
        "    let s: int = a + b\n"
        "    return s\n"
    )
    ast = _parse(src)
    east = expand_macros(ast)
    code = CythonGenerator('mtest').generate(ast)
    assert 's: int = a + b' in code
    assert 'return s' in code
    # 展开前后 AST 顶层结构应保持一致
    assert len(east.body) == len(ast.body)
