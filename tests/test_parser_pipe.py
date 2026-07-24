"""测试管道操作符(|>)解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_pipe_simple():
    """测试简单管道表达式 - x |> f 转换为 f(x)"""
    source = '''result = x |> f'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assign = ast.body[0]
    assert assign.kind == "Assign"
    # x |> f 应该转换为 f(x)
    call = assign.value
    assert call.kind == "Call"
    assert call.func.id == "f"
    assert len(call.args) == 1
    assert call.args[0].id == "x"


def test_pipe_with_call():
    """测试管道带参数 - x |> f(y, z) 转换为 f(x, y, z)"""
    source = '''result = x |> f(y, z)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assign = ast.body[0]
    # x |> f(y, z) 应该转换为 f(x, y, z)
    call = assign.value
    assert call.kind == "Call"
    assert call.func.id == "f"
    assert len(call.args) == 3
    assert call.args[0].id == "x"  # x 成为第一个参数
    assert call.args[1].id == "y"
    assert call.args[2].id == "z"


def test_pipe_chain():
    """测试管道链 - x |> f |> g |> h 转换为 h(g(f(x)))"""
    source = '''result = x |> f |> g |> h'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assign = ast.body[0]
    # x |> f |> g |> h 应该转换为 h(g(f(x)))
    call_h = assign.value
    assert call_h.kind == "Call"
    assert call_h.func.id == "h"
    assert len(call_h.args) == 1
    
    call_g = call_h.args[0]
    assert call_g.kind == "Call"
    assert call_g.func.id == "g"
    assert len(call_g.args) == 1
    
    call_f = call_g.args[0]
    assert call_f.kind == "Call"
    assert call_f.func.id == "f"
    assert len(call_f.args) == 1
    assert call_f.args[0].id == "x"


def test_pipe_in_function():
    """测试函数返回语句中的管道"""
    source = '''def process(x):
    return x |> f |> g'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    return_stmt = func_def.body[0]
    # x |> f |> g 应该转换为 g(f(x))
    call_g = return_stmt.value
    assert call_g.kind == "Call"
    assert call_g.func.id == "g"


def test_pipe_with_complex_expression():
    """测试复杂表达式中的管道"""
    source = '''result = (a + b) * c |> f'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assign = ast.body[0]
    call = assign.value
    assert call.kind == "Call"
    assert call.func.id == "f"
    assert len(call.args) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
