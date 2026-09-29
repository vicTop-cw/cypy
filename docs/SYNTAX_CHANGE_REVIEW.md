# 语法变更审核清单

**生成时间**: 2026-07-30
**需要用户审核决策**

> **口径声明（2026-09-26，FIST `cron-cypy/T0r258.5.2`）**：本清单是**文档动作**台账，
> 不声明编译器实现状态。§1 的第二列原名「实现状态」，实测与 `cypyc/` 冲突
> （机检判据 `Find_BUG/audit_2026q3/feat_docs_01.py`，出自 `T0r258.5.1`），现改名并在
> 每行给出**规范文件**指向。实现状态的唯一权威表是
> `SYNTAX_IMPLEMENTATION_STATUS.md` §2（已实现）与 §2.4 / §7.1（未实现）。

---

## 1. 本清单涉及的语法条目（列＝文档动作，**不是实现状态**）

下表 ✅ 的含义是「本清单为该语法做的文档动作（写 / 改哪份规范）已完成」；
**编译器落没落地请看 `SYNTAX_IMPLEMENTATION_STATUS.md`**。

| 语法 | 文档动作 | 规范文件 |
|------|----------|----------|
| `vec[T; N]` 向量类型 | ✅ 完成 | `21-simd-vector.md` |
| `vec![v1, v2]` 向量字面量 | ✅ 完成 | `21-simd-vector.md` |
| `vec![value; N]` 重复形式 | ✅ 完成 | `21-simd-vector.md` |
| `x |> f(args)` 管道操作符 | ✅ 完成 | `12-operators.md` |
| `A \| B` 联合类型 | ✅ 完成（降级为 object） | `26-union-type.md` |
| `macro name(params) = body` | ✅ 完成 | `18-macros.md` |
| `constraint Name = A \| B` | ✅ 完成（规范已写 **且实现已落**：`T0r258.1.2`，A1 `PASS=24 FAIL=0 UNREG/RUNFAIL=0 WARN=0`、`repro_gate.py feat_constraint_ fixed` 6/6 exit 0） | `33-type-constraints-subtypes-dispatch.md` |
| `subtype A <: B` | ⚠ 规范已写；实现**只到词法**（`subtype` 已是保留字），解析/语义/生成未落 | `33-type-constraints-subtypes-dispatch.md` |
| `dispatch name(params) -> ret` | ⚠ 仅规范已写（`dispatch` 不在 `Lexer.KEYWORDS`，`cypyc/` 无任何落点，探针 `feat_dispatch_01` 实测仍复现） | `33-type-constraints-subtypes-dispatch.md` |
| `cypyc build <dir>` 项目级编译 | ✅ 完成 | `23-compilation.md` |

**表内第 7~9 条（constraint / subtype / dispatch）的状态口径**：这三条的**落章权属于各自的实现轮**，
必须带着自己的 A1~A5 验收号才能改；本文件此前一律写「✅ 完成（仅指规范已写）」，那是把
**规范状态**写在**实现状态**这一栏里的失真——机检 `Find_BUG/audit_2026q3/feat_docs_01.py`
据此报 X1 FALSE_DONE 与 X3 CONTRADICTION（与 `SYNTAX_IMPLEMENTATION_STATUS.md` 互相打架）。
2026-09-26 12:3x 按实测改为三态：`constraint` 已由 `T0r258.1.2` 四层落定（✅），
`subtype` 只到词法层（⚠，`in Lexer.KEYWORDS` = True 而 `SubtypeDecl` 不存在），
`dispatch` 只有规范（⚠，`in Lexer.KEYWORDS` = False 且 `cypyc/` 无落点）；
`len(Lexer.KEYWORDS)` 实测 65。裁决与验收细节见 `SYNTAX/33-type-constraints-subtypes-dispatch.md` §7.1。
`SYNTAX_IMPLEMENTATION_STATUS.md` §2.4 / §7 的同三条语法已同步为同一套三态（本轮由 `T0r258.5.2`
带着 `T0r258.1.2` 的验收号一起改，两份文档不再互相打架；机检 `feat_docs_01.py` 的 X1/X3 归零是这次对齐的判据）。

---

## 2. 需要审核的语法移除/调整

### 2.1 冗余关键字建议移除

