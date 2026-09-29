# 泛型系统

## 泛型类型参数

### 基本语法

```python
# 泛型函数
def identity<T>(x: T) -> T:
    return x

# 使用泛型函数
let num: int = identity<int>(42)
let name: str = identity<str>("Alice")
```

### 多类型参数

```python
def pair<T, U>(first: T, second: U) -> tuple<T, U>:
    return (first, second)

let p: tuple<int, str> = pair<int, str>(42, "answer")
```

## 泛型函数

### 类型推断

```python
# 编译器自动推断类型参数
def get_first<T>(items: list<T>) -> T:
    return items[0]

let numbers: list<int> = [1, 2, 3]
let first_num: int = get_first(numbers)  # 自动推断 T=int

let names: list<str> = ["Alice", "Bob"]
let first_name: str = get_first(names)  # 自动推断 T=str
```

## 泛型特质

### 定义泛型特质

```python
trait Container<T>:
    def add(self, item: T) -> None:
    def get(self, index: int) -> T:
    def size(self) -> int:
```

### 实现泛型特质

```python
struct List<T>:
    items: list<T>

    def add(self, item: T) -> None:
        self.items.append(item)

    def get(self, index: int) -> T:
        return self.items[index]

    def size(self) -> int:
        return len(self.items)

impl Container<T> for List<T>:
    pass
```

## 类型约束

### 联合类型约束

```python
# 类型参数必须是 int 或 float
def process<T: int | float>(value: T) -> T:
    return value

let result1: int = process<int>(42)     # ✅
let result2: float = process<float>(3.14)  # ✅
# let result3: str = process<str>("hello")  # ❌ 类型约束不满足
```

### 特质约束

```python
trait Comparable:
    def compare(self, other: object) -> int:

# 类型参数必须实现 Comparable 特质
def sort<T: Comparable>(items: list<T>) -> list<T>:
    # 实现排序逻辑
    return sorted(items, key=lambda x: x)
```

### 多约束

```python
# 多个约束
def serialize<T: Serializable & Printable>(obj: T) -> str:
    obj.print()
    return obj.to_json()
```

## 声明界在使用侧的判定

1. **判定位**：凡是写了**显式类型实参**的使用位都要过声明界 —— 注解位（`let x: Num<str>`）与
   构造位（`One<str>(v="s")`）两形同源，且与函数调用位共用同一份判定
   （联合界／单名界／特质界／typeclass 界的消息口径一致，不各写一份）。
2. **成对口径**：违界必红、合界必绿。"合界"指类型实参落在声明界的成员之内 —— `T: int | float`
   接受 `int` 与 `float`；`T: Show` 只对**显式写了 `impl Show for X:`** 的 `X` 放行，
   方法签名再像也不算实现（特质实现是声明式的，不做结构性匹配）。
3. **不互相遮蔽**：类型实参的元数错与违界错是两条独立判据，同时出现时两条都要在册。
4. **不判的一面**：构造位**没写**类型实参时不做类型参数推断 —— `b = One(v="s")` 保持 0 诊断
   （此时界无从判定，也不许凭空产诊断）；同一程序若写成 `let a: NumS<str> = NumS(v="s")`，
   违界由**注解位**判下，而不是由字面量推断判下。该推断面另立单（BUG-135），不写进"已完成"。

## 泛型类

### 泛型类定义

```python
class Box<T>:
    def __init__(self, content: T):
        self.content = content

    def get(self) -> T:
        return self.content

    def set(self, content: T) -> None:
        self.content = content

# 使用泛型类
let int_box: Box<int> = Box<int>(42)
let str_box: Box<str> = Box<str>("hello")
```

### 泛型类的判定口径

1. **定义侧形态**：类型参数表紧跟类名、写在基类之前，三种前缀都接受 ——
   `class Box<T>:`、`class Box<T>(Base):`、`class Box<T> extends Base:`。
   参数表以逗号分隔，每项可带约束（`T: int | float`、`T: Comparable`）。
   空参数表 `class Box<>:` 报 `Generic parameter list cannot be empty`（带行列），
   与 `struct` 用的是同一份实现。
   `cdef class` **不是本门面的类前缀**：解析器没有 `cdef` 关键字，写它只会得到
   `Undefined name 'cdef'`（见账本）。
