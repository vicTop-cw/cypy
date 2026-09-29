## 一、这一环做了什么，以及没做什么

R4-打磨（根任务 `T0r90`，执行人 `cypy-polisher`）的半径是「措辞面 + 账面 + 测试面 + 骨架」，
不是语义面：产品码在本环零改动（`polish_r4_baselines.json|radius.product` 实测为空清单），
冻结面 `{{polish_r4_docs.json|frozen_total}}` 个文件在本环 mtime 分栏里也是空栏
（`polish_r4_baselines.json|radius.frozen`），而补注件的独立复核给出
`{{polish_r4_appendixC.json|frozen_sha_equal}}`——两条路各自数、各自空。
HEAD 仍是 `{{polish_r4_baselines.json|git.head}}`，暂存区 `{{polish_r4_baselines.json|git.staged}}` 行。

本环真做了六件事，每件由一个可复跑判据件承重，正文数字一律从件里反解：

1. 法①：`docs/USAGE.md` 里那句「源未变会复用 `.pyd`」按调用面实读改写；
2. 法②：附录 C 的形差分两栏——改冻结面交人工，非冻结补注 `docs/APPENDIX_C_DEVIATIONS.md` 由我方写；
3. 法③：`memory/bugs.md` 缺 `task_id` 的卡片以「只增不改」补记，差分逐行了结；
4. 法④：判据件的重复骨架收敛到共用件 `{{polish_r4_debt.json|kit}}`，收敛前后关键格数逐字相等；
5. 法⑤：验证环的调用面探针固化成 `{{polish_r4_locks.json|new_test_file}}` 永久锁，先红后绿且证承重；
6. 法⑥：结构债（3000 行红线、`type_checker.py` 体量、`hook.eval` 写侧形状）逐条测量后挂账，不动刀。

没做的：不改语义、不重注册 golden、不 `git add/commit/push`、不删文件或别人的 worktree、
不删不放宽既有测试、不替人工裁「要不要动冻结面」。

## 二、法①：文档口径只认调用面实读，不认源码字面

被改的那句原文在 `{{polish_r4_docs.json|old_line_number_measured}}` 行——这是盘上实测行号，
不是计划与上一环账里写的 406：`{{polish_r4_docs.json|citation_drift}}`。
改前 sha `{{polish_r4_docs.json|before_sha}}`，改后 `{{polish_r4_docs.json|after_sha}}`，
差分形态是「1 删 1 增」，逐字两行在件里 `polish_r4_docs.json|diff_changed_lines`；
新写入正文逐字为：

> `{{polish_r4_docs.json|new_line}}`

新措辞的全部依据是同一源、同一 `output_dir` 连调两次 `compile_to_pyd` 的真跑：
`.pyd` 被复用是否为真 `{{polish_r4_docs.json|measurement.pyd_reused_between_calls}}`、
`get_cached_pyd()` 是否恒 None `{{polish_r4_docs.json|measurement.get_cached_pyd_all_none}}`、
同一次调用是否连打「缓存命中」与「缓存未命中」两行
`{{polish_r4_docs.json|measurement.single_call_prints_both_cache_verdicts}}`（两行原文
`{{polish_r4_docs.json|measurement.cache_steps_first_two}}`）。
逐次的 mtime 与落盘布尔在件里 `polish_r4_docs.json|measurement.rows`，本环没有把它们抄进正文，
只把「判定」抄进来——抄数字就会抄错。

签名面与字段面同样按实读反解：`compile_to_pyd` 形参
`{{polish_r4_docs.json|call_face_claims.compile_to_pyd_params}}`、
`CompileResult` 字段 `{{polish_r4_docs.json|call_face_claims.compile_result_fields}}`、
CLI 可见子命令 `{{polish_r4_docs.json|call_face_claims.cli_subcommands_seen}}`（`--help` rc=
{{polish_r4_docs.json|call_face_claims.cli_help_rc}}）。

