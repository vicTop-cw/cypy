# 编译与工具链

## 编译流程

### 转译流程

```
┌─────────────────────────────────────────────┐
│              Cypy 源码 (.cypy)              │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              词法分析 (Lexer)               │
│  将源码转换为 Token 流                      │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              语法分析 (Parser)              │
│  将 Token 流转换为 AST                     │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              语义分析 (Analyzer)            │
│  作用域分析、类型检查、依赖分析              │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              代码生成 (Codegen)             │
│  将 AST 转换为 Cython 代码                  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              Cython 编译器                  │
│  cythonize 生成 C 代码                      │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              C 编译器                       │
│  MSVC/GCC/Clang 生成 .pyd/.so              │
└─────────────────────────────────────────────┘
```

## 命令行工具

### 基本命令

```bash
# 编译单个文件
cypyc --compile input.cypy

# 类型检查（仅检查，不生成代码）
cypyc --check input.cypy

# 编译并运行
cypyc run input.cypy

# 编译整个目录
cypyc --compile ./src --output ./build

# 启动热重载开发服务器
cypyc watch ./src

# 显示帮助
cypyc --help
```

### 选项

```bash
# 输出详细日志
cypyc --compile input.cypy --verbose

# 指定输出目录
cypyc --compile input.cypy --output ./build

# 指定编译配置文件
cypyc --compile input.cypy --profile release

# 清理缓存
cypyc --clean
```

## 项目级编译

### 基本用法

```bash
# 编译整个项目（支持跨模块类型推断）
cypyc build <project_directory>

# 指定输出目录
cypyc build <project_directory> -o output

# 指定入口模块（只编译该模块及其依赖）
cypyc build <project_directory> --entry main

# 仅类型检查
cypyc build <project_directory> --check-only

# 详细输出
cypyc build <project_directory> -v
```

### 编译流程

项目级编译采用两阶段处理：

1. **第一阶段 - 类型收集**
   - 扫描所有 `.cypy` 文件
   - 解析所有模块的 AST
   - 构建模块依赖图
   - 收集所有模块的导出类型到 `TypeRegistry`

2. **第二阶段 - 类型检查与编译**
   - 按拓扑顺序编译模块（依赖模块先编译）
   - 使用 `TypeRegistry` 进行跨模块类型推断
   - 生成 Cython 代码并编译为 `.pyd`

### 示例项目结构

```
my_project/
├── types.cypy      # 类型定义模块
├── geometry.cypy   # 依赖 types
├── main.cypy       # 依赖 types 和 geometry
└── output/
    ├── types/
    │   └── types.pyd
    ├── geometry/
    │   └── geometry.pyd
    └── main/
        └── main.pyd
```

### 跨模块类型推断

项目级编译支持跨模块类型推断：

```python
# types.cypy
def create_point(x: float, y: float) -> tuple<float, float>:
    return (x, y)

# geometry.cypy
from types import create_point

def midpoint(p1: tuple<float, float>, p2: tuple<float, float>) -> tuple<float, float>:
    mx = (p1[0] + p2[0]) / 2.0
    my = (p1[1] + p2[1]) / 2.0
    return create_point(mx, my)
```

编译时，`geometry.cypy` 能够正确识别 `create_point` 的类型签名。

## 缓存机制

### 缓存目录

```
__pycache__/
└── cypy/
    ├── <hash>/
    │   ├── input.pyx      # 生成的 Cython 代码
    │   ├── input.c        # 生成的 C 代码
    │   ├── input.pyd      # 编译后的二进制
    │   └── manifest.json  # 元数据
    └── manifest.json      # 全局缓存索引
```

### 缓存策略

```python
# 缓存基于文件内容的 SHA256 哈希
# 仅当文件内容变化时重新编译
# 使用 mtime 检测文件修改
```

### 文件锁定处理

```python
# 当检测到文件锁定时（Windows）
# 自动切换到临时目录编译
# 然后复制到目标位置
```

## 导入机制

### 自定义导入钩子

```python
# Cypy 使用自定义导入钩子
# 自动识别 .cypy 文件和带 #!bin cypy 的 .py 文件
# 编译并导入为普通 Python 模块

import my_module  # 自动检测并编译 .cypy 文件
```

### 编译后导入

```python
# 编译后的模块可以直接导入
import my_compiled_module  # 导入 .pyd 文件
```

## 性能优化

### 编译优化

```bash
# 使用 release 配置
cypyc --compile input.cypy --profile release

# 启用优化选项
cypyc --compile input.cypy --opt=3
```

### 类型优化

```python
# 使用静态类型注解提升性能
def process(data: list<int>) -> int:
    let total: int = 0
    for num in data:
        total += num
    return total

# 使用 @value 结构体
@value
struct Point:
    x: int
    y: int
```

## 编译特性

| 特性 | 说明 |
|------|------|
| **多阶段编译** | Lexer → Parser → Analyzer → Codegen |
| **命令行工具** | `cypyc` 提供编译、检查、运行、热重载命令 |
| **缓存机制** | 基于 SHA256 哈希的增量缓存 |
| **文件锁定** | Windows 下自动处理 .pyd 文件锁定 |
| **导入钩子** | 自动识别和编译 Cypy 文件 |
| **性能优化** | 支持优化级别和 release 配置 |