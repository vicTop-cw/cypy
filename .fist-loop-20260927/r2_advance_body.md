# R2-推进（advance）正文

环节口径：半径 = **「已声明未实现」的功能补全**。本环只动一条链：`cypyc watch`。
动手前先把上一环转结的那句原话**重测**了一遍——结论是它的一半是错的，另半没说到点上。
`HEAD` 保持 `{{.fist-loop-20260927/advance_r2_baselines.json|git.head}}`（红线：不 add / 不 commit /
不 push，实测暂存区 {{.fist-loop-20260927/advance_r2_baselines.json|git.staged}} 个文件）。

## 一、先重测：BUG-48 的原话哪半站得住

账本里 BUG-48 的 summary 是「cypyc watch 只打印横幅：改动或新增被监控文件后 16s 内**无任何重编译产物
与事件日志**，rc 始终 0」。本环用同一个夹具（`.fist-loop-20260927/advance_r2_watch_probe.py`：
真子进程跑 `cypyc watch`，改一个已存在文件 + 新增一个文件）在**改码之前**重测，实测
（`advance_r2_watch_probe_before.json`）：

| 原话的一半 | 实测 | 判定 |
|-----------|------|------|
| 「无事件日志」 | `[HotReload] File changed` 出现 {{.fist-loop-20260927/advance_r2_watch_probe_before.json|grep.file_changed}} 次，`Successfully reloaded` {{.fist-loop-20260927/advance_r2_watch_probe_before.json|grep.successfully_reloaded}} 次，`Failed to reload` {{.fist-loop-20260927/advance_r2_watch_probe_before.json|grep.failed_to_reload}} 次，`Traceback` {{.fist-loop-20260927/advance_r2_watch_probe_before.json|grep.traceback}} 次 | **不成立** |
| 「无重编译产物」 | 重编译**发生了**（重载成功），但 `-o` 目录里文件数 =
  {{.fist-loop-20260927/advance_r2_watch_probe_before.json|outputs_in_out_dir}} | 半成立：产物存在过，只是**没落到用户指定的目录**（编译进临时目录，`finally` 里删掉） |
| 「rc 始终 0」 | rc=0 且进程正常响应 Ctrl+C | 成立，但不是缺陷本身 |

⇒ 本环修的是三件**真缺**的：① `-o/--output`（手册写「Output directory for compiled files」）在 watch
路径上收不到任何东西；② CLI 从不传 `on_reload`，用户看不到批次结论（引擎早留了这个口子）；
③ `--debounce` 被引擎写死 0.5 忽略（CLI 还照抄用户输入打印「Debounce delay: 0.2s」，等于撒谎）。
这条"先重测再动手"的纪律有直接收益：如果照原话去补一个"让 watch 触发重编译"的实现，
就是在给已经能工作的路径加第二套触发器。

## 二、三件落地与各自的成对对照

| 主张 | 修在哪 | 调用面判据 | 成对对照 |
|------|--------|-----------|---------|
| `-o` 收到编译产物 | `hot_reload.py`：引擎新增 `artifact_dir` + `_publish_artifacts()`，成功编译后把 `.pyx/.pyd` 复制过去（`.c` 中间产物不算"编译文件"）；`cli.py::run_watch` 传 `artifact_dir=args.output` | `advance_r2_watch_probe.json` 的 `outputs_in_out_dir` 实测
  {{.fist-loop-20260927/advance_r2_watch_probe.json|outputs_in_out_dir}}；`grep.watch_published` =
  {{.fist-loop-20260927/advance_r2_watch_probe.json|grep.watch_published}} 行 `[Watch] Published …` | **反例**：不设 `artifact_dir` ⇒ `_publish_artifacts` 必须返回 `[]` 且目录里什么都不出现（`test_publish_artifacts_is_noop_without_artifact_dir`、`test_real_toolchain_publishes_compiled_artifacts` 的第二段）⇒ 证明我没改动库路径的默认行为 |
| CLI 挂上 on_reload | `run_watch` 内定义 `report_reload(result)` 并传入 `start()` | `advance_r2_wiring.json` 的 `cli_wiring.on_reload_callable` + `callback_output`（哨兵引擎收到什么就断言什么，且**真调一次**回调，回调体里名字写错当场就炸） | 哨兵同时核对 `artifact_dir` / `debounce_delay` / `watch_dirs` / `stopped`，逐项取值：
  `{{.fist-loop-20260927/advance_r2_wiring.json|cli_wiring}}` |
