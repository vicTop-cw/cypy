# cypyc Compilation Bugs — Cross-Library Tracker

> Bugs discovered while porting Python libraries to Cypy.
> Each bug includes a minimal reproducible `.cypy` snippet.

---

## BUG-001: Docstrings in struct body crash parser ❌ FIXED
**Severity:** High  
**Found in:** Vanna  
**Error:** `Expected IDENTIFIER, got STRING at N:M`

```cypy
struct Foo:
    """This is a docstring"""
    x: int
```

**Fix:** Skip `STRING` tokens in struct/trait body parsing loop.  
**File:** `cypyc/parser/parser.py` — `_parse_struct_def()`

---

## BUG-002: @staticmethod decorator not supported in structs ❌ FIXED
**Severity:** High  
**Found in:** Vanna  
**Error:** `Expected IDENTIFIER, got AT at N:M`

```cypy
struct MathUtil:
    @staticmethod
    def add(a: int, b: int) -> int:
        return a + b
```

**Fix:** Handle `AT` tokens in struct body, parse decorators before `def`.  
**File:** `cypyc/parser/parser.py` — `_parse_struct_def()`

---

## BUG-003: Multi-line function signatures rejected ❌ FIXED
**Severity:** Medium  
**Found in:** Vanna, beartype  
**Error:** `Invalid indentation level N at line M. Expected one of [...]`

```cypy
def create_user(
    name: str,
    email: str,
) -> str:
    return name
```

**Root cause:** Lexer emitted INDENT/DEDENT inside parentheses; parser didn't skip NEWLINEs in param list.  
**Fix:** Added `_paren_depth` tracking to lexer (skip indent checks inside `()`/`[]`/`{}`); added NEWLINE skipping in `_parse_params()` + RPAREN check at loop top.  
**Files:** `cypyc/parser/lexer.py`, `cypyc/parser/parser.py`

---

## BUG-004: `guard ... else raise` not supported ❌ FIXED
**Severity:** Medium  
**Found in:** Vanna, beartype  
**Error:** `Unexpected token RAISE`

```cypy
def divide(a: float, b: float) -> float:
    guard b != 0.0 else raise ValueError("Division by zero")
    return a / b
```

**Fix:** Added `RAISE` handling to `_parse_guard_stmt()` and `_generate_guard_else_block()`.  
**Files:** `cypyc/parser/parser.py`, `cypyc/codegen/cython_generator.py`

---

## BUG-005: Relative imports not supported ❌ FIXED
**Severity:** Medium  
**Found in:** Vanna (any package-style module)  
**Error:** `Expected IDENTIFIER, got DOT at N:M`

```cypy
from .module import Foo
from ..core import Bar
```

**Fix:** Modified `_parse_from_import()` to consume leading dots for relative import paths.  
**File:** `cypyc/parser/parser.py`

---

## BUG-006: `id()` built-in not available ❌ FIXED
**Severity:** Low  
**Found in:** Vanna  
**Error:** `Undefined name 'id'`

```cypy
let addr: int = id(some_obj)
```

**Fix:** Added `id` to both `scope_analyzer._register_builtins()` and `type_checker.builtin_functions`. Also fixed `_builtin_names` reset order bug. Added Cython codegen: `id(x)` → `<size_t><void*>x`.  
**Files:** `cypyc/analyzer/scope_analyzer.py`, `cypyc/analyzer/type_checker.py`, `cypyc/codegen/cython_generator.py`

---

## BUG-007: `type` as return annotation rejected ❌ FIXED
**Severity:** Low  
**Found in:** Vanna (returning a type from a method)  
**Error:** `Return type mismatch: expected type, got X`

```cypy
struct Foo:
    def get_type(self) -> type:
        return Foo
```

**Fix:** Allow `type` as valid return type in type checker.  
**File:** `cypyc/analyzer/type_checker.py`

---

## BUG-008: `self.field: type = value` in struct methods ❌ FIXED
**Severity:** Low  
**Found in:** Vanna, beartype  
**Error:** Parser tries to parse as field definition, fails

```cypy
struct Counter:
    _count: int
    def increment(self) -> None:
        self._count: int = self._count + 1
```

**Fix:** In `_parse_expr_stmt()`, handle annotated attribute assignment (`Attribute : type = expr`).  
**File:** `cypyc/parser/parser.py`

---

## BUG-009: `_builtin_names` reset after `_register_builtins()` ❌ FIXED
**Severity:** High  
**Found in:** beartype  
**Description:** `self._builtin_names: set = set()` was placed AFTER `_register_builtins()` call in `ScopeAnalyzer.__init__`, overwriting the populated set with empty set.

**Fix:** Move `_builtin_names` initialization before `_register_builtins()`.  
**File:** `cypyc/analyzer/scope_analyzer.py`

---

## BUG-010: `not isinstance()` inside `and` expressions ✅ FIXED
**Severity:** Medium  
**Found in:** beartype  
**Error:** `Unexpected token NOT at N:M`

```cypy
if isinstance(obj, int) and not isinstance(obj, bool):
    pass
```

