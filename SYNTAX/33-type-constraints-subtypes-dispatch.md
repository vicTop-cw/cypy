# 命名约束 / 名义子类型 / 多方法分派（constraint · subtype · dispatch）

> **FIST 任务**：`T0r258.1.1`（constraint）、`T0r258.2.1`（subtype）、`T0r258.3.1`（dispatch）
> **文件性质**：**语义规范 + 期望行为探针**。本轮（R2 单元 1）**只定规矩、只交红探针**，
> 不动 `cypyc/`、`cypy_bridge/`、`cypy_hook/` 任何生产代码。
> **实现状态**：三件套 **全部未实现（0/4 层）**。`constraint` 与 `dispatch` 目前会被**静默吞成普通标识符/函数调用**，
> `subtype` 目前在 parser 层硬失败。见 §0.2 实测原文。
> **机检**：本文每条带 ID 的「应该」都由 `Find_BUG/audit_2026q3/feat_<簇>_NN.py` 钉住，映射见 §6。

---

## 0. 定位与分工

### 0.1 与既有文档的分工（不冲突声明）

| 文档 | 管什么 | 与本文的关系 |
|------|--------|-------------|
| `27-constraints.md` | **已实现**的 `duck` 约束：`meta:` 块里的**表达式约束**（`a < b -> bool`、`name: str`、`add(self, item: T)`），落 `_duck_registry`，**结构性**判定（"有没有这些成员"） | 本文**不碰、不改、不重新定义** `duck`。§2.6 只规定「`constraint` 成员名与 `duck` 约束名同时命中哪个注册表」的优先级，避免两套界检查互相覆盖 |
| `26-union-type.md` | 匿名联合类型 `A \| B` 的**类型表达式**语义（降级为 `object`） | `constraint` 的右端**是**联合类型表达式，但绑定到一个**有身份的名字**上，身份带来界检查（§2.2） |
| `12-type-alias.md` | `type Name = T`：**编译期替换**，名字对可赋值性透明 | 本文的 `constraint`/`subtype` 都是**有身份**的类型级声明；§2.3 给出与别名的命名空间冲突规则 |
| `11-generics.md` | 泛型参数与内联界 `T: int \| float`、`T: Comparable` | `constraint Name` 是把这种内联界**提取成命名单元**；§2.4 规定展开后必须与内联界同义（探针专项做了内联界的回归护栏） |
| `07-trait-impl.md` / `08-class.md` | 名义 trait + 显式 `impl`；class 继承 | §3.6 给出「为什么不直接用 class 继承」、§3.5 给出「subtype 上能否 `impl` trait」的裁决 |
| `03-type-conversion.md` | `as` 显式转换 | §3.3 的 downcast **复用 `as`**，不新增语法 |

**本文与 `27-constraints.md` 的关键分工（一句话）**：`duck` 回答「这个类型**会不会**这些操作」，
`constraint` 回答「这个类型**是不是**名单里的那一个」。前者结构性、后者名义性、互不替换。

### 0.2 实测基线（2026-09-26，`python -m cypyc transpile` + 直连 `cypy_hook.hook.transpile_file`）

```
$ python -m cypyc transpile <constraint 用例>
[FAIL] Transpile failed:                      # ← stderr
  - Undefined name 'constraint' at 1:1        # ← 不是语法错误，是"未知变量"
  - Generic constraint violation: type 'int' does not satisfy constraint 'Numeric' ... at 0:0
```

| # | 输入 | 当前实测行为 | 定性 |
|---|------|-------------|------|
| B1 | `constraint Numeric = int \| float` | 吞成 `ExprStmt(Name('constraint'))` + `Assign(Name('Numeric'), BinOp('\|', int, float))`；analyzer 只报 `Undefined name 'constraint'` | **静默吞**（最危险） |
| B2 | `constraint Numeric = int \| float` + `def f<T: Numeric>(x: T)` 用 `f(1)` | 报 `type 'int' does not satisfy constraint 'Numeric'` | 名不存在的界退化成"永不相等" |
| B3 | `def f<T: int \| float>(x: T)` + `f('a')` | 报 `does not satisfy constraint 'int \| float'` | 内联联合界**已可用**（正例基准） |
| B4 | `def f<T: int>(x: T)` + `f(True)` | **拒绝** `type 'bool' does not satisfy constraint 'int'`，而 `let x: int = True` **放行** | 两套判据不一致 |
| B5 | `class B(A)`；`def f<T: A>(x: T)` + `f(B())` | **拒绝**（子类不满足父类界） | 界检查未走 `inheritance_map` |
| B6 | `def f<T: list>(x: T)` + `f([1,2])` | 放行；`T: list<int>` + `f([1,2])` **拒绝** | 泛型界带实参即失效 |
| B7 | `def f<T: A + B>(x)` | parse 抛 `Expected IDENTIFIER, got PLUS at 1:18` | 无诊断、只有词法抱怨 |
| B8 | `def f<T: (A, B)>(x)` | **静默接受**，`generic_constraints['T']` 变成 `Constant` | **静默吞**（次危险） |
| B9 | `type N = int` + `type N = str`（及 `struct N` + `type N`） | **双双通过**，无重名诊断 | 别名命名空间无护栏 |
| S1 | `subtype Meter <: int` | parse 抛 `Unexpected token SUBTYPE at 1:15` | `<:` token 已存在（`lexer.py:32,786`）但 parser 从不消费 |
| S2 | `type Meter = int` 后 `let i: int = m`（m: Meter） | **放行**（别名双向可赋值，非名义） | 现替代品给不出 §3.3 的方向性 |
| D1 | `dispatch area(x: int) -> int` | parse 抛 `Expected RPAREN, got COLON at 1:16` | |
| D2 | `dispatch area(x)`（无注解无返回） | 吞成 `ExprStmt(Name('dispatch'))` + `ExprStmt(Call(area,[x]))` | **静默吞** |
| D3 | `def dispatch(x)` / `dispatch = 7` / `dispatch(1)` | **全部通过**（`dispatch` 非保留字） | 关键字化会破坏既有代码，见 §2.7 |
| X1 | `python -m cypyc transpile <坏文件>` 的退出码 | **exit 0**（`cypyc/__main__.py:4` 丢掉了 `main()` 返回值；`python cypyc/cli.py` 才返回 1） | **判据陷阱**，见 §7 D-0 |
| X2 | `def f(x: int)->int` 与 `def f(x: str)->int` 同名共存 | `Name 'f' is already declared in this scope (line 4, col 5)`（`scope_analyzer.py:132-142`） | **Cypy 今天没有重载**，dispatch 的昂贵由此而来（§4.5 第 1 条） |
| X3 | `let x: int = True` | **放行**（`_is_subtype` 的 `bool<int<float<double` 数值序） | 与 B4 直接矛盾 → C-2.2 统一判定入口的理由 |
| X4 | `isinstance(v, <subtype 名>)`（假设 subtype 已实现且 codegen 什么都不发） | 会被 `cython_generator.py:548-564` 的 `_cypy_is_instance_of` 兜底成 `globals().get('Meter') is None -> return False` —— **恒假的静默误判** | S-4.3 必须编译期报错，不能放行 |
| X5 | `python -m cypyc run <坏文件>` | 打印 `[FAIL] Execution failed:` 后仍 exit 0 | `scripts/e2e_golden.sh:51-58` 的 RUNFAIL 分支因此是死代码 |


> X1 对所有探针的写法有硬约束：**探针不许依赖 `python -m cypyc` 的退出码判成败**，
> 必须读 `cypy_hook` 返回的结构化 `errors` 列表 + 检查产物文件是否生成。全部 14 个探针都遵守此约束。
> 探针共用 `_feat_typesys_lib.py`（下划线开头，`repro_gate.py` 的 `{prefix}*.py` glob 不会把它当探针）。

### 0.3 判等基线（与上一轮 `Type.__eq__` 改动兼容）

`cypyc/analyzer/type_checker.py:5-37` 的现状：`Type.__eq__` 比较
`(name, is_pointer, is_ref, generic_params, union_members)`，且显式 `__hash__ = None`。

由此得到三件套都必须遵守的三条**不变式**（§6 有探针钉住）：

* **INV-1** 约束/子类型的**名字**进入 `Type` 时只能是 `Type.name`（subtype）或独立的注册表键（constraint），
  **不得**把成员塞进 `union_members` 之外的字段，否则 `__eq__` 判等会与 codegen 的 `object` 降级互相错位。
* **INV-2** 任何"两个类型是否等价"的判定**必须**走 `Type.__eq__` 或 `_is_subtype`，
  **禁止**再新增第四套基于裸 `str` 名字比较的分支（B4/B5/B6 的根因就是 `type_checker.py:2557`
  的 `if inferred_type.name in constraint_names` 直接比字符串，绕开了 `_is_subtype`）。
* **INV-3** `Type` 不可哈希（`__hash__ = None`），所以注册表键**必须是 `str`**（名字），
  不得把 `Type` 对象当 dict key —— `constraint_defs`/`subtype_defs` 的设计据此给出（§5）。

---

## 1. 语法总览

```python
# 命名联合类型约束（§2）
constraint Numeric = int | float | double

# 泛型界引用命名约束（§2.4）
def clamp<T: Numeric>(v: T, lo: T, hi: T) -> T: ...

# 名义子类型（§3）
subtype Meter <: float
subtype Kilometer <: float

# 多方法分派（§4，本轮 deferred）
dispatch area(x: Shape) -> float:
    arm Circle:
        return 3.14159 * x.r * x.r
    arm Square:
        return x.a * x.a
```

三条都是**顶层声明**（与 `type`/`class`/`struct`/`trait`/`enum` 同级），
不允许出现在函数体、`meta:` 块或任何缩进块内。

---

## 2. `constraint Name = A | B | C` —— 命名联合类型约束

