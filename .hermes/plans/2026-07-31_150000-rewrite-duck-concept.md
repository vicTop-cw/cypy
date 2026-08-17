# 重写 duck 关键字：借鉴 Nim concept 设计

## 目标

将 Cypy 的 `duck` 关键字从当前「类似 trait 的操作符列表」升级为真正的**结构约束系统**，参考 Nim 的 `concept` 设计理念：

- **trait** = 显式接口（需要 `impl` 实现）
- **duck** = 隐式结构约束（编译器自动判断类型是否满足约束）

核心差异：`duck` 约束的不是「方法列表」，而是「类型的结构行为」——如果一个类型能被当作约束要求的表达式使用，它就满足约束。

## 核心设计

### 语法规则

```
duck_name := 'duck' Identifier ('[' Identifier (',' Identifier)* ']')? ':' NEWLINE INDENT duck_body DEDENT
duck_body := duck_requirement*
duck_requirement :=
    # 1. 操作符约束（必须以操作符形式表达，区别于 trait 的方法列表）
    #    二元操作符:  left_name op right_name '->' type
    #    一元操作符:  op name '->' type
    Identifier op Identifier '->' type          # a < b -> bool
    op Identifier '->' type                     # -a -> Self

    # 2. 属性约束（类型必须具有该属性）
    Identifier ':' type                         # name: str

    # 3. 方法约束（类型必须具有该方法）
    Identifier '(' param_list? ')' '->' type   # len(self) -> int, add(self, x: T) -> None

    # 4. 引用约束（组合/继承其他 duck）
    Identifier ('[' type (',' type)* ']')?     # Comparable, Container[int]
```

### 关键设计点

1. **操作符约束必须用表达式语法**（`a < b -> bool`），这是与 trait 方法列表的根本区别
2. **支持 `Self` 返回类型**（表示约束类型本身，引用 Nim concept 的设计）
3. **引用约束可带泛型参数**（`Container[int]` 而非仅 `Container`）
4. **一元操作符支持**（`-a -> Self`）
5. **空 duck 可作为类型别名**（`duck NumLike: RealNumber`）

### 示例

```python
meta:
    # 基础可比较约束
    duck Comparable:
        a < b -> bool
        a > b -> bool
        a == b -> bool

    # 数值约束（Self 表示约束类型本身）
    duck Numeric:
        a + b -> Self
        a - b -> Self
        a * b -> Self
        -a -> Self

    # 泛型约束
    duck Container[T]:
        __len__(self) -> int
        __contains__(self, item: T) -> bool
        add(self, item: T) -> None

    # 组合约束（引用其他 duck）
    duck Sortable[T]:
        Comparable          # T 必须可比较
        Container[T]        # 必须是 T 的容器

    # 空 duck（仅作类型别名）
    duck Num:
        Numeric
        Comparable
```

### 类型检查使用

```python
# 泛型参数约束
def sort[T: Comparable](items: list[T]) -> list[T]:
    ...

def process[T: Container[int]](container: T) -> None:
    ...

# 函数调用时编译器自动检查类型是否满足约束
nums: list[int] = [3, 1, 2]
sorted_nums = sort(nums)  # int 满足 Comparable ✓
```

## AST 结构升级

### DuckRequirement 扩展

```python
class DuckRequirement(ASTNode):
    """单个 duck 约束项"""
    def __init__(self, kind: str, name: str, params: List[str],
                 return_type: Optional[str] = None,
                 generic_args: List[str] = None,    # NEW: 引用约束的泛型参数
                 is_unary: bool = False,            # NEW: 是否为一元操作符
                 line: int = 0, col: int = 0):
        super().__init__("DuckRequirement", line, col)
        self.kind = kind            # "operator" | "attribute" | "method" | "reference"
        self.name = name
        self.params = params
        self.return_type = return_type
        self.generic_args = generic_args or []
        self.is_unary = is_unary
```

### DuckDef 扩展

```python
class DuckDef(ASTNode):
    def __init__(self, name: str, type_params: List[str],
                 requirements: List[DuckRequirement],
                 line: int = 0, col: int = 0):
        super().__init__("DuckDef", line, col)
        self.name = name
        self.type_params = type_params
        self.requirements = requirements
```

## 重写步骤

### Step 1: 文档重写 (`SYNTAX/27-constraints.md`)

- 重写 duck 关键字的设计理念，强调与 trait 的区别
- 补充完整语法定义（操作符、属性、方法、引用、泛型）
- 添加 `Self` 返回类型说明
- 添加类型检查使用示例
- 修正不规范的示例（如当前文档中的误导用法）

