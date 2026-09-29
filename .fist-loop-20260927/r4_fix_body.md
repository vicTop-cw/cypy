## 一、这一环做了什么

R4-寻虫 入账的 BUG-61..BUG-70 十张单，本环按「本环可修 / 下一环 / 交人工」三栏分派后动手。
分派表从盘上账本反解（`memory/bugs.md` 的标题行与 `- summary:`），不是手抄：

- 本环修（产品码）：{{fix_r4_claim.json|fixed_code}} —— 四条根因都在同一个分析器文件里，
  且共用同一套签名结构与兼容谓词；
- 本环修（文档面）：{{fix_r4_claim.json|fixed_docs}} —— `docs/USAGE.md` 不是冻结面，
  按 argparse / dataclass 实读改写；
- 下一环：{{fix_r4_claim.json|next_round}} —— 要真编译才能判，本环无授权；
- 交人工：{{fix_r4_claim.json|handoff}} —— 冻结面 / 不可逆结构改动 ⇒ 只挂账不动刀。
- 认领件的自我修正：{{fix_r4_claim.json|note}}

产品码改动只落在一个文件：`cypyc/analyzer/type_checker.py`。
**注**：本环根任务发布时我在 `description` 里把它写成 `cypyc/semantic/type_checker.py`（路径笔误）。
`description` 发布后没有任何工具能改（120 个工具里没有改 description 的那一个），所以这条错位会
一直留在任务库里；正确路径以本报告与 `fix_r4_rc.json` 的 `target` 为准。

## 二、根因合并修：共享件与调用点

- 改动量：{{fix_r4_rc.json|added_lines}} 增 / {{fix_r4_rc.json|removed_lines}} 删；
- 新增定义：{{fix_r4_rc.json|new_defs}}；
- 共享符号：{{fix_r4_rc.json|shared_symbols}}；
- 调用点合计：{{fix_r4_rc.json|call_site_total}} 处；
- 对照基线：{{fix_r4_rc.json|baseline}}。

四条根因不是四个补丁，而是同一张表 + 同一个判定入口的四条腿：

| 根因 | 缺的是哪一层 | 落在共享件的哪一处 |
|---|---|---|
| RC1 函数符号被登记成它的返回类型 | 没有「可调用签名」这个数据结构 | `_register_callable` 建 `callable_sigs` / `callable_arity` |
| RC2 实参类型从不与形参声明比对 | 没有可复用的兼容性谓词 | `_callable_arg_mismatch` 内部走唯一的 `_is_subtype`（INV-2） |
| RC3 struct 成员类型在方法体里解析不出 | 同一张签名表没覆盖属性位调用 | `_visit_Attribute` 的 Callable 分支 + `self` 绑定不再被 `object` 覆盖 |
| RC4 诊断文案外泄内部表示 | 显示层与判定层混在一起 | `_type_display` + `_mismatch` 单一出口 |

逐根因的符号引用计数与共享机制说明：{{fix_r4_rc.json|note}}
差量**不是** `git diff HEAD`——工作区在 R1 之前就是脏的，拿 HEAD 作差会把 R1–R3 的 1164 行
增量算到本环头上（这个坑我在本轮第一次跑 `fix_r4_rc.py` 时真的踩了，改成与本轮快照比）。

## 三、锁先行与回退矩阵

锁文件 `tests/test_loop_20260927_fix_r4.py`：12 条参数化夹具 + 3 条承重对照 +
2 条调用面/文案锁 + 1 条横向泄漏锁，共 18 条。

- 修前实测：`{{fix_r4_locks.json|before.summary_line}}`（红名单 14 条在
  `fix_r4_locks.json` 的 `before.failed_names`，逐条点名）；
- 修后实测：`{{fix_r4_locks.json|after.summary_line}}`；
- 两态跑的是**同一份锁文件**，中间只允许产品码变化。

回退矩阵（把四条腿分别摘回修前原文，只跑锁文件；每腿的期望红 / 对照是否被误伤）：

