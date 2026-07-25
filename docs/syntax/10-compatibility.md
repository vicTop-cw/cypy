# Cypy 语言语法规范 - 兼容性指南

## 1. Python 版本兼容性

### 1.1 支持的版本

Cypy 要求 Python 3.9 或更高版本。

| Python 版本 | 支持状态 | 说明 |
|-------------|----------|------|
| 3.13 | ✅ 支持 | 推荐使用 |
| 3.12 | ✅ 支持 | 完全兼容 |
| 3.11 | ✅ 支持 | 完全兼容 |
| 3.10 | ✅ 支持 | 完全兼容 |
| 3.9 | ✅ 支持 | 最低要求版本 |
| 3.8 | ❌ 不支持 | `python_requires=">=3.9"` |
| 3.7 | ❌ 不支持 | 缺少类型注解特性 |
| 3.6 | ❌ 不支持 | 缺少多项特性 |

### 1.2 版本要求原因

#### Python 3.9 特性依赖

```python
# 类型注解（Python 3.9+）
def func(x: list[int]) -> tuple[str, ...]:  # 泛型类型注解
    pass

# f-string（Python 3.6+，但 Cython 3.0 需要更高版本）
result = f"{x=}"  # Python 3.8+

# 字典合并运算符
dict1 = {"a": 1}
dict2 = {"b": 2}
merged = dict1 | dict2  # Python 3.9+
```

#### Cython 3.0 依赖

```python
# setup.py 中的依赖声明
python_requires=">=3.9",
install_requires=[
    "Cython>=3.0.0",
    "pyyaml",
    "colorama"
]
```

### 1.3 版本检查

```python
import sys

# 检查 Python 版本
if sys.version_info < (3, 9):
    raise RuntimeError("Cypy requires Python 3.9 or higher")

print(f"Python version: {sys.version}")
# 输出示例: Python version: 3.13.0
```

## 2. Python 语法兼容性

### 2.1 完全兼容的 Python 语法

#### 变量与赋值

```python
# 普通变量
x = 10
y = "hello"

# 多重赋值
a, b = 1, 2

# 链式赋值
c = d = e = 0

# 扩展解包
first, *rest = [1, 2, 3, 4]

# 命名常量（Cypy 扩展）
val PI: float = 3.14159
```

#### 控制流

```python
# if-elif-else
if x > 0:
    print("positive")
elif x < 0:
    print("negative")
else:
    print("zero")

# for 循环
for i in range(10):
    print(i)

# while 循环
while x > 0:
    x -= 1

# 循环控制
for i in range(10):
    if i == 5:
        break
    if i % 2 == 0:
        continue
    print(i)

# match-case（Python 3.10+）
match x:
    case 1:
        print("one")
    case 2:
        print("two")
    case _:
        print("other")
```

#### 函数

```python
# 普通函数
def greet(name: str) -> str:
    return f"Hello, {name}"

# 默认参数
def func(x: int, y: int = 0) -> int:
    return x + y

# 可变参数
def varargs(*args: int, **kwargs: str) -> None:
    pass

# lambda 函数
add = lambda x, y: x + y

# 类型注解
def typed_func(x: int, y: str) -> bool:
    return True
```

#### 类

```python
class Person:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def greet(self) -> str:
        return f"Hello, {self.name}"

# 继承
class Student(Person):
    def __init__(self, name: str, age: int, grade: str):
        super().__init__(name, age)
        self.grade = grade
```

#### 异常处理

```python
try:
    result = 10 / 0
except ZeroDivisionError:
    print("Cannot divide by zero")
except Exception as e:
    print(f"Error: {e}")
else:
    print("No error")
finally:
    print("Always executed")
```

#### 上下文管理器

```python
# with 语句
with open("file.txt", "r") as f:
    content = f.read()

# 自定义上下文管理器
class MyContext:
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

with MyContext() as ctx:
    pass
```

#### 模块与导入

```python
# 导入模块
import math
from datetime import datetime

# 导入别名
import numpy as np
from os import path as os_path

# 相对导入
from . import utils
from ..config import settings

# 条件导入
try:
    import optional_module
except ImportError:
    optional_module = None
```

### 2.2 Cypy 特有语法（不兼容 Python）