反向对照在这条法里是**判据而不是姿态**：件里三个布尔各管一头——改前措辞必须被实测判假
（`pyd_reused_between_calls=false` 就是那句旧话的反证），当前措辞必须被实测判真，
且那份改前副本真在盘上而不是口头假设（`tests/` 侧的对应锁见 §六，
`{{polish_r4_locks.json|doc_predicate}}`）。

## 三、法②：形差分两栏，冻结面一根手指都没碰

`{{polish_r4_appendixC.json|frozen_doc}}` 的《已实现的限制修复》表体在 R4-验证 里反解出 14 行，
其中 4 行不成立：1 行 claim-false + 3 行 claim-half-true。逐行的冻结面原文、现写真跑证据与裁决
在件里 `polish_r4_appendixC.json|deviations`（4 个对象，含 `verdict` 与 `reason`），
本环对它们只做两件可逆的事：

- **交人工栏**：`{{polish_r4_appendixC.json|queue_frozen_edit}}`——这是冻结表体的实测行号，
  不是我按「1..4 连续」猜的；理由是改冻结面=改已发布的语义承诺，不可撤回；
- **我方可做栏**：新增非冻结补注 `{{polish_r4_appendixC.json|note_file}}`，
  `{{polish_r4_appendixC.json|note_done_rows}}` 行、`{{polish_r4_appendixC.json|note_bytes}}` B，
  件在本环之前不存在（`{{polish_r4_appendixC.json|existed_before_this_run}}`）。

冻结面自证：`{{polish_r4_appendixC.json|frozen_files}}` 个 .md 逐个 sha 与 R4-验证 实测逐字相等
（全表在 `polish_r4_appendixC.json|frozen_sha`），并配一条必然违例的 canary
`{{polish_r4_appendixC.json|canary}}`——往冻结文件的**副本**注入一字节，比较谓词必须抓到。
没有这条 canary，「sha 相等」既可能是没动，也可能是谓词坏了，两者在报告里长得很像。

## 四、法③：账面卫生以「只增不改」为准，差分逐行了结

`memory/bugs.md` 里缺 `- task_id:` 的历史卡片是
`{{polish_r4_ledger.json|missing_before}}`，共 8 张。补记方式是 append-only：
差分实测新增 `{{polish_r4_ledger.json|append_only_diff.added}}` 行、删除
`{{polish_r4_ledger.json|append_only_diff.removed}}` 行，被删样本清单
`{{polish_r4_ledger.json|append_only_diff.removed_samples}}`（空=真的一行没删）。
卡片总数改前改后同为 `{{polish_r4_ledger.json|cards_total_after}}`（只补注不新增卡），
带合法 task_id 的卡片数 `{{polish_r4_ledger.json|valid_task_ids_before}}` →
`{{polish_r4_ledger.json|valid_task_ids_after}}` 不变——这条不变是关键：
如果我当时能把 8 张都「找回单号」，合法计数就会虚增 8，那才是账面造假。

为什么补记措辞是「未派单」而不是「丢了单号」：这 8 张卡在服务端 `bugs` 树里按 summary 前 20 字
反查命中数为空（`polish_r4_ledger.json|resolved_from_sqlite` 反解结果就是空集，
配套门禁把它钉成「必须等于空」），sqlite 侧 bugs 行 `{{polish_r4_ledger.json|sqlite_bug_rows}}`
也对不上号。补派=向服务端写新条目，不可撤回 ⇒ `{{polish_r4_ledger.json|adjudication}}`。
差分谓词自己配 canary：往临时副本删一行，必须报
`{{polish_r4_ledger.json|canary}}`（added=1/removed=0 是「少一行被抓」的形状）——
否则「removed 恒 0」是装饰。

## 五、法④：骨架收敛必须带「行为不变」证据，不能只说收敛了

