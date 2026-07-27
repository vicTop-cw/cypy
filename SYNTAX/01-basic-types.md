# 基础类型系统

## 数值类型

### 整数类型

```python
# 普通整数
x: int = 42
y: int = -10

# 长整数（Python 3 中 int 已支持任意精度）
large: int = 1000000000000000000000
```

### 浮点数类型

```python
# 单精度浮点数
pi: float = 3.14159

# 双精度浮点数
e: double = 2.718281828459045
```

### 布尔类型

```python
flag: bool = True
result: bool = False

# 布尔运算
and_result: bool = True and False
or_result: bool = True or False
not_result: bool = not True
```

## 字符串类型

### 基本字符串

```python
# 普通字符串
name: str = "Alice"

# 多行字符串
description: str = """
This is a
multi-line string
"""

# 原始字符串（不转义）
path: str = r"C:\Users\admin\Documents"

# f-string（格式化字符串）
age: int = 30
message: str = f"Name: {name}, Age: {age}"
```

### 字符串操作

```python
# 连接
full_name: str = "Alice" + " " + "Smith"

# 重复
stars: str = "*" * 10

# 切片
sub: str = "Hello, World"[0:5]  # "Hello"

# 长度
length: int = len("Hello")  # 5
```

## 容器类型

### 列表

```python
# 普通列表（带类型注解）
numbers: list[int] = [1, 2, 3, 4, 5]
names: list[str] = ["Alice", "Bob", "Charlie"]

# 嵌套列表
matrix: list[list[int]] = [[1, 2], [3, 4]]

# 空列表
empty: list[int] = []
```

### 字典

```python
# 字典（键值对）
person: dict[str, object] = {"name": "Alice", "age": 30}
config: dict[str, bool] = {"debug": True, "verbose": False}

# 空字典
empty: dict[str, int] = {}
```

### 集合

```python
# 集合（唯一元素）
unique_numbers: set[int] = {1, 2, 3, 3, 2, 1}  # {1, 2, 3}

# 空集合
empty: set[int] = set()
```

### 元组

```python
# 元组（不可变）
point: tuple[int, int] = (10, 20)
rgb: tuple[int, int, int] = (255, 0, 0)

# 单元素元组（注意逗号）
single: tuple[int] = (42,)
```

## 特殊类型

### None 类型

```python
# None 值
value: None = None

# 可选类型（可能为 None）
optional: object = None
```

### Never 类型

```python
# 表示永远不会正常返回的函数
def abort() -> Never:
    raise SystemExit(1)
```

## 类型推断

Cypy 采用渐进式类型系统，有注解的变量使用静态类型，无注解的变量退化为 `object` 类型：

```python
# 有注解变量 - 使用静态类型
x: int = 10       # int 类型，编译时检查
name: str = "Bob" # str 类型，编译时检查

# 无注解变量 - 退化为 object 类型
dynamic = 42      # object 类型，运行时动态
dynamic = "hello" # ✅ 允许重新赋值为其他类型

# 函数返回类型推断
def add(a: int, b: int):
    return a + b  # 推断返回类型为 int

# 列表字面量类型推断
numbers = [1, 2, 3]  # object 类型（无注解）
items: list[int] = [1, 2, 3]  # list[int] 类型
```

## 类型检查规则

| 规则 | 说明 |
|------|------|
| **有注解** | 变量使用静态类型，编译时检查类型一致性 |
| **无注解** | 变量退化为 `object` 类型，运行时动态类型 |
| **函数参数** | 有注解的参数进行类型检查，无注解的参数接受任意类型 |
| **函数返回** | 有注解的返回值进行类型检查，无注解时从返回语句推断 |
| **数值转换** | 支持 `bool` → `int` → `float` → `double` 的隐式向上转换 |
| **泛型兼容** | `list[int]` 可以赋值给 `list[object]`（向上转换） |