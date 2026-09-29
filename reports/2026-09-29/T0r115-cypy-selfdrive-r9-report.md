# Cypy 自驱式组合环 R9（2026-09-29）交付报告

- 驱动：FIST-Mbt 0.3.4（129 工具，MCP 2026-07-28 无状态握手，入口 `cmd/cli/cli.js serve`），ns `cypy-loop-20260929`，根任务 `T0r115`
- 环：`loop_create` 名 `cypy-selfdrive-r9`，steps `advance → bugfind → fix_and_merge → verify → polish → advance`；
  基线由实测反解：`baseline_test_count=2212`（终版 pytest）、`baseline_open_bug_count=25`（9 段账本落盘时的 open 块读数；
  本环后段又立 `BUG-117`，收尾复算 26，口径见 §2.5）
- 链形：每支叶 `claim → omega_spec_create → omega_spec_review(approve) → execute → run_check → omega_result_verify(pass) →
  submit → verify`；拆分建议 `laya_decide(no_sidecar=true)`；对账走 `call_log` + sqlite 只读复算
- 红线遵守：未 commit、未 push、未动 `examples/` golden 基准（只读跑了 `--check-only`）、未删改任何既有断言、凭据未读取未回显

---

## 1. 结论

| 面 | 判据 | 实测（逐字） |
|----|------|------|
| Ω-gate | 准确率 100% | `CONCLUSION specs=3 cases=51 passed=51 failed=0 refused=0 accuracy=100.00% rc=0` |
| pytest 全量 | 0 红且收集数可解释 | `2212 passed in 328.07s (0:05:28)`，`PYTEST_RC=0`；`2212 = 2202（R8 终版）+ 10（本轮新增测试对）` |
| 自研套件 | 47/47 | `Total: 47 \| Passed: 47 \| Failed: 0`，`NATIVE_RC=0` |
| 外部 golden | 25 例全 PASS | `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`，`E2E_RC=0` |
| 锁承重矩阵 | 摘掉即红 | `CONCLUSION baseline=… cases=51 passed=51 … control_green=True load_bearing=2/2 not_load_bearing=[]` |
| 账本 | 只增不删 | 追加 9 段（1 FIXED / 6 DUPLICATE / 2 AMENDMENT），`insert_only_verified=true`，open 块 32 → 25（追加时读数）→ **26**（本环后段又立 `BUG-117`，收尾复算） |
| FIST 账面 | 根可归档、拒绝逐字 | `CONCLUSION root=已完成 rollup={'已完成': 20, '待领取': 5} error_rows=0`（根 `T0r115` 由 `verifier` 归档）|

**目标达成度**：本轮闭掉一型真实产品缺陷（切片结果类型，BUG-71）并把一型缺陷收窄到规范已背书的半区（越界槽位），
三套全量绿 ⇒ **「无回归」达成**；「所有语法特性稳定、无 bug」**仍未达成**——账上 26 个 open 块，
其中产品面 17 条、本仓判据面 1 条、工具/账面面 8 条。

---

## 2. 证据

### 2.1 修好的第一型：切片被判成元素类型（BUG-71，卡片自设的四条判据逐一补齐）

- 根因（卡片机制栏早已写对，本轮证实）：`_visit_Subscript` 只判 `hasattr(node.slice,'kind')`，
  而切片在 AST 里是 **dict** `{"slice": True, "start":…, "end":…, "step":…}`（`cypyc/parser/parser.py:3952-3991`）
  ⇒ 走不到任何分支，直接返回 `params[0]`（元素类型）。
- 修复：`cypyc/analyzer/type_checker.py:4298` 在取元素类型之前先过 `:4311` 的切片分支，
  形态判据单点 `:4333 _is_slice_form()`（只认那个 dict；语言里没有独立 `Slice` 节点，所以不写「万一是节点」的死分支）。
- 规范先行：`SYNTAX/14-syntax-sugar.md` 新增「切片的类型规则（R9 补）」1-3 条（现测 377 行）。
- 调用面（卡片点名的仓内 DEMO，只读复跑）：
  `examples/demos/upcoming_features/planned_features.cypy` 的 `transpile --check-only`
  由修前 rc=1（4 条诊断，首条 `Type mismatch: expected list[int], got int at 60:9`）
  变修后 rc=0 —— 逐字 `[OK] Static analysis passed (no code generated)`。