- RC1（`_register_callable` 直接 return）：期望红命中 {{fix_r4_revert.json|rows.0.expected_red_hit}}，
  对照误伤 {{fix_r4_revert.json|rows.0.controls_broken}}，另有 4 条属跨根因连带
  （{{fix_r4_revert.json|rows.0.other_cause_failures}} 的条数在门禁 ④-5 里点名）；
- RC2（`_callable_arg_mismatch` 恒 False）：期望红命中 {{fix_r4_revert.json|rows.1.expected_red_hit}}，
  对照误伤 {{fix_r4_revert.json|rows.1.controls_broken}}；
- RC3（撤 `self` 守卫）：期望红命中 {{fix_r4_revert.json|rows.2.expected_red_hit}}，
  对照误伤 {{fix_r4_revert.json|rows.2.controls_broken}}；
- RC4（`_type_display` 回退成裸名）：期望红命中 {{fix_r4_revert.json|rows.3.expected_red_hit}}，
  对照误伤 {{fix_r4_revert.json|rows.3.controls_broken}}；
- 四腿的共同点：`status` 全是 `{{fix_r4_revert.json|rows.0.status}}`（真的改坏了文件、跑完了、
  又复原），摘完复原 `baseline_sha256 == restored_sha256 ==
  {{fix_r4_revert.json|restored_sha256}}`，干净态意外失败 {{fix_r4_revert.json|clean_run_failed}}。

跨根因的连带变红是**合并修**的必然结果，逐条记在 {{fix_r4_revert.json|collateral}}，
并写明"连带 ≠ 该单没修好"；{{fix_r4_revert.json|note}}

## 四、语义变更影响面（正面测，不靠推断）

存量语料 {{fix_r4_impact.json|corpus}} 个 `.cypy`（仓内全部 + `examples/` + DEMO），
同一批 AST 上分别跑「快照版」与「修后版」分析器：

- 修前无诊断 → 修后有诊断：{{fix_r4_impact.json|newly_rejected}}
- 修前有诊断 → 修后消失：{{fix_r4_impact.json|newly_accepted}}
- 待裁决：{{fix_r4_impact.json|unadjudicated}}
- 两侧都解析不动的档位：{{fix_r4_impact.json|corpus_unparsed}} 个，口径见
  {{fix_r4_impact.json|note}}

这个"零"不是先验结论，是三轮误报被实测打掉之后剩下的零。中途真的出现过 9 档命中（14 条诊断），
逐条分因后修掉三处越界改动：

1. `_visit_Name` 一律给函数名挂返回类型 ⇒ `return f ~: 21` 脱糖成 `ReturnStmt(Name)` +
   独立 `ExprStmt(BuildBlockExpr)` 后被判「got str」；改判为「只在声明侧是 Callable 时才代入签名」；
2. `_visit_Attribute` 对未声明成员返回 `None` ⇒ 诊断把 `None` 渲染成 `str`；改为回落 `object`；
3. `_call_is_judgable` 用 (0,0) 位置判可审 ⇒ 脱糖产生的无位置节点被放过；改为
   「有位置就判；无位置时只判属性调用」。

每一次放宽/收紧都由 `fix_r4_impact.py` 重新跑满 203 档确认，不靠"应该没问题"。

## 五、文档面对齐与冻结面只读对照

`docs/USAGE.md` 六处按实读改写（D08 入口点、D09 Python 下限、D10 `hook` 选项清单、
D11 构建产物字段、D12 `hook.eval` 返回值），外加一条**反向对照**：实现里没有的
`--incremental` 不得出现在文档里。

- 已对齐：{{fix_r4_docs.json|agreed}}
- 仍未对齐：{{fix_r4_docs.json|still_open}}
- 半开项（如实标注，不假装闭环）：{{fix_r4_docs.json|half_open}}
  —— `hook.eval` 读侧要 `__result__` 而写侧从不产出，缺的是**生成侧**，改它超出本单授权 ⇒ 转结。

冻结面按「只读探针 + 它必须仍然错着」正面测：
{{fix_r4_docs.json|frozen_control}}（`SYNTAX/appendix-C-features.md` 的 `cypyc --compile` 行
仍与实现不符 ⇒ 证明本环没去动它；它要是"变一致了"反倒说明我改了冻结面），
冻结字节 sha {{fix_r4_docs.json|frozen_bytes_sha}}。

