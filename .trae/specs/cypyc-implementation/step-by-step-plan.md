# Cypy 转译器 - 系统化最小单元逐步实现计划

## 一、现有代码状态分析

### 已实现功能
| 模块 | 状态 | 已实现功能 | 缺失功能 |
|------|------|-----------|---------|
| Lexer | ✅ 基础完成 | 基本关键字、运算符、常量识别 | `meta`、`constraint`、`subtype`、`dispatch`、`val` 关键字；`<:` 运算符；管道操作符 `|>` |
| Parser | ✅ 基础完成 | 函数定义、变量声明、表达式、基本控制流 | 泛型语法 `Pair[T,U]`；指针类型 `int*`；`meta` 块；`impl` 语句；`&` 解引用 |
| TypeMapper | ✅ 基础完成 | 基本类型映射（int→int, float→double） | 指针类型完善；自定义类型注册；类型别名支持 |
| TypeChecker | ✅ 基础完成 | 基本类型检查；返回类型检查 | 指针类型检查；`val` 不可变验证；结构体字段检查 |
| CythonGenerator | ⚠️ 部分实现 | 函数、变量、表达式生成 | struct/enum/defer 生成；指针操作转换；`cdef` 声明生成 |
| Transformers | ⚠️ 框架完成 | 基本访问者模式 | defer→try/finally 转换；泛型特化；trait/impl 合并 |
| CLI | ⚠️ 框架完成 | 参数解析 | 实际转译流程集成；类型检查/内存检查命令 |

### 当前问题
1. **Lexer**：缺少 `meta` 关键字族和 `<:` 运算符
2. **Parser**：缺少泛型语法、`meta` 块、`impl` 语句、`&` 解引用运算符
3. **CythonGenerator**：未生成 `cdef` 声明，未实现 defer→try/finally 转换
4. **TypeChecker**：未验证指针类型和 `val` 不可变性
5. **CLI**：未集成转译流程

---

## 二、语法单元清单（按难度递增排序）

### 阶段一：基础语法（核心）- 依赖：无
| 序号 | 语法单元 | 难度 | 预计时间 | 优先级 |
|------|----------|------|----------|--------|
| 1.1 | 基础类型注解转译（int→cdef int） | ⭐ | 1天 | 高 |
| 1.2 | 指针类型识别与映射（int*） | ⭐⭐ | 1天 | 高 |
| 1.3 | struct 定义转译（cdef struct） | ⭐⭐ | 1.5天 | 高 |
| 1.4 | defer 语句→try/finally 转换 | ⭐⭐⭐ | 2天 | 高 |

### 阶段二：核心转译（关键）- 依赖：阶段一
| 序号 | 语法单元 | 难度 | 预计时间 | 优先级 |
|------|----------|------|----------|--------|
| 2.1 | `&ptr` 解引用→`ptr[0]` | ⭐⭐ | 1天 | 高 |
| 2.2 | `addr()` 取地址→`&x` | ⭐⭐ | 0.5天 | 高 |
| 2.3 | enum 定义转译 | ⭐⭐ | 1天 | 中 |
| 2.4 | `val`/`let` 变量声明 | ⭐ | 0.5天 | 中 |
| 2.5 | 管道操作符 `|>` | ⭐ | 0.5天 | 低 |

### 阶段三：高级类型（进阶）- 依赖：阶段二
| 序号 | 语法单元 | 难度 | 预计时间 | 优先级 |
|------|----------|------|----------|--------|
| 3.1 | 泛型语法解析（中括号） | ⭐⭐⭐ | 2天 | 高 |
| 3.2 | 泛型结构体转译 | ⭐⭐⭐ | 1.5天 | 中 |
| 3.3 | 泛型函数转译 | ⭐⭐⭐ | 1.5天 | 中 |
| 3.4 | trait 定义转译 | ⭐⭐ | 1天 | 中 |
| 3.5 | impl 实现合并 | ⭐⭐⭐ | 1.5天 | 中 |

### 阶段四：Meta 系统（复杂）- 依赖：阶段三
| 序号 | 语法单元 | 难度 | 预计时间 | 优先级 |
|------|----------|------|----------|--------|
| 4.1 | meta 块解析 | ⭐⭐ | 1天 | 中 |
| 4.2 | constraint 类型约束 | ⭐⭐⭐ | 1天 | 中 |
| 4.3 | subtype 子类型关系 | ⭐⭐⭐ | 1天 | 中 |
| 4.4 | dispatch 多重分派 | ⭐⭐⭐⭐ | 2天 | 低 |