### 2.1 语法（C-1）

```
ConstraintDecl ::= 'constraint' IDENTIFIER '=' TypeList NEWLINE
TypeList       ::= TypeExpr ( '|' TypeExpr )*
TypeExpr       ::= IDENTIFIER [ '<' TypeList '>' ]        # 只允许"名字 [+ 实参]"
```

* **C-1.1** 成员数 ≥ 1；0 成员（`constraint E =`）是语法错误。
* **C-1.2** 每个成员必须是**类型名**（内置标量 `int/float/double/bool/str/bytes/None/object/Any`、
  已声明的 `class`/`struct`/`enum` 名、已声明的另一个 `constraint` 名、已声明的 `subtype` 名）。
  成员**不是**任意类型表达式：`*int`、`[T]`、`{k: v}`、字面量类型一律拒绝。
* **C-1.3** 成员名去重后按**声明顺序**保留，用于诊断文案（§2.5 要打印成员表）。
* **C-1.4** 跨行续写只允许用括号 `( ... )`？——**不允许**，见 §2.6：括号形式今天会被静默吞成 `Constant`（B8）。

### 2.2 语义（C-2）

* **C-2.1 它是界，不是类型。** `Numeric` **不得**出现在任何值类型位置：
  `let x: Numeric = 1`、`def f(v: Numeric)`、`list<Numeric>`、`as Numeric` 全部必须**编译期报错**：

  ```
  error at <file>:<line>:<col>: 'Numeric' is a constraint, not a type: it can only appear as a generic
    bound 'T: Numeric'. For a usable union type write 'type Numeric = int | float'.
  ```

  理由（也是与别名的分工）：联合类型在当前 codegen 里降级为 `object`（`26-union-type.md`），
  别名可以替换成 `object`，而约束**没有可替换的目标**——它的"展开"是一组**候选类型**，
  不是单个类型。把二者混在一起就会得到 B2 那种"int 不满足 Numeric"的假报错。
  探针：`feat_constraint_03`。

* **C-2.2 满足关系（satisfaction）**：对泛型实参类型 `A` 与约束 `N`，

  ```
  A satisfies N  ⟺  ∃ m ∈ members(N) : _is_subtype(A, m)     # 复用 type_checker.py:1985
  ```

  **必须**走单一判定入口 `_is_subtype`（INV-2），由此一次性修掉 B4/B5/B6 三处不一致：

  | 情形 | 规定结果 | 现状 | 依据 |
  |------|---------|------|------|
  | `int` vs 成员 `int` | 满足 | 满足 | 恒等 |
  | `bool` vs 成员 `int` | **满足** | **不满足**（B4） | `_is_subtype` 的 numeric_order `bool<int<float<double` |
  | `float` vs 成员 `int` | 不满足 | 不满足 | 同上（加宽只向上） |
  | `B`（`class B(A)`）vs 成员 `A` | **满足** | **不满足**（B5） | `_is_subtype` 的 `inheritance_map` 分支 |
  | `list[int]` vs 成员 `list` | **满足**（头部名匹配即满足） | 满足 | `Type.name == 'list'`，`generic_params` 不参与 §2.2 判定 |
  | `list[int]` vs 成员 `list<int>` | **满足**（元素类型当前**不检查**） | **不满足**（B6） | 见 §2.2.1 的 deferred |
  | `str` vs 成员 `int \| float` | 不满足 | 不满足 | 一致（基准行为 B3） |
  | 成员是已声明 `duck` 约束名 | 满足 ⟺ `_type_satisfies_duck`（结构判定） | 部分可用 | 与 `27` 的分工见 §2.6 |
  | 成员是 `Any`/`object` | 恒满足（top） | — | |
  | 成员是 `Never` | 恒不满足（bottom） | — | |

  * **2.2.1 `deferred`**：泛型成员（`list<int>`、`dict<str, T>`）的**元素类型一致性检查**不在本轮定稿。
    理由：`Type.generic_params` 当前在 codegen 里被整体丢弃（`ctypedef object`），
    元素级检查会造成"编译期拒绝、产物里根本没有这个信息"的空转判据。列入 §7 **D-2**。
    **规范现状**：带实参的成员只比较头部名；这是**明写的宽松**，不是隐藏缺陷。

* **C-2.3 传递性**：成员允许是另一个 `constraint` 名，按**成员并集**展开（`constraint A = int | float`、
  `constraint B = A | str` ⇒ `B` 的成员是 `int, float, str`）。
* **C-2.4 环检测**：`constraint A = B | int; constraint B = A | str` 必须报错，
  且**必须**指名环路径：

  ```
  error: circular constraint definition: A -> B -> A
  ```

* **C-2.5 未定义成员**：

  ```
  error at <file>:<line>:<col>: constraint 'Numeric' references undefined type 'Intg' (not a builtin,
    class, struct, enum, subtype or constraint in this module)
  ```

  探针：`feat_constraint_06`（含环与未定义成员）。

### 2.3 与 `type` 别名的命名空间（C-3）

* **C-3.1 禁止同名。** `constraint`、`type` 别名、`subtype`、`class`、`struct`、`enum`、`trait`、
  `typeclass` 共用**一个模块级名字空间**（`scope_analyzer` 的 `current_scope.symbols`）。
  重名即报错，**后声明者被拒**：

  ```
  error at <file>:<line>:<col>: redefinition of 'Numeric': it is already declared as a constraint
    at <file>:<first_line>:<first_col>. A constraint and a type alias cannot share a name --
    'type Numeric = ...' is transparent to assignability, 'constraint Numeric = ...' is not.
  ```

  这条**顺带修掉 B9**：`scope_analyzer._user_def_kinds`（`scope_analyzer.py:54`）当前是
  `{'function','class','struct','trait','typeclass','enum'}`，**不含 `'type'`**，
  所以两个 `type N = ...` 互相静默覆盖（`add_symbol` 是无条件 `symbols[name] = symbol`，
  `scope_analyzer.py:20-23`）。实现单元必须把 `'type'` 与新增的 `'constraint'`/`'subtype'` 一起纳入
  `_user_def_kinds`。**注意**：这会让既有代码里"故意重名覆盖别名"的写法开始报错 ——
  列入 §7 **D-1**（需 owner 裁决：立即收紧 / 先 warning 一轮）。
  探针：`feat_constraint_03`（constraint × type 同名）与 `feat_subtype_04`（subtype × class 同名）。

* **C-3.2 二者可以互相引用但不等价**：

  ```python
  type Numeric = int | float        # 可用于值位置；对可赋值性透明（Meter 版的 int 也算 int）
  constraint Range = int | float    # 只能用于 T: Range；有身份（诊断里指名 'Range'）
  ```

  同一模块内两套都允许存在，只要**不同名**。规范给出的选型口诀：
  **要写类型 → `type`；要写界 → `constraint`；两个都要 → 写两遍不同名。**

### 2.4 用作泛型界（C-4）

* **C-4.1** `def f<T: Numeric>(x: T)` 与把成员**就地内联**（`def f<T: int | float>`）**必须同义**：
  同一个实参在两种写法下必须得到同一判定与**同一模板**的诊断（只差约束名那一栏）。
  这是防止"命名约束做成 parser 能吃、analyzer 无视的假实现"（R2 任务包 §四 明令禁止）的核心判据。
  探针：`feat_constraint_02` 的 case 3 做内联界回归护栏（B3 现状已可用，必须不退化）。
* **C-4.2 检查时机 = 每个调用点**（现在 `type_checker` 已有的 `_visit_Call` 路径，
  `type_checker.py:929` / `:1908` 两处，实单元需确认这两条路径共用同一入口函数，不得新增第三处）。
* **C-4.3 泛型参数被显式指定时同样检查**：`f<Numeric>(...)`、`f<int>(...)`。
* **C-4.4 违反界 = 编译期错误，禁止静默降级为 `object`。** 探针：`feat_constraint_02`。

### 2.5 违反界的诊断模板（C-5）

唯一模板（字段名固定，探针用正则逐字段核对）：

```
error at {file}:{line}:{col}: constraint violation: type '{actual_type}' does not satisfy constraint
  '{constraint_name}' (allowed: {member_1} | {member_2} | ...), in call to '{callee_name}'
  declared at {decl_file}:{decl_line}:{decl_col}
```

硬性要求：

* **C-5.1 位置必须是调用点的真实行/列**。当前 `at 0:0`（B1/B2 原文里就有）是**不可接受的**，
  因为 `0:0` 让 IDE 与增量编译无法定位；探针直接拒绝含 ` at 0:0` 的诊断。
* **C-5.2 必须展开成员**（`(allowed: int | float)`），不能只说 `'Numeric'` —— 命名约束的价值就在
  "报错时把名单摊开给用户看"，否则与 `type` 别名相比没有增益。
* **C-5.3 `{actual_type}` 必须是推断后的类型名**（`bool`/`int`/`str`/`B`/`list`），不是 `object`。
* **C-5.4 兼容**：现有 `Generic constraint violation:` 前缀在既有测试里**零断言**
  （`grep -rn "does not satisfy" tests/ test_suite/` → 0 命中），
  因此实现单元可以直接换成 C-5 模板，但**必须保留** `does not satisfy constraint '<name>'`
  这段子串以便 `--emit-code` 日志与热重载告警继续可 grep。
* **C-5.5 多个实参同时违例 → 报第一条并停止该调用点的后续界检查**（避免一次泛型调用刷 5 行）。

探针：`feat_constraint_04`。

### 2.6 多界组合：明确**不支持**（C-6）

**本轮决定：不支持。** 具体规定：

