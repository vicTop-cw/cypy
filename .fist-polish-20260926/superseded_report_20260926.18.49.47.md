# Cypy 打磨周报告（issue_up 开）— 2026-09-26 18:49:47 +0800

## 〇、门禁自评（五条，逐条给判据）

| 门禁 | 结论 | 判据 |
|---|---|---|
| ① `pytest tests/ -q` 全绿且用例数 ≥ 基线 1745 | 不绿：仍有 1 条红（================= 1 failed, 1815 passed in 1126.17s (0:18:46) =================）。该红条在本轮红线口径下不可清偿——三条出路都要动 `examples/` 或放宽判据，详见 §六.2，交指挥官裁决；用例 1792 → 1816 | `.fist-polish-20260926/pytest_final_sweep6.log` 末行原文：`================= 1 failed, 1815 passed in 1126.17s (0:18:46) =================`。终态红条只有 golden 那一条，BUG-13 的墙钟判据本轮没再翻面 |
| ② 每单修复 ≥1 条锁死回归 | 绿（已修的 12/12 单各配 1..2 条、共 24 条回归并 verify 到 已完成；第 13 单 BUG-13 是判据缺陷、入账未修，不占用本门禁） | §二表 + `python -m pytest tests/test_polish_20260926.py -q` → 24 passed；库里 12/13 张修复单逐行 `已完成`（唯一非已完成行就是 BUG-13，只读直查见 §五.9） |
| ③ 标记盘点收敛、新增为零 | 绿：裸 except 2→0、吞异常 20→3、宽 except 46→45；TODO/FIXME/HACK/XXX/type:ignore 恒为 0 | `markers_baseline.json` vs `markers_after_sweep4.json`（同脚本同范围，与 `markers_after_sweep4b.json` 两次复扫计数完全一致） |
| ④ 确诊缺陷 100% 入账 | 绿（13/13 入账，其中 12 单修完 verify、BUG-13 入账未修转结；无口头发现未入账；误报 4 条按红线不刷账） | `memory/bugs.md`（`## BUG-1..BUG-13`）+ `bug_list` count=13 + `intake_map.json`/`intake_map2.json`/`intake_map3.json`/`intake_map4.json`/`intake_map5.json` + `probe_ledger_final.json`（bugs.md 标题 ↔ 库内 task 行的配对核账）+ `annotate_bugs_fixed.out.json`（12/12 条已闭环条目各带一段追加式 `### FIXED(verify=已完成)`，BUG-13 无该段） |
| ⑤ 报告落 `memory/reviews/yyyyMMdd.HH.mm.ss.md` | 绿 | 本文件 `memory/reviews/20260926.18.49.47.md` |

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
| ② 测试实跑暴露 | 基线 1791 passed / 1 failed（收集 1792，509.24s (0:08:29)）；另跑 `python scripts/run_tests.py`（`test_suite/` 自研套件）终态 Total 47 / Passed 47 / Failed 0 / Skipped 0，656.80s | 1 条红：`examples/subtype_units.cypy` 缺 golden —— 属上一轮 subtype 在途工作，非本轮产品缺陷，见 §六；自研套件 47/47 全绿，pytest 面除该条红外 1815 passed（见 §三） |
| ②b 终态红条复测 | 全量复跑 `pytest_final_sweep6.log` 里 `TestDigestCost` **没再翻面**（红条回到 1 条），故按 sweep5 那条红定性；取证是三种堆各测一次：单跑该用例 / 整文件跑 / 灌 1.5M 循环对象 + `gc.freeze()`（`pytest_digestcost_ordering.log`、`meas_digest_cost.out.txt`、`meas_digest_gc.out.txt`） | 判据缺陷确诊 → BUG-13（CPU 时间恒 0.39–0.47s，墙钟 0.54→3.385s 随收集顺序翻面），产品侧判 [误报]：`ast_differ.py` 自 09-25 16:39 未改 |
| ③ 亲自读码审查 | 按 codegen→analyzer→parser/incremental→bridge/hook 通读三包；收口前对 parser 面与 incremental 面各复查一遍；第三遍把上一轮在途未验收的 subtype/analyzer 面与 project 装配面重读一遍；第四遍专读 bridge 面（GIL/线程/资源三类），并用 `.fist-polish-20260926/sweep4_classes.py` 的 AST 站点表把可疑处逐条复验 | 确诊 5 条（BUG-2/BUG-7 + 复查时补的 BUG-8 + 第三遍补的 BUG-11 + 第四遍补的 BUG-12）+ 误报 4 条 |

③ 里点名的六个聚焦类别不是「通读时扫了一眼」，而是各有一条机检扫描器与落盘产物
（`sweep4_classes.py` → `sweep4_classes.json`，实扫 56 文件 / 30093 行）：

| 扫描器 key | 类别 | 命中 | 处置 |
|---|---|---|---|
| `A_mutable_default` | 可变默认参数（list/dict/set 字面量作默认值） | 0 处 | —（无命中） |
| `B_open_no_ctx` | open()/NamedTemporaryFile 无上下文管理器且无可见 close() | 0 处 | —（无命中；子进程 timeout 那处缺陷已由 BUG-2 修口） |
| `C_subprocess_no_timeout` | subprocess.* 调用没有 timeout= 关键字 | 0 处 | —（无命中） |
| `D_lock_no_finally` | 锁 acquire 没有包在 try/finally 里 | 3 处 | 全部 3 处逐条判**误报**（见本段末「GilState.acquire() 三处站点」） |
| `E_index_after_filter` | 推导式/过滤结果直接下标 [0]（越界面） | 0 处 | —（无命中） |

