"""测试 match/case 模式匹配解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ArrayPattern


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


def test_match_struct_pattern_simple():
    """测试简单结构体解构模式 - Point { x, y }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match point:
    case Point { x, y }:
        print(x, y)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 2
    assert pattern.fields[0][0] == "x"
    assert pattern.fields[1][0] == "y"
    assert not pattern.has_ellipsis


def test_match_struct_pattern_custom_names():
    """测试自定义变量名的结构体解构模式 - Point { x: px, y: py }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match point:
    case Point { x: px, y: py }:
        print(px, py)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 2
    assert pattern.fields[0][0] == "x"
    assert pattern.fields[0][1].name == "px"
    assert pattern.fields[1][0] == "y"
    assert pattern.fields[1][1].name == "py"


def test_match_struct_pattern_with_ellipsis():
    """测试带省略号的结构体解构模式 - Point { x: px, .. }"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match point:
    case Point { x: px, .. }:
        print(px)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 1
    assert pattern.fields[0][0] == "x"
    assert pattern.fields[0][1].name == "px"
    assert pattern.has_ellipsis


def test_match_struct_pattern_mixed():
    """测试混合形式的结构体解构模式"""
    from cypyc.parser.parser import StructPattern
    
    source = '''match point:
    case Point { x, y: py, .. }:
        print(x, py)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, StructPattern)
    assert pattern.struct_name == "Point"
    assert len(pattern.fields) == 2
    assert pattern.fields[0][0] == "x"
    assert pattern.fields[0][1].name == "x"
    assert pattern.fields[1][0] == "y"
    assert pattern.fields[1][1].name == "py"
    assert pattern.has_ellipsis


def test_match_struct_pattern_codegen():
    """测试结构体解构模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''struct Point:
    x: int
    y: int

def test_match(p):
    match p:
        case Point { x, y }:
            return x + y
        case Point { x: px, .. }:
            return px'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case Point(x=x, y=y):" in code
    assert "case Point(x=px, **_):" in code


def test_match_array_pattern_fixed_length():
    """测试固定长度数组模式"""
    source = '''match arr:
    case [x, y, z]:
        print(x + y + z)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ArrayPattern)
    assert len(pattern.elements) == 3


def test_match_nested_array_pattern():
    """测试嵌套数组模式"""
    source = '''match arr:
    case [[a, b], [c, d]]:
        print(a, b, c, d)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ArrayPattern)
    assert len(pattern.elements) == 2
    assert isinstance(pattern.elements[0], ArrayPattern)
    assert isinstance(pattern.elements[1], ArrayPattern)
    assert len(pattern.elements[0].elements) == 2
    assert len(pattern.elements[1].elements) == 2


def test_match_mixed_array_pattern():
    """测试混合模式（变量+嵌套数组）"""
    source = '''match arr:
    case [x, [y, z]]:
        print(x, y, z)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ArrayPattern)
    assert len(pattern.elements) == 2
    assert pattern.elements[0].kind == "Pattern"
    assert pattern.elements[0].name == "x"
    assert isinstance(pattern.elements[1], ArrayPattern)
    assert len(pattern.elements[1].elements) == 2


def test_match_array_pattern_with_constants():
    """测试常量+变量混合数组模式"""
    source = '''match arr:
    case [1, x, 3]:
        print(x)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ArrayPattern)
    assert len(pattern.elements) == 3
    assert pattern.elements[0].kind == "Constant"
    assert pattern.elements[0].value == 1
    assert pattern.elements[1].kind == "Pattern"
    assert pattern.elements[1].name == "x"
    assert pattern.elements[2].kind == "Constant"
    assert pattern.elements[2].value == 3


def test_match_deeply_nested_array_pattern():
    """测试深层嵌套数组模式"""
    source = '''match arr:
    case [[[a]], b]:
        print(a, b)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    match_stmt = ast.body[0]
    assert len(match_stmt.cases) == 1
    pattern = match_stmt.cases[0].pattern
    assert isinstance(pattern, ArrayPattern)
    assert len(pattern.elements) == 2
    assert isinstance(pattern.elements[0], ArrayPattern)
    assert isinstance(pattern.elements[0].elements[0], ArrayPattern)
    assert pattern.elements[0].elements[0].elements[0].kind == "Pattern"
    assert pattern.elements[0].elements[0].elements[0].name == "a"
    assert pattern.elements[1].kind == "Pattern"
    assert pattern.elements[1].name == "b"


def test_match_array_pattern_codegen():
    """测试数组模式的代码生成"""
    from cypyc.codegen.cython_generator import CythonGenerator
    
    source = '''def test_match(arr):
    match arr:
        case [x, y, z]:
            return x + y + z
        case [[a, b], [c, d]]:
            return a + b + c + d
        case [1, x, 3]:
            return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    code = generator.generate(ast)
    
    assert "case [x, y, z]:" in code
    assert "case [[a, b], [c, d]]:" in code
    assert "case [1, x, 3]:" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
