# 鸭子类型约束系统（Duck Typing Constraints）

## 概述

Cypy 提供了基于 `duck` 关键字的鸭子类型约束系统，参考 Nim 语言的 `concept` 概念设计。与传统的 `trait`（需要显式 `impl` 实现）不同，`duck` 约束通过**表达式约束**实现隐式的类型检查——如果一个类型"走起路像鸭子，叫起来像鸭子"，那它就是鸭子。

## 核心特性

1. **操作符约束**：定义类型必须支持的操作符（如 `<`、`+`、`*`）
2. **属性约束**：定义类型必须具有的属性
3. **方法约束**：定义类型必须支持的方法
4. **组合约束**：支持约束的继承与组合
5. **泛型约束**：支持类型参数化的约束

---

## 语法结构

所有 `duck` 约束定义在 `meta:` 块中：

```python
meta:
    duck Comparable:
        a < b -> bool
        a > b -> bool
        a == b -> bool
```

---

## 1. 操作符约束

### 语法

```python
duck 名称:
    左操作数 操作符 右操作数 -> 返回类型
```

### 支持的操作符

| 类别 | 操作符 |
|------|--------|
| 比较 | `<`, `>`, `<=`, `>=`, `==`, `!=` |
| 算术 | `+`, `-`, `*`, `/` |
| 其他 | `<=>` (三路比较) |

### 示例

```python
meta:
    # 定义可比较约束
    duck Comparable:
        a < b -> bool
        a > b -> bool
        a <= b -> bool
        a >= b -> bool
        a == b -> bool
        a != b -> bool

    # 定义数值运算约束
    duck Numeric:
        a + b -> Self      # 加法
        a - b -> Self      # 减法
        a * b -> Self      # 乘法
        a / b -> Self      # 除法
        -a -> Self         # 负号运算

    # 定义有序约束（继承 Comparable）
    duck Ordered:
        Comparable
        a <=> b -> int     # 三路比较 (-1, 0, 1)
```

### 使用约束

```python
# 函数参数约束
def sort<T: Comparable>(items: list<T>) -> list<T>:
    """T 必须支持比较操作符"""
    # 编译器检查 T 是否满足 Comparable 约束
    # 即 T 必须支持 <, >, <=, >=, ==, !=
    ...

def max<T: Ordered>(a: T, b: T) -> T:
    """T 必须支持有序操作"""
    return a if a > b else b
```

---

## 2. 属性约束

### 语法

```python
duck 名称:
    属性名: 类型
```

### 示例

```python
meta:
    # 定义命名约束
    duck Named:
        name: str          # 必须有 name 属性

    # 定义大小约束
    duck Sized:
        size: int          # 必须有 size 属性

    # 定义有标识符约束
    duck Identified:
        id: int
        name: str
```

### 使用约束

```python
def display<T: Named>(obj: T) -> None:
    """显示任何有 name 属性的对象"""
    print(obj.name)

def resize<T: Sized>(obj: T, new_size: int) -> None:
    """调整有 size 属性的对象"""
    obj.size = new_size
```

---

## 3. 方法约束

### 语法

```python
duck 名称:
    方法名(参数列表) -> 返回类型
```

### 示例

```python
meta:
    # 定义可迭代约束
    duck Iterable:
        __iter__(self) -> Iterator

    # 定义容器约束（泛型）
    duck Container<T>:
        add(self, item: T) -> None
        remove(self, item: T) -> bool
        __contains__(self, item: T) -> bool
        __len__(self) -> int

    # 定义索引约束
    duck Indexable<T>:
        __getitem__(self, index: int) -> T
        __setitem__(self, index: int, value: T) -> None
```

### 使用约束

```python
def process<T: Container<int>>(container: T) -> None:
    """处理任何存储整数的容器"""
    container.add(42)
    if 42 in container:
        container.remove(42)

def get_first<T: Indexable<str>>(obj: T) -> str:
    """获取第一个字符串元素"""
    return obj[0]
```

---

## 4. 组合约束

### 语法

通过引用其他约束实现组合：

```python
duck 名称:
    其他约束名         # 继承/引用
    额外约束项
```

### 示例

```python
meta:
    # 基础约束
    duck Comparable:
        a < b -> bool
        a > b -> bool

    duck Container<T>:
        add(self, item: T) -> None
        __len__(self) -> int

    # 组合约束
    duck Sequence<T>:
        Iterable           # 继承 Iterable 约束
        Container<T>       # 继承 Container<T> 约束
        get(self, index: int) -> T
        set(self, index: int, value: T) -> None

    # 组合多个约束
    duck SortableContainer<T>:
        Comparable         # 元素可比较
        Container<T>       # 是一个容器
```

### 约束检查逻辑

```python
# 编译器检查类型是否满足 SortableContainer<T>:
# 1. 满足 Comparable: 元素 T 必须支持 <, >
# 2. 满足 Container<T>: 类型必须支持 add, __len__
# 3. 额外: 类型必须支持 get, set

# list<int> 满足 SortableContainer<int> 吗？
# - int 满足 Comparable ✓ (int 支持 <, >)
# - list 满足 Container<int> ✓ (list 支持 append, len)
# - list 支持 get/set ✓ (list 支持索引访问)
# 结论: list<int> 满足 SortableContainer<int> ✓
```

---

## 5. 完整示例

### 集合操作库

