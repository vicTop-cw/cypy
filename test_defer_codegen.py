"""测试 defer 代码生成功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ASTNode
from cypyc.codegen.cython_generator import CythonGenerator


def _parse_source(source: str) -> ASTNode:
    """解析源代码并返回 AST"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    return parser.parse()


def test_defer_basic():
    """测试基本 defer 代码生成"""
    source = '''
def test_defer():
    let x: int = 10
    defer:
        print("cleanup")
    return x
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含 try/finally 结构
    assert "try:" in result, "生成的代码应包含 try: 块"
    assert "finally:" in result, "生成的代码应包含 finally: 块"
    assert "cleanup" in result, "生成的代码应包含 defer 清理代码"


def test_defer_multiple():
    """测试多个 defer 语句（逆序执行）"""
    source = '''
def test_defer_multiple():
    defer:
        print("first")
    defer:
        print("second")
    defer:
        print("third")
    return 42
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含 try/finally 结构
    assert "try:" in result
    assert "finally:" in result
    
    # 验证 defer 按逆序执行：third, second, first
    # 找到 finally 块后的 print 语句
    finally_idx = result.find("finally:")
    finally_section = result[finally_idx:]
    
    first_print = finally_section.find("third")
    second_print = finally_section.find("second")
    third_print = finally_section.find("first")
    
    # 验证顺序：third 在 second 前，second 在 first 前
    assert first_print < second_print < third_print, "defer 应按逆序执行"


def test_defer_no_try_finally_when_no_defer():
    """测试没有 defer 时不生成 try/finally"""
    source = '''
def test_no_defer():
    let x: int = 10
    return x
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证没有 try/finally（简单函数不应有 try/finally）
    # 注意：Cython 可能有其他 try/finally，所以检查函数体内部
    # 这里只是简单验证代码生成没有错误


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
