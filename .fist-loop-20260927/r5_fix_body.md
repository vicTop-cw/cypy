## 一、这一环做了什么

R5-寻虫 入账的 BUG-78..BUG-90 十三张新单，加上账本现数还留 OPEN 的旧单里本环可修的那批，
一共 {{fix_r5_intake.json|planned_ids}} 张进入本环认领栏；其中 BUG-91 是本环修到一半才入账的
（BUG-90 接上调用方之后暴露的另一条，见 §八 第 13/14 条），认领表按法①「从盘上反解」重跑过一次。
动手的判据不是「我觉得修完了」，
而是八法各自的判据件：认领表（`fix_r5_intake.json`）、锁（`fix_r5_locks.json`）、
改动点与归属（`fix_r5_rc.json`）、回退矩阵（`fix_r5_revert.json`）、影响面（`fix_r5_impact.json`）、
三套体系与半径（`fix_r5_baselines.json`）、账面闭环（`fix_r5_ledger.json`）、
驱动面与调用对账（`fix_r5_drivers_lint.json`、`fix_r5_calllog_tally.json`）。

产品面一共动了这些文件（逐字列，不数给人看）：{{fix_r5_rc.json|files_this_ring}}。
其中 {{fix_r5_rc.json|product_files_without_card}} 是「车道自己报了、但没有任何一张单的机制栏点名」的文件
——上一版的归属口径会把这类改动算成没人做，这一版改由回退矩阵按锁承重现测归属（见 §四）。

## 二、认领表与派单半径

分栏由 `fix_r5_intake.json` 从账本与任务库现读后算出，不是我手写的名单：

- 分栏定义：{{fix_r5_intake.json|split_columns}}
- 本环认领（进修）：{{fix_r5_intake.json|planned_ids}}
- 账本现数的未闭环旧单：{{fix_r5_intake.json|legacy_open_ids}}
- 交人工／挂账不占修的：{{fix_r5_intake.json|handoff_quote_len}} 条带卡片原文逐字引文
- 归属规则没模棱两可的（`ambiguous_bare` 必须是空表）：账上有服务端单号缺位的
  {{fix_r5_intake.json|no_server_card_ids}} 张，逐条点名而不是折算

车道（子代理）派单与回执落在 `.fist-loop-20260927/r5_fix_lanes.json`，各条车道的
`scope_declared`（我亲笔写的文件半径）与 `files_reported`（车道自报）都被 `fix_r5_rc.json`
拿 git diff 复算过（逐条复算结果见 {{fix_r5_rc.json|lane_receipts}}）：**报了不等于改了**。三条要单独点名的事实：

1. `lane-codegen` 达到 150 轮上限、没有交付报告 ⇒ 它的交付面一律以盘上实测为准
   （锁文件 `tests/codegen/test_r5_fix_codegen.py` 在 §三 的锁节点档里逐节点复算，`cython_generator.py`
   的 mtime 落在本环窗口内），它的自述「我正在实现」不作证据；
2. `lane-cli-hook` 自报只动 `cypyc/cli.py`、`cypy_hook/hook.py` 与新增 `tests/cli/test_r5_fix_cli_hook.py`，
   并逐张给出修前红原文；它同时报了两处「没修完」：BUG-88 的症状 2（编译顺序仍打全集，
   根因在 `cypyc/project/project_compiler.py:722`，不在它半径内）与 BUG-85 的 `-v` 全量面
   （要真编译才能钉）；
3. 我自己也占两条车道：`lane-commander`（BUG-76 修好后 R4-推进 钉住的那格形状必然翻红，该格的注释
   自己写着「修好后这两格会红 ⇒ 与关账同批走」，所以钉档翻转在关账这一批做，逐字交代见 §六）；
   `lane-commander-identity`（BUG-90 的调用方接线那一半 + 新单 BUG-91，逐字红字与双向 A/B 见 §八 第 13/14 条）。

## 三、锁先行

每单一条会失败的锁，跑到**断言级红**才动实现。红不是我说红：

- 有锁的单：{{fix_r5_locks.json|locked_ids}}（无锁的逐条在 {{fix_r5_locks.json|locks_missing}}）
- 锁节点总数：{{fix_r5_locks.json|lock_nodes_total}}（条数从 pytest 的 `-v` 输出现读，
  且加了「collected 数 = 解析到的节点数」的对账门——参数化 id 里带空格时旧正则悄悄丢过 13 条）
