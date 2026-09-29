## 一、这一环做了什么，以及没做什么

R4-推进（根任务 `T0r93`，执行人 `cypy-advancer`）的半径由指挥官裁定为**「只补已声明未实现」**，
所以本环的产品改动只有两档分析器：
`{{advance_r4_baselines.json|radius.product_by_mtime_this_ring}}`
（mtime ≥ `{{advance_r4_irreversible.json|ring_start}}` 的产品文件数出来的，不是从 diff 里读的）。
冻结面 `{{advance_r4_baselines.json|frozen_total}}` 个文件 sha 变更表
`{{advance_r4_baselines.json|frozen_changed}}`，冻结面 porcelain 脏行按 mtime 归因后
落在本环窗口内的 `{{advance_r4_baselines.json|frozen_dirt_in_ring}}`、无解释的
`{{advance_r4_baselines.json|frozen_unexplained}}`，文档栏 `{{advance_r4_baselines.json|radius.docs}}`，
tests 栏只新增一个锁文件 `{{advance_r4_locks.json|new_test_file}}`。
HEAD 仍是 `{{advance_r4_baselines.json|git.head}}`，暂存区 `{{advance_r4_baselines.json|git.staged}}` 行。

本环真做了六件事，每件由一个可复跑判据件承重，正文数字一律从件里反解：

1. 法①：`Never` 落到分析器名称面，文档工作例真跑 CLI；
2. 法②：`repr/open/iter` 三个「文档在用、名称表缺席」的内建名补齐——放行 `open`
   随即激活一条休眠测试，按指挥官裁决把它的期望改成声明面语义（见 §三·B）；
3. 法③：半径外的运算子与类型面量化成三态表，四条缺陷真入账成卡
   （BUG-74/75 由量表钉住，BUG-76/77 由 §三·B 的后果件钉住）；
4. 法④：补口固化成永久回归锁，改前码档必红；
5. 法⑤⑥：同一趟两棵树扫描回答「产物动没动」与「语料有没有新增红」；
6. 法⑦⑧：三套体系 + 冻结面 + 半径同刻复算，不可逆动作零执行。

没做的：不动 `PROJECT-SPEC/`、`SYNTAX/` 的冻结语义；不重注册 golden；不 `git add/commit/push`；
不删文件也不删别人的 worktree；不删既有测试（唯一被改的断言是指挥官裁决的那一条，
去掉守卫之后判据更硬，见 §三·B）；不放宽任何判据；**不顺手实现半径外的形状**
（`^`、`~`、`*char`、`let` 强制不可变、`defer` 的异常路径安全都在挂账表里，本环不动手）。

## 二、法①：`Never` 只补名称表，产物走既有映射

夹具 `{{advance_r4_never.json|cases.0.probe}}` 逐字取自
`{{advance_r4_never.json|doc_source}}` 第 125-133 行的工作例（原文整段存在件里
`advance_r4_never.json|doc_quote`）。两棵树跑同一批夹具（字节自证），
改后各档 rc `{{advance_r4_never.json|cases.1.after.rc}}` 序列与改前
`{{advance_r4_never.json|cases.1.before.rc}}` 序列逐档点名在件里；
文档工作例的产物签名是 `{{advance_r4_never.json|worked_example_from_doc.after_pyx_signature}}`
——`Never → NoReturn` 这条映射早就在 `cypyc/codegen/type_mapper.py` 里，本环一行 codegen 都没动。

三格 canary：`{{advance_r4_never.json|canary.never_now_accepted}}`（放行新名）、
`{{advance_r4_never.json|canary.bogus_names_still_rejected}}`（`NeverX`/`repx` 仍被拒）、
`{{advance_r4_never.json|canary.red_moves_only_in_name_table}}`（改前的红因全是 `Undefined name`）。

参数位的 `Never` 只做记录不写成主张：件里 `annotation_kept_in_pyx` 实测为否——
产物把参数注解丢了（`def needs_never(x):`），所以本环的主张止于「名称面不再误判」，
**不主张「已支持参数位 Never」**。

## 三、法②：三个内建名的「文档在用」是量出来的

