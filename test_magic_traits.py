"""测试魔法属性体系 - __implicit_copy__, __implicit_into__, 守卫策略"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ASTNode
from cypyc.analyzer.type_checker import TypeChecker


def _get_type_checker(source: str) -> TypeChecker:
    """获取类型检查器并运行检查"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    checker = TypeChecker()
    checker.check(ast)
    return checker


class TestImplicitCopy:
    """测试 __implicit_copy__ 魔法属性"""

    def test_implicit_copy_registered(self):
        """测试 __implicit_copy__ 方法被正确注册"""
        source = '''
struct StringWrapper:
    value: str

    def __implicit_copy__(self) -> StringWrapper:
        return StringWrapper(value=self.value)

let s = StringWrapper("hello")
let s2 = s
'''
        checker = _get_type_checker(source)
        # 检查没有错误
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"
        # 检查魔法方法被注册
        assert 'StringWrapper' in checker.magic_methods
        assert '__implicit_copy__' in checker.magic_methods['StringWrapper']

    def test_implicit_copy_multiple_assignments(self):
        """测试多次赋值都触发 __implicit_copy__"""
        source = '''
struct Wrapper:
    data: int

    def __implicit_copy__(self) -> Wrapper:
        return Wrapper(data=self.data)

let w1 = Wrapper(42)
let w2 = w1
let w3 = w2
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0


class TestImplicitInto:
    """测试 __implicit_into__ 魔法属性"""

    def test_implicit_into_registered(self):
        """测试 __implicit_into__ 方法被正确注册"""
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
        checker = _get_type_checker(source)
        # 检查魔法方法被注册
        assert 'Celsius' in checker.magic_methods
        assert '__implicit_into__' in checker.magic_methods['Celsius']
        # 应该没有类型错误（通过 __implicit_into__ 转换）
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_implicit_into_no_method_should_error(self):
        """测试没有 __implicit_into__ 方法时应该报错"""
        source = '''
struct TypeA:
    value: int

struct TypeB:
    value: str

let a = TypeA(42)
let b: TypeB = a
'''
        checker = _get_type_checker(source)
        # 应该有类型错误（没有隐式转换方法）
        assert len(checker.errors) > 0, "应该报告类型错误，因为没有隐式转换方法"


class TestGuardedStrategy:
    """测试守卫策略魔法属性"""

    def test_guarded_pred_registered(self):
        """测试 __guarded_pred__ 和 __guarded_action__ 被正确注册"""
        source = '''
struct Number:
    value: float

    def __guarded_pred__(self) -> bool:
        return True

    def __guarded_action__(self) -> object:
        return self.value

let num = Number(value=3.14)
'''
        checker = _get_type_checker(source)
        # 检查守卫策略方法被注册
        assert 'Number' in checker.magic_methods
        assert '__guarded_pred__' in checker.magic_methods['Number']
        assert '__guarded_action__' in checker.magic_methods['Number']

    def test_guarded_strategy_allows_conversion(self):
        """测试守卫策略允许合法转换"""
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
        checker = _get_type_checker(source)
        # 如果守卫策略允许转换，应该没有错误
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"


class TestMagicTraitCombined:
    """测试魔法属性组合使用"""

    def test_multiple_magic_methods_on_same_struct(self):
        """测试同一个结构体有多个魔法方法"""
        source = '''
struct SmartValue:
    data: int

    def __implicit_copy__(self) -> SmartValue:
        return SmartValue(data=self.data)

    def __implicit_into__(self) -> int:
        return self.data

let v = SmartValue(42)
let v_copy = v
let i: int = v
'''
        checker = _get_type_checker(source)
        # 检查多个魔法方法都被注册
        assert 'SmartValue' in checker.magic_methods
        assert '__implicit_copy__' in checker.magic_methods['SmartValue']
        assert '__implicit_into__' in checker.magic_methods['SmartValue']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
