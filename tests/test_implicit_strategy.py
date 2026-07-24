"""测试隐式策略体系"""
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


def test_implicit_struct():
    """测试隐式结构体定义"""
    code = """
implicit struct Config:
    debug: bool
    timeout: int
"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 查找结构体定义
    struct_def = None
    for stmt in ast.body:
        if hasattr(stmt, 'name') and stmt.name == 'Config':
            struct_def = stmt
            break
    
    assert struct_def is not None
    assert hasattr(struct_def, 'is_implicit')
    assert struct_def.is_implicit == True


def test_implicit_param():
    """测试隐式参数"""
    code = """
def greet(name: str, implicit greeting: str = "Hello"):
    return f"{greeting}, {name}"
"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 查找函数定义
    func_def = None
    for stmt in ast.body:
        if hasattr(stmt, 'name') and stmt.name == 'greet':
            func_def = stmt
            break
    
    assert func_def is not None
    # 检查第二个参数是否是隐式参数
    assert len(func_def.params) == 2
    assert func_def.params[1].name == 'greeting'
    assert func_def.params[1].is_implicit == True


def test_implicit_copy_method():
    """测试 __implicit_copy__ 魔法方法"""
    code = """
class StringWrapper:
    def __init__(self, value: str):
        self.value = value
    
    def __implicit_copy__(self) -> StringWrapper:
        return StringWrapper(self.value)

val s = StringWrapper("hello")
val s2 = s  # 应该调用 __implicit_copy__
"""
    cython_code = parse_and_generate(code)
    assert '__implicit_copy__' in cython_code


def test_implicit_into_method():
    """测试 __implicit_into__ 魔法方法"""
    code = """
class IntWrapper:
    def __init__(self, value: int):
        self.value = value
    
    def __implicit_into__[str](self) -> str:
        return str(self.value)

val i = IntWrapper(42)
val s: str = i  # 应该调用 __implicit_into__[str]
"""
    cython_code = parse_and_generate(code)
    assert '__implicit_into__' in cython_code


def test_no_strategy_annotation():
    """测试 @no_strategy 注解"""
    code = """
@no_strategy
def pure_func(x: int) -> int:
    return x * 2
"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    # 应该能够解析 no_strategy 关键字
    assert any(t.type == 'NO_STRATEGY' for t in tokens)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