| 关键字 | 问题说明 | 建议 |
|--------|----------|------|
| `cdef` | 与 `def` 功能重叠，有类型注解时自动生成 cpdef | **建议移除** |
| `POINTER` | 使用指针类型 `T*` 语法更直观 | **建议移除** |
| `NO_STRATEGY` | 使用场景有限，文档未说明用途 | **建议移除** |
| `FOR_KW` | 与 `FOR` 重复定义 | **建议合并到 FOR** |

### 2.2 冗余 Token 建议清理

| Token | 问题说明 | 建议 |
|-------|----------|------|
| `FAT_ARROW` (`=>`) | 未在语法中使用 | **建议保留**（可能用于未来 match 箭头） |
| `BACKTICK_BLOCK` | 解析支持但 codegen 不完整 | **建议完善实现** |

---

## 3. 需要补充文档的语法

| 语法 | 文档位置 | 需补充内容 |
|------|----------|-----------|
| 联合类型 | 已建 `26-union-type.md`（176 行） | `A \| B` 语法与类型检查 |
| 类型约束三件套（constraint / subtype / dispatch） | 已建 `33-type-constraints-subtypes-dispatch.md`（783 行；实测文内计数 124 / 121 / 119 次） | 三者的语义规范与期望行为；本行原指向 `27-constraints.md` 是错的（该文件实测 475 行、`duck` 出现 50 次、另两词各 0 次，它是**已实现**的 duck 约束规范） |
| 元块 | 更新 `00-introduction.md` | `meta:` 块语法 |
| 命名参数糖 | 更新 `14-syntax-sugar.md` | `name~` 语法 |

---

## 4. 需要补充测试的语法

| 语法 | 现有测试 | 需补充测试 |
|------|----------|-----------|
| `VecType`/`VecLiteral` | 无 | `test_vec.py` |
| `UnionType` | 无 | `test_union_type.py` |
| `MacroDef`/`MacroCall` | 无 | `test_macro.py` |
| `ConstraintDef` | 无 | `test_constraint.py` |
| 项目级编译 | 无 | `test_project_compiler.py` |
| 跨模块类型推断 | 无 | `test_cross_module_types.py` |

---

## 5. 待完善功能

| 功能 | 当前状态 | 建议优先级 |
|------|----------|-----------|
| 宏的编译期展开 | 生成桩代码，未真正展开 | 高 |
| `UnionType` 类型检查 | 降级为 object，无运行时检查 | 中 |
| `BacktickBlock` 代码生成 | 解析支持，codegen 部分 | 低 |

---

## 6. 文档清理建议

### 6.1 `.trae/documents/` 历史规划文档

以下文档为历史版本规划，建议归档或删除：

| 文档 | 状态 | 建议 |
|------|------|------|
| `cypy-next-steps-plan.md` | 已过时 | 删除 |
| `cypy-next-steps-plan-2.md` | 已过时 | 删除 |
| `cypy-next-steps-plan-3.md` | 已过时 | 删除 |
| `bug-fix-plan.md` | 已完成 | 删除 |
| `codegen-fix-plan.md` | 已完成 | 删除 |
| `integration_test_fix_plan.md` | 已完成 | 删除 |
| `test-suite-plan.md` | 已完成 | 删除 |
| `pointer_check_plan.md` | 已完成 | 删除 |

### 6.2 `.hermes/plans/` 历史计划

| 文档 | 状态 | 建议 |
|------|------|------|
| `2026-07-29_210000-cypy-project-masterplan-v2.md` | 参考价值 | 保留 |
| `2026-07-29_122900-cypy-project-masterplan.md` | 已过时 | 删除 |

---

## 7. 审核结果

**审核时间**: 2026-07-30
**审核结果**: 已执行

### 7.1 移除关键字（已执行）

实测口径（2026-09-26，全部只读）：`Lexer.KEYWORDS` 决定某词是否还是关键字；
`grep -rn 'TokenType\.<NAME>' cypyc/ --include=*.py | wc -l` 决定该 Token 是否还有引用。