| `--debounce` 生效 | `HotReloadEngine.start()` 新增 `debounce_delay` 参数，只有显式传值才覆盖监控器默认 | `monitor_debounce_measured` = `{{.fist-loop-20260927/advance_r2_wiring.json|monitor_debounce_measured}}`（传 1.23 ⇒ 监控器存 1.23；不传 ⇒ 仍是 0.5） | 同一条判据自带两态：默认态必须是 0.5，否则我就是在改库消费者的时序 |
| 手册与实现同一句话 | `docs/USAGE.md` 2.5 段补 `-o` 行为、`[Watch] Published/No artifacts` 两种结论行、以及"临时目录编译再复制"的说明 | 报告能引用到的每一行文档描述，都在上面的实测里有对应物 | 反例由实测提供：`No artifacts published` 这一支在
  {{.fist-loop-20260927/advance_r2_watch_probe.json|grep.watch_no_artifacts}} 次批次里出现过，措辞没吹 |

## 三、附带抓到的更深缺陷：并发编译批次互踩 `build/`

探针第一次改完码重跑时**没出产物**（`failed_to_reload: 2`），日志原文给了三条互不相同的成因：
`error: command 'cl.exe' failed with exit code 1`、`can't copy 'build\lib.win-amd64-cpython-313\<mod>.pyd'`、
`[WinError 2] 系统找不到指定的文件: <临时目录>`。这不是我改坏了：

- 负复现（同一夹具、开关两态，`.fist-loop-20260927/advance_r2_race_probe.json`）：
  把 `engine._compile_lock` 换成 `nullcontext()`（其余逐字相同）后，
  **{{.fist-loop-20260927/advance_r2_race_probe.json|attempts}} 轮并发全部出红**，红轮清单
  `{{.fist-loop-20260927/advance_r2_race_probe.json|lock_off_red_rounds}}`，且每条红的成因都被
  `compileish_failure` 认成编译类（防止"我的夹具坏了"冒充产品缺陷）；
- 锁开同夹具：`{{.fist-loop-20260927/advance_r2_race_probe.json|lock_on}}` 逐轮
  `successes=[true, true]`、每轮都有发布产物；
- 机理：`compile_to_pyd` 把**最终**产物写进传入目录，但 setuptools 的**中间**产物固定在
  调用进程 CWD 下共享的 `build/`。watchdog 对一次保存发多个事件（实测 3 个），
  两个批次并发编译就互相踩。

处置：本环加**类级** `threading.RLock`（`HotReloadEngine._compile_lock`，锁的是进程共享的
`build/` 而非某个引擎实例），并把跨进程那半边入账 **BUG-54**
（`T0r62`，`advance_r2_bug54.json`）——修它要动 `cypy_hook` 的中间目录策略，而那个目录同时服务
import hook 与缓存命中面，不在"推进"半径里，也不该在自动轮里顺手改。
锁一开始写成实例属性、放在 `__init__` 里，被基线撞红一次（§五 第 7 条），才改成类属性。

## 四、三套基线、lint 与 git 红线（同一时刻复算）

| 体系 | 实测 | 下限/期望 |
|------|------|-----------|
| pytest 全量 | `{{.fist-loop-20260927/advance_r2_baselines.json|pytest.line}}` | ≥ {{.fist-loop-20260927/advance_r2_baselines.json|pytest.floor}}（= R2-打磨 1894 + 本环 9 条锁，只升不降）；收集 {{.fist-loop-20260927/advance_r2_baselines.json|pytest.collected}} |
| 自研套件 | `{{.fist-loop-20260927/advance_r2_baselines.json|suite.line}}` | 47/47 |
| e2e golden | `{{.fist-loop-20260927/advance_r2_baselines.json|e2e.line}}` | PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0 |
| 作用域化 lint | 亲笔 {{.fist-loop-20260927/advance_r2_lint.json|authored_lines_checked}} 行，违例 `{{.fist-loop-20260927/advance_r2_lint.json|refuse}}` | 亲笔行零违例 + 必然违例自检 `{{.fist-loop-20260927/advance_r2_lint.json|selftest}}` |
| git 红线 | HEAD `{{.fist-loop-20260927/advance_r2_baselines.json|git.head}}`，暂存 {{.fist-loop-20260927/advance_r2_baselines.json|git.staged}}，脏行 {{.fist-loop-20260927/advance_r2_baselines.json|git.dirty_rows}} | 不 add/commit/push |
| 改动半径 | {{.fist-loop-20260927/advance_r2_baselines.json|radius.count}} 档，本单亲笔 4 档（`hot_reload.py`/`cli.py`/`USAGE.md`/新测试），归不到本单的 `{{.fist-loop-20260927/advance_r2_baselines.json|radius.unclaimed_by_this_lane}}` | 时间窗 19:24 起（本环起跑前最后一次改动之后） |

