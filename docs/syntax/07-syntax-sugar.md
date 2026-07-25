# Cypy 语言语法规范 - 语法糖

## 1. 管道操作符 `|>`

管道操作符用于函数组合，将前一个函数的输出作为后一个函数的输入。

### 1.1 基本语法

```python
result = data |> process |> filter |> transform |> str
```

等价于：

```python
result = str(transform(filter(process(data))))
```

### 1.2 使用示例

```python
def add_one(x: int) -> int:
    return x + 1

def multiply_by_two(x: int) -> int:
    return x * 2

def to_string(x: int) -> str:
    return f"Result: {x}"

# 使用管道操作符
result = 5 |> add_one |> multiply_by_two |> to_string
# 等价于：to_string(multiply_by_two(add_one(5)))
# 结果："Result: 12"
```

### 1.3 管道与 lambda

```python
# 结合 lambda 使用
result = [1, 2, 3, 4, 5] \
    |> (lambda x: [i * 2 for i in x]) \
    |> (lambda x: [i for i in x if i > 5]) \
    |> sum

# 等价于：sum([i for i in [i * 2 for i in [1, 2, 3, 4, 5]] if i > 5])
# 结果：18
```

### 1.4 管道与方法调用

```python
# 管道操作符可以链式调用方法
result = "hello world" \
    |> str.upper \
    |> str.split \
    |> (lambda x: len(x))

# 结果：2
```

## 2. `val` — 不可变变量

`val` 用于声明不可变变量，声明后不能重新赋值。

### 2.1 基本语法

```python
val PI: double = 3.14159
val MAX_SIZE: int = 1000
val NAME: str = "Cypy"

PI = 3.14  # ❌ 编译错误：不可重新赋值
```

### 2.2 使用示例

```python
def calculate_circle_area(radius: float) -> float:
    val PI: double = 3.14159
    val area: double = PI * radius * radius
    return area

# val 变量可以在整个作用域内使用
val CONSTANT: int = 42

def use_constant() -> int:
    return CONSTANT * 2
```

### 2.3 `val` 与 `let` 的区别

```python
# val：不可变变量，必须初始化，不能重新赋值
val PI: double = 3.14159

# let：可变变量，可以重新赋值
let x: int = 10
x = 20  # ✅ 允许

# 不可变变量可以作为可变变量的初始值
val BASE: int = 100
let counter: int = BASE
counter += 1  # ✅ 允许
```

## 3. `let` — 块级绑定

`let` 用于声明块级作用域的可变变量。

### 3.1 基本语法

```python
let x: int = 10
let name: str = "Alice"

x = 20  # ✅ 允许重新赋值
```

### 3.2 块级作用域

```python
def process():
    let x: int = 10
    if x > 5:
        let y: int = 20  # 仅在 if 块内可见
        print(x + y)     # ✅ 30
    print(y)  # ❌ 编译错误：y 不在当前作用域
```

### 3.3 `if let` 模式匹配

```python
def process_optional(value):
    if let x = value:
        print(f"Value is {x}")
    else:
        print("Value is None")

# 等价于
def process_optional(value):
    if value is not None:
        x = value
        print(f"Value is {x}")
    else:
        print("Value is None")
```

## 4. `defer` — 延迟清理

`defer` 用于声明延迟执行的清理代码，在函数退出时自动执行。

### 4.1 基本语法

```python
def process_data(size: int) -> int:
    buffer: int* = malloc(sizeof(int) * size)
    defer free(buffer)  # 函数退出时自动执行
    
    buffer[0] = 42
    return buffer[0]
```

### 4.2 多个 defer

```python
def open_files():
    f1 = open("file1.txt", "r")
    defer f1.close()
    
    f2 = open("file2.txt", "r")
    defer f2.close()
    
    # 处理文件
    content1 = f1.read()
    content2 = f2.read()
    
    # defer 语句按逆序执行：先关闭 f2，再关闭 f1
```

### 4.3 defer 与异常

```python
def safe_process():
    resource = acquire_resource()
    defer release_resource(resource)  # 即使发生异常也会执行
    
    if error_condition:
        raise ValueError("Error")  # defer 仍会执行
    
    return "Success"
```

### 4.4 defer 在循环中

```python
def process_multiple(count: int) -> None:
    for i in range(count):
        buffer: int* = malloc(sizeof(int))
        defer free(buffer)  # 每次循环结束时执行
        buffer[0] = i
        print(&buffer[0])
```

## 5. `guard` — 守卫表达式

`guard` 用于条件检查和提前返回。

### 5.1 基本语法

```python
def process(x: int) -> int:
    guard x != 0 else 0  # 如果 x == 0，返回 0
    return x
```

### 5.2 使用示例

```python
def divide(a: float, b: float) -> float:
    guard b != 0 else float("inf")  # 除数不能为零
    return a / b

def get_value(data: dict, key: str) -> object:
    guard key in data else None  # 键必须存在
    return data[key]

def validate_input(value: str) -> str:
    guard value is not None else raise ValueError("Value cannot be None")
    guard len(value) > 0 else raise ValueError("Value cannot be empty")
    return value
```

### 5.3 guard 与 else 块

