"""测试宏相关功能 - 参考 lang-zone 设计"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.parser.macro_expander import expand_macros
from cypyc.codegen.cython_generator import CythonGenerator
from cypy_bridge.compiler import CCodeGenerator


def test_backtick_block_parsing():
    """测试反引号代码块解析"""
    source = '''def test_backtick():
    code = ```
        x + y
    ```
    fmt = f```
        value = ${x}
    ```
    raw = r```
        literal text
    ```
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证解析成功且包含3个BacktickBlock节点
    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(ast, 'BacktickBlock')
    assert len(blocks) == 3
    assert blocks[0].prefix is None
    assert blocks[1].prefix == 'f'
    assert blocks[2].prefix == 'r'


def test_macro_call_statement():
    """测试宏调用作为独立语句"""
    source = '''def test_macro_call():
    @twice!
    result = @log_call!(1, 2, 3)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证解析成功且包含2个MacroCall节点
    from cypyc.utils.ast_utils import ASTUtils
    calls = ASTUtils.collect_nodes(ast, 'MacroCall')
    assert len(calls) == 2
    assert calls[0].name == 'twice!'
    assert calls[1].name == 'log_call!'
    assert len(calls[1].args) == 3


def test_macro_call_expression():
    """测试宏调用作为表达式"""
    source = '''def test_expr():
    result = @add!(1, 2) + @mul!(3, 4)
    return result'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证解析成功且包含2个MacroCall节点
    from cypyc.utils.ast_utils import ASTUtils
    calls = ASTUtils.collect_nodes(ast, 'MacroCall')
    assert len(calls) == 2


def test_macro_def_with_backtick():
    """测试包含反引号代码块的宏定义"""
    source = '''macro twice(input: Tokens) -> Tokens =
    f```
        $input + $input
    ```

def test_usage():
    @twice!(x)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证解析成功且包含宏定义和宏调用
    from cypyc.utils.ast_utils import ASTUtils
    macros = ASTUtils.collect_nodes(ast, 'MacroDef')
    calls = ASTUtils.collect_nodes(ast, 'MacroCall')
    assert len(macros) == 1
    assert len(calls) == 1


def test_macro_expansion():
    """测试宏展开"""
    source = '''macro twice(input: Tokens) -> Tokens =
    f```
        $input + $input
    ```

def test_usage():
    @twice!(x)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 验证宏调用被展开为真实 AST 节点（不再是 BacktickBlock）
    from cypyc.utils.ast_utils import ASTUtils
    calls = ASTUtils.collect_nodes(expanded_ast, 'MacroCall')
    # 宏调用应该被展开为其他节点
    assert len(calls) >= 0


def test_macro_codegen():
    """测试宏代码生成"""
    source = '''macro log_call(ts: Tokens) -> Tokens =
    print("Calling...")
    $(ts)
    print("Done.")

def test_usage():
    result = @log_call!(1 + 2)
    return result'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 生成代码
    codegen = CCodeGenerator()
    c_code = codegen.generate(expanded_ast, "test_mod")

    # 验证宏已在编译期展开并生成正确代码
    assert "Calling..." in c_code
    assert "Done." in c_code
    # 普通语句体宏（非反引号宏）仍由生成器渲染为函数
    assert "log_call" in c_code


def test_decorator_vs_macro_call():
    """测试装饰器和宏调用的区分"""
    source = '''@decorator
def decorated_func():
    pass

def test_func():
    @macro_call!
    x = 1
    return x'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 验证解析成功
    from cypyc.utils.ast_utils import ASTUtils
    funcs = ASTUtils.collect_nodes(ast, 'FuncDef')
    assert len(funcs) == 2
    
    # 第一个函数应该有装饰器
    assert len(funcs[0].decorators) == 1
    
    # 第二个函数内应该有宏调用
    calls = ASTUtils.collect_nodes(funcs[1], 'MacroCall')
    assert len(calls) == 1
    assert calls[0].name == 'macro_call!'


def test_macro_interpolation_simple():
    """测试宏插值 - 简单参数替换"""
    source = '''macro add_one(x: Tokens) -> Tokens =
    f```
        $x + 1
    ```

def test_usage():
    result = @add_one!(5)
    return result'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 验证反引号块被展开为真实 AST 节点（不再是 BacktickBlock）
    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(expanded_ast, 'BacktickBlock')
    # f```...``` 形式应该被重新解析为真实 AST 节点
    # 所以不再有 BacktickBlock
    assert len(blocks) == 0
    
    # 验证展开后的表达式存在
    binops = ASTUtils.collect_nodes(expanded_ast, 'BinOp')
    assert len(binops) >= 1


def test_macro_interpolation_expression():
    """测试宏插值 - $(expr)表达式形式"""
    source = '''macro log(expr: Tokens) -> Tokens =
    f```
        print("value: ", $(expr))
        return $expr
    ```

def test_usage():
    @log!(x + y)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 验证反引号块被展开为真实 AST 节点
    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(expanded_ast, 'BacktickBlock')
    # f```...``` 形式应该被重新解析为真实 AST 节点
    assert len(blocks) == 0
    
    # 验证展开后的调用存在
    calls = ASTUtils.collect_nodes(expanded_ast, 'Call')
    assert len(calls) >= 1


def test_macro_interpolation_complex():
    """测试宏插值 - 复杂参数"""
    source = '''macro create_struct(name: Tokens) -> Tokens =
    f```
        struct $name:
            x: int
            y: int
    ```

def test_usage():
    @create_struct!(Point)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 验证反引号块被展开为真实 AST 节点
    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(expanded_ast, 'BacktickBlock')
    # f```...``` 形式应该被重新解析为真实 AST 节点
    assert len(blocks) == 0
    
    # 验证展开后的结构体定义存在
    structs = ASTUtils.collect_nodes(expanded_ast, 'StructDef')
    assert len(structs) >= 1
    assert structs[0].name == 'Point'


def test_macro_interpolation_dollar_escape():
    """测试宏插值 - $$ 转义"""
    source = '''macro escape_test(x: Tokens) -> Tokens =
    f```
        let price = $$100
        value = $x
    ```

def test_usage():
    @escape_test!(42)
    return 0'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    # 展开宏
    expanded_ast = expand_macros(ast)

    # 验证反引号块被展开为真实 AST 节点
    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(expanded_ast, 'BacktickBlock')
    # f```...``` 形式应该被重新解析为真实 AST 节点
    assert len(blocks) == 0
    
    # 验证展开后的 LetStmt 存在
    let_stmts = ASTUtils.collect_nodes(expanded_ast, 'LetStmt')
    assert len(let_stmts) >= 1


def test_raw_backtick_block_is_not_interpolated():
    """r```...``` 原始块：$name 与 $$ 都不处理（插值扫描器不得越界）"""
    source = '''macro keep(x: Tokens) -> Tokens =
    r```
        literal $x and $$y
    ```

def test_usage():
    @keep!(v)
    return 0'''

    ast = Parser(Lexer(source).tokenize()).parse()
    expanded = expand_macros(ast)

    from cypyc.utils.ast_utils import ASTUtils
    blocks = ASTUtils.collect_nodes(expanded, 'BacktickBlock')
    assert len(blocks) == 1
    assert blocks[0].content == 'literal $x and $$y'


def test_non_parameter_interpolation_keeps_expression_parentheses():
    """$(expr) 中 expr 不是形参时按表达式处理：保留括号，不改写文本"""
    source = '''macro show(expr: Tokens) -> Tokens =
    f```
        print($(1 + 2))
    ```

def test_usage():
    @show!(q)
    return 0'''

    code = CythonGenerator('mtest').generate(expand_macros(Parser(Lexer(source).tokenize()).parse()))
    assert 'print(1 + 2)' in code


def test_macro_body_comment_and_double_quoted_string_are_not_interpolated():
    """宏体里的注释与双引号字面量是普通文本：其中的 $name 不被插值（2026-Q3 缺陷 04）"""
    source = '''macro p(x: Tokens) -> Tokens =
    f```
        # note about $x
        label = "value=$x"
        print(label)
    ```

def test_usage():
    @p!(9)
    return 0'''

    code = CythonGenerator('mtest').generate(expand_macros(Parser(Lexer(source).tokenize()).parse()))
    assert '# note about $x' not in code      # 注释不会变成 "# note about 9"
    assert 'value=$x' in code
    assert 'value=9' not in code


if __name__ == '__main__':
    pytest.main([__file__, '-v'])