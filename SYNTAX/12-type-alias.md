# 类型别名

## 基本类型别名

### 定义和使用

```python
# 简单类型别名
type Point = tuple[int, int]
type Matrix = list[list[float]]
type Callback = Callable[[int], str]

# 使用类型别名
let origin: Point = (0, 0)
let identity: Matrix = [[1, 0], [0, 1]]

def process(callback: Callback):
    result = callback(42)
    print(result)
```

## 泛型类型别名

### 定义泛型别名

```python
# 泛型类型别名
type Result[T] = tuple[bool, T]
type Optional[T] = T | None
type ListOrSet[T] = list[T] | set[T]

# 使用泛型类型别名
let success: Result[int] = (True, 42)
let failure: Result[str] = (False, "error")
let maybe_num: Optional[int] = None
let numbers: ListOrSet[int] = [1, 2, 3]
```

## 类型别名扩展

### 在代码生成中的扩展

```python
# 类型别名在编译时被扩展为真实类型
type ID = int
type Name = str

struct User:
    id: ID      # 编译时扩展为 int
    name: Name  # 编译时扩展为 str

# 使用时完全等价于原始类型
let user: User = User(id=1, name="Alice")
let uid: ID = user.id  # 类型为 int
```

## 类型别名与特质/结构体

### 结合使用

```python
# 类型别名可以引用特质
trait Logger:
    def log(self, message: str) -> None:

type LogHandler = Logger

# 使用类型别名作为特质
def configure(handler: LogHandler):
    handler.log("Configured")

# 类型别名可以引用结构体
struct Configuration:
    debug: bool
    timeout: int

type Config = Configuration

let cfg: Config = Configuration(debug=True, timeout=30)
```

## 类型别名特性

| 特性 | 说明 |
|------|------|
| **类型安全** | 类型别名是类型的别名，不是新类型，编译时完全等价 |
| **泛型支持** | 支持泛型类型别名 `type Result[T]` |
| **编译时扩展** | 类型别名在代码生成阶段被扩展为真实类型 |
| **可读性** | 提高代码可读性，用有意义的名称替代复杂类型 |
| **重构友好** | 修改类型别名定义即可影响所有使用位置 |