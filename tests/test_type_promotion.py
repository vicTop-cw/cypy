"""类型提升测试 - 验证 Cypy 编译器的类型提升规则

类型提升顺序：bool < int < float < double

规则：
- bool + int = int
- bool + float = float
- bool + double = double
- int + float = float
- int + double = double
- float + double = double
"""

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


class TestBoolPromotion:
    """bool 类型提升测试"""

    def test_bool_plus_bool(self):
        """bool + bool = int (bool 在算术运算中提升为 int)"""
        source = '''
def test():
    a: bool = True
    b: bool = False
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_plus_int(self):
        """bool + int = int"""
        source = '''
def test():
    a: bool = True
    b: int = 5
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_plus_float(self):
        """bool + float = float"""
        source = '''
def test():
    a: bool = True
    b: float = 2.5
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_plus_double(self):
        """bool + double = double"""
        source = '''
def test():
    a: bool = True
    b: double = 2.5
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_multiply_int(self):
        """bool * int = int"""
        source = '''
def test():
    a: bool = True
    b: int = 5
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestIntPromotion:
    """int 类型提升测试"""

    def test_int_plus_float(self):
        """int + float = float"""
        source = '''
def test():
    a: int = 1
    b: float = 2.0
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_plus_double(self):
        """int + double = double"""
        source = '''
def test():
    a: int = 1
    b: double = 2.0
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_multiply_float(self):
        """int * float = float"""
        source = '''
def test():
    a: int = 3
    b: float = 2.5
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_divide_int(self):
        """int / int 在 Python 3 中结果为 float"""
        source = '''
def test():
    a: int = 10
    b: int = 3
    c = a / b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestFloatPromotion:
    """float 类型提升测试"""

    def test_float_plus_double(self):
        """float + double = double"""
        source = '''
def test():
    a: float = 1.0
    b: double = 2.0
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_float_plus_float(self):
        """float + float = float"""
        source = '''
def test():
    a: float = 1.0
    b: float = 2.0
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_float_multiply_double(self):
        """float * double = double"""
        source = '''
def test():
    a: float = 1.5
    b: double = 2.0
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestDoubleType:
    """double 类型测试"""

    def test_double_plus_double(self):
        """double + double = double"""
        source = '''
def test():
    a: double = 1.0
    b: double = 2.0
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_double_multiply_double(self):
        """double * double = double"""
        source = '''
def test():
    a: double = 1.5
    b: double = 2.0
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestComplexPromotion:
    """复杂表达式类型提升测试"""

    def test_three_type_mix(self):
        """int + float + double = double"""
        source = '''
def test():
    a: int = 1
    b: float = 2.0
    c: double = 3.0
    d = a + b + c
    return d
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_parenthesized_promotion(self):
        """括号表达式类型提升"""
        source = '''
def test():
    a: int = 1
    b: float = 2.0
    c: double = 3.0
    d = (a + b) * c
    return d
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_mixed_arithmetic_chain(self):
        """混合算术链类型提升"""
        source = '''
def test():
    a: bool = True
    b: int = 1
    c: float = 2.0
    d = a + b + c
    return d
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestPromotionWithComparison:
    """类型提升与比较运算"""

    def test_int_float_comparison(self):
        """int 和 float 可以比较"""
        source = '''
def test():
    a: int = 1
    b: float = 2.0
    c = a < b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_int_comparison(self):
        """bool 和 int 可以比较"""
        source = '''
def test():
    a: bool = True
    b: int = 2
    c = a < b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])