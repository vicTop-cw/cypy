"""测试 match/case 模式匹配解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_match_simple():
    """测试简单 match/case"""
    source = '''match x:
    case 1:
        print("one")
    case 2:
        print("two")
    else:
        print("other")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 2
    assert match_stmt.orelse is not None


def test_match_with_if_guard():
    """测试带条件守卫的 case"""
    source = '''match x:
    case n if n > 0:
        print("positive")
    case n if n < 0:
        print("negative")
    else:
        print("zero")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert match_stmt.kind == "MatchStmt"
    assert len(match_stmt.cases) == 2


def test_match_wildcard():
    """测试通配符模式"""
    source = '''match x:
    case 1:
        pass
    case _:
        pass'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 2


def test_match_list_pattern():
    """测试列表模式"""
    source = '''match lst:
    case [a, b]:
        print(a + b)
    case [a, b, c]:
        print(a + b + c)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 2


def test_match_tuple_pattern():
    """测试元组模式"""
    source = '''match point:
    case (x, y):
        print(x, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1


def test_match_or_pattern():
    """测试 OR 模式"""
    source = '''match x:
    case 1 | 2 | 3:
        print("small")
    case _:
        print("large")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
