"""
集成测试套件
覆盖端到端编译、运行时行为等核心功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from test_suite.core.suite import Suite
from test_suite.core.assertions import Assert, Check
from test_suite.fixtures.compiler import CompilerFixture


integration_suite = Suite("IntegrationSuite")


# ===== 端到端编译运行测试 =====
@integration_suite.test("integration_basic_arithmetic")
def test_integration_basic_arithmetic():
    """测试基本算术运算端到端"""
    source = """
def main() -> int:
    a: int = 10
    b: int = 20
    c = a + b * 2
    return c
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 50)


@integration_suite.test("integration_string_concatenation")
def test_integration_string_concatenation():
    """测试字符串连接端到端"""
    source = """
def main() -> str:
    hello: str = "Hello"
    world: str = "World"
    return hello + ", " + world + "!"
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, "Hello, World!")


@integration_suite.test("integration_control_flow")
def test_integration_control_flow():
    """测试控制流端到端"""
    source = """
def main() -> int:
    x: int = 10
    if x > 5:
        return 1
    elif x == 5:
        return 0
    else:
        return -1
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 1)


@integration_suite.test("integration_while_loop")
def test_integration_while_loop():
    """测试 while 循环端到端"""
    source = """
def main() -> int:
    i: int = 0
    sum: int = 0
    while i < 5:
        sum += i
        i += 1
    return sum
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 10)


# ===== 结构体端到端测试 =====
@integration_suite.test("integration_struct_usage")
def test_integration_struct_usage():
    """测试结构体使用端到端"""
    source = """
struct Point:
    x: int
    y: int

def main() -> int:
    p = Point {x: 10, y: 20}
    return p.x + p.y
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 30)


# ===== 函数调用端到端测试 =====
@integration_suite.test("integration_function_call")
def test_integration_function_call():
    """测试函数调用端到端"""
    source = """
def add(a: int, b: int) -> int:
    return a + b

def multiply(a: int, b: int) -> int:
    return a * b

def main() -> int:
    return multiply(add(2, 3), 4)
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 20)


# ===== 类型转换端到端测试 =====
@integration_suite.test("integration_type_conversion")
def test_integration_type_conversion():
    """测试类型转换端到端"""
    source = """
def main() -> float:
    x: int = 10
    y: float = x as float
    z: float = 3.14
    return y + z
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(source)
        Assert.is_not_none(result, "Execution failed")
        Assert.almost_equal(result, 13.14, tolerance=0.01)


# ===== DEMO 示例测试 =====
@integration_suite.test("demo_integration_full_program")
def test_demo_integration_full_program():
    """完整程序集成 DEMO"""
    demo_source = """
# 完整程序集成示例
struct Calculator:
    result: int = 0
    
    def add(self, value: int):
        self.result += value
    
    def subtract(self, value: int):
        self.result -= value
    
    def multiply(self, value: int):
        self.result *= value

def main() -> int:
    calc = Calculator {}
    calc.add(10)
    calc.multiply(2)
    calc.subtract(5)
    print(f"Final result: {calc.result}")
    return calc.result
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(demo_source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 15)
    
    test = integration_suite.tests[-1]
    test.with_demo("integration", "full_program", demo_source)


@integration_suite.test("demo_integration_recursion")
def test_demo_integration_recursion():
    """递归函数集成 DEMO"""
    demo_source = """
# 递归函数集成示例
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def main() -> int:
    result = factorial(5)
    print(f"5! = {result}")
    return result
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(demo_source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 120)
    
    test = integration_suite.tests[-1]
    test.with_demo("integration", "recursion", demo_source)


@integration_suite.test("demo_integration_array")
def test_demo_integration_array():
    """数组操作集成 DEMO"""
    demo_source = """
# 数组操作集成示例
def sum_array(arr: list<int>) -> int:
    total: int = 0
    for item in arr:
        total += item
    return total

def main() -> int:
    numbers = [1, 2, 3, 4, 5]
    return sum_array(numbers)
"""
    with CompilerFixture() as fixture:
        result = fixture.compile_and_run(demo_source)
        Assert.is_not_none(result, "Execution failed")
        Assert.equal(result, 15)
    
    test = integration_suite.tests[-1]
    test.with_demo("integration", "array_operations", demo_source)
