# 附录 C - 主要特性参考

> 本附录提供 Cypy 语言主要特性的概览，每项特性给出简述、关键语法、最小示例，并指向详细的 SYNTAX 文档。
> 适用于快速查阅与回顾。

---

## 1. Cypy 语言概览

### 简述

Cypy（Cython + Python Syntactic Sugar）是一种基于 Python 语法体系的**编译型语言**。源码（`.cypy`）经 `cypyc` 转译为 Cython（`.pyx`），再由 Cython 编译器生成 C 代码，最终编译为 Python 扩展（`.pyd`/`.so`）。

### 设计目标

| 目标 | 说明 |
|------|------|
| Python 兼容 | 大部分 Python 语法可用，缩进必须为 4 的倍数 |
| 渐进式类型 | 有注解 → 静态类型（cpdef）；无注解 → PyObject（仍走 Cython） |
| 性能 | 通过 Cython 后端生成 C 代码，获得接近原生 C 的性能 |
| 显式内存 | 指针默认逃逸，`defer` 提供自动清理 |
| 语法糖 | 引入构建块、命名参数、管道等，保持 Python 可读性 |

### 编译流水线

```
.cypy → cypyc 转译 → .pyx → cythonize → .c → C 编译器 → .pyd/.so
```

### 关键语法

```bash
cypyc --compile input.cypy       # 编译
cypyc --check input.cypy         # 仅类型检查
cypyc run input.cypy             # 编译并运行
cypyc watch ./src                # 热重载开发
```

参见：`00-introduction.md`、`23-compilation.md`、`25-compatibility.md`。

---

## 2. 类型系统

### 简述

Cypy 提供静态类型系统，支持类型注解、类型推断、联合类型与 `Never` 类型。无注解变量退化为 `object`（PyObject）。

### 关键语法

```cypy
let x: i32 = 10                  # 显式类型
let y = 20                       # 类型推断为 i32
let z: i32 | str = "hello"       # 联合类型
def f() -> Never: raise Error()  # Never：永不返回
def g(a: i32, b: f64) -> bool:   # 函数注解 → cpdef 优化
    return a > 0
```

### 主要类型

| 类别 | 示例 |
|------|------|
| 整数 | `i8`、`i16`、`i32`、`i64`、`u8`、`u16`、`u32`、`u64` |
| 浮点 | `f32`、`f64` |
| 布尔 | `bool` |
| 字符串 | `str` |
| 指针 | `*i32`、`*mut i32` |
| 联合 | `int \| str` |
| Never | `Never` |
| SIMD | `vec[f32; 4]` |

参见：`01-basic-types.md`、`02-type-annotations.md`、`03-type-conversion.md`、`26-union-type.md`。

---

## 3. 数据结构

### 简述

Cypy 提供四种数据结构定义方式：`struct`（C 风格值类型）、`enum`（枚举）、`class`（Python 风格引用类型）、`type`（类型别名）。

### 关键语法

```cypy
# struct：值语义，可加 @value 自动生成比较/哈希
@value
struct Point:
    x: f64
    y: f64

# enum
enum Color:
    Red, Green, Blue

# class：引用语义
class Stack<T>:
    items: list<T>
    def push(self, x: T) -> None:
        self.items.append(x)

# type alias
type Vec3 = vec[f32; 3]
type IntPair = tuple<i32, i32>
```

参见：`05-struct.md`、`06-enum.md`、`08-class.md`、`12-type-alias.md`、`06d-builtin-magic-traits.md`。

---

## 4. 泛型系统

### 简述

Cypy 支持泛型函数、泛型 struct、泛型 trait。语法上使用尖括号 `<T>` 声明类型参数。

### 关键语法

```cypy
# 泛型函数
def identity<T>(x: T) -> T:
    return x

# 泛型 struct
struct Pair<T, U>:
    first: T
    second: U

# 泛型 trait
trait Container<T>:
    def get(self) -> T
    def put(self, x: T) -> None

# 实例化
let p = Pair<i32, str>(first=1, second="a")
```

参见：`11-generics.md`。

---

## 5. Trait 与 TypeClass

### 简述

`trait` 定义接口，`impl ... for ...` 为类型实现 trait。`typeclass` 是更强的约束形式。`extends` 实现 trait 继承。class 显式声明实现 trait 时使用 Python 风格 `class C(T):`。

### 关键语法