| 写法 | 规定 | 现状 |
|------|------|------|
| `T: A + B` | **不支持**，必须报"多界不支持"的定向诊断（§2.6.1） | parse 抛 `Expected IDENTIFIER, got PLUS`（B7） |
| `T: A & B` | **不支持**，同上 | parse 抛 `Expected IDENTIFIER, got DEREF` |
| `T: (A, B)` | **不支持**，同上；**当前是静默接受，必须变成硬错误** | `generic_constraints['T']` 变成 `Constant`（B8） |
| `T: A, U: B`（各参数独立界） | **支持**（已有能力，探针做回归护栏） | 正常 |
| `constraint Both = Alpha & Beta` | **不支持**；替代方案=手工把成员摊平进一个 `constraint`，或用 `duck`（`27-constraints.md` 的"组合约束"是 `duck` 的能力，本文不重复造） | 无 |

* **2.6.1 定向诊断**：

  ```
  error at <file>:<line>:<col>: multiple generic bounds are not supported: got 'A + B'.
    Use one constraint name, or an inline union 'T: int | float', or a 'duck' constraint for
    structural requirements (see SYNTAX/27-constraints.md).
  ```

  即：拒绝时必须**指名替代方案**，不能只留词法错误。
* **2.6.2 为什么不做**：交集界需要"成员集合 ∩ 成员集合"的可满足性判定，
  而 §2.2 的 `satisfies` 依赖 `_is_subtype`；两个不同 class 的交集在 Cypy 里
  没有运行时表示可承载（无多重继承运行时 vtable 合并），会退化成"编译期看似严格、产物无差别"。
  列入 §7 **D-3**（若 owner 要，需先定 class 多继承）。
* **C-6 与 `27-constraints.md` 的接口**：`27` 的 `duck` 组合（`duck Ordered: Comparable; a <=> b -> int`）
  继续由 `27` 管；本文只规定**当界名同时存在于 `duck_constraints` 与 `constraint_defs` 时**的优先级：
  **`constraint_defs` 优先**（名义优先于结构），并报 warning 说明遮蔽。

### 2.7 关键字化与向后兼容（C-7）

`constraint`/`subtype`/`dispatch` 三个词当前都**不是**关键字（`lexer.py:160-223` 的 `KEYWORDS` 里没有），
且实测 `dispatch = 7`、`def dispatch(x)`、`print(constraint)` 全部可用（D3）。

* **C-7.1** 实现单元必须把 `constraint` / `subtype` 两词加入 `KEYWORDS`，并**同步提供**保留字清单更新
  （`SYNTAX/appendix-A-keywords.md`）。`dispatch` **本轮不进** `KEYWORDS`——它随 F3 的下一轮实现一起进，
  提前进只得到一个能被词法识别却无人解析的悬空关键字（裁决见 §7.1 D-4）。
* **C-7.2** 关键字化是**破坏性变更**：既有 `.cypy` 里把这三个词当变量/函数名用的代码会开始报语法错。
  本文**倾向直接破坏**，依据是全库实测（`grep -rlE '\b(constraint|subtype|dispatch)\b' --include='*.cypy'
  examples Find_BUG tests` → 10 个文件命中，逐条核对**全部**落在注释、字符串字面量或
  `Find_BUG/audit_2026q3/fixtures/` 的负例语料里，没有一处把它们当标识符）；实现单元必须在动 lexer 前
  **重跑**这条 grep 并把结果写进交付物（清单见 §7.1 D-4）。裁决见 §7 **D-4**。
* **C-7.3** 若 owner 选择"软保留字"（仅在行首 `constraint NAME =` 形态下识别），
  则 §2.1 的语法必须补一条形态限定，并且探针 `feat_constraint_01` 的 case 2
  （`constraint = 5` 必须报错）需要相应放宽。**这是两种互斥设计，只能选一种。**

### 2.8 四层落点（见 §5 汇总表）

---

## 3. `subtype Name <: Base` —— 名义子类型

### 3.1 语法（S-1）

```
SubtypeDecl ::= 'subtype' IDENTIFIER '<:' IDENTIFIER NEWLINE
```

* **S-1.1** 单继承、无 body、无泛型参数（`subtype Box<T> <: T` 不支持，deferred）。
* **S-1.2** `Base` 必须是已声明类型名：内置标量（`int/float/double/str/bytes/bool`）、
  `class`、`struct`、`enum`，或另一个 `subtype` 名。
  **不允许**：联合类型、泛型应用（`list<int>`）、`constraint` 名、`trait` 名、`type` 别名
  （别名在 `_get_type_from_node` 里会被替换掉目标，身份判定会随别名定义漂移，见 **D-5**）。
* **S-1.3** 自引用 `subtype X <: X` 报错；环（`A<:B`, `B<:A`）报错并打印路径，同 C-2.4 模板。
* **S-1.4** 词法侧零成本：`<:` 已是 `TokenType.SUBTYPE`（`lexer.py:32`，产出于 `lexer.py:786`），
  但 parser **从不消费**它 —— 这就是 S1 硬失败的根因，也是实现单元的最小改动点。

### 3.2 语义（S-2）

* **S-2.1 名义 + 结构同构**：`Meter` 与 `Base` 在**所有结构操作**上完全等同 `Base`
  （字段、方法、运算符、`+`、`len()`、codegen 的 C 类型），**只有类型身份不同**。
  `Type` 层面 = `Type("Meter")`，即 `name` 换成子类型名，其余字段照搬 `Base` 的
  （`is_pointer/is_ref/generic_params/union_members` 全等，INV-1）。
* **S-2.2 `_is_subtype` 是唯一真源**：注册时把 `Meter` 并入 `inheritance_map`
  （`type_checker.py:94` 已有的 `Dict[str, List[str]]`），于是
  `_is_subtype(Meter, Base)`（`type_checker.py:2005` 现成的 `inheritance_map` 分支）自然成立。
  **禁止**为 subtype 新增第二套可赋值判定（INV-2）。
* **S-2.3 约束满足联动**：`constraint M = Meter` + `f(Base 值)` **必须不满足**（名义不放宽），
  但 `constraint M = Base` + `f(Meter 值)` **必须满足**（S-2.2 的必然推论，探针 `feat_subtype_02` 钉住）。

### 3.3 可赋值方向（S-3）

```
Meter → float（基类型）           隐式，允许
float → Meter（子类型）           **必须显式转换**
其他 subtype → Meter（兄弟）      禁止（即使两步 as 也不给直转，见 S-3.3）
Meter → object / Any             隐式，允许（top）
```

* **S-3.1 upcast 隐式**：`let v: float = m`（`m: Meter`）必须放行 —— 复用 `_is_subtype`，现状已具备。
* **S-3.2 downcast 用 `as`，不新增语法**：`let m: Meter = x as Meter`（`x: float`）。
  理由：`03-type-conversion.md` 已把 `as` 定为唯一显式转换运算符，
  再造 `Meter(x)`（会被解析成 Call）或 `@Meter x`（与装饰器 `@` 冲突）都会引入歧义。
  **S-3.2.1** 无 `as` 的 `let m: Meter = x` 必须报错：

  ```
  error at <file>:<line>:<col>: cannot assign 'float' to 'Meter': 'Meter' is a nominal subtype of
    'float'; downcast requires an explicit 'x as Meter'
  ```
* **S-3.3 兄弟不可互转**：`Meter`/`Kilometer` 同基 `float`，`m as Kilometer` **必须报错**：

  ```
  error: cannot cast 'Meter' to 'Kilometer': nominal subtypes of the same base are not mutually
    comparable; cast through the base 'float' in two steps if that is really what you mean
  ```

  理由：单位/货币/索引这类 subtype 的**存在意义就是防止兄弟混用**；允许直转就等于没做。
  两步 `m as float as Kilometer` **允许**（显式承认"我知道我在跨单位"）。
  探针：`feat_subtype_02`。
* **S-3.4 现替代品不满足本条**：`type Meter = float` 时 `let v: float = m` 与 `let m: Meter = x`
  **双向都静默通过**（实测 S2），因为别名对可赋值性透明。这正是 `subtype` 不能被 `type` 替换掉的证据。

### 3.4 运行时表示（S-4）—— 明确：**零变化**

* **S-4.1** `subtype Meter <: float` 生成的 `.pyx` 里 **MUST NOT** 出现新的类型对象：
  不发 `ctypedef`、不发 `cdef class`、不发注册表。codegen 侧 `Meter` 在**类型标注位置**
  一律渲染成基类型名（`float`），因此 C 层与 `type Meter = float` 产物**逐字节同构**。
  （对比：`type` 别名当前发 `ctypedef object Num`，`cython_generator.py:3269-3291`。）
* **S-4.2** 推论：`type(m).__name__` 在运行时**就是基类型的名字**（`'float'`），不是 `'Meter'`。
* **S-4.3 `isinstance` 行为**（探针 `feat_subtype_03` 钉住）：
  * `isinstance(m, float)` → **True**（运行时表示未变，与 S-4.2 一致）。
  * `isinstance(m, Meter)` → **编译期报错**，因为 `Meter` 没有运行时类型对象：

    ```
    error at <file>:<line>:<col>: 'Meter' is a subtype with no runtime type object;
      use isinstance(m, float) or promote 'Meter' to a 'struct' if you need runtime identity
    ```

    理由（也是被否决的方案）：*让 `isinstance(m, Meter)` 恒真* 会让"运行时判定"与"零表示变化"
    自相矛盾（同基的兄弟 subtype 会**互相误判**）；*按 `_cypy_trait_registry` 的路子发运行时表*
    （`cython_generator.py:527-560` 有现成范本）则要求 `type(x).__name__` 变化 = 必须有运行时包装 = 违背 S-4.1。
    **要运行时身份就写 `struct`**，这是语言的唯一分界线。
  * `match`/`case` 的类型模式 `case m: Meter =>` 同 S-4.3 第二行处理（编译期报错）。
