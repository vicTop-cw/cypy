# Cypy 自驱式组合环 R8（2026-09-29）交付报告

- 驱动：FIST-Mbt v0.3.4（129 工具，MCP 2026-07-28 无状态握手，入口 `cmd/cli/cli.js serve`），ns `cypy-loop-20260929`，根任务 `T0r114`
- 环：`loop_create` 名 `cypy-selfdrive-r8`，steps `advance → bugfind → fix_and_merge → verify → polish → advance`
- 链形：每条叶 `claim → omega_spec_create → omega_spec_review(approve) → execute → run_check → omega_result_verify(pass) →
  submit → verify`；拆分建议走 `laya_decide(no_sidecar=true)`；对账走 `call_log` 表 + sqlite 只读复算，不靠回忆
- 本轮落点：**建起项目第一层可执行 Ω-spec（`corpus/` + `scripts/omega_gate.py` + `tests/regression/test_corpus_pairs.py`），
  这层判据首跑就打出两条真缺陷，同轮确诊同轮修**
- 红线遵守：未 commit、未 push、未动 `examples/` golden 基准、未弱化任何既有判据、凭据未读取未回显

---

## 1. 结论

| 面 | 判据 | 实测 |
|----|------|------|
| Ω-gate 跑批 | 准确率必须 100% | `CONCLUSION specs=2 cases=41 passed=41 failed=0 refused=0 accuracy=100.00% rc=0` |
| pytest 全量 | 0 红且收集数可解释 | `2202 passed in 445.10s (0:07:25)`，`PYTEST_RC=0`；`2202 = 2158（R7 基线）+ 44（本轮回归件）` |
| 自研套件 | 47/47 | `Total: 47 \| Passed: 47 \| Failed: 0`，`NATIVE_RC=0` |
| 外部 golden | 25 例全 PASS | `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`，`E2E_RC=0` |
| 回归锁承重 | 摘掉即红 | `CONCLUSION control_green=True load_bearing=5/5 not_load_bearing=[] anchor_cells_refused=[]` |
| 新门的负控制 | 每道门都要能红 | `CONCLUSION controls=5 carrying=5 corpus_untouched=True all_carry=True` |
| FIST 账面 | 叶全闭、0 拒 | `CONCLUSION closed=9 by_kind={'face': 5, 'boundary-declared-na': 4} still_pending=0 root=拆分中 calls=98 refused=0 refusal_rows=0 run_check_states=['passed']`（a4；a3 另闭 9 支）|
| FIST 收根 | 枝干与根都要过 Omega 门禁 | `CONCLUSION root=已完成 branches_closed=6/6 rollup={'已完成': 25} calls=28 refused=0 call_log_error_rows=0` |
| 账本 | 只增不删 | 抬头 117（116 个去重编号，`BUG-96` 双写）、`### FIXED(` 段 82（79→82）、open 条目 35（去重 34）|

**目标达成度**：本轮把「模式匹配的位置槽位面」补到了 class 分支并与生成器共用单一判据，注解形态面维持 R7 终态，
三套回归全绿 ⇒ **「无回归」达成**。但「所有语法特性稳定、无 bug」**未达成**：账上仍有 34 个 open 编号，
其中三条是本轮自己确诊并按裁决留下的（`BUG-114` 语法未落地、`BUG-115` 名称序未消费、`BUG-116` 覆盖面只 2 个 op）。

---

## 2. 证据

### 2.1 本轮新增的可执行 spec 层（三件套，共用同一批测试对）

- `corpus/cypy.annotation.shape.json` —— 24 格，指纹 `fnv1a64:927770342620acae`
- `corpus/cypy.pattern.positional.json` —— 17 格，指纹 `fnv1a64:e39989a43763a282`
- `scripts/omega_gate.py` —— fnv1a64 封/验、断言键闭集（11 个键）、`EXPECTED_KEYS` 外的键一律 `refuse` 而不是降级为存在性检查、
  结果落 `reports/YYYY-MM-DD/omega-*.json`、非 100% 即 `rc=1`，结论行打在最后（`run_check` 只抓末段 stdout）
- `tests/regression/test_corpus_pairs.py` —— 同一批 41 对参数化成 pytest 用例 + 3 道常驻门（语料存在且指纹相符、
  用例地板值 `FLOOR_CASES = 41`、未知断言键必须被 refuse），收集数 44

`corpus/*.json` 由 `.fist-loop-20260929/make_corpus.py` 生成（dump → reload → 断言格数）；
本轮两次手改 JSON 都产出了非法 JSON（相邻字符串拼接不是 JSON），所以语料不再手写。
**格号口径**：`scripts/omega_gate.py` 与回归件都用 `enumerate()` 的 0 基索引（`#11` 即第 12 格），下文引用的格号都是这个口径。

