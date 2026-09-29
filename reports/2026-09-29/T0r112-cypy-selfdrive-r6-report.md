# Cypy 自驱式组合环 R6（2026-09-29）交付报告

- 驱动：FIST-Mbt v0.3.4（129 工具，MCP 2026-07-28 无状态握手），ns `cypy-loop-20260929`，根任务 `T0r112`
- 环：`loop_create` 名 `cypy-selfdrive-20260929`，steps `advance → bugfind → fix_and_merge → verify → polish → advance`
- 决策口径：本轮所有需裁决项由代理自决（见「裁决登记」），前后自洽；未越红线（未 commit、未 push、未改 examples/golden）

---

## 1. 结论

1. **三条历史开口闭环**：BUG-37（位置模式绑定名被判 int 的假阳性）、BUG-36（struct 位置模式不调 `__unapply__`、
   产物访问不存在的 `__f0/__f1`）、BUG-41（tests 同名类遮蔽 6 条用例）。
2. **一条工具面缺陷同轮确诊同轮修**：`scripts/fist.py` 指向上游已迁走的入口、发已被拒的 `initialize`、
   `list-tools` 是恒绿探针、且无条件注入 `namespace/project_dir` 使 `loop_create` 一类工具在调用面不可用
   （账本 BUG-93 / 服务端 BUG-101 线）。
3. **无回归（判据面全绿）**：pytest 全量、自研套件、e2e golden 三套体系见文末终验行；
   修复前后 e2e 均为 `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`，自研套件 `47/47`。
4. **新增账面**：BUG-92（规范缺口，试过两种收紧都被既有判据打红，故只入账）、BUG-94（兄弟仓 serve 横幅）、
   BUG-95（本仓无 `corpus/`、无 `tests/regression/`）、BUG-107（本轮自曝：report_bug 双发 + 编号撞车）、
   BUG-108（BUG-34 的 R6 复验正身）；服务端侧另立 BUG-105（环不落库）、BUG-106（待领取叶无退役出路）。
5. **语法特性稳定度**：模式匹配/结构体位置形态的**提取器形态已可用并有调用面证据**；
   「无 `__unapply__` 且实参元数 > 字段数」这一形态仍不稳定（BUG-92），且 `[int]` 类非法标注会把 AST repr
   写进产物（BUG-108/BUG-34）——这两条是「所有语法特性无 bug」目标下**尚未达成**的部分，不掩饰。

## 2. 证据（全部盘面上可复跑，file:line + 命令）

### 2.1 基线（开工前，冻结被测量面）

| 体系 | 命令 | 实测 |
|------|------|------|
| pytest 全量 | `python -X utf8 -m pytest tests -q -rf --tb=line` | `2119 passed in 661.78s`，0 failed |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | `Total: 47 Passed: 47 Failed: 0`，100.00% |
| e2e golden | `bash scripts/e2e_golden.sh` | `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0` |
| 账本口径 | `bug_list` / `memory/bugs.md` 逐条反解 | 工具面 91 条全报 OPEN；**真开口 12 条**（FIXED 72 / DUPLICATE 1 / NOT 5 / OUT 1） |

日志：`.fist-loop-20260929/logs/base_pytest_b2.log`、`base_native_b1.log`、`base_e2e_b1.log`；
快照：`.fist-loop-20260929/baseline_snapshot.json`（head=17d68b4，commit 日期 2026-08-17，
porcelain=181，manifest=328 —— 本仓 HEAD 远旧于盘面，故回退矩阵底树用盘面快照而非 `git archive HEAD`）。

### 2.2 BUG-37：位置模式绑定名的类型被覆盖成 int

- 根因：`cypyc/analyzer/type_checker.py` `_visit_Pattern()` 无条件 `self.type_map[node.name] = Type("int")`
  （注释自称"暂定"），且 `_bind_pattern_names()` 原本只认 `Name`/`Call`/`Tuple`，不认识
  `ExtractorPattern`/`Pattern`（`Pattern` 用 `.name`，`Name` 用 `.id`，两族节点不同）。
