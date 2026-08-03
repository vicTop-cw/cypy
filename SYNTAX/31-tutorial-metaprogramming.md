# 元编程教程

## 概述

元编程是指编写能够生成或操作代码的代码。Cypy 提供了多种元编程特性，包括编译期常量、编译期求值、宏系统等，让你可以在编译时执行代码生成和优化。

## 编译期常量

### 基本用法

使用 `const` 关键字定义编译期常量：

```cypy
const MAX_SIZE = 100
const PI = 3.141592653589793
const DEBUG = True
```

编译期常量在编译时被解析和替换，不会生成运行时代码。

### 与普通变量的区别

```cypy
const COMPILE_TIME = 42  # 编译期常量，直接嵌入代码
let runtime = 42         # 运行时变量，存储在内存中
```

### 使用场景

```cypy
# 配置常量
const MAX_CONNECTIONS = 10
const DEFAULT_TIMEOUT = 30

# 数学常量
const E = 2.718281828459045
const GOLDEN_RATIO = 1.618033988749895

# 条件编译
const ENABLE_LOGGING = True
const OPTIMIZE_FOR_SPEED = True
```

## 编译期求值

### comptime 表达式

使用 `comptime` 关键字在编译时求值表达式：

```cypy
def compile_time_demo():
    # 编译时计算
    let result = comptime 2 ** 10  # result = 1024（编译时确定）
    let greeting = comptime "Hello".upper()  # greeting = "HELLO"
    
    print(result)
    print(greeting)
```

### comptime 用于默认参数

```cypy
def process(value: int, min_val: int = comptime 0, max_val: int = comptime 100):
    if value < min_val or value > max_val:
        raise ValueError(f"超出范围 [{min_val}, {max_val}]")
    return value
```

### comptime 块

```cypy
def generate_data():
    let config = comptime:
        # 这个块在编译时执行
        items = []
        for i in range(5):
            items.append(i * 2)
        items
    
    print(f"编译期生成: {config}")  # [0, 2, 4, 6, 8]
```

## meta 块

### 基本用法

`meta` 块在编译时执行，用于生成代码：

```cypy
meta:
    # 编译时执行的代码
    # 可以访问编译期信息
    print("编译中...")
    
    # 可以生成变量
    __generated_at__ = "2024-01-01"
```

### 生成函数

```cypy
meta:
    # 在编译时生成辅助函数
    def _generate_id() -> int:
        import random
        return random.randint(1, 1000)
    
    GENERATED_ID = _generate_id()
```

## 条件编译

### 使用 const 控制

```cypy
const DEBUG = True

def debug_log(message: str):
    if DEBUG:
        print(f"[DEBUG] {message}")

def release_log(message: str):
    if not DEBUG:
        print(f"[INFO] {message}")
```

### 优化示例

```cypy
const OPTIMIZE = True

def compute(x: int) -> int:
    if OPTIMIZE:
        # 优化版本（编译时选择）
        return x * x * x
    else:
        # 调试版本
        result = x * x
        result = result * x
        return result
```

## 类型级别元编程

### 类型别名

```cypy
typealias Vector2D = tuple<float, float>
typealias Matrix3x3 = tuple<tuple<float, float, float>, ...>
```

### 泛型类型别名

```cypy
typealias Optional<T> = T | None
typealias Result<T> = tuple<bool, Optional<T>>
typealias ListOrNone<T> = list<T> | None
```

### 类型工厂

```cypy
typealias Factory<T> = Callable[[], T]

def create_factory<T>(default: T) -> Factory<T>:
    def factory() -> T:
        return default
    return factory
```

## 宏系统

### 基本宏

```cypy
macro debug_print(expr):
    """调试打印宏"""
    return print(f"{expr} = {repr(expr)}")

# 使用宏
let x = 42
debug_print(x)  # 展开为: print(f"x = {repr(x)}")
```

### 宏模板

```cypy
macro repeat[n](func):
    """重复执行 n 次"""
    body = []
    for i in range(n):
        body.append(func())
    return body

# 使用
repeat[3](lambda: print("Hello"))
```

## 编译期类型检查

### 类型守卫

```cypy
def validate_type<T>(value) -> bool:
    """编译期类型检查"""
    return isinstance(value, T)
```

### 静态断言

```cypy
def static_assert(condition: bool, message: str):
    """静态断言"""
    if not condition:
        raise AssertionError(message)

# 在编译时检查
static_assert(MAX_SIZE > 0, "MAX_SIZE 必须大于 0")
```

## 代码生成示例

### 生成测试代码

```cypy
meta:
    # 生成测试用例
    test_cases = [
        (1, 2, 3),
        (4, 5, 9),
        (10, -5, 5),
    ]
    
    # 生成测试函数
    for i, (a, b, expected) in enumerate(test_cases):
        def test_add_{i}():
            result = a + b
            assert result == expected, f"{a} + {b} = {result}, expected {expected}"
```

### 生成配置类

```cypy
meta:
    config_items = {
        'host': 'localhost',
        'port': 8080,
        'timeout': 30,
    }
    
    class Config:
        pass
    
    for key, value in config_items.items():
        setattr(Config, key, value)
```

## 性能优化

### 编译期计算

```cypy
# 编译期计算查找表
const LOOKUP_TABLE = comptime [i * i for i in range(100)]

def fast_square(n: int) -> int:
    if 0 <= n < 100:
        return LOOKUP_TABLE[n]
    return n * n
```

### 消除运行时开销

```cypy
const ENABLE_CHECKS = False

def process_data(data: list<int>) -> int:
    if ENABLE_CHECKS:
        # 仅在调试模式下执行
        if not data:
            raise ValueError("数据为空")
    
    # 核心逻辑
    return sum(data)
```

## 最佳实践

### 1. 使用 const 代替魔法数字

```cypy
# 好的做法
const BUFFER_SIZE = 4096
const MAX_RETRIES = 3

# 避免
def process(buffer: bytes):
    if len(buffer) > 4096:  # 魔法数字
        pass
```

### 2. 利用 comptime 优化热路径

```cypy
def hot_path_computation(x: int) -> int:
    # 编译期计算常量部分
    let multiplier = comptime 2 * 3.14159
    return int(x * multiplier)
```

### 3. 使用 defer 配合动态代码生成

```cypy
def generate_resource():
    resource = comptime create_resource()
    
    defer:
        resource.cleanup()
    
    return resource
```

## 与 Python 的对比

| 特性 | Python | Cypy 元编程 |
|------|--------|-------------|
| 编译期常量 | 无 | `const` |
| 编译期求值 | 无 | `comptime` |
| 编译期代码生成 | 无 | `meta` |
| 类型别名 | `TypeAlias` | `typealias` |
| 泛型 | 运行时 | 编译时展开 |

## 高级技巧

### 编译期反射

```cypy
meta:
    # 编译期获取模块信息
    __module_name__ = __name__
    __module_file__ = __file__
```

### 条件导入

```cypy
const USE_OPENCV = True

if USE_OPENCV:
    import cv2
else:
    import PIL.Image
```

### 生成装饰器

```cypy
meta:
    def timed(func):
        def wrapper(*args, **kwargs):
            import time
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            print(f"{func.__name__} took {end - start:.2f}s")
            return result
        return wrapper
```
