"""反引号编译期宏（@name!(...)）展开回归测试。

这些测试覆盖此前宏展开器的缺陷：
1. 多语句反引号宏展开后整段丢失（被错误塞入单个表达式语句）；
2. 默认 Cython 编译器路径不支持反引号宏（仅 bridge 模式可用）；
3. 接入 expand_macros 后字符串模板宏（macro name = f"..."）仍应正常工作；
4. 同一反引号宏被多次调用时，因共享宏定义体被原地改写，后续调用会复用
   前一次调用的插值结果（log(a)/log(b) 都变成 log(a)）；
5. （2026-Q3 审计 T0r61.2.2）嵌套宏不递归展开、字符串实参不重新转义、
   插值扫到注释/字符串与已插入文本。
"""
import ast

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, Call, Constant, Name
from cypyc.parser.macro_expander import MacroExpander, expand_macros
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


def test_backtick_macro_multiple_calls_independent():
    """回归：同一反引号宏被多次调用时，各调用应使用各自的参数插值

    修复前因宏定义体被原地改写，第二次调用会复用第一次的插值结果
    （log(a) / log(b) 都变成 log(a)）。
    """
    src = (
        "macro inc(x: Tokens) -> Tokens =\n"
        "    f```\n"
        "    log($x)\n"
        "    ```\n"
        "\n"
        "def demo():\n"
        "    @inc!(a)\n"
        "    @inc!(b)\n"
        "    return 0\n"
    )
    ast = _parse(src)
    code = CythonGenerator('mtest').generate(ast)
    assert 'log(a)' in code
    assert 'log(b)' in code
    # 不应出现两次相同的 log(a)（即第二次不能复用第一次的插值）
    assert code.count('log(a)') == 1


# ==========================================================================
# 2026-Q3 审计 T0r61.2.2 回归：嵌套宏递归展开 / 字符串实参转义 / 插值扫描
# ==========================================================================

INNER_DEF = ('macro inner() -> Tokens =\n'
             '    f```\n'
             '    print("INNER")\n'
             '    ```\n\n')


def _demo_body(ast) -> str:
    code = CythonGenerator('m').generate(ast)
    return "\n".join(l for l in code.splitlines()
                     if l.startswith('def demo') or l.startswith('    '))


def test_nested_macro_in_macro_body_expands():
    """回归（缺陷 02）：宏体里嵌套 @inner!() 必须被展开，不留残余 MacroCall"""
    src = (INNER_DEF
           + "macro outer() -> Tokens =\n    f```\n    @inner!()\n    ```\n\n"
           + "def demo():\n    @outer!()\n    return 0\n")
    expanded = expand_macros(_parse(src))
    body = _demo_body(expanded)
    assert "print('INNER')" in body, body
    assert ASTUtils.collect_nodes(expanded, 'MacroCall') == []


def test_nested_macro_without_at_sign_expands():
    """回归（缺陷 02）：宏体里的 inner!()（无 @，解析成 Call(Name('inner!'))) 也要展开"""
    src = (INNER_DEF
           + "macro outer() -> Tokens =\n    f```\n    inner!()\n    ```\n\n"
           + "def demo():\n    @outer!()\n    return 0\n")
    expanded = expand_macros(_parse(src))
    body = _demo_body(expanded)
    assert "print('INNER')" in body, body
    assert 'inner!' not in body


def test_three_level_macro_chain_expands():
    """回归（缺陷 02）：a -> b -> c 三级链式宏一次遍历内全部展开"""
    src = (INNER_DEF.replace('print("INNER")', 'print("C")').replace('inner', 'ccc')
           + 'macro b() -> Tokens =\n    f```\n    @ccc!()\n    ```\n\n'
           + 'macro a() -> Tokens =\n    f```\n    @b!()\n    ```\n\n'
           + "def demo():\n    @a!()\n    return 0\n")
    expanded = expand_macros(_parse(src))
    assert "print('C')" in _demo_body(expanded)
    assert ASTUtils.collect_nodes(expanded, 'MacroCall') == []


def test_parametric_nested_macro_passes_arguments():
    """回归（缺陷 02）：带参宏嵌套调用时实参要透传到内层宏"""
    src = ("macro inner(x: Tokens) -> Tokens =\n    f```\n    log($x)\n    ```\n\n"
           + "macro outer(x: Tokens) -> Tokens =\n    f```\n    @inner!($x)\n    ```\n\n"
           + "def demo():\n    @outer!(v)\n    return 0\n")
    expanded = expand_macros(_parse(src))
    body = _demo_body(expanded)
    assert 'log(v)' in body, body
    assert 'log(x)' not in body


def test_self_recursive_macro_raises():
    """自引用宏必须显式报错（递归守卫不能被递归展开绕过）"""
    src = ("macro a() -> Tokens =\n    f```\n    @a!()\n    ```\n\n"
           + "def demo():\n    @a!()\n    return 0\n")
    with pytest.raises(ValueError, match='Recursive macro expansion'):
        expand_macros(_parse(src))


def test_mutually_recursive_macros_raise():
    """互相引用（a -> b -> a）同样报 ValueError，而不是无限递归"""
    src = ("macro a() -> Tokens =\n    f```\n    @b!()\n    ```\n\n"
           + "macro b() -> Tokens =\n    f```\n    @a!()\n    ```\n\n"
           + "def demo():\n    @a!()\n    return 0\n")
    with pytest.raises(ValueError, match='Recursive macro expansion'):
        expand_macros(_parse(src))