* **S-4.4** `as Meter` 的产物**必须**是 C 层的 no-op（因为两边同一 C 类型），
  只在 cypyc 的类型检查里"消耗"一次显式转换；codegen 不得插入运行时校验分支。

### 3.5 与 trait / `impl` 的边界（S-5）

* **S-5.1 v1 规定：`impl SomeTrait for Meter` 编译期拒绝。**

  ```
  error at <file>:<line>:<col>: cannot implement trait 'Show' for 'Meter': 'Meter' is a nominal
    subtype with no runtime identity (its runtime type is 'float'); implement 'Show' for 'float'
    instead, or declare 'Meter' as a struct
  ```

  技术理由（这是实测出来的硬约束，不是审美）：trait 的运行时判定
  `_cypy_is_instance_of` 用 `type(obj).__name__ in _cypy_trait_registry[trait]`
  （`cython_generator.py:550`）。`Meter` 的运行时名是 `float`，于是 `impl Show for Meter`
  会把 `Meter` 注册进表却**永远匹配不上**（静默失效）；
  若为了让它匹配而把键换成 `float`，就会连带把**所有** `float` 值都判成实现了 `Show`（语义泄漏）。
  两条路都坏，故拒绝。**列入 §7 D-6**（若 owner 要 trait 能挂 subtype，必须先给 subtype 运行时身份）。
* **S-5.2 `T: SomeTrait` 的界检查对 subtype 的行为**：沿用 `27-trait-impl.md` 的显式 `impl` 名单
  （`trait_impls`）；`Meter` 没有 `impl` 记录，所以**不满足**任何 trait 界 —— 与 S-5.1 自洽。
* **S-5.3 与 `duck` 的关系**：`duck` 是结构判定（成员名/操作符）。`Meter` 的结构 == `float` 的结构，
  所以 `duck Numeric`（`27-constraints.md` 的 `a + b -> Self`）对 `Meter` **必须判定为满足**——
  这是 S-2.1"结构同构"的必然结果，探针 `feat_subtype_05` 把它钉成期望，
  并在实现前用**当前**能跑通的 struct 同构体做对照（subtype 未实现，故该探针 exit 1）。

### 3.6 为什么不直接用 class 继承（S-6）

| 维度 | `class B(A)` | `subtype Meter <: float` |
|------|-------------|--------------------------|
| 运行时表示 | 新类型对象、新 vtable、堆分配 | **零变化**（S-4.1） |
| 能否给内置类型派生 | 不能（`class Meter(int)` 会产生包装对象，破坏 C 层 `double` 表示） | **能**，这是唯一动机 |
| 可赋值性方向 | 双向都宽松（`A()` 赋给 `B` 变量当前无护栏） | 严格单向（§3.3） |
| 加字段/加方法 | 能 | **不能**（无 body，S-1.1） |
| 运行时 `isinstance` 身份 | 有 | **无**（S-4.3） |
| 适用场景 | 多态、共享实现 | **单位 / 权限 / 语义标签**（`Meter`、`UserId`、` Celsius`） |

**选型规则写进规范**：需要"同一种表示、不同的身份"→ `subtype`；
需要"不同的表示或共享实现"→ `class`；需要"编译期单位混用检查"→ `subtype` + §3.3。

### 3.7 链式 / 重名 / 未声明基类型（S-7）

* **S-7.1 链式** `subtype A <: B; subtype B <: float` 支持，`A → B → float` 传递隐式 upcast；
  `float → A` 仍需 `as`（§3.3）；`as` 跨级（`A as float`）**允许**（沿链向上一路都是 upcast 的逆，
  显式即放行）。
* **S-7.2 深度上限 8**：超过即报 `error: subtype chain too deep (limit 8): A -> ... -> H`。
  理由：`_is_subtype` 沿 `inheritance_map` 递归，必须有硬上限防环/防退化链。
* **S-7.3 未声明基类型**：

  ```
  error at <file>:<line>:<col>: subtype 'Meter' refers to unknown base type 'Flaot'
  ```
* **S-7.4 重名**：与 §2.3 C-3.1 同一规则、同一模板（`redefinition of 'X': it is already declared as a ...`）。

---

## 4. `dispatch name(params) -> ret` —— 多方法分派（**本轮 DEFERRED，仅成交付提案**）

> **状态（2026-09-26 定稿，叶子 `T0r258.3.2`）**：本节正文已由"提案"改写为**可开工的定稿规范**——
> 语法（P-1）、静态语义（P-2/P-3）、诊断模板（§4.4.1）、四层落点（§5 总表 + §4.7 开工清单）、与既有机制的交互（P-5）
> 全部闭合；§7.1 的三条裁决已落成具体条款而不再被重开：**D-7 `arm` 块** → P-1'.6 + §4.6 第 5 条，
> **D-8 单键** → P-2.1 + P-2.6 + D-mlt，**D-9 禁止 `subtype` 做分派键** → P-2.3（白名单形式）+ D-key。
> **DEFERRED 的是实现，不是规范**（标题原样保留）。一句话理由：
> **本轮把 `dispatch`/`arm` 送进 `KEYWORDS` 只会得到一个 parser 能吃、analyzer/codegen 无人服务的悬空关键字**
> （任务包 F3 边界原文「不做半实现、不留悬空关键字」；§7.1 D-4 本轮只放行 `constraint`/`subtype` 两词），
> 而四层同时到位必须先付 §4.5 列出的 8 项代价（重载表 / 运行时类型标签 / 继承闭包 / 跨 TU 合并 / 产物判据）。
>
> **零实现的可复核证据**（纯静态 grep，本轮**没有**跑过任何编译管线，见 §8 变更记录的"不实测"声明）：
>
> ```
> $ grep -rn "dispatch" cypyc/ | wc -l        # 整个编译器里连这个词都不存在
> 0
> ```
>
> 探针状态：`feat_dispatch_01/02/03` 当前全部 **exit 1 = 未实现**（判据命令与三态约定见 §6 开头）。
> 实现前的实测原文一律**引用已落盘记录**，不在本叶子重新测量：
> `feat_dispatch_01.py:36-59`（四种形态的当前 parse 结果 + 同名 `def` 的控制组）、
> `feat_dispatch_03.py:33-39`（`_check_redefinition` 拦下同名重载的原文）、
> `fixtures/feat_type_system/_measured_cli.txt:21-23`（`读取文件错误: Expected RPAREN, got COLON at 4:16`）。
> **任何把 §4 当作"已可实现 / 已完成"的判断都属越界；下一轮开工顺序与验收判据 = §4.7。**

### 4.1 语法与形状（P-1，**定稿**）

```python
dispatch area(x: Shape) -> float:
    arm Circle:
        return 3.14159 * x.r * x.r
    arm Square:
        return x.a * x.a
    else:
        return 0.0
```

```
DispatchDecl ::= 'dispatch' IDENTIFIER '(' ParamList ')' ['->' TypeExpr] ':' NEWLINE
                 INDENT Arm+ [ElseArm] DEDENT
ParamList    ::= Param (',' Param)*                  # 复用 parser._parse_params（parser.py:1146），≥1 个参数
Arm          ::= 'arm' TYPE_NAME ':' NEWLINE INDENT Stmt+ DEDENT      # 恰好一个类型名，无逗号表
ElseArm      ::= 'else' ':' NEWLINE INDENT Stmt+ DEDENT              # 至多一条，且必须在最后
```

* **P-1.1 头行 = 分派槽签名**：名字、参数名与**静态上界类型**、返回类型。**第 1 参数必须带类型注解**
  （它就是分派键的上界），缺注解即报 D-hdr（§4.4.1）。返回注解可缺省 ⇒ 入口函数按 `object` 返回
  （与 `def` 无注解的现有处理同构）。参数表**复用** `Param` 节点与 `_parse_params`
  （`cypyc/parser/parser.py:233`、`:1146`），因此默认值 / `mut` / 关键字参数这些形态今天就能用，**不新增形态**。
* **P-1.2 `arm` 只带一个类型名**（**D-8 裁决的直接后果**）：`arm Circle:` 合法；`arm Circle, Square:`、
  `arm A, B:` 是**语法错误**，模板 D-mlt。多参数全键分派（true multi-methods）本轮与下一轮都**不做**；
  现有探针 `feat_dispatch_02.py:57-72` 接受"要么能用、要么指名拒绝"，本条把答案钉成**拒绝**。
* **P-1.3 至少 1 条 arm**（0 条 = D-empty），`else:` 至多一条且必须位于最后（否则 D-stray 的同族 D-ord，
  见 §4.4.1）。
* **P-1.4 只能出现在模块顶层**：复用 `Parser._require_module_level("dispatch", token)`
  （`cypyc/parser/parser.py:838-841`，`struct` 已在用同一函数）⇒ D-mlvl。
* **P-1.5 `arm` 不是通用语句（反悬空关键字条款，本条是 D-7 的一半）**：`_parse_dispatch` **自己**消化
  INDENT/DEDENT 与 arm 循环（范本：`_parse_block` `parser.py:3711-3734`、`_parse_class_def` `:1266-1286`），
  **`_parse_statement` 只新增 `TokenType.DISPATCH` 一条分支**（`parser.py:1042-1043` 同位，紧接
  `TokenType.TYPE` 那条），**绝不新增 `TokenType.ARM` 分支**。于是游离的 `arm Circle:` 在顶层与函数体里
  都是语法错误，且必须是定向诊断 D-stray（"只在 `dispatch` 块内合法"），不能只留
  `Expected ... got ARM`。**词法侧无需新增缩进逻辑**：`:` 后紧跟换行即置 `_expect_indent`
  （`cypyc/parser/lexer.py:849-856`），`arm X:` 与 `class X:` 走同一条路径；arm 体仍受"每次 +4"约束
  （`lexer.py:456-460`），所以 §4.1 例子里 4/8 空格的两级缩进是必需的、不是风格。
