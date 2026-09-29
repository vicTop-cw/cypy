# Cypy 语法实现状态报告

**生成时间**: 2026-08-03
**最后核对**: 2026-09-26（FIST `cron-cypy/T0r258.5.2`：§1 统计、§5.2/§5.3 示例与 golden 覆盖、
§6 测试覆盖、§7.2 关键字存废、§8.2 文档指向全部按当场实测重算；§2 与 §7.1 的 ✅/❌ **状态标记未动**，
`constraint` / `subtype` / `dispatch` 三行的收口权在各实现轮）
**分析版本**: 当前主分支

---

## 1. 统计概览（2026-09-26 实测快照）

| 类别 | 数量 |
|------|------|
| TokenType 定义 | 129 |
| KEYWORDS 映射 | 65 |
| AST 节点类 | 87 |
| Codegen `_visit_` 方法 | 75 |

**这四个数是写下的那一刻的实测值，不是常量**（本表原值 137 / 70 / 83 / 70 全部与实测不符，
是 `T0r258.5.1` 机检出的失真）。计数口径（右列命令可直接复跑）：

| 项 | 口径 / 命令 |
|----|-------------|
| TokenType 定义 | `cypyc/parser/lexer.py` 中 4 空格缩进的 `NAME = "..."` 成员，**去重**计数 |
| KEYWORDS 映射 | `python -c "from cypyc.parser.lexer import Lexer; print(len(Lexer.KEYWORDS))"` |
| AST 节点类 | `parser.py` 中 `^class \w+\(ASTNode\)` 命中数 |
| Codegen `_visit_` 方法 | `cython_generator.py` 中 `def _visit_X` 的**唯一**方法名数（定义处共 76，`_visit_ExprStmt` 重复 1 处） |

> **并发提示**：`constraint` / `subtype` / `dispatch` 的实现轮（`T0r258.1.1~3.1`）正在往词表里加词，
> 「KEYWORDS 映射」这一项会随每一层落地而变。机检判据
> `python Find_BUG/audit_2026q3/feat_docs_01.py` 的 X7 规则每次都按实时值比对（INFO 级，不过门）。
> 关键字逐词清单见 `SYNTAX/appendix-A-keywords.md`。

---

## 2. 已完整实现（Lexer + Parser + Codegen）

### 2.1 核心语法（100% 完成）

| 关键字 | AST 节点 | 状态 |
|--------|----------|------|
| `if/elif/else` | IfStmt | ✅ |
| `for` | ForStmt | ✅ |
| `while` | WhileStmt | ✅ |
| `break/continue` | BreakStmt/ContinueStmt | ✅ |
| `return` | ReturnStmt | ✅ |
| `def` | FuncDef | ✅ |
| `class` | ClassDef | ✅ |
| `struct` | StructDef | ✅ |
| `enum` | EnumDef | ✅ |
| `trait` | TraitDef | ✅ |
| `typeclass` | TypeClassDef | ✅ |
| `impl` | ImplStmt | ✅ |
| `import/from` | Import/FromImport | ✅ |
| `let/var/const` | LetStmt | ✅ |
| `defer` | DeferStmt | ✅ |
| `guard` | GuardStmt | ✅ |
| `match/case` | MatchStmt/CaseClause | ✅ |
| `try/except/finally` | TryStmt | ✅ |
| `raise` | RaiseStmt | ✅ |
| `assert` | AssertStmt | ✅ |
| `with` | WithStmt | ✅ |
| `yield` | YieldStmt | ✅ |
| `async/await` | FuncDef/AwaitExpr | ✅ |
| `spawn/go` | SpawnStmt/GoStmt | ✅ |
| `lambda` | LambdaExpr | ✅ |
| `del` | DelStmt | ✅ |
| `type` | TypeAlias | ✅ |
| `exception` | ExceptionDef | ✅ |
| `suite/test/setup/teardown` | SuiteDef/TestDef | ✅ |
| `comptime` | ComptimeStmt/ComptimeFuncDef | ✅ |
| `pointer/ref/mut` | PointerType/RefType | ✅ |
| `is/in/and/or/not` | BinOp/UnaryOp | ✅ |
| `global/nonlocal` | GlobalStmt/NonlocalStmt | ✅ |

