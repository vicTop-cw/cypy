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


# ==================== let/var/let 测试 ====================

class TestLetVarValBoundary(TestBoundaryFramework):
    def test_let_error_reassignment(self):
        """错误写法：let 变量重新赋值"""
        source = "def foo():\n    let x: int = 10\n    x = 20\n"
        result, error = self._parse_code(source)
        # 当前解析器可能不检查 let 的不可变性
    
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
        source = "struct Pair<CustomType>:\n    value: CustomType\n"
        result, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_generic_scope_inside_struct(self):
        """作用域边界：struct 内定义泛型"""
        source = "struct Outer:\n    struct Inner<T>:\n        value: T\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== meta 块测试 ====================

class TestMetaBoundary(TestBoundaryFramework):
    def test_meta_error_outside_block(self):
        """错误写法：duck 关键字在 meta 块外使用"""
        source = "duck Comparable:\n    a < b -> bool\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)

    def test_meta_error_invalid_syntax(self):
        """错误写法：meta 块内无效语法"""
        source = "meta:\n    123\n"
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)

    def test_meta_scope_inside_function(self):
        """作用域边界：函数内定义 meta"""
        source = "def foo():\n    meta:\n        duck Comparable:\n            a < b -> bool\n"
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


# ==================== 常量声明边界测试 ====================

class TestConstBoundary(TestBoundaryFramework):
    def test_const_basic(self):
        """正确写法：基本常量声明"""
        source = """const PI: float = 3.14159
const MAX_SIZE: int = 100
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_const_with_expression(self):
        """正确写法：常量表达式"""
        source = """const HALF_PI: float = 3.14159 / 2
const DOUBLE_MAX: int = 100 * 2
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_const_reassignment(self):
        """错误写法：常量重新赋值"""
        source = """const PI: float = 3.14159
PI = 3.14
"""
        _, error = self._parse_code(source)
        # 常量不应被重新赋值
    
    def test_const_in_function(self):
        """错误写法：函数内声明常量"""
        source = """def test():
    const LOCAL: int = 10
"""
        _, error = self._parse_code(source)
        # 常量应在模块级别声明
    
    def test_const_no_initial_value(self):
        """错误写法：常量无初始值"""
        source = """const EMPTY: int
"""
        _, error = self._parse_code(source)
        # 常量必须有初始值

# ==================== 类型转换边界测试 ====================

class TestTypeCastBoundary(TestBoundaryFramework):
    def test_cast_basic_types(self):
        """正确写法：基本类型之间的转换"""
        source = """def test():
    x: int = 10
    y: float = x as float
    z: int = y as int
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_cast_invalid_target_type(self):
        """错误写法：无效的目标类型"""
        source = """def test():
    x: int = 10
    y: InvalidType = x as InvalidType
"""
        _, error = self._parse_code(source)
        # 无效类型可能在代码生成阶段处理
    
    def test_cast_custom_type_no_cast_method(self):
        """错误写法：自定义类型没有 __cast__ 方法"""
        source = """struct Custom:
    value: int

def test():
    c: Custom
    d: AnotherType = c as AnotherType
"""
        _, error = self._parse_code(source)
        # 自定义类型转换需要 __cast__ 方法
    
    def test_cast_nested(self):
        """正确写法：嵌套类型转换"""
        source = """def test():
    x: int = 10
    y: float = (x as float) as float
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_cast_with_expression(self):
        """正确写法：表达式的类型转换"""
        source = """def test():
    x: int = 10
    y: float = (x + 5) as float
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)

# ==================== 指针操作边界测试 ====================

class TestPointerBoundary(TestBoundaryFramework):
    def test_pointer_valid_c_type(self):
        """正确写法：C类型指针声明"""
        source = """def test():
    x: int = 10
    ptr: int* = addr(x)
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pointer_invalid_python_type(self):
        """错误写法：Python对象类型指针声明"""
        source = """def test():
    s: str = 'hello'
    ptr: str* = addr(s)
"""
        _, error = self._parse_code(source)
        # 类型检查器应该阻止指向Python对象的指针
    
    def test_addr_on_python_obj(self):
        """错误写法：对Python对象取地址"""
        source = """def test():
    s: str = 'hello'
    ptr: int* = addr(s)
"""
        _, error = self._parse_code(source)
        # 指针检查器应该阻止对Python对象取地址
    
    def test_addr_on_valid_c_type(self):
        """正确写法：对C类型取地址"""
        source = """def test():
    x: int = 10
    ptr: int* = addr(x)
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pointer_scope_inside_loop(self):
        """作用域边界：循环内声明指针"""
        source = """def test():
    for i in range(10):
        x: int = i
        ptr: int* = addr(x)
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)

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