`D_lock_no_finally` 的三处是 cypy_bridge/nogil.py:102、cypy_bridge/nogil.py:80、cypy_bridge/nogil.py:153。另有两类扫描器判不了、只能靠读码：增量缓存失效面
（`cypyc/incremental/` 三件由 BUG-3/5/6/9/10 五单覆盖）与 codegen 缩进/作用域边界（由 BUG-4/8 与
第四遍通读覆盖，未再新增确诊）。收口时同一脚本**复跑一次**并与收口前快照逐类别比对
（`sweep4_classes_before_reclosure.json`）：命中集合逐类别一致，且 `gen_report.py` 在漂移时直接 `sys.exit`
拒绝出报告——所以「四类实测 0 命中」是扫出来的 0，不是没扫的 0。

确诊 13 条（其中 12 条已修复并 verify，BUG-13 是判据缺陷、入账后转结待裁决）→ 全部 `report_bug(publish_task=true)` 入账；
误报 4 条不刷账：`cypyc/cli.py:36`（sys.stdout.reconfigure 是启动期防御）、
`cypy_bridge/pointer.py:142/412`（多策略取址的刻意 fallthrough，非吞错）、第四遍的
`nogil_thread` 线程池「未关闭」疑点（`nogil_pool.__exit__` 已 `shutdown(wait=True)`，
`.fist-polish-20260926/repro_sweep4_nogil.py` 复现不出，判 B not reproduced）与
`GilState.acquire()` 三处站点（:80/:102/:153 是本模块模拟 GIL 的标志位读写，不是真 GIL 调用）；
待定 1 条（subtype golden，转结）。审查推理零付费 API。
跳过/预期失败逐条研判：基线日志与终态日志里 `skipped`、`xfail` 两个needle 的命中数为
0 → 0（`pytest_baseline.log`、`pytest_final_sweep6.log` 全文计数），
即两遍全量都没有任何被跳过或被标记预期失败的用例，该通道**无待研判对象**——这是实测出来的 0，
不是「没去看」。真正需要逐条研判的是那 1 条 `TestDigestCost` 红条（②b）。


## 二、修复闭环表（bug id ↔ 任务 id ↔ 回归测试）

| bug | 缺陷 | 自动发布任务 | 改动文件 | 锁死回归 | 账本 |
|---|---|---|---|---|---|
| BUG-1 | clear_cache 把 .pyd 删除失败当成功 | T0r6 | `cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug1_clear_cache_does_not_claim_success_when_remove_fails` | verify=已完成 |
| BUG-2 | build_ext 子进程无 timeout | T0r7 | `cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug2_bridge_build_subprocess_run_passes_timeout / test_bug2_build_timeout_is_shared_with_sibling_callers` | verify=已完成 |
| BUG-3 | 增量重解析异常被吞，陈旧 AST 继续参与编译 | T0r8 | `cypyc/project/project_compiler.py` | `tests/test_polish_20260926.py::test_bug3_reparse_failure_is_reported_not_swallowed` | verify=已完成 |
| BUG-4 | 五个 transformer 把递归收集包进静默 try | T0r9 | `cypyc/transformer/{defer,enum,generic,struct,trait}_transformer.py` | `tests/test_polish_20260926.py::test_bug4_transformer_recursion_is_outside_broad_try ×5` | verify=已完成 |
| BUG-5 | 热重载状态快照/回滚吞掉 getattr/setattr 失败 | T0r10 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug5_state_snapshot_reports_getattr_failure / test_bug5_state_restore_reports_setattr_failure` | verify=已完成 |
| BUG-6 | 读不到首行即判『不是 Cypy 文件』（含 BOM 误判） | T0r11 | `cypyc/incremental/file_monitor.py` | `tests/test_polish_20260926.py::test_bug6_cypy_file_with_bom_is_still_detected / test_bug6_unreadable_cypy_candidate_warns` | verify=已完成 |
| BUG-7 | manifest 损坏与无 manifest 不可区分 | T0r12 | `cypy_hook/hook.py, cypy_bridge/compiler.py` | `tests/test_polish_20260926.py::test_bug7_corrupt_manifest_warns / test_bug7_corrupt_bridge_manifest_warns` | verify=已完成 |
| BUG-8 | 宏重解析失败静默降级，整条语句从输出消失 | T0r13 | `cypyc/parser/macro_expander.py` | `tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported` | verify=已完成 |
| BUG-9 | HotReloadEngine 模块级状态快照/回滚仍静默（BUG-5 只修了代理那份） | T0r14 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug9_module_state_snapshot_warns / test_bug9_module_state_restore_warns` | verify=已完成 |
| BUG-10 | 热重载的依赖分析与增量缓存更新把解析失败整段吞掉（:332/:457） | T0r15 | `cypyc/incremental/hot_reload.py` | `tests/test_polish_20260926.py::test_bug10_dependency_analysis_parse_failure_warns / test_bug10_cache_update_parse_failure_warns` | verify=已完成 |
| BUG-11 | 项目模式 type_check_module 丢掉 ScopeAnalyzer 已报出的诊断（两入口相反裁决） | T0r16 | `cypyc/project/project_compiler.py` | `tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors / test_bug11_type_level_name_collision_is_reported` | verify=已完成 |
| BUG-12 | GilState.__exit__ 无条件 acquire，把用户异常顶成 NoGilError | T0r17 | `cypy_bridge/nogil.py` | `tests/test_polish_20260926.py::test_bug12_gilstate_exit_does_not_replace_user_exception / test_bug12_gilstate_exit_still_restores_state` | verify=已完成 |
| BUG-13 | TestDigestCost 的墙钟阈值随同进程既有堆涨落，判据跨收集顺序不可复现 | T0r18 | `tests/test_incremental.py:547（判据本体；未改）` | `tests/test_polish_20260926.py::无（入账未修：任何修法都要改既有判据口径，见 §六.8）` | 入账未修（§六.8 转结） |

回归文件：`tests/test_polish_20260926.py`，本轮收集 24 条用例（12 个已闭环单对应 24 条，逐单在 §二 表内点名）。