**Root cause (corrected):** Not in `_parse_comparison`. The logical `and` keyword and the `&&` operator both map to `TokenType.AND`, and `_parse_bitwise_and()` re-used `TokenType.AND` as its loop condition — so it greedily consumed the **logical** `and` as a bitwise-`&` operator (which sits at a lower precedence than `_parse_and_expr`). After `a and`, the right operand `not b` was then parsed as a shift/primary expression, hitting `not` and failing. Worse, `a and isinstance(...)` "passed" only because the call parsed as `a & isinstance(...)` (semantically wrong, no error).  
**Fix:** `_parse_bitwise_and()` now matches the single `&` token (`TokenType.DEREF`), leaving `and`/`&&` exclusively to the logical `_parse_and_expr()`. Also normalized `&&`/`||` codegen to `and`/`or` (see BUG-021).  
**Files:** `cypyc/parser/parser.py` — `_parse_bitwise_and()`; `cypyc/codegen/cython_generator.py` — `_visit_BinOp()`


---

## BUG-011: `_expect(TokenType.RPAREN)` fails with trailing comma ✅ FIXED
**Severity:** Low  
**Found in:** beartype (multi-line signatures with trailing comma)

```cypy
def foo(
    a: int,
    b: str,
) -> None:  # trailing comma before RPAREN
    pass
```

**Note:** Parser now handles this (fixed as part of BUG-003), but only after adding RPAREN check at top of inner while loop.  
**Status:** Fixed as part of BUG-003.

---

## Summary

| Bug | Severity | Status | Library |
|-----|----------|--------|---------|
| BUG-001 | High | ✅ Fixed | Vanna |
| BUG-002 | High | ✅ Fixed | Vanna |
| BUG-003 | Medium | ✅ Fixed | Vanna, beartype |
| BUG-004 | Medium | ✅ Fixed | Vanna |
| BUG-005 | Medium | ✅ Fixed | Vanna |
| BUG-006 | Low | ✅ Fixed | Vanna |
| BUG-007 | Low | ✅ Fixed | Vanna |
| BUG-008 | Low | ✅ Fixed | Vanna |
| BUG-009 | High | ✅ Fixed | beartype |
| BUG-010 | Medium | ✅ Fixed | beartype |
| BUG-011 | Low | ✅ Fixed | beartype |
| BUG-019 | High | ✅ Fixed | tenacity |
| BUG-020 | High | ✅ Fixed | tenacity |
| BUG-021 | Medium | ✅ Fixed | tenacity |
| BUG-022 | High | ✅ Fixed | sqlalchemy_core |
| BUG-023 | High | ✅ Fixed | sqlalchemy_core |
| BUG-024 | High | ✅ Fixed | tenacity, sqlalchemy_core |

## BUG-012: NEWLINEs inside parens break expression parsing ❌ FIXED
**Severity:** High
**Found in:** pydantic (fields, validation, models)
**Error:** `Unexpected token NEWLINE at N:M`

```cypy
def test() -> int:
    let x: int = foo(
        a=1,
        b=2,
    )
    return x
```

**Root cause:** Lexer emitted NEWLINE tokens inside `()` even though INDENT/DEDENT were suppressed. Parser's expression parser hit NEWLINE as statement terminator.
**Fix:** Lexer now fully suppresses NEWLINE tokens when `_paren_depth > 0`. Added RPAREN break-check at top of call-args while-loop.
**Files:** `cypyc/parser/lexer.py`, `cypyc/parser/parser.py`

---

## BUG-013: `var` at module level not supported ❌ FIXED (workaround)
**Severity:** Low
**Found in:** pydantic (registry, validation)
**Error:** `Undefined name 'var'`

```cypy
var REGISTRY: dict<str, object> = {}
```

**Root cause:** `var` keyword is only supported inside function scope, not at module level.
**Workaround:** Use `let` with a mutable struct wrapper for module-level state.

---

## BUG-014: `class Foo<T>:` generic params only on struct/trait ❌ FIXED (workaround)
**Severity:** Medium
**Found in:** pydantic (model_faithful, examples_faithful)
**Error:** `Expected COLON, got LT at N:M`

```cypy
class Model<T>:
    ...
```

**Root cause:** `_parse_struct_def` and `_parse_trait_def` handle `<T>` generics, but `_parse_class_def` does not.
**Workaround:** Use `struct` with generic params instead of `class`.

---

## BUG-015: `struct Foo(Base):` inheritance not supported ❌ FIXED (workaround)
**Severity:** Medium
**Found in:** pydantic (models)
**Error:** `Expected COLON, got LPAREN at N:M`

```cypy
struct Address(BaseModel):
    ...
```

**Root cause:** Struct definitions do not support parenthesized base class inheritance.
**Workaround:** Use composition (`_base: object`) instead of inheritance.

---

## BUG-016: `**dict` keyword unpacking in function calls not supported ❌ FIXED (workaround)
**Severity:** Medium
**Found in:** pydantic (base_model, models)
**Error:** `Unexpected token POW at N:M`

```cypy
return BaseModel(**data)
```

**Root cause:** The `**` in function calls is keyword unpacking (like `**kwargs`), but the parser treats it as the POW operator.
**Workaround:** Replace `Foo(**data)` with explicit field-by-field construction.

---

