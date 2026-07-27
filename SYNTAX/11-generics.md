# 泛型系统

## 泛型类型参数

### 基本语法

```python
# 泛型函数
def identity[T](x: T) -> T:
    return x

# 使用泛型函数
let num: int = identity[int](42)
let name: str = identity[str]("Alice")
```

### 多类型参数

```python
def pair[T, U](first: T, second: U) -> tuple[T, U]:
    return (first, second)

let p: tuple[int, str] = pair[int, str](42, "answer")
```

## 泛型函数

### 类型推断

```python
# 编译器自动推断类型参数
def get_first[T](items: list[T]) -> T:
    return items[0]

let numbers: list[int] = [1, 2, 3]
let first_num: int = get_first(numbers)  # 自动推断 T=int

let names: list[str] = ["Alice", "Bob"]
let first_name: str = get_first(names)  # 自动推断 T=str
```

## 泛型特质

### 定义泛型特质

```python
trait Container[T]:
    def add(self, item: T) -> None:
    def get(self, index: int) -> T:
    def size(self) -> int:
```

### 实现泛型特质

```python
struct List[T]:
    items: list[T]
    
    def add(self, item: T) -> None:
        self.items.append(item)
    
    def get(self, index: int) -> T:
        return self.items[index]
    
    def size(self) -> int:
        return len(self.items)

impl Container[T] for List[T]:
    pass
```

## 类型约束

### 联合类型约束

```python
# 类型参数必须是 int 或 float
def process[T: int | float](value: T) -> T:
    return value

let result1: int = process[int](42)     # ✅
let result2: float = process[float](3.14)  # ✅
# let result3: str = process[str]("hello")  # ❌ 类型约束不满足
```

### 特质约束

```python
trait Comparable:
    def compare(self, other: object) -> int:

# 类型参数必须实现 Comparable 特质
def sort[T: Comparable](items: list[T]) -> list[T]:
    # 实现排序逻辑
    return sorted(items, key=lambda x: x)
```

### 多约束

```python
# 多个约束
def serialize[T: Serializable & Printable](obj: T) -> str:
    obj.print()
    return obj.to_json()
```

## 泛型类

### 泛型类定义

```python
class Box[T]:
    def __init__(self, content: T):
        self.content = content
    
    def get(self) -> T:
        return self.content
    
    def set(self, content: T) -> None:
        self.content = content

# 使用泛型类
let int_box: Box[int] = Box[int](42)
let str_box: Box[str] = Box[str]("hello")
```

## 泛型特性

| 特性 | 说明 |
|------|------|
| **类型参数** | 使用 `[T]` 或 `[T, U]` 声明类型参数 |
| **类型推断** | 编译器自动推断类型参数 |
| **泛型函数** | 函数可以是泛型的 |
| **泛型特质** | 特质可以是泛型的 |
| **泛型类** | 类可以是泛型的 |
| **类型约束** | 支持联合类型约束 `T: int \| float` |
| **特质约束** | 支持特质约束 `T: Comparable` |