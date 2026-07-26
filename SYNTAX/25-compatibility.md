# 兼容性

## Python 兼容性

### 语法兼容

```python
# 任何合法的 Python 代码都是合法的 Cypy 代码
def python_function(x, y):
    return x + y

# Python 3 特性支持
def fstring_example(name: str) -> str:
    return f"Hello, {name}!"

def type_hints_example(x: int) -> str:
    return str(x)
```

### 标准库兼容

```python
# 可以导入 Python 标准库
import os
import sys
import json
import threading
import asyncio

# 使用标准库功能
def read_config(path: str) -> dict[str, object]:
    with open(path, "r") as f:
        return json.load(f)
```

## 降级规则

### 渐进式类型

```python
# 有注解的变量 - 静态类型检查
val x: int = 10
x = "hello"  # ❌ 编译时类型错误

# 无注解的变量 - 退化为 PyObject
let dynamic = 42
dynamic = "hello"  # ✅ 允许，运行时动态类型

# 函数参数
def mixed_func(typed: int, untyped):
    # typed 参数进行类型检查
    # untyped 参数接受任意类型
    return typed + untyped
```

### `@python` 装饰器

```python
# @python 装饰器跳过类型检查，回退到 CPython
@python
def legacy_code(x, y):
    # 不进行类型检查
    return x + y

# 普通函数仍进行类型检查
def modern_code(x: int, y: int) -> int:
    return x + y
```

## 版本要求

### Python 版本

```python
# 支持 Python 3.6+
# Python 3.10+ 推荐（模式匹配支持）
```

### 依赖版本

```python
# Cython >= 0.29.28
# watchdog >= 2.1.0（热重载功能）
```

## 迁移指南

### 从 Python 迁移

```python
# 步骤 1：将 .py 文件重命名为 .cypy
# 步骤 2：添加类型注解
# 步骤 3：编译测试

# 示例迁移
# 原 Python 代码
def add(a, b):
    return a + b

# 迁移后的 Cypy 代码
def add(a: int, b: int) -> int:
    return a + b
```

### 增量迁移

```python
# 可以逐步迁移项目
# 保留部分文件为 .py（不转译）
# 将关键文件转换为 .cypy

# 混合使用
import python_module  # .py 文件，不转译
import cypy_module   # .cypy 文件，编译为 .pyd
```

## 注意事项

### 不支持的特性

```python
# Python 某些高级特性可能不支持
# 1. eval() 和 exec() 中的 Cypy 代码
# 2. 动态类创建（type()）
# 3. 某些复杂的元编程技术

# 这些功能需要使用 @python 装饰器
@python
def dynamic_code():
    exec("print('Hello')")
```

### Cython 差异

```python
# Cypy 与 Cython 的差异
# 1. Cypy 使用 Python 语法 + 扩展
# 2. Cython 需要显式 cdef/cpdef
# 3. Cypy 自动生成 Cython 代码

# Cypy 代码
struct Point:
    x: int
    y: int

# 生成的 Cython 代码（简化）
# cdef class Point:
#     cdef int x
#     cdef int y
```

## 兼容性特性

| 特性 | 说明 |
|------|------|
| **Python 超集** | 任何合法 Python 代码都是合法 Cypy 代码 |
| **渐进式类型** | 有注解使用静态类型，无注解退化为 PyObject |
| **@python 装饰器** | 跳过类型检查，回退到 CPython |
| **标准库兼容** | 可以导入和使用 Python 标准库 |
| **增量迁移** | 支持逐步迁移项目 |
| **版本要求** | Python 3.6+，推荐 3.10+ |