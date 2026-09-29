# Cypy 自驱式组合环 R7（2026-09-29）交付报告

- 驱动：FIST-Mbt v0.3.4（129 工具，MCP 2026-07-28 无状态握手），ns `cypy-loop-20260929`，根任务 `T0r113`
- 环：`loop_create` 名 `cypy-selfdrive-r7`，steps `advance → bugfind → fix_and_merge → verify → polish → advance`，
  `baseline_test_count=2158`（本轮全量实测反解）、`baseline_open_bug_count=34`（本地账本反解，口径见 §2.6）
- 链形：每条叶 `claim → omega_spec_create → omega_spec_review(approve) → execute → run_check →
  omega_result_verify(pass) → submit → verify`；`laya_decide(no_sidecar=true)` 出拆分建议；
  对账走 `call_log` 表 + sqlite 只读复算，不靠回忆
- 红线遵守：未 commit、未 push、未动 `examples/` golden 基准、未弱化任何既有判据

---

## 1. 结论

1. **两条「静默错误产物」类缺陷闭环**：
   - **BUG-92**（位置模式实参元数 > 可解包槽位数时零诊断、产物发不存在的 `.__f{i}`）——
     先在 `SYNTAX/17` 补元数条款，再落分析器诊断，再把 R6 打红我的那两条既有断言**改严**（不是回退）；
   - **BUG-108 / BUG-34**（非法注解形态 `[int]`/`(int,str)`/`{str:int}` 把 AST 节点 repr 写进产物且零诊断）——
     `SYNTAX/02` 补「注解形态闭集」，分析器按闭集拒绝并点名正确写法，生成器末路 `str(node)` 改 `"object"`。
2. **无回归**：三套体系两轮全量（改动前 R7a、删死代码后 R7b）逐字结论行见 §2.5。
3. **锁承重 4/4**：副本树矩阵 M1–M4 每格「摘掉即红」，对照格「只动注释」全绿 ⇒ 红的是锁不是尺（§2.4）。
4. **本环自己发现并如实改判的一处**：矩阵 M4 的第一版针是 `_validate_annotation_shapes` 里
   `kind != "ComptimeStmt"` 那道跳过，实测**不承重**；结构核证 `ComptimeStmt` 根本没有 `type_annotation` 字段
   （§2.3），故该守卫是死代码，**已删除**，行为主张不变，账改判走 `### AMENDMENT` 段（§2.6）。
5. **边界审视 23 格**（注解面 15 + 元数面 8）：0 CRASH、0 静默放过、0 本面假阳性；
   `comptime: [1,2]` 与 6 种合法形态放行，`[int]` 系列与极值（12 层嵌套 / 200 元组 / 非类型字面量）全部带行列拒绝（§2.2）。
6. **账面推进但不虚报**：`T0r113` 树下 15 支叶，本环真实关掉 11 支（4 条交付面 + 2 条真实边界审视 +
   5 条按叶子自身条款申报「不适用」），**4 支重复描述的叶留在「待领取」**（逐字 id 见 §2.7）。
   根单仍「拆分中」—— 这是账面事实，不是已归档。
7. **语法特性稳定度**：模式匹配的位置/提取器形态、类型注解形态两类已可用且都有调用面证据；
   目标「所有语法特性无 bug」**本环仍未达成**——本地账本尚有 33 条 open（§3）。

## 2. 证据（全部盘面上可复跑，file:line + 命令）

### 2.1 改动面

