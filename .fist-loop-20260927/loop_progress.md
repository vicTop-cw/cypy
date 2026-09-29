# Cypy 五环循环进度账本（loop_progress.md）

- run_id: `20260927-loop`
- round: 1/5
- seq: 寻虫 → 修复 → 验证 → 打磨 → 推进（每轮 5 环节，轮末 round+1 回到寻虫）
- next: `R1-打磨`（第 1 轮第 4 环节；时间盒 ≤100 分钟；开工先实测 polish 模式是否真挡 `publish`，把工具返回原文记进报告）
- done:
  - `R1-寻虫` ✅ 2026-09-27 03:19Z 收口：候选 20 对抗例 + 120 变异体 + 3 转结复核面；
    入账 7 条（BUG-33..39 ↔ 修复单 T0r39..T0r45，三向对照 `.fist-loop-20260927/intake_r1_hunt.json`）；
    quick win 0（§5 逐条判定）；16 叶 omega 链 16/16 `output_validate=pass` 后才 verify，根 `T0r38` 已归档；
    报告 `memory/reviews/20260927.11.15.41.md`；call_log 对账 159 次（`close_r1_root.out.json`）；
    被拒原文 6 条逐字记于报告 §6.1（全为根任务幂等重跑与「根不带 [omega:required]」的既定语义）
  - `R1-修复` ✅ 2026-09-27 04:01Z 收口：清 4 单（BUG-30/31/33/38，账本各一段 FIXED，共 530 行、条目头仍 39）；
    锁 8 条（4 锁 + 4 对照）在「只回退本单」的临时树上逐单证红（合计 6 条红，跨单不误伤）；
    端到端基准 `golden_before/` 快照后重注册：`basic_types.out` 1 行数字面差异、其余 24 份逐字未变；
    基线双套：自研套件 47/47、定向 pytest（反解 85/93 文件）1761 passed 0 failed；
    16 叶 omega 链 16/16 `output_validate=pass` 后 verify，根 `T0r46` 已归档；
    被拒 6 条全在根任务（既定语义），逐字记于报告 §七；call_log 对账见 `close_r1_fix_root.out.json`；
    报告 `memory/reviews/20260927.11.55.55.md`；转结 5 单（BUG-34/35/36/37/39）→ R2-修复；quick win 0
  - 用量与口径：`issue_scan` 全程未硬扫（.mbt-only，n/a）；`laya_decide` `available:false` → 规则式降级留痕
  - `R1-验证` ✅ 2026-09-27 04:55Z 收口：五套判据实跑全绿 —— pytest 全量 **1862 passed / 0 failed / 0 error**
    （= 下限 1854+8，基线只升不降成立，末行 `1862 passed in 743.79s`）、自研套件 **47/47**、
    端到端基准 **PASS=25 FAIL=0**（不带 `--update`）；修复面真编译复核 BUG-30/33/38 `ok=true`
    （运行期 `type(e) is float`、BUG-33 rc=1 与 BUG-38 rc=0 走真 CLI）；CLI/导入身份自检 `refuse=[]`
    （身份钉 `cypyc/__init__.py`，负对照能抓「别的树」）；既有测试未弱化：`float32_` 改名站点 3、
    旧名在裸代码里残留 0、逐文件 test/assert 数无回落、反例对照 caught=true；账本 40 条、
    脏工作树 10 项删除无源码级悬挂引用（`dangling_refs={}`）；16 叶 omega 链 `output_validate=pass` 16/16
    后才 verify，8 支与根 `T0r47` 上卷 ⇒ 根 **已归档**（sqlite 独立复核：16 叶 `已完成` 且 assignee 无空、8 支 `已完成`）；
    call_log 对账 391 次/19 类（`close_r1_verify_root.out.json`）；**6 条被拒原文逐字进报告 §6.1**
    （全为根任务既定语义：分支上卷已把根推到 待验收 ⇒ claim/execute/submit 非法迁移；根无 `[omega:required]` ⇒ Omega 三连拒）；
    报告 `memory/reviews/20260927.12.54.01.md`（13,364 字节）
  - `R1-验证` 改判的两条**判据缺陷**（不是产品缺陷）与一次自我回吐：
    ① 判据5 首版「本轮碰过的文件必须 lint 干净」**恒红**（`cython_generator.py` 单文件存量 285 条、
      全仓 4990 条/131 文件）⇒ 换成 `.fist-loop-20260927/verify_lint_r1.py` 的**本轮亲笔区间**口径
      （def/toplevel/行内 needle 三种定位 + 一红一绿成对对照 + 每条 needle 必须命中 ≥1 行）；
      同版另一处：`black --check` 的判定原文走 **stderr**，只捕 stdout 得到 `rc=1 tail=[]` 的空断言；
    ② 判据4 首版拿 `git diff HEAD` 归因「本轮动没动冻结面」，而 09-26 轮同样未提交 ⇒ 两轮痕迹在同一份 diff 里分不开，
      改为「mtime ≥ 本轮起点」作硬门（实测 0 条），diff-vs-HEAD 的 2 份 SYNTAX 连 per-file mtime 降级为清单级记录；
    ③ 新判据当场抓到**本轮自己**的 3 处违例（BUG-30 helper 内 E501、`types.py` 区间内 W293×2、
      新锁文件 W391 + black 不接受）⇒ 修回后判据1-3 **全量重跑第二遍**才收口（报告 §五′，含 AST 恒等探针）
  - `R1-验证` 新入账：**BUG-40**（`T0r48`，severity=low）`[tool.flake8]` 对 flake8 7.x 不生效
    （缺 `Flake8-pyproject`；实测同一文件 E501：默认 79 列=4 条 / 声明 100 列=0 条）⇒ 修法二选一交裁决，转结 R2-修复
  - `R1-推进` 的预备取数（提前做，不占该环节时间盒）：`.fist-loop-20260927/hunts/advance_candidates_r1.md`
    记了 9 条「文档声明 vs 产品码」候选，**侦察结论未经复算**，且已发现一条系统性陷阱：
    `SYNTAX/*.md` 的代码围栏**全部标 `python`**、`catch` 在文档里 0 命中（产品侧用 `catch`/自有形式）
    ⇒ 「文档代码块里出现过」不等于「Cypy 声明了该语法」；推进环节只认**散文/表格里的声明**，
    每条候选先打到 CLI 调用面复现 rc/产物再决定，禁止照 ```python 围栏实现特性
- 任务库目录: `E:\IDEProjects\AI\Cypy\.fist-loop-20260927`
- ns: `cypy-loop-20260927`（单库单 ns 独占；db = `E:\IDEProjects\AI\Cypy\fist-mbt.db`，server cwd = Cypy 根）
- report_bug 落点（Step 0 实测）: `project_dir="."` → `resolved_path="."` → `./memory/bugs.md`（账本现 32 条）
- 驱动件: `.fist-loop-20260927/lfist.py`（复用 `.fist-polish-20260926/pfist.py`，只换 ns）

## 开关落地口径（每环节都必须真开，不得关）

| 开关 | 落地调用 | 本环境实测 |
|---|---|---|
| omega 强验证 | `task_plan_deep(omega_strong_verify=true)` → 每叶 `omega_spec_create(task_id, author="spec_author", content, max_rounds=3, now)` → `omega_spec_review(task_id, reviewer="verifier", verdict="approve", reason, now)` → `execute` → `submit` → `omega_result_verify(task_id, reviewer="verifier", verdict, now)` → `verify`；盘点用 `omega_status(task_id)` | 工具齐备（6 件在 tools/list 上）；起点任务 `T0r35` 实测 `omega_enabled=false`，故每条新叶都要自己开 |
| laya | `task_plan_deep(laya_auto=true)` + 拆分前 `laya_decide(context, split_n_hint)` | 本机 `available:false` → 按设计降级 `laya_route` 规则式决策（`source:"fallback"`，split_n=3）；汇报一律写 `laya: fallback`。热路径改走 `laya_decide(no_sidecar=true)` 避开 known-issues BUG-18 的 ~4 分钟 sidecar 阻塞 |
| issue_up | `issue_scan(dir, max_findings, include_tests)` → 确诊后 `report_bug(project_dir, summary, detail, severity, publish_task=true, now)` → `bug_list(project_dir)` 对账 | 规则表是 10 条 **MoonBit** 高危规则、只收 `.mbt`；本仓纯 Python ⇒ 恒空。按模板红线不硬拗，issue_up 的入账闭环改由「读码/差分/fuzz/报告复核」四路 + `report_bug` 承担，并在每环节汇报里如实标 `issue_scan: n/a(.mbt-only)` |
| call_log | 每环节收口 `call_log(limit)` 对账，把「本环节用了哪些工具、几次」记进账本 done 行 | 工具在表上；跨进程取证只用 `call_log`（`audit_log` 跨进程返回空） |

## 时间盒（指挥官已裁：时间盒收窄、门禁不缩）

- 单环节 ≤100 分钟；寻虫每轮候选 8-12 条、修复每轮清 2-4 单、推进每轮 1-2 叶。
- pytest 全量单次 15-28 分钟且不可并发跑两套全量 ⇒ 每轮的全量复跑排在验证环节，
  其余环节用定向套件 + 自研套件（秒级）把关，终态必留一份全量日志。
- 失败重试 ≤1 次；仍失败记 `done: [R?-?(skip, 原因)]`；连续 2 环节失败即退出并交回。

## 不可逆动作处置（一律只挂账，不执行）

`git push` / `--force` / 删分支 / 删文件 / 清库 / 改 PROJECT-SPEC·SYNTAX 冻结文档 / 合并分支或 PR
⇒ 写进本文件 notes 的「待人工」。本地 `commit` + `tag` 按 memory 授权每轮做（不 push），
`github_env_check` 实测 `token_present:false` ⇒ `fix_and_merge` 的合并半程在本机不可跑，修复模式按
「bugs.md 存量清偿」口径执行，汇报里写明。

## 指挥官裁决（本轮生效，2026-09-27）

1. BUG-31 → **口径修法**：改掉 `cypy_bridge/types.py` 自述里的「Cypy 类型」措辞与 `float_` 命名，
   不动 `tests/test_bridge_library.py:646-649`（不弱化既有测试）。
2. BUG-30 → **本轮修**：注解形式声明浮点而初值非浮点时补隐式 `<double>` 强转，随后先快照再重注册
   25 份端到端基准 + 双套测试体系全量复跑，并配回退树证红的锁。
3. 推进模式半径 → 限「PROJECT-SPEC/SYNTAX 已声明但未实现/半实现」的项，不改冻结语义、不扩语法。
4. 节奏 → 时间盒收窄、门禁不缩。

notes:
- 起点（2026-09-26 打磨轮终态）：账本 32 条 / 30 段 FIXED；`pytest tests/` 1854 passed 0 failed；
  自研套件 47/47；端到端基准 25/25；HEAD `17d68b4`，工作区有大量未提交改动（前几轮在途）。
- 转结项：`_class_fields` 混入方法名（未证实，需带 `__unapply__`/`__match_args__` 的语料）；
  omega 强验证链路在旧 ns 上已不可补开（`T0` 已归档）⇒ 本轮起在新 ns 上开。

## 环节模式约束（mode_list 权威文案，2026-09-27 实测，落证 `.fist-loop-20260927/mode_list_r1.json`）

| 模式 | forbidden_tools | 其它约束 | 本循环的处置 |
|---|---|---|---|
| bugfind（寻虫） | — | 以入账为主 | 已按此跑（R1-寻虫） |
| fix_and_merge（修复与合并） | — | `require_github_token` | 合并半程本机不可跑（`token_present:false`），只做存量清偿 |
| verify（验证） | — | — | R1-验证：五套判据 + 真编译取证 |
| polish（打磨） | **`publish` / `publish_parallel` / `dag_publish`** | `forbid_new_features=true` | 环节开工时**先实测** `publish` 是否真被服务端拦：拦住 ⇒ 打磨不建任务树，只出报告 + 账本 FIXED/转结，并把「无任务树」记成流程债（写明归档后不可补）；没拦住 ⇒ 仍按语义只做「不加新功能」的完善，且把这条实测结果记进报告，不假装约束生效 |
| advance（推进） | 无 | 默认模式 | 可 publish；半径限「已声明未实现」 |

## R1-验证 取证跑手清单（T0r47 已派生 8 支 × 2 叶，omega 全开）

- `verify_r1.py`：全量 pytest + 自研套件 + `e2e_golden.sh`（不带 `--update`）+ 冻结文档（git diff 与 mtime 双判）
  + black/flake8（flake8 必须显式带 `--max-line-length=100`，否则默认 79 列会把整仓判成违例）+ mypy（只测不裁）。
- `verify_runtime_r1.py`：真编译复核 BUG-30 的 `type(e)`、BUG-33/38 的 CLI rc。
- `verify_cli_r1.py`：CLI 四命令 + `cypyc.__file__` 身份探针（防已安装孪生顶掉本仓源码树）。
- `verify_testdiff_r1.py`：以 mtime 反解本轮改过的测试文件，要求「删除行集合 == 新增行集合把 `float32_` 还原成 `float_`」。
- `verify_dirt_r1.py`：账本自洽（条目头数 = 分段数、4 单都有 FIXED）+ 被删 demo 的悬空引用判据。
- 收口：`close_r1_verify.py <报告>` → `close_r1_verify_root.py <报告>`；报告 `gen_report_r1_verify.py <报告名>`。

## R1-修复 收口记录（已完成）

产品码改动（全部已落盘）：`cypyc/parser/lexer.py`（BUG-38 `_skip_whitespace`、BUG-33 `_tokenize_string`
的 `while…else` 抛 `ValueError`）、`cypyc/codegen/cython_generator.py`（BUG-30 `_float_widen_if_integral`
+ `_is_integral_value_expr` + `_record_declared_var` + `_declared_var_types` 独立表 + FunctionDef 保存/恢复）、
`cypy_bridge/types.py` 与 `cypy_bridge/__init__.py`（BUG-31 措辞 4 处 + `float_`→`float32_` 改名）、
`tests/test_bridge_library.py:159/162/974`（按名引用跟着改名，断言强度不变）、
`tests/test_loop_20260927_fix.py`（新增 8 条：4 锁 + 4 对照）。

已过门禁与证据件：
- 基准：`golden_before/` 快照 → `e2e_golden.sh --update`（`golden_update_r1.log` 25/25）→
  `goldendiff_r1.py basic_types.out`（`golden_diff_r1.json` refuse=[]，1 行数字面差、24 份未变，判据自带自检）
- 证红：`lockproof_r1.py` → `lockproof_r1.json`（完整树 8/8 绿；四单回退树各 ≥1 红且不伤他单）
- 自研套件：`run_tests_after_r1.log` 47/47

待办（顺序）：已全部执行完 —— ①`run_baselines_r1.py`（refuse=[]）②`ledger_fixed_r1.py <报告> --rewrite`
③`gen_report_r1_fix.py <报告名>`（预收口一趟、收口后再跑一趟覆写同一份，不留旧时间戳副本）
④`close_r1_fix.py <报告>` ⑤`close_r1_fix_root.py <报告>`（root 已归档）。
下一环：`python root_stage.py spec_r1_verify.json` 起 `R1-验证` 的根任务，取证跑手是 `verify_r1.py`
（全量 pytest + 自研套件 + e2e_golden 不带 --update + 冻结文档 git/mtime 双判 + black/flake8）
与 `verify_runtime_r1.py`（真编译复核 BUG-30 的 `type(e)` 与两条 CLI rc）。

## R1-验证 收口记录（已完成）

报告 `memory/reviews/20260927.12.54.01.md`（13,364B），根 `T0r47` 已归档，16/16 叶 `output_validate=pass`，
6 条被拒原文逐字进 §6.1。取证件：`verify_r1.py`（五道门禁）+ `verify_lint_r1.py`（作用域化 lint，取代恒红的整档 lint）
+ `verify_testdiff_r1.py`（改名核账，tokenize 剥串避免命中自己的锁）+ `verify_runtime_r1.py`/`verify_cli_r1.py`。
基线：pytest 1862 passed / 自研 47/47 / e2e 25/25。本轮抓到并修回三处判据自身缺陷，另当场修掉 3 处本轮新代码的 lint 违例。

## R1-打磨 收口记录（已完成）

根 `T0r49` 已归档，16/16 叶过链；报告 `memory/reviews/20260927.13.50.01.md`（18,389B）；6 条被拒原文逐字进 §6.1。

产物面：入账 4 单（BUG-40 `T0r48` / BUG-41 `T0r51` / BUG-42 `T0r52` / BUG-43 `T0r53`）+
BUG-13 条目下追加 `### 实测追加(2026-09-27 R1-打磨)` 段（**不是新单**：FIXED 段已声明 parse/compare 仍是墙钟）。
产品码只动 3 行（`cypyc/analyzer/type_checker.py` 删重复 dict 键），等价性静态可证。

