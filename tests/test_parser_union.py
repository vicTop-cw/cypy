"""测试联合类型解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_union_type_simple():
    """测试简单联合类型"""
    source = '''type Number = int | float'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    type_alias = ast.body[0]
    assert type_alias.kind == "TypeAlias"
    assert type_alias.name == "Number"
    assert type_alias.target.kind == "UnionType"
    assert len(type_alias.target.types) == 2


def test_union_type_three_types():
    """测试三种类型的联合"""
    source = '''type Result = int | float | None'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    type_alias = ast.body[0]
    assert type_alias.kind == "TypeAlias"
    assert type_alias.target.kind == "UnionType"
    assert len(type_alias.target.types) == 3


def test_union_type_in_function():
    """测试函数参数使用联合类型"""
    source = '''def add(a: int | float, b: int | float) -> int | float:
    return a + b'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.params[0].type_annotation.kind == "UnionType"
    assert func_def.params[1].type_annotation.kind == "UnionType"
    assert func_def.return_type.kind == "UnionType"


def test_union_type_with_generic():
    """测试联合类型与泛型组合"""
    source = '''type Maybe<T> = T | None'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    type_alias = ast.body[0]
    assert type_alias.kind == "TypeAlias"
    assert type_alias.target.kind == "UnionType"


def test_union_type_in_struct():
    """测试结构体字段使用联合类型"""
    source = '''struct Data:
    value: int | float | str'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    struct_def = ast.body[0]
    assert struct_def.kind == "StructDef"
    assert struct_def.fields[0].type_annotation.kind == "UnionType"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
