# Cypy 语言完整语法文档

> **Cypy** = Cython + Python Syntactic Sugar
> 
> 一种基于 Python 语法体系的编译型语言，通过 Cython 作为后端实现性能提升，同时引入类型系统和语法糖，在保持 Python 兼容性的前提下提供更好的性能和稳定性。

---

## 目录

1. [设计理念](#1-设计理念)
2. [类型系统](#2-类型系统)
3. [作用域层级系统](#3-作用域层级系统)
4. [基础语法](#4-基础语法)
5. [新语法构造](#5-新语法构造)
6. [语法糖](#6-语法糖)
7. [编译与工具链](#7-编译与工具链)
8. [兼容性与降级规则](#8-兼容性与降级规则)
9. [代码示例](#9-代码示例)
10. [实现说明](#10-实现说明)

---

## 1. 设计理念

### 1.1 核心原则

| 原则 | 说明 |
|------|------|
| **Python 超集** | 任何合法的 Python 代码都是合法的 Cypy 代码 |
| **渐进式类型** | 有注解的变量使用静态类型，无注解的变量退化为 PyObject |
| **编译时检查** | `cypyc` 转译器提前发现类型错误 |
| **Cython 后端** | 最终编译目标为 Cython，生成高性能 C 代码 |
| **简洁语法** | 引入必要的语法糖，保持 Python 的可读性 |
| **显式内存管理** | 指针变量默认逃逸，需显式使用 `defer` 延迟清理 |

### 1.2 架构层次

```
┌─────────────────────────────────────────────┐
│              Cypy 源码 (.cypy)              │
└─────────────────────┬───────────────────────┘
                      │ cypyc 转译器
                      ▼
┌─────────────────────────────────────────────┐
│              Cython 代码 (.pyx)             │
└─────────────────────┬───────────────────────┘
                      │ Cython 编译器
                      ▼
┌─────────────────────────────────────────────┐
│                  C 代码 (.c)                │
└─────────────────────┬───────────────────────┘
                      │ C 编译器
                      ▼
┌─────────────────────────────────────────────┐
│               二进制扩展 (.so/.pyd)          │
└─────────────────────────────────────────────┘
```

---

## 2. 类型系统

### 2.1 类型映射表

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
| `list[T]` | `list` | `PyListObject*` | 泛型列表 |
| `dict[K, V]` | `dict` | `PyDictObject*` | 泛型字典 |
| `set[T]` | `set` | `PySetObject*` | 泛型集合 |
| `int*` | `cdef int*` | `int*` | 指向 int 的指针 |
| `double*` | `cdef double*` | `double*` | 指向 double 的指针 |
| `struct_name*` | `cdef struct_name*` | `struct_name*` | 指向结构体的指针 |
| `Option[T]` | `object` | `PyObject*` | 可选类型 |
| `Result[T, E]` | `object` | `PyObject*` | 结果类型 |
| `Vec[T]` | `list` | `PyListObject*` | 动态数组 |
| `HashMap[K, V]` | `dict` | `PyDictObject*` | 哈希映射 |
| `meta[T]` | `type` | `PyTypeObject*` | 类型的类型（元类） |
| 无注解 | `object` | `PyObject*` | 动态类型 |

### 2.2 指针类型

#### 语法

```python
# 声明指针变量
ptr: int* = malloc(sizeof(int))
buffer: double* = malloc(sizeof(double) * 100)
data: Point* = malloc(sizeof(Point))
```

#### 转译目标

```cython
# Cython 转译结果
from libc.stdlib cimport malloc, free, sizeof

cdef int* ptr = <int*>malloc(sizeof(int))
cdef double* buffer = <double*>malloc(sizeof(double) * 100)
cdef Point* data = <Point*>malloc(sizeof(Point))
```

#### 指针操作

```python
# 指针解引用（使用 &）
val value: int = &ptr

# 指针赋值（使用 &）
&ptr = 42

# 指针算术（数组访问）
buffer[i] = 3.14

# 结构体指针字段访问
data.x = 1.0  # 自动解引用，等价于 (&data).x
data.y = 2.0

# 取地址操作（使用 addr() 内置函数）
arr: int* = malloc(sizeof(int) * 10)
elem_ptr: int* = addr(arr[5])  # 获取数组元素的地址
```

#### 运算符语义

> **关键设计**：`&` 仅用于解引用指针，`addr()` 函数用于取地址，`*` 仅用于指针类型注解和乘法运算。这种设计避免了解析时的歧义问题。

```
& 运算符语义：
  - 前缀运算符，仅用于解引用指针（获取指针指向的值）
      &ptr              → 获取 ptr 指向的值（ptr 必须是指针类型）
      &ptr = 42         → 赋值给 ptr 指向的内存
      
  - 注意：& 不能用于取地址，取地址必须使用 addr() 函数

addr() 内置函数：
  - 用于获取变量或表达式的地址
      addr(local_var)   → 获取局部变量的地址
      addr(arr[i])      → 获取数组元素的地址
      
  - 仅适用于 C 类型变量（int, double, struct 等），不适用于 Python 对象

* 运算符语义：
  - 在类型注解中 → 指针类型修饰符
      x: int*           → 指向 int 的指针类型
      
  - 在表达式中 → 乘法运算符
      x * y             → 乘法运算
```

#### 运算符语义示例

```python
# 指针声明（* 在类型注解中表示指针类型）
ptr: int* = malloc(sizeof(int))
defer free(ptr)

# 解引用（& 在前缀位置，操作数必须是指针类型）
value: int = &ptr      # 获取 ptr 指向的值
&ptr = 42              # 赋值给 ptr 指向的内存

# 取地址（使用 addr() 函数）
local: int = 100
local_ptr: int* = addr(local)  # 获取 local 变量的地址

# 数组操作
arr: int* = malloc(sizeof(int) * 10)
defer free(arr)

arr[5] = 42              # 数组元素赋值
elem_ptr: int* = addr(arr[5])  # 取地址（使用 addr()）
&elem_ptr = 100          # 解引用（elem_ptr 类型为 int*）

# 乘法（* 在中缀位置）
result = 2 * 3           # 乘法运算
area = &ptr * 2          # 先解引用 ptr，再乘法
```

#### 地址操作限制

> **重要**：`addr()` 函数仅适用于 C 类型变量，不适用于 Python 对象。

| 类型 | 是否支持 addr() | 说明 |
|------|-----------------|------|
| `int`, `double`, `float` 等 | ✅ 支持 | C 原生类型 |
| `struct` 字段 | ✅ 支持 | C 结构体字段 |
| `int*`, `double*` 等 | ✅ 支持 | 指针变量本身 |
| Python `str`, `list`, `dict` | ❌ 不支持 | Python 对象 |
| Python class 实例 | ❌ 不支持 | Python 对象 |

```python
# 正确：C 类型变量取地址
x: int = 100
ptr: int* = addr(x)  # ✅

# 错误：Python 对象不能取地址
name: str = "Cypy"
ptr: str* = addr(name)  # ❌ 编译错误：Python 对象不支持取地址

data = {"key": "value"}
ptr = addr(data)  # ❌ 编译错误：Python 对象不支持取地址
```

#### 逃逸语义

> **核心规则**：所有指针变量默认是**逃逸的**（escaped），编译器不会自动插入 `free()` 调用。必须显式使用 `defer` 语句进行延迟清理。

```python
# 正确：使用 defer 清理指针
ptr: int* = malloc(sizeof(int))
defer free(ptr)  # ← 必须显式清理

&ptr = 42
return &ptr
```

#### 指针与 Python 对象的互操作

| 操作 | 是否允许 | 说明 |
|------|----------|------|
| 指针 → Python 对象 | ❌ 不允许 | 指针不能直接赋值给 Python 对象 |
| Python 对象 → 指针 | ❌ 不允许 | Python 对象不能直接转换为指针 |
| 指针解引用 → Python 对象 | ✅ 允许 | 解引用后的值可以赋值给 Python 对象 |
| Python 对象 → 指针指向内存 | ✅ 允许 | 通过解引用赋值 |

```python
# 正确的转换
ptr: int* = malloc(sizeof(int))
defer free(ptr)

py_value = 42
&ptr = py_value  # Python int → C int

result = &ptr  # C int → Python int
print(result)
```

### 2.3 类型推断规则

```
规则 1: 变量声明时若有类型注解，使用该类型
    x: int = 10           → cdef int x = 10
    ptr: int* = malloc(...) → cdef int* ptr = <int*>malloc(...)

规则 2: 变量声明时若无类型注解，退化为 PyObject
    x = 10                → x = 10 (PyObject)

规则 3: 函数参数/返回值有注解时，使用指定类型
    def add(a: int, b: int) -> int:
        return a + b      → cpdef int add(int a, int b)

规则 4: 函数参数/返回值无注解时，使用 PyObject
    def add(a, b):
        return a + b      → def add(a, b)

规则 5: 指针类型必须显式注解，不能推断
    ptr: int* = malloc(...)  # ✅ 必须有注解
    ptr = malloc(...)        # ❌ 编译错误：指针类型必须显式声明
```

### 2.4 类型安全

- **编译时检查**：`cypyc` 会检查类型注解的一致性
- **自动转换**：C 类型与 Python 对象之间自动转换
- **运行时保护**：类型不匹配时抛出 `TypeError`
- **指针安全**：`cypyc` 会检查指针类型匹配，防止类型错误的指针操作

### 2.5 泛型类型

> **设计理念**：泛型是 Cypy 类型系统的核心特性，使用尖括号 `<>` 表示类型参数，支持泛型结构体、泛型函数、泛型 trait 和类型约束。

#### 泛型语法

```python
# 泛型变量声明
values: list[int] = [1, 2, 3]
mapping: dict[str, int] = {"a": 1, "b": 2}

# 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

# 泛型函数
def identity[T](value: T) -> T:
    return value

def swap[T, U](a: T, b: U) -> Pair[U, T]:
    return Pair[U, T](b, a)
```

#### 泛型结构体

```python
# 定义泛型结构体
struct Option[T]:
    has_value: bool
    value: T

struct Result[T, E]:
    is_ok: bool
    ok_value: T
    err_value: E

# 使用泛型结构体
def find_user(id: int) -> Option[str]:
    if id == 1:
        return Option[str](has_value=True, value="Alice")
    return Option[str](has_value=False, value="")

def divide(a: float, b: float) -> Result[float, str]:
    if b == 0:
        return Result[float, str](is_ok=False, ok_value=0.0, err_value="Division by zero")
    return Result[float, str](is_ok=True, ok_value=a / b, err_value="")
```

#### 泛型函数

```python
# 简单泛型函数
def make_pair[T, U](first: T, second: U) -> Pair[T, U]:
    return Pair[T, U](first, second)

# 泛型函数与类型推断
def create_list[T](*args: T) -> list[T]:
    return list(args)

# 使用
p = make_pair(1, "hello")  # 自动推断为 Pair[int, str]
nums = create_list(1, 2, 3)  # 自动推断为 list[int]
```

#### 泛型 Trait

```python
# 泛型 trait
trait Collection[T]:
    def add(self, item: T) -> None:
        ...
    
    def get(self, index: int) -> T:
        ...
    
    def size(self) -> int:
        ...

# 实现泛型 trait
struct Vec[T]:
    data: T*
    length: int
    capacity: int

impl Collection[T] for Vec[T]:
    def add(self, item: T) -> None:
        # 实现逻辑
        pass
    
    def get(self, index: int) -> T:
        return &self.data[index]
    
    def size(self) -> int:
        return self.length
```

#### 类型约束

> **设计理念**：类型约束允许限制泛型参数必须满足的条件，增强类型安全。

```python
# 使用 trait 作为约束
def process[T: Drawable](item: T) -> None:
    item.draw()

# 多重约束
def serialize[T: Serializable & Clone](obj: T) -> bytes:
    return obj.serialize()

# where 子句（更复杂的约束）
def compare[T, U](a: T, b: U) -> bool where T: Comparable[U]:
    return a.compare_to(b)
```

#### 内置泛型类型

| 类型 | 说明 | 转译目标 |
|------|------|----------|
| `Option[T]` | 可选类型（存在或不存在） | Python 对象 |
| `Result[T, E]` | 结果类型（成功或失败） | Python 对象 |
| `Vec[T]` | 动态数组 | Python list |
| `HashMap[K, V]` | 哈希映射 | Python dict |
| `list[T]` | 泛型列表 | Python list |
| `dict[K, V]` | 泛型字典 | Python dict |
| `set[T]` | 泛型集合 | Python set |

#### 泛型转译策略

```python
# Cypy 泛型函数
def identity[T](value: T) -> T:
    return value

# 转译结果（Cython，运行时类型擦除）
def identity(value):
    return value

# Cypy 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

# 转译结果（Cython，使用 C 结构体）
cdef struct Pair:
    object first
    object second
```

> **注意**：由于 Cython 不支持真正的静态泛型实例化，Cypy 采用**运行时类型擦除**策略，将泛型参数退化为 PyObject。对于性能敏感的场景，可以使用特化版本。

#### 泛型类型擦除策略

Cypy 的泛型转译根据类型参数的性质采用不同策略：

**策略 1：C 原生类型参数（int, double, float, bool 等）**

```python
# Cypy 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

# 实例化：Pair[int, double]
# 转译结果（生成特化版本）
cdef struct Pair_int_double:
    int first
    double second

# 实例化：Pair[double, double]  
# 转译结果（生成特化版本）
cdef struct Pair_double_double:
    double first
    double second
```

**策略 2：Python 对象类型参数（str, list, dict, 类实例等）**

```python
# Cypy 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

# 实例化：Pair[str, list[int]]
# 转译结果（类型擦除）
cdef struct Pair:
    object first
    object second
```

**策略 3：混合类型参数**

```python
# Cypy 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

# 实例化：Pair[int, str]
# 转译结果（混合特化）
cdef struct Pair_int_object:
    int first
    object second
```

**策略 4：泛型函数转译**

```python
# Cypy 泛型函数
def identity[T](value: T) -> T:
    return value

# 转译结果（类型擦除，运行时检查）
def identity(value):
    return value

# 带类型约束的泛型函数
def process[T: Drawable](item: T) -> None:
    item.draw()

# 转译结果（添加运行时类型检查）
def process(item):
    if not isinstance(item, Drawable):
        raise TypeError(f"Expected Drawable, got {type(item)}")
    item.draw()
```

**策略 5：泛型 trait 实现**

```python
# Cypy 泛型 trait
trait Collection[T]:
    def add(self, item: T) -> None:
        ...
    
    def get(self, index: int) -> T:
        ...

# 实现泛型 trait
impl Collection[int] for Vec_int:
    def add(self, item: int) -> None:
        # 实现逻辑
        pass
    
    def get(self, index: int) -> int:
        return &self.data[index]
```

**类型擦除规则总结**

| 类型参数 | 转译策略 | 性能特点 |
|----------|----------|----------|
| 纯 C 类型 | 特化生成 | 高性能，零运行时开销 |
| 纯 Python 对象 | 类型擦除 | 中等性能，有类型转换开销 |
| 混合类型 | 混合特化 | 高性能，仅对象字段有转换开销 |
| 泛型函数 | 类型擦除 + 运行时检查 | 中等性能，有类型检查开销 |

> **编译器优化**：`cypyc` 会在编译时分析泛型实例化模式，自动生成特化版本。对于常用的类型组合（如 `Pair[int, int]`, `Vec[double]`），会在编译时生成特化的 C 结构体和函数，避免运行时类型检查。

### 2.6 meta 类型系统（类型的类型）

> **设计理念**：参考 Julia 的类型系统设计，`meta` 是 Cypy 中"类型的类型"系统。它不是 Python 风格的元类（metaclass），而是用于定义类型约束、实现多重分派（Multiple Dispatch）的编译期工具。`meta` 代码仅在 `cypyc` 转译器中有效，**不翻译成 Cython 代码**，而是指导转译器生成优化的分派代码。

> **核心思想**：类型是一等公民。在 Cypy 中，类型本身可以作为值传递、存储和操作，但这些操作发生在编译期而非运行期。

#### meta 基本概念

```
meta 系统的核心层次：
┌─────────────────────────────────────────┐
│  值层（Value Level）                     │
│  ┌───────────────────────────────────┐  │
│  │  具体值：42, "hello", Point(1,2)  │  │
│  └───────────────────────────────────┘  │
└─────────────────────┬───────────────────┘
                      │ 类型Of
                      ▼
┌─────────────────────────────────────────┐
│  类型层（Type Level）                    │
│  ┌───────────────────────────────────┐  │
│  │  类型：int, str, Point, Pair[T,U] │  │
│  └───────────────────────────────────┘  │
└─────────────────────┬───────────────────┘
                      │ meta Of
                      ▼
┌─────────────────────────────────────────┐
│  meta 层（Meta Level）                   │
│  ┌───────────────────────────────────┐  │
│  │  meta 类型：meta[int], meta[Point] │  │
│  │  类型约束：Number, Drawable, etc.  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

#### meta 语法

> **重要说明**：`meta` 块是 Cypy 特有的编译期构造，其中使用的 `<:`（子类型关系）、`constraint`、`abstract`、`subtype`、`concrete`、`dispatch` 等关键字仅在 `meta` 块内有效，**不能在普通 Cypy 代码中使用**。`meta` 块内容不生成任何运行时代码，仅用于指导 `cypyc` 转译器进行类型检查和多分派代码生成。

```python
# meta 关键字用于声明类型层面的约束和分派规则
meta:
    # 定义类型约束
    constraint Number = int | float | double
    
    # 定义类型层次
    abstract Animal
    subtype Dog <: Animal
    subtype Cat <: Animal
    
    # 定义多重分派规则
    dispatch add(a: int, b: int) -> int
    dispatch add(a: float, b: float) -> float
    dispatch add(a: int, b: float) -> float
```

#### 类型约束定义

```python
meta:
    # 联合类型约束
    constraint Number = int | float | double | long
    
    # 交集类型约束
    constraint SerializableAndClone = Serializable & Clone
    
    # 泛型约束
    constraint Collection[T] = Vec[T] | list[T]
    
    # 递归约束
    constraint Tree[T] = Leaf[T] | Node[T, Tree[T], Tree[T]]
    
    # 约束继承
    constraint RealNumber <: Number
    constraint Integer <: RealNumber
```

#### 类型层次定义

```python
meta:
    # 抽象类型（类似 Julia 的 abstract type）
    abstract Shape
    
    # 子类型关系（类似 Julia 的 <:）
    subtype Circle <: Shape
    subtype Rectangle <: Shape
    subtype Square <: Rectangle  # 传递性：Square <: Rectangle <: Shape
    
    # 泛型抽象类型
    abstract Container[T]
    
    subtype Vec[T] <: Container[T]
    subtype list[T] <: Container[T]
    
    # 具体类型
    concrete Point
    concrete Pair[T, U]
```

#### 多重分派定义（核心特性）

```python
meta:
    # 定义函数分派规则
    dispatch meet(a: Dog, b: Dog) -> str
    dispatch meet(a: Dog, b: Cat) -> str
    dispatch meet(a: Cat, b: Dog) -> str
    dispatch meet(a: Cat, b: Cat) -> str
    
    # 泛型分派
    dispatch process[T](item: T) -> None
    dispatch process[T: Drawable](item: T) -> None
    
    # 优先级规则（更具体的类型优先）
    dispatch add(a: int, b: int) -> int          # 最具体
    dispatch add(a: int, b: float) -> float      # 次具体
    dispatch add(a: Number, b: Number) -> Number # 最通用
```

#### meta 与函数实现的配合

```python
# 定义类型（值层）
struct Dog:
    name: str

struct Cat:
    name: str

# 定义 meta 规则（meta 层）
meta:
    abstract Animal
    subtype Dog <: Animal
    subtype Cat <: Animal
    
    dispatch meet(a: Dog, b: Dog) -> str
    dispatch meet(a: Dog, b: Cat) -> str
    dispatch meet(a: Cat, b: Dog) -> str
    dispatch meet(a: Cat, b: Cat) -> str
    dispatch meet(a: Animal, b: Animal) -> str  # 兜底
```

#### 分派实现

```python
# 根据 meta 规则实现具体方法
def meet(a: Dog, b: Dog) -> str:
    return f"{a.name} and {b.name} play together"

def meet(a: Dog, b: Cat) -> str:
    return f"{a.name} chases {b.name}"

def meet(a: Cat, b: Dog) -> str:
    return f"{a.name} hisses at {b.name}"

def meet(a: Cat, b: Cat) -> str:
    return f"{a.name} and {b.name} ignore each other"

def meet(a: Animal, b: Animal) -> str:
    return f"Animals meet"

# 使用
dog1 = Dog(name="Buddy")
cat1 = Cat(name="Mittens")

print(meet(dog1, dog1))  # "Buddy and Buddy play together"
print(meet(dog1, cat1))  # "Buddy chases Mittens"
print(meet(cat1, dog1))  # "Mittens hisses at Buddy"
```

#### meta 转译策略

> **关键设计**：`meta` 代码不翻译成 Cython 运行时代码。`cypyc` 转译器在编译时解析 `meta` 块，生成优化的分派代码。

```python
# Cypy 源码（含 meta）
meta:
    abstract Shape
    subtype Circle <: Shape
    subtype Rectangle <: Shape
    dispatch area(s: Circle) -> double
    dispatch area(s: Rectangle) -> double

struct Circle:
    radius: double

struct Rectangle:
    width: double
    height: double

def area(s: Circle) -> double:
    return PI * s.radius * s.radius

def area(s: Rectangle) -> double:
    return s.width * s.height

# 转译结果（Cython，分派被特化）
cdef struct Circle:
    double radius

cdef struct Rectangle:
    double width
    double height

cpdef double area_Circle(Circle s):
    return 3.14159 * s.radius * s.radius

cpdef double area_Rectangle(Rectangle s):
    return s.width * s.height

# 分派函数（运行时根据类型选择）
cpdef double area(object s):
    if isinstance(s, Circle):
        return area_Circle(s)
    elif isinstance(s, Rectangle):
        return area_Rectangle(s)
    else:
        raise TypeError(f"Unsupported type: {type(s)}")
```

#### 泛型多重分派

```python
meta:
    # 泛型分派规则
    dispatch serialize[T](obj: T) -> bytes
    dispatch serialize[T: Serializable](obj: T) -> bytes
    
    # 特定类型的泛型分派
    dispatch serialize[T](obj: Vec[T]) -> bytes
    dispatch serialize[T](obj: list[T]) -> bytes

# 实现
def serialize[T](obj: T) -> bytes:
    # 默认实现
    return str(obj).encode()

def serialize[T: Serializable](obj: T) -> bytes:
    # 优化实现
    return obj.serialize()

def serialize[T](obj: Vec[T]) -> bytes:
    # Vec 特定实现
    ...

def serialize[T](obj: list[T]) -> bytes:
    # list 特定实现
    ...
```

#### meta 的编译期处理

`cypyc` 转译器对 `meta` 块的处理流程：

```
1. 解析阶段：
   └── 解析 meta 块中的类型约束和分派规则
   └── 构建类型层次图（Type Hierarchy Graph）
   └── 构建分派表（Dispatch Table）

2. 类型检查阶段：
   └── 验证函数实现是否符合 meta 规则
   └── 检查分派规则的完整性
   └── 检查类型层次的一致性

3. 代码生成阶段：
   └── 根据分派规则生成特化函数
   └── 生成分派调度器
   └── 优化分派路径（内联、缓存等）
```

#### meta 与类型系统的交互

```python
meta:
    # 类型约束可以用于函数参数
    constraint Numeric = int | float | double
    
    # 定义分派
    dispatch compute[T: Numeric](value: T) -> T

# 使用约束
def compute[T: Numeric](value: T) -> T:
    return value * 2

# 自动生成特化版本
# compute_int(int) -> int
# compute_float(float) -> float  
# compute_double(double) -> double
```

#### meta 的限制

| 限制 | 说明 |
|------|------|
| **编译期有效** | `meta` 代码仅在 `cypyc` 转译时处理，不生成运行时代码 |
| **不能嵌套** | `meta` 块只能写在模块顶级（层级 0） |
| **无运行时反射** | `meta` 不提供运行时类型检查或反射能力 |
| **静态分派** | 分派决策在编译时确定，不支持动态添加方法 |

#### 与 Julia 的对比

| 特性 | Cypy (meta) | Julia |
|------|-------------|-------|
| **类型作为值** | 编译期 | 运行期 |
| **多重分派** | 编译期生成特化代码 | 运行时分派 |
| **类型层次** | 显式声明 | 自动推断 |
| **元编程** | meta 块 | Expr + eval |
| **性能** | 静态分派，零运行时开销 | JIT 编译，首次调用有开销 |
| **灵活性** | 中等 | 高度灵活 |

---

## 3. 作用域层级系统

### 3.1 层级定义

Cypy 使用缩进层级来确定作用域，层级从 0 开始编号：

```
层级 0: 模块顶级 (无缩进)
层级 1: 类/函数内部
层级 2: 条件/循环内部
层级 3: 嵌套条件/循环内部
...
```

### 3.2 层级表示

使用 **缩进级别** (indent level) 和 **块类型** (block type) 来表示当前位置：

```python
# 层级表示结构
{
    "level": int,              # 缩进层级 (从 0 开始)
    "block_type": str,         # 块类型: module, class, function, if, while, for, with, try
    "parent": Optional[Scope], # 父作用域引用
    "variables": Dict[str, Type],  # 当前作用域的变量声明
    "is_top_level": bool,      # 是否为模块顶级
    "defer_stack": List[AST]   # 当前作用域的 defer 语句栈
}
```

### 3.3 层级规则

| 规则 | 说明 |
|------|------|
| **模块顶级** | 层级为 0，只能定义模块级变量、函数、类、impl、struct、trait、enum |
| **类内部** | 层级为 1，可定义类变量、方法（遵循 Python 规则） |
| **函数内部** | 层级为 1，可定义局部变量、嵌套函数、defer 语句 |
| **代码块** | 层级 >= 2，可定义局部变量、defer 语句 |

### 3.4 安全注入点

在转译时，不同层级有不同的注入规则：

```
层级 0 (模块顶级):
  - 可安全注入 import 语句
  - 可安全注入 cdef 声明
  - 可安全注入模块级变量

层级 1 (类/函数):
  - 可安全注入 cdef/cpdef 声明
  - 可安全注入局部变量声明
  - 可安全注入 defer 语句（收集到 defer_stack）

层级 >= 2 (代码块):
  - 仅能注入表达式和语句
  - 可安全注入 defer 语句（收集到 defer_stack）
  - 不能注入函数/类定义
```

---

## 4. 基础语法

### 4.1 变量声明

#### 有类型注解

```python
# Cypy 语法
x: int = 10
y: float = 3.14
name: str = "Cypy"

# 转译为 Cython
cdef int x = 10
cdef float y = 3.14
cdef str name = "Cypy"
```

#### 无类型注解（退化）

```python
# Cypy 语法
x = 10
y = 3.14
name = "Cypy"

# 转译为 Cython（保持不变）
x = 10
y = 3.14
name = "Cypy"
```

### 4.2 指针变量声明

```python
# Cypy 语法
ptr: int* = malloc(sizeof(int))
buf: double* = malloc(sizeof(double) * 10)

# 转译为 Cython
from libc.stdlib cimport malloc, sizeof

cdef int* ptr = <int*>malloc(sizeof(int))
cdef double* buf = <double*>malloc(sizeof(double) * 10)
```

### 4.3 函数定义

#### 有类型注解

```python
# Cypy 语法
def add(a: int, b: int) -> int:
    return a + b

# 转译为 Cython
cpdef int add(int a, int b):
    return a + b
```

#### 无类型注解

```python
# Cypy 语法
def add(a, b):
    return a + b

# 转译为 Cython（保持不变）
def add(a, b):
    return a + b
```

### 4.4 类定义

沿用 Python 体系，支持继承、方法、属性：

```python
# Cypy 语法（与 Python 完全一致）
class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
    
    def distance(self, other) -> float:
        return ((self.x - other.x)**2 + (self.y - other.y)**2)**0.5
```

---

## 5. 新语法构造

> **规则**：`impl`, `struct`, `trait`, `enum`, `macro`, `meta` 只能写在模块顶级（层级 0），且不能嵌套。

### 5.1 `struct` — 结构体

用于定义 C 风格的数据结构，生成高效的内存布局。

#### 语法

```python
struct Point:
    x: double
    y: double
    z: double = 0.0  # 可选默认值
```

#### 转译目标

```cython
# Cython 转译结果
cdef struct Point:
    double x
    double y
    double z = 0.0
```

#### 使用方式

```python
# 创建结构体实例（栈上）
p: Point = Point()
p.x = 1.0
p.y = 2.0

# 创建结构体指针（堆上）
ptr: Point* = malloc(sizeof(Point))
defer free(ptr)
ptr.x = 1.0  # 自动解引用
ptr.y = 2.0
```

### 5.2 `enum` — 枚举

用于定义命名常量集合。

#### 语法

```python
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3
```

#### 转译目标

```cython
# Cython 转译结果
cdef enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3
```

#### 使用方式

```python
def get_color_name(c: Color) -> str:
    if c == Color.RED:
        return "红色"
    elif c == Color.GREEN:
        return "绿色"
    elif c == Color.BLUE:
        return "蓝色"
```

### 5.3 `trait` — 特质（接口）

用于定义行为契约，类似于 Go 的接口或 Rust 的 trait。

#### 语法

```python
trait Drawable:
    def draw(self) -> None:
        ...
    
    def resize(self, width: int, height: int) -> None:
        ...
```

#### 转译目标

```cython
# Cython 转译结果
cdef class Drawable:
    cpdef void draw(self):
        pass
    
    cpdef void resize(self, int width, int height):
        pass
```

### 5.4 `impl` — 实现

用于为类型实现 trait。

#### 语法

```python
impl Drawable for Circle:
    def draw(self) -> None:
        print(f"Drawing circle at ({self.x}, {self.y})")
    
    def resize(self, width: int, height: int) -> None:
        self.radius = min(width, height) / 2
```

#### 转译策略（AST 合并）

> **关键设计**：`impl` 方法不会通过运行时 monkey-patching 绑定到类，而是在 AST 阶段直接合并到目标类的方法列表中。

**转译流程**：

```
1. 解析阶段：收集所有 `impl Trait for Class` 定义
2. AST 合并阶段：将 impl 中的方法注入到目标类的 body 中
3. 代码生成阶段：生成完整的类定义（包含注入的方法）
```

#### 转译目标

```cython
# Cython 转译结果（AST 合并后）
# Circle 类已包含 Drawable trait 的实现
cdef class Circle:
    cdef Point center
    cdef double radius
    
    def __init__(self, Point center, double radius):
        self.center = center
        self.radius = radius
    
    cpdef void draw(self):
        print(f"Drawing circle at ({self.center.x}, {self.center.y})")
    
    cpdef void resize(self, int width, int height):
        self.radius = min(width, height) / 2
```

#### 实现约束

| 约束 | 说明 |
|------|------|
| **必须为 `cdef class`** | 实现 trait 的类必须是 `cdef class`，以便支持 `cpdef` 方法 |
| **方法签名必须匹配** | `impl` 中的方法签名必须与 trait 定义完全匹配 |
| **不能重复实现** | 同一类对同一 trait 只能实现一次 |

### 5.5 `macro` — 宏系统

用于编译期代码生成，参考 lang-zone 设计。

#### 语法

```python
# 宏定义
macro twice(input: Tokens) -> Tokens =
    f```
        $input + $input
    ```

# 宏调用
result = @twice!(x)
```

#### 反引号代码块

反引号代码块支持三种前缀：

| 前缀 | 说明 | 示例 |
|------|------|------|
| 无前缀 | 普通形式，不插值 | ```code``` |
| `f` | 插值形式，支持 `$()` 和 `$name` | f```$x + 1``` |
| `r` | 原始形式，不插值、不展开宏 | r```literal``` |

#### 宏插值语法

| 语法 | 说明 | 示例 |
|------|------|------|
| `$name` | 简单参数替换 | `$x` → `5` |
| `$(expr)` | 表达式形式，保持括号 | `$(x + y)` → `(x + y)` |
| `$$` | 转义为单个 `$` | `$$100` → `$100` |

#### 宏调用语法

| 语法 | 说明 | 示例 |
|------|------|------|
| `@name!` | 无参数宏调用 | `@log!` |
| `@name!(args...)` | 带参数宏调用 | `@add!(1, 2)` |

#### 完整示例

```python
# 定义日志宏
macro log(expr: Tokens) -> Tokens =
    f```
        print("value: ", $(expr))
        return $expr
    ```

# 定义结构体生成宏
macro create_struct(name: Tokens) -> Tokens =
    f```
        struct $name:
            x: int
            y: int
    ```

# 使用宏
def test():
    @log!(x + y)
    @create_struct!(Point)
    return 0
```

#### 转译策略

宏在编译期展开，操作 Token 流。`cypyc` 转译器在解析阶段处理宏调用，将其替换为展开后的代码。

### 5.6 `comptime` — 编译期求值

用于在编译时执行表达式并将结果替换为常量。

#### 语法

```python
# 单行形式：编译期计算表达式
result: int = comptime: 2 + 3 * 4

# 块形式：编译期执行代码块
comptime:
    x = 10
    y = 20
    result = x + y

# 作为表达式使用
value: int = comptime: calculate_constant()
```

#### 转译策略

`comptime` 代码在 `cypyc` 转译时执行，结果作为常量值嵌入生成的代码中。

```python
# Cypy 源码
PI: double = comptime: 3.1415926535

# 转译结果（Cython）
PI = 3.1415926535
```

#### 注意事项

| 注意事项 | 说明 |
|----------|------|
| **编译期执行** | `comptime` 代码在编译时执行，无法访问运行时变量 |
| **无副作用** | 避免在 `comptime` 中执行有副作用的操作 |
| **常量结果** | 求值结果必须是常量，可嵌入代码 |

### 5.7 构建块（Build Blocks）

用于创建闭包无参函数，内部默认 unsafe，允许指针语法。

#### 语法

| 符号 | 名称 | 说明 |
|------|------|------|
| `=:` | 变量构建块 | 自动将最后表达式作为返回值赋值给左侧变量 |
| `~:` | 调用构建块 | 返回元组、命名元组、字典或实现 `BuildParams` trait 的对象 |
| `*:` | 生成器构建块 | 返回迭代器，`yield` 产生参数包 |

#### 变量构建块 `=:`

```python
result: int =:
    x = 10
    y = 20
    x + y  # 最后表达式作为返回值

# 转译结果
result = (lambda: (10, 20, 10 + 20)[-1])()
```

#### 调用构建块 `~:`

```python
def create_object():
    pass

# 使用调用构建块传递参数
create_object ~:
    param1 = value1
    param2 = value2
```

#### 生成器构建块 `*:`

```python
def process_items():
    pass

# 使用生成器构建块产生多个参数包
process_items *:
    yield (1, "first")
    yield (2, "second")
    yield {"key": "value"}
```

#### 构建值操作符 `^`

```python
# 使用 ^ 获取构建值
builder ~:
    value = 42
    
result = ^builder  # 获取构建块的返回值
```

### 5.8 Lambda 表达式

用于创建匿名函数。

#### 语法

```python
# 简单 lambda
add = lambda x, y: x + y

# 带类型注解的 lambda
multiply = lambda x: int, y: int: x * y

# 作为参数传递
result = map(lambda x: x * 2, [1, 2, 3])

# 嵌套 lambda
outer = lambda x: lambda y: x + y
```

#### 转译目标

```cython
# Cypy lambda
add = lambda x, y: x + y

# 转译结果（Cython）
add = lambda x, y: x + y
```

### 5.9 参数检查站（Parameter Checkpoint）

用于在函数定义或调用时指定参数验证函数。

#### 语法

```python
# 函数定义时指定 checker
def validate_params():
    print("params validated")

def <validate_params> process_data(a, b):
    print("processing")

# 调用时指定 checker
def custom_checker():
    print("custom check passed")

result = compute<custom_checker>(3, 4)

# 混合使用：checker + 泛型
def <log_params> transform[T](value: T) -> T:
    return value

result = transform<log_params>[str]("hello")
```

#### 语法规则

```
def <checker>? name [generic]? (params)
```

| 位置 | 语法 | 说明 |
|------|------|------|
| 函数名前 | `<checker>` | 参数检查站，可选 |
| 函数名后 | `[T]` | 泛型参数，可选 |

#### 转译策略

```python
# Cypy 源码
def <validate_params> process_data(a, b):
    pass

# 转译结果（Cython）
cpdef process_data(a, b):
    validate_params()  # 在函数体开头自动调用
    pass

# 调用时指定 checker
result = compute<custom_checker>(3, 4)

# 转译结果
result = (custom_checker(), compute(3, 4))[1]
```

### 5.10 SIMD 向量类型（vec）

用于 SIMD 并行计算。

#### 语法

```python
# 向量类型定义
v: vec[int; 4]  # 4个int的向量

# 向量字面量
v1 = vec![1, 2, 3, 4]      # 元素列表形式
v2 = vec![0; 4]            # 重复形式（4个0）
v3 = vec![1.0, 2.0, 3.0, 4.0]  # 浮点向量

# 向量操作
result = v1 + v2  # 逐元素加法
result = v1 * v2  # 逐元素乘法
```

#### 向量类型语法

```
vec[ElementType; Size]
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `ElementType` | 元素类型 | `int`, `float`, `double` |
| `Size` | 向量大小（必须是编译期常量） | `4`, `8`, `16` |

### 5.11 并发与协程

#### `spawn` — 并发任务

用于在后台执行异步任务。

```python
def background_task():
    # 后台执行的任务
    pass

# 作为语句使用
spawn background_task()

# 作为表达式使用（获取任务句柄）
task = spawn background_task()

# 块形式
spawn:
    # 任务体
    process_data()
```

#### `go` — 轻量级协程

用于创建并启动协程。

```python
def coroutine_func():
    # 协程代码
    pass

# 作为语句使用
go coroutine_func()

# 作为表达式使用
task = go coroutine_func()

# 块形式
go:
    # 协程体
    for i in range(10):
        process(i)
```

### 5.12 模式匹配（match/case）

用于模式匹配和分支处理。

#### 语法

```python
match value:
    case 0:
        print("zero")
    case 1 | 2:
        print("one or two")
    case x if x > 10:
        print(f"large: {x}")
    case _:
        print("other")
```

#### 支持的模式

| 模式类型 | 说明 | 示例 |
|----------|------|------|
| 常量模式 | 匹配字面量值 | `case 0`, `case "hello"` |
| 变量模式 | 绑定匹配值到变量 | `case x` |
| OR 模式 | 匹配多个模式 | `case 1 \| 2 \| 3` |
| 列表模式 | 匹配列表结构 | `case [a, b, c]` |
| 元组模式 | 匹配元组结构 | `case (a, b)` |
| 条件模式 | 添加额外条件 | `case x if x > 0` |
| 通配符模式 | 匹配任何值 | `case _` |

#### 完整示例

```python
def process_result(result):
    match result:
        case {"status": "success", "data": data}:
            print(f"Got data: {data}")
        case {"status": "error", "message": msg}:
            print(f"Error: {msg}")
        case None:
            print("No result")
        case _:
            print("Unknown result type")
```

---

## 6. 语法糖

### 6.1 管道操作符 `|>`

用于函数链式调用，从左到右依次应用。

#### 语法

```python
# Cypy 语法
result = data |> process |> filter |> transform |> str

# 等价于 Python
result = str(transform(filter(process(data))))
```

#### 转译规则

```python
# 含赋值
y = x |> double |> add_one |> str
# 转译为
y = str(add_one(double(x)))

# 不含赋值
x |> double |> add_one |> print
# 转译为
print(add_one(double(x)))
```

### 6.2 `owend` — 所有权声明

用于声明拥有所有权的变量，支持资源管理和转移语义。

#### 语法

```python
# Cypy 语法
owend x: int = 10

# 转译为 Python
x = Owned(10)
```

#### 转译目标

```python
# 自动注入 Owned 类定义
import weakref

class Owned:
    __slots__ = ('_value', '_refs')
    def __init__(self, value):
        self._value = value
        self._refs = weakref.WeakSet()
    
    def get(self):
        return self._value
    
    def transfer(self):
        old = self._value
        self._value = None
        return Owned(old)
    
    # 支持算术运算
    def __add__(self, other):
        return self._value + other
    # ... 其他运算符
```

### 6.3 `let` — 块级绑定

用于在控制流结构中进行变量绑定（用户偏好）。

#### 语法

```python
# Cypy 语法
if let x = compute_value():
    print(x)

while let line = read_line():
    process(line)
```

#### 转译目标（安全作用域）

> **关键设计**：使用临时变量模式，避免绑定变量泄漏到外部作用域。

```python
# Cython 转译结果（if let）
_tmp = compute_value()
if _tmp is not None:
    x = _tmp
    print(x)

# Cython 转译结果（while let）
while True:
    _tmp = read_line()
    if _tmp is None:
        break
    line = _tmp
    process(line)
```

#### 作用域规则

| 规则 | 说明 |
|------|------|
| **绑定变量作用域** | `let` 绑定的变量仅在条件块内部可见 |
| **None 检查** | 自动添加 `is not None` 检查 |
| **循环更新** | `while let` 在每次迭代开始时重新求值 |

### 6.4 `val` — 不可变变量

用于声明不可重新赋值的变量。

#### 语法

```python
# Cypy 语法
val PI: double = 3.14159
val name: str = "Cypy"

# 转译为 Python（通过 lint 检查）
PI = 3.14159
name = "Cypy"
```

> **注意**：`val` 的不可变性由 `cypyc` 编译器在编译时检查，运行时不强制。

### 6.5 `defer` — 延迟清理

用于延迟执行清理操作（类似 Go 的 defer），确保资源在函数退出时被正确释放。

#### 语法

```python
# Cypy 语法
def process_data(size: int) -> int:
    # 分配内存
    buffer: int* = malloc(sizeof(int) * size)
    defer free(buffer)  # ← 函数退出时自动执行
    
    # 使用 buffer
    buffer[0] = 42
    
    # 即使提前返回，defer 也会执行
    if size == 0:
        return 0
    
    return buffer[0]
```

### 6.6 `guard` — 守卫表达式

用于提前终止函数并隐式返回，避免嵌套条件判断。

#### 语法

```python
# 单行形式：guard cond else expr（无冒号，隐式返回）
def process(x: int) -> int:
    guard x != 0 else 0
    return x

# 多行形式：guard cond else: 换行块体（有冒号）
def process(x: int) -> int:
    guard x != 0 else:
        print("error: x is zero")
        0  # 隐式返回
    return x

# guard let 绑定形式
def process_optional() -> int:
    guard let value = get_value() else 0
    return value
```

#### 转译策略

```python
# Cypy 源码
def process(x: int) -> int:
    guard x != 0 else 0
    return x

# 转译结果（Cython）
cpdef int process(int x):
    if not (x != 0):
        return 0
    return x

# guard let 形式
def process_optional() -> int:
    guard let value = get_value() else 0
    return value

# 转译结果
def process_optional():
    value = get_value()
    if not value:
        return 0
    return value
```

#### 注意事项

| 注意事项 | 说明 |
|----------|------|
| **只能在函数内部使用** | `guard` 必须在函数作用域内 |
| **隐式返回** | else 分支的值会被隐式返回，不需要 `return` 关键字 |
| **无副作用** | else 分支应该是纯表达式或简单语句 |

### 6.7 列表推导式

支持条件过滤的列表生成语法。

#### 语法

```python
# 简单列表推导式
squares = [x * x for x in range(10)]

# 带条件的列表推导式
even_squares = [x * x for x in range(10) if x % 2 == 0]

# 嵌套列表推导式
matrix = [[i * j for j in range(3)] for i in range(3)]

# 多重条件
filtered = [x for x in numbers if x > 0 and x < 100]
```

#### 转译目标

```cython
# Cypy 列表推导式
squares = [x * x for x in range(10)]

# 转译结果（Cython）
squares = [x * x for x in range(10)]
```

### 6.8 联合类型

使用 `|` 操作符定义联合类型。

#### 语法

```python
# 类型别名形式
type Number = int | float | double

# 函数参数形式
def process(value: int | str) -> None:
    pass

# 变量声明形式
result: int | None = None

# 复杂联合类型
type Result = Success[str] | Error[int]
```

#### 转译策略

```python
# Cypy 联合类型
type Number = int | float | double

# 转译结果（类型擦除）
Number = object  # 运行时退化为 PyObject
```

### 6.9 异常处理

完整支持 Python 异常处理语法。

#### 语法

```python
# 基本 try/except
try:
    risky_operation()
except ValueError as e:
    print(f"Value error: {e}")
except Exception as e:
    print(f"Generic error: {e}")

# try/except/finally
try:
    file = open("data.txt")
    data = file.read()
except IOError as e:
    print(f"IO error: {e}")
finally:
    file.close()

# try/except/else
try:
    result = compute()
except ValueError:
    result = 0
else:
    print(f"Success: {result}")

# raise 语句
raise ValueError("Invalid argument")
raise ValueError("Invalid") from original_exception
```

### 6.10 上下文管理器

支持 `with` 语句和上下文管理器协议。

#### 语法

```python
# 单个上下文
with open("file.txt") as f:
    content = f.read()

# 多个上下文
with open("input.txt") as infile, open("output.txt", "w") as outfile:
    data = infile.read()
    outfile.write(data)

# 自定义上下文管理器
class ResourceManager:
    def __enter__(self):
        # 获取资源
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 释放资源
        pass

with ResourceManager() as resource:
    use(resource)
```

#### 高级 defer 特性（可选）

**带条件的 defer**：

```python
def process_file(filename: str):
    file_handle = open(filename)
    defer file_handle.close()  # 始终执行
    
    if not file_handle.readable():
        return  # defer 仍会执行，文件被正确关闭
```

**多个 defer 语句**：

```python
def complex_operation():
    resource1: Resource* = allocate_resource()
    defer release_resource(resource1)
    
    resource2: Resource* = allocate_resource()
    defer release_resource(resource2)
    
    resource3: Resource* = allocate_resource()
    defer release_resource(resource3)
    
    # 执行顺序（退出时）：
    # 1. release_resource(resource3)
    # 2. release_resource(resource2)
    # 3. release_resource(resource1)
```

**defer 与 return 的交互**：

```python
def safe_compute():
    buffer: int* = malloc(sizeof(int) * 100)
    defer free(buffer)
    
    if check_condition():
        return 0  # defer 执行，buffer 被释放
    
    &buffer = 42
    return &buffer  # defer 执行，buffer 被释放
```

**defer 与异常的交互**：

```python
def safe_operation():
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)
    
    try:
        risky_operation()
    except Exception as e:
        print(f"Error: {e}")
        raise  # defer 仍会执行，ptr 被释放
```

#### defer 编译优化

> **编译器优化**：对于简单的 `defer free(ptr)` 模式，编译器可以进行以下优化：

```python
# 原始代码
ptr: int* = malloc(sizeof(int))
defer free(ptr)

# 优化后的转译（无 try/finally 开销）
ptr: int* = malloc(sizeof(int))
# ... 使用 ptr ...
free(ptr)  # 在作用域结束时直接插入
```

**优化条件**：

| 条件 | 是否优化 | 说明 |
|------|----------|------|
| 作用域内无 return | ✅ 优化 | 直接在作用域末尾插入 free |
| 作用域内无异常抛出 | ✅ 优化 | 不需要 try/finally |
| defer 语句在作用域开头 | ✅ 优化 | 更容易分析控制流 |
| 存在条件分支 | ❌ 不优化 | 需要 try/finally 保证安全 |

---

## 7. 编译与工具链

### 7.1 `cypyc` 转译器

#### 命令行接口

```bash
# 转译单个文件
cypyc input.cypy

# 转译并编译
cypyc --compile input.cypy

# 类型检查（仅检查，不生成代码）
cypyc --check input.cypy

# 输出详细信息
cypyc --verbose input.cypy

# 检查内存泄漏（指针未清理检测）
cypyc --check-memory input.cypy
```

#### 转译流程

```
1. 词法分析（Tokenization）
   └── 将源码分解为 token 流

2. 语法分析（Parsing）
   └── 构建 AST（使用 Python ast + 自定义扩展）

3. 作用域分析（Scope Analysis）
   └── 计算每个节点的缩进层级和作用域
   └── 收集 defer 语句到 defer_stack

4. 类型检查（Type Checking）
   └── 验证类型注解的一致性
   └── 检查指针类型显式声明
   └── 检查指针变量是否有对应的 defer 清理

5. 代码生成（Code Generation）
   └── 将 AST 转换为 Cython 代码
   └── 应用 defer try/finally 包装

6. Cython 编译
   └── cythonize → C 代码 → 二进制扩展
```

### 7.2 集成开发流程

```bash
# 开发阶段：使用 import hook 实时转译
python -m cypy_hook my_script.py

# 发布阶段：编译为二进制
cypyc --compile my_module.cypy

# 内存检查（推荐）
cypyc --check-memory my_module.cypy
```

---

## 8. 兼容性与降级规则

### 8.1 Python 兼容性

| 特性 | 支持情况 |
|------|----------|
| 所有 Python 语法 | ✅ 完全支持 |
| Python 标准库 | ✅ 完全支持 |
| 第三方 Python 库 | ✅ 完全支持 |
| Python 装饰器 | ✅ 支持 |
| Python 上下文管理器 | ✅ 支持 |
| Python 异步语法 (`async/await`) | ✅ 支持（Cython 0.29+） |

### 8.2 降级规则

```
规则 1: 无类型注解的变量 → PyObject（与 Python 行为一致）

规则 2: 无类型注解的函数参数 → PyObject

规则 3: 纯 Python 代码文件 (.py) → 直接导入，不转译

规则 4: 混合代码 → 有注解的部分使用静态类型，其余退化

规则 5: 不支持的语法构造 → 保持原样传递给 Python 解释器

规则 6: 指针类型必须显式注解 → 无注解的指针声明会报错
```

### 8.3 迁移策略

```python
# 第一步：直接将 .py 重命名为 .cypy
# 所有代码保持不变，自动降级为 Python 行为

# 第二步：逐步添加类型注解
def add(a: int, b: int) -> int:
    return a + b

# 第三步：使用新语法构造
struct Point:
    x: int
    y: int

# 第四步：使用指针和 defer 进行性能优化
# 注意：返回指针时不能使用 defer，调用者负责清理
def allocate_buffer(size: int) -> int*:
    buf: int* = malloc(sizeof(int) * size)
    return buf  # 调用者负责使用 defer free(buf) 清理

# 使用示例（正确的 defer 用法）
def process_data():
    buf: int* = allocate_buffer(100)
    defer free(buf)
    # 使用 buf...

# 第五步：使用语法糖提高可读性
result = data |> process |> filter |> str
```

---

## 9. 代码示例

### 9.1 完整示例（含泛型、指针、defer 和 meta）

```python
# example.cypy

from libc.stdlib cimport malloc, free, sizeof
from libc.string cimport memset

# ===== 模块顶级定义（层级 0）=====

# 泛型结构体
struct Pair[T, U]:
    first: T
    second: U

struct Option[T]:
    has_value: bool
    value: T

struct Result[T, E]:
    is_ok: bool
    ok_value: T
    err_value: E

# 普通结构体
struct Point:
    x: double
    y: double

# 枚举
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

# 泛型 trait
trait Collection[T]:
    def add(self, item: T) -> None:
        ...
    
    def get(self, index: int) -> T:
        ...
    
    def size(self) -> int:
        ...

trait Drawable:
    def draw(self) -> None:
        ...
    
    def resize(self, width: int, height: int) -> None:
        ...

# cdef class 用于持有 struct 字段
class Circle:
    def __init__(self, center: Point, radius: double):
        self._center = center
        self._radius = radius
    
    @property
    def center(self) -> Point:
        return self._center
    
    @property
    def radius(self) -> double:
        return self._radius

# 实现 trait（层级 0）
impl Drawable for Circle:
    def draw(self) -> None:
        print(f"Drawing circle at ({self.center.x}, {self.center.y})")
    
    def resize(self, width: int, height: int) -> None:
        self._radius = min(width, height) / 2

# ===== 泛型函数 =====

def identity[T](value: T) -> T:
    return value

def make_pair[T, U](first: T, second: U) -> Pair[T, U]:
    return Pair[T, U](first, second)

def find_user(id: int) -> Option[str]:
    if id == 1:
        return Option[str](has_value=True, value="Alice")
    return Option[str](has_value=False, value="")

def divide(a: float, b: float) -> Result[float, str]:
    if b == 0:
        return Result[float, str](is_ok=False, ok_value=0.0, err_value="Division by zero")
    return Result[float, str](is_ok=True, ok_value=a / b, err_value="")

# ===== 指针与 defer =====

# 正确的指针返回示例（调用者负责清理）
def allocate_points(count: int) -> Point*:
    arr: Point* = malloc(sizeof(Point) * count)
    return arr

# 使用泛型和指针（调用者负责清理）
def create_pairs[T, U](count: int) -> Pair[T, U]*:
    arr: Pair[T, U]* = malloc(sizeof(Pair[T, U]) * count)
    
    for i in range(count):
        arr[i].first = identity(1)
        arr[i].second = identity("hello")
    
    return arr  # 调用者负责使用 defer free(arr) 清理

# ===== meta 类型系统 =====

# 定义类型（值层）
struct Dog:
    name: str

struct Cat:
    name: str

# 定义 meta 规则（meta 层）- 仅在 cypyc 转译时有效
meta:
    # 抽象类型和子类型关系
    abstract Animal
    subtype Dog <: Animal
    subtype Cat <: Animal
    
    # 类型约束
    constraint Number = int | float | double
    
    # 多重分派规则
    dispatch meet(a: Dog, b: Dog) -> str
    dispatch meet(a: Dog, b: Cat) -> str
    dispatch meet(a: Cat, b: Dog) -> str
    dispatch meet(a: Cat, b: Cat) -> str
    dispatch meet(a: Animal, b: Animal) -> str  # 兜底
    
    # 泛型分派
    dispatch compute[T: Number](value: T) -> T

# 分派实现
def meet(a: Dog, b: Dog) -> str:
    return f"{a.name} and {b.name} play together"

def meet(a: Dog, b: Cat) -> str:
    return f"{a.name} chases {b.name}"

def meet(a: Cat, b: Dog) -> str:
    return f"{a.name} hisses at {b.name}"

def meet(a: Cat, b: Cat) -> str:
    return f"{a.name} and {b.name} ignore each other"

def meet(a: Animal, b: Animal) -> str:
    return f"Animals meet"

# 泛型分派实现
def compute[T: Number](value: T) -> T:
    return value * 2

# ===== 管道操作符 =====

val PI: double = 3.14159

def compute_area(radius: double) -> double:
    return PI * radius * radius

# ===== let 语法 =====

def process_file(filename: str):
    if let content = read_file(filename):
        lines = content |> str.split |> len
        print(f"File has {lines} lines")

# ===== 主程序 =====

def main():
    # 使用泛型
    p = make_pair(1, "hello")  # Pair[int, str]
    print(f"Pair: ({p.first}, {p.second})")
    
    # 使用 Option
    user = find_user(1)
    if user.has_value:
        print(f"Found user: {user.value}")
    
    # 使用 Result
    result = divide(10.0, 2.0)
    if result.is_ok:
        print(f"Division result: {result.ok_value}")
    
    # 使用指针和 defer
    points: Point* = allocate_points(5)
    defer free(points)
    
    for i in range(5):
        points[i].x = i * 10.0
        points[i].y = i * 20.0
        print(f"Point {i}: ({points[i].x}, {points[i].y})")
    
    # 使用多重分派（meta 指导的分派）
    dog1 = Dog(name="Buddy")
    dog2 = Dog(name="Max")
    cat1 = Cat(name="Mittens")
    
    print(meet(dog1, dog2))  # "Buddy and Max play together"
    print(meet(dog1, cat1))  # "Buddy chases Mittens"
    print(meet(cat1, dog1))  # "Mittens hisses at Buddy"
    print(meet(cat1, cat1))  # "Mittens and Mittens ignore each other"
    
    # 使用泛型分派
    print(compute(5))    # 10 (int)
    print(compute(3.14)) # 6.28 (float)
    
    # 使用 Circle
    center: Point = Point()
    center.x = 10.0
    center.y = 20.0
    circle = Circle(center, 5.0)
    
    area = circle.radius |> compute_area |> round
    print(f"Area: {area}")
    
    circle.draw()
    circle.resize(20, 30)
    print(f"Resized radius: {circle.radius}")

if __name__ == "__main__":
    main()
```

### 9.2 转译后的 Cython 代码

```cython
# example.pyx（转译结果，AST 合并后 + defer 处理）

from libc.stdlib cimport malloc, free, sizeof
from libc.string cimport memset

cdef enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

cdef struct Point:
    double x
    double y

cdef class Drawable:
    cpdef void draw(self):
        pass
    
    cpdef void resize(self, int width, int height):
        pass

# Circle 类包含 impl 注入的方法
cdef class Circle:
    cdef Point _center
    cdef double _radius
    
    def __init__(self, Point center, double radius):
        self._center = center
        self._radius = radius
    
    @property
    def center(self):
        return self._center
    
    @property
    def radius(self):
        return self._radius
    
    # impl Drawable for Circle 注入的方法
    cpdef void draw(self):
        print(f"Drawing circle at ({self._center.x}, {self._center.y})")
    
    cpdef void resize(self, int width, int height):
        self._radius = min(width, height) / 2

cpdef Point* create_point_array(int count):
    cdef Point* arr = <Point*>malloc(sizeof(Point) * count)
    
    try:
        cdef int i
        for i in range(count):
            arr[i].x = i * 1.0
            arr[i].y = i * 2.0
        
        return arr
    finally:
        free(arr)  # ❌ 这里有问题！返回后会被释放

cpdef Point* allocate_points(int count):
    cdef Point* arr = <Point*>malloc(sizeof(Point) * count)
    return arr

PI = 3.14159

cpdef double compute_area(double radius):
    return PI * radius * radius

def process_file(str filename):
    _tmp = read_file(filename)
    if _tmp is not None:
        content = _tmp
        lines = len(content.split())
        print(f"File has {lines} lines")

def main():
    cdef Point* points = allocate_points(5)
    
    try:
        cdef int i
        for i in range(5):
            points[i].x = i * 10.0
            points[i].y = i * 20.0
            print(f"Point {i}: ({points[i].x}, {points[i].y})")
        
        cdef Point center
        center.x = 10.0
        center.y = 20.0
        circle = Circle(center, 5.0)
        
        area = round(compute_area(circle.radius))
        print(f"Area: {area}")
        
        circle.draw()
        circle.resize(20, 30)
        print(f"Resized radius: {circle.radius}")
    finally:
        free(points)

if __name__ == "__main__":
    main()
```

---

## 10. 实现说明

### 10.1 解析器架构

Cypy 使用两阶段解析策略：

```
┌─────────────────────────────────────────────────────────┐
│                    Cypy 源码 (.cypy)                   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  阶段一：预处理（Preprocessor）                          │
│  - 将 cypy 关键字替换为 Python 可解析的标记               │
│  - 例如：struct → __cypy_struct__, defer → __cypy_defer__│
│  - 处理缩进层级，标记每个节点的 scope_level              │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  阶段二：AST 解析（AST Parser）                          │
│  - 使用 Python ast 模块解析预处理后的代码                 │
│  - 自定义 AST 节点类型处理 cypy 特有构造                 │
│  - 构建完整的作用域树（Scope Tree）                      │
│  - 收集 defer 语句到每个作用域的 defer_stack              │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  阶段三：语义分析（Semantic Analysis）                   │
│  - 类型检查（Type Checking）                            │
│  - 作用域解析（Scope Resolution）                       │
│  - impl 方法合并（Trait Implementation Merge）          │
│  - 指针清理检查（Pointer Cleanup Check）                │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  阶段四：代码生成（Code Generation）                     │
│  - 将 Cypy AST 转换为 Cython 代码                       │
│  - 应用类型映射规则                                     │
│  - 应用 defer try/finally 包装                          │
│  - 生成 setup.py 构建脚本                               │
└─────────────────────────────────────────────────────────┘
```

### 10.2 从 Regex 到 AST 的迁移路径

当前 `cypy_hook.py` 使用简单的 regex 替换，仅支持 `owend` 和 `|>` 语法糖。迁移到完整 AST 解析器需要以下步骤：

| 步骤 | 内容 | 优先级 |
|------|------|--------|
| **Step 1** | 实现预处理阶段，将 cypy 关键字替换为占位符 | 高 |
| **Step 2** | 扩展 Python ast 模块，支持自定义节点类型 | 高 |
| **Step 3** | 实现作用域分析器，计算缩进层级 | 高 |
| **Step 4** | 实现 defer 语句收集和 try/finally 包装 | 高 |
| **Step 5** | 实现类型检查器，验证类型注解 | 中 |
| **Step 6** | 实现指针清理检查 | 中 |
| **Step 7** | 实现 impl AST 合并逻辑 | 中 |
| **Step 8** | 实现代码生成器，输出 Cython 代码 | 中 |
| **Step 9** | 集成 Cython 编译器，自动编译 | 低 |

### 10.3 struct、指针与 class 的交互规则

> **关键约束 1**：任何持有 `struct` 类型字段的类必须声明为 `cdef class`。

```python
# 正确：使用 cdef class
cdef class Circle:
    cdef Point center  # struct 字段
    cdef double radius
    
    def __init__(self, Point center, double radius):
        self.center = center
        self.radius = radius

# 错误：普通 class 不能持有 struct 字段
class Circle:
    def __init__(self, Point center, double radius):
        self.center = center  # ❌ 编译错误
```

> **关键约束 2**：指针类型只能是局部变量或 `cdef class` 的 `cdef` 字段，不能是普通 Python class 的属性。

```python
# 正确：局部指针变量
def func():
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)

# 正确：cdef class 的 cdef 字段
cdef class Buffer:
    cdef int* data
    
    def __init__(self, int size):
        self.data = <int*>malloc(sizeof(int) * size)
    
    def __dealloc__(self):
        if self.data != NULL:
            free(self.data)

# 错误：普通 class 的属性
class MyClass:
    def __init__(self):
        self.ptr = malloc(sizeof(int))  # ❌ 编译错误
```

### 10.4 缩进层级检测算法

```python
# 伪代码：缩进层级检测
def detect_indent_levels(source: str) -> List[int]:
    lines = source.split('\n')
    levels = []
    for line in lines:
        leading_whitespace = len(line) - len(line.lstrip())
        # 假设使用 4 空格缩进
        level = leading_whitespace // 4
        levels.append(level)
    return levels

# 示例
source = """
def foo():
    if True:
        return 1
"""
# levels = [0, 0, 1, 2]
```

### 10.5 作用域树构建

```python
# 伪代码：作用域树节点
class ScopeNode:
    def __init__(self, level: int, block_type: str):
        self.level = level
        self.block_type = block_type
        self.variables = {}  # 变量名 → 类型
        self.defer_stack = []  # defer 语句列表（LIFO）
        self.children = []   # 子作用域
    
    def add_variable(self, name: str, var_type: Type):
        self.variables[name] = var_type
    
    def add_defer(self, ast_node):
        self.defer_stack.append(ast_node)

# 构建过程
def build_scope_tree(levels: List[int], ast_nodes: List[AST]) -> ScopeNode:
    root = ScopeNode(0, "module")
    stack = [root]
    
    for level, node in zip(levels, ast_nodes):
        # 弹出栈直到找到父作用域
        while stack[-1].level >= level:
            stack.pop()
        
        parent = stack[-1]
        new_scope = ScopeNode(level, get_block_type(node))
        
        # 如果是 defer 语句，添加到当前作用域的 defer_stack
        if is_defer_node(node):
            parent.add_defer(node)
        
        parent.children.append(new_scope)
        stack.append(new_scope)
    
    return root
```

### 10.6 defer 转译算法

```python
# 伪代码：defer try/finally 包装
def wrap_with_defer(scope: ScopeNode, body: AST) -> AST:
    if not scope.defer_stack:
        return body
    
    # 构建 finally 块：按 LIFO 顺序执行 defer 语句
    finally_body = []
    for defer_node in reversed(scope.defer_stack):
        finally_body.append(defer_node.expr)
    
    # 包装 try/finally
    return Try(
        body=body,
        handlers=[],
        orelse=[],
        finalbody=finally_body
    )

# 递归处理嵌套作用域
def process_defer(scope: ScopeNode):
    # 处理子作用域
    for child in scope.children:
        process_defer(child)
    
    # 包装当前作用域的 body
    scope.body = wrap_with_defer(scope, scope.body)
```

### 10.7 指针清理检查算法

```python
# 伪代码：检查指针变量是否有对应的 defer 清理
def check_pointer_cleanup(scope: ScopeNode):
    for var_name, var_type in scope.variables.items():
        if is_pointer_type(var_type):
            # 检查是否有对应的 defer free(var_name)
            has_defer = any(
                is_free_call(d.expr, var_name)
                for d in scope.defer_stack
            )
            
            if not has_defer:
                # 检查是否返回了指针（所有权转移）
                if not is_returned(scope, var_name):
                    # 检查是否传递给了其他函数（所有权转移）
                    if not is_transferred(scope, var_name):
                        # 报告警告：指针可能泄漏
                        warn(f"Pointer '{var_name}' may leak: no defer free()")
    
    # 递归检查子作用域
    for child in scope.children:
        check_pointer_cleanup(child)
```

---

## 附录：关键字列表

| 关键字 | 分类 | 说明 |
|--------|------|------|
| `struct` | 新构造 | 定义结构体 |
| `enum` | 新构造 | 定义枚举 |
| `trait` | 新构造 | 定义特质/接口 |
| `impl` | 新构造 | 实现特质 |
| `meta` | 新构造 | meta 块（编译期类型约束和分派） |
| `constraint` | meta 关键字 | 定义类型约束（仅在 meta 块内有效） |
| `abstract` | meta 关键字 | 定义抽象类型（仅在 meta 块内有效） |
| `subtype` | meta 关键字 | 定义子类型关系（仅在 meta 块内有效） |
| `concrete` | meta 关键字 | 定义具体类型（仅在 meta 块内有效） |
| `dispatch` | meta 关键字 | 定义多重分派规则（仅在 meta 块内有效） |
| `owend` | 语法糖 | 所有权声明 |
| `let` | 语法糖 | 块级绑定（控制流） |
| `val` | 语法糖 | 不可变变量声明 |
| `defer` | 语法糖 | 延迟清理语句 |
| `|>` | 语法糖 | 管道操作符 |
| `&` | 运算符 | 解引用指针 |
| `addr()` | 内置函数 | 取地址（仅适用于 C 类型变量） |
| `Option[T]` | 泛型类型 | 可选类型 |
| `Result[T, E]` | 泛型类型 | 结果类型 |
| `Vec[T]` | 泛型类型 | 动态数组 |
| `HashMap[K, V]` | 泛型类型 | 哈希映射 |
| `int*`, `double*`, etc. | 类型 | 指针类型注解 |
| 其他 Python 关键字 | 继承 | 保持 Python 语义 |

---

**版本**: Cypy 1.0  
**日期**: 2026-07-22  
**后端**: Cython 3.0+