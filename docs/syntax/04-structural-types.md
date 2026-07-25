# Cypy 语言语法规范 - 结构类型

## 1. 结构体 (struct)

结构体用于定义 C 风格的数据结构，支持字段和方法。

### 1.1 语法规则

> **规则**：`struct` 只能写在模块顶级（层级 0），且不能嵌套。

### 1.2 简单结构体（仅字段）

```python
# 简单结构体（只有字段）→ 编译为 cdef struct
struct Point:
    x: float
    y: float

struct Rectangle:
    width: float
    height: float
```

编译后的 Cython 代码：

```cython
cdef struct Point:
    float x
    float y

cdef struct Rectangle:
    float width
    float height
```

### 1.3 带方法的结构体

```python
# 带方法的结构体 → 编译为 cdef class
struct Rectangle:
    width: float
    height: float
    
    def area(self) -> float:
        return self.width * self.height
    
    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

struct Counter:
    count: int = 0  # 带默认值
    
    def increment(self) -> None:
        self.count += 1
    
    def reset(self) -> None:
        self.count = 0
```

编译后的 Cython 代码：

```cython
cdef class Rectangle:
    cdef float width
    cdef float height
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
    
    cpdef float area(self):
        return self.width * self.height
```

### 1.4 结构体字面量

```python
# 使用结构体字面量语法创建实例
p = Point {x: 10.0, y: 20.0}
rect = Rectangle {width: 5.0, height: 3.0}

# 访问结构体字段
print(f"Point: ({p.x}, {p.y})")
print(f"Rectangle area: {rect.area()}")
```

### 1.5 结构体字段访问

```python
struct Person:
    name: str
    age: int
    score: float = 0.0  # 默认值

# 创建实例
person = Person {name: "Alice", age: 30}

# 访问字段
print(person.name)   # ✅
print(person.age)    # ✅
print(person.score)  # ✅ 使用默认值 0.0

# 修改字段
person.age = 31      # ✅
person.score = 95.5  # ✅
```

### 1.6 泛型结构体

```python
struct Container[T]:
    value: T
    next: Container[T]*

# 使用泛型结构体
int_container: Container[int] = Container[int] {value: 42, next: NULL}
str_container: Container[str] = Container[str] {value: "hello", next: NULL}
```

## 2. 枚举 (enum)

枚举用于定义命名常量集合。

### 2.1 语法规则

> **规则**：`enum` 只能写在模块顶级（层级 0），且不能嵌套。

### 2.2 基本枚举

```python
enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

enum Direction:
    UP
    DOWN
    LEFT
    RIGHT
```

编译后的 Cython 代码：

```cython
cdef enum Color:
    RED = 1
    GREEN = 2
    BLUE = 3

cdef enum Direction:
    UP
    DOWN
    LEFT
    RIGHT
```

### 2.3 使用枚举

```python
def get_color_name(color: Color) -> str:
    match color:
        case Color.RED:
            return "Red"
        case Color.GREEN:
            return "Green"
        case Color.BLUE:
            return "Blue"
        case _:
            return "Unknown"

# 使用枚举值
selected = Color.GREEN
print(get_color_name(selected))  # 输出: Green
```

### 2.4 枚举值比较

```python
def is_primary(color: Color) -> bool:
    return color == Color.RED or color == Color.GREEN or color == Color.BLUE
```

## 3. 特质 (trait)

特质用于定义接口，描述一组方法签名。

### 3.1 语法规则

> **规则**：`trait` 只能写在模块顶级（层级 0），且不能嵌套。

### 3.2 基本特质

```python
trait Drawable:
    def draw(self) -> None:
        ...
    
    def resize(self, scale: float) -> None:
        ...

trait Printable:
    def to_string(self) -> str:
        ...
```

### 3.3 特质继承

```python
trait Shape(Drawable):
    def area(self) -> float:
        ...
    
    def perimeter(self) -> float:
        ...
```

## 4. 实现 (impl)

`impl` 用于为类型实现特质。

### 4.1 语法规则

> **规则**：`impl` 只能写在模块顶级（层级 0），且不能嵌套。

### 4.2 基本实现

```python
# 定义特质
trait Drawable:
    def draw(self) -> None:
        ...

# 定义结构体
struct Circle:
    x: float
    y: float
    radius: float

# 为 Circle 实现 Drawable 特质
impl Drawable for Circle:
    def draw(self) -> None:
        print(f"Drawing circle at ({self.x}, {self.y}) with radius {self.radius}")
```

### 4.3 实现多个特质

```python
struct Rectangle:
    width: float
    height: float

impl Drawable for Rectangle:
    def draw(self) -> None:
        print(f"Drawing rectangle with width {self.width} and height {self.height}")

impl Printable for Rectangle:
    def to_string(self) -> str:
        return f"Rectangle(width={self.width}, height={self.height})"
```