### Step 2: AST 扩展 (`cypyc/parser/parser.py`)

- 扩展 `DuckRequirement` 类：添加 `generic_args`、`is_unary` 字段
- 更新 `_parse_duck_requirement`：
  - 支持一元操作符（`-a -> Self`）
  - 支持引用约束的泛型参数（`Container[T]`）
  - 支持 `Self` 返回类型
- 更新 `_parse_duck_def`：确保正确的解析流程

### Step 3: 代码生成增强 (`cypyc/codegen/cython_generator.py`)

- 增强 `_visit_DuckDef`：
  - 正确生成约束注册表（包含泛型参数信息）
  - 对 `Self` 返回类型进行标记
  - 生成便于类型检查的约束元数据
- 注册 duck 约束到全局注册表 `_duck_registry`

### Step 4: 分析器完善

**`scope_analyzer.py`**：
- `_visit_DuckDef`：注册 duck 名称到作用域，标记为 `"duck"` 类型

**`type_checker.py`**：
- 实现真正的结构约束检查逻辑：
  - 操作符检查：验证类型是否支持对应操作符的重载
  - 属性检查：验证类型是否具有指定属性
  - 方法检查：验证类型是否具有指定方法签名
  - 引用检查：递归检查引用的 duck 约束
  - `Self` 解析：将 `Self` 替换为当前约束类型
- 在泛型实例化时调用约束检查

**`bridge_generator.py`**：
- 添加 DuckDef 节点的桥接代码生成支持

### Step 5: 测试套件重写

**`examples/test_duck.cypy`**：
- 完整的语法示例文件

**`tests/test_duck.py`**：
- Lexer 测试：DUCK token 识别
- Parser 测试：
  - 简单 duck 定义
  - 操作符约束（二元/一元）
  - 属性约束
  - 方法约束
  - 泛型约束
  - 组合/引用约束
  - Self 返回类型
  - 泛型参数绑定的引用约束
- Codegen 测试：代码生成正确性
- Integration 测试：端到端编译

### Step 6: 验证

- 运行现有测试套件，确保无回归
- 运行新 duck 测试套件
- 手动使用示例代码进行编译测试

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `SYNTAX/27-constraints.md` | 重写 | 完整重写 duck 设计文档 |
| `cypyc/parser/parser.py` | 修改 | 扩展 AST + 解析逻辑 |
| `cypyc/codegen/cython_generator.py` | 修改 | 增强代码生成 |
| `cypyc/analyzer/scope_analyzer.py` | 修改 | 完善作用域注册 |
| `cypyc/analyzer/type_checker.py` | 修改 | 实现约束检查逻辑 |
| `cypyc/bridge/bridge_generator.py` | 修改 | 添加桥接支持 |
| `examples/test_duck.cypy` | 重写 | 完整示例 |
| `tests/test_duck.py` | 重写 | 完整测试套件 |

## 与 trait 的区别

| 维度 | trait | duck |
|------|-------|------|
| 定义方式 | 方法/属性签名 | 表达式约束（`a < b -> bool`） |
| 实现方式 | 显式 `impl` | 隐式自动满足 |
| 操作符 | 需显式声明 `__lt__` 等 | 直接写操作符表达式 |
| 检查方式 | 编译期显式检查 | 编译期结构匹配 |
| 运行时开销 | 无 | 无 |
| 适用场景 | API 契约、运行时多态 | 泛型约束、数值/集合运算 |

## 开放问题

1. **运行时反射**：是否需要在运行时提供 `is_duck` 类型判断？当前只在编译期检查。
2. **交叉 duck 引用**：A duck 引用 B duck，B 又引用 A，需要循环依赖检测（类似 trait 的循环检测）。
3. **Self 的精确语义**：当 duck 约束被用于泛型参数时，`Self` 应绑定到具体实例类型，需要在类型检查时正确替换。
4. **性能**：大量 duck 约束的类型检查可能较慢，需要考虑缓存机制。

## 风险与权衡

- **解析复杂度**：支持更多约束形式会增加 parser 的复杂度，但可通过约束上下文限定（仅在 `meta` 块中）来控制
- **类型检查性能**：结构约束检查比显式 trait 检查更复杂，但可通过增量检查和缓存优化
- **学习曲线**：duck 的表达式约束语法对用户可能有一定学习成本，但 Nim concept 的实践已证明其直观性