# 模式匹配

## 基本语法

### match-case 语句

```python
# 基本模式匹配
let value = 42

match value:
    case 0:
        print("Zero")
    case 1:
        print("One")
    case _:
        print("Other")
```

## 字面量模式

### 值匹配

```python
# 字面量模式
let status = "active"

match status:
    case "active":
        print("User is active")
    case "inactive":
        print("User is inactive")
    case "pending":
        print("User is pending")
    case _:
        print("Unknown status")
```

## 变量模式

### 绑定变量

```python
# 变量模式
let point = (10, 20)

match point:
    case (x, 0):
        print(f"On x-axis at {x}")
    case (0, y):
        print(f"On y-axis at {y}")
    case (x, y):
        print(f"Point ({x}, {y})")
```

## 元组模式

### 解构元组

```python
# 元组模式
let data = ("user", 42, "admin")

match data:
    case ("user", id, role):
        print(f"User {id} has role {role}")
    case ("system", code, message):
        print(f"System message: {code} - {message}")
```

## 列表模式

### 解构列表

```python
# 列表模式
let items = [1, 2, 3, 4, 5]

match items:
    case []:
        print("Empty list")
    case [first]:
        print(f"Single element: {first}")
    case [first, *rest]:
        print(f"First: {first}, Rest: {rest}")
```

## 字典模式

### 解构字典

```python
# 字典模式
let config = {"debug": True, "timeout": 30}

match config:
    case {"debug": True}:
        print("Debug mode enabled")
    case {"timeout": t} if t > 60:
        print(f"Long timeout: {t}s")
    case {"debug": False, "timeout": t}:
        print(f"Production mode with {t}s timeout")
```

## 结构体模式

### 解构结构体

```python
# 结构体模式
struct Point:
    x: int
    y: int

let p = Point(x=10, y=20)

match p:
    case Point(x=0, y=0):
        print("Origin")
    case Point(x=x, y=0):
        print(f"On x-axis: {x}")
    case Point(x=0, y=y):
        print(f"On y-axis: {y}")
    case Point(x=x, y=y):
        print(f"Point ({x}, {y})")
```

## 枚举模式

### 解构枚举

```python
# 枚举模式
enum Shape:
    CIRCLE(radius: float)
    RECTANGLE(width: float, height: float)
    TRIANGLE(base: float, height: float)

let shape = Shape.CIRCLE(radius=5.0)

match shape:
    case Shape.CIRCLE(r):
        print(f"Circle with radius {r}")
    case Shape.RECTANGLE(w, h):
        print(f"Rectangle {w}x{h}")
    case Shape.TRIANGLE(b, h):
        print(f"Triangle area: {b*h/2}")
```

## OR 模式

### 多个模式匹配

```python
# OR 模式
let value = 42

match value:
    case 0 | 1 | 2:
        print("Small number")
    case 3 | 4 | 5:
        print("Medium number")
    case _:
        print("Large number")
```

## Guard 模式

### 条件守卫

```python
# Guard 模式
let point = (3, 4)

match point:
    case (x, y) if x == y:
        print(f"Diagonal: ({x}, {y})")
    case (x, y) if x > y:
        print(f"x > y: ({x}, {y})")
    case (x, y):
        print(f"Normal: ({x}, {y})")
```

## 嵌套模式

### 复杂嵌套

```python
# 嵌套模式
let data = ("user", {"name": "Alice", "age": 30}, ["admin", "editor"])

match data:
    case ("user", {"name": name, "age": age}, roles):
        print(f"User {name}, {age} years old, roles: {roles}")
    case _:
        print("Unknown data format")
```

## 提取器模式

参考 Scala 的 `unapply` 方法，Cypy 支持提取器模式，允许类定义 `__unapply__` 方法来控制如何在模式匹配中提取值：

```python
struct Email:
    address: str
    
    def __unapply__(self) -> tuple<str, str> | None:
        """提取用户名和域名"""
        if '@' in self.address:
            parts = self.address.split('@')
            return (parts[0], parts[1])
        return None

# 使用提取器模式
match email:
    case Email(user, domain):
        print(f"User: {user}, Domain: {domain}")
    case _:
        print("Invalid email")
```

### 解包模式

`__unwarp__` 方法用于包装类型的解包，返回被包装的值：

```python
struct Wrapper<T>:
    value: T
    
    def __unwarp__(self) -> T:
        """解包返回内部值"""
        return self.value

# 使用解包模式
match wrapped:
    case Wrapper(x):
        print(f"Unwrapped: {x}")
```

### 序列提取器

`__unapply_seq__` 方法用于提取可变长度的序列：

```python
struct Numbers:
    values: list<int>
    
    def __unapply_seq__(self) -> tuple<int, ...> | None:
        """提取序列"""
        return tuple(self.values) if self.values else None

# 使用序列提取器
match numbers:
    case Numbers(x, y, ..):
        print(f"First two: {x}, {y}")
```