- [x] `POINTER` 关键字 - ✅ **已移除**（实测 `grep -rn POINTER cypyc/ --include=*.py` = **0** 命中，连枚举成员都不存在）
- [x] `cdef` 关键字 - ✅ **已移除**（2026-07-30 的「保留」结论经实测作废：`cdef` **不在** `Lexer.KEYWORDS` 里；
  `TokenType.CDEF` 只剩 `cypyc/parser/lexer.py:84` 的定义行，`grep -rn 'TokenType\.CDEF' cypyc/` = **0** 引用）
- [x] `NO_STRATEGY` 关键字 - ✅ **已移除**（原结论「用作 `@no_strategy` 装饰器，有实际用途」不成立：
  它不在 `Lexer.KEYWORDS`，`grep -rni no_strategy cypyc/ cypy_bridge/` 全仓只有 **1** 处命中，
  就是 `cypyc/parser/lexer.py:134` 那行死枚举本身，`TokenType.NO_STRATEGY` 引用 **0** 处）
- [ ] `FOR_KW` Token - ❌ **保留**（实测确在：定义 `cypyc/parser/lexer.py:110`，
  `cypyc/parser/parser.py:2445` 与 `:2477` 各引用 1 次；但 lexer 从不产出它——
  `KEYWORDS` 里 `"for"` 映射到 `TokenType.FOR`（`lexer.py:170`），
  `grep -rn 'Token(TokenType\.FOR_KW' cypyc/` = **0** 命中，故那两个分支当前不可达。
  「非重复定义」成立，「用于歧义消解」在实测上是死路径）

**说明**：原「`cdef`、`NO_STRATEGY`、`FOR_KW` 均有实际用途」与实测相反，已按上面三条更正。
残留的死枚举（`TokenType.CDEF`、`TokenType.NO_STRATEGY` 各 1 行，共 0 引用）属词表清理类工作，
本单元只做文档对齐，未动 `cypyc/`，也未登记为缺陷。

### 7.2 补充文档（已执行）

- [x] 新建 `26-union-type.md` - ✅ 已创建（176 行，`A | B` 匿名联合类型）
- [x] 新建 `27-constraints.md` - ✅ 已创建（475 行，实测文内 `duck` 出现 50 次、`_duck_registry` 2 次：
  它是**已实现的 `duck` 鸭子约束**规范，与本清单 §3 早期误指向的三件套无关）
- [x] 新建 `33-type-constraints-subtypes-dispatch.md` - ✅ 已创建（783 行，`constraint` 124 /
  `subtype` 121 / `dispatch` 119 次；本轮 `T0r258.1.1~3.1` 写入，`git status --short SYNTAX/` 仍显示
  未跟踪 `?? SYNTAX/33-type-constraints-subtypes-dispatch.md`，本单元无权 `git add`）
- [x] 更新 `README.md` - ✅ 已更新（添加项目级编译说明）
- [x] 更新 `21-simd-vector.md` - ✅ 已更新（vec 语法说明）
- [x] 更新 `18-macros.md` - ✅ 已更新（宏语法说明）
- [x] 更新 `23-compilation.md` - ✅ 已更新（项目级编译说明，249 行）

### 7.3 补充测试（已执行）

- [x] 创建 `test_vec.py` - ✅ 已创建（9 测试）
- [x] 创建 `test_union_type.py` - ✅ 已创建（10 测试）
- [x] 创建 `test_macro.py` - ✅ 已创建（8 测试）
- [x] 创建 `test_project_compiler.py` - ✅ 已创建（6 测试）

### 7.4 文档清理（已执行）

- [x] 删除 `.trae/documents/` 中的历史规划文档（12 个文件）
- [x] 删除 `.hermes/plans/` 中的历史计划文档（1 个文件）
- [x] 清理 `test_reports/` 中的重复测试报告（保留最新版本）

### 7.5 测试验证

| 测试类别 | 测试数量 | 通过 | 失败 |
|---------|----------|------|------|
| test_vec.py | 9 | 9 | 0 |
| test_union_type.py | 10 | 10 | 0 |
| test_macro.py | 8 | 8 | 0 |
| test_project_compiler.py | 6 | 6 | 0 |
| 现有测试套件 | 46 | 46 | 0 |
| **总计** | **79** | **79** | **0** |

---

**审核说明**：

1. **同意**：将立即执行
2. **拒绝**：保持现状，不做修改
3. **待定**：需要进一步讨论后再决定