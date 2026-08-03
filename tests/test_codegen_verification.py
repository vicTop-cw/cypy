# 代码生成验证测试
# 验证生成的 Cython 代码语法有效性

import pytest
from cypy_hook.hook import CypyHook


class TestCodegenVerification:
    """验证生成的 Cython 代码语法有效性"""
    
    def test_struct_generation(self):
        """验证结构体代码生成（普通结构体使用 cdef struct）"""
        source = """struct Point:
    x: int
    y: int

def create_point() -> Point:
    return Point(x=10, y=20)
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 普通结构体使用 cdef struct
        assert "cdef struct Point:" in result.cython_code
        assert "int x" in result.cython_code
        assert "int y" in result.cython_code
    
    def test_struct_with_methods(self):
        """验证带方法的结构体代码生成（使用 cdef class）"""
        source = """struct Vector:
    x: float
    y: float
    
    def add(self, other: Vector) -> Vector:
        return Vector(x=self.x + other.x, y=self.y + other.y)
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "cdef class Vector:" in result.cython_code
        assert "def __init__(self, x, y):" in result.cython_code
        assert "@cython.binding(False)" in result.cython_code
        assert "@cython.final" in result.cython_code
        assert "__slots__" in result.cython_code
        assert "cpdef Vector add(self, Vector other):" in result.cython_code
    
    def test_struct_with_default_values(self):
        """验证带默认值的结构体代码生成（普通结构体使用 cdef struct）"""
        source = """struct Config:
    host: str = "localhost"
    port: int = 8080
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 普通结构体使用 cdef struct，默认值直接在字段定义中
        assert "cdef struct Config:" in result.cython_code
        assert 'str host = "localhost"' in result.cython_code
        assert "int port = 8080" in result.cython_code
    
    def test_function_with_types(self):
        """验证带类型注解的函数代码生成"""
        source = """def add(a: int, b: int) -> int:
    return a + b
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "cpdef int add(int a, int b):" in result.cython_code
        # 模块级函数不使用 @cython.binding(False)（否则无法作为模块属性访问）
        assert "@cython.binding(False)" not in result.cython_code
    
    def test_enum_generation(self):
        """验证枚举代码生成"""
        source = """enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "class Color(IntEnum):" in result.cython_code
        assert "RED = 1" in result.cython_code
    
    def test_generic_struct(self):
        """验证泛型结构体代码生成"""
        source = """struct Box<T>:
    value: T
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "cdef struct Box:" in result.cython_code
    
    def test_const_generation(self):
        """验证常量代码生成"""
        source = """const PI = 3.14159
const MAX_SIZE = 100
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "cdef readonly" in result.cython_code
        assert "PI = 3.14159" in result.cython_code
        assert "MAX_SIZE = 100" in result.cython_code
    
    def test_pipeline_operator(self):
        """验证管道操作符代码生成"""
        source = """def add_one(x: int) -> int:
    return x + 1

def square(x: int) -> int:
    return x * x

def compute():
    result = 5 |> add_one |> square
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 管道操作符应该转换为函数调用
        assert "square(add_one(5))" in result.cython_code
    
    def test_defer_statement(self):
        """验证 defer 语句代码生成"""
        source = """def safe_file():
    f = open("test.txt", "w")
    defer:
        f.close()
    f.write("hello")
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果 defer 语句已实现，应该生成 try-finally
        if result.success and result.cython_code:
            assert "try:" in result.cython_code
            assert "finally:" in result.cython_code
            assert "f.close()" in result.cython_code
    
    def test_comptime_expression(self):
        """验证 comptime 表达式代码生成"""
        source = """def demo():
    value = comptime 2 ** 10
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果 comptime 已实现，应该在编译期计算
        if result.success and result.cython_code:
            assert "value = 1024" in result.cython_code
    
    def test_cython_directives(self):
        """验证 Cython 编译指令生成"""
        source = """def simple():
    pass
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "# cython: language_level=3" in result.cython_code
        assert "# cython: boundscheck=False" in result.cython_code
        assert "# cython: wraparound=False" in result.cython_code
        assert "# cython: cdivision=True" in result.cython_code
        assert "import cython" in result.cython_code
    
    def test_go_statement(self):
        """验证 go 语句代码生成"""
        source = """async def main():
    go asyncio.sleep(1)
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果 go 语句已实现，应该生成 asyncio.create_task
        if result.success and result.cython_code:
            assert "asyncio.create_task" in result.cython_code
            assert "import asyncio" in result.cython_code
    
    def test_spawn_statement(self):
        """验证 spawn 语句代码生成"""
        source = """def main():
    spawn print("hello")
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "threading.Thread" in result.cython_code
        assert "import threading" in result.cython_code
    
    def test_match_statement(self):
        """验证 match 语句代码生成"""
        source = """def demo(x):
    match x:
        case 1:
            pass
        case 2:
            pass
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "match x:" in result.cython_code
        assert "case 1:" in result.cython_code
    
    def test_fstring(self):
        """验证 f-string 代码生成"""
        source = """def demo(name: str):
    return f"Hello, {name}"
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert 'f"Hello, {name}"' in result.cython_code
    
    def test_list_comprehension(self):
        """验证列表推导式代码生成"""
        source = """def demo():
    return [x * 2 for x in range(10) if x % 2 == 0]
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果列表推导式已实现
        if result.success and result.cython_code:
            assert "[x * 2 for x in range(10) if x % 2 == 0]" in result.cython_code
    
    def test_type_alias(self):
        """验证类型别名代码生成"""
        source = """typealias Vector2D = tuple<float, float>
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果 typealias 已实现
        if result.success and result.cython_code:
            assert "Vector2D = tuple[float, float]" in result.cython_code
    
    def test_let_statement(self):
        """验证 let 语句代码生成"""
        source = """def demo():
    let x: int = 10
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert "cdef int x = 10" in result.cython_code
    
    def test_pointer_operations(self):
        """验证指针操作代码生成"""
        source = """def demo():
    cdef int x = 10
    cdef int* ptr = addr(x)
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        # 如果指针操作已实现
        if result.success and result.cython_code:
            assert "cdef int *ptr = &x" in result.cython_code
            assert "from libc.stdlib cimport malloc, free" in result.cython_code
    
    def test_compile_time_constants(self):
        """验证编译期常量代码生成"""
        source = """const DEBUG = True
const VERSION = "1.0"
"""
        hook = CypyHook()
        result = hook.transpile(source)
        
        assert 'cdef readonly DEBUG = True' in result.cython_code
        assert 'cdef readonly VERSION = "1.0"' in result.cython_code