- 修复：新增 `_pattern_slot_types()`（按 SYNTAX/17 提取器优先级取 `__unapply__` 返回元组的实参类型，
  `GenericType` 的实参在 `.args`（parser.py:820-824）；无提取器回落字段声明序；再回落 `object`），
  `_bind_pattern_names()` 补 `Pattern`/`ExtractorPattern`/`StructPattern` 三支路，
  `_visit_Pattern()` 改为「未登记过的名字才补 object」。
- 调用面：`python -m cypyc transpile .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy`
  的 `Return type mismatch: expected str, got int at 8:9` 消失；
  `hunt_e_extractor_positional.cypy` 从 rc=1 变 rc=0。
- 锁：`tests/test_pattern_positional_struct.py::test_positional_binding_takes_slot_type_not_int` /
  `test_positional_binding_falls_back_to_field_order_without_extractor` /
  `test_wrong_return_type_still_reported`（反向对照，防「只是把门拆了」）。

### 2.3 BUG-36：struct 的成员在 `.fields`/`.methods`，采集器只读 `.body`

- 根因：`cypyc/codegen/cython_generator.py:_collect_module_info()` 对 `StructDef` 遍历 `stmt.body`，
  而 StructDef 根本没有 `body`（parser.py:117-135，字段在 `.fields`、方法在 `.methods`；
  分析器同一事实见 type_checker.py:3300 的注释）⇒ `_extractor_types` 收不到 struct、`_class_fields` 恒空
  ⇒ 消费侧 `field_name = fields[i] if i < len(fields) else f"__f{i}"` 永远走占位分支。
  同函数里 `_collect_method_names()` 却已正确读 `.methods` —— 同一份文件内的不对称证明这是疏漏而非设计。
- 修复：新增 `_record_pattern_shape()`：字段序取 `.fields`，提取器标记扫 `.methods`+`.body`，
  并把 `FuncDef` 逐出位置字段（否则 `case Shape(3,4)` 会拿去和绑定方法比较，恒 False 且零诊断）。
- 调用面（真编译，不是单测桩）：
  `python -X utf8 -m cypyc run .fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy`
  → 逐字回执（logs/run_e_after.log 末尾四行）：`a` / `[OK] Execution successful` / `  Output: 0`（程序 stdout 是 `a`，`Output:` 那行打的是返回码 0）；产物逐字含
  `_ext_1 = (_match_subject_1.__unapply__() if hasattr(...) ...)`、`user = _ext_1_a0`，全文无 `.__f`。
  日志：`.fist-loop-20260929/logs/run_e_after.log`。
- 锁：`tests/test_pattern_positional_struct.py::test_struct_extractor_is_called_not_phantom_attr` /
  `test_struct_field_order_drives_positional_pattern` / `test_methods_are_not_positional_fields` /
  `test_class_methods_excluded_from_positional_fields`。

### 2.4 BUG-41：同名测试类遮蔽的 6 条用例放行

- AST 反解（不是手数）：`TestPointerBoundary` 定义于行 200 与 420，`TestPipelineBoundary` 行 282 与 910；
  首份独有的方法 5 个 + 首份整类被遮 ⇒ 实际新放行 **6 条**。
- 处置：只给**首现**类改名（`…ShadowedOnce`），不删任何断言；改名脚本断言锚点 `count==2` 且首现行号==预期行号，
  否则中止（避免「两串同文改到另一处」）。
- 实测：`pytest tests/test_boundary_comprehensive.py -q -k ShadowedOnce` → `6 passed, 122 deselected`。

### 2.5 BUG-93：FIST 驱动面对齐上游 0.3.4

- 上游事实（实测，非回忆）：`node cmd/cli/cli.js` 裸跑只打 help；`initialize` 回
  `-32601 Method not found: initialize — this server speaks MCP 2026-07-28`；带 `_meta` 的
  `tools/list` 回 129 工具；旧入口 `cmd/main/main.js` 仍在但 mtime 落后（`main.js` sha `1e96c699`、
  `cli.js` sha `080a3937`），上游 CHANGELOG 的 BUG-93 已把 104 处入口路径迁到 `cmd/cli`。
- 改：入口 `cmd/cli/cli.js` + `serve`；服务 cwd 改本仓根（任务库落 `E:/IDEProjects/AI/Cypy/fist-mbt.db`，
  不再写兄弟仓库）；`project_dir` 默认 `.`；删 `initialize`；`list-tools` 必须解出非空清单并点名
  12 个必需工具，否则 rc=1；新增 `_omit_defaults` 退出键。
