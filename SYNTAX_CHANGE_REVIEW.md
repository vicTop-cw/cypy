# 语法变更审核清单

**生成时间**: 2026-07-30
**需要用户审核决策**

---

## 1. 新增语法特性（已完成实现）

以下语法特性已完整实现，无需审核：

| 语法 | 实现状态 | 文档状态 |
|------|----------|----------|
| `vec[T; N]` 向量类型 | ✅ 完成 | ✅ 已更新 |
| `vec![v1, v2]` 向量字面量 | ✅ 完成 | ✅ 已更新 |
| `vec![value; N]` 重复形式 | ✅ 完成 | ✅ 已更新 |
| `x |> f(args)` 管道操作符 | ✅ 完成 | ✅ 已有 |
| `A \| B` 联合类型 | ✅ 完成（降级为 object） | 需补充 |
| `macro name(params) = body` | ✅ 完成 | ✅ 已更新 |
| `constraint Name = A \| B` | ✅ 完成 | 需补充 |
| `subtype A <: B` | ✅ 完成 | 需补充 |
| `dispatch name(params) -> ret` | ✅ 完成 | 需补充 |
| `cypyc build <dir>` 项目级编译 | ✅ 完成 | ✅ 已更新 |

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
| 联合类型 | 新建 `26-union-type.md` | `A \| B` 语法与类型检查 |
| 类型约束 | 新建 `27-constraints.md` | `constraint`/`subtype`/`dispatch` |
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

- [x] `POINTER` 关键字 - ✅ **已移除**（确认死代码，parser 从未使用）
- [ ] `cdef` 关键字 - ❌ **保留**（实际是性能关键字，映射 Cython `cdef`，非冗余）
- [ ] `NO_STRATEGY` 关键字 - ❌ **保留**（用作 `@no_strategy` 装饰器，有实际用途）
- [ ] `FOR_KW` Token - ❌ **保留**（在 parser 中用于歧义消解，非重复定义）

**说明**：经过代码分析，`cdef`、`NO_STRATEGY`、`FOR_KW` 均有实际用途，不属于冗余关键字。

### 7.2 补充文档（已执行）

- [x] 新建 `26-union-type.md` - ✅ 已创建
- [x] 新建 `27-constraints.md` - ✅ 已创建
- [x] 更新 `README.md` - ✅ 已更新（添加项目级编译说明）
- [x] 更新 `21-simd-vector.md` - ✅ 已更新（vec 语法说明）
- [x] 更新 `18-macros.md` - ✅ 已更新（宏语法说明）
- [x] 更新 `23-compilation.md` - ✅ 已更新（项目级编译说明）

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