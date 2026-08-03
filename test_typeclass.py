"""测试 TypeClass 实现 - 对标 Rust trait / Scala Type Class"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ASTNode, TypeClassDef, TypeClassImpl
from cypyc.analyzer.type_checker import TypeChecker


def _parse_source(source: str) -> ASTNode:
    """解析源代码并返回 AST"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    return parser.parse()


def _get_type_checker(source: str) -> TypeChecker:
    """获取类型检查器并运行检查"""
    ast = _parse_source(source)
    checker = TypeChecker()
    checker.check(ast)
    return checker


class TestTypeClassParsing:
    """测试 TypeClass 语法解析"""

    def test_simple_typeclass_parsing(self):
        """测试简单 TypeClass 定义解析"""
        source = '''
typeclass Show:
    def show(self) -> str
'''
        ast = _parse_source(source)
        assert ast is not None
        # 检查是否有 TypeClassDef 节点
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert typeclass_nodes[0].name == "Show"
        assert len(typeclass_nodes[0].methods) == 1

    def test_typeclass_with_generics(self):
        """测试带泛型参数的 TypeClass 解析"""
        source = '''
typeclass Container<T>:
    def get(self) -> T
    def put(self, value: T) -> None
'''
        ast = _parse_source(source)
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert typeclass_nodes[0].name == "Container"
        assert typeclass_nodes[0].generic_params == ["T"]
        assert len(typeclass_nodes[0].methods) == 2

    def test_typeclass_impl_parsing(self):
        """测试 TypeClass 实现解析"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float
    y: float

impl typeclass Show for Point:
    def show(self) -> str:
        return f"({self.x}, {self.y})"
'''
        ast = _parse_source(source)
        # 检查 TypeClassDef 节点
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert typeclass_nodes[0].name == "Show"
        
        # 检查 TypeClassImpl 节点
        impl_nodes = [n for n in ast.body if isinstance(n, TypeClassImpl)]
        assert len(impl_nodes) == 1
        assert impl_nodes[0].typeclass_name == "Show"
        assert impl_nodes[0].target_type == "Point"
        assert len(impl_nodes[0].methods) == 1

    def test_multiple_typeclass_defs(self):
        """测试多个 TypeClass 定义"""
        source = '''
typeclass Show:
    def show(self) -> str

typeclass Eq<T>:
    def eq(self, other: T) -> bool
'''
        ast = _parse_source(source)
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 2
        assert typeclass_nodes[0].name == "Show"
        assert typeclass_nodes[1].name == "Eq"
        assert typeclass_nodes[1].generic_params == ["T"]

    def test_typeclass_impl_with_generics(self):
        """测试带泛型的 TypeClass 实现"""
        source = '''
typeclass Container<T>:
    def get(self) -> T

struct Box<T>:
    value: T

impl typeclass Container<T> for Box<T>:
    def get(self) -> T:
        return self.value
'''
        ast = _parse_source(source)
        impl_nodes = [n for n in ast.body if isinstance(n, TypeClassImpl)]
        assert len(impl_nodes) == 1
        assert impl_nodes[0].generic_params == ["T"]


class TestTypeClassRegistration:
    """测试 TypeClass 注册和查找"""

    def test_typeclass_registered_in_checker(self):
        """测试 TypeClass 被正确注册到类型检查器"""
        source = '''
typeclass Show:
    def show(self) -> str
'''
        checker = _get_type_checker(source)
        assert "Show" in checker.type_classes

    def test_typeclass_instance_registered(self):
        """测试 TypeClass 实现被正确注册"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)
'''
        checker = _get_type_checker(source)
        # 检查 TypeClass 定义被注册
        assert "Show" in checker.type_classes
        # 检查 TypeClass 实现被注册
        assert ("Show", "Point") in checker.type_class_instances

    def test_typeclass_method_resolution(self):
        """测试 TypeClass 方法解析"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)
'''
        checker = _get_type_checker(source)
        # 方法应该能被正确解析
        method = checker.resolve_type_class_method("Show", "show", "Point")
        assert method is not None

    def test_typeclass_check_resolution(self):
        """测试类型是否实现了 TypeClass 的检查"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)
'''
        checker = _get_type_checker(source)
        # 检查 Point 是否实现了 Show
        assert checker.check_type_class_resolution("Show", "Point") is True
        # 检查未实现的类型
        assert checker.check_type_class_resolution("Show", "UnknownType") is False


class TestTypeClassTypeChecking:
    """测试 TypeClass 类型检查"""

    def test_typeclass_no_errors(self):
        """测试正确的 TypeClass 实现不产生错误"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)