账本侧留档（归档口径要求「报告与 bugs.md 增量留档」）：`memory/bugs.md` 的 12 条已闭环条目各追加了一段 `### FIXED(verify=已完成)`，写明任务 id、库里状态、改动文件与锁死回归；条目正文与标题行的 `OPEN` 一字未改（追加脚本 `.fist-polish-20260926/annotate_bugs_fixed.py` 自带「回剥插入段 == 原文」的逐字节自证，BUG-13 那段没有写）。

本表用例名的口径修正：`TESTS` 是手写文案，之前有 3 条用例名被写成了截断形态（BUG-5 的两条各少了尾缀、BUG-6 的 BOM 那条同样被截短），pytest 按那些名字根本收集不到——是报告的错，不是产品的错。现已全部改为真实 `def` 全名，并在生成器里双向绑定：表里出现的名字必须是真实函数，真实函数也必须全部出现在表里，否则 `sys.exit`（本轮实测 20 个 `def` / 24 条收集用例，BUG-4 那 1 个函数 parametrize 展开 5 条）。
RED 证据（第一遍 8 单）：逐单交付物里的原话，例如 BUG-1 单面写着「RED：修复前该用例断言『.pyd 仍在但条目被删』失败（8 failed 之一），GREEN：现 15 passed。」；
该遍没单独落 RED 日志文件（只有逐单文案，见 `close_fixes.out.json` 的 `*:execute`），
第二遍改前
`pytest tests/test_polish_20260926.py -q -k "bug9 or bug10"` → `4 failed, 16 deselected in 0.29s`
（`.fist-polish-20260926/pytest_second_sweep_red.log`）。第三遍改前
`pytest tests/test_polish_20260926.py -q -k bug11` → `2 failed, 20 deselected in 0.27s`
（`.fist-polish-20260926/pytest_third_sweep_red.log`）。第四遍改前
`pytest tests/test_polish_20260926.py -q -k bug12` → `1 failed, 1 passed, 22 deselected in 0.45s`
（`.fist-polish-20260926/pytest_fourth_sweep_red.log`）。
GREEN 证据：修复后 `python -m pytest tests/test_polish_20260926.py -q` → `24 passed`，
全量终态见 §三。
BUG-8 是收口前复查 parser 面时补入的（上一轮审计明确留开的「两处静默降级」之一，
本次按「口头发现必须入账」处理）：修复前 `pytest tests/test_polish_20260926.py -q -k bug8`
→ `1 failed`（`capsys.readouterr().err == ''`，即整条宏语句消失而零告警）；
修复后 → 该条 pass、同文件 24 passed，且 `tests/test_macro_expansion.py`
23 passed 未回退（降级返回值不变，只补告警）。
判据开关对照（BUG-4）：旧形 synthetic 命中 `['_collect_defers']`，新形与实文件命中 `[]`——
该单最初 5 条全绿是判据不bind（把 except 体误当静默区），改成「递归是否在静默 try 内」后才真正转红再转绿。
判据加固（BUG-10，第二轮全量时抓到）：最初两条 BUG-10 用例靠 `monkeypatch` 把
`cypyc.parser.parser.Parser` 换成必抛异常的桩，单跑 24 passed，但**全量跑时该桩未被触发**
（`tests/test_polish_20260926.py::test_bug10_cache_update_parse_failure_warns` 红，`err` 为空串），
属判据依赖 ambient import 身份的不牢靠写法。已改成用「源文件真的读不到」触发同一 except 站点，
并加一条自证断言 `compiler.calls == []`（若解析/读盘没走进该站点就直接判红，而不是假绿）。
加固后开关对照：把 `hot_reload.py` 里 `_analyze_module_dependencies`/`_compile_and_reload_module`
两处 `_warn_parse(...)` 退回 `pass` → `2 failed, 18 deselected in 0.26s`
（`.fist-polish-20260926/pytest_switchoff_bug10.log`），恢复后 → 该文件 24 passed；
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
恢复后 → 该文件 24 passed，产品文件 md5 `167b194f99634b280cc3096237bcddc7`。
调用面不止测库函数：`.fist-polish-20260926/probe_cli_check_e2e.py` 真起
`python -m cypyc build <临时项目> --check-only -o <临时输出>` → **exit 1** 且 stdout 打印
`Name 'f' is already declared in this scope (line 5, col 5)`（原始输出
`probe_cli_check_e2e.out`）——源文件与输出目录都在临时目录，仓库 `output/`、`dist/` 未被写。
第四遍（BUG-12，收口后转读 bridge 面时补入）：`cypy_bridge/nogil.py` 的
`GilState.__exit__` 无条件 `self.acquire()`，而 `acquire()` 在 `not self._released` 时抛
`NoGilError`——于是**区域内已经自行 acquire、或语句自身正在抛异常**时，退出上下文会把用户的
`ValueError` 顶成 `NoGilError('GIL is not released')`，原始异常连同 traceback 一起消失
（与本模块 `NoGilContext` 修过的嵌套覆盖同族）。复现器
`.fist-polish-20260926/repro_sweep4_nogil.py` 打 A REPRODUCED / B not reproduced，
其中 B（`nogil_thread` 线程池未关闭）判**误报**、不入账。修法一行守卫 `if self._released:`，
`return False` 保持不变（不吞异常）。反向用例 `test_bug12_gilstate_exit_still_restores_state`
锁住「不许过度修成不再 acquire」。开关对照：把守卫退回改前形态 → `switch-off result: 1 failed, 1 passed`
（`.fist-polish-20260926/pytest_switchoff_bug12.log`，红的正是替换异常那一条，恢复态那条仍 pass），
恢复后 `pytest tests/test_polish_20260926.py -q` → `24 passed in 0.47s`，产品文件 md5 `d500e1d87a72b252f7f26bbd7d04fa7c`。

## 三、基线前后对照

