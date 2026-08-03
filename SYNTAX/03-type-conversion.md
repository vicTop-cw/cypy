# 类型转换

## 显式转换

### `as` 语法

```python
# 基本类型转换
x: float = 3.14
y: int = x as int  # 3

# 字符串转换
num: int = "42" as int
text: str = 100 as str

# 容器类型转换
items: list<int> = (1, 2, 3) as list<int>
```

### 内置函数转换

```python
# 使用内置函数
let x: float = float(42)
let y: int = int(3.99)
let z: str = str(True)
```

## 隐式转换

### 隐式策略体系

Cypy 通过 `__implicit_copy__` 和 `__implicit_into__` 魔法方法实现隐式类型转换：

```python
struct Celsius:
    temp: float
    
    def __implicit_copy__(self) -> float:
        return self.temp
    
    def __implicit_into__(self) -> Fahrenheit:
        return Fahrenheit(temp=self.temp * 9/5 + 32)

struct Fahrenheit:
    temp: float

# 隐式转换
let c: Celsius = Celsius(temp=0)
let f: Fahrenheit = c  # 通过 __implicit_into__ 转换
let t: float = c       # 通过 __implicit_copy__ 转换
```

## 魔法方法

### `__cast__` 和 `__try_cast__`

```python
struct SafeInt:
    value: int
    
    def __cast__(self, target_type: type) -> object:
        if target_type == float:
            return float(self.value)
        raise TypeError(f"Cannot cast SafeInt to {target_type}")
    
    def __try_cast__(self, target_type: type) -> tuple<bool, object>:
        if target_type == float:
            return (True, float(self.value))
        return (False, None)

# 使用 cast
let safe: SafeInt = SafeInt(value=42)
let f: float = safe as float  # 调用 __cast__

# 使用 try_cast
let (success, result) = safe.__try_cast__(str)
if success:
    print(result)
```

## 守卫策略

### 兜底守卫机制

```python
struct Number:
    value: float
    
    def __guarded_pred__(self, target_type: type) -> bool:
        # 判断是否可以转换
        return target_type in (int, float)
    
    def __guarded_action__(self, target_type: type) -> object:
        # 执行转换
        if target_type == int:
            return int(self.value)
        return self.value

# 当其他转换失败时，守卫策略生效
let num: Number = Number(value=3.14)
let i: int = num  # 通过守卫策略转换
```

### 策略栈与深度限制

```python
# 策略栈最多5层，防止递归转换
# 超过深度限制将抛出 TypeError
let result: int = convert_through_five_layers(value)
```

## 类型转换规则

| 规则 | 说明 |
|------|------|
| **显式转换** | 使用 `as` 语法或内置函数，编译时检查 |
| **隐式转换** | 通过 `__implicit_copy__` 和 `__implicit_into__` |
| **守卫策略** | `__guarded_pred__` 判断条件，`__guarded_action__` 执行转换 |
| **策略栈** | 最多5层深度，防止递归滥用 |