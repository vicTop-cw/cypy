# Cypy 使用文档（`cypyc`）

Cypy 是一门类 Python 语法的编译型语言，源码写 `.cypy`，经 `cypyc` 转译为 **Cython (.pyx)**，再编译成 C 扩展（`.pyd` / `.so`）。本文档覆盖 `cypyc` 的**全部使用方式**：命令行（CLI）、Python 库 API、Import Hook 集成、项目级编译，以及发布到 PyPI 的方法。

编译链路：

```
.cypy  ──transpile──▶  .pyx  ──Cython──▶  .c  ──C compiler──▶  .pyd / .so
```

---

## 一、安装

### 1.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | ≥ 3.8 |
| Cython | ≥ 3.0.0 |
| setuptools | ≥ 60.0 |
| watchdog | ≥ 3.0.0（仅 `watch` 需要） |
| C 编译器 | 编译 `.pyd` 时需要（Windows：MSVC / Visual Studio Build Tools；Linux：gcc） |

### 1.2 源码可编辑安装（开发用）

```bash
cd /path/to/Cypy
pip install -e .
```

安装后会在环境中注册 `cypyc` 命令，并安装 Python 包 `cypyc` 与 `cypy_hook`。

> 注意：`pyproject.toml` 中依赖必须写成 PEP 508 字符串数组：
> ```toml
> dependencies = ["Cython>=3.0.0", "setuptools>=60.0", "watchdog>=3.0.0"]
> ```
> 不能写成 `[project.dependencies]` 键值表（会触发 `configuration error`）。

### 1.3 验证安装

```bash
cypyc --help          # 应列出 transpile/compile/build/run/watch/hook 子命令
python -c "import cypyc, cypy_hook; print(cypyc.__version__)"
```

---

## 二、命令行（CLI）用法

命令格式：`cypyc [全局选项] <子命令> [参数]`

全局选项：

| 选项 | 说明 |
|------|------|
| `-o, --output DIR` | 生成文件输出目录（默认 `output`） |
| `-v, --verbose` | 详细输出（处理步骤、生成代码等） |
| `--version` | 显示版本号 |

### 2.1 `transpile` —— 转译为 Cython（不编译）

```bash
cypyc transpile demo.cypy
cypyc transpile demo.cypy -o build          # 指定输出目录
cypyc transpile demo.cypy --emit-cython     # 在终端打印生成的 .pyx 代码
cypyc transpile demo.cypy --emit-ast        # 打印 AST
cypyc transpile demo.cypy --check-only      # 仅做静态分析/类型检查，不生成代码
cypyc transpile demo.cypy --bridge          # 使用 bridge 编译器生成 C 代码（而非 Cython）
cypyc transpile demo.cypy --generate-setup  # 额外生成 setup.py
```

默认生成 `output/demo.pyx`。

### 2.2 `compile` —— 转译并编译为 `.pyd`

```bash
cypyc compile demo.cypy
cypyc compile demo.cypy -o dist
cypyc compile demo.cypy --bridge           # 用 C 生成器而非 Cython
```

成功后会打印 `.pyd` 文件路径。

### 2.3 `run` —— 编译并运行

```bash
cypyc run demo.cypy                 # 编译并调用默认入口 main()
cypyc run demo.cypy my_func         # 调用指定函数
cypyc run demo.cypy main -o build   # 指定输出目录
```

约定：程序入口为 `def main() -> int`，文件末尾以 `if __name__ == "__main__": main()` 作为运行入口。

### 2.4 `build` —— 项目级编译（跨模块类型推断）

适合多文件、有互相 `import` 的项目：

```bash
cypyc build ./myproject                 # 编译整个目录
cypyc build ./myproject --entry main    # 仅编译 main 模块及其依赖
cypyc build ./myproject --check-only    # 仅做全项目类型检查
```

`build` 会做模块发现、依赖图分析、跨模块类型推断，再逐模块编译。

### 2.5 `watch` —— 热重载开发服务器

监听目录文件变化并自动重编译：

```bash
cypyc watch ./myproject
cypyc watch ./myproject --debounce 0.3   # 文件变更防抖时延（秒）
```

### 2.6 `hook` —— Python 导入钩子管理

让普通 Python 进程能直接 `import` 带 Cypy 标记的 `.py` 文件：

```bash
cypyc hook install        # 安装 import hook（写入用户 sitecustomize / 注册）
cypyc hook uninstall      # 卸载
cypyc hook status         # 查看是否已安装
cypyc hook clear-cache    # 清除 Cypy 编译缓存（__pycache__/cypy）
```