### 2.2 类型系统（100% 完成）

| 特性 | AST 节点 | 状态 |
|------|----------|------|
| 基础类型 | Name | ✅ |
| 泛型类型 | GenericType | ✅ |
| 联合类型 | UnionType | ✅ |
| 指针类型 | PointerType | ✅ |
| 引用类型 | RefType | ✅ |
| 类型转换 | CastExpr | ✅ |
| 解引用 | DerefExpr | ✅ |

### 2.3 新增语法特性（刚实现）

| 特性 | AST 节点 | 状态 |
|------|----------|------|
| SIMD 向量类型 | VecType | ✅ |
| 向量字面量 | VecLiteral | ✅ |
| 管道操作符 `|>` | PipeExpr | ✅ |
| 宏定义 | MacroDef | ✅ |
| 宏调用 | MacroCall | ✅ |
| 元块 | MetaBlock | ✅ |
| 构建值表达式 | BuildValueExpr | ✅ |

### 2.4 三件套现状：constraint 已实现 / subtype 仅词法 / dispatch 仅规范

| 特性 | AST 节点 | 状态 | 计划版本 |
|------|----------|------|----------|
| 类型约束 `constraint` | ConstraintDef | ✅ 已实现（四层齐：`Lexer.KEYWORDS` → `parser.py` `class ConstraintDef` + `_parse_constraint` → `type_checker.constraint_defs` 与界检查/摊平 → `cython_generator._visit_ConstraintDef` 只发注释） | v0.5 → **本轮 `T0r258.1.2` 已落** |
| 子类型声明 `subtype` | SubtypeDecl | ⚠ 仅词法已收（`subtype` 在 `Lexer.KEYWORDS`，已是保留字、不能再用作标识符）；`SubtypeDecl` / 解析 / 语义 / 生成**均未落** | v0.5（`T0r258.2.2`） |
| 分发声明 `dispatch` | DispatchDecl | ❌ 未实现（`dispatch` **不在** `Lexer.KEYWORDS`，`cypyc/` 无任何落点） | 裁决 DEFERRED，本轮不做 |

> **注**：本小节的状态标记按本轮纪律**只能由各自的实现轮带着 A1~A5 验收号来改**。
> `T0r258.1.2`（constraint）收口时改了它自己那一行；`subtype` 行改成 ⚠ 而不是继续写 ❌，
> 理由是**保留字这一层已经生效**（`subtype` 不能再用作标识符），写 ❌ 会漏报已存在的行为——
> 机检 `Find_BUG/audit_2026q3/feat_docs_01.py` 的 X2 FALSE_TODO 抓的正是这种漏报；
> ⚠ 是该探针给的第三态（`marker_of` 认 ✅/❌/⚠ = DONE/TODO/PART，只有 DONE 与 TODO 互相打架才记 X3）。
> **2026-09-26 12:3x 实测**：`len(Lexer.KEYWORDS)` = **65**；`'constraint' in Lexer.KEYWORDS` = True、
> `'subtype'` = True、`'dispatch'` = False；
> `grep -c '^class \(SubtypeDecl\|DispatchDecl\)' cypyc/parser/parser.py` = 0（`ConstraintDef` 已有）。
> 语义与验收口径见 `SYNTAX/33-type-constraints-subtypes-dispatch.md`（783 行，`git status` 仍为未跟踪）。
> `constraint` 已不再需要「用 `type` 别名替代」这句口径：`type Numeric = int \| float` 是**编译期替换**、
> `constraint Numeric = int \| float` 是**界**，二者分工不同且不能互相冒充（裁决 D-1/D-3；
> 把约束写在值位置现在会直接报 `is a constraint, not a type`）。