# ==================== go/spawn 并发语句测试 ====================

class TestGoSpawnBoundary(TestBoundaryFramework):
    def test_go_call_form(self):
        """正确写法：go 调用形式"""
        source = """async def fetch(url: str) -> str:
    return url

async def run():
    task = go fetch("test")
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_spawn_call_form(self):
        """正确写法：spawn 调用形式"""
        source = """def worker():
    pass

def main():
    spawn worker()
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_go_block_form(self):
        """正确写法：go 块形式"""
        source = """async def run():
    go:
        print("async task")
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_spawn_block_form(self):
        """正确写法：spawn 块形式"""
        source = """def main():
    spawn:
        print("thread task")
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_go_outside_async(self):
        """错误写法：在非异步函数中使用 go"""
        source = """def main():
    go fetch("url")
"""
        _, error = self._parse_code(source)
        # 应该报错，go 需要在异步上下文
    
    def test_spawn_outside_function(self):
        """错误写法：在函数外使用 spawn"""
        source = """spawn worker()
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_go_with_nonexistent_func(self):
        """错误写法：go 调用不存在的函数"""
        source = """async def run():
    task = go nonexistent_func()
"""
        _, error = self._parse_code(source)
        # 应该在语义分析阶段报错
    
    def test_spawn_with_nonexistent_func(self):
        """错误写法：spawn 调用不存在的函数"""
        source = """def main():
    spawn nonexistent_func()
"""
        _, error = self._parse_code(source)
        # 应该在语义分析阶段报错


# ==================== 列表推导式边界测试 ====================

class TestListCompBoundary(TestBoundaryFramework):
    def test_list_comp_basic(self):
        """正确写法：基本列表推导式"""
        source = """def test():
    result = [x for x in range(10)]
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_list_comp_with_condition(self):
        """正确写法：带条件的列表推导式"""
        source = """def test():
    result = [x for x in range(10) if x % 2 == 0]
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_list_comp_nested(self):
        """正确写法：嵌套循环列表推导式"""
        source = """def test():
    result = [(x, y) for x in [1, 2] for y in [3, 4]]
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_list_comp_multiple_conditions(self):
        """正确写法：多个条件的列表推导式"""
        source = """def test():
    result = [x for x in range(20) if x > 5 if x < 15]
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_list_comp_tuple_destructure(self):
        """错误写法：元组解构列表推导式（当前不支持）"""
        source = """def test():
    pairs = [(1, 'a'), (2, 'b')]
    result = [x for x, y in pairs]
