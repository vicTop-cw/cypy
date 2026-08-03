# 变量声明

## 三种变量声明形式

Cypy 提供三种变量声明方式，分别对应不同的可变性和编译期处理：

### 1. `x = value` - 可变变量（默认）

```python
# 可变变量，等同于 mut x = value
counter: int = 0
counter += 1  # ✅ 允许重新赋值

name = "Alice"  # 无类型注解，类型为 PyObject
name = 42       # ✅ 允许改变类型
```

**特性：**
- 默认可变，可以重新赋值
- 等同于 `mut x = value`（`mut` 关键字可选）
- 无类型注解时，类型退化为 `PyObject`

### 2. `let x = value` - 不可变变量

```python
# 不可变变量，声明后不能重新赋值
let pi: float = 3.14159
let MAX_USERS: int = 1000

# 尝试重新赋值会报错
# pi = 3.14  # ❌ 错误：let 变量不可重新赋值
```

**特性：**
- 声明后不可重新赋值（语义检查）
- 适合常量值和不需要修改的变量
- 编译器可进行更多优化

### 3. `const x = value` - 编译期常量

```python
# 编译期常量，值在编译时展开到.pyd
const PI: float = 3.14159
const MAX_SIZE: int = 1000
const GREETING: str = "Hello, Cypy!"
```

**特性：**
- 值在编译期计算并展开
- 生成到 `.pyd` 文件中，运行时不可修改
- 适合真正的常量值（数学常数、配置参数等）
- 使用 `let` 确保不可修改（`let` 声明的变量不可重新赋值）

## 选择建议

```python
# 优先使用 const（编译期常量）
const PI: float = 3.14159
const MAX_RETRY: int = 3

# 不需要修改的变量使用 let
let userName: str = "Alice"
let age: int = 30

# 需要修改的变量使用默认赋值
count: int = 0
count += 1
```

## 类型注解

### 有注解 vs 无注解

```python
# 有类型注解：使用静态类型
let x: int = 10          # int 类型
let name: str = "Bob"    # str 类型
let flag: bool = True    # bool 类型

# 无类型注解：退化为 PyObject（动态类型）
x = 10          # PyObject
name = "Bob"    # PyObject
name = 42       # ✅ 允许改变类型
```

**规则：**
- **有注解**：使用指定的静态类型
- **无注解**：类型退化为 `PyObject`，支持动态类型

## 变量作用域

### 块级作用域

```python
def example():
    x = 10  # 函数作用域
    
    if True:
        let y = 20  # 块级作用域
        print(x, y)  # ✅ 10, 20
    
    # print(y)  # ❌ y 不在作用域内
    
    return x
```

### 模块级全局变量

Cypy 支持模块级全局变量，在函数内部修改全局变量时**无需显式 `global` 声明**：

```python
# 模块级全局变量
counter: int = 0

def increment() -> int:
    # Cypy 自动识别并添加 global 声明
    counter += 1
    return counter

def reset() -> None:
    counter = 0

# 使用全局变量
increment()  # 1
increment()  # 2
print(counter)  # 2
reset()
print(counter)  # 0
```

**全局变量特性：**
- **自动 global 声明**：编译器自动检测函数内对模块级变量的修改，并添加 `global` 声明
- **Python 兼容性**：生成的代码与 Python 的全局变量行为一致
- **类型注解支持**：全局变量可以有类型注解，也可以没有

## 变量命名规则

### 标识符规则

```python
# 有效命名
userName: str = "Alice"      # 驼峰命名
user_name: str = "Bob"       # 蛇形命名
MAX_SIZE: int = 1000         # 常量大写

# 无效命名（会报错）
# 1name: str = "Test"    # 不能以数字开头
# my-name: str = "Test"  # 不能包含连字符
# class: str = "Test"    # 不能使用关键字
```

## 变量特性总结

| 声明形式 | 可变性 | 类型处理 | 编译期处理 |
|---------|-------|---------|-----------|
| `x = value` | 可变 | 有注解用静态类型，无注解退化为 PyObject | 运行时赋值 |
| `let x = value` | 不可变 | 有注解用静态类型，无注解退化为 PyObject | 运行时赋值（只读） |
| `const x = value` | 编译期常量 | 有注解用静态类型，无注解退化为 PyObject | 编译期展开到.pyd |