### 4.4 使用实现

```python
def render(obj: Drawable) -> None:
    obj.draw()

# 使用实现了特质的类型
circle = Circle {x: 10.0, y: 20.0, radius: 5.0}
rect = Rectangle {width: 8.0, height: 4.0}

render(circle)   # ✅ Circle 实现了 Drawable
render(rect)     # ✅ Rectangle 实现了 Drawable
```

## 5. 宏 (macro)

宏是编译期代码替换机制，用于代码生成和元编程。

### 5.1 语法规则

> **规则**：`macro` 只能写在模块顶级（层级 0），且不能嵌套。

### 5.2 基本宏定义

```python
macro twice(input: Tokens) -> Tokens =
    f```$input + $input```

# 使用宏
result = @twice!(x)  # 展开为: x + x
```

### 5.3 带参数的宏

```python
macro assert_eq(a: Tokens, b: Tokens) -> Tokens =
    f```assert $a == $b, f"{repr($a)} != {repr($b)}"```

# 使用宏
@assert_eq!(add(2, 3), 5)
```

### 5.4 多行宏

```python
macro swap(a: Tokens, b: Tokens) -> Tokens =
    f```
temp = $a
$a = $b
$b = temp
```

# 使用宏
x = 10
y = 20
@swap!(x, y)
# 展开为:
# temp = x
# x = y
# y = temp
```

## 6. 编译期求值 (comptime)

`comptime` 用于在编译期计算常量表达式。

### 6.1 基本语法

```python
# 编译期常量计算
result: int = comptime: 2 + 3 * 4  # result = 14（编译时计算）

# 编译期字符串处理
name: str = comptime: "hello".upper()  # name = "HELLO"（编译时计算）
```

### 6.2 编译期类型检查

```python
# 编译期断言
comptime:
    assert sizeof(int) == 4, "int must be 4 bytes"

# 编译期类型判断
comptime:
    if __debug__:
        print("Debug mode enabled")
```

## 7. 结构类型对比

| 类型 | 用途 | 编译目标 | 是否支持方法 |
|------|------|----------|-------------|
| `struct` | C 风格数据结构 | `cdef struct` / `cdef class` | ✅（带方法时） |
| `enum` | 命名常量集合 | `cdef enum` | ❌ |
| `trait` | 接口定义 | Python 抽象基类 | ❌（仅方法签名） |
| `impl` | 特质实现 | Python 类方法 | ✅ |
| `macro` | 编译期代码生成 | 代码替换 | ❌ |

## 8. 结构类型的访问控制

### 8.1 公共字段

```python
struct Point:
    x: float  # 公共字段（默认）
    y: float
```

### 8.2 私有字段

```python
struct Person:
    name: str       # 公共字段
    _age: int       # 私有字段（以下划线开头）
```

### 8.3 访问控制规则

```
规则 1: 以下划线开头的字段为私有字段
规则 2: 私有字段仅在结构体内部可访问
规则 3: 公共字段可在任何地方访问
规则 4: 方法默认是公共的
```

## 9. 结构类型的内存布局

### 9.1 结构体内存布局

```python
struct Point:
    x: float  # 偏移 0，大小 4
    y: float  # 偏移 4，大小 4
# 总大小: 8 字节

struct Complex:
    real: double   # 偏移 0，大小 8
    imag: double   # 偏移 8，大小 8
# 总大小: 16 字节
```

### 9.2 使用 sizeof

```python
size: int = sizeof(Point)    # size = 8
size = sizeof(int)           # size = 4
size = sizeof(double)        # size = 8
```

## 10. 完整示例

```python
# 定义特质
trait Shape:
    def area(self) -> float:
        ...
    
    def perimeter(self) -> float:
        ...

# 定义结构体
struct Circle:
    x: float
    y: float
    radius: float

struct Rectangle:
    width: float
    height: float

# 实现特质
impl Shape for Circle:
    def area(self) -> float:
        return 3.14159 * self.radius * self.radius
    
    def perimeter(self) -> float:
        return 2 * 3.14159 * self.radius

impl Shape for Rectangle:
    def area(self) -> float:
        return self.width * self.height
    
    def perimeter(self) -> float:
        return 2 * (self.width + self.height)

# 使用
def print_shape_info(shape: Shape) -> None:
    print(f"Area: {shape.area()}")
    print(f"Perimeter: {shape.perimeter()}")

circle = Circle {x: 0.0, y: 0.0, radius: 5.0}
rect = Rectangle {width: 4.0, height: 3.0}

print_shape_info(circle)   # ✅
print_shape_info(rect)     # ✅
```