本报告引用的终态数字仍描述当前工作区，按 mtime 归因而非口头保证：新鲜度守卫扫了四棵树的
151 个 `.py`（`cypyc/`、`cypy_bridge/`、`cypy_hook/`、`tests/`），最新修改是
`cypy_bridge/nogil.py`，它比终态日志 `pytest_final_sweep6.log` 早 6257 秒；任何晚于该日志的产品/测试文件都会让
`gen_report.py` 直接 `sys.exit` 拒绝出报告（本轮之后的改动只落在 `.fist-polish-20260926/` 与
`memory/` 两处，故未重跑 18 分钟的全量）。


| 判据 | 基线 | 终态 |
|---|---|---|
| `python -m pytest tests/ -q` | 1791 passed / 1 failed / 收集 1792 | 1815 passed / 1 failed / 收集 1816 |
| 用例总数（≥1745 只增不减） | 1792 | 1816 |
| 末行原文 | `================= 1 failed, 1791 passed in 509.24s (0:08:29) ==================` | `================= 1 failed, 1815 passed in 1126.17s (0:18:46) =================` |
| `python scripts/run_tests.py`（`test_suite/` 自研套件） | 未取基线（见下注） | Total 47 / Passed 47 / Failed 0 / Skipped 0（656.80s，退出码 0） |

`test_suite/` 不是 pytest 收集面：`python -m pytest test_suite -q` → `no tests ran`（退出码 5，
套件文件命名为 `*_suite.py`，无 `test_*` 收集匹配），因此该体系须由 `scripts/run_tests.py` 驱动。
分套件终态：ParserSuite 18通过/0失败/0跳过、AnalyzerSuite 10通过/0失败/0跳过、CodegenSuite 9通过/0失败/0跳过、IntegrationSuite 10通过/0失败/0跳过。
两套体系的终态**不是同一口径**：自研套件 47/47 全绿，pytest 面
1815 passed 但仍有 1 条红（§六.2 的 golden 转结，非本轮产品缺陷），
因此门禁①按「不绿」计——不拿第二套体系的绿来抵扣那条红。
自研套件的 `test_suite/fixtures/compiler.py` 会 `from cypy_hook.hook import CypyHook`（本轮 BUG-7
改动文件），其 47 条全绿即证明该改动未打破第二套体系的调用面。
基线缺失说明：本轮只在修复后跑了该套件（判据为「该套件自身全绿」而非「不回落」），未回退代码重测基线，
因此这一行只有终态数据，不写作前后对照。
终态复现说明：修完之后共跑过 6 次全量。BUG-1..8 落地后的两次计数完全一致
（`================= 1 failed, 1807 passed in 363.84s (0:06:03) ==================` / `================= 1 failed, 1807 passed in 401.65s (0:06:41) ==================`，只差耗时 363.84s (0:06:03) 与 401.65s (0:06:41)）；
第二遍（BUG-9/BUG-10）落地后一次 `pytest_final_sweep2.log` → `================= 2 failed, 1810 passed in 346.18s (0:05:46) ==================`，
多出的那条红是本轮**自己的**回归判据在全量下没绑上（见 §二「判据加固」），不是产品回退；
加固后 `pytest_final_sweep3.log` → `================= 1 failed, 1811 passed in 327.62s (0:05:27) ==================`；第三遍（BUG-11）落地后
`pytest_final_sweep4.log` → `================= 1 failed, 1813 passed in 338.07s (0:05:38) ==================`；第四遍（BUG-12）落地后
`pytest_final_sweep5.log` → `================= 2 failed, 1814 passed in 2615.15s (0:43:35) =================`（多出的那条红就是 BUG-13 的墙钟判据，机制见 §六.8）；
第五遍复测后终态 `pytest_final_sweep6.log` → `================= 1 failed, 1815 passed in 1126.17s (0:18:46) =================`。
「与产品/基准有关的红只有 subtype golden 一条」这一不变量保持，且七次收集数与通过数只增不减
（1808、1808 → 1812 → 1812 →
1814 → 1816 → 1816）。
标记面同理：`markers_after_sweep4.json` 与 `markers_after_sweep4b.json` 两次独立复扫的
counts 字典逐项相等（脚本已在不等时 `sys.exit`）；`test_suite_after_sweep4.log` 与 BUG-8 之前的
`test_suite_final.log` 同为 47/47——BUG-9..BUG-12 只补告警或只加一行守卫、
未改对外控制流，第二套自研体系（47 条、656.80s）因此无需重跑基线。

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

