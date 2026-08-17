# Changelog

本项目所有重要变更均记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-08-17

### 新增

- **编译器核心**：`cypyc` 命令行工具，支持 `transpile` / `compile` / `run` / `hook` 子命令。
- **语法特性**：结构体（struct）、枚举（enum）、trait、泛型、模式匹配、管道运算符（`|>`）、
  列表推导、`let`/`var` 变量语义、`defer`、`go` 协程、`spawn` 线程、指针操作、
  编译期元编程（comptime / meta block）、宏展开、联合类型（union）、SIMD 向量类型。
- **类型系统**：渐进式类型标注、编译期类型检查、类型推断、泛型约束、magic traits。
- **双后端**：Cython 后端（默认）与 Bridge 后端（直接生成 C 代码并编译为 `.pyd`）。
- **增量编译**：增量编译缓存、热重载、动态代码感知系统。
- **测试体系**：`tests/` 与 `test_suite/` 双测试体系，覆盖语法、类型、代码生成、
  集成、性能基准与代码质量检查。

### 修复

- 修复 Bridge 后端链接时硬编码 `python313.lib` 导致非 3.13 环境编译失败的问题，
  改为按当前解释器版本动态生成库名。
- 修复 Bridge 后端缓存未按 Python 版本隔离，导致跨版本 `.pyd` 缓存污染、
  导入失败的问题。
- 修复 `try/except` 无参 `raise` 时异常值为 `NULL`，对 `NULL` 调用
  `PyObject_IsInstance` 导致原生层访问违例（access violation）崩溃的问题，
  改用 `PyErr_GivenExceptionMatches` 进行异常类型匹配。
- 修复 `tests/code_quality/test_code_quality.py` 中 f-string 反斜杠语法错误
  （Python 3.11 不允许），恢复测试收集。

### 变更

- 项目按 FIST 规范完成 fist 化：部署 `PROJECT-SPEC/` 规范体系与 `omega/` 验证框架。
- 清理根目录调试产物、临时日志与散落测试脚本，统一归档到 `docs/`、`reports/`。
- 示例统一收敛到 `examples/` 目录（`demos/` 分类示例 + `legacy/` 历史示例）。

### 文档

- 新增 `CHANGELOG.md`。
- `docs/` 收录使用说明（USAGE.md）、类型推断计划（PLAN_TYPE_INFERENCE.md）、
  语法变更审核（SYNTAX_CHANGE_REVIEW.md）。
- `SYNTAX/` 提供 33 份语法特性文档。
