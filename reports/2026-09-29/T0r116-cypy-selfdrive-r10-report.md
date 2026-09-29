# T0r116 · Cypy 自驱组合环 R10 报告

- 轮次：R10（推进 → 寻虫 → 修复 → 验证 → 打磨 → 推进）
- FIST 命名空间：`cypy-loop-20260929` · 根单：`T0r116` · 环名：`cypy-selfdrive-r10`
- 执行者：`cypy-selfdrive-agent` · 日期：2026-09-29（UTC 起于 05:45Z）
- 判据基线（开工实测，非沿用）：pytest `2212 passed`（`.fist-loop-20260929/logs/r9_*` 上轮终验）；
  本轮终验见 §5.4
- 本轮半径：**泛型调用点的类型实参**（`SYNTAX/11-generics.md`），半径外一律只入账不动手

> 口径说明（本报告的每个数字都能反解）：文件路径给出即证据件；`logs/*.log` 与 `*.json` 均在
> `.fist-loop-20260929/`；「实测」= 本轮在这台机器上跑出来的，「主张」= 别人或旧轮写的、我未复测的。

---

## 1. 本轮做了什么（一句话版）

把 `f<T>(x)` 从"被当成 `<checker>` 参数检查站"改回手册承诺的"类型实参表"：解析收多项、
分析器按声明顺序代入并判元数、产物一律擦除实参；顺带把第二台发射器（`cypy_bridge`）里的同形死码删掉。
寻虫腿在同一个探针面上打出 7 张新单（BUG-119…125），判据层从 3 op/51 对扩到 **4 op/71 对**，
并用 6 格变异矩阵证明三处改动各自承重。

---

## 2. 靶面是怎么选出来的

不是新发明的语法，而是账本 + 手册的缺口：

1. `SYNTAX/11-generics.md` 是手册章节（137 行 → 本轮 164 行，实测 `wc -l` 面为 164 行），承诺 `identity<int>(42)`、
   `pair<int, str>(42, "answer")`、`class Box<T>:`、`trait Container<T>:` —— 但 `corpus/` 里
   没有一份 spec 覆盖泛型（实测 `corpus/` 本轮前只有 3 份：`cypy.annotation.shape` 24 对、
   `cypy.pattern.positional` 19 对、`cypy.type.slice` 8 对）。
2. 账本里泛型同族的旧单（BUG-21、BUG-55）都已 FIXED，说明"泛型登记面"被修过，
   但"泛型调用点"从未被任何判据认领。
3. `SYNTAX_IMPLEMENTATION_STATUS.md:339` 把 `11-generics.md` 标成「✅ 完整 / 无缺口」——
   无判据认领的主张正是本轮该测的地方（该格现状见 §7 与 BUG-124）。

---

## 3. 寻虫（探针 + 基线，全部实测）

探针件：`.fist-loop-20260929/probe_r10_generics.py`（复用 `scripts/omega_gate.py` 的 `execute()` ⇒
与 Ω-gate 同一把尺子），15 个形态 × `typecheck`/`codegen` 两面，逐字输出
`.fist-loop-20260929/logs/r10_generics_probe1.out`。
基线件：`.fist-loop-20260929/baseline_r10_typeargs.py` → `baseline_r10_typeargs.json`，
逐字输出 `logs/r10_baseline_typeargs2.out`，结论行：
`CONCLUSION files=77 parse_fail=0 callsites=13 risk_n=0`，形态分布
`SHAPE {"generic_func": 11, "generic_struct": 2}`。

### 3.1 本轮修掉的那条（BUG-118）

- `identity<Foo>(v)`（`Foo` 是带必填字段的 struct）产物曾是 `return (Foo(), identity(v))[1]` ——
  运行期含义是把类型名当零参函数调用；`--check-only` 与 codegen 都 0 诊断 ⇒ 静默错误产物。
  全仓 13 处调用点用该形态，其中 `examples/demos/traits_duck/duck_basic.cypy:143,147`
  （`display_name<NamedItem>(item)`、`resize<SizedBox>(box, 20)`）就是用户定义类型。
- `pair<int, str>(42, "a")`（手册 :23 承诺）曾是 `Unexpected token COMMA at 6:34`（解析器只收单个标识符）。
- `identity<int>("Alice")` 曾 0 诊断；`pair<int>(42)`（被调方 `<T, U>`）曾无元数诊断。

### 3.2 打了卡但**不在本环半径**的（逐条一句话）

