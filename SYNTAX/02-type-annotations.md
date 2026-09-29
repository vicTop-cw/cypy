# 类型注解

## 变量注解

### 基本语法

```python
# 基本类型注解
age: int = 30
name: str = "Alice"
is_active: bool = True
score: float = 95.5

# 容器类型注解
numbers: list<int> = [1, 2, 3]
mapping: dict<str, int> = {"a": 1, "b": 2}
coordinates: tuple<int, int> = (10, 20)

# 无初始化的注解
result: int
result = 42

# 可选类型（可能为 None）
maybe_value: object = None
```

### 渐进式类型

```python
# 有注解的变量 - 静态类型检查
let x: int = 10
x = "hello"  # ❌ 类型错误

# 无注解的变量 - 退化为 PyObject
dynamic = 42
dynamic = "hello"  # ✅ 允许，运行时动态类型
```

## 函数注解

### 参数和返回值注解

```python
# 带类型注解的函数
def add(a: int, b: int) -> int:
    return a + b

# 部分注解
def greet(name: str):
    return f"Hello, {name}"  # 返回类型从 return 语句推断

# 无注解函数（完全动态）
def process(data):
    return data

# 可选参数
def repeat(s: str, times: int = 3) -> str:
    return s * times

# 可变参数
def sum_all(*args: int) -> int:
    total: int = 0
    for num in args:
        total += num
    return total
```

### 类型检查行为

```python
def double(x: int) -> int:
    return x * 2

result = double(42)    # ✅ 正确
result = double("42")  # ❌ 编译时类型错误
```

## 类型别名

### 基本类型别名

```python
# 简单类型别名
type Point = tuple<int, int>
type Matrix = list<list<float>>

# 使用类型别名
origin: Point = (0, 0)
identity: Matrix = [[1, 0], [0, 1]]
```

### 泛型类型别名

```python
# 泛型类型别名
type Result<T> = tuple<bool, T>

# 使用泛型类型别名
success: Result<int> = (True, 42)
failure: Result<str> = (False, "error")
```

## 联合类型

### 联合类型注解

```python
# 联合类型（支持多种类型）
type Numeric = int | float
type StringOrNone = str | None

# 使用联合类型
def process_value(val: Numeric) -> Numeric:
    return val * 2

def get_name() -> StringOrNone:
    return None  # 或返回字符串
```

## 特殊注解

### Never 类型注解

```python
# 返回 Never 的函数
def fatal_error(message: str) -> Never:
    raise RuntimeError(message)

# 不会到达的代码路径
def safe_divide(a: float, b: float) -> float:
    if b == 0:
        fatal_error("Division by zero")  # 返回 Never
    return a / b  # 类型检查通过
```

### 无返回值函数

```python
# 返回 None 的函数（省略返回类型）
def print_message(msg: str):
    print(msg)

# 显式标注 None 返回
def log(message: str) -> None:
    print(f"[LOG] {message}")
```

## 注解与 `@python` 装饰器

```python
@python
def legacy_code(x, y):
    # @python 装饰器跳过类型检查
    return x + y

# 普通函数仍进行类型检查
def modern_code(x: int, y: int) -> int:
    return x + y
```

## 注解形态闭集（R7 补，2026-09-29）

文档上文给出的容器写法是**唯一**的容器注解形态：`list<int>` / `dict<str, int>` / `tuple<int, int>`。
本节把「什么样的注解算合法形态」钉成闭集，供分析器据此诊断（缺陷账本 BUG-34 / BUG-108 的规范依据）。

| 合法形态 | 节点 | 例子 |
|---------|------|------|
| 类型名 | `Name` | `int`、`str`、自定义 `struct` 名 |
| 泛型 | `GenericType` | `list<int>`、`dict<str, int>`、`tuple<int, int>`、`Box<T>` |
| 指针 | `PointerType` | `*char`、`*void` |
| 联合 | `UnionType` | `int | str`、`tuple<str, str> | None` |
| 引用 | `RefType` | `ref<int>` |

**禁止形态（必须诊断，带行列号）**：把字面量当类型写。

```python
xs: [int] = [1, 2, 3]          # ❌ 未文档化：列表字面量形态，正确写法 list<int>
pair: (int, str) = (1, "a")    # ❌ 未文档化：元组字面量形态，正确写法 tuple<int, str>
ms: {str: int} = {"a": 1}      # ❌ 未文档化：字典字面量形态，正确写法 dict<str, int>
```

规则原文：

1. 嵌套形态同样受限：`list<[int]>` 这类「泛型的实参里出现字面量形态」也必须诊断；
2. 诊断文案必须点名**正确写法**（`list<int>` 等），不得只说「类型错误」；
3. **任何情况下不得把 AST 节点的 Python repr 落进产物**：生成器遇到未知形态只能退化为 `object`，
   产物里出现 `Constant(line=` / `GenericType(line=` 这类片段即视为缺陷；
