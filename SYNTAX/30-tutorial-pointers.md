# 指针操作教程

## 概述

Cypy 支持 C 风格的指针操作，包括 `addr()` 取地址和 `*` 解引用。指针操作允许你直接访问内存地址，实现高效的内存管理和数据操作。

## 基本概念

### 指针类型

指针类型使用 `*` 前缀表示（Cypy 风格，类型在 `*` 之后）：

```cypy
let ptr: *int      # 指向 int 的指针
let fptr: *float   # 指向 float 的指针
let vp: *Vector    # 指向 Vector 结构体的指针
```

### 取地址操作

使用 `addr()` 函数获取变量的内存地址：

```cypy
let x: int = 10
let ptr: *int = addr(x)  # ptr 现在指向 x 的地址
```

### 解引用操作

使用 `*` 运算符访问指针指向的值：

```cypy
let ptr: *int = addr(x)
print(*ptr)  # 输出 x 的值
*ptr = 20    # 修改 x 的值
```

## 示例 1：基本指针操作

```cypy
def pointer_basics():
    let x: int = 10
    
    # 获取地址
    let ptr: *int = addr(x)
    
    # 解引用读取
    print(f"原始值: {x}")
    print(f"指针地址: {ptr}")
    print(f"通过指针访问: {*ptr}")
    
    # 解引用修改
    *ptr = 20
    print(f"修改后的值: {x}")
```

## 示例 2：指针作为函数参数

```cypy
def modify_value(ptr: *int):
    *ptr = *ptr * 2

def main():
    let value: int = 5
    print(f"调用前: {value}")
    modify_value(addr(value))  # 传递指针
    print(f"调用后: {value}")  # 输出: 10
```

## 示例 3：动态内存分配

使用 `malloc` 和 `free` 进行动态内存管理。

> **注意**：`<int*>malloc(...)` 中的 `<int*>` 是 C 互操作的类型转换语法，用于与 C 库函数交互，保留 C 风格写法。

```cypy
def dynamic_array():
    # 分配 5 个 int 的内存（C 互操作语法）
    let arr: *int = <int*>malloc(5 * sizeof(int))
    
    # 初始化
    for i in range(5):
        arr[i] = i * 2
    
    # 访问
    for i in range(5):
        print(f"arr[{i}] = {arr[i]}")
    
    # 释放内存
    free(arr)
```

## 示例 4：结构体指针

```cypy
struct Point:
    x: int
    y: int

def struct_pointer():
    let p: Point = Point(x=10, y=20)
    let pp: *Point = addr(p)
    
    # 通过指针访问字段
    print(f"({pp.x}, {pp.y})")  # 输出: (10, 20)
    
    # 修改字段
    pp.x = 100
    print(f"({p.x}, {p.y})")    # 输出: (100, 20)
```

## 安全注意事项

### 1. 仅允许 C 类型使用指针

Python 对象（如 `str`、`list`）不能使用 `addr()`：

```cypy
# 错误：不能对 Python 对象取地址
let name = "hello"
let ptr: *str = addr(name)  # 编译错误
```

### 2. 避免悬空指针

确保指针指向的内存仍然有效：

```cypy
def dangling_pointer():
    mut ptr: *int = None
    
    {
        let x: int = 10
        ptr = addr(x)  # x 在块结束后被销毁
    }
    
    # 危险：ptr 现在是悬空指针
    # *ptr = 20  # 未定义行为
```

### 3. 使用 defer 确保资源释放

```cypy
def safe_memory():
    # C 互操作语法，保留 C 风格的类型转换
    let buffer: *int = <int*>malloc(100 * sizeof(int))
    
    defer:
        free(buffer)  # 确保函数退出时释放
    
    # 使用 buffer...
```

## 性能优势

指针操作的主要优势是性能：

- **避免拷贝**：直接修改内存，无需复制数据
- **减少开销**：指针操作是原生 C 操作，非常快
- **数组访问**：直接内存偏移，比 Python 列表快

## 常见用途

1. **高性能计算**：避免 Python 对象开销
2. **与 C 库交互**：传递指针给 C 函数
3. **内存密集型操作**：大数组处理
4. **底层数据结构**：实现链表、树等

## 与 Python 的对比

| 特性 | Python | Cypy 指针 |
|------|--------|-----------|
| 内存访问 | 间接（对象引用） | 直接（内存地址） |
| 性能 | 较慢 | 极快 |
| 安全性 | 高（GC 管理） | 需手动管理 |
| 语法 | 无指针语法 | `*` 和 `addr()` |