| 单号 | severity | 一句话（实测形态，非推测） |
|------|----------|------------------------------|
| BUG-119 | high | `class Box<T>:` 直接 `Expected COLON, got LT at 1:10`；同写法 `struct Wrap<T>` 可用（探针 G14/B2） |
| BUG-120 | medium | `trait Foo:` 的无体抽象方法 `Expected increased indentation at line 3`；非泛型同形 ⇒ 不是泛型专属（F1/F2） |
| BUG-121 | high | 方括号形态 `identity[list[int]](xs)` 被当"下标后调用"原样进产物 ⇒ 运行期 `TypeError`，0 诊断（G13/A3） |
| BUG-122 | medium | 类型实参子树不被 visit ⇒ `f<Undefined>(x)` 静默降级 `object`（本环代入实现的亲笔限制） |
| BUG-123 | medium | `inspect.getsource` 型锁在同一进程内被测文件行号漂移时读到错位窗口 ⇒ 本轮 `r10_pytest_a2.log` 打出一次假红（见 §5.5） |
| BUG-124 | medium | `SYNTAX_IMPLEMENTATION_STATUS.md` 每章写「✅ 完整 / 无」，`grep -rn SYNTAX_IMPLEMENTATION_STATUS tests/ scripts/ PROJECT-SPEC/` → 0 命中（无主主张） |
| BUG-125 | high | 用户 `def id(x: int) -> int` 的调用点在产物里被改写成 `<size_t><void*>3`，`addr(3)` → `&3`，0 诊断（`cython_generator.py:3779-3810` 只看名字） |

### 3.3 边界审视（本轮新语法面的输入域四类）

实测（探针，逐条进 Ω-spec 而非只写在报告里）：

| 类别 | 形态 | 实测结果 |
|------|------|----------|
| 空 | `identity<>(1)` | `stage=parse`，`Unexpected token GT at 6:15` ⇒ 语法级硬拒，不收"能吃但无人管" |
| 非法 | `identity<int,>(1)`（尾逗号） | `stage=parse`，`Unexpected token COMMA at 6:18` ⇒ 不做隐式扩张 |
| 非法 | `mk<int, str>(1)`（非泛型挂两项） | `Type arguments on non-generic 'mk': it declares no type parameter, got 2 at 6:12` |
| 极值/嵌套 | `identity<list<list<int>>>(xs)` | 解析收下且代入 ⇒ 返回 `list[list[int]]`（三连 `>` 未被切错） |
| 复合 | `identity<dict[str, int]>(d)`、`identity<int | float>(v)` | `errors=0`，方括号/管道内的逗号不得当实参表分隔符 |
| 资源极限 | —— | **显式声明不适用**：类型实参是编译期语法/代入判定，无堆增长、无循环、无 I/O，故本形态无可测的资源维度；这一格不给断言（不给恒真门） |

---

## 4. 规范先行 + 修复面

### 4.1 条款（先写规范，再改实现）

`SYNTAX/11-generics.md` 新增「调用点的类型实参」5 条 + 「明确不支持」表：

1. 调用点 `<…>` 只有类型实参这一种解释（`<checker>` 在定义侧且 `SYNTAX/33:518` P-1.8 已判 v1 不支持）；
2. 元数必须等于被调方声明的类型参数个数，非泛型被调方挂 `<…>` 亦判；
3. 多项可写，逗号分隔，每项是类型表达式；
4. 产物必须擦除：既不得留下标形态，也不得插入对类型名的零参调用；
5. 代入优先于推断，且与约束一起判。

「明确不支持」表逐条指认 BUG-119/120/121/122 —— 手册不再宣称自己做得到。

### 4.2 实现落点

| 文件:行 | 改动 |
|---------|------|
| `cypyc/parser/parser.py:650-659` | `Call.checker`（字符串）→ `Call.type_args`（类型表达式表） |
| `cypyc/parser/parser.py:3855-3885` | 可回溯试探的 `< type {, type} >` 判定：整形状对不上就恢复 `self.pos`，交回比较运算分支 |
| `cypyc/parser/parser.py:3943-3951` | 实参表只归紧邻一次调用（链式 `f<T>(a)(b)` 第二段不继承） |
| `cypyc/codegen/cython_generator.py:3814-3818` | 删 `(checker(), f(args))[1]` 分支，产物只留调用本身 |
| `cypyc/analyzer/type_checker.py:1272-1301` | 新增 `_bind_explicit_type_args`：元数、非泛型、按声明顺序代入 |
| `cypyc/analyzer/type_checker.py:1330-1347` | 泛型函数路径：显式实参优先于统一化推断（没写才推断） |
| `cypy_bridge/compiler.py:284-289` | 第二台发射器里读 `node.checker` 的同形死码一并删（解析器不再产出该字段） |