### 2.2 两条同轮确诊同轮修的缺陷（调用面逐字）

**① `BUG-112` class 的位置槽位恒空 ⇒ 元数检查被静默跳过**

- 根因：`ClassDef` 的实例属性只有 `name/bases/body/is_cdef`，字段以 `LetStmt` 存在 `.body`；
  旧 `_pattern_slot_types` 只读 `.fields` ⇒ class 槽位表恒空 ⇒ `if slots and len(node.args) > len(slots)` 前置不成立。
- 修复：`cypyc/analyzer/type_checker.py:3994` 新增 `_positional_fields()`（class 走 `.body` 并按
  `NON_FIELD_KINDS`（:3991）剔非数据成员），槽位循环 :3985 改用它；诊断文案落 `:4272`。
- 调用面：`corpus/cypy.pattern.positional.json#11`（`class C: a: int` + `case C(x, y)`）由「观测为空」变为
  `Positional pattern 'C' has 2 slot(s) but type 'C' unpacks only 1 at 8:14`。
- 锁：该格 + 参数化格 + 矩阵 **M5**（退回 fields-only ⇒ `3 failed, 41 passed`，`collected=44`，摘掉即红）。

**② `BUG-113` `__match_args__` 被当成第三个数据字段计入槽位数**

- 根因：`struct` 内的 `__match_args__ = ("x", "y")` 被 parser 收成第三个 `StructField`
  ⇒ `slot_types` 返回 `['int','int','object']`、`_class_fields['Point']` 含 `__match_args__`
  ⇒ `case Point(a, b, c)` 零诊断通过，产物还可能生成 `.__match_args__ ==` 比较。
- 规范先行：`SYNTAX/17-pattern-matching.md` 追加规则 6（`__`-包围的类属性不是数据字段）与规则 7
  （名称序目前未被消费，正解指向账本条目），441→449 行（规则 6、7 占 442–449）。
- 修复：判据单点 `cypyc/utils/ast_utils.py:7 ASTUtils.is_positional_member`；
  分析器 `_positional_fields` 与生成器 `cypyc/codegen/cython_generator.py:443` 共用（各写一遍就会漂移）。
- 调用面（本轮实测）：`#13` 相符放行 `slot_types=["int","int"]`、`#14` 超元报
  `Positional pattern 'Point' has 3 slot(s) but type 'Point' unpacks only 2 at 9:14`、`#15` 产物 `class_fields={"Point": ["x","y"]}` 且不含元数据比较。

两条同型：**同一个事实有两个读取点，而两侧规则不一致**（分析器知道 `.fields`，生成器不知道；
两侧都各自硬编码「什么算字段」）。下一轮最省力的寻虫面仍是「AST 节点属性名 vs 读取点」交叉核对。

### 2.3 三套回归的逐字终态

```
====================== 2202 passed in 445.10s (0:07:25) =======================
PYTEST_RC=0
Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0
NATIVE_RC=0
[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0
E2E_RC=0
```

证据件：`.fist-loop-20260929/logs/r8_pytest_r3.log`、`logs/r8_native_r2.log`、`logs/r8_e2e_r2.log`、`logs/r8_final.flag`（`ALLDONE`）。

**明确不作验证的两份**：`logs/r8_pytest_r1_prefix.log`（2202 之前、修一半的盘面）与
`logs/r8_pytest_r2_mixedlabel.log`（同一轮里既有修复前又有修复后的混合运行）—— 它们只用于说明缺陷是怎么被打出来的，
不能当回归证据。

### 2.4 回归锁承重矩阵（`.fist-loop-20260929/verify_r7_locks.py`，副本树 `lockproof_r7/`）

```
M1 生成器末路回到 str(node)      anchor=1 run=2/12  restored=True verdict=承重：摘掉即红
M2 摘掉注解闭集校验挂钩           anchor=1 run=4/10  restored=True verdict=承重：摘掉即红
M3 摘掉位置模式元数诊断            anchor=1 run=1/19  restored=True verdict=承重：摘掉即红
M4 让元数比较条件永假             anchor=1 run=1/19  restored=True verdict=承重：摘掉即红
M5 class 位置槽位退回 fields-only anchor=1 run=3/41  restored=True verdict=承重：摘掉即红
C  对照：只动一行注释             anchor=1 run=0/14  restored=True verdict=对照绿（尺没坏）
CONCLUSION control_green=True load_bearing=5/5 not_load_bearing=[] anchor_cells_refused=[]
```