- 修前红（通道 A：`git archive HEAD` 快照树 + 本轮测试复算）：{{fix_r5_locks.json|lock_red_before}}
- 修后绿（通道 A′：当前树）：{{fix_r5_locks.json|lock_green_after}}
- 断言级红（收集错、import 错、夹具崩一律不算）：{{fix_r5_locks.json|assertion_level_red_only}}

四条独立红通道并存，任何一条单独都不够：A=HEAD 快照复算、B=车道留下的逐字红日志、
C=卡片里的修前观察原文、D=回退矩阵（§四）。A 通道对「本环中途才出现的缺陷」天然测不到
（HEAD 上没有那条锁），所以 `lock_green_on_head` 那一栏如实记下来，不假装 A 一路包打。

三条反证：HEAD 树探针（同一份码必须数出 19 条 PASS）、幽灵节点（不存在的 nodeid 必须
`no tests ran` 且 rc=4）、collected 与解析节点数相等。缺任何一条，「全红」和「全绿」都可能是
测量器自己坏了。

## 四、根因合并修与回退矩阵

改动点用 `git numstat + ast` 反解成 `file::symbol`，条数
{{fix_r5_rc.json|change_points}}，引用符号 {{fix_r5_rc.json|symbols_referenced}}，
合并后的根因组 {{fix_r5_rc.json|merged_root_cause_len}}。同族根因共用同一处修法：
binop 优先级表、defer 出口搬迁、comptime 求值契约、builtin 名集、argparse 播种、hook 首行读取。
守恒门是「每个文件归到符号的改动行数 = 该文件 diff 新增行段数」，不吞行也不造行。

回退矩阵（法④）这一版把摘回单元从「卡片点名的文件」改成「本环改过的每一个产品文件」，
先逐文件探针测承重，再按实测承重闭包合组复扫：

- 摘回单元：{{fix_r5_revert.json|extras.units_probed}}
- 每个单元打红了哪些单的锁：{{fix_r5_revert.json|extras.bearing}}
- 没有一张单的锁承重的产品文件（必须空表）：{{fix_r5_revert.json|extras.unborne_files}}
- 卡片点名面与实测承重面不一致的文件（归属差，逐条点名）：
  {{fix_r5_revert.json|extras.declared_face_not_bearing}}
- 矩阵条数：{{fix_r5_revert.json|matrix_rows}}（= 认领单数；没产品码改动的单也占一行写 not_measured）
- 摘回后变红的单：{{fix_r5_revert.json|revert_red_ids}}；断言级：{{fix_r5_revert.json|assertion_level_ids}}
- 组间牵连（必须空表）：{{fix_r5_revert.json|collateral}}
- sha 复原：{{fix_r5_revert.json|sha_restored}}/{{fix_r5_revert.json|sha_files_total}}
- 空操作反证（摘一条本环没碰过的文件 ⇒ 所有锁仍须全绿）：{{fix_r5_revert.json|canary_no_op_revert}}
- 副本树身份：{{fix_r5_revert.json|extras.identity}}；真树未被写入：{{fix_r5_revert.json|extras.root_tree_dirtied}}

这一版矩阵的直接收获：BUG-84 的机制栏写着 `type_checker`，实测承重在
`cypyc/analyzer/scope_analyzer.py`；BUG-88 的机制栏写着 `project_compiler`，实测承重在 `cypyc/cli.py`。
按上一版口径这两单会被算成「没改产品码」，现在按实测面入账，并把口径差留在 §八。

## 五、语义变更影响面（正面测，不靠推断）

存量语料 {{fix_r5_impact.json|corpus_total}} 档，同一份输入喂 HEAD 引擎
（{{fix_r5_impact.json|head_tree}}）与当前引擎各跑一遍：

- 「修前可编译 → 修后被拒」（收紧）：{{fix_r5_impact.json|new_rejections_len}} 档 ⇒ 必须为 0，
  有命中就挂账交裁决，不自己放行；