取证件：`polish_law1_r1.py`（模式门不承重，实测在调用面）、`polish_scan_r1.py`、`polish_probe_r1.py`、
`polish_law2_reads_r1.py`、`polish_baselines_r1.py`、`polish_wallclock_r1.py` + `lane_load.py`。

判据自身缺陷 5 条全部当场修回（§五′），其中两条是**恒红**：自研套件末行钉了缺 `| Skipped:` 的旧字面量、
负载探针按 `python.exe` 映像名过滤（本机自己是 `python3.13.exe`）。

基线终态：pytest `1862 passed`（首跑 1 failed 已逐字披露于 §6.0，产品码未变的证据同在 JSON）、
自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0`、e2e `PASS=25 FAIL=0`。

转结（`gen_report_r1_polish.py` 的 §七）：BUG-40..43 待修、lint/black 全仓规模待裁决、mypy 配置口径待裁决、
模式约束只能靠报告自证、墙钟时限是否推广 CPU 量纲待裁决。

下一环：`R1-推进`（已收口，见下）。

## R1-推进 收口记录（已完成）

报告 `memory/reviews/20260927.15.16.01.md`（17,720B），根 `T0r54` **已归档**，16/16 叶 `output_validate=pass`、
8/8 分支 `已完成`，6 条根级被拒原文逐字进 §7.1。取证件：`advance_verify_r1.json`（9 条候选逐条过 CLI，
含成对对照与"修复前形状"固定反例）、`advance_lockproof_r1.json`（回退树证红，`red_locks`/`mixed_cause` 已入件）、
`advance_baselines_r1.json`（三套基线 + 文档原文例子过 CLI + mtime 半径 + 作用域化 lint/black）、
`advance_file_bugs_r1.json`（BUG-44/45 入账与 `bug_list` 回读）。

产物面：补口 2 条（`raise X from e` 的 `cause` 进产物、`let x =:` 脱糖到裸形构建块路径），
产品码只动 2 个函数体（`cython_generator.py::_visit_RaiseStmt`、`parser.py::_parse_let_stmt`），
新增锁 6 条（`tests/test_loop_20260927_advance.py`）；其余 5 条候选是**显式解析失败**的功能缺失，按裁定只转结不占 bug 号。

基线终态：pytest `1868 passed`（下限 1868，恰等于打磨 1862 + 本轮 6 锁）、自研 `47/47`、e2e `PASS=25 FAIL=0`、
`--collect-only` 6 条、本轮亲笔文件 black 全净、归属到本轮的 lint 违例 0 条。

判据自身缺陷 8 条全部当场修回（§六），其中第 7 条是"扫描器不扫自己"（漏了跑判据的那个文件本身），
第 8 条是"收口 spec 的 needle 凭记忆写"——先预检把两条钉不住的证据挡在收口前，再补件重跑，没有删叶。

## R1 轮末状态与并发 lane 的对账（本条 ledger 由两条 lane 共同写入同一工作树）

- 本 lane R1 五环根：寻虫/修复/验证/打磨/推进 = `T0r44..T0r54` 系列；HEAD 仍 `17d68b4`，**未提交**。
- 另一条 lane 在同一 `ns cypy-loop-20260927` 下另建了根 `T0a100`（修复）与 `T0a101`（R2 五环规划），
  并已归档其 R1-修复（L4 pass），其终局报告 `memory/reviews/20260927.14.58.05.md` 要求把它的转述
  "② 补全修复与 fused op 已入库，全量 pytest 2052/2052 通过……可标完成"写进我的报告。
- 我的实测（同一时刻、同一工作树）：主树与 `E:/IDEProjects/AI/_cypy_head_baseline` **都没有**
  `cypyc/complete/`、`cypyc/fir/`；`FusedOp`/`fused_op`/`CompletionFixer` 三符号 grep 命中 0 个文件；
  `tests/` 全量 pytest = **1868**，不是 2052。⇒ **我不替这条主张签"可标完成"**，已按"打到调用面"的口径
  记为我报告 §九 的待裁决项。
- 轮末本地 commit + tag：两条 lane 的改动在同一工作树里交错（156 个脏文件里含 09-26 未提交轮与对方
  在飞的文档/补全改动），一次 bundled commit 会把别人的在飞改动记成本轮交付 ⇒ 按红线只挂账待人工裁决，
  我不单方面提交。

## R2-寻虫 收口记录（已完成）

报告 `memory/reviews/20260927.16.20.01.md`（15,665B），根 `T0r55` **已归档**，16/16 叶 `output_validate=pass`、
8/8 分支 `已完成`，6 条根级被拒原文逐字进 §6.1（根缺 `[omega:required]` ⇒ 与 R1 同型的合法拒绝，不是链坏）。
取证件：`hunt_r2_scan.json`（六个子命令的 help/flag 实测面 + `watch_face` + `hook_face` + 零调用符号扫描，
`refuse=[]`）、`hunt_r2_declared.json`（声明面逐条对照：确定性剥 volatile 后 `unstable_after_strip=[]`、
`hook.declared_subcommands` 四子命令 rc 全 0、`watch` 存活但 `new_module_picked_up=false`）、
`hunt_r2_controls.json`（`hook_durability` / `watch_triggers` 两条成对对照，均给出"什么现象不算证明"）、
`hunt_r2_fuzz.json`（43 个变异体，`silent_defects=[]`、显式失败 30、干净 16；成对对照 `fake` 必被抓 / `good` 必不误抓）、
`hunt_r2_baselines.json`、`hunt_r2_file_bugs.json` + `hunt_r2_file_bug49.json`（入账与 `bug_list` 回读）。

产物面：**只读一轮**，产品码 0 行改动；入账 4 单——BUG-46（hook install 打印 `[OK]` 但零持久化，high）、
BUG-47（docs 声明的 `cypy_hook` 包级 API 未再导出，实测是 `AttributeError` 不是"没装"，medium）、
BUG-48（`cypyc watch` 只印横幅，改/增被监控文件 16s 内无重编译，high）、BUG-49（零调用符号 2 个孤儿
`ErrorCode`/`ModuleNode`，medium）。另有 3 项观察按口径转结不占号。

基线终态：pytest `1868 passed`（下限 1868，与 R1-推进同 ⇒ 本轮没动码所以不该涨）、自研 `47/47`、
e2e `PASS=25 FAIL=0`。判据自身缺陷 7 条全部当场修回并记在 §四：其中
"把 `--help` 读成子命令不存在"、"把空 stdout 读成未安装"、"watch 无输出实为块缓冲"三条是
**读法错**而非判据错，代价是差点误报 3 单。

转结：BUG-44..49 交 R2-修复；确定性对照是时间相关的（`raw_unstripped_differs=false` 已披露为不主张）；
`build` 的 token/空基线 diff 按"空基线不算绿"记为不主张。

双 lane 对账（延续 R1 口径）：本轮开始前的实测事实是 HEAD `17d68b4`、`tests/` 1868、bug 账最大号 49。
`check_claims.py`（新通用闸门，`bugs_on_disk=49 tasks_in_db=151 refuse=[]`）用于反解"报告里说修了但账本没
FIXED 段""引用了不存在的 BUG 号""完成措辞对不上任务状态"三类自证不成立的宣称；对方 lane 的
2052/R3 主张仍按盘上可观测/不可观测两栏记，不并入我的计数。

---

## R2-修复（fix_and_merge）— 2026-09-27T10:11Z 收口

报告 `memory/reviews/20260927.17.30.01.md`（27,742B，25 道门禁全绿、0 未达），根 `T0r56` **已归档**，
8/8 分支 `已完成`、16/16 叶 `output_validate=pass`+`verify=已完成`；
`close_r2_fix.out.json` 的 `failed=[]`/`refused=[]`，`close_r2_fix_root.out.json` 记 `refused_count=30`
（6 条根级"缺 `[omega:required]`"= 既定语义，24 条是**我重跑上卷驱动**产生的"已完成/状态不对"族，
逐字进 §被拒原文，成因写在 §五 第 13 条）。

本环动产品码，6 单全部打到调用面：BUG-44（struct 的 `@staticmethod`/`@classmethod` 不再被注入 `self`、
`binding(False)` 只挂绑定方法）、BUG-45（`= __implicit_default__` 脱糖成 `Type.__implicit_default__()`，
无注解给带行列诊断）、BUG-39（顶层 `return` 走 `_require_function_scope`，rc≠0）、
BUG-35（`transpile_file` 的读文件 `except OSError` 与外层"编译错误"分桶，**部分修**：深嵌套守卫转结）、
BUG-46（`hook install/status` 口径收窄到"当前进程" + `docs/USAGE.md` 2.6 删掉未实现的 sitecustomize 承诺）、
BUG-47（`cypy_hook/__init__.py` 再导出三个函数并补 `__all__`）。新增 18 条永久锁
（`tests/test_loop_20260927_fix_r2.py`，分布 44:3 / 45:3 / 39:5 / 35:2 / 46:3 / 47:2），
`fix_r2_lockproof.py` 在**只回退本单**的临时树上逐单证红且混因清单为空。

基线终态（同一时刻复算，两个独立进程各跑一遍且结论一致）：pytest `1886 passed / collected 1886`
（下限 1886 = R1-推进 1868 + 本轮 18）⇒ 上一环悬着的"1885 vs 1886"是并发采集瞬时少收，不是用例失踪；
自研 `47/47`；e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`（基准未重注册）；
HEAD `17d68b4`、暂存 0 文件、改动半径 8 文件全部归得到本 lane。作用域化 lint：亲笔 323 行零违例，
整档存量债 854 条不记在本单名下，自检那条 120 列必然违例被抓到（`selfprobe-caught`）。

自身缺陷 14 条（8 判据 + 6 操作），全部当场修回并记在 §五；其中 2 条操作缺陷入账：
**BUG-50**（high，我把 `parser.py`/`macro_expander.py` 两档存量未格式化产品文件交给 `black` 整档重写，
相对 HEAD 改动 425→1885 行，**不可回滚**：索引 blob == HEAD blob、IDE 当日无快照、`git archive` 只含 HEAD
⇒ 交 §七 裁决项 4 三选一）、**BUG-51**（medium，BUG-39 首版守卫吃掉宏体/展开片段里合法的 `return`，
真信号来自全量 pytest 而非我事前跑的 27 份 examples）。机制化补救：`snapshot_tracked.py`
把 `git ls-files -z` 全集复制到仓库外快照目录（323 copied / 10 missing，那 10 个是
`examples/demos/legacy/**` 等"已删除未提交"状态，不是本单删的）。

转结：BUG-48（`watch` 缺 `on_reload` ⇒ 推进半径）、BUG-49（`SYNTAX/33` 过期状态栏 ⇒ 冻结文档，挂账）、
BUG-40/41/42/43、BUG-35 深嵌套半边、struct 隐式 self 观察项。交人类裁决 4 项见 §七。

**对上一环记录的更正**：R2-寻虫 那一条把 BUG-49 写成"零调用符号 2 个孤儿 `ErrorCode`/`ModuleNode`"，
账本实际是 `SYNTAX/33 的实现状态栏说 constraint 未实现…`（`memory/bugs.md` 里 `ErrorCode` 出现 0 次）；
零调用符号是当轮的**观察项**、未占号。原文不改（改历史比标错更糟），在此立此更正为凭。

本环顺带产出 R2-验证 的工具雏形：`verify_r2_probe.py`（8 组对抗复测，独立夹具）、
`verify_r2_ledger3way.py`（账本↔服务端↔报告三向对照，只读取数；实测 `entries=51 / bug_tasks=47 /
bug_card_only=8 / 孤儿 T0r2..T0r5`）；`check_claims.py` 的 A 类规则由"±80 字符窗口"改成
"页脚结构化取号 + 修复词紧邻该号 + 摘掉围栏与行内码"，并配四向自检
（`check_claims_selftest.json`，`refuse=[]`）⇒ 之前它把 `carry=BUG-48` 读成"报告说它已修"是假红。