'''
        checker = _get_type_checker(source)
        assert len(checker.errors) == 0, f"Unexpected errors: {checker.errors}"

    def test_typeclass_undefined_impl_error(self):
        """测试未定义 TypeClass 的实现产生错误"""
        source = '''
struct Point:
    x: float

impl typeclass UndefinedTypeClass for Point:
    def show(self) -> str:
        return str(self.x)
'''
        checker = _get_type_checker(source)
        # 应该有错误，因为 UndefinedTypeClass 未定义
        assert len(checker.errors) > 0

    def test_typeclass_duplicate_impl_error(self):
        """测试重复实现同一个 TypeClass 产生错误"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)

impl typeclass Show for Point:
    def show(self) -> str:
        return "duplicate"
'''
        checker = _get_type_checker(source)
        # 应该有歧义错误
        assert len(checker.errors) > 0


class TestTypeClassWithGenerics:
    """测试带泛型的 TypeClass"""

    def test_generic_typeclass_parsing(self):
        """测试泛型 TypeClass 解析"""
        source = '''
typeclass Functor<T>:
    def map(self, func: callable) -> Functor<T>
'''
        ast = _parse_source(source)
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert typeclass_nodes[0].generic_params == ["T"]

    def test_generic_typeclass_impl(self):
        """测试泛型 TypeClass 实现"""
        source = '''
typeclass Functor<T>:
    def map(self, func: callable) -> Functor<T>

struct List<T>:
    items: list

impl typeclass Functor<T> for List<T>:
    def map(self, func: callable) -> List<T>:
        return self
'''
        ast = _parse_source(source)
        impl_nodes = [n for n in ast.body if isinstance(n, TypeClassImpl)]
        assert len(impl_nodes) == 1
        assert impl_nodes[0].generic_params == ["T"]

    def test_typeclass_with_constraints(self):
        """测试带约束的 TypeClass"""
        source = '''
typeclass Bound<T: int>:
    def get_bound(self) -> T
'''
        ast = _parse_source(source)
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert "T" in typeclass_nodes[0].generic_constraints


class TestTypeClassIntegration:
    """测试 TypeClass 集成场景"""

    def test_multiple_typeclasses_and_impls(self):
        """测试多个 TypeClass 和实现"""
        source = '''
typeclass Show:
    def show(self) -> str

typeclass Eq:
    def eq(self, other: object) -> bool

struct Point:
    x: float
    y: float

struct Color:
    r: int
    g: int
    b: int

impl typeclass Show for Point:
    def show(self) -> str:
        return f"({self.x}, {self.y})"

impl typeclass Show for Color:
    def show(self) -> str:
        return f"rgb({self.r}, {self.g}, {self.b})"

impl typeclass Eq for Point:
    def eq(self, other: object) -> bool:
        return self.x == other.x and self.y == other.y
'''
        checker = _get_type_checker(source)
        # 检查所有 TypeClass 都被注册
        assert "Show" in checker.type_classes
        assert "Eq" in checker.type_classes
        # 检查所有实现都被注册
        assert ("Show", "Point") in checker.type_class_instances
        assert ("Show", "Color") in checker.type_class_instances
        assert ("Eq", "Point") in checker.type_class_instances
        # 检查没有错误
        assert len(checker.errors) == 0, f"Unexpected errors: {checker.errors}"

    def test_typeclass_with_functions(self):
        """测试 TypeClass 在函数中的使用"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)

def display(value: Point) -> str:
    return value.show()
'''
        ast = _parse_source(source)
        assert ast is not None
        # 检查 TypeClass 被注册
        typeclass_nodes = [n for n in ast.body if isinstance(n, TypeClassDef)]
        assert len(typeclass_nodes) == 1
        assert typeclass_nodes[0].name == "Show"
        # 检查 display 函数存在
        func_nodes = [n for n in ast.body if hasattr(n, 'name') and n.name == 'display']
        assert len(func_nodes) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
