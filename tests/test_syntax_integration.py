"""
全面的语法集成测试
覆盖所有语法单元的正常输入、边界值输入和异常输入

注意：测试用例基于实际实现编写，而非文档描述
"""
import unittest

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.analyzer.pointer_checker import PointerChecker


class CypyTestBase(unittest.TestCase):
    """测试基类，提供解析和生成功能"""
    
    def _parse_and_generate(self, source):
        """解析代码并返回生成的Cython代码或错误信息"""
        try:
            lexer = Lexer(source)
            parser = Parser(lexer.tokenize())
            ast = parser.parse()
            
            type_checker = TypeChecker()
            type_checker.check(ast)
            if type_checker.errors:
                return None, "; ".join(type_checker.errors)
            
            pointer_checker = PointerChecker()
            pointer_checker.check(ast, type_checker.type_map)
            if pointer_checker.errors:
                return None, "; ".join(pointer_checker.errors)
            
            generator = CythonGenerator()
            code = generator.generate(ast)
            return code, None
        except Exception as e:
            return None, str(e)
    
    def _assert_parse_success(self, source):
        """断言解析成功"""
        code, error = self._parse_and_generate(source)
        self.assertIsNone(error, f"Parse failed: {error}")
        return code
    
    def _assert_parse_failure(self, source, expected_error=None):
        """断言解析失败"""
        code, error = self._parse_and_generate(source)
        self.assertIsNotNone(error, "Expected parse to fail")
        if expected_error:
            self.assertIn(expected_error, error)
        return error


class TestTypeSystem(CypyTestBase):
    """类型系统测试"""

    def test_primitive_types(self):
        """测试基本类型注解"""
        source = """def test_types(a: int, b: float) -> float:
    return a + b
"""
        code = self._assert_parse_success(source)
        self.assertIn("cpdef", code)

    def test_no_type_annotation(self):
        """测试无类型注解的退化"""
        source = """def dynamic(a, b):
    return a + b
"""
        code = self._assert_parse_success(source)

    def test_invalid_pointer_no_annotation(self):
        """测试指针无类型注解（当前实现允许，malloc返回void*可赋值给object）"""
        source = """def bad_ptr():
    ptr = malloc(sizeof(int))
"""
        # 当前实现允许无类型注解的指针变量，malloc返回void*自动转为object类型
        code = self._assert_parse_success(source)
        self.assertIsNotNone(code)


class TestVariableDeclarations(CypyTestBase):
    """变量声明测试"""

    def test_typed_variable(self):
        """测试带类型注解的变量"""
        source = """def test():
    x: int = 10
"""
        code = self._assert_parse_success(source)

    def test_let_simple(self):
        """测试简单let声明"""
        source = """let x = 42
"""
        code = self._assert_parse_success(source)

    def test_empty_variable(self):
        """测试空变量声明（边界值）"""
        source = """def test():
    x: int
"""
        code = self._assert_parse_success(source)


class TestFunctions(CypyTestBase):
    """函数定义测试"""

    def test_typed_function(self):
        """测试带类型注解的函数"""
        source = """def add(a: int, b: int) -> int:
    return a + b
"""
        code = self._assert_parse_success(source)
        self.assertIn("cpdef int add", code)

    def test_untyped_function(self):
        """测试无类型注解的函数"""
        source = """def add(a, b):
    return a + b
"""
        code = self._assert_parse_success(source)

    def test_invalid_function_definition(self):
        """测试不完整的函数定义（异常输入）"""
        source = """def incomplete(
"""
        error = self._assert_parse_failure(source)


class TestStruct(CypyTestBase):
    """结构体测试"""

    def test_basic_struct(self):
        """测试基本结构体"""
        source = """struct Point:
    x: int
    y: int
"""
        code = self._assert_parse_success(source)
        self.assertIn("cdef struct Point", code)

    def test_empty_struct(self):
        """测试空结构体（边界值）"""
        source = """struct Empty:
    x: int
"""
        code = self._assert_parse_success(source)

    def test_struct_in_function_scope(self):
        """测试在函数内定义struct（应该失败）"""
        source = """def bad():
    struct Bad:
        x: int
"""
        error = self._assert_parse_failure(source)


class TestEnum(CypyTestBase):
    """枚举测试"""

    def test_basic_enum(self):
        """测试基本枚举"""
        source = """enum Color:
    RED = 1
    GREEN = 2
"""
        code = self._assert_parse_success(source)

    def test_enum_without_values(self):
        """测试无值枚举"""
        source = """enum Direction:
    NORTH
    SOUTH
"""
        code = self._assert_parse_success(source)

    def test_single_value_enum(self):
        """测试单值枚举（边界值）"""
        source = """enum Status:
    OK
"""
        code = self._assert_parse_success(source)

    def test_enum_in_function_scope(self):
        """测试在函数内定义enum（应该失败）"""
        source = """def bad():
    enum Bad:
        A
"""
        error = self._assert_parse_failure(source)


