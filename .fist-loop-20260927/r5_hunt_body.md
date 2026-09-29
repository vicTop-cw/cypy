## 一、本环做了什么

R5-寻虫 是五轮循环的最后一环狩猎：**只诊断、只入账、零产品码改动**。四张测量电池 + 一张入账件 +
三张基线/驱动面件，八条法逐法独立复算，门禁 {{report_spec_r5_hunt.json|gates_total}} 道由 `report_kit`
与自证件用同一把尺子预跑。

- 语义邻域 {{hunt_r5_faces.json|families}} 带、用例 {{hunt_r5_faces.json|cases_total}} 条，
  变异通道翻转归属 `{{hunt_r5_faces.json|flips_by_mutant}}`，白建通道点名
  `{{hunt_r5_faces.json|unattributed_mutants}}`，本族候选确诊
  {{hunt_r5_faces.json|candidate_total}} 条（R4-修复 把那一层四个根因改掉了，这一层今天
  **没有新候选**——这不是「没看见」，见 §二 的活性证明）。
- 声明面主张 {{hunt_r5_declared.json|rows_total}} 条逐条现读原文 + 当场重测：文档陈旧
  {{hunt_r5_declared.json|stale_total}} 条、真实缺口 {{hunt_r5_declared.json|real_gap_total}} 条、
  按设计撤回 {{hunt_r5_declared.json|withdrawn_design}} 条、没测/仍然成立
  {{hunt_r5_declared.json|not_measured_or_true}} 条。
- 生成面 {{hunt_r5_codegen.json|cases}} 条用例全部成对确诊：`{{hunt_r5_codegen.json|confirmed}}`。
- 真实入口面 {{hunt_r5_cli_face.json|cases}} 条：确诊 `{{hunt_r5_cli_face.json|confirmed}}`，
  未确认 `{{hunt_r5_cli_face.json|unsure}}`（对照两态同观察 ⇒ 只能记未确认，不占号）。
- 入账：卡表 {{hunt_r5_book.json|cards}} 张，账本最大号
  {{hunt_r5_book.json|ledger_before_max}}→{{hunt_r5_book.json|ledger_after_max}}，
  `ns='bugs'` 任务 {{hunt_r5_book.json|sqlite_bug_tasks_before}}→
  {{hunt_r5_book.json|sqlite_bug_tasks_after}}，逐卡在账校验
  {{hunt_r5_book.json|on_disk_keys_len}}/13 命中。

## 二、观察面先证明「看得见」，再谈有没有虫（法①）

`SYNTAX` 声明的六个语义邻域（函数符号被当返回类型 / 普通函数调用不判元数 / 别名与结构字段回调 /
文案形状 / 元数判定上下文 / 类型别名回调）每格都按**文档声明的语义**定期望，而不是按今天跑出什么。

零发现要能被证伪，所以这一步不靠「跑通了就算看见」：三条变异通道各自锚在产品码里
`count==1` 的位置（锚点条数由驱动实测，不是数一眼），把检查改坏后逐格看期望是否翻转。

- 翻转归属：`{{hunt_r5_faces.json|flips_by_mutant}}`（两个通道真的让格子从「符合声明」翻成
  「不符合」），按族分布 `{{hunt_r5_faces.json|flips_by_family}}`。
- 第三条通道 `callback_param` 一格都没翻 ⇒ **它不承载观察性证明**，被逐条点名在
  `{{hunt_r5_faces.json|unattributed_mutants}}` 而不是从表里删掉。上一环踩过「只跑正例的对照冒充
  确诊」的坑，这次的写法是：宁可留一条白建的通道在账上，也不把归属含糊掉。
- 看不见样本的格 `{{hunt_r5_faces.json|blind_spots}}`（空表 = 本环这一层没有暗格，
  这条主张由变异翻转撑着，不是由「没报错」撑着）。