- 「修前无诊断 → 修后有诊断」：{{fix_r5_impact.json|new_diagnostics_len}} 档，清单逐条在场；
- 本环新接受的语料（变宽也要数出来）：{{fix_r5_impact.json|new_acceptances_len}} 档；
- 产物形状变化：{{fix_r5_impact.json|shape_changed_len}} 档（零变化就说明两棵树跑的是同一份码）；
- 需要裁决的档：{{fix_r5_impact.json|corpus_adjudication_files}}；
- 两棵树的 API 面差异如实记录：{{fix_r5_impact.json|api_surface}}，
  因此**分析器诊断面**这一路记 `not_measured`（HEAD 引擎没有 `analyze_only` 这个入口，
  硬跑只会得到一串 AttributeError，那不是诊断面而是通道坏）——见 {{fix_r5_impact.json|diagnostics_channel}}。

## 六、账面闭环

bug 单没有关闭 API，也没有 `[omega:required]`（`report_bug` 发的单本来就没这标记，
服务端 Omega 链对它们不可用是既定语义），所以闭环强度落在三处：**任务库终态**、
**md 追加留档**、**call_log 里真有这些调用**，三向对照必须同源。

- 闭环单（五件交集算出来的）：{{fix_r5_ledger.json|closed_ids}}
- 追加的 FIXED 段：{{fix_r5_ledger.json|fixed_sections}}
- 留 OPEN 的转结段（逐字写明卡在哪）：{{fix_r5_ledger.json|not_fixed_sections}}
- 三向对照不一致项（必须空表）：{{fix_r5_ledger.json|three_way_bad}}
- 账本条目总数不因追加段落而变：{{fix_r5_ledger.json|ledger_total}}

钉档翻转的逐字交代（唯一一处改既有测试）：`tests/test_loop_20260927_advance_r4.py`
的 `test_defer_declared_shape[defer_two_exits]` 原本钉的是 BUG-76 的缺陷形状
（`"pinned_defect"`，`exits=2`、`cleanups=1`），修后实测产物是两个 `return` 前各注入一次
`f.close()`。翻档方式是把判定档换成 `all_exits_cleaned(exits=2, cleanups=2)` 并**逐出口**校验
`return` 前一行确有清理——旧档只数总次数，新档要求每个出口都有清理，覆盖面只升不降。
该格注释自己写着「修好后这两格会红 ⇒ 与关账同批走，不许悄悄把钉住的形状改掉」，
所以这次改动随关账同批、且写进 BUG-76 的 FIXED 段。合成违例对照：把「嵌套 return 前没有清理」
的形状喂给新分支，被抓到（`line 3 prev='if flag:'`），证明新档会红不是恒绿。
其余四处空守卫（comptime / go / typealias / pointer）按纪律保留守卫并逐条交裁决，见 §九。

## 七、基线、红线与半径

三套体系同批复算，地板从上一环实测件（`.fist-loop-20260927/hunt_r5_baselines.json`）反解，
只升不降：

- 地板四栏：{{fix_r5_baselines.json|floors}}（出处 {{fix_r5_baselines.json|floors_source}}）
- pytest：{{fix_r5_baselines.json|pytest}}；collect-only：{{fix_r5_baselines.json|collect}}
- 自研套件：{{fix_r5_baselines.json|suite}}
- e2e golden：{{fix_r5_baselines.json|e2e}}（FAIL/WARN/UNREG 三格为零）
- 三套体系是否全绿：{{fix_r5_baselines.json|three_systems_green}} → {{fix_r5_baselines.json|three_systems_ok}}

红线与半径：

- HEAD：{{fix_r5_baselines.json|git}}（本环不得提交、不得 add，实测暂存区
  {{fix_r5_baselines.json|git.staged}} 行）
- 外部 HEAD 基线 worktree 仍在：{{fix_r5_baselines.json|git.foreign_worktree_present}}
- 冻结面（PROJECT-SPEC/SYNTAX/套件配置/根文档）改动半径：
  {{fix_r5_baselines.json|radius.forbidden_total}}
- 判据件与账本侧写入数（正面证明 mtime 口径是活的）：{{fix_r5_baselines.json|radius.allowed_touched}}

## 八、本环我自己的失效（19 条，判据写错不是产品坏）

1. 本环根任务 `T0r110` 发布时 description 里没拼环标签、也没拼 `[omega:required]`。
   后果：`call_log` 按环标签那一档对本环恒 0 行——那是**过滤器看不见**，不是没开过。
   任务库里 description 发布后没有任何工具能改（120 个工具里没有改 description 的那一个），
   这条错位会一直留着。补法：`fix_r5_calllog_tally.py` 换成「根描述首行指纹档 + ts 窗口档」
   两路对账，实测见 {{fix_r5_calllog_tally.json|fingerprint_channel}}。
   叶子的 Omega 强验证不受影响：`task_plan_deep(omega_strong_verify=true)` 把标记打在子任务上
   （现读 `T0r110.1.1` 的 description 含 `[omega:required]`）。
