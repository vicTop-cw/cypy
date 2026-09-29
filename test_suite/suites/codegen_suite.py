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
        # FIX T0r61.5.2 (defect 3): 原来只做子串检查 Assert.contains(cython_code,
        # "__name__")——把 __name__/__file__ 赋值删掉、仅留一个含这两个词的注释，
        # 测试照样通过。改为要求真正的模块级赋值语句存在。
        magic_lines = [ln.strip() for ln in cython_code.splitlines()]
        Assert.true(
            any(ln.startswith("__name__ =") for ln in magic_lines),
            "generated Cython lacks `__name__ = ...` assignment",
        )
        Assert.true(
            any(ln.startswith("__file__ =") for ln in magic_lines),
            "generated Cython lacks `__file__ = ...` assignment",
        )


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
        # FIX T0r61.5.2 (defect 3): 值断言——必须看到 C 风格强制转换，
        # 而不是"生成器返回了非 None"。宽度 token 随 BUG-14 裁决（float≡double）改钉 <double>。
        Assert.contains(cython_code, "<double>x")


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
        # FIX T0r61.5.2 (defect 3): 块体语句必须出现在生成结果中（原判仅 is_not_none）
        Assert.contains(cython_code, "def main():")
        Assert.contains(cython_code, "x = 1")
        Assert.contains(cython_code, "y = 2")
        Assert.contains(cython_code, "x + y")
        Assert.contains(cython_code, "result = ")


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
        # FIX T0r61.5.2 (defect 3): 值断言——调用构建块必须 lower 成真实调用
        # （原判仅 is_not_none，生成器输出 "garbage" 也能通过）。
        Assert.contains(cython_code, "def compute():")
        Assert.contains(cython_code, "result = compute()")


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
        # FIX T0r61.5.2 (defect 3): 值断言——生成器构建块的元素必须出现在输出中
        # （原判仅 is_not_none，"garbage" 也能通过）。
        Assert.contains(cython_code, "def main():")
        Assert.contains(cython_code, "100")
        Assert.contains(cython_code, "200")


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
        # FIX T0r61.5.2 (defect 3): DEMO 也不能只查 is_not_none
        Assert.contains(cython_code, "def fibonacci(")
        Assert.contains(cython_code, "fibonacci(n - 1) + fibonacci(n - 2)")
    
    # FIX T0r61.5.2 (defect 1): `codegen_suite.tests[-1]` 在运行期恒为最后注册的
    # Test（demo_codegen_struct），会把本 Demo 的元数据挂到别的测试上并被覆盖。
    # 改用 Suite.run() 在执行每个测试前发布的 current_test。
    test = codegen_suite.current_test
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
        # FIX T0r61.5.2 (defect 3): 结构体 DEMO 必须生成 Rectangle 类型与 area 方法
        Assert.contains(cython_code, "Rectangle")
        Assert.contains(cython_code, "def area(")
    
    # FIX T0r61.5.2 (defect 1): 见上文——必须用 current_test，不能用 tests[-1]
    test = codegen_suite.current_test
    test.with_demo("codegen", "codegen_struct", demo_source)