#### 结构体

```python
# Cypy 特有：struct 关键字
struct Point:
    x: float
    y: float

p = Point {x: 1.0, y: 2.0}
```

#### 枚举

```python
# Cypy 特有：enum 关键字
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

c = Color.RED
```

#### 特质

```python
# Cypy 特有：trait 关键字
trait Drawable:
    def draw(self) -> None:
        pass

impl Drawable for Point:
    def draw(self) -> None:
        print(f"Drawing Point at ({self.x}, {self.y})")
```

#### 类型别名

```python
# Cypy 特有：type 关键字
type Vector = tuple[float, float, float]
type Matrix = list[list[float]]
```

#### 不可变变量

```python
# Cypy 特有：val 关键字
val MAX_VALUE: int = 100
```

#### 块级绑定

```python
# Cypy 特有：let 关键字
if condition:
    let x: int = 10
    print(x)
# x 在此处不可访问
```

#### 延迟清理

```python
# Cypy 特有：defer 关键字
def func():
    resource = acquire_resource()
    defer release_resource(resource)
    # 使用资源
    pass
# release_resource 在此处自动调用
```

#### 守卫表达式

```python
# Cypy 特有：guard 关键字
def process(data: dict | None) -> str:
    guard data is not None else return "No data"
    return str(data)
```

#### 构建块语法

```python
# Cypy 特有：=: ~: *: 操作符
result =:
    x = 10
    y = 20
    x + y
```

#### 管道操作符

```python
# Cypy 特有：|> 操作符
result = [1, 2, 3] |> map(lambda x: x * 2) |> list()
```

#### 所有权声明

```python
# Cypy 特有：owned 关键字
def create_data() -> owned dict:
    return {"key": "value"}
```

### 2.3 Python 3.10+ 特性

#### 模式匹配

```python
# Python 3.10+
match status:
    case 200:
        print("OK")
    case 404:
        print("Not Found")
    case 500:
        print("Server Error")
    case _:
        print(f"Unknown: {status}")

# 结构模式匹配
match point:
    case Point(x=0, y=0):
        print("Origin")
    case Point(x, y) if x == y:
        print(f"Diagonal: ({x}, {y})")
```

## 3. Cython 兼容性

### 3.1 Cython 版本要求

```python
# setup.py
install_requires=[
    "Cython>=3.0.0",
]
```

### 3.2 生成的 Cython 代码

```cython
# Cypy 生成的 Cython 代码示例

# 结构体
cdef struct Point:
    float x
    float y

# 函数
cdef int add(int a, int b):
    return a + b

# 类
cdef class Person:
    cdef str name
    cdef int age
    
    def __init__(self, str name, int age):
        self.name = name
        self.age = age
```

### 3.3 Cython 特有语法

```cython
# Cython 特有（自动生成）
cdef int x          # C 级别的变量
cpdef int func()    # 同时提供 C 和 Python 接口
@cython.boundscheck(False)  # 禁用边界检查
@cython.wraparound(False)   # 禁用负索引
```

## 4. 平台兼容性

### 4.1 支持的操作系统

| 操作系统 | 支持状态 | 说明 |
|----------|----------|------|
| Windows | ✅ 支持 | 生成 `.pyd` 文件 |
| Linux | ✅ 支持 | 生成 `.so` 文件 |
| macOS | ✅ 支持 | 生成 `.so` 文件 |

### 4.2 架构支持

| 架构 | 支持状态 |
|------|----------|
| x86_64 / AMD64 | ✅ 支持 |
| ARM64 | ✅ 支持 |
| x86 | ⚠️ 有限支持 |

### 4.3 编译产物

```
# Windows
output/test.cp313-win_amd64.pyd

# Linux
output/test.cpython-313-x86_64-linux-gnu.so

# macOS
output/test.cpython-313-darwin.so
```

## 5. 迁移指南

### 5.1 从 Python 迁移到 Cypy

#### 步骤 1: 基础转换

```python
# Python 代码
def calculate(x, y):
    return x + y

# Cypy 代码（添加类型注解）
def calculate(x: int, y: int) -> int:
    return x + y
```

#### 步骤 2: 使用结构体