## BUG-017: `_expect_indent` flag not reset inside parens ❌ FIXED
**Severity:** Medium
**Found in:** pydantic (examples_faithful build-block test)
**Error:** `Expected increased indentation at line N. Expected 4, got 0`

```cypy
outer(inner ~:
    process(data)
)
```

**Root cause:** `~:` sets `_expect_indent=True` in lexer, but inside parens INDENT is never generated, so the flag is never reset. When `)` exits parens, the flag is still True and the next line fails the indent check.
**Fix:** Reset `_expect_indent=False` when skipping indentation inside parens.
**File:** `cypyc/parser/lexer.py`

---

## BUG-018: `_parse_build_block` assumes INDENT always exists ❌ FIXED
**Severity:** Medium
**Found in:** same scenario as BUG-017
**Error:** `Expected INDENT, got IDENTIFIER at N:M`

**Root cause:** `_parse_build_block` always calls `_parse_block()` which requires INDENT. Inside parens there are no INDENT tokens.
**Fix:** Check if next token is INDENT; if not, parse as single-expression block.
**File:** `cypyc/parser/parser.py`

---

## Known Pre-existing Issues (not introduced by this work)

均已于本轮核实为**已解决**（不需任何排除的全量套件 `python -m pytest tests/` 一次性 **1466 passed**）：

- **test_is_not_regression.py** — ~~挂起于 `compile_and_import`~~ ✅ 不再挂起，3 个测试（含端到端 `compile_and_import`）在全量套件中通过。历史挂起根因为共享 `output/` 目录下的 `struct.pyd` 遮蔽 stdlib `struct`（`sys.path.insert(0, output/)`），当前导入时序下不再触发。
- **test_hot_reload.py** — ~~因缺少 watchdog 被跳过~~ ✅ 本环境 watchdog 可用，16 个测试实际运行并通过（非跳过）。

---

## BUG-019: Attribute assignment `obj.attr = value` drops RHS ✅ FIXED
**Severity:** High  
**Found in:** tenacity (复刻压测)  
**Error:** `o.y = 5` / `self.x = v` 被解析为表达式语句（ExprStmt），赋值右侧整个丢失，生成的 Cython 为裸 `o.y` / `self.x`（无效、字段不更新）。`Name` 目标的赋值（`a = a + 1`）正常，故此前测试未覆盖而潜伏。

```cypy
struct Foo:
    x: int
    def set_x(self, v: int):
        self.x = v          # 生成裸 self.x，右侧 v 丢失
def f(o: object) -> int:
    o.y = 5                 # 生成裸 o.y
    return 1
```

**Root cause:** `_parse_expr_stmt()` 把 `return Assign(...)` 写在了 `if self._is_destructure_target(value):` 块**内部**。`_is_destructure_target()` 对 `Name` 返回 True（因此 `a = a+1` 正常），但对 `Attribute`/`Subscript` 返回 False —— 于是属性/下标赋值跳过该块、落到函数末尾的 `return ExprStmt(value)`，丢失右侧。  
**Fix:** 把默认 `return Assign(value, right_value)` 移到解构块**之外**（构建块 `~:`/`*:`/`^:` 各自提前 return，其余情况统一返回 Assign）。  
**File:** `cypyc/parser/parser.py` — `_parse_expr_stmt()`

---

## BUG-020: Struct with explicit `__init__` emits duplicate constructor ✅ FIXED
**Severity:** High  
**Found in:** tenacity (复刻压测)  
**Error:** 当结构体显式定义 `__init__` 且参数少于字段总数时，codegen 同时生成「全参自动构造器」与用户版 `__init__`，后者（覆盖前者）因参数更少导致字段不赋值。

```cypy
struct Attempt:
    number: int
    has_exception: bool
    def __init__(self, number: int):
        self.number = number
        self.has_exception = False
# 生成两个 def __init__，Cython 以后定义者为准 → Attempt(number=5) 实际不赋值
```

**Root cause:** `_visit_StructDef()` 无条件为每个 struct 生成全参 `__init__`，再额外发出用户方法（含用户 `__init__`），造成重复定义。  
**Fix:** 仅当用户未显式定义 `__init__` 时才生成自动全参构造器。  
**File:** `cypyc/codegen/cython_generator.py` — `_visit_StructDef()`

---

## BUG-021: `&&` / `||` codegen emits invalid Cython ✅ FIXED
**Severity:** Medium  
**Found in:** tenacity (复刻压测) + BUG-010 修复后暴露  
**Error:** `a && b` / `a || b` 原样输出为 `a && b` / `a || b`，而 Cython/Python 不支持 `&&`/`||` 运算符，生成非法代码。

```cypy
def f(a: bool, b: bool) -> bool:
    return a && b     # 生成非法：a && b
```

**Root cause:** `_visit_BinOp()` 直接用 `node.op` 原样输出；`&&`/`||` 未被归一化为 `and`/`or`。  
**Fix:** 在 `_visit_BinOp()` 中将 `&&` → `and`、`||` → `or`（与逻辑 `and`/`or` 关键字统一）。  
**File:** `cypyc/codegen/cython_generator.py` — `_visit_BinOp()`

---