副本树身份探针 `identity_ok=True`，两个被改文件摘回后 `restored_bytes_identical=True`。

### 2.5 新门的 5 道负控制（`logs/r8_negatives_a3.txt`）

篡改 spec ⇒ 指纹不符；少一条用例 ⇒ 地板门真红（`baseline_cases=41 after_removal=40 floor=41`）；
未知断言键 ⇒ `verdict=null` + 原因而不是静默降级；放过非法/拦掉合法两向对照都判红；
克隆语料少一条 ⇒ pytest 地板门 `1 failed in 0.90s`。`corpus_untouched=True`（负控制跑在克隆树上）。

### 2.6 缺陷账本（`memory/bugs.md`）

- 抬头 117 个，去重编号 116（`BUG-96` 被写了两次：服务端 03:13:47Z 的「规范缺口 `__f{i}`」与手写 03:19:00Z 的
  「转结确诊:类型标注」——后者本应改指 `BUG-108`，R6 已记撞号，本轮只点名不复写）。
- `### FIXED(` 段 82（79 → 82，本轮追加 3 段：`BUG-95`、`BUG-112`、`BUG-113`），插入式校验
  `insert_only_verified=True`，字节 330875 → 334716；逐字改动的行只有 1 行（见 §4.2）。
- 真开口按条目内段落反解：35 个条目 / 34 个去重编号 —— `BUG-40 43 49 50 52 53 54 65 68 69 70 71 72 73 77 94 96 97 98 99 100 101 102 103 104 105 106 107 109 110 111 114 115 116`。
  `bug_list` 会按标题行报「全部 OPEN」，那个数不能用。

### 2.7 FIST 账面三向对照（`logs/r8_bugsurface_a1.txt`）

```
CONCLUSION ledger=5/5 bug_list_by_id=5/5 bug_list_by_summary=5/5 report_bug_rows=19 tasks_ns_bugs_rows_0929=0 three_way_ok=True rc=0
```

本轮 `report_bug` 走 `publish_task=False` ⇒ **`tasks` 表 ns='bugs' 在 09-29 一行都没有**（最新行是 09-28 的 `T0r111`），
单据只落 md 账本；服务端自己的读路径（`bug_list`）能按编号和 summary 前缀认全 5 条，所以账面成立。
`call_log` 今日 19 行 `report_bug`（含 a1/a2/a3/a4 的重试），`result_json` 全部只存 2 字节 `ok` —— 这条正是 `BUG-111` 的正文形状。

---

## 3. 分析：为什么本轮先建判据层，而不是再写新语料

R6/R7 两轮修的都是「同文件内的不对称」（`.body` vs `.fields`、采集器 vs 生成器），
那种缺陷的特点是能过单测、过全量、过 e2e —— 因为**没有任何一层把「规格」写成可执行的东西**。
所以本轮的推进面选在 PROJECT-SPEC/05 要求的 Ω-spec 层：期望值来自 `SYNTAX/02` 与 `SYNTAX/17` 的条文，
不是照着实现抄的；跑批用独立入口（`scripts/omega_gate.py`）+ 同一批数据进 pytest（一份地板值，两处共用）。

结果验证了这个选择：**首跑就打出两条静默缺陷**（`#11` 的 class 分支、`#13–15` 的元数据字段），
它们的共同点是「零诊断」——零诊断在纯 pytest 体系里是绿，在 Ω-gate 里是「期望有诊断而观测为空」的 FAIL。

同轮两条修复都选了单点判据（`ASTUtils.is_positional_member`）而不是两侧各写一遍过滤条件；
`BUG-114/115` 都不在缺陷轮里夹实现（要动类型语法/新增语义），按 D-R7-4 的同一口径转裁决。

---

## 4. 缺口与风险

### 4.1 产品缺口（本轮新增，均已入账）

| 编号 | 内容 | 状态 |
|------|------|------|
| `BUG-112` | class 位置槽位恒空 ⇒ 元数检查被跳过 | 同轮修，有承重锁 |
| `BUG-113` | `__match_args__` 被当第三个数据字段 | 同轮修，规范先行 |
| `BUG-114` | `SYNTAX/17` 承诺的 `tuple<int, ...>` / `case Numbers(x, y, ..)` 进不了解析器 | **未修，交裁决**（要动类型语法与模式语法）|
| `BUG-115` | 元数来源未消费 `__match_args__` 名称序 | **未修，交裁决**（新增语义，不夹在缺陷轮）|
| `BUG-116` | `corpus/` 只覆盖 2 个 op / 41 对，其余 20+ 章节无 Ω-spec | **未修，按轮次扩**（不被 `BUG-95` 的目录闭环遮蔽）|

