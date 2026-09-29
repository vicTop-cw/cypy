# T0r117 · Cypy 自驱组合环 R11 报告（2026-09-29）

轮次：推进 → 寻虫 → 修复 → 验证 → 打磨 → 推进
命名空间：`cypy-loop-20260929` · 根单 `T0r117` · 驱动 FIST-Mbt（129 工具，`cmd/cli/cli.js serve`）
判据基线（开工时逐字取自 R10 终版实测）：pytest `2241 passed` rc=0、Ω-gate `specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0`、自研 `Total: 47 | Passed: 47`、e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`。

---

## 1. 本轮靶面与为什么是它

R10 收口泛型调用点后，`SYNTAX/11-generics.md` 的「明确不支持」表里挂着四行，其中第一行就是**手册自己给了完整范例、解析器却吃不下的泛型类**：

- 手册 `SYNTAX/11-generics.md:107-125` 写的是
  `class Box<T>: def __init__(self, content: T): …` + `let int_box: Box<int> = Box<int>(42)`；
- 实测形态：`Expected COLON, got LT at 1:10`（探针 16 例里 14 例卡在这一条，见 `.fist-loop-20260929/logs/r11_generics_probe1.out`）。

同一件事在 struct 上是通的（`struct Wrap<T>` 解析、出码、字段表都在），所以这不是"要不要支持泛型类"的设计分歧，而是**同一事实两处读取不一致**的老形状（R6 的 `.fields/.body`、R8 的 `ClassDef.body`）：`ClassDef` 节点连 `generic_params` 属性都没有，`_parse_class_def` 也不看尖括号。

寻虫半径因此定在：定义侧解析 → 使用侧元数 → 接收者代入 → 产物擦除，四段一条链，配一份新 Ω-spec。

## 2. 决策（本轮自决，逐条给依据）

| 编号 | 决策 | 依据 |
|---|---|---|
| D-R11-1 | 定义侧参数表**合并实现**：`Parser._parse_type_param_list` 由 class 与 struct 共用，空参数表文案两处逐字相同 | 探针实测两形原本各写一份；合并后 `.fist-loop-20260929/logs/r11_locks_a8.out` 的 L1 格退解析器 ⇒ 34 红（承重） |
| D-R11-2 | 使用侧元数**共用一条文案**：`TypeChecker._generic_arity_diagnostic` 同时服务注解位与调用位，不新造第三种说法 | R10 的 `corpus/cypy.generic.callsite.json` 已钉住这两句；新门必须复用而非并列（并列=两处读取） |
| D-R11-3 | **裸名按擦除**：`let b: Box = Box(1)` 合法、0 诊断；成员类型取 `object` | 先实测才开门：`.fist-loop-20260929/logs/r11_baseline_ann2.out` 扫 1147 份 .cypy，注解位 55 处、元数违例 0 ⇒ 开门不打红既有源 |
| D-R11-4 | 代入落在 `_visit_Attribute` 的 class 分支（按接收者类型实参逐位），**不在裸名表里装形式参数** | `type_map['get']` 是按裸名建的表，装不下接收者；原样登记会把 `T` 当返回类型外泄成 `expected int, got T`，把有效程序打红 |
| D-R11-5 | struct 侧**只补裸名擦除，不补方法代入**：方法代入会把"从不判"的程序打红，面比 class 大 ⇒ 立 `BUG-128` 转结 | R9 的 BUG-99 教训（越界推广打红既有锁）；对照实测见 `.fist-loop-20260929/logs/r11_subst2.out` 的 S6/S9/S10 与 S13 |
| D-R11-6 | 定义侧声明界（`T: int \| float`）在注解位/实例化位**不判** ⇒ 立 `BUG-129`，本轮只保证解析收下并落 `generic_constraints` | 实测两形 0 诊断（class 与 struct 同），函数调用位才判；补齐要把那条路径抽成共用件并处理特质界，属另轮 |
| D-R11-7 | 报告数字一律由填充件从终版日志反解写入，正文不手加 | `fill_r11_report.py`；引用核验 `verify_r11_report.py` 会把每个逐字结论回 evidence 比对 |

## 3. 寻虫：实测面与四张新单

### 3.1 探针（修复前 → 修复后）

| 形态 | 修复前（`.fist-loop-20260929/logs/r11_generics_probe1.out`） | 修复后（`.fist-loop-20260929/logs/r11_generics_probe2.out`） |
|---|---|---|
| `class Box<T>:` 手册范例 | `stage=parse`，`Expected COLON, got LT at 1:10` | `stage=ok` errors=0，`generic_params=['T']` |
| `class Pair<T, U>:` | 同上（col 11） | errors=0，`generic_params=['T', 'U']` |
| `class Num<T: int \| float>:` | 同上 | errors=0，`constraints={'T': UnionType(...)}` |
| `class Box<T> extends Base:` / `class Box<T>(Base):` | 同上 | errors=0，`bases` 仍在 |
| `class Box<>:` | 同上（被当成未知前缀） | `Generic parameter list cannot be empty at 1:7`（与 struct 逐字同文案） |
| `cdef class Box<T>:` | 同上（col 15） | 解析成 `ExprStmt + ClassDef`，`Undefined name 'cdef' at 1:1` ⇒ 新单 BUG-127 |

### 3.2 新立缺陷单（先取号再写台账，四张均开口留证据）

| 单号 | 定性 | 活证据 |
|---|---|---|
| BUG-126 | 诊断行号恒 +1：2 行文件的 `Return type mismatch` 报 `3:1` | `measure_r11_substitution.py` + `.fist-loop-20260929/logs/r11_subst1.out`；module-level 最小样例同形复现 ⇒ 既有缺陷，非本轮引入 |
| BUG-127 | `cdef class` 不是本门面语法却不被硬拒；`ClassDef.is_cdef` 从解析器恒 False ⇒ codegen 的 cdef-class 分支不可达 | `.fist-loop-20260929/logs/r11_generics_probe2.out` C6；`_parse_class_def` 全仓唯一调用点在 `cypyc/parser/parser.py:1218` 且不带实参 |
| BUG-128 | 泛型 struct 的**方法**调用不代入（只扫 `.fields`）⇒ `Wrap<str>.get()` 在 `-> int` 里 0 诊断 | 与 class 侧同形成对：`.fist-loop-20260929/logs/r11_subst2.out`（class 报 `expected int, got str`） |
| BUG-129 | 定义侧声明界在注解位/实例化位不判（class 与 struct 两形同） | `class Num<T: int \| float>` + `Num<str>` ⇒ errors=[]；对照 `cypy.generic.callsite.json` 里函数调用位是判的 |

### 3.3 边界审视（输入域四类）

- **空/非法**：`class Box<>:` 硬拒；`Plain<int>()`（无类型参数被挂实参）报 `Type arguments on non-generic`；两形都在 corpus 里。
- **嵌套极值**：`list<Box<int>>`、`Pair<int, str>` 逐位、`l.next().next()` 链式接收者报 `expected int, got Link[int]`（证明代入可复合而非退化成 object）。
- **成对反例**：每个"代入生效"的正例配一个必红反例（`.fist-loop-20260929/logs/r11_subst2.out` 的 S2/S3、S4/S5、S12/S13、S9/S10）——只验正例的话，把成员类型退化成 `object` 也能全绿，那是假绿。
- **资源极限**：本面是编译期语法/代入判定，无堆、无循环、无 I/O ⇒ 对该形态不可判定，依此**不放恒真门**，只把依据写在本节。

## 4. 修复：四处改动与调用面

| 文件:行 | 改动 | 调用面复查 |
|---|---|---|
| `cypyc/parser/parser.py:329-347` | `ClassDef` 增 `generic_params` / `generic_constraints`，默认空表/空字典（不是 None） | `_first_classdef(...).generic_params` 直读；非泛型类读回 `[]`/`{}` |
| `cypyc/parser/parser.py:1599-1623` | 新 `Parser._parse_type_param_list`：class/struct 共用，含空表硬拒与 `T: Bound` 约束 | 两形文案逐字相同（锁 `test_empty_param_list_wording_is_shared_with_struct`） |
| `cypyc/parser/parser.py:1628` + `:1657` | `_parse_class_def` / `_parse_struct_def` 各自只调用它；构造点把两张表挂回节点 | 三种前缀 + `cdef` 反例的解析回读见 §3.1 |
| `cypyc/analyzer/type_checker.py:1296-1311` | 新 `_generic_arity_diagnostic`：元数与非泛型两条文案的唯一产生处 | 注解位（`:3964-3972`）与调用位（R10 的 `_bind_explicit_type_args`）都走它 |
| `cypyc/analyzer/type_checker.py:2513-2534` | class 分支按接收者类型实参逐位代入后再解析 `.body` 里的 LetStmt/FuncDef | `Box<int>.content`→int、`Box<str>.get()`→str；裸名→object |
| `cypyc/analyzer/type_checker.py:592-608`、`:643-646` | `_visit_ClassDef` 记录所属类的形式参数名；`_visit_FuncDef` 不把 `T` 登进裸名表 | `type_map['get']` 读回不是 `T`（锁 + 矩阵 L4 格承重） |
| `cypyc/analyzer/type_checker.py:3964-3972` | 注解位元数判定（同一节点按整条消息去重，不叠第二笔同事实的账） | 每个违例程序恰报 1 条（锁 `test_arity_wording_is_shared_between_annotation_and_callsite`） |

产物侧无需改动即满足擦除：`_visit_ClassDef` 出 `class Box:`，探针实测产物头是 `class Box:` / `class Pair:`，文本内无 `<int>`、无 `-> T`（corpus 的 4 格 codegen 断言钉住，且只在 `stage=ok` 的有效程序上验，避免 `not_contains` 恒真）。

## 5. 验证

### 5.1 判据层扩容

`corpus/` 从 4 份 71 对 → **5 份 100 对**（新 op `cypy.generic.class`，29 对，指纹 `fnv1a64:90f410a1d1cd0fd8`）。
回归地板 `tests/regression/test_corpus_pairs.py` 同步 `FLOOR_SPECS=5`、`FLOOR_CASES=100`。
生成件 `.fist-loop-20260929/make_corpus_r11.py` 落盘前逐条跑 `omega_gate.execute + judge` 自证，有一条不符就拒绝写 corpus ——
本轮它拒了两次（#20 链式代入我按"应 0 诊断"写、实测报 `expected int, got Link[int]`；#24 拿含类型错误的程序去断言产物），两次都按实测把断言改到真相上。

### 5.2 承重矩阵（7 格）

`python -X utf8 .fist-loop-20260929/verify_r11_locks.py` ⇒ `CONCLUSION cells=7/7 load_bearing=5/5 identity_flips=5/5 comment_control_zero_red=True rc=0`
逐格红数：L1 退解析器 34 · L2 退注解位元数 4 · L3 退接收者代入 18 · L4 退形式参数守卫 1 · L5 退 struct 裸名擦除 2 · L6 只改注释 0。
每格还带**身份探针**（被摘的那一处在副本树里必须读成 False）：5/5 翻假；注释对照格必须 0 红（尺子不在数散文）。
本件的三份坏尺子留档：`.fist-loop-20260929/logs/r11_locks_a1.out`（锚点手抄 ⇒ 三格 ruler_crash）、`.fist-loop-20260929/logs/r11_locks_a3.out`（区间用字符偏移当行数）、`.fist-loop-20260929/logs/r11_locks_a5.out`（结论分母硬编码成 `/5`、`/4`）。

### 5.3 三套体系 + Ω-gate 终值（终版日志逐字）

```
pytest   :: `2284 passed in 301.08s (0:05:01)`（pytest_rc=0）
native   :: `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`
e2e      :: `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
omega    :: `CONCLUSION specs=5 cases=100 passed=100 failed=0 refused=0 accuracy=100.00% rc=0`
```

