# 指针类型

## 指针声明

### 基本语法

```python
# 声明指针变量（默认逃逸）
let ptr: *int = addr(42)

# 指针指向结构体
struct Point:
    x: int
    y: int

let p: *Point = addr(Point(x=10, y=20))
```

### 指针与数组

```python
# 数组指针
let arr: list[int] = [1, 2, 3, 4, 5]
let arr_ptr: *int = addr(arr[0])

# 指针算术
let next_ptr: *int = arr_ptr + 1  # 指向下一个元素
```

## 指针操作

### 解引用

```python
# 使用 & 操作符解引用
let value: int = &ptr

# 修改指针指向的值
&ptr = 100
```

### 地址获取

```python
# 使用 addr() 获取变量地址
let x: int = 42
let ptr: *int = addr(x)

# addr() 仅适用于 C 类型变量
let name: str = "Alice"
# let str_ptr: *str = addr(name)  # ❌ 不支持
```

## 内存管理

### 延迟清理

```python
def allocate_buffer(size: int) -> *char:
    let buffer: *char = malloc(size)
    defer:
        free(buffer)  # 函数退出时自动执行
    return buffer
```

### 指针逃逸规则

```python
# 默认逃逸 - 需要显式清理
let escaped: *int = malloc(sizeof(int))
defer:
    free(escaped)

# 局部指针 - 无需清理（编译器自动处理）
def use_local():
    let local: int = 42
    let ptr: *int = addr(local)
    # local 作用域结束后自动释放
```

## 指针类型转换

### 类型转换

```python
# 指针类型转换
let void_ptr: *void = malloc(100)
let int_ptr: *int = void_ptr as *int
```

### 空指针检查

```python
def safe_deref(ptr: *int) -> int:
    if ptr == null:
        raise ValueError("Null pointer")
    return &ptr
```

## 指针使用限制

### 作用域限制

```python
# 指针只能在函数作用域内使用
struct Data:
    # ❌ 结构体字段不能是指针类型
    # ptr: *int
    value: int
```

### 构建块内使用

```python
# 指针可以在构建块内使用
def create_buffer(size: int) -> *char:
    buffer =:
        let b: *char = malloc(size)
        defer:
            free(b)
        b
    return buffer
```

## 指针安全规则

| 规则 | 说明 |
|------|------|
| **默认逃逸** | 指针变量默认逃逸，需显式使用 `defer` 清理 |
| **addr() 限制** | 仅适用于 C 类型变量，不支持 Python 对象 |
| **作用域限制** | 指针声明只能在函数作用域内 |
| **空指针检查** | 解引用前应检查指针是否为 null |
| **defer 必须** | 在函数内创建的指针必须用 `defer` 清理 |