### 4.2 本轮自曝的两处尺子缺陷（都已修，逐字留证）

1. **M5 假红**：`verify_r7_locks.py` 原先对整段 stdout 做 `(\d+) error` 检索，被自家断言文案喂出 11 ⇒
   M5 被判「尺坏了」，而 `failed+passed=44=collected` 明明自洽。逐字命中的行：
   ```
   E   AssertionError: cypy.pattern.positional.json#11 error 判不过：缺片段 "Positional pattern 'C'"；观测=''
   ```
   已改成只认汇总行形状 + 计数算术自洽门；`load_bearing` 从 4/5 变 5/5（`logs/r8_locks_a2.txt` 是坏尺读数，`logs/r8_locks_a3.txt` 是修正后读数，两份都留）。
2. **账本行数笔误**：本轮写进 `BUG-113` FIXED 段的「441→448 行」实测应为 449。
   锚点命中恰好 1 处、改动只落 1 行、改后数字与实测相等，逐字 before/after 在
   `.fist-loop-20260929/fix_r8_ledger_linecount.json`（原文行：`  （\`__match_args__\` 名称序目前未被消费，正解另立 BUG-115），441→448 行。`）。
   该段是本环几十秒前自写、尚无其他条目引用，故直接改而不追加 AMENDMENT；这条纪律上的判断记在这里供复核。

### 4.3 FIST 侧过程债（无出路 API，只能披露）

- **a3 轮的叶分类尺 bug**：驱动拿 `zip(leaves, tree)` 分类，树里含根与枝干 ⇒ 串位，
  产出逐字 `REFUSED sqlite | (分形状) | 叶 18 支里按描述只认出 13+4 支，剩余形状未知`（13+4=17，有一支形状不明）。
  a3 是在这道拒绝之后仍然关闭了 9 支，所以**这 9 支的 `kind` 标签与实际交付面是否相符，无法事后独立复核**：
  `T0r114.1.2`（face）、`T0r114.1.3`（face）、`T0r114.2.1`（face）、`T0r114.2.3`（face）、`T0r114.3.1`（face）、
  `T0r114.2.2`（boundary-real）、`T0r114.3.3`（boundary-real）、`T0r114.5.1`（boundary-declared-na）、`T0r114.6.2`（boundary-declared-na）。
  a4 用「只读叶自身 description」的判据重算后关闭另外 9 支：
  `T0r114.1.1`（face）、`T0r114.3.2`（face）、`T0r114.4.1`（face）、`T0r114.4.2`（face）、`T0r114.5.2`（face）、
  `T0r114.4.3`（boundary-declared-na）、`T0r114.5.3`（boundary-declared-na）、`T0r114.6.1`（boundary-declared-na）、`T0r114.6.3`（boundary-declared-na）；
  两份 `leaf_status` 的并集经核对恰好覆盖 18 支叶、`left_pending_general=[]`、`still_pending=0`。
  **服务端无 amend 接口、归档后不可 reopen** ⇒ a3 那 9 支的 `deliverable` 文字若与面不符只能这样点名，不做掩盖。
- **建树仍多生描述叶**（`BUG-110`）：`split_n=5` ⇒ 6 枝 × 3 叶 = 18 叶，其中 13 支描述逐字复制根单。
  本轮策略：只有真实交付面的 5 支按 face 关闭，其余按叶自身条款申报 `不适用`；不强凑 1:1。
- **收根本轮完成，但形状是实测出来的**：`T0r114` 的 18 支叶闭完后，6 支枝干仍停「待验收」、根停「拆分中」；
  第一次尝试逐字被拒三次（`close_r8_root.json` 的 steps 栏）：
  ```
  Omega 强验证门禁：任务 [T0r114.1] 尚未做成果复验，请先由验证者执行 omega_result_verify
  Omega 强验证门禁：任务 [T0r114] 尚未创建语料，请先由语料创建者执行 omega_spec_create
  非法迁移: submit 要求状态 [执行中]，当前是 [拆分中]
  ```
  补链 `omega_spec_create → omega_spec_review → omega_result_verify → verify` 后 6/6 枝干与根全部「已完成」
  （`rollup={'已完成': 25}` = 1 根 + 6 枝 + 18 叶，`calls=28 refused=0 call_log_error_rows=0`）。
  上一轮 `T0r113` 与更早 `T0r112` 仍停「拆分中」——它们的枝干没做过 Omega 复验，本轮不越轮去动，转入下一轮的收根面。
