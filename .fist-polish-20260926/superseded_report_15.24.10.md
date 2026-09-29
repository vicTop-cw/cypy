# Cypy 打磨周报告（issue_up 开）— 2026-09-26 15:24:10 +0800

## 〇、门禁自评（五条，逐条给判据）

| 门禁 | 结论 | 判据 |
|---|---|---|
| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | 不绿：仍有 1 条红（================= 1 failed, 1813 passed in 338.07s (0:05:38) ==================），系上一轮 subtype 在途产物，见 §六.2；用例 1792 → 1814 | `.fist-polish-20260926/pytest_final_sweep4.log` 末行原文：`================= 1 failed, 1813 passed in 338.07s (0:05:38) ==================` |
| ② 每单修复 ≥1 条锁死回归 | 绿（11/11 单已 verify，每单各配 1..2 条，共 22 条） | §二表 + `python -m pytest tests/test_polish_20260926.py -q` → 22 passed |
| ③ 标记盘点收敛、新增为零 | 绿：裸 except 2→0、吞异常 20→3、宽 except 46→45；TODO/FIXME/HACK/XXX/type:ignore 恒为 0 | `markers_baseline.json` vs `markers_after_sweep3.json`（同脚本同范围，与 `markers_after_sweep3b.json` 两次复扫计数完全一致） |
| ④ 确诊缺陷 100% 入账 | 绿（11/11，无口头发现未入账；误报 2 条按红线不刷账） | `memory/bugs.md`（`## BUG-1..BUG-11`）+ `bug_list` count=11 + `intake_map.json`/`intake_map2.json`/`intake_map3.json` |
| ⑤ 报告落 `memory/reviews/yyyyMMdd.HH.mm.ss.md` | 绿 | 本文件 `memory/reviews/20260926.15.24.10.md` |

- 主题：Cypy 打磨周——编译器与桥接库缺陷清偿（三路排查入账 → 逐单修复闭环 → 基线只升不降）

- 命名空间：`cypy-polish-20260926`（未使用 `default`）
- 任务库落点口径：FIST-Mbt server 进程 cwd 固定为 `E:\IDEProjects\AI\Cypy`，因此
  `fist-mbt.db` 落在 Cypy 根、`project_dir="."` 恒解析到 `Cypy\memory\bugs.md`。
  隔离实测：新库建立时任务数 0，现网库（`E:/IDEProjects/AI/FIST-Mbt/fist-mbt.db`）29 个
  namespace 全程未被本轮回写；`cron-cypy` 流水线与 `Gen_Prompts/` 未读未写。
  任务隔离靠 namespace 达成，不靠目录（目录方案被 `report_bug` 的路径防护否掉，见 §五）。
- 扫描范围：`cypyc/`、`cypy_bridge/`、`cypy_hook/`；`tests/` 只加回归；`examples/`、
  `dist/`、`output/` 未动。零 `git add/commit/push`，上一轮 60+ 未提交改动原样保留。

## 一、三路发现

| 通道 | 候选 | 研判 |
|---|---|---|
| ① 标记盘点 | 56 文件 / 29997 行：裸 except 2、吞异常 20、宽 except 46、subprocess 3；TODO/FIXME/HACK/XXX/type:ignore 全为 0 | 逐条读码定性，第一遍确诊 5 条；第二遍把剩下的吞异常站点逐条读完再确诊 2 条（BUG-9/BUG-10，其余为兜底/防御性或宽 except 正常用法） |
| ② 测试实跑暴露 | 基线 1791 passed / 1 failed（收集 1792，509.24s (0:08:29)）；另跑 `python scripts/run_tests.py`（`test_suite/` 自研套件）终态 Total 47 / Passed 47 / Failed 0 / Skipped 0，79.90s | 1 条红：`examples/subtype_units.cypy` 缺 golden —— 属上一轮 subtype 在途工作，非本轮产品缺陷，见 §六；两套体系同绿（见 §三） |
| ③ 亲自读码审查 | 按 codegen→analyzer→parser/incremental→bridge/hook 通读三包；收口前对 parser 面与 incremental 面各复查一遍；第三遍把上一轮在途未验收的 subtype/analyzer 面与 project 装配面重读一遍 | 确诊 4 条（BUG-2/BUG-7 + 复查时补的 BUG-8 + 第三遍补的 BUG-11）+ 误报 2 条 |

