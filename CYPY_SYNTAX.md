# Cypy 语言语法规范文档

> **Cypy** = Cython + Python Syntactic Sugar
> 
> 一种基于 Python 语法体系的编译型语言，通过 Cython 作为后端实现性能提升，同时引入类型系统和语法糖，在保持 Python 兼容性的前提下提供更好的性能和稳定性。

---

## 目录

1. [设计理念](#1-设计理念)
2. [类型系统](#2-类型系统)
3. [模块级魔法属性](#3-模块级魔法属性)
4. [新语法构造](#4-新语法构造)
5. [类型转换与隐式策略](#5-类型转换与隐式策略)
6. [构建块语法](#6-构建块语法)
7. [语法糖](#7-语法糖)
8. [编译与工具链](#8-编译与工具链)
9. [兼容性与降级规则](#9-兼容性与降级规则)
10. [代码示例](#10-代码示例)
11. [变更日志](#11-变更日志)

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

#### 指针操作

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
```

### 2.3 类型推断规则

```
规则 1: 变量声明时若有类型注解，使用该类型
    x: int = 10           → cdef int x = 10

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
    ptr = malloc(...)        # ❌ 编译错误
```

---

## 3. 模块级魔法属性

Cypy 自动生成以下模块级魔法属性：

### 3.1 自动生成的属性

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `__name__` | `str` | 模块名称 |
| `__file__` | `str` | 模块文件路径 |
| `__package__` | `str` | 包名称 |
| `__path__` | `None` | 包路径 |
| `__compile_time__` | `str` | 编译时间（ISO 格式） |
| `__target__` | `str` | 目标平台（如 `AMD64-windows`） |
| `__profile__` | `str` | 构建配置（`debug` 或 `release`） |
| `__all__` | `list` | 公共 API 列表（自动收集） |
| `__private__` | `list` | 私有变量列表 |
| `__deps__` | `list` | 依赖模块列表 |

### 3.2 使用示例

```python
print(f"Module name: {__name__}")
print(f"Compile time: {__compile_time__}")
print(f"Target platform: {__target__}")
```

### 3.3 自定义 `__all__`

```python
__all__ = ["public_func", "PublicClass"]

def public_func():
    pass

def _private_func():
    pass
```

---

## 4. 新语法构造

> **规则**：`impl`, `struct`, `trait`, `enum`, `macro`, `meta` 只能写在模块顶级（层级 0），且不能嵌套。

### 4.1 `struct` — 结构体

用于定义 C 风格的数据结构，支持字段和方法。

#### 语法

```python
# 简单结构体（只有字段）→ cdef struct
struct Point:
    x: float
    y: float

# 带方法的结构体 → cdef class
struct Rectangle:
    width: float
    height: float
    
    def area(self) -> float:
        return self.width * self.height
```

#### 使用方式

```python
# 使用结构体字面量语法
p = Point {x: 10.0, y: 20.0}
rect = Rectangle {width: 5.0, height: 3.0}

print(f"Point: ({p.x}, {p.y})")
print(f"Rectangle area: {rect.area()}")
```

### 4.2 `enum` — 枚举

```python
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3
```

### 4.3 `trait` — 特质（接口）

```python
trait Drawable:
    def draw(self) -> None:
        ...
```

### 4.4 `impl` — 实现

```python
impl Drawable for Circle:
    def draw(self) -> None:
        print(f"Drawing circle")
```

### 4.5 `macro` — 宏系统

```python
macro twice(input: Tokens) -> Tokens =
    f```$input + $input```

result = @twice!(x)
```

### 4.6 `comptime` — 编译期求值

```python
result: int = comptime: 2 + 3 * 4
```

---

## 5. 类型转换与隐式策略

### 5.1 类型转换表达式

使用 `as` 关键字进行显式类型转换：

```python
def convert_values() -> float:
    a: int = 10
    b: float = a as float
    c: int = b as int
    return (a + c) as float
```

### 5.2 隐式策略

#### 隐式结构体定义

```python
implicit struct Config:
    debug: bool = True
    timeout: int = 30
    url: str = "http://localhost"
```

#### 隐式变量声明

```python
implicit ctx: Config = Config {debug: False, timeout: 60}
```

### 5.3 魔法转换方法

| 方法 | 说明 |
|------|------|
| `__cast__(self, target_type)` | 显式类型转换 |
| `__try_cast__(self, target_type)` | 尝试转换，失败返回 None |

---

## 6. 构建块语法

构建块用于创建闭包无参函数，内部默认 unsafe，允许指针语法。

### 6.1 构建块类型

| 符号 | 名称 | 说明 |
|------|------|------|
| `=:` | 变量构建块 | 自动将最后表达式作为返回值赋值给左侧变量 |
| `~:` | 调用构建块 | 返回元组、命名元组、字典或实现 `BuildParams` trait 的对象 |
| `*:` | 生成器构建块 | 返回迭代器，`yield` 产生参数包 |

### 6.2 变量构建块 `=:`

```python
result =:
    x = 10
    y = 20
    x + y  # 最后表达式作为返回值，result = 30
```

### 6.3 调用构建块 `~:`

```python
def create_user(name: str, age: int) -> str:
    return f"User: {name}, Age: {age}"

user = create_user ~:
    name = "Alice"
    age = 30
```

### 6.4 生成器构建块 `*:`

```python
def process_items(items):
    for item in items:
        print(f"Processing: {item}")
    return len(items)

count = process_items *:
    yield (1, "first")
    yield (2, "second")
    yield (3, "third")
```

---

## 7. 语法糖

### 7.1 管道操作符 `|>`

```python
result = data |> process |> filter |> transform |> str
```

### 7.2 `owend` — 所有权声明

```python
owend x: int = 10
```

### 7.3 `let` — 块级绑定

```python
if let x = compute_value():
    print(x)
```

### 7.4 `val` — 不可变变量

```python
val PI: double = 3.14159
```

### 7.5 `defer` — 延迟清理

```python
def process_data(size: int) -> int:
    buffer: int* = malloc(sizeof(int) * size)
    defer free(buffer)  # 函数退出时自动执行
    buffer[0] = 42
    return buffer[0]
```

### 7.6 `guard` — 守卫表达式

```python
def process(x: int) -> int:
    guard x != 0 else 0
    return x
```

### 7.7 联合类型

```python
type Number = int | float | double

def process(value: int | str) -> None:
    pass
```

---

## 8. 编译与工具链

### 8.1 `cypyc` 转译器

#### 命令行接口

```bash
# 转译单个文件
cypyc input.cypy

# 转译并编译
cypyc --compile input.cypy

# 类型检查（仅检查，不生成代码）
cypyc --check input.cypy
```

#### 转译流程

```
1. 词法分析（Tokenization）
   └── 将源码分解为 token 流

2. 语法分析（Parsing）
   └── 构建 AST（支持自定义扩展节点）

3. 作用域分析（Scope Analysis）
   └── 计算每个节点的缩进层级和作用域

4. 类型检查（Type Checking）
   └── 验证类型注解的一致性

5. 代码生成（Code Generation）
   └── 将 AST 转换为 Cython 代码

6. Cython 编译
   └── cythonize → C 代码 → 二进制扩展
```

---

## 9. 兼容性与降级规则

### 9.1 Python 兼容性

| 特性 | 支持情况 |
|------|----------|
| 所有 Python 语法 | ✅ 完全支持 |
| Python 标准库 | ✅ 完全支持 |
| 第三方 Python 库 | ✅ 完全支持 |
| Python 装饰器 | ✅ 支持 |
| Python 上下文管理器 | ✅ 支持 |
| Python 异步语法 (`async/await`) | ✅ 支持 |

### 9.2 降级规则

```
规则 1: 无类型注解的变量 → PyObject（与 Python 行为一致）
规则 2: 无类型注解的函数参数 → PyObject
规则 3: 纯 Python 代码文件 (.py) → 直接导入，不转译
规则 4: 混合代码 → 有注解的部分使用静态类型，其余退化
规则 5: 指针类型必须显式注解 → 无注解的指针声明会报错
```

---

## 10. 代码示例

### 10.1 完整示例：结构体与方法

```python
struct Rectangle:
    width: float
    height: float
    
    def area(self) -> float:
        return self.width * self.height

def main() -> int:
    rect = Rectangle {width: 5.0, height: 3.0}
    print(f"Area: {rect.area()}")
    return 0
```

### 10.2 完整示例：构建块

```python
def main() -> int:
    # 变量构建块
    result =:
        x = 10
        y = 20
        x + y
    
    print(f"Result: {result}")
    return 0
```

### 10.3 完整示例：模块级魔法属性

```python
__all__ = ["main"]

def main() -> int:
    print(f"Module: {__name__}")
    print(f"Compile time: {__compile_time__}")
    return 0
```

---

## 11. 变更日志

### v1.0.6 (2026-07-25)

**泛型系统增强**：

- ✅ 泛型函数类型参数推断（`make_pair(1, 2)` 自动推断为 `make_pair[int]`）
- ✅ 泛型函数参数约束（支持 `def make_pair[T: int](a: T, b: T) -> Pair[T]`）
- ✅ 泛型参数在返回类型注解中正确处理
- ✅ TryStmt AST 节点属性修正（`handlers` 而非 `except_clauses`）

**测试结果**：

- ✅ 所有 52 个测试用例通过
- ✅ 泛型函数 `def make_pair[T](a: T, b: T) -> Pair[T]` 编译成功
- ✅ 泛型函数调用 `make_pair(1, 2)` 类型推断成功

### v1.0.5 (2026-07-25)

**类型系统完善**：

- ✅ 泛型类型推断（在结构体字面量中根据字段值推断泛型参数类型）
- ✅ 类型参数约束（支持 `struct Pair[T: int]: ...` 语法）
- ✅ 类型别名展开（支持递归类型别名展开）
- ✅ 异常处理完善（添加 `_visit_RaiseStmt` 和 `_visit_TryStmt` 处理）
- ✅ 一等类型用法（支持 `type(expr)` 获取表达式类型）

**测试结果**：

- ✅ 所有 52 个测试用例通过
- ✅ 泛型结构体 `struct Pair[T]: first: T` 编译成功
- ✅ 泛型约束 `struct Pair[T: int]: ...` 编译成功
- ✅ 类型别名递归展开编译成功

### v1.0.4 (2026-07-25)

**类型系统完善**：

- ✅ 泛型类型参数注册（在 struct 和 type alias 内注册泛型参数为类型，解决 `Undefined name 'T'` 错误）
- ✅ val 变量不可变性检查（已有功能，重新验证）
- ✅ addr() 参数类型限制（只能接受原生类型 int/float/double/bool 和指针类型，不能接受 Python 对象）

**测试结果**：

- ✅ 所有 52 个测试用例通过
- ✅ 泛型结构体 `struct Pair[T]: first: T` 编译成功

### v1.0.3 (2026-07-25)

**边界检查增强**：

- ✅ defer 模块级定义检查（已修复，defer 只能在函数内使用）
- ✅ 泛型空参数列表检测（已修复，struct 和 type alias 检测空泛型参数）
- ✅ 缩进不足检测（已修复，缩进不足和不一致会报错）
- ✅ 边界测试覆盖率提升至 93%（42/45）

**设计决策**：

- ✅ struct 允许在函数内定义（兼容 R7 测试用例）
- ✅ enum/trait/impl/meta 保持模块级限制

**测试结果**：

- ✅ 所有 52 个测试用例通过
- ✅ R7 测试文件全部通过

### v1.0.2 (2026-07-25)

**新增特性**：

- ✅ `and`/`or` 布尔运算符支持（词法分析器添加关键字映射）
- ✅ `not` 运算符支持
- ✅ `in`/`is` 运算符支持
- ✅ `cdef` 关键字支持（`cdef class`、`cdef` 变量声明）
- ✅ `match`/`case` 模式匹配支持（常量模式、变量绑定、元组模式、列表模式、OR 模式）
- ✅ `enum` 限定名访问（`Color.Red`）
- ✅ `yield from` 语法支持
- ✅ `spawn`/`go` 并发语句支持（使用 Python `threading` 模块）
- ✅ `free` 内置函数注册
- ✅ `Exception` 内置类型注册
- ✅ 十六进制/二进制/八进制字面量解析（自动识别进制）
- ✅ 数字下划线分隔符支持（`1_000_000`）
- ✅ 浮点数科学计数法支持（`1.5e10`、`-1.5e-10`）
- ✅ 类型别名支持（`type MyList = list[int]`）
- ✅ 嵌套泛型类型解析（`list[list[int]]`）
- ✅ 结构体可在函数内部定义
- ✅ 指针类型限制移除（可在任何地方使用）

**修复问题**：

- ✅ 转义序列丢失（`\t`、`\n`、`\r` 被错误转换为普通字符）
- ✅ `match` 变量绑定未注册到作用域（`case other:` 报 `Undefined name`）
- ✅ `GuardStmt` 类型检查错误（访问不存在的 `condition` 字段，`orelse` 列表处理错误）
- ✅ 类型别名解析失败
- ✅ `yield` 语句代码生成丢失（生成器函数未生成 `yield` 代码）
- ✅ class 继承语法不支持（`class Child(Parent):` 报语法错误）
- ✅ class 方法 `self` 参数未识别（报 `Undefined name`）
- ✅ `spawn`/`go` 代码生成丢失
- ✅ 结构体必须在模块级定义的限制
- ✅ match 语句中的元组模式解析错误（列表对象无 `kind` 属性）
- ✅ enum 限定名访问解析错误（`case Color.Red:` 报语法错误）
- ✅ 浮点数科学计数法解析错误（`1.5e` 无法转换为 float）

### v1.0.1 (2026-07-24)

**新增特性**：

- ✅ 复合赋值表达式支持属性目标（`self.result += value`）
- ✅ for 循环变量类型推断（从泛型列表推断元素类型）
- ✅ 列表字面量类型推断（自动识别 `list[int]`、`list[float]` 等）
- ✅ 泛型类型支持（`Type` 类支持 `generic_params`）
- ✅ `GenericType` AST 节点处理
- ✅ 集成测试全覆盖（10/10 通过）

**修复问题**：

- ✅ 结构体方法体为空（复合赋值表达式未正确解析）
- ✅ for 循环变量未注册到作用域
- ✅ 列表字面量代码生成错误（生成 `Constant(...)` 而非实际值）
- ✅ 泛型类型参数未正确传递
- ✅ `Type.__repr__` 未显示泛型参数
- ✅ 模块名提取错误（`.pyd` 文件包含版本和平台信息）
- ✅ `cdef struct` 字段生成错误（多余的 `cdef` 前缀）

### v1.0.0 (2026-07-24)

**新增特性**：

- ✅ 类型转换表达式 `expr as Type`
- ✅ 隐式策略（`implicit struct`、隐式变量声明）
- ✅ 模块级魔法属性（`__name__`、`__file__`、`__compile_time__`、`__target__`、`__profile__`、`__all__`、`__private__`、`__deps__`）
- ✅ 结构体字面量语法 `StructName {field1: value1, field2: value2}`
- ✅ 结构体方法支持（自动生成 `cdef class`）
- ✅ 构建块语法（`=:`、`~:`、`*:`）
- ✅ f-string 解析支持
- ✅ 测试套件框架

**修复问题**：

- ✅ f-string 解析错误（`f"..."` 被拆分为两个 token）
- ✅ 隐式变量声明解析错误
- ✅ 结构体字面量未处理
- ✅ 类型检查器未识别结构体属性
- ✅ 构建块代码生成错误
- ✅ 结构体方法中 `self` 类型识别

**文档更新**：

- ✅ 更新语法规范文档，涵盖所有最新特性
- ✅ 添加 DEMO 示例代码文件夹