TEMPLATE_G = ("macro G(x: Tokens) -> Tokens =\n"
              "    f```\n"
              "    f($x)\n"
              "    ```\n\n"
              "def demo():\n"
              "    @G!(%s)\n"
              "    return 0\n")


def _generated_arg_line(src):
    """取 demo() 里 f(...) 那一行的实参文本（供字符串实参断言复用）"""
    code = CythonGenerator('m').generate(_parse(src))
    for line in code.splitlines():
        if line.startswith('    f(') and line.endswith(')'):
            return line[len('    f('):-1]
    return None


@pytest.mark.parametrize("arg_src,expected_value", [
    ('"a,b"', 'a,b'),                                   # 审计示例：本来就正常
    ('"say \\"hi\\""', 'say "hi"'),                     # 内嵌引号
    ('"c:\\\\path"', 'c:\\path'),                       # 反斜杠
    ('"line1\\nline2"', 'line1\nline2'),                # 换行
])
def test_string_argument_survives_roundtrip(arg_src, expected_value):
    """回归（缺陷 03）：字符串实参重新序列化时必须再转义，语句不得被静默丢弃"""
    src = TEMPLATE_G % arg_src
    expanded = expand_macros(_parse(src))
    # 展开后不应留下无法解析的反引号块（旧实现会降级成 BacktickBlock 并丢整条语句）
    assert ASTUtils.collect_nodes(expanded, 'BacktickBlock') == []
    arg_text = _generated_arg_line(src)
    assert arg_text is not None, "macro call statement was silently dropped"
    assert ast.literal_eval(arg_text) == expected_value


def test_fstring_argument_keeps_prefix():
    """回归（缺陷 03）：f"..." 实参的 f 前缀不能在插值时丢失"""
    src = TEMPLATE_G % 'f"v={x}"'
    expanded = expand_macros(_parse(src))
    assert ASTUtils.collect_nodes(expanded, 'BacktickBlock') == []
    arg_text = _generated_arg_line(src)
    assert arg_text is not None
    assert arg_text.lower().startswith('f'), arg_text
    assert ast.literal_eval(arg_text[1:]) == 'v={x}'


def test_arg_to_code_escapes_and_ast_to_code_shares_serializer():
    """回归（缺陷 03）：:366 / :391 / :377 三条分支共用同一个字面量序列化器"""
    ex = MacroExpander()
    assert ast.literal_eval(ex._arg_to_code(Constant('say "hi"'))) == 'say "hi"'
    assert ast.literal_eval(ex._arg_to_code(Constant('c:\\path'))) == 'c:\\path'
    assert ast.literal_eval(ex._arg_to_code(Constant("it's"))) == "it's"
    # 裸字符串实参也要带引号，否则 "a,b" 会展开成两个参数
    assert ast.literal_eval(ex._arg_to_code('a,b')) == 'a,b'
    # :391 的 AST 分支同样转义
    assert ast.literal_eval(ex._ast_to_code(Constant('say "hi"'))) == 'say "hi"'
    assert ex._ast_to_code(Call(Name('f'), [Constant('a"b')])) == "f('a\"b')"
    # f 前缀被保留；其余前缀（r/b/u）词法上已按普通字符串解码，不再重复转义
    assert ex._arg_to_code(Constant('v={x}', prefix='f')) == 'f"v={x}"'



def test_interpolation_does_not_rescan_inserted_text():
    """回归（缺陷 04）：$(x) 展开出的实参文本不能再被 $name pass 扫一遍"""
    arg = Constant('a$x')
    ex = MacroExpander()
    assert ex._substitute_interpolations("print($(x))", [arg], [{"name": "x"}]) == 'print("a$x")'
    src = ("macro t(x: Tokens) -> Tokens =\n    f```\n    print($(x))\n    ```\n\n"
           "def demo():\n    @t!(\"a$x\")\n    return 0\n")
    expanded = expand_macros(_parse(src))
    assert ASTUtils.collect_nodes(expanded, 'BacktickBlock') == []
    assert 'print' in _demo_body(expanded)


def test_interpolation_skips_comments_and_double_quoted_strings():
    """回归（缺陷 04）：注释与双引号字面量里的 $name 是普通文本，不参与插值"""
    ex = MacroExpander()
    out = ex._substitute_interpolations('# note about $x\nlabel = "value=$x"',
                                        [Constant(9)], [{"name": "x"}])
    assert out == '# note about $x\nlabel = "value=$x"'


def test_interpolation_inside_single_quoted_string_is_kept():
    """兼容性钉桩：单引号字面量内仍插值（test_backtick_macro_multistmt_not_dropped 依赖）"""
    ex = MacroExpander()
    out = ex._substitute_interpolations("print('twice: $x')", [Name('name')], [{"name": "x"}])
    assert out == "print('twice: name')"


def test_dollar_escape_still_works_in_substitution():
    """$$ 转义必须继续有效（tests/test_macro_features.py 依赖）"""
    ex = MacroExpander()
    out = ex._substitute_interpolations("let price = $$100\nlet v = $x",
                                        [Constant(42)], [{"name": "x"}])
    assert out == "let price = $100\nlet v = 42"


def test_macro_call_with_undefined_macro_is_left_alone():
    """未定义的宏（含 name!() 形式）不得被展开或丢弃"""
    src = "def demo():\n    unknown!()\n    @nope!(1)\n    return 0\n"
    expanded = expand_macros(_parse(src))
    assert 'unknown!()' in _demo_body(expanded) or 'unknown!' in _demo_body(expanded)