* **P-1.6 名字空间（D-7 的另一半）**：槽名以 kind `'dispatch'` 进模块作用域
  （`ScopeAnalyzer.add_symbol` `cypyc/analyzer/scope_analyzer.py:20-23`，范本 `_visit_TypeAlias` `:507-514`），
  因此 `dispatch area(...)` 与 `def area` / `class area` / `type area` 同名**必须**被
  `_check_redefinition`（`scope_analyzer.py:132-142`）拒绝，沿用 §2.3 C-3.1 的
  `redefinition of 'X': it is already declared as a ...` 模板（D-name）。
  **`arm` 的类型名不占名字空间**（arm 是槽的分支，不是声明）。
  这条就是选 `arm` 块而不选"同名多 `def`"的技术理由：**"一名多物"被关在 `dispatch` 这一个构造里，
  `function` kind 的可重复性一个字都不用放开**，`_user_def_kinds`（`scope_analyzer.py:54-55`）只需追加
  `'dispatch'` 一项（与 D-1 已裁决纳入的 `'type'/'constraint'/'subtype'` 同一批改动）。
* **P-1.7 arm 体内的静态收窄**：第 1 参数在 `arm Circle:` 体内的静态类型 = `Circle`（不是头行的 `Shape`），
  其余参数 = 头行声明类型。落点：`_visit_DispatchDecl` 对每条 arm 压作用域并写
  `type_map[<第1参数名>]`，参数注册写法沿用 `_visit_FuncDef`（`type_checker.py:436` 起）；
  返回值检查沿用现有 `Return type mismatch: ...`（`type_checker.py:757-796`），不新增模板。
  **附带事实（防下一轮踩空）**：analyzer 今天**没有任何成员存在性诊断**
  （`grep -rn "not found on type\|has no attribute" cypyc/analyzer/` → 0 命中，2026-09-26 静态核对），
  所以 `x.r` 拼错不会在这里报错；P-1.7 只承诺"收窄后返回值与可赋值性判定成立"，**不承诺成员校验**。
* **P-1.8 v1 明确不支持（一律在 `_parse_dispatch` 里语法级硬拒绝，不做"能吃但无人管"）**：
  泛型 dispatch（`dispatch f<T>(...)`）、`<checker>` 参数检查站（`parser.py:1052-1057` 的 `def f<checker>` 形态）、
  class 内的 dispatch（P-1.4 已排除）、arm 体内再挂 `meta:` 块、`arm` 的别名写法 `arm x is Circle:`。
* **P-1.9 调用点能力边界（诚实条款）**：cypyc **今天对任何用户函数都没有实参类型 / 元数检查**
  （`_visit_Call` `type_checker.py:911` 只做"逐个 visit 实参 + 用 `type_map[func_name]` 给返回类型"；
  `grep -n "Argument\|missing argument\|number of arguments" cypyc/analyzer/type_checker.py` → 0 命中，2026-09-26）。
  因此 v1 的 dispatch 只承诺"**返回类型正确 + 选臂可观察**"，**不得**在规范里声称"其余参数参与静态检查"
  比 `def` 更强；调用点实参检查是独立缺口（§7 建议新增 D-10，见 §4.6 第 6 条）。
* **P-1' 已否决（D-7 裁决，不再重开）**：`@dispatch` 装饰 + 同名多 `def` 形态**不做**。
  实测代价：两个同名 `def` 今天就被 `_check_redefinition` 报
  `Name 'f' is already declared in this scope`（§0.2 表 X2 行；`feat_dispatch_01.py:57-63` 与
  `feat_dispatch_03.py:33-39` 各钉一次），走这条路必须先放开 `function` 的可重复声明，
  而那条护栏被 A2 基线的 1681 个测试间接依赖（锚点见任务包 §一）。

### 4.2 分派键（P-2）

* **P-2.1 v1 = 单分派键，取第 1 个参数的运行时类型**（裁决 D-8）；其余参数只参与**静态**类型检查，
  不进键。头行第 1 参数的注解就是该槽的**类型上界**（无注解 → D-hdr）。
* **P-2.2 运行时键的取值 = `type(arg).__name__`**，与 `cython_generator.py:550` 一带现有 trait
  判定同一套机制（可复用同一辅助函数），但 dispatch 的表**独立成表**，不与 trait 注册表混用。
* **P-2.3 arm 目标是一个白名单，不是任意类型表达式**：
  * 允许：头行上界的**后代闭包 ∪ {上界本身}** 内的 `class` / `struct` / `enum` 名；
  * **禁止 `subtype` 名**（裁决 D-9）—— 它在运行期与其基类型同身份（§3.4 零运行时表示，
    `feat_dispatch_03.py` 实测记录），`arm Meter:` 永不可达，故在**声明期**报 D-key（§4.4.1）；
  * 允许内置类型名（`int`/`float`/`str`/`bool`/`list`/`dict`），但只有当头行上界是
    `object`/`Any` 时才可能命中（见 P-2.4）。
* **P-2.4 内置类型没有共同用户基类**，所以对内置键分派时上界必须写 `object`/`Any`；
  此时**必须**存在 `arm object:` 或 `else:` 兜底，否则触发 P-4b（D-none）。
* **P-2.5 兜底分支的可达性是声明期结论**：只要上界不是任何 arm 的子集，就可能出现"谁都不匹配"，
  因此"无兜底"是**声明期硬错误**而不是运行期风险（模板 D-none）。
* **P-2.6 多参数全键分派（true multi-methods）本轮与下一轮都不做**（D-8）：
  歧义检测复杂度从 O(n) 升到 O(n·m) 且需要跨类型的格论判定，理由见 §4.5 第 3 条与 §4.6 第 6 条。

### 4.3 特化优先与歧义（P-3 / P-4）

* **P-3 最特化优先（most specific wins）**：对候选 arm 集合，按第 1 参数类型的
  **继承链深度**排序（越深越特化），取最深者；`Meter`（`subtype of float`）比 `float` 特化。
  平局规则：同深度且**不同名** → 落 P-4 歧义错误。
* **P-4 编译期歧义 = 硬错误**：

  ```
  error at <file>:<line>:<col>: ambiguous dispatch for 'area': arms 'B' and 'C' are equally specific
    subtypes of 'Shape'; add a more specific arm or narrow the call
  ```

  歧义检测在**声明时**做（不需要调用点），因为 `class B(A)` / `class C(A)` 的兄弟关系是模块内静态信息。
  **注意**：跨模块分派槽（`dispatch` 在库 A，arm 在库 B）**当前无法检测** —— 见 §4.5 第 3 条。
* **P-4b 无兜底 = 硬错误**：分派槽被调用时可能收到不匹配任何 arm 的实参
  （因为头行只声明上界），所以必须有 `arm object:`/`else:`，否则声明期报错。

### 4.4 与既有机制的关系（P-5）

| 既有机制 | 与 dispatch 的关系（提案） |
|---------|--------------------------|
| `trait`/`impl`（`07-trait-impl.md`） | 语义重叠区 = "按类型选实现"。分工：**编译期选（trait，单态化到 `impl`）vs 运行期选（dispatch）**。同名冲突时报 `redefinition` |
| `duck`（`27-constraints.md`） | 不冲突：`duck` 是界检查谓词，不是实现选择器 |
| 魔术方法（`06d-builtin-magic-traits.md`：`__add__`/`__radd__` 等） | **不合并**。`a + b` 仍是"左操作数优先 + Python 反射调用"，不进 dispatch 表；否则每个 `+` 都要付出 §4.5 的运行时代价 |
| 重载（当前**不存在**） | 见 §4.5 第 1 条：Cypy 现在没有重载基础设施 |
| `match`（`17-pattern-matching.md`） | 类型模式 `case x: Circle =>` 已能表达"手写分派"。dispatch 的**唯一增益**是把这张表提到声明层、可被静态检查（歧义/无兜底）；否则建议用户直接用 `match` |

### 4.4.1 诊断模板（D-*，**全部在声明期**，模板 id 供 §4.7 与探针引用）

统一要求与 §2.5 的 C-5 完全一致：**必须带真实 `file:line:col`**（`at 0:0` 一律算不合格）、
**必须指名替代方案**、一个 dispatch 头只报第一条错误。以下模板里的 `{name}`/`{found}` 都是
编译期可得的静态信息，不需要运行期。

| id | 触发条件（条款） | 模板 |
|----|----------------|------|
| **D-hdr** | 第 1 参数无类型注解（P-1.1） | `error at {file}:{line}:{col}: dispatch key parameter '{param}' of '{name}' must be annotated (the annotation is the upper bound of the dispatch slot); write e.g. 'dispatch {name}(x: Shape)'` |
| **D-empty** | 0 条 arm（P-1.3） | `error at {file}:{line}:{col}: dispatch '{name}' has no arms; add at least one 'arm TYPE:' block or use 'def'` |
| **D-mlt** | `arm A, B:` 多类型表（P-1.2 / 裁决 D-8） | `error at {file}:{line}:{col}: dispatch arm of '{name}' takes exactly one type name, got {found}; multi-key dispatch is not supported -- write one 'arm' per type, or a union type alias 'type R = A \| B' plus an 'arm R:'... (rejected: arms must be single types)` |
| **D-ord** | `else:` 不在最后（P-1.3） | `error at {file}:{line}:{col}: the 'else' arm of dispatch '{name}' must be the last arm, found another arm at {file}:{other_line}:{other_col}` |
| **D-stray** | 游离的 `arm X:`（P-1.5，反悬空关键字条款） | `error at {file}:{line}:{col}: 'arm' is only valid inside a 'dispatch' block; found a stray "arm {found}:" -- wrap it in 'dispatch {name}(x: T) -> R:' or use 'match'` |
| **D-mlvl** | `dispatch` 出现在函数/class 体内（P-1.4） | `error at {file}:{line}:{col}: 'dispatch {name}' must be declared at module level (nested dispatch is not supported)` |
| **D-name** | 槽名与 `def`/`class`/`struct`/`type`/`trait`/`constraint`/`subtype`/`dispatch` 同名（P-1.6） | 复用 §2.3 C-3.1 的 `redefinition of '{name}': it is already declared as a {kind} at {file}:{line}:{col}`（由 `_check_redefinition` 出，不新增文案） |
| **D-amb** | 同深度兄弟 arm（P-4） | 见 §4.3 的 P-4 原文模板 |
| **D-none** | 无 `arm object:` 且无 `else:`（P-4b） | `error at {file}:{line}:{col}: dispatch '{name}' can receive a value matching no arm; add 'else:' or an 'arm object:' fallback` |
| **D-key** | arm 目标是 `subtype` 名（**裁决 D-9**） | `error at {file}:{line}:{col}: dispatch arm '{found}' is a subtype and has no runtime type identity in Cypy (SYNTAX/33 S-4); the runtime value is indistinguishable from its base '{base}' -- arm the base type instead` |

