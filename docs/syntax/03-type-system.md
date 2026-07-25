# Cypy 语言语法规范 - 类型系统

## 1. 类型映射

Cypy 的类型系统基于 Python 类型注解，编译时映射到 Cython 静态类型：

### 1.1 基本类型映射

| Cypy 类型注解 | Cython 类型 | C 类型 | 说明 |
|--------------|-------------|--------|------|
| `int` | `cdef int` | `int` | 32 位整数 |
| `long` | `cdef long` | `long` | 64 位整数 |
| `float` | `cdef float` | `float` | 单精度浮点 |
| `double` | `cdef double` | `double` | 双精度浮点 |
| `bool` | `cdef bint` | `int` (0/1) | 布尔值 |
| `char` | `cdef char` | `char` | 字符 |
| `str` | `cdef str` | `PyUnicodeObject*` | Python 字符串 |
| `bytes` | `cdef bytes` | `PyBytesObject*` | Python 字节串 |
| 无注解 | `object` | `PyObject*` | 动态类型 |

### 1.2 容器类型映射

| Cypy 类型注解 | Cython 类型 | 说明 |
|--------------|-------------|------|
| `list[T]` | `list` | 泛型列表 |
| `dict[K, V]` | `dict` | 泛型字典 |
| `set[T]` | `set` | 泛型集合 |
| `tuple[T1, T2, ...]` | `tuple` | 元组 |

### 1.3 指针类型映射

| Cypy 类型注解 | Cython 类型 | C 类型 | 说明 |
|--------------|-------------|--------|------|
| `int*` | `cdef int*` | `int*` | 指向 int 的指针 |
| `double*` | `cdef double*` | `double*` | 指向 double 的指针 |
| `struct_name*` | `cdef struct_name*` | `struct_name*` | 指向结构体的指针 |

### 1.4 高级类型映射

| Cypy 类型注解 | Cython 类型 | 说明 |
|--------------|-------------|------|
| `Option[T]` | `object` | 可选类型（可为 None） |
| `Result[T, E]` | `object` | 结果类型 |
| `Vec[T]` | `list` | 动态数组 |
| `HashMap[K, V]` | `dict` | 哈希映射 |
| `meta[T]` | `type` | 类型的类型（元类） |

## 2. 指针类型

### 2.1 指针声明

```python
# 声明指针变量（必须有类型注解）
ptr: int* = malloc(sizeof(int))
buffer: double* = malloc(sizeof(double) * 100)
data: Point* = malloc(sizeof(Point))

# 指针类型必须显式注解，不能推断
ptr = malloc(sizeof(int))  # ❌ 编译错误：缺少类型注解
```

### 2.2 指针操作

```python
# 指针解引用（使用 &）
value: int = &ptr
&ptr = 42

# 指针算术（数组访问）
buffer[i] = 3.14

# 结构体指针字段访问（自动解引用）
data.x = 1.0
data.y = 2.0

# 取地址操作（使用 addr() 内置函数）
arr: int* = malloc(sizeof(int) * 10)
elem_ptr: int* = addr(arr[5])

# 指针比较
if ptr is not NULL:
    pass
```

## 3. 类型推断规则

### 3.1 变量类型推断

```
规则 1: 变量声明时若有类型注解，使用该类型
    x: int = 10           → cdef int x = 10

规则 2: 变量声明时若无类型注解，退化为 PyObject
    x = 10                → x = 10 (PyObject)

规则 3: None 可赋值给任意类型
    let x: int = None     → ✅ 允许（可选类型）

规则 4: 列表字面量自动推断元素类型
    numbers = [1, 2, 3]   → list[int]
    mixed = [1, "a"]      → list[object]
```

### 3.2 函数类型推断

```
规则 1: 函数参数/返回值有注解时，使用指定类型
    def add(a: int, b: int) -> int:
        return a + b      → cpdef int add(int a, int b)

规则 2: 函数参数/返回值无注解时，使用 PyObject
    def add(a, b):
        return a + b      → def add(a, b)

规则 3: 返回类型可从返回语句推断
    def multiply(a: int, b: int):
        return a * b      → 推断返回类型为 int
```

### 3.3 循环变量类型推断

```python
# 从泛型列表推断元素类型
items: list[int] = [1, 2, 3, 4, 5]
for item in items:
    # item 自动推断为 int 类型
    print(item + 1)

# 从字典推断键值类型
person: dict[str, int] = {"age": 30}
for key, value in person.items():
    # key 推断为 str，value 推断为 int
    pass
```

## 4. 泛型类型

### 4.1 泛型列表