- 锁：`tests/test_fist_driver_protocol.py`（10 条，假 Popen 驱动，不起 node 不碰库；
  含错误帧/空清单/缺 `omega_verify` 三条必然红的对照 + 注入开关的双向对照）。
- 调用面：`python scripts/fist.py list-tools` → `# 129 tools; cwd=E:/IDEProjects/AI/Cypy; missing=[]`、rc=0。

### 2.6 寻虫面（本轮新取证）

- 边界审视（位置模式四类输入，逐个真跑 transpile）：
  `空实参 rc=0` / `极值 32 槽 rc=0` / `字面量与绑定混写 rc=0` /
  `未定义类型 rc=1 ["Undefined name 'Unknown' at 1:10", "... at 3:14"]` /
  `嵌套八层 rc=1 ["编译错误: Unexpected pattern token CASE at 6:24"]` /
  `空匹配体 rc=1 ["编译错误: Expected increased indentation at line 6. Expected 8, got 0"]`；
  **0 内部崩溃、0 挂起**；canary 两格（必绿源 rc=0、必红源 rc=1 且非崩溃）通过。
  证据 `.fist-loop-20260929/hunt_r6_boundary.json`。
  尺子自坏过一次并留档：cypyc 按**调用进程 cwd** 解析源路径，先前「cwd=本目录 + 相对文件名」使 8 格全部
  「读取文件错误」而横幅回显看着像真跑了；第二处：诊断行带 ANSI 色码，按字面 `- ` 锚定必然数出 0 条。
- BUG-34 复验（→ 正身 BUG-108）：`adv_10_slice_step_zero.cypy` 与 `adv_19_negative_index_const.cypy`
  仍逐字产出 `xs: Constant(line=2, col=9) = [1, 2, 3]` / `= []`，rc=0 且零诊断；
  分析器侧无任何标注形态校验（grep `Invalid type annotation`/`Unsupported annotation` 命中 0 条）。
- 账面自曝 BUG-107：驱动重跑三遍且 report_bug 无幂等守卫 ⇒ 同一主张入账 3 遍
  （BUG-96/99/102、97/100/103、98/101/104），并与手写台账撞出两个 `## BUG-96` 抬头。
  处置：只做插入与正身指认（规范缺口→BUG-96、横幅→BUG-97、corpus→BUG-98、我的复验条→BUG-108），
  不删任何正文；驱动已补 `existing summary` 守卫。

### 2.7 Omega 强验证链（工具面形状是实测出来的）

- 门禁拒绝文案逐字（第一遍踩的三档，都是「拒绝带出路」的正例）：
  `Omega 强验证门禁：任务 [T0r112.1.1] 尚未创建语料，请先由语料创建者执行 omega_spec_create`；
  `Omega 强验证门禁：语料 [spec:T0r112.1.1:r1] 状态为 [pending]，未通过审核前禁止进入执行`；
  `执行前语料 [spec:T0r112.1.1:r1] 未通过审核（[pending]），不可进入成果复验`；
  `非法迁移: submit 要求状态 [执行中]，当前是 [已领取]`；`未知角色: 'cypy-selfdrive-agent'`（角色是闭集）。
- 因此本轮形状（6 条叶全部走完，终态 **已完成**）：
  `claim → omega_spec_create → omega_spec_review(approve) → execute → run_check → omega_result_verify(pass) → submit → verify`
- `run_check` 实测 18 次全 ok（每条叶的 pytest 选段/探针真跑，回执带 `stdout_tail`，判定落 `specs` 表），例如
  `3 passed, 5 deselected` / `5 passed, 3 deselected`。
- 语料（Ω-spec JSON）随 `omega_spec_create` 落库：`op=cypy.pattern.positional`，5 条测试对含 2 条错误路径。
- laya：`laya_decide`（no_sidecar=true，规则式确定性档）→ `split_n=6`、feature_route=拆解调度，
  `task_plan_deep(omega_strong_verify=true, gradient=true, boundary_probe=true, reinject_context=true)`
  → 建树 29 节点（根 1 + 支 6 + 叶 21，含边界审视叶）。
