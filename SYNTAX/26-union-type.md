# 联合类型

## 概述

联合类型（Union Type）允许一个变量或参数接受多种类型。使用 `|` 运算符定义联合类型。

## 语法

### 基本语法

```python
# 类型注解中的联合类型
let value: int | float = 42
let name: str | None = get_name()

# 函数参数和返回值
def process(input: str | int) -> str | None:
    if isinstance(input, str):
        return input.upper()
    return None
```

### 多个类型

```python
# 支持任意数量的类型
let result: int | float | str | bool = get_value()

# 常见模式
let maybe_list: list<int> | list<str> = get_items()
```

### 与类型守卫配合

```python
def handle(value: int | str) -> str:
    if isinstance(value, int):
        # 此处 value 自动收窄为 int
        return str(value * 2)
    else:
        # 此处 value 自动收窄为 str
        return value.upper()
```

## 代码生成

### 映射到 Cython

联合类型在 Cython 中降级为 `object` 类型，并添加注释说明：

```python
# Cypy 源码
let value: int | float = 42

# 生成的 Cython 代码
let value: object = 42  # union[int | float]
```

### 函数签名

```python
# Cypy 源码
def process(input: str | int) -> str | None:
    ...

# 生成的 Cython 代码
def process(input):
    # input: object  # union[str | int]
    # return: object  # union[str | None]
    ...
```

## 使用场景

### 1. 可选值

```python
let user_id: int | None = find_user(name)
if user_id is not None:
    print(f"User found: {user_id}")
```

### 2. 灵活参数

```python
def display(content: str | bytes) -> None:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    print(content)
```

### 3. 多态返回

```python
def parse_response(data: dict) -> str | int | float | list:
    if "error" in data:
        return data["error"]
    elif "count" in data:
        return int(data["count"])
    elif "score" in data:
        return float(data["score"])
    else:
        return list(data.items())
```

## 限制

### 当前限制

| 限制 | 说明 |
|------|------|
| 无运行时类型检查 | 联合类型降级为 `object`，无自动类型检查 |
| 无自动收窄 | 需要手动使用 `isinstance` 进行类型守卫 |
| 不可作为泛型约束 | 联合类型不能直接用于泛型参数约束 |
| 无判别联合 | 不支持带标签的判别联合（Tagged Union） |

### 未来计划

- [ ] 运行时类型检查支持
- [ ] 自动类型收窄（Type Narrowing）
- [ ] 判别联合（Tagged/Discriminated Union）
- [ ] 交叉类型（Intersection Type）

## 最佳实践

1. **优先使用具体类型**：只有在确实需要多类型支持时才使用联合类型
2. **配合类型守卫**：使用 `isinstance` 进行安全的类型收窄
3. **避免过多类型**：建议联合类型不超过 3-4 种类型
4. **提供文档说明**：使用注释说明每种类型的预期行为

```python
# Good: 清晰的联合类型
let result: int | None = compute_value()

# Bad: 过于复杂的联合类型
let value: int | float | str | bytes | list | dict | tuple | None = get_unknown()
```

## 与 Option 类型对比

| 特性 | 联合类型 | Option 类型 |
|------|----------|-------------|
| 语法 | `T | None` | `Option<T>` |
| 类型安全 | 低（降级为 object） | 中（有 Option 包装） |
| 模式匹配 | 需要手动检查 | 支持 `Some/None` 模式 |
| 代码生成 | 简单降级 | 需要包装/解包 |

## 示例

完整的使用示例：

```python
# 类型定义
type Number = int | float

# 函数定义
def add(a: Number, b: Number) -> Number:
    return a + b

# 使用
let x: Number = 42
let y: Number = 3.14
let result = add(x, y)  # 45.14

# 带 None 的联合
def find_user(user_id: int) -> str | None:
    users = ["Alice", "Bob"]
    if user_id < len(users):
        return users[user_id]
    return None

# 使用
let name = find_user(0)
if name is not None:
    print(f"Found: {name}")
```