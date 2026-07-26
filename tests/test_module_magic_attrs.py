"""测试模块级魔法属性"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def parse_and_generate(code: str, source_file: str = None) -> str:
    """解析并生成 Cython 代码"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 类型检查
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    # 代码生成
    generator = CythonGenerator(source_file=source_file)
    return generator.generate(ast)


def test_module_identity_attrs():
    """测试身份属性：__name__/__file__/__package__/__path__"""
    code = """
def public_func():
    pass
"""
    cython_code = parse_and_generate(code, "test_module.cy")
    assert '__name__' in cython_code
    assert '__file__' in cython_code
    assert '__package__' in cython_code
    assert '__path__' in cython_code
    assert 'test_module' in cython_code


def test_module_visibility_attrs():
    """测试可见性属性：__all__/__private__"""
    code = """
def public_func():
    pass

def _private_func():
    pass

class PublicClass:
    pass

class _PrivateClass:
    pass
"""
    cython_code = parse_and_generate(code, "test_module.cy")
    assert '__all__' in cython_code
    assert '__private__' in cython_code
    assert 'public_func' in cython_code
    assert '_private_func' in cython_code
    assert 'PublicClass' in cython_code
    assert '_PrivateClass' in cython_code


def test_module_compile_attrs():
    """测试编译环境属性：__compile_time__/__target__/__profile__"""
    code = """
let x: int = 42
"""
    cython_code = parse_and_generate(code, "test_module.cy")
    assert '__compile_time__' in cython_code
    assert '__target__' in cython_code
    assert '__profile__' in cython_code


def test_module_deps_attr():
    """测试依赖属性：__deps__"""
    code = """
import math
from typing import List
"""
    cython_code = parse_and_generate(code, "test_module.cy")
    assert '__deps__' in cython_code
    assert 'math' in cython_code or '"math"' in cython_code


def test_module_magic_methods_in_all():
    """测试魔法方法在 __all__ 中"""
    code = """
class MyClass:
    def __cast__[float](self) -> float:
        return 0.0
    
    def _private_method(self):
        pass
"""
    cython_code = parse_and_generate(code, "test_module.cy")
    assert '__all__' in cython_code
    # __cast__ 应该在 __all__ 中
    assert '__cast__' in cython_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