基准**未重注册**：本环改的是 watch/hot_reload 路径，25 份端到端基准产物逐字不变
（见 e2e 末行 `PASS=25 FAIL=0`）⇒ 不需要 `--update`。

## 五、本环自身缺陷（判据/工具 6 条 + 操作 5 条）

1. 转结来的原话我**差点照抄**：如果按 BUG-48 的字面主张去实现"让 watch 触发重编译"，
   就会给已经工作的路径加第二套触发器。机制化：`advance_r2_watch_probe.py` 在任何改码之前先跑，
   把 before 件钉在盘上（`advance_r2_watch_probe_before.json`），报告 §一 的数字全部从它反解。
2. 第一条 after 探针"看起来成功"却掩盖了失败：`add_produced_or_reloaded` 的判据写的是
   "out 目录出现 .pyx **或** 日志出现 Successfully reloaded"——后者在旧码里本来就为真 ⇒ 该探针
   即便产物为零也算绿。改成"必须同时等到 a 与 b 两份产物"之后，第三跑当场暴露了 `cl.exe` 互踩。
   ⇒ **判据里任何"或"都要问一遍：另一支是不是恒真**。
3. 三条 `min_chars`/needle 我按估数写（打磨环刚记过同型错）：本环起跑前把 spec 里每条 needle 的
   `min_chars` 改成**从盘面实测文件大小自动贴合**（超出实测就下调到 `实测-50`），一次预检都没浪费。
   这条机制是上一环 §五 第 10 条的直接产物，本轮实测有效。
4. **又在基线跑动时改了被测量文件**：lint 抓到我自己写的 5 条超长行（`hot_reload.py:355`、
   `cli.py:682`、测试 133/134/273），而全量基线彼时已在跑。处置与打磨环一致——首跑留档
   `advance_r2_baselines_run1.json`，改完**整档重跑**，报告数字取最终件。首跑不只是"过期"：
   它自己就带一条红（第 7 条），两件事叠在一起，靠重跑才分得开。首跑的逐条 stdout 同批留档（`r2advance_logs/pytest_gate_run1.txt`、
   `…_collected_run1.txt`、`suite_final_run1.log`、`e2e_final_run1.log`、`baselines_run1.stdout`），
   重跑覆盖的只有同名最终件。
   复犯说明"起跑后冻结被测量面"还没变成肌肉记忆：本轮的改进是**先把 lint 跑在全量之前**
   （下一环应把它排成硬性第一步，而不是靠我记得）。

5. `advance_r2_wiring.py` 首版的 monkeypatch 复原写成
   `hook_mod.CypyHook = SpyHook.__mro__[0]` + `del` 再 import，是**能跑但误导**的垃圾代码；
   落盘前重写成"起跑前存三个真对象、`finally` 里显式复原"。哨兵脚本自己把全局状态弄脏，
   后果是同一进程里后续测试跑在假对象上 ⇒ 复原必须是显式的。
6. 一次性把三件（-o 发布 / 回调 / debounce）挤进一个环节，测试面比预期大：9 条锁里有 2 条要真编译器
   （单条 8-15s）。没有越界，但下一环同类工作应先问"能不能用哨兵把工具链依赖隔掉"——
   本轮的 `test_publish_*` 三条就是隔掉的例子，只留 1 条真编译兜住调用面。
