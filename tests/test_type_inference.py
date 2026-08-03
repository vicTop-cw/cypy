"""类型推断测试 - 验证 Cypy 编译器的类型推断功能"""

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


class TestBasicTypeInference:
    """基础类型推断测试"""

    def test_int_addition(self):
        """int + int = int"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        # 验证没有类型错误
        assert len(tc.errors) == 0

    def test_int_subtraction(self):
        """int - int = int"""
        source = '''
def test():
    a: int = 5
    b: int = 2
    c = a - b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_multiplication(self):
        """int * int = int"""
        source = '''
def test():
    a: int = 3
    b: int = 4
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_int_division(self):
        """int / int = float (Python 3 语义)"""
        source = '''
def test():
    a: int = 10
    b: int = 3
    c = a / b
    return c
'''
        tc = _get_type_checker(source)
        # 在 Python 3 中，int / int 结果是 float

    def test_int_modulo(self):
        """int % int = int"""
        source = '''
def test():
    a: int = 10
    b: int = 3
    c = a % b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_float_addition(self):
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

    def test_string_concatenation(self):
        """str + str = str"""
        source = '''
def test():
    a: str = "hello"
    b: str = "world"
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_string_repeat(self):
        """str * int = str"""
        source = '''
def test():
    a: str = "hi"
    b: int = 3
    c = a * b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestComparisonTypeInference:
    """比较运算类型推断测试"""

    def test_equality_comparison(self):
        """a == b 返回 bool"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c = a == b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_less_than_comparison(self):
        """a < b 返回 bool"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c = a < b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_greater_than_comparison(self):
        """a > b 返回 bool"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c = a > b
    return c
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_in_operator(self):
        """a in b 返回 bool"""
        source = '''
def test():
    items: list = [1, 2, 3]
    c = 1 in items
    return c
'''
        tc = _get_type_checker(source)
        # in 操作符应返回 bool 类型

    def test_is_operator(self):
        """a is b 返回 bool"""
        source = '''
def test():
    a: int = 1
    b: int = 1
    c = a is b
    return c
'''
        tc = _get_type_checker(source)
        # is 操作符应返回 bool 类型