产品代码：`cypy_bridge/compiler.py`、`cypy_bridge/nogil.py`、`cypy_hook/hook.py`、`cypyc/project/project_compiler.py`、
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
2. 缺陷入账返回 `bug_id` + 自动发布 `task_id`，本轮映射见 §二（BUG-1↔T0r6 / BUG-2↔T0r7 / BUG-3↔T0r8 / BUG-4↔T0r9 / BUG-5↔T0r10 / BUG-6↔T0r11 / BUG-7↔T0r12 / BUG-8↔T0r13 / BUG-9↔T0r14 / BUG-10↔T0r15 / BUG-11↔T0r16 / BUG-12↔T0r17 / BUG-13↔T0r18）。
3. 诊断期间产生的孤儿任务（T0r1：task not found: T0r1；T0r2：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r3：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r4：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]；T0r5：非法迁移: complete 要求状态 [待验收]，当前是 [待领取]）——归档步骤见 §六，未把诊断噪声留作待办。
4. `pfist.py --batch` 首条 `report_bug` 报 `no response from report_bug within timeout`，
   而同一 payload 单发 0.2s 返回（BUG-4/BUG-5 探针复现）。**该现象本轮已复现排除，结论是
   「不是 FIST-Mbt 的缺陷，是我方驱动的缺陷」**：`.fist-polish-20260926/probe_batch_first_call.py`
   以 25s deadline、与 `pfist.py main()` 完全同形的「initialize 回复留在缓冲区」读法跑 4 个形状
   （原始输出 `.fist-polish-20260926/probe_batch_first_call.out.json`）——
   A 未读 initialize 后首条 `bug_list`：matched，2 帧 `id=1:error` + `id=2:result`，0.26s；
   B 已消费 initialize：matched，0.02s；
   C 未读 initialize 后首条是**被拒的** `report_bug`：matched，0.23s，原样报错
   `report_bug: 非法 project_dir（拒绝绝对路径/穿越/盘符）`；
   D 用 `pfist.py --batch` 回放同一被拒 payload：0.64s 出结果。四个形状全部有响应，
   server 侧无「首条超时」可复现面（探针前后 Cypy 账本 10 条不变、任务库 mtime/size 不变）。
   真正确诊的两条都在驱动里，且已修：① `--batch` 吞退出码——批内含 `__error__` 帧时仍 `rc=0`
   （形状 D 改前实测），改为 `return 1 if failed else 0`；② 读取侧用阻塞 `readline()` 配
   `select.select()`（Windows 管道不支持）且 deadline 无效，server 已退出时
   `proc.stdin.flush()` 抛 `OSError: [Errno 22] Invalid argument` 直接冒到顶层，
   使「server exited」分支不可达、EOF/无匹配帧/超时被揉成同一条文本；改为 daemon reader 线程 +
   `queue.Queue`，`_recv` 按 deadline 取并分类记 `eof` / `deadline … zero lines` / `skipped kinds`，
   `_send` 包 `OSError` 并把写失败原样并入 `__error__`。修复由
   `.fist-polish-20260926/test_pfist_reader.py` 锁死（7 项全 PASS、`rc=0`、
   `pfist_guard.err` 0 字节；含「死 server 必须分类为 `server exited (1) …` 而非 within timeout」
   「有错批 rc=1 / 无错批 rc=0」「单连接两次顺序调用 11 / 11」「账本 9665 字节与任务库 143360 字节前后不变」，
   原始输出 `pfist_guard.out`）。按红线「误报不 report_bug」，这**不向 FIST-Mbt 账本补第 5 条**；
   本节原先写的「改用带 `bug_list` 前置对账的幂等入账器 `intake.py`」仍然有效（幂等对账是
   独立收益，但不再是这条误判现象的替代品）。
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
   **BUG-9**（缺陷账本只写不销，无 bug 关闭 API → Cypy 侧 13 条全 OPEN 而 13 张单全「已完成」）、
   **BUG-10**（`archive` 走 complete 要求 `[待验收]`，停在 `[待领取]` 的孤儿单无合法废弃路径，
   原样报错 `非法迁移: complete 要求状态 [待验收]，当前是 [待领取]`）
   ——**这一条的结论已被 §五.8 的 BUG-13 更正：出路存在（`pause`），当时只试过一条路径**）、
   **BUG-11**（`report_bug` 返回 `bug_id` 而 `bug_list` 同一行叫 `id`，按写侧字段名对账会静默取到 null）。
   隔离实测：`fist-mbt.db` 修改时间仍为 14:19:34（早于本轮写入），即**它的现网任务库零改动**，
   只追加 markdown 账本；逐条原始回复见 `.fist-polish-20260926/report_fist_findings.out.json`
   （`ledger_before=6 → ledger_after=11`，第一遍 4 条上报的 id
   BUG-8..BUG-11 已在 `E:/IDEProjects/AI/FIST-Mbt/memory/bugs.md` 现有 31 个 `## BUG-n` 标题中逐条反查到），
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
8. **第二遍 issue_up（终态报告出完之后追加）**：把 §五.4 的排除法做彻底时，顺手把「本轮只试过一条路径就下结论」
   的两处也重测了，向 FIST-Mbt 账本补入 **BUG-12** 与 **BUG-13**
   （`ledger_before=10 → ledger_after=13`，
   脚本 `report_fist_findings2.py`，原始回复 `report_fist_findings2.out.json`）：
   ① BUG-12 是新发现的**契约缺陷**——`list` 的描述写「不传 namespace 则列出全库」，
   实测不带 namespace 只回单一命名空间的行（19 行，逐行 ns 均为
   `cypy-polish-20260926`），而 `list(namespace="bugs")` 的 15 行
   （含 `report_bug` 自动发布的全部修复单）一条都不出现；按描述写的「全库扫一遍找未闭环单」会**静默漏单**。
   入账前该前提由 `report_fist_findings2.py` 的 `scope_measurement()` 复核（namespace 集合与缺失行
   任一不符合预期即 `sys.exit` 拒绝上报），证据 `probe_list_scope.out.json`。
   ② BUG-13 是**对它自己账本 BUG-10 的更正**（详见 §六.1 的实测出路）：BUG-10 写「停在
   [待领取] 的任务没有任何合法废弃路径、只能靠假交付物刷成已完成」，实测 `pause` 工具（描述：
   任意活跃状态 → 已暂停）就是合法出路，本轮已用它把 16 条挂账行 park 掉。
   「archive 走 complete 要求 [待验收]」这半句仍然成立，被更正的是结论强度。
   **本轮对它账本合计 6 条**（第一遍 4 + 第二遍 2），
   其中 1 条是自我更正——上报者把自己写错的条目也当成待清偿对象。
9. **闭环表此前只引用我自己的调用日志，现补一次「不经过 MCP、不读我的日志」的独立核账**：
   `probe_ledger_final.py` 以 `sqlite3.connect("file:E:/IDEProjects/AI/Cypy/fist-mbt.db?mode=ro", uri=True)`
   只读直查本轮隔离库，并把 `memory/bugs.md` 的 `## BUG-n` 标题与该条目 `- task_id:` 逐条配对后比对库内状态：
   13 张修复单 **12/13 在库里就是 `已完成`**
   （BUG-1→`T0r6`、BUG-2→`T0r7`、BUG-3→`T0r8`、BUG-4→`T0r9`、BUG-5→`T0r10`、BUG-6→`T0r11`、BUG-7→`T0r12`、BUG-8→`T0r13`、BUG-9→`T0r14`、BUG-10→`T0r15`、BUG-11→`T0r16`、BUG-12→`T0r17`、BUG-13→`T0r18`，逐行 `ns` 均为 `bugs`），根 `T0` 库里状态 `已归档`；
   全库状态分布 `已完成 18、已暂停 16、已归档 1、待领取 1`——即可行动状态（待领取/执行中/待验收/已打回）为 0，
   §六.1 的 park 结果在库层复核成立；命名空间分布 `cypy-polish-20260926 19、bugs 17`，`default` 不在其中（本轮零写入 `default`）。
   §五.3 提到的那条幽灵单 `T0r1` 库里查无此行（`ghost_T0r1` 为 null），与当时的 `task not found` 报错一致。
   本条的四个前提（单数、根状态、无挂账、无幽灵）都已写成 `gen_report.py` 的 `sys.exit` 守卫——
   库里任一不符，这份报告就生成不出来，而不是生成后再解释。证据 `probe_ledger_final.json`。
