"""测试 guard 守卫表达式代码生成"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_bridge.compiler import CCodeGenerator


def test_guard_single_line_codegen():
    """测试单行 guard 语法生成正确的 C 代码"""
    source = '''def test_guard(x: int) -> int:
    guard x != 0 else 0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码包含条件返回
    assert "if (!((x != 0))) {" in c_code
    assert "return 0;" in c_code


def test_guard_multi_line_codegen():
    """测试多行 guard 语法生成正确的 C 代码"""
    source = '''def test_guard(x: int) -> int:
    guard x != 0 else:
        printf("error")
        0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码包含块和隐式返回
    assert "if (!((x != 0))) {" in c_code
    assert 'printf("error");' in c_code
    assert "return 0;" in c_code


def test_guard_let_codegen():
    """测试 guard let 语法生成正确的 C 代码"""
    source = '''def get_value() -> int:
    return 42

def test_guard_let() -> int:
    guard let v = get_value() else 0
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码先绑定再判断
    assert "v = get_value();" in c_code
    assert "if (!(v)) {" in c_code
    assert "return 0;" in c_code


def test_guard_with_defer():
    """测试 guard 与 defer 结合使用"""
    source = '''def test_guard_defer(x: int) -> int:
    defer free(ptr)
    guard x != 0 else 0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证 guard 和 defer 都被正确处理
    assert "if (!((x != 0))) {" in c_code
    assert "return 0;" in c_code
    assert "free(ptr);" in c_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