收集数增量合账（不接受「总数变大了就算稳」）：总数从 2241 到 2284，差 43，拆开是 `tests/test_generic_class_r11.py` 新锁 13 支 + `TestClassBoundary` 拆出的空参数表反例 1 支 + 新 op 的参数化用例 29 对（`tests/regression/test_corpus_pairs.py` 每对一条）；填充件里带 `locks + pairs + 1 == delta` 的合账断言，对不齐就直接 exit。

### 5.4 中途红与作废

`.fist-loop-20260929/logs/r11_pytest_a1.log` 的 `1 failed, 2240 passed` 不是产品回归，而是既有边界锁 `TestClassBoundary::test_class_with_type_param` 的 docstring 就写着「错误写法：带类型参数的类（当前不支持）」—— 它钉的正是 BUG-119 的坏形态。
按既往轮纪律**不删锁、不 xfail**，改成双向格：正向 `class Container<T>:` 必须收下且 `generic_params==['T']`，并新增配对的 `test_class_with_empty_type_param_list`（`class Container<>:` 仍硬拒）。改严后的锁随终版一起绿。

## 6. 账面

### 6.1 缺陷账（口径写明）

`memory/bugs.md` 实测 `headers=134` 个抬头（去重编号 133 个，`BUG-96` 双写仍在）。
口径 A（块内既无 `### FIXED(` 也无 `### DUPLICATE`；`### NOT-FIXED(...)` 按「转结未修」算开口）：
open 块 **37** —— 同一份账在口径 B（闭合段再算上 `### OUT`/`### WONT`）下是 36 块，**两个数不是分歧，是口径**；其中 判据/文档面 3 张（BUG-117、BUG-123、BUG-124），其余 34 张是产品面；
开口块的严重度分布 5 high / 22 medium / 10 low。
`### FIXED` 段总数 84→89，`### AMENDMENT` 段 7→9。
上一轮终态取自 `.fist-loop-20260929/verify_r10_report.json` 的 ledger 段（headers 126 / open 34 / FIXED 84），
本轮的两端数字都由 `fill_r11_report.py` 从账本与核验件反解，正文不手加。
动作明细：BUG-119 追 `### FIXED(R11 …)`（含双向格说明），BUG-120 追 `### AMENDMENT(R11 …)`
（半径缩到"仅手册的 `-> T:` 带冒号形态"，另记 `TraitDef` 没有 `generic_constraints` 落脚点），
BUG-122 追 `### AMENDMENT(R11 …)`（不判存在性的面从函数调用位扩到 class 实例化位/注解位），
新立 BUG-126/127/128/129 四张（先取号再写台账，`file_r11_bugs.json` 逐字留回执）。
`Find_BUG/BUGS.md` 是另一本账（审计轮产品缺陷账），不参与这里的计数。