10. **§四 的 `output_validate` 此前只是表格里的一行，本轮真用了它一次**：把 13 张修复单里
   已 verify 的 12 张（BUG-13 未 verify，不纳入）拿去做**交付物硬门复算**——artifact 清单不写死，
   由 `ov_audit_and_fist_report.py` 从 `memory/bugs.md` 本轮追加的 `### FIXED` 段落里解析出「改动文件」与
   「锁死回归」两行，展开成 49 条 `path` + `contains`/`min_chars` 检查交给 server 读真实文件：
   结果 12/12 全部 `verdict=pass`、证据层 `l4-pass`（逐单：BUG-1=pass、BUG-2=pass、BUG-3=pass、BUG-4=pass、BUG-5=pass、BUG-6=pass、BUG-7=pass、BUG-8=pass、BUG-9=pass、BUG-10=pass、BUG-11=pass、BUG-12=pass）。
   同一次运行还带一条**负向对照**：给 BUG-1 的清单再塞一个仓库里不存在的 `def test_zzz...` 路标，
   server 立刻判 `l4-hard-failed`——说明上面那批 pass 不是空转出来的。脚本与逐单回显见
   `.fist-polish-20260926/ov_audit_and_fist_report.json`。
   复算过程中顺带把 `output_validate` 的**真实契约**量清楚了（第 41 条工具事实，供下一轮少走弯路）：
   文件型 artifact 只认 `contains` / `not_contains` / `min_chars`，`check_key` 只能引用
   `external_results`；我最初按 §四 表格那句「`path`/`check_key` + invariant」写的探针参数名是错的，
   因此**先前两条「缺陷」候选都是我的探针坏了而不是工具坏了**——「`check_key` 被忽略」由改用正确字段后
   推翻；「`not_contains` 被静默忽略」由一次假对照推翻（我给的禁止串在源码里被拆成两行，`count` 实测为 0，
   于是 `pass` 本来就是正确答案）。判据见 `probe_output_validate3.py` 与其 json。
   真正**活下来的一条**已入账：`parse_artifact` 只 `m.get` 那五个已知键、从不检查剩余键，
   所以拼错或臆造的字段（`contans`、`invariant`）会把硬门静默降级成「文件存在+非空」，
   而 pass 文案仍断言「invariant 全部通过」——上报为其账本 BUG-31（`severity=medium`，
   账本 30 → 31 条，落 `E:\IDEProjects\AI\FIST-Mbt\memory\bugs.md`）。
   **本轮对它账本累计 7 条。** 该条 `publish_task=False`：
   修 FIST-Mbt 不在本轮范围内、也不该往它现网看板播种任务，这是与 §三「publish_task=true」的一处**有意偏离**，
   与前两遍上报同口径。

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
   `E:\IDEProjects\AI\Cypy\fist-mbt.db`，不影响现网。**这一段初版有两处不实，现已实测更正**：
   ① 初版把「未开工任务无法废弃」当成 FIST-Mbt 的缺陷报进它的账本（BUG-10），
   依据只是试过 `archive` 一条路径；tools/list 的 116 个工具里就有 `pause`（描述：任意活跃状态
   → 已暂停）与 `reopen_task`（任意非归档任务回滚为已领取），出路存在，故已以 BUG-13
   更正该条目（见 §五.8；「archive 走 complete 要求 [待验收]」这半句仍成立，被更正的是结论强度）。
   ② 初版只披露了 4 条孤儿，漏了同一棵树里 **12 条从未被领取的深拆叶子**
   （T0.1.1..T0.6.2）——T0.1..T0.6 是在父级直接走完 verify 的，叶子实际被父级执行取代，
   账面却仍写 `待领取`；「T0.1..T0.6 已完成、根已归档」那句话因此把一处挂账说漏了。
   收尾时两类共 **16 条**逐条 `pause`（12 条 ns
   `cypy-polish-20260926` + 4 条 ns `bugs`），逐条 `get` 复核终态全部 `已暂停`，
   park 之后全库 `待领取` 行为 0（`probe_lifecycle_park.py` → `probe_lifecycle_park.out.json`
   的 before/after 两栏）。没有伪造 `已完成`：`已暂停` 才是这些行应有的终态。
   §五.4 的批量无响应现象已在 §五.4 以 4 形状实测排除（server 侧 0.02–0.26s 全部有响应），
   确诊的两条在驱动侧并已修+锁死，故该现象未入账。
   时间顺序如实记：BUG-8 是在根 `T0` 已归档之后才确诊补入的（收口前复查 parser 面），
   其修复单 `T0r13` 单独走完 claim→execute→submit→verify 到 `已完成`（原始回复见
   `close_fixes.out.json` 的 `BUG-8:*` 5 步），根任务不回退重开——因为修复单本就落在
   ns `bugs`（见 §五.5），根 `T0` 的最终状态仍是 `已归档`。