class TestComplexExpressionInference:
    """复杂表达式类型推断测试"""

    def test_chained_addition(self):
        """连续加法类型推断"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c: int = 3
    d = a + b + c
    return d
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_mixed_arithmetic(self):
        """混合算术运算类型推断"""
        source = '''
def test():
    a: int = 1
    b: float = 2.0
    c = a + b * 2
    return c
'''
        tc = _get_type_checker(source)
        # int + float 应该正确处理

    def test_parenthesized_expression(self):
        """带括号表达式类型推断"""
        source = '''
def test():
    a: int = 1
    b: int = 2
    c: int = 3
    d = (a + b) * c
    return d
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestFunctionReturnTypeInference:
    """函数返回类型推断测试"""

    def test_explicit_return_type(self):
        """显式返回类型声明"""
        source = '''
def add(a: int, b: int) -> int:
    return a + b
'''
        tc = _get_type_checker(source)
        # 函数应被正确注册
        assert 'add' in tc.type_map

    def test_implicit_return_type(self):
        """隐式返回类型推断"""
        source = '''
def add(a: int, b: int):
    return a + b
'''
        tc = _get_type_checker(source)
        # 函数应被正确注册
        assert 'add' in tc.type_map

    def test_function_call_result(self):
        """函数调用结果类型推断"""
        source = '''
def add(a: int, b: int) -> int:
    return a + b

def test():
    result = add(1, 2)
    return result
'''
        tc = _get_type_checker(source)
        assert 'add' in tc.type_map


class TestImplicitObjectType:
    """隐式 object 类型测试"""

    def test_unannotated_variable(self):
        """无注解变量使用 object 类型"""
        source = '''
def test():
    a = 1
    b = "hello"
    return a
'''
        tc = _get_type_checker(source)
        # 无类型注解的变量不应报错

    def test_object_arithmetic(self):
        """object 类型参与运算"""
        source = '''
def test():
    a = 1
    b = 2
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        # object + object = object，不报错

    def test_object_mixed_operation(self):
        """object 与具体类型混合运算"""
        source = '''
def test():
    a = 1
    b: int = 2
    c = a + b
    return c
'''
        tc = _get_type_checker(source)
        # object + int = object，不报错


class TestLambdaTypeInference:
    """Lambda 表达式类型推断测试 - 支持 -> 语法和参数类型注解"""

    def test_lambda_basic(self):
        """基本 Lambda 表达式"""
        source = '''
def test():
    f = lambda x -> x + 1
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_with_typed_params(self):
        """带类型注解的 Lambda 参数"""
        source = '''
def test():
    f = lambda x: int -> x * 2
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_with_multiple_params(self):
        """多参数 Lambda"""
        source = '''
def test():
    f = lambda x, y -> x + y
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_with_typed_multiple_params(self):
        """带类型注解的多参数 Lambda"""
        source = '''
def test():
    f = lambda x: int, y: int -> x + y
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_return_type_inference(self):
        """Lambda 返回类型推断"""
        source = '''
def test():
    f = lambda x: int -> x * 2
    result = f(5)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_as_argument(self):
        """Lambda 作为函数参数"""
        source = '''
def apply(f, x: int) -> int:
    return f(x)

def test():
    result = apply(lambda x: int -> x * 2, 5)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_string_operation(self):
        """Lambda 字符串操作"""
        source = '''
def test():
    f = lambda s -> s + " world"
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_list_operation(self):
        """Lambda 列表操作"""
        source = '''
def test():
    f = lambda items -> items[0]
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_bool_param(self):
        """Lambda 布尔参数类型注解"""
        source = '''
def test():
    f = lambda flag: bool -> flag and True
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_float_return(self):
        """Lambda 浮点运算"""
        source = '''
def test():
    f = lambda x: float -> x * 1.5
    return f
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0


class TestBidirectionalTypeChecking:
    """双向类型检查测试 - 自顶向下的期望类型传播"""

    def test_expected_type_from_declaration(self):
        """从声明类型传播期望类型"""
        source = '''
def test():
    x: int = 42
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_expected_type_from_function_param(self):
        """从函数参数传播期望类型"""
        source = '''
def greet(name: str) -> str:
    return "hello " + name

def test():
    result = greet("world")
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_lambda_type_from_context(self):
        """Lambda 类型从上下文推断（双向）"""
        source = '''
def apply_twice(f, x: int) -> int:
    return f(f(x))

def test():
    inc = lambda x: int -> x + 1
    result = apply_twice(inc, 5)
    return result
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) == 0

    def test_type_mismatch_detection(self):
        """类型不匹配检测"""
        source = '''
def test():
    x: int = "hello"
    return x
'''
        tc = _get_type_checker(source)
        assert len(tc.errors) > 0


class TestTypeClassSupport:
    """类型类（Type Class）支持测试"""

    def test_type_class_registration(self):
        """类型类注册"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        assert "Show" in tc.type_classes
        assert "T" in tc.type_classes["Show"]

    def test_type_class_instance_registration(self):
        """类型类实例注册"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        
        class MockNode:
            pass
        
        impl_node = MockNode()
        tc.register_type_class_instance("Show", "int", impl_node)
        assert ("Show", "int") in tc.type_class_instances

    def test_type_class_resolution(self):
        """类型类方法解析"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        
        # 模拟 impl 节点
        class MockFuncDef:
            def __init__(self, name):
                self.name = name
                self.params = []
                self.body = []
                self.return_type = None
                self.type_annotation = None
                self.id = None
        
        class MockImplNode:
            def __init__(self, methods):
                self.methods = methods
                self.body = methods
        
        show_int_method = MockFuncDef("show")
        impl_node = MockImplNode([show_int_method])
        tc.register_type_class_instance("Show", "int", impl_node)
        
        # 解析方法
        resolved = tc.resolve_type_class_method("Show", "show", "int")
        assert resolved is not None
        assert resolved.name == "show"

    def test_type_class_check_resolution(self):
        """检查类型是否实现了类型类"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        
        class MockImplNode:
            pass
        
        tc.register_type_class_instance("Show", "int", MockImplNode())
        tc.register_type_class_instance("Show", "str", MockImplNode())
        
        assert tc.check_type_class_resolution("Show", "int") == True
        assert tc.check_type_class_resolution("Show", "str") == True
        assert tc.check_type_class_resolution("Show", "float") == False

    def test_type_class_inheritance(self):
        """类型类继承解析"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        
        # 注册继承关系
        tc.inheritance_map["Child"] = ["Parent"]
        
        class MockFuncDef:
            def __init__(self, name):
                self.name = name
                self.params = []
                self.body = []
                self.return_type = None
                self.type_annotation = None
                self.id = None
        
        class MockImplNode:
            def __init__(self, methods):
                self.methods = methods
                self.body = methods
        
        parent_method = MockFuncDef("show")
        parent_impl = MockImplNode([parent_method])
        tc.register_type_class_instance("Show", "Parent", parent_impl)
        
        # Child 应该通过继承获得 Parent 的 Show 实现
        assert tc.check_type_class_resolution("Show", "Child") == True

    def test_type_class_ambiguity_detection(self):
        """类型类歧义检测"""
        tc = TypeChecker()
        tc.register_type_class("Show", {"T": None})
        
        class MockImplNode:
            pass
        
        tc.register_type_class_instance("Show", "int", MockImplNode())
        # 第二次注册同一类型的实例应该报错
        tc.register_type_class_instance("Show", "int", MockImplNode())
        
        assert len(tc.errors) > 0
        assert "Ambiguous" in tc.errors[0]