### 阶段五：工具链（集成）- 依赖：所有阶段
| 序号 | 语法单元 | 难度 | 预计时间 | 优先级 |
|------|----------|------|----------|--------|
| 5.1 | CLI 转译命令集成 | ⭐ | 1天 | 高 |
| 5.2 | CLI 类型检查命令 | ⭐⭐ | 1天 | 高 |
| 5.3 | CLI 内存检查命令 | ⭐⭐ | 1天 | 中 |
| 5.4 | Import hook 实现 | ⭐⭐ | 1天 | 中 |

---

## 三、详细实现方案

### 阶段一：基础语法

#### 1.1 基础类型注解转译

**目标**：将带类型注解的变量/函数参数转为 Cython `cdef` 声明

**实现方案**：
1. 修改 `type_mapper.py`：添加 `to_cdef()` 方法，返回完整的 `cdef` 类型声明
2. 修改 `cython_generator.py`：
   - `_visit_FuncDef`：生成 `cdef` 函数声明
   - `_visit_LetStmt`：生成 `cdef` 变量声明
3. 修改 `type_checker.py`：增强类型检查，验证注解类型有效性

**测试用例**：
```python
# test_type_annotation.cypy
def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> str:
    return f"Hello, {name}"
```

**预期转译结果**：
```cython
cdef int add(int a, int b):
    return a + b

cdef str greet(str name):
    return f"Hello, {name}"
```

**验证标准**：
- [ ] 解析器正确识别类型注解
- [ ] 代码生成器输出正确的 `cdef` 声明
- [ ] 类型检查器能检测类型不匹配错误

---

#### 1.2 指针类型识别与映射

**目标**：支持 `int*`、`double*` 等指针类型注解

**实现方案**：
1. 修改 `lexer.py`：在 `_tokenize_identifier` 后检查后续的 `*`，合并为指针类型 token
2. 修改 `parser.py`：
   - 添加 `PointerType` AST 节点
   - 修改 `_parse_type`：支持 `Type*` 语法
3. 修改 `type_mapper.py`：
   - 添加指针类型映射规则
   - `int*` → `int*`
   - `double*` → `double*`
4. 修改 `type_checker.py`：添加指针类型检查

**测试用例**：
```python
# test_pointer_type.cypy
def allocate() -> int*:
    from libc.stdlib cimport malloc, sizeof
    ptr: int* = malloc(sizeof(int))
    return ptr
```

**预期转译结果**：
```cython
from libc.stdlib cimport malloc, sizeof

cdef int* allocate():
    cdef int* ptr = <int*>malloc(sizeof(int))
    return ptr
```

**验证标准**：
- [ ] Lexer 正确识别 `int*` 为指针类型
- [ ] Parser 构建正确的 `PointerType` AST 节点
- [ ] TypeMapper 正确映射指针类型
- [ ] 类型检查器验证指针类型使用合规

---

#### 1.3 struct 定义转译

**目标**：将 `struct Point: x: int; y: int` 转为 `cdef struct Point`

**实现方案**：
1. 修改 `parser.py`：确保 `StructDef` 和 `StructField` 正确解析字段类型
2. 修改 `struct_transformer.py`：收集所有 struct 定义，建立类型映射
3. 修改 `cython_generator.py`：
   - 添加 `_visit_StructDef`：生成 `cdef struct`
   - 添加 `_visit_StructField`：生成字段声明

**测试用例**：
```python
# test_struct.cypy
struct Point:
    x: int
    y: int

struct Node:
    value: int
    next: Node*
```

**预期转译结果**：
```cython
cdef struct Point:
    cdef int x
    cdef int y

cdef struct Node:
    cdef int value
    cdef Node* next
```

**验证标准**：
- [ ] Parser 正确解析 struct 定义
- [ ] 代码生成器输出正确的 `cdef struct`
- [ ] 支持自引用指针类型

---

#### 1.4 defer 语句→try/finally 转换

**目标**：将 `defer free(ptr)` 转为 `try/finally` 结构