`{{advance_r4_builtins.json|added}}` 三个名字的声明面引用行：
`{{advance_r4_builtins.json|doc_evidence.0.cited}}`、
`{{advance_r4_builtins.json|doc_evidence.1.cited}}`、
`{{advance_r4_builtins.json|doc_evidence.2.cited}}`（合计
`{{advance_r4_builtins.json|doc_evidence.0.doc_hits_total}}` 等三档调用点数在件里）。
改前两态 rc 见 `advance_r4_builtins.json|added_rows`，改后全部放行。

反面同量：`{{advance_r4_builtins.json|not_added}}` 六个内建名在冻结语料里的调用点数是
`{{advance_r4_builtins.json|not_added_rows.0.doc_call_sites}}`（六档全为 0），
且它们在改后树里仍被拒——所以「未声明」不是形容词而是一格测量。
canary 五格 `{{advance_r4_builtins.json|canary.undocumented_names_have_zero_doc_call_sites}}`
等全部成立（逐格见件）。

### 三·B 放行 `open` 的后果：一条休眠测试被激活（裁决已执行）

法②把 `open` 补进名称表之后，`tests/test_codegen_verification.py::test_defer_statement`
从「静默空过」变成「真跑断言」并立刻红了。后果件
`{{advance_r4_dormant.json|card_expected_id}}` 用两棵树把这件事钉成测量：

- 改前 `{{advance_r4_dormant.json|activation.before.undefined_open}}` ⇒
  `success={{advance_r4_dormant.json|activation.before.success}}`，产物
  `{{advance_r4_dormant.json|activation.before.code_empty}}`（空）⇒ 测试里的
  `if result.success` 守卫为假，整块断言被跳过；
- 改后 `success={{advance_r4_dormant.json|activation.after.success}}`，而
  `try:{{advance_r4_dormant.json|activation.after.has_try}}` /
  `finally:{{advance_r4_dormant.json|activation.after.has_finally}}`。

那条断言要求的是 **超出声明面** 的形状：冻结文档
`{{advance_r4_dormant.json|doc_basis.0.file}}:{{advance_r4_dormant.json|doc_basis.0.lines}}` 与
`{{advance_r4_dormant.json|doc_basis.1.file}}:{{advance_r4_dormant.json|doc_basis.1.lines}}`
只承诺「函数退出时自动执行 / 多 defer 逆序」，两处都没有 try/finally 或异常路径字样
（`{{advance_r4_dormant.json|doc_basis.0.try_or_finally_declared}}` /
`{{advance_r4_dormant.json|doc_basis.1.try_or_finally_declared}}` 两格都是 False）。
2026-09-28 指挥官裁决：**改测试期望为声明面语义，不动产品码**。执行结果——

- 去掉守卫、改成无条件断言（函数体逐字在件的 `test_patch.body_after` 键里；正文不整段
  引用，免得一段代码打断行文），判据因此**变硬**而不是放宽；
- 4 档形状实测：`{{advance_r4_dormant.json|shapes.0.moved_to_end}}`（单 defer 搬到体末）、
  `{{advance_r4_dormant.json|shapes.1.reverse_order}}`（多 defer 逆序）、
  `{{advance_r4_dormant.json|shapes.2.deferred_before_return}}`（defer 在 return 前声明时
  清理被搬到 return **之前**，这条路可达）——三档今天成立；
- 第 4 档不成立：`{{advance_r4_dormant.json|pinned_defect.exit_paths}}` 个出口只发出
  `{{advance_r4_dormant.json|pinned_defect.cleanup_count}}` 次清理，机制见
  `{{advance_r4_dormant.json|pinned_defect.mechanism}}` ⇒ 入账 **BUG-76**，本环不动
  codegen（异常路径安全也没写进文档，属裁决面）；
- 同款休眠守卫现存 `{{advance_r4_dormant.json|vacuous_guards.count}}` 处
  （`{{advance_r4_dormant.json|vacuous_guards.files}}`），逐条 file:line 在件里 ⇒ 入账
  **BUG-77**，本环一条都不动它们（一次量完再改，避免边改边猜）；
- canary 八格 `{{advance_r4_dormant.json|canary}}`：形状错的必须被拒、切片确实变窄、
  守卫扫描器既看得见也不会把我自己写的注释当成守卫。

## 四、法③：半径外量化成表，量表钉住的卡真入账