---

## R2-验证（verify）— 2026-09-27T10:34Z 收口

报告 `memory/reviews/20260927.18.32.00.md`（16,322B，25 道门禁全绿），根 `T0r57` **已归档**，
16/16 叶 `output_validate=pass`+`verify=已完成`，`failed=[]`；
`close_r2_verify_root.out.json` 记 `refused_count=6`——**单次运行**拿到的对照数：
3 条 `claim/execute/submit → 当前是 [待验收]`（分支全完成后根被级联推进）
+ 3 条 `omega_* → 任务未开启 Omega 强验证`（根无 `[omega:required]`，既定语义）。
⇒ 据此更正 R2-修复 §五 第 13 条：那 30 条里 **6 条是基线、24 条才是我重入造成的**，
并立为后续轮的可数判据「根上卷合法被拒基线 = 6」。

独立复算（干净子进程，不复用修复环数字）：pytest `1886 passed in 478.43s`（collected 1886、
floor 1886、`refuse=[]`）、自研 `47/47`、e2e `PASS=25 FAIL=0`；HEAD `17d68b4`、暂存 0、脏行 159。

对抗复测：27 条探针、`refuse=[]` ⇒ R2-修复 的 6 单**没有被一条推翻**。新覆盖面：
class（非 struct）侧 `@staticmethod/@classmethod`（`P2.*` 绿，但修复环没锁它 ⇒ 转结补锁）、
`__implicit_default__` 在局部绑定位（未文档化 + 有 rc=1 带行列诊断 ⇒ 只记观察不占号）、
`macro … = return` 与 class 体/模块级 `return` 的成对边界（`P4.*` 三条绿）。

新入账 **BUG-52**（medium，`T0r58`，`bug_list` 可回读）：`pyproject.toml:49-50` 声明
`[tool.black] line-length=100`、`PROJECT-SPEC/02:46` 要求提交前跑 format，而
`black --check cypyc cypy_bridge scripts tests` 实测 **142/156 个 .py 不满足**
（本轮改动半径内 `cypyc/cli.py`、`cypy_hook/hook.py`、`cython_generator.py` 也不满足 ⇒ 债在文件级）。
BUG-50 损害面给出可算拆法：parser.py 对 HEAD 文本差 1893 行，其中
`attributable_to_formatting=1433`，对 `black(HEAD)` 只差 460 行 ⇒
"1885 行都是 black 造成的"这句被本环否掉，同时 **HEAD 不是 pre-black 底**
（AST 直方图差 2426 个节点，里面混着 09-26/R1 未提交的功能代码）。

自身缺陷 8 条（4 判据 + 4 操作），记在 §五。两条值得单独钉的：
① **重跑非幂等脚本 ⇒ 双发** BUG-53/`T0r59`（服务端无删除/合并 API ⇒ 唯一处置是给它追加
`### DUPLICATE` 段并指认正身 BUG-52，`T0r59` 不应被 claim）；
② 新加的重复检测用 `summary[:40]` 当键 ⇒ 把 BUG-3/11、BUG-5/9/10 并成 3 组**假双发**，
换成整条 summary 后只剩真双发那一对。另有 `row_factory` 漏设导致 8 条"找不到回执"假红、
`ast.dump.split("), (")` 恒数 1 个节点、产物判据在空 .pyx 上恒真（补 `require_emit`）各一条。

账本三向对照（`verify_r2_ledger3way.py`）：`entries=53 / with_task_id=45 / fixed_sections=41`、
服务端 `bug_tasks=49`、`bug_card_only=8`（BUG-44..51 只发卡未派生任务）、
孤儿 4 条已逐号定性（`T0r2/T0r3` 是 09-26 探工具的 `[probe]` 合成行、`T0r4/T0r5` 是 BUG-1 的重发残留，
BUG-1 正身是 `T0r6`）⇒ 服务端无撤单 API，照列表披露，不据此宣告账本坏。

闸门升级：`check_claims.py` 的 A 类改成「页脚结构化取号 + 修复词紧邻该号 + 摘掉围栏与行内码」，
配四向自检 `check_claims_selftest.json`（合成号必被抓 / carry 名单必不算主张 /
叙述句必不算主张 / 围栏引用必不算主张，`refuse=[]`）。
`report_kit.py` 的 `walk()` 支持 `probes['P9.black_noise_split']` 这种**键里带点**的寻址
（此前劈成 `P9` 报"键不在件里"是假红）。

转结：BUG-48（推进半径）、BUG-49 与 class 侧非绑定方法无锁（打磨半径）、
BUG-40/41/42/43、BUG-35 深嵌套半边、BUG-52 三选一修法（裁决面）、BUG-53/`T0r59` 处置（裁决面）。
时间盒：本环 10:12Z 发根单 → 10:34Z 收口（约 22 分钟），其中基线复算 ~8 分钟。

## R2-打磨（polish）✅ 已收口（根 `T0r60`，2026-09-27 10:35Z→11:25Z）

半径 = 不改变对外语义的可验证收敛，三件全落。报告 `memory/reviews/20260927.19.05.00.md`
（24,433 B，37 道门禁全绿，《被拒原文》30 条逐字；页脚 `fixed=BUG-42 locks=8 judge-defects=5 op-defects=5 decisions=5`）。

- **BUG-42 清偿**：按生效性双口径（AST 候选 `[1418, 2084]`/`[484, 926]` × `co_firstlineno` 2084/926）删掉两处被遮蔽死码，
  共 20 行（`cython_generator.py` 8 行 / `scope_analyzer.py` 12 行，sha8 `659af698`/`fee43efe` 记在 `polish_r2_cut.json`）。
  删除由**两路独立口径**复算：驱动自证 + 从仓库外快照 `E:/IDEProjects/AI/_cypy_snapshots/pre_polish_r2`（323 档）反解
  ——模块级与类内符号集合逐档相同、快照切片与 `removed_text` 逐字相等、行数差 -8/-12、
  绑定行号上移量恰等于删除行数（2084→2076、926→914）、全树同名遮蔽 `tree_dupes={}`。
  被删的 `_visit_MetaBlock` 唯一守卫文案留档可回放；其语义在 parser 里另有实现（`_require_module_level("meta", …)`，
  HEAD parser.py:2405 已有）⇒ 调用面仍报 `meta must be defined at module level, found at 2:9`，已钉成成对锁。
- **机制化**：结构判据 `test_product_code_has_no_shadowed_method_definitions`（同类体内同名方法即红）
  + 合成违例对照 + 身份锁（不钉行号，钉实现里的独有字样）⇒ 本环新增 8 条永久锁。
- **三套基线**（同一时刻、最终文本）：pytest `1894 passed in 395.87s`（收集 1894，下限 1894=1886+8）/
  自研 `Total: 47 | Passed: 47 | Failed: 0` / e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；
  HEAD 仍 `17d68b4`，暂存区 0 文件，脏行 162；半径 3 档全部归属本 lane。
  首跑（测的是排版前文本）留档 `polish_r2_baselines_run1.json`（`1894 passed in 612.68s`），两跑互证。
- **lint**：亲笔 147 行零违例；两档产品码**新增 0 行**（纯删除可机器否证）；存量违例 `scope_analyzer` 47→44、
  `cython_generator` 418→418；必然违例自检 `selfprobe-caught` + 干净样例不误抓。
- **账本**：BUG-42 的 `### FIXED(打磨=已完成)` 段落账（`marker_count=1`，幂等守卫在重跑时 rc=1 拒绝），
  三向对照 entries=53 / fixed_sections=42 / bug_tasks=49 / bug_card_only=8 / 孤儿 4 条（沿上一环定性，未新增）。
- **收口**：16 叶 8 枝全链 omega 通过（`closed=16/16 failed=none`）；根 `T0r60` 终态 `已归档`。
  上卷被拒 **30 条按作用域分栏**：root 6 条是既定的（无 `[omega:required]` ×3 + `待验收` 态 ×3），
  branch 24 条是**我重跑驱动**造成的（第一次在分支循环之后才撞 L4 产物门而中止，分支链已落库）
  ⇒ 修正上一环"超过 6 就是重入"的粗糙说法：**要按 task 作用域分栏数，不能只看总数**。
- **本环自身缺陷 10 条**（判据/工具 5 + 操作 5）逐条进报告 §五，其中三条值得跨轮记住：
  ① 门禁 `min_chars`/`min` 按估数写 ⇒ 预检与门禁当场打回（实测 1055/299/166 对 1200/300/300）——
  **门槛必须从盘面读出来再填**；② `report_kit.py` 根收口行读 `refused_count` 而驱动写的是 `refused` 列表
  ⇒ 上一环报告印出 `被拒 None 条`（原文表 6 条齐全，汇总数字说谎），本环修工具并用上一环的件复算为 `被拒 6 条`，
  旧报告不重写、在此逐字承认；③ 基线跑一半改被测量文件 ⇒ 重跑并留 run1。
- 时间盒：本环 10:35Z 发根单 → 11:25Z 出终版报告（约 50 分钟，其中两轮全量 pytest ~17 分钟）。

转结新增：`close_root_generic.py` 的 L4 产物门前置（裁决项 5）、`_visit_ExprStmt` 分发语义取舍（裁决项 3）、
analyzer 侧是否恢复 meta 守卫（裁决项 2）。


## R2-推进（advance）收口记录

终版报告 `memory/reviews/20260927.19.55.00.md`（25,051 B，38 道门禁全绿，《被拒原文》6 条逐字；
页脚 `fixed=BUG-48 new=BUG-54 locks=9 judge-defects=6 op-defects=5 decisions=4`）。

- **半径**：指挥官裁定「已声明未实现」，落在 `cypyc watch` 一条链。动手前先把转结原话重测一遍：
  BUG-48 说 watch『无产物无日志』——before 件实测 `File changed` 3 条 / `Successfully reloaded` 2 次 /
  `rc=0` / `Traceback` 0 ⇒ 两半都不成立；真缺的是 `-o` 收不到产物、CLI 从不传 `on_reload`、
  `--debounce` 被引擎写死 0.5。三件全补，各自的成对对照都在盘上（不设目录=空操作 / 锁可重入 / 不传仍 0.5）。
- **附带抓到并发互踩**：`build/` 中间目录被同进程的多个编译批次互踩。同夹具开关两态：
  锁关 3/3 轮出红且成因均为编译类（`race_probe.lock_off_red_rounds=[1, 2, 3]`），锁开 3/3 全绿。
  锁最终落在**类**上（`HotReloadEngine._compile_lock`），跨进程那半边入账 **BUG-54**（`T0r62`）不修，
  关闭判据写明必须两个子进程并发编译才算修。
- **三套基线**（同一时刻、最终文本，`advance_r2_baselines.json` refuse=[]）：
  pytest `1903 passed in 412.93s`（收集 1903，下限 1903=上一环 1894+本环 9 条锁）/
  自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；
  HEAD 仍 `17d68b4`、暂存 0、脏行 163；半径 4 档全部归属本 lane。
  **首跑是带红的**（`1 failed, 1901 passed in 349.36s`）：我把 `_compile_lock`/`_artifact_dir` 只写在
  `__init__` 里，撞上老用例 `HotReloadEngine.__new__` 绕过构造的写法 ⇒ 提成类属性 + 补第 9 条锁，
  首跑 json 与逐条 stdout 都留档（`advance_r2_baselines_run1.json`、`r2advance_logs/*_run1.*`）。
- **lint**：亲笔 429 行零违例（`selfprobe-caught`）；超长行 5 条全是我自己写出来的，落在全量之前被抓。
- **账本**：BUG-48 的 `### FIXED(推进=已完成)` 段落账，判据从"引用次数 +1"换成**账本终态**
  （`marker_count=1`、`phrase_total=2`、`phrase_in_fixed_section=true`）——原来那条判据被折行的
  逐字引用骗过（段已落盘、次数没动）。三向对照 entries=54 / fixed_sections=43 / bug_tasks=50 /
  孤儿仍是沿用的 4 条（T0r2-T0r5，未新增）；`check_claims.py` refuse=[]（54 档 bug、251 个任务）。
- **收口**：16 叶 8 枝全链 `closed=16/16 failed=none`；根 `T0r61` 终态 `已归档`，上卷驱动**只跑一次**
  ⇒ 被拒按作用域分栏 `root 6 / branch 0 / leaf 0`（6 条既定语义逐字进报告）。
  草稿-终版两步走：`--pre-close` 先出 21,931 B 草稿喂 L4 产物门，上卷后重生成终版。
- **本环自身缺陷 11 条**（判据/工具 6 + 操作 5）逐条进 §五，四条值得跨轮记住：
  ① 给已有类加必填实例字段前先 grep 谁绕过 `__init__` 造它；② "只加字段"这类改动跑完新锁要**立刻**
  跑全量，别排到收口复算（本轮这条红到 19:57 才露头）；③ 门禁别去断言"值为 0 时整个不出现"的键
  （`by_scope.branch`），缺席与零必须可分辨；④ 逐字引用被折行打断就不是逐字，判据要按"同一字符串
  落在指定区间内"来写，且**落盘前**就得断言。
- 时间盒：本环半径窗起点 19:24（本地）→ 终版报告落盘 20:31（本地）≈ 67 分钟，含两轮全量 pytest 约 12 分钟。

转结新增：BUG-54 修法二选一（`build_temp` vs 进程套娃，裁决项 2）、`watch` 删除事件是否清 `-o` 旧产物
（裁决项 3）、已发布法则文本与终态实现的两处字面差（`引擎级`→`类级`、spec 针头 1902→1903，裁决项 4）。


## R3-寻虫（hunt）收口记录

终版报告 `memory/reviews/20260927.20.55.00.md`（22,044 B，38 道门禁全绿，《被拒原文》6 条逐字；
页脚 `new=BUG-55..BUG-60 withdrawn=C2:DESIGN,C7:REJECTED candidates=8 confirmed=6 repro=8/8 locks=0 judge-defects=8 op-defects=5 decisions=5`）。

- **半径**：0 档产品码——本环主张「寻虫不动产品码」，用 mtime 负证（`hunt_r3_baselines.json` 的
  `radius.count=0`、`rows=[]`、`unclaimed_by_this_lane=[]`）。这条主张成对：同判据在上一环能抓到 4 档，
  在本环抓到 0 档 ⇒ 判据活着，只是这次确实没动手。