## BUG-022: Function/method default argument values dropped in codegen ✅ FIXED
**Severity:** High  
**Found in:** sqlalchemy_core (复刻压测)  
**Error:** `Column("id")` 报 `TypeError: __init__() takes exactly 3 positional arguments (1 given)` —— struct `__init__`/函数的默认参数值（如 `table: str = ""`）被生成器丢弃，形同必填。

```cypy
struct Column:
    name: str
    table_name: str
    def __init__(self, name: str, table: str = ""):
        self.name = name
        self.table_name = table
# 生成 def __init__(self, name, table_name):  —— 默认值 = "" 丢失
```

**Root cause:** 实际被调用的签名生成函数 `_generate_param_strings()`（非 `_generate_params`）在拼接参数时只输出了 `name` 与类型，**从不追加 `= <default_value>`**。`Param.default_value` 在 parser 阶段已正确存储，但 codegen 没使用。  
**Fix:** 在 `_generate_param_strings()` 中，若 `param.default_value is not None`，将 `param_str` 改写为 `f"{param_str}={self._expr_to_str(param.default_value)}"`。对所有函数/方法/struct `__init__` 生效。  
**File:** `cypyc/codegen/cython_generator.py` — `_generate_param_strings()`

---

## BUG-023: Trait wrapper does not forward operator overloads / isinstance ✅ FIXED
**Severity:** High  
**Found in:** sqlalchemy_core (复刻压测)  
**Error（a）运算符转发：** `(col == 5) & (col2 > 18)` 报 `TypeError: unsupported operand type(s) for &: '_BinaryExpression' and '_BinaryExpression'`。当运算符方法返回 `trait` 类型（如 `ClauseElement`）时，codegen 返回的是 **trait 包装器**（`_ClauseElement__BinaryExpression`），而包装器类**未定义 `__and__` 等双下方法**，运算符转发失败。  
**Error（b）isinstance：** `_compile_operand` 中 `isinstance(o, ClauseElement)` 对**具体 struct 实例**返回 `False`。原因：Cypy 的 trait 通过独立的**包装器类**实现（具体 struct 并非 trait 的子类），故运行时 `isinstance(具体实例, Trait)` 恒假。

```cypy
trait ClauseElement:
    def compile(self) -> str
struct Column:           # 用 impl ClauseElement for Column: pass 注册
    def __eq__(self, other) -> ClauseElement:   # 返回 trait 类型
        return _BinaryExpression(self, "=", other)
# (col == 5) 得到 trait 包装器；对其做 & 失败
```

**Workaround（历史）：** 运算符方法返回**具体类型**（`_BinaryExpression`）而非 trait；`isinstance` 改用具体节点类型。（已由下述编译器修复取代）  
**Compiler fix（已完成）：**
- **isinstance（b）：** codegen 期把 `isinstance(x, Trait)` 改写为 `_cypy_is_instance_of(x, 'Trait')`，并发射模块级注册表 `_cypy_trait_registry = {trait: (实现类型名,...)}`（`_collect_module_info` 预扫描 `TraitDef`/`ImplStmt` 采集，含 trait 继承传递性）。助手先按 `type(obj).__name__` 查表命中具体 struct，再回退到真正的 `isinstance`（覆盖 trait 包装器子类）；非 trait 的 `isinstance` 原样输出。
- **运算符转发（a）：** `impl` 生成的包装器按 struct 方法的元数转发其运算符双下方法（`__add__`/`__eq__`/`__and__`/…）委托给 `__inner__`。Cython 要求特殊方法参数个数精确，故用固定位置参数（非 `*args`）生成签名；trait 基类不定义运算符，无签名冲突。
- **比较运算符返回类型（c，本轮打磨）：** 类型检查器 `_visit_BinOp` 旧对 `==`/`!=`/`<`/`>`/`<=`/`>=` 无条件返回 `bool`，使 `col == 5`（其 `__eq__` 声明返回 `ClauseElement`）被误推为 bool，`let x: ClauseElement = (col==5)&(...)` 报 `Type mismatch`。现新增 `_comparison_override_result_type()`：当操作数为自定义 struct/class 且重载了对应 dunder、其声明返回类型非 bool/None/object 时，采用声明的返回类型（左操作数优先）；原生类型比较仍返回 bool，无语义变化。
- **trait 值类型鸭子化（d，本轮打磨）：** `_type_to_str` 将作为*变量/参数/字段类型*出现的 trait 回退为 `object`（与泛型/union 处理一致），因为具体 struct 并非 trait 扩展类型的子类，保留扩展类型会让 Cython 对赋值做严格检查而拒绝（`Cannot convert _BinaryExpression to extension type ClauseElement`）。为避免误伤，trait 作为*基类/超类标识符*时改由新增的 `_trait_class_ref()` 取真实类名（`_visit_TraitDef` 的基类、`_collect_module_info` 的 super trait 采集），确保 trait 继承与方法合并不受影响。
**Files:** `cypyc/codegen/cython_generator.py` — `_collect_module_info()`、`_emit_trait_isinstance_support()`、`_visit_Call()`、`_visit_ImplStmt()`、`_type_to_str()`、`_trait_class_ref()`；`cypyc/analyzer/type_checker.py` — `_visit_BinOp()`、`_comparison_override_result_type()`  
**Regression test:** `tests/test_trait_isinstance.py`（含比较链式类型自洽、trait 变量回退 object、trait 基类保留、继承传递性）  
**原始动机用例已回归 native trait 风格：** `Find_BUG/sqlalchemy_core/sqlalchemy_core.cypy` 现已去掉两处规避——运算符方法直接返回 `ClauseElement`、`_compile_operand` 用 `isinstance(o, ClauseElement)`；`tests/test_find_bug_sqlalchemy_core.py::test_runtime_build_query` 编译为 pyd 后仍产出 `SELECT * FROM users WHERE id = 5 AND age > 18`，端到端验证 BUG-023 修复。

