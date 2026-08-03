"""测试 ClassDef 代码生成功能"""
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


def test_class_def_basic():
    """测试基本类定义代码生成"""
    source = '''
class Point:
    x: int
    y: int
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含 class 定义
    assert "class Point" in result, "生成的代码应包含 class Point"


def test_class_def_with_method():
    """测试带方法的类定义代码生成"""
    source = '''
class Point:
    x: int
    y: int
    
    def distance(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含 class 和方法定义（有类型注解时生成 cpdef）
    assert "class Point" in result
    assert "distance(self)" in result


def test_class_def_with_inheritance():
    """测试继承的类定义代码生成"""
    source = '''
class Base:
    def base_method(self):
        pass

class Derived(Base):
    def derived_method(self):
        pass
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含继承关系
    assert "class Base" in result
    assert "class Derived(Base)" in result


def test_class_def_with_constructor():
    """测试带构造函数的类定义代码生成"""
    source = '''
class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含构造函数
    assert "class Point" in result
    assert "__init__" in result


def test_cdef_class_def():
    """测试 cdef class 定义代码生成"""
    source = '''
cdef class FastPoint:
    x: int
    y: int
    
    def distance(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
'''
    ast = _parse_source(source)
    generator = CythonGenerator()
    result = generator.generate(ast)
    
    # 验证生成的代码包含 cdef class
    assert "cdef class FastPoint" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
