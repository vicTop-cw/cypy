# 构建块语法

## 索引构建块 (^:)

### 基本语法

```python
# 索引构建块 ^: 获取容器中指定键元素的最后一个元素
# container ^: key → container[key][-1]
def get_last_score(scores: dict, player: str) -> int:
    result = scores ^:
        player
    return result
```

### 使用场景

```python
# 从列表中获取指定索引的最后一个元素
def get_last_item(items: list, key: str) -> int:
    result = items ^:
        key
    return result

# 在循环中使用索引构建块
def process_with_index(items: list, keys: list) -> list:
    results: list = []
    for key in keys:
        value = items ^:
            key
        results.append(value)
    return results
```

### 语法规则

```python
# ^: 符号后必须换行
result = container ^:
    key  # ✅ 正确：换行形式

# result = container ^: key  # ❌ 错误：必须换行
```

## 去括号语法 (~:)

### 基本语法

```python
# 去括号语法 ~: 简化函数调用的括号书写
# expr ~: block → lambda: expr(block)
def transform_list(data: list, func: callable) -> list:
    return [func(item) for item in data]

# 使用 ~: 语法
result = transform_list(data) ~:
    lambda x: x * 2
```

### 链式调用

```python
# ~: 支持链式调用
result = transform_list(data) ~:
    lambda x: x * 2
```

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
| **索引构建块** | `^:` 获取容器[key][-1]，取最后一个元素 |
| **去括号语法** | `~:` 简化函数调用括号书写 |
| **early return** | 支持在构建块内提前返回 |
| **guard** | 支持守卫语句 |
| **语法要求** | 符号前后必须有空格，后必须换行 |