## 六、账面闭环

六张修复单（T0r75/76/77/78/80/81，ns `bugs`）逐单 `claim → execute → submit → verify`，
并往 `memory/bugs.md` 的对应条目追加 `### FIXED(verify=已完成) — 2026-09-28 R4-修复 追加留档` 段
（段前后各留整行空行：上一环实测过"隐形标题"会让条目从 `bug_list` 消失并被服务端重发同一条）。

- 三向对照（md 段 / sqlite 终态 / `call_log` 里真调过 ≥4 次）一致：
  {{fix_r4_ledger.json|agree_total}} 张，本环驱动 6 张（见 `fix_r4_ledger.json` 的 `cards`，
  逐张带 `task_id / steps / final_status / completed_by`）；
- 账本条目总数 {{fix_r4_ledger.json|ledger_total}} 条——追加 FIXED 段**没有**多生出条目；
- 闭环强度口径：{{fix_r4_ledger.json|note}}

这些单子拿不到 Omega 链：`report_bug` 发的单不在 `task_plan_deep` 的树里、`description` 没有
`[omega:required]`，三连会全部被协议层拒绝而 `verify` 照过（上一轮实测并已入账）。
所以锁死强度全部落在判据件上：锁 + 回退矩阵 + 203 档差分 + 文档实读对照。

驱动件 `fix_r4_ledger.json` 落盘之后我又改过一次驱动的**排版**（flake8 E127/E128，只动 `print`
的续行缩进）。绿灯不能跨时间抵扣，所以补了一个只读复核件把盘上现状独立重读一遍：
{{fix_r4_ledger_check.json|agree_total}}/{{fix_r4_ledger_check.json|total}} 张一致，
{{fix_r4_ledger_check.json|note}}

## 七、基线、红线与半径

三套判据体系同批全量复算。地板取上一环实测件（`hunt_r4_baselines.json`），不是手填：

- 地板：{{fix_r4_baselines.json|floors}}
- 本环三套同绿：{{fix_r4_baselines.json|three_systems_green}}
- 明细：pytest {{fix_r4_baselines.json|pytest}}、收集 {{fix_r4_baselines.json|collect}}、
  自研套件 {{fix_r4_baselines.json|suite}}、e2e golden {{fix_r4_baselines.json|e2e}}
- git 红线：{{fix_r4_baselines.json|git}}
- 改动半径按类别分栏：{{fix_r4_baselines.json|radius}}
- 冻结面文件数 {{fix_r4_baselines.json|frozen_total}}，其 mtime 落在本环窗口内的：
  {{fix_r4_baselines.json|radius.frozen}}；sha 表见 `fix_r4_baselines.json` 的 `frozen_sha`。
- 自证未过项：{{fix_r4_baselines.json|refuse}}

驱动面 lint：本轮亲笔 {{fix_r4_drivers_lint.json|drivers_scanned}} 个脚本
（清单按 mtime 窗口 glob 从盘上反解，不手写——上一环手写清单漏过整个目录），
硬错 {{fix_r4_drivers_lint.json|hard_violations}} 条，软账
{{fix_r4_drivers_lint.json|soft_total}} 条（上一环同口径基线
{{fix_r4_drivers_lint.json|previous_round_soft_baseline}} 条 ⇒ 只降不升成立），
注入对照抓到 {{fix_r4_drivers_lint.json|canary.bad_caught}} 条、干净文件误报
{{fix_r4_drivers_lint.json|canary.clean_false_positive}} 条。

## 八、本环我自己的失效（判据写错，不是产品坏）

操作类 8 条，逐条给"怎么发现 / 怎么改"：

1. **`fix_r4_locks.py` 用哨兵值把"真全绿"读成红灯**：`fields.get("failed", -1)`，而 pytest 全绿的
   汇总行里根本没有 `failed` 这一段 ⇒ 拿到 `-1` ⇒ 判据报「修后必须全绿」失败，实际是 18 passed。
   改成缺键显式补 0，并加 `rc` 与 `failed+errors` 同向互校（单侧造假会在这里露出来），
   再加一条"全绿时 passed 条数 ≥ 15"防空汇总行蒙过。