**实现方案**：
1. 修改 `parser.py`：支持 `defer` 单语句形式（`defer free(ptr)`）
2. 修改 `defer_transformer.py`：
   - 在函数体中收集 defer 语句
   - 将函数体重写为嵌套的 try/finally 结构（LIFO 顺序）
3. 修改 `cython_generator.py`：生成正确的 try/finally 代码

**测试用例（单 defer）**：
```python
# test_defer_single.cypy
def safe_allocate():
    from libc.stdlib cimport malloc, free, sizeof
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)
    &ptr = 42
    return &ptr
```

**预期转译结果**：
```cython
from libc.stdlib cimport malloc, free, sizeof

cdef int safe_allocate():
    cdef int* ptr = <int*>malloc(sizeof(int))
    try:
        ptr[0] = 42
        return ptr[0]
    finally:
        free(ptr)
```

**测试用例（多 defer，LIFO）**：
```python
# test_defer_multiple.cypy
def complex_op():
    from libc.stdlib cimport malloc, free, sizeof
    r1: int* = malloc(sizeof(int))
    defer free(r1)
    r2: int* = malloc(sizeof(int))
    defer free(r2)
    &r1 = 1
    &r2 = 2
```

**预期转译结果**：
```cython
from libc.stdlib cimport malloc, free, sizeof

cdef void complex_op():
    cdef int* r1 = <int*>malloc(sizeof(int))
    try:
        cdef int* r2 = <int*>malloc(sizeof(int))
        try:
            r1[0] = 1
            r2[0] = 2
        finally:
            free(r2)
    finally:
        free(r1)
```

**验证标准**：
- [ ] 单个 defer 正确生成 try/finally
- [ ] 多个 defer 按 LIFO 顺序生成嵌套的 try/finally
- [ ] defer 在 return 前执行
- [ ] defer 在异常时执行

---

### 阶段二：核心转译

#### 2.1 `&ptr` 解引用→`ptr[0]`

**目标**：支持 `&ptr` 解引用指针，转为 Cython 的 `ptr[0]`

**实现方案**：
1. 修改 `lexer.py`：确保单独的 `&` 作为单目运算符识别
2. 修改 `parser.py`：
   - 在 `_parse_unary_expr` 中支持 `&` 前缀运算符
   - 添加 `DerefExpr` AST 节点
3. 修改 `cython_generator.py`：将 `DerefExpr(ptr)` 转为 `ptr[0]`

**测试用例**：
```python
# test_deref.cypy
def test():
    from libc.stdlib cimport malloc, free, sizeof
    ptr: int* = malloc(sizeof(int))
    defer free(ptr)
    &ptr = 42          # 赋值
    val: int = &ptr    # 取值
    return val
```

**预期转译结果**：
```cython
from libc.stdlib cimport malloc, free, sizeof

cdef int test():
    cdef int* ptr = <int*>malloc(sizeof(int))
    try:
        ptr[0] = 42
        cdef int val = ptr[0]
        return val
    finally:
        free(ptr)
```

**验证标准**：
- [ ] Lexer 正确识别单独的 `&`
- [ ] Parser 构建 `DerefExpr` AST 节点
- [ ] 代码生成器正确转换为 `ptr[0]`

---

#### 2.2 `addr()` 取地址→`&x`

**目标**：支持 `addr(local_var)` 获取变量地址

**实现方案**：
1. 修改 `parser.py`：正常解析 `addr()` 函数调用
2. 修改 `type_checker.py`：验证参数必须是 C 类型变量（非 PyObject）
3. 修改 `cython_generator.py`：将 `addr(x)` 转为 `&x`

**测试用例**：
```python
# test_addr.cypy
def test_addr():
    local: int = 100
    local_ptr: int* = addr(local)
    &local_ptr = 200
    return local  # 返回 200
```

**预期转译结果**：
```cython
cdef int test_addr():
    cdef int local = 100
    cdef int* local_ptr = &local
    local_ptr[0] = 200
    return local
```

**验证标准**：
- [ ] Parser 正确解析 `addr()` 调用
- [ ] 类型检查器验证参数为 C 类型
- [ ] 代码生成器正确转换为 `&x`

---

#### 2.3 enum 定义转译

**目标**：支持 `enum Color: RED = 1; GREEN = 2`

**实现方案**：
1. 修改 `parser.py`：确保 `EnumDef` 和 `EnumVariant` 正确解析
2. 修改 `enum_transformer.py`：收集 enum 定义
3. 修改 `cython_generator.py`：添加 `_visit_EnumDef`，生成 Python `IntEnum`