```python
def complex_check(value: int) -> str:
    guard value > 0 else:
        return "Negative"
    
    guard value < 100 else:
        return "Too large"
    
    return "Valid"
```

## 6. `owend` — 所有权声明

`owend` 用于声明拥有所有权的变量，变量负责资源的生命周期管理。

### 6.1 基本语法

```python
owend x: int = 10
owend buffer: int* = malloc(sizeof(int) * 100)
```

### 6.2 所有权转移

```python
def create_buffer(size: int) -> int*:
    owend buffer: int* = malloc(sizeof(int) * size)
    return buffer  # 所有权转移给调用者

# 调用者负责释放内存
ptr = create_buffer(10)
defer free(ptr)
```

### 6.3 所有权规则

```
规则 1: owend 变量拥有其资源的所有权
规则 2: 返回 owend 变量会转移所有权
规则 3: owend 变量离开作用域时自动清理
规则 4: 所有权可以转移但不能复制
```

## 7. 联合类型

联合类型用于表示一个值可以是多种类型之一。

### 7.1 基本语法

```python
type Number = int | float | double

def process(value: int | str) -> None:
    pass
```

### 7.2 使用示例

```python
# 定义联合类型
type Result = int | str | None

def compute() -> Result:
    if success:
        return 42
    elif error:
        return "Error"
    else:
        return None

# 类型检查
def handle_result(result: Result) -> str:
    match result:
        case int(x):
            return f"Number: {x}"
        case str(s):
            return f"String: {s}"
        case None:
            return "None"
        case _:
            return "Unknown"
```

### 7.3 联合类型与 isinstance

```python
def process_value(value: int | str | bool) -> str:
    if isinstance(value, int):
        return f"Integer: {value}"
    elif isinstance(value, str):
        return f"String: {value}"
    elif isinstance(value, bool):
        return f"Boolean: {value}"
    return "Unknown"
```

## 8. 类型别名

类型别名用于为复杂类型定义简短名称。

### 8.1 基本语法

```python
type Vector = tuple[float, float, float]
type Matrix = list[list[float]]
type Callback = callable[[int, str], bool]
type Result[T, E] = tuple[T, E]
```

### 8.2 使用示例

```python
# 定义类型别名
type Point2D = tuple[float, float]
type Point3D = tuple[float, float, float]
type Color = tuple[int, int, int]  # RGB

# 使用类型别名
def distance(a: Point2D, b: Point2D) -> float:
    return ((a[0] - b[0])**2 + (a[1] - b[1])**2)**0.5

def get_position() -> Point3D:
    return (1.0, 2.0, 3.0)

def create_color(r: int, g: int, b: int) -> Color:
    return (r, g, b)
```

### 8.3 泛型类型别名

```python
# 泛型类型别名
type Container[T] = list[T]
type Pair[T, U] = tuple[T, U]

# 使用泛型类型别名
int_container: Container[int] = [1, 2, 3]
str_container: Container[str] = ["a", "b", "c"]
mixed_pair: Pair[int, str] = (42, "hello")
```

## 9. 语法糖对比

| 语法糖 | 用途 | 示例 |
|--------|------|------|
| `|>` | 函数组合 | `data |> process |> filter` |
| `val` | 不可变变量 | `val PI = 3.14` |
| `let` | 可变变量 | `let x = 10` |
| `defer` | 延迟清理 | `defer free(buffer)` |
| `guard` | 条件检查 | `guard x != 0 else 0` |
| `owend` | 所有权声明 | `owend ptr = malloc(...)` |
| `|` | 联合类型 | `int \| str` |
| `type` | 类型别名 | `type Vector = tuple[float, float]` |

## 10. 语法糖与性能

### 10.1 编译期展开

```python
# 语法糖在编译时展开，无运行时开销
result = data |> process |> filter

# 编译后等价于：
result = filter(process(data))
```

### 10.2 零开销抽象

```python
# defer 语句在编译时转换为 try-finally
buffer = malloc(...)
defer free(buffer)

# 编译后等价于：
buffer = malloc(...)
try:
    # 代码
finally:
    free(buffer)
```

## 11. 完整示例

```python
# 语法糖综合示例

# 管道操作符
def add_one(x: int) -> int:
    return x + 1

def square(x: int) -> int:
    return x * x

result = 5 |> add_one |> square
print(f"Pipeline result: {result}")  # 输出: 36

# val 和 let
val PI: double = 3.14159
let radius: float = 5.0
let area: float = PI * radius * radius
print(f"Circle area: {area}")

# defer 延迟清理
def safe_process():
    f = open("temp.txt", "w")
    defer f.close()
    f.write("Hello, Cypy!")
    return "Done"

# guard 守卫表达式
def divide(a: float, b: float) -> float:
    guard b != 0 else float("inf")
    return a / b

result = divide(10, 2)
print(f"Divide result: {result}")  # 输出: 5.0

# 联合类型和类型别名
type Result = int | str | None

def compute(status: str) -> Result:
    match status:
        case "success":
            return 42
        case "error":
            return "Failed"
        case _:
            return None

result = compute("success")
print(f"Compute result: {result}")

# 所有权声明
def create_resource():
    owend resource = "allocated"
    print(f"Resource {resource}")
    return resource  # 所有权转移

resource = create_resource()
print(f"Received resource: {resource}")
```
