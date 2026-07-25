# Cypy 语言语法规范 - 基础语法

## 1. 变量声明

### 1.1 基本变量声明

Cypy 支持多种变量声明方式：

```python
# Python 风格（无类型注解）→ PyObject
x = 10
name = "Alice"
active = True

# 带类型注解（静态类型）
x: int = 10
name: str = "Alice"
active: bool = True
price: float = 3.99

# 类型注解但无初始值
count: int
value: float
```

### 1.2 可变与不可变变量

```python
# 可变变量（默认）
mutable x: int = 10
x = 20  # ✅ 允许

# 不可变变量（val）
val PI: double = 3.14159
PI = 3.14  # ❌ 编译错误：不可重新赋值
```

### 1.3 隐式变量声明

```python
# 使用 implicit 声明隐式变量
implicit ctx: Config = Config {debug: False}

# 隐式变量可在整个模块中访问
def process():
    return ctx.debug  # ✅ 可访问隐式变量
```

## 2. 函数定义

### 2.1 基本函数定义

```python
# 无类型注解（Python 风格）→ PyObject
def add(a, b):
    return a + b

# 带类型注解
def add(a: int, b: int) -> int:
    return a + b

# 返回类型推断（从返回语句推断）
def multiply(a: int, b: int):
    return a * b  # 推断返回类型为 int

# 无返回值函数
def print_message(msg: str) -> None:
    print(msg)
```

### 2.2 参数类型

```python
# 默认参数值
def greet(name: str = "Guest") -> str:
    return f"Hello, {name}"

# 可变参数
def sum_all(*args: int) -> int:
    total = 0
    for num in args:
        total += num
    return total

# 关键字参数
def configure(*, host: str = "localhost", port: int = 8080) -> None:
    pass

# 解包参数
def create_user(name: str, age: int) -> dict:
    return {"name": name, "age": age}

user = create_user(**{"name": "Bob", "age": 25})
```

### 2.3 异步函数

```python
async def fetch_data(url: str) -> str:
    import asyncio
    await asyncio.sleep(1)
    return f"Data from {url}"
```

### 2.4 测试函数

```python
# 使用 test def 声明测试函数
test def test_add() -> int:
    assert add(2, 3) == 5
    return 0

test def test_multiply() -> int:
    assert multiply(4, 5) == 20
    return 0
```

## 3. 控制流语句

### 3.1 条件语句

```python
# if-else
def check_value(x: int) -> str:
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"

# 条件表达式
result = "even" if x % 2 == 0 else "odd"

# match-case（Python 3.10+ 语法）
def process_value(value):
    match value:
        case 0:
            return "zero"
        case 1 | 2:
            return "small"
        case int(x) if x > 10:
            return "large integer"
        case _:
            return "other"
```

### 3.2 循环语句

```python
# for 循环
def sum_list(items: list[int]) -> int:
    total = 0
    for item in items:
        total += item
    return total

# for 循环带索引
for i, value in enumerate(items):
    print(f"Index {i}: {value}")

# while 循环
def countdown(n: int) -> None:
    while n > 0:
        print(n)
        n -= 1

# break 和 continue
def find_first_even(numbers: list[int]) -> int:
    for num in numbers:
        if num % 2 == 0:
            return num
    return -1
```

### 3.3 异常处理

```python
# try-except
def safe_divide(a: float, b: float) -> float:
    try:
        return a / b
    except ZeroDivisionError:
        return float("inf")

# try-except-else-finally
def process_file(path: str) -> None:
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        print("File not found")
    else:
        print(content)
    finally:
        print("Done")

# raise 语句
def validate_age(age: int) -> None:
    if age < 0:
        raise ValueError("Age cannot be negative")
```

## 4. 内置数据类型

### 4.1 数值类型

```python
# 整数
a: int = 42
b: long = 1000000000000

# 浮点数
c: float = 3.14
d: double = 2.718281828

# 布尔值
e: bool = True
f: bool = False
```

### 4.2 字符串

```python
# 普通字符串
name: str = "Alice"

# 多行字符串
description: str = """
This is a
multi-line string
"""

# f-string（格式化字符串）
age: int = 30
message: str = f"Name: {name}, Age: {age}"

# 原始字符串
path: str = r"C:\Users\admin"
```

### 4.3 容器类型

```python
# 列表
numbers: list[int] = [1, 2, 3, 4, 5]
mixed: list = [1, "hello", True]

# 字典
person: dict[str, object] = {"name": "Bob", "age": 25}

# 集合
unique: set[int] = {1, 2, 3, 3, 2, 1}

# 元组
point: tuple[int, int] = (10, 20)
```

## 5. 运算符

### 5.1 算术运算符

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `+` | 加法 | `a + b` |
| `-` | 减法 | `a - b` |
| `*` | 乘法 | `a * b` |
| `/` | 除法 | `a / b` |
| `//` | 整除 | `a // b` |
| `%` | 取模 | `a % b` |
| `**` | 幂运算 | `a ** b` |

### 5.2 比较运算符

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `==` | 等于 | `a == b` |
| `!=` | 不等于 | `a != b` |
| `<` | 小于 | `a < b` |
| `>` | 大于 | `a > b` |
| `<=` | 小于等于 | `a <= b` |
| `>=` | 大于等于 | `a >= b` |
| `in` | 成员检测 | `x in list` |
| `not in` | 非成员检测 | `x not in list` |
| `is` | 身份检测 | `x is None` |
| `is not` | 非身份检测 | `x is not None` |

### 5.3 逻辑运算符

| 运算符 | 说明 | 示例 |
|--------|------|------|
| `and` | 逻辑与 | `a and b` |
| `or` | 逻辑或 | `a or b` |
| `not` | 逻辑非 | `not a` |

### 5.4 赋值运算符

```python
x = 10          # 简单赋值
x += 5          # 等价于 x = x + 5
x -= 3          # 等价于 x = x - 3
x *= 2          # 等价于 x = x * 2
x /= 2          # 等价于 x = x / 2
x //= 2         # 等价于 x = x // 2
x %= 3          # 等价于 x = x % 3
x **= 2         # 等价于 x = x ** 2
```

## 6. 模块与导入

### 6.1 导入语句

```python
# 导入整个模块
import math
result = math.sqrt(16)

# 导入指定名称
from math import sqrt, pi
result = sqrt(16)

# 导入并别名
import numpy as np
arr = np.array([1, 2, 3])

# 导入所有名称
from module import *
```

### 6.2 模块级变量

```python
# 模块级常量
MAX_SIZE: int = 1000

# 模块级变量
counter: int = 0

# 导出列表
__all__ = ["public_func", "PublicClass"]

def public_func():
    pass

def _private_func():
    pass
```

## 7. 类定义

### 7.1 基本类定义

```python
class Person:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def greet(self) -> str:
        return f"Hello, my name is {self.name}"

# 创建实例
p = Person("Alice", 30)
print(p.greet())
```

### 7.2 继承

```python
class Student(Person):
    def __init__(self, name: str, age: int, grade: str):
        super().__init__(name, age)
        self.grade = grade
    
    def study(self) -> None:
        print(f"{self.name} is studying")
```

### 7.3 装饰器

```python
def debug(func):
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Result: {result}")
        return result
    return wrapper

@debug
def add(a: int, b: int) -> int:
    return a + b
```

## 8. 上下文管理器

```python
# with 语句
with open("file.txt", "r") as f:
    content = f.read()

# 自定义上下文管理器
class Timer:
    def __enter__(self):
        import time
        self.start = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        self.end = time.time()
        print(f"Elapsed: {self.end - self.start}s")

with Timer():
    # 执行耗时操作
    pass
```