```python
# 显式声明泛型列表
numbers: list[int] = [1, 2, 3]
names: list[str] = ["Alice", "Bob"]
mixed: list[object] = [1, "hello", True]

# 泛型列表类型推断
items = [1, 2, 3]       # 推断为 list[int]
floats = [1.0, 2.0, 3.0] # 推断为 list[float]
```

### 4.2 泛型字典

```python
# 显式声明泛型字典
person: dict[str, int] = {"age": 30, "score": 95}
config: dict[str, object] = {"debug": True, "timeout": 30}

# 泛型字典类型推断
mapping = {"name": "Alice", "age": 30}  # 推断为 dict[str, object]
```

### 4.3 泛型集合

```python
# 显式声明泛型集合
unique: set[int] = {1, 2, 3, 3, 2, 1}
tags: set[str] = {"python", "cython", "cypy"}
```

### 4.4 泛型结构体

```python
struct Container[T]:
    value: T
    next: Container[T]*

# 使用泛型结构体
int_container: Container[int] = Container[int] {value: 42, next: NULL}
str_container: Container[str] = Container[str] {value: "hello", next: NULL}
```

## 5. 类型检查

### 5.1 编译时类型检查

Cypy 在编译时进行严格的类型检查：

```python
def add(a: int, b: int) -> int:
    return a + b

# ✅ 正确调用
result = add(2, 3)

# ❌ 类型不匹配
result = add("2", 3)  # 编译错误：期望 int，得到 str
result = add(2)       # 编译错误：缺少参数
```

### 5.2 类型转换检查

```python
# ✅ 显式转换
a: int = 10
b: float = a as float

# ❌ 隐式转换（无类型注解时允许）
x: int = 10.5  # 编译错误：期望 int，得到 float
```

### 5.3 结构体字段检查

```python
struct Point:
    x: float
    y: float

p = Point {x: 10.0, y: 20.0}

# ✅ 正确访问
print(p.x)

# ❌ 字段不存在
print(p.z)  # 编译错误：结构体 Point 没有字段 z
```

## 6. 类型兼容性

### 6.1 向上兼容

```python
# int 可赋值给 float（向上兼容）
value: float = 10  # ✅ 允许，自动转换

# float 不可赋值给 int（需要显式转换）
count: int = 3.14  # ❌ 编译错误
count: int = 3.14 as int  # ✅ 允许
```

### 6.2 None 兼容性

```python
# None 可赋值给任意类型
x: int = None      # ✅ 允许
name: str = None   # ✅ 允许
ptr: int* = None   # ✅ 允许

# 使用前需检查
if x is not None:
    print(x + 1)
```

### 6.3 容器类型兼容性

```python
# list[子类] 可赋值给 list[父类]（协变）
class Animal:
    pass

class Dog(Animal):
    pass

animals: list[Animal] = [Dog(), Dog()]  # ✅ 允许
```

## 7. 类型系统特性

### 7.1 渐进式类型

Cypy 采用渐进式类型系统，允许动态类型和静态类型混合使用：

```python
# 动态类型（PyObject）
name = "Alice"
age = 30

# 静态类型（编译时检查）
count: int = 100
price: float = 3.99

# 混合使用
def process(data, limit: int) -> str:
    # data 是 PyObject（动态）
    # limit 是 int（静态）
    return f"Processed {limit} items"
```

### 7.2 类型注解可选

类型注解是可选的，无注解时退化为 PyObject：

```python
# 完全无注解（纯 Python 模式）
def add(a, b):
    return a + b

# 部分注解
def multiply(a: int, b):
    return a * b

# 完全注解
def divide(a: float, b: float) -> float:
    return a / b
```

### 7.3 类型别名

```python
# 定义类型别名
type Number = int | float | double
type Vector = tuple[float, float, float]
type Callback = callable[[int, str], bool]

# 使用类型别名
def process(value: Number) -> str:
    return str(value)

def get_position() -> Vector:
    return (1.0, 2.0, 3.0)
```

## 8. 类型系统与 Cython 的关系

### 8.1 编译后的类型

| Cypy 代码 | 编译后的 Cython 代码 |
|-----------|---------------------|
| `x: int = 10` | `cdef int x = 10` |
| `def add(a: int, b: int) -> int:` | `cpdef int add(int a, int b):` |
| `ptr: int* = malloc(sizeof(int))` | `cdef int* ptr = <int*>malloc(sizeof(int))` |
| `p = Point {x: 1.0, y: 2.0}` | `cdef Point p; p.x = 1.0; p.y = 2.0` |

### 8.2 性能优势

使用静态类型的优势：

1. **编译时检查**：提前发现类型错误
2. **更快的执行**：静态类型避免运行时类型检查
3. **更小的内存占用**：基础类型使用 C 级内存布局
4. **更好的 C 互操作性**：直接访问 C 数据结构