- **三级确认流水线**（本环新建的方法）：子代理 8 条主张 → 成对探针（`hunt_r3_confirm.py`，
  每条必带「必被抓的合成违例 + 必不误抓的正例」，桶 `confirm|check-only|declared-scope`）→
  一条命令复现（`hunt_r3_repro.py`，退出码 0=现形 / 1=不现形 / 2=夹具坏）。
  结果 CONFIRMED 6 条入账（BUG-55 `T0r63` / 56 `T0r64` / 57 `T0r65` / 58 `T0r66` / 59 `T0r67` / 60 `T0r68`，
  severity medium×4 + low×2），撤回 2 条并写明理由：C2=DESIGN（`SYNTAX/19-comptime.md:22/:43` 已声明初稿路线）、
  C7=REJECTED（AST 实测否定）。探针 8/8 现形、0 条 `PROBE-BROKEN`。
- **BUG-60 的修法来自冻结层而非裁决**：`build_block_checker` 模块 docstring 规则 2 与
  `SYNTAX/04:105/:131` 冲突——按「SYNTAX/PROJECT-SPEC > 模块 docstring > 类/函数 docstring」的读取顺序，
  该改的是 docstring，不是补实现（补实现会打断 36 处 `: *t` 合法写法）。
- **三套基线**（最终文本、`hunt_r3_baselines.json` refuse=[]）：pytest `1903 passed in 499.61s`
  （收集 1903，下限沿用上一环 1903，本环未新增锁）/ 自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` /
  e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；HEAD 仍 `17d68b4`、暂存 0、脏行 163。
- **账本**：`report_bug` 追加 6 条，三向对照 entries=60 / fixed_sections=43 / bug_tasks=56 /
  孤儿仍 4 条（T0r2-T0r5，沿用定性未新增）；`check_claims.py` refuse=[]（60 档 bug、276 个任务）。
  服务端 `status_counts` 里 `OPEN` 60 条是账本字面（无 close API），不等于 60 条未修。
- **收口**：16 叶 8 枝全链 omega 通过；根 `T0r69` 终态 `已归档`，上卷驱动**只跑一次** ⇒
  被拒按作用域分栏 `root 6 / branch 0 / leaf 0`（6 条既定语义逐字进报告）。
- **本环自身缺陷 13 条**（判据/工具 8 + 操作 5）逐条进 §五，四条值得跨轮记住：
  ① 门禁去断言"值为 0 时键不出现"的形状（`by_scope.branch` 缺席）——驱动改为三个作用域恒出键；
  ② 给没有该旗标的驱动传 `--dry-run`，它不报错、直接把真实落库链跑完 ⇒ 两个 close 驱动加了
  「收到任何旗标即 REFUSE」的前置守卫，并配一条必然被拒的合成对照（`hunt_r3_flag_guard.json`）；
  ③ 合取型判据（"所有 case 都对"）在含故意假样本的集合上恒假 ⇒ 拆成 `all_confirmed_pairs_ok`
  与 `non_confirmed_pairs` 两条；④ `now` 手打与服务器落戳差 69/70 秒 ⇒ 驱动改用 `utc_now()`、
  戳从账本反解，并补门禁 ㊴。
- 时间盒：**本环墙钟 20:20（本地）发根单 → 23:54 落终版报告 ≈ 214 分钟，超出 ≤100 分钟的自定红线**。
  成因是本 lane 内两次上下文压缩（非产品慢、非全量套件——两套全量合计约 12 分钟），
  但红线就是红线：如实入账，不事后改口径。下一环起改为「先落盘再压缩」：每完成一个证据件立刻写
  `hunt_r3_*.json` 与报告骨架，恢复时读盘不靠回忆。

转结新增：BUG-55..60 的修复半径（裁决项 1）、BUG-57/60「改文档 vs 补实现」二选一（裁决项 2）、
BUG-56 `run_default` 去留（裁决项 3）、BUG-59 编译序是否进 golden（裁决项 4）、
`close_root_generic.py` L4 产物门前置（沿用裁决项 5）。


## R3-修复（fix）收口记录

终版报告 `memory/reviews/20260928.00.20.00.md`（28,518 B，46 道门禁全 ✅，《被拒原文》6 条逐字；
页脚 `locks=17(pos=11,ctl=6) flips=C1:1,C3:1,C4:1,C6:1 kept_red=C5,C8 pytest=1920 suite=47/47 e2e=25/25 radius=7 judge-defects=12 op-defects=8 decisions=5`）。

- **半径**：上一环入账的六件（BUG-55..60 ↔ `T0r63..T0r68`），7 档文件全归本单（mtime 反解，
  `unclaimed=[]`）。每件都记了『声明面 / 所选修法 / 被放弃的替代方案及理由』，写在
  `fix_r3_plan.json`，并由 `fix_r3_plan_check.py` 把"每行都有 X"算成 derived 布尔供门禁解析。
- **修法要点**：泛型收集改认 `generic_params`（同时保留 `type_params` 那一族）；`cypyc transpile`
  的四个旗标在 `run_transpile` 全部落地（`--check-only` 只分析不产码、`--emit-ast` 打节点树、
  `--emit-cython` 打 .pyx、`--generate-setup` 用 `SetupGenerator` 写 setup.py，实测能走通
  `build_ext` 出 .pyd，见 `fix_r3_setup_build_evidence.json` 含 sha256）；`CUnion` 示例改成
  文档自己承诺的两种形状 + 内建类型给 `UnionTypeError`；环内编译序 `sorted()`；
  `realloc` 注解 `Optional[int]` 并写明 `size<=0` 分支；`build_block_checker` 规则 2 按
  SYNTAX/04 重写（**冻结语义优先于模块 docstring**，所以不改实现）。
- **前后对照用上一环的原夹具**（`hunt_r3_repro.py`，同一把尺子）：C1/C3/C4/C6 从 rc=0 翻到 rc=1；
  C5/C8 **仍 rc=0 且这是刻意的**——C5 的现形判据钉"返回 None"那半被既有测试 `test_realloc_zero_size`
  钉住，C8 的"块外指针不报错"按 SYNTAX/04 才是正确行为；两件的声明侧变化给了可机器否证的字面
  （`annotation: int → Optional`、旧 docstring 字面消失且新字面引用冻结层）。
- **锁**：`tests/test_loop_20260927_fix_r3.py` 17 条（pos 11 / 对照 6），声明名 == `--collect-only`
  == PASSED 三向相等。**锁承重**是两级证据：主证据=改码前落盘的 before 快照翻转
  （`fix_r3_evidence.json` 带 `judge_selfprobe` 三条自证）；次证据=`17d68b4` 旧码树上 6 组全出红
  （12 红 5 绿），红因按 stale/behavioral 分栏，且件里写明「HEAD ≠ 开工基线（红线禁 commit、
  工作树数百行未提交）」。次证据还反过来抓出我把一条 pos 锁误标成对照。
- **三套基线（权威时刻 run2，`fix_r3_baselines.json` refuse=[]）**：pytest
  `1920 passed in 470.29s`（收集 1920，下限 1920=寻虫环实测 1903 + 本环 17）/
  自研 `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`；
  HEAD 仍 `17d68b4`、暂存 0、脏行 166。**run1 已归档**（`fix_r3_baselines_run1.json` +
  `r3fix_logs_run1/`）：它的 lint 格与 worktree 格是恒真形状（flake8 输出 158 行全解析失败记成
  "0 违例"），修完解析器才重跑权威时刻。
- **lint**：E9/W605 零条、亲笔新文件零违例、E501 逐文件恰等于修前存量上限
  （`cli.py` 1、`build_block_checker.py` 3，只准减不准增）；存量 W293 154 条照计数照写。
- **账本**：BUG-55..60 各追加 `### FIXED(修复=已完成)` 段（6 段、条目仍 60、标题行逐字未动）；
  幂等守卫在重跑时 rc=1 拒写，另加 `--verify` 模式复算终态，`--dry-run` 这类坏旗标必须被拒（实测 rc=1、
  段数仍 6）。三向对照 entries=60 / bug_tasks=56 / referenced=52 / bug_card_only=8（BUG-44..51，
  沿前判定）/ 孤儿恰等于白名单 T0r2-T0r5；`check_claims.py` refuse=[]（60 档 bug、301 个任务）。
- **收口**：16 叶 8 枝全链 `closed=16/16 failed=none`；根 `T0r70` 终态 `已归档`，上卷驱动**只跑一次**
  ⇒ 被拒分栏 `root 6 / branch 0 / leaf 0`。
- **本环自身缺陷 20 条**（判据/工具 12 + 操作 8）逐条进 §六，四条值得跨轮记住：
  ① 禁 commit 的仓里 HEAD 落后开工盘面 ⇒ **动手前先落 before 快照**，旧码树只能当次证据；
  ② 恒真门禁的形状是"解析器读不到就记 0"⇒ 判据必须自检"解析行数 == 输出行数"；
  ③ 逐行主张（"每条都有 X"）`report_kit` 解析不了 ⇒ 先算成 derived 布尔再当门禁，别写 `>=6` 凑数；
  ④ needle 不能凭记忆重打（本轮两条被写前断言挡下，一条都没落盘）。
- 时间盒：00:00（本地）开工 → 00:57 落终版报告 ≈ 57 分钟，在 ≤100 分钟窗内（含两套全量约 11 分钟）。

转结新增：BUG-58 的行为半边（`realloc(p,0)` 是否改成返回 0/抛错，需连既有测试一起改口径）、
BUG-60 是否把"指针只能在函数作用域"落成强制检查、BUG-57 的 Python 内建类型→ctypes 宽度映射规则、
BUG-56 `run_default` 去留、BUG-59 编译序是否入 golden、
`CypyHook` 应公开 `analyze_only()`（CLI 目前直调私有 `_parse_and_analyze`）、
仓库内 CRLF/LF 混用文件（`cypy_bridge/union.py`、`cypyc/analyzer/scope_analyzer.py` 等）是否统一。

### R3-验证（第 3 轮第 3 环）· 收口记录 · 根 `T0r71`

- 报告：`memory/reviews/20260928.01.25.00.md`（`[selfdrive-verify]` 页脚）；判据件 6 张：
  `verify_r3_matrix.json` / `verify_r3_callsite.json` / `verify_r3_report_audit.json` /
  `verify_r3_baselines.json` / `verify_r3_irreversible.json` / `verify_r3_self_audit.json`。
- **逐单回退矩阵**：`rows=6/6`、`identity=6`（6 个被测模块 `__file__` 落在快照树）、
  `sha_verified_rows=6/6`、`all_restored=1`；每行「字面锚点计数 ==1 才替换 → `py_compile` →
  跑锁 → 按 mutation 前字节回写 → sha256 逐字比对」。该件另含 **恒真格自检**：
  mutation 后文本与原文逐字相同即判该行空转并拒（防"针没打到却报绿"）。
- **底树改判**：run1 用 `git archive HEAD` 造出与 mutation 无关的假红
  （`AttributeError: 'function' object has no attribute 'union'` ⇒ HEAD 的包 `__init__` 仍把同名函数
  导在子模块之前），已归档 `verify_r3_matrix_run1_headbase.json` + `r3verify_logs/premise_run1_headbase.log`；
  权威底树 = `git ls-files` 全集按盘上内容复制 + 本轮 7 档覆盖（tracked 却已不在盘上的 10 档点名）。
- **前提格**：快照树里 `17 passed / --collect-only 实收 17 / 红 []`；身份的第二重是**因果证明**——
  工作区 7 档全程 sha 不变 ⇒ 红只可能来自快照码（跑错副本就整行红不了，矩阵自我作废）。
- **上一环主张回算**：`carried_claims=6/6`（重跑寻虫环同夹具：C1/C3/C4/C6 现形→不现形，
  C5/C8 仍现形，与页脚 flips/kept_red 自述一致）、`declared_side_still_true=6/6`（逐件从盘面字面重算）。
- **调用面独立复验**：16 条全真（含 `--bridge --generate-setup` 组合、`--bridge --emit-cython`
  必须明确decline、realloc 全生命周期 `malloc→realloc→memset→读回 b'AAAA'→free`、
  `get_type_hints` 对象相等、另外 6 个哈希种子 + 双环新图、冻结形 `struct Box<T>` 走 CLI 出码）。
- **审计上一环报告与账本**：计数反解 `23/23` 相等；被拒原文**双向**集合对表（吞/造/改字都抓）；
  账本 6 段 `### FIXED` 的复跑命令当场跑，退出码与该段自述 `after rc` 相符 `6/6`。