```python
# collections.cypy
meta:
    # 可比较约束
    duck Comparable:
        a < b -> bool
        a > b -> bool
        a == b -> bool

    # 容器约束
    duck Container<T>:
        add(self, item: T) -> None
        remove(self, item: T) -> bool
        __contains__(self, item: T) -> bool
        __len__(self) -> int

    # 可排序容器
    duck SortableContainer<T>:
        Comparable
        Container<T>

# 使用约束
def sort<T: SortableContainer<U>, U: Comparable>(container: T) -> T:
    """对可排序容器进行排序"""
    items = list(container)
    # 使用 Comparable 约束的操作符
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] > items[j]:
                items[i], items[j] = items[j], items[i]
    return container

def find_max<T: Container<U>, U: Comparable>(container: T) -> U:
    """查找容器中的最大值"""
    items = list(container)
    if not items:
        raise ValueError("容器为空")
    max_val = items[0]
    for item in items[1:]:
        if item > max_val:  # 使用 Comparable 约束
            max_val = item
    return max_val
```

### 数学运算库

```python
# math_ops.cypy
meta:
    duck Numeric:
        a + b -> Self
        a - b -> Self
        a * b -> Self
        a / b -> Self
        -a -> Self

    duck Real:
        Numeric
        a < b -> bool
        a > b -> bool

# 使用约束
def distance<T: Real>(a: T, b: T) -> T:
    """计算两点间的距离"""
    diff = a - b
    return diff * diff  # 使用 Numeric 约束的 * 操作

def clamp<T: Real>(value: T, min_val: T, max_val: T) -> T:
    """将值限制在范围内"""
    if value < min_val:   # 使用 Real 约束的 < 操作
        return min_val
    elif value > max_val:  # 使用 Real 约束的 > 操作
        return max_val
    return value
```

---

## 与 trait 的核心区别

| 特性 | `trait` | `duck` |
|------|---------|--------|
| 定义方式 | 方法签名 | 表达式约束 |
| 检查方式 | 显式 `impl` | 隐式检查 |
| 操作符支持 | 需要显式定义 | 直接支持 `a < b` |
| 属性约束 | 需要 getter | 直接支持 `name: str` |
| 灵活性 | 较低 | 高（鸭子类型） |
| 组合能力 | 继承 | 表达式组合 |
| 类型安全 | 高 | 高（编译期检查） |

### 选择建议

- 使用 `trait` 当：
  - 需要显式的接口契约
  - 需要控制哪些类型实现接口
  - 需要运行时类型标识

- 使用 `duck` 当：
  - 需要灵活的鸭子类型约束
  - 约束操作符或属性
  - 希望自动推导类型满足约束

---

## 与 type 别名的区别

| 特性 | `type` 别名 | `duck` 约束 |
|------|------------|------------|
| 用途 | 为类型创建新名称 | 定义类型必须支持的操作 |
| 示例 | `type Num = int \| float` | `duck Comparable: a < b -> bool` |
| 检查方式 | 编译期类型替换 | 编译期操作检查 |
| 运行时 | 无运行时开销 | 无运行时开销 |

---

## 代码生成

### 生成策略

当前实现采用**注释 + 运行时注册表**策略：

```python
# Cypy 源码
meta:
    duck Comparable:
        a < b -> bool
        a > b -> bool

    duck Container<T>:
        add(self, item: T) -> None
        len(self) -> int

# 生成的 Cython 代码
# === Meta Block ===
# Duck constraint: Comparable
#   Operator: <(a, b) -> bool
#   Operator: >(a, b) -> bool
_duck_registry['Comparable'] = {'type_params': [], 'requirements': [...]}

# Duck constraint: Container
#   Generic: [T]
#   Method: add(self, item) -> None
#   Method: len(self) -> int
_duck_registry['Container'] = {'type_params': ['T'], 'requirements': [...]}
```

---

## 最佳实践

### 1. 优先使用操作符约束

```python
# 好的做法：使用操作符约束
duck Comparable:
    a < b -> bool
    a > b -> bool

# 避免：只定义方法
duck Comparable:
    less_than(self, other: Self) -> bool  # 不够直观
```

### 2. 约束命名清晰

```python
# 好的命名
duck Comparable:     # 可比较
duck Container<T>:   # 容器
duck Iterable:       # 可迭代

# 避免模糊命名
duck C1:             # 不清楚用途
duck Thing:          # 太泛化
```

### 3. 合理使用组合

```python
# 好的组合：分层设计
duck Comparable:
    a < b -> bool
    a > b -> bool

duck Container<T>:
    add(self, item: T) -> None
    remove(self, item: T) -> bool

duck SortableContainer<T>:
    Comparable         # 元素可比较
    Container<T>       # 是一个容器

# 避免：过度耦合
duck SortableContainer<T>:
    a < b -> bool      # 直接重复定义
    a > b -> bool
    add(self, item: T) -> None
    remove(self, item: T) -> bool
```

### 4. 约束粒度适当

```python
# 合适的粒度
duck Sized:
    size: int

duck Comparable:
    a < b -> bool
    a > b -> bool

# 太细：每个操作一个约束
duck LessThan:
    a < b -> bool

duck GreaterThan:
    a > b -> bool

# 太粗：一个约束包含所有
duck Everything:
    a < b -> bool
    a > b -> bool
    a + b -> Self
    a - b -> Self
    ...
```

---

## 未来方向

| 功能 | 状态 | 说明 |
|------|------|------|
| 运行时鸭子类型检查 | 规划中 | 在函数入口插入约束检查代码 |
| 自动约束推导 | 规划中 | 根据函数体自动推导约束需求 |
| 约束优化 | 规划中 | 消除冗余约束检查 |
| IDE 支持 | 规划中 | 基于约束的代码补全和错误提示 |
| 约束组合语法 | 规划中 | 支持 `A & B` 形式的约束组合 |
