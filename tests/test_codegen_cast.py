"""测试类型转换魔法方法 (__cast__/__try_cast__) 和 as 操作符"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def parse_and_generate(code: str) -> str:
    """解析并生成 Cython 代码"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 类型检查
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    # 代码生成
    generator = CythonGenerator()
    return generator.generate(ast)


def test_cast_expr_basic():
    """测试基本类型转换：int as float"""
    code = """
let x: int = 42
let y: float = x as float
"""
    cython_code = parse_and_generate(code)
    assert "<float>x" in cython_code or "x as float" in cython_code


def test_cast_expr_custom_type():
    """测试自定义类型转换：class 的 __cast__ 方法"""
    code = """
class Rational:
    def __init__(self, num: int, den: int):
        self.num = num
        self.den = den
    
    def __cast__<float>(self) -> float:
        return self.num / self.den

let r = Rational(3, 4)
let f: float = r as float
"""
    cython_code = parse_and_generate(code)
    assert "__cast__" in cython_code


def test_cast_expr_nested():
    """测试嵌套类型转换"""
    code = """
let x: int = 100
let y: float = (x as float) * 2.5
"""
    cython_code = parse_and_generate(code)
    assert "<float>x" in cython_code or "x as float" in cython_code


def test_try_cast_method():
    """测试 __try_cast__ 方法定义"""
    code = """
class SafeInt:
    def __init__(self, value: int):
        self.value = value

    def __try_cast__<bool>(self) -> bool:
        if self.value != 0:
            return True
        return False

let s = SafeInt(42)
let b: bool = s as bool
"""
    cython_code = parse_and_generate(code)
    assert "__try_cast__" in cython_code


def test_cast_chain():
    """测试类型转换链"""
    code = """
let x: int = 42
let y: float = x as float
let z: int = y as int
"""
    cython_code = parse_and_generate(code)
    # 应该生成两次类型转换
    assert ("<float>x" in cython_code or "x as float" in cython_code)
    assert ("<int>y" in cython_code or "y as int" in cython_code)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