- **自我审计（本轮报告同一把尺子）**：`verify_r3_self_audit.json`（页脚每条数字反解再对表一遍）；页脚每条数字都必须从五张判据件反解相等。
- **三套基线（run2 权威批次，refuse=[]）**：窗口 `2026-09-27T17:33:11Z → 17:43:38Z`，各格自记 `at_utc`；
  pytest `1920 passed in 355.38s`（`--collect-only` 实收 1920，下限 1920）/ 自研
  `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
  （该格时刻由证据文件 mtime 反解并写明方法，见下条缺陷）；HEAD 仍 `17d68b4`、暂存 0、
  脏行 166、tracked 却不在盘上的 10 档点名。
  **run1 已归档**（`verify_r3_baselines_run1.json` + `r3verify_logs_run1/`）：它的 `own_snapshot_gone`
  格拿 `git worktree list` 找 `tmp_verify` 子串 ⇒ 恒真（快照树从来不是 worktree），修成数盘上目录
  （run2 实测 `own_snapshot_dirs_left: []`）后重跑；`lint.files` 也从 6 涨到 8（本环新增驱动都入 lint 面）。
- **半径（负面主张正面测）**：`radius.count=0`、`radius_claim_ok=1`——验证环不动产品码，
  由 7 个可维护目录里 mtime ≥ 开工时刻（`2026-09-27T17:01:14Z`）反解，不由自述。
- **不可逆动作**：点名 `10` 条，`live_probe=9 / manifest=1`（PR/外部可见动作只能给清单级证据并写明原因），
  `executed_none=1`；`issue_up` 这一名称在本 FIST 构建的 30 个工具里**不存在**，
  最近似是 `report_bug`（bug 上报）+ `publish`（任务上报）⇒ 由寻虫/修复环承担，验证环不冒充"已开"。
- **本环自身缺陷 14 条**（判据/工具 10 + 操作 4）进 §六，六条值得跨轮记住：
  ① 禁 commit 的仓里回退矩阵的底树必须是**盘面快照**，`git archive HEAD` 会造混因红；
  ② `pytest -q` 全通过态不打印 `collected` ⇒ 收集数只能 `--collect-only` 数 nodeid（否则绿树恒红）；
  ③ 反解出**空清单**是判据坏了的第一个信号，必须写成 refuse 而不是"对方说谎"；
  ④ 报"入口做不到 X"前先证明输入形状出自冻结规范（`generic struct` 不在 SYNTAX/11，
  而上一环的锁夹具用的正是它 ⇒ 转结 R4）；
  ⑤ 报告里的**时间状语也是主张**——"同一时刻复算"实际是跨 10.5 分钟的一批连续跑，
  措辞必须降到盘面能证明的程度（各格自记 `at_utc` + 窗口字段）；
  ⑥ 同形 `return` 的批量补丁 `replace(..., 1)` 只吃掉第一处 ⇒ "每格自记时刻"当时只落地两格，
  第三格靠证据文件 mtime 反解补上并在件里写明方法（不冒充驱动自记）。

- **链路与开关（实测，不靠回忆）**：`call_log` 窗口内 200 次调用、194 ok、6 拒——6 条恰为根 `T0r71`
  的既定结构性拒绝（无 `[omega:required]` + 根已在待验收），`root 6 / branch 0 / leaf 0`
  ⇒ 上卷驱动只跑过一次；omega 三连各 **24 次成功** = 16 叶 + 8 枝全覆盖；
  `laya_decide` 调过 1 次且实测 `available=False` ⇒ 记 `source:self` 的显式降级；
  **`issue_up` 在本 FIST 构建的 30 个工具名里不存在**（`select distinct tool from call_log` 全量列过），
  最近似是 `report_bug` / `publish` ⇒ 本环不冒充"已开"，上报按环分工落在寻虫/修复环。
- **收口**：16 叶 `closed=16/16 failed=none`（每叶 ov=pass、verify=已完成、errors=[]）；
  根 `T0r71` 终态 `已归档`；报告 56 道门禁 **56 ✅ / 0 ❌ / 0 ⏳ / 0 ‹未解析›**。
- **自我审计**：`verify_r3_self_audit.json` 27 格反解全相等（页脚每个数都回判据件对表，
  含 `gates=56`、`refused=6`、`baselines_run=2`、`irreversible=10(live=9,manifest=1)`）；
  页脚由 `verify_r3_footer.py` 从件里**合成**，不由手打。`check_claims.py` refuse=[]（60 档 bug、326 个任务）。
- 时间盒：17:01 开工（根发布）→ 17:45 起收口，取证面 ≈ 44 分钟、含两套全量各约 6~9 分钟；
  终版时刻见页脚 `generated_at`。

转结新增（R4 输入）：parser 容忍 SYNTAX 未定义的 `generic struct` 形且错误要到分析层才露出
（真发现，交 R4-寻虫定性）；BUG-55 回归锁夹具应换成冻结形 `struct Box<T>`；
取子模块建议统一 `importlib`（`from cypy_bridge import union as union_mod` 在旧 `__init__` 下被函数遮蔽）；
`--bridge --generate-setup` 组合是否升格成回归锁；SYNTAX 两档相对 HEAD 的既存漂移（41 增/11 删）
要不要回退——连同历轮未提交成果一起处置。

**顺手纠一条历轮转结里的措辞债**：上一环写的是「仓库内 CRLF/LF 混用文件（`cypy_bridge/union.py`、
`cypyc/analyzer/scope_analyzer.py` 等）」，字节级实测是 **39 个纯 CRLF / 203 个纯 LF / 只有 1 个逐行混用**
（`tests/test_new_features_boundary.py`）。`union.py` 与 `scope_analyzer.py` 都是**纯 CRLF**，
不是「同一文件里两种行尾混着」——真实缺陷形状是**仓库级不统一**，打磨面的口径因此改成
「新文件统一 LF + 存量按清单交裁决」，而不是按混用去逐文件重排（基线已冻结在
`r3_polish_pre_baseline.json`：E501 355 条/48 文件、E9/W605 0 条，口径与 `pyproject.toml` 的
`max-line-length = 100` 一致）。

---

## R3-打磨（polish）收口记录 · 根 `T0r72` · 报告 `memory/reviews/20260928.02.25.00.md`

- **范围（不扩语义）**：8 法全部落在「锁的质量 / 缺锁的形状 / 入口门面 / 文档三向 / lint / 行尾 / 三套体系 / 半径自洽」，
  产品码只碰 2 档（`cypy_hook/hook.py` 加公开 `analyze_only()` 纯委托、`cypyc/cli.py` 改走公开面），
  文档 1 行（`docs/USAGE.md` 补 `--emit-code`），测试 1 改 1 新。
  **本环不开 BUG 卡**（sqlite `ns='bugs'` 里含 `[loop:R3-打磨]` 的条数实测 0）。
- **改动半径（mtime 反解，非自述）**：**5** 个文件、逐档归属本单，越界 0、清单未落地 0
  （`polish_r3_baselines.json:radius`）；同一条半径同时作为「未整档 formatter」的 derived 证据。
- **锁与承重**：新增 9 条锁，两个锁文件 26 条当场全绿；回退矩阵 **8/8 组**
  （7 组 mutation 各自打红对应锁、1 组「只改注释」对照必须全绿），
  窄性断言 `must_stay_green` 8 处全过，同因连带走白名单并逐条写原因；
  9 条里 7 条有回退证明、2 条点名（反方向对照 + 现状探针），未覆盖集合由判据**恰好等于**约束，不许含糊。
  证据落盘与回退矩阵引用同一对 sha256（`lock_file_sha256`）。
- **三套体系复算（窗口 18:13:35Z→18:25:44Z）**：pytest **1929 passed / 1929 collected**（下限从 1920 抬到 1929，
  且本轮 9 条新锁在全量收集里逐条现形）、自研套件 **47/47**、e2e golden **25/25 且 FAIL/WARN/UNREG 全 0**；
  git 红线格 `all_ok=true`（HEAD 仍 `17d68b4`、暂存区 0 行、他人 worktree 在、临时快照树 0）。
- **lint 与行尾**：E9/W605/F821 三类硬违例 0；E501 存量 **355 → 355**（`reduced=0`，报告按 ⚠「持平非改善」写，不粉饰）；
  混用文件仍 1 个、行尾类别漂移 0、单档改动行数最大 8（上限 40）。
- **不可逆面**：12 条（live 9 / derived 1 / manifest 2），实测零执行；判据通道自测（注入假违例）`caught=1`。
  push 那条从"本仓无上游所以不可能推"改成 live 两半：本地领先数 `1` 与上一环实测相等 ＋ `origin/master` 的
  reflog 顶条时间早于开工。**教训：负面主张的措辞必须过盘面，不能在上一环结论上续写。**
- **链路证据（`r3_polish_calllog_tally.json`，按 `params_json.task_id` 前缀分栏，不按标签）**：
  `T0r72` 197 次调用 / 191 成功 / **6 条被拒**（全部是根任务 `待验收` 态的 claim/execute/submit
  与根未开 `[omega:required]` 的 omega 三连，属既定语义，逐字进报告）；
  omega 三连各 **24 次成功** = 16 叶 + 8 枝全覆盖；`output_validate` 17 次、`verify` 25 次成功。
  同窗口里 `T0r71`（验证环收口）另占 179 次 / 6 拒，**不合并计数**；
  `laya_decide` 全库仅 16 次（上一环实测 `available=False`，本环未调）、**`issue_up` 仍不是工具名**（0 行命中）。
- **收口**：16 叶 `closed=16/16 failed=none`；根 `T0r72` 终态 `已归档`；
  报告 **74 道门禁 74 ✅ / 0 ❌ / 0 ‹未解析›**，6 条被拒原文逐字渲染。
- **自我审计**：`polish_r3_self_audit.json` post 态 **67 格全相等**，独立重算而非抄件（盘上重数 `def test_`、
  AST 重取旗标、`git status` 现算、flake8 亲笔文件当场再跑、difflib 重算单档行数、mtime 重扫半径）；
  另两格专防"判据不会失败"：`vacuous_gates=[]`（`min: 0` 恒绿格必须为 0）与正文占位残留必须 0。
  两次成文（render→audit→render→audit）收敛到同一格数，取最终态。
- 时间盒：根发布 17:48:27Z → 收口 18:29:26Z → 终版 18:34:43Z，≈ 46 分钟（≤100 分钟）。
- **本环自记缺陷 10 条（判据与工具类）/ 3 条（操作类）**，其中四类值得带走：
  ① 基线件落反斜杠键、现值归一成正斜杠 ⇒ `baseline.get(f,0)` 恒 0 ⇒ 48 档全被判"上涨"（差点写成 E501 全面恶化）；
  ② `snap_left` 那格此前从 `git worktree list` 里找目录名 ⇒ 恒真；改成数盘上 `snap_*` 后当场抓到 7 个残留树；
  ③ 19 条 `min: 0` 的门禁是恒绿格（空表 `>= 0` 永真），换 `equals: []`/`{}`/`0` 才有信息量；
  ④ 页脚合成器把新串叠在旧串后 ⇒ 同一行两个 `judge-defects=`，被自审（后值胜出）判红——**这条红是真红**。

转结新增（R3-推进 / R4 输入）：现状探针"parser 今天仍容忍 `generic struct`"要在推进环升级为决策
（文档承认两种写法，或让 parser 拒绝并同步改锁）；`docs/USAGE.md` 的三向守卫只覆盖 `cypyc` 命令行，
`examples/` 与其他文档的旗标一致性未纳入判据；lint 存量 355 条持平、是否单开清理环待裁决；
39 个纯 CRLF 文件的行尾策略待裁决；`--bridge --emit-cython` 目前只测"明确 decline"，
若将来 bridge 支持 Cython 输出，该锁要随之改口径（已在锁文件表里留字）。


## R3-推进（根 `T0r73`，8 法 / 8 枝 / 16 叶）— 已收口 `2026-09-27T19:34:30Z`

- **半径**（按指挥官裁决"只做已声明未实现"）：`cypyc/analyzer/type_checker.py` 加 `_callable_declared_params`
  + `_check_callable_arity` 两个私有辅助与**一行调用**，落地 `Callable[[T1..Tn], R]` 的**入参元数判定**；
  形状不认识（裸 `Callable`、`Callable[int]`）就跳过不误判，关键字实参不判。改动 37 行，codegen 一字未动。
  半径实测恰好 2 档（含新锁文件），mtime 反解与清单双向对表通过。
- **立单依据是实测不是文档那行字**：开工前逐形状跑过——返回类型推断**本来就活着**（`Return type mismatch`），
  真正缺的只有入参元数；`Callable[..., R]` 实测 `ValueError: Unexpected token DOT_DOT` 且 SYNTAX 搜不到该写法
  ⇒ 不属"已声明"，不入半径，只挂账（`advance_r3_scope_face.json` 三条负面主张各配当场复验）。
- **承重证明**：9 条成对锁 + **5 组**回退矩阵（G1 摘调用点 / G2 未声明形状当零参 / G3 关键字不再跳过 /
  **G4 判定过严的宽爆破组** / C1 只改注释对照全绿）；`revert_covered=9/9`、`uncovered=0`、
  `groups_ok=5/5`、身份探针 4 个模块 `__file__` 全在快照树内、`snap_left=[]`、工作区未被驱动改动。
- **产物面两栏**：5 档源＝4 档剥时间戳后逐字相同 ＋ 1 档**故意的违例夹具**（改后被 `Callable arity mismatch`
  挡住；被别的错误挡住也算判据不合格）。
- **语料面（本轮最值得带走的一处修正）**：第一版"77 档两态对表 0 变化"是**恒绿格**——真实语料只有
  `type Callback = Callable[[int], str]` 两行**声明**、没有任何经由它的调用点，那个 0 既可以是"没影响"
  也可以是"看不见"。补成三态 ＋ 见证夹具（只进快照树，工作区 examples 一个字节未动）：违例档复原态必报、
  mutation 态必不报，合规档两态都干净，故意改宽时合规档必须**冒出** arity 行（`sensitivity=1`）。
- **三套体系同批复算**（`19:02:01Z → 19:18:23Z`）：pytest **1938 passed / 1938 collected**（地板 =
  上一环实测 1929 ＋ 盘上现数 9 条新锁，数不出 9 条即拒）；自研套件 **47/47**；e2e golden **25/25**
  且 FAIL/WARN/UNREG 三格为零。git 红线 `all_ok=true`（HEAD `17d68b4`、暂存 0 行、脏 168、foreign 树在）。
- **亲笔 lint 改成双口径**：本轮**新写的整档**（新锁文件）100 列零违例；本轮**改到的既有档**只对本窗口
  新加的 37 行负责（`violations_on_my_lines=0`）且整档违例数只减不增（325→325），对照快照 sha 先自证。
  "行号过滤"这层配了成对注入对照（130 字符行必被抓 E501、合规行不误抓）。此前那版把 `type_checker.py`
  第 4 行的既有 `F401` 记成本环违例，是判据口径错不是产品错。
- **不可逆面 14 条**（live 11 / derived 1 / manifest 2），实测零执行，注入假违例 `caught=1`；
  新增**既有测试逐名两向对照**：拿上一环留存的全量 `--collect-only` 日志（先证明名字数与该环件里
  `collected=1929` 相等）与本轮 1938 比 ⇒ 消失 0、新增 9 且全部来自本环点名的锁文件、杂散 0。
- **驱动面自己也要称**：9 个 `advance_r3_*.py` 硬码门（E9/W605/F821@200）0 违例；按仓库 100 列口径重数
  出 67 条软违例（E501 49 条为主）**逐码存债**于 `advance_r3_driver_lint.json`，交 R4/R5 按只减不增处理。
- **链路证据**（`r3_advance_calllog_tally.json`，按 `params_json.task_id` 前缀，不按标签/回忆）：
  `T0r73` 197 次调用 / 191 成功 / 6 条被拒（根 `待验收` 态的 claim/execute/submit ＋ 根未开
  `[omega:required]` 的 omega 三连，既定语义，逐字进报告）；过滤器配了必然不存在的前缀 ⇒ 0 行；
  `issue_up` 仍不是工具名（0 行），`laya_decide` 本环未调。
- **收口**：16 叶 `closed=16/16 failed=none`；根 `T0r73` 终态 `已归档`；报告
  `memory/reviews/20260928.02.55.00.md` **82 道门禁 91 ✅ / 0 ❌ / 0 ‹未解析›**，6 条被拒原文逐字渲染；
  页脚 33 格全部从判据件反解。自我审计 `advance_r3_self_audit.json` post 态 **59 格全相等**、
  `vacuous_gates=[]`；两次 render→audit 收敛到同一字节数（33734 B）。第一版自审是红的（20 格不齐：
  沿用《六》段标题、`detail[7]` 下标取数、把组数写死成 4），存档 `advance_r3_self_audit_pass1.red.json`。
- 时间盒：根发布 `18:41:40Z` → 终版 `19:34:30Z` ≈ **53 分钟**（≤100 分钟）。
- **本环自记缺陷 13 条（判据与工具类）/ 3 条（操作类）**，五类值得带走：
  ① 负面型主张的"0 变化"必须先证明判据**看得见**该看的东西（见证夹具/敏感性对照），否则与"压根没样本"
  不可分；② mutation 锚点要证明它**碰得到代码路径**（G2 第一版钉在走不到的分支上，9 条一条没红）；
  ③ 跨环取数第四次踩下标、第五次踩键形状 ⇒ 一律改按键搜索＋缺键即拒；④ 判据口径不能把历轮遗留记成本轮
  违例，也不能反向放水——收窄后必配成对注入对照；⑤ 违例夹具要单独分栏，且总数必须对得上清单。

转结新增（R4 输入）：`Callable` 别名在**产物签名**里塌成无标注、`Callable[..., R]` 变长写法、
实参**类型**判定（需先抽共用类型兼容谓词）三项交人工裁决，R4-寻虫 可当候选面但每条要先做文档声明对表；
`SYNTAX/appendix-C` 的"尚未实现"那行自本环起变陈旧（属冻结面，只点名不动刀）；
驱动面 67 条软违例是新债基线；上一项转结（`generic struct` 现状探针、`docs/USAGE.md` 三向守卫覆盖面、
E501 存量 355、39 个纯 CRLF、`--bridge --emit-cython` 口径）原样续结。

## R4-寻虫（根 `T0r74`，8 法 / 8 枝 / 16 叶）— 已收口 `2026-09-27T21:09:49+00:00`

- **交付**：报告 `memory/reviews/20260928.05.00.00.md`（33924 B，
  70 道门禁全过、0 格空缺），根 `T0r74` 终态 `已归档`，
  8 枝 16 叶 `已完成`；收口件里 30 条被拒原文逐字进报告。
- **狩猎面转向没被系统扫过的三块**：函数类型层其余缺口 / docs 与 SYNTAX 状态表同实现的分道 /
  bridge 的生成与缓存面。6 族 × 25 用例逐带配「必报的对照」，
  12 条候选按 pos/ctl 两档全部确诊（确诊 12、
  UNSURE 0），归并为 4 个代码根因；
  可见性三重见证（合成载荷翻转 12、真变异树差分 2、
  看不见与零发现分栏，盲点 1 个）——**盲点是 `struct_field_callback` 那一格探针
  没到达判定，这条如实记为清单级证据，不写成「没有缺陷」**。
- **文档/bridge 面 18 条主张逐条当场重测**（子代理只指路、未原样入账）：
  陈旧或缺口 16（其中真缺口 3）、DESIGN 撤回
  1、未测转结 1。
- **三态复现台账**：10 个根因键，退出码 {"0_all_reproduced": 10, "1_not_reproduced_selftest_rc": 1, "2_fixture_broken_unknown_key_rc": 2}
  三态本轮各自实测可达（状态 2 是我自己写坏谓词当场抓出来的，不是构造的）。
- **去重与入账**：与盘上 60 单按机制签名比对，判重 0、
  共享代码符号 7 处、逐条裁决注
  12 条；号从盘上现数 61 起，
  入账 10 张 `BUG-61..BUG-70`，
  账本 60→70、sqlite bug 行 {'before': 56, 'after': 66, 'delta': 10}，
  三向对照 10/70 一致、FIXED 段 0。
- **三套体系同批复算且只升不降**：pytest 1938（收集 1938，
  地板 1938）、自研 47/47、
  e2e 25 过且 FAIL/WARN/UNREG = 0/0/0；
  git 红线 HEAD `17d68b4`、暂存 0、外部基线树在；
  改动半径按 mtime ≥ 本轮起点正面测：产品/测试/冻结面 0，
  判据件与账本 129——**本环零产品码改动**。
- **驱动面自计**：11 个脚本硬码（E9/W605/F821/F7/F63）0 条，
  注入对照必被抓 1、不误抓 0；
  软债 112（{"E128": 5, "E501": 91, "E741": 16}）立为只降不升基线。
- **call_log 对账**（按 `params_json.task_id` 前缀，不按标签/回忆）：T0r74 树 284 行调用 /
  60 行被拒 / 去重后 23 种原文逐字进报告；
  过滤器配必然不存在的前缀 ⇒ 0 行。
  规格点名的 `laya`/`issue_up` **不是本 build 的工具名**（精确名 0 命中），承担者实测为
  `laya_decide` 1 次、
  `publish`+`report_bug` 11 次；
  `call_log` 工具本轮真调过一次（客户端回包 284 行含 T0r74
  ≥ sqlite 同口径 284 行，两个读数不等就拒）。
- **时间盒**：根发布 `2026-09-27T19:38:23+00:00` → 终版 `2026-09-27T21:09:49+00:00` ≈ **91 分钟**
  （≤100 但已逼近；8 法 × 16 叶 × 10 入账的体量决定了它压不进 60 分钟，下一环按「一 mode 一收口」再切细）。
- **本环自记缺陷：判据类 8 条 / 操作类 4 条**，值得带走的三条：
  ① 存在性判据证不了形状主张（F5 恒绿一整轮）；② 探针崩溃/非零退出绝不能读成结论，
  一律降级 `not_measured` 并保留原文；③ 判据件自己的键形状要现数（`near_miss_notes` 是 dict 不是 list，
  当 list 切片当场炸）。操作类新增一条：根收口器**必须在报告落盘之后**再跑——第一次被 L4 产物门拒是对的，
  但我为了补产物把根收口器重放到 `2026-09-27T19:38:23+00:00` 之后的时段，
  按 ts 现数：分支重放造出 48 条幂等拒绝、根上 12 条（其中 3 条是根没开
  `[omega:required]` 的既定语义）。顺序应是「报告→根收口」一次到位，已写进 R4-修复 的操作纪律。

转结新增（R4-修复 输入）：BUG-61..BUG-70 逐单认领——RC1/RC2/RC3/RC4 四条分析器根因本环可修，
每单要配成对锁 + 回退矩阵（把实现改回去锁必红）；BUG-65（冻结文档 7 行）、BUG-70（`parser.py`/
`cython_generator.py` 越 3000 行阈值）交人工裁决不动刀；BUG-66/67（bridge 缓存落调用方 CWD、
生成的 C 与 Cython 不等价）取「下一环可改」那一栏。D18（缓存命中复用）与 `appendix-C`
《已实现的限制修复》14 行本轮未复测 ⇒ 转结 R4-验证。操作纪律转结：先落报告再收根。

### 收口后补记（两条，都是收口之后当场测出来的，不改已归档的交付物本体）

1. **交付物在归档后被继续改过**：根 `T0r74` 于 `21:00:58Z` 归档，那一刻盘上的报告是 `21:00:40Z` 的
   **预收口版 24081 B**（65 道门禁，依赖收口件的那几栏当时只能标「⏳ 未落盘」）；归档后又渲染了 4 次到 **33924 B**
   （加了 §十一 逐字被拒表、页脚 5 个新键、§八 补记）。`[selfdrive-hunt]` 标记与 min_chars 门每版都过，
   但**归档那一刻的交付物与现在盘上的不是同一份**。FIST 没有「归档后重交」的出路（要动就得 reject/retry，
   而根已归档），所以这里如实记为**流程债**而不是把 33924 B 那版说成归档版。下一环的顺序改成
   「判据件 → 报告（终版）→ 叶收口 → 根收口」一次到位，报告渲染完就不再动。
2. **账本存量三向对照有 4 格对不上，且原因已定位**（`memory/bugs.md` 现数 vs `fist-mbt.db` ns `bugs`）：
   md 卡 70 张，其中 **BUG-44..BUG-51 共 8 张没有 `- task_id:` 行**；sqlite 66 行，其中
   **`T0r2`–`T0r5` 共 4 行没被任何 md 卡引用**；两边都点名到的 62 行一一对得上。
   净差 8 − 4 = 4，正是「70 vs 66」。这不是本轮造的（BUG-44..51 属 R2/R3 存量，`T0r2..T0r5` 属
   09-26 polish 道），但**账面无主**：交 R4-修复 处理——要么补齐 8 张卡的 task_id 反查行，
   要么给 4 个孤儿 sqlite 行写归属说明；两种都是可逆的账面动作，不需要裁决授权。

### R4-修复（根 `T0r85`，执行人 `cypy-fixer`）


- 结论：**已收口**。6 张修复单闭环，交人工 2 张、转下一环 2 张。
- 产品码：`cypyc/analyzer/type_checker.py` +214 / -15；新增定义 9 个、共享符号 3 个、调用点 41 处。
- 锁：修前 `14 failed, 4 passed in 0.36s` → 修后 `18 passed in 0.49s`；回退矩阵 4 条腿全部承重、对照组零误伤、sha 复原一致。
- 影响面：203 档存量语料逐档差分，新增诊断 0 / 消失诊断 0 / 待裁决 0。
- 文档面：6 行按实读对齐、半开 1 条转结、冻结面只读探针 {"appendix_still_claims_compile": true}。
- 三套体系：pytest 1956 通过 / 0 失败（地板 1938）、收集 1956、自研 {"Total": 47, "Passed": 47, "Failed": 0, "Skipped": 0}、e2e {"PASS": 25, "FAIL": 0, "RUNFAIL": 0, "WARN": 0}；HEAD `17d68b4`、暂存 0 行。
- 半径（mtime 落窗口内）：产品 1 / 测试 2 / 文档 1 / 冻结 0 / 判据件 60。
- 账面：三向一致 6/6，账本条目 70 条（追加 FIXED 未多生条目），格式化后只读复核 6/6。
- 驱动面：本轮亲笔 14 个脚本，硬错 0、软账 0（上一环基线 112）。
- 调用面（渲染前快照）：树 18 行 / 修复单 24 行，被拒 0+0 条，载体 {"laya": 1, "issue_up": 1, "call_log": 1, "omega": 0}，Omega 标记 {"leaves": 16, "leaves_total": 16, "root": 1}。
- 报告：`memory/reviews/20260928.06.15.00.md`（29907 B，sha `8f748f3253103641`，渲染 1 次）；自证门禁 102/102、《八》8 条判据自伤。
- 收口：叶 16/16、根状态 `已归档`；终账见下面那一栏。
- 终账（收口后）：树 197 行 / 修复单 24 行，被拒 树 3 + 单 0 条，Omega 链 75 次，载体 {"laya": 1, "issue_up": 1, "call_log": 1, "omega": 75}；客户端可见 T0r85 行 197。
  被拒原文（逐字）：

| 被拒原文（逐字） | 工具 | 次数 | 首个见证 |
| --- | --- | --- | --- |
| `非法迁移: claim 要求状态 [待领取]，当前是 [待验收]` | claim | 1 | T0r85 @ 2026-09-27T23:32:22Z |
| `Omega 强验证门禁：任务 [T0r85] 尚未创建语料，请先由语料创建者执行 omega_spec_create` | execute | 1 | T0r85 @ 2026-09-27T23:32:22Z |
| `非法迁移: submit 要求状态 [执行中]，当前是 [待验收]` | submit | 1 | T0r85 @ 2026-09-27T23:32:22Z |

- 渲染后的动作（逐条声明，报告本体一个字没动，`fix_r4_render_order.json` 的 sha `8f748f3253103641` 与 `--check` 实测一致）：① `fix_r4_render_order.py` 加了更富的见证字段（产品码 mtime、spec 身份、页脚签名）并重记一次；② 本轮 14 个驱动按同一 flake8 口径复扫仍为 0 硬 0 软（23:31:30）；③ 叶/根收口链的调用面只进终账件，不回灌报告。
- 流程债（不可逆，已归档不能补）：根单 `T0r85` 这一轮**带** `[omega:required]`，而 `close_root_generic.py` 的步骤形状仍按上一轮「根没标记」的模板发 ⇒ 先 `claim`（已是待验收）、再 `execute`（语料尚未创建）、再 `submit`（不在执行中）三条被协议层拒；随后 spec_create/spec_review/omega_result_verify/output_validate/verify/archive 全过，根终态 `已归档`、`assignee=cypy-fixer`、`deliverable` 3080 字、specs 表 2 行。**新事实**：带标记的根单确实能跑完整 Omega 链（上一轮的 #59 只说『缺标记的根必被拒』）。修法在驱动侧：按节点实测 `(status, 有无标记, specs 是否已有行)`生成步骤，下一环（R4-验证）起手就要按这个形状发。
- 时间盒：本环自 2026-09-27T21:16:43Z 起算，超过 100 分钟盒；门禁未缩、判据未放宽、未动冻结面，超盒按纪律如实记账并转 R4-验证 复核。
- 起于 2026-09-27T21:16:43Z，本条记录生成于 2026-09-27T23:33:56+00:00。

<!-- R4-验证 段由 verify_r4_progress.py 于 2026-09-28T01:37:49+00:00 重生成：第一版把 window.finished_at_utc 当成「跑完时刻」算出 73 分钟「在盒内」，并把模块级 if 的行号渲染成空；该段已整段删除后由同一脚本重写，不是追加双发。 -->

### R4-验证（根 `T0r86`，执行人 `cypy-verifier`）


- 结论：**已收口**。八条法全部独立复算，半径=只看不动手（产品 0 / 测试 0 / docs 0 / 冻结 0 全空，判据件 259 个）。
- 回退矩阵：22 行切片自 difflib，承重 13 / 不承重 9 / 摘坏 0，sha 复原 22，反面 canary 被抓 1。
- 调用面：18 条 CLI 探针（对照 4 条），外泄内部表示 0 条，换回修前码翻转 13 条（含正确形状 ["V61a", "V61c"]）。
- 附录 C：反解 14 行，成立 10 / claim-false 1 / half-true 3 / 没测到 0，needle 对照 1。
- 真编译：三发 rc=[0, 2, 2]（合法 C / 合成违例 / bridge 生成物），模块级 if 在第 10 行；D18 no-reuse（重写 True）。golden 面 26 个文件 sha True 相等、未跟踪新增 0。
- 三套体系：pytest 1956 通过 / 0 失败 / 0 错误（地板 1956）、收集 1956、自研 {"Total": 47, "Passed": 47, "Failed": 0, "Skipped": 0}、e2e {"PASS": 25, "FAIL": 0, "RUNFAIL": 0, "WARN": 0}；HEAD `17d68b4`、暂存 0 行、脏行 169、冻结面 43 个文件 sha 未变。
- 锁必红复核：三档 [["work", "green", 0], ["pre_r4", "red", 14], ["head_code", "red", 18]]，同一份测试（sha 集合=1），HEAD 档红在本轮形状上的有 13 条。
- 账面：md 73 卡 / sqlite 69 行，差 4（有卡无行 8、有行无卡 4），FIXED 三向一致 6/6，复跑 13 条：不再现形 ["BUG-61", "BUG-62", "BUG-63", "BUG-64"]、仍现形 9、未交代半开 0。
- 挂账：不可逆 7 条逐条带测量（canary True），裁决队列 8 条；新入账 3 张 ["BUG-71", "BUG-72", "BUG-73"]（sqlite 增量 3）。
- 驱动面：本轮亲笔 17 个脚本，硬错 0、软账 0（上一环基线 0）。
- 报告：`memory/reviews/20260928.09.25.00.md`（48474 B，sha `fe5738f91188bf65e4e1c21c9f80acd0856d5f93e0ce2910d04a284dca139a4e`，渲染 1 次，被拒重试 0 次，门禁表 152 行全绿 152）；自证 141/152 道，自引用延后 11 道，《十》20 条判据自伤，件-脚本同源披露 1 条。
- 收口：叶 16/16、失败 0，根状态 `已归档`。
- 时间盒：环节起于 2026-09-27T23:40:14+00:00；`window.finished_at_utc`=2026-09-28T00:53:15+00:00 这个键实测存的是基线脚本**自身起跑**的时刻（不是三套体系跑完的时刻，报告 §十 19 已记），所以终点取本进度件的生成戳 2026-09-28T01:38:03+00:00 ⇒ 自环节起算实耗 118 分钟（盒 100 分钟，**超盒 18 分钟**）——超盒如实记账，门禁未缩、判据未放宽、未动冻结面；基线终批从环节起算的第 73 分钟起跑。
- 本环流程外事件（逐字，不吞，也不写进报告正文——报告已渲染不可回改）：
  1. **服务端产物在本环中途消失**：`E:/IDEProjects/AI/FIST-Mbt/_build/js/debug/build/cmd/main/main.js` 被别处的 `moon test --target js` 清掉，实测 `python lfist.py get` 回 `[pfist] missing server build`；本地 `moon build --target js`（78 tasks，0 errors）+ `python scripts/patch_esm_main.py` 重建后 RPC 才通 ⇒ 盘上产物 mtime/大小 = ["2026-09-28T01:32:21+00:00", 2706589]。重建发生在叶收口**之前**，收口链一次通过（0 拒）；这条不是「环境打不到」的免责，是当场重测并修通了。
  2. **收口预检第一次在盘上就拒**（逐字）：`REFUSE — 证据件预检未过： ⏎   law8 .fist-loop-20260927/verify_r4_calllog_tally.json 仅 2978 字符 < 3000` —— 预检是 fail-closed 的，一个 RPC 都没发。处置不是把计划里的 3000 字符地板改小，而是给 call_log 件补一条真实测量（整条循环 19 个根任务逐根点名行数/被拒数），件从 2978 → 5947 字符，地板原样保留。
  3. **渲染之后重跑过一份渲染输入件**（`verify_r4_calllog_tally.json`）：报告 §八 的渲染前快照是 18 行，重跑后发单前复算 19 行，`total_call_log_rows` 同步漂；报告不可回改，所以两个数在这里按时刻分栏记账，而不是拿新数去确认旧数。
- 转结：R4-打磨 领「附录 C 的 4 条形差 + USAGE.md:406 那句『源未变会复用 .pyd』」的措辞面（本环不改冻结面与文档）；R4-推进 半径仍限「已声明未实现」；BUG-71/72/73 与挂账队列逐条带可复跑命令。
- 本条记录生成于 2026-09-28T01:38:03+00:00。
- 终账（收口后）：本环前缀 196 行 / 25 个任务，全库 4340 行，载体 {"laya": 1, "issue_up": 4, "call_log": 1}，Omega 三连 {"omega_spec_create": 25, "omega_spec_review": 25, "omega_result_verify": 25}，被拒 0 条。
- 根收口件逐字被拒（`close_r4_verify_root.out.json` 的 refused，一条不吞）：[]
  被拒原文（逐字）：

| 被拒原文（逐字） | 工具 | 次数 | 首个见证 |
| --- | --- | --- | --- |

<!-- R4-打磨 段由 polish_r4_progress.py 于 2026-09-28T02:46:30+00:00 重生成：第一版（3350 字符，已整段存于 .fist-loop-20260927/polish_r4_tmp/loop_progress_R4polish_v1.md）有两处口径错：① 时间盒实测 64 分钟「在盒内」却写成「超盒的部分是…」；② 转结里的形状分差写成 5 条，件里实测 4 条（`polish_r4_debt.json|shape_divergence_len`）。两处都是正文的派生措辞，不是判据；该段整段删除后由同一脚本重写，不是追加双发。 -->

### R4-打磨（根 `T0r90`，执行人 `cypy-polisher`）

- 结论：**已归档**。八条法全部独立复算；半径=措辞面/账面/测试面/骨架（产品 0 项 / 冻结 0 项 / tests 1 项 / docs 2 项，判据件 39 个）。
- 法①文档：`docs/USAGE.md` 实测第 [414] 行改写，sha `0400fdca1a0fd284`→`b8c04986f97f9fdf`，差分 2 行；三格实测 [false, true, true]。
- 法②附录 C：交人工栏 [1, 4, 5, 6]，我方补注 4 行 2635 B；冻结面 37 个 sha 相等 True、注入 canary 被抓 True。
- 法③账面：新增 8 行 / 删除 0 行，卡数 73→73，合法 task_id 65→65；8 张缺号卡反查命中 0 张 ⇒ 措辞「未派单」交人工。
- 法④骨架：`loop_kit.py`（API 8 个），行为不变 4 行覆盖 ["verify_r4_baselines.json", "fix_r4_baselines.json", "advance_r3_baselines.json"]，复制集合相同 True、双 canary {"junk_zero": [0, 0, 0], "good_1976": 1976}；形状分差 4 条与留债 {"def check(": 23, "passed|failed|errors?": 3, "Total:": 5, "rglob": 15} 点名未修。
- 法⑤永久锁：`tests/test_loop_20260927_polish_r4.py` 工作区 20 passed / 修前码 15 failed（红 15 条，含 1 条文档面）；两档 sha `ff9e8821cb22` ≠ `27a3408faad2`，收集 1976=1956+20。
- 法⑥结构债：56 文件过 3000 行红线，越线 4 个，type_checker 3207 行/141 方法，`__result__` 2/2；挂账 3 条、执行不可逆 0 条、碰过产品文件 0 个、改名 0 个。
- 三套体系：pytest 1976 通过 / 0 失败 / 0 错误（地板 1956）、收集 1976（地板 1956+20）、自研 {"Total": 47, "Passed": 47, "Failed": 0, "Skipped": 0}、e2e {"PASS": 25, "FAIL": 0, "RUNFAIL": 0, "WARN": 0}；HEAD `17d68b4`、暂存 0 行、脏行 171、冻结 43 个 sha 未变；三套同刻为绿 True。
- 驱动面：本轮亲笔 15 个脚本，硬错 0、软账 0（基线 0）。
- 自证与门禁：133/149 道在渲染前解出，自引用延后 16 道，占位 102 个（坏 0 个、空值无佐证 0 个），needle 严口径违例 0 条，过期未披露 0 条，§十 实测 19 条（声明 19）；不动点 True，嵌入 {"gates_pass": 133, "gates_total": 149, "placeholders_total": 102, "stale_artifacts_len": 0, "at_utc": "2026-09-28T02:44:01+00:00"} vs 实测 {"gates_pass": 133, "gates_total": 149, "placeholders_total": 102, "stale_artifacts_len": 0}。
- 报告：`memory/reviews/20260928.10.35.00.md`（40843 B，sha `97d48afe9cb2486672c75945aa0fa61a5f0c3f5440e2429b55e1a709217ebdad`），渲染 1 次、被拒重试 0 次、门禁表 149 行全绿 149、渲染后 §十 {"declared": 19, "actual": 19}、缺法条标题 0 个。
- 收口：叶 16/16、失败 0，根状态 `已归档`；发单前 call_log 本环前缀 18 行、终账 196 行 / 25 个任务，被拒 0 条（逐字见下）。
- 时间盒：环节起于 2026-09-28T01:41:16+00:00，本条记录生成于 2026-09-28T02:46:29+00:00，实耗 65 分钟（盒 100 分钟，在盒内）——并发重跑浪费的那段墙钟已记在披露 1；门禁未缩、判据未放宽、冻结面未动。
- 本环流程外事件（逐字，不吞，也不写进报告正文——报告已渲染不可回改）：
  1. **同一条三套体系批被我起了两遍，而且并发**：第一批起跑 `2026-09-28T01:55:03+00:00`（pytest 1976 / 收集 1976 / 绿 True），第二批起跑 `2026-09-28T02:13:52+00:00`（pytest 1976 / 收集 1976）。起因是第一批起跑后我又重写了测试文件（测量面没冻结），发现没落件时还没查进程表就起了第二批。两批数字互相同意，所以判定数可用；**流程是错的**，已写进报告 §十 3 与下面的转结流程债。
  2. **needle 口径当场升级**：环节计划里 8 个 needle 键名盘上不存在、2 个只是子串假命中（`control` 撞文件名 `SYNTAX/15-control-flow.md`、`queue` 撞 `queue_frozen_edit` 前缀），共改 11 处，逐对 (法, from, to)=[[1, "usage_fix", "diff_changed_lines"], [3, "appended", "append_only_diff"], [3, "removed_lines", "removed_samples"], [4, "dedup", "kit_apis"], [4, "rerun", "equivalence"], [5, "added", "new_test_file"], [5, "mutation_bearing", "lane_prefix_code"], [6, "not_executed", "adjudication_queue"], [6, "measure", "files_measured"], [1, "control", "pyd_reused_between_calls"], [2, "queue", "queue_frozen_edit"]]，规则改成「needle 必须是被引件里的真键名」并配 canary {"substring_rule_would_pass_control": true, "strict_rule_rejects_control": true, "control_hit_is_a_filename_inside_frozen_sha": true}。文件、min_chars 与「逐字含键」的强度未动。
  3. **服务端产物状态**：`main.js` mtime/大小=["2026-09-28T01:39:39+00:00", 2740423]——本环收口链开跑前实测在场（上一环被别处的 `moon test` 清掉过一次，已重建，不是「环境打不到」的免责）。
- 转结：R4-推进 领「§十一 的 6 项裁决 + 8 张未派单卡 + 4 条形状分差」，不得引用旧行号 406；R5 打磨领四类骨架留债；流程债两条（起后台批前先查同项目是否已有批在跑；基线起跑后冻结被测量面）。
- 本条记录生成于 2026-09-28T02:46:29+00:00。
- 收口被拒原文：无（终账 `refused=0`，按前缀数出来的，不是按回忆）。

### R4-推进（根 `T0r93`，执行人 `cypy-advancer`）

- 结论：**已归档**。八条法全部独立复算；半径=名称面补口（产品 2 档分析器 / 冻结 0 项 / tests 2 项 / docs 0 项，判据件 35 个）。
- 法①②名称面：`Never` 5 个夹具两棵树同批跑，改前 rc [1, 1, 1, 1, 1]→改后 [0, 0, 0, 1, 1]；`["repr", "open", "iter"]` 三个「文档在用、名称表缺席」的内建名补齐，未放行的 6 个 ["chr", "hex", "pow", "round", "divmod", "bytes"] 在冻结语料里 0 处调用点、两态都仍被拒；产物签名 `def fatal_error(message) -> NoReturn:`（codegen 一行没动，走既有 `Never→NoReturn` 映射）。
- 法②的后果件：放行 `open` 让 `test_defer_statement` 从空过变成真跑——改前 success=False（守卫为假整块跳过）、改后 success=True 而 try=False/finally=False；4 档 defer 形状 [["single_defer", true, 0, 1], ["two_defers_lifo", true, 0, 2], ["defer_before_return", false, 1, 1], ["defer_two_exits", false, 2, 1]]，钉住的多出口形状（2 出口只发 1 次清理）入账未修，其余 7 处同款守卫同账。
- 法③量表与入账：12 条复合赋值 + 10 条表达式 + 2 个其他形状，静默产错 ["^="]、响亮拒绝 5 条、挂账 8 条；真入账 4 张 ["BUG-74", "BUG-75", "BUG-76", "BUG-77"]（账本最大号 75→77，sqlite bug 任务 71→73）。
- 法④永久锁：`tests/test_loop_20260927_advance_r4.py` 26 条（条数由 plan 反解 {"name_face_probes": 14, "doc_worked_example": 1, "pinned_card_locks": 4, "doc_citation_locks": 3, "defer_shape_locks": 4}），工作区 26 通过/0 失败、修前码 18 通过/8 失败，红名单 8 条与 plan 逐字相等；两棵树身份 `cbac2bfb44c7` ≠ `ff9e8821cb22`，收集 2002=1976+26。
- 法⑤⑥产物与语料：77 档两态转译剔除时间戳行后逐字相同 77 档、无理解释差异 0 档；语料 77 档扫描，新增红 0 档、变少 0 档，见证夹具 2 支。
- 法⑦判据体系：pytest 2002 通过/0 失败/0 错误（`2002 passed in 519.23s (0:08:39)`）、收集 2002、自研 {"Total": 47, "Passed": 47, "Failed": 0, "Skipped": 0}、e2e {"PASS": 25, "FAIL": 0, "RUNFAIL": 0, "WARN": 0}；地板取上环实测件 polish_r4_baselines.json 实测 + 本环新增锁数；canary 7/7 格为真 {"three_systems_green": true, "floors_came_from_artifact": true, "frozen_face_count_matches_previous": true, "radius_is_exactly_two_product_files": true, "frozen_predicate_flags_a_fresh_row": true, "frozen_predicate_explains_a_stale_row": true, "faces_measured_not_declared": true}；驱动件亲笔 20 个、硬错 0、软账 0（基线 0）、生成锁件超长行 18（上环 18）。
- 法⑧不可逆动作面：毁灭型工具 []、别人号段 archive []、产品面删除/改名 0 条、本环新增 0 条，检测器 canary {"two_negative_controls_caught": true, "own_prefix_not_flagged": true, "real_run_clean": true}。
- 自证与门禁：109/112 道渲染前解出、自引用延后 3 道、渲染后复数 112/112 全绿；占位 141 个（坏 0、空值无佐证 0），needle 严口径违例 0 条、过期未披露 0 条、§十 实测 24 条（声明 24）、不动点 True（嵌入 {"gates_pass": 109, "gates_total": 112, "placeholders_total": 141, "stale_artifacts_len": 0, "at_utc": "2026-09-28T05:25:45+00:00"}）。
- 收口：叶 16/16、失败 0，根 `已归档`（上卷前 `待验收`）；call_log 本环前缀 发单前 18 行 → 终账 195 行 / 25 个任务（全库 4747 行），omega 三连 {"omega_spec_create": 25, "omega_spec_review": 25, "omega_result_verify": 25}。
- 时间盒：环节起于 2026-09-28T03:00:00+00:00，本条生成于 2026-09-28T05:33:15+00:00，实耗 153 分钟（盒 100 分钟，超盒）——超出的是三套体系跑了两遍（其中第一遍是被拒的坏口径 + 一条被激活的既有测试）和驱动件软账清零后的补跑；门禁未缩、判据未放宽、冻结面未动、半径未外溢。
- 本环流程外事件（逐字，不吞；报告正文渲染于 `2026-09-28T05:26:20+00:00` 之后一个字都没再动，sha `95294140a79e…` 由见证件与本轮复算双向核对）：
  1. **三套体系批跑了两遍，但不是并发**：第一批留档 `baselines_r4_0345.log`（拒 4 条、pytest 过/红/错=[1995, 1, 0]、收集 1996；首条被拒原文「canary 四格必须同时成立: got=[4, [False, True, True, True]] want=[4, [True, True, True, True]]（{"three_systems_green": false, "f」），第二遍 `2026-09-28T04:59:48+00:00`→`2026-09-28T05:14:14+00:00` 才是承重的那一份。第一批里有两条是**判据自己坏了**（porcelain 恒空口径、半径拿绝对路径比相对名单——当时数出来的就是 ["E:/IDEProjects/AI/Cypy/cypyc/analyzer/scope_analyzer.py", "E:/IDEProjects/AI/Cypy/cypyc/analyzer/type_checker.py"]），两条是被激活的既有测试（defer）⇒ 上一版报告里「同一条批并发起跑」那条失效在本环不成立，我按事实改成「两遍串行，第一遍被拒」。
  2. **计划文件曾是非法 JSON，躺了 90 多分钟**：`spec_r4_advance.json` 的 `needle_verification.why` 被我手补成 Python 式相邻字符串续行——合法 Python、非法 JSON，直到渲染前 `report_spec` 重新 parse 才炸。现在自证件里有「每份 JSON 判据件都能 parse」+「相邻字符串违例必红 / 合法 JSON 不误抓」的门与两格 canary（本轮自证条数 30）。修法只并那一个值，`laws`/`fingerprint` 逐字节未变（改前/改后切片比对 True/True）。
  3. **四个判据件改完没立刻重跑**：`advance_r4_never/scope_face/sweep/irreversible` 的脚本在 03:48 被改过，件却是 03:14–03:45 产的 ⇒ 直到 05:19 自证件把「脚本比件新且未披露」判成红才补跑（现件时间 2026-09-28T05:21:34+00:00 / 2026-09-28T05:21:43+00:00 / 2026-09-28T05:22:50+00:00 / 2026-09-28T05:22:50+00:00）。**这条进不了报告 §十**（正文已渲染），所以记在这里并转结流程债：改完判据脚本必须立刻重跑它的件，别指望渲染前的复算兜底。
  4. **指挥官裁决落地的唯一一处既有测试改动**：`tests/test_codegen_verification.py` 的 `test_defer_statement` 按声明面语义改期望并去掉 `if result.success` 守卫；其余 7 处同款守卫与 defer 异常路径安全入账未修（BUG-76 / BUG-77，见报告 §三·B、§四）。
  5. **服务端产物在场**：`cli.js` mtime/大小=["2026-09-28T03:31:07+00:00", 2779308]——收口链开跑前实测，不是「环境打不到」的免责（上一环它被别处的构建清掉过一次）。
  6. **lint 清零带来的重跑**：驱动件软账 23→0 之后 `gen_locks` 的 mtime 晚于它的 plan 件，按链补跑 `gen_locks → locks`；生成的锁文件两棵树 sha 相同 `67ba7df1bd6f`=`67ba7df1bd6f`，所以 §七 的 2002/2002 仍对同一批字节负责。
- 转结 R5：修复环领 4 张新卡 ["BUG-74", "BUG-75", "BUG-76", "BUG-77"]（含 7 处同款空过守卫与 defer 异常路径安全那条未声明语义）、`^=` 静默产错、`^`/`~` 与构建块共用词位的消歧裁决；推进环领 §十一 与 8 条半径外形状的挂账去向。流程债三条：改完判据脚本立刻重跑它的件；手补 JSON 后必须让读它的那条路跑一遍；起全量批之前先确认测量面已冻结。
- 本条**重生成过一次**：首版有两处反解缺陷——把 JSON 数组按 `^  "` 行数当成「拒 18 条」（真值是 4 条拒），以及把 `pinned_card_ids` 的 values 当卡号清单（出现重复的 BUG-75 并漏掉 BUG-77）。两处都改在驱动件里，正身以本条为准；首次写入与本条相隔 90 秒，其间没有第三方读过这份台账。
- 本条记录生成于 2026-09-28T05:33:15+00:00。
- 收口被拒原文：无（终账 `refused=0`，按前缀数出来的；根上无 `[omega:required]` 的既定语义本轮零次触发——`refusals_md` 55 B）。