```cypy
trait Drawable:
    def draw(self) -> None

trait Resizable extends Drawable:
    def resize(self, factor: f64) -> None

impl Drawable for Circle:
    def draw(self) -> None:
        print("drawing circle")

class Square(Drawable):
    def draw(self) -> None:
        print("drawing square")

# typeclass：更强约束
typeclass Monoid<T>:
    def empty() -> T
    def combine(a: T, b: T) -> T
```

参见：`07-trait-impl.md`、`06d-builtin-magic-traits.md`、`11-generics.md`。

---

## 6. Duck 约束

### 简述

`duck` 块提供鸭子类型约束：在编译期检查类型是否具备特定运算符、属性、方法或引用。`meta` 块用于元编程上下文。

### 关键语法

```cypy
meta:
    duck {
        op "+"       # 必须支持 + 运算符
        op "*"
        attr "size"  # 必须有 size 属性
        method "iter"  # 必须有 iter 方法
    }
```

### 应用场景

- 泛型函数中对类型参数的能力约束
- 替代 trait bound 的轻量级约束方式
- 在 `meta` 块中作为编译期检查

参见：`27-constraints.md`、`31-tutorial-metaprogramming.md`。

---

## 7. 模式匹配

### 简述

`match` / `case` 提供结构化模式匹配，支持字面量、变量、元组、列表、字典、结构体、范围、OR 模式、guard 和提取器。

### 关键语法

```cypy
match shape:
    case Circle(r):
        print(f"circle r={r}")
    case Rect(w, h) if w == h:
        print("square")
    case Rect(w, h):
        print(f"rect {w}x{h}")
    case (x, y):
        print(f"point ({x},{y})")
    case [a, b, c]:
        print(f"triple {a},{b},{c}")
    case {"key": v}:
        print(f"dict v={v}")
    case 1..10:
        print("range 1-10")
    case Red | Green:
        print("warm color")
    case _:
        print("unknown")
```

### 支持的模式

| 模式 | 示例 |
|------|------|
| 字面量 | `case 1:` |
| 变量 | `case x:` |
| 元组 | `case (a, b):` |
| 列表 | `case [a, b, c]:` |
| 字典 | `case {"k": v}:` |
| 结构体 | `case Point(x, y):` |
| 范围 | `case 1..10:` |
| OR | `case A \| B:` |
| Guard | `case x if x > 0:` |
| 提取器 | `case Re(x):` |
| 通配 | `case _:` |

参见：`17-pattern-matching.md`。

---

## 8. 指针与内存

### 简述

Cypy 支持指针类型，提供 `&`（取地址）和 `*`（解引用），并通过 `defer` 实现自动资源清理。指针默认逃逸，需手动管理。

### 关键语法

```cypy
def use_ptr() -> None:
    mut x: i32 = 42
    let p: *mut i32 = &x      # 取地址
    *p = 100                   # 解引用赋值
    print(*p)                  # 100

# defer：函数退出时执行（含异常路径）
def with_file() -> None:
    let fh = open("data.txt")
    defer fh.close()           # 保证关闭
    for line in fh:
        process(line)

# addr() 函数式取地址
let q = addr(x)
```

参见：`04-pointer-types.md`、`30-tutorial-pointers.md`。

---

## 9. 元编程

### 简述

Cypy 提供三层元编程：`macro` 宏系统（代码生成）、`comptime` 编译期求值、`meta` 元编程块。支持三反引号代码字面量捕获。

### 关键语法

```cypy
# comptime：编译期求值
let size = comptime 4 * 4        # 16，编译期常量
comptime:
    assert N > 0

# macro：宏定义（三反引号捕获代码）
macro swap = `(a, b) = (b, a)`
# 调用：@swap!(x, y)

# 模板宏
def debug!(expr):
    print(`{expr} = {expr}`)

# meta 块
meta:
    let fields = ["x", "y"]
    for f in fields:
        emit(f"def get_{f}(self): return self.{f}")
```

### 三反引号字面量

```cypy
let code = `
    def generated(x):
        return x + 1
`
# 支持前缀 f/r
let fc = f`value = {x}`
```

参见：`18-macros.md`、`19-comptime.md`、`31-tutorial-metaprogramming.md`。

---

## 10. 并发

### 简述

Cypy 提供三种并发原语：`spawn`（OS 线程）、`go`（协程）、`async`/`await`（异步）。

### 关键语法