- 锁：`corpus/cypy.type.slice.json` 8 格（含成对另一半：`y: int = xs[1:3]` 必须报
  `Type mismatch: expected int, got list[int]` 且带行列）+ 参数化回归格 + 矩阵 S1（形态判断恒假 ⇒ 6 格真红）。

### 2.2 修好的第二型（半区）：越界槽位不再发不存在的成员访问

- 规范依据：`SYNTAX/17-pattern-matching.md` 规则 5（R7 补）+ 规则 8（R9 补，现测 457 行）——
  **仅当字段集合在本模块可见时**，越界槽位不得生成属性访问；不可见外部类属规则 4「运行期解包」半径。
- 修复：`cypyc/codegen/cython_generator.py:1794` 引入 `fields_known`，`:1799` 仅对可见类型让该 `case` 恒不命中，
  不再走 `.__f{i}`；不可见一侧形态不变。
- 调用面逐字：修前 `if _match_subject_1.a == 1 and _match_subject_1.b == 2 and _match_subject_1.__f2 == 3:`
  → 修后 `if _match_subject_1.a == 1 and _match_subject_1.b == 2 and False:`，
  同时分析器仍报 `Positional pattern 'E' has 3 slot(s) but type 'E' unpacks only 2 at 7:14`。
- 锁：`corpus/cypy.pattern.positional.json` 第 #17/#18 格（0 基口径）+ 矩阵 S2（退回发 `.__f{i}` ⇒ 1 格真红）。
- **未闭的半区明确留在账上**：BUG-99 只加 `### AMENDMENT`，不加 `### FIXED`；BUG-96（两个同编号块）与 BUG-102
  指认正身为 DUPLICATE，其中「规范缺口」那一族仍由 BUG-99 承载开口。

### 2.3 判据扩面：Ω-spec 从 2 op/41 对到 3 op/51 对

| 文件 | op | 格数 | 指纹 |
|------|----|------|------|
| `corpus/cypy.annotation.shape.json` | cypy.annotation.shape | 24 | `fnv1a64:927770342620acae` |
| `corpus/cypy.pattern.positional.json` | cypy.pattern.positional | 19 | `fnv1a64:a157d9639e05ea07` |
| `corpus/cypy.type.slice.json` | cypy.type.slice | 8 | `fnv1a64:580098c7d0fbf2aa` |

回归地板同批抬：`FLOOR_SPECS` 2→3、`FLOOR_CASES` 41→51（`tests/regression/test_corpus_pairs.py`，仍是唯一一份地板值）。
语料由 `make_corpus.py` 生成 + `omega_gate.py --seal` 重封，未手改 JSON。

### 2.4 本轮自曝的三处尺/流程缺陷（都已改，逐字留证）

1. **一次真实回归被如实记下**：初版把规则 5 直接推广到全部形态，打红既有锁
   `tests/test_extractor_pattern.py::test_extractor_pattern_codegen`（逐字 `assert "_match_subject_1.__f0" in code`，
   全量读数 `1 failed, 2211 passed in 359.56s`，见 `logs/r9_pytest_r1.log`）。
   读该用例夹具后发现它的 `Email` **从未在该源里定义** ⇒ 属规则 4 半径 ⇒ 处置是**把改动收窄到可见字段半区**
   （§2.2），不改测试、不 xfail、不把半条规范硬推成全条。
2. **恒真断言陷阱**（另立单 BUG-117）：`op=codegen` 对已报错的程序直接返回空码（`stage=typecheck`），
   于是「产物不含 `__f2`」这类 `not_contains` 在无效程序上恒真 ⇒ 越界槽位那格改走 `codegen_unchecked`，
   并在 corpus 里写明原因；正解（gate 对 `codegen`+有错 给 refuse/warn）交裁决。
3. **门禁读错日志 + 拒绝分支不打印**：收批门最初指向 `r9_pytest_r1.log`（那一版是红的），
   于是正确地拒绝开批，但那条分支只写 json 不打印 ⇒ 后台任务拿到一份**空 stdout**（"失败了却没有任何话"）。
   已改为指向终版 `r9_pytest_r2.log` 并让每条拒绝分支都打逐字 tail；两份读数都留着：
   `logs/r9_closure_a2.out`（空 stdout 的形状）与 `logs/r9_closure_a3.out`（修好后 8 条逐字拒绝）。

### 2.5 账本（`memory/bugs.md`，append-only）