4. `comptime:` 行内形式（`comptime: [1, 2]`）**不是**类型注解，不受本节约束
   （锁死用例见 `tests/analyzer/test_r5_fix_comptime_types.py::test_bug83_inline_form_control_still_clean`）。

## 容器元素位判定（R13 补，2026-09-29）

上一节钉的是「注解**写成什么形态**算合法」，本节钉「写成合法形态之后**判不判**」。
缺陷账本 BUG-137 的规范依据：`let bad: tuple<bool, int> = (True, "x")` 这类
「声明与字面量都是文档化形态、元素却不同」的赋值，在分析器里曾被「容器同名即放行」一并吞掉。

1. **定长容器（`tuple`）**：元素个数与逐位类型都要判。个数不符报个数，
   个数相符则逐位比：`tuple<int, int>` 收 `(1,)` 与 `(1, "a")` 都是编译期错误。
2. **变长容器（`list` / `set` / `Array`）**：声明的元素类型即每个位的要求
   （字面量 heterogeneous 时元素类型塌成 `object`，见规则 4），`list<int>` 收 `["s"]` 要报。
   嵌套同理：`list<list<int>>` 收 `[["s"]]` 要报。
3. **数值加宽单向放行**：`bool → int → float → double` 与标量位同一条阶梯，
   `list<float>` 收 `[1, 2]` 合法，`list<int>` 收 `[1.5]` 非法。
4. **占位形态一律放行**（这四类正是「同名即放行」分支当初要覆盖的形态，收紧后仍不得报）：
   值侧没有元素信息（空容器构造器 `list()`、无参 `set<…>()`）、值侧元素为 `object` / `Any`、
   值侧元素含 `None`、声明侧为 `object` / `Any` / `type`。
5. **保守集**：只有当两侧元素名都落在闭合标量表
   （`bool` `int` `long` `float` `double` `char` `str` `bytes`）时才允许报「名字不同即不兼容」；
   用户类、trait、`subtype`、别名残余一律放行。这是**刻意**的选择：误报会打断既有锁，
   而漏报有账可查（`list<Dog>` 收 `[Cat()]` 至今静默 ⇒ 记在 BUG-137 的「未覆盖」栏，不粉饰成已判）。
6. `dict<str, int>` 的键值位**在 R13 时不在本节范围内**（当时字典字面量不推断类型，
   拿不存在的实得类型去比只会造出假绿）——该豁免自 R14 起作废，见下一节；
   规则 3-5 对 dict 的键位（第 1 位）与值位（第 2 位）同样成立。

规则 1-3 的反例都要过 `scripts/omega_gate.py` 的 `generics:alias` 语料族，
锁死用例见 `tests/test_container_elements_r13.py`（R13）与 `tests/test_dict_elements_r14.py`（R14）。

## 字典字面量的键值位判定（R14 补，2026-09-29）

上一节的规则 6 曾把 `dict` 排除在外，理由诚实：字典字面量根本不推断出类型，
拿不存在的「实得类型」去比只会造出假绿。R14 补上了推断件，于是这一节把 `dict` 接进判定集合。

1. **字面量必须推断出类型**：`{}` ⇒ `dict<object, object>`；
   键（值）同形 ⇒ 该类型；数值可加宽的一串 ⇒ 取阶梯上最宽的那个；
   混形 ⇒ 该位塌成 `object`。塌成 `object` 的位按规则 4 一律放行，**不发明拒绝**。
2. **`dict` 进入本节判定集合**：键位比 `generic_params[0]`，值位比 `generic_params[1]`，
   逐个位用同一把尺（`_slot_incompatible`），不另起一套文案。
3. **上一节规则 3-5 对两个位同样成立**：`dict<str, float>` 收 `{"a": 1}` 合法（单向加宽）、
   `dict<str, int>` 收 `{}` 合法（占位）、`dict<str, Dog>` 收 `{"a": Dog()}` 仍放行（保守集不动）。
4. **别名与嵌套一并生效**：`type Count = dict<str, int>` 之后 `let bad: Count = {"a": "b"}` 要报；
   `dict<str, list<int>>` 收 `{"a": ["s"]}` 要报（嵌套位递归到上一节的元素判定）。
5. **上一节规则 6 自本条起作废**，改写为：仍不在范围内的是「字典推导式、
   `for k, v in d` 解包出来的键值位、以及 `d["k"] = v` 的写入位」——那些面靠字面量推断之外通道取类型，
   本轮不判，记在缺陷账本里而不是粉饰成已判。
6. **有账的漏报**：`dict<str, int>` 收 `{"a": 1, "b": "c"}`（值位混形）至今静默，
   本节把它钉成**正向对照**（必须一直绿），扩面那天要先让它红，而不是悄悄改判据。

判据语料：`corpus/cypy.dict.elements.json`（op `cypy.dict.elements`）；
成对探针：`.fist-loop-20260929/probe_r14_dict.py`。

