# Cypy 语言语法规范 - 构建块语法

## 1. 构建块概述

构建块是 Cypy 引入的一种语法糖，用于创建闭包无参函数，内部默认 unsafe，允许指针语法。

### 1.1 构建块类型

| 符号 | 名称 | 说明 |
|------|------|------|
| `=:` | 变量构建块 | 自动将最后表达式作为返回值赋值给左侧变量 |
| `~:` | 调用构建块 | 返回元组、命名元组、字典或实现 `BuildParams` trait 的对象 |
| `*:` | 生成器构建块 | 返回迭代器，`yield` 产生参数包 |

### 1.2 构建块特点

```
特点 1: 构建块内部默认 unsafe，允许指针语法
特点 2: 最后表达式自动作为返回值
特点 3: 构建块可访问外部作用域变量
特点 4: 构建块可嵌套使用
```

## 2. 变量构建块 `=:`

变量构建块用于将一系列表达式的结果赋值给变量，最后一个表达式作为返回值。

### 2.1 基本语法

```python
result =:
    x = 10
    y = 20
    x + y  # 最后表达式作为返回值，result = 30
```

编译后的代码：

```cython
result = (lambda: (x := 10, y := 20, x + y))()
# 或等价的：
x = 10
y = 20
result = x + y
```

### 2.2 使用示例

```python
def compute_area() -> float:
    # 变量构建块计算矩形面积
    area =:
        width = 5.0
        height = 3.0
        width * height  # 返回 15.0
    
    return area

# 使用变量构建块初始化复杂数据结构
data =:
    name = "Alice"
    age = 30
    scores = [85, 90, 95]
    {"name": name, "age": age, "avg_score": sum(scores) / len(scores)}
```

### 2.3 指针操作

```python
def process_buffer(size: int) -> int:
    # 构建块内部允许指针操作（默认 unsafe）
    result =:
        buffer: int* = malloc(sizeof(int) * size)
        defer free(buffer)  # 延迟清理
        buffer[0] = 42
        &buffer[0]  # 返回第一个元素的值
    
    return result
```

## 3. 调用构建块 `~:`

调用构建块用于简化函数调用，将参数以赋值语句的形式传递。

### 3.1 基本语法

```python
def create_user(name: str, age: int) -> str:
    return f"User: {name}, Age: {age}"

user = create_user ~:
    name = "Alice"
    age = 30
```

编译后的代码：

```cython
user = create_user(name="Alice", age=30)
```

### 3.2 使用示例

```python
def configure_server(host: str, port: int, debug: bool = False) -> str:
    return f"Server config: {host}:{port} (debug={debug})"

# 使用调用构建块
config = configure_server ~:
    host = "localhost"
    port = 8080
    debug = True

# 等价于
# config = configure_server(host="localhost", port=8080, debug=True)
```

### 3.3 嵌套构建块

```python
def create_person(name: str, address: dict) -> str:
    return f"Person: {name}, Address: {address}"

# 嵌套使用调用构建块和变量构建块
person = create_person ~:
    name = "Bob"
    address =:
        city = "Beijing"
        street = "Main Street"
        {"city": city, "street": street}
```

## 4. 生成器构建块 `*:`

生成器构建块用于生成参数包，返回迭代器。

### 4.1 基本语法

```python
def process_items(*items):
    for item in items:
        print(f"Processing: {item}")
    return len(items)

count = process_items *:
    yield (1, "first")
    yield (2, "second")
    yield (3, "third")
```

编译后的代码：

```cython
count = process_items(*[(1, "first"), (2, "second"), (3, "third")])
```

### 4.2 使用示例

```python
def sum_values(*args: int) -> int:
    total = 0
    for val in args:
        total += val
    return total

# 使用生成器构建块
total = sum_values *:
    yield 10
    yield 20
    yield 30

# 等价于
# total = sum_values(10, 20, 30)
```

### 4.3 复杂生成器

```python
def create_report(title: str, *sections: str) -> str:
    result = [f"# {title}"]
    for i, section in enumerate(sections, 1):
        result.append(f"\n## Section {i}\n{section}")
    return "\n".join(result)

# 使用生成器构建块传递多个参数
report = create_report ~:
    title = "Monthly Report"
    *:
        yield "Sales data analysis"
        yield "Customer feedback"
        yield "Future plans"
```

## 5. 构建块组合使用

### 5.1 组合示例