- 但翻转只覆盖到 3/6 族：**没被变异覆盖的族**
  `{{hunt_r5_faces.json|families_without_flip}}` 这三带今天只由格级期望（文档声明的语义）证明，
  没有「把它改坏就一定翻红」的通道 ⇒ 它们的活性主张比另三带弱一档，R5-验证 要补这一档。

## 三、声明面：18 条主张逐条自己重测（法②）

每条先读它自己的定位声明（`file:line` + 逐字引文），再当场重测；子代理给的同名结论只当「去哪儿看」
的线索。口径：文档自述未实现且今天确实没实现 ⇒ `design` 撤回不占号；今天已实现而状态表还写着
未实现 ⇒ `stale-doc`；文档写了不存在的能力 ⇒ `real-gap`；跑不动/要真编译 ⇒ `not_measured`，
**不许写成「没问题」**。

- 撤回与未测栏：`{{hunt_r5_declared.json|withdrawn_design}}` /
  `{{hunt_r5_declared.json|not_measured_or_true}}`（D03 walrus 属设计；D11 是上一环修法①的复验，
  今天 `result.pyd_paths` 真在 dataclass 字段里 ⇒ 记 `doc-still-true`；D18 要真编译，没测）。
- 陈旧与缺口全集点名：`{{hunt_r5_declared.json|stale_or_gap}}`。
- 规模红线实测（PROJECT-SPEC 自己写的 3000 行）：`{{hunt_r5_declared.json|size_lines}}`。
- hook 子命令 `--help` 实读集里文档未列的选项：`{{hunt_r5_declared.json|undocumented_hook_options}}`。
- 观察身份钉死在被测树：`{{hunt_r5_declared.json|identity}}`（防已安装孪生静默顶掉源码树）。

## 四、生成面成对确诊（法③）

每条一个 pos（现象现形）+ 一个同族 ctl（今天行为正确的形状），两档齐全才 CONFIRMED；
`{{hunt_r5_codegen.json|canary}}` 是这条判据的反向证明：期望写反就确认不了、对照方向逐条声明。

机制签名（进账本的键）：`{{hunt_r5_codegen.json|keys}}`。同一批夹具双跑必须一致，
不一致 ⇒ 直接拒判而不是取其中一次。

## 五、真实入口面成对确诊（法④）

观察对象是命令行、退出码、stderr 原文、`sys.modules` 里的 loader 身份、缓存目录实况——
**不用「源码里有某字样」代替调用面**。未确认那条（`{{hunt_r5_cli_face.json|unsure}}`）的
pos 与 ctl 两态同观察，说明这一带整体不可达，归因不了具体缺哪条检查，所以只记未确认、不占号。

确诊的六条：`{{hunt_r5_cli_face.json|keys}}`。

## 六、判据自证与残渣（法⑤）

每道判据都配「坏了必红」的对照；测量面造的目录必须在跑完之后不存在。这一条本环改过口径——
首版 `tmp_left` 采在 `shutil.rmtree(..., ignore_errors=True)` **之前**，于是它既永远非空、
又掩盖了「清理其实失败」的事实（首跑实测留下 21 个目录）。现在先清理（带重试，不吃错误）、
再采样，非空即拒：`{{hunt_r5_codegen.json|tmp_left}}` / `{{hunt_r5_cli_face.json|tmp_left}}`。

needle 严口径同样由独立扫描件测：`{{hunt_r5_needles.json|real_key_len}}/{{hunt_r5_needles.json|checked_len}}`
条全部是被引件里的真键名，前缀式假命中的 canary 抓到
`{{hunt_r5_needles.json|prefix_canary}}` 条。

## 七、入账、基线与半径（法⑥⑦⑧）

号从盘上现数：起点 {{hunt_r5_book.json|ledger_before_max}}（`memory/bugs.md` 里
`^## BUG-\d+ ` 的最大值），入账到 {{hunt_r5_book.json|ledger_after_max}}；每张卡带机制签名、
`file:line` 立单原文、pos/ctl 实测、一键复跑命令与「什么现象不算证明」。二次扫描的
`{{hunt_r5_book.json|duplicates}}` 就是幂等门：重跑一条都不重开，且看得见为什么不开。