**测试用例**：
```python
# test_enum.cypy
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

enum Status:
    PENDING
    ACTIVE
    COMPLETED
```

**预期转译结果**：
```cython
from enum import IntEnum

class Color(IntEnum):
    RED = 1
    GREEN = 2
    BLUE = 3

class Status(IntEnum):
    PENDING = 0
    ACTIVE = 1
    COMPLETED = 2
```

**验证标准**：
- [ ] Parser 正确解析 enum 定义
- [ ] 支持自定义值和自动递增
- [ ] 代码生成器输出正确的 IntEnum

---

#### 2.4 `val`/`let` 变量声明

**目标**：支持 `val`（不可变）和 `let`（可变）变量声明

**实现方案**：
1. 修改 `lexer.py`：添加 `val` 关键字
2. 修改 `parser.py`：修改 `_parse_let_stmt` 支持 `val` 关键字，设置 `mutable=False`
3. 修改 `type_checker.py`：验证 `val` 变量不可重新赋值
4. 修改 `cython_generator.py`：生成普通变量声明

**测试用例**：
```python
# test_val_let.cypy
def test():
    val PI: double = 3.14159
    let counter: int = 0
    
    counter += 1
    # PI = 3.14  # 编译错误：val 不可重新赋值
    
    return counter
```

**预期转译结果**：
```cython
cdef int test():
    cdef double PI = 3.14159
    cdef int counter = 0
    
    counter += 1
    return counter
```

**验证标准**：
- [ ] Parser 正确识别 `val` 和 `let`
- [ ] 类型检查器检测 `val` 的重新赋值错误
- [ ] 代码生成器输出正确的变量声明

---

#### 2.5 管道操作符 `|>`

**目标**：支持 `5 |> double |> add_one` → `add_one(double(5))`

**实现方案**：
1. 修改 `lexer.py`：添加 `|>` 运算符识别
2. 修改 `parser.py`：在表达式解析中支持管道操作符
3. 修改 `cython_generator.py`：将 `a |> f` 转为 `f(a)`

**测试用例**：
```python
# test_pipeline.cypy
def double(n: int) -> int:
    return n * 2

def process():
    result: int = 5 |> double |> str
    return result
```

**预期转译结果**：
```cython
cdef int double(int n):
    return n * 2

cdef str process():
    cdef str result = str(double(5))
    return result
```

**验证标准**：
- [ ] Lexer 正确识别 `|>`
- [ ] Parser 正确解析管道表达式
- [ ] 代码生成器正确转换为嵌套函数调用

---

### 阶段三：高级类型

#### 3.1 泛型语法解析（中括号）

**目标**：支持 `Pair[T, U]` 和 `def identity[T](value: T) -> T`

**实现方案**：
1. 修改 `parser.py`：
   - 添加 `GenericType` AST 节点
   - 修改 `_parse_type`：支持 `Type[TypeArgs]` 语法
   - 修改 `_parse_func_def`：支持函数的类型参数列表
2. 修改 `type_mapper.py`：支持泛型类型映射

**测试用例**：
```python
# test_generic_syntax.cypy
def identity[T](value: T) -> T:
    return value

def create_pair[T, U](first: T, second: U) -> Pair[T, U]:
    return Pair[T, U](first, second)
```

**验证标准**：
- [ ] Parser 正确解析泛型类型参数
- [ ] 构建正确的 `GenericType` AST 节点
- [ ] 支持多类型参数

---

#### 3.2 泛型结构体转译

**目标**：支持 `struct Pair[T, U]: first: T; second: U`

**实现方案**：
1. 修改 `parser.py`：支持结构体的类型参数
2. 修改 `struct_transformer.py`：处理泛型结构体
3. 修改 `cython_generator.py`：
   - C 类型参数：生成特化结构体 `Pair_int_double`
   - Python 对象：类型擦除，退化为 `object`

**测试用例**：
```python
# test_generic_struct.cypy
struct Pair[T, U]:
    first: T
    second: U

struct Option[T]:
    has_value: bool
    value: T
```

**预期转译结果（类型擦除版本）**：
```cython
cdef struct Pair:
    cdef object first
    cdef object second

cdef struct Option:
    cdef bint has_value
    cdef object value
```

