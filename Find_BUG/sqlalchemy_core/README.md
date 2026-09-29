# sqlalchemy_core — Cypy 复刻（复刻库压测 · Phase 3 运算符重载 + trait）

将 SQLAlchemy Core **表达式语言子集**（SQL 表达式树 DSL）移植到 Cypy，用于压测编译器在
**运算符重载 / trait 多态 / dict / list / while / 字符串拼接 / isinstance 自省** 等路径上的正确性。

## 移植内容（子集）

- `ClauseElement` trait —— 表达式节点统一接口（`compile() -> str`）
- `Column` struct —— 列节点，重载 `__eq__/__ne__/__lt__/__le__/__gt__/__ge__/__and__/__or__/__add__/__sub__`，以及 `in_()`
- `_BinaryExpression` / `_InExpression` struct —— 二元/IN 表达式节点（含链式 `__and__/__or__`）
- `Table` struct —— 列集合（`dict<str, Column>`）
- `Select` struct —— `where(...)` 链式 + `compile()` 拼 SQL
- `build_query()` —— 端到端冒烟：`SELECT * FROM users WHERE id = 5 AND age > 18`

## 压测方式

```powershell
python -m cypyc build Find_BUG/sqlalchemy_core --check-only   # 仅类型检查
python -m cypyc build Find_BUG/sqlalchemy_core                 # 完整构建（可运行 .pyd）
```

自动化回归见 `tests/test_find_bug_sqlalchemy_core.py`（编译 + 运行时执行 + 默认参数单测）。

## 由此暴露并修复/记录的编译器缺陷

| Bug | 说明 | 状态 |
|-----|------|------|
| BUG-022 | 函数/方法默认参数值在 codegen 中丢失 | ✅ Fixed |
| BUG-023 | trait 包装器不转发运算符重载 + `isinstance(具体实例, Trait)` 运行时为假 | ⚠️ Workaround（已知局限） |

详见根目录 `Find_BUG/BUGS.md`。
