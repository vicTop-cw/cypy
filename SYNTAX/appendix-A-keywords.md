# 附录 A - 关键字参考

> 本附录按类别列出 Cypy 语言中的全部关键字，并给出语法、说明和最小代码示例。
> 关键字来源：`cypyc/parser/lexer.py` 中的 `Lexer.KEYWORDS` 字典。

## 关键字总览

Cypy 关键字共 61 个，按用途分为 11 个类别。所有关键字均为保留字，不可作为标识符使用。

> **注**：`True` / `False` 在词法分析中作为独立的 `TokenType.TRUE` / `TokenType.FALSE` 处理，但语义上属于布尔值关键字。

---

## 1. 控制流关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `if` | 控制流 | `if <cond>:` | 条件分支起始 | `if x > 0: print(x)` |
| `elif` | 控制流 | `elif <cond>:` | 否则如果分支 | `elif x == 0: print("zero")` |
| `else` | 控制流 | `else:` | 否则分支 | `else: print("neg")` |
| `for` | 控制流 | `for <name> in <iter>:` | 迭代循环 | `for i in range(10): print(i)` |
| `while` | 控制流 | `while <cond>:` | 条件循环 | `while n > 0: n -= 1` |
| `break` | 控制流 | `break` | 跳出最近循环 | `for i in xs: if i == 0: break` |
| `continue` | 控制流 | `continue` | 跳过本次循环 | `for i in xs: if i < 0: continue` |
| `return` | 控制流 | `return [<expr>]` | 从函数返回 | `return x + 1` |
| `guard` | 控制流 | `guard <cond> [: <action>]` | 守卫：条件不满足时执行兜底动作 | `guard x > 0: return -1` |
| `defer` | 控制流/内存 | `defer <stmt>` | 延迟到函数退出时执行 | `defer free(ptr)` |
| `match` | 控制流 | `match <expr>:` | 模式匹配入口 | `match x: case 1: ...` |
| `case` | 控制流 | `case <pattern> [: <action>]` | 匹配分支 | `case (a, b): print(a+b)` |
| `yield` | 控制流 | `yield [<expr>]` | 生成器产出值 | `yield i * i` |

参见：`15-control-flow.md`、`17-pattern-matching.md`、`04-pointer-types.md`。

---

## 2. 定义关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `def` | 定义 | `def name(params) -> T:` | 函数定义（统一入口；有注解生成 cpdef，无注解退化为 PyObject） | `def add(a: i32, b: i32) -> i32: return a+b` |
| `class` | 定义 | `class Name[(Base)]:` | 类定义（Python 风格） | `class Foo: pass` |
| `struct` | 定义 | `struct Name<T>:` | C 风格结构体，值语义 | `struct Point: x: i32; y: i32` |
| `enum` | 定义 | `enum Name: ...` | 枚举类型 | `enum Color: Red, Green, Blue` |
| `trait` | 定义 | `trait Name<T>:` | 特质定义（接口） | `trait Drawable: def draw(self) -> None` |
| `typeclass` | 定义 | `typeclass Name<T>:` | 类型类（更强约束的 trait） | `typeclass Monoid<T>: def empty() -> T` |
| `impl` | 定义 | `impl Name for Type:` | 为类型实现 trait | `impl Drawable for Circle: ...` |
| `extends` | 定义 | `trait B extends A:` | trait 继承 | `trait B extends A: ...` |
| `type` | 定义 | `type Name = T` | 类型别名 | `type Vec3 = vec[f32; 3]` |
| `macro` | 定义 | `macro name = ...` 或 `def name!():` | 宏定义 | `macro swap = \`(a, b) = (b, a)\`` |

参见：`05-struct.md`、`06-enum.md`、`07-trait-impl.md`、`08-class.md`、`09-functions.md`、`12-type-alias.md`、`16-exceptions.md`、`18-macros.md`。

---

## 3. 变量声明关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `let` | 变量 | `let name [: T] = expr` | 不可变绑定（推荐） | `let x: i32 = 10` |
| `const` | 变量 | `const name [: T] = expr` | 编译期常量 | `const PI: f64 = 3.14159` |
| `mut` | 变量 | `mut name [: T] = expr` | 可变绑定 | `mut count: i32 = 0` |

参见：`10-variables.md`、`25-compatibility.md`。

---

## 4. 类型系统关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `meta` | 类型/元 | `meta <block>` | 元编程块，编译期执行 | `meta: print("compiling")` |
| `duck` | 类型 | `duck { ... }` | 鸭子类型约束块 | `duck { op "+"; attr "size" }` |
| `is` | 类型/运算 | `x is T` 或 `x is None` | 身份/类型判断 | `if x is None: ...` |
| `in` | 类型/运算 | `x in coll` | 成员测试 | `if key in dict: ...` |
| `Never` | 类型 | `Never` | 永不返回类型（如抛异常、无限循环） | `def fail() -> Never: raise Error()` |
| `vec` | 类型 | `vec[T; N]` 或 `vec![a, b, c]` | SIMD 向量类型/字面量 | `let v = vec![1.0, 2.0, 3.0, 4.0]` |

参见：`01-basic-types.md`、`21-simd-vector.md`、`27-constraints.md`、`31-tutorial-metaprogramming.md`。

---