---

## BUG-024: `for k, v in ...` 多目标解包不支持 ❌ FIXED
**Severity:** High  
**Found in:** tenacity / sqlalchemy_core（字典遍历通用场景）  
**Error:** `Expected IN, got COMMA at N:M`

```cypy
def main() -> None:
    d: dict<str, int> = {"a": 1, "b": 2}
    for k, v in d.items():     # Expected IN, got COMMA
        print(k, v)
```

**Root cause:** `_parse_for_stmt()` 仅用 `_parse_bitwise_or()` 解析单个循环目标，遇 `COMMA` 即终止，随后 `_expect(IN)` 失败。此外 `_extract_names()` / `_extract_bind_names()` 未识别 `SlicePattern`，`for head, *tail in ...` 中 `*tail` 不会注册为循环变量（`Undefined name 'tail'`）。  
**Fix:** 新增 `_parse_for_target()` / `_parse_for_target_element()`，支持 `for k, v` / `for (k, v)` / 尾随逗号 / 嵌套 `for k, [a, b]` / `for head, *rest`，多目标返回列表，与既有解构目标形态统一；`_extract_names()` / `_extract_bind_names()` 增加 `SlicePattern` 分支。codegen 侧 `_for_target_to_str()` 渲染 `(k, v)`。  
**Files:** `cypyc/parser/parser.py`、`cypyc/analyzer/scope_analyzer.py`、`cypyc/analyzer/type_checker.py`  
**Regression test:** `tests/test_for_unpacking.py`

---

## BUG-025: 负索引下标在编译产物里段错误（`xs[-1]` / `d[k][-1]`）❌ OPEN
**Severity:** Critical（无诊断的 SIGSEGV，exit 139）
**Found in:** T0r258.4.2 golden 判据加固（给 `examples/new_syntax_features.cypy` 补真实输出时撞出）
**Error:** 进程直接死亡，shell 只报 `Segmentation fault`，`echo $?` = 139，编译器/CLI 不给任何诊断。

```cypy
def main() -> int:
    xs = [10, 20, 30]
    print(f"list negative index = {xs[-1]}")   # 同一段代码写 xs[0] 是好的
    return 0
```

**Evidence（全部可复跑）:**
- `Find_BUG/audit_2026q3/scratch/anchor02/v_neg_index_list.cypy` → `exit=139`；删掉 `output/v_neg_index_list.{c,pyx,pyd}` 全量重建后仍 139（不是缓存假象）。
- `Find_BUG/audit_2026q3/scratch/anchor02/repro_subscript_chain.cypy`（`d[k][-1]`，str 键 + 负索引）→ `exit=139`。
- faulthandler 原文留档 `Find_BUG/audit_2026q3/scratch/anchor02/subscript_chain.faulthandler.log`：`Windows fatal exception: access violation`，`Current thread … File "…/cypy_hook/hook.py", line 622 in run_module`。
- 对照组 `Find_BUG/audit_2026q3/scratch/anchor02/v_pos_index.cypy`（`scores["alice"][0]`）exit 0 且输出正确 → 差异只在**下标符号**，与 `^:` 无关。

**Root cause（假设，未修）:** 生成的 .pyx 头部固定带 `# cython: boundscheck=False` + `# cython: wraparound=False`（见 `output/*.pyx` 前 6 行），列表被 Cython 推断成 C 级容器时负索引不再回绕而是越界访问。
**Files:** `cypyc/codegen/cython_generator.py`（指令头、`Subscript` 生成）、`cypyc/analyzer/type_checker.py`（list 元素类型推断）
**连带影响:** `^:` 索引构建块的规范语义正是 `container[key][-1]`（`SYNTAX/13-build-blocks.md:9`），所以本缺陷使 `^:` 整体不可用 —— 相关用例挂起在 `examples/_pending_build_blocks.cypy`。
**边界:** `cypyc/parser|analyzer|codegen` 由并发的 constraint/subtype 实现线占用，本单元只登记不修。

---

## BUG-026: `~:` 去括号构建块在 `return` 位置被静默误编译 ❌ OPEN
**Severity:** High（静默误编译 + 声明的 `-> int` 没有拦住返回函数对象）
**Found in:** T0r258.4.2（原 `examples/new_syntax_features.cypy:100-118` 的 4 个 `test_deparens_*`）
**Error:** 运行期打印 `<cyfunction double_value at 0x…>`，没有任何编译告警。

