# 特质与实现

## 特质定义

### 基本语法

```python
# 定义特质
trait Printable:
    def print(self) -> None:

trait Serializable:
    def to_json(self) -> str:
```

### 带方法体的特质

```python
trait Comparable<T>:
    def compare(self, other: T) -> int:

    def equals(self, other: T) -> bool:
        return self.compare(other) == 0

    def less_than(self, other: T) -> bool:
        return self.compare(other) < 0
```

## 实现特质

### 基本实现

```python
trait Printable:
    def print(self) -> None:

struct Person:
    name: str
    age: int

    def print(self) -> None:
        print(f"Person: {self.name}, {self.age}")

# 实现特质
impl Printable for Person:
    pass  # 方法已在结构体中定义
```

### 外部实现

```python
struct Point:
    x: int
    y: int

# 在结构体外部实现特质
impl Printable for Point:
    def print(self) -> None:
        print(f"Point: ({self.x}, {self.y})")
```

## 泛型特质

### 定义泛型特质

```python
trait Container<T>:
    def add(self, item: T) -> None:
    def remove(self, item: T) -> bool:
    def contains(self, item: T) -> bool:
    def size(self) -> int:
```

### 实现泛型特质

```python
struct List<T>:
    items: list<T>

    def add(self, item: T) -> None:
        self.items.append(item)

    def remove(self, item: T) -> bool:
        if item in self.items:
            self.items.remove(item)
            return True
        return False

    def contains(self, item: T) -> bool:
        return item in self.items

    def size(self) -> int:
        return len(self.items)

impl Container<T> for List<T>:
    pass
```

## 特质继承

### 特质组合

```python
trait Readable:
    def read(self) -> str:

trait Writable:
    def write(self, data: str) -> None:

# 继承多个特质
trait ReadWrite extends Readable, Writable:
    pass

struct File:
    path: str

    def read(self) -> str:
        return f"Reading from {self.path}"

    def write(self, data: str) -> None:
        print(f"Writing to {self.path}: {data}")

impl ReadWrite for File:
    pass
```

## 特质作为类型

### 特质类型注解

```python
trait Logger:
    def log(self, message: str) -> None:

struct ConsoleLogger:
    def log(self, message: str) -> None:
        print(f"[LOG] {message}")

struct FileLogger:
    def log(self, message: str) -> None:
        print(f"[FILE] {message}")

# 使用特质作为类型
def process(data: str, logger: Logger):
    logger.log(f"Processing: {data}")

# 传入不同实现
let console: ConsoleLogger = ConsoleLogger()
let file: FileLogger = FileLogger()
process("hello", console)
process("world", file)
```

## 特质特性

| 特性 | 说明 |
|------|------|
| **接口定义** | 特质定义方法签名，不包含实现（除非提供默认实现） |
| **实现分离** | 特质实现与结构体定义分离 |
| **泛型支持** | 支持泛型特质 `trait Name<T>` |
| **多重继承** | 特质可以继承多个其他特质 |
| **类型抽象** | 特质可以作为类型注解，实现多态 |