2. `fix_r5_revert.py` 第一版的节点正则 `::test_(?:bug|r5_(\d{2})_` 括号不配对，
   `re.compile` 当场就炸。写完后只过了 black/flake8 没跑过 ⇒ 说明「lint 过了」不等于「能跑」，
   驱动件也要有起跑证据。现在 `started` 戳与 `self_checks` 条数都进了门禁表。
3. 回退矩阵的第一版按「单」摘回，把整文件的符号集当成单的全部改动，18 行里 14 行报组间牵连
   ——那是假分离不是真耦合。改成「共享文件闭包 + 实测承重闭包」两级并查集后牵连归零。
4. 副本树只拷了 `cypyc/cypy_hook/cypy_bridge/scripts/tests` 五个目录，`tests/cli` 那批锁在
   副本里**连空操作摘回都会红**。是 canary 抓的（「有红就是夹具或环境自己坏了，整套矩阵作废」），
   改成全量复制（跳过缓存/构建产物/别的环的 scratch）后基线 134 节点全绿。
   教训：矩阵的分辨力取决于副本树能不能当环境，不取决于摘回逻辑写得多对。
5. 摘回用文本模式写 HEAD 原文，Windows 工作树是 CRLF、`git show` 给的是 LF，
   于是「复原」永远比不出 sha、`sha 复原 N/M` 一路红。改成按字节写/按字节还原才对。
6. 参数化 id 里带空格（`test_x[a b]`）被旧节点正则静默丢掉，BUG-79 一度数出 0 条节点。
   补了「collected 数 = 解析到的节点数」的等式门才看得见；这类「丢行」不会报错，只会让结论变绿。
7. `fix_r5_rc.py` 的归属口径按卡片机制栏点名的文件算，`scope_analyzer.py`（BUG-84 的真承重面）
   和 `cli.py`（BUG-88 的真承重面）都被算成「没改产品码」。现在 rc 逐条列出
   `product_files_without_card`，归属改由回退矩阵实测承重补上。
8. 影响面第一版把 HEAD 引擎的 `AttributeError` 当成了「修后有诊断」，canary 第一条就红了。
   根因是 HEAD 引擎没有 `analyze_only` 入口。现在只比 `transpile` 面，
   分析器诊断面明确记 `not_measured`，并把这段通道差绑在一条可判红的门上。
9. `lane-codegen` 跑死没有报告。我一度想按「它最后一条自述在实现 BUG-78」入账——
   交付面必须以盘上实测为准，自述一律不作证据。
10. 本环第一次全量基线（08:57Z 起那趟）与第二趟并发跑，pytest 报 1 failed；
    其中 `defer_two_exits` 那格确实是 BUG-76 修好的后果（真实信号），
    但并发污染这件事本身让「谁的数算数」变得不可判——之后一律串行跑全量。
11. 报告门禁表第一版我自己数错了两路口径：`corpus_total` 用全库 glob 得 206（件里是 203，
    因为语料面按 `corpus_dirs` 五个目录），产品文件面用全量 `git diff HEAD` 得 42
    （本环窗口内是 8，因为 HEAD 之后已有五轮的改动没提交）。
    两条门都是「口径没对齐」而不是「数错了」，现在两路都按件里声明的窗口/目录现读。
12. **派单半径越出认领表**：BUG-77 在 `fix_r5_intake.json` 的归属栏是「未认领（转结仍 OPEN）」
    （理由：机制行与修法行都没点名可改文件面），但我给 `lane-tests` 派单时把 77 写进了它的卡面，
    于是它改了 `tests/test_codegen_verification.py` 与 `tests/test_unit_test_modes.py`
    （7 处空守卫收了 3 处）。改动已在盘上，删它等于毁掉已完成的工作，不记等于悄悄改测试
    ⇒ 账本里给 77 追加 `### OUT-OF-RADIUS(R5-修复 越出认领半径)` 段，本单仍 OPEN，
    要不要收这批改法交指挥官裁决（见 §九）。入账数见
    {{fix_r5_ledger.json|out_of_radius_booked}}。

