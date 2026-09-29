# T0r118 · Cypy 自驱组合环 R12 报告（2026-09-29）

- 轮次：R12（推进 → 寻虫 → 修复 → 验证 → 打磨 → 推进），FIST 根单 `T0r118`，
  命名空间 `cypy-loop-20260929`，判据面 Ω-gate，缺陷面 `issue_up`（`report_bug`），
  机制裁决 `laya_decide`，全程 `call_log` 对账。
- 靶面：**泛型声明界（`T: int | float` / `T: Show` / `T: Number`）在使用侧的判定**，闭合 BUG-129。
- 基线（开工时实测，非回忆）：pytest 终版 `2284 passed in 301.08s (0:05:01)`（R11 的 `.fist-loop-20260929/logs/r11_pytest_a2.log`）；
  Ω-gate 终版 `CONCLUSION specs=5 cases=100 passed=100 failed=0 refused=0 accuracy=100.00% rc=0`
  （R11 的 `.fist-loop-20260929/logs/r11_gate_a3.log`）；台账开口按环上登记口径反解 37 块（`ring_r12_start_a1.json` 的
  `ledger_open_at_start`，即 FIST `loop_create` 用的 `baseline_open_bug_count`）。
- 终值（本轮）：pytest `2325 passed in 314.09s (0:05:14)`；自研套件 `✓ Passed: 47` / `✗ Failed: 0` /
  `~ Skipped: 0`；e2e golden `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；
  Ω-gate `CONCLUSION specs=6 cases=123 passed=123 failed=0 refused=0 accuracy=100.00% rc=0`。
- 本轮不写"完成"：语法特性总体仍有 39 块开口（口径 A，§6.1 写明它与环上登记口径的差）；
  §8 列出没做完的部分，§9 是 R13 入口。
- 工作树身份：HEAD 仍是 2026-08-17 的 `17d68b4`，本轮全部改动**未提交**（约 200 个脏路径，
  含并发他轮的在写文件）⇒ 本报告所有"实测"数取自**盘面树**（活树），不取自 `git archive HEAD`；
  引用任何锚点时同时给 `file:line`，行号以盘面为准，提交后可能漂移。

## 1. 本轮靶面与为什么是它

R11 收尾留了三条不自证关闭的入口（`BUG-128` / `BUG-129` / 裁决面三条）。选 `BUG-129` 的理由是省力的**和**：

1. 它是"承诺半落地"型：`SYNTAX/11-generics.md` 的「类型约束」段落早就写了定义侧声明界，
   函数调用位也真判（`corpus/cypy.generic.callsite.json` 里那条 `Generic constraint violation` 门 100% 通过），
   但注解位 / 实例化位**一条都不判** ⇒ 同一份声明界三条路径只有一条消费，属于同一事实多处读取的分叉。
2. 它的存量半径可测：全仓只有 16 份源带约束声明、共 34 处（§3.1 实测）⇒ 开门前就能知道会不会打红既有源。
3. 判据面现成：Ω-gate 的 `errors/stage/contains/matches` 口径在 R8-R11 已打磨过，新增一个 op 的成本低于改语义。

`BUG-128`（struct 方法不代入）与它同族但**面更大**（方法调用从不判的既有程序比违界的程序多得多），
按 R9 的 BUG-99 教训（越界推广打红既有锁）不在同一轮里顺手推广 ⇒ 留给 R13 与 `BUG-135` 一起做。

## 2. 决策（本轮自决，逐条给依据）

| # | 决策 | 依据 |
|---|---|---|
| D-0 | 半径先测后开门，不"改完看看" | `.fist-loop-20260929/measure_r12_constraint_radius.py` 改动前后同集合逐文件比错误集合（§3.1） |
| D-1 | 界判定收进**一处**共用件，三处使用位各接一行 | 函数调用位已有 `_check_generic_constraint`；再写第二份消息合成点就是"同一事实两处读取"的分叉重演 |
| D-2 | 摘掉字面量位自带的窄复制 | 它只取 `getattr(ast,'id')` ⇒ `T: int \| float` 取到 `None` 静默放行；且它已在 R11 的语料里造成"同一个事实两个读法" |
| D-3 | 显式类型实参构造位只对 class/struct 生效 | 函数由 `_visit_Call` 那份统一判，两边都判会给同一条界两笔账 |
| D-4 | 去重按**整条消息**而不是按节点 | 注解位节点会被多处重复访问（`_visit_GenericType` 与所在声明各访问一次），按节点去重会把两笔不同的账并成一笔 |
| D-5 | 构造位不写类型实参时的推断**不做**，另立单并钉 `errors: 0` | 收紧它是语义推广（要从字面量反推实参），面比 D-1 大；R9 教训 ⇒ 不顺手推广 |
| D-6 | 台账地板只上调不下调：`FLOOR_SPECS 5→6`、`FLOOR_CASES 100→123` | 判据基线（`tests/regression/test_corpus_pairs.py:34-35`）是防语料缩水的棘轮，改语义轮必须让它变严 |
| D-7 | 两套测试体系 + e2e + Ω-gate 全跑，不跑单文件凑绿 | 项目规范：`test_suite/` 不在 pytest 收集面，pytest 全绿照不到它 |
| D-8 | 台账/报告里的数字一律运行时反解，段落戳用写盘瞬间的 UTC | 本轮就是被这条打回两次（§6.4），所以派生数由脚本 `format` 现算，不手敲 |
| D-9 | 不 commit、不 push，不动别人在写的文件 | 用户约束；工作树含并发他轮的脏改动 |

## 3. 寻虫：实测面与两张新单

### 3.1 探针与存量半径

半径件 `.fist-loop-20260929/measure_r12_constraint_radius.py`（改动前 `r12_radius_before.json`、
改动后 `r12_radius_after.json`，同一份文件集合、同一口径）：

- 改动前：`CONCLUSION phase=before sources=206 with_cons=16 decls=34 parse_refused=3 real_crashes=0 out=r12_radius_before.json`
  —— 口径：106 份盘面 `.cypy` + 100 对既有 corpus 源，历轮 `.fist-loop-*` scratch 树排除；
  `parse_refused=3` 是既有解析拒绝样本（本轮不当缺陷算），`real_crashes=0`。
- 改动后：`CONCLUSION phase=after new_red_sources=0 gone_red_sources=0 touched=0 unchanged_non_cons=190 new_red_without_constraint_decl=0 real_crashes=0`
  —— **开门不牵连任何既有源**：新增红 0、消失红 0、非约束源变动 0。

探针件 `.fist-loop-20260929/probe_r12_ctor_inference.py`（`.fist-loop-20260929/logs/r12_probe_a2.out`）打的是六形现状：
注解位违界、显式实参构造位违界、字面量位违界、元数与界并存、去重、以及**构造位不写类型实参**那一形
⇒ 前五形本轮判定，第六形 0 诊断（这就是 D-5 与 `BUG-135`）。

### 3.2 新立缺陷单（先取号再写台账，两张均开口留证据）

入账件 `.fist-loop-20260929/file_r12_bugs.py`，回执 `CONCLUSION filed=2 refused=0 skipped=0 new_ids=2 headers=136 call_log={"rows": 3, "error_rows_ok_needle": 0, "report_bug_rows": 2}`：

- `BUG-134`（low，[判据面·诊断文案]）：违界诊断的归属文案写成 `in call to '<unknown>'` ——
  类/结构体的注解位不是"调用"，`<unknown>` 又不是任何可定位的符号 ⇒ 用户按报告找不到主语。
  修法要在消息合成点分「注解位 / 调用位」两种归属，涉及 `BUG-126`（行号 +1）同一片代码 ⇒ 另轮带判据收。
- `BUG-135`（medium，[analyzer]）：构造位 `Box(v=1)` 不写类型实参时不做推断（与 `BUG-128` 同一推断层）。
  本轮把它**钉成主张**：语料里 `ctor_infer` 那格期望 `errors: 0`，回归锁 `test_inferred_constructor_position_still_unjudged`
  同向钉 ⇒ 将来做推断时这两处必须一起翻红，不会被静默改成"看起来已经做了"。

### 3.3 边界审视（输入域四类）

- 空/缺：`T: int | float` 的联合界在字面量位是本轮的**主靶**（窄复制在那儿恒放行）；
  空约束表 `class Plain<T>` 三处使用位都短路返回，0 诊断。
- 重复/幂等：同一注解位被重复访问时按整条消息去重 ⇒ 语料 `ann_dup` 与反例格 `dedup_would_double`
  成对（后者摘掉去重必须变多，两格基数都写进本格，不用空集合 `all()`）。
- 并发/时序：本面是编译期单遍判定，无并发输入域。
- 资源极限：无堆、无循环、无 I/O，尺寸类输入对本形态不可判定 ⇒ **不放恒真门**，依据写在上一句。

### 3.4 收口之后的 R13 入口探针（新账一张，不挂 R12 根单）

收口腿跑完（`ring_r12_close_a1.json`）之后，我按 §9 列的入口先打了 12 形探针
（`.fist-loop-20260929/probe_r13_type_alias.py`，走 `scripts/omega_gate.py` 那份 `execute()`，
日志 `.fist-loop-20260929/logs/r13_probe_alias_a2.out`）—— 打的是手册 `SYNTAX/02-type-annotations.md:92`
承诺的「泛型类型别名」。结论行按 `stage/errors` 计数：

| 形 | 内容 | 读数 |
|---|---|---|
| `A_basic_alias` | 非泛型别名 `type Point = tuple<int, int>` | 0 诊断（对照，正常） |
| `B/D/E/F` | 泛型别名 + **正确**实参（含 codegen 出 31 行产物） | 0 诊断（对照，正常） |
| `G_wrong_inner` | `bad: Result<int> = (True, "x")` | **0 诊断**（应为内层类型不符） |
| `H_wrong_flag` | `bad: Result<int> = (1, 2)` | **0 诊断** |
| `J_alias_wrong_kind` | `type Pair<T> = tuple<T, T>` + `bad: Pair<int> = (1, "s")` | **0 诊断** |
| `I_unknown_in_alias` | `bad: Result<NotAType> = (True, 1)` | **0 诊断**（类型实参不存在也不报） |
| `C_alias_bound_use` | 定义侧写约束界 `type Num<T: int \| float> = ...` | 解析失败 `Expected IDENTIFIER, got COLON at 1:11` |

错误程序与正确程序得到**同一个读数** ⇒ 别名被登记但参数从不代入；而状态表 `02-type-annotations.md` 那行原本写
「✅ 完整 / 无」⇒ 主张宽于实现（同族第二害）。两处一起入账为 `BUG-136`（medium，先取号再写台账：
回执 `file_r13_alias_bug.json`，`new_ids=['BUG-136']`、三向对照 `md ↔ bug_list(dict/count=137) ↔ call_log`），
状态表那行同步改成 ⚠ 部分。`L_plain_class_control`（`b: Box<str> = Box(1)` 也 0 诊断）**不另立单**：
它就是 `BUG-135` 写的"构造位不写类型实参 ⇒ 不推断、成员不代入"，探针只补了一形。

## 4. 修复：一处共用件 + 三处接线

产品码改动只有 `cypyc/analyzer/type_checker.py` 一个文件、四处（行号取盘面）：

| 位置 | 作用 |
|---|---|
| `cypyc/analyzer/type_checker.py:1311` | 新增 `def _check_declared_bounds(self, decl, binding, node)`：读 `decl.generic_constraints`，逐参过既有 `_check_generic_constraint`；按整条消息去重 |
| `cypyc/analyzer/type_checker.py:1361` | 显式类型实参构造位接线（`func_name not in self.func_defs` ⇒ 只对 class/struct，见 D-3） |
| `cypyc/analyzer/type_checker.py:2456` | 结构体字面量位：原窄复制四行**摘掉**，改调共用件（D-2） |
| `cypyc/analyzer/type_checker.py:3995` | 注解位接线：元数诊断之后，`zip(generic_params, 实参)` 成 binding（D-4 的重复访问点） |

产物侧本轮零改动：声明界是编译期判定，擦除约定沿用 R11（`tests/test_generic_bounds_r12.py` 里那支
codegen 擦除锁钉住"界判定不许改变出码文本"）。

手册：`SYNTAX/11-generics.md:107` 起新增「声明界在使用侧的判定」规则 1-4，先立条款再动实现；
规则 4 明确写出**不判的一面**（构造位不写类型实参时不做推断）⇒ 文档不遮 `BUG-135`。

## 5. 验证

### 5.1 判据层扩容

- 新 Ω-spec `corpus/cypy.generic.bounds.json`：23 对，指纹 `fnv1a64:65b49102e98d2fa0`，
  生成件 `.fist-loop-20260929/make_corpus_r12.py` 在落盘前逐条走 `execute + judge`，一条不符就拒写。
  本轮它拒了自己 3 次：`stage` 取值猜成 `check`（带诊断的 typecheck 实测是 `ok`）、
  trait 实现忘写 `impl Show for Impl:`、typeclass 语法写成 `typeclass Number for T:`
  （实际是 `typeclass Number:` + `impl typeclass Number for int:`）。
- 回归锁 `tests/test_generic_bounds_r12.py`：18 支，含两支结构针 ——
  `test_struct_literal_path_reuses_the_shared_checker`（源码里不许长回窄复制：
  `_visit_StructLiteral` 必须含 `_check_declared_bounds` 且不含旧消息合成串）、
  `test_bound_diagnostic_points_at_the_annotation_site`（诊断行列按源反解指向注解位）。
- 台账地板：`tests/regression/test_corpus_pairs.py:34-35` 的 `FLOOR_SPECS = 6` / `FLOOR_CASES = 123`（D-6）。

### 5.2 承重矩阵（6 格，`verify_r12_locks.py`）

终版 `CONCLUSION cells=6 load_bearing_cells=4 all_red=True comment_control_zero_red=True bad=[] rc=0`
（`.fist-loop-20260929/logs/r12_matrix_a2.out`；a1 那版的读数见 §5.4）。逐格读数：

| 格 | 变异 | pytest 红 | Ω-gate 红 | 身份探针 |
|---|---|---|---|---|
| L0 | 现树不动 | 0（144 passed） | 0 | — |
| M1 | 摘注解位接线 | 16 | 8 | `kind=摘除, anchor_gone=True` |
| M2 | 摘显式实参接线 | 2 | 1 | `kind=摘除, anchor_gone=True` |
| M3 | 字面量位退回窄复制 | 3 | 1 | `kind=替换, anchor_gone=True` |
| M4 | 共用件短路（三处全成装饰） | 22 | 11 | `kind=替换, anchor_gone=True` |
| M5 | 只改注释（对照格） | **0** | **0** | `code_unchanged=True, comment_actually_changed=True` |

L0 那行的 Ω-gate 单 op 读数：`CONCLUSION specs=1 cases=23 passed=23 failed=0 refused=0 accuracy=100.00% rc=0`；
M4（最狠那格）：`CONCLUSION specs=1 cases=23 passed=12 failed=11 refused=0 accuracy=52.17% rc=1`。

### 5.3 三套体系 + Ω-gate + e2e 终值（终版日志逐字）

| 体系 | 终值 | 日志 |
|---|---|---|
| pytest 全量 | `2325 passed in 329.95s (0:05:29)`，`pytest_rc=0` | `.fist-loop-20260929/logs/r12_pytest_a4.log` |
| 自研 `test_suite/` | `✓ Passed: 47` / `✗ Failed: 0` / `~ Skipped: 0`，`suite_rc=0` | `.fist-loop-20260929/logs/r12_suite_a2.log` |
| e2e golden | `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`，`e2e_rc=0` | `.fist-loop-20260929/logs/r12_e2e_a1.log`（收口后复跑 a2 见下） |
| Ω-gate 全 spec | `CONCLUSION specs=6 cases=123 passed=123 failed=0 refused=0 accuracy=100.00% rc=0` | `.fist-loop-20260929/logs/r12_gate_all_a2.log` |

顺序说清楚，免得读成"改完没复验"：表格里的数是**交完全档 formatter 之后**的复跑
（pytest a3→a4、套件 a1→a2、Ω-gate a1→a2、矩阵 a2→a3，四份复跑同数）；
a3 那份 `2325 passed in 314.09s (0:05:14)` 是开批门实际读取的那一份
（`run_r12_ring.py` 的日志常量钉的是 a3 路径），两次的**计数**相同、**墙钟**差 15.86s ⇒ 再次印证墙钟不是产品信号。

Ω-gate 的期望对数不写死：收口件的开批门拿 `corpus` 目录下每份 spec 逐份相加（本轮反解 = 123）与门禁结论行对表，
不等就 refuse ⇒ 少挂一个 spec 会被这道门看见，而不是被"cases=119 也算过"糊过去。

### 5.4 中途红与作废

- `.fist-loop-20260929/logs/r12_gate_a1.log` 的 `CONCLUSION specs=6 cases=119 passed=119 failed=0 refused=0 accuracy=100.00% rc=0`
  **作废**（那是 23 对语料只落 19 对时的读数）；终值以 `r12_gate_all_a1.log` 为准。
- 承重矩阵 a1 版 `CONCLUSION cells=6 load_bearing_cells=5 all_red=False comment_control_zero_red=True bad=["M5 只改注释（对照格，必须 0 红） 摘掉后 0 红 ⇒ 锁不承重"] rc=1`：
  错在**尺**不在锁 —— `identity()` 先按字符串相等分类，把"只改注释"那格误判成"替换"。
  修法是剥注释后再分类（`verify_r12_locks.py`），a2 才成立；a1 的 json 另存 `verify_r12_matrix.a1.json` 未被覆盖。
- 台账段落被连写坏两次，见 §6.4。

## 6. 账面

### 6.1 缺陷账（口径写明）

`memory/bugs.md` 本轮终态（脚本反解，非手加）：抬头 137 块、开口 39 块、`### FIXED` 段 90 个。
口径 A：块内既无 `### FIXED` 也无 `### DUPLICATE` 记作开口 —— `### AMENDMENT`、`### OUT`、`### WONTFIX`
在口径 A 里也算"已闭"，所以这个 38 与 FIST 隔离库的 `status='OPEN'` 计数**不同库不同口径**，不可互相指认。
39 块按严重度：5 high / 23 medium / 11 low（三个数都由核验件从账上反解并逐格比，不是我把分档数相加）。
本轮之后**泛型/类型约束族仍开着**的：`BUG-49`、`BUG-121`、`BUG-122`、`BUG-128`、`BUG-135`
（`BUG-120` 是同族但 summary 走"手册形态"措辞 ⇒ 不在这条内容式反解里，见 §9 第 4 条）——
即"泛型/类型约束族开口 6 条（49+121+122+128+135+136）"，这份集合按正文内容反解，不按轮次编号猜。
同一本账再按**环口径**（`OUT`/`WONT` 也算闭）反解是 38 块 —— 差的那 1 块是 `BUG-77`（段内标 `### OUT`）；R12 收口当时登记的 37 块仍记在 §1 的基线句里（收口后 R13 入口探针又入账一张，见 §3.4），两者不是同一时刻的数；
FIST `loop_create` 的 `baseline_open_bug_count` 用的正是环口径那个数（见 `ring_r12_start_a1.json`）。