2. **subtype 的 golden 缺失＝门禁 ① 里与产品/基准有关的红（另有 §六.8 的判据红），而它的三条出路全部要越红线，交你裁决**
   （`examples/subtype_units.cypy`，86 行、untracked，`git status --porcelain -- examples/subtype_units.cypy` 原样输出 `?? examples/subtype_units.cypy`）：
   终态该红条为 `FAILED tests/test_golden_anchor_probes.py::TestGoldenPairing::test_every_example_has_golden`。判据机制本轮重测过（不复用旧登记）：要求写在
   `tests/test_golden_anchor_probes.py:34-38`（每个 example 都要有同名 `.out`），而作用域由
   `tests/test_golden_anchor_probes.py:24-25` 的 `example_sources()` 决定——**以 `_` 开头的文件名被排除在外**，
   仓库里既有的隔离件就是 `_pending_build_blocks.cypy`、`_pending_type_defects.cypy`，且 `tests/test_judge_strictness.py:88-91` 反向断言这类
   `_pending_*.cypy` 必须存在（即「在途/已知缺陷语料用下划线前缀挂起」是本仓既有约定）。
   三条出路与各自撞的红线：① 注册 `examples/subtype_units.out` → 动 `examples/`（本轮「examples/ 不动」）；
   ② 按既有约定改名为 `examples/_pending_subtype_units.cypy` → 同样动 `examples/`，且等于替 R2 lane 宣布
   subtype 语料是「已知缺陷件」，属语义裁决不是打磨；③ 放宽 `example_sources()` 的排除规则 → 把红灯改成绿灯，
   属伪造判据，本轮明确不做（也违反「确诊才入账/不顺手改」）。
   ⇒ 本轮三条都不取，转结回 R2 lane（任务 `T0r258.2.2` 实现 subtype 那一支自己收口）。**结论要说清：只要
   `examples/subtype_units.cypy` 以现名留在工作区，门禁 ① 对本轮就不可满足——这是红线之间的冲突，不是缺陷漏修。**
3. **吞异常站点已见底**：基线 20 处 → 终态 3 处，剩下的正是 §一
   判为误报的 3 处（`cypyc/cli.py:36`、`cypy_bridge/pointer.py:142` 与 `:412`），该类别无待穷尽面。
   **宽 except 仍有 45 处**：本轮只确诊其中会掩盖真实失败的若干处，其余（IO 兜底、
   可选依赖探测、`except Exception as e` 后已 print/写入 errors）按口径保留，是下一轮的盘点面。
4. **「验收之后改判据，账面无处可写」这条结论被本轮自己推翻并已更正**（T0r15 / BUG-10，§二「判据加固」）：
   初版依据只有一条实测——`execute T0r15` → `{"__error__": {"code": -32000, "message": "非法执行: 任务处于 [已完成]"}}`，据此写了「已完成的单不允许追加/更正交付物」
   「FIST-Mbt 的第二个只写不销面」，并退而用 `heartbeat` 挂说明（`post_verify_amend.out.json` 的
   `try:heartbeat`）。通读 tools/list 的 116 个工具后发现 `reopen_task`（任意非归档任务回滚为已领取），
   于是把更正真走了一遍：`reopen_task T0r15` → `已领取` → `execute`（交付物 568 → 1057
   字符，追加「上一版结论是误判」的原文）→ `run_check`（实跑 `tests/test_polish_20260926.py`，
   `check:T0r15:r1` status=passed）→ `submit` → `verify` → 终态 `已完成`。
   逐步原始回复 `probe_lifecycle_amend.py` → `probe_lifecycle_amend.out.json`。
   因此：**「已完成的单无法更正交付物」不成立，撤稿**；FIST-Mbt 侧仍然成立的「只写不销」只剩
   bug 账本那一条（BUG-9：13 条 bug 全 OPEN 而 13 张修复单全「已完成」）。
   教训记在报告而不是记在工具上：单条路径被拒只能证明「那条路径不通」，不能证明「无路可走」——
   下结论前应先把工具面全量列一遍（本轮 §五.4 的排除法也是同一动作救回来的）。
5. **F2 subtype 子代理在 150 turn 处被截断**（`agent "F2-subtype": Reached the maximum turn limit`），
   其 `cypyc/analyzer`、`cypyc/codegen` 改动留在工作区未验收；本轮未触碰其语义，只在第三遍回读
   project 装配面时撞出 BUG-11（诊断丢弃，非 subtype 语义），R2 lane 仍需自行核账。
6. **第三遍（BUG-11）与第四遍（BUG-12）同样在根 `T0` 已归档之后补入**：其修复单
   `T0r16` / `T0r17` 各自单独走完
   claim→execute→submit→verify（原始回复见 `close_fixes3.out.json` / `close_fixes4.out.json`，
   第四遍另在单面上挂了 `run_check` 实跑 `tests/test_polish_20260926.py` 的机器校验），
   根任务不回退重开——原因与 §五.5/§六.1 相同：修复单本就落在 ns `bugs`。
7. **第四遍的判据自纠（写进报告，不当已解决）**：AST 站点表 `sweep4_classes.json` 最初把
   `hook.run()`/`self.run()` 也当成「无 timeout 的子进程」报了 2 处，属规则太宽（凡是名为
   `run` 的调用都收）。加上接收者限定 `subprocess.` 后同一遍的类 C 归零，之后才用它做排查面。
   这与 §二「判据不bind」是同一类错误：**判据报出的站点数必须先证明它能报出现行的真缺陷**，
   否则「0 处」和「2 处」都不能当结论。