13. **BUG-90 只修了一半，被它自己的锁全数放过**：那张卡的机制栏写着「`CythonGenerator(source_file=None)`
    的默认值从未被任何调用方覆盖」，但车道的锁一律直接构造生成器（`_lower(..., source_file=...)`），
    两个真入口 `CypyHook.transpile_file` 与 `ProjectCompiler.compile_module` 从没被打通。
    结果删掉伪造之后，走文件入口的产物干脆没有身份常量——抓到它的不是 pytest 那 {{fix_r5_baselines.json|pytest.passed}}
    条，是自研套件里 `codegen_module_magic_attrs` 那一条（套件走的是真入口）。「模块有实现有单测 ≠ 入口可用」
    这一环自己又犯了一次，修法与调用面锁见车道 `lane-commander-identity`。
14. **接线之后又新增一单**：产物头注把 Windows 源路径原文写进模块 docstring，单反斜杠被读成
    unicode 转义 ⇒ 项目模式 cythonize 就地 `CompileError`（新单 {{fix_r5_book91.json|bug_num}}，同环已修，
    双向 A/B 与逐字红字见件 `fix_r5_book91.json`，生成器按字节还原 sha {{fix_r5_book91.json|measurement.generator_sha}}）。
    这条在 HEAD 不可达——没有调用方传真路径，所以三套体系都没有它的暴露面；「修一半」的口子
    是接上线之后才现形的。入账三向对照：账本现 {{fix_r5_book91.json|ledger_after}} 条、
    bugs 树 {{fix_r5_book91.json|sqlite_bugs}}、call_log report_bug {{fix_r5_book91.json|calllog_report_bug}}。
15. **我一度想降地板来过关，实际是该补栏**：法⑧ 的门禁把 `fix_r5_drivers_lint.json` 的字节数压在
    `min_chars` 地板上，本环件掉到地板以下。第一反应是地板定高了，核对上一环同位件才发现它带
    逐脚本点名栏，本环只给了一个总数——是证据变薄，不是尺子写错。补上点名栏并加两条守恒门
    （逐档合计 = 总行数、每条输出都落得进清单）后件自然过地板，地板一格没动。
    逐档字节数记在 `fix_r5_needles.json` 的 `file_chars` 栏，门禁表里逐档可见。

16. **法② 的门宽于主张**：`每条锁都必须旧码里红` 写成了无条件门，于是一条只查「卡片在账本里」的
    装饰锁（BUG-73 的 `test_bug73_card_present_in_ledger`）把整套判据判红——而 73 本来就没被任何
    车道交付（cli-hook 的回执自己写着「BUG-73 没有交付条目」）。判据红的是测量器自己，不是产品。
    改成：装饰锁只能落在车道声明的 `undelivered_cards` 名单里，两个方向都不许扩张；
    红按「断言／产品异常／夹具类」三档分栏，夹具类一律判红。现读
    {{fix_r5_locks.json|no_code_lock_ids}}。
17. **法② 的件没把自证红折进 refuse**：`fix_r5_locks.json` 的 refuse 只装显式拒收，红留在
    `self_checks` 里 ⇒ 门禁表第一道「refuse 逐字为空」对这件**恒绿**，12 道自证红了两道件面还是零拒收。
    本环其它件都折叠了，唯独它没折——同一形状在 §八 第 1 条（缺证据被渲染成正文）已经记过一次。
    现在一律折叠，红必须让门禁表看得见。
18. **参数化 id 里的 " - " 把短汇总行截断**：`FAILED <nodeid> - <message>` 用非贪婪切分时，
    `..._keeps_parens[a - (b - c)-a - (b - c)]` 的 message 被切成空串，一条真红被判成「没有承载」。
    改成只在异常名边界上切，并把「空承载」本身留成判红项——这条门今天正是这么抓到的。
    逐档承载分布见 {{fix_r5_locks.json|red_kind_totals}}。

19. **控制跑坏掉时，件里看不到原因**：回退矩阵收尾那次「全量跑恢复绿」的控制跑一度交出
    `collected=-1 / 节点 0`——等式门抓到了红，但件里只存了两个数，没存那一跑的 rc 和尾巴，
    于是「矩阵读不到真相」这句主张连自己为什么读不到都答不上。现在件里带
    `baseline_run` / `restored_run` 的 rc、collected、节点数与输出尾三行，
    数到 0 直接判拒而不是判红。现读 {{fix_r5_revert.json|extras.restored_run}}。

