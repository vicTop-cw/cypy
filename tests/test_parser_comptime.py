"""测试 comptime 编译期求值解析（参考 lang-zone 语法）"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_comptime_simple_expression():
    """测试简单编译期表达式（参考 lang-zone：comptime: expr）"""
    source = '''comptime: 2 + 3 * 4'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "ComptimeStmt"


def test_comptime_with_function_call():
    """测试编译期函数调用（参考 lang-zone：comptime: expr）"""
    source = '''comptime: calculate_size(10, 20)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "ComptimeStmt"


def test_comptime_in_function():
    """测试在函数内使用 comptime（参考 lang-zone：comptime: expr）"""
    source = '''def func():
    comptime: 1 + 1
    return 0'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    # 检查函数体中有 comptime 语句
    comptime_stmts = [s for s in func_def.body if hasattr(s, 'kind') and s.kind == "ComptimeStmt"]
    assert len(comptime_stmts) == 1


def test_comptime_with_variables():
    """测试编译期变量引用（参考 lang-zone：comptime: expr）"""
    source = '''let N: int = 100
comptime: N * 2'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 2
    assert ast.body[1].kind == "ComptimeStmt"


def test_comptime_block():
    """测试编译期块形式（参考 lang-zone）"""
    source = '''comptime:
    PI = 3.14159
    ANSWER = 42'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "ComptimeStmt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])