**验证标准**：
- [ ] Parser 正确解析泛型结构体
- [ ] 代码生成器正确处理类型擦除

---

#### 3.3 泛型函数转译

**目标**：支持泛型函数 `def identity[T](value: T) -> T`

**实现方案**：
1. 修改 `generic_transformer.py`：处理泛型函数
2. 修改 `cython_generator.py`：生成特化或类型擦除的函数

**测试用例**：
```python
# test_generic_function.cypy
def identity[T](value: T) -> T:
    return value
```

**验证标准**：
- [ ] Parser 正确解析泛型函数
- [ ] 代码生成器正确处理泛型函数

---

#### 3.4 trait 定义转译

**目标**：支持 `trait Drawable: def draw(self) -> None: ...`

**实现方案**：
1. 修改 `parser.py`：确保 `TraitDef` 正确解析方法签名
2. 修改 `trait_transformer.py`：处理 trait 定义
3. 修改 `cython_generator.py`：生成 Python 抽象基类

**测试用例**：
```python
# test_trait.cypy
trait Drawable:
    def draw(self) -> None: ...

trait Sized:
    def get_size(self) -> int: ...
```

**验证标准**：
- [ ] Parser 正确解析 trait 定义
- [ ] 代码生成器输出正确的接口定义

---

#### 3.5 impl 实现合并

**目标**：支持 `impl Drawable for Point`

**实现方案**：
1. 修改 `lexer.py`：添加 `impl` 和 `for` 关键字支持
2. 修改 `parser.py`：添加 `ImplStmt` AST 节点，解析 `impl Trait for Type`
3. 修改 `trait_transformer.py`：将 impl 方法合并到目标类型

**测试用例**：
```python
# test_impl.cypy
struct Point:
    x: int
    y: int

trait Drawable:
    def draw(self) -> None: ...

impl Drawable for Point:
    def draw(self) -> None:
        print(f"Drawing Point ({&self.x}, {&self.y})")
```

**验证标准**：
- [ ] Parser 正确解析 impl 语句
- [ ] 转换器正确合并方法到目标类型

---

### 阶段四：Meta 系统

#### 4.1 meta 块解析

**目标**：支持 `meta:` 块解析

**实现方案**：
1. 修改 `lexer.py`：添加 `meta` 关键字
2. 修改 `parser.py`：添加 `MetaBlock` AST 节点，解析 meta 块内容

**测试用例**：
```python
# test_meta.cypy
meta:
    constraint Number = int | float
```

**验证标准**：
- [ ] Parser 正确解析 meta 块
- [ ] 构建正确的 `MetaBlock` AST 节点

---

#### 4.2 constraint 类型约束

**目标**：支持 `constraint Number = int | float | double`

**实现方案**：
1. 修改 `lexer.py`：添加 `constraint` 关键字
2. 修改 `parser.py`：解析 constraint 定义
3. 修改 `meta_transformer.py`：处理类型约束，建立约束映射

**测试用例**：
```python
# test_constraint.cypy
meta:
    constraint Number = int | float | double
    constraint Real = int | float | double | long
```

**验证标准**：
- [ ] Parser 正确解析 constraint
- [ ] 类型检查器使用约束验证泛型参数

---

#### 4.3 subtype 子类型关系

**目标**：支持 `subtype Dog <: Animal`

**实现方案**：
1. 修改 `lexer.py`：添加 `<:` 运算符
2. 修改 `parser.py`：解析 subtype 关系
3. 修改 `meta_transformer.py`：建立子类型层次

**测试用例**：
```python
# test_subtype.cypy
struct Animal:
    name: str

struct Dog:
    name: str
    breed: str

meta:
    abstract Animal
    subtype Dog <: Animal
```

**验证标准**：
- [ ] Parser 正确解析 subtype 关系
- [ ] 类型检查器验证子类型兼容性

---

#### 4.4 dispatch 多重分派

**目标**：支持 `dispatch meet(a: Dog, b: Cat)`

**实现方案**：
1. 修改 `lexer.py`：添加 `dispatch` 关键字
2. 修改 `parser.py`：解析 dispatch 声明
3. 修改 `meta_transformer.py`：生成特化函数和分派调度器