---

## 三、作为 Python 库调用（API 用法）

`cypyc` 暴露两个包：

- `cypyc`：顶层包，含 `main()`（CLI 入口）与 `__version__`。
- `cypy_hook`：核心集成包，暴露 `CypyHook`（编程接口）及 `install_hook` / `uninstall_hook` / `is_hook_installed` 等。

### 3.1 `CompileResult` 数据结构

所有编译方法都返回 `CompileResult`（`cypy_hook.hook`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | `bool` | 是否成功 |
| `cython_code` | `Optional[str]` | 生成的 Cython 源码（转译成功时有值） |
| `pyx_path` | `Optional[str]` | 生成的 `.pyx` 路径 |
| `pyd_path` | `Optional[str]` | 编译出的 `.pyd/.so` 路径 |
| `errors` | `List[str]` | 错误列表 |
| `steps` | `List[str]` | 处理步骤日志 |

### 3.2 `CypyHook` 配置方法

```python
from cypy_hook import CypyHook

hook = CypyHook()
hook.set_source_dir("src")     # 源目录
hook.set_output_dir("output")  # 生成文件目录
hook.set_verbose(True)         # 打印处理日志
```

### 3.3 模式一：纯转译（得到 Cython 代码/文件）

```python
from cypy_hook import CypyHook

hook = CypyHook()
hook.set_output_dir("output")

# 转译一段代码字符串
result = hook.transpile("let x: int = 10\nprint(x)")
if result.success:
    print(result.cython_code)

# 转译一个文件（写入 output/<name>.pyx）
result = hook.transpile_file("demo.cypy")
if result.success:
    print("pyx ->", result.pyx_path)
else:
    print("errors:", result.errors)
```

### 3.4 模式二：编译为 `.pyd`

```python
from cypy_hook import CypyHook

hook = CypyHook()
result = hook.compile_to_pyd("demo.cypy", output_dir="dist")
if result.success:
    print("pyd ->", result.pyd_path)
```

参数：`compile_to_pyd(source_path, output_dir=None, force_recompile=False)`。
- `force_recompile=True` 时跳过增量编译缓存，强制重新编译。

### 3.5 模式三：一步转译 + 编译 + 运行

```python
from cypy_hook import CypyHook

hook = CypyHook()
result, output = hook.run("demo.cypy", "main")   # func_name 默认 "main"
if result.success:
    print("返回值:", output)

# 调用带参数的函数
result, output = hook.run("mathlib.cypy", "add", 1, 2)
```

也可直接用 `run_module` 调用已编译模块中的函数：

```python
output = hook.run_module(result.pyd_path, "add", 3, 4)
```

### 3.6 模式四：Hook 集成（动态编译并 import）

```python
from cypy_hook import CypyHook

hook = CypyHook()
src = """
def add(a: int, b: int) -> int:
    return a + b
"""
result, module = hook.compile_and_import(src, module_name="my_mod")
if result.success:
    print(module.add(2, 3))   # 像普通模块一样调用
```

直接求值代码片段：

```python
from cypy_hook import CypyHook

hook = CypyHook()
value = hook.eval("let x: int = 21 * 2\nx")
print(value)   # 42
```

### 3.7 完整示例（带错误处理）

```python
from cypy_hook import CypyHook

hook = CypyHook()
hook.set_output_dir("build")

result = hook.compile_to_pyd("demo.cypy")
if not result.success:
    for err in result.errors:
        print("编译错误:", err)
else:
    result, out = hook.run("demo.cypy", "main")
    print("运行结果:", out)
```

---

## 四、Import Hook 集成（在 Python 中直接 import Cypy 文件）

让 Python 进程在遇到带标记的文件时自动编译并加载。

### 4.1 在 Python 中启用

```python
import cypy_hook
cypy_hook.install_hook()          # 注册到 sys.meta_path
# 之后即可 import 带 "#!bin cypy" 标记的文件
import my_module                  # my_module.py 首行为 #!bin cypy
cypy_hook.uninstall_hook()        # 卸载
print(cypy_hook.is_hook_installed())
```

### 4.2 被 import 的文件格式

Cypy 文件首行必须是标记 `#!bin cypy`：

```python
#!bin cypy
def greet(name: str) -> str:
    return "Hello, " + name
```

然后在另一个普通 `.py` 中：

```python
import cypy_hook
cypy_hook.install_hook()
import greet_module
print(greet_module.greet("World"))
```