> `D-key` 是 §7.1 裁决 D-9 的落点：`subtype` 保持零运行时表示（§3.4 不动），因此
> `arm Meter:` **永不可达**这一实测矛盾（`feat_dispatch_03.py` 记录的就是它）在**声明期**被拒绝，
> 而不是靠给 subtype 装箱来解决。



### 4.5 为什么它比前两件贵（实测证据）

1. **没有重载基础设施**：`func_defs: Dict[str, FuncDef]`（`type_checker.py:102`，注册于 `:342`）、
   `scope_analyzer` 的 `symbols: Dict[str, Symbol]` 都是**一名一物**。
   引入 dispatch 要先决定"一名多物"的表示，这会触及 `_check_redefinition`（`:132`）这条
   被现有 1681 个测试间接依赖的护栏 —— 前两件（constraint/subtype）**完全不碰**这张表。
2. **必须有运行时类型标签**：`subtype` 的定稿是"零运行时表示"（§3.4），
   于是 `arm Meter:` 在运行时**无法**与 `arm float:` 区分（`type(x).__name__` 都是 `'float'`，S-4.2）。
   → 要么破掉 §3.4（给 subtype 发运行时包装，代价=每个内置值装箱），
   要么在 dispatch 里**禁止** subtype 做 arm（但那样 `dispatch` 对内置类型就只剩 `int/float/str/list` 这几个平铺键，
   价值有限）。**这个矛盾必须 owner 先解（D-9），它同时决定 §3.4 是否要改口。**
3. **跨模块**：`constraint`/`subtype` 的注册表是**模块内**的（`type_alias_defs` 同级，per-`TypeChecker` 实例），
   而 dispatch 的 arm 天然可跨模块添加 → 需要跨 TU 的分派表合并 + 增量编译依赖边
   （`cypyc/incremental/dependency_graph.py`），歧义检测（P-4）也要等全量 arm 才可靠。
4. **产物判据成本**：dispatch 的 golden 必须真的 `cypyc run` 出可观察输出才能钉住语义
   （单文件 e2e 实测 8.3s），负例（歧义）还要求"声明期"就报错 —— 比 constraint 的负例高一个数量级工作量。

### 4.6 能直接开工的最小切片（下一轮建议）

若 D-7/D-8/D-9 关账，按这个顺序做，每步都带自己的红→绿探针：

1. lexer 加 `dispatch`/`arm` 关键字（C-7.2 的 grep 结论复用）+ parser 出 `DispatchDecl(name, params, ret, arms)`
   → 绿 `feat_dispatch_01` case 1（当前 parse 抛 `Expected RPAREN, got COLON`）。
2. analyzer：分派槽注册表 + 歧义/无兜底/arm-非后代 三条声明期诊断 → 绿 `feat_dispatch_02`、`feat_dispatch_03`。
3. codegen：发 `_cypy_dispatch_<name>` 字典 + 入口 `def`，复用 `_cypy_is_instance_of` 的判定路径。
4. e2e：`examples/` 加**一个**（且只有一个）dispatch golden；`scripts/e2e_golden.sh` 与
   `examples/*.out` 只读，`--update` 必须逐行审定 diff（R2 红线）。
5. `D-key` 落地：arm 目标是 `subtype` 名时在声明期拒绝（裁决 D-9），并保证 §3.4 的
   「零运行时表示」条款不被装箱方案悄悄推翻（`feat_subtype_03` 钉的就是零表示）。
6. **不在 P0**：调用点实参类型 / 元数检查（P-1.9 的诚实条款 —— cypyc 今天对 `def` 也没有这项检查）。
   若 owner 要它，先裁 §7 新增的 **D-10**，因为它会同时改变 `def` 的行为，不是一个 dispatch 局部决定。

### 4.7 开工清单与验收判据（下一轮 P0 切片表）

每片都必须"红→绿"可机检；**禁止只做 S1/S2 而不做 S4/S6**（parser 能吃、analyzer/codegen 无人服务
= R2 任务包 §四 明令禁止的假实现）。

| 片 | 落点（现成锚点，复用不另造） | 红→绿判据 | 前置裁决 |
|----|------------------------------|-----------|----------|
| S1 lexer | `cypyc/parser/lexer.py`：`KEYWORDS`（`:160-223`）加 `dispatch`/`arm`，`TokenType` 加 `DISPATCH`/`ARM`（与 `:32` 的 `SUBTYPE` 同处声明） | `feat_dispatch_01.py` 的「`dispatch` 不再是普通标识符」与「`dispatch = 7` 现在必须报语法错」 | D-4（第二批保留字）、D-7 |
| S2 parser | `cypyc/parser/parser.py`：`DispatchDecl(name, params, ret, arms)` AST + `_parse_dispatch()`（自吞 INDENT/DEDENT，范本 `_parse_class_def` `:1266-1286`、`_parse_block` `:3711-3734`）+ `_parse_statement` 增**一条** `TokenType.DISPATCH` 分支（`:1042-1043` 同位）；模块级检查复用 `_require_module_level`（`:838-841`） | `feat_dispatch_01.py`：`dispatch area(x)` 今天被吞成两个 `ExprStmt`，必须变成 D-hdr/D-mlvl 硬错 | P-1 |
| S3 名字空间 | `cypyc/analyzer/scope_analyzer.py`：`add_symbol(name,'dispatch',node)`（`:20-23`，范本 `_visit_TypeAlias` `:507-514`）+ `_user_def_kinds`（`:54-55`）追加 `'dispatch'` | `feat_dispatch_01.py` 的同名冲突 case（走 D-name 模板，不新增文案） | D-7、D-1 已并入的同一批改动 |
| S4 声明期诊断 | `cypyc/analyzer/`：收集遍末尾做歧义/兜底/键类型检查（`type_checker.py` 与 `_check_redefinition` 平级位置） | `feat_dispatch_02.py` 三条：arm 非头行后代 / 同深度兄弟歧义 / 无兜底；再加 §4.4.1 的 D-hdr/D-mlt/D-empty/D-ord/D-stray/D-key | D-3、D-8、**D-9** |
| S5 arm 体静态收窄 | `cypyc/analyzer/type_checker.py::_visit_DispatchDecl`：逐 arm 压作用域写 `type_map[第1参数]`，返回检查沿用现有 `Return type mismatch`（`:757-796`） | `feat_dispatch_02.py` 的静态部分 + 不新增返回类型模板 | P-1.7 |
| S6 codegen | `cypyc/codegen/cython_generator.py`：发 `_cypy_dispatch_<name>` 表 + 入口 `def`，判定复用 `_cypy_is_instance_of`（`:550` 一带，与 trait 表同一套机制但**独立成表**） | `feat_dispatch_03.py`：运行期按第 1 参数选臂，最特化优先，输出可观察 | P-2、P-3 |
| S7 调用面 | `examples/` 恰好一个新语法 golden（`--update` 逐行审定 diff；`scripts/e2e_golden.sh` 只读） | A1 全绿且 `feat_anchor_01` 对该文件判「有约束力」（P≥1 且 G≥P） | R2 红线 |

---

## 5. 四层落点汇总（复用既有注册表，不另造）