| 文件 | 改动 | 反查 |
|------|------|------|
| `SYNTAX/02-type-annotations.md` | 追加「## 注解形态闭集（R7 补，2026-09-29）」，158→189 行 | `run_check` 叶 `T0r113.1.1` 逐字回 `SPEC OK 189 441` |
| `SYNTAX/17-pattern-matching.md` | 追加「## 位置模式的元数与槽位规则（R7 补，2026-09-29）」，418→441 行 | 同上 |
| `cypyc/analyzer/type_checker.py` | `ANNOTATION_TYPE_KINDS` / `ANNOTATION_SHAPE_HINTS` / `_check_annotation_shape` / `_validate_annotation_shapes`，挂钩在 `check()` 第 324 行；`_visit_ExtractorPattern` 补元数诊断（4241-4242） | 见 §2.4 矩阵 M2/M3/M4 |
| `cypyc/codegen/cython_generator.py` | `_type_to_str` 末路 `return str(node)` → `return "object"`（4149-4150 带指认注释） | 矩阵 M1 |
| `tests/test_annotation_shape.py` | 新建，`collected 14`（6 个函数，含收集数地板与产物字节守卫） | `--collect-only` |
| `tests/test_extractor_pattern.py` | `test_extractor_pattern_type_checker` 改双向格（相符必须放行 / 不符必须带行列诊断） | 矩阵 M3 |

### 2.2 边界审视（`.fist-loop-20260929/hunt_r7_boundary.py`）

判据形状：只看本面诊断（注解面数 `Invalid type annotation`、元数面数 `Positional pattern`），
其它诊断单列 `other` 不冒充本面结论；三根 canary 必须成对（合法格静默 / 非法格带行列 / 超元带行列），
不成对即整份作废并 rc=1。逐字结论行（`logs/r7_boundary_b1.txt`）：

```
probe_self=OK cases=23/23 canary_silent=True canary_diag=True canary_arity=True judge_ok=True
CONCLUSION judge_ok=True crashes=0 silent=0 false_positive=0 syntax_caught=1 observed=3 rows_json=.fist-loop-20260929/hunt_r7_boundary.json
```

第一版尺把 `x: list<int> = 1` 的**正确**报错（`Type mismatch: expected list[int], got int`）判成产品假阳性，
是尺坏了不是码坏了；改判据口径后该格 `surf=0 other=1`，`pointer_valid` 同型。逐字记录在两版日志
（`logs/r7_boundary_a2.txt` / `logs/r7_boundary_b1.txt`）。

调用面（真 CLI，非单测桩；退出码不走管道，逐字实测 `adv10_rc=1`、`huntf_rc=1`）：

```
- Invalid type annotation at 2:9 (期望 类型名或 list<int> / tuple<int, int> / dict<str, int>，实际是 Constant 字面量形态)
- Positional pattern 'Email' has 2 slot(s) but type 'Email' unpacks only 1 at 6:14
```

before 证据仍在盘上：`.fist-loop-20260927/cliout/adv_10_slice_step_zero.pyx` 第 30 行
`    xs: Constant(line=2, col=9) = [1, 2, 3]`；`.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx`
第 39 行 `        domain = _match_subject_1.__f1`。本轮两条语料都到不了产物面（`-o .fist-loop-20260929/out_r7`
在拒绝路径上未创建）。

### 2.3 死代码核证（M4 改判的依据）

```
class ComptimeStmt(ASTNode):
    def __init__(self, expr: Any, line: int = 0, col: int = 0):
        super().__init__("ComptimeStmt", line, col)
        self.expr = expr
has type_annotation in class source: False
construction sites: 2 … passes type_annotation: False / False
```
（逐字：`logs/r7_comptime_structural_proof_a1.txt`）；语料同向：`logs/r7_comptime_fact_a1.txt`
`CONCLUSION files=109 parsed=97 unparsable=12 ComptimeStmt_nodes=3 with_type_annotation=0`。
⇒ 那道跳过对任意输入都不可能命中，删除后行为不变（`test_comptime_inline_form_is_not_an_annotation`
与 `test_r5_fix_comptime_types.py::test_bug83_inline_form_control_still_clean` 两把锁继续认领该行为）。

### 2.4 锁承重矩阵（`.fist-loop-20260929/verify_r7_locks.py`，底树 = 盘面快照副本 `lockproof_r7/`）

身份探针先过（`cypyc/__init__.py`、`analyzer/type_checker.py`、`codegen/cython_generator.py` 三个 `__file__`
都落在树内），不过则整份矩阵不作数。

