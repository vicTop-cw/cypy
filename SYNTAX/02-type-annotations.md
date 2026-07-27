# 类型注解

## 变量注解

### 基本语法

```python
# 基本类型注解
age: int = 30
name: str = "Alice"
is_active: bool = True
score: float = 95.5

# 容器类型注解
numbers: list[int] = [1, 2, 3]
mapping: dict[str, int] = {"a": 1, "b": 2}
coordinates: tuple[int, int] = (10, 20)

# 无初始化的注解
result: int
result = 42

# 可选类型（可能为 None）
maybe_value: object = None
```

### 渐进式类型

```python
# 有注解的变量 - 静态类型检查
let x: int = 10
x = "hello"  # ❌ 类型错误

# 无注解的变量 - 退化为 PyObject
dynamic = 42
dynamic = "hello"  # ✅ 允许，运行时动态类型
```

## 函数注解

### 参数和返回值注解

```python
# 带类型注解的函数
def add(a: int, b: int) -> int:
    return a + b

# 部分注解
def greet(name: str):
    return f"Hello, {name}"  # 返回类型从 return 语句推断

# 无注解函数（完全动态）
def process(data):
    return data

# 可选参数
def repeat(s: str, times: int = 3) -> str:
    return s * times

# 可变参数
def sum_all(*args: int) -> int:
    total: int = 0
    for num in args:
        total += num
    return total
```

### 类型检查行为

```python
def double(x: int) -> int:
    return x * 2

result = double(42)    # ✅ 正确
result = double("42")  # ❌ 编译时类型错误
```

## 类型别名

### 基本类型别名

```python
# 简单类型别名
type Point = tuple[int, int]
type Matrix = list[list[float]]

# 使用类型别名
origin: Point = (0, 0)
identity: Matrix = [[1, 0], [0, 1]]
```

### 泛型类型别名

```python
# 泛型类型别名
type Result[T] = tuple[bool, T]

# 使用泛型类型别名
success: Result[int] = (True, 42)
failure: Result[str] = (False, "error")
```

## 联合类型

### 联合类型注解

```python
# 联合类型（支持多种类型）
type Numeric = int | float
type StringOrNone = str | None

# 使用联合类型
def process_value(val: Numeric) -> Numeric:
    return val * 2

def get_name() -> StringOrNone:
    return None  # 或返回字符串
```

## 特殊注解

### Never 类型注解

```python
# 返回 Never 的函数
def fatal_error(message: str) -> Never:
    raise RuntimeError(message)

# 不会到达的代码路径
def safe_divide(a: float, b: float) -> float:
    if b == 0:
        fatal_error("Division by zero")  # 返回 Never
    return a / b  # 类型检查通过
```

### 无返回值函数

```python
# 返回 None 的函数（省略返回类型）
def print_message(msg: str):
    print(msg)

# 显式标注 None 返回
def log(message: str) -> None:
    print(f"[LOG] {message}")
```

## 注解与 `@python` 装饰器

```python
@python
def legacy_code(x, y):
    # @python 装饰器跳过类型检查
    return x + y

# 普通函数仍进行类型检查
def modern_code(x: int, y: int) -> int:
    return x + y
```