### 2.5 v0.3-v0.4 新增功能

| 特性 | AST 节点 | 状态 |
|------|----------|------|
| 三元条件表达式 `x if c else y` | IfExp | ✅ |
| `*args`/`**kwargs` 可变参数 | Param (is_var_positional/is_var_keyword) | ✅ |
| 整除运算符 `//` | BinOp | ✅ |
| 复合赋值 `//=`、`%=` | AugAssign | ✅ |
| `global`/`nonlocal` 声明 | GlobalStmt/NonlocalStmt | ✅ |
| CythonGenerator `await` 支持 | AwaitExpr | ✅ |
| CythonGenerator `async def` 支持 | FuncDef (is_async) | ✅ |
| CythonGenerator BacktickBlock | BacktickBlock | ✅ |

---

## 3. 有 Token/AST 但部分实现的特性

### 3.1 有 TokenType 但无独立 AST

| Token | 状态 | 说明 |
|-------|------|------|
| `NEVER` | ⚠️ | 类型系统中使用，无独立 AST |
| `FOR_KW` | ⚠️ | 已合并到 FOR（实测：`lexer.py:170` 把 `"for"` 直接映射到 `TokenType.FOR`；`grep -rn 'Token(TokenType\.FOR_KW' cypyc/` = **0** 次产出，故 `parser.py:2445`、`:2477` 那 2 处 `FOR_KW` 分支当前不可达） |
| `OWNED` | ⚠️ | 解析为 LetStmt 修饰符 |
| `BANG` | ⚠️ | 用于 vec! 和宏调用，无独立 AST |
| `FAT_ARROW` | ⚠️ | 解析为表达式一部分 |
| `BACKTICK_BLOCK` | ⚠️ | 有 AST 但 codegen 未完整 |

### 3.2 有 AST 但 Codegen 通过父节点处理

| AST 节点 | 处理方式 | 状态 |
|----------|----------|------|
| `Module` | 顶层入口 | ✅ |
| `StructField` | StructDef 内部处理 | ✅ |
| `EnumVariant` | EnumDef 内部处理 | ✅ |
| `Param` | FuncDef 内部处理 | ✅ |
| `CaseClause` | MatchStmt 内部处理 | ✅ |
| `Decorator` | FuncDef/ClassDef 前置处理 | ✅ |

---

## 4. 有定义但未独立使用的特性

### 4.1 模式匹配相关（已整合）

| AST 节点 | 状态 | 说明 |
|----------|------|------|
| `Pattern` | ✅ | 基类，通过子类实现 |
| `SlicePattern` | ✅ | 切片模式 |
| `ArrayPattern` | ✅ | 数组模式 |
| `StructPattern` | ✅ | 结构体模式 |
| `DictPattern` | ✅ | 字典模式 |
| `TypePattern` | ✅ | 类型模式 |
| `AsPattern` | ✅ | 别名模式 |
| `ExtractorPattern` | ✅ | 提取器模式 |
| `RangePattern` | ✅ | 范围模式 |

### 4.2 构建块相关（已整合）

| AST 节点 | 状态 | 说明 |
|----------|------|------|
| `BuildBlockExpr` | ✅ | 主构建块表达式 |
| `BuildValueExpr` | ✅ | 构建值表达式 |

---

## 5. 示例文件覆盖情况

### 5.1 已有示例文件

| 文件 | 覆盖特性 |
|------|----------|
| `basic_types.cypy` | 类型转换 |
| `control_flow.cypy` | if/for/while/match |
| `functions.cypy` | 函数/管道操作 |
| `struct_enum.cypy` | 结构体/枚举 |
| `concurrency.cypy` | spawn/go |
| `list_comprehension.cypy` | 列表推导式 |
| `pointers.cypy` | 指针操作 |
| `meta.cypy` | 元块/约束 |
| `new_syntax_features.cypy` | guard/named-arg |
| `pipe_operator.cypy` | 管道操作 |
| `defer.cypy` | 延迟执行 |

