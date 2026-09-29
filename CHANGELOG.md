# Changelog

本项目所有重要变更均记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增

- **字典字面量的键值位判定（2026-09-29 自驱组合环 R14）**：`cypyc/analyzer/type_checker.py` 此前
  **没有** `_visit_DictLiteral`，字面量落到 `_visit_children` 返回 `None` ⇒ `dict<K, V>` 的键位与值位
  连「实得类型」都没有，`let x: dict<str, int> = {"a": "b"}` 一类 7 形全部 0 诊断（BUG-141）。
  本轮新增 `_visit_DictLiteral` + `_slot_lub`（同形取该类型并保留参数、数值串取 `bool→int→float→double`
  最宽、其余塌 `object` 并按占位放行），`dict` 进入 `_ELEMENT_CHECKED_CONTAINERS`，诊断对 dict 点名
  `Dict key` / `Dict value` 而非 `element 1/2`；赋值位与返回位仍共用 `_check_container_elements` 一份判定。
  规范先行落 `SYNTAX/02-type-annotations.md`「字典字面量的键值位判定（R14 补，2026-09-29）」，
  并把上一节 R13 的规则 6（dict 豁免）就地标注作废；
  R13 的两条豁免锁与 `cypy.container.elements` 里那条 dict 案例同轮**收紧**（断言反向，不删除；该份
  spec 因此重封指纹）。判据：Ω-spec `cypy.dict.elements` 25 对（`fnv1a64:de31b469f22cbed7`）+
  锁 `tests/test_dict_elements_r14.py`（29 支）。另立并闭合 BUG-142：`SYNTAX/02` 曾把锁死用例
  指向不存在的 `tests/regression/test_container_elements_r13.py`，现改为实际路径并新增一条
  「手册引用的就是这份文件本身」的对表锁。
  验证：pytest 2444 全绿（半径 2390 + 新锁 29 + 新语料 25）、自研套件 47/47、Ω-gate 8 spec / 176 例 100%、
  e2e golden 25/25、承重矩阵 7 格（5 格承重全部 pytest 与 Ω-gate 双侧转红，只改注释对照 0 红；
  就是 M3 那一格先抓到「数值阶梯取最宽」在 Ω-gate 半边没语料，才把 spec 从 23 对补到 25 对）、
  承重矩阵见 `.fist-loop-20260929/`。
- **泛型语法链路（2026-09-29 自驱组合环 R10/R11）**：调用点类型实参 `identity<int>(42)`、
  `pair<int, str>(42, "a")` 与泛型类 `class Box<T>:`（含 `extends`/`(Base)` 两种基类形态、
  `T: int | float` 约束）现可解析、检查并出码；产物按 Cypy 既有约定**擦除**类型实参
  （不再是运行期会把类型名当零参函数调的 `(类型名(), f(x))[1]`）。
  元数与「非泛型被调方挂实参」给诊断，接收者按声明顺序逐位代入（`l.next().next()` 可复合）。
  规范条款见 `SYNTAX/11-generics.md`「调用点的类型实参」与「泛型类的判定口径」；
  判据在 `corpus/cypy.generic.callsite.json`、`corpus/cypy.generic.class.json`（R11 收口时 5 op / 100 对，
  现为 6 op / 123 对，见下条）；
  回归锁 `tests/test_generic_callsite_r10.py`、`tests/test_generic_class_r11.py`。
  未闭环的同族面按缺陷入账：BUG-120/121/122（手册形态与裁决面）、BUG-128（struct 方法不代入）、
  BUG-129（声明界在注解位/实例化位不判）。

