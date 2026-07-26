# 枚举

## 枚举定义

### 基本语法

```python
# 简单枚举
enum Color:
    RED
    GREEN
    BLUE

# 使用枚举
let c: Color = Color.RED
print(c)  # Color.RED
```

### 带值的枚举

```python
# 带整数值的枚举
enum Status:
    PENDING = 0
    ACTIVE = 1
    INACTIVE = 2

# 使用
let s: Status = Status.ACTIVE
print(int(s))  # 1
```

### 带不同类型值的枚举

```python
# 枚举值可以是不同类型
enum Result:
    SUCCESS = True
    ERROR = "failed"
    TIMEOUT = 408

let r: Result = Result.SUCCESS
```

## 枚举使用

### 枚举成员检查

```python
enum Direction:
    NORTH
    SOUTH
    EAST
    WEST

let d: Direction = Direction.NORTH

# 检查是否为枚举成员
if d == Direction.NORTH:
    print("Going north")

# 获取枚举名称
print(d.name)  # "NORTH"
```

### 枚举遍历

```python
enum Color:
    RED
    GREEN
    BLUE

# 遍历所有枚举成员
for color in Color:
    print(color)
```

## 枚举方法

### 自定义方法

```python
enum Operation:
    ADD
    SUBTRACT
    MULTIPLY
    DIVIDE
    
    def apply(self, a: float, b: float) -> float:
        match self:
            case Operation.ADD:
                return a + b
            case Operation.SUBTRACT:
                return a - b
            case Operation.MULTIPLY:
                return a * b
            case Operation.DIVIDE:
                return a / b

# 使用方法
let op: Operation = Operation.MULTIPLY
print(op.apply(3, 4))  # 12
```

## 枚举与模式匹配

### 模式匹配中的枚举

```python
enum Shape:
    CIRCLE(radius: float)
    RECTANGLE(width: float, height: float)
    TRIANGLE(base: float, height: float)

let shape: Shape = Shape.CIRCLE(radius=5.0)

match shape:
    case Shape.CIRCLE(r):
        print(f"Circle with radius {r}")
    case Shape.RECTANGLE(w, h):
        print(f"Rectangle {w}x{h}")
    case Shape.TRIANGLE(b, h):
        print(f"Triangle with area {b*h/2}")
```

## 枚举特性

| 特性 | 说明 |
|------|------|
| **类型安全** | 枚举值是唯一的类型，不能与整数混淆 |
| **名称访问** | 可以通过 `.name` 获取枚举名称字符串 |
| **值访问** | 可以通过 `int()` 获取枚举整数值 |
| **遍历** | 支持 `for` 循环遍历所有枚举成员 |
| **方法** | 可以定义自定义方法 |
| **模式匹配** | 支持 match/case 模式匹配 |