```cypy
# spawn：OS 线程
let handle = spawn worker(data)
let result = handle.join()

# go：协程（轻量）
go process(item)
go background_task()

# async/await：异步
async def fetch(url: str) -> bytes:
    return await http_get(url)

async def main() -> None:
    let a = await fetch("http://a")
    let b = await fetch("http://b")
    print(a, b)
```

参见：`20-concurrency.md`、`32-tutorial-concurrency.md`。

---

## 11. SIMD 向量

### 简述

`vec[T; N]` 提供固定大小的 SIMD 向量类型，支持 `vec![]` 字面量构造。用于数值计算的性能优化。

### 关键语法

```cypy
let v1: vec[f32; 4] = vec![1.0, 2.0, 3.0, 4.0]
let v2: vec[f32; 4] = vec![5.0, 6.0, 7.0, 8.0]
let v3 = v1 + v2          # 逐元素加法（SIMD 加速）
let s = v1 * v2           # 逐元素乘法
let sum = v3.sum()        # 求和

# 类型别名
type Vec4f = vec[f32; 4]
type Vec8i = vec[i32; 8]
```

### 操作

| 操作 | 示例 | 说明 |
|------|------|------|
| 算术 | `v1 + v2` | 逐元素 |
| 索引 | `v[0]` | 访问元素 |
| 求和 | `v.sum()` | 横向归约 |
| 最大 | `v.max()` | 横向最大 |
| 最小 | `v.min()` | 横向最小 |

参见：`21-simd-vector.md`。

---

## 12. 构建块

### 简述

构建块语法（`=:`、`~:`、`*:`、`^:`）创建闭包无参函数，支持 early return 和 guard，是 Cypy 的核心语法糖。所有构建块符号必须**后跟换行**。

### 关键语法

```cypy
# =: 变量构建块（绑定闭包）
square =:
    return x * x

# ~: 调用构建块（创建并立即调用）
result = ~:
    let temp = compute(x)
    return temp * 2

# *: 生成器构建块
gen = *:
    for i in range(10):
        yield i

# ^: 索引构建块（lz 模式）
key = ^:
    hash(x)

# ^ 构建值（在构建块内引用产出）
accumulator =:
    if x < 0: return -1
    ^x            # 等价于 return x
```

### 关键特性

- 支持 **early return**：构建块内可使用 `return` 提前退出
- 支持 **guard**：构建块内可使用 `guard` 守卫
- 闭包语义：可捕获外部变量

参见：`13-build-blocks.md`。

---

## 13. 语法糖

### 简述

Cypy 引入多种语法糖以提升表达力：命名参数（`name~`）、列表推导、f-字符串、解包、管道（`|>`）。

### 关键语法

```cypy
# 命名参数糖：f(x~ 10, y~ 20) 等价于 f(x=10, y=20)
draw(width~ 800, height~ 600)

# 列表推导
let squares = [i * i for i in range(10)]
let evens = [i for i in xs if i % 2 == 0]

# 字典推导
let d = {k: v for k, v in pairs}

# f-字符串（支持 f、r、rf 前缀）
let msg = f"value = {x}, sum = {x + y}"
let raw = r"C:\path\to\file"

# 解包
let (a, b, c) = (1, 2, 3)
let [x, y, *rest] = list

# 管道
let result = data
    |> filter(lambda x: x > 0)
    |> map(lambda x: x * 2)
    |> sum
```

参见：`14-syntax-sugar.md`。

---

## 14. 编译系统

### 简述

Cypy 提供完整的编译工具链：单文件编译、项目编译、增量编译、热重载。

### 关键语法

```bash
# 单文件
cypyc --compile input.cypy
cypyc --check input.cypy         # 仅类型检查
cypyc run input.cypy             # 编译并运行

# 项目编译（自动发现 .cypy 文件）
cypyc build ./project

# 增量编译（基于 AST 差异 + 依赖图）
cypyc build --incremental ./project

# 热重载（不中断应用）
cypyc watch ./src
```

### 编译阶段

1. **词法分析** → Token 流
2. **语法分析** → AST（带缓存）
3. **类型检查** → 类型推导与校验
4. **转译** → Cython 代码（`.pyx`）
5. **Cython 编译** → C 代码（`.c`）
6. **C 编译** → 二进制扩展（`.pyd`/`.so`）

参见：`23-compilation.md`、`24-incremental-hot-reload.md`。

---

## 15. 与 Python/Cython 的兼容性

### 简述

