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