### 4.3 缓存与清理

- 编译产物缓存在 `__pycache__/cypy/` 下，按内容哈希管理，源文件未变则复用。
- CLI 清理：`cypyc hook clear-cache`。
- 库清理：

```python
from cypy_hook.hook import CypyCacheManager
CypyCacheManager().clear_cache()          # 清全部
CypyCacheManager().clear_cache("a.cypy")  # 清单个文件
```

---

## 五、项目级编译 API（`cypyc.project`）

多模块项目可用 `ProjectCompiler` 做跨模块类型推断与整体构建：

```python
from cypyc.project import ProjectCompiler

compiler = ProjectCompiler(project_root="./myproject", output_dir="output")
result = compiler.build(entry_point="main")   # entry_point 可空，编译全部

if result.success:
    print("构建成功:", result.output_files)
else:
    print("构建失败:", result.errors)
```

主要方法：

| 方法 | 说明 |
|------|------|
| `discover_modules(directory=None)` | 发现目录下所有 `.cypy` 模块 |
| `build_dependency_graph()` | 构建模块依赖图 |
| `collect_type_exports()` → `TypeRegistry` | 收集跨模块类型导出 |
| `type_check_module(name)` | 校验单个模块 |
| `compile_module(name)` | 编译单个模块 |
| `build(entry_point=None)` → `ProjectCompileResult` | 整体构建 |
| `get_type_registry()` / `get_dependency_graph()` | 取内部状态 |

---

## 六、发布到 PyPI

`cypyc` 已用 `pyproject.toml` 描述元数据，可构建为可分发的 wheel / sdist。

### 6.1 元数据（现有 `pyproject.toml` 关键字段）

```toml
[project]
name = "cypyc"
version = "0.1.0"
description = "Cypy compiler - A Python-like language that compiles to Cython"
requires-python = ">=3.8"
dependencies = ["Cython>=3.0.0", "setuptools>=60.0", "watchdog>=3.0.0"]

[project.scripts]
cypyc = "cypy_hook.hook:main"     # 安装后注册 cypyc 命令
```

> 发布前建议：把 `version` 与 `cypyc/__init__.py` 中的 `__version__` 保持一致；
> 在 `[project]` 中补充 `authors`、`license`、`readme`、`project-urls` 等字段。

### 6.2 构建

```bash
pip install build twine
python -m build            # 生成 dist/*.whl 与 dist/*.tar.gz
```

### 6.3 上传

```bash
twine check dist/*         # 上传前校验
twine upload dist/*        # 上传到 PyPI（需 PYPI_API_TOKEN）
# 测试环境：twine upload --repository testpypi dist/*
```

### 6.4 用户安装发布的库后使用

```bash
pip install cypyc
cypyc run hello.cypy       # 命令行
# 或
python -c "from cypy_hook import CypyHook; print(CypyHook().transpile('let x=1'))"
```

---

## 七、注意事项与常见问题

1. **缩进必须是 4 的倍数**（语言硬性要求），注意空格对齐。
2. **仅部分兼容 Python**：未加类型注解的变量退化为 `object`，不会做静态优化。
3. **编译需要 C 编译器**：`compile` / `build` / `run` 依赖本机 MSVC(gcc)，仅 `transpile`/`--check-only` 不需要。
4. **`constraint` / `subtype` / `dispatch` 尚未实现**（v0.5 计划），联合类型可用 `type Numeric = int | float`。
5. **CLI 自动识别**：若首参是 `.cypy`/`.py` 文件且非子命令，会自动当作 `transpile`，如 `cypyc demo.cypy`。
6. **缓存命中**：`transpile_file` / `compile_to_pyd` 默认增量编译，源未变会复用 `.pyd`；调试时可用 `force_recompile=True` 或 `cypyc hook clear-cache`。
7. **导入 Hook 标记**：仅首行 `#!bin cypy` 的 `.py` 文件会被 `cypy_hook` 的 MetaPathFinder 拦截编译。

---

## 八、快速上手清单

```bash
# 1. 安装
pip install -e .

# 2. 看转译结果
cypyc transpile examples/hello.cypy --emit-cython

# 3. 直接运行
cypyc run examples/hello.cypy

# 4. 在 Python 里调用
python - <<'PY'
from cypy_hook import CypyHook
r, out = CypyHook().run("examples/hello.cypy", "main")
print(out)
PY
```

详见 `SYNTAX/` 目录下的语法文档与 `SYNTAX_IMPLEMENTATION_STATUS.md`（特性实现状态）。