`{{advance_r4_scope_face.json|augmented_matrix}}` 12 条复合赋值 +
`{{advance_r4_scope_face.json|binary_matrix}}` 10 条二元/一元表达式 +
`{{advance_r4_scope_face.json|other_faces}}` 两类其他形状，规格取
`{{advance_r4_scope_face.json|doc_source}}` 表格里的等价式（`x = x <op> 3`）与产物逐字比。
三态结果：`silent_wrong` = `{{advance_r4_scope_face.json|silent_wrong}}`
（只有 `^=`：`x ^= 5` 的产物是 `x = 5`，左操作数与运算符一起丢了，而 rc=0 不报错）；
声明了却被响亮拒绝的是 `{{advance_r4_scope_face.json|declared_rejected}}`。
分类器自己配了一红一绿两支对照（合成行必被判 `silent_wrong`、真实的 `+=` 行必不被误判）。

挂账表 `{{advance_r4_scope_face.json|adjudication_queue}}` 逐条给去向。
本环真入账四张卡（键名 `{{advance_r4_filed.json|cards}}`，号
`{{advance_r4_filed.json|filed.0.ledger_number}}`/`{{advance_r4_filed.json|filed.1.ledger_number}}`/
`{{advance_r4_filed.json|filed.2.ledger_number}}`/`{{advance_r4_filed.json|filed.3.ledger_number}}`）：
前两张由量表钉住（静默产错码 high、`^`/`~` 词位不可达 medium），后两张由 §三·B 的后果件钉住
（defer 多出口漏清理 high、休眠守卫 medium）。判据件里预先点名的号
`{{advance_r4_filed.json|pinned_card_ids}}` 与实际落账号逐一对上，号不连续就拒发；
账本最大号 `{{advance_r4_filed.json|ledger_before_max}}`→`{{advance_r4_filed.json|ledger_after_max}}`，
sqlite bug 任务 `{{advance_r4_filed.json|sqlite_bug_tasks_before}}`→
`{{advance_r4_filed.json|sqlite_bug_tasks_after}}`（md 与库两栏同判，两张表都数一遍）。
为什么不修：`^` 与 `~` 单独出现时被词法器恒定判为构建块词位
（`cypyc/parser/lexer.py:955-973`、`cypyc/parser/parser.py:3796-3800`），
而 `^:`（`SYNTAX/13-build-blocks.md`）与 `~:` 是冻结语义——消歧要动解析器与冻结面，
超出「只补名称表」的安全半径，交 R5-修复带回归锁处理。

## 五、法④：永久锁与它的承重证明

`{{advance_r4_locks.json|new_test_file}}` 由
`{{advance_r4_locks.json|generator}}` 从 `{{advance_r4_locks.json|sources}}` 四份量件套反解生成
（探针与 defer 源逐字取自 `.fist-loop-20260927/advance_r4_probe/` 与后果件）。
条数与「改前该红的 id 名单」写在 `{{advance_r4_locks.json|lock_plan}}` 里，由生成器按
反解到的条目数算出（本文件 `{{advance_r4_locks.json|expected_tests}}` 条），
`{{advance_r4_locks.json|plan_prefix_red_ids}}` 就是改前码档应当红的那几行——
实测红点与它**逐字相等**才算承重（`{{advance_r4_locks.json|canary.red_list_exact_match}}`），
两边各数一遍，谁手打 20/26 都会被对方打回。工作区档
`{{advance_r4_locks.json|lane_work.summary_line}}`，改前码档
`{{advance_r4_locks.json|lane_prefix_code.summary_line}}`，红点
`{{advance_r4_locks.json|lane_prefix_code.red_ids}}`。
身份：`{{advance_r4_locks.json|identity.work_type_checker_sha}}` ≠
`{{advance_r4_locks.json|identity.snap_type_checker_sha}}`，锁文件两棵树同 sha
`{{advance_r4_locks.json|identity.lock_sha_work}}`。
收集 `{{advance_r4_locks.json|collect_after_locks}}` =
上一环地板 `{{advance_r4_locks.json|previous_round_collect_floor}}` + 本环新增
`{{advance_r4_baselines.json|locks_added_this_ring}}`（地板原文：
`{{advance_r4_locks.json|floor_source}}`），
并与「过+红+错」以及收集到的 id 全集互证（`-q` 不打印 collected，收集数只走
`--collect-only`：`{{advance_r4_locks.json|lane_collect.collect}}` 条，与 plan 全集逐字对齐见
`{{advance_r4_locks.json|canary.collected_ids_equal_plan_universe}}`）。