- 对账（sqlite 只读，不靠回忆）：`close_r6_leaves.json` 记 `rows_for_this_round=170 refused=61`，
  逐工具分栏 `claim ok=6/refused=0`、`omega_spec_review ok=6/refused=0`、`run_check ok=18/refused=0`、
  `submit ok=6/refused=12`、`verify ok=6/refused=12`；拒绝集中在**前两遍形状错**与**重跑重复执行**，
  非账面缺口；`loop_create ok=0/refused=1`（环已存在）＋`loop_tick 6 次全拒`（见缺口）。

## 3. 分析

- BUG-36/37 同源于一件事：**struct 的 AST 形状在两处实现里理解不一致**。分析器知道 `.fields`，
  生成器不知道；`_collect_method_names` 知道 `.methods`，紧挨着 8 行之下的采集器不知道。
  这类「同文件内的不对称」是最高性价比的寻虫信号，本轮已把它变成一条机器可检判据的候选
  （建议下一轮：对 AST 节点类做一次「属性名 vs 读取点」的交叉核对，读不存在的属性即红）。
- 位置模式的另一半不稳定的原因不是实现错，而是**规范没写元数**：SYNTAX/17 通篇没有 arity 条款，
  而 `tests/test_extractor_pattern.py:192/:235` 已把「1 字段 + 2 实参」的形态钉成
  「无诊断 + 就是 `__f{i}`」。本轮两种收紧都被这两条既有判据打红 ⇒ 按红线退回，只入账不擅改判据。
- BUG-108 与 BUG-92 是同一类失效的两个面：**未文档化/未校验的输入形态，末路都写成「把它转成字符串」**。
  修它需要的不是更聪明的兜底，而是「标注必须是类型形状」这一条可检判据 + 产物侧禁 `line=` 字面量的守卫。
- 环（loop）不落库与「待领取无出路」两条说明：组合环目前只能**在一次会话内**推进；
  跨会话续跑要重建环，而重建又会在账面留下两份环记录。这是本轮「推进→…→推进」最后一跳没能在
  工具面上闭合的真因（不是代理没做，是出路缺档）。

## 4. 缺口与风险

1. `corpus/` 与 `tests/regression/` 仍不存在（BUG-95）⇒ 05 定义的「项目准确率」在本项目没有客观来源；
   本轮 Ω-spec 只落了任务面（`omega_spec_create`），没落盘到仓内判据面。
2. BUG-92 / BUG-108 未修（前者需规范补条款，后者需同时动两处判据面）⇒ 「所有语法特性无 bug」未达成。
3. 剩余 9 条历史开口未动：BUG-34（已由 BUG-108 承接复验）、40、43、49、50、52、54、65、70。
4. 树面残留：`T0r112` 仍为「拆分中」，15 条叶「待领取」且代理面没有退役出路（BUG-106）；
   `loop_tick` 6 次全被拒（BUG-105）⇒ 环的步骤推进没有账面证据，只有 6 条叶的闭环是硬的。
5. 账面重复：BUG-99/102、100/103、101/104 是 DUPLICATE（已在 BUG-107 指认正身，未删除），
   `bug_list` 的 OPEN 计数因此偏大 3 条。
6. 未证实转结（沿用既有口径，本轮未证）：`cython_generator.py:421-430/:439-445` 的 `_class_fields`
   历史疑点在 StructDef 修复后已不可复现（方法名不再进 fields），但「class 分支的位置字段语义」
   仍无文档支撑（BUG-92 同族）。

## 5. 裁决登记（代理自决，未等发起）

| 编号 | 裁决 | 依据 |
|------|------|------|
| D-R6-1 | 本轮半径 = 账本 12 条开口中的 5 条（36/37/41/34 复验 + 工具面），不碰 examples/golden | 04 规范与既往红线「不弱化既有判据、不动 golden」 |
| D-R6-2 | 位置模式元数收紧**撤回**，改为入账 BUG-92 | 两种收紧分别打红 `test_extractor_pattern.py:192/:235`，属未文档化收紧 |
| D-R6-3 | BUG-34 不在本轮修，改写复验正身 BUG-108 | 需同时新增分析器拒绝面 + 产物守卫，属独立判据轮 |
| D-R6-4 | `scripts/fist.py` 就地改（不分叉新驱动），cwd=本仓、`project_dir=.` | 与既往四轮 lane 的收口库口径一致，避免账本分家 |
| D-R6-5 | 不 commit、不 push；本地不做 `git add` | HEAD（2026-08-17）远旧于盘面，提交会把三轮未提交的在制工作混成一笔 |
| D-R6-6 | 环注册名与 ns 分开看待（`cypy-selfdrive-20260929` vs `cypy-loop-20260929`） | loop_tick 拒绝文案逐字暴露混用；已入账 BUG-105 |