三套判据体系同一批复算，地板**从上一环实测件反解**（`{{hunt_r5_baselines.json|floors_source}}`），
四栏 `{{hunt_r5_baselines.json|floors}}`：pytest {{hunt_r5_baselines.json|pytest.passed}} 通过、
收集 {{hunt_r5_baselines.json|collect.nodeids}}、自研套件与 e2e 见判据件；三套同刻为绿
{{hunt_r5_baselines.json|three_systems_green}}。git 红线：HEAD `{{hunt_r5_baselines.json|git.head}}`
未动、暂存 {{hunt_r5_baselines.json|git.staged}} 行；半径按 mtime 正面测出
（`{{hunt_r5_baselines.json|radius.forbidden_total}}` 个禁用面改动，允许面
{{hunt_r5_baselines.json|radius.allowed_touched}} 个）。

驱动面与被测面同等受审：亲笔脚本 {{hunt_r5_drivers_lint.json|drivers_scanned}} 个，硬错
{{hunt_r5_drivers_lint.json|hard_violations}}、软账 {{hunt_r5_drivers_lint.json|soft_total}}
（上一环基线 0，只降不升）。

## 八、本环自身缺陷（16 条，逐条不吞；类别归因写在每条行内，不做没人复核的手数分栏）

1. `report_bug` 的 `severity` 是闭集 `critical/high/medium/low`，我的卡表用了内部口径 P0/P1/P2 ⇒
   13 条 RPC **全部被拒**、账本零写入。回执逐字见 §十一。修法是把闭集校验挪到发单之前（一条都不发，
   避免半账），并配 canary：没映射的档位（P9）必须在本地就被拒。
2. `hunt_r5_declared.py` 的 D11 立单原文 `result.output_files` 在上一环修法①里已经被改掉 ⇒
   needle 找不到 ⇒ 自证门「每行立单原文都在盘上」如实拒绝该条。改成现读 `result.pyd_paths` 并用
   `dataclasses.fields()` 真判字段存在，本条翻成 `doc-still-true`（上一环的修法被独立复验）。
3. `hunt_r5_faces.py` 的活性判据原先钉在 R4 的一条候选上，而那条已被 R4-修复 改掉 ⇒ 判据恒假。
   重做为三条变异通道，其中 `callback_param` 一格都不翻 ⇒ 明写进 unattributed，不静默丢弃。
4. 电池件的 `tmp_left` 语义写错（采在清理前 + `ignore_errors=True` 静默失败），首跑实测留了 21 个
   残渣目录却报告「看起来正常」⇒ 改为清理后复测并可拒判（见 §六）。
5. `hunt_r5_book.py` 的三向对齐原用「跑前后计数差」⇒ 重跑差为 0 就恒红；改成按机制签名逐条
   反解在账存在性（账本 hits≥1、`ns='bugs'` 恰好 1 行、键名去重后回加等于卡数）。
6. 全局改名脚本用 `str.replace` 把 `datetime.datetime.now(...)` 也换掉了：`now_iso()` 的定义体被
   改成 `return now_iso()`（自递归），`py_compile` 抓不出来，靠 flake8 的 F401 才暴露 ⇒
   教训：**脚本化替换之后要跑一次实际调用，不是只 compile**；本轮改成 tokenize 级改名 + 逐处计数。
7. Bash heredoc 吞反斜杠（`\d` 变体被吃成非法转义，`assert` 因此数错命中处数）⇒ 补丁一律先 Write
   成脚本文件再执行。