本轮账面动作：
- `BUG-129` 追 `### FIXED(R12 …)` 段（含修法、半径、判据、手册、未随本单关闭的相邻面五段）；
- `BUG-134`、`BUG-135` 入账未修（§3.2）；`BUG-136`（泛型类型别名不代入不判）在**收口之后**由 R13 入口探针入账，不挂 R12 根单（§3.4）；
- 修本环自己写坏的台账：4 个畸形段落戳 + 6 处未插值占位（§6.4）。

**存量读数（不是门）**：台账里还有 17 处时钟戳缺 `Z` 后缀、1 处只到分钟精度（`…T10:28Z`）。
这些**不能**补 `Z` 了事 —— 落笔时没记时区，补上等于替历史宣布"那是 UTC" ⇒ 只记录、只认账，不改动。

### 6.2 FIST 侧（start 阶段）

根单 `T0r118`（带 `[omega:required]`），`task_plan_deep` 拆出 4 枝 12 叶，
判据（`omega_spec_create` + `omega_spec_review approve`）挂在每支叶上，`run_check` 的步序按 (状态, specs 行数) 分派。
首装回执 `ring_r12_start_a1.json`（40 次调用、0 拒绝）；复跑自证幂等（`.fist-loop-20260929/logs/r12_legs_a1.out`）：
`CONCLUSION stage=start root=T0r118 rows=17 leaves=12 faces_missing=0 calls=2 refused=0 benign=0 tag=a2`
—— 第二次跑只剩 2 次调用（读树 + 复用根单），没有重发判据、没有重派叶。

