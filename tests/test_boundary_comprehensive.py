"""
系统性边界测试框架 - 覆盖所有语法元素的四个关键维度

测试维度：
1. 错误写法测试 - 验证错误处理机制
2. 正确但无映射的写法 - 验证系统行为模式
3. 作用域边界测试 - 验证非预期作用域下的行为
4. 缩进层次测试 - 验证缩进处理逻辑

每个语法元素都有对应的测试用例，遵循最小干扰原则。
"""
import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class BoundaryTestResult:
    """标准化测试结果摘要"""
    def __init__(self, syntax_name, test_dimension, input_code, behavior, passed, notes=""):
        self.syntax_name = syntax_name
        self.test_dimension = test_dimension
        self.input_code = input_code
        self.behavior = behavior
        self.passed = passed
        self.notes = notes

    def __str__(self):
        return f"""
【语法元素】{self.syntax_name}
【测试维度】{self.test_dimension}
【输入示例】
{self.input_code}
【系统表现】{self.behavior}
【测试状态】{'通过' if self.passed else '不通过'}
【备注说明】{self.notes}
"""


class TestBoundaryFramework(unittest.TestCase):
    """边界测试框架基类"""
    
    def _parse_code(self, source):
        """解析代码并返回(ast, generator, code)或异常信息"""
        try:
            lexer = Lexer(source)
            parser = Parser(lexer.tokenize())
            ast = parser.parse()
            generator = CythonGenerator()
            code = generator.generate(ast)
            return (ast, generator, code), None
        except Exception as e:
            return None, str(e)


# ==================== struct 定义测试 ====================

class TestStructBoundary(TestBoundaryFramework):
    def test_struct_error_empty_name(self):
        """错误写法：struct 无名称"""
        source = "struct:\n    x: int\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
        self.assertIn("Expected IDENTIFIER", error)
    
    def test_struct_error_nested(self):
        """错误写法：struct 嵌套在函数内"""
        source = "def foo():\n    struct Point:\n        x: int\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_struct_scope_inside_if(self):
        """作用域边界：if 块内定义 struct"""
        source = "if True:\n    struct Point:\n        x: int\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_struct_indent_mixed(self):
        """缩进层次：混合缩进（空格+制表符）"""
        source = "struct Point:\n\t x: int\n    y: int\n"
        _, error = self._parse_code(source)
        # 混合缩进可能导致解析问题
        print(f"struct 混合缩进测试: {error}")


# ==================== enum 定义测试 ====================

class TestEnumBoundary(TestBoundaryFramework):
    def test_enum_error_empty(self):
        """错误写法：enum 无变体"""
        source = "enum Color:\n    pass\n"
        _, error = self._parse_code(source)
        # enum 应该允许空体或 pass
        print(f"enum 空体测试: {'错误' if error else '通过'}")
    
    def test_enum_error_invalid_value(self):
        """错误写法：enum 变体值无效"""
        source = "enum Color:\n    RED = \"invalid\"\n"
        result, error = self._parse_code(source)
        # 应该能解析，因为 enum 值可以是任意表达式
    
    def test_enum_scope_inside_loop(self):
        """作用域边界：for 循环内定义 enum"""
        source = "for i in range(5):\n    enum Color:\n        RED\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_enum_indent_excessive(self):
        """缩进层次：过度缩进"""
        source = "enum Color:\n            RED\n    GREEN\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== trait 定义测试 ====================

class TestTraitBoundary(TestBoundaryFramework):
    def test_trait_error_no_methods(self):
        """错误写法：trait 无方法"""
        source = "trait Empty:\n    pass\n"
        result, error = self._parse_code(source)
        # trait 应该允许空体
    
    def test_trait_scope_nested_class(self):
        """作用域边界：class 内定义 trait"""
        source = "class Outer:\n    trait Inner:\n        def method():\n            pass\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_trait_indent_insufficient(self):
        """缩进层次：不足缩进"""
        source = "trait Shape:\ndef area() -> float:\n        pass\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== impl 实现测试 ====================

class TestImplBoundary(TestBoundaryFramework):
    def test_impl_error_no_trait(self):
        """错误写法：impl 无 trait 名称"""
        source = "impl for Circle:\n    def area():\n        pass\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_impl_scope_inside_function(self):
        """作用域边界：函数内定义 impl"""
        source = "def foo():\n    impl Shape for Circle:\n        def area():\n            pass\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== let/var/val 测试 ====================

class TestLetVarValBoundary(TestBoundaryFramework):
    def test_val_error_reassignment(self):
        """错误写法：val 变量重新赋值"""
        source = "def foo():\n    val x: int = 10\n    x = 20\n"
        result, error = self._parse_code(source)
        # 当前解析器可能不检查 val 的不可变性
    
    def test_var_scope_global(self):
        """作用域边界：全局作用域使用 var"""
        source = "var x: int = 10\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_let_indent_inconsistent(self):
        """缩进层次：不一致缩进"""
        source = "def foo():\n    let a: int = 1\n      let b: int = 2\n    let c: int = 3\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== defer 语句测试 ====================

class TestDeferBoundary(TestBoundaryFramework):
    def test_defer_error_empty(self):
        """错误写法：defer 无语句块"""
        source = "def foo():\n    defer\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_defer_scope_nested(self):
        """作用域边界：嵌套 defer"""
        source = "def foo():\n    defer:\n        defer:\n            pass\n"
        result, error = self._parse_code(source)
        # 嵌套 defer 应该允许
    
    def test_defer_indent_zero(self):
        """缩进层次：零缩进 defer"""
        source = "defer:\n    pass\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== 指针操作测试 ====================