2. **`fix_r4_claim.py` 的账本正则只反解出 1 张卡**：`^## BUG-(\d+) .*?\n- summary: (.*)` 配 `re.S`
   时贪婪的 `(.*)` 一路吃到全文最后一个 `\n- ` ⇒ 70 条账本只读到 BUG-1，其余 69 条在判据眼里
   "不存在"。改成按下一条标题切块，并新增"反解条目数 == 盘上标题数"的断言。
   与上一环"清单口径漏一个目录"同族：**读少了不会报错，只会静默少读**。
3. **三向对照的字符窗口写死 4000**：BUG-61 的条目有 261 行，从根因键到追加的 FIXED 段远超 4000
   字符 ⇒ 真留档会被读成没留档。改成追加前与自证用**同一个** `block_span()` 定位函数。
4. **lint 清单如果继续手写，本轮新增的两支脚本（tally / render_order）就不在监管内**：
   改成按 mtime 窗口 glob 反解，并把逐文件 mtime/字节留档，让口径本身可被复核。
5. **后台全量复算与「摘实现」矩阵不能同时跑**：上一环为躲这个把后台任务杀掉；本轮把矩阵跑完
   之后才启动复算，并验证被杀任务没留下孤儿进程在污染耗时读数（本机现在有 3 个不属于本环的
   python 进程：两支 `hunt_r2_scan.py` 遗留 + `cypyc watch` + 兄弟项目的 `ab_r16.py`，
   按纪律不杀别人家进程，只在自己的报告里写明"全量套件墙钟不是产品信号"）。
6. **`fix_r4_baselines.py` 把 porcelain 的第 1 位当成索引位**：`ln[:2].strip() and ln[0] != "?"`
   对 `' M'` / `' D'` 这类**只改了工作区**的行同样为真 ⇒ 第一次全量复算报"暂存区 91 行"，
   看起来像我违令 `git add`。实际 `git diff --cached --name-only` 是 **0 行**（现在也是）。
   改成只看第 0 位（`X` 非空格才算 staged），红线这才测到它声称的东西。
7. **冻结面对 `HEAD` 比是错的锚**：`git diff HEAD -- SYNTAX` 回 2 个文件
   （`SYNTAX/01-basic-types.md`、`SYNTAX/appendix-A-keywords.md`），那是**本轮之前**就存在的脏态
   （本轮 mtime 半径里 frozen 栏为 0 可证），拿 HEAD 作锚等于把别人的旧账算成本环违例，
   而且是一条**永远不可能通过**的判据。改锚成"对本环自己的 sha 留档比"：
   `fix_r4_docs.json` 在 22:02 记下的 `frozen_bytes_sha` 必须与复算时刻一致。
   顺带把这条既有的脏态原样转给 R4-验证 复核归属，本环不动刀也不认领。
8. **一条 R3 遗留的锁被实测判成假阳性**（`tests/test_loop_20260927_polish_r3.py::
   test_polish_every_documented_cypyc_flag_is_real`）：它拿 `cypyc/cli.py` 里 `parse_args` 的 AST
   切片当"argparse 真有的旗标"，而 `hook` 子命令的旗标其实声明在 `cypy_hook/hook.py` 的 parser 上
   （切片对 `hook` 返回**空集**）。我按 D10 把 hook 的六个未记选项补进文档后，这条锁把
   `--transpile-only` 判成"文档跑到实现前面"，而 `python -m cypyc.cli hook --help` 当场就列出它。
   改法不是放宽断言：比较面换成调用面 `--help`，并**新增**一条「AST 声明过的旗标必须出现在
   --help 里」的反向断言（切片漏项从此会被单独抓到）。这条锁是本轮全量复算里唯一的 1 红，
   改后是否 1956 全绿以本报告《七》引用的 `fix_r4_baselines.json` 为准，不在这段散文里自证。

## 九、要谁裁决

1. **BUG-61..64 的修法半径**：改动只在分析器的**新增**分支里（`callable_sigs` 命中才生效），
   203 档存量语料实测零新增诊断、零消失诊断。但仓外用户语料未知——如果他们的代码里有
   「把函数当值传递再调用」的写法，新分支会开始报 arity / arg 类型诊断。要不要在
   `--check-only` 上开一档宽松模式，请指挥官定；本环没有自行放宽，也没有自行收紧。
