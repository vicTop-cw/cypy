# Cypy 语言语法规范 - 模块级魔法属性

## 1. 概述

Cypy 在编译时自动生成一系列模块级魔法属性，用于提供模块的元信息、编译配置和环境信息。

### 1.1 魔法属性分类

| 分类 | 属性 |
|------|------|
| **身份与元信息** | `__name__`, `__file__`, `__package__`, `__path__` |
| **可见性与 API 管理** | `__all__`, `__public__`, `__private__` |
| **编译与环境信息** | `__compile_time__`, `__target__`, `__profile__`, `__deps__` |

## 2. 身份与元信息属性

### 2.1 `__name__`

模块名称，与 Python 标准行为一致。

```python
def main() -> int:
    print(f"Module name: {__name__}")
    return 0

if __name__ == "__main__":
    main()
```

### 2.2 `__file__`

模块文件的绝对路径。

```python
import os

def get_module_path() -> str:
    return __file__  # 返回当前模块的文件路径

def get_module_dir() -> str:
    return os.path.dirname(__file__)
```

### 2.3 `__package__`

包名称，用于包内模块的引用。

```python
# 在包内的模块中
print(f"Package name: {__package__}")

# 如果是独立模块，__package__ 为空字符串
```

### 2.4 `__path__`

包的搜索路径。

```python
# 在包的 __init__.py 中
print(f"Package path: {__path__}")
```

## 3. 可见性与 API 管理属性

### 3.1 `__all__`

公共 API 列表，控制 `from module import *` 的行为。

```python
# 自动收集（默认行为）
# Cypy 会自动收集以下划线开头以外的公共名称

# 自定义 __all__
__all__ = ["public_func", "PublicClass", "PI"]

def public_func() -> int:
    return 42

def _private_func() -> int:
    return 0

class PublicClass:
    pass

class _PrivateClass:
    pass

val PI: double = 3.14159
```

### 3.2 `__public__`

公共名称列表，由 Cypy 自动生成。

```python
# __public__ 包含所有公共名称
# 自动排除以下划线开头的名称

print(f"Public names: {__public__}")
# 输出: ['public_func', 'PublicClass', 'PI', '__all__', '__public__', ...]
```

### 3.3 `__private__`

私有名称列表，由 Cypy 自动生成。

```python
# __private__ 包含所有以下划线开头的名称

print(f"Private names: {__private__}")
# 输出: ['_private_func', '_PrivateClass']
```

## 4. 编译与环境信息属性

### 4.1 `__compile_time__`

编译时间，ISO 格式字符串。

```python
def get_compile_info() -> str:
    return f"Compiled at: {__compile_time__}"

# 输出示例: "Compiled at: 2026-07-25T10:30:00"
```

### 4.2 `__target__`

目标平台信息。

```python
def get_target_info() -> str:
    return f"Target platform: {__target__}"

# 输出示例: "Target platform: AMD64-windows"
```

### 4.3 `__profile__`

构建配置，`debug` 或 `release`。

```python
def is_debug() -> bool:
    return __profile__ == "debug"

if is_debug():
    print("Running in debug mode")
else:
    print("Running in release mode")
```

### 4.4 `__deps__`

依赖模块列表，由 Cypy 自动收集。

```python
def get_dependencies() -> list[str]:
    return __deps__

print(f"Module dependencies: {__deps__}")
# 输出示例: ['math', 'os', 'sys']
```

## 5. 属性生成规则

### 5.1 自动生成规则

```
规则 1: __name__, __file__, __package__, __path__ 始终生成
规则 2: __all__ 默认为自动收集，可自定义覆盖
规则 3: __public__ 和 __private__ 始终自动生成
规则 4: __compile_time__ 在编译时生成
规则 5: __target__ 根据编译平台生成
规则 6: __profile__ 根据构建配置生成
规则 7: __deps__ 从 import 语句自动收集
```

### 5.2 可见性规则

```
规则 1: 以下划线开头的名称视为私有
规则 2: 非下划线开头的名称视为公共
规则 3: __all__ 可覆盖默认的公共名称列表
规则 4: __public__ 和 __private__ 基于实际名称自动生成
```

## 6. 使用示例

### 6.1 模块信息查询

