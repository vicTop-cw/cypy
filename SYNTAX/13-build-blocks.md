# 构建块语法

## 变量构建块

### 基本语法

```python
# 变量构建块 :=
let result =:
    let x: int = 10
    let y: int = 20
    x + y  # 最后一个表达式作为返回值

print(result)  # 30
```

### 自动赋值

```python
# 构建块自动将最后表达式赋值给左侧变量
let greeting =:
    let name: str = "Alice"
    f"Hello, {name}"

print(greeting)  # "Hello, Alice"
```

## 调用构建块

### 基本语法

```python
# 调用构建块 ~:
def apply(func):
    return func()

let value = apply(~:
    let x: int = 5
    x * 2
)

print(value)  # 10
```

### 返回元组/字典

```python
# 调用构建块必须返回元组、命名元组、字典或实现 BuildParams 的对象
let data = apply(~:
    (1, "hello")  # 返回元组
)

let config = apply(~:
    {"debug": True, "timeout": 30}  # 返回字典
)
```

## 生成器构建块

### 基本语法

```python
# 生成器构建块 *:
def create_generator():
    return *:
        for i in range(5):
            yield i

let gen = create_generator()
for num in gen:
    print(num)  # 0, 1, 2, 3, 4
```

### yield 空参数包

```python
# yield 后跟空格表示空参数包
def countdown(n: int):
    return *:
        while n > 0:
            yield
            n -= 1
```

## 构建块的规则

### 语法规则

```python
# 构建块符号必须有空格前后
let x =:  # ✅ 正确
# let x=:  # ❌ 错误：缺少空格

# 构建块符号后必须换行
let x =:
    pass  # ✅ 正确

# let x =: pass  # ❌ 错误：必须换行
```

### early return 和 guard

```python
# 支持 early return
let result =:
    let x: int = get_value()
    if x < 0:
        return "negative"
    if x == 0:
        return "zero"
    "positive"

# 支持 guard 语句
let data =:
    let input = get_input()
    guard input else "no input"
    process(input)
```

## 构建块特性

| 特性 | 说明 |
|------|------|
| **变量构建块** | `=:` 创建闭包，自动赋值最后表达式 |
| **调用构建块** | `~:` 创建闭包，返回给调用者执行 |
| **生成器构建块** | `*:` 创建生成器闭包，返回迭代器 |
| **early return** | 支持在构建块内提前返回 |
| **guard** | 支持守卫语句 |
| **语法要求** | 符号前后必须有空格，后必须换行 |