### 6.2 FIST 侧（start 阶段回执，逐字取自 `ring_r11_start.json`）

根单 `T0r117`；建单后回读 17 行 = 根 1 + 枝干 4 + 叶 12（general 叶 6 与六面一比一，faces_missing=0），
边界叶 6 支（实测 2 + 声明不适用 4）；`claim`+`omega_spec_create`+`omega_spec_review` 三段对每叶各一次，
calls=0 refused=0 benign=0。

### 6.3 FIST 侧（close 阶段回执）

收口回执（逐字取自 `.fist-loop-20260929/ring_r11_close.json`，即修针后的 **a4** 复跑；a3 的读数见 §6.4）：根 `T0r117` 终态 **已完成**；rollup `{"已完成": 17}`；待领取叶 0；calls=21 refused=0 idempotent=0 benign=0；本窗口 `call_log` 红行（`ok=0` 口径）0 行，旧口径 `%__error__%` 同窗 0 行（两口径并印是 §6.4 里 BUG-131 的修法，恒 0 那把尺不再单独承重）；枝干终态 `{}`；入口四道门观测（四条各自逐字取自对应日志；不合并成一份再序列化后的「引用」——那串在证据里根本不存在）：`CONCLUSION specs=5 cases=100 passed=100 failed=0 refused=0 accuracy=100.00% rc=0`、`pytest_rc=0`、`Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`、`[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`。每叶步骤按 (状态, specs 行数) 分派，交付物写成服务端要求的五段式，因此 `docs_check=True` 的 `verify` 是原样通过的（未关门禁）。组合环的服务端推进腿在本会话内走完：九格门 `{"create_ok": true, "status_pre_ok": true, "all_ticks_ok": true, "status_post_ok": true, "cross_process_negative_confirmed": true, "round_advanced": true, "mode_sequence_matches_declared_steps": true, "current_idx_progression": true, "no_early_stop": true}`，回执 `.fist-loop-20260929/r11_loop_drive.json`（`round` 0→1、`next_mode` 与登记的 steps 逐位相同）。