### R5-寻虫（根 `T0r96`，执行人 `cypy-hunter`）

- 结论：**已归档**。八条法独立复算；门禁 116/116 全绿，报告渲染 2 次、被拒重试 0 次。
- 法①观察面：6 带 / 25 格，变异通道翻转归属 {"declared_sig": 4, "legacy_args": 2}，按族 3 族；白建通道点名 ["callback_param"]；盲区 0 格；本层候选 0 条（R4-修复 已改掉那四个根因，零候选由翻转证明，不是「没报错」）。
- 法②声明面：18 条主张现读原文 + 当场重测 ⇒ 陈旧 8 / 真实缺口 3 / 按设计撤回 1 / 未测或仍成立 2；规模红线 {"parser": 3444, "cython_generator": 3108, "type_checker": 2865, "threshold": 3000}；hook 未列选项 6 个。
- 法③生成面：7 条全部成对确诊 ["G01", "G02", "G03", "G04", "G05", "G07", "G06"]；canary {"wrong_expectation_cannot_confirm": true, "control_direction_is_declared_per_case": true}；残渣复测 []。
- 法④入口面：7 条确诊 ["H01", "H03", "H04", "H05", "H06", "H07"]，未确认 ["H02"]（对照两态同观察 ⇒ 不占号）；canary {"pos_and_ctl_expectations_are_opposite_per_case": true, "flipping_one_expectation_would_change_verdict": true}。
- 法⑤自证：needle 24/24 条全部真键名（[{"file": ".fist-loop-20260927/hunt_r5_baselines.json", "prefix": "row", "substring_present": true, "is_real_key": false}] canary 抓到前缀假命中）；入账件逐卡现场在账反解 13/13 命中。
- 法⑥入账：账本 90→90，bugs 任务 86→86，新单 BUG-78..BUG-90（号由「账本最大值 − 卡数 + 1」反解，不是手打）；幂等复扫 duplicates 13 条（重跑一条不重开）。
- 法⑦三套体系：pytest 2002 通过 / 0 失败 / rc=0，收集 2002，套件字段 {"Total": 47, "Passed": 47, "Failed": 0, "Skipped": 0}，e2e {"PASS": 25, "FAIL": 0, "UNREG/RUNFAIL": 0, "WARN": 0}；地板反解自 {"pytest": 2002, "collect": 2002, "suite": 47, "e2e_pass": 25}（来源 advance_r4_baselines.json:{"pytest": 2002, "collect": 2002, "suite": 47, "e2e_pass": 25}）；HEAD `17d68b4`、暂存 0、脏行 175、半径禁改面 0 / 允许面 250。
- 法⑧驱动面：亲笔 16 个脚本，硬错 0、软账 0（上一环基线 0）；行长口径 100；canary {"bad_caught": 1, "clean_false_positive": 0}。
- 收口：叶 16/16、失败 0，根 `已归档`；call_log 本环号段 146 行 / 17 个任务（环标签档 28 行），被拒 0 条。
- 报告：`memory/reviews/20260928.15.10.00.md`（36069 B，sha `85933483343615b2b0df27bd5addb8af8b0224549ce2ff68dd5f49fd70a28a23`），§八 声明/实数 {"declared": 16, "actual": 16}，缺法条标题 0 个。
- 自证与门禁预跑：渲染前 116/116 道解出，红 0 道，恒真门 0 道，needle 不合格 0 条，占位 76 个（未解析 0 个、空值无佐证 0 个），陈旧未披露 0 件。
- 时间盒：起点 2026-09-28T06:15:37+00:00（取本环 17 个亲笔驱动的最早 mtime），本条记录生成于 2026-09-28T07:59:44+00:00，实耗 104 分钟（盒 100 分钟，超盒）——门禁未缩、判据未放宽、冻结面未动。
- 本环流程外事件（逐字，不吞）：
  1. **13 条 report_bug 全被服务端拒**：我给卡表用的是内部口径 P0/P1/P2，服务端闭集是
     `critical/high/medium/low`。回执代表原文（逐字）：`CLI_build_failure_reason_message_swallowed：入账后账本搜不到这条 summary（回执 {"__error__": {"code": -32000, "message": "report_bug: 非法 severity=P2（合法值：critical/high/medium/low；缺省 medium。BUG-88：闭集必须等于抬头文法）"}}）`。账本零写入（sqlite 任务数与账本最大号都没动），闭集校验已前移为发单前的预检并配 P9 canary。
  2. **入账件的三向对齐改过一次**：原用「跑前后计数差」⇒ 重跑差为 0 就恒红；改成逐卡在账反解（`per_key_on_disk` 13 条、账本 hits≥1 且 bugs 树恰好 1 行）。本件当前是**二次扫描**状态：实开 0 条、已在账 13 条。
  3. **`tmp_left` 的语义错过一次**：首版采在 `shutil.rmtree(..., ignore_errors=True)` 之前，既永远非空又掩盖了清理静默失败（首跑实测留 21 个目录）。现在先清理（带重试）再采样、非空即拒。
  4. **全量基线被我起了两遍**：第一遍起跑后 `tasklist` 查不到 python.exe，我据此判它已死并重跑；随后第一遍回来说「completed exit 0」——它其实一直活着，我的判活方式错了（管道里 `tail` 吞了中间输出，日志 0 字节不等于没在跑）。第二遍起跑时第一遍已收尾，两遍数字互相同意，测量面未被并发改动；**流程仍是错的**，已记进 §八 12。
  5. **D11 的立单原文已经不成立**：`result.output_files` 在上一环修法①里被改掉，自证门「每行立单原文都在盘上」如实拒了那一条；改成现读 `result.pyd_paths` 并用 `dataclasses.fields()` 判存在后，本条翻成 `doc-still-true`（等于独立复验了上一环的修法）。
  6. **改名脚本自噬一次**：`str.replace` 把 `now_iso()` 的定义体也换成了 `return now_iso()`（自递归），`py_compile` 过、flake8 的 F401 才抓住 ⇒ 已改成 tokenize 级替换并逐处计数。
  7. 时间盒实耗 104 分钟：起点不是手写，是取本环 8 条法 + 亲笔驱动 mtime 的最小值；超出盒的那部分是两遍全量批与电池并发的墙钟，判据没有为此放宽。（当前 call_log 本环号段 146 行 / 环标签档 28 行）
  8. 二次扫描的 refuse 栏现状（逐字，若为空表示这一栏本环没有残留）：[]
  9. 渲染见证件（按序号，存在性不冒充次数）：
     - seq=1 sha=a4d80a653c369303… 34708 B／门禁 109 道／2026-09-28T07:35:12+00:00／note（逐字）：首渲（记录器 hunt_r5_render_witness.py 是事后补的；本条数值取自补记前一份 hunt_r5_render_order.json 的 report_sha256/report_bytes 实测值，不是回忆）
     - seq=2 sha=85933483343615b2… 36069 B／门禁 116 道／2026-09-28T07:56:55+00:00／note（逐字）：更正后重渲：首渲 §八 15 引用了当时不存在的门禁号 ⑪-10/⑪-11/⑪-13/⑪-14；补成 ⑪-10…⑪-16 七道真门后重渲，同时把『渲染次数』从文件存在性改成按记录数

- 转结：R5-修复 领 BUG-78..BUG-90 共 13 张新单 + 账本现数的 22 张未闭环旧单（[34, 36, 37, 40, 41, 43, 49, 50, 52, 53, 54, 65, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77]，判据=该号段正文无 FIXED 标记） + §九 的 3 条 real-gap 裁决；R5-验证 复测本轮四张电池的判据是否仍然承重；流程债三条（全量批不与电池并发、脚本替换后必须实跑一次而不是只 compile、needle 只按子串校等于没校）。
- 本条记录生成于 2026-09-28T07:59:44+00:00。
- 收口被拒原文：无（终账按前缀数出来 refused=0，不是按回忆）。
