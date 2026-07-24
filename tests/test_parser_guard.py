"""测试 guard 守卫表达式解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, GuardStmt, Name, Constant, BinOp


def test_guard_single_line():
    """测试单行 guard 语法能被正确解析"""
    source = '''def test():
    guard x != 0 else None
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.body) == 2
    
    guard_stmt = func_def.body[0]
    assert isinstance(guard_stmt, GuardStmt)
    assert not guard_stmt.is_let
    assert guard_stmt.let_target is None
    
    # 验证条件表达式
    assert isinstance(guard_stmt.test, BinOp)
    assert guard_stmt.test.op == "!="
    
    # 验证 else 分支是表达式（单行）
    assert isinstance(guard_stmt.orelse, Name)
    assert guard_stmt.orelse.id == "None"


def test_guard_multi_line():
    """测试多行 guard 语法能被正确解析"""
    source = '''def test():
    guard x != 0 else:
        print("error")
        None
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    guard_stmt = func_def.body[0]
    
    assert isinstance(guard_stmt, GuardStmt)
    assert not guard_stmt.is_let
    
    # 验证 else 分支是块（多行）
    assert isinstance(guard_stmt.orelse, list)
    assert len(guard_stmt.orelse) == 2


def test_guard_let():
    """测试 guard let 绑定语法能被正确解析"""
    source = '''def test():
    guard let v = get_value() else None
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    guard_stmt = func_def.body[0]
    
    assert isinstance(guard_stmt, GuardStmt)
    assert guard_stmt.is_let
    assert isinstance(guard_stmt.let_target, Name)
    assert guard_stmt.let_target.id == "v"


def test_guard_invalid_outside_function():
    """测试 guard 在函数外使用会报错"""
    source = '''guard x != 0 else None'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    
    with pytest.raises(ValueError, match="must be used inside a function"):
        parser.parse()


def test_guard_orelse_not_present():
    """测试缺少 else 会报错"""
    source = '''def test():
    guard x != 0'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    
    with pytest.raises(ValueError):
        parser.parse()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