```python
# Python 代码
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

# Cypy 代码（使用 struct）
struct Point:
    x: float
    y: float
```

#### 步骤 3: 使用不可变变量

```python
# Python 代码
MAX_SIZE = 100

# Cypy 代码（使用 val）
val MAX_SIZE: int = 100
```

#### 步骤 4: 使用类型别名

```python
# Python 代码（注释方式）
# Vector is tuple[float, float, float]

# Cypy 代码（使用 type）
type Vector = tuple[float, float, float]
```

#### 步骤 5: 使用构建块

```python
# Python 代码
def process(data):
    cleaned = data.strip()
    parsed = int(cleaned)
    return parsed * 2

# Cypy 代码（使用构建块）
def process(data: str) -> int:
    result =:
        cleaned = data.strip()
        parsed = cleaned as int
        parsed * 2
    return result
```

### 5.2 兼容性检查清单

```python
# 兼容性检查清单

# ✅ 必须：Python 版本 >= 3.9
import sys
assert sys.version_info >= (3, 9), "Python 3.9+ required"

# ✅ 必须：Cython >= 3.0
import Cython
assert Cython.__version__ >= "3.0.0", "Cython 3.0+ required"

# ✅ 推荐：使用类型注解
def func(x: int) -> int:
    pass

# ✅ 推荐：使用静态类型
struct Point:
    x: float
    y: float

# ✅ 可选：使用 Cypy 特有语法
val MAX: int = 100
type Vector = tuple[float, float, float]
```

### 5.3 常见兼容性问题

#### 问题 1: 使用了 Python 3.9+ 语法

```python
# 问题代码（Python 3.9+）
dict1 = {"a": 1}
dict2 = {"b": 2}
merged = dict1 | dict2  # 字典合并运算符

# 兼容写法
merged = {**dict1, **dict2}
```

#### 问题 2: 使用了 f-string 调试

```python
# 问题代码（Python 3.8+）
x = 10
print(f"{x=}")  # f-string 调试

# 兼容写法
print(f"x={x}")
```

#### 问题 3: 使用了 match-case

```python
# 问题代码（Python 3.10+）
match status:
    case 200:
        print("OK")
    case _:
        print("Unknown")

# 兼容写法
if status == 200:
    print("OK")
else:
    print("Unknown")
```

## 6. 版本策略

### 6.1 语义化版本

```
版本格式: MAJOR.MINOR.PATCH

- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的功能新增
- PATCH: 向后兼容的 bug 修复
```

### 6.2 版本历史

```
v1.0.0    - 初始版本
v1.0.1    - 修复类型转换和隐式策略
v1.0.2    - 修复字符串转义和 match-case
v1.1.0    - 添加模块级魔法属性
v1.2.0    - 添加构建块语法
```

### 6.3 弃用策略

```
规则 1: 新特性在 MINOR 版本中添加
规则 2: 弃用特性在 MINOR 版本中标记
规则 3: 移除弃用特性在 MAJOR 版本中进行
规则 4: 所有变更记录在 CHANGELOG.md 中
```

## 7. 完整示例

```python
# 兼容性兼容的代码示例

# 确保 Python 版本
import sys
if sys.version_info < (3, 9):
    raise RuntimeError("Cypy requires Python 3.9 or higher")

# 兼容的字典合并（Python 3.5+）
dict1 = {"a": 1}
dict2 = {"b": 2}
merged = {**dict1, **dict2}

# 兼容的 f-string（Python 3.6+）
name = "Cypy"
message = f"Hello, {name}!"

# Cypy 特有语法
struct Config:
    debug: bool = False
    timeout: int = 30

val MAX_RETRIES: int = 3
type Result = tuple[bool, str]

def process(config: Config) -> Result:
    guard config.debug else return (True, "OK")
    
    result =:
        print(f"Processing with timeout: {config.timeout}")
        attempts = 0
        while attempts < MAX_RETRIES:
            attempts += 1
            if attempts == MAX_RETRIES:
                return (False, "Failed")
        (True, "Success")
    
    return result

# 主入口（兼容 Python）
if __name__ == "__main__":
    config = Config {debug: True, timeout: 60}
    success, msg = process(config)
    print(f"Result: {success}, Message: {msg}")
```
