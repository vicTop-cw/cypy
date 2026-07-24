"""测试 vec SIMD 向量类型解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_vec_list_form():
    """测试 vec 列表形式解析"""
    source = '''def func():
    v = vec![1, 2, 3, 4]
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 检查是否有 vec 字面量
    vec_literals = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'VecLiteral':
                vec_literals.append(stmt.value)
    assert len(vec_literals) == 1
    
    vec_lit = vec_literals[0]
    assert len(vec_lit.elements) == 4
    assert vec_lit.size == 4


def test_vec_repeat_form():
    """测试 vec 重复形式解析"""
    source = '''def func():
    v = vec![0; 4]
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    vec_literals = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'VecLiteral':
                vec_literals.append(stmt.value)
    assert len(vec_literals) == 1
    
    vec_lit = vec_literals[0]
    assert len(vec_lit.elements) == 1
    assert vec_lit.size == 4


def test_vec_with_expression_elements():
    """测试 vec 包含表达式元素"""
    source = '''def func(a: int, b: int):
    v = vec![a + b, a - b, a * b, a / b]
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    vec_literals = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'VecLiteral':
                vec_literals.append(stmt.value)
    assert len(vec_literals) == 1
    
    vec_lit = vec_literals[0]
    assert len(vec_lit.elements) == 4


def test_vec_size_8():
    """测试 vec 大小为 8"""
    source = '''def func():
    v = vec![1, 2, 3, 4, 5, 6, 7, 8]
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    
    vec_literals = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'VecLiteral':
                vec_literals.append(stmt.value)
    assert len(vec_literals) == 1
    
    vec_lit = vec_literals[0]
    assert vec_lit.size == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