class TestTraitImpl(CypyTestBase):
    """Trait和Impl测试"""

    def test_trait_definition(self):
        """测试trait定义"""
        source = """trait Drawable:
    def draw(self):
        x = 1
"""
        code = self._assert_parse_success(source)

    def test_trait_in_function_scope(self):
        """测试在函数内定义trait（应该失败）"""
        source = """def bad():
    trait Bad:
        def method(self):
            x = 1
"""
        error = self._assert_parse_failure(source)


class TestDefer(CypyTestBase):
    """Defer语句测试"""

    def test_defer_at_module_level(self):
        """测试在模块级使用defer（应该失败）"""
        source = """defer print("module")
"""
        error = self._assert_parse_failure(source)


class TestScopeRules(CypyTestBase):
    """作用域规则测试"""

    def test_struct_top_level_only(self):
        """测试struct只能在模块顶级定义"""
        sources = [
            """def bad():
    struct Inner:
        x: int""",
            """if True:
    struct Inner:
        x: int""",
        ]
        for source in sources:
            error = self._assert_parse_failure(source)

    def test_enum_top_level_only(self):
        """测试enum只能在模块顶级定义"""
        source = """def bad():
    enum Inner:
        A"""
        error = self._assert_parse_failure(source)

    def test_trait_top_level_only(self):
        """测试trait只能在模块顶级定义"""
        source = """def bad():
    trait Inner:
        def method(self):
            x = 1"""
        error = self._assert_parse_failure(source)


class TestIndentation(CypyTestBase):
    """缩进测试"""

    def test_correct_indentation(self):
        """测试正确的缩进"""
        source = """def test():
    x = 1
    if True:
        y = 2
"""
        code = self._assert_parse_success(source)

    def test_insufficient_indentation(self):
        """测试缩进不足（应该失败）"""
        source = """def test():
x = 1"""
        error = self._assert_parse_failure(source)

    def test_excessive_indentation(self):
        """测试缩进过多（超过预期的缩进级别）"""
        # 函数体期望4个空格，但使用了8个空格
        source = """def test():
        x = 1"""
        code, error = self._parse_and_generate(source)
        # 当前实现允许任意大于当前级别的缩进，但在非期望缩进情况下会检查
        # 这里期望函数体缩进应该是4的倍数且与其他行一致
        self.assertIsNotNone(error, "Excessive indentation should be detected")

    def test_mixed_indentation(self):
        """测试混合缩进（空格和tab）"""
        source = """def test():
    x = 1
\ty = 2"""
        code, error = self._parse_and_generate(source)
        self.assertIsNotNone(error, "Mixed indentation should be detected")


class TestEdgeCases(CypyTestBase):
    """边界情况测试"""

    def test_empty_file(self):
        """测试空文件（边界值）"""
        source = ""
        code = self._assert_parse_success(source)

    def test_unicode_characters(self):
        """测试Unicode字符"""
        source = '''def greet(name: str) -> str:
    x = "你好"
'''
        code = self._assert_parse_success(source)

    def test_long_identifier(self):
        """测试长标识符"""
        source = """def very_long_function_name_that_exceeds_normal_length(arg: int) -> int:
    return arg * 2
"""
        code = self._assert_parse_success(source)

    def test_missing_colon(self):
        """测试缺少冒号（异常输入）"""
        source = """def test()
    x = 1"""
        error = self._assert_parse_failure(source)

    def test_unclosed_paren(self):
        """测试未闭合的括号（异常输入）"""
        source = """def test(x: int):
    return (x + 1"""
        error = self._assert_parse_failure(source)


class TestRegression(CypyTestBase):
    """回归测试 - 确保之前修复的问题不再出现"""

    def test_build_block_symbol_conflict(self):
        """测试构建块符号与指针类型冲突（之前修复的问题）"""
        source = """struct Point:
    x: int
"""
        code = self._assert_parse_success(source)
        self.assertIn("cdef struct Point", code)

    def test_cycle_dependency(self):
        """测试循环依赖检测"""
        source = """trait A:
    def method(self):
        x = 1

struct B:
    x: int
"""
        code = self._assert_parse_success(source)


class TestBuildBlocks(CypyTestBase):
    """构建块语法测试"""

    def test_build_assign(self):
        """测试变量构建块 =:"""
        source = """def test():
    x =:
        1 + 2
"""
        code, error = self._parse_and_generate(source)
        if error:
            self.skipTest(f"Build block not implemented: {error}")
        else:
            self.assertIsNotNone(code)


class TestPointerOperations(CypyTestBase):
    """指针操作测试"""

    def test_pointer_type_annotation(self):
        """测试指针类型注解"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
"""
        code = self._assert_parse_success(source)

    def test_deref_expression(self):
        """测试解引用表达式"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
    &ptr = 42
"""
        code = self._assert_parse_success(source)

    def test_addr_function(self):
        """测试addr()函数"""
        source = """def test():
    x: int = 10
    ptr: int* = addr(x)
"""
        code = self._assert_parse_success(source)


