# Cypy 语言介绍

## 概述

Cypy（Cython + Python Syntactic Sugar）是一种基于 Python 语法体系的编译型语言，通过 Cython 作为后端实现性能提升，同时引入静态类型系统和丰富的语法糖，在保持 Python 兼容性的前提下提供更好的性能和开发体验。

## 设计理念

| 原则 | 说明 |
|------|------|
| **部分语法兼容** | 支持大部分 Python 语法，但存在一些限制（如缩进必须是4的倍数） |
| **渐进式类型** | 有注解的变量使用静态类型，无注解的变量退化为 PyObject |
| **编译时检查** | `cypyc` 转译器提前发现类型错误 |
| **Cython 后端** | 最终编译目标为 Cython，生成高性能 C 代码 |
| **简洁语法** | 引入必要的语法糖，保持 Python 的可读性 |
| **显式内存管理** | 指针变量默认逃逸，需显式使用 `defer` 延迟清理 |

## 架构层次

```
┌─────────────────────────────────────────────┐
│              Cypy 源码 (.cypy)              │
│  Python 语法 + 类型注解 + Cypy 语法糖       │
└─────────────────────┬───────────────────────┘
                      │ cypyc 转译器
                      ▼
┌─────────────────────────────────────────────┐
│              Cython 代码 (.pyx)             │
│  cdef/cpdef（兼容层）+ 静态类型 + C 特性         │
└─────────────────────┬───────────────────────┘
                      │ Cython 编译器 (cythonize)
                      ▼
┌─────────────────────────────────────────────┐
│                  C 代码 (.c)                │
│  C 函数 + Python C API 调用                  │
└─────────────────────┬───────────────────────┘
                      │ C 编译器 (MSVC/GCC/Clang)
                      ▼
┌─────────────────────────────────────────────┐
│               二进制扩展 (.so/.pyd)          │
│  可直接导入的 Python 扩展模块                │
└─────────────────────────────────────────────┘
```

## 核心特性

1. **静态类型系统** - 支持类型注解、指针类型、泛型
2. **结构体定义** - C 风格的数据结构，支持字段和方法，`@value` 装饰器自动生成比较和哈希方法
3. **特质系统** - trait/impl 实现类似接口的功能，支持泛型特质和特质继承
4. **模式匹配** - match/case 支持常量、变量、元组、列表、字典、结构体、枚举模式
5. **构建块语法** - `=:`、`~:`、`*:` 创建闭包无参函数，支持 early return 和 guard
6. **延迟清理** - `defer` 语句自动资源管理，函数退出时执行
7. **编译期求值** - `comptime` 在编译时执行代码，支持表达式和块形式
8. **宏系统** - 编译期代码生成，支持宏模板和宏展开
9. **增量编译** - 仅重新编译修改的模块，基于 AST 差异和依赖图分析
10. **热重载** - 不中断应用运行更新代码，代理模块模式解决 Windows 文件锁定
11. **`def` 函数系统** - 统一使用 `def` 关键字，有类型注解时生成优化代码（cpdef），无注解时退化为 PyObject（def）
12. **`@python` 装饰器** - 跳过类型检查，仍生成 Cython 代码（非纯 CPython 回退）
13. **渐进式类型** - 无注解变量为 `object` 类型，有注解变量保持静态检查
14. **守卫策略** - 支持 `__guarded_pred__` 和 `__guarded_action__` 兜底机制
15. **隐式类型转换** - 通过 `__implicit_copy__` 和 `__implicit_into__` 实现

## 文件扩展名

| 扩展名 | 说明 |
|--------|------|
| `.cypy` | Cypy 源文件 |
| `.py` | Python 源文件（可导入，不转译；第一行 `#!bin cypy` 标记为 Cypy 代码） |
| `.pyx` | 生成的 Cython 代码 |
| `.pyd`/`.so` | 编译后的二进制扩展 |

## 快速开始

```bash
# 安装
pip install cypy-lang

# 编译单个文件
cypyc --compile input.cypy

# 类型检查（仅检查，不生成代码）
cypyc --check input.cypy

# 启动热重载开发服务器
cypyc watch ./src

# 编译并运行
cypyc run input.cypy
```

## 文档结构

```
SYNTAX/
├── 00-introduction.md          # 语言介绍
├── 01-basic-types.md           # 基础类型系统
├── 02-type-annotations.md      # 类型注解
├── 03-type-conversion.md       # 类型转换
├── 04-pointer-types.md         # 指针类型
├── 05-struct.md                # 结构体
├── 06-enum.md                  # 枚举
├── 06d-builtin-magic-traits.md # 内置魔法特质
├── 07-trait-impl.md            # 特质与实现
├── 08-class.md                 # 类定义
├── 09-functions.md             # 函数
├── 10-variables.md             # 变量声明
├── 11-generics.md              # 泛型系统
├── 12-operators.md             # 操作符
├── 12-type-alias.md            # 类型别名
├── 13-build-blocks.md          # 构建块语法
├── 14-syntax-sugar.md          # 语法糖
├── 15-control-flow.md          # 控制流
├── 16-exceptions.md            # 异常处理
├── 17-pattern-matching.md      # 模式匹配
├── 18-macros.md                # 宏系统
├── 19-comptime.md              # 编译期求值
├── 20-concurrency.md           # 并发
├── 21-simd-vector.md           # SIMD向量
├── 22-magic-properties.md      # 魔法属性
├── 23-compilation.md           # 编译与工具链
├── 24-incremental-hot-reload.md # 增量编译与热重载
└── 25-compatibility.md         # 兼容性
```