## 六、法⑤⑥：一趟扫描同时回答「产物动没动」和「有没有新增红」

`{{advance_r4_codegen_diff.json|files_compared}}` 档 `examples/*.cypy` 在两棵树上各转译一遍，
剔除时间戳类行（`{{advance_r4_codegen_diff.json|volatile_prefixes}}`）后逐字相同的有
`{{advance_r4_codegen_diff.json|all_textual_identical}}` 档，
无理解释的差异 `{{advance_r4_codegen_diff.json|differing_unjustified}}`。
语料新增诊断行的文件 `{{advance_r4_corpus.json|files_with_new_errors}}`，
诊断反而变少的 `{{advance_r4_corpus.json|files_with_errors_gone}}`。

「零新增」这件事先看尺子看不看得见样本：
`{{advance_r4_corpus.json|witnesses.0.witness}}` 两态产物不同（before rc
`{{advance_r4_corpus.json|witnesses.0.before_rc}}` → after rc
`{{advance_r4_corpus.json|witnesses.0.after_rc}}`），
`{{advance_r4_corpus.json|witnesses.1.witness}}` 两态都报且产物相同——两支都在位，
上面那个空表才不是空集蒙出来的。

## 七、法⑦：三套体系、冻结面与半径

pytest `{{advance_r4_baselines.json|systems.pytest.passed}}` 通过 /
`{{advance_r4_baselines.json|systems.pytest.failed}}` 失败 /
`{{advance_r4_baselines.json|systems.pytest.errors}}` 错误
（地板 `{{advance_r4_baselines.json|floors.pytest}}` = 上一环实测
1976 + 本环新增锁数）；收集 `{{advance_r4_baselines.json|systems.collect.nodeids}}`
（地板 `{{advance_r4_baselines.json|floors.collect}}`）；
自研套件 `{{advance_r4_baselines.json|systems.suite.fields.Total}}` 条；
e2e golden PASS `{{advance_r4_baselines.json|systems.e2e.PASS}}`、
FAIL `{{advance_r4_baselines.json|systems.e2e.FAIL}}`、
RUNFAIL `{{advance_r4_baselines.json|systems.e2e.RUNFAIL}}`、
WARN `{{advance_r4_baselines.json|systems.e2e.WARN}}`。三套同刻为绿
`{{advance_r4_baselines.json|three_systems_green}}`。
脏行 `{{advance_r4_baselines.json|git.dirty_rows}}`（相邻两轮都未提交，
diff-vs-HEAD 分不开轮次 ⇒ 只作清单级记录，轮次归因用 mtime）。
冻结面的 porcelain 脏行 `{{advance_r4_baselines.json|frozen_dirty_mtime}}` 不是「为空」判的：
落在本环窗口（mtime ≥ `2026-09-28T03:00:00+00:00`）内的 `{{advance_r4_baselines.json|frozen_dirt_in_ring}}` 条，
无解释（既不早于本 loop 开工、sha 又不等于上环记录）的 `{{advance_r4_baselines.json|frozen_unexplained}}` 条；
归因尺子自己的两侧对照（刚写的行必须被抓、loop 前的行必须被放）在
`{{advance_r4_baselines.json|frozen_canary_rows}}`，canary 六格
`{{advance_r4_baselines.json|canary}}`。

驱动件面：本轮亲笔 `{{advance_r4_drivers_lint.json|drivers_scanned}}` 个脚本，硬错
`{{advance_r4_drivers_lint.json|hard_violations}}`、软账 `{{advance_r4_drivers_lint.json|soft_total}}`
（基线 `{{advance_r4_drivers_lint.json|previous_round_soft_baseline}}`，只降不升）；
生成的锁文件超长 `{{advance_r4_drivers_lint.json|generated_lock.e501}}` 行 ≤
上一环同类件 `{{advance_r4_drivers_lint.json|generated_lock.previous_ring_e501}}` 行。

## 八、法⑧：不可逆动作零执行