| 层 | 现成范本（`type` 别名） | `constraint` 的对应物 | `subtype` 的对应物 | `dispatch` 的对应物（提案） |
|----|------------------------|----------------------|-------------------|---------------------------|
| **lexer** | `TokenType.TYPE` + `KEYWORDS["type"]`（`lexer.py:179`） | 新增 `TokenType.CONSTRAINT` + `KEYWORDS["constraint"]`（`KEYWORDS` 表 `lexer.py:160-223`） | 新增 `KEYWORDS["subtype"]`；**`<:` 的 `TokenType.SUBTYPE` 已存在**（`lexer.py:32`，产出 `:786`），只需被 parser 消费 | 新增 `TokenType.DISPATCH` + `ARM` |
| **parser** | AST `TypeAlias`（`parser.py:255`）、`_parse_type_alias`（`:2754`）、`_parse_statement` 分派 `if token.type == TokenType.TYPE: return self._parse_type_alias()`（`:1042-1043`） | AST `ConstraintDef(name, members: List[ASTNode], line, col)`；`_parse_constraint()`；`_parse_statement` 同一位置加分支 | AST `SubtypeDef(name, base, line, col)`；`_parse_subtype_def()`（内部 `_expect(TokenType.SUBTYPE)`） | AST `DispatchDecl(name, params, ret, arms)`；`_parse_dispatch()`（含 INDENT/DEDENT 的 `arm` 块） |
| **analyzer / scope** | `_visit_TypeAlias` → `add_symbol(name, "type", node)`（`scope_analyzer.py:507-514`）；`_user_def_kinds`（`:54`） | `_visit_ConstraintDef` → `add_symbol(name, "constraint", node)`；**`_user_def_kinds` 必须扩到 `{'type','constraint','subtype',...}`**（顺带修 B9，见 D-1） | `_visit_SubtypeDef` → `add_symbol(name, "subtype", node)` | `_visit_DispatchDecl` → `add_symbol(name, "dispatch", node)` + 允许 `arm` 不占名字 |
| **analyzer / type check** | `type_alias_defs: Dict[str, Any]`（`type_checker.py:109`）+ 注册 `:391-397` / `:1417` + 解析 `:2710` / `:2772`；界检查入口 `_check_generic_constraint`（`:2440`） | **新增 `constraint_defs: Dict[str, ConstraintDef]`（`str` 键，INV-3）**，注册位置/收集遍**照抄 `type_alias_defs` 那两处**；判定改造：`_check_generic_constraint` 的 `else` 分支（`:2550-2559` 的裸名字比较）改为"成员逐个 `_is_subtype`"（INV-2） | **不新增注册表**：把边写进现成的 `inheritance_map: Dict[str, List[str]]`（`type_checker.py:94`），由 `_is_subtype`（`:2005`）自动生效；可赋值性方向在 `LetStmt`/`Assign` 路径加一条"downcast 需 `as`"检查 | **新增 `dispatch_slots: Dict[str, DispatchDecl]`**，与 `func_defs`（`:102`）平级；歧义检测在收集遍末尾 |
| **codegen** | `_collect_type_aliases`（`cython_generator.py:120`）+ `_visit_TypeAlias`（`:3269`，非泛型发 `ctypedef`） | `_visit_ConstraintDef` → **只发注释**（`# constraint Numeric = int | float`），**不发 `ctypedef`**（C-2.2：约束不是类型，发出来等于伪造可用性） | `_visit_SubtypeDef` → **什么都不发**（S-4.1 零表示；对比 `_emit_trait_isinstance_support` `:527`，那个是 trait 的运行时表，subtype **故意不复用**） | `_visit_DispatchDecl` → 发 `_cypy_dispatch_<name>` 表 + 入口 `def`，复用 `_cypy_is_instance_of` |
| **调用面** | `examples/*.cypy` + `scripts/e2e_golden.sh`（只读） | 见 §6 探针内嵌语料（**暂不入 `examples/`**，否则打烂 A1） | 同 | 同（P0 阶段唯一允许新增 golden 的一件） |

> **为什么 `constraint` 要新表、`subtype` 不要**：约束是"名字 → 成员集合"的一对多映射，
> 与别名的"名字 → 单个类型节点"不同构，硬塞进 `type_alias_defs` 会让 `_get_type_from_node`
> （`:2703`）在遇到约束名时返回一个**并不存在的类型**，直接制造 C-2.2 要杜绝的假报错。
> 子类型则天生是"继承边"，`inheritance_map` 已经是为它准备的。

---

## 6. 条款 ↔ 探针映射（机检索引）

探针约定（与 `Find_BUG/audit_2026q3/repro_*.py` 同风格）：
**exit 1 = 期望行为未实现（红）**；**exit 0 = 已实现（绿）**；**exit 2 = 判据自身出错**
（编译管线崩了、临时目录写不进、`errors` 结构变了等既非实现问题也非探针问题的情况）。
全部只读、幂等、语料写在 `tempfile.TemporaryDirectory()` 里，**不在仓库留状态**。
运行入口：`python Find_BUG/audit_2026q3/repro_gate.py feat_constraint_ feat_subtype_ feat_dispatch_ scripts`。

| 探针 | 钉住的条款 | 红→绿的判据（要点） |
|------|-----------|-------------------|
| `feat_constraint_01` | C-1, C-7 | `constraint N = int \| float` 解析出 `ConstraintDef`；`constraint = 5` 必须**报错**（关键字已生效）；`type N = int` 仍解析出 `TypeAlias`（控制组） |
| `feat_constraint_02` | C-2.2, C-2.3, C-4.1, C-4.4 | 命名约束作界：`int`/`float` 通过、`str` 拒绝；并集展开；**内联界 `T: int\|float` 不退化**（回归护栏） |
| `feat_constraint_03` | C-2.1, C-3.1, C-3.2 | `let x: Numeric = 1` 拒绝；`type Numeric` + `constraint Numeric` 同名拒绝；不同名共存放行 |
| `feat_constraint_04` | C-5.1–C-5.5 | 诊断正则：必须含 `constraint violation`、`type '<actual>'`、`allowed: int \| float`、真实 `file:line:col`，且**不含** ` at 0:0` |
| `feat_constraint_05` | C-2.2 表, S-2.3 判定联动 | 满足关系逐条：`bool`→`int` 成员满足、`float`→`int` 不满足、`class B(A)` 的 `B` 满足成员 `A`、`list[int]` 满足成员 `list`（头部名）、`list[int]` 满足 `list<int>`（宽松，见 2.2.1）、`str` 不满足 |
| `feat_constraint_06` | C-1.2, C-1.3, C-2.4, C-2.5, C-6 | 未定义成员/环/0 成员/非类型名成员的定向诊断；`T: A + B`、`T: (A, B)` 必须**硬拒绝并指名替代方案**（当前 `T: (A,B)` 静默吞） |
| `feat_subtype_01` | S-1, S-3.1, S-7.3 | `subtype Meter <: float` 解析出 `SubtypeDef`；`let v: float = m`（upcast）放行；未知基类型定向诊断；控制组：`subtype` 作为普通标识符**必须已报错**（关键字化） |
| `feat_subtype_02` | S-3.1–S-3.4, S-7.1 | 方向性四例：upcast 隐式、downcast 需 `as`、缺 `as` 报错、兄弟 `Meter as Kilometer` 报错、两步 `as float` 放行；链式 `A<:B<:float` |
| `feat_subtype_03` | S-4.1–S-4.4 | 产物零变化（`.pyx` 里不出现 `Meter` 类型对象、`ctypedef`/`cdef class` 均不发）、`isinstance(m, float)` 保留、`isinstance(m, Meter)` 编译期报错、`as` 是 codegen no-op |
| `feat_subtype_04` | S-1.3, S-6, S-7.2, S-7.4 | 自引用/环/深度>8 报错；与 `class` 继承的边界（同基 `class` 有运行时身份、`subtype` 没有）；重名冲突模板 |
| `feat_subtype_05` | S-5.1–S-5.3 | `impl Trait for Meter` 编译期拒绝（附"运行时类型是 float"的理由文案）；`T: SomeTrait` 界对 `Meter` 不满足；`duck` 结构判定对 `Meter` **必须满足**（对照现有 struct 同构体） |
| `feat_dispatch_01` | P-1, P-1' | `dispatch`/`arm` 块解析出 `DispatchDecl`；**专项探静默吞**：`dispatch area(x)` 当前被吞成两个 `ExprStmt`，关键字化后必须报语法错；同名 `def` 仍被 `_check_redefinition` 拦（记录 P-1' 的代价） |
| `feat_dispatch_02` | P-3, P-4, P-4b | 声明期三条诊断：arm 非头行类型的后代 / 歧义（同深度兄弟）/ 无兜底分支 |
| `feat_dispatch_03` | P-2, §4.5 第 2 条 | 运行期分派可观察输出（最特化优先）+ **subtype 无运行时身份导致 `arm Meter:` 永不可达**的实测矛盾（这条同时是 D-9 的证据） |

> **A1 判据保护**：本轮**不向 `examples/` 放任何新语法语料**（三件套现在编译不过，放进去直接
> `RUNFAIL`/`FAIL` 打烂 A1）。正/负例语料全部内嵌在探针里、写临时目录。
> 探针内唯一"今天就能跑"的正例基准（内联联合界 B3）在实现单元转绿时才可提升为 `examples/` golden，
> 且 `bash scripts/e2e_golden.sh` / `scripts/e2e_golden.sh` **只读**。

### 6.1 落盘语料（不接判据，供实现单元直接取用）

`Find_BUG/audit_2026q3/fixtures/feat_type_system/`：

| 文件 | 性质 | 今天实测 |
|------|------|---------|
| `pos_inline_union_bound.cypy` + `.expected` | **正例基准**：内联联合界 `T: int \| float`（唯一今天真正可用的界形态），3 行可观察输出 | `cypyc run` 打印 `1 / 2.5 / 3`，与 `.expected` 一致 |
| `neg_constraint_silently_swallowed.cypy` | **负例 N1**：静默吞形态 | `Undefined name 'constraint' at 8:1` ×2 + `type 'int' does not satisfy constraint 'Numeric' ... at 0:0` |
| `neg_constraint_value_position.cypy` | **负例 N2**：约束名出现在值位置（C-2.1） | 只报 `Undefined name 'constraint'`，**没有**任何"约束不是类型"的诊断 |
| `neg_subtype_missing.cypy` | **负例 N3**：`subtype` 声明（S-1） | `读取文件错误: Unexpected token SUBTYPE at 4:15` |
| `neg_dispatch_missing.cypy` | **负例 N4**：`dispatch` 块（P-1，deferred） | `读取文件错误: Expected RPAREN, got COLON at 4:16` |
| `_measured_cli.txt` | 上述 4 个负例的 `python -m cypyc transpile` **原文**（ANSI 已剥离） | 生成于 2026-09-26 |

`pos_inline_union_bound.cypy` 的 3 行输出就是 C-4.1「命名约束必须与内联界同义」的可观察基准：
`constraint Numeric = int | float` 落地后，把该文件的界换成 `T: Numeric` 输出必须**逐字节不变**。

---

## 7. 缺口与裁决清单（**必须 owner 关掉才能进实现单元**）