class TestGenericConstraints:
    """增强的泛型约束测试"""

    def test_union_type_constraint(self):
        """联合类型约束"""
        tc = TypeChecker()
        
        class MockTypeNode:
            def __init__(self, id):
                self.id = id
        
        # 模拟 UnionType 约束
        constraint = type('MockConstraint', (), {
            'kind': 'UnionType',
            'types': [MockTypeNode("int"), MockTypeNode("float")]
        })()
        
        # int 应该满足约束
        tc._check_generic_constraint("T", Type("int"), constraint, None)
        assert len(tc.errors) == 0
        
        # str 不应该满足约束
        tc._check_generic_constraint("T", Type("str"), constraint, None)
        assert len(tc.errors) > 0

    def test_trait_constraint(self):
        """Trait 约束"""
        tc = TypeChecker()
        
        class MockTypeNode:
            def __init__(self, id):
                self.id = id
        
        # 模拟 NamedType 约束（Trait 约束）
        constraint = type('MockConstraint', (), {
            'kind': 'NamedType',
            'id': 'Display',
            'types': [],
            'generic_params': []
        })()
        
        tc.trait_defs["Display"] = True
        tc.trait_impls["Display"] = ["int", "str"]
        
        # int 实现了 Display
        tc._check_generic_constraint("T", Type("int"), constraint, None)
        assert len(tc.errors) == 0
        
        # float 没有实现 Display
        tc._check_generic_constraint("T", Type("float"), constraint, None)
        assert len(tc.errors) > 0

    def test_multiple_trait_constraint(self):
        """多重 Trait 约束"""
        tc = TypeChecker()
        
        class MockTypeNode:
            def __init__(self, id):
                self.id = id
        
        # 模拟 IntersectionType 约束（多重 trait 约束）
        constraint = type('MockConstraint', (), {
            'kind': 'IntersectionType',
            'types': [MockTypeNode("Display"), MockTypeNode("Debug")],
            'generic_params': []
        })()
        
        tc.trait_defs["Display"] = True
        tc.trait_defs["Debug"] = True
        tc.trait_impls["Display"] = ["int"]
        tc.trait_impls["Debug"] = ["int"]
        
        # int 同时实现了 Display 和 Debug
        tc._check_generic_constraint("T", Type("int"), constraint, None)
        assert len(tc.errors) == 0
        
        # 清空错误
        tc.errors.clear()
        
        # str 只实现了 Display，没有实现 Debug
        tc.trait_impls["Display"] = ["int"]
        tc.trait_impls["Debug"] = []
        tc._check_generic_constraint("T", Type("int"), constraint, None)
        assert len(tc.errors) > 0

    def test_f_bounded_constraint(self):
        """F-bounded 约束"""
        tc = TypeChecker()
        
        class MockTypeNode:
            def __init__(self, id):
                self.id = id
        
        # 模拟 F-bounded 约束：Container[T]
        constraint = type('MockConstraint', (), {
            'kind': 'NamedType',
            'id': 'Container',
            'types': [],
            'generic_params': [MockTypeNode("T")]
        })()
        
        # 检查 F-bounded：泛型参数 T 出现在约束的泛型参数中
        tc._check_generic_constraint("T", Type("MyType"), constraint, None)
        # F-bounded 约束应该检查通过
        assert len(tc.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])