- 抬头 117（`BUG-96` 双写）、`### FIXED(` 83、`### DUPLICATE(` 8、`### AMENDMENT(` 5；改动前快照
  `.fist-loop-20260929/bugs.md.pre_r9_ledger`，difflib 证明 `insert_only_verified=true`。
- **open 口径必须点名**：`### NOT-FIXED(...)` 的含义是「转结未修＝开口」，所以闭合段只认 `FIXED|DUPLICATE|OUT|WONT`。
  同一份账本在该口径下 open 块 32→25（9 段落盘时）→ **26**（本环后段立了 `BUG-117`）；
  若沿用 R8 报告的「只看 `### FIXED(`」口径，数字会不同——两个口径不混用。
- 26 个 open 编号：`BUG-40 43 49 50 52 54 65 68 69 70 72 73 94 97 99 100 103 105 106 109 110 111 114 115 116 117`
  （产品面 17：40/43/49/50/52/54/65/68/69/70/72/73/99/109/114/115/116；本仓判据面 1：117；
  工具与账面面 8：94/97/100/103/105/106/110/111）。
- 账本改动之后重跑读账本的测试族：`166 passed`（`test_loop_20260927_polish_r4` / `_advance_r4` /
  `test_polish_20260926` / `test_pattern_positional_struct` / `test_annotation_shape` / `test_extractor_pattern` / `tests/regression`）。

### 2.6 FIST 账面（`call_log` 复算，不靠回忆）

- 主批 a3：`calls=142 refused=8`，8 条逐字都是形状类拒绝（例：
  `Omega 强验证门禁：任务 [T0r115.3] 尚未做成果复验，请先由验证者执行 omega_result_verify`）。
  **本轮拒绝计数不再假 0**：R8 那版 `note()` 只认 `ok:false`/"refuse"，把 `{"__error__":…}` 全记成未拒；
  本轮按形状识别，并用 `call_log` 的 `result_json like '%__error__%'` 行数独立复核（补腿阶段 `error_rows=0`）。
- 补腿一（`close_r9_branches.py`）：枝干/根 `execute` 落交付物 ⇒ `拆分中 → 执行中`，
  但 `result_verify` 之前必须先 `submit`，逐字 `非法验收: 任务处于 [执行中]，需先 submit`（20 调用 12 拒，全是这一形状）。
- 补腿二（submit→verify）：`T0r115.3/.4/.5` 与根全部 `已完成`，
  `CONCLUSION root=已完成 rollup={'已完成': 20, '待领取': 5} error_rows=0`。
- 留下的 5 支待领取叶按编号点名，不伪造关闭（逐字取自 sqlite）：
  `T0r115.3.2 / T0r115.4.1 / T0r115.4.2 / T0r115.5.1 / T0r115.5.2`。
  它们的形状是 `task_plan_deep` 多生的「逐字复制根单描述」叶（BUG-110），且待领取叶无代理可见退役出路（BUG-106）。
- `laya_decide(no_sidecar=true)` 回 `available:false / source:fallback / split_n:5`（已知形状，BUG-65 系）。
- 新单：`BUG-117`（回执逐字 `{"bug_id": "BUG-117", "id": "BUG-117", "status": "OPEN", "path": "./memory/bugs.md"}`），
  走 `publish_task=False` ⇒ 与 R8 同样不产生 `tasks` 行（账在 md + `call_log`）。

---

## 3. 分析：为什么这轮值得先读那条被打红的锁

R8 的结论是「同一事实的两处读取不一致」，本轮的切片缺陷正是同一形状在第三个读取点（下标 vs 切片的形态判断）上的复现。
但更值得记的是中途那次红：**我按规范收紧，规范本身却分两条管辖半径**（规则 5 管可见字段、规则 4 管不可见外部类）。
如果把被打红的断言改成新的期望，就等于用我这一轮的读法覆盖掉「不可见类型走运行期解包」这条既有承诺；
如果硬推到全形态，产物会留下未绑定的名字（该用例的 `print(user, domain)`）——那是把「静默错值」换成「编译期未定义」。
两条都不如**收窄 + 明确记账未闭半区**诚实。判据面同理：`not_contains` 跑在空产物上恒真，
所以「产物不含 X」的断言必须先证明该阶段真的出了产物（BUG-117 就是这么打出来的）。

---

## 4. 缺口与风险