## 5. 并发关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `spawn` | 并发 | `spawn <expr>` | 启动 OS 线程 | `let h = spawn worker()` |
| `go` | 并发 | `go <expr>` | 启动协程（轻量） | `go process(item)` |
| `async` | 并发 | `async def name(...):` | 异步函数定义 | `async def fetch(url): ...` |
| `await` | 并发 | `await <expr>` | 等待异步结果 | `let r = await fetch(url)` |

参见：`20-concurrency.md`、`32-tutorial-concurrency.md`。

---

## 6. 元编程关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `comptime` | 元编程 | `comptime <expr>` 或 `comptime:` | 编译期求值 | `let x = comptime 2 + 3` |
| `meta` | 元编程 | `meta <block>` | 元编程块 | `meta: let n = 4` |
| `macro` | 元编程 | `macro name = ...` | 宏定义 | `macro log = \`(msg) => print(msg)\`` |

参见：`18-macros.md`、`19-comptime.md`、`31-tutorial-metaprogramming.md`。

---

## 7. 模块关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `import` | 模块 | `import module [as alias]` | 导入模块 | `import math` |
| `from` | 模块 | `from module import name` | 从模块导入 | `from os import path` |
| `as` | 模块 | `import m as alias` 或 `expr as T` | 别名 / 类型转换 | `import numpy as np` |

参见：`23-compilation.md`。

---

## 8. 异常处理关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `try` | 异常 | `try:` | 异常捕获块起始 | `try: risky()` |
| `except` | 异常 | `except [Exc [as e]]:` | 捕获指定异常 | `except ValueError as e: ...` |
| `finally` | 异常 | `finally:` | 无论是否异常都执行 | `finally: cleanup()` |
| `raise` | 异常 | `raise [<exc>]` | 抛出异常 | `raise ValueError("bad")` |
| `with` | 异常/资源 | `with <ctx> as v:` | 上下文管理器 | `with open(f) as fh: ...` |

参见：`16-exceptions.md`。

---

## 9. 测试关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `suite` | 测试 | `suite Name:` | 测试套件定义 | `suite Math: ...` |
| `test` | 测试 | `test "<name>":` | 单个测试用例 | `test "add basic": assert add(1,2)==3` |
| `setup` | 测试 | `setup:` | 测试前置钩子 | `setup: self.data = []` |
| `teardown` | 测试 | `teardown:` | 测试后置钩子 | `teardown: close(self.fh)` |

---

## 10. 布尔值

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `True` | 布尔 | `True` | 布尔真值 | `let ok = True` |
| `False` | 布尔 | `False` | 布尔假值 | `let ok = False` |

---

## 11. 其他关键字

| 关键字 | 类别 | 语法 | 说明 | 示例 |
|--------|------|------|------|------|
| `pass` | 其他 | `pass` | 空语句占位 | `def f(): pass` |
| `del` | 其他 | `del <name>` | 删除变量/属性 | `del x` |
| `not` | 逻辑 | `not <expr>` | 逻辑非 | `if not ok: ...` |
| `and` | 逻辑 | `a and b` | 逻辑与（短路） | `if a and b: ...` |
| `or` | 逻辑 | `a or b` | 逻辑或（短路） | `if a or b: ...` |
| `assert` | 调试 | `assert <cond> [, msg]` | 断言 | `assert x > 0, "must be positive"` |
| `mut` | 内存 | `mut name [: T] = expr` 或 `param: mut T` | 可变变量声明 / 参数修饰符 | `mut x: int = 10` |
| `owned` | 内存 | `owned <name>` 或 `param: owned T` | 独占所有权 | `def consume(x: owned Buf): ...` |
| `lambda` | 函数 | `lambda params: expr` | 匿名函数 | `let f = lambda x: x + 1` |
| `global` | 作用域 | `global <name>` | 声明全局变量 | `global counter; counter += 1` |
| `nonlocal` | 作用域 | `nonlocal <name>` | 声明外层函数变量 | `nonlocal x; x += 1` |

参见：`12-operators.md`、`04-pointer-types.md`、`07-trait-impl.md`。

---

## 关键字速查表（按字母序）

```
and       as        assert    async     await     break     case
class     comptime  const     continue  def       defer     del
duck      elif      else      enum      except    extends   False
finally   for       from      global    go        guard     if
impl      import    in        is        lambda    let       macro
match     meta      mut       Never     nonlocal  not       or
owned     pass      raise     return    setup     spawn     struct
suite     test      teardown  trait     True      try       type
typeclass vec       while     with      yield
```

## 备注

1. **`def` 是统一函数入口**：有类型注解 → 生成 `cpdef` 优化代码；无注解 → 退化为 `PyObject`（仍是 Cython 代码，非纯 CPython 回退）。
2. **`cdef` 由代码生成层自动处理**：Cypy 源码中不再使用 `cdef` 关键字，编译器在生成 Cython 代码时自动插入相应的 `cdef` 声明。变量声明请使用 `let`/`mut`/`const`。
3. **`meta` 双重用途**：既属于类型系统（元编程块），也属于元编程关键字，依据上下文区分。
4. **`and`/`or`/`not`/`is`/`in`** 在词法层是关键字，但在语法层作为运算符使用，参见附录 B。
5. **`vec` 关键字与 `vec!` 宏调用**：`vec` 单独用于类型 `vec[T; N]`；`vec!` 是 `vec` + `!`（BANG），用于 SIMD 字面量。