2. **一份实现，两处使用**：定义侧的参数表（class 与 struct 共用 `_parse_type_param_list`）、
   使用侧的元数比对（注解位与调用位共用 `_generic_arity_diagnostic`）——
   `Type argument count mismatch` 与 `Type arguments on non-generic` 这两条文案在整仓只有这一处产生。
3. **使用侧元数**：`let b: Box<int> = Box<int>(42)` 里注解位与调用位的类型实参个数都必须等于
   声明侧的类型参数个数；对没有类型参数的 class/struct 写 `<…>` 报 `Type arguments on non-generic`。
   **裸名合法**（`let b: Box = Box(1)`），按擦除形态处理，不报错。
4. **代入按声明顺序逐位**：成员访问 `b.content` 与方法调用 `b.get()` 的类型，取接收者的类型实参
   代入声明侧参数后的结果（`Box<int>` 上的 `get()` 就是 `int`）。没写类型实参时按 `object`。
   **形式参数名（`T`）不得作为类型出现在诊断里** —— 名字表按裸名建（`type_map["get"]`），
   承载不了接收者的代入，因此泛型类的方法名登记成未知类型，代入只在成员访问那条路径上做。
5. **产物必须擦除**：类头生成为 `class Box:`（对照：泛型 `struct Wrap<T>` 生成为 `cdef class Wrap:`），
   产物文本里既不得出现 `<int>` / `[int]` 的下标或尖括号残留，也不得出现形式参数名。

## 调用点的类型实参

`f<A, B>(x, y)` 尖括号里的内容是**类型实参表**，只有这一种解释：

1. **不与 `<checker>` 形态争义**：参数检查站是**定义侧**形态（`def f<checker>(…)`），且 v1 明确不支持
   （见 [33-type-constraints-subtypes-dispatch.md](33-type-constraints-subtypes-dispatch.md) 的 P-1.8）。
   所以调用点的 `<…>` 永远是类型实参，不会被当成"取那个名字当函数再零参调用一次"。
2. **元数**：类型实参个数必须等于被调方声明的类型参数个数；不符报
   `Type argument count mismatch`。对没有类型参数的函数/结构体写 `<…>` 报
   `Type arguments on non-generic`。
3. **多实参可写**：`pair<int, str>(42, "answer")` 与单实参 `identity<int>(42)` 同一条规则 ——
   逗号分隔，每项是一个类型表达式（`int`、`list<int>`、`tuple<int, str>`、用户定义的类型名）。
4. **产物必须擦除**：类型实参只参与静态代入，生成的调用形如 `f(x, y)`；
   既不得保留下标形态（`f[int](x)`），也不得插入对类型名的零参调用（`(int(), f(x))[1]`）。
   后者的运行期含义是"把类型当零参函数调用一次"，而 `struct`/`class` 的名字带必填字段时这样调用必然抛错。
5. **代入优先于推断**：写了显式类型实参时 `T := 该实参`，并按声明的顺序逐位代入；
   没写时按实参类型统一化推断（既有行为不变）。显式实参同样受约束（`T: int | float`、`T: Comparable`）判定。

### 明确不支持（v1）

| 形态 | 现状 |
|------|------|
| `trait Container<T>:` 的无体抽象方法（带冒号那形） | 解析不接受，见账本 BUG-120 |
| `f[T](x)`（方括号形态的类型实参） | 手册未承诺；现状被解析成「下标后调用」并进产物，见账本 BUG-121 |
| 类型实参里的未定义类型名 `f<Undefined>(x)` | 不判存在性，静默降级为 `object`，见账本 BUG-122 |

## 泛型特性

| 特性 | 说明 |
|------|------|
| **类型参数** | 使用 `<T>` 或 `<T, U>` 声明类型参数 |
| **类型推断** | 编译器自动推断类型参数 |
| **泛型函数** | 函数可以是泛型的 |
| **泛型特质** | 特质可以是泛型的 |
| **泛型类** | 类可以是泛型的 |
| **类型约束** | 支持联合类型约束 `T: int \| float` |
| **特质约束** | 支持特质约束 `T: Comparable` |