### 6.4 收口腿自己的账：两把坏尺与一条作废的自证句

收口不是一次就成的：第一次真跑（a3）把账收完了却被判成失败，追下去是**我自己的尺子**坏了两处，
外加一条从 R9 就用错口径的自证句。四张单同轮确诊同轮修（BUG-130、BUG-131、BUG-132、BUG-133，回执 `.fist-loop-20260929/file_r11_ledger_bugs.json`：
`{"rows": 5, "error_rows_ok_needle": 0, "error_rows_old_needle": 0, "report_bug_rows": 4}`），台账只追加 `### FIXED` 段，标题行的 `OPEN` 一字未改。

- **a3 为什么"红"**：`CONCLUSION` 逐字 `CONCLUSION stage=close root=T0r117 root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0 calls=105 refused=24 benign=0 call_log_error_rows=0` —— 17/17 已完成、0 支待领取，rc 却被 24 条
  「已通过审核，无需重复创建」判负。根因是守卫针写成 `spec_type='omega'`，而库里实际只有
  `spec`/`check`/`result` ⇒ 恒 0 ⇒ 收口把已 approved 的语料重发一遍（BUG-130）。
  修后同树复跑（a4）：`CONCLUSION stage=close root=T0r117 root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0 calls=21 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 call_log_error_rows=0 old_needle_rows=0`，两次的账终态逐字相同，幂等拒绝从 24 掉到 0。
  配套加了开批门 `spec_kind_guard()`：对着活库读 `distinct spec_type`，三个针值缺任一或库里一行 specs 都没有 ⇒ 拒绝收口。
