# 内置魔法 Trait 和全局函数

Cypy 通过魔法方法（magic methods）实现类型系统的核心功能，包括隐式转换、守卫策略、比较与哈希等。

## 隐式转换 Trait

### `__implicit_copy__`

`__implicit_copy__` 实现 Mojo 风格的隐式复制，当需要复制一个值时自动调用。

```python
struct StringWrapper:
    letue: str
    
    def __implicit_copy__(self) -> StringWrapper:
        return StringWrapper(letue=self.letue)

let s = StringWrapper("hello")
let s2 = s  # 自动调用 __implicit_copy__
```

### `__implicit_into__`

`__implicit_into__` 实现 Scala 风格的隐式转换，当类型不匹配时自动搜索并调用。

```python
struct Celsius:
    temp: float
    
    def __implicit_into__[Fahrenheit](self) -> Fahrenheit:
        return Fahrenheit(temp=self.temp * 9/5 + 32)

struct Fahrenheit:
    temp: float

let c: Celsius = Celsius(temp=0)
let f: Fahrenheit = c  # 自动调用 __implicit_into__
```

### `__implicit_default__`

`__implicit_default__` 提供隐式默认值填充，当参数未提供时自动使用。

```python
struct Config:
    timeout: int
    debug: bool
    
    @staticmethod
    def __implicit_default__() -> Config:
        return Config(timeout=30, debug=False)

def process(data: str, cfg: Config = __implicit_default__):
    print(f"Processing: {data} with timeout {cfg.timeout}")

process("hello")  # 使用默认 Config
```

## 守卫策略 Trait

### `__guarded_pred__`

`__guarded_pred__` 判断是否可以执行转换。

```python
struct Number:
    value: float
    
    def __guarded_pred__(self, target_type: type) -> bool:
        return target_type in (int, float)
```

### `__guarded_action__`

`__guarded_action__` 执行转换操作。

```python
struct Number:
    value: float
    
    def __guarded_action__(self, target_type: type) -> object:
        if target_type == int:
            return int(self.value)
        return self.value

let num: Number = Number(value=3.14)
let i: int = num  # 通过守卫策略转换
```

## 比较与哈希 Trait

### `__hash__`

`__hash__` 计算对象的哈希值，用于字典键和集合。

```python
struct Point:
    x: int
    y: int
    
    def __hash__(self) -> int:
        return hash((self.x, self.y))

let p1: Point = Point(x=1, y=2)
let p2: Point = Point(x=1, y=2)
print(hash(p1) == hash(p2))  # True
```

### `__eq__`

`__eq__` 判断两个对象是否相等。

```python
struct Point:
    x: int
    y: int
    
    def __eq__(self, other: Point) -> bool:
        return self.x == other.x and self.y == other.y

let p1: Point = Point(x=1, y=2)
let p2: Point = Point(x=1, y=2)
print(p1 == p2)  # True
```

### 比较操作符

| 魔法方法 | 操作符 | 说明 |
|----------|--------|------|
| `__lt__` | `<` | 小于 |
| `__le__` | `<=` | 小于等于 |
| `__gt__` | `>` | 大于 |
| `__ge__` | `>=` | 大于等于 |

```python
struct Person:
    name: str
    age: int
    
    def __lt__(self, other: Person) -> bool:
        return self.age < other.age
    
    def __eq__(self, other: Person) -> bool:
        return self.name == other.name and self.age == other.age

let alice: Person = Person(name="Alice", age=30)
let bob: Person = Person(name="Bob", age=25)
print(alice > bob)   # True
print(alice >= bob)  # True
```

## 类型转换 Trait

### 数值转换

| 魔法方法 | 说明 |
|----------|------|
| `__int__` | 转换为整数 |
| `__float__` | 转换为浮点数 |
| `__bool__` | 转换为布尔值 |

```python
struct SafeInt:
    value: int
    
    def __int__(self) -> int:
        return self.value
    
    def __float__(self) -> float:
        return float(self.value)
    
    def __bool__(self) -> bool:
        return self.value != 0

let safe: SafeInt = SafeInt(value=42)
let i: int = int(safe)   # 42
let f: float = float(safe)  # 42.0
let b: bool = bool(safe)    # True
```

### 字符串转换

| 魔法方法 | 说明 |
|----------|------|
| `__str__` | 转换为可读字符串 |
| `__repr__` | 转换为可重现字符串 |

```python
struct Point:
    x: int
    y: int
    
    def __str__(self) -> str:
        return f"({self.x}, {self.y})"
    
    def __repr__(self) -> str:
        return f"Point(x={self.x}, y={self.y})"

let p: Point = Point(x=1, y=2)
print(str(p))   # (1, 2)
print(repr(p))  # Point(x=1, y=2)
```

## 容器 Trait

### `__len__`

`__len__` 返回容器长度。

```python
struct Stack:
    items: list[int]
    
    def __len__(self) -> int:
        return len(self.items)

let stack: Stack = Stack(items=[1, 2, 3])
print(len(stack))  # 3
```

### `__getitem__`

`__getitem__` 支持索引访问。

```python
struct Stack:
    items: list[int]
    
    def __getitem__(self, index: int) -> int:
        return self.items[index]

let stack: Stack = Stack(items=[1, 2, 3])
print(stack[0])  # 1
```

### `__setitem__`

`__setitem__` 支持索引赋值。

```python
struct Stack:
    items: list[int]
    
    def __setitem__(self, index: int, value: int) -> None:
        self.items[index] = value

let stack: Stack = Stack(items=[1, 2, 3])
stack[0] = 10
print(stack[0])  # 10
```

## 迭代器 Trait

### `__iter__`

`__iter__` 返回迭代器。

```python
struct Range:
    start: int
    end: int
    
    def __iter__(self) -> iter:
        return iter(range(self.start, self.end))

for i in Range(start=0, end=5):
    print(i)  # 0, 1, 2, 3, 4
```

## 上下文管理器 Trait

### `__enter__` 和 `__exit__`

支持 `with` 语句。

```python
struct FileHandler:
    filename: str
    
    def __enter__(self) -> FileHandler:
        print(f"Opening {self.filename}")
        return self
    
    def __exit__(self, exc_type: type, exc_val: object, exc_tb: object) -> bool:
        print(f"Closing {self.filename}")
        return False

with FileHandler(filename="test.txt") as fh:
    print("Processing file...")
```

## 运算符重载 Trait

见 [12-operators.md](12-operators.md) 了解完整的操作符重载方法。

## 全局函数

### `cast`

显式类型转换。

```python
let x: float = 3.14
let y: int = cast(int, x)  # 3
```

### `try_cast`

安全的类型转换，返回成功与否和结果。

```python
let (success, result) = try_cast(str, 42)
if success:
    print(result)  # "42"
```

### `size_of`

获取类型大小（字节）。

```python
print(size_of(int))    # 4
print(size_of(float))  # 8
```

### `offset_of`

获取结构体字段偏移。

```python
struct Point:
    x: int
    y: int

print(offset_of(Point, "x"))  # 0
print(offset_of(Point, "y"))  # 4
```

### `align_of`

获取类型对齐方式。

```python
print(align_of(int))   # 4
print(align_of(float)) # 8
```
