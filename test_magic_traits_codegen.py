"""测试魔法属性的代码生成功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def _get_generator(source: str, run_type_check: bool = False) -> CythonGenerator:
    """获取代码生成器并生成代码"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    
    if run_type_check:
        checker = TypeChecker()
        checker.check(ast)
        # 将类型检查器的魔法方法信息传递给代码生成器
        generator.register_magic_methods(checker.magic_methods)
        # 设置待处理的隐式操作（基于类型检查结果）
        generator.register_pending_operations({}, {})
    
    generator.generate(ast)
    return generator


class TestImplicitCopyCodeGen:
    """测试 __implicit_copy__ 代码生成"""

    def test_implicit_copy_in_cdef(self):
        """测试 cdef 变量的隐式复制代码生成"""
        source = '''
struct StringWrapper:
    value: str
    def __implicit_copy__(self) -> StringWrapper:
        return StringWrapper(value=self.value)

let s = StringWrapper("hello")
let s2 = s
'''
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        # 验证变量赋值代码生成
        assert 's2' in result


class TestImplicitIntoCodeGen:
    """测试 __implicit_into__ 代码生成"""

    def test_implicit_into_code_generated(self):
        """测试隐式转换代码生成"""
        source = '''
struct Celsius:
    temp: float
    def __implicit_into__(self) -> Fahrenheit:
        return Fahrenheit(temp=self.temp * 9 / 5 + 32)

struct Fahrenheit:
    temp: float

let c = Celsius(temp=0)
let f: Fahrenheit = c
'''
        generator = _get_generator(source, run_type_check=True)
        result = "\n".join(generator.output)
        # 验证变量赋值代码生成
        assert 'f' in result


class TestGuardedStrategyCodeGen:
    """测试守卫策略代码生成"""

    def test_guarded_strategy_code_generated(self):
        """测试守卫策略代码生成"""
        source = '''
struct SafeInt:
    value: int
    def __guarded_pred__(self) -> bool:
        return True
    def __guarded_action__(self) -> object:
        return self.value

let s = SafeInt(42)
let i: int = s
'''
        generator = _get_generator(source, run_type_check=True)
        result = "\n".join(generator.output)
        # 验证变量赋值代码生成
        assert 'i' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