本环新写的件接进共用骨架 `{{polish_r4_debt.json|kit}}`，对外 API
`{{polish_r4_debt.json|kit_apis}}`。收敛的证据不是「我抽了一个函数」，而是**同一批旧件用新旧两套解析
各跑一遍、逐字段相等**：核对覆盖的归档件 `{{polish_r4_debt.json|equivalence_artifacts}}`，
逐行三向对照（原文行 / 新解析 / 旧件记录值）在件里 `polish_r4_debt.json|equivalence`（4 行）。
快照复制器与参考实现的文件集合同集 `{{polish_r4_debt.json|copy_tree_face}}`，
解析器配双 canary `{{polish_r4_debt.json|canary}}`：垃圾行必须解出 0/0/0，
`1976 passed` 必须解出 1976——只配一边就是「恒真或恒假」的老毛病。

形状分差没有被抹平，而是逐条点名，实测 `{{polish_r4_debt.json|shape_divergence_len}}` 条
（逐条原文在件里 `polish_r4_debt.json|shape_divergence`）：
R3 那批件把自研套件的 47 记成字符串 `"47"`，新解析记成整数 47；
强行统一=改动上一环的渲染输入证据，属越界，故留债。
留债也逐件点名 `{{polish_r4_debt.json|debt_remaining_counts}}`，口径说明在件里
`{{polish_r4_debt.json|scope_note}}`；本轮真正接入共用骨架的只有
`{{polish_r4_debt.json|kit_users_this_ring}}`——「建了模块不接线」是另一类谎，
所以这条计数必须非空。

## 六、法⑤：探针不做成一次性脚本，做成 tests/ 里的永久锁

新锁文件 `{{polish_r4_locks.json|new_test_file}}` 共 20 个用例，两档跑：

- 工作区档（当前产品码 + 当前文档）：`{{polish_r4_locks.json|lane_work.summary}}`，
  计数 `{{polish_r4_locks.json|lane_work.counts}}`；
- 修前码档（把 `cypyc/analyzer/type_checker.py` 换成 R4-修复 之前的快照文本，树在
  `{{polish_r4_locks.json|identity.snap_tree}}`；身份由 sha 双向证明：工作区
  `{{polish_r4_locks.json|identity.work_type_checker_sha}}` ≠ 快照
  `{{polish_r4_locks.json|identity.snap_type_checker_sha}}`）：
  `{{polish_r4_locks.json|lane_prefix_code.summary}}`，红的用例名逐条点名在件里
  `polish_r4_locks.json|lane_prefix_code.red`。

「今天的绿灯不是证据」这条纪律在这里落地：同一份锁在修前码上必须红，才证明锁认的是本轮修的那四个
形状（BUG-61..64 的 CLI 调用面 + 文档那句），而不是碰巧长绿的通用断言。
混因在这里分栏：15 条红里 14 条打在产品面、1 条
`test_usage_doc_does_not_claim_pyd_reuse` 打在文档面——快照树带的是改前措辞，
所以它红的因是 §二 的文档改写而不是产品码；件里把这条单独断言
（`polish_r4_locks.json` 的 self_checks「B 道的红里必须有文档口径锁」）。
既有测试一条没动：`polish_r4_baselines.json|radius.tests` 只含这一份新文件。
收集数 `{{polish_r4_locks.json|collect_after_locks}}` = 上一环地板
`{{polish_r4_locks.json|previous_round_collect_floor}}` + 20，多出来的恰好就是新锁。
文档谓词单独配对 `{{polish_r4_locks.json|doc_predicate}}`：
改前文本必须让锁失败、当前文本必须通过、且那份改前副本真在盘上。

## 七、法⑥：结构债只测量、只挂账

`{{polish_r4_structural.json|files_measured}}` 个产品文件逐个量代码行（剔注释与空行），
红线 `{{polish_r4_structural.json|redline}}` 行，越线文件
`{{polish_r4_structural.json|over_redline}}`；`type_checker.py` 实测
`{{polish_r4_structural.json|type_checker}}`；`hook.eval` 写侧 `__result__` 字面在单文件出现
`{{polish_r4_structural.json|hook_eval_marker_count}}` 次、在产品面总数
`{{polish_r4_structural.json|hook_eval_marker_product_face_total}}` 次（包含关系：后者 ≥ 前者）。
挂账队列 3 条，每条带「为什么不可逆」与测量口径，逐条原文在件里
`polish_r4_structural.json|adjudication_queue`；本环执行了的不可逆动作
`{{polish_r4_structural.json|executed_irreversible}}`（空=真没动）。

