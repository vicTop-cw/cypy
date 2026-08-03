"""测试泛型类型约束功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
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


class TestGenericConstraints:
    """测试泛型类型约束"""

    def test_simple_constraint_int(self):
        """测试简单的泛型约束（int）"""
        source = '''
def identity<T: int>(value: T) -> T:
    return value

let result = identity(42)
'''
        checker = _get_type_checker(source)
        # 应该没有错误
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_simple_constraint_string(self):
        """测试简单的泛型约束（str）"""
        source = '''
def process<T: str>(value: T) -> T:
    return value

let result = process("hello")
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_constraint_violation(self):
        """测试泛型约束违反"""
        source = '''
def process<T: str>(value: T) -> T:
    return value

let result = process(42)
'''
        checker = _get_type_checker(source)
        # 应该有约束违反错误
        assert len(checker.errors) > 0, "应该报告泛型约束违反错误"
        assert "Generic constraint violation" in checker.errors[0]

    def test_multiple_constraints(self):
        """测试多个泛型约束"""
        source = '''
def combine<T: int, U: str>(a: T, b: U) -> T:
    return a

let result = combine(42, "hello")
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_constraint_on_struct(self):
        """测试结构体的泛型约束"""
        source = '''
struct Pair<T: int, U: str>:
    first: T
    second: U

let p = Pair(42, "hello")
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_numeric_constraint(self):
        """测试数值类型约束"""
        source = '''
def add<T: int>(a: T, b: T) -> T:
    return a + b

let result = add(10, 20)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_constraint_float(self):
        """测试浮点类型约束"""
        source = '''
def scale<T: float>(value: T) -> T:
    return value

let result = scale(3.14)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_trait_constraint(self):
        """测试 Trait 约束：T: TraitName"""
        source = '''
trait Display:
    def display(self) -> str

struct Point:
    x: float

impl Display for Point:
    def display(self) -> str:
        return "point"

def show<T: Display>(value: T) -> str:
    return value.display()

let p = Point(1.0)
let result = show(p)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_trait_constraint_violation(self):
        """测试 Trait 约束违反"""
        source = '''
trait Display:
    def display(self) -> str

struct NoDisplay:
    value: int

def show<T: Display>(value: T) -> str:
    return value.display()

let nd = NoDisplay(42)
let result = show(nd)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) > 0, "应该报告 trait 约束违反错误"

    def test_union_constraint(self):
        """测试联合类型约束：T: int | float"""
        source = '''
def process<T: int | float>(value: T) -> T:
    return value

let r1 = process(42)
let r2 = process(3.14)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_union_constraint_violation(self):
        """测试联合类型约束违反"""
        source = '''
def process<T: int | float>(value: T) -> T:
    return value

let r = process("hello")
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) > 0, "应该报告联合类型约束违反"

    def test_typeclass_constraint(self):
        """测试 TypeClass 约束"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return "point"

def display<T: Show>(value: T) -> str:
    return value.show()

let p = Point(1.0)
let result = display(p)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"

    def test_f_bounded_constraint(self):
        """测试 F-bounded 约束：T: Container<T>"""
        source = '''
typeclass Container<T>:
    def get(self) -> T

struct Box:
    value: int

impl typeclass Container<int> for Box:
    def get(self) -> int:
        return self.value

def process<T: Container<T>>(container: T) -> T:
    return container

let b = Box(42)
let result = process(b)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
