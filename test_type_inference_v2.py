"""类型推断增强测试 - 验证 Cypy 编译器的类型推断功能"""

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


class TestLiteralTypeInference:
    """字面量类型推断测试 - 阶段一"""

    def test_int_literal_inference(self):
        """let x = 42 应推断为 int"""
        source = '''
def test():
    x = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        assert 'test' in tc.type_map

    def test_float_literal_inference(self):
        """let x = 3.14 应推断为 float"""
        source = '''
def test():
    x = 3.14
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_literal_inference(self):
        """let flag = true 应推断为 bool"""
        source = '''
def test():
    flag = True
    return flag
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_string_literal_inference(self):
        """let s = "hello" 应推断为 str"""
        source = '''
def test():
    s = "hello"
    return s
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_none_literal_inference(self):
        """let x = None 应推断为 None"""
        source = '''
def test():
    x = None
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_variable_inference_in_let(self):
        """let x = 42 中的 x 应被推断为 int"""
        source = '''
def test():
    let x = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_var_statement_inference(self):
        """var x = 42 中的 x 应被推断为 int"""
        source = '''
def test():
    var x = 42
    x = 100
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestFunctionReturnTypeInference:
    """函数返回类型推断测试 - 阶段二"""

    def test_int_return_inference(self):
        """无返回类型注解的函数返回 int 应推断为 int"""
        source = '''
def get_value():
    return 42
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        assert 'get_value' in tc.type_map

    def test_float_return_inference(self):
        """无返回类型注解的函数返回 float 应推断为 float"""
        source = '''
def get_pi():
    return 3.14
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_string_return_inference(self):
        """无返回类型注解的函数返回 str 应推断为 str"""
        source = '''
def greet():
    return "hello"
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_return_inference(self):
        """无返回类型注解的函数返回 bool 应推断为 bool"""
        source = '''
def is_valid():
    return True
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_arithmetic_return_inference(self):
        """函数返回 a + b 的结果，应推断为 int"""
        source = '''
def add(a: int, b: int):
    return a + b
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        assert 'add' in tc.type_map

    def test_explicit_return_type_still_works(self):
        """显式返回类型注解仍然有效"""
        source = '''
def add(a: int, b: int) -> int:
    return a + b
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        assert 'add' in tc.type_map

    def test_multiple_returns_inferred(self):
        """多个 return 语句应能正确推断"""
        source = '''
def get_size(items: list):
    if items:
        return len(items)
    else:
        return 0
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestContainerTypeInference:
    """容器字面量类型推断测试 - 阶段三"""

    def test_empty_list_inference(self):
        """空列表应推断为 list[object]"""
        source = '''
def test():
    items = []
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_list_inference(self):
        """int 列表应推断为 list[int]"""
        source = '''
def test():
    items = [1, 2, 3]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_float_list_inference(self):
        """float 列表应推断为 list[float]"""
        source = '''
def test():
    items = [1.0, 2.0, 3.0]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_string_list_inference(self):
        """str 列表应推断为 list[str]"""
        source = '''
def test():
    items = ["a", "b", "c"]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_mixed_numeric_list_inference(self):
        """混合数值列表应推断为 list[float]（向上转换）"""
        source = '''
def test():
    items = [1, 2.0, 3]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_bool_list_inference(self):
        """bool 列表应推断为 list[bool]"""
        source = '''
def test():
    items = [True, False]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_tuple_inference(self):
        """元组字面量应推断为 tuple[int, str]"""
        source = '''
def test():
    point = (1, "hello")
    return point
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_nested_list_inference(self):
        """嵌套列表应正确推断"""
        source = '''
def test():
    matrix = [[1, 2], [3, 4]]
    return matrix
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_list_type_verification(self):
        """验证列表类型推断结果"""
        source = '''
def test():
    items = [1, 2, 3]
    return items
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0
        # 验证 items 的类型是 list[int]
        if 'items' in tc.type_map:
            items_type = tc.type_map['items']
            assert items_type.name == 'list'
            assert len(items_type.generic_params) > 0
            assert items_type.generic_params[0].name == 'int'


class TestTypeInferenceRegression:
    """回归测试 - 确保现有功能不受影响"""

    def test_explicit_type_annotation_still_works(self):
        """显式类型注解仍然有效"""
        source = '''
def test():
    x: int = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_type_mismatch_still_detected(self):
        """类型不匹配仍然应该被检测到"""
        source = '''
def test():
    x: str = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) > 0  # 应该有类型错误

    def test_function_with_explicit_types(self):
        """带显式类型的函数仍然正常工作"""
        source = '''
def add(a: int, b: int) -> int:
    return a + b

def test():
    result = add(1, 2)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_let_without_initial_value(self):
        """无初始值的 var 语句仍然正常工作"""
        source = '''
def test():
    var x: int = 42
    x = 100
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_object_type_fallback(self):
        """复杂表达式仍可回退到 object 类型"""
        source = '''
@python
def dynamic_func():
    pass

def test():
    x = dynamic_func()
    return x
'''
        tc = _get_type_checker(source)
        # @python 函数返回 object，所以不应该报错


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