正面测「没动手」比喊口号难，这里用三类谓词：本环窗口内被改的产品文件
`{{polish_r4_structural.json|product_files_touched_this_ring}}`（mtime 实测）、
改名清单 `{{polish_r4_structural.json|renamed_verbatim}}`（空）、
删除清单 10 条逐字在件里 `polish_r4_structural.json|deleted_verbatim`——这 10 条与上一环记录的
**同集且计数相等**，所以它是「历轮旧账未结」而不是「本环新删」；本环净删除 0。
这条口径的弱点我也记账：它是**计数一致**而不是逐名对照（件里 self_checks 已把这半句写进去）。
canary `{{polish_r4_structural.json|canary}}`：刚写下的文件必须被同一谓词判为「碰过」、
临时 scratch 必须清干净。git 面总行数 `{{polish_r4_structural.json|git.rows}}`，
其中绝大多数是历轮改动，与本环半径不冲突。

## 八、法⑦：三套体系同批复算，地板取上一环实测件

| 体系 | 本环实测 | 地板（R4-验证 实测件） | 判定口径 |
|---|---|---|---|
| pytest | `{{polish_r4_baselines.json|systems.pytest.summary_line}}` | `{{polish_r4_baselines.json|floors.pytest}}` | 只升不降 |
| 收集 | `{{polish_r4_baselines.json|systems.collect.nodeids}}` | `{{polish_r4_baselines.json|floors.collect}}` | +20 恰为新锁 |
| 自研套件 | `{{polish_r4_baselines.json|systems.suite.line}}` | `{{polish_r4_baselines.json|floors.suite}}` | 同批复算 |
| e2e golden | `{{polish_r4_baselines.json|systems.e2e}}` | `{{polish_r4_baselines.json|floors.e2e_pass}}` | 零 FAIL 零 WARN |

三套同时为绿 `{{polish_r4_baselines.json|three_systems_green}}`；失败用例名清单
`{{polish_r4_baselines.json|systems.pytest.failed_names}}`（空，且这条空集由门禁钉住）；
「只升不降」的比较函数自己配 canary `{{polish_r4_baselines.json|canary}}`——
拿 `passed+1` 当地板必须报违规，否则这条门恒绿。
半径按 mtime 分栏实测：产品 `{{polish_r4_baselines.json|radius.product}}`、
测试 `{{polish_r4_baselines.json|radius.tests}}`、docs `{{polish_r4_baselines.json|radius.docs}}`、
冻结 `{{polish_r4_baselines.json|radius.frozen}}`，扫描文件数
`{{polish_r4_baselines.json|scanned_files}}`（空扫描=分栏装饰，所以这条也要点数）。

**本环在这里犯了一个流程错，如实记账**：同一条三套体系批被我起了两遍。
第一批 `{{polish_r4_baselines.json|window.start_utc}}` 起跑后，我在其后 13 分钟又重写了测试文件，
测量面因此没冻结；发现第一批没落件时，我又没查进程表就起了第二批——
于是两套全量并发跑，违反本项目已知的「别并发跑两套全量」。
本环正文引用的是**第二批**（`{{polish_r4_baselines.json|window.batch_started_at_utc}}` 起跑，
此时 tests/docs 全部定稿），第一批降为交叉复核。
从环节起点到本件写出实测 `{{polish_r4_baselines.json|elapsed_min_from_start}}` 分钟（盒 100 分钟）；
叶/根收链在这之后才发，收口完成时刻与全环耗时以 `.fist-loop-20260927/loop_progress.md` 为准，
本报告不预支「已按盒收口」这句结论。
并发的代价是墙钟被自己毒成两倍；判定数（passed/failed/collect/e2e）不依赖墙钟，所以本表仍可用。

## 九、法⑧：驱动面与账面到本环为止的样子