8. 我给 `T0rPENDING` 占位断言「应有 8 处」，实测 18 处 ⇒ 断言把这次不匹配拦在了写入之前。
9. `hunt_r5_needles.py` 首版按三元组解包 `artifacts`，遇到单测件（只有 键+needle）直接崩 ⇒
   改成容错解包，并把「法条引用了不存在的判据件」独立成一条拒绝。
10. `hunt_r5_report_spec.py` 首版把两张门禁用「入账件里 cards 是列表」的假设写成 `len(...)`，
    实际件里存的是整数 ⇒ 门禁在预跑阶段就会 crash；改为按类型取值，并把「号段」门禁换成
    **两路独立现读**（生成时直读 `memory/bugs.md` 与直查 sqlite），不再引用件里自报的数。
11. 驱动面 lint 的软账基线是上一环实测的 0 ⇒ 本环所有亲笔脚本必须零软账；过程中出现 26 条
    （E501/E741/E127/E128/F841），逐条清完而不是放宽口径或加 `# noqa`。
12. 三套体系全量批与电池并发跑，墙钟被拖到 20 分钟以上（上一环同规模约 13 分钟）⇒ 流程债：
    全量批不与其它测量并发；本轮没因此改判据，只是如实记耗时不可信。
13. **卡表机制签名是我重打的字面量**，不是从判据件取的 ⇒ 13 张卡里 8 张的账本签名与电池签名
    不一致（同一件事两个名字）。账本已落笔不可回改，修法是以电池为权威源、把不一致逐对写进
    `key_alias`（门禁 ⑥-5/⑥-6 钉住），并要求「每个 case 都能在电池里数到一行签名」——
    以后重打字面量会被这道门直接抓住。这条也是我自己写过的「各处重打字面量」告诫的反例。

14. 门禁 ⑫ 首版把「needle 是真键名」写成了「needle 对应的**值** ≥1」⇒ 三条零值测量
    （`blind_spots=[]`、幂等重跑的 `filed=[]`、硬错为 0 的 `hard_violations=[]`）被读成红。
    坏的是公式不是盘面：改成从 `hunt_r5_needles.json` 的 `per_law_real` 逐法数「真键名条数 == 3」，
    另加总覆盖面 `equals 24` 与 `pending_artifacts equals []` 两道（零值合法、假 needle 必红）。
15. `publish` / `laya_decide` / `report_bug` 的 params 里**没有** `task_id`，首版 call_log 对账只按
    号段前缀数 ⇒ 这三个规格点名的能力读数恒为 0，会被读成「本轮没开过」。补按环标签现数的一档
    `ring_tag_calls`（本环 28 行：publish 1、laya_decide 1、report_bug 26＝13 收＋13 拒），
    并配「不存在的标签必数 0 行」对照与逐字分组门（⑪-10…⑪-16 共六道）。
16. **首渲的正文引用了当时还不存在的门禁号**（写了 ⑪-10/⑪-11/⑪-13/⑪-14，实际只有 ⑪-1…⑪-9）
    ⇒ 这是「标题改了正文没改」的同一类错，只不过这次是**结论比证据先写**。补完六道门之后重渲一次；
    渲染次数原先是按「文件存在」算的（存在性冒充次数），现补 `hunt_r5_render_witness.py` 按序号
    记录每一趟写盘（sha、字节数、门禁道数、note），两次的 sha 都在 `hunt_r5_renders.json` 里。
## 九、要谁裁决

- appendix-C 特性状态表 8 行 `stale-doc` 与 USAGE 三处口径：改文档，还是把「未实现」重新标回？
  本环一个字没改（冻结面与 docs 都在禁改清单里）。
- `real-gap` 3 条：`i32/i64/...` 类型面、`--compile`/`build --incremental` 组合、3000 行规模红线
  被 parser/cython_generator/type_checker 三个文件越过 ⇒ 越线拆分是不可逆动作，只挂账。
- H02 那条未确认候选：需要人来判定是夹具不可达还是环境缺件，本环不猜。
- BUG-74/75（上一轮入账未修）与本轮 BUG-78..90 的修属排序：全部交 R5-修复。