- **容器元素位判定与类型别名代入到底（2026-09-29 自驱组合环 R13，闭合 BUG-137/138/139）**：
  同名容器不再「名字对上就放行」—— `tuple<bool, int>` 收 `(True, "x")`、`list<int>` 收 `["s"]`、
  `list<list<int>>` 收 `[["s"]]`、定长元组个数不符，以及返回位上的全部同形，现各报一条带行列号的诊断
  （`Element N type mismatch: expected …, got …` / `Tuple element count mismatch`）；
  四类占位形态（空容器构造器、嵌套无参、含 `None`/`object` 元素、声明侧 `object`）继续放行，
  `dict` 键值位明确不在本节范围（字典字面量至今不推断类型）。
  别名侧：`_substitute_type` 补 `UnionType` 分支 ⇒ `type Maybe<T> = T | None` 不再「整条不代入」；
  新增 `_expand_nested_alias` ⇒ 别名右端里出现的**其它别名**展开到底
  （`type Triple<T> = Pair<Pair<T>>` 的正确字面量此前被误判为类型不符，属假阳性），
  自指别名 `type Loop<T> = Loop<T>` 由 `_alias_stack` 名链守卫停在原地而非 RecursionError。
  规范条款见 `SYNTAX/02-type-annotations.md`「容器元素位判定（R13 补）」规则 1-6；
  判据 `corpus/cypy.container.elements.json`（28 对，台账现为 7 op / 151 对）；
  回归锁 `tests/test_container_elements_r13.py`（含「手册闭合标量表 ↔ 代码常量」双向对表）。
  同轮把 R13 入口单 BUG-136 **改判**（其「别名参数从不代入」的机制栏为假）：
  抬头仍 `OPEN`，只留「带界别名 `type Num<T: int | float> =` 不解析」那一面；
  其余仍开面按缺陷入账 —— 联合别名的成员元素位不判（`_type_in_union` 只比成员名）、
  字典字面量不推断类型、BUG-122 类型实参不判存在性、BUG-135/128 推断层。
- **泛型声明界在使用侧的判定（2026-09-29 自驱组合环 R12，闭合 BUG-129）**：`T: int | float`、`T: Show`、
  `T: Number` 这类**定义侧声明界**现在在三处使用位都会判 —— 注解位 `let x: Num<str>`、
  显式类型实参构造位 `Num<str>(...)`、结构体字面量位 `NumS {v: "s"}`。
  三处共用同一件 `TypeChecker._check_declared_bounds`（`cypyc/analyzer/type_checker.py:1311`），
  与函数调用位复用同一个 `_check_generic_constraint` ⇒ 联合/单名/特质/typeclass 四类界只有一份判定与一份消息；
  原先字面量位自带的那份窄复制只认单名界（`T: int | float` 取到 `None` ⇒ 静默放行），本轮摘除。
  元数判定与界判定并存、互不遮蔽；诊断行列指向注解位本身（行号 +1 的既有缺陷见 BUG-126）。
  规范条款见 `SYNTAX/11-generics.md`「声明界在使用侧的判定」规则 1-4（规则 4 明写不判的一面）；
  判据 `corpus/cypy.generic.bounds.json`（23 对，Ω-gate 台账合计 6 op / 123 对）、
  回归锁 `tests/test_generic_bounds_r12.py`（18 支，含"字面量位不许长回窄复制"的源码针）。
  未随本条闭环的同族面：BUG-135（构造位不写类型实参时不做推断）、BUG-134（违界诊断的
  `in call to '<unknown>'` 文案误导）、BUG-128（struct 方法不代入）⇒ 均入账未修。

### 修复

通过 `Find_BUG/` 的"用 Cypy 复刻流行库以压测编译器"工程（Vanna / beartype / tenacity /
pydantic / sqlalchemy_core）发现并修复共 24 项编译器缺陷（`Find_BUG/BUGS.md` BUG-001~024），
涵盖解析器、词法器、类型检查器与代码生成：

> **台账现状更正（2026-09-26 实测，FIST `cron-cypy/T0r258.5.2`）**：本条原文写「当前 0 项未决」，
> 与台账不符。实测 `grep -c '^## BUG-' Find_BUG/BUGS.md` = **32** 条登记，其中
> `grep -c '^## BUG-.*OPEN'` = **6** 条未决（BUG-025~030，2026-09-26 由 `T0r258.4.2` 新登记，
> 每条附最小复现与活证据）、标 FIXED **26** 条。未决的 6 条边界都在
> `cypyc/parser|analyzer|codegen`，与并发的 `constraint`/`subtype` 实现线同一区，
> 相应用例显式挂起（`examples/_pending_build_blocks.cypy`、`examples/_pending_type_defects.cypy`）
> 而不是伪装成 PASS。另：`BUGS.md:627` 的自述行写 "Total: 23 fixed, 6 open"，
> 与标题实测的 26 条 FIXED 差 3 条 —— 该口径差在 `Find_BUG/`（本单元无权修改）内，留待台账轮次对齐。

