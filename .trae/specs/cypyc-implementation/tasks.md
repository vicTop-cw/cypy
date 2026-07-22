# Cypy 转译器 (cypyc) 实现计划

## 项目结构设计

```
cypy/                          # 项目根目录
├── cypyc/                     # 转译器核心模块
│   ├── __init__.py
│   ├── __main__.py            # 命令行入口
│   ├── cli.py                 # 命令行参数解析
│   ├── parser/                # 解析器模块
│   │   ├── __init__.py
│   │   ├── lexer.py           # 词法分析器（tokenizer）
│   │   ├── parser.py          # 语法分析器（AST 构建）
│   │   └── preprocessor.py    # 预处理器（关键字替换）
│   ├── analyzer/              # 语义分析器模块
│   │   ├── __init__.py
│   │   ├── scope_analyzer.py  # 作用域分析
│   │   ├── type_checker.py    # 类型检查器
│   │   ├── defer_analyzer.py  # defer 语句收集
│   │   └── pointer_checker.py # 指针清理检查
│   ├── transformer/           # AST 转换器模块
│   │   ├── __init__.py
│   │   ├── struct_transformer.py
│   │   ├── enum_transformer.py
│   │   ├── trait_transformer.py
│   │   ├── defer_transformer.py
│   │   ├── generic_transformer.py
│   │   └── meta_transformer.py
│   ├── codegen/               # 代码生成器模块
│   │   ├── __init__.py
│   │   ├── cython_generator.py
│   │   ├── type_mapper.py     # 类型映射表
│   │   └── setup_generator.py # setup.py 生成
│   └── utils/                 # 工具模块
│       ├── __init__.py
│       ├── ast_utils.py
│       ├── indent_detector.py
│       └── error_reporter.py
├── cypy_hook/                 # Import hook 模块
│   ├── __init__.py
│   └── hook.py                # 实时转译 hook
├── tests/                     # 测试模块
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_analyzer.py
│   ├── test_transformer.py
│   ├── test_codegen.py
│   ├── test_cli.py
│   └── test_hook.py
├── examples/                  # 示例代码
│   ├── hello.cypy
│   ├── struct.cypy
│   ├── defer.cypy
│   ├── generic.cypy
│   └── meta.cypy
├── setup.py                   # 项目安装脚本
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

---

## Phase 1: 基础架构搭建

### [x] Task 1.1: 项目结构初始化
- **Priority**: high
- **Depends On**: None
- **Description**: 创建项目目录结构和基础配置文件
- **Acceptance Criteria Addressed**: N/A
- **Test Requirements**:
  - `programmatic` TR-1.1.1: 所有目录和文件正确创建
  - `programmatic` TR-1.1.2: `python -m cypyc --help` 输出帮助信息
- **Notes**: 使用 pyproject.toml 管理项目依赖

### [x] Task 1.2: 词法分析器 (Lexer)
- **Priority**: high
- **Depends On**: Task 1.1
- **Description**: 实现词法分析器，将 Cypy 源码分解为 token 流
- **Acceptance Criteria Addressed**: FR-1, FR-6, FR-9, FR-11, FR-12
- **Test Requirements**:
  - `programmatic` TR-1.2.1: 正确识别 `struct`、`enum`、`trait`、`impl`、`defer`、`meta` 关键字
  - `programmatic` TR-1.2.2: 正确识别泛型中括号 `[T, U]`
  - `programmatic` TR-1.2.3: 正确识别指针类型 `int*`
  - `programmatic` TR-1.2.4: 正确识别 `|>` 管道操作符
- **Notes**: 使用正则表达式或手工实现，后续可考虑使用 PLY

### [x] Task 1.3: 语法分析器 (Parser)
- **Priority**: high
- **Depends On**: Task 1.2
- **Description**: 实现 PEG 语法分析器，构建 Cypy AST
- **Acceptance Criteria Addressed**: FR-1, FR-6, FR-7, FR-8, FR-9, FR-11, FR-12
- **Test Requirements**:
  - `programmatic` TR-1.3.1: 正确解析 `struct` 定义
  - `programmatic` TR-1.3.2: 正确解析 `enum` 定义
  - `programmatic` TR-1.3.3: 正确解析 `trait` 和 `impl` 定义
  - `programmatic` TR-1.3.4: 正确解析 `defer` 语句
  - `programmatic` TR-1.3.5: 正确解析泛型类型 `Pair[T, U]`
  - `programmatic` TR-1.3.6: 正确解析 `meta` 块
- **Notes**: 使用 parsec 或 pyparsing 实现 PEG 解析器

### [x] Task 1.4: 作用域分析器
- **Priority**: high
- **Depends On**: Task 1.3
- **Description**: 实现缩进层级检测和作用域树构建
- **Acceptance Criteria Addressed**: FR-9
- **Test Requirements**:
  - `programmatic` TR-1.4.1: 正确计算缩进层级（0-模块，1-类/函数，≥2-代码块）
  - `programmatic` TR-1.4.2: 正确构建作用域树
  - `programmatic` TR-1.4.3: 正确收集每个作用域的变量和 defer 语句
- **Notes**: 参考语法文档中的 ScopeNode 伪代码

---

## Phase 2: 核心转译功能

### [x] Task 2.1: 类型映射器
- **Priority**: high
- **Depends On**: Task 1.4
- **Description**: 实现 Cypy 类型到 Cython 类型的映射表
- **Acceptance Criteria Addressed**: FR-10, FR-11
- **Test Requirements**:
  - `programmatic` TR-2.1.1: `int` → `cdef int`
  - `programmatic` TR-2.1.2: `double` → `cdef double`
  - `programmatic` TR-2.1.3: `int*` → `cdef int*`
  - `programmatic` TR-2.1.4: `str` → `cdef str`
  - `programmatic` TR-2.1.5: 无注解 → `object`
- **Notes**: 参考语法文档中的类型映射表

### [x] Task 2.2: Struct 转译器
- **Priority**: high
- **Depends On**: Task 2.1
- **Description**: 实现 `struct` 到 Cython `cdef struct` 的转译
- **Acceptance Criteria Addressed**: FR-6, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.2.1: `struct Point: x: int; y: int` → `cdef struct Point: cdef int x; cdef int y`
  - `programmatic` TR-2.2.2: 支持泛型结构体 `struct Pair[T, U]`
- **Notes**: 泛型结构体需要特化处理

### [x] Task 2.3: Defer 转译器
- **Priority**: high
- **Depends On**: Task 1.4, Task 2.1
- **Description**: 实现 `defer` 语句到 try/finally 的转译
- **Acceptance Criteria Addressed**: FR-9, AC-6
- **Test Requirements**:
  - `programmatic` TR-2.3.1: 单个 defer 正确生成 try/finally
  - `programmatic` TR-2.3.2: 多个 defer 按 LIFO 顺序执行
  - `programmatic` TR-2.3.3: defer 在 return 前正确执行
  - `programmatic` TR-2.3.4: defer 在异常时正确执行
- **Notes**: 参考语法文档中的 defer 编译优化规则

### [x] Task 2.4: 指针操作转译
- **Priority**: high
- **Depends On**: Task 2.1
- **Description**: 实现 `&` 解引用和 `addr()` 取地址的转译
- **Acceptance Criteria Addressed**: FR-10, AC-7
- **Test Requirements**:
  - `programmatic` TR-2.4.1: `&ptr = 42` → `ptr[0] = 42`
  - `programmatic` TR-2.4.2: `value = &ptr` → `value = ptr[0]`
  - `programmatic` TR-2.4.3: `addr(local)` → `&local`
  - `programmatic` TR-2.4.4: `addr(arr[i])` → `&arr[i]`
- **Notes**: `addr()` 仅适用于 C 类型变量

### [x] Task 2.5: Enum 转译器
- **Priority**: medium
- **Depends On**: Task 2.1
- **Description**: 实现 `enum` 到 Python enum 或 C 枚举的转译
- **Acceptance Criteria Addressed**: FR-7
- **Test Requirements**:
  - `programmatic` TR-2.5.1: `enum Color: RED = 1; GREEN = 2` → Python Enum 或 C 枚举
- **Notes**: 支持自定义值和自动递增

---

## Phase 3: 高级类型系统

### [x] Task 3.1: 泛型转译器
- **Priority**: high
- **Depends On**: Task 2.2
- **Description**: 实现泛型类型的转译，支持类型特化和擦除
- **Acceptance Criteria Addressed**: FR-11, AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1.1: 泛型结构体 `Pair[int, str]` 生成特化代码
  - `programmatic` TR-3.1.2: 泛型函数 `def identity[T](value: T) -> T` 生成特化或擦除代码
  - `programmatic` TR-3.1.3: 泛型 trait `trait Collection[T]` 正确处理类型约束
- **Notes**: C 类型参数使用特化，Python 对象使用类型擦除

### [x] Task 3.2: Trait 和 Impl 转译器
- **Priority**: medium
- **Depends On**: Task 2.1
- **Description**: 实现 `trait` 和 `impl` 的转译，支持 AST 合并
- **Acceptance Criteria Addressed**: FR-8
- **Test Requirements**:
  - `programmatic` TR-3.2.1: `trait Drawable: def draw(self)` 定义接口
  - `programmatic` TR-3.2.2: `impl Drawable for Circle` 将方法合并到 Circle 类
- **Notes**: 需要在语义分析阶段进行方法合并

### [x] Task 3.3: Meta 类型系统转译器
- **Priority**: medium
- **Depends On**: Task 3.1
- **Description**: 实现 `meta` 块的解析和多重分派代码生成
- **Acceptance Criteria Addressed**: FR-12, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.3.1: `meta: constraint Number = int | float` 定义类型约束
  - `programmatic` TR-3.3.2: `meta: subtype Dog <: Animal` 定义子类型关系
  - `programmatic` TR-3.3.3: `meta: dispatch meet(a: Dog, b: Cat)` 生成特化函数和调度器
- **Notes**: meta 块不生成运行时代码，仅指导转译器

---

## Phase 4: 语法糖和工具链

### [x] Task 4.1: 管道操作符转译
- **Priority**: low
- **Depends On**: Task 1.3
- **Description**: 实现 `|>` 管道操作符的转译
- **Acceptance Criteria Addressed**: FR-13, AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1.1: `result = data |> process |> filter` → `result = filter(process(data))`
- **Notes**: 已有基础实现，需要迁移到 AST 解析

### [x] Task 4.2: Val 和 Let 语法转译
- **Priority**: low
- **Depends On**: Task 1.3, Task 2.1
- **Description**: 实现 `val`（不可变变量）和 `let`（块级绑定）的转译
- **Acceptance Criteria Addressed**: FR-13, FR-14
- **Test Requirements**:
  - `programmatic` TR-4.2.1: `val PI: double = 3.14` → `PI: double = 3.14`（编译期检查不可变）
  - `programmatic` TR-4.2.2: `if let content = read_file(path)` → `content = read_file(path); if content:`
- **Notes**: `val` 需要在类型检查阶段验证不可变性

### [x] Task 4.3: 命令行接口 (CLI)
- **Priority**: high
- **Depends On**: Task 2.2, Task 2.3, Task 2.4
- **Description**: 实现 `cypyc` 命令行工具
- **Acceptance Criteria Addressed**: FR-1, FR-2, FR-3, FR-4, AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-4.3.1: `cypyc input.cypy` 生成 `input.pyx`
  - `programmatic` TR-4.3.2: `cypyc --check input.cypy` 输出类型检查结果
  - `programmatic` TR-4.3.3: `cypyc --check-memory input.cypy` 输出内存泄漏警告
  - `programmatic` TR-4.3.4: `cypyc --compile input.cypy` 完成完整编译流程
- **Notes**: 使用 argparse 实现命令行参数解析

### [x] Task 4.4: Import Hook 实现
- **Priority**: medium
- **Depends On**: Task 4.3
- **Description**: 实现 import hook，支持开发阶段实时转译
- **Acceptance Criteria Addressed**: FR-5, AC-4
- **Test Requirements**:
  - `programmatic` TR-4.4.1: 安装 hook 后 `import test` 能加载 `test.cypy`
  - `programmatic` TR-4.4.2: 修改 `test.cypy` 后重新导入能加载最新代码
- **Notes**: 参考现有 `cypy_hook.py` 实现

---

## Phase 5: 质量保障和优化

### [x] Task 5.1: 类型检查器
- **Priority**: high
- **Depends On**: Task 2.1, Task 1.4
- **Description**: 实现完整的类型检查器
- **Acceptance Criteria Addressed**: FR-2, AC-2
- **Test Requirements**:
  - `programmatic` TR-5.1.1: 检测类型不匹配错误
  - `programmatic` TR-5.1.2: 检测未声明变量错误
  - `programmatic` TR-5.1.3: 检测指针类型未显式注解错误
- **Notes**: 参考语法文档中的类型系统设计

### [x] Task 5.2: 指针清理检查器
- **Priority**: medium
- **Depends On**: Task 1.4, Task 2.3
- **Description**: 实现指针内存泄漏检查
- **Acceptance Criteria Addressed**: FR-3, AC-3
- **Test Requirements**:
  - `programmatic` TR-5.2.1: 检测未使用 defer 清理的指针变量
  - `programmatic` TR-5.2.2: 检测 use-after-free 错误（返回后使用已释放指针）
- **Notes**: 需要跟踪指针的生命周期

### [x] Task 5.3: 代码生成器优化
- **Priority**: low
- **Depends On**: Task 4.3
- **Description**: 优化生成的 Cython 代码质量
- **Acceptance Criteria Addressed**: NFR-3
- **Test Requirements**:
  - `human-judgment` TR-5.3.1: 生成的代码格式清晰，便于阅读和调试
- **Notes**: 添加适当的注释和代码格式化

### [x] Task 5.4: 测试套件
- **Priority**: high
- **Depends On**: 所有其他任务
- **Description**: 编写完整的测试套件
- **Acceptance Criteria Addressed**: NFR-7
- **Test Requirements**:
  - `programmatic` TR-5.4.1: 单元测试覆盖率 > 80%
  - `programmatic` TR-5.4.2: 集成测试覆盖所有语法构造
- **Notes**: 使用 pytest 作为测试框架

---

## 任务依赖关系图

```
Task 1.1 ──→ Task 1.2 ──→ Task 1.3 ──→ Task 1.4 ──→ Task 2.1
                                                           │
                    ┌──────────────────────────────────────┘
                    ▼
          Task 2.2 ──→ Task 3.1 ──→ Task 3.3
                    ├──→ Task 2.3
                    ├──→ Task 2.4
                    └──→ Task 2.5