半径自觉：BUG-121 的方括号形态、BUG-119 的泛型类（要动 `ClassDef` 签名 + class 出码 + 名字空间三处）、
BUG-120 的 trait 抽象方法（需 owner 先裁"必须有体"还是"接受无体"）、BUG-122（会牵出既有
`Undefined name` 模板对复合类型的连带判定）—— 一律只入账，不在本环扩权动手。

---

## 5. 判据与验证

### 5.1 Ω-spec 扩面

- 生成件：`.fist-loop-20260929/make_corpus_r10.py`（落盘前逐条用 `omega_gate.execute/judge` 自证，
  断言与实测不符 ⇒ 拒绝写 `corpus/`）
- 新增 `corpus/cypy.generic.callsite.json`：20 对，指纹 `fnv1a64:65bd56a87c83d42a`
  （14 对主形态 + 6 对 §3.3 边界）
- 判据层从 3 op/51 对 → **4 op/71 对**
- 逐字跑批：`CONCLUSION specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0`

### 5.2 回归锁

- `tests/test_generic_callsite_r10.py` 9 支（4 支产物擦除、2 支诊断、1 支代入、1 支约束、
  1 支对照半边「`<` 作为比较运算不被前视吃掉」）
- `tests/regression/test_corpus_pairs.py` 地板 `FLOOR_SPECS` 3→4、`FLOOR_CASES` 51→71
  （同一批 pair 在 pytest 面逐对执行）

### 5.3 变异矩阵（承重证明）

`.fist-loop-20260929/verify_r10_locks.py`，每格一棵独立树（树名带 pid），9 道门全过，
逐字结论 `CONCLUSION cases=6 gates_pass=9/9 ok=True`（`.fist-loop-20260929/logs/r10_locks_a4.out`）：

| 格 | 变异 | pytest 红 | Ω-gate（14 对时） |
|----|------|-----------|--------------------|
| L0 | 不修（现状） | 0 | 14/14 rc=0 |
| L1 | 解析+生成+分析三处全退回修复前 | 18 | 3/14 rc=1 |
| L2 | 只退解析器 | 10 | 8/14 rc=1 |
| L3 | 只退分析器 | 7 | 10/14 rc=1 |
| L4 | 只把产物改回 `(类型名(), f(x))[1]` | 9 | 8/14 rc=1 |
| L5 | 只改注释（对照格） | 0 | 14/14 rc=0 |

读法：L1–L4 每格都红 ⇒ 三处改动**各自**承重（不是只有整体退回才红）；
L5 不红 ⇒ 尺子数的是语义而不是我的散文。矩阵自己也是被判据面：
第一版脚本的解析器回退锚点命中了 `parser.py` 里另一处同名行（12 空格缩进的 `saved_pos = self.pos`），
把文件剪坏 ⇒ `rc=2` 被 `no_ruler_crash_in_any_case` 这道门打成假绿风险，
已加"逐字含缩进匹配 + 区间长度 < 40 行 + 复原后必须 `compile()` 通过"三条自证，
坏尺子的证据留在 `.fist-loop-20260929/verify_r10_locks.run1_rulerbroken.json`（不覆盖）。
注：L1–L5 的红数是**语料 14 对时**测的；语料到 20 对后，承重的格只会红得更多，未重跑数不写。

### 5.4 三套全量（冻结被测量面后）

| 判据体系 | 逐字结论 |
|----------|----------|
| `python -X utf8 -m pytest tests` | `2241 passed in 406.00s`，`pytest_rc=0`（`logs/r10_pytest_a4.log`） |
| `python -X utf8 scripts/run_tests.py` | `Total: 47 \| Passed: 47 \| Failed: 0 \| Skipped: 0`，`native_rc=0`（`logs/r10_native_a2.log`） |
| `bash scripts/e2e_golden.sh` | `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`，`e2e_rc=0`（`logs/r10_e2e_a2.log`） |
| Ω-gate | `specs=4 cases=71 passed=71 failed=0 refused=0 accuracy=100.00% rc=0` |

算术自证：2212（上轮终验）+ 9（新锁）+ 20（新 pair）= 2241 ⇒ 与实测数一致，无静默丢失用例；
收集面另由 `test_generic_callsite_r10.py` 9 支与 `test_corpus_pairs.py` 的 71 支点名覆盖。