产品面：删除/改名 `{{advance_r4_irreversible.json|product_bad_status}}`，
本环未跟踪新增 `{{advance_r4_irreversible.json|product_untracked_new}}`；
既往遗留的未跟踪产品文件 `{{advance_r4_irreversible.json|product_untracked_all}}`
照列不拒判（拒判只会逼人删别人的文件）。
账本面自 `{{advance_r4_irreversible.json|ring_start}}` 起共 `{{advance_r4_irreversible.json|rpc_rows}}`
次调用，工具集 `{{advance_r4_irreversible.json|rpc_tools_since_start}}`，
archive 目标 `{{advance_r4_irreversible.json|archive_targets}}`，
判定 `{{advance_r4_irreversible.json|verdict.destructive_tools}}` /
`{{advance_r4_irreversible.json|verdict.foreign_archive_targets}}`。
检测器自带三条合成对照（`{{advance_r4_irreversible.json|canary.two_negative_controls_caught}}` 等），
抓不到就自判坏——「零不可逆」这句话因此不是姿态。

## 九、账与能力面（call_log 反解，不按标签、不按回忆）

发单前本环前缀 `{{advance_r4_calllog_tally.json|rows_T0r93}}` 行 /
`{{advance_r4_calllog_tally.json|distinct_tasks}}` 个任务，被拒
`{{advance_r4_calllog_tally.json|stages.T0r93.refused}}` 条；
不存在的对照前缀数出 `{{advance_r4_calllog_tally.json|control_absent_prefix_rows}}` 行
（过滤器不恒真）。规格点名的四项能力按承担者记账：
`{{advance_r4_calllog_tally.json|spec_named_carriers.laya.this_stage_total}}` 次
`laya_decide`、`{{advance_r4_calllog_tally.json|spec_named_carriers.issue_up.this_stage_total}}`
次 `publish`/`report_bug`、omega 链三工具
`{{advance_r4_calllog_tally.json|omega_chain_by_tool}}`。
`laya_decide` 在本 build 回 `available:false` ⇒ 按模板显式降级为规则式自决
`split_n=8`（每条法一支），这一条是实测不是叙述。
整条循环的根任务逐根点名在件里 `advance_r4_calllog_tally.json|loop_roots`。

## 十、本环我自己的失效（24 条，逐条：现象 → 我错在哪 → 改成什么才承重）

1. 参数位 `Never` 的期望写成「rc 与改前一致」，实测改前 1、改后 0 ⇒ 判据被自己打回。
   错在把「不许新增误判」写成「不许改变行为」。改成「名称面不再报 `Undefined name`」，
   产物是否保留注解按实测记录，不升格成语义主张。
2. 探针夹具最初写到 `.fist-loop-20260927/` 根目录，CLI 报「读取文件错误: No such file」⇒
   我先怀疑路径形状不支持绝对路径，实为自己写错了落盘目录。改为统一落在
   `advance_r4_probe/`，并在 lib 里加 `stage_probe`（复制进树内 + 相对路径喂 CLI）。
3. ANSI 色码混进诊断解析 ⇒ 「Undefined name」被 `\x1b[…m` 打断。加 `ANSI.sub` 后复测。
4. 用 `… | tail -3` 之后取 `$?` 得到 rc=0，把一次 rc=1 的转译失败记成成功 ⇒ 老坑重踩；
   改成 `subprocess` 直接取 `returncode`，管道不进判据。
5. `git status --porcelain` 的全部行被我当成「未跟踪新增」⇒ 42 个已跟踪修改文件被读成本环新文件，
   判据当场假红。改成只认 `??` 前缀，并补三条对照（合成 `??` 必被抓、` M` 必不被抓、
   把起点推到未来就不许还数到今天写的文件）。
6. FIST 服务端被上游 03:20Z 重建：旧入口 `cmd/main/main.js` 成了裸 ESM 崩，
   我的 `report_bug` 全部 `stdout closed (EOF)` ⇒ 我一度把它当成派单机制坏了。
   真因在客户端入口（`cmd/cli/cli.js serve`）。两轮 fail-closed 保证零副作用
   （`refuse` 非空 ⇒ 没落任何半张卡，sqlite 增量 0 可查），换完入口直接重跑即得正确号。
7. 换入口只改了 `lfist_lib.Client` 不够：手工探针 `lfist.py` 走 `pfist.main()`，
   它读模块全局 `Client` ⇒ 「修了还是 EOF」的假结论。补 `pfist.Client = lfist_lib.Client`，
   并用一次真 `list` 调用而不是 import 成功来复验。
