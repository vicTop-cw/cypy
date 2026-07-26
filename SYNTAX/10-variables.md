# 变量声明

## 基本声明

### `val` 不可变变量

```python
# val 声明不可变变量（不能重新赋值）
val name: str = "Alice"
val age: int = 30

# 尝试重新赋值会报错
# name = "Bob"  # ❌ 错误：val 变量不可重新赋值
```

### `let` 可变变量

```python
# let 声明可变变量（可以重新赋值）
let score: int = 0
score = 100  # ✅ 允许

let temperature: float = 25.0
temperature = 30.5  # ✅ 允许
```

## 可变与不可变

### 选择建议

```python
# 优先使用 val（不可变）
val PI: float = 3.14159
val MAX_USERS: int = 1000

# 需要修改时使用 let
let count: int = 0
count += 1  # 需要可变
```

## 隐式变量

### `implicit` 关键字

```python
# 声明隐式变量
implicit ctx: Context = Context()

# 在函数中使用隐式参数
def process(data: str, implicit ctx: Context):
    ctx.log(data)

# 调用时无需传递隐式参数
process("hello")  # ctx 自动传入
```

## 变量作用域

### 块级作用域

```python
def example():
    val x: int = 10  # 函数作用域
    
    if True:
        let y: int = 20  # 块级作用域
        print(x, y)  # ✅ 10, 20
    
    # print(y)  # ❌ y 不在作用域内
    
    return x
```

### 全局变量

```python
# 模块级全局变量
val GLOBAL_CONFIG: dict[str, bool] = {"debug": True}

def update_config():
    # 修改全局变量
    GLOBAL_CONFIG["debug"] = False

def use_global():
    print(GLOBAL_CONFIG["debug"])
```

## 类型推断

### 自动推断

```python
# 从字面量推断类型
val x = 10          # int
val name = "Bob"    # str
val flag = True     # bool

# 从表达式推断类型
val sum = 1 + 2     # int
val greeting = "Hello, " + "World"  # str

# 无注解变量退化为 PyObject
let dynamic = 42
dynamic = "hello"  # ✅ 允许
```

## 变量命名规则

### 标识符规则

```python
# 有效命名
val userName: str = "Alice"      # 驼峰命名
val user_name: str = "Bob"       # 蛇形命名
val MAX_SIZE: int = 1000         # 常量大写

# 无效命名（会报错）
# val 1name: str = "Test"    # 不能以数字开头
# val my-name: str = "Test"  # 不能包含连字符
# val class: str = "Test"    # 不能使用关键字
```

## 变量特性

| 特性 | 说明 |
|------|------|
| **val** | 不可变变量，声明后不能重新赋值 |
| **let** | 可变变量，可以重新赋值 |
| **implicit** | 隐式变量，可作为函数的隐式参数 |
| **类型推断** | 无注解时从上下文推断类型 |
| **渐进式类型** | 有注解使用静态类型，无注解退化为 PyObject |
| **块级作用域** | 变量在声明的块内有效 |