- **解析器/词法器**：多行函数签名与括号内 NEWLINE 解析（BUG-003/011/012）、圆括号内
  `_expect_indent` 未重置（BUG-017）、`_parse_build_block` 假定必存在 INDENT（BUG-018）、
  struct 体内文档字符串崩溃（BUG-001）、`@staticmethod`（BUG-002）、相对导入（BUG-005）。
- **代码生成**：属性赋值丢失右值（BUG-019）、显式 `__init__` 重复构造（BUG-020）、
  `&&`/`||` 生成非法 Cython（BUG-021）、函数/方法默认参数值丢失（BUG-022）、
  `for k, v in ...` 多目标解包不支持（BUG-024）。
- **类型系统**：`not isinstance()` 嵌套于 `and` 误判（BUG-010）、`type` 作为返回标注被拒（BUG-007）。
- **trait 系统（BUG-023）**：修复 `isinstance(具体实例, Trait)` 运行时恒假（codegen 期
  改写为运行时注册表查表，含 trait 继承传递性）、trait 包装器不转发运算符双下方法
  （按元数生成固定参数转发）、比较运算符尊重自定义 dunder 声明返回类型、trait 作为
  变量/参数类型时鸭子化回退 `object`（区分于作为基类/超类标识符时保留真实类名）。

**审计修复轮（2026-09-25，FIST `cron-cypy/T0r61`，判据源 `Tnr-FIST-Mbt-Cypy代码审查报告.md`）**
29 条关键项经第二遍亲审为 26 条真实缺陷（critical 5 / high 21），全部修复并各配精确回归用例：

- **增量编译链**：`dependency_graph` 标识符词表归一化（原先 `Name`/`Identifier` 之外的节点
  被漏采，依赖词表恒空）；`ast_differ` 改用 blake2b 递归结构摘要并剔除位置信息
  （此前 `str()` 把行号带进摘要，纯格式化会误判为语义变更；禁用 builtin `hash()`，
  因其受 `PYTHONHASHSEED` 影响逐进程随机）。
- **前端**：预处理器 include 路径用 realpath+normcase 做包含校验并抛 `IncludeError` 族
  （此前可 `../` 逃逸项目根）；宏替换改 token 级并对字面量做序列化，`$(...)` 插值单遍处理；
  `indent_detector` Tab 归一化为列；`Type.__eq__` 纳入 `union_members` 并显式 `__hash__ = None`。
- **运行时桥接**：`cypy_bridge` 的指针所有权、`defer`/`nogil` 单例、`memory` 注解与返回值
  不一致导致的死分支、`union` 函数遮蔽同名子模块等语义修正。
- **构建钩子与 CLI**：`cypy_hook` 产物后缀改由 `sysconfig` 的 `EXT_SUFFIX` 推导（不再硬编码
  `-win_amd64.pyd`），构建超时 60→180s；修复 `chdir` 之后才 `abspath` 相对输出目录、以及
  `finally` 无条件删除临时目录连带删掉正在回报产物的两处真实回归；`cypyc run` 改为
  `success and not errors` 才回报成功，缺入口函数抛 `FunctionNotFoundError`（模块级程序不再误判）。
- **项目编译与测试基建**：`project_compiler` 相对导入基准、`endswith` 兜底去除与歧义诊断、
  同名冲突诊断、成功位循环后计算；`test_suite` 的 `Suite.current_test`、`skipped` 计数与
  `Check.has_failures()` 真正生效；`scripts/sync_demo.py` 补 orphan 报告并修 GBK 控制台崩溃。
- **顺带查明（审查报告未列）**：`-={name} - set(generic_params)` 优先级写法会生成 phantom
  泛型依赖；`test_suite/fixtures/parser.py` 调用不存在的 `Preprocessor.preprocess` 使预处理器
  长期零覆盖。

