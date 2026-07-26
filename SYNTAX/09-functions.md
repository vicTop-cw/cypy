# 函数

## 函数定义

Cypy 使用 `def` 关键字定义函数，类型注解是可选的：

```python
# 带类型注解的函数
def greet(name: str) -> str:
    return f"Hello, {name}"

# 无返回值函数
def log(message: str) -> None:
    print(f"[LOG] {message}")

# 带默认参数的函数
def repeat(s: str, times: int = 3) -> str:
    return s * times

# 动态类型函数（无类型注解）
def add(x, y):
    return x + y
```

## 类型注解规则

### 有注解 vs 无注解

```python
# 有类型注解：使用静态类型
def add(x: int, y: int) -> int:
    return x + y

# 无类型注解：参数和返回值退化为 PyObject
def dynamic_add(x, y):
    return x + y
```

**规则：**
- **有注解**：使用指定的静态类型
- **无注解**：类型退化为 `PyObject`，支持动态类型

### 代码生成差异

```python
# 无类型注解 → 生成普通 def
def add(x, y):
    return x + y
# 生成: def add(x, y):

# 有类型注解 → 生成 cpdef（Cython 优化）
def add(x: int, y: int) -> int:
    return x + y
# 生成: cpdef int add(int x, int y):
```

## 可变参数

```python
# 可变位置参数
def sum_all(*args: int) -> int:
    total: int = 0
    for num in args:
        total += num
    return total

# 可变关键字参数
def format_user(**kwargs: object) -> str:
    return ", ".join(f"{k}: {v}" for k, v in kwargs.items())
```

## 函数调用

### 基本调用

```python
# 位置参数
result = greet("Alice")

# 关键字参数
result = greet(name="Bob")

# 混合调用
result = repeat("Hello", times=5)
```

### 解包参数

```python
# 列表解包
let nums: list[int] = [1, 2, 3]
result = sum_all(*nums)  # 6

# 字典解包
let user_data: dict[str, object] = {"name": "Alice", "age": 30}
result = format_user(**user_data)
```

## 高阶函数

### 函数作为参数

```python
def apply(func, value: int) -> int:
    return func(value)

def double(x: int) -> int:
    return x * 2

result = apply(double, 5)  # 10
```

### 函数作为返回值

```python
def create_multiplier(factor: int):
    def multiply(x: int) -> int:
        return x * factor
    return multiply

let triple = create_multiplier(3)
result = triple(5)  # 15
```

## 异步函数

### 基本异步函数

```python
async def fetch_data(url: str) -> str:
    # 模拟异步操作
    await asyncio.sleep(1)
    return f"Data from {url}"

# 使用异步函数
async def main():
    data = await fetch_data("https://example.com")
    print(data)
```

## 生成器函数

### 基本生成器

```python
def count_up_to(n: int):
    let i: int = 1
    while i <= n:
        yield i
        i += 1

# 使用生成器
for num in count_up_to(5):
    print(num)  # 1, 2, 3, 4, 5
```

### 带类型注解的生成器

```python
def generate_fibonacci() -> Generator[int, None, None]:
    let a: int = 0
    let b: int = 1
    while True:
        yield a
        (a, b) = (b, a + b)
```

## 装饰器

### 内置装饰器

```python
@python
def legacy_code(x, y):
    # @python 装饰器跳过类型检查，回退到 CPython
    return x + y

@staticmethod
def utility_method():
    pass

@classmethod
def factory_method(cls):
    return cls()

@property
def value(self):
    return self._value
```

### 自定义装饰器

```python
def timing_decorator(func):
    def wrapper(*args, **kwargs):
        let start: float = time.time()
        result = func(*args, **kwargs)
        let end: float = time.time()
        print(f"Function {func.__name__} took {end - start:.4f}s")
        return result
    return wrapper

@timing_decorator
def slow_function():
    time.sleep(0.5)
```

## 测试函数

### 测试套件与测试用例

参照 lang-zone/hermes 的测试框架设计，Cypy 提供了简洁的测试语法：

```python
suite MathTests:
    test add_positive_numbers:
        assert add(2, 3) == 5
        assert add(-1, 1) == 0
    
    test divide_by_non_zero:
        assert divide(10, 2) == 5
    
    test divide_by_zero_raises:
        with pytest.raises(ZeroDivisionError):
            divide(10, 0)
    
    setup:
        # 套件级初始化
        print("Setting up MathTests")
    
    teardown:
        # 套件级清理
        print("Cleaning up MathTests")
```

### 独立测试用例

```python
test simple_add:
    assert 1 + 1 == 2

test string_concat:
    assert "hello" + " " + "world" == "hello world"
```

## 函数特性

| 特性 | 说明 |
|------|------|
| **类型注解** | 参数和返回值支持类型注解，无注解退化为 PyObject |
| **默认参数** | 支持默认参数值 |
| **可变参数** | 支持 `*args` 和 `**kwargs` |
| **高阶函数** | 函数可以作为参数或返回值 |
| **异步函数** | 支持 `async/await` |
| **生成器** | 支持 `yield` 语法 |
| **装饰器** | 支持 `@python`、`@staticmethod`、`@classmethod` 等 |
| **测试语法** | 支持 `suite` 和 `test` 关键字定义测试套件和测试用例 |
