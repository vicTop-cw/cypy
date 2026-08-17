"""
代码生成测试套件
覆盖 Cython 代码生成、类型映射、特殊语法等核心功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_suite.core.suite import Suite
from test_suite.core.assertions import Assert, Check
from test_suite.fixtures.compiler import CompilerFixture


codegen_suite = Suite("CodegenSuite")


# ===== 基本代码生成测试 =====
@codegen_suite.test("codegen_basic_function")
def test_codegen_basic_function():
    """测试基本函数代码生成"""
    source = """
def add(a: int, b: int) -> int:
    return a + b

def main() -> int:
    return add(1, 2)
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")
        # 模块级函数以普通 def 生成，剥离类型注解（避免 cpdef 闭包问题）
        Assert.contains(cython_code, "def add(a, b):")


@codegen_suite.test("codegen_struct_def")
def test_codegen_struct_def():
    """测试结构体代码生成"""
    source = """
struct Point:
    x: int
    y: int

def main() -> int:
    p = Point {x: 10, y: 20}
    return p.x
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")
        # Cypy 使用 cdef struct 生成结构体
        Assert.contains(cython_code, "cdef struct Point")


# ===== 模块级魔法属性测试 =====
@codegen_suite.test("codegen_module_magic_attrs")
def test_codegen_module_magic_attrs():
    """测试模块级魔法属性生成"""
    source = """
def main() -> int:
    return 0
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source, "test_module")
        Assert.is_not_none(cython_code, "Code generation failed")
        Assert.contains(cython_code, "__name__")
        Assert.contains(cython_code, "__file__")


# ===== 类型转换代码生成测试 =====
@codegen_suite.test("codegen_cast_expression")
def test_codegen_cast_expression():
    """测试类型转换代码生成"""
    source = """
def main() -> float:
    x: int = 10
    y: float = x as float
    return y
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")


# ===== 构建块代码生成测试 =====
@codegen_suite.test("codegen_build_assign")
def test_codegen_build_assign():
    """测试构建块赋值代码生成"""
    source = """
def main() -> int:
    result =:
        x = 1
        y = 2
        x + y
    return result
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")


@codegen_suite.test("codegen_build_call")
def test_codegen_build_call():
    """测试构建块调用代码生成"""
    source = """
def compute() -> int:
    return 42

def main() -> int:
    result ~:
        compute()
    return result
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")


@codegen_suite.test("codegen_build_gen")
def test_codegen_build_gen():
    """测试构建块生成代码生成"""
    source = """
def main() -> int:
    result *:
        yield (100,)
        yield (200,)
    return 0
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(source)
        Assert.is_not_none(cython_code, "Code generation failed")


# ===== DEMO 示例测试 =====
@codegen_suite.test("demo_codegen_basic")
def test_demo_codegen_basic():
    """代码生成基础 DEMO"""
    demo_source = """
# 代码生成基础示例
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

def main() -> int:
    result = fibonacci(10)
    print(result)
    return 0
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(demo_source)
        Assert.is_not_none(cython_code, "Code generation failed")
    
    test = codegen_suite.tests[-1]
    test.with_demo("codegen", "codegen_basic", demo_source)


@codegen_suite.test("demo_codegen_struct")
def test_demo_codegen_struct():
    """结构体代码生成 DEMO"""
    demo_source = """
# 结构体代码生成示例
struct Rectangle:
    width: float
    height: float
    
    def area(self) -> float:
        return self.width * self.height

def main() -> int:
    rect = Rectangle {width: 10.0, height: 5.0}
    print(rect.area())
    return 0
"""
    with CompilerFixture() as fixture:
        cython_code = fixture.compile(demo_source)
        Assert.is_not_none(cython_code, "Code generation failed")
    
    test = codegen_suite.tests[-1]
    test.with_demo("codegen", "codegen_struct", demo_source)