8. **第五遍（BUG-13）：门禁 ① 的红条里有一条是判据自己坏了，已入账、刻意不修**
   （`tests/test_incremental.py:547`，修复单 `T0r18` 留在 待领取）。
   终态全量 sweep5 里 `TestDigestCost::test_digest_cost_on_ten_thousand_line_module` 报
   `digest cost too high: 3.223s`（阈值 `wall < 2.0`），只跑该文件也是同一形状
   （`pytest_isolated_incremental_sweep5.log` → `1 failed, 37 passed`、3.385s），
   但**同一条用例单独跑是绿的**（`pytest_digestcost_ordering.log`：单条 1 passed / 该 class 2
   passed / 前置 20 条后再跑 21 passed）。产品侧被排除：`meas_digest_cost.out.txt` 用同一份
   `_large_module`+`parse_source`+`ASTDiffer` 复测，摘要 CPU 时间 0.391/0.406/0.422s、
   墙钟 0.510–0.708s；`meas_digest_gc.out.txt` 再灌 1.5M 个循环对象（alloc_blocks
   135568→3135582）后 CPU 仍 0.42→0.47s，墙钟 0.793→0.945s，对这些对象 `gc.freeze()`
   （活对象数不变）墙钟回落到 0.544s。⇒ 多出来的秒数花在「GC 扫描本进程既有堆 + 被抢占」
   （纯 CPU 校准循环 wall/cpu 比 1.28–1.40），不花在 cypyc 的摘要计算上；
   `cypyc/incremental/ast_differ.py` 自 2026-09-25 16:39 未改，sweep4→sweep5 之间唯一产品
   改动是 `cypy_bridge/nogil.py` 的异常守卫。为什么现在才翻面：本轮用例数从 1745 涨到
   1816，同一进程里先跑的越多、判据越贵——**这条判据的结论依赖与它无关的堆**。
   不修的口径：四种改法（`process_time`、计时前 `gc.collect()`+`freeze()`、拆 `-m perf`
   单进程跑、阈值改成同进程内相对比值）都要动一条既有测试的判定，超出本轮
   「`tests/` 只补回归不改语义」的授权，按门禁纪律交回指挥官；本报告也不因此把阈值调绿。

## 七、执行记录

- 驱动脚本：`.fist-polish-20260926/{pfist,intake,intake2,intake3,intake4,intake5,meas_digest_cost,meas_digest_gc,sweep4_classes,repro_sweep4_nogil,switchoff_bug12,marker_scan,gen_bugs,gen_bugs_add8,apply_fixes,close_fixes,close_fix8,close_fixes2,close_fixes3,report_fist_findings,report_fist_findings2,post_verify_amend,probe_scope_drop,probe_cli_check_e2e,probe_batch_first_call,test_pfist_reader,probe_lifecycle_snapshot,probe_lifecycle_amend,probe_lifecycle_park,probe_ledger_final,switchoff_bug11,patch_gen_report4,patch_gen_report5,verify_report4,verify_report5,gen_report}.py`
- 终态证据：`.fist-polish-20260926/{markers_after_sweep4,markers_after_sweep4b,intake_map,intake_map2,intake_map3,intake_map4,intake_map5,meas_digest_cost.out,meas_digest_gc.out,sweep4_classes,close_fixes.out,close_fixes2.out,close_fixes3.out,close_fixes4.out,report_fist_findings.out,report_fist_findings2.out,post_verify_amend.out,probe_batch_first_call.out,probe_lifecycle_snapshot,probe_lifecycle_amend.out,probe_lifecycle_park.out,probe_list_scope.out,probe_ledger_final}.json`、
  `.fist-polish-20260926/{pytest_baseline,pytest_final_sweep6,test_suite_after_sweep4,pytest_testsuite_final,pytest_isolated_incremental_sweep5,pytest_digestcost_ordering}.log`、
  `.fist-polish-20260926/pfist_guard.out`（驱动修复后的 7 项守卫，`failures: none`、stderr 0 字节即
  `pfist_guard.err`）
  （`pytest_testsuite_final` 是 `pytest test_suite -q` 的 `collected 0 items / no tests ran`，即第二套体系不在 pytest 收集面的证据）
- RED / 开关对照证据：`{pytest_second_sweep_red,pytest_switchoff_bug10,pytest_third_sweep_red,pytest_switchoff_bug11,pytest_fourth_sweep_red,pytest_switchoff_bug12,pytest_green_bug12}.log`
- 中间快照（留档对照，不作为终态引用）：`markers_after.json`、`markers_after_final.json`、
  `markers_after_recheck.json`、`markers_after_sweep2.json`、`markers_after_sweep2b.json`、
  `markers_after_sweep3.json`、`markers_after_sweep3b.json`、`test_suite_after_sweep3.log`、
  `test_suite_final.log`、`test_suite_after_bug8.log`、`test_suite_after_sweep2.log`、
  `pytest_final.log`、`pytest_final_after_bug8.log`、`pytest_final_sweep2.log`、
  `pytest_final_sweep3.log`、`pytest_final_sweep4.log`、`pytest_final_sweep5.log`（终态为 `pytest_final_sweep6.log`）——
  取自各遍修复之间，计数与终态逐项相等（吞异常 3、宽 except 45、
  套件 47/47），
  其中 `pytest_final_sweep2.log` 多出的那条红已在 §二/§六.4 交代
- 诊断账本快照（入账前被清空重建）：`.fist-polish-20260926/bugs_ledger_diagnostic_snapshot.md`
- 上一版本报告（本轮终态之前生成，已被本文件取代，留在驱动目录不删）：
  `.fist-polish-20260926/superseded_report_15.03.28.md`、`.fist-polish-20260926/superseded_report_15.24.10.md`、`.fist-polish-20260926/superseded_report_15.26.25.md`、`.fist-polish-20260926/superseded_report_15.27.49.md`、`.fist-polish-20260926/superseded_report_15.47.42.md`、`.fist-polish-20260926/superseded_report_16.02.30.md`、`.fist-polish-20260926/superseded_report_16.14.44.md`、`.fist-polish-20260926/superseded_report_16.20.27.md`、`.fist-polish-20260926/superseded_report_18.09.31.md`、`.fist-polish-20260926/superseded_report_18.14.11.md`、`.fist-polish-20260926/superseded_report_18.25.17.md`、`.fist-polish-20260926/superseded_report_20260926.18.27.13.md`、`.fist-polish-20260926/superseded_report_20260926.18.44.48.md`、`.fist-polish-20260926/superseded_report_20260926.18.48.29.md`