| 格 | 摘掉的变量 | 实跑 | 判定 |
|----|-----------|------|------|
| M1 | 生成器末路退回 `str(node)` | `2 failed, 12 passed`（collected 14） | 承重 |
| M2 | `check()` 里的注解闭集挂钩改成 `pass` | `4 failed, 10 passed` | 承重 |
| M3 | 元数诊断的文案前缀 | `1 failed, 19 passed`（collected 20） | 承重 |
| M4 | 元数比较条件 `if slots and …` → `if False:` | `1 failed, 19 passed` | 承重 |
| C | 只往注释里加一句 | `0 failed, 14 passed`，rc=0 | 对照绿 ⇒ 尺没坏 |

逐格锚点 `count == 1` 全部先断言后改；每格跑完按字节摘回并复核（`restored=True`）。
结论行：`CONCLUSION control_green=True load_bearing=4/4 not_load_bearing=[]`。

### 2.5 三套全量

| 体系 | 命令 | R7a（注解闭集+元数落地后） | R7b（删死代码后） |
|------|------|---------------------------|------------------|
| pytest 全量 | `python -X utf8 -m pytest tests` | `2158 passed in 413.15s` rc=0 | 见 §2.8 |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | 47 通过 / 0 失败 / 0 跳过，rc=0（逐字行在 `logs/r7_native_r1.log`） | 见 §2.8 |
| e2e golden | `bash scripts/e2e_golden.sh` | `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0` rc=0 | 见 §2.8 |

收集数算式（不是手加）：R6 终态 `2144 collected / 2144 passed` → R7 `collected 2158 items`，
差值 14 == `tests/test_annotation_shape.py --collect-only` 的 `14 tests collected`；
被放行的 6 条同名遮蔽叶在 R6 已计入 2144。**墙钟耗时不作为产品信号**（同仓既往实测大幅波动）。

### 2.6 本地账本（`memory/bugs.md`，append-only）

- 口径：`open` = 条目块内没有 `### FIXED(` 段。反解函数 `measure_open_bugs()` 落在
  `.fist-loop-20260929/close_r7_ring.py`，两个时点各自实测：本环开工 `33 open / 76 closed / 109 条`，
  收口后 `112 条 / 79 FIXED 段 / 33 open`。
  算式自洽：34（含 BUG-109）+ 新增 2（BUG-110/111）- 本环关闭 3（BUG-34/92/108）= 33。
- 本环追加：`### FIXED(R7 组合环 …)` × 3（BUG-34 / BUG-92 / BUG-108）+
  `### AMENDMENT(R7 矩阵改判 …)` × 1（BUG-108 段的 comptime 措辞改判）；
  两次写盘都由脚本自证 insert-only（difflib 无 delete/replace 行）、temp + `os.replace`、撞号即中止。
  新票号一律从 `report_bug` 回执反解（`BUG-109/110/111`），正文里没有手写编号。
- 备份：`.fist-loop-20260929/bugs_ledger_pre_r7b.md`（写盘前快照）。

### 2.7 FIST 账面（ns `cypy-loop-20260929` / 根 `T0r113`）