## 九、要谁裁决

交指挥官或人工裁决的，一律只挂账不动刀：

1. 四处**空守卫**保留原样（`comptime` / `go` / `typealias` / `pointer` 相关的
   `if ...: assert` 形状），车道按纪律不删守卫也不放宽断言 ⇒ 要真收就得改产品语义，
   超出修复环授权。
2. BUG-88 症状 2：`result.compilation_order` 是全图拓扑序（`cypyc/project/project_compiler.py:722`），
   裁剪要 project_compiler 侧配合回报 scope ⇒ 本环只把失败原因打全，顺序行仍打全集。
3. BUG-83 残留：`cypyc/parser/macro_expander.py:140-144` 对块形式 `ComptimeStmt.expr` 为 list
   仍抛 `'list' object has no attribute '__dict__'`；CLI 两张脸被分析器诊断提前拦住所以用户看不到。
4. 寻虫环 H06 探针判据过粗（用 `"3" in out` 判 ignored）⇒ 复测要改成逐模块行
   （`main: type check passed` 是否出现），否则修复后仍会被报成 ignored。
5. BUG-30（`<double>` 强转 + 基准重注册）与 BUG-31（口径修法：改措辞 + 改名，不动既有测试）
   按指挥官已裁执行，本环不改判据口径；重注册后的基准以 R5-验证 环实测为准。
6. 交人工的 {{fix_r5_intake.json|handoff_quote_len}} 张单（冻结面 / 不可逆结构改动）一律没占修，
   账本状态没动。
7. BUG-77 的测试面改动是我派单越界产生的（§八 第 12 条）：要么指挥官认下这 3 处收口
   （空守卫→无条件断言），要么我按指示把它们逐条退回原状。本环不自行决定，
   因为这张单本来不在认领栏里。
8. BUG-73（`.pyd` 增量缓存两处各查各的）**本环没有交付**：车道回执自述「73 没有交付条目」，
   唯一那条锁只查账本在场性；本轮实测两次 `compile_to_pyd` 连跑仍是「先报缓存命中、再报缓存未命中」
   且第二次 `.pyd` 被重写。要么下一轮按机制栏做「单一缓存权威 + 编译后登记产物」并配代码级锁，
   要么把这张单改判交人工——本环不自作主张把它算成修完。它留在
   {{fix_r5_ledger.json|leftover_ids}} 里如实转结。

## 十、转结与顺序账

- 本环没修完的单：{{fix_r5_ledger.json|leftover_ids}}，逐张在账本里追加
  `### NOT-FIXED(R5-修复 转结)` 并写明卡在哪道（入账未修是合法终态，不是「没问题」）。
- 顺序：判据件 → 账面闭环 → 报告 spec（门禁条数见 `report_spec_r5_fix.json` 的 `gates_total`）→
  自证 → 渲染一次 → 见证件 → 收口链（16 叶 × omega 全链 + 8 支 + 根上卷）→ `loop_progress.md`。
  渲染次数按 `fix_r5_renders.json` 的记录数算，不按「报告文件存在」；渲染后动一个字都要看得见。
- call_log 对账：本环号段 {{fix_r5_calllog_tally.json|stages}}，
  对照前缀数出 {{fix_r5_calllog_tally.json|control_absent_prefix_rows}} 行（必须 0），
  全库行数 {{fix_r5_calllog_tally.json|total_call_log_rows}}。
  规格点名的 `laya` / `issue_up` 在本 build 里没有同名工具，实际承担者与次数逐条在
  {{fix_r5_calllog_tally.json|spec_named_carriers}}；`report_bug` 这一路本环**有**调用（修复途中立了
  BUG-91），三路计数（ts 窗口 / 卡片 detail 里的环标签 / 入账件自记的 call_log 增量）要同源，
  对照仍用寻虫环同工具计数，不写「已开启」这种没法判红的话。
  实测三路见 {{fix_r5_calllog_tally.json|fingerprint_channel.windows}}。
- 红线：本环零提交、零 `git add`、零冻结面改动；本地 commit + tag 只在 R5 收尾后一次，
  push 一律不做。不可逆动作只挂账。