```python
def print_module_info() -> None:
    print(f"Module name: {__name__}")
    print(f"File path: {__file__}")
    print(f"Package: {__package__}")
    print(f"Compile time: {__compile_time__}")
    print(f"Target platform: {__target__}")
    print(f"Build profile: {__profile__}")
    print(f"Dependencies: {__deps__}")
    print(f"Public API: {__all__}")
```

### 6.2 条件编译

```python
# 根据构建配置执行不同代码
if __profile__ == "debug":
    # 调试模式：启用详细日志
    def debug_log(message: str) -> None:
        print(f"[DEBUG] {message}")
else:
    # 发布模式：禁用调试日志
    def debug_log(message: str) -> None:
        pass
```

### 6.3 版本信息

```python
# 使用编译时间作为版本标识
__version__ = __compile_time__[:10]  # 使用日期作为版本

def get_version() -> str:
    return __version__
```

### 6.4 API 导出控制

```python
# 控制模块导出的 API
__all__ = ["calculate", "Point", "Vector"]

# 公共 API
def calculate(x: int, y: int) -> int:
    return x + y

struct Point:
    x: float
    y: float

type Vector = tuple[float, float, float]

# 内部实现（不导出）
def _internal_helper() -> None:
    pass

class _InternalClass:
    pass
```

## 7. 与 Python 的兼容性

### 7.1 标准属性兼容

```python
# Cypy 兼容 Python 的标准模块属性
# 以下代码在 Python 和 Cypy 中都能运行

def main():
    print(f"Module: {__name__}")
    print(f"File: {__file__}")
    
    if __name__ == "__main__":
        print("Running as main")
```

### 7.2 扩展属性

```python
# Cypy 扩展的属性仅在 Cypy 中可用
# 在 Python 中使用需要条件检查

def get_compile_time() -> str:
    if hasattr(__builtins__, "__compile_time__"):
        return __compile_time__
    return "Not available in Python"
```

## 8. 编译时生成

### 8.1 属性生成时机

```
编译阶段 1: 解析 AST
    └── 收集 import 语句，生成 __deps__
    
编译阶段 2: 代码生成
    └── 生成 __name__, __file__, __package__, __path__
    
编译阶段 3: 最终处理
    └── 生成 __compile_time__, __target__, __profile__
    └── 收集公共/私有名称，生成 __all__, __public__, __private__
```

### 8.2 生成的代码示例

```cython
# Cypy 生成的模块级代码示例

# 身份与元信息
__name__ = "mymodule"
__file__ = "/path/to/mymodule.cypy"
__package__ = ""
__path__ = None

# 可见性与 API 管理
__all__ = ["public_func", "PublicClass"]
__public__ = ["public_func", "PublicClass", "__all__", ...]
__private__ = ["_private_func", "_PrivateClass"]

# 编译与环境信息
__compile_time__ = "2026-07-25T10:30:00"
__target__ = "AMD64-windows"
__profile__ = "release"
__deps__ = ["math", "os"]
```

## 9. 完整示例

```python
# 模块级魔法属性综合示例

# 自定义导出列表
__all__ = ["main", "calculate", "CONFIG"]

# 模块级配置
struct Config:
    debug: bool = False
    timeout: int = 30

CONFIG = Config {debug: True, timeout: 60}

# 公共 API
def calculate(a: int, b: int) -> int:
    """计算两个整数的和"""
    return a + b

def main() -> int:
    """主函数"""
    # 输出模块信息
    print(f"=== Module Info ===")
    print(f"Name: {__name__}")
    print(f"File: {__file__}")
    print(f"Compile time: {__compile_time__}")
    print(f"Target: {__target__}")
    print(f"Profile: {__profile__}")
    print(f"Dependencies: {__deps__}")
    
    # 使用配置
    if CONFIG.debug:
        print(f"\n=== Debug Mode ===")
        print(f"Timeout: {CONFIG.timeout}")
    
    # 执行计算
    result = calculate(10, 20)
    print(f"\nResult: {result}")
    
    return 0

# 私有函数（不导出）
def _validate_input(value: int) -> bool:
    return value > 0

# 主入口
if __name__ == "__main__":
    exit(main())
```