```cypy
def double_value(x: int) -> int:
    return x * 2

def test_deparens_basic() -> int:
    return double_value ~:
        21
```

生成的 .pyx（`output/repro_deparens_in_return.pyx`）：

```python
def test_deparens_basic():
    return double_value
    21
```

**Evidence:** `Find_BUG/audit_2026q3/scratch/anchor02/repro_deparens_in_return.run.log`（exit 0，输出函数对象 + `type = <class '…cython_function_or_method'>`）。
**对照:** 赋值形态 `result = double_value ~: 21` 正确编译成 `result = double_value(21)` → 42（`repro_deparens_noncanonical.run.log`）→ 缺陷只在 **return/表达式上下文**。
**Files:** `cypyc/parser/parser.py`（ReturnStmt 体内的构建块归属）、`cypyc/codegen/cython_generator.py`
**处置:** 4 个 `test_deparens_*` 与 `^:` 用例一起挂起到 `examples/_pending_build_blocks.cypy`。

---

## BUG-027: `~:` 的规范形态（lambda 实参）根本不可解析 ❌ OPEN
**Severity:** High（`SYNTAX/13-build-blocks.md` 写的就是这个形态）
**Found in:** T0r258.4.2
**Error:** `Expected ARROW, got INTEGER at 11:23`（`exit=1`）

```cypy
def transform_list(data: list, func: callable) -> list: ...

result = transform_list(data) ~:
    lambda x: x * 2
```

**Evidence:** `Find_BUG/audit_2026q3/scratch/anchor02/repro_deparens_canonical.run.log`。规范出处 `SYNTAX/13-build-blocks.md`「去括号语法 (~:)」。
**Root cause（假设，未修）:** 构建块体按普通表达式解析，`lambda x:` 的 ARROW 与 `~:` 后的换行块边界冲突。
**Files:** `cypyc/parser/lexer.py`、`cypyc/parser/parser.py`
**处置:** 与 BUG-026 同批挂起（`examples/_pending_build_blocks.cypy`）。

---

## BUG-028: 字符串取值的 enum 在运行期崩溃 ❌ OPEN
**Severity:** High
**Found in:** T0r258.4.2（`examples/struct_enum.cypy` 恢复可跑后暴露）
**Error:** `invalid literal for int() with base 10: 'pending'`（`[FAIL] Execution failed:` / `运行错误: 运行模块错误: …`，exit 1）

```cypy
enum Status:
    PENDING = "pending"
    COMPLETED = "completed"

def main() -> int:
    let status: Status = Status.COMPLETED
    print(f"Status: {status}")
    return 0
```

**Evidence:** 摘掉这段之前的完整 `examples/struct_enum.cypy` 运行输出留档 `Find_BUG/audit_2026q3/scratch/anchor02/_probe_struct_enum.log`（同一条错误），去掉字符串枚举后同文件产出 11 行正常输出；最小复现留档 `examples/_pending_type_defects.cypy`。
**Root cause（假设，未修）:** 枚举成员的底层类型被写死为 int（`cdef enum` + `int(...)` 化），非 int 取值在构造成员时走 `int("pending")`。
**Files:** `cypyc/codegen/cython_generator.py`（EnumDef 生成）、`cypyc/analyzer/type_checker.py`
**处置:** 该用例从 `examples/struct_enum.cypy` 移出，挂起到 `examples/_pending_type_defects.cypy`（不是删基准）。

---

## BUG-029: 字段式 struct 跨函数边界被装箱成 dict ❌ OPEN
**Severity:** High（HEAD 版 `examples/struct.cypy` 就是这么写的，一跑就红）
**Found in:** T0r258.4.2（恢复 `examples/struct.cypy` 的 HEAD 干净版后首跑）
**Error:** `运行错误: 运行模块错误: 'dict' object has no attribute 'x'`（字段名随访问点变化，亦见 `'width'`）

```cypy
struct Point:
    x: int
    y: int

def create_point(x: int, y: int) -> Point:
    return Point(x, y)          # 定位/关键字构造都一样

def main() -> int:
    let p = create_point(10, 20)
    print(f"{p.x}")             # AttributeError: 'dict' object has no attribute 'x'
    return 0
```

**Root cause（已定位到生成物）:** 只有字段声明的 struct 被编成 `cdef struct`（见 `output/struct_records.pyx` 早先版本），而 `def` 函数的形参与返回值都不带 Cython 类型，于是 C struct 一旦跨 `def` 边界就被自动装箱成 **dict**；同一函数内的局部使用（`p = Point(3, 4)` 后立刻 `p.x`）正常 —— 对照 `Find_BUG/audit_2026q3/scratch/anchor02/probe_fields_only_positional.cypy`（exit 0，输出正确）。带显式 `__init__` 的 struct 编成扩展类型（`cdef class`），跨边界安全（`examples/struct_enum.cypy` 全靠这个形态）。
**Files:** `cypyc/codegen/cython_generator.py`（struct 生成策略 + `def` 函数签名是否带类型）
**处置:** `examples/struct_records.cypy` 改用显式 `__init__` 形态；HEAD 原形态挂起到 `examples/_pending_type_defects.cypy`。

---