### 5.2 需要补充的示例（2026-09-26 跟进：四项已落地，但都不在 golden 锚点内）

| 特性 | 建议 | 跟进实测（`git ls-files` 命中路径） |
|------|------|--------------------------------------|
| `Vec` 向量 | 创建 `vec_examples.cypy` | 已建 `examples/demos/simd_vectors/vec_examples.cypy` |
| `Macro` 宏 | 创建 `macro_examples.cypy` | 已建 `examples/demos/macros/macro_examples.cypy` |
| `UnionType` | 创建 `union_type.cypy` | 已建 `examples/demos/concurrency_advanced/union_type.cypy` 与 `examples/demos/type_system/union_type_examples.cypy` |
| 项目级编译 | 创建 `project_example/` | 已建 `examples/test_project/`（`main.cypy` / `geometry.cypy` / `types.cypy`） |

### 5.3 golden 锚点的实际覆盖面（2026-09-26 实测）

取样本口径写在 `scripts/e2e_golden.sh:91-93`：`for src in examples/*.cypy` 之后紧跟
`case "$(basename "$src")" in _*) continue ;; esac` —— **只扫 `examples/` 顶层、跳过 `_` 前缀**，
`examples/demos/**` 与 `examples/legacy/**` 一条都不进（所以上面 §5.2 那四项已建示例都不受 golden 保护）。

| 量 | 实测值 | 命令 |
|----|--------|------|
| 仓库跟踪的 `.cypy` 总数 | 77 | `git ls-files \| grep -cE '\.cypy$'` |
| 顶层非 `_` 前缀样本 | 23 | `git ls-files examples \| grep -E '^examples/[^/]+\.cypy$' \| grep -vc '/_'` |
| 磁盘 golden 基准份数 | 23 | `ls examples/*.out \| wc -l` |
| golden 基准被 git 跟踪的份数 | 0 | `git ls-files 'examples/*.out' \| wc -l`（LINK-4 的入库不在实现轮权限内，改以 `Find_BUG/audit_2026q3/golden_before/` 快照留档） |

**结论**：golden 判据锚定的是 **23 / 77**（≈30%）份 `.cypy`；其余 **54** 份（77 − 23）不在锚点内——
它们是 `examples/demos/**`、`examples/legacy/**` 等子目录样本（glob 只写了一层 `examples/*.cypy`），
外加磁盘上 2 份 `_` 前缀挂起样本（`examples/_pending_build_blocks.cypy`、
`examples/_pending_type_defects.cypy`，未跟踪，被上面那条 `case ... in _*) continue` 排除）。
所以「golden 全绿 = 示例全绿」的读法不成立。

---

## 6. 测试覆盖情况