Cypy 设计为与 Python/Cython 高度兼容，但存在一些必要差异。

### 兼容矩阵

| 特性 | Python | Cython | Cypy |
|------|--------|--------|------|
| 缩进 | 任意 4/8/Tab | 任意 | **必须 4 的倍数** |
| 函数定义 | `def` | `def`/`cdef`/`cpdef` | `def`（统一入口） |
| 类型注解 | 可选 | 可选 | 可选（无注解→PyObject） |
| 指针 | 不支持 | `*` 支持 | `*T` + `&`/`addr()` |
| struct | 不支持 | `cdef struct` | `struct` |
| 内存管理 | GC | GC + 手动 | GC + `defer` |
| 宏 | 不支持 | 不支持 | `macro` + `comptime` |
| 模式匹配 | 3.10+ `match` | 无 | `match`/`case`（增强） |

### 兼容性策略

| 方面 | 说明 |
|------|------|
| `cdef` 兼容 | 由代码生成层（codegen）自动处理，Cypy 源码不再使用 `cdef` 关键字 |
| `.py` 文件 | 可直接导入，不转译；首行 `#!bin cypy` 标记为 Cypy 代码 |
| `@python` 装饰器 | 跳过类型检查，仍生成 Cython 代码（非纯 CPython 回退） |
| Python 库 | 可直接 `import` 使用 Python 标准库与第三方库 |

### 主要差异

1. **缩进严格**：必须为 4 的倍数，不能混用 Tab 和空格
2. **`def` 统一**：有注解 → cpdef（优化）；无注解 → 退化为 PyObject（仍走 Cython）
3. **指针默认逃逸**：需显式 `defer` 清理
4. **构建块符号**：`=:` 等是新增语法，Python 中无
5. **类型后缀**：`name~ expr` 命名参数糖为 Cypy 特有

参见：`25-compatibility.md`、`23-compilation.md`。

---

## 特性速查表

| 特性 | 关键字/符号 | 详细文档 |
|------|------------|----------|
| 静态类型 | `: T` | `02-type-annotations.md` |
| 联合类型 | `A \| B` | `26-union-type.md` |
| struct | `struct` | `05-struct.md` |
| enum | `enum` | `06-enum.md` |
| class | `class` | `08-class.md` |
| 泛型 | `<T>` | `11-generics.md` |
| trait | `trait`/`impl` | `07-trait-impl.md` |
| typeclass | `typeclass` | `07-trait-impl.md` |
| duck 约束 | `duck` | `27-constraints.md` |
| 模式匹配 | `match`/`case` | `17-pattern-matching.md` |
| 指针 | `*T`/`&x`/`addr()` | `04-pointer-types.md` |
| defer | `defer` | `04-pointer-types.md` |
| 宏 | `macro`/`name!` | `18-macros.md` |
| comptime | `comptime` | `19-comptime.md` |
| meta 块 | `meta` | `31-tutorial-metaprogramming.md` |
| spawn 线程 | `spawn` | `20-concurrency.md` |
| go 协程 | `go` | `20-concurrency.md` |
| async/await | `async`/`await` | `20-concurrency.md` |
| SIMD 向量 | `vec[T; N]`/`vec![]` | `21-simd-vector.md` |
| 构建块 | `=:`/`~:`/`*:`/`^:` | `13-build-blocks.md` |
| 命名参数糖 | `name~` | `14-syntax-sugar.md` |
| 管道 | `\|>` | `14-syntax-sugar.md` |
| f-字符串 | `f"..."`/`f``...``` | `14-syntax-sugar.md` |
| 增量编译 | `cypyc build --incremental` | `24-incremental-hot-reload.md` |
| 热重载 | `cypyc watch` | `24-incremental-hot-reload.md` |

## 备注

1. **渐进式类型**：Cypy 不强制类型注解，无注解变量退化为 `object`，仍走 Cython 后端（不是纯 CPython 回退）。
2. **`def` 统一入口**：避免在 `def`/`cdef`/`cpdef` 之间选择；编译器根据注解决定生成代码。
3. **构建块是核心**：`=:` 等构建块支持 early return 和 guard，是 Cypy 区别于 Python/Cython 的标志性特性。
4. **指针与 defer 配合**：指针默认逃逸，必须显式 `defer` 清理，避免内存泄漏。
5. **三反引号字面量**：用于宏代码捕获，支持 `f`/`r` 前缀，符合 lang-zone 规范。
