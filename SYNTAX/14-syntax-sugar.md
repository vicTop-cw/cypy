# 语法糖

## 命名参数语法糖 (name~)

### 基本语法

```python
# name~ 语法糖：在函数调用中自动转换为 name=name 形式
def make_point(x: float, y: float, z: float) -> tuple<float, float, float>:
    return (x, y, z)

# 传统写法
return make_point(x=x, y=y, z=z)

# 使用 name~ 语法糖
return make_point(x~, y~, z~)
```

### 混合参数

```python
# 支持位置参数和命名参数糖混合使用
def add_values(a: int, b: int, c: int) -> int:
    return a + b + c

x = 10
y = 20
c = 30

# 前两个位置参数 + 后命名参数糖
result = add_values(x, y, c~)  # 等价于 add_values(x, y, c=c)
```

### 方法调用

```python
# 方法调用中的 name~ 语法糖
class Calculator:
    def add(self, x: float) -> float:
        self.value += x
        return self.value

calc = Calculator(0.0)
value = 5.0

# 方法调用中的 name~
result = calc.add(value~)  # 等价于 calc.add(value=value)
```

## 管道操作符

### 基本语法

```python
# 管道操作符 |>
def process(x: int) -> int:
    return x * 2

def filter(x: int) -> int:
    return x + 1

# 普通调用
result = filter(process(5))  # 11

# 使用管道操作符
result = 5 |> process |> filter  # 11
```

### 链式调用

```python
# 管道操作符支持链式调用
let data = [1, 2, 3, 4, 5]

def double(x: int) -> int:
    return x * 2

def square(x: int) -> int:
    return x ** 2

def sum_list(items: list<int>) -> int:
    return sum(items)

# 管道链式处理
let total = data |> map(double) |> map(square) |> sum_list
```

## 守卫语句

### 单行形式

```python
# 单行守卫：guard cond else expr
def divide(a: float, b: float) -> float:
    guard b != 0 else raise ValueError("Division by zero")
    return a / b
```

### 多行形式

```python
# 多行守卫：guard cond else:
def process(input: str) -> str:
    guard input else:
        print("No input provided")
        return "default"
    return input.strip()
```

### 隐式返回

```python
# guard 语句的 else 子句值会隐式返回
def get_name(user: dict<str, object>) -> str:
    guard "name" in user else "Unknown"
    return str(user["name"])
```

### 循环守卫

```python
# 在循环中使用 guard，失败时生成 break（退出循环）
def process_items(items: list<int>) -> int:
    count: int = 0
    for item in items:
        guard item > 0 else break  # 非正数则跳过
        count = count + 1
    return count

# 在 while 循环中使用 guard
def find_first_valid(values: list<int>) -> int:
    i: int = 0
    while i < len(values):
        guard values[i] > 0 else break  # 遇到非正数停止
        i = i + 1
    return i

# guard else continue：跳过当前迭代
def sum_positive(items: list<int>) -> int:
    total: int = 0
    for item in items:
        guard item > 0 else continue  # 非正数跳过
        total = total + item
    return total

# guard else return：提前返回
def validate_and_process(data: list<int>) -> str:
    for value in data:
        guard value >= 0 else return "Invalid data"  # 负数提前返回
        guard value < 100 else break  # 超过100停止处理
    return "ok"
```

### 嵌套循环中的守卫

```python
# 嵌套循环中的 guard 正确 break 当前层循环
def find_pairs(items: list<int>) -> int:
    count: int = 0
    for i in range(len(items)):
        for j in range(len(items)):
            guard items[i] + items[j] < 100 else break  # 退出内层循环
            count = count + 1
    return count
```

## defer 语句

### 基本语法

```python
# defer 延迟清理
def open_file(path: str) -> str:
    let file = open(path, "r")
    defer:
        file.close()  # 函数退出时自动执行
    return file.read()
```

### 多个 defer

```python
# 支持多个 defer，按逆序执行
def complex_operation():
    let resource1 = acquire_resource()
    defer:
        release_resource(resource1)
    
    let resource2 = acquire_resource()
    defer:
        release_resource(resource2)
    
    # 执行操作
    return "done"
```

## match-case 模式匹配

### 基本语法

```python
# match-case 模式匹配
let value = 42

match value:
    case 0:
        print("Zero")
    case 1:
        print("One")
    case _:
        print("Other")
```

### 复杂模式

```python
# 元组模式
let point = (10, 20)

match point:
    case (0, 0):
        print("Origin")
    case (x, 0):
        print(f"On x-axis: {x}")
    case (0, y):
        print(f"On y-axis: {y}")
    case (x, y):
        print(f"Point: ({x}, {y})")
```

## f-string 格式化

### 基本语法

```python
# f-string 格式化
let name = "Alice"
let age = 30

# 简单表达式
let message = f"Name: {name}, Age: {age}"

# 格式化选项
let pi = 3.14159
let formatted = f"Pi: {pi:.2f}"  # "Pi: 3.14"

# 表达式计算
let result = f"2 + 3 = {2 + 3}"  # "2 + 3 = 5"
```

## 切片语法

### 基本切片

```python
# 切片语法
let numbers = [0, 1, 2, 3, 4, 5]

# 基本切片
let first_three = numbers[:3]  # [0, 1, 2]
let last_two = numbers[-2:]    # [4, 5]
let middle = numbers[1:4]      # [1, 2, 3]

# 步长切片
let even = numbers[::2]        # [0, 2, 4]
let reversed = numbers[::-1]   # [5, 4, 3, 2, 1, 0]
```

## 解包语法

### 元组解包

```python
# 元组解包
let (x, y) = (10, 20)
print(x, y)  # 10 20

# 忽略某些值
let (_, result) = process()

# 扩展解包
let (first, *rest) = [1, 2, 3, 4, 5]
print(first)  # 1
print(rest)   # [2, 3, 4, 5]
```

### 字典解包

```python
# 字典解包
let config = {"debug": True, "timeout": 30}
let merged = {"verbose": False, **config}
print(merged)  # {"verbose": False, "debug": True, "timeout": 30}
```

## 语法糖特性

| 特性 | 说明 |
|------|------|
| **命名参数糖 (name~)** | `name~` 自动转换为 `name=name` 关键字参数 |
| **管道操作符** | `|>` 转换为嵌套函数调用 |
| **守卫语句** | `guard cond else expr` 单行形式 |
| **循环守卫** | 循环中 guard 失败生成 `break`/`continue`/`return` |
| **defer** | 函数退出时自动执行清理代码 |
| **match-case** | Python 3.10+ 模式匹配语法 |
| **f-string** | 格式化字符串，支持表达式 |
| **切片** | 支持步长、负索引 |
| **解包** | 支持元组、列表、字典解包 |