- **本轮自曝第三处尺缺陷（拒绝计数）**：a3 收根脚本的 `note()` 只认 `ok:false` 与 "refuse" 字串，
  而服务端的错误形状是 `{"__error__": {"code": -32000, ...}}` ⇒ 9 条真拒绝被记成 `refused=0`。
  已改按形状识别（`__error__` / `error` 键 / `-32` 前缀 code），并用 `call_log` 里 `result_json like '%__error__%'` 的行数做独立复核。
  同源的第二处：产物门拿 `"fail=0 rc=0"` 当连续子串 needle，而结论行中间夹着 `report=<文件名>` ⇒ 门恒假、
  第一次收根被自己的门拒了（`logs/r8_root_a1.out` 逐字保留）。
- **服务端产物的一次瞬断**：收根 v2 首跑（`logs/r8_root_b1.err`）在第一条 RPC 就 `OSError: [Errno 22] Invalid argument`
  —— `node _build/js/debug/build/cmd/cli/cli.js serve` 在加载时报
  `ReferenceError: require is not defined in ES module scope`（bundle 缺 `createRequire` 兼容层）。
  跑上游 `scripts/patch_esm_main.py` 后同一命令正常应答并重跑成功。崩前 `call_log` 09-29 05:00 之后 0 行 ⇒ 无半成品状态，重跑安全。

---

## 5. 裁决登记（本轮自决，未等人发起）

| 编号 | 决策 | 依据 |
|------|------|------|
| D-R8-1 | 推进面选「建 Ω-spec 层」而非「写新语料/新特性」 | PROJECT-SPEC/05：验证先行；R6/R7 缺陷形态都是「零诊断」，pytest 体系测不出 |
| D-R8-2 | corpus 与 pytest 共用同一批测试对，地板值只认一份（41） | 两处各写一遍必然漂移；语料改为 `make_corpus.py` 生成 + reload 断言 |
| D-R8-3 | 「什么算位置字段」收敛为单点 `ASTUtils.is_positional_member` | 两条缺陷同源于「两侧各写一遍」 |
| D-R8-4 | `BUG-114/115` 不在缺陷轮夹实现，规范条文先写明「目前未实现」 | 沿用 D-R7-4；SYNTAX/17 规则 7 显式防被读成已完成 |
| D-R8-5 | 叶分类只看每支叶自己的 description；已归档叶不重开，账面漂移只披露 | a3 实测教训；服务端无 amend/reopen |
| D-R8-6 | 混合运行与修复前运行一律标「不作验证」，终验只认 `r8_pytest_r3.log` 等三份 | 「留红比改测试凑绿诚实」；避免用中间态冒充足绿 |
| D-R8-7 | 收根前先过两道门（报告在盘 + 报告引用验针 `fail=0 rc=0`），枝干/根的 Omega 链按服务端错误文案补齐，不越轮去动上一轮的根单 | L4 产物门；`T0r113/T0r112` 的复验缺口属上一轮账面，本轮只点名 |
| D-R8-8 | 拒绝计数改按形状识别（`__error__`/`error`/`-32` code），并加一条 `call_log` 的独立复核 | a3 实测 9 条真拒绝被记成 0，「0 拒」这类主张必须有第二条读取通道 |

---

## 6. 建议入档位置

- 项目记忆（本目录）：`project-cypy-r6-selfdrive-loop.md` 续写 R8 段——
  需记的是「非读代码可得」的三件：a3 叶分类串位造成的 9 支账面漂移（无出路）、
  `report_bug(publish_task=False)` 不落 task 行（`tasks` ns='bugs' 09-29 为 0 行）、M5 尺假红的成因。
- 用户级记忆：负面向门要「只认汇总行形状 + 算术自洽」，以及「`(\d+) error` 型 needle 会被自家断言文案喂红」——
  这条属于「判据恒绿/恒红来源清单」的新成员。
- 不入档：本轮的修复细节（代码与账本已承载）、语料格号清单（`corpus/*.json` 是可执行件，抄进文档就是第二份真相）。

---

**一句话终态**：`corpus/` + Ω-gate + 回归件这层可执行规格已立住并立刻打出两条真缺陷，三套回归全绿、5/5 锁承重、5/5 负控制会红，
`T0r114` 的 18 叶 / 6 枝 / 1 根全部走完 Omega 链收口（28 调用 0 拒）⇒ 本轮「无回归」与账面闭环达成；
「所有语法特性稳定、无 bug」仍未达成——账上 34 个去重 open 编号，其中 `BUG-114/115/116` 是本轮明确交出的裁决面，
上一轮的 `T0r113`/`T0r112` 两根因缺枝干复验仍停「拆分中」。

*（内容由AI生成，仅供参考）*
