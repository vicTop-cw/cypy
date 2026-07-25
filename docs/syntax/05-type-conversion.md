# Cypy 语言语法规范 - 类型转换与隐式策略

## 1. 显式类型转换

### 1.1 使用 `as` 关键字

Cypy 使用 `as` 关键字进行显式类型转换：

```python
def convert_values() -> float:
    a: int = 10
    b: float = a as float    # 整数转浮点
    c: int = b as int        # 浮点转整数（截断）
    return (a + c) as float  # 表达式结果转换
```

### 1.2 基本类型转换

```python
# 数值类型转换
x: int = 42
y: float = x as float       # y = 42.0
z: int = 3.99 as int        # z = 3（截断）

# 字符串转换
name: str = 42 as str       # name = "42"
count: int = "123" as int   # count = 123

# 布尔转换
flag: bool = 0 as bool      # flag = False
flag = 1 as bool            # flag = True
flag = "hello" as bool      # flag = True（非空字符串）
```

### 1.3 指针类型转换

```python
# 指针类型转换（使用 & 解引用）
ptr: int* = malloc(sizeof(int))
value: int = &ptr           # 解引用

# 指针类型转换
buffer: void* = malloc(sizeof(int) * 10)
int_buffer: int* = buffer as int*  # void* 转 int*
```

### 1.4 表达式转换

```python
# 表达式结果转换
result: float = (2 + 3) as float      # result = 5.0
average: double = (a + b) / 2 as double  # 先计算再转换

# 函数返回值转换
def compute() -> int:
    return 42

value: float = compute() as float      # value = 42.0
```

## 2. 隐式策略

### 2.1 隐式结构体定义

```python
# 定义隐式结构体（模块级可用）
implicit struct Config:
    debug: bool = True
    timeout: int = 30
    url: str = "http://localhost"

# 隐式结构体在整个模块中自动可用
def process_request():
    if Config.debug:
        print(f"Connecting to {Config.url}")
    # 访问隐式结构体的字段
    return Config.timeout
```

### 2.2 隐式变量声明

```python
# 声明隐式变量
implicit ctx: Config = Config {debug: False, timeout: 60}

# 隐式变量可在整个模块中访问
def get_config():
    return ctx  # ✅ 可访问

def use_config():
    print(ctx.debug)  # ✅ 可访问
```

### 2.3 隐式参数

```python
# 函数参数标记为隐式
def process(data: list[int], implicit ctx: Config) -> int:
    if ctx.debug:
        print(f"Processing {len(data)} items")
    return len(data)

# 调用时无需传递隐式参数
result = process([1, 2, 3])  # ctx 自动从模块级隐式变量获取
```

### 2.4 隐式策略规则

```
规则 1: 隐式结构体使用 `implicit struct` 定义
规则 2: 隐式变量使用 `implicit` 关键字声明
规则 3: 隐式变量/结构体在模块级别自动可用
规则 4: 隐式参数在函数调用时自动填充
规则 5: 隐式策略可用于简化上下文传递
```

## 3. 魔法转换方法

### 3.1 `__cast__` 方法

`__cast__` 方法用于自定义类型的显式转换：

```python
struct Point:
    x: float
    y: float
    
    def __cast__(self, target_type: type) -> object:
        if target_type == tuple:
            return (self.x, self.y)
        elif target_type == list:
            return [self.x, self.y]
        elif target_type == str:
            return f"Point({self.x}, {self.y})"
        raise TypeError(f"Cannot cast Point to {target_type}")

# 使用自定义转换
p = Point {x: 10.0, y: 20.0}
coord: tuple = p as tuple  # (10.0, 20.0)
arr: list = p as list      # [10.0, 20.0]
desc: str = p as str       # "Point(10.0, 20.0)"
```

### 3.2 `__try_cast__` 方法

`__try_cast__` 方法用于安全的类型转换，失败时返回 None：

```python
struct SafeNumber:
    value: int
    
    def __try_cast__(self, target_type: type) -> object:
        if target_type == float:
            return float(self.value)
        elif target_type == str:
            return str(self.value)
        return None  # 转换失败返回 None

# 使用安全转换
num = SafeNumber {value: 42}
f: float = num as float  # 42.0（成功）
s: str = num as str      # "42"（成功）
b: bool = num as bool    # None（失败，返回 None）
```

### 3.3 内置类型转换

```python
# 数值类型之间的隐式转换（向上转换）
x: float = 10    # ✅ int 自动转为 float
y: double = 3.14 # ✅ float 自动转为 double

# 数值类型之间的显式转换（向下转换）
a: int = 3.99 as int    # ✅ 需要显式转换，结果为 3
b: float = 100 as float # ✅ 显式转换

# 布尔类型转换
flag: bool = 0          # ✅ 0 转为 False
flag = 42               # ✅ 非零转为 True
flag = ""               # ✅ 空字符串转为 False
flag = "hello"          # ✅ 非空字符串转为 True

# None 转换
value: int = None       # ✅ None 可赋值给任意类型
if value is not None:
    print(value)
```