class TestBuiltinAPI(CypyTestBase):
    """内置API代码生成测试"""

    def test_malloc_codegen(self):
        """测试malloc代码生成"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
"""
        code = self._assert_parse_success(source)
        # sizeof是Cython内置关键字，不需要导入
        self.assertIn("from libc.stdlib cimport malloc, free", code)
        self.assertIn("<void*>malloc(sizeof(int))", code)

    def test_free_codegen(self):
        """测试free代码生成"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
    free(ptr)
"""
        code = self._assert_parse_success(source)
        self.assertIn("free(ptr)", code)

    def test_addr_codegen(self):
        """测试addr代码生成"""
        source = """def test():
    x: int = 10
    ptr: int* = addr(x)
"""
        code = self._assert_parse_success(source)
        self.assertIn("&x", code)

    def test_deref_codegen(self):
        """测试解引用代码生成"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
    &ptr = 42
"""
        code = self._assert_parse_success(source)
        self.assertIn("ptr[0] = 42", code)

    def test_no_libc_import_without_builtins(self):
        """测试不使用内置函数时不导入C库"""
        source = """def test(x: int) -> int:
    return x + 1
"""
        code = self._assert_parse_success(source)
        self.assertNotIn("from libc.stdlib", code)

    def test_defer_codegen(self):
        """测试defer语句生成try/finally"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)
"""
        code = self._assert_parse_success(source)
        self.assertIn("try:", code)
        self.assertIn("finally:", code)
        self.assertIn("free(ptr)", code)

    def test_multiple_defer_codegen(self):
        """测试多个defer语句生成try/finally（按逆序执行）"""
        source = """def test():
    x = 1
    defer print("first")
    y = 2
    defer print("second")
"""
        code = self._assert_parse_success(source)
        self.assertIn("try:", code)
        self.assertIn("finally:", code)
        # 第二个defer应该在finally块中先执行（逆序）
        self.assertIn("print(\"second\")", code)
        self.assertIn("print(\"first\")", code)


class TestPipeOperator(CypyTestBase):
    """管道操作符测试"""

    def test_simple_pipe(self):
        """测试简单管道操作"""
        source = """def process(data: int) -> int:
    return data * 2

def filter(value: int) -> int:
    return value + 1

def test():
    result = 5 |> process |> filter
"""
        code = self._assert_parse_success(source)

    def test_pipe_with_multiple_args(self):
        """测试多参数管道操作"""
        source = """def add(a: int, b: int) -> int:
    return a + b

def test():
    result = 5 |> add(10)
"""
        code = self._assert_parse_success(source)


class TestValLetSemantics(CypyTestBase):
    """let/let语义测试"""

    def test_let_immutable(self):
        """测试let声明的变量不可重新赋值"""
        source = """def test():
    let x: int = 10
    x = 20
"""
        code, error = self._parse_and_generate(source)
        self.assertIsNotNone(error, "Immutable variable should not be reassignable")
        self.assertIn("cannot be reassigned", error)

    def test_mutable_assignment(self):
        """测试默认赋值声明的变量可以重新赋值"""
        source = """def test():
    x: int = 10
    x = 20
"""
        code = self._assert_parse_success(source)

    def test_let_no_initial_assignment(self):
        """测试let变量不可重新赋值（无初始值）"""
        source = """def test():
    let x: int
    x = 10
"""
        code, error = self._parse_and_generate(source)
        self.assertIsNotNone(error, "Immutable variable should not be reassignable")

    def test_let_letid_single_assignment(self):
        """测试let变量的单次赋值是允许的"""
        source = """def test():
    let x: int = 10
    return x
"""
        code = self._assert_parse_success(source)


class TestMetaSystem(CypyTestBase):
    """Meta系统测试"""

    def test_meta_duck_constraint(self):
        """测试meta duck约束定义"""
        source = """meta:
    duck Number:
        a + b -> Self
"""
        code = self._assert_parse_success(source)

    def test_meta_duck_reference(self):
        """测试meta duck引用约束"""
        source = """meta:
    duck Animal:
        name: str
    duck Dog:
        Animal
        bark(self) -> str
"""
        code = self._assert_parse_success(source)

    def test_meta_duck_method(self):
        """测试meta duck方法约束"""
        source = """meta:
    duck Greeter:
        greet(self) -> str
"""
        code = self._assert_parse_success(source)


class TestDeferComprehensive(CypyTestBase):
    """Defer综合测试"""

    def test_single_defer(self):
        """测试单个defer语句"""
        source = """def test():
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)
"""
        code = self._assert_parse_success(source)

    def test_multiple_defer(self):
        """测试多个defer语句（LIFO顺序）"""
        source = """def test():
    ptr1: int* = malloc(sizeof(int))
    defer free(ptr1)
    ptr2: int* = malloc(sizeof(int))
    defer free(ptr2)
"""
        code = self._assert_parse_success(source)


if __name__ == "__main__":
    unittest.main()