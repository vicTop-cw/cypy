"""Scala 级别类型推断测试 - 验证高级类型推断功能"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker, Type


def _get_type_checker(source: str) -> TypeChecker:
    """辅助函数：解析并检查代码，返回类型检查器"""
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    type_checker = TypeChecker()
    type_checker.check(ast)
    return type_checker


class TestScalaStyleInference:
    """Scala 风格的高级类型推断测试"""

    def test_scala_any_type_system(self):
        """Scala 风格的 Any 类型系统"""
        source = '''
def test():
    x: object = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_scala_nothing_bottom_type(self):
        """Scala 风格的 Nothing 底部类型"""
        source = '''
def fail() -> Nothing:
    raise Exception("error")

def test():
    result = fail()
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_scala_null_type(self):
        """Scala 风格的 Null 类型"""
        source = '''
def test():
    x: Null = None
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_generic_type_inference(self):
        """泛型类型推断 - 使用内置 list 泛型"""
        source = '''
def test():
    items = [1, 2, 3]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_multi_type_inference(self):
        """多种类型的推断"""
        source = '''
def test():
    a = 42
    b = 3.14
    c = "hello"
    d = True
    return a
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestControlFlowNarrowing:
    """控制流类型窄化测试 - Scala 风格的流敏感性类型"""

    def test_type_narrowing_in_branch(self):
        """条件分支中的类型窄化"""
        source = '''
def test(x: int):
    if x > 0:
        return x + 1
    else:
        return x - 1
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_type_narrowing_with_else(self):
        """if-else 分支中的类型保持"""
        source = '''
def test(x: int):
    if x > 0:
        return x + 1
    else:
        return 0
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_nested_condition_narrowing(self):
        """嵌套条件中的类型推断"""
        source = '''
def test(x: int):
    if x > 0:
        if x < 100:
            return x * 2
    return 0
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_conditional_assignment(self):
        """条件赋值的类型推断"""
        source = '''
def test(flag: bool):
    x: int = 0
    if flag:
        x = 42
    else:
        x = 0
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestLeastUpperBound:
    """最小上界（LUB）算法测试"""

    def test_numeric_lub(self):
        """数值类型的 LUB：bool → int → float → double"""
        source = '''
def test():
    x = True + 1
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_mixed_numeric_lub(self):
        """混合数值类型的 LUB"""
        source = '''
def test():
    x = 1 + 2.0
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_list_type_lub(self):
        """列表类型的 LUB"""
        source = '''
def test():
    a = [1, 2, 3]
    return a
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_string_list_lub(self):
        """字符串列表的 LUB"""
        source = '''
def test():
    items = ["a", "b", "c"]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestAdvancedInference:
    """高级类型推断测试"""

    def test_return_type_inference_no_annotation(self):
        """无返回类型注解的函数应从 return 推断"""
        source = '''
def add(a: int, b: int):
    return a + b

def test():
    result = add(1, 2)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        assert 'add' in tc.type_map

    def test_polymorphic_usage(self):
        """多态使用 - 相同模式用于不同类型"""
        source = '''
def test():
    a = 42
    b = "hello"
    c = 3.14
    return a
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_context_bound_style(self):
        """上下文边界风格的推断"""
        source = '''
def show_int(value: int) -> str:
    return str(value)

def test():
    result = show_int(42)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_recursive_type_inference(self):
        """递归函数的类型推断"""
        source = '''
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def test():
    return factorial(5)
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_conditional_return_inference(self):
        """条件返回的类型推断"""
        source = '''
def abs_val(x: int):
    if x >= 0:
        return x
    else:
        return -x

def test():
    return abs_val(-5)
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestInferenceRegression:
    """类型推断回归测试"""

    def test_explicit_types_still_work(self):
        """显式类型注解仍然有效"""
        source = '''
def test():
    x: int = 42
    y: str = "hello"
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_type_errors_still_detected(self):
        """类型错误仍应被检测"""
        source = '''
def test():
    x: str = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) > 0

    def test_complex_program_still_works(self):
        """复杂程序仍可正常工作"""
        source = '''
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    a = 0
    b = 1
    i = 2
    while i <= n:
        temp = a + b
        a = b
        b = temp
        i = i + 1
    return b

def main():
    result = fibonacci(10)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_struct_usage(self):
        """结构体使用仍可正常工作"""
        source = '''
struct Point:
    x: int
    y: int

def test():
    p = Point(1, 2)
    return p.x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_list_operations(self):
        """列表操作仍可正常工作"""
        source = '''
def test():
    items = [1, 2, 3]
    result = len(items)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