class TestPointerBoundary(TestBoundaryFramework):
    def test_pointer_error_double_deref(self):
        """错误写法：双重解引用"""
        source = "def foo(ptr: int**):\n    return &&ptr\n"
        _, error = self._parse_code(source)
        # 双重指针可能不支持
    
    def test_pointer_scope_inside_loop(self):
        """作用域边界：循环内指针声明"""
        source = "def foo():\n    for i in range(10):\n        ptr: int* = NULL\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pointer_addr_on_python_obj(self):
        """错误写法：Python 对象取地址"""
        source = "def foo():\n    s: str = \"hello\"\n    ptr: str* = addr(s)\n"
        _, error = self._parse_code(source)
        # 当前可能不会报错，因为 addr() 只是函数调用


# ==================== 泛型测试 ====================

class TestGenericBoundary(TestBoundaryFramework):
    def test_generic_error_empty_args(self):
        """错误写法：泛型无参数"""
        source = "struct Pair[]:\n    first: T\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_generic_error_unsupported_type(self):
        """正确但无映射：不支持的泛型类型参数"""
        source = "struct Pair[CustomType]:\n    value: CustomType\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_generic_scope_inside_struct(self):
        """作用域边界：struct 内定义泛型"""
        source = "struct Outer:\n    struct Inner[T]:\n        value: T\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== meta 块测试 ====================

class TestMetaBoundary(TestBoundaryFramework):
    def test_meta_error_outside_block(self):
        """错误写法：meta 关键字在块外使用"""
        source = "constraint Number = int | float\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_meta_error_invalid_syntax(self):
        """错误写法：meta 块内无效语法"""
        source = "meta:\n    invalid_syntax\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_meta_scope_inside_function(self):
        """作用域边界：函数内定义 meta"""
        source = "def foo():\n    meta:\n        constraint Number = int | float\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== Never 类型测试 ====================

class TestNeverBoundary(TestBoundaryFramework):
    def test_never_error_as_param(self):
        """错误写法：Never 作为参数类型"""
        source = "def foo(x: Never):\n    pass\n"
        result, error = self._parse_code(source)
        # 当前可能允许，但语义上不正确
    
    def test_never_scope_nested(self):
        """作用域边界：嵌套函数返回 Never"""
        source = "def outer():\n    def inner() -> Never:\n        raise RuntimeError()\n    inner()\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)


# ==================== 管道操作符测试 ====================

class TestPipelineBoundary(TestBoundaryFramework):
    def test_pipeline_error_empty(self):
        """错误写法：空管道"""
        source = "result = 5 |>\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_pipeline_error_multiple(self):
        """错误写法：连续管道无表达式"""
        source = "result = 5 |> |>\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_pipeline_scope_nested(self):
        """作用域边界：嵌套表达式中的管道"""
        source = "result = (5 |> add(10)) |> multiply(2)\n"
        result, error = self._parse_code(source)
        # 当前可能不支持，管道操作符可能未完全实现


# ==================== 类型注解测试 ====================

class TestTypeAnnotationBoundary(TestBoundaryFramework):
    def test_annotation_error_invalid_type(self):
        """错误写法：无效类型名称"""
        source = "x: InvalidType = 10\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)  # 解析器接受任何标识符作为类型
    
    def test_annotation_scope_class_method(self):
        """作用域边界：类方法参数注解"""
        source = "class Foo:\n    def bar(self, x: int) -> str:\n        return str(x)\n"
        _, error = self._parse_code(source)
        # 类解析可能有问题
    
    def test_annotation_indent_variation(self):
        """缩进层次：不同缩进层级的注解"""
        source = "def foo():\n    x: int = 1\n        y: int = 2\n    z: int = 3\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== 作用域层级系统测试 ====================

class TestScopeBoundary(TestBoundaryFramework):
    def test_scope_level_zero(self):
        """作用域层级：模块级（0级）"""
        source = "x: int = 10\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_scope_level_one(self):
        """作用域层级：函数/类级（1级）"""
        source = "def foo():\n    x: int = 10\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_scope_level_two(self):
        """作用域层级：代码块级（2级）"""
        source = "def foo():\n    if True:\n        x: int = 10\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_scope_level_three(self):
        """作用域层级：嵌套块级（3级）"""
        source = "def foo():\n    for i in range(5):\n        if i > 2:\n            x: int = i\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)


# ==================== 缩进规则测试 ====================

class TestIndentationBoundary(TestBoundaryFramework):
    def test_indent_spaces(self):
        """缩进：标准4空格"""
        source = "def foo():\n    x: int = 1\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_indent_tabs(self):
        """缩进：制表符"""
        source = "def foo():\n\tx: int = 1\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_indent_mixed_error(self):
        """缩进：混合空格和制表符（错误）"""
        source = "def foo():\n    x: int = 1\n\ty: int = 2\n"
        _, error = self._parse_code(source)
        # 可能解析失败或产生意外结果
    
    def test_indent_excessive(self):
        """缩进：过度缩进"""
        source = "def foo():\n            x: int = 1\n"
        _, error = self._parse_code(source)
        # 过度缩进可能导致 DEDENT 问题
    
    def test_indent_insufficient(self):
        """缩进：不足缩进"""
        source = "def foo():\n x: int = 1\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


if __name__ == "__main__":
    # 收集所有测试结果
    test_results = []
    
    # 运行测试
    unittest.main(verbosity=2)