## BUG-030: duck 约束只在 `def main` 调用点上被正确求解 ❌ OPEN（归 constraint/subtype 线）
**Severity:** Medium-High（误报会挡住合法代码，且诊断丢位置）
**Found in:** T0r258.4.2（给 `examples/test_meta.cypy` / `examples/test_duck.cypy` 补驱动时）
**Error:** `Generic constraint violation: type 'int' does not satisfy constraint 'NumberLike' for parameter 'T' at 0:0`
（同一个 `combine(20, 22)` 直接写在 `main()` 里就通过；挪进另一个函数就报错。`at 0:0` 说明约束诊断也没带上调用点。）

```cypy
meta:
    duck NumberLike:
        a + b -> Self

def combine<T: NumberLike>(a: T, b: T) -> T:
    return a + b

def test_meta() -> int:
    total = combine(20, 22)      # ← 报错点在非 main 函数里
    return total

def main() -> int:
    print(f"assign form = {test_meta()}")
    return 0
```

**Evidence（同文件对照组，均已实测）:**
- 失败：`Find_BUG/audit_2026q3/scratch/anchor02/probe_duck_via_wrapper.cypy`、`probe_duck_assign.cypy`（`Find_BUG/audit_2026q3/scratch/anchor02/_via_wrapper.log`、`.../_assign_form.log`）
- 通过：`probe_duck_two_types.cypy`（main 内 int + float 两个调用点都正确：42 / 3.75）、`probe_duck_call.cypy`（`find_max(3, 7)` = 7）
**Files:** `cypyc/analyzer/`（约束求解与泛型实例化的作用域）—— **与本轮 constraint/subtype 实现线同一区，本单元未动**。
**处置:** `examples/test_meta.cypy`、`examples/test_duck.cypy` 的驱动刻意只在 `main()` 里调用受约束泛型，并在文件注释里写明原因与编号。

---

## BUG-031: 产物目录遮蔽 stdlib，把一份 traceback 冻结成 7 份 golden ✅ FIXED
**Severity:** Critical（判据级：23 条 e2e 锚点里 7 条基准是别人的崩溃回溯）
**Found in:** T0r258.4.1 审计 → T0r258.4.2 修复
**Error:** 任何在 `output/` 里执行的 `setup.py` 报
`AttributeError: 'dict' object has no attribute 'width'`，栈是 `setuptools → _distutils_hack → distutils.archive_util → zipfile → struct`，命中的是 `output/struct.cp313-win_amd64.pyd`（由 `examples/struct.cypy` 编出）。

**活证据（修复前后）:**
- 修复前：`cd output && python -c "import zipfile"` → 上述 AttributeError，`exit=1`；同目录 golden `examples/{struct_enum,test_duck,test_macro,test_meta,test_new_features,test_union,test_vec}.out` 7 份逐字节相同（md5 前缀 `b4321a0bc7`，2691B/31 行，内嵌 `E:\IDEProjects\AI\Cypy\output\setup.py`）。留档在 `Find_BUG/audit_2026q3/golden_before/`。
- 修复后：`cd output && python -P -c "import zipfile"` → OK；`python -m cypyc run examples/test_vec.cypy` 由「31 行 traceback」变成真实输出。

**Root cause:** 解释器跑 `python setup.py` 时把**脚本所在目录**插到 `sys.path[0]`，而构建时的工作目录正是产物目录。
**Fix:** 构建子进程一律用 `cypy_hook/hook.py` 新增的 `build_isolated_command()`（CPython ≥3.11 加 `-P`）+ `build_isolated_env()`（`PYTHONSAFEPATH=1`），`cypyc/project/project_compiler.py` 的同一处调用一并改用；`run_module()` 改成「导入+调用期间临时挂载产物目录，`finally` 务必摘掉」（与 `CypyLoader` 里既有做法一致）；另外把撞名的示例改名 `examples/struct.cypy → examples/struct_records.cypy` 拆掉具体引信。
**Regression test:** `tests/test_judge_strictness.py::TestBuildPathIsolation`、`::TestStdlibNameCollision`

---

## BUG-032: `python -m cypyc` 恒返回 0 + golden 判据三条 fail-open 结构缺陷 ✅ FIXED
**Severity:** Critical（判据级：13 条藏在绿灯里烂掉的锚点）
**Found in:** T0r258.4.1 审计（LINK-1~LINK-4）→ T0r258.4.2 修复
**表现:**
1. `cypyc/__main__.py` 只有裸 `main()`，丢弃返回码 → 打印 `[FAIL] Execution failed:` 时进程仍 exit 0。实测修复前：`python -m cypyc run examples/test_duck.cypy` 与 `python -m cypyc run examples/__does_not_exist__.cypy` 都是 `exit=0`（留档 `Find_BUG/audit_2026q3/scratch/anchor02/_link1_before.out`、`.../_link1_before2.out`），而 `cypyc/cli.py:run_run` 明明 return 1。
2. `scripts/e2e_golden.sh` 的 `strip_debug` 不过滤 `[FAIL] Execution failed:` 与其后诊断 → 失败文本被当成「程序 stdout」注册进 golden。
3. 末行 `[ "$fail" -eq 0 ] || exit 1` 只看 fail → 空 golden 记 WARN、UNREG/RUNFAIL 记录后仍整体 exit 0。
4. `examples/*.out` 与 `scripts/e2e_golden.sh` 都未纳入 git → `--update` 无 diff、无历史、不可归因。