| 步 | 事实 |
|----|------|
| 建单 | `publish_parallel` → `T0r113`，描述首行 `[omega:required]`（缺它则 Omega 三连被拒而 verify 照过） |
| 拆分 | `laya_decide(no_sidecar)` 回 `available:false / source:fallback / split_n:5`（规则式 +1）； `task_plan_deep(split_n=4, omega_strong_verify=true, gradient, boundary_probe, reinject_context)` 回 `created:5` |
| 树形 | sqlite `tasks` 反查 21 行 = 1 根 + 5 枝 + 15 叶；15 叶里 **8 支描述与根单逐字相同**、7 支是 `[边界审视·全局输入域 owner]` 梯度叶 |
| a 轮 | 用 `list(namespace=…)` 回读 → 该 ns **0 行**（sqlite 同 ns 21 行）⇒ 叶清单不可得， 守卫「叶数 ≠ 交付条数」触发，**一条链都没发、0 假账**；`report_bug` → `BUG-109`； 按 ns 过滤的 `call_log` 复算被 R6 历史污染（200 行 / 76 拒）——口径作废，b 轮改时间窗 |
| b 轮 | 复用根（不重发 publish）、叶改 sqlite 反查；11 支叶走完 8 步链，全部 `待领取 → 已完成`、 assignee `cypy-selfdrive-agent`、`run_check` 11/11 `passed`；6 次 `loop_tick`； `report_bug` → `BUG-110`、`BUG-111`（幂等守卫跳过了 `BUG-109` 的 summary，回执栏记 skipped） |
| 对账 | 自计票 `rpc_sent_total=121`；sqlite 窗口 `ts>=2026-09-29T03:52:52Z` 且 task/name/ns 命中 `rows=120 refused=0`；`sent_but_invisible_to_filter=["laya_decide"]`（它的 params 不带三个过滤键， 工具其实落库——这是 §2.7 末行的口径缺陷，已入账 BUG-111） |
| 留守 | 4 支重复描述的叶仍在「待领取」：`T0r113.3.1`、`T0r113.3.2`、`T0r113.4.1`、`T0r113.4.2`； 根单状态 `拆分中`（叶未全闭不上卷，BUG-106 已记代理面无退役出路） |

### 2.8 R7b 终验（删除死代码守卫后的三套全量，逐字结论行）

```
====================== 2158 passed in 458.28s (0:07:38) =======================   PYTEST_RC=0
Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0                                    NATIVE_RC=0
[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0                        E2E_RC=0
```

与 R7a 对照：**2158 → 2158**（收集数与通过数同值，删除那道守卫既没让用例静默消失、也没新增用例），
自研套件与 e2e 两格逐字相同。耗时 413.15s vs 458.28s 的差异不作为产品信号
（同仓既往实测：全量墙钟随负载大幅波动）。日志：`.fist-loop-20260929/logs/r7b_{pytest,native,e2e}_r1.log`。

## 3. 分析：三条根因形状

1. **「同文件内的不对称」是本环两类静默缺陷的共同形状**：分析器知道 `.fields`、生成器读 `.body`；
   分析器有类型闭集概念、生成器末路直接把节点 `str()` 出去。修任一侧都会留下另一侧继续静默，
   所以本环把「文档条款 → 分析器拒绝面 → 生成器退化面 → 产物字节守卫」串成一条链，缺一格就红。
2. **注解闭集的「正解」不在本轮半径内**：`[int]` 在解析器里就不是类型节点（是 `Constant`/`DictLiteral`），
   要真正接受括号形态得给类型位置加类型表达式产生器 —— 那等于新增语法，而 `SYNTAX/02` 只承认
   `list<int>` / `tuple<…>` / `dict<…>`。本轮选择「拒绝 + 点名正确写法」，把新增语法交回裁决（BUG-109）。
3. **判据自己的失效模式比产品的更贵**：本环三次被尺误导 ——
   ① 边界探针把正确报错算成产品假阳性；② `list(namespace=)` 回 0 行让守卫误判「无叶可闭」；
   ③ M4 第一版针钉在死代码上，「不承重」是真结论、改判靠的是结构核证而不是把针挪走。
   三次都留下了可复跑日志，没有一次靠叙述过去。

## 4. 缺口与风险

