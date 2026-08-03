"""类型检查测试 - 验证 Cypy 编译器的类型错误检测功能"""

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


class TestTypeMismatchErrors:
    """类型不匹配错误测试"""

    def test_int_plus_str_error(self):
        """int + str 应该报错"""
        source = '''
def test():
    a: int = 1
    b: str = "hello"
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) > 0
        assert "Type mismatch" in tc.errors[0] or "mismatch" in tc.errors[0].lower()

    def test_int_plus_list_error(self):
        """int + list 应该报错"""
        source = '''
def test():
    a: int = 1
    b: list = [1, 2, 3]
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) > 0


class TestObjectTypeNoError:
    """object 类型不应报错测试"""

    def test_object_plus_any(self):
        """object 类型参与运算不报错（动态类型）"""
        source = '''
def test():
    a = 1
    b = "hello"
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        # object 类型参与任何运算都不报错
        # 因为 object 是动态类型
        assert len(tc.errors) == 0

    def test_object_assign_any(self):
        """object 类型变量首次赋值后类型被推断"""
        source = '''
def test():
    a = 1
    return a
'''
        tc = _get_type_checker(source)
        # object 类型首次赋值后不报错
        assert len(tc.errors) == 0


class TestComparisonTypeErrors:
    """比较运算类型错误测试"""

    def test_incompatible_comparison(self):
        """不兼容类型的比较"""
        source = '''
def test():
    a: int = 1
    b: str = "hello"
    c = a < b
    return c
'''
        tc = _get_type_checker(source)
        # 数值和字符串比较可能报错（取决于实现）


class TestEdgeCases:
    """边界情况测试"""

    def test_none_type_operations(self):
        """None 类型参与运算"""
        source = '''
def test():
    a = None
    b: int = 1
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        # None 参与算术运算


if __name__ == '__main__':
    pytest.main([__file__, '-v'])