亲笔驱动 `{{polish_r4_drivers_lint.json|drivers_scanned}}` 个（口径=本环窗口内新写的脚本，
逐件字节数与 mtime 在 `polish_r4_drivers_lint.json|detail`），硬错
`{{polish_r4_drivers_lint.json|hard_violations}}`、软账
`{{polish_r4_drivers_lint.json|soft_total}}`（上一环基线
`{{polish_r4_drivers_lint.json|previous_round_soft_baseline}}`，只降不升），
行长口径 `{{polish_r4_drivers_lint.json|line_length_declared}}`。
lint 的 canary `{{polish_r4_drivers_lint.json|canary}}`：合成的超长行必须被抓到、
干净文件必须零命中，否则「0 硬错」无从谈起。
这条口径的边界也写在墙上：旧环的 48/41 个脚本不在本环窗口内，
「0 硬错」不能读成「全仓 0 硬错」。

call_log 只按 `params_json.task_id` 前缀对账（不按标签、不按回忆）：渲染前快照本环前缀
`{{polish_r4_calllog_tally.json|rows_T0r90}}` 行 / `{{polish_r4_calllog_tally.json|distinct_tasks}}` 个任务，
被拒 `{{polish_r4_calllog_tally.json|stages.T0r90.refused}}` 条，
对照前缀实测 `{{polish_r4_calllog_tally.json|control_absent_prefix_rows}}` 行（必须 0，否则过滤器恒真），
全库 `{{polish_r4_calllog_tally.json|total_call_log_rows}}` 行、历轮根合计
`{{polish_r4_calllog_tally.json|loop_roots_total_rows}}` 行，
没有任何根零调用（`{{polish_r4_calllog_tally.json|loop_roots_without_calls}}`）。

这里必须说清一件事，否则就是在替自己编绿灯：渲染前这一刻本环的 omega 链计数是
`{{polish_r4_calllog_tally.json|omega_chain_by_tool}}`——**全 0**，因为收口链（16 叶 × omega 全链 +
8 支 + 根上卷）按规定顺序在这份报告渲染**之后**才发。所以本环对「omega 开启」的主张只到
发单与规格面为止：本环种子调用 `{{polish_r4_calllog_tally.json|stage_seed_rows.total}}` 次；
规格点名的 `laya` / `issue_up` 不是本 build 的工具名，承担同一能力的实际名与逐工具计数
在件里 `polish_r4_calllog_tally.json|spec_named_carriers`（本 build 里这些名的全库计数见
`polish_r4_calllog_tally.json|named_tools_in_this_build`）。
收口链的实发次数、被拒原文与三向对账一律落 `.fist-loop-20260927/loop_progress.md`，
本 spec 因此**不留 closure 位**——留了就等于要求渲染时收口件已存在，那会把顺序倒过来。
缺陷入账面：本环复算到的三条形状类主张在 bugs 树的行数各自为 1
（`polish_r4_calllog_tally.json|bug_intake_rows`）。

## 十、本环我自己的失效（19 条，逐条：现象 → 我错在哪 → 改成什么才承重）

1. **计划里的 needle 键名是猜的**：`spec_r4_polish.json` 在 09:10 写就，此时判据件还不存在，
   16 个证据槽位里 8 个 needle 键名在盘上根本不存在（`usage_fix`/`appended`/`removed_lines`/
   `dedup`/`rerun`/`added`/`mutation_bearing`/`not_executed`），另 1 个（`measure`）只作为
   `files_measured` 的子串侥幸命中。我错在把「计划措辞」当成了「证据键名」。改法：以件里真存在的
   键名校正，逐槽位断言命中，11 处改动与理由写进件里 `needle_correction`
   （文件、`min_chars` 地板与「逐字含键」的强度一位未动）。
2. **子串口径本身会放行假命中**：`control` 这个 needle 在件里命中的是
   `SYNTAX/15-control-flow.md` 这个**文件名**，件里并没有 `control` 键；`queue` 命中的是
   `queue_frozen_edit` 的前缀。如果我不动这条口径，收口预检会「过」在它根本没测到的东西上。
   改法：needle 升级为「必须是被引件里的真键名」，并配一条 canary 证明旧口径确实会放过 `control`。
