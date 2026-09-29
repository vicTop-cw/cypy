"""
分析器测试套件
覆盖类型检查、作用域分析、指针检查等核心功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_suite.core.suite import Suite
from test_suite.core.assertions import Assert, Check
from test_suite.fixtures.compiler import CompilerFixture


analyzer_suite = Suite("AnalyzerSuite")


# ===== 类型检查测试 =====
@analyzer_suite.test("type_check_basic_types")
def test_type_check_basic_types():
    """测试基本类型检查"""
    source = """
def main() -> int:
    x: int = 42
    y: float = 3.14
    z: str = "hello"
    return x
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Type check failed: {errors}")
        Assert.equal(errors, [], "clean program produced type errors")
        # FIX T0r61.5.2 (defect 3): 配对负例——分析器还必须"拒绝坏程序"。
        # 此前所有 analyzer 测试只断言 success=True，把分析器整个删掉
        # （任何输入都返回成功）套件依旧全绿。
        bad_ok, bad_errors = fixture.analyze_only(
            'def main() -> int:\n    return "text"\n', "bad_ret_type"
        )
        Assert.false(bad_ok, f"analyzer accepted return-type mismatch, errors={bad_errors}")
        Assert.true(len(bad_errors) > 0, "analyzer reported no error for return-type mismatch")


@analyzer_suite.test("type_check_arithmetic")
def test_type_check_arithmetic():
    """测试算术运算类型检查"""
    source = """
def main() -> int:
    a: int = 10
    b: int = 20
    result = a + b
    return result
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Type check failed: {errors}")
        Assert.equal(errors, [], "clean program produced type errors")
        # FIX T0r61.5.2 (defect 3): 负例——str + int 必须被拒绝
        bad_ok, bad_errors = fixture.analyze_only(
            'def main() -> int:\n    s: str = "a"\n    return s + 1\n', "bad_arith"
        )
        Assert.false(bad_ok, f"analyzer accepted str+int, errors={bad_errors}")


@analyzer_suite.test("type_check_return_type")
def test_type_check_return_type():
    """测试返回类型检查"""
    source = """
def compute() -> float:
    return 3.14

def main() -> int:
    x = compute()
    return int(x)
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Type check failed: {errors}")
        Assert.equal(errors, [], "clean program produced type errors")


# ===== 作用域分析测试 =====
@analyzer_suite.test("scope_analysis_local_var")
def test_scope_analysis_local_var():
    """测试局部变量作用域分析"""
    source = """
def main() -> int:
    x: int = 10
    if x > 5:
        y: int = 20
    return x
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Scope analysis failed: {errors}")
        Assert.equal(errors, [], "clean program produced scope errors")
        # FIX T0r61.5.2 (defect 3): 负例——未定义名字必须被拒绝
        bad_ok, bad_errors = fixture.analyze_only(
            "def main() -> int:\n    return mystery_var\n", "bad_scope"
        )
        Assert.false(bad_ok, f"analyzer accepted undefined name, errors={bad_errors}")


@analyzer_suite.test("scope_analysis_global_var")
def test_scope_analysis_global_var():
    """测试全局变量作用域分析"""
    source = """
g: int = 42

def main() -> int:
    return g
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Scope analysis failed: {errors}")
        Assert.equal(errors, [], "clean program produced scope errors")


# ===== 参数检查测试 =====
@analyzer_suite.test("param_checker_basic")
def test_param_checker_basic():
    """测试参数检查器基本功能"""
    source = """
def greet(name: str, age: int) -> str:
    return f"Hello, {name}, age {age}"

def main() -> int:
    greet("Alice", 30)
    return 0
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Param check failed: {errors}")
        Assert.equal(errors, [], "clean program produced param errors")
        # FIX T0r61.5.2 (defect 3): 负例——调用未定义函数必须被拒绝
        bad_ok, bad_errors = fixture.analyze_only(
            "def main() -> int:\n    return mystery(1)\n", "bad_call"
        )
        Assert.false(bad_ok, f"analyzer accepted undefined function call, errors={bad_errors}")


@analyzer_suite.test("type_conversion_explicit")
def test_type_conversion_explicit():
    """测试显式类型转换"""
    source = """
def main() -> float:
    x: int = 10
    y: float = x as float
    return y
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Explicit conversion failed: {errors}")
        Assert.equal(errors, [], "clean program produced conversion errors")


@analyzer_suite.test("type_conversion_implicit")
def test_type_conversion_implicit():
    """测试隐式类型转换"""
    source = """
def main() -> float:
    x: int = 10
    y: float = x
    return y
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(source)
        Assert.true(success, f"Implicit conversion failed: {errors}")
        Assert.equal(errors, [], "clean program produced conversion errors")


# ===== DEMO 示例测试 =====
@analyzer_suite.test("demo_type_safety")
def test_demo_type_safety():
    """类型安全 DEMO"""
    demo_source = """
# 类型安全示例
def safe_compute(a: int, b: float) -> float:
    # 显式转换确保类型安全
    result = (a as float) + b
    return result

def main() -> int:
    x = safe_compute(10, 3.14)
    print(x)
    return 0
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(demo_source)
        Assert.true(success, f"Type safety demo failed: {errors}")
        Assert.equal(errors, [], "demo program produced type errors")
    
    # FIX T0r61.5.2 (defect 1): `analyzer_suite.tests[-1]` 在运行期恒为最后注册的
    # Test（demo_scope_usage），会把本 Demo 的元数据挂到别的测试上并被覆盖。
    # 改用 Suite.run() 在执行每个测试前发布的 current_test。
    test = analyzer_suite.current_test
    test.with_demo("analyzer", "type_safety", demo_source)


@analyzer_suite.test("demo_scope_usage")
def test_demo_scope_usage():
    """作用域使用 DEMO"""
    demo_source = """
# 作用域示例
module_level: str = "global"

def outer() -> int:
    outer_var: int = 10
    
    def inner() -> int:
        inner_var: int = 20
        return outer_var + inner_var
    
    return inner()

def main() -> int:
    return outer()
"""
    with CompilerFixture() as fixture:
        success, errors = fixture.analyze_only(demo_source)
        Assert.true(success, f"Scope demo failed: {errors}")
        Assert.equal(errors, [], "demo program produced scope errors")
    
    # FIX T0r61.5.2 (defect 1): 见上文——必须用 current_test，不能用 tests[-1]
    test = analyzer_suite.current_test
    test.with_demo("analyzer", "scope_usage", demo_source)