```python
def calculate_statistics(data: list[int]) -> dict:
    stats =:
        total = sum(data)
        avg = total / len(data)
        max_val = max(data)
        min_val = min(data)
        {
            "total": total,
            "average": avg,
            "max": max_val,
            "min": min_val
        }
    return stats

# 使用调用构建块传递数据
result = calculate_statistics ~:
    data =:
        numbers = [10, 20, 30, 40, 50]
        numbers

# 使用生成器构建块创建列表
data =:
    items = [i * 2 for i in range(10)]
    items

result = calculate_statistics ~:
    data =:
        [1, 3, 5, 7, 9]
```

### 5.2 构建块与指针

```python
def init_array(size: int, default: int) -> int*:
    arr: int* = malloc(sizeof(int) * size)
    for i in range(size):
        arr[i] = default
    return arr

# 使用构建块管理指针生命周期
def safe_init(size: int) -> list[int]:
    result =:
        buffer: int* = init_array(size, 42)
        defer free(buffer)
        # 将指针内容复制到列表
        [&buffer[i] for i in range(size)]
    
    return result
```

## 6. 构建块作用域

### 6.1 变量作用域

```python
x = 100  # 外部变量

result =:
    x = 10  # 内部变量，遮蔽外部变量
    y = 20
    x + y  # 返回 30

print(x)  # 输出 100（外部变量不受影响）
```

### 6.2 闭包特性

```python
def make_counter() -> callable:
    count = 0
    
    increment =:
        nonlocal count
        count += 1
        count
    
    return increment

counter = make_counter()
print(counter())  # 1
print(counter())  # 2
print(counter())  # 3
```

## 7. 构建块与类型推断

### 7.1 类型推断

```python
# 变量构建块的返回类型从最后表达式推断
result =:
    x: int = 10
    y: int = 20
    x + y  # 推断返回类型为 int

# 显式类型注解
result: float =:
    x: int = 10
    y: int = 20
    (x + y) as float  # 返回类型为 float
```

### 7.2 函数参数类型检查

```python
def add(a: int, b: int) -> int:
    return a + b

# 调用构建块会检查参数类型
result = add ~:
    a = "10"  # ❌ 编译错误：期望 int，得到 str
    b = 20
```

## 8. 构建块的性能优势

### 8.1 编译期优化

```python
# 构建块在编译时展开，无运行时闭包开销
result =:
    x = 10
    y = 20
    x + y

# 编译后等价于：
x = 10
y = 20
result = x + y
```

### 8.2 指针操作优化

```python
# 构建块内部默认 unsafe，允许直接指针操作
# 无需额外的安全检查，性能更高

buffer: int* = malloc(sizeof(int) * 100)
result =:
    # 直接访问指针，无边界检查
    buffer[0] = 42
    buffer[1] = 84
    &buffer[0] + &buffer[1]
```

## 9. 构建块与其他特性的结合

### 9.1 与结构体结合

```python
struct Point:
    x: float
    y: float

# 使用变量构建块创建结构体
p =:
    x = 10.0
    y = 20.0
    Point {x: x, y: y}

# 使用调用构建块
def create_point(x: float, y: float) -> Point:
    return Point {x: x, y: y}

p = create_point ~:
    x = 10.0
    y = 20.0
```

### 9.2 与 defer 结合

```python
def process_file(path: str) -> str:
    content =:
        f = open(path, "r")
        defer f.close()  # 构建块结束时自动关闭文件
        f.read()
    
    return content
```

### 9.3 与 comptime 结合

```python
# 编译期计算
result: int = comptime:
    x = 2
    y = 3
    x * y * 4  # result = 24（编译时计算）
```

## 10. 完整示例

```python
# 构建块综合示例

# 变量构建块
def calculate():
    result =:
        a = 10
        b = 20
        c = a + b
        c * 2  # 返回 60
    return result

# 调用构建块
def create_user(name: str, age: int, active: bool = True):
    return {
        "name": name,
        "age": age,
        "active": active
    }

user = create_user ~:
    name = "Alice"
    age = 30
    active = True

# 生成器构建块
def sum_numbers(*args: int) -> int:
    return sum(args)

total = sum_numbers *:
    yield 1
    yield 2
    yield 3
    yield 4
    yield 5

# 嵌套构建块
def create_report(title: str, data: dict):
    return {
        "title": title,
        "data": data,
        "timestamp": __compile_time__
    }

report = create_report ~:
    title = "Performance Report"
    data =:
        metrics = ["CPU", "Memory", "Disk"]
        values = [80, 60, 45]
        dict(zip(metrics, values))

print(f"Result: {calculate()}")
print(f"User: {user}")
print(f"Total: {total}")
print(f"Report: {report}")
```
