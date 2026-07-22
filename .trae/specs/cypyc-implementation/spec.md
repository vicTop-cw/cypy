# Cypy 转译器 (cypyc) 实现 - 产品需求文档

## Overview
- **Summary**: 实现一个完整的 Cypy 语言转译器 `cypyc`，将 Cypy 源码 (.cypy) 转译为 Cython 代码 (.pyx)，最终编译为高性能 C 扩展。包含 import hook 实时转译支持和完整的类型检查系统。
- **Purpose**: 为 Python 开发者提供一个渐进式类型化的编译型语言，在保持 Python 语法兼容性的同时获得 C 级性能提升。
- **Target Users**: Python 开发者、数据科学家、高性能计算工程师、需要编写性能敏感代码的开发者。

## Goals
- 实现完整的 Cypy 转译器 `cypyc`，支持命令行转译和编译
- 实现 import hook 实时转译，支持开发阶段快速迭代
- 实现类型检查系统，在编译期发现类型错误
- 实现 `struct`、`enum`、`trait`、`impl`、`defer`、`meta` 等新语法构造的转译
- 实现指针类型和 `addr()` 内置函数
- 实现泛型类型系统（中括号语法）
- 实现 meta 类型系统，支持多重分派

## Non-Goals (Out of Scope)
- 实现完整的 Cython 编译器（使用现有 Cython 作为后端）
- 支持 Python 2 语法
- 实现 JIT 编译
- 实现运行时反射（meta 仅在编译期有效）
- 实现垃圾回收（指针默认逃逸，需手动 defer）
- 实现并行编译

## Background & Context
- 当前项目已有基础的 `cypy_hook.py`，仅支持 `owend` 和 `|>` 两个简单语法糖
- 语法文档 `CYPY_SYNTAX.md` 已定义完整的语言规范
- 项目分散在两个目录：`E:\IDEProjects\AI\Cypy`（规范文档）和 `E:\IDEProjects\py\study\Pys\Cypy`（运行时代码）
- 需要统一到单一项目结构，并实现完整的转译器

## Functional Requirements
- **FR-1**: 命令行工具 `cypyc` 支持转译单个 .cypy 文件为 .pyx 文件
- **FR-2**: `cypyc` 支持类型检查模式（仅检查不生成代码）
- **FR-3**: `cypyc` 支持内存泄漏检查（指针未清理检测）
- **FR-4**: `cypyc` 支持集成编译（调用 Cython 编译器）
- **FR-5**: Import hook 支持在开发阶段实时转译 .cypy 文件
- **FR-6**: 支持 `struct` 语法转译为 Cython `cdef struct`
- **FR-7**: 支持 `enum` 语法转译为 Python enum 或 C 枚举
- **FR-8**: 支持 `trait` 和 `impl` 语法，实现 AST 合并
- **FR-9**: 支持 `defer` 语句，生成 try/finally 包装
- **FR-10**: 支持指针类型注解（`int*`、`double*` 等）和 `addr()` 内置函数
- **FR-11**: 支持泛型类型（中括号语法），实现类型特化和擦除
- **FR-12**: 支持 `meta` 块，实现类型约束和多重分派规则
- **FR-13**: 支持管道操作符 `|>` 和不可变变量 `val`
- **FR-14**: 支持 `let` 语法（块级绑定）

## Non-Functional Requirements
- **NFR-1**: 转译器处理速度 < 1秒/1000行代码
- **NFR-2**: 类型检查错误信息清晰，包含行号和上下文
- **NFR-3**: 生成的 Cython 代码可读，便于调试
- **NFR-4**: 与 Python 3.8+ 兼容
- **NFR-5**: 与 Cython 3.0+ 兼容
- **NFR-6**: 支持 Windows、Linux、macOS 平台
- **NFR-7**: 代码覆盖率 > 80%

## Constraints
- **Technical**: Python 3.8+，Cython 3.0+，无其他外部依赖
- **Business**: 开源项目，社区驱动
- **Dependencies**: Python ast 模块、Cython 编译器

## Assumptions
- 用户已安装 Python 3.8+ 和 Cython 3.0+
- 用户了解 Python 语法和基本的 C 指针概念
- 开发团队熟悉 Python 编译器设计和 AST 操作

## Acceptance Criteria

### AC-1: 命令行转译
- **Given**: 存在 `test.cypy` 文件，包含 `struct`、`defer` 和类型注解
- **When**: 执行 `cypyc test.cypy`
- **Then**: 生成 `test.pyx` 文件，包含正确的 Cython 代码
- **Verification**: `programmatic`

### AC-2: 类型检查
- **Given**: `test.cypy` 包含类型错误（如将 int 赋值给 double）
- **When**: 执行 `cypyc --check test.cypy`
- **Then**: 输出包含错误位置和描述的类型错误报告
- **Verification**: `programmatic`

### AC-3: 内存泄漏检查
- **Given**: `test.cypy` 中指针变量没有对应的 `defer free()`
- **When**: 执行 `cypyc --check-memory test.cypy`
- **Then**: 输出内存泄漏警告，包含变量名和位置
- **Verification**: `programmatic`

### AC-4: Import hook 实时转译
- **Given**: 安装了 import hook，存在 `test.cypy`
- **When**: Python 脚本执行 `import test`
- **Then**: `test.cypy` 被实时转译并加载为 Python 模块
- **Verification**: `programmatic`

### AC-5: Struct 转译
- **Given**: `struct Point: x: int; y: int`
- **When**: 转译
- **Then**: 生成 `cdef struct Point: cdef int x; cdef int y`
- **Verification**: `programmatic`

### AC-6: Defer 转译
- **Given**: `ptr: int* = malloc(sizeof(int)); defer free(ptr)`
- **When**: 转译
- **Then**: 生成 try/finally 结构，finally 块中调用 `free(ptr)`
- **Verification**: `programmatic`

### AC-7: 指针操作
- **Given**: `&ptr = 42` 和 `addr(local)`
- **When**: 转译
- **Then**: `&ptr` 转译为 `ptr[0]`，`addr(local)` 转译为 `&local`
- **Verification**: `programmatic`

### AC-8: 泛型转译
- **Given**: `struct Pair[T, U]: first: T; second: U`
- **When**: 转译
- **Then**: 生成特化的 Cython 结构体或类型擦除的实现
- **Verification**: `programmatic`

### AC-9: Meta 多分派
- **Given**: `meta: dispatch meet(a: Dog, b: Cat) -> str` 和对应实现
- **When**: 转译
- **Then**: 生成特化函数和分派调度器
- **Verification**: `programmatic`

### AC-10: 管道操作符
- **Given**: `result = data |> process |> filter`
- **When**: 转译
- **Then**: 生成 `result = filter(process(data))`
- **Verification**: `programmatic`

## Open Questions (已解决)
- [x] **解析策略选择**: 当前使用自定义词法分析器（手工实现）+ 递归下降解析器，不使用 PLY 或 parsec，因为语法相对简单且自定义实现更灵活、性能更好
- [x] **泛型转译策略**: 采用混合策略，对于 C 类型参数使用类型特化，对于 Python 对象类型使用类型擦除
- [x] **meta 分派调度器**: 采用编译期静态分派，在转译时根据类型约束生成特化函数和调度器
- [x] **`cypyc --watch` 热重载**: 暂不实现，当前 import hook 已经支持开发阶段的实时转译