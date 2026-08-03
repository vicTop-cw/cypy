"""测试隐式策略体系（魔法方法）"""
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


def test_implicit_copy_method():
    """测试 __implicit_copy__ 魔法方法"""
    code = """
class StringWrapper:
    def __init__(self, value: str):
        self.value = value

    def __implicit_copy__(self) -> StringWrapper:
        return StringWrapper(self.value)

let s = StringWrapper("hello")
let s2 = s  # 应该调用 __implicit_copy__
"""
    cython_code = parse_and_generate(code)
    assert '__implicit_copy__' in cython_code


def test_implicit_into_method():
    """测试 __implicit_into__ 魔法方法"""
    code = """
class IntWrapper:
    def __init__(self, value: int):
        self.value = value

    def __implicit_into__<str>(self) -> str:
        return str(self.value)

let i = IntWrapper(42)
let s: str = i  # 应该调用 __implicit_into__<str>
"""
    cython_code = parse_and_generate(code)
    assert '__implicit_into__' in cython_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
