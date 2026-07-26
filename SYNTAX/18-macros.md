# 宏系统

## 基本语法

### 宏定义

```python
# 简单宏定义
macro debug_log(message: str):
    print(f"[DEBUG] {message}")

# 使用宏
debug_log("Hello, World")  # 编译期展开为 print("[DEBUG] Hello, World")
```

### 带参数的宏

```python
# 带参数的宏
macro assert_gt(a: expr, b: expr):
    if not (a > b):
        raise AssertionError(f"{a} is not greater than {b}")

# 使用宏
let x: int = 10
let y: int = 5
assert_gt(x, y)  # 编译期展开为条件检查
```

## 宏模板

### 宏模板语法

```python
# 宏模板使用 ! 标记
def repeat![n: int](body: block):
    for _ in range(n):
        body

# 使用宏模板
repeat![3]:
    print("Hello")  # 编译期展开为三次打印
```

### 宏调用语法

```python
# 宏调用使用 @name! 语法
@log!
def process():
    pass

# 展开后等价于：
# def process():
#     print("[LOG] Entering process")
#     try:
#         pass
#     finally:
#         print("[LOG] Exiting process")
```

## 宏展开

### 编译期展开

```python
# 宏在编译期展开
macro square(x: expr):
    x * x

# 使用宏
let result = square(5)  # 编译期展开为 5 * 5
```

### 复杂宏展开

```python
# 复杂宏展开
macro with_lock(lock: expr, body: block):
    lock.acquire()
    try:
        body
    finally:
        lock.release()

# 使用宏
let mutex = threading.Lock()
with_lock(mutex):
    critical_section()  # 编译期展开为带锁的 try-finally 块
```

## 宏与类型系统

### 类型安全宏

```python
# 类型安全宏
macro checked_cast[T, U](value: expr) -> expr:
    if isinstance(value, T):
        return value as U
    raise TypeError(f"Cannot cast {type(value)} to {U}")

# 使用宏
let x: object = 42
let y: int = checked_cast[object, int](x)
```

## 宏组合

### 宏嵌套

```python
# 宏可以嵌套
macro debug:
    @log!
    def wrapper(func):
        def inner(*args, **kwargs):
            debug_log(f"Calling {func.__name__}")
            return func(*args, **kwargs)
        return inner

# 使用嵌套宏
@debug
def process():
    pass
```

## 宏的限制

### 运行时限制

```python
# 宏在编译期执行，无法访问运行时数据
macro compile_time_const():
    return 42  # ✅ 编译期常量

# macro runtime_value():
#     return input()  # ❌ 错误：宏无法调用运行时函数
```

### 递归限制

```python
# 宏递归有限制
macro recurse(n: int):
    if n > 0:
        recurse(n - 1)  # ⚠️ 可能导致编译期无限递归
    print(n)
```

## 宏特性

| 特性 | 说明 |
|------|------|
| **编译期执行** | 宏在编译期展开，不产生运行时代码 |
| **宏模板** | 使用 `!` 标记宏模板和调用 |
| **参数类型** | 支持 expr、block 等参数类型 |
| **类型安全** | 可以结合类型系统进行检查 |
| **宏组合** | 宏可以嵌套和组合 |
| **递归限制** | 宏递归有编译期限制 |