| ID | 问题 | 本文件的默认倾向 | 不裁决的后果 |
|----|------|----------------|------------|
| **D-0** | `python -m cypyc` **永远 exit 0**（`cypyc/__main__.py:4` 丢掉 `main()` 返回值），`scripts/e2e_golden.sh:51-58` 的 `run exit=` 分支因此**永不触发** | 修 `__main__.py`（1 行），但它是生产代码，本轮不动 | A1 的 `RUNFAIL=0` 是**假绿**；F4 簇（判据咬合）必须处理 |
| **D-1** | `_user_def_kinds` 是否纳入 `'type'`（让重复 `type N` 报错） | 纳入（C-3.1 的前提），但**先跑全量 e2e + pytest 确认无既有依赖** | C-3.1 的冲突诊断做不出来；B9 静默覆盖继续存在 |
| **D-2** | 泛型成员的元素类型检查（`list<int>`） | 本轮宽松（只比头部名），显式写进 §2.2.1 | 要么假严格、要么静默失效 |
| **D-3** | 多界组合 `T: A + B` / `T: A & B` | **不支持**，只给定向诊断 | 若 owner 要，需要先定 class 多继承 + 交集可满足性 |
| **D-4** | 三词是否硬保留字（会破坏 `constraint`/`subtype`/`dispatch` 当普通名字用的既有 `.cypy`） | 硬保留（附全库 grep 证据） | 软保留字方案与 §2.1 语法互斥（C-7.3） |
| **D-5** | `subtype X <: <type 别名>` 是否允许 | 不允许（别名会被替换，身份判定随定义漂移） | `Type.__eq__`（含 `union_members`）会被别名展开结果污染 |
| **D-6** | `impl Trait for <subtype>` | v1 拒绝（S-5.1 的 `type(x).__name__` 泄漏论证） | trait 运行时表静默失效或语义泄漏 |
| **D-7** | dispatch 用 `arm` 块还是同名多 `def`（P-1 vs P-1'） | `arm` 块 | P-1' 需要放开 `function` 的可重复声明，波及 `_check_redefinition` 全局护栏 |
| **D-8** | dispatch 是单键还是多键分派 | v1 单键（第 1 参数） | 多键的歧义检测复杂度指数级上升 |
| **D-9** | **dispatch 与 §3.4 的直接矛盾**：subtype 零运行时表示 ⇒ `arm Meter:` 不可达 | 要么禁止 subtype 做 arm，要么给 subtype 运行时包装（推翻 §3.4） | 三件套的 F2/F3 语义互相矛盾，必须先解 |
| **D-10** | （**新增，下一轮再裁**）调用点是否检查实参类型/元数 —— cypyc 今天对普通 `def` 也没有这项检查（P-1.9 实测：`_visit_Call` 只逐个 visit 实参并取 `type_map[func_name]` 作返回类型） | 不在 dispatch 里单独开；要开就同时对 `def` 生效 | 若只给 dispatch 加检查，会出现「同一句调用，dispatch 报错而 def 静默」的判等不一致 |

### 7.1 指挥官裁决（2026-09-26，R2 收口，关闭后 F1.2/F2.2 才可进实现）

三件套的语义边界由本轮裁决定稿；**裁决只关闭问题，不扩大范围**——凡本轮不做的一律写明
「不做 + 落点」，不留悬空关键字。

| ID | 裁决 | 依据 / 附带条件 |
|----|------|----------------|
| **D-0** | **已关闭**：`cypyc/__main__.py` 传播 `cli.main()` 返回码（T0r258.4.2 的 LINK-1，+10/−1）。判据的 `run exit=` 分支自此是活代码 | 加固后同一批旧 golden 由 `PASS=22 FAIL=0 WARN=1 exit 0` 变 `PASS=13 FAIL=9 UNREG=1 WARN=0 exit 1`（单调只减绿，实测两遍）；退出码的负向实测原文见本轮报告 A1 段 |
| **D-1** | **纳入**：`_user_def_kinds` 扩到 `{'type','constraint','subtype',...}`，C-3.1 的重复定义冲突诊断照做 | 附带条件（不可跳过）：改完必须**先**跑全量 `bash scripts/e2e_golden.sh` + `python -m pytest -q tests test_suite`；若既有 golden/测试因原先的静默覆盖而红，按缺陷登记 `Find_BUG/BUGS.md` 而不是回退判据 |
| **D-2** | **本轮宽松**：泛型成员只比头部名（`list[int]` 满足成员 `list`，`list[int]` 满足 `list<int>`），实参一致性 deferred | 已写进 §2.2.1；`feat_constraint_05` 的表项即判据，实现不得偷偷收紧 |
| **D-3** | **不支持**多界组合 `T: A + B` / `T: A & B` / `T: (A, B)`：一律硬拒绝 + 指名替代方案 | `T: (A, B)` 今天被 parser 静默吞成 `Constant` 后走裸名字比较（`type_checker.py:2508-2513`），静默接受比崩溃更糟，`feat_constraint_06` 专门钉这条 |
| **D-4** | **硬保留字**：`constraint` / `subtype` 自本轮起进 `KEYWORDS`（`dispatch` 随 F3 下一轮一起进，本轮不进） | 全库 `.cypy` 实测 `grep -rlE '\\b(constraint\|subtype\|dispatch)\\b' --include='*.cypy' examples Find_BUG tests` → **10 个文件命中**（清单落 `output/reserved_word_hits.txt`），**全部**是注释、字符串字面量或 `Find_BUG/audit_2026q3/fixtures/` 的负例语料，没有一处把它们当普通标识符使用 ⇒ 硬保留不破坏任何既有可编译语料 |
| **D-5** | **不允许** `subtype X <: <type 别名>`：基类型必须是具名 builtin/struct/class | 别名会被替换，身份判定随定义漂移，且会污染 `Type.__eq__` 的 `union_members` 比较 |
| **D-6** | **v1 拒绝** `impl Trait for <subtype>` | 与 §3.4「零运行时表示」同源：`impl` 依赖 `type(x).__name__` 运行时表，subtype 故意没有那张表 |
| **D-7** | 采纳 `arm` 块形态（P-1）；**P-1' 不做** | 放开 `function` 重复声明会牵动 `_check_redefinition` 全局护栏，收益不抵风险 |
| **D-8** | v1 单键分派（第 1 参数） | 多键歧义检测复杂度指数级上升 |
| **D-9** | **裁决：禁止 `subtype` 做 `arm` 的键**（声明期定向诊断），而不是给 subtype 加运行时包装 | §3.4 的零表示是 F2 全部条款的地基（`feat_subtype_03` 就是钉它的），不为一个本轮 deferred 的特性推翻它。矛盾因此从「实现冲突」降为「规范边界」，`feat_dispatch_03` 的实测记录即本条证据 |

`dispatch` 整件维持 **deferred**：F3 只交提案 + 探针，本轮不进 lexer（D-4 的裁决据此只对
`constraint`/`subtype` 生效，避免留一个能被解析却无人实现的关键字）。


* `dispatch` 整件：**实现 deferred 到下一轮**（§4 自 `T0r258.3.2` 起是**定稿规范**，deferred 的
  是写代码，不是继续讨论语义；开工顺序见 §4.7）。
* 泛型成员的实参一致性（§2.2.1）、多界组合（§2.6）、`subtype` 的泛型参数与 trait 挂载（S-1.1/S-5.1）、
  跨模块分派槽与增量编译（§4.5 第 3 条）：均 **deferred**，无实现、无关键字残留。

---

## 8. 变更记录

* 2026-09-26 建档（R2 单元 1，`T0r258.1.1/.2.1/.3.1`）。
  同时勘正：`docs/SYNTAX_CHANGE_REVIEW.md:20-22` 把三件套标为「✅ 完成」是指**文档动作**栏，
  与 `SYNTAX_IMPLEMENTATION_STATUS.md:83-91, 221-223` 的「❌ 未实现」并不矛盾，
  但该行**极易误读**；`docs/SYNTAX_CHANGE_REVIEW.md:33` 声称本文三件套规范落在 `27-constraints.md`，
  而 `27-constraints.md` 通篇是已实现的 `duck` 约束 —— 该指路错误由 F5 簇（`feat_docs_`）勘正，本文不越界改它。

* 2026-09-26 `T0r258.4.2`：新增 **§7.1 指挥官裁决**（D-0 已随 LINK-1 关闭；D-1 纳入 `'type'`
  但附全量复跑前置；D-2 只比头部名；D-3/D-5/D-6 拒绝并给定向诊断；D-4 硬保留字且**只进
  `constraint`/`subtype`**，附 10 文件命中清单 `output/reserved_word_hits.txt`；D-7 `arm` 块；
  D-8 单键；D-9 禁止 subtype 做 arm 键）。同批改写 §2.7 的 C-7.1/C-7.2，使其与裁决一致
  （原文写「三词都进 KEYWORDS」，会让 `dispatch` 成为悬空关键字）。

* 2026-09-26 `T0r258.3.2`：§4 由提案改写为**可开工的定稿规范** —— P-1.1..P-1.9（含 P-1.5
  「`arm` 不是通用语句」与 P-1.9「cypyc 今天对任何用户函数都没有实参类型/元数检查」两条反悬空/
  诚实条款）、P-1' 依裁决 D-7 明确否决、新增 **§4.4.1 诊断模板（D-hdr/D-empty/D-mlt/D-ord/
  D-stray/D-mlvl/D-name/D-amb/D-none/D-key）**、新增 **§4.7 开工清单与验收判据**（S1..S7，
  每片带现成 file:line 落点与红→绿探针），§4.6 补第 5/6 条，§7 新增待裁项 **D-10**
  （调用点实参检查须与 `def` 同时生效，否则判等不一致）。`dispatch`/`arm` 本轮**不进** lexer。