## 6. 建议入档位置

- 产品知识：`PROJECT-SPEC` 之外的 `SYNTAX/17-pattern-matching.md` 需补「元数与字段数不符」条款（BUG-92 出路①）
- 判据：`tests/test_pattern_positional_struct.py`（8 条）与 `tests/test_fist_driver_protocol.py`（11 条）已入库
- 账面：`memory/bugs.md` 追加 BUG-92/93/94/95/107/108 + BUG-36/37/41 的 `### FIXED` 段（只增不删，difflib 复验 0 删除行）
- 兄弟仓移交：`loop_*` 不落库（服务端 BUG-105）、待领取叶无退役出路（BUG-106）、serve 横幅（BUG-97）
- 过程件：`.fist-loop-20260929/`（baseline_snapshot、hunt_r6_boundary、close_r6_leaves、close_r6_ring2、
  verify_r6_ledger、fix_r6_ledger、logs/*）

---

## 终验（最后落笔，跑完才写）

- 基线（本轮开工时）：pytest `2119 passed / 0 failed`；自研套件 `47/47`；e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
- 修复后第一遍全量：pytest `2122 passed / 6 failed`，6 条失败全部落在**本轮新写的驱动测试自身**
  （帧 id 与 `sys.argv[0]` 口径错），非产品回归；自研套件 `47/47`（86.98s）；e2e `PASS=25 FAIL=0`
- 驱动测试修正后局部：`19 passed`，收集数按文件实测 `test_fist_driver_protocol.py=11` +
  `test_pattern_positional_struct.py=8`（`--collect-only -q` 数 `<Function` 行，两个数各自实测相加，不手数）
- 终验全量（三套体系同时跑完，日志 `.fist-loop-20260929/logs/final_*.log`）：

| 体系 | 命令 | 终态 |
|------|------|------|
| pytest 全量 | `python -X utf8 -m pytest tests -q -rf --tb=line` | **`2144 passed in 489.52s`，0 failed**（基线 2119 + 本轮新增 19 条驱动/模式锁 + 放行 6 条被遮蔽用例 = 2144，双向对得上） |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | 见 `logs/final_native_r1.log`（`Total: 47 / Passed: 47`） |
| e2e golden | `bash scripts/e2e_golden.sh` | `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`（跑在最终产品码上：该轮启动于两处产品修改之后，其后仅动 tests/ 与账面文件） |

**锁承重矩阵**（`.fist-loop-20260929/verify_r6_locks.py`，底树=盘面快照副本，非 `git archive HEAD`）：

| 格 | 摘掉的变量 | 结果 |
|----|-----------|------|
| L1 | 生成器 `_record_pattern_shape` 两处调用 | `3 failed, 5 passed`（三条 struct 位置模式锁全红） |
| L2 | 分析器 `_visit_Pattern` 改回无条件 `Type("int")` | `2 failed`（两条槽位类型锁红） |
| L3 | 两个 `…ShadowedOnce` 类名改回同名 | `122 deselected / 0 selected`（遮蔽复现，rc=5） |
| 对照 | 只动一行注释 | `8 passed`，rc=0（证明上面三格的红不是尺坏了） |

身份探针逐字：`lockproof_tree/cypyc/__init__.py` + `lockproof_tree/cypyc/analyzer/type_checker.py` ⇒ 真跑副本树。

**一句话终态**：模式匹配的提取器形态已闭环且有调用面证据；元数不符（BUG-92）与非法标注形态（BUG-108/BUG-34）
仍在账上未修，因此「所有语法特性无 bug」本轮**未达成**，不是可宣布完成的轮次。