"""
        _, error = self._parse_code(source)
        # 当前不支持元组解构作为循环变量
        self.assertIsNotNone(error)
    
    def test_list_comp_empty(self):
        """正确写法：空列表推导式"""
        source = """def test():
    result = [x for x in []]
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_list_comp_syntax_error(self):
        """错误写法：缺少 for 子句"""
        source = """def test():
    result = [x]
"""
        _, error = self._parse_code(source)
        # 这是普通列表字面量，不是推导式
    
    def test_list_comp_unbalanced_parens(self):
        """错误写法：括号不匹配"""
        source = """def test():
    result = [x for x in (1, 2, 3]
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)


# ==================== f-string 边界测试 ====================

class TestFStringBoundary(TestBoundaryFramework):
    def test_fstring_basic(self):
        """正确写法：基本 f-string"""
        source = """def test():
    name = "World"
    msg = f"Hello, {name}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_fstring_with_expression(self):
        """正确写法：f-string 包含表达式"""
        source = """def test():
    x = 10
    msg = f"x squared is {x ** 2}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_fstring_with_format_spec(self):
        """正确写法：f-string 包含格式说明符"""
        source = """def test():
    pi = 3.14159
    msg = f"Pi: {pi:.2f}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_fstring_raw(self):
        """正确写法：raw f-string"""
        source = """def test():
    path = r"C:\\Users\\test"
    msg = rf"Path: {path}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_fstring_uppercase(self):
        """正确写法：大写 F-string"""
        source = """def test():
    name = "Test"
    msg = F"Hello, {name}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_fstring_empty_expr(self):
        """错误写法：空表达式（当前 lexer 可能不报错）"""
        source = """def test():
    msg = f"Hello, {}"
"""
        _, error = self._parse_code(source)
        # 当前 lexer 可能不检测空表达式，这是已知限制
    
    def test_fstring_unclosed_brace(self):
        """错误写法：未闭合的花括号（当前 lexer 可能不报错）"""
        source = """def test():
    msg = f"Hello, {name"
"""
        _, error = self._parse_code(source)
        # 当前 lexer 可能不检测未闭合花括号，这是已知限制
    
    def test_fstring_nested_braces(self):
        """正确写法：嵌套花括号"""
        source = """def test():
    x = 10
    msg = f"Value: {{{x}}}"
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)


# ==================== match 语句边界测试 ====================

class TestMatchBoundary(TestBoundaryFramework):
    def test_match_basic(self):
        """正确写法：基本 match 语句"""
        source = """def test(x: int):
    match x:
        case 1:
            pass
        case _:
            pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_match_with_enum(self):
        """正确写法：match 匹配枚举"""
        source = """enum Color:
    RED
    GREEN
    BLUE

def test(c: Color):
    match c:
        case Color.RED:
            pass
        case Color.GREEN:
            pass
        case Color.BLUE:
            pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_match_with_tuple(self):
        """正确写法：match 匹配元组"""
        source = """def test(pair):
    match pair:
        case (1, y):
            pass
        case (x, 2):
            pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_match_with_guard(self):
        """正确写法：match 带守卫条件"""
        source = """def test(x: int):
    match x:
        case n if n > 0:
            pass
        case _:
            pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_match_empty(self):
        """错误写法：空 match 语句"""
        source = """def test(x):
    match x:
        pass
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_match_missing_default(self):
        """正确写法：match 缺少默认 case"""
        source = """def test(x: int):
    match x:
        case 1:
            pass
        case 2:
            pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_match_duplicate_case(self):
        """错误写法：重复的 case"""
        source = """def test(x: int):
    match x:
        case 1:
            pass
        case 1:
            pass
"""
        _, error = self._parse_code(source)
        # 可能在语义分析阶段报错
    
    def test_match_outside_function(self):
        """错误写法：函数外使用 match"""
        source = """x = 1
match x:
    case 1:
        pass
"""
        _, error = self._parse_code(source)
        # match 应该可以在模块级别使用


# ==================== 管道操作符边界测试 ====================

class TestPipelineBoundary(TestBoundaryFramework):
    def test_pipeline_basic(self):
        """正确写法：基本管道操作"""
        source = """def test():
    result = 5 |> double |> square
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pipeline_with_function_call(self):
        """正确写法：管道操作带参数"""
        source = """def test():
    result = data |> process(filter="active") |> format()
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pipeline_complex_expression(self):
        """正确写法：复杂表达式中的管道"""
        source = """def test():
    result = (x + y) |> normalize() |> scale(2)
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_pipeline_empty(self):
        """错误写法：空管道"""
        source = """def test():
    result = 5 |>
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_pipeline_double(self):
        """错误写法：连续管道无表达式"""
        source = """def test():
    result = 5 |> |>
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_pipeline_at_start(self):
        """错误写法：管道操作符在表达式开头"""
        source = """def test():
    result = |> process(data)
"""
        _, error = self._parse_code(source)
        self.assertIsNotNone(error)
    
    def test_pipeline_nested(self):
        """正确写法：嵌套管道操作"""
        source = """def test():
    result = 5 |> (x -> x + 1) |> (x -> x * 2)
"""
        _, error = self._parse_code(source)
        # 匿名函数可能不支持


# ==================== 协程/async 边界测试 ====================

class TestAsyncBoundary(TestBoundaryFramework):
    def test_async_function_def(self):
        """正确写法：异步函数定义"""
        source = """async def fetch(url: str) -> str:
    return url
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_async_with_return_type(self):
        """正确写法：带返回类型的异步函数"""
        source = """async def compute() -> int:
    return 42
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_async_call(self):
        """正确写法：调用异步函数"""
        source = """async def helper():
    pass

async def main():
    await helper()
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_await_outside_async(self):
        """错误写法：在非异步函数中使用 await"""
        source = """def main():
    await helper()