3. **测量面起跑后没冻结，还并发起第二套全量**：09:55 的基线批跑到一半，10:08 我又重写了测试文件；
   发现没落件时我没先查进程表就起了第二批。我错在把「重跑一次就好」当成无代价动作——
   本项目的墙钟判据本来就吃进程堆，并发等于自己毒自己的测量。改法：正文只引用第二批
   （起跑于测试与文档都定稿之后），第一批降为交叉复核，并把「起后台批前先查同项目是否已有批在跑」
   记进流程债（§十二）。
4. **批量字符串替换源码**：我一度从验证环的自证件整词替换 `verify`→`polish` 来生成打磨环的自证件，
   替换本身撞在自家断言上（模块 docstring 里合法含 `verify`）。改法：逐键改写 + 显式断言改动处数。
5. **引用号没重测**：环节计划与上一环的账都写 `USAGE.md:406`，盘上实测该句在第 414 行。
   我没有沿用旧号，而是把漂移在件里点名（`citation_drift`），也不回头改历史账。
6. **把「查不到 task_id」预设成「丢单号」**：BUG-44..51 在 `bugs` 树里按 summary 反查 0 条，
   说明它们从未进服务端账。补记措辞因此是「未派单」，并把补派交人工；
   如果我当时按「找回单号」写，就是在账面上伪造一次服务端归属。
7. **行号想当然**：`queue_frozen_edit` 实测是 `[1, 4, 5, 6]`，我一度以为该是连续的 1..4。以件为准。
8. **收敛证据的覆盖面比主张窄**：`equivalence` 只有 4 行、全部来自 baselines 类件，
   「关键格数不变」这句在本环只对这三份归档件成立。我把它写成逐件点名而不是全称命题。
9. **形状分差没被抹平，但也没被消解**：R3 把 47 记成字符串 `"47"`。
   统一=改上一环渲染输入，越界；本环的处理是点名 + 转结，报告里不许出现「已收敛」。
10. **lint 的口径只覆盖本环 11 个亲笔脚本**：旧环脚本不在窗口内，「0 硬错」不能读成「全仓 0 硬错」。
    件里用 `drivers_scanned` 与 `detail` 把口径钉死，正文再声明一次边界。
11. **锁的红里混了两种因**：`lane_prefix_code` 15 条红有 1 条打在文档面而不是产品面。
    如果不分栏，「锁认本轮形状」这句就会被一次不相干的文档改写撑起来。
12. **删除清单是计数一致而非逐名对照**：件里 self_checks 自己写了「口径=计数一致，未逐名对照 ⇒
    记为上界一致」。我把这半句抄进正文，而不是把它读成「已逐名核实」。
13. **call_log 的两个时刻容易被读成一个**：§九 的行数是渲染前快照，收口链的行数在报告之后才产生。
    两处都显式标了「渲染前」，并且不在报告里预支「收口零被拒」这句结论。
14. **omega 链计数为 0 的读法**：这 0 不是「没开 omega」，而是「收口链还没发」。
    我把整块 `omega_chain_by_tool` 原样放进正文，而不是挑一个好看的数写。
15. **时间盒**：从环节起点到基线件写出实测的分钟数写在 §八，收口链之后的全环耗时进进度账。
    门禁没有缩、判据没有放宽、冻结面没有动；并发重跑浪费的那段墙钟记在这里，不当「已按盒收口」讲。
16. **又拍了一个猜出来的地板**：我把形状分差的门禁写成 `min: 5`，件里实测是 4 条。
    我错在给「条数」填了一个看起来合理的数，而不是先量。改法：给件补一格
    `shape_divergence_len`（由 `len()` 反解），正文引用这一格，门禁地板降到
    语义上真正 required 的 3（套件计数的 Total/Passed/Failed 三个字段各至少一条）。