**测试用例**：
```python
# test_dispatch.cypy
struct Dog:
    name: str

struct Cat:
    name: str

meta:
    subtype Dog <: Animal
    subtype Cat <: Animal
    dispatch meet(a: Dog, b: Dog) -> str
    dispatch meet(a: Dog, b: Cat) -> str

def meet(a: Dog, b: Dog) -> str:
    return f"{a.name} and {b.name} play"
```

**预期转译结果**：
```cython
cdef struct Dog:
    cdef str name

cdef struct Cat:
    cdef str name

cdef str meet_Dog_Dog(Dog a, Dog b):
    return f"{a.name} and {b.name} play"

cdef str meet_Dog_Cat(Dog a, Cat b):
    ...

def meet(a, b):
    if isinstance(a, Dog) and isinstance(b, Dog):
        return meet_Dog_Dog(a, b)
    elif isinstance(a, Dog) and isinstance(b, Cat):
        return meet_Dog_Cat(a, b)
```

**验证标准**：
- [ ] Parser 正确解析 dispatch
- [ ] 代码生成器生成特化函数和调度器

---

### 阶段五：工具链

#### 5.1 CLI 转译命令集成

**目标**：实现 `cypyc input.cypy` → `input.pyx`

**实现方案**：
1. 修改 `cli.py`：
   - 读取 `.cypy` 源文件
   - 调用 Lexer → Parser → Transformers → CythonGenerator
   - 将结果写入 `.pyx` 文件

**测试用例**：
```bash
cypyc test.cypy  # 生成 test.pyx
```

**验证标准**：
- [ ] CLI 正确读取源文件
- [ ] 生成正确的 `.pyx` 文件

---

#### 5.2 CLI 类型检查命令

**目标**：实现 `cypyc --check input.cypy`

**实现方案**：
1. 修改 `cli.py`：添加 `--check` 参数
2. 调用 Lexer → Parser → TypeChecker
3. 输出类型错误报告

**测试用例**：
```bash
cypyc --check test.cypy  # 输出类型错误
```

**验证标准**：
- [ ] CLI 正确执行类型检查
- [ ] 输出清晰的错误信息（含行号和上下文）

---

#### 5.3 CLI 内存检查命令

**目标**：实现 `cypyc --check-memory input.cypy`

**实现方案**：
1. 修改 `cli.py`：添加 `--check-memory` 参数
2. 调用指针清理检查器
3. 输出内存泄漏警告

**测试用例**：
```bash
cypyc --check-memory test.cypy  # 输出内存泄漏警告
```

**验证标准**：
- [ ] CLI 正确执行内存检查
- [ ] 检测未使用 defer 清理的指针

---

#### 5.4 Import hook 实现

**目标**：支持开发阶段实时转译 `.cypy` 文件

**实现方案**：
1. 修改 `cypy_hook/hook.py`：
   - 使用 `importlib` 实现自定义加载器
   - 集成转译器，实时转译 `.cypy` 文件

**测试用例**：
```python
# demo.py
import cypy_hook
cypy_hook.install()
import test  # 自动加载 test.cypy
```

**验证标准**：
- [ ] 安装 hook 后能正确加载 `.cypy` 文件
- [ ] 支持开发阶段的实时转译

---

## 四、测试策略

### 4.1 单元测试框架
- 使用 `pytest` 作为测试框架
- 每个模块对应独立的测试文件
- 测试命名规范：`test_{module}.py`

### 4.2 测试分层

| 层级 | 测试内容 | 覆盖率要求 |
|------|----------|-----------|
| 单元测试 | 单个函数/方法的正确性 | ≥ 80% |
| 集成测试 | 多个模块协作的正确性 | 覆盖所有语法构造 |
| 端到端测试 | 完整转译流程的正确性 | 覆盖示例代码 |

### 4.3 测试用例库结构

```
tests/
├── test_lexer.py          # 词法分析器测试
├── test_parser.py         # 语法分析器测试
├── test_type_mapper.py    # 类型映射器测试
├── test_type_checker.py   # 类型检查器测试
├── test_codegen.py        # 代码生成器测试
├── test_transformer.py    # 转换器测试
├── test_cli.py            # CLI 测试
├── test_hook.py           # Import hook 测试
└── fixtures/              # 测试用例文件
    ├── struct.cypy
    ├── defer.cypy
    ├── generic.cypy
    ├── meta.cypy
    └── ...
```

### 4.4 测试执行流程