### 5.5 一次作废的全量跑（如实入账）

`logs/r10_pytest_a2.log`（`1 failed, 2234 passed`）**判作废**：该轮跑到 84% 时我改了
`cypy_bridge/compiler.py:284` 区（净 +1 行），而失败的那条锁用 `inspect.getsource` 读
`_compile_c_to_shared_lib`（函数 :3760、目标行 :3837）—— 已导入的 code 对象带着旧行号切新文件，
窗口错位 1 行 ⇒ `scan` 空 ⇒ `assert ([])`。同一条件单跑绿（`1 passed in 0.34s`，
`logs/r10_bug26_single_a1.log`；更早那次 0.08s 的读数没留文件证据，故本处不引用它，
账本 BUG-123 里的 `0.08s` 已另补 AMENDMENT 指认本件），
冻结后 a3（2235 passed）与 a4（2241 passed）两轮 rc=0。
机制不是猜测，缺陷已入账 **BUG-123**；流程侧本轮按规范补的纪律是"基线起跑后冻结被测量面，
动了就重跑并留 run1"。

---

## 6. 账面（FIST 与账本）

### 6.1 账本

`.fist-loop-20260929/close_r10_ledger.py`（写前留 `bugs.md.pre_r10_fixed` 快照，写后逐字校验前缀与标题行）：

- 本轮新开 8 张：BUG-118（已 FIXED）、BUG-119…125（OPEN）
- 追加段：`### FIXED(修复=已完成) — 2026-09-29` 2621 字节，`### FIXED` 段总数 83→84
- 账本头数 118→126，逐字实测 `headers=126`，`bug_list` 回读 `126` 行 ⇒ 两向对齐
- open 块 **34**（单一口径：块内无 `### FIXED` 也无 `### DUPLICATE`），
  按 severity 实测 6 high / 19 medium / 9 low；按 `- summary:` 前缀粗分：判据/文档面 3（BUG-117、BUG-123、BUG-124）、其余 31
- 算术自证：上轮收口后同一口径 open=27（快照 `.fist-loop-20260929/bugs.md.pre_r10_file` 实测）
  ＋本轮新开 8 －关闭 1 = 34 ✔
- 口径差别要说清：把关闭标记放宽到 `### (FIXED|DUPLICATE|OUT|WONT)`（R9 的 `loop_create` 用的就是这条）
  实测 open=33 —— 差的那一条是 BUG-77（带 OUT/WONT 段）。本报告的 34 用的是上面写明的窄口径。
- **口径更正**（不代写、不删条）：R9 报告写的「open 块 32→25→26」用的是另一套口径（未在本轮复述规则下重算）。
  本轮统一口径后同一份快照实测 27（R9 收口时点）⇒ 后续轮次以"块内无 FIXED/DUPLICATE"为准。

### 6.2 FIST 环账面

（渲染于收根之后，输入件均为本腿回执）

本小节的每个数字都从下列回执件反解：`close_r10_ring.json`、`close_r10_ring2.json`、
`close_r10_ledger.json`、`file_r10_bugs.json`、`audit_r10_stuck.json`、`verify_r10_report.json`，
逐字结论行见 `logs/r10_ring_a2.out`、`logs/r10_ring_a3.out`。