## 模式匹配优先级系统

当进行模式匹配时，Cypy 按照以下优先级查找匹配方法（从高到低）：

| 优先级 | 模式类型 | 魔法方法 | 说明 |
|--------|---------|---------|------|
| 1 | 内置字面量模式 | - | 常量值匹配（`case 42`, `case "hello"`） |
| 2 | 通配符模式 | - | 匹配任意值（`case _`） |
| 3 | 变量模式 | - | 绑定到变量（`case x`） |
| 4 | 元组/数组/字典模式 | - | 结构化解构（`case (x, y)`） |
| 5 | 类型模式 | - | 类型检查 + 绑定（`case int x`） |
| 6 | `__match_args__` | `__match_args__` | Python 标准位置解构 |
| 7 | `__unapply__` | `__unapply__` | Scala 风格提取器（优先） |
| 8 | `__unapply_seq__` | `__unapply_seq__` | 序列提取器 |
| 9 | `__unwarp__` | `__unwarp__` | 自定义解包方法 |
| 10 | OR 模式 | - | 多个模式组合（`case 1 \| 2 \| 3`） |

### 优先级说明

1. **`__match_args__`**：Python 标准属性，定义位置参数的名称顺序
2. **`__unapply__`**：参考 Scala 的 extractor，返回元组或 `None`
3. **`__unapply_seq__`**：用于可变长度的序列提取
4. **`__unwarp__`**：用于包装类型的简单解包

运行时，当匹配 `case TypeName(p1, p2, ...)` 形式的模式时，解释器会按优先级依次查找这些方法。

## 范围模式

匹配数值范围内的值：

```python
let score = 75

match score:
    case 0..60:
        print("Fail")
    case 60..70:
        print("Pass")
    case 70..80:
        print("Good")
    case 80..90:
        print("Excellent")
    case 90..100:
        print("Perfect")
    case _:
        print("Invalid score")
```

范围模式支持整数和浮点数：

```python
let temp = 25.5

match temp:
    case -10..0:
        print("Freezing")
    case 0..20:
        print("Cold")
    case 20..30:
        print("Comfortable")
    case 30..40:
        print("Hot")
    case _:
        print("Extreme")
```

范围模式可以与 Guard 条件组合使用：

```python
match value:
    case 1..10 if value % 2 == 0:
        print("Even number between 1 and 10")
    case 1..10 if value % 2 == 1:
        print("Odd number between 1 and 10")
```

## match 表达式

match 可以作为表达式使用，返回匹配的结果：

```python
def classify(x):
    return match x:
        case 1..10: "small"
        case 10..100: "medium"
        case _: "large"
```

match 表达式在函数返回、变量赋值等场景非常方便：

```python
let result = match status_code:
    case 200: "OK"
    case 404: "Not Found"
    case 500: "Server Error"
    case _: "Unknown"

print(result)  # 输出匹配的结果
```

match 表达式支持所有模式类型，包括范围模式、提取器模式等：

```python
def describe(point):
    return match point:
        case Point(0, 0): "Origin"
        case Point(x, y) if x == y: "Diagonal"
        case Point(x, 0): f"On X-axis: {x}"
        case Point(0, y): f"On Y-axis: {y}"
        case _: "Other"
```

## 模式匹配特性

| 特性 | 说明 |
|------|------|
| **字面量模式** | 匹配具体值 |
| **变量模式** | 绑定匹配的值到变量 |
| **元组模式** | 解构元组 |
| **列表模式** | 解构列表，支持 `*rest` |
| **字典模式** | 解构字典 |
| **结构体模式** | 解构结构体字段 |
| **枚举模式** | 解构枚举成员 |
| **OR 模式** | 多个模式用 `\|` 连接 |
| **Guard 模式** | 添加条件判断 |
| **嵌套模式** | 支持多层嵌套 |
| **提取器模式** | 参考 Scala 的 `__unapply__` |
| **解包模式** | `__unwarp__` 自定义解包 |
| **范围模式** | `case 1..10:` 匹配范围内的值 |
| **match 表达式** | `match x: case 1: "one"` 返回值形式 |
| **解构绑定** | 在 `let` 语句中使用模式解构 |

## 解构绑定

在 `let` 语句中支持使用模式进行解构绑定：

```python
# 元组解构
let (x, y) = (1, 2)
print(x + y)  # 输出: 3

# 列表解构（支持 *rest）
let [a, b, *rest] = [1, 2, 3, 4, 5]
print(a)     # 输出: 1
print(b)     # 输出: 2
print(rest)  # 输出: [3, 4, 5]

# 字典解构
let {"name": n, "age": a} = get_person()
print(n, a)

# 嵌套解构
let ((x, y), z) = ((1, 2), 3)
print(x, y, z)  # 输出: 1 2 3
```

解构绑定可以与类型注解结合使用：

```python
let (x: int, y: int) = (1, 2)
let [a: str, *rest: list<str>] = ["first", "second", "third"]
```