2. **BUG-65（冻结面 7 行）与 BUG-70（3000 行红线）**：仍只挂账，需要人来定"文档降级"还是
   "类型系统补齐 / 拆结构轮"。
3. **BUG-68/69 的真编译验证**：需要跑真实 MSVC 编译（会写 `.pyd`，不动 git）。
   **授权我在 R4-验证 做吗？**
4. **`hook.eval` 的生成侧缺口**：在写侧补 `__result__`（改生成器），还是在文档里取消承诺？
   本环按文档侧"不再承诺返回值"处理，生成侧转结。
5. **我改了一条 R3 遗留锁的比较面**（《八》第 8 条）：红线是"不得为了让测试绿而放宽既有断言"。
   我的处理是换锚到调用面并加了一条反向断言（净效果更严），但**这条判断由我做出并不中立**——
   请指挥官复核 `git diff -- tests/test_loop_20260927_polish_r3.py`，若认为应当保留 AST 切片口径，
   正确修法是把 `hook` 的 parser 也纳入切片，而不是回退到"文档不许写真实旗标"。

## 十、转结与顺序账

本环收口顺序按法 ⑥：**判据件 → 报告终版 → 叶收口 → 根收口**。
因此有两件事在这份报告里看不到，写明以免被读成"没做"：

- **叶收口与根收口都在渲染之后**（这正是法 ⑥ 的排序，不是遗漏）。因此本报告带的调用面是
  **渲染前快照**：任务树 {{fix_r4_calllog_tally.json|tree_rows}} 行 / 修复单
  {{fix_r4_calllog_tally.json|bug_card_rows}} 行；被拒分栏 树
  {{fix_r4_calllog_tally.json|tree_refused}} 条、单
  {{fix_r4_calllog_tally.json|bug_card_refused}} 条。
  收口批跑完会另出一份终账 `fix_r4_calllog_tally_final.json`（含 16 叶 × Omega 八件套、
  8 支与根的收口链、逐字被拒原文），它**不进本报告的门禁表**，进 `loop_progress.md`
  与 R4-验证 的输入件。
- Omega 链在这一刻还没跑，但**标记已经在库裡**：本环树
  {{fix_r4_calllog_tally.json|omega_marked.leaves}}/{{fix_r4_calllog_tally.json|omega_marked.leaves_total}}
  张叶与根任务 {{fix_r4_calllog_tally.json|omega_marked.root}}/1 的 `description` 都带
  `[omega:required]`（`fix_r4_calllog_tally.json` 的 `spec_named_carriers.omega` 里写明
  `deferred_to_closure`）——把"待执行"写成"已开启"是本环禁止的措辞。
- **渲染后不再改**由 `fix_r4_render_order.py` 留 sha256 并在收口后用 `--check` 只读比对；
  上一环"归档后又重渲染一次"造成的交付物与库里不一致，这一环不再犯。

`call_log` 逐字被拒原文（本环，任务树 + 六张修复单两栏一起进表）：

{{fix_r4_calllog_tally.json|refusals_md}}

规格点名能力的承担者与次数（`laya` / `issue_up` 不是本 build 的工具名，写"已开启"必须点名载体）：
{{fix_r4_calllog_tally.json|spec_named_carriers}}

转 R4-验证：D18 / BUG-69 的两次真编译实测（待授权）、`appendix-C`《已实现的限制修复》14 行逐行
复测、BUG-61..64 的**调用面**复算（`python -m cypyc.cli transpile --check-only` 全链，不只是模块内
单测）、锁文件在 HEAD 产品码 + 当前测试下的"必红"复核（防止今天的绿灯是明天的假账）。
转 R4-打磨：`hook.eval` 生成侧缺口、文档面剩余半开项、驱动面软 lint 债 0 条（只降不升基线已刷新）。
转 R4-推进：BUG-42 / BUG-43（模式匹配 `__unapply__`、位置模式误判）仍挂 `待领取`，属"已声明未实现"半径。

页脚（从判据件反解，不手填）：