| 面 | 状态 | 备注 |
|----|------|------|
| 越界槽位·不可见类型半区 | **未修，开口（BUG-99）** | 需要先裁规则 4 的运行期解包形态；既有锁 `test_extractor_pattern_codegen` 钉着当前形态 |
| `tuple<int, ...>` / `case (x, y, ..)` | 未修（BUG-114） | 进不了解析器，要动类型语法与模式语法 |
| `__match_args__` 名称序 | 未修（BUG-115） | 元数仍按字段声明序 |
| Ω-spec 覆盖面 | 未闭（BUG-116） | 已推进到 3 op/51 对，其余 20+ 章节仍无 spec |
| `codegen` 空码使 `not_contains` 恒真 | 新单（BUG-117） | 判据面缺陷，本轮用 `codegen_unchecked` 绕开而不是修 gate |
| 上一轮的 `T0r113` / `T0r112` | 仍「拆分中」 | 枝干缺 Omega 复验；本轮不越轮动它们（形状已在 R8 报告与本轮补腿里实测清楚） |
| 5 支待领取叶 | 无出路 | BUG-106；按编号点名 |
| **流程债：收根早于本报告落盘** | 已发生，不可回滚 | PROJECT-SPEC/05 的 L4 产物门要求「报告先落盘才能收根」，本轮开批门只钉了 Ω-gate 与 pytest 终版两条，**没有把报告文件当门**，于是 `T0r115` 在本报告写出来之前就归档了（`completed_by=verifier`，05:35；报告 05:36）。归档后不可 reopen，报告也不能作为第二份交付物重挂上去 ⇒ 只能记流程债；下一轮的收批门要加「报告在盘」这一条（R8 已有现成件 `close_r8_root.py` 的两道门可抄） |

---

## 5. 裁决登记（本轮自决）

| 编号 | 决策 | 依据 |
|------|------|------|
| D-R9-1 | 靶面从账本 open 清单选，而不是新写语料 | 目标是「无 bug」；且 R8 证明判据层立刻能打出真缺陷 |
| D-R9-2 | 关闭动作一律由实测格驱动，主张作废用 DUPLICATE 指认正身而非删正文 | 账本 append-only；BUG-107 记的双发只能指认 |
| D-R9-3 | 既有锁被打红时**收窄改动到规范背书半区**，不改断言、不 xfail、不硬推全形态 | §3；`1 failed, 2211 passed` 的逐字夹具证据 |
| D-R9-4 | 半区修复只写 AMENDMENT，不写 FIXED | 「已修一半」必须是三态标记，不能被下一轮读成全闭 |
| D-R9-5 | `not_contains` 类断言改走 `codegen_unchecked`，并把恒真陷阱另立单 | 判据不能靠空产物充绿 |
| D-R9-6 | 收批门的每条拒绝分支都必须打印逐字 tail | 「失败但空 stdout」不可审 |
| D-R9-7 | 不越轮去动 R6/R7 的根单 | 它们的复验债属上一轮账面，本轮只把形状测清 |

---

## 6. 建议入档位置

- 项目记忆：`project-cypy-r6-selfdrive-loop.md` 续写 R9 段——要记的是非读代码可得的三条：
  ①「收根需要 execute→submit→verify 三段，枝干同理，且 depth 是离叶距离」；
  ②「`report_bug(publish_task=False)` 不落 `tasks` 行」；③ open 口径必须点名 `NOT-FIXED` 属开口。
- 用户记忆：本轮已写入「判据恒绿/恒红清单」（相邻字段 needle、整段数符号、空产物上的 `not_contains`）与
  「全局缓解不得遮掉钉住的缺陷」（按规范分半径收窄，而不是改测试）。
- 不入档：修复细节（代码 + 账本已承载）、corpus 格号清单（可执行件，抄进文档就是第二份真相）。

---

**一句话终态**：切片类型面按仓内自带 DEMO 的调用面闭透（rc 1→0）、越界槽位面在可见字段半区闭合并把未闭半区如实钉在账上，
Ω-spec 扩到 3 op/51 对且两条修复各配「摘掉即红」的锁，三套全量绿、根 `T0r115` 归档（`rollup={'已完成': 20, '待领取': 5}`）；
「所有语法特性稳定、无 bug」仍未达成——账上 26 个 open 编号（产品 17 / 本仓判据 1 / 工具与账面 8），R6/R7 两根待收。

*（内容由AI生成，仅供参考）*