**环与树**：根单 `T0r116`（描述带 `[omega:required]`），
回读形状 {"root": "T0r116", "rows": 17, "leaves": 12, "branches": 4, "general": ["T0r116.1.1", "T0r116.1.2", "T0r116.2.1", "T0r116.2.2", "T0r116.3.1", "T0r116.……；
`loop_create` 六步环 `cypy-selfdrive-r10`（steps：advance→bugfind→fix_and_merge→verify→polish→advance，
`baseline_test_count=2241`、`baseline_open_bug_count=34`），
`laya_decide` 回执 "{\"available\": false, \"decision\": {\"source\": \"fallback\", \"complex\": true, \"feature_route\": \"拆解调度\", \"split_n\": 4, \"splits_per_family\"……

**每叶完整链**（claim → omega_spec_create → omega_spec_review → execute → run_check →
omega_result_verify → submit → verify，`verify` 一律带 `docs_check=True`）：
第一腿逐字 `CONCLUSION root=T0r116 root_status=拆分中 rollup={'待验收': 12, '拆分中': 4} non_terminal=[['T0r116.1', '拆分中'], ['T0r116.1.1', '待验收'], ['T0r116.1.2', '待验收'], ['T0r116.1.3', '待验收'], ['T0r116.2', '拆分中'], ['T0r116.2.1', '待验收'], ['T0r116.2.2', '待验收'], ['T0r116.2.3', '待验收'], ['T0r116.3', '拆分中'], ['T0r116.3.1', '待验收'], ['T0r116.3.2', '待验收'], ['T0r116.3.3', '待验收'], ['T0r116.4', '拆分中'], ['T0r116.4.1', '待验收'], ['T0r116.4.2', '待验收'], ['T0r116.4.3', '待验收']] calls=117 refused=70 call_log_error_rows=0`；补腿逐字 `CONCLUSION root_status=已完成 rollup={'已完成': 17} calls=95 refused=0 benign=0 call_log_error_rows=0`；补腿第一支叶的步骤回执 {"reject": "ok", "retry": "ok", "execute": "ok", "run_check": {"state": "passed", "ok": true, "tail": " cases=19 passed=19\r\nSPEC cypy.type.slice cases=8 passed=8\r\nCONCLUSION specs=4 cases=71 passed=71 failed=0 refuse……

**本轮把 R9 欠的流程债做成了入口门**：开批前四件全查（报告在盘且 ≥6000 字节、
引用核验件 `failed=0` 且 `report_bytes` 与当前报告逐字相等、Ω-gate 终值 `cases=71 … rc=0`、
三套终验日志各自命中），任一不合就整腿拒收并打印原因（`close_r10_ring.py` 的 `entry_gate()`）。
R9 那笔「收根早于报告落盘」的流程债本轮不再是转结，而是**机制上不可能再发生**。

**`docs_check=True` 实测打回过一次**（这是本轮学到的服务端门禁，不是我的臆想），
第一腿逐字拒绝文案 `REFUSED T0r116.1.1 verify | {"__error__": {"code": -32000, "message": "文档一致性门禁未通过：回传段: 结论: 缺失；回传段: 证据: 缺失；回传段: 分析: 缺失；回传段: 缺口与风险: 缺失；回传段: 建议入档位置: 缺失"}}`
⇒ 交付物必须是「结论 / 证据 / 分析 / 缺口与风险 / 建议入档位置」五段式。
处置：**照做而不是关门禁** —— 12 支叶按服务端给出的出路
（`reject → retry → execute → submit → verify`）重写五段式交付物后重收，
补腿 `refused=0`、`call_log_error_rows=0`。

**重复噪声**：第一腿在"已经走过一遍链"的叶上重复发 spec 步骤 ⇒ 70 条
`语料 […] 已通过审核，无需重复创建` 一类拒绝，
这不是账面缺陷而是脚本没按状态分派；补腿改为按当前状态 + `specs` 表计数分派后噪声归零
（`benign=0` 意味着连噪声都不需要了）。

**账本**：本轮 8 张单全部走 `report_bug` 取号（`filed=5` +
`filed=3`，`refused=0`，
`new_ids=[118, 119, 120, 121, 122, 123, 124, 125]`），
账本 `bug_list` 回读 0 行与头数 126 双向对齐；
BUG-118 的 `### FIXED` 段 + 两条 `### AMENDMENT`（0.08s 读数改指到有文件的证据件、
file:line 锚漂移更正）全部只增不改（`prefix_identical=true`、`header_untouched=true`）。

**上一轮卡点审计**（`audit_r10_stuck.py`，只读库，不强推）：
`T0r116` 本轮树：{"total": 17, "non_terminal": 0, "pending_leaves": 0, "closable_now": 0, "blocked_by_children": 0} ⇒ 零非终态节点；上一轮两棵树 `T0r113`={"total": 21, "non_terminal": 7, "pending_leaves": 4, "closable_now": 4, "blocked_by_children": 3}、`T0r112`={"total": 29, "non_terminal": 21, "pending_leaves": 15, "closable_now": 15, "blocked_by_children": 6}。审计口径：叶子状态是 `待领取`（共 19 支）时，其父枝与根**不能**诚实收口 —— 要么拿真实交付物把叶子走完整链，要么等有退役出路（BUG-106）。本轮不伪造这两棵树叶子的交付物，因此 `T0r112`/`T0r113` 继续留 `拆分中`，这是**账面事实**而不是本环的欠账：本轮新树 `T0r116` 已 17/17 全闭。

**本轮 FIST 调用面**：两腿合计 212 次工具调用
（另有入账两批的 `report_bug`/`bug_list` 面，逐条回执见 `file_r10_bugs.json` 与 `close_r10_ledger.json`），
`call_log` 里 `__error__` 行数两腿分别为 0/0；
拒绝按形状逐条捕获，未做"过滤掉再报数"。

**引用核验**：`verify_r10_report.py` {"checks": 14, "failed": []}
—— BUG 号 [21, 55, 77, 106, 109, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125]、路径 17 个、逐字结论 9 条、
file:line 锚 9 条（含两条 canary：区间整体平移必须红、不存在的单号必须被点名）。


---

## 7. 本轮决策（自决，不等发起）

| 编号 | 决策 | 依据与代价 |
|------|------|------------|
| D-R10-1 | 靶面选"泛型调用点"而非新语法 | 手册已承诺、判据零覆盖、账本无主 ⇒ 缺口成本最低且可判 |
| D-R10-2 | 调用点 `<…>` 一律按类型实参解释，**删**掉 checker 语义而非二者共存 | `<checker>` 在定义侧且 SYNTAX/33 P-1.8 已判 v1 不支持；共存等于让手册继续说谎。代价：`Call` 字段改名，需全仓消费者复核（子代理扫面：除 `cypy_bridge` 外零活读者） |
| D-R10-3 | 多项类型实参按手册收下（`pair<int, str>(…)`） | 手册 :23 明文；实测原为解析错误 |
| D-R10-4 | 方括号形态 `f[T](x)` **不**并入本轮修复，只入账（BUG-121） | 手册从未承诺；把它判成类型实参是"扩大语言"，需要 owner 先定口径 |
| D-R10-5 | 泛型类解析（BUG-119）与 trait 抽象方法（BUG-120）转结下轮 | 分别要动 ClassDef 签名/出码/名字空间 与 文档-实现二选一裁决 |
| D-R10-6 | 边界四类里"资源极限"显式声明不适用，不给断言 | 该形态无堆/无循环/无 I/O；写恒真门比不写更坏 |
| D-R10-7 | 上一轮卡住的 `T0r112`/`T0r113` 不强推收口 | 19 支 `待领取` 叶无代理侧退役出路（BUG-106），强推＝伪造账面；本轮只做审计（§6.2） |

---

## 8. 目标达成度（不提前收口）

**"所有语法特性稳定、无 bug、无回归"未达成**，如实记：

- 产品面 open 31 条（含本轮新立 5 条产品面：119、120、121、122、125）
- 判据/文档面 open 3 条（117、123、124）
- 泛型族里手册与实现的分叉只闭合了调用点一项（`<>` 形态），
  泛型类、trait 抽象方法、方括号形态、类型实参存在性四项仍开
- 无回归这一面本轮有证据：三套全量 + Ω-gate 全绿，且新锁承重（§5.3）；
  但"无回归"是对**全部**语法的断言，现有判据只覆盖 4 op/71 对，覆盖面不足本身已入账（BUG-116 仍开）

需要 owner 裁决的（不阻塞本轮收口，本轮按上述自决推进过）：
① BUG-120 走"文档补'必须有体'"还是"解析器接受无体签名"；
② BUG-121 的方括号形态是语法级硬拒还是并入类型实参表；
③ BUG-124 的状态表是配判据还是窄化口径；
④ BUG-125 内置特判与用户重名的出路（诊断 vs 让位）。

---

## 9. 下一环入口（R11 靶面，按成本排序）

1. BUG-119 泛型类：`class Box<T>:` 解析 + `Box<int>(42)` 的代入 —— 与本轮调用点修复同一条链，
   且手册已有完整范例（:107-125），判据可直接续在 `cypy.generic.callsite` 的姊妹 op 上
2. BUG-109（旧单）：注解位的类型表达式产生器缺失 —— 与 BUG-122（类型实参子树不被 visit）同族，
   可一批收
3. BUG-121/120 需要 §8 的裁决位；若 owner 未回，我按 D-R10-4 的读法继续"只入账不动手"
4. 判据扩面（BUG-116）：从 `SYNTAX/06-enum.md`、`SYNTAX/09-functions.md` 里各挑一个"手册承诺但零判据"的 op

---

*报告身份：本文件由 R10 自驱环写入；引用核验件 `.fist-loop-20260929/verify_r10_report.json`，
核验脚本 `.fist-loop-20260929/verify_r10_report.py`（每条 BUG 号、每个数字、每个路径逐格反解）。*