**判据加固轮（2026-09-26，FIST `cron-cypy/T0r258.4.1` → `T0r258.4.2`，锚点 A1
`bash scripts/e2e_golden.sh`）**：原「A1 全绿」是假绿，四条互相独立的断链任一条存在时判据都不咬——
LINK-1 `cypyc/__main__.py` 丢弃返回码使 `python -m cypyc run` 恒 exit 0（判据的 RUNFAIL 分支是死代码）、
LINK-2 CLI 失败横幅 `[FAIL] Execution failed:` 被 `strip_debug` 当成「程序 stdout」注册进 golden、
LINK-3 空/纯空白 golden「比对通过」即算绿、LINK-4 末行门控只看 `fail`。加固的**单调性证明**
（新判据跑同一批未改动的旧 golden，绿集合只准减）：

- 加固前基准：`PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1` exit 0
- 加固后、基准未动：`PASS=13 FAIL=9 UNREG/RUNFAIL=1 WARN=0` exit 1
  （原 22 条 PASS 里只有 **13** 条真的约束了实现；没有任何一条原 FAIL 变 PASS）
- 清污 + 重注册后：`PASS=23 FAIL=0 UNREG/RUNFAIL=0 WARN=0` exit 0

那 9 条 FAIL 的真成分：7 份逐字节相同的编译期 traceback（同一根因：构建子进程把产物目录
`output/` 插进 `sys.path[0]`，`struct` 等同名 `.pyd` 遮蔽 stdlib 模块，崩溃在装钩子阶段被复制给
后续每个示例）+ 1 份 1 字节空 golden + 1 条改名后的未注册示例。根因登记为 BUG-031/032，
并落了三条防复发：示例改名、构建统一走 `cypy_hook/hook.py:build_isolated_command()`
（CPython ≥ 3.11 加 `-P`）+ `build_isolated_env()`（`PYTHONSAFEPATH=1`）、
`tests/test_golden_anchor_probes.py` 机检「示例名撞 `sys.stdlib_module_names` 即红」。
全部实测数字与产物路径见 `reports/2026-09-26/T0r258-cypy-feature-r2-report.md` §二。

### 测试

- 新增回归测试：`tests/test_trait_isinstance.py`、`tests/test_for_unpacking.py`、
  `tests/test_find_bug_tenacity.py`、`tests/test_find_bug_sqlalchemy_core.py` 等。
- `sqlalchemy_core` 动机用例已回归 native trait 风格（运算符返回 trait、`isinstance(o, Trait)`），
  编译为 `.pyd` 后端到端验证通过。
- 修复 `tests/test_ownership.py` 中辅助数据类被 pytest 误收集产生的告警（`__test__ = False`）。
- 审计修复轮新增/扩充永久回归用例：`tests/test_incremental.py`(38)、`tests/test_preprocessor.py`(28)、
  `tests/test_test_suite_harness.py`(12)、`tests/test_cli.py`（`run_run` 失败路径）、
  `tests/test_codegen_error_handling.py`，以及 `test_bridge_library.py`/`test_ownership.py`/
  `test_macro_expansion.py`/`test_project_compiler.py`/`test_hook.py`/`test_bridge_integration.py` 扩充，
  全量套件基线 1466 → 1681 passed / 0 failed。
- `Find_BUG/audit_2026q3/`：31 个自门控复现脚本（exit 1 = 缺陷仍在，exit 0 = 已修）+
  三模式判据 `repro_gate.py`（scripts / reproduce / fixed），已登记为 CI 可用的外部判据。

### 文档

- 修正 `Find_BUG/BUGS.md`：BUG-011 状态标记与正文/汇总表对齐；"已知遗留问题"章节
  标注 `test_is_not_regression`、`test_hot_reload` 均已在无需排除的全量套件中通过（1466 passed）。
