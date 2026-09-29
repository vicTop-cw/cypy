# Find_BUG 复刻方案（cypyc 编译器压测 · 库移植清单）

> 目标：用真实流行库的 Cypy 移植来压测 `cypyc` 编译器，在真实工程里暴露并修复 bug。
> 原则：**复刻库的“脑子/接口”，把重依赖（pandas / plotly / chromadb / numpy）推到 trait 背后当可选 backend**；
> 数据层用 Cypy 原生 `struct` / `list<dict>` 替换，内核零重依赖。

---

## 0. 关于 pandas（结论：不推荐复刻）

用户判断正确——pandas **效用不大，不建议复刻**。原因：

- pandas 的“价值”几乎全在 **C / Cython 内核**（DataFrame 的列式存储、groupby、向量化），纯 Python 层很薄。
- 复刻它要么去重写 C 内核（那测的是 C 扩展桥接，不是 cypyc 的 Python 语义编译目标），要么只复刻薄薄的 Python 壳（测不出东西）。
- 同理 **numpy** 也不适合（C 内核）。
- 真正该复刻的是“用 pandas 的**上层语义**”——而 Cypy 已经用 `struct` / `list<dict<str,str>>` / `SqlResult` 表达了，没必要再搬 pandas 本身。

---

## 1. 选库标准（什么样的库最能揪 bug）

优先选**大量使用 Cypy 要对标的 Python 黑魔法**的库，移植时最容易撞到编译器缺陷：

| 语言特性 | Cypy 对应物 | 易踩的编译 bug |
|---|---|---|
| metaclass / `__init_subclass__` | `struct` 初始化 | 元类继承、字段收集顺序 |
| descriptor / property | trait 方法 | 描述符协议、`__get__`/`__set__` |
| 泛型 `Generic[...]` / `TypeVar` | `trait Tool<T>` | 类型参数边界、递归类型、前向引用 |
| 装饰器（嵌套/带参） | — | 闭包捕获、注解读取、默认参求值 |
| 运算符重载 `__eq__`/`__and__` | — | 双下方法名映射、反射算子 |
| async/await | — | 协程编译、上下文管理器、`async for` |
| 运行时类型自省 | — | `get_type_hints`、forward ref、typing_extensions |

---

## 2. 推荐移植清单（按 bug 产出 / 性价比排序）

### Tier 1 —— 最高产出，且精准打中 Cypy 卖点（优先）

**① Pydantic（核心子集，纯 Python 部分）**
- 为什么：直接对应 Cypy 的 `struct` 主张——验证“用 `struct` 能否取代 pydantic 的 metaclass+descriptor 魔法”。
- 压测特性：metaclass、`__init_subclass__`、descriptor、`Generic`/`TypeVar`、`Field`、validator、`model_construct`、runtime `get_type_hints`、forward ref。
- 预期 bug 类：泛型边界、描述符协议、字段收集顺序、嵌套模型递归类型。
- 体量：中～大。建议先移植 `BaseModel` + 基础校验 + `Field`，不做 pydantic-core（Rust 部分）。
- 备选（更轻）：**attrs** —— 同样覆盖 decorator+slots+converter，体量小一半。

**② beartype**
- 为什么：纯 typing 体操 + `@overload` + 递归类型 + 装饰器，是“类型系统编译”的放大镜。
- 压测特性：`TypeVar`、递归类型、装饰器、`typing` 全家族、`is_bearable`/`beartype` 运行时检查。
- 预期 bug 类：泛型边界、重载解析、复杂注解解析。
- 体量：小且密，性价比极高。

**③ SQLAlchemy Core（表达式 DSL 子集）**
- 为什么：运算符重载 + metaclass + descriptor 的集大成者，SQL 表达式树 `Column == 1` 这类语法最易暴露算子编译 bug。
- 压测特性：metaclass、descriptor、运算符重载（`__eq__`/`__and__`/`__or__`/`__in__`）、复杂继承、`@declared_attr`。
- 预期 bug 类：双下方法映射、反射算子、元类字段收集。
- 体量：大。建议只移植 Core 表达式层（不碰 ORM 会话/引擎）。

### Tier 2 —— 补装饰器 / 闭包 / async 覆盖

**④ Click（或 Typer）**
- 为什么：装饰器巢 + 注解驱动 CLI，常用且中等体量。
- 压测特性：嵌套装饰器、闭包、注解读取、默认参求值、`@group`/`@command` 组合。
- 预期 bug 类：装饰器叠加顺序、闭包变量捕获、可选参默认值。

**⑤ tenacity**
- 为什么：小、纯装饰器 + 泛型 + 异常状态机，是验证“装饰器 + 泛型”的一击快 win。
- 压测特性：装饰器、`Generic`、`TypeVar`、异常链。
- 体量：小，适合作为新特性合入后的冒烟测试。

**⑥ httpx（或 anyio）**
- 为什么：补 Vanna port 缺的 **async** 覆盖；sync/async 双实现 + 上下文管理 + 类型密集。
- 压测特性：async/await、`async with`、`__aenter__`/`__aexit__`、Protocol、泛型客户端。
- 预期 bug 类：协程编译、异步上下文管理器、协议类。

### 备选（按需）
- **marshmallow**：schema/field + 装饰器 + validator，中等。
- **loguru** / **structlog**：descriptor/proxy + 绑定，中等，测描述符与代理。

---

## 3. 移植通用套路（每个库照此执行）

1. **先抽接口（trait 化）**：把重依赖抽象成 trait——如 `Llm`、`VectorStore`、`DataFrameBackend`、`Engine`。
2. **原生数据层**：用 `struct` / `list<dict>` 替代 pandas DataFrame / numpy 数组；只在用户硬要时才桥接。
3. **内核零重依赖**：plotly/chromadb/numpy 等退化成可选 backend，不进核心 `from` 列表。
4. **先跑通最小闭环**：挑一个端到端路径（如 pydantic 的 `Model(**data)` 校验；Vanna 的 `ask`）先绿，再扩。
5. **每个移植=一份 bug 清单**：遇到 cypyc 编译/运行错误，记进 `Find_BUG/<lib>/BUGS.md`，便于修编译器。

---

## 4. 推进相位

- **Phase 0（进行中）**：Vanna —— 补 `Llm` trait + `generate_sql` + `ask` 闭环（见 `vanna-port-what-to-replicate_20260902.md`）。
- **Phase 1**：beartype（小，先验证泛型/装饰器编译）。
- **Phase 2**：Pydantic 核心子集（验证 struct 取代 metaclass/descriptor）。
- **Phase 3**：SQLAlchemy Core 表达式层（运算符重载 + 元类）—— ✅ 已完成（见 `sqlalchemy_core/`，暴露并修复 BUG-022，记录 BUG-023）。
- **Phase 4**：Click / tenacity（装饰器冒烟）→ httpx（async 覆盖）。

---

## 5. 目录约定

```
Find_BUG/
├── Vanna/            # 进行中
├── beartype/         # Phase 1
├── pydantic/         # Phase 2（v1 子集源码已建：base_model/fields/validation/errors/registry/models）
├── sqlalchemy_core/  # Phase 3（表达式层子集：运算符重载 + trait，见 README/BUGS）
├── tenacity/         # Phase 4（装饰器 + 泛型 + 异常，见 README/BUGS）
├── BUGS.md           # 跨库编译器 bug 汇总
└── REPLICATION_PLAN.md  # 本文件
```