### 6.1 现有测试文件

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_codegen_guard.py` | Guard 语句 |
| `test_new_syntax_boundary.py` | 边界条件 |
| `test_e2e_new_features.py` | 端到端测试 |
| `test_type_inference.py` | TypeClass（`TestTypeClassSupport` 类，实测收集 6 例，全部打在 analyzer 层 `TypeChecker.register_type_class*`） |

#### 更正记录（`T0r258.5.2`，2026-09-26）

本表原第 4 行写 `test_typeclass_codegen.py`，是**幽灵文件**：
`git ls-files | grep -i typeclass` 与 `find . -name <该名>` 双查**均为空**（判据 X5 PHANTOM_FILE）。
实测：仓库里**没有任何 TypeClass 的 codegen 层用例**——`grep -rn typeclass test_suite/` 0 命中，
唯一沾边的是示例 `examples/demos/traits_duck/trait_advanced.cypy`。故本行改指真实落点
`tests/test_type_inference.py`，并把「codegen 层零覆盖」写成明面缺口，而不是留一个不存在的文件名。

### 6.2 需要补充的测试（2026-09-26 跟进）

| 特性 | 建议测试 | 跟进实测 |
|------|----------|----------|
| `VecType/VecLiteral` | `test_vec.py` | 已建（`git ls-files` 命中） |
| `UnionType` | `test_union_type.py` | 已建 |
| `MacroDef/MacroCall` | `test_macro.py` | 已建 |
| 项目级编译 | `test_project_compiler.py` | 已建 |
| `ConstraintDef` | `test_named_constraints.py` | **已建**（`tests/test_named_constraints.py`，328 行，`pytest --collect-only` 实测收集 34 例）；仓库里仍没有叫 `test_constraint.py` 的文件（`git ls-files \| grep -c test_constraint.py` = 0，此实测未变） |

### 6.3 两套测试体系的真实入口（2026-09-26 实测）

`python -m pytest -q tests test_suite` 的第二条路径**收集 0 条**：

```
$ python -m pytest -q --collect-only test_suite/
collected 0 items
========================= no tests collected in 0.13s =========================
```

原因：native 套件不是 pytest 文件，而是 `test_suite/suites/` 下的 4 个 `*_suite.py`
（`parser_suite.py` / `analyzer_suite.py` / `codegen_suite.py` / `integration_suite.py`），
由 `python scripts/run_tests.py [--suite parser|analyzer|codegen|integration]` 驱动
（`scripts/run_tests.py:65-68` 显式 import 这四个模块）。所以「跑了两条路径」实际只等于跑了
`tests/` 一条，`test_suite/` 的 native 用例需要单独用 `scripts/run_tests.py` 才算执行到。

---

## 7. 语法变更点（需审核）

### 7.1 新增语法（已实现）

| 语法 | 实现状态 | 审核建议 |
|------|----------|----------|
| `vec[T; N]` | ✅ 已实现 | 保持 |
| `vec![v1, v2]` | ✅ 已实现 | 保持 |
| `A \| B` 联合类型 | ✅ 已实现（降级为 object） | 建议优化类型检查 |
| `macro name(ts: Tokens) = body` | ✅ 已实现 | 保持 |
| `constraint Name = A \| B` | ✅ 已实现 | `T0r258.1.2` 四层齐落；调用面 `examples/constraint_numeric.cypy` + golden 已注册（A1 `PASS=24 FAIL=0 UNREG/RUNFAIL=0 WARN=0`）；探针 `repro_gate.py feat_constraint_ fixed` 6/6 exit 0；回归 `tests/test_named_constraints.py`（收集 34 例） |
| `subtype A <: B` | ⚠ 仅词法 | `subtype` 已是保留字（`Lexer.KEYWORDS` 实测含它），解析/语义/生成未落 —— 状态声明权在 `T0r258.2.2` |
| `dispatch name(params) -> ret` | ❌ 未实现 | `dispatch` **不在** `Lexer.KEYWORDS`（`in` 实测 False），`cypyc/` 无任何落点；裁决 DEFERRED，本轮不做 |
| `x |> f(args)` | ✅ 已实现 | 保持 |

### 7.2 潜在移除/调整（2026-09-26 按词表与 Token 实测拆开）

原句「所有潜在移除项（cdef、POINTER、NO_STRATEGY、FOR_KW）均已从语言中移除」对其中 2 项不成立。
逐项实测（判据 X6 的同源命令，只读）：

| 项 | 在 `Lexer.KEYWORDS`？ | Token 成员定义处 / `TokenType.<名>` 被引用数 | 结论 |
|----|----------------------|---------------------------------------------|------|
| `cdef` | 否 | `cypyc/parser/lexer.py:84` / **0** 处 | 已移出语言，但死枚举成员仍在 |
| `POINTER` | 否 | 无（`grep -rn POINTER cypyc/ --include=*.py` = 0 命中） | 彻底移除 |
| `NO_STRATEGY` | 否 | `cypyc/parser/lexer.py:134` / **0** 处 | 已移出语言，但死枚举成员仍在；所谓「`@no_strategy` 装饰器用途」全仓仅那 1 行定义，无任何实现 |
| `FOR_KW` | 否（`"for"` 映射到 `TokenType.FOR`，`lexer.py:170`） | `cypyc/parser/lexer.py:110` / **2** 处（`parser.py:2445`、`:2477`） | **未移除**（成员与引用都在）；但 lexer 从不产出该 token，那 2 个分支不可达 |

清理这 3 处残留（`TokenType.CDEF`、`TokenType.NO_STRATEGY` 两行死枚举，加不可达的 `FOR_KW` 分支）
属词表清理类改动，本单元只对齐文档、不动 `cypyc/`，也未登记为缺陷。

### 7.3 待完善功能

| 功能 | 当前状态 | 建议 |
|------|----------|------|
| `BacktickBlock` | ✅ 已完成（codegen 已实现） | 保持 |
| `UnionType` 类型检查 | 降级为 object | 增强类型检查器 |

---

## 8. 文档状态

### 8.1 SYNTAX 文档完整性

| 文档 | 状态 | 需更新 |
|------|------|--------|
| `00-introduction.md` | ✅ 完整 | 无 |
| `01-basic-types.md` | ✅ 完整 | 无 |
| `02-type-annotations.md` | ⚠ 部分 | 已闭环（R13/R14）：容器**元素位**判定与别名代入——`tuple<bool, int>` 收 `(True, "x")`、`list<int>` 收 `["s"]`、定长元组个数不符、以及返回位同形此前全部静默（BUG-137 FIXED），别名套别名不展开造成正确程序被拒（BUG-138 FIXED），联合形态别名整条不代入（BUG-139 FIXED）；Ω-spec `cypy.container.elements` 28 对，规范见 `SYNTAX/02-type-annotations.md`「容器元素位判定（R13 补）」规则 1-6。R14 起同节补「字典字面量的键值位判定」规则 1-6：`{"a": "b"}` 收进 `dict<str, int>` 报 `Dict value type mismatch`，键位/返回位/嵌套/别名同尺，空字面量与混形塌位仍放行（BUG-141 FIXED，Ω-spec `cypy.dict.elements` 25 对，锁 `tests/test_dict_elements_r14.py` 29 支）。未闭环：定义侧带约束界 `type Num<T: int \| float>` 仍直接解析失败（BUG-136 的 (f) 面）、联合成员的元素位仍不判（`ListOrSet<int>` 收 `["s"]` 静默，`_type_in_union` 只比成员名）、类型实参不判存在性（BUG-122）、字典推导式与 `for k, v in d` 解包位不走字面量推断因而不判 |
| `03-type-conversion.md` | ✅ 完整 | 无 |
| `04-pointer-types.md` | ✅ 完整 | 无 |
| `05-struct.md` | ✅ 完整 | 无 |
| `06-enum.md` | ✅ 完整 | 无 |
| `07-trait-impl.md` | ✅ 完整 | 无 |
| `08-class.md` | ✅ 完整 | 无 |
| `09-functions.md` | ✅ 完整 | 无 |
| `10-variables.md` | ✅ 完整 | 无 |
| `11-generics.md` | ⚠ 部分 | 已闭环：调用点类型实参（解析/代入/产物擦除，Ω-spec `cypy.generic.callsite`，BUG-118 FIXED）、泛型类（定义侧三种前缀与约束解析、注解位/调用位元数、接收者逐位代入、产物擦除，Ω-spec `cypy.generic.class`，BUG-119 FIXED）、**定义侧声明界在使用侧的判定**（注解位 / 显式类型实参构造位 / 结构体字面量位三处共用 `TypeChecker._check_declared_bounds`，四类界复用同一件 `_check_generic_constraint`，Ω-spec `cypy.generic.bounds` 23 对，BUG-129 FIXED）。未闭环：trait 带冒号的无体签名不解析（BUG-120，R11 已把半径缩到「仅 `-> T:` 那形」）、方括号形态 `f[T](x)` 产物坏（BUG-121）、类型实参不判存在性（BUG-122，R11 扩到 class 实例化位）、泛型 struct 的方法调用不代入（BUG-128）、构造位不写类型实参时不做推断（BUG-135，与 BUG-128 同一推断层）、违界诊断的 `in call to '<unknown>'` 文案误导（BUG-134） |
| `12-operators.md` | ✅ 完整 | 无 |
| `12-type-alias.md` | ⚠ 部分 | 已闭环（R13）：泛型别名代入、**别名套别名展开到底**、联合形态别名代入、标量别名嵌在别的别名右端里（BUG-138/139 FIXED，Ω-spec `cypy.container.elements` + 锁 `tests/test_container_elements_r13.py`）⇒ 手册「类型安全：别名不是新类型，编译时完全等价」那句现在才站得住。R14 另把「别名右端是字典」这一面接上判定：`type Count = dict<str, int>` 之后 `let bad: Count = {"a": "b"}` 要报（BUG-141 FIXED 的一部分）。未闭环：定义侧带约束界 `type Name<T: Bound> =` 仍不解析（BUG-136 的 (f) 面）、联合形态别名的**成员元素位**仍不判（`ListOrSet<int>` 收 `["s"]` 静默）、产物面本轮未动（擦除路径不变，e2e golden 复验） |
| `13-build-blocks.md` | ✅ 完整 | 无 |
| `14-syntax-sugar.md` | ✅ 完整 | 无 |
| `15-control-flow.md` | ✅ 完整 | 无 |
| `16-exceptions.md` | ✅ 完整 | 无 |
| `17-pattern-matching.md` | ✅ 完整 | 无 |
| `18-macros.md` | ✅ 完整 | 无 |
| `19-comptime.md` | ✅ 完整 | 无 |
| `20-concurrency.md` | ✅ 完整 | 无 |
| `21-simd-vector.md` | ✅ 完整 | 无 |
| `22-magic-properties.md` | ✅ 完整 | 无 |
| `23-compilation.md` | ✅ 完整 | 无 |
| `24-incremental-hot-reload.md` | ✅ 完整 | 无 |
| `25-compatibility.md` | ✅ 完整 | 无 |

### 8.2 计划补建的文档（2026-09-26 按实际文件名跟进）

原「需要补建的文档」三条计划已过期，实测状态如下（行数 = `wc -l` 实测）：

| 计划文档 | 实测状态 |
|----------|----------|
| `26-union-type.md` | 已创建，176 行 |
| `27-project-compilation.md` | 未建，计划作废：项目级编译说明实际落在 `23-compilation.md`（249 行，含 project 字样 6 处） |
| `28-constraints.md` | 未建，计划作废：内容拆到两份现存规范文件里 —— `27-constraints.md`（475 行，已实现的 duck 约束：`meta:` 块 + `_duck_registry`）与 `33-type-constraints-subtypes-dispatch.md`（783 行，constraint / subtype / dispatch 语义规范；本轮写入，`git status --short SYNTAX/` 显示为未跟踪 `??`，本单元无权入库） |

---

## 9. 总结与建议

### 9.1 完成度

- **核心语法**: 100% 完成
- **类型系统**: 100% 完成
- **新特性**: 100% 完成（刚实现）
- **文档覆盖**: 约 75%（部分文档需更新）
- **测试覆盖**: 约 80%（新特性需补充测试）

### 9.2 优先级建议

2. **中优先级**
   - 完善宏的编译期展开实现
   - 增强 UnionType 的类型检查
   - 实现 `Callable[[T], R]` 函数类型标注

3. **低优先级**
   - 优化代码注释和内联文档
   - 清理冗余关键字