17. **把「渲染之后才存在的见证件」写成了渲染输入的门禁**：我一度给报告 spec 加了 13 道读
    `polish_r4_render_order.json` 的门禁——那份件是渲染完成后才产的，报告不可能在它存在时
    校验它，这条顺序倒置会让自证永远红。改法：把那 13 项检查留在见证件自己的拒绝清单里
    （renders/label 齐平/红格/§十 渲染后条数/法条标题齐备），从渲染输入里删掉；
    见证件不合格就整条链非零退出，报告不会因此「预支」一句见证。
18. **驱动面 lint 只数不拦**：`polish_r4_drivers_lint.py` 把 `hard_violations` 数出来了，
    却在有硬错时仍然 `refuse=[]`——我新写的进度件有一条 `E999 SyntaxError`，件照样「绿」。
    这是「守卫覆盖面必然窄于主张」的又一例：数了不拦的门禁等于装饰。改法：给件补
    「有硬错必 refuse」，报告侧 ⑧-14 之外再由件自己拒；同一次复跑把这条从装饰变成承重。
19. **编辑工具吃掉行尾**：我用一次「删掉多余空行」的编辑把 `lines.append(...)` 的收尾和下一条
    语句并到了同一行，造成语法错（就是 18 里那条 E999）。我错在把 Edit 当成只会改字符的操作——
    它匹配 `old_string` 时会把边界一起吃掉。改法：改完立刻用编译/lint 复测，别靠肉眼。

## 十一、要谁裁决（只挂账，本环不动刀）

| 事项 | 为什么交人工 | 活证据（可复跑件里的路径） |
|---|---|---|
| `SYNTAX/appendix-C-features.md` 形差行的措辞修正（含 claim-false 的切片语法行） | 改冻结面=改已发布的语义承诺，不可撤回 | `polish_r4_appendixC.json|queue_frozen_edit`、逐行现真在 `deviations` |
| BUG-44..51 是否补派进服务端 `bugs` 树 | 服务端写入不可撤回，且反查 0 条说明归属本身待定 | `polish_r4_ledger.json|missing_before`、`resolved_from_sqlite`、`adjudication` |
| 3000 行红线拆分（4 个越线文件） | 拆文件改导入面与既有测试路径，属结构重排 | `polish_r4_structural.json|over_redline` + `sizes` 逐文件 |
| `type_checker.py` 体量/分支重写 | 移动语义判定点需要 golden 重注册 | `polish_r4_structural.json|type_checker` |
| `hook.eval` 写侧 `__result__` 形状 | 改产物形状影响已发布扩展读取面 | `polish_r4_structural.json|hook_eval_marker_count` |
| examples 里 10 条遗留删除（历轮未结） | 删文件不可逆，且与本环半径无关 | `polish_r4_structural.json|deleted_verbatim` 逐字行 |

## 十二、转结与顺序账

- 转结给 **R4-推进**：`docs/` 与 `tests/` 的口径已与调用面对齐，推进环半径仍限「已声明未实现」，
  不得再引用 `USAGE.md:406` 这个旧行号；§十一 的 6 项裁决与 8 张未派单卡片继续挂着，不在推进环动手。
- 转结给 **R5 打磨**：`shape_divergence` 点名的字符串/整数形状差（条数见 §五）与
  `debt_remaining_counts` 的四类骨架留债（换骨架=改上一环渲染输入，只能作为新一轮半径）。
- 转结给 **流程债**：「起后台批量前先枚举同项目是否已有批在跑」「基线起跑后冻结被测量面」
  两条本轮再次踩中的操作纪律（§十 3）。
- 顺序账（本环不可回改的次序）：判据件 → 自证件 ⇄ 收口 spec（不动点收敛）→ 报告渲染一次 →
  渲染见证 → 16 叶 omega 全链 → 8 支上卷 → 根归档 → 终账 call_log → 进度账。
  收口件不是报告的渲染输入，报告也不是收口的证据来源；两者互不追改。
- 自引用面：指向 `polish_r4_self_audit.json` 自身的门禁与占位在第 N 次运行只能读到第 N−1 次的自己，
  属自指振荡，因此无条件延后——由渲染器当场判，自证件里只记 deferred 清单。
- 门禁表全部由 `report_kit.py` 从件里反解，任一格不成立这份报告就不会以绿态存在。