确诊 11 条 → 全部 `report_bug(publish_task=true)` 入账；
误报 2 条不刷账：`cypyc/cli.py:36`（sys.stdout.reconfigure 是启动期防御）、
`cypy_bridge/pointer.py:142/412`（多策略取址的刻意 fallthrough，非吞错）；
待定 1 条（subtype golden，转结）。审查推理零付费 API。

## 二、修复闭环表（bug id ↔ 任务 id ↔ 回归测试）

| bug | 缺陷 | 自动发布任务 | 改动文件 | 锁死回归 | 账本 |
|---|---|---|---|---|---|
| BUG-1 | clear_cache 把 .pyd 删除失败当成功 | T0r6 | `cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug1_clear_cache_does_not_claim_success_when_remove_fails` | verify=已完成 |
| BUG-2 | build_ext 子进程无 timeout | T0r7 | `cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug2_bridge_build_subprocess_run_passes_timeout (+timeout 常量共用一条)` | verify=已完成 |
| BUG-3 | 增量重解析异常被吞，陈旧 AST 继续参与编译 | T0r8 | `cypyc/project/project_compiler.py` | `tests/test_polish_20260926.py::test_bug3_reparse_failure_is_reported_not_swallowed` | verify=已完成 |
| BUG-4 | 五个 transformer 把递归收集包进静默 try | T0r9 | `cypyc/transformer/{defer,enum,generic,struct,trait}_transformer.py` | `tests/test_polish_20260926.py::test_bug4_transformer_recursion_is_outside_broad_try ×5` | verify=已完成 |
| BUG-5 | 热重载状态快照/回滚吞掉 getattr/setattr 失败 | T0r10 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug5_state_snapshot / test_bug5_state_restore` | verify=已完成 |
| BUG-6 | 读不到首行即判『不是 Cypy 文件』（含 BOM 误判） | T0r11 | `cypyc/incremental/file_monitor.py` | `tests/test_polish_20260926.py::test_bug6_cypy_file_with_bom / test_bug6_unreadable_cypy_candidate_warns` | verify=已完成 |
| BUG-7 | manifest 损坏与无 manifest 不可区分 | T0r12 | `cypy_hook/hook.py, cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug7_corrupt_manifest_warns / test_bug7_corrupt_bridge_manifest_warns` | verify=已完成 |
| BUG-8 | 宏重解析失败静默降级，整条语句从输出消失 | T0r13 | `cypyc/parser/macro_expander.py` | `tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported` | verify=已完成 |
| BUG-9 | HotReloadEngine 模块级状态快照/回滚仍静默（BUG-5 只修了代理那份） | T0r14 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug9_module_state_snapshot_warns / test_bug9_module_state_restore_warns` | verify=已完成 |
| BUG-10 | 热重载的依赖分析与增量缓存更新把解析失败整段吞掉（:332/:457） | T0r15 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug10_dependency_analysis_parse_failure_warns / test_bug10_cache_update_parse_failure_warns` | verify=已完成 |
| BUG-11 | 项目模式 type_check_module 丢掉 ScopeAnalyzer 已报出的诊断（两入口相反裁决） | T0r16 | `cypyc/project/project_compiler.py` | `tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors / test_bug11_type_level_name_collision_is_reported` | verify=已完成 |

回归文件：`tests/test_polish_20260926.py`，本轮收集 22 条用例（每单 ≥1 条）。
RED 证据（第一遍 8 单）：逐单交付物里的原话，例如 BUG-1 单面写着「RED：修复前该用例断言『.pyd 仍在但条目被删』失败（8 failed 之一），GREEN：现 15 passed。」；
该遍没单独落 RED 日志文件（只有逐单文案，见 `close_fixes.out.json` 的 `*:execute`），
第二遍改前
`pytest tests/test_polish_20260926.py -q -k "bug9 or bug10"` → `4 failed, 16 deselected in 0.29s`
（`.fist-polish-20260926/pytest_second_sweep_red.log`）。第三遍改前
`pytest tests/test_polish_20260926.py -q -k bug11` → `2 failed, 20 deselected in 0.27s`
（`.fist-polish-20260926/pytest_third_sweep_red.log`）。
GREEN 证据：修复后 `python -m pytest tests/test_polish_20260926.py -q` → `22 passed`，
全量终态见 §三。
BUG-8 是收口前复查 parser 面时补入的（上一轮审计明确留开的「两处静默降级」之一，
本次按「口头发现必须入账」处理）：修复前 `pytest tests/test_polish_20260926.py -q -k bug8`
→ `1 failed`（`capsys.readouterr().err == ''`，即整条宏语句消失而零告警）；
修复后 → 该条 pass、同文件 22 passed，且 `tests/test_macro_expansion.py`
23 passed 未回退（降级返回值不变，只补告警）。
判据开关对照（BUG-4）：旧形 synthetic 命中 `['_collect_defers']`，新形与实文件命中 `[]`——
该单最初 5 条全绿是判据不bind（把 except 体误当静默区），改成「递归是否在静默 try 内」后才真正转红再转绿。
判据加固（BUG-10，第二轮全量时抓到）：最初两条 BUG-10 用例靠 `monkeypatch` 把
`cypyc.parser.parser.Parser` 换成必抛异常的桩，单跑 22 passed，但**全量跑时该桩未被触发**
（`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns` 红，`err` 为空串），
属判据依赖 ambient import 身份的不牢靠写法。已改成用「源文件真的读不到」触发同一 except 站点，
并加一条自证断言 `compiler.calls == []`（若解析/读盘没走进该站点就直接判红，而不是假绿）。
加固后开关对照：把 `hot_reload.py` 里 `_analyze_module_dependencies`/`_compile_and_reload_module`
两处 `_warn_parse(...)` 退回 `pass` → `2 failed, 18 deselected in 0.26s`
（`.fist-polish-20260926/pytest_switchoff_bug10.log`），恢复后 → 该文件 22 passed；
产品代码字节级复原（`cypyc/incremental/hot_reload.py` md5 `d38409d96f12791a85e8a67ccc3aee36`）。全量里为何不生效未继续深挖
（`test_hook.py`、`test_hot_reload.py`、`test_macro_expansion.py` 两两组合均复现不出），
新判据不再依赖该身份，污染源无法再让它假绿。
第三遍（BUG-11，收口后回读在途面时补入）：`cypyc/project/project_compiler.py` 的
`type_check_module()` 跑了 `ScopeAnalyzer().analyze(ast)` 却从不读它的 `errors`，只上送
TypeChecker 那一份——而单文件管线 `cypy_hook/hook.py:250-257` 两份都读，于是**同一份源码在两个入口
拿到相反裁决**。一次性探针 `.fist-polish-20260926/probe_scope_drop.py` 实测三条 DROPPED
（重名 `def f`、`subtype Money` 撞 `class Money`、`type Thing` 撞 `constraint Thing`，
均为 `ok=True errors=[]`），对照组 `uses_undefined` 不丢（TypeChecker 自己报同一句），
说明丢的正是作用域独有的那一类。修法只加两行（把 `scope_analyzer.errors` 接进去 + 按序去重），
不新增判定规则、不新增诊断文案。开关对照：把这两行退回改前形态 → `2 failed, 20 deselected in 0.27s`
（`.fist-polish-20260926/pytest_switchoff_bug11.log`，失败用例名与 RED 首跑逐条相同），
恢复后 → 该文件 22 passed，产品文件 md5 `167b194f99634b280cc3096237bcddc7`。
调用面不止测库函数：`.fist-polish-20260926/probe_cli_check_e2e.py` 真起
`python -m cypyc build <临时项目> --check-only -o <临时输出>` → **exit 1** 且 stdout 打印
`Name 'f' is already declared in this scope (line 5, col 5)`（原始输出
`probe_cli_check_e2e.out`）——源文件与输出目录都在临时目录，仓库 `output/`、`dist/` 未被写。

## 三、基线前后对照

| 判据 | 基线 | 终态 |
|---|---|---|
| `python -m pytest tests/ -q` | 1791 passed / 1 failed / 收集 1792 | 1813 passed / 1 failed / 收集 1814 |
| 用例总数（≥1745 只增不减） | 1792 | 1814 |
| 末行原文 | `================= 1 failed, 1791 passed in 509.24s (0:08:29) ==================` | `================= 1 failed, 1813 passed in 338.07s (0:05:38) ==================` |
| `python scripts/run_tests.py`（`test_suite/` 自研套件） | 未取基线（见下注） | Total 47 / Passed 47 / Failed 0 / Skipped 0（79.90s，退出码 0） |

`test_suite/` 不是 pytest 收集面：`python -m pytest test_suite -q` → `no tests ran`（退出码 5，
套件文件命名为 `*_suite.py`，无 `test_*` 收集匹配），因此该体系须由 `scripts/run_tests.py` 驱动。
分套件终态：ParserSuite 18通过/0失败/0跳过、AnalyzerSuite 10通过/0失败/0跳过、CodegenSuite 9通过/0失败/0跳过、IntegrationSuite 10通过/0失败/0跳过。
两套体系**同绿**（pytest 1813 passed、自研套件 47/47 passed），
自研套件的 `test_suite/fixtures/compiler.py` 会 `from cypy_hook.hook import CypyHook`（本轮 BUG-7
改动文件），其 47 条全绿即证明该改动未打破第二套体系的调用面。
基线缺失说明：本轮只在修复后跑了该套件（判据为「同绿」而非「不回落」），未回退代码重测基线，
因此这一行只有终态数据，不写作前后对照。
终态复现说明：修完之后共跑过 5 次全量。BUG-1..8 落地后的两次计数完全一致
（`================= 1 failed, 1807 passed in 363.84s (0:06:03) ==================` / `================= 1 failed, 1807 passed in 401.65s (0:06:41) ==================`，只差耗时 363.84s (0:06:03) 与 401.65s (0:06:41)）；
第二遍（BUG-9/BUG-10）落地后一次 `pytest_final_sweep2.log` → `================= 2 failed, 1810 passed in 346.18s (0:05:46) ==================`，
多出的那条红是本轮**自己的**回归判据在全量下没绑上（见 §二「判据加固」），不是产品回退；
加固后 `pytest_final_sweep3.log` → `================= 1 failed, 1811 passed in 327.62s (0:05:27) ==================`；第三遍（BUG-11）落地后终态
`pytest_final_sweep4.log` → `================= 1 failed, 1813 passed in 338.07s (0:05:38) ==================`，
「唯一红 = subtype golden」这一不变量保持，且五次收集数与通过数只增不减
（1808、1808 → 1812 → 1812 → 1814）。
标记面同理：`markers_after_sweep3.json` 与 `markers_after_sweep3b.json` 两次独立复扫的
counts 字典逐项相等（脚本已在不等时 `sys.exit`）；`test_suite_after_sweep3.log` 与 BUG-8 之前的
`test_suite_final.log` 同为 47/47——BUG-9/BUG-10 只补 stderr 告警、
未改控制流，第二套自研体系（47 条、79.90s）因此无需重跑基线。

标记盘点收敛（同脚本 `.fist-polish-20260926/marker_scan.py`，同范围同口径）：

| 类别 | 基线 | 终态 | 结论 |
|---|---|---|---|
| TODO | 0 | 0 | 持平 |
| FIXME | 0 | 0 | 持平 |
| HACK | 0 | 0 | 持平 |
| XXX | 0 | 0 | 持平 |
| type_ignore | 0 | 0 | 持平 |
| bare_except | 2 | 0 | 收敛 |
| except_swallowed | 20 | 3 | 收敛 |
| broad_except | 46 | 45 | 收敛 |
| mutable_default_arg | 0 | 0 | 持平 |
| open_without_with | 0 | 0 | 持平 |
| subprocess_call | 3 | 3 | 持平 |

新增标记为零（TODO/FIXME/HACK/XXX/type:ignore 基线即 0，终态仍 0）。
判据口径自审：`mutable_default_arg` 只匹配 `def f(...= [] | {} | set())` 同一行的形态（`list()/dict()`
工厂与跨行签名不在口径内）、`open_without_with` 是同步行内 `open(` 且不含 `with`，两者的 0 是
「口径内为零」而非「绝对为零」；合成对照：`def f(a=[])` / `def g(cfg={})` 均命中前者，
`h=open(p).read()` 命中后者而 `with open(p) as f` 被正确排除。`bare_except`/`except_swallowed`/
`broad_except` 三条走 AST，不依赖行文本。

## 四、本轮改动文件（与既有未提交改动区分）

产品代码：`cypy_bridge/compiler.py`、`cypy_hook/hook.py`、`cypyc/project/project_compiler.py`、
`cypyc/incremental/hot_reload.py`、`cypyc/incremental/file_monitor.py`、
`cypyc/parser/macro_expander.py`、
`cypyc/transformer/{defer,enum,generic,struct,trait}_transformer.py`；
测试：`tests/test_polish_20260926.py`（新增）；
账本与本仓证据：`memory/bugs.md`（本轮新建）、`.fist-polish-20260926/*`、
`fist-mbt.db`（Cypy 根，本轮新建）。
以上文件的**其余**未提交改动均属上一轮，本轮未回滚、未合并、未提交。

## 五、FIST-Mbt 侧实测与上报

1. `report_bug` 的 `project_dir` 只收相对路径且按 server 进程 cwd 解析（BUG-5 契约在本轮复现：
   传绝对路径被 `bug_project_dir_ok` 拒；server cwd 落在 `.fist-polish-20260926/` 时会把账本写进
   任务库目录）。本轮采取「server cwd = Cypy 根」方案，`project_dir="."` 全程直写
   `Cypy\memory\bugs.md`，实测 `resolved_path=E:\IDEProjects\AI\Cypy`。
2. 缺陷入账返回 `bug_id` + 自动发布 `task_id`，本轮映射见 §二（BUG-1↔T0r6 / BUG-2↔T0r7 / BUG-3↔T0r8 / BUG-4↔T0r9 / BUG-5↔T0r10 / BUG-6↔T0r11 / BUG-7↔T0r12 / BUG-8↔T0r13 / BUG-9↔T0r14 / BUG-10↔T0r15 / BUG-11↔T0r16）。
3. 诊断期间产生的孤儿任务（T0r1：task not found: T0r1；T0r2：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r3：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r4：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r5：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]）——归档步骤见 §六，未把诊断噪声留作待办。
4. `pfist.py --batch` 首条 `report_bug` 报 `no response from report_bug within timeout`，
   而同一 payload 单发 0.2s 返回（BUG-4/BUG-5 探针复现）。客户端把「EOF/无匹配帧/超时」
   揉成同一条错误消息，无法区分；因此本轮改用带 `bug_list` 前置对账的幂等入账器
   `.fist-polish-20260926/intake.py`（重跑不重复写账）。该现象待 FIST-Mbt 侧复现，
   在其账本可用后按 §六 转结上报。
5. `report_bug(publish_task=true)` 自动发布的修复单落在 **namespace `bugs`、`parent_id=null`**
   （活证据：兄弟仓 `src/server/bugreport.mbt:264` 硬编码 `ns="bugs"`；运行面见
   `close_fixes.out.json` 里 `BUG-1:claim` 与 `BUG-8:claim` 的原始回复字段），即它们不是本轮
   `cypy-polish-20260926` 那棵树的孩子。因此「父任务自动上卷」只覆盖 `task_plan_deep` 生成的
   T0.1..T0.6；修复单必须在 §二表里逐单对账，不能靠根任务状态推断。这一点是本轮实测出的契约细节，
   FIST-Mbt 侧文档未写。
6. **对 FIST-Mbt 自身的 issue_up 已实际执行**（本轮不再只转结）：以 `cwd=E:\IDEProjects\AI\FIST-Mbt`
   起同一个 main.js、`project_dir="."`、`publish_task=false`，把它自己的 4 条实测缺陷
   写进它的账本 `E:/IDEProjects/AI/FIST-Mbt/memory/bugs.md`：
   **BUG-8**（修复单硬落 ns `bugs`、根上卷覆盖不到）、
   **BUG-9**（缺陷账本只写不销，无 bug 关闭 API → Cypy 侧 11 条全 OPEN 而 11 张单全「已完成」）、
   **BUG-10**（`archive` 走 complete 要求 `[待验收]`，停在 `[待领取]` 的孤儿单无合法废弃路径，
   原样报错 `非法迁移: complete 要求状态 [待验收]，当前是 [待领取]`）、
   **BUG-11**（`report_bug` 返回 `bug_id` 而 `bug_list` 同一行叫 `id`，按写侧字段名对账会静默取到 null）。
   隔离实测：`fist-mbt.db` 修改时间仍为 14:19:34（早于本轮写入），即**它的现网任务库零改动**，
   只追加 markdown 账本；逐条原始回复见 `.fist-polish-20260926/report_fist_findings.out.json`
   （`ledger_before=6 → ledger_after=11`，本轮 4 条上报的 id
   BUG-8..BUG-11 已在 `E:/IDEProjects/AI/FIST-Mbt/memory/bugs.md` 现有 11 个 `## BUG-n` 标题中逐条反查到），
   驱动脚本 `report_fist_findings.py`。
   两个口径细节：该脚本的 before/after 计的是 **distinct summary 数**（不是条目数）——它入账前该账本已有
   7 条标题、其中 2 条是本轮早期诊断留下的同 summary 探针（`## BUG-6` / `## BUG-7`
   「BUG-5 resolved_path check」），折叠后显示 6；这两条探针残留在**它的**账本里无法删除
   （正是 BUG-9 描述的「只写不销」），已如实留证而不伪装成干净收口。
7. BUG-11 不是纸面推演，是本轮自己踩到的坑：`intake.py` 的「已在账」分支按
   `row.get("bug_id")` 取值，重跑第 8 条时把之前 7 条已有单写成了
   `"bug_id": null`（`task_id` 仍对），报告渲染时以 `KeyError: None` 暴露。已两处收口：入账器改为
   `bug_id or id` 回退（重跑 `intake.py` → `mapping=8 failures=0 missing=0`，8 个真 id 全回来），
   且 `gen_report.py` 不再单信 mapping——§二表的 bug 编号一律用 `memory/bugs.md` 的
   `## BUG-n` + `- task_id:` 反查校验，对不上即 `sys.exit` 拒绝出报告（两份账互为约束）。

## 六、遗留与转结

1. **账本收尾过程中撞上一次外部重建**：写 FIST 账本期间，兄弟仓 `E:\IDEProjects\AI\FIST-Mbt\_build\js\...`
   被另一次 `moon build` 重建（node 进程 13:42 起，`_build/js/debug/build/` 一度为空），
   `close_fixes.py` 首次运行报 `[pfist] missing server build: ...main.js`。等 `main.js` 复现
   （13:48，2313919 字节）后重跑，结果：BUG-1..7 逐单 `claim→execute→submit→verify` 全部
   `已完成`，T0.1..T0.6 `已完成`，根 `T0` `已完成 → 已归档`（`archive` 需 `by="human_steward"`，
   以 polisher 身份调用被拒：`archive 仅限人类指挥官`）。逐条原始回复见 `close_fixes.out.json`。
   残留：入账探针留下的 4 条孤儿任务 T0r2..T0r5 无法归档——`archive` 走的是
   `complete`，要求状态 `[待验收]`，而它们停在 `[待领取]`（原样报错：
   `非法迁移: complete 要求状态 [待验收]，当前是 [待领取]`）。它们只存在于本轮隔离库
   `E:\IDEProjects\AI\Cypy\fist-mbt.db`，不影响现网；FIST-Mbt 侧「未开工任务无法废弃」这一点
   已按 §五.6 入账为其账本的 BUG-10（不再是转结）；§五.4 的批量无响应现象因缺可复现证据
   仍留作转结，未刷账。
   时间顺序如实记：BUG-8 是在根 `T0` 已归档之后才确诊补入的（收口前复查 parser 面），
   其修复单 `T0r13` 单独走完 claim→execute→submit→verify 到 `已完成`（原始回复见
   `close_fixes.out.json` 的 `BUG-8:*` 5 步），根任务不回退重开——因为修复单本就落在
   ns `bugs`（见 §五.5），根 `T0` 的最终状态仍是 `已归档`。
2. **subtype 的 golden 缺失**（`examples/subtype_units.cypy`）：终态唯一红条即 `FAILED tests/test_golden_anchor_probes.py::TestGoldenPairing::test_every_example_has_golden`，
   判据要求每个 example 都有已注册基准。属上一轮 T0r258.2.2 在途产物，本轮按
   「examples/ 不动、不改语义」不代其注册基准；转结回 R2 lane。
3. **吞异常站点已见底**：基线 20 处 → 终态 3 处，剩下的正是 §一
   判为误报的 3 处（`cypyc/cli.py:36`、`cypy_bridge/pointer.py:142` 与 `:412`），该类别无待穷尽面。
   **宽 except 仍有 45 处**：本轮只确诊其中会掩盖真实失败的若干处，其余（IO 兜底、
   可选依赖探测、`except Exception as e` 后已 print/写入 errors）按口径保留，是下一轮的盘点面。
4. **验收之后改判据，账面无处可写**（T0r15 / BUG-10，§二「判据加固」）：实测
   `execute T0r15` → `{"__error__": {"code": -32000, "message": "非法执行: 任务处于 [已完成]"}}`，即已完成的单不允许追加/更正交付物；本轮改用
   `heartbeat` 把加固说明挂进该单（原始回复见 `post_verify_amend.out.json` 的 `try:heartbeat`，
   状态仍 `已完成`）。这是 FIST-Mbt 的第二个「只写不销」面：能记 liveness，不能记 amended deliverable。
   未伪造「已完成」——单面交付文本确实停留在加固前那一版，读单者需结合本报告 §二。
5. **F2 subtype 子代理在 150 turn 处被截断**（`agent "F2-subtype": Reached the maximum turn limit`），
   其 `cypyc/analyzer`、`cypyc/codegen` 改动留在工作区未验收；本轮未触碰其语义，只在第三遍回读
   project 装配面时撞出 BUG-11（诊断丢弃，非 subtype 语义），R2 lane 仍需自行核账。
6. **第三遍（BUG-11）同样在根 `T0` 已归档之后补入**：其修复单 `T0r16`
   单独走完 claim→execute→submit→verify（原始回复见 `close_fixes3.out.json`），
   根任务不回退重开——原因与 §五.5/§六.1 相同：修复单本就落在 ns `bugs`。


## 七、执行记录

- 驱动脚本：`.fist-polish-20260926/{pfist,intake,intake2,intake3,marker_scan,gen_bugs,gen_bugs_add8,apply_fixes,close_fixes,close_fix8,close_fixes2,close_fixes3,report_fist_findings,post_verify_amend,probe_scope_drop,probe_cli_check_e2e,switchoff_bug11,gen_report}.py`
- 终态证据：`.fist-polish-20260926/{markers_after_sweep3,markers_after_sweep3b,intake_map,intake_map2,intake_map3,close_fixes.out,close_fixes2.out,close_fixes3.out,report_fist_findings.out,post_verify_amend.out}.json`、
  `.fist-polish-20260926/{pytest_baseline,pytest_final_sweep4,test_suite_after_sweep3,pytest_testsuite_final}.log`
  （`pytest_testsuite_final` 是 `pytest test_suite -q` 的 `collected 0 items / no tests ran`，即第二套体系不在 pytest 收集面的证据）
- RED / 开关对照证据：`{pytest_second_sweep_red,pytest_switchoff_bug10,pytest_third_sweep_red,pytest_switchoff_bug11}.log`
- 中间快照（留档对照，不作为终态引用）：`markers_after.json`、`markers_after_final.json`、
  `markers_after_recheck.json`、`markers_after_sweep2.json`、`markers_after_sweep2b.json`、
  `test_suite_final.log`、`test_suite_after_bug8.log`、`test_suite_after_sweep2.log`、
  `pytest_final.log`、`pytest_final_after_bug8.log`、`pytest_final_sweep2.log`、`pytest_final_sweep3.log`——
  取自各遍修复之间，计数与终态一致（吞异常 7→3、宽 except 45、套件 47/47），
  其中 `pytest_final_sweep2.log` 多出的那条红已在 §二/§六.4 交代
- 诊断账本快照（入账前被清空重建）：`.fist-polish-20260926/bugs_ledger_diagnostic_snapshot.md`
