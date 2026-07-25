# Cypy 语言语法规范 - 编译与工具链

## 1. `cypyc` 转译器

`cypyc` 是 Cypy 的命令行工具，用于转译和编译 Cypy 源代码。

### 1.1 安装

```bash
# 安装 cypyc
pip install cypy

# 从源码安装
pip install -e .
```

### 1.2 命令行接口

```bash
# 查看帮助
cypyc --help

# 版本信息
cypyc --version
```

## 2. 核心命令

### 2.1 `transpile` — 转译

将 Cypy 源码转译为 Cython 代码，不进行编译。

```bash
# 转译单个文件
cypyc transpile input.cypy

# 指定输出文件
cypyc transpile input.cypy --output output.pyx

# 转译整个目录
cypyc transpile src/ --output build/
```

### 2.2 `compile` — 编译

将 Cypy 源码转译并编译为二进制扩展。

```bash
# 编译单个文件
cypyc compile input.cypy

# 指定输出目录
cypyc compile input.cypy --output dist/

# 调试模式编译
cypyc compile input.cypy --profile debug

# 发布模式编译（默认）
cypyc compile input.cypy --profile release
```

### 2.3 `run` — 运行

编译并运行 Cypy 程序。

```bash
# 编译并运行
cypyc run input.cypy

# 传递命令行参数
cypyc run input.cypy -- --arg1 --arg2 value

# 调试模式运行
cypyc run input.cypy --profile debug
```

### 2.4 `check` — 类型检查

仅进行类型检查，不生成代码。

```bash
# 类型检查
cypyc check input.cypy

# 详细输出
cypyc check input.cypy --verbose

# 检查多个文件
cypyc check src/*.cypy
```

### 2.5 `hook` — Git Hook

安装 Git pre-commit hook，在提交前自动进行类型检查。

```bash
# 安装 hook
cypyc hook install

# 卸载 hook
cypyc hook uninstall
```

## 3. 编译流程

### 3.1 完整编译流程

```
1. 词法分析（Tokenization）
   └── Lexer 将源码分解为 token 流
   └── 支持自定义关键字：struct, enum, trait, impl, macro, etc.

2. 语法分析（Parsing）
   └── Parser 构建 AST
   └── 支持自定义 AST 节点：StructDef, TraitDef, ImplStmt, etc.

3. 作用域分析（Scope Analysis）
   └── ScopeAnalyzer 计算缩进层级和作用域
   └── 注册变量和函数到作用域

4. 类型检查（Type Checking）
   └── TypeChecker 验证类型注解一致性
   └── 推断泛型类型和列表元素类型

5. 宏展开（Macro Expansion）
   └── MacroExpander 处理宏定义和宏调用
   └── 进行编译期代码替换

6. 代码生成（Code Generation）
   └── CythonGenerator 将 AST 转换为 Cython 代码
   └── 生成模块级魔法属性

7. Cython 编译
   └── cythonize 将 .pyx 转换为 .c
   └── C 编译器将 .c 编译为 .so/.pyd

8. 输出
   └── 生成二进制扩展文件
   └── 生成构建产物
```

### 3.2 编译阶段详解

#### 阶段 1: 词法分析

```python
# 源码
struct Point:
    x: float
    y: float

# 生成的 tokens
STRUCT, IDENTIFIER(Point), COLON, INDENT
IDENTIFIER(x), COLON, IDENTIFIER(float), NEWLINE
IDENTIFIER(y), COLON, IDENTIFIER(float), NEWLINE
```

#### 阶段 2: 语法分析

```python
# 构建的 AST
Module(body=[
    StructDef(name='Point', fields=[
        Field(name='x', type=Identifier('float')),
        Field(name='y', type=Identifier('float'))
    ])
])
```

#### 阶段 3: 作用域分析

```python
# 作用域树
GlobalScope(symbols={
    'Point': Symbol(type='struct', node=StructDef(...))
})
```

#### 阶段 4: 类型检查

```python
# 类型映射
Point.x: float → cdef float
Point.y: float → cdef float
```

#### 阶段 5: 宏展开

```python
# 宏定义
macro twice(x) = $x + $x

# 宏调用
result = @twice!(5)

# 展开后
result = 5 + 5
```

#### 阶段 6: 代码生成

```python
# 生成的 Cython 代码
cdef struct Point:
    float x
    float y
```

#### 阶段 7: Cython 编译

