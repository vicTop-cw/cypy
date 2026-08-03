# 魔法属性

## 模块级魔法属性

### 身份属性

```python
# 模块身份属性
print(__name__)    # 模块名称
print(__file__)    # 模块文件路径
print(__package__) # 包名称
print(__path__)    # 包路径
```

### 可见性属性

```python
# 模块可见性属性
__all__ = ["public_func", "PublicClass"]  # 公开导出的名称
__private__ = ["_private_func"]          # 私有名称
```

### 编译环境属性

```python
# 编译环境属性
print(__compile_time__)  # 编译时间戳
print(__target__)        # 目标平台 (cython/c)
print(__profile__)       # 编译配置文件
```

### 依赖属性

```python
# 依赖属性
__deps__ = ["numpy", "scipy"]  # 模块依赖
```

## 结构体魔法方法

### `@value` 自动生成

```python
@value
struct Point:
    x: int
    y: int

# @value 自动生成以下方法：
# __eq__ - 相等比较
# __hash__ - 哈希值
# __repr__ - 字符串表示
# __copy__ - 复制
```

### 自定义魔法方法

```python
struct Vector:
    x: float
    y: float
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector):
            return False
        return self.x == other.x and self.y == other.y
    
    def __hash__(self) -> int:
        return hash((self.x, self.y))
    
    def __repr__(self) -> str:
        return f"Vector({self.x}, {self.y})"
```

## 类型转换魔法方法

### `__cast__` 和 `__try_cast__`

```python
struct SafeInt:
    value: int
    
    def __cast__(self, target_type: type) -> object:
        if target_type == float:
            return float(self.value)
        raise TypeError(f"Cannot cast to {target_type}")
    
    def __try_cast__(self, target_type: type) -> tuple<bool, object>:
        if target_type == float:
            return (True, float(self.value))
        return (False, None)
```

### `__implicit_copy__` 和 `__implicit_into__`

```python
struct Celsius:
    temp: float
    
    def __implicit_copy__(self) -> float:
        return self.temp
    
    def __implicit_into__(self) -> Fahrenheit:
        return Fahrenheit(temp=self.temp * 9/5 + 32)
```

## 守卫策略魔法方法

### `__guarded_pred__` 和 `__guarded_action__`

```python
struct Number:
    value: float
    
    def __guarded_pred__(self, target_type: type) -> bool:
        return target_type in (int, float)
    
    def __guarded_action__(self, target_type: type) -> object:
        if target_type == int:
            return int(self.value)
        return self.value
```

## 上下文管理器魔法方法

### `__enter__` 和 `__exit__`

```python
class Resource:
    def __enter__(self):
        print("Acquiring resource")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Releasing resource")

# 使用上下文管理器
with Resource():
    print("Using resource")
```

## 迭代器魔法方法

### `__iter__` 和 `__next__`

```python
class RangeIterator:
    def __init__(self, end: int):
        self.current = 0
        self.end = end
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.current >= self.end:
            raise StopIteration
        let value = self.current
        self.current += 1
        return value

# 使用迭代器
for i in RangeIterator(5):
    print(i)  # 0, 1, 2, 3, 4
```

## 魔法属性特性

| 特性 | 说明 |
|------|------|
| **模块级属性** | `__name__`, `__file__`, `__all__`, `__compile_time__` |
| **结构体方法** | `__eq__`, `__hash__`, `__repr__`, `__copy__` |
| **类型转换** | `__cast__`, `__try_cast__`, `__implicit_copy__`, `__implicit_into__` |
| **守卫策略** | `__guarded_pred__`, `__guarded_action__` |
| **上下文管理器** | `__enter__`, `__exit__` |
| **迭代器** | `__iter__`, `__next__` |