**Fix:** `cypyc/__main__.py` 改 `sys.exit(main())`；判据端 `strip_debug` 先去 ANSI 色码、再从行首 `[FAIL] ` **截断到 EOF**，且只要原始输出里出现该横幅就直接判 FAIL（既不比对也不写盘）；空/纯空白 golden 与 `--update` 的空输出都改判 FAIL；末行门控同时看 `fail/runfail/warn`；额外把「基准内嵌机器绝对路径」也判 FAIL。LINK-4 的入库不在本单元权限内（禁止 `git add`），改为强制快照：`Find_BUG/audit_2026q3/golden_before/`（23 份 .out + 判据/入口原件）。
**不变量:** 判据只变严不变松 —— 单调性实测见 `Find_BUG/audit_2026q3/scratch/anchor02/_monotonic_after_judge.log`（新判据跑旧基准：原 22 PASS 缩水，无一条原 FAIL 变 PASS）。
**Regression test:** `tests/test_judge_strictness.py::TestJudgeRefusesFakeGreen`（用假 python 端到端考判据 7 个场景）、`::TestJudgeScriptOnlyGotStricter`、`::TestExitCodePropagation`

---

## BUG-033: 探针 `feat_constraint_02` 的 C-2.3 用例自相矛盾，实现全对也永远红 ❌ OPEN（判据级）
**Severity:** High（判据级：A4 门禁 `repro_gate.py feat_constraint_ fixed` 被这一条钉死在 exit 1）
**Found in:** T0r258.1.2（constraint 实现单元收口）
**Files:** `Find_BUG/audit_2026q3/feat_constraint_02.py:23,86,94`（判据本体，实现单元无权改）

**两处独立的缺陷，任一处都足以让它咬不住任何东西：**

1. `:86` 的语料漏拼 `DECL`（`:23` 的 `constraint Numeric = int | float`）：
   ```
   union_src = ("constraint Small = Numeric | str\n" + CALL.replace("Numeric", "Small"))
   ```
   于是该模块里 `Numeric` **根本没声明过**，按 C-2.5（同一轮 `feat_constraint_06` 正钉着它）
   三个子用例全部合法报错，`:94` 的 `u_int["success"]` 永不可能为真。
2. `:94` 断言 `not u_float["success"]`，与 §2.3  itself 冲突：正确展开后
   `Small` 的成员是 `int | float | str`，`clamp(1.5)` **必须**放行。
   能满足 `int✓ ∧ str✓ ∧ float✗` 的成员表只有 `{int, str}`，即要求 `Numeric` 展开成**只剩 int** ——
   没有任何条款授权这种展开。

**活证据（可直接复跑）:**
- `python Find_BUG/audit_2026q3/feat_constraint_02.py` → `checks=7 unmet=1`，唯一 MISS 是
  `C-2.3 nested constraint members are flattened`，detail 里同时含
  `constraint 'Small' references undefined type 'Numeric' ... at 1:20`（缺陷 1 的直接指纹）。
- 把 `DECL` 按 `:86` 的原意拼回去（正确的 C-2.3 语料），当前实现三个实参全绿：
  `clamp(1)`/`clamp(1.5)`/`clamp('a')` 均 `success=True, errors=[]`，
  违例时诊断摊开的正是展开后的名单（`constraint Small = Numeric | bool` + `clamp('a')` →
  `(allowed: int | float | bool)`）。也就是说：缺陷 1 修好后 `:94` 仍因缺陷 2 恒红。

**建议的判据修正（交判据 owner，实现单元未动判据）:**
`:86` 改为 `union_src = (DECL + "constraint Small = Numeric | str\n" + CALL.replace("Numeric", "Small"))`；
`:93-95` 改为断言 `u_int and u_str and u_float` 三者皆 `success`（成员都放行），
负例另加一个非成员实参（如 `clamp([1, 2])` → `(allowed: int | float | str)` 被拒）。

**本单元处置:** 判据只读，不改；条款实现侧的等价护栏已落到
`tests/test_named_constraints.py::TestTransitiveFlattening`
（`test_nested_constraint_members_are_flattened` /
`test_flattened_constraint_accepts_every_member_at_call_site` /
`test_violation_diagnostic_prints_flattened_members`），开关对照实测：
把 `_expand_constraint_members` 换成「不展开嵌套」后这些用例立即变红。

---

**Total: 26 fixed, 7 open**（口径实测：`grep -c '^## BUG-' Find_BUG/BUGS.md`=33 条，
其中 `.*OPEN`=7、`.*FIXED`=26；本行此前写「23 fixed」是 3 条修复未回写汇总的滞后数。
BUG-025~030 为本轮 T0r258.4.2 新登记的**未修**缺陷，全部附最小复现与活证据；BUG-031/032 本轮修复；
BUG-033 是判据自身的缺陷（`feat_constraint_02` 的 C-2.3 用例），编译管线无问题，故不改判据、只登记。）