7. **我加的东西把一条老用例撞红了**（首跑被拒原文逐字：
   `pytest 不达标：rc=1 passed=1901 下限=1902 failed=['test_bug10_cache_update_parse_failure_warns']`）：
   `_compile_lock`/`_artifact_dir` 只写在 `__init__` 里，而 `tests/test_polish_20260926.py:343`
   用 `HotReloadEngine.__new__(HotReloadEngine)` 绕过构造函数造引擎 ⇒
   `AttributeError: 'HotReloadEngine' object has no attribute '_compile_lock'`。
   这不是老测试"写法取巧"——它锁的正是"属性从哪来"这件事，而我不能改它。处置：两样都提成
   **类属性**（锁的作用域本来就该是进程，见 §三），并补第 9 条锁
   `test_engine_attributes_survive_construction_without_init` 把这条构造路径显式钉住。
   教训：**给已有类加必填实例字段前，先 grep 谁在绕过 `__init__` 造它**（`__new__`/`object.__new__`/
   `cls.__new__(cls)` 三种形状），这类构造在回归测试里是常态而非异常。
8. 第 4、7 条同源于"新代码只按自己的设计路径自检"：前 8 条新锁全绿、`watch` 端到端探针全绿，
   红的是一条**没被我碰过**的老用例。⇒ 加字段/加锁这类"看似只增不改"的改动，跑完新锁必须立刻
   跑一次**全量**再看结果，不能等到 §四 的复算步骤。本轮实际顺序是先写报告骨架、后跑全量，
   才让这条红在 19:57 才露头。
9. **折行把"逐字引用"吃掉了**：账本 FIXED 段要逐字引用 BUG-48 的原话，我写的段落里那句被排版
   拆成两行（`…16s 内无任何` 换行 `  重编译产物与事件日志』`），字符层面就不再是那句原话。
   而脚本的判据是「`PHRASE` 出现次数比落盘前 +1」——段已写进账本、次数没动，于是**先落盘后判红**
   （`原话引用次数应 +1，实测 +0（段里没逐字引用或被重复追加）`）。两处都改了：
   ① 落盘前先断言 `PHRASE in section`（写不进去的违例才是违例）；② 判据从"次数增量"换成
   **账本终态**（原话恰 2 处：条目正文 1 + FIXED 段 1，且第 2 处必须落在 FIXED 段范围内），
   幂等复跑也只做核验不追加。⇒ 「次数变了」永远证明不了"逐字"，**逐字**只能用同一字符串
   在指定区间内出现来判。账本已落的那段就地补全引用（只改我自己的 FIXED 段，条目正文与
   `OPEN` 一字未动），补完实测 `phrase_total=2`、`phrase_in_fixed_section=true`。
10. **门禁去断言一个"零时才不出现"的键**：`㊱ 枝干 0 条 ⇒ 驱动只跑了一次` 指向
    `advance_r2_root_split.json|by_scope.branch`，而 `by_scope` 是 `Counter(dict(...))`——
    枝干真是 0 时这个键**整个不存在**，终版报告因此报
    `gate ㊱ 路径失败：键 branch 不在件里（实际键：['root']）`。
    "缺席"和"零"在证据件上必须是两种可分辨的状态，而我要断言的是零 ⇒
    改的是**生成件的一侧**（三个作用域恒定 `setdefault(_s, 0)`），不是把断言改成"键不存在"。
    同一把刀还削出另一条：上一次枝干真有 24 条重跑拒绝时，这个键存在、门禁照过，
    所以这条门禁此前只在"违规"形状下被验证过，在"合规"形状下从来没跑通过。
11. **`--pre-close` 的容错漏了门禁与件清单**：预收口那一份报告本来就还没有收口产物，
    但 `report_kit.py` 只在"收口件"一栏容忍 MISSING，`artifacts` 清单和 `gates` 循环照旧拒 ⇒
    首份草稿被打回 9 条（`artifact …close_r2_advance.out.json 不可用（MISSING None）` 等）。
    补齐两处容错时把范围钉死在 **state=="MISSING" 且 pre_close**（坏 JSON/路径仍在两种模式下照拒），
    并配一条必然违例对照：把 ① 号门禁的件名换成不存在的文件、**不带** `--pre-close` 跑
    （`r2advance/synthetic_missing_gate.json`）⇒ 实测仍 `rc=1`
    `gate ① 的件 .fist-loop-20260927/__no_such_artifact__.json 不可用` ⇒
    容错没有把终版路径一起放水。