8. 锁的承重证明第一版用 pytest header 的 `rootdir:` 行证明「跑在哪棵树」，
   而 `-q` 根本不打印 header ⇒ 两条恒假判据。改成 `identity_probe`（模块解析到哪个目录）
   + 两棵树 `type_checker.py` sha 不同 + 锁文件同 sha 三件一起证。
9. 同版还把 `-q` 输出里含 `::` 的行数当收集数 ⇒ 工作区档得 0、改前档得 7（那 7 行是 FAILED 行），
   「少收＝用例静默消失」的格差点把解析器坏了报成产品坏了。改成
   `--collect-only` 单独一趟 + 「过+红+错 == 收集数」的基数自证。
10. 生成器第一版用 `re.sub(r"\W","",op)` 造夹具名，`&= | = ^= <<=…` 全被压成同名文件 ⇒
    12 条复合赋值差点测成同一份源。改成 `aug%02d`/`bin%02d` 索引命名，并在两棵树读同一份
    夹具时断言字节相等。
11. 生成器 docstring 里残留一行 ``` 围栏与反引号转义，触发 W605（硬错码）⇒ 由驱动件 lint 打回；
    改为纯文本并去掉转义。
12. `scope_face` 第一版把「六个未声明内建名」写成形容词，没有实测支撑 ⇒ 补
    冻结语料里 `name(` 调用点计数（六档全 0）并加第五格 canary，让「未声明」这个词可红。
13. 计划文件 `spec_r4_advance.json` 在建树派单之后才补 `needle_verification` 块
    （laws/fingerprint 未动）⇒ 盘上计划与建树回包存在一次漂移，只能记流程债：
    归档后不可 reopen，这条不能事后补。
14. 亲笔驱动件第一版有 12 条 E501/E127 与 3 条 F841 ⇒ 由本轮 `drivers_lint` 打回，
    用锚定补丁逐行改（没交整档 formatter，避免把 1885 行噪声那种事故重演）。
15. 报告 spec 第一版含 `min: 0` 的门禁（被拒原文分组数）⇒ 恒真格；自证件「不许有 min=0」会拒。
    换成 `total_call_log_rows` 下限 + `grouped_by` 结构门两条会红的判据。
16. 把 `advance_r4_render_order.json`（渲染之后才存在）写进 artifacts 清单 ⇒
    「清单里的件都在盘上」在渲染前恒红，正是上一环点过的顺序倒置。从清单里摘掉，只留 `.py`。
17. 法⑦的冻结面判据第一版写成「porcelain 与 sha 两栏都必须为空」⇒ 被 3 条 09-26 的历史脏行
    打回（tracked 的 `M` 行是相对 HEAD 而言，本 loop 各轮都没提交，全都算脏）。这种口径既
    证真不了也证伪不了本环的动作：脏状态在，改动却不在。改成三格——上环记录的
    `{{advance_r4_baselines.json|frozen_total}}` 个 sha 逐字节未变、本环窗口（mtime）内无脏行、
    每条脏行给解释（早于 loop 开工或 sha 与上环相等），再配一新一旧两条合成行 canary 证明这把
    尺子两侧都会动。同一件里 `radius` 拿 `rglob` 的绝对路径去比相对名单 ⇒ 恒红，改
    `relative_to(ROOT).as_posix()` 后才对上。
18. `defer` 的四个形状夹具第一版调了未定义的名字（`say`/`f` 都没定义）⇒ 两棵树**都**被拒，
    「改前改后产物逐字相同」于是拿两个空串相比，恒真。错在我把「判据跑通了」当成「判据有意义」：
    空产物也能满足等式。改成每个夹具自带定义、并在件里钉住两态的 rc 与诊断行数，另加一格
    `predicate_rejects_wrong_shape` 的合成违例，证明这把尺子对错的形状会红。
19. `moved_to_end` 第一版在产物里找 `"f.close()"` 双引号字面量 ⇒ 恒 False：emitter 会把字符串
    常量归一成单引号。错在拿源里的写法去比产物的写法。改成从源反解出单引号形态再比，
    并把 False 的结果留成一次红（而不是悄悄放宽）。
20. canary 里写了 `"try:" in code_a is False` ⇒ Python 链式比较，整式恒 False，
    「守卫自己坏了」被冒充成「断言通过」；同一件的守卫扫描器还把我自己的注释文本数了进去
    （8 处 vs 实测 7 处）。改成显式布尔 + 只统计语句行，并补 `guard_scanner_not_fooled_by_comment_mention`
    与 `slicer_narrows_to_target_function` 两格，让「抓到自己的注释」这件事可复跑。
21. 锁的期望值第一版手写 `[20, 0, 0]` 与一串红名单字面量 ⇒ 测试文件重生成一次就和判据漂移。
    错在把「量出来的东西」又抄了一遍当常量。改成生成器落 `advance_r4_lock_plan.json`
    （条数按反解条目算、红名单按「源里是否用到本轮放行的名字」推），判据两边各数一遍再逐字比，
    并加两格 canary 让「名单不精确等值」「收集到的 id 不等于计划全集」必红。
22. 派单之后手补 `spec_r4_advance.json` 的 `needle_verification` 块时，把一句话写成了
    Python 式的相邻字符串续行 ⇒ 合法 Python、**非法 JSON**，在盘上躺了 90 多分钟没人发现，
    直到渲染前 `report_spec` 重新 parse 才炸。错在「补完没让读它的那条路跑一遍」：
    当时能跑通的件都是补之前跑的。改成单个 JSON 字符串值，并在自证件加三格——
    每份 `advance_r4_*.json` 都能 parse、计划文件本身能 parse、以及「相邻字符串续行」这种
    真出过的违例必红 + 合法 JSON 不误抓；除该值以外 `laws`/`fingerprint` 逐字节未变
    （改前/改后两段切片比对为 `True/True`），建树时用的语义没有漂。
23. 自证件里 `if not (canary["substring_rule_would_pass_control"] and ...)` 读的是**改名前**的键
    （`control` → `canary_prefix` 时只扫了赋值处，没扫消费处）⇒ 一旦跑到就是 KeyError，
    「判据不成立」被降级成「脚本崩了」，而崩不会被任何门禁计数。改成两处消费都用件里的真键名，
    并让新加的 parse 格子复用同一份 `canary` 字典，避免再造第二个命名空间。
24. 驱动件软账清零（23 条 E501/E126/E127/E128/E201/E202/E306）之后，`gen_locks` 自己的 mtime
    晚于它产出的 `advance_r4_lock_plan.json` ⇒ 被过期判据打回。错在把「只改格式」当成零影响改动：
    判据看的是字节与时间，不看我的意图。改成按链重跑 `gen_locks → locks`，
    并钉住生成的锁文件改前/改后逐字节相同（`{{advance_r4_locks.json|identity.lock_sha_work}}`
    = `{{advance_r4_locks.json|identity.lock_sha_snap}}`，两棵树同一份字节），
    所以 §七 那 2002/2002 的实测仍对同一批字节负责，不必重跑 15 分钟的三套体系。

## 十一、要谁裁决（只挂账，本环不动刀）

1. `{{advance_r4_scope_face.json|silent_wrong}}` 的修法要不要立刻进 R5-修复：它是唯一
   rc=0 的静默产错码形状（`^=`），已入账 `BUG-74`。
2. `^` / `~` 与冻结的 `^:` / `~:` 构建块共用词位 ⇒ 放开二元/一元用法需要**语义裁决**
   （消歧规则归谁），已入账 `BUG-75`；本环不动解析器。
3. `*char` 与 `let` 强制不可变两格：都属于「声明了但需要设计」，
   在 `advance_r4_scope_face.json|adjudication_queue` 里标为挂账，不是遗漏。
4. 上一环留下的 8 张缺 `task_id` 卡片与 `BUG-30/31` 之外的冻结面交人工栏，
   状态照旧（本环未派单也未关闭）。

## 十二、转结与顺序账

- 本报告的 16 叶 × omega 全链、8 支与根上卷在渲染**之后**才发：此刻
  `{{advance_r4_calllog_tally.json|stages.T0r93.refused}}` 条被拒是本环发单前的事实，
  收口链的结果与被拒原文一律进 `.fist-loop-20260927/loop_progress.md`。
- 产品改动早于建树派单（03:05 动手、03:50 派单），是本轮的一处顺序倒置，
  已在 §十 13 点名，不进红线也不补派「事后单」。
- 三套体系与冻结面为绿只对本报告时刻负责；下一环开工必须重跑，不得拿本环绿灯抵扣。
- 本环未提交任何东西（`{{advance_r4_baselines.json|git.staged}}` 行暂存），
  单次本地 commit + tag 仍按既定安排放到 R5 收口之后。
