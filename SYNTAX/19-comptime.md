# 编译期求值

## 基本语法

### 表达式形式

```python
# 编译期表达式
let PI: float = comptime: 3.141592653589793
let MAX_SIZE: int = comptime: 1024 * 1024

# 编译期计算
let TWO_PI: float = comptime: PI * 2
```

### 块形式

```python
# 编译期块
let config = comptime:
    let debug: bool = True
    let timeout: int = 30
    {"debug": debug, "timeout": timeout}

# 使用编译期结果
print(config["debug"])  # True
```

## 编译期计算

### 常量计算

```python
# 编译期常量计算
let FIB_10: int = comptime:
    let a: int = 0
    let b: int = 1
    for _ in range(10):
        (a, b) = (b, a + b)
    a

print(FIB_10)  # 55（编译期计算完成）
```

### 字符串处理

```python
# 编译期字符串处理
let GREETING: str = comptime:
    let name: str = "World"
    f"Hello, {name}!"

print(GREETING)  # "Hello, World!"（编译期生成）
```

## 编译期函数

### 定义编译期函数

```python
# 编译期函数
comptime def compute_hash(data: str) -> int:
    let hash_value: int = 0
    for char in data:
        hash_value = hash_value * 31 + ord(char)
    return hash_value

# 使用编译期函数
let NAME_HASH: int = comptime: compute_hash("Alice")
```

### 编译期函数限制

```python
# 编译期函数只能调用其他编译期函数
comptime def add(a: int, b: int) -> int:
    return a + b

# 编译期函数可以调用其他编译期函数
comptime def multiply(a: int, b: int) -> int:
    return add(a, add(a, a))  # 递归调用编译期函数

let result: int = comptime: multiply(3, 4)  # 12
```

## 编译期与运行时

### 混合使用

```python
# 编译期和运行时混合使用
let compile_time_value: int = comptime: 42
let runtime_value: int = input() as int  # 运行时输入

# 编译期值可以在运行时使用
print(f"Compile time: {compile_time_value}")
print(f"Runtime: {runtime_value}")
```

### 条件编译

```python
# 使用编译期进行条件编译
let DEBUG_MODE: bool = comptime:
    import os
    os.environ.get("DEBUG", "False") == "True"

if DEBUG_MODE:
    print("Debug mode enabled")
else:
    print("Production mode")
```

## 编译期宏

### 宏与编译期

```python
# 宏可以使用编译期求值
macro generate_id():
    return comptime:
        import uuid
        str(uuid.uuid4())

# 使用宏
let id: str = generate_id()  # 编译期生成 UUID
```

## 编译期特性

| 特性 | 说明 |
|------|------|
| **表达式形式** | `comptime: expr` 单行形式 |
| **块形式** | `comptime:` 多行块 |
| **编译期函数** | `comptime def` 定义编译期函数 |
| **常量计算** | 在编译期完成计算，结果嵌入代码 |
| **条件编译** | 根据编译期条件选择代码路径 |
| **宏集成** | 宏可以使用编译期求值 |