## 六、账本与收口

- BUG-48 的 `### FIXED(推进=已完成)` 段挂在账本 `## BUG-48` 条目内，段内先逐字反驳原话，
  再写落地三件；条目正文与标题行 `OPEN` 一字未改（账本无 close/edit API）。
- **已发布的法则文本改不动**：`spec_r2_advance.json` 的 description 已在收口前发到账上，里面写的是『同一引擎内并发编译批次…本环加**引擎级**串行锁』。终态实现是**类级**锁（`HotReloadEngine._compile_lock`，理由见 §三 与 §五 第 7 条）——发布文本不可改写，故逐字留在此处作对照。同一条法则的验收针我在本地 spec 里从「1902 passed」改成了「1903 passed」（第 9 条锁落地后的实测收集数），账上已发布的法则文本仍写 1902 ⇒ 两处字面差都属**本地件跟随实测、服务端文本冻结**，不做追改。
- 新缺陷 BUG-54（跨进程 `build/` 互踩）已入账并给出**关闭判据**：必须用两个子进程并发编译
  不同模块仍各自产出 .pyd 才算修，引擎内锁不算。
- 三向对照复算：账本条目 {{.fist-loop-20260927/verify_r2_ledger3way.json|ledger.entries}} 条、
  FIXED 段 {{.fist-loop-20260927/verify_r2_ledger3way.json|ledger.fixed_sections}} 段、sqlite bug 任务
  {{.fist-loop-20260927/verify_r2_ledger3way.json|server.bug_tasks}} 个，拒绝清单
  `{{.fist-loop-20260927/verify_r2_ledger3way.json|refuse}}`（沿用上一环定性的 4 条孤儿）。
- 收口链：16 叶 8 枝 `{{.fist-loop-20260927/close_r2_advance.out.json|leaves}}` 条走完
  claim→omega→execute→submit→output_validate→omega_result_verify→verify，失败叶子
  `{{.fist-loop-20260927/close_r2_advance.out.json|failed}}` 条；根 `T0r61` 终态
  `{{.fist-loop-20260927/close_r2_advance_root.out.json|root_final}}`，上卷被拒
  `{{.fist-loop-20260927/close_r2_advance_root.out.json|refused}}`——
  **上卷驱动本环只跑一次**：先用 `report_kit.py --pre-close` 落一份不含上卷数字的报告草稿
  （L4 产物门要的就是"报告已在盘上"），再跑驱动，最后重生成终版把被拒清单反解进来。
  结构性合法拒绝应为根任务 6 条、枝干 0 条——枝干上出现任何一条都意味着驱动被重跑过，
  这是打磨环实测出来的分栏口径。

## 七、未做与转结 / 交人类裁决

| 项 | 为什么不进本环 |
|----|----------------|
| BUG-54 跨进程 `build/` 隔离 | 要动 `cypy_hook` 的中间目录策略，同时影响 import hook 与缓存命中面 ⇒ 属修复/裁决面 |
| `watch` 的删除事件是否要清掉 `-o` 里的旧产物 | 手册没承诺过；新增这条语义就是扩大对外承诺，不在"补已声明未实现"的半径里 |
| BUG-49 过期实现状态栏 / BUG-40 flake8 配置 / BUG-41 同名遮蔽 / BUG-43 mypy 版本 / BUG-35 深嵌套半边 | 沿前三环同因（冻结文档、配置口径、需动既有测试）⇒ 继续挂账 |
| BUG-50/52 formatter 债、BUG-53/`T0r59` 处置 | 裁决面未变 |

交裁决：

1. **轮末本地 commit + tag**：本树仍压着 09-26 与各环未提交改动，需先答"哪一份是权威工作树"。
2. **BUG-54 修法二选一**：给每次编译独立 `build_temp`（动 `cypy_hook`，影响缓存命中面），
   还是给仓库级 watch 加单实例锁（只动 CLI，但限制并行使用）。
3. `watch` 的产物发布范围要不要含 `.c` 中间产物（现在按"编译文件"字面只发 `.pyx/.pyd`）。
4. BUG-50 的 `parser.py`/`macro_expander.py` 文本债处置三选一不变。