- **恒 0 的错误计数器**：`call_log` 失败行按 `result_json like '%__error__%'` 取数，而服务端把失败写成 `ok=0` + 纯文本
  ⇒ 同窗口两口径读数 `{"ok_0": 31, "percent_error": 0}`（BUG-131）。**据此作废**：R9/R10 与本轮 a3 之前所有
  「call_log 0 错误行 / benign=0 即无幂等噪声」的自证句——账（任务状态、specs 行）没坏，坏的是那句读数。
  修法是两口径并印，不再让单口径承重。
- **组合环从没在服务端推进过**（BUG-132）：`loop_tick` 自 R9 起 33 条全红。两条成因分开钉——
  键名形状对照 `SHAPE_CONTROL {"只传声明键": {"环查无": 24, "成功": 24, "键名被拒": 0, "其它": 0}, "含未声明键": {"键名被拒": 10, "成功": 0, "环查无": 0, "其它": 0}}`（注入未声明键 10/10 被拒、声明键 0 次键名拒绝），
  以及 `loop_create` 自述的"进程内 LoopRegistry" × 每次调用 spawn 新 serve ⇒ 跨会话必 `loop not found`。
  本轮把 create+6×tick+status 收进同一会话：`CONCLUSION stage=loop_drive ticks_ok=6/6 gates={"create_ok": true, "status_pre_ok": true, "all_ticks_ok": true, "status_post_ok": true, "cross_process_negative_confirmed": true, "round_advanced": true, "mode_sequence_matches_declared_steps": true, "current_idx_progression": true, "no_early_stop": true} evidence=r11_loop_drive.json`（`round` 0→1、mode 序列与登记 steps 逐位相同、
  current_idx 1..5→0），自检件用坏数据把九格门逐格翻红：`CONCLUSION stage=selftest cases=8 bad=[]`。
  **限制照写**：环状态进程内 ⇒ 服务端没有跨轮可审的环账，本报告"环已推进"只指"同会话内 6 步走完且回执全绿"。
