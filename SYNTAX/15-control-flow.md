# 控制流

## 条件语句

### if-else 语句

```python
# 简单条件
let x: int = 42
if x > 0:
    print("Positive")
elif x < 0:
    print("Negative")
else:
    print("Zero")
```

### 三元表达式

```python
# 三元条件表达式
let age: int = 25
let status = "Adult" if age >= 18 else "Minor"
print(status)  # "Adult"
```

## 循环语句

### for 循环

```python
# 基本 for 循环
let numbers: list[int] = [1, 2, 3, 4, 5]
for num in numbers:
    print(num)

# 带索引的循环
for i, num in enumerate(numbers):
    print(f"Index {i}: {num}")

# 范围循环
for i in range(5):
    print(i)  # 0, 1, 2, 3, 4
```

### while 循环

```python
# 基本 while 循环
let count: int = 0
while count < 5:
    print(count)
    count += 1

# while-else 语句
let found: bool = False
let items: list[int] = [1, 2, 3, 4, 5]
let target: int = 3
let i: int = 0

while i < len(items):
    if items[i] == target:
        found = True
        break
    i += 1
else:
    print(f"Target {target} not found")
```

### 循环控制

```python
# break 和 continue
for i in range(10):
    if i == 3:
        continue  # 跳过当前迭代
    if i == 7:
        break     # 退出循环
    print(i)  # 0, 1, 2, 4, 5, 6
```

## 异常处理

### try-except 语句

```python
# 基本异常处理
try:
    let result = 10 / 0
except ZeroDivisionError:
    print("Cannot divide by zero")

# 多个异常类型
try:
    let value = int("abc")
except ValueError:
    print("Invalid integer")
except TypeError:
    print("Wrong type")
```

### try-except-else-finally

```python
# 完整异常处理结构
try:
    let file = open("data.txt", "r")
    content = file.read()
except FileNotFoundError:
    print("File not found")
else:
    print(f"Read {len(content)} characters")
finally:
    file.close()  # 无论是否异常都会执行
```

## match-case 模式匹配

### 基本语法

```python
# 模式匹配
let value = "hello"

match value:
    case "hello":
        print("Hello world")
    case "bye":
        print("Goodbye")
    case _:
        print("Unknown")
```

### 复杂模式

```python
# 结合条件的模式匹配
let point = (3, 4)

match point:
    case (x, y) if x > y:
        print(f"x greater than y: {x} > {y}")
    case (x, y) if x < y:
        print(f"y greater than x: {y} > {x}")
    case (x, y):
        print(f"Equal: {x} = {y}")
```

## 跳转语句

### return 语句

```python
# 函数返回
def find_positive(numbers: list[int]) -> int:
    for num in numbers:
        if num > 0:
            return num  # 提前返回
    return 0  # 默认返回
```

### yield 语句

```python
# 生成器
def generate_numbers(n: int):
    for i in range(n):
        yield i  # 产生值

let gen = generate_numbers(5)
for num in gen:
    print(num)  # 0, 1, 2, 3, 4
```

## 控制流特性

| 特性 | 说明 |
|------|------|
| **if-elif-else** | 标准条件分支 |
| **三元表达式** | `value if cond else default` |
| **for 循环** | 支持迭代器、枚举、范围 |
| **while 循环** | 支持 while-else |
| **break/continue** | 循环控制 |
| **异常处理** | try-except-else-finally |
| **模式匹配** | match-case |
| **return/yield** | 函数返回和生成器 |