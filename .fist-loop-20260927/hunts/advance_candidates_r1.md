# R1-推进 候选清单：冻结文档「已声明未实现」面

来源：一次只读侦察（Explore 子代理，2026-09-27 04:40Z 前后）。**本清单未经我复算**，
推进环节开工前必须逐条自己打到调用面复现（判据=同一条 .cypy 源码在 CLI 上的实测 rc/产物），
因为子代理报的是「代码形状 + 内存探针」，而形状推断出的失败点历史上写过错现场。

分类口径：(c)=文档声明有该语法、产品码没有处理路径；(d)=parser 收下但 codegen 丢/写错（静默型）。

| # | 特性 | 声明处 | 现状证据（待复算） | 测试/示例用过吗 | 尺寸 |
|---|---|---|---|---|---|
| 1 | `raise X from e` 异常链 | `SYNTAX/16-exceptions.md:104,111` | parser 存了 cause（`cypyc/parser/parser.py:2341`），`_visit_RaiseStmt`（`cypyc/codegen/cython_generator.py:3193-3198`）只写 `raise {exc}` ⇒ (d) 静默丢 `from` | 0 条测试；仅 `examples/demos/boundary_cases/exception_edges.cypy:104`、`concurrency_advanced/exceptions_demo.cypy:190` | tiny |
| 2 | 枚举内自定义方法 | `SYNTAX/06-enum.md:79,90,135` | `_parse_enum_def`（`parser.py:1412-1433`）只吃 IDENTIFIER ⇒ `Expected IDENTIFIER, got DEF`；`EnumDef`（`parser.py:136`）无 `methods` 字段 | 12 个枚举示例都不带方法；0 测试 | medium |
| 3 | struct 里 `@staticmethod` | `SYNTAX/06d-builtin-magic-traits.md:49-50`、`22-magic-properties.md:41` | (d) 产物保留 `self` ⇒ `C.mk()` TypeError；class 路径正确 | 语料里 `@staticmethod` 都在 `class` 内 | tiny |
| 4 | `__implicit_default__` 隐式默认填充 | `06d:40-56`（`:53` 用例） | `grep -rn __implicit_default__ cypyc/ cypy_bridge/` = 0 命中 ⇒ 产物里是未定义名 | 无 | medium |
| 5 | `let x =:` 变量构建块 | `SYNTAX/13-build-blocks.md:74,86,170` | `_parse_let_stmt`（`parser.py:1567,1589`）⇒ `Expected NEWLINE, got BUILD_ASSIGN`；裸 `x =:` 走 `_parse_build_block`（`parser.py:3943`）是通的 | 测试/示例只用裸形 | tiny/medium |
| 6 | `guard <cond>: <action>`（无 else） | `SYNTAX/appendix-A-keywords.md:41` | `parser.py:2399` 硬要 ELSE ⇒ 解析失败；`14-syntax-sugar.md:93-150` 只描述带 else 的形 | `tests/test_codegen_guard.py` 全带 else | tiny |
| 7 | `f(name~ value)` | `SYNTAX/appendix-B-operators.md:187` | `_parse_call`（`parser.py:3313`）失败；裸 `g(x~)` 可用 | `examples/new_syntax_features.cypy:24` 只用裸形 | tiny |
| 8 | `def f(..args)` 具名可变参数 | `appendix-B:167` | `parser.py:1198-1216` 只把裸 `..` 当匿名分隔符 | 无 | tiny |
| 9 | `case Point(x=0, y=0)` | `SYNTAX/17-pattern-matching.md:110-126` | `Unexpected pattern token ASSIGN`；位置形 `Point(x,y)` 对 cdef-class struct 产出 `.__f0`（`cython_generator.py:1687`）⇒ (d) 错码 | 语料用花括号/解构形 | medium |

**明确不可选（文档自己声明是未来工作，不是「已声明未实现」缺口）**：
`dispatch/arm`（`33-…md:438`「本轮 DEFERRED，仅成交付提案」）、宏体展开（`18-macros.md:67-78`）、
`comptime:` 块与 `comptime def`（`19-comptime.md:36-47`）、SIMD 与 `Mat4*Vec4`（`21-simd-vector.md:123-126`）、
`Callable[[T],R]`/海象/`&` 冲突（`appendix-C-features.md:590-596`）、`fn` 关键字（`25-compatibility.md:28`）。
**已核实不是缺口的**：`constraint` 四层已落地（`cython_generator.py:3394` + `tests/test_named_constraints.py`，
appendix-A:88 的「代码生成层无」是过期描述）；`subtype` 空产物是 `33` S-4.1 规定的；`@value` 完整。
**先查再动**：外部账本 `Find_BUG/BUGS.md:444,469,498`（BUG-025/026/027）与 #5 的 `^:`/`~:` 构建块重叠，
动 #5 前要先确认不是同一件事的两种记法。

## 推进环节的取法（时间盒 1-2 叶）

1. **#1 `raise … from e`**——只有一个 codegen 分支要补，AST 字段已在，声明句无歧义；
   今天没有任何测试断言「被丢掉的形式」，所以补上不会与既有绿冲突（零假绿风险）。
2. **#5 `let x =:`**——只动 parser 一个分支，落到**已有且被测过**的 codegen 路径；
   13 号文档的 3 个例子就是现成的验收判据。
3. #2 枚举方法最大但纯增量（今天是硬解析错误，落地不可能回退任何现有产物）。