1. **语法单元实现后**：立即编写单元测试
2. **阶段完成后**：运行阶段集成测试
3. **每日构建**：运行完整测试套件

---

## 五、进度跟踪与质量保障

### 5.1 进度跟踪表

| 阶段 | 语法单元 | 状态 | 测试结果 | 负责人 |
|------|----------|------|----------|--------|
| 阶段一 | 1.1 基础类型注解 | [ ] | - | - |
| 阶段一 | 1.2 指针类型识别 | [ ] | - | - |
| 阶段一 | 1.3 struct 转译 | [ ] | - | - |
| 阶段一 | 1.4 defer 转换 | [ ] | - | - |
| 阶段二 | 2.1 `&ptr` 解引用 | [ ] | - | - |
| 阶段二 | 2.2 `addr()` 取地址 | [ ] | - | - |
| 阶段二 | 2.3 enum 转译 | [ ] | - | - |
| 阶段二 | 2.4 val/let | [ ] | - | - |
| 阶段二 | 2.5 管道操作符 | [ ] | - | - |
| 阶段三 | 3.1 泛型语法 | [ ] | - | - |
| 阶段三 | 3.2 泛型结构体 | [ ] | - | - |
| 阶段三 | 3.3 泛型函数 | [ ] | - | - |
| 阶段三 | 3.4 trait 定义 | [ ] | - | - |
| 阶段三 | 3.5 impl 实现 | [ ] | - | - |
| 阶段四 | 4.1 meta 块解析 | [ ] | - | - |
| 阶段四 | 4.2 constraint | [ ] | - | - |
| 阶段四 | 4.3 subtype | [ ] | - | - |
| 阶段四 | 4.4 dispatch | [ ] | - | - |
| 阶段五 | 5.1 CLI 转译 | [ ] | - | - |
| 阶段五 | 5.2 CLI 类型检查 | [ ] | - | - |
| 阶段五 | 5.3 CLI 内存检查 | [ ] | - | - |
| 阶段五 | 5.4 Import hook | [ ] | - | - |

### 5.2 质量保障措施

1. **代码审查**：每个语法单元实现后进行代码审查
2. **单元测试覆盖率**：每个模块 ≥ 80%
3. **集成测试**：每个阶段完成后运行集成测试
4. **文档同步**：代码变更同步更新文档
5. **CI/CD**：配置持续集成，自动运行测试

### 5.3 质量验收标准

| 标准 | 要求 |
|------|------|
| 功能正确性 | 所有测试用例通过 |
| 类型安全性 | 类型检查器能检测所有类型错误 |
| 内存安全性 | 指针清理检查器能检测内存泄漏 |
| 代码质量 | 符合 PEP 8 规范，无语法错误 |
| 文档一致性 | 文档与实现代码一致 |

---

## 六、依赖关系图

```
1.1 基础类型注解 ──→ 1.2 指针类型 ──→ 1.3 struct ──→ 1.4 defer
    │                    │                    │
    │                    │                    └──→ 2.1 &解引用
    │                    │                    └──→ 2.2 addr()
    │                    └──→ 2.3 enum
    │                    └──→ 2.4 val/let
    └──→ 2.5 管道操作符

1.3 struct ──→ 3.1 泛型语法 ──→ 3.2 泛型结构体
                    │                    └──→ 3.3 泛型函数
                    └──→ 3.4 trait ──→ 3.5 impl

3.1 泛型语法 ──→ 4.1 meta块 ──→ 4.2 constraint
                    │                    └──→ 4.3 subtype ──→ 4.4 dispatch

阶段一+二 ──→ 5.1 CLI转译 ──→ 5.2 CLI类型检查
                    │                    └──→ 5.3 CLI内存检查
                    └──→ 5.4 Import hook
```

---

## 七、时间节点规划

| 阶段 | 任务 | 预计时间 | 里程碑 |
|------|------|----------|--------|
| 阶段一 | 1.1-1.4 | 5.5 天 | 基础转译能力完成 |
| 阶段二 | 2.1-2.5 | 3.5 天 | 核心转译能力完成 |
| 阶段三 | 3.1-3.5 | 7.5 天 | 高级类型系统完成 |
| 阶段四 | 4.1-4.4 | 5 天 | Meta 系统完成 |
| 阶段五 | 5.1-5.4 | 4 天 | 工具链完成 |
| **总计** | | **25.5 天** | **1.0 版本发布** |