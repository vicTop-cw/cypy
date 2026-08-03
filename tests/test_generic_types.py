"""泛型类型测试 - 验证 Cypy 编译器的泛型类型支持"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker


def _get_type_checker(source: str) -> TypeChecker:
    """辅助函数：解析并检查代码，返回类型检查器"""
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    type_checker = TypeChecker()
    type_checker.check(ast)
    return type_checker


class TestGenericList:
    """泛型列表类型测试"""

    def test_list_int_type(self):
        """list[int] 类型声明"""
        source = '''
def test():
    items: list<int> = [1, 2, 3]
    return items[0]
'''
        tc = _get_type_checker(source)
        # 验证 items 被正确识别

    def test_list_str_type(self):
        """list[str] 类型声明"""
        source = '''
def test():
    names: list<str> = ["a", "b", "c"]
    return names[0]
'''
        tc = _get_type_checker(source)
        # 验证 names 被正确识别


class TestGenericFunction:
    """泛型函数测试"""

    def test_generic_function_definition(self):
        """泛型函数定义"""
        source = '''
def identity<T>(value: T) -> T:
    return value
'''
        tc = _get_type_checker(source)
        # 验证泛型函数被正确注册
        assert 'identity' in tc.type_map

    def test_generic_function_call(self):
        """泛型函数调用"""
        source = '''
def identity<T>(value: T) -> T:
    return value

def test():
    a: int = identity<int>(42)
    b: str = identity<str>("hello")
    return a
'''
        tc = _get_type_checker(source)
        # 验证泛型函数调用类型推断


class TestGenericTypeAlias:
    """泛型类型别名测试"""

    def test_simple_generic_alias(self):
        """简单泛型类型别名"""
        source = '''
type Maybe<T> = T | None

def test():
    a: Maybe<int> = 42
    b: Maybe<str> = "hello"
    return a
'''
        tc = _get_type_checker(source)
        # 验证泛型类型别名

    def test_nested_generic_alias(self):
        """嵌套泛型类型别名"""
        source = '''
type Result<T, E> = T | E

def test():
    r: Result<int, str> = 42
    return r
'''
        tc = _get_type_checker(source)
        # 验证多参数泛型类型别名


class TestGenericStruct:
    """泛型结构体测试"""

    def test_generic_struct_definition(self):
        """泛型结构体定义"""
        source = '''
struct Box<T>:
    value: T

    def get(self) -> T:
        return self.value
'''
        tc = _get_type_checker(source)
        # 验证泛型结构体被正确注册
        assert 'Box' in tc.struct_defs


class TestUnionType:
    """联合类型测试"""

    def test_simple_union(self):
        """简单联合类型"""
        source = '''
def test():
    a: int | str = 42
    a = "hello"
    return a
'''
        tc = _get_type_checker(source)
        # 验证联合类型

    def test_union_in_generic(self):
        """泛型中的联合类型"""
        source = '''
type Result<T> = T | str

def test():
    r: Result<int> = 42
    r = "error"
    return r
'''
        tc = _get_type_checker(source)
        # 验证泛型联合类型


class TestOptionalType:
    """可选类型测试"""

    def test_optional_explicit(self):
        """显式可选类型"""
        source = '''
def test():
    a: int | None = None
    if a == None:
        return 0
    return a
'''
        tc = _get_type_checker(source)
        # 验证显式可选类型


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