## 十、转结

- R5-修复：BUG-78..BUG-90 十三张新单 + BUG-74..77 四张旧单 + 生成面那批「已声明未实现」的
  裁决面（§九）；复跑命令见每张卡的 detail 段。
- R5-验证/打磨/推进：本轮转结的三条流程债（并发跑全量批、脚本替换后只 compile、
  needle 只按子串校）都要在各自环节被自己的判据接住。
- 交人工：`{{hunt_r5_declared.json|stale_or_gap}}` 共 15 条声明面主张，逐条去向见 §九。

## 十一、规格点名工具的实际承担者与被拒原文

`omega 强验证 / laya / issue_up / call_log` 四件事的计数只从 `call_log` 现数，两条口径都要写清：
带 `task_id` 的调用按号段前缀数（本环 `T0r96` = `{{hunt_r5_calllog_tally.json|stages.T0r96.rows}}` 行，
逐工具分布 `{{hunt_r5_calllog_tally.json|stages.T0r96.by_tool}}`）；而 `publish` / `laya_decide` /
`report_bug` 的 params 里**没有** `task_id`，只有环标签，所以按前缀数它们恒为 0——那不能读成"没开过"。
本环标签 `{{hunt_r5_calllog_tally.json|ring_tag_calls.tag}}` 下按标签现数的真值是
`{{hunt_r5_calllog_tally.json|ring_tag_calls.total}}` 行，其中成功
`{{hunt_r5_calllog_tally.json|ring_tag_calls.ok}}`、被拒 `{{hunt_r5_calllog_tally.json|ring_tag_calls.refused}}`。

- 工具面（不是 sqlite 直读）能否看到这些调用：`call_log` 工具本轮真打了一次，
  回包 `{{hunt_r5_calllog_tally.json|call_log_tool_probe.rows_returned}}` 行、含本环号段
  `{{hunt_r5_calllog_tally.json|call_log_tool_probe.rows_containing_stage}}` 行（sqlite 同口径
  `{{hunt_r5_calllog_tally.json|call_log_tool_probe.sqlite_rows}}` 行）。
- 跨环正例对照：`{{hunt_r5_calllog_tally.json|stage_seed_rows.scope}}`，共
  `{{hunt_r5_calllog_tally.json|stage_seed_rows.total}}` 行；不存在的标签数出
  `{{hunt_r5_calllog_tally.json|ring_tag_calls.absent_control_rows}}` 行（证明过滤器不恒真）。

被拒原文（逐字，来自 `call_log` 的 `result_json`，按原文去重分组；本环 13 次 `report_bug` 拒收
全部在此，不按标签挑两条代表）：

{{hunt_r5_calllog_tally.json|ring_tag_calls.refusals_md}}

去重后 `{{hunt_r5_calllog_tally.json|ring_tag_calls.distinct_refusal_texts}}` 组、合计
`{{hunt_r5_calllog_tally.json|ring_tag_calls.refused}}` 次。

号段前缀那一档（收口链）的被拒原文同理由 `call_log` 反解，本环
`{{hunt_r5_calllog_tally.json|distinct_refusal_texts}}` 组、`{{hunt_r5_calllog_tally.json|stages.T0r96.refused}}` 次：

{{hunt_r5_calllog_tally.json|refusals_md}}

- 其余本轮被抓到并当场改正的判据原文（`severity=P2` 的闭集拒收全文、账本号不连续、
  needle 在 `docs/USAGE.md` 里连子串都不是）不在最终判据件里——它们在收口前就被改正，
  逐字文本只保留在 `.fist-loop-20260927/loop_progress.md` 的本环条目，不回灌本报告正文。
- 收口链（16 叶 × omega 全链 + 根上卷）若在渲染后被拒，原文只进 `.fist-loop-20260927/loop_progress.md`
  与本节的最终版收口件，不回灌本报告正文。