- **收口阶段的崩溃形态**（BUG-133）：a2 起跑即 `UnboundLocalError`（根单 id 只在 start 分支赋值），
  失败形态是崩而不是拒。修法：close 起手显式绑定，查无根单则拒绝并落回执
  （「账上查无根单：ns=cypy-loop-20260929 且 description 含 T0r999-不存在的根单前缀 且 parent_id=''」）；负控制是真跑出来的 —— 把前缀换成账上必然查无的名字另存一件（与原文件只差 1 行），
  `CONCLUSION refused=1 stage=close gate_reasons=1`，且该窗口 `call_log` 新增 0 行 ⇒ 拒绝发生在任何 RPC 之前。
- **同名覆写**：`ring_r11_close.json` 被 a4 原地覆写，a3 的读数只活在 `.fist-loop-20260929/logs/r11_ring_close_a3.out` 里；
  负控制件的 refused 回执也写同名文件 ⇒ 跑之前先把 a2 那份另存为 `.fist-loop-20260929/logs/r11_ring_close_refused_a2crash.json`。
  既往轮把这条记成"登记同名覆写不只是留 .prev"，本轮仍然只能靠 `.out` 序列号留痕。

## 7. 规范与状态表

`SYNTAX/11-generics.md` 新增「泛型类的判定口径」规则 1-5（定义侧三种前缀与约束、一份实现两处用、使用侧元数与裸名擦除、按声明顺序逐位代入、产物必须擦除），
并把「明确不支持」表里 `class Box<T>:` 那行**删除**（已闭环），`trait … -> T:` 那行改成带冒号限定；
`SYNTAX_IMPLEMENTATION_STATUS.md` 的 `11-generics.md` 行改为「已闭环 2 op / 未闭环 BUG-120·121·122·128·129」。
规则里的每一句都有 corpus 或锁认领，没有"文档写了但没人判"的主张。

## 8. 没做完什么（不写"完成"）

- 目标「所有语法特性稳定，无 bug」远未达成：账上仍有 **37 块开口**，其中泛型这条链就还挂着 BUG-120/121/122/128/129 五张。
- `class Box<T>` 的**方法体**与 `self.content = content` 的字段类型合流不做（class 的方法虽被遍历，字段赋值不产生类型边）；本轮只保证「声明侧参数表 → 使用侧元数 → 成员类型代入 → 产物擦除」这条链，越界的都是开口单。
- 上一轮的 `T0r112`/`T0r113` 两根仍停「拆分中」：19 支待领取叶没有退役出路（BUG-106），要收必须先给它们真交付物，本轮**不伪造**，故不动。
- 墙钟耗时不当产品信号：pytest 全量随负载在 340-360s 区间摆动，本轮只报计数与 rc。

## 9. R12 入口（按省力排序）

1. BUG-129：把函数调用位的约束判定抽成共用件，让 class/struct 的实例化位/注解位也判声明界（含 `Comparable` 特质界）——与 BUG-109 的类型表达式产生器同批最省。
2. BUG-128：struct 方法代入（收紧面大 ⇒ 先扫 corpus 与 examples 里"方法调用从不判"的存量，再开门）。
3. BUG-126：诊断行号 +1（改它会牵动所有钉死 `at L:C` 的锁，必须先做锁的盘点门）。
4. 裁决面：BUG-121（`f[T](x)` 方括号形态）、BUG-122（类型实参存在性）、BUG-120（手册 `-> T:` 无体签名两案）。
5. BUG-116 判据扩面：26 章语法只有 5 个 op，注解/模式/切片/调用点/泛型类之外的章节仍无 Ω-spec。
6. 驱动件交接（不是产品面，但会决定 R12 的账能不能信）：`run_r11_ring.py` 本轮修了三处尺子 ——
   spec_type 针改走常量并由 `spec_kind_guard()` 对活库自证、错误行口径改 `call_log.ok=0` 并双口径并印、
   组合环收进同一会话（`drive_loop()` + `r11_loop_drive.py` 的九格门与 `--selftest`）。
   R12 复制这些件时**不要抄回旧针**，并且照例把里面的上轮事实（语料下限、基线数、根单前缀）逐个打回占位重填。

---
*本轮全部证据件在 `.fist-loop-20260929/`（探针、基线、生成器、矩阵、环回执 JSON 与日志），禁 commit 红线不变，HEAD 仍是 2026-08-17 的 `17d68b4`，盘面即事实。*