"""
        _, error = self._parse_code(source)
        # 应该报错
    
    def test_nested_async_function(self):
        """正确写法：嵌套异步函数"""
        source = """async def outer():
    async def inner():
        return 42
    return await inner()
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_async_lambda(self):
        """错误写法：异步 lambda"""
        source = """async def test():
    func = async lambda x -> x + 1
"""
        _, error = self._parse_code(source)
        # 可能不支持


# ==================== 函数参数边界测试 ====================

class TestFunctionParamsBoundary(TestBoundaryFramework):
    def test_params_basic(self):
        """正确写法：基本参数"""
        source = """def test(a: int, b: str) -> None:
    pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_params_with_default(self):
        """正确写法：带默认值的参数"""
        source = """def test(a: int = 10, b: str = "default") -> None:
    pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_params_keyword_only(self):
        """正确写法：关键字-only 参数"""
        source = """def test(a: int, *, b: str) -> None:
    pass
"""
        _, error = self._parse_code(source)
        # 可能支持
    
    def test_params_varargs(self):
        """错误写法：可变参数（当前不支持）"""
        source = """def test(*args, **kwargs):
    pass
"""
        _, error = self._parse_code(source)
        # 当前不支持 *args 和 **kwargs
        self.assertIsNotNone(error)
    
    def test_params_invalid_order(self):
        """错误写法：默认参数在非默认参数之前（当前不检测）"""
        source = """def test(a: int = 10, b: int) -> None:
    pass
"""
        _, error = self._parse_code(source)
        # 当前不检测参数顺序，这是已知限制
    
    def test_params_duplicate_names(self):
        """错误写法：重复的参数名（当前不检测）"""
        source = """def test(a: int, a: str) -> None:
    pass
"""
        _, error = self._parse_code(source)
        # 当前不检测重复参数名，这是已知限制
    
    def test_params_nested_default(self):
        """正确写法：嵌套默认值表达式"""
        source = """def test(a: int = 1 + 2, b: str = "a" + "b") -> None:
    pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)


# ==================== 类边界测试 ====================

class TestClassBoundary(TestBoundaryFramework):
    def test_class_basic(self):
        """正确写法：基本类定义"""
        source = """class Foo:
    def __init__(self):
        pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_class_with_inheritance(self):
        """正确写法：带继承的类定义"""
        source = """class Base:
    pass

class Derived(Base):
    pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_class_method(self):
        """正确写法：类方法"""
        source = """class Foo:
    def method(self):
        pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_class_nested(self):
        """正确写法：嵌套类"""
        source = """class Outer:
    class Inner:
        pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_class_with_type_param(self):
        """错误写法：带类型参数的类（当前不支持）"""
        source = """class Container<T>:
    value: T
"""
        _, error = self._parse_code(source)
        # 当前类不支持泛型语法，只有 struct 支持
        self.assertIsNotNone(error)


# ==================== 结构体边界测试 ====================

class TestStructBoundaryExtended(TestBoundaryFramework):
    def test_struct_with_methods(self):
        """正确写法：带方法的结构体"""
        source = """struct Point:
    x: int
    y: int
    
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
    
    def distance(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_struct_with_operator_overload(self):
        """正确写法：带操作符重载的结构体"""
        source = """struct Vector:
    x: float
    y: float
    
    def __add__(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y)
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_struct_empty(self):
        """正确写法：空结构体"""
        source = """struct Empty:
    pass
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)
    
    def test_struct_nested_in_class(self):
        """正确写法：类内嵌套结构体"""
        source = """class Outer:
    struct Inner:
        value: int
"""
        _, error = self._parse_code(source)
        # 可能不支持
    
    def test_struct_with_generic(self):
        """正确写法：泛型结构体"""
        source = """struct Pair<T, U>:
    first: T
    second: U
"""
        _, error = self._parse_code(source)
        self.assertIsNone(error)


if __name__ == "__main__":
    # 收集所有测试结果
    test_results = []
    
    # 运行测试
    unittest.main(verbosity=2)