Task 2.1 ──→ Task 3.2

Task 1.3 ──→ Task 4.1
Task 2.1 ──→ Task 4.2

Task 2.2, 2.3, 2.4 ──→ Task 4.3 ──→ Task 4.4

Task 2.1, 1.4 ──→ Task 5.1
Task 1.4, 2.3 ──→ Task 5.2

Task 4.3 ──→ Task 5.3

所有任务 ──→ Task 5.4
```

---

## 时间节点规划

| 阶段 | 任务 | 预计时间 | 里程碑 |
|------|------|----------|--------|
| Phase 1 | 1.1-1.4 | 2 周 | 基础解析器完成 |
| Phase 2 | 2.1-2.5 | 3 周 | 核心转译功能完成 |
| Phase 3 | 3.1-3.3 | 3 周 | 高级类型系统完成 |
| Phase 4 | 4.1-4.4 | 2 周 | 工具链完成 |
| Phase 5 | 5.1-5.4 | 2 周 | 质量保障完成 |
| **总计** | | **12 周** | **1.0 版本发布** |

---

## 资源需求评估

| 资源类型 | 需求 |
|----------|------|
| 开发人员 | 2-3 人（编译器设计、Python 开发、Cython 专家） |
| 测试人员 | 1 人 |
| 硬件资源 | 标准开发机（8GB+ RAM） |
| 软件资源 | Python 3.8+、Cython 3.0+、pytest、parsec/pyparsing |

---

## 风险评估与应对策略

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|----------|
| 解析器复杂度高 | 高 | 高 | 采用 PEG 解析器，分阶段实现，先支持核心语法 |
| 类型系统设计复杂 | 中 | 高 | 参考 Julia 设计，从简单类型检查开始，逐步扩展 |
| 泛型特化实现困难 | 中 | 中 | 先实现类型擦除，再逐步添加特化支持 |
| Cython 兼容性问题 | 中 | 中 | 使用 Cython 3.0+，定期测试兼容性 |
| 性能问题 | 低 | 中 | 使用 AST 缓存，优化代码生成路径 |
| 文档与代码不一致 | 中 | 低 | 保持文档和代码同步，定期审查 |

---

## 质量保障措施

1. **代码审查**：所有代码提交前必须经过至少一人审查
2. **单元测试**：每个模块必须有对应的单元测试
3. **集成测试**：覆盖完整转译流程的端到端测试
4. **性能测试**：定期运行性能基准测试
5. **文档更新**：代码变更必须同步更新文档
6. **CI/CD**：配置持续集成，自动运行测试