- **语法状态文档一致性轮（2026-09-26，FIST `cron-cypy/T0r258.5.2`，判据
  `Find_BUG/audit_2026q3/feat_docs_01.py`）**：按 `T0r258.5.1` 机检出的失真逐条改文档，
  不夹带任何未经实现轮验收号的状态翻转。
  - 本文件：`当前 0 项未决` → 实测台账现状（32 条登记 / 6 条 OPEN / 26 条 FIXED）；
    新增上面「判据加固轮」的 A1 三段实测。
  - `docs/SYNTAX_CHANGE_REVIEW.md`：§1 的列名从「实现状态」改为「本清单文档动作」并显式声明
    实现状态以 `SYNTAX_IMPLEMENTATION_STATUS.md` 为准；`constraint`/`subtype`/`dispatch` 的规范
    指向由 `27-constraints.md`（实测全文 475 行、`duck` 出现 50 次、`subtype`/`dispatch` 各 0 次，
    它是已实现的 duck 约束规范）改指 `33-type-constraints-subtypes-dispatch.md`；§7.1 的
    `cdef`/`NO_STRATEGY` 存废结论按 lexer 实测更正（`cdef` 不在 `Lexer.KEYWORDS`，
    `TokenType.NO_STRATEGY` 全仓 0 引用）。
  - `SYNTAX_IMPLEMENTATION_STATUS.md`：§1 概览四项数字改为实测值并附计数口径；§6.1 的
    幽灵文件 `test_typeclass_codegen.py`（`git ls-files` + `find` 双查均无）改指真实落点
    `tests/test_type_inference.py::TestTypeClassSupport`；§7.2 的「四个潜在移除项均已移除」
    按 token 实测拆开；§8.2 的三条文档指向对齐实际文件名；新增 golden 锚点与 pytest
    收集两条覆盖事实（23/77 锚定、`test_suite` 收集 0 条）。
  - `SYNTAX/appendix-A-keywords.md`：补齐 `true`/`false` 两行（`lexer.py:232-233` 实测
    `"true"→TokenType.TRUE`、`"false"→TokenType.FALSE`），总览数字改为「本次实测 + 命令 +
    快照日期」写法，不再写无来源的固定总数。

## [0.1.0] - 2026-08-17

### 新增

- **编译器核心**：`cypyc` 命令行工具，支持 `transpile` / `compile` / `run` / `hook` 子命令。
- **语法特性**：结构体（struct）、枚举（enum）、trait、泛型、模式匹配、管道运算符（`|>`）、
  列表推导、`let`/`var` 变量语义、`defer`、`go` 协程、`spawn` 线程、指针操作、
  编译期元编程（comptime / meta block）、宏展开、联合类型（union）、SIMD 向量类型。
- **类型系统**：渐进式类型标注、编译期类型检查、类型推断、泛型约束、magic traits。
- **双后端**：Cython 后端（默认）与 Bridge 后端（直接生成 C 代码并编译为 `.pyd`）。
- **增量编译**：增量编译缓存、热重载、动态代码感知系统。
- **测试体系**：`tests/` 与 `test_suite/` 双测试体系，覆盖语法、类型、代码生成、
  集成、性能基准与代码质量检查。

### 修复

- 修复 Bridge 后端链接时硬编码 `python313.lib` 导致非 3.13 环境编译失败的问题，
  改为按当前解释器版本动态生成库名。
- 修复 Bridge 后端缓存未按 Python 版本隔离，导致跨版本 `.pyd` 缓存污染、
  导入失败的问题。
- 修复 `try/except` 无参 `raise` 时异常值为 `NULL`，对 `NULL` 调用
  `PyObject_IsInstance` 导致原生层访问违例（access violation）崩溃的问题，
  改用 `PyErr_GivenExceptionMatches` 进行异常类型匹配。
- 修复 `tests/code_quality/test_code_quality.py` 中 f-string 反斜杠语法错误
  （Python 3.11 不允许），恢复测试收集。

### 变更

- 项目按 FIST 规范完成 fist 化：部署 `PROJECT-SPEC/` 规范体系与 `omega/` 验证框架。
- 清理根目录调试产物、临时日志与散落测试脚本，统一归档到 `docs/`、`reports/`。
- 示例统一收敛到 `examples/` 目录（`demos/` 分类示例 + `legacy/` 历史示例）。

### 文档

- 新增 `CHANGELOG.md`。
- `docs/` 收录使用说明（USAGE.md）、类型推断计划（PLAN_TYPE_INFERENCE.md）、
  语法变更审核（SYNTAX_CHANGE_REVIEW.md）。
- `SYNTAX/` 提供 33 份语法特性文档。
