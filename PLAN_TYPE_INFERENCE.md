# Cypy 类型推断系统增强计划

## 一、现状分析

### 1.1 当前类型检查器架构
当前的 `TypeChecker` 位于 [cypyc/analyzer/type_checker.py](file:///e:/IDEProjects/AI/Cypy/cypyc/analyzer/type_checker.py)，采用简单的访问者模式：
- 每个 AST 节点有对应的 `_visit_*` 方法
- 类型信息存储在 `type_map: Dict[str, Type]` 中
- 不支持类型变量、替换系统或统一算法

### 1.2 当前类型推断的限制
根据 [tests/test_type_inference.py](file:///e:/IDEProjects/AI/Cypy/tests/test_type_inference.py) 的测试覆盖，当前系统存在以下限制：

| 场景 | 当前行为 | 期望行为 |
|------|---------|---------|
| `let x = 42` | 推断为 `object` | 推断为 `int` |
| `let s = "hello"` | 推断为 `object` | 推断为 `str` |
| `let items = [1, 2, 3]` | 推断为 `object` | 推断为 `list[int]` |
| `def add(a: int, b: int): return a + b` | 返回 `object` | 返回 `int` |
| `if isinstance(x, int): x + 1` | `x` 仍为 `object` | `x` 窄化为 `int` |

### 1.3 技术选型决策
经过调研，选择 **TypeScript 风格的混合推断** 而非完整的 Hindley-Milner 系统，原因：
- 完整 HM 系统需要类型变量、替换、统一等复杂机制，是大规模重构
- 与 Cython 代码生成目标兼容性更好
- 用户能立即感受到改进效果

---

## 二、增强方案

### 2.1 阶段一：字面量类型推断（高优先级）

**目标**：从初始化值推断变量类型，而非默认 `object`

**修改文件**：`cypyc/analyzer/type_checker.py`

**实现要点**：

```python
# 修改 _visit_LetStmt 方法
def _visit_LetStmt(self, node: LetStmt) -> None:
    declared_type = self._get_type_from_node(node.type_annotation)
    if node.value:
        value_type = self._visit(node.value)
        if declared_type:
            # 有显式类型注解，使用声明的类型
            self.type_map[node.name] = declared_type
        elif value_type:
            # 无显式注解，从初始化值推断类型
            self.type_map[node.name] = value_type  # 原来默认 object，现在用 value_type
```

**支持的字面量类型**：
- `int` 字面量 → `Type("int")`
- `float` 字面量 → `Type("float")`
- `bool` 字面量 → `Type("bool")`
- `str` 字面量 → `Type("str")`
- `None` → `Type("None")`
- 列表字面量 → `Type("list", generic_params=[元素类型])`
- 元组字面量 → `Type("tuple", generic_params=[各元素类型])`

### 2.2 阶段二：函数返回类型推断

**目标**：从函数体的 return 语句推断返回类型

**修改文件**：`cypyc/analyzer/type_checker.py`

**实现要点**：

```python
# 修改 _visit_FuncDef 方法
def _visit_FuncDef(self, node: FuncDef) -> None:
    # ... 现有代码 ...
    
    # 收集所有 return 语句的类型
    return_types = []
    for stmt in node.body:
        if isinstance(stmt, ReturnStmt):
            ret_type = self._visit(stmt)
            if ret_type:
                return_types.append(ret_type)
    
    # 如果没有显式返回类型注解，推断返回类型
    if not return_type and return_types:
        # 找到最具体的公共类型
        inferred_return = self._find_common_type(return_types)
        self.current_function_return_type = inferred_return
        self.type_map[node.name] = inferred_return
```

**类型合并策略**：
- `int` 和 `int` → `int`
- `int` 和 `float` → `float`（向上转换）
- `int` 和 `str` → `object`（无法统一）

### 2.3 阶段三：泛型函数调用点推断增强

**目标**：从参数类型和返回值使用上下文推断泛型参数

**修改文件**：`cypyc/analyzer/type_checker.py`

**实现要点**：

```python
# 修改 _visit_Call 方法
def _visit_Call(self, node: Call) -> Optional[Type]:
    # ... 现有代码 ...
    
    # 增强：从赋值目标类型反推泛型参数
    # 如果调用结果被赋值给有类型注解的变量
    # 使用该类型信息帮助推断泛型参数
```

### 2.4 阶段四：条件表达式类型窄化

**目标**：在 `if isinstance(x, int)` 等条件分支中，将 `x` 的类型窄化

**修改文件**：`cypyc/analyzer/type_checker.py`

**实现要点**：

```python
# 新增方法
def _narrow_type(self, name: str, narrow_to: Type) -> None:
    """在当前作用域中将变量类型窄化"""
    # 保存旧类型以便退出作用域时恢复
    # 在条件块内使用窄化后的类型

# 修改 _visit_IfStmt 方法
def _visit_IfStmt(self, node: IfStmt) -> None:
    # 检测 isinstance 条件
    # 如果是 isinstance(x, Type)，在 then 分支中将 x 窄化为 Type
```

### 2.5 阶段五：容器字面量类型推断

**目标**：从容器字面量的元素推断泛型参数

**修改文件**：`cypyc/analyzer/type_checker.py`

**实现要点**：

```python
# 修改 _visit_Constant 方法
def _visit_Constant(self, node: Constant) -> Optional[Type]:
    value = node.value
    if isinstance(value, list):
        # 推断列表元素类型
        if value:
            element_types = [self._infer_literal_type(item) for item in value]
            common_type = self._find_common_type(element_types)
            return Type("list", generic_params=[common_type])
        else:
            return Type("list", generic_params=[Type("object")])
    elif isinstance(value, tuple):
        # 推断元组各元素类型
        element_types = [self._infer_literal_type(item) for item in value]
        return Type("tuple", generic_params=element_types)
```

---

## 三、实施计划

### 3.1 任务分解

| 任务 | 优先级 | 估计工作量 | 依赖 |
|------|--------|-----------|------|
| 阶段一：字面量类型推断 | P0 | 2天 | 无 |
| 阶段二：函数返回类型推断 | P0 | 2天 | 阶段一 |
| 阶段三：泛型调用点推断增强 | P1 | 3天 | 阶段一、二 |
| 阶段四：条件类型窄化 | P1 | 3天 | 阶段一 |
| 阶段五：容器字面量类型推断 | P1 | 2天 | 阶段一 |
| 测试用例覆盖 | P0 | 3天 | 所有阶段 |

### 3.2 里程碑

**里程碑 1**：基础类型推断可用
- `let x = 42` → `int`
- `let s = "hello"` → `str`
- 函数返回类型自动推断

**里程碑 2**：泛型和容器推断可用
- `let items = [1, 2, 3]` → `list[int]`
- 泛型函数调用自动推断类型参数

**里程碑 3**：类型窄化可用
- `if isinstance(x, int): x + 1` 在分支内正确推断

---

## 四、技术细节

### 4.1 类型数据结构增强

当前的 `Type` 类需要增强以支持更丰富的类型信息：

```python
class Type:
    def __init__(self, name: str, is_pointer: bool = False, is_ref: bool = False, 
                 generic_params: List['Type'] = None, nullable: bool = False):
        self.name = name
        self.is_pointer = is_pointer
        self.is_ref = is_ref
        self.generic_params = generic_params or []
        self.nullable = nullable  # 新增：是否可为 None
    
    # 新增方法
    def is_subtype_of(self, other: 'Type') -> bool:
        """检查是否是另一个类型的子类型"""
        # 实现子类型关系判断
```

### 4.2 类型合并算法

```python
def _find_common_type(self, types: List[Type]) -> Type:
    """从一组类型中找到最具体的公共类型"""
    if not types:
        return Type("object")
    
    # 数值类型向上转换：bool → int → float → double
    numeric_order = ['bool', 'int', 'float', 'double']
    numeric_types = {t for t in types if t.name in numeric_order}
    
    if numeric_types:
        indices = [numeric_order.index(t.name) for t in numeric_types]
        return Type(numeric_order[max(indices)])
    
    # 检查所有类型是否相同
    if all(t == types[0] for t in types):
        return types[0]
    
    # 无法统一，返回 object
    return Type("object")
```

### 4.3 字面量类型推断辅助函数

```python
def _infer_literal_type(self, value: Any) -> Type:
    """从字面量值推断类型"""
    if isinstance(value, int):
        return Type("int")
    elif isinstance(value, float):
        return Type("float")
    elif isinstance(value, bool):
        return Type("bool")
    elif isinstance(value, str):
        return Type("str")
    elif value is None:
        return Type("None")
    elif isinstance(value, list):
        if value:
            element_types = [self._infer_literal_type(item) for item in value]
            common_type = self._find_common_type(element_types)
            return Type("list", generic_params=[common_type])
        else:
            return Type("list", generic_params=[Type("object")])
    elif isinstance(value, tuple):
        element_types = [self._infer_literal_type(item) for item in value]
        return Type("tuple", generic_params=element_types)
    else:
        return Type("object")
```

---

## 五、测试计划

### 5.1 新增测试用例

| 测试类别 | 测试场景 | 预期结果 |
|---------|---------|---------|
| 字面量推断 | `let x = 42` | `x: int` |
| 字面量推断 | `let s = "hello"` | `s: str` |
| 字面量推断 | `let flag = true` | `flag: bool` |
| 函数返回推断 | `def add(a: int, b: int): return a + b` | 返回 `int` |
| 函数返回推断 | `def get_value(): return 42` | 返回 `int` |
| 容器推断 | `let items = [1, 2, 3]` | `items: list[int]` |
| 容器推断 | `let coords = (1, 2.0)` | `coords: tuple[int, float]` |
| 类型窄化 | `if isinstance(x, int): x + 1` | `x` 窄化为 `int` |
| 泛型推断 | `fn id[T](x: T) -> T: return x; id(42)` | 返回 `int` |

### 5.2 回归测试

确保修改不会破坏现有功能：
- 现有类型检查测试全部通过
- 模式匹配测试全部通过
- 提取器模式测试全部通过

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 类型推断过于激进导致错误 | 中等 | 高 | 添加配置选项控制推断严格程度 |
| 与 Python 动态特性冲突 | 低 | 高 | 保留 `@python` 装饰器跳过类型检查 |
| 泛型推断复杂场景失败 | 中等 | 中 | 提供显式类型注解作为 fallback |
| 性能影响 | 低 | 中 | 类型推断只在编译期执行 |

---

## 七、后续扩展方向

1. **Hindley-Milner 统一引擎**：作为独立模块实现，支持更复杂的多态类型推断
2. **Trait 约束求解器**：参考 Rust Chalk，实现基于逻辑的 trait 约束求解
3. **类型推导可视化**：提供类型推导过程的调试信息和可视化工具
4. **增量类型检查**：支持增量编译时的类型检查优化