```bash
# cythonize 命令
cythonize -i input.pyx

# 生成的文件
input.c      # C 代码
input.so     # 二进制扩展（Linux）
input.pyd    # 二进制扩展（Windows）
```

## 4. 编译配置

### 4.1 命令行选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output` | 输出目录 | `output` |
| `-p, --profile` | 构建配置 | `release` |
| `-v, --verbose` | 详细输出 | `false` |
| `-d, --debug` | 调试模式（等价于 `--profile debug`） | `false` |

### 4.2 构建配置

```bash
# 调试模式
cypyc compile input.cypy --profile debug
# 生成调试符号，禁用优化

# 发布模式
cypyc compile input.cypy --profile release
# 启用优化，禁用调试符号
```

### 4.3 输出目录结构

```
output/
├── input.pyx           # 转译后的 Cython 代码
├── input.c             # Cython 生成的 C 代码
├── input.cp313-win_amd64.pyd  # 二进制扩展
└── build/              # 构建临时文件
```

## 5. 集成到项目

### 5.1 设置文件

```python
# setup.py
from setuptools import setup, Extension
from Cython.Build import cythonize
from cypyc.compiler import CypyCompiler

# 创建 Cypy 编译器实例
compiler = CypyCompiler()

# 转译 Cypy 文件
compiler.transpile("src/", "build/")

# 构建扩展
ext_modules = cythonize("build/*.pyx")

setup(
    name="myproject",
    ext_modules=ext_modules,
)
```

### 5.2 Makefile

```makefile
# Makefile
.PHONY: all clean

all:
    cypyc compile src/main.cypy --output dist/

clean:
    rm -rf dist/ build/ __pycache__ *.pyc *.pyd
```

### 5.3 CI/CD 集成

```yaml
# .github/workflows/build.yml
name: Build
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.9"
      - run: pip install cypy cython
      - run: cypyc compile src/ --output dist/
      - run: python -c "import mymodule; print('Build successful')"
```

## 6. 错误处理

### 6.1 编译错误类型

| 类型 | 说明 | 示例 |
|------|------|------|
| **语法错误** | 词法或语法分析失败 | `Expected COLON, got IN` |
| **类型错误** | 类型检查失败 | `Type mismatch: expected int, got str` |
| **作用域错误** | 变量未定义 | `Undefined name 'x'` |
| **编译错误** | Cython 编译失败 | `Cannot convert Python object to C int` |

### 6.2 错误输出格式

```bash
# 错误输出示例
Error: Type mismatch
File: input.cypy
Line: 5
Column: 10
Code:     x: int = "hello"
             ^
Message: Expected int, got str
```

### 6.3 调试技巧

```bash
# 详细输出
cypyc compile input.cypy --verbose

# 仅转译（不编译）
cypyc transpile input.cypy --output output.pyx

# 检查类型
cypyc check input.cypy --verbose

# 生成 AST（用于调试）
cypyc transpile input.cypy --dump-ast
```

## 7. 性能优化

### 7.1 编译优化

```bash
# 启用所有优化
cypyc compile input.cypy --profile release

# 使用 O3 优化
cypyc compile input.cypy --opt=3

# 启用 LTO（链接时优化）
cypyc compile input.cypy --lto
```

### 7.2 代码优化建议

```python
# 使用静态类型（优化前）
def add(a, b):
    return a + b

# 使用静态类型（优化后）
def add(a: int, b: int) -> int:
    return a + b

# 使用结构体（优化前）
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

# 使用结构体（优化后）
struct Point:
    x: float
    y: float
```

### 7.3 性能对比

| 场景 | Python | Cypy（无类型） | Cypy（有类型） |
|------|--------|----------------|----------------|
| 简单加法 | 1x | ~1x | ~10x faster |
| 循环计算 | 1x | ~1x | ~50x faster |
| 结构体访问 | 1x | ~1x | ~100x faster |

## 8. 完整示例

```bash
# 创建项目结构
mkdir -p myproject/src

# 创建 Cypy 文件
cat > myproject/src/main.cypy << 'EOF'
def main() -> int:
    x: int = 10
    y: int = 20
    return x + y

if __name__ == "__main__":
    print(f"Result: {main()}")
EOF

# 编译
cd myproject
cypyc compile src/main.cypy --output dist/

# 运行
python -c "import main; print(f'Result: {main.main()}')"
```
