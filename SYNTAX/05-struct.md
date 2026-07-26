# 结构体

## 结构体定义

### 基本语法

```python
# 简单结构体
struct Point:
    x: int
    y: int

# 使用结构体
let p: Point = Point(x=10, y=20)
print(p.x, p.y)  # 10 20
```

### 带方法的结构体

```python
struct Vector:
    x: float
    y: float
    
    def magnitude(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
    
    def normalize(self) -> Vector:
        let mag: float = self.magnitude()
        return Vector(x=self.x / mag, y=self.y / mag)

# 使用方法
let v: Vector = Vector(x=3.0, y=4.0)
print(v.magnitude())  # 5.0
```

## `@value` 装饰器

### 自动生成方法

```python
@value
struct Point:
    x: int
    y: int

# @value 自动生成 __eq__、__hash__、__repr__、__copy__
let p1: Point = Point(x=1, y=2)
let p2: Point = Point(x=1, y=2)

print(p1 == p2)      # True (__eq__)
print(hash(p1))      # 基于字段的哈希值 (__hash__)
print(repr(p1))      # Point(x=1, y=2) (__repr__)
let p3: Point = p1   # 自动复制 (__copy__)
```

### 公共字段访问

```python
@value
struct Config:
    debug: bool
    timeout: int

# 字段默认为公共访问
let cfg: Config = Config(debug=True, timeout=30)
cfg.debug = False  # ✅ 允许修改
```

## 隐式结构体

### `implicit struct` 语法

```python
implicit struct Context:
    timestamp: float
    user_id: int

# 隐式结构体可以作为隐式参数
def log(message: str, implicit ctx: Context):
    print(f"[{ctx.timestamp}] {ctx.user_id}: {message}")

# 设置隐式上下文
implicit ctx: Context = Context(timestamp=1234567890.0, user_id=1)
log("Hello")  # 自动传入 ctx
```

## 结构体字面量

### 简洁初始化

```python
struct Config:
    debug: bool
    verbose: bool
    timeout: int

# 使用结构体字面量语法
let cfg: Config = Config {
    debug: True,
    verbose: False,
    timeout: 30
}
```

## 结构体特性

| 特性 | 说明 |
|------|------|
| **C 风格布局** | 结构体字段在内存中连续排列 |
| **静态类型** | 所有字段必须有类型注解 |
| **方法支持** | 可以定义方法，`self` 指向结构体实例 |
| **@value** | 自动生成 `__eq__`、`__hash__`、`__repr__`、`__copy__` |
| **隐式声明** | `implicit struct` 支持隐式参数传递 |
| **字面量语法** | `Struct {field: value}` 简洁初始化 |