| 项 | 状态 | 说明 |
|----|------|------|
| BUG-109 解析器无类型表达式产生器 | 入账未修 | 括号形态的正解；放开等于新增语法，交裁决 |
| BUG-110 `task_plan_deep` 叶数与描述不受控 | 入账（兄弟仓面） | 8 支叶逐字复制根单 ⇒ 交付面与叶数无法 1:1；本环处置已在 §2.7 逐字 |
| BUG-111 `call_log.result_json` 只存 `ok`；`laya_decide` 对 ns/task 过滤不可见 | 入账 | 复原能力缺失：拒绝文案与回执只能靠调用方自存 |
| BUG-106 待领取叶无代理可见退役出路 | 既往入账，仍在 | 直接后果：本环 4 支叶无法闭，根单无法上卷 |
| BUG-95 本仓无 `corpus/`、无 `tests/regression/` | 既往入账，仍在 | PROJECT-SPEC 03/05 要求的 Ω-spec 语料落盘面这一条还没通 |
| 元数检查只在槽位类型可见时生效 | 已知边界，写在 SYNTAX/17 条款里 | 类型不可见时越界槽位仍可走到 `.__f{i}`；未另立单，属 BUG-109 同一半径 |
| `nested_bracket_extreme` 出 12 条诊断（每层一条） | 观测，未判为缺陷 | 诊断可用但偏噪；若要合并成一条需先定「嵌套字面量」的报告粒度 |
| 叶 `T0r113.1.2` 的 deliverable 半句失效 | 账面漂移，已 AMENDMENT | 归档后无改档出路，以本地账本改判段为准 |

## 5. 裁决登记（本轮自决，不再回问）

| 号 | 决定 | 依据 |
|----|------|------|
| D-R7-1 | 先补 `SYNTAX/17` 元数条款再落诊断，并把 R6 打红我的那条既有断言**改严**而非删除或 xfail | 规范优先于实现；弱化判据是红线 |
| D-R7-2 | 注解非法形态走「拒绝 + 点名正确写法」，不在解析器新增括号类型语法 | `SYNTAX/02` 只承认 `list/tuple/dict<…>`；新增语法需裁决 |
| D-R7-3 | 生成器末路退化为 `"object"` 而不是抛异常 | 末路对全部 AST 节点开放，抛异常会把未知形态变成编译期崩溃 |
| D-R7-4 | a 轮叶数对不齐时**整批不打卡**，不做强行 4↔15 映射 | 宁可账面停在拆分中，也不造 11 条假交付 |
| D-R7-5 | b 轮复用根 `T0r113`、不重复 `publish_parallel` | BUG-107 的双发教训；重跑必须带幂等守卫 |
| D-R7-6 | 5 支 `[边界审视]` 叶按叶子自身条款「显式声明不适用并说明依据」关闭，另 2 支挂真实探针 | 叶子描述本身就给了该出路；同时把重复叶问题入账 BUG-110 |
| D-R7-7 | M4 改判：证据链（矩阵不承重 + 结构证明 + 语料测量）支持后删除该守卫并复跑三套全量 | 「看着像在防什么」的死代码比没有更贵 |
| D-R7-8 | 继续不 commit、不 push（R6 的 D-R6-5 延用） | 工作树含三轮未提交改动，HEAD 是 8 月基线 |

## 6. 建议入档位置

- 规范：`SYNTAX/02-type-annotations.md`（注解形态闭集）、`SYNTAX/17-pattern-matching.md`（元数与槽位规则）
- 判据：`tests/test_annotation_shape.py`、`tests/test_extractor_pattern.py`、`tests/test_pattern_positional_struct.py`
- 账本：`memory/bugs.md` 的 `BUG-34 / BUG-92 / BUG-108` FIXED 段 + BUG-108 的 AMENDMENT 段
- 过程件：`.fist-loop-20260929/`（探针、两批收口件、矩阵尺、日志 `r7_*` / `r7b_*`）
- 项目记忆：R7 的「不对称形状」根因法与「尺三次误导」的处置，值得与 R6 条目并写

---

**一句话终态**：模式匹配的元数面与类型注解形态两面已闭环，且每面都有「摘掉即红」的锁与调用面逐字回执；
但目标「所有语法特性稳定、无 bug」本轮**未达成**——本地账本仍有 33 条 open（含 BUG-109 这条本环留下的正解缺口），
FIST 侧根单 `T0r113` 仍「拆分中」（4 支重复描述叶无法退役）。