机制裁决 `laya_decide` 的入参写的是本轮真问题（三处使用位收一处、推断面另轮、
`T0r112`/`T0r113` 两根待领取叶无退役出路），回执正文在 `ring_r12_start_a1.json` 的 `laya` 字段。

### 6.3 FIST 侧（close 阶段）

本节按固定顺序生成，先立顺序再谈内容：出口件（本报告 §1-§6.2 与 §7-§9）→ 引用核验 → 收口腿 →
由 `.fist-loop-20260929/fill_r12_report.py --stage post` 把逐字回执追加在本节末尾 → 重跑引用核验。
所以开批门读的是**补记前**那一版（其 `report_bytes` 与当时的核验件逐字相等），
补记后的一致性由**最后一次**核验担保 —— 两次核验各自钉一个版本，不存在「同一文件自己比自己」的恒真。

（收口腿已在盘，补记于 2026-09-29T09:33:40Z，回执 `.fist-loop-20260929/ring_r12_close_a1.json`。）

（收口腿已在盘，补记于 2026-09-29T09:38:37Z，回执 `.fist-loop-20260929/ring_r12_close_a1.json`。）

**R12 收口腿逐字回执（`--tag a1`）**

- 开批门四道读数（每条各自取自对应日志，不合并成一个「再序列化后的引用」）：
  - 终版 pytest：`pytest_rc=0`
  - 自研套件：`{"passed": 47, "failed": 0, "rc": "suite_rc=0"}`
  - e2e golden：`[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
  - Ω-gate：`CONCLUSION specs=6 cases=123 passed=123 failed=0 refused=0 accuracy=100.00% rc=0`（期望对数从 corpus 目录反解 = `123`）
  - 台账脏检：`{"dblstamp_lines": 0, "residue_lines": 0, "hard_bad_stamps": 0, "read_clock_no_Z": 17, "read_minute_precision": 1}`；承重矩阵：`{"cells": 6, "mutation_cells": 4, "load_bearing": 4, "all_mutation_red": true, "control_cells": 1, "control_zero_red": true, "l0_green": true}`
- 根与树：根 `T0r118.1`，逐叶终态 rollup `{"已完成": 17}`，枝干 `{"T0r118.1": "已完成", "T0r118.2": "已完成", "T0r118.3": "已完成", "T0r118.4": "已完成"}`，待领取叶 `0`，根终态 `已完成`。
- 调用账：calls=89 refused=0 idempotent=0 benign=0；本窗口 `call_log` 红行（ok=0 口径）0 行，旧口径 `%__error__%` 同窗 `0` 行（两口径并印：恒 0 那把尺不再单独承重，见 R11 报告 §6.4 与 BUG-131）。
- 组合环推进腿（服务端、同一会话内走完）：ticks_ok=6/6，门表 `{"create_ok": true, "status_pre_ok": true, "all_ticks_ok": true, "status_post_ok": true, "cross_process_negative_confirmed": true, "round_advanced": true, "mode_sequence_matches_declared_steps": true, "current_idx_progression": true, "no_early_stop": true}`，round `0→1`，mode 序列 `["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"]`。
- 逐叶步序：
  - `T0r118.1.1`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.1.2`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.1.3`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.2.1`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.2.2`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.2.3`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.3.1`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.3.2`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.3.3`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.4.1`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.4.2`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
  - `T0r118.4.3`：已领取 → 已完成（步序 `{"execute": "ok", "run_check": {"state": "passed", "ok": true}, "submit": "ok", "verify": "ok"}`）
- 拒绝：无（`refusals` 为空数组）。
- 收口腿结论行（逐字取自 `.fist-loop-20260929/logs/r12_ring_close_a1.out`）：
  `CONCLUSION stage=close root=T0r118 root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0 calls=89 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 call_log_error_rows=0 old_needle_rows=0 tag=a1`
- 终局自证（第二把尺 `.fist-loop-20260929/r12_self_certify.py`：与核验件同读同一批证据，但**不共享判定代码**，
  专查「报告里的引用是否只存在于报告」与「报告点名的编号是否都在账上」）：判定的逐字行抄自
  `.fist-loop-20260929/logs/r12_selfcertify_a2.out`。顺序是刻意的 —— 先跑一次"本节不抄判定行"的形态拿到
  `rc=0`，再把那一行抄回来；反过来先抄再跑就永远不收敛，因为 `orphans=` 数的是"本节引用在别处存不存在"，
  被抄进本节之后它就成了自己的输入（带计数的 `claims=` 那行同理，故本节只抄不含报告字数量的那一行）：
  `CONCLUSION_STABLE self_certify orphans=0 missing_bug_ids=[] rc=0`

### 6.4 本腿自犯的坏尺与坏模板（下列每一条都由现算/复跑抓出，不靠回忆；条数不写死，见核验件的反查）

1. **未插值占位一路落盘**：`amend_r12_ledger.py` 的段落模板用 `str.format`，占位却写成 `{{CASES}}` ——
   双花括号在 `str.format` 里是**转义字面量**（那是 f-string 的写法），于是 `{CASES}`/`{FP}`/`{LOCKS}`
   原样进了台账。第二次写盘（改派生数之后）又叠了 6 处。⇒ 现在段落级有三条会红的门：格式化后
   `[{}]` 计数为 0、`{CAPS}` 残留为 0、派生数必须作为子串在场；落盘后再开一条不动点门
   `after_text.count(seg) == len(touched)`（"我要写的那段逐字进去了"，顺带挡 CRLF 改写与半截写）。
2. **段落戳双裹**：模板写 `2026-09-29T{ts}Z）`，而 `{ts}` 本身已是完整 `…T…Z` ⇒ 落盘成
   `2026-09-29T2026-09-29T08:25:31ZZ`。R11 那份 `amend_r11_ledger_bugs.py` 用同一模板，
   所以台账里躺着 **4 个**这样的戳（`repair_ledger_stamps.py` 逐行修：只动戳串，
   三个计数不变、逐行 diff 只落在含坏戳的 4 行上）。上游模板一并改成 `{ts}`，防再犯。
3. **门的口径要钉亲笔区间**：脏检最初写成整档扫 ⇒ 本件的自证被**别轮**的 4 个坏戳顶成永红，
   而按 `(?m)^(?=### )` 切"自己那段"又会越过 `## BUG-` 边界吃到别单正文（实测凭空多出 2 个花括号）。
   现在：门只作用在本件写出的 `seg` 上，整档计数当**读数**印（`SWEEP_WHOLE_LEDGER`）。
4. 尺子的自检钉进了常驻门并实际执行（不是写了不跑）：
   `CONCLUSION selftest=sweep ok=True（两份真实坏样本各打回一格，活台账三门归零）` ——
   样本是上面这两版**真实落盘过的坏产物**（`.fist-loop-20260929/logs/r12_ledger_bad_section.prev.txt` 与同目录的 `.cur.txt`），不是合成串。
5. 幂等守卫复验：`CONCLUSION touched=0（已在账，幂等）`。
6. **补记件的双写**：`fill_r12_report.py` 的"回收自己那段"针写成 `（--tag ` 字面量，而标题实际是
   `（\`--tag a1\`）`（两侧有反引号）⇒ `--refresh` 匹配不上，退化成**再插一份**，报告里同时躺着两份回执
   （字节 +3726 暴露的，不是我看出来的）。修法：从 `.pre_fill` 恢复单副本，把针改成 `（[^*]*?）`，
   并补一条"标记份数"门（首次插入后必须 1、替换分支必须不变）—— 现在它由核验件的
   `close_receipt_appears_once` 常驻把关。同轮还有两处**散文里嵌 ASCII 直引号导致 f-string 语法错**
   （一次在打印件、一次在这次的补记段模板）⇒ 中文串里要引号请用「」。
7. **核验件不能进自己的证据池**：canary 那条被我改了一个字符的结论，上一版被写进 `verify_r12_report.json`
   的 `detail`，而该文件在证据目录里 ⇒ 探针串"在证据中出现"、canary 假绿。现在 `self_output()`
   把 `verify_*_report.json` 与 `*reportcheck*` / `*fill_post*` 剔出证据池。
   派生读数（从回执再 dump 的 rollup/gates 形状）另走"深度相等"这条尺，不混进字节子串那条。
8. **我自己写了一条不合规的风格主张**：§7 原先写"改动文件过 `black`/`isort` 既有口径"—— 实测 `black --check`
   对 8 份文件报 Would 重排（含产品文件），`isort` 也红。真账是：亲笔 7 份现在过 black（已交格式化），
   产品文件是**存量债**（HEAD 自己那份 `black --diff` 现算 1686 行 ±、`isort` 报的是 HEAD 第 1 行的既有导入）
   ⇒ 报告改成两口径写法，并新增 `style_claim_two_tiers` 把这句话钉成会红的门（数错了就红）。
8b. **回读形状假设错 ⇒ 三方对照的一条腿读成空**：入账件的 `bug_list` 回读的是 `dict`（`{count, bugs:[…]}`），
   我按 `list` 假设写判定 ⇒ `bug_list_has_new_summary` 恒 False（看着像"服务端没记上"，其实是我的尺瞎了）。
   现在按形状归一化并把 `bug_list_shape`/`count` 一起印进回执；复跑（幂等守卫 SKIP）自证：
   `bug_list_shape=dict count=137 has_new_summary=True`。
   同轮还暴露一条：§6.4 举例用的**正则字面串**被"逐字引用"那把尺当成日志原文要找 ⇒ 只放行含 `\d` 的串，
   单列 `regex_like_exemption_stays_small` 且封顶 3 条（不悄悄放宽整尺）。
9. **"取第一个匹配"造出空门**：新加的 `post_format_reruns_agree` 第一版用 `Passed: (\d+)` 与 `cases=(\d+)`
   取数 ⇒ 拿到的是套件**第一族**的 18 与 Ω-gate **第一份 spec** 的 24，两侧当然相等，门"PASS"了却没在比终值。
   读 detail 才看见（`suite=18/18 gate=24/24`）—— 修法是按形状取汇总行
   （`Total: \d+ \| Passed:`、`CONCLUSION specs=\d+ cases=`），现在它报 `pytest=2325/2325 suite=47/47 gate=123/123`。
   这条正是既往轮记过的"别取第一个/最后一个匹配当汇总"的同型复发。

## 7. 规范与状态表

- `SYNTAX/11-generics.md:107` 「声明界在使用侧的判定」规则 1-4（先立规范再动实现，与 R11 同法）。
- `SYNTAX_IMPLEMENTATION_STATUS.md:339` 的 `11-generics.md` 行改口径：`BUG-129` 移入"已闭环"，
  未闭环改列 `BUG-120`、`BUG-121`、`BUG-122`、`BUG-128`、`BUG-134`、`BUG-135` 六条。
- `CHANGELOG.md` `[未发布] / 新增` 补 R12 条，并把 R10/R11 那条里已过时的"5 op / 100 对"标注成
  「R11 收口时 5 op / 100 对，现为 6 op / 123 对」⇒ 不留会骗下一个人的旧数。
- 代码风格（**两口径，别混**）：本轮亲笔的 10 份文件（1 份新测试 + 9 份 `.fist-loop-20260929/*` 腿件，
  含收口后的 R13 探针、入账件与终局自证件；清单写死在核验件的 `my_writes` 里，加文件就得同时改报告）
  已交 `black`（line-length 100）并复检 clean；产品文件 `cypyc/analyzer/type_checker.py` 属**存量未格式化**
  —— HEAD 那一份自己就过不了 `black`（`--diff` 现算打出 1686 行 ±（核验件每次重算并对表）），`isort` 报的
  `from typing import Dict, List, Any, Optional` 是 HEAD 第 1 行的既有导入（本轮没碰导入）
  ⇒ **不交整档 formatter**（那会产生不可审的千行差并把并发他轮的改动裹进来），亲笔新增的函数按 100 列手写。
  这条口径由核验件的 `style_claim_two_tiers` 现算把关（亲笔清单必须全 clean，产品文件不参与）。

## 8. 没做完什么（不写"完成"）

1. 构造位类型实参推断没做（`BUG-135`），且本轮把它钉成 `errors: 0` 的主张 —— 做它的人必须同时翻红两处。
2. 违界诊断的归属文案仍误导（`BUG-134`）；诊断行号 +1（`BUG-126`）仍在，本轮**没有**动它，
   因为修它会打红一批钉死 `at L:C` 的既有锁，需要单独一轮带着判据迁移。
3. `BUG-128`（struct 方法不代入）未动，与 `BUG-135` 同一推断层。
4. 特质界/typeclass 界只判"显式写了类型实参"的位；裸名 `let x: Box = Box(1)` 仍按擦除不报（R11 既定口径）。
5. 泛型类型别名不代入不判（`BUG-136`，§3.4 探针 12 形实测）—— 本轮只入账未动实现；
6. 台账存量戳不规范 17 + 1 处（§6.1）只记录未改；`T0r112`/`T0r113` 两根仍停"拆分中"（`BUG-106` 无退役出路）。
7. 本轮改动**未提交**（用户约束）⇒ HEAD 与盘面的差距仍是约 200 个脏路径，回归锁的"已入库"状态尚未成立。

## 9. R13 入口（按省力排序）

1. `BUG-136` 泛型类型别名代入（§3.4 探针 12 形已在盘）：与 `BUG-135` 同一处机制（别名/构造位都不建 binding），先做别名展开再做构造位推断可共用一次回归；成对反例已备好（G/H/J/I 四形）；
2. `BUG-126` 诊断行号 +1：改动点集中（消息合成处），但要一次性过一遍所有钉 `at L:C` 的锁 ——
   先列清单再动，清单从 `tests/` 反解，不手写。
3. `BUG-134` + `BUG-135` 同批：归属文案与推断面都在 `_check_declared_bounds` 的上下游，一次做完可少一轮回归。
4. `BUG-128` struct 方法代入：与 class 分支同一形状，先测半径（同一件 measure 脚本换个针）再决定收不收。
5. 手册形态三条 `BUG-120`、`BUG-121`、`BUG-122`：要的是**裁决**（支持还是显式硬拒），不是实现 —— 见 D-5 的教训，
   别在实现轮里顺手替文档做决定。
6. 账面：`T0r112`/`T0r113` 的待领取叶仍无出路 —— 现算自 `fist-mbt.db`：`T0r112` 待领取 15（另 6 支"拆分中"、8 支已完成）、`T0r113` 待领取 4（另 3 支"拆分中"、14 支已完成）⇒ 合计 19 支。要么给 `reopen`/退役机制，要么转结流程债，不能靠"报告里不提"。