## 4. 类型转换规则

### 4.1 转换规则表

| 源类型 | 目标类型 | 转换方式 | 说明 |
|--------|----------|----------|------|
| `int` | `float` | 隐式 | 自动转换 |
| `float` | `int` | 显式 | 截断小数部分 |
| `int` | `str` | 显式 | 数字转字符串 |
| `str` | `int` | 显式 | 字符串转数字 |
| `bool` | `int` | 隐式 | True→1, False→0 |
| `int` | `bool` | 隐式 | 0→False, 非零→True |
| 任意类型 | `None` | 隐式 | 允许赋值 |
| `None` | 任意类型 | 隐式 | 允许赋值 |

### 4.2 转换优先级

```
规则 1: 向上转换（精度增加）→ 自动隐式转换
规则 2: 向下转换（精度损失）→ 需要显式转换
规则 3: 跨类型转换（数值↔字符串）→ 需要显式转换
规则 4: None 可与任意类型相互转换 → 隐式转换
```

### 4.3 编译时检查

```python
# ✅ 允许：向上转换
x: float = 10

# ❌ 编译错误：向下转换需要显式转换
y: int = 3.14  # 错误：期望 int，得到 float

# ✅ 允许：显式向下转换
z: int = 3.14 as int

# ❌ 编译错误：字符串不能隐式转数字
count: int = "123"  # 错误：期望 int，得到 str

# ✅ 允许：显式转换
count: int = "123" as int
```

## 5. 递归防护

### 5.1 递归转换防护

Cypy 在类型转换时会防止无限递归：

```python
struct RecursiveType:
    def __cast__(self, target_type: type) -> object:
        # 防止递归转换到自身类型
        if target_type == RecursiveType:
            return self
        # 其他转换逻辑
        ...

# 递归防护机制会检测并阻止无限递归转换
```

### 5.2 策略激活栈

```python
# 策略激活栈用于跟踪当前正在执行的策略
# 防止同一策略被无限递归调用

# 当策略执行时，会将其加入激活栈
# 如果再次遇到相同策略，会触发递归防护
```

## 6. 类型兼容性检查

### 6.1 类型兼容性规则

```python
# 子类可赋值给父类（协变）
class Animal:
    pass

class Dog(Animal):
    pass

animal: Animal = Dog()  # ✅ 允许

# 父类不可赋值给子类（需要显式转换）
dog: Dog = Animal()     # ❌ 编译错误
dog: Dog = Animal() as Dog  # ✅ 显式转换

# 容器类型兼容性
items: list[Animal] = [Dog(), Dog()]  # ✅ 允许
```

### 6.2 多态转换

```python
# 多态类型转换
struct Shape:
    pass

struct Circle(Shape):
    radius: float

struct Rectangle(Shape):
    width: float
    height: float

# 子类转父类（隐式）
shape: Shape = Circle {radius: 5.0}  # ✅

# 父类转子类（显式）
circle: Circle = shape as Circle     # ✅ 需要显式转换

# 类型检查
if isinstance(shape, Circle):
    # 类型守卫，shape 在此分支内被推断为 Circle
    print(shape.radius)
```

## 7. 类型转换与性能

### 7.1 隐式转换的性能影响

```python
# 隐式转换在编译时完成，无运行时开销
x: float = 10  # 编译时转换，无运行时开销

# 显式转换在编译时完成，无运行时开销
y: int = 3.99 as int  # 编译时转换，无运行时开销

# 运行时转换（使用内置函数）
z = int("123")  # 运行时转换，有开销
```

### 7.2 转换优化

```python
# 编译时常量转换（最优）
value: float = comptime: 42 as float  # 编译时完成

# 静态类型转换（优）
x: int = 10
y: float = x  # 编译时完成

# 动态类型转换（一般）
x = 10  # PyObject
y = float(x)  # 运行时转换
```

## 8. 完整示例

```python
# 隐式结构体定义
implicit struct AppConfig:
    debug: bool = True
    log_level: str = "INFO"
    timeout: int = 30

# 隐式变量声明
implicit ctx: AppConfig = AppConfig {debug: False}

# 使用隐式策略
def log_message(msg: str) -> None:
    if ctx.debug:
        print(f"[DEBUG] {msg}")
    elif ctx.log_level == "INFO":
        print(f"[INFO] {msg}")

# 类型转换示例
struct Point:
    x: float
    y: float
    
    def __cast__(self, target_type: type) -> object:
        if target_type == tuple:
            return (self.x, self.y)
        return None

# 使用类型转换
p = Point {x: 10.0, y: 20.0}
coord: tuple = p as tuple
print(f"Coordinates: {coord}")

# 显式类型转换
count: int = "123" as int
price: float = 42 as float
print(f"Count: {count}, Price: {price}")
```
