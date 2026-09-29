## 一、本环做了什么

R4-寻虫把狩猎面转向 R1–R3 没系统扫过的三块：函数类型层的其余缺口、`docs/`＋`SYNTAX/` 状态表与
今天实现的分道、`cypy_bridge` 的生成与缓存面。全程 omega 强验证、逐叶归档、issue_up 入账、
call_log 计数；**一行产品码都没改**（半径按 mtime 正面测，见《七》）。

判据件与数出来的东西（件都在 `.fist-loop-20260927/`，逐件自带 refuse 与自证）：

- 上下文覆盖探针 `hunt_r4_probe.json`：{{hunt_r4_probe.json|battery_cases}} 个语句上下文逐个跑，
  变异树差分 {{hunt_r4_probe.json|witness_pos_differ}} 格，残留 {{hunt_r4_probe.json|mutant_left}}。
- 六面电池 `hunt_r4_faces.json`：{{hunt_r4_faces.json|families}} 族 / {{hunt_r4_faces.json|cases_total}} 条，
  与期望不符的候选 {{hunt_r4_faces.json|candidate_total}} 条，看不见分栏 {{hunt_r4_faces.json|blind_spots}}。
- 成对确诊 `hunt_r4_confirm.json`：CONFIRMED {{hunt_r4_confirm.json|confirmed_total}} 条、
  UNSURE {{hunt_r4_confirm.json|unsure_total}} 条。
- 可观察性见证 `hunt_r4_witness.json`：合成载荷打翻 {{hunt_r4_witness.json|w1_flipped}} 条、
  真变异树差分 {{hunt_r4_witness.json|w2_changed}} 条、零发现但可见的族见
  `per_family_visibility`（{{hunt_r4_witness.json|blind_spot_total}} 格看不见被原样记账）。
- 文档面重测 `hunt_r4_declared.json`：{{hunt_r4_declared.json|rows_total}} 条主张，
  其中陈旧或缺口 {{hunt_r4_declared.json|stale_or_gap}} 条、DESIGN 撤回
  {{hunt_r4_declared.json|withdrawn_design}} 条、未测 {{hunt_r4_declared.json|not_measured_or_true}} 条。
- 机制级去重 `hunt_r4_dedup.json`：与盘上 {{hunt_r4_dedup.json|ledger_cards}} 单比对，
  判重命中 {{hunt_r4_dedup.json|duplicates}}，号从 {{hunt_r4_dedup.json|numbering_from_disk}} 起，
  入账单计划 {{hunt_r4_dedup.json|plan_total}} 条。
- 三态复现台账 `hunt_r4_repro.json`：全十条键现形 {{hunt_r4_repro.json|all_exit_codes_zero}}，
  三态各自可达 {{hunt_r4_repro.json|state_reached}}。
- 入账 `hunt_r4_filed.json`：{{hunt_r4_filed.json|filed_total}} 单
  （{{hunt_r4_filed.json|filed}}），账本 {{hunt_r4_filed.json|ledger_before}} →
  {{hunt_r4_filed.json|ledger_after}}。
- 三向对照 `hunt_r4_ledger3way.json`：md／sqlite／call_log 三面一致 {{hunt_r4_ledger3way.json|agree_total}} 条。

身份探针：全部分析跑在工作树 `{{hunt_r4_confirm.json|identity}}` 上——不是安装副本，不是快照残留。

## 二、可见性先于结论：每族一条「必报的对照」

法 4 要求把「零发现」与「看不见」分家，所以每一族先钉一条今天**必然该报**的形状：

| 族 | 对照证明的是 | 结果 | 候选数 |
|---|---|---|---|
| F1 函数名被登记成返回类型 | 返回值与声明不符会被报 | 对照已报 | 3 |
| F2 普通函数元数从不判 | Callback 形参的元数违例在报 | 对照已报 | 2 |
| F3 实参类型兼容 | 实参位置的元数违例在报 | 对照已报 | 3 |
| F4 struct 成员类型 | 局部变量声明类型会流到 return | 对照已报 | 3 |
| F5 文案形状 | 普通类型不符文案存在 | 对照已报 | 1 |
| F6 上下文覆盖 | 最普通语句里的违例在报 | 对照已报 | 0（无候选，但**由变异树证明能看见**） |

F6 这一行的「0」是本环最想留下来的一格：它不是「没缺陷」，而是「能看见、所以确实没有」。
探针侧同样诚实记账——`context_not_visited = {{hunt_r4_probe.json|context_not_visited}}`：
`struct_field_callback` 那一格根本没走到元数判定，因此**不算**在「十六个上下文全覆盖」的证据里。

## 三、四个代码根因（12 条候选按根因归并，不是一个观察一张单）

| 单 | 根因（机制，file:line 级） | 症状 | 严重度 |
|---|---|---|---|
| BUG-61 | 函数名登记成它的**返回类型**，没有可调用签名（`type_checker.py:523-525`，同族 :393-395、:473-475）⇒ 元数判定挂错表 | C01-C05 | high |
| BUG-62 | 实参类型与形参声明从不做兼容性比对：`_visit_Call:1039-1043` 只求类型不比对；同族赋值在 :768 会报 | C06-C08 | high |
| BUG-63 | struct 成员声明类型在方法体里解析不出：`_visit_Attribute:2122` 不查成员登记表 | C09-C11 | high |
| BUG-64 | 类型不符文案内插 `Type` 对象 ⇒ 打印 `Callable[tuple[int], str]`，源语法是 `Callable[[int], str]` | C12 | medium |

最刺眼的一对双向证据（同一基座 `def mk(cb: Callback, n: int) -> Callback`）：正确调用 `mk(one, 1)`
被判「expected 1, got 2」，而少传实参的 `mk(one)` 一声不吭。判定挂的是 `Callback` 的参数表，
函数自己那两个参数全程没参与。产物层零改动（codegen 差分见 R3-推进件，本环未碰生成器）。

## 四、文档与 bridge 面：18 条主张逐条当场重测

子代理只用来指路，下表每条的实测都是本环脚本自己跑的（详文与原文行号在件里）：

| id | 主张所在 | 结论 |
|---|---|---|
| D01 | appendix-C:594 把 `Callable[[T],R]` 列为未实现 | stale-doc（元数判定今天会报） |
| D02 | appendix-C:595 说 `&` 需换成 `｜`/`^` | stale-doc（`a & b` 静态分析零错） |
| D03 | appendix-C:596 walrus `:=` 未实现 | **design 撤回**（去掉 `:=` 的同族形状干净 ⇒ 文档准确） |
| D04 | appendix-C:64 主类型表宣称 `i8/i16/i32/…` | real-gap（`let a: i32 = 12` → expected i32, got int） |
| D05 | appendix-C:264 `mut x: i32` / `*mut i32` 示例 | stale-doc（照抄即词法错误） |
| D06 | appendix-C:33 `cypyc --compile` / `build --incremental` | real-gap（两条 rc=1；对照 `transpile` rc=0） |
| D07 | appendix-C:520 缩进「必须 4 的倍数」 | stale-doc（8 空格被拒、4 空格干净） |
| D08 | USAGE:367 入口点 `cypy_hook.hook:main` | stale-doc（pyproject 实为 `cypyc.cli:main`） |
| D09 | USAGE:19 「Python ≥ 3.8」 | stale-doc（声明文件是 3.9；3.8 兼容性本机测不出 ⇒ 只比一致性） |
| D10 | USAGE §2.6 只列四个 hook 动作 | usage-mismatch（`--help` 里 6 个未记选项） |
| D11 | USAGE:333 示例读 `result.output_files` | example-fails（dataclass 字段集里没有） |
| D12 | USAGE:251 `hook.eval(...)` 返回 42 | example-fails（读侧只认 `__result__`，写侧 0 处产出） |
| D13 | USAGE:404 「constraint/subtype/dispatch 尚未实现」 | stale-doc（前两个当场可解析；dispatch 半句仍准确） |
| D14 | 状态表:106 「SubtypeDecl 均未落」 | stale-doc（`_parse_subtype_def`、`subtype_defs` 都在） |
| D15 | PROJECT-SPEC:42 单文件 3000 行红线 | real-gap（规模见下） |
| D16 | `BridgeCacheManager` 缓存目录查询是只读的 | bridge-side-effect（在调用方 CWD 造目录） |
| D17 | `cypy_bridge` 自述「与 Cython 等价」 | bridge-not-equivalent（生成 C 有模块级语句） |
| D18 | USAGE:406 「缓存命中复用 `.pyd`」 | **未测**（要两次真编译 ⇒ 转结 R4-验证，本环不写结论） |

D15 的规模口径是「剔注释与字符串后的 token 覆盖行数」，实测：
`{{hunt_r4_declared.json|size_lines}}`。D16 的实测目录清单：
`{{hunt_r4_declared.json|cache_dirs_created_in_caller_cwd}}`（探针跑在独立临时 CWD，跑完自删）。
D17 只证到「生成物里有函数外的 `if`」这一半：`{{hunt_r4_declared.json|bridge_module_level_if}}`，
真 MSVC 编译验证转结 R4-验证。D10 的未记选项：`{{hunt_r4_declared.json|undocumented_hook_options}}`。
D12 的写侧命中数：`{{hunt_r4_declared.json|eval_result_symbol_hits}}`（0 处才敢下这条结论）。

## 五、去重与近亲裁决（按机制签名，不按标签）

与盘上 {{hunt_r4_dedup.json|ledger_cards}} 条已入账单比对，机制级判重命中
{{hunt_r4_dedup.json|duplicates}}。撞了代码符号、逐条给过裁决的近亲：

| 新单 | 已入账 | 共享符号 | 为什么不判重 |
|---|---|---|---|
| DOC_status_stale_rows | BUG-32 | constraint / subtype / type_mapper | 它钉 codegen 注释渲染丢用户原文；本条是状态表未回写。与它真正同族的是 BUG-64（渲染层用内部表示），已在 BUG-64 点名交叉复核 |
| DOC_status_stale_rows | BUG-49 | constraint / subtype | 它钉 `SYNTAX/33` 那一行且仍 OPEN；本条覆盖 appendix-C／USAGE／STATUS 另 7 行，行不重叠 |
| DOC_cli_face_mismatch | BUG-48、BUG-54 | build / incremental / transpile | 那两张讲 watch 不产出与 `build/` 并发互踩；本条讲 argparse 里不存在的旗标与未记选项 |
| SPEC_file_size_redline | BUG-42 | parser / cython_generator | 它讲同名方法定义两次成死代码；本条讲文件规模越过自己定的阈值；将来拆分时顺手消掉 BUG-42 |
| BRIDGE_cache_side_effect | BUG-54 | 路径段（非代码符号） | 同属「中间/缓存落到调用方 CWD」一族，但代码点与修法不同，两单互相引用 |

未归号的两条被点名，不静默吞掉：`{{hunt_r4_dedup.json|unclaimed_reason}}`。

## 六、三态复现台账（入账承诺的命令都真跑过）

每张单的复现命令形如 `python -X utf8 .fist-loop-20260927/hunt_r4_repro.py <根因键>`，
退出码读法 0=现形 / 1=不现形 / 2=夹具坏。本轮十条键全 0，且 **1 与 2 两态在同一批里现取**：
`{{hunt_r4_repro.json|state_reached}}`。

「2」不是装饰：本环真实翻红过一次——`DOC_status_stale_rows` 的 D13 谓词去读
`measured["split_note"]`，而那个字段挂在行上不在 `measured` 里，脚本当场 rc=2；
修完才拿到 0。那次崩溃还暴露第二个问题：错误原因没落到输出行上，第一屏看不见为什么坏。

## 七、基线、半径与账本

- 三套判据体系同一批复算：pytest 通过 `{{hunt_r4_baselines.json|pytest.passed}}`（下限 1938，只升不降）、
  收集 `{{hunt_r4_baselines.json|collect.nodeids}}`、自研套件
  `{{hunt_r4_baselines.json|suite.fields.Passed}}/{{hunt_r4_baselines.json|suite.fields.Total}}`、
  e2e 基准 PASS `{{hunt_r4_baselines.json|e2e.fields.PASS}}` / FAIL
  `{{hunt_r4_baselines.json|e2e.fields.FAIL}}` / WARN `{{hunt_r4_baselines.json|e2e.fields.WARN}}`；
  全绿旗标 `{{hunt_r4_baselines.json|three_systems_green}}`。
- git 红线：HEAD `{{hunt_r4_baselines.json|git.head}}`（本环未提交、未 push）、暂存
  `{{hunt_r4_baselines.json|git.staged}}`、脏行 `{{hunt_r4_baselines.json|git.dirty_rows}}`、
  外部 HEAD 基线 worktree 仍在 `{{hunt_r4_baselines.json|git.foreign_worktree_present}}`。
- 改动半径按 mtime ≥ `{{hunt_r4_baselines.json|radius.window_start}}` 正面测：
  产品／测试／冻结面被摸 `{{hunt_r4_baselines.json|radius.forbidden_total}}` 个文件，
  判据件与账本新增 `{{hunt_r4_baselines.json|radius.allowed_touched}}` 个（正面计数，证明口径是活的）。
- 账本三向：md 条目／sqlite bug 任务／call_log 的 report_bug 回执一致
  `{{hunt_r4_ledger3way.json|agree_total}}` 条；bug 树行数
  `{{hunt_r4_ledger3way.json|sqlite_bug_rows}}`；寻虫环 FIXED 段
  `{{hunt_r4_ledger3way.json|fixed_sections_total}}` 个——没修就不许写已修。
- 驱动面自身 lint：本轮亲笔 `{{hunt_r4_drivers_lint.json|drivers_scanned}}` 个脚本，硬错
  `{{hunt_r4_drivers_lint.json|hard_violations}}`，合成违例被抓
  `{{hunt_r4_drivers_lint.json|canary.bad_caught}}`（证明这一格能红），软账
  `{{hunt_r4_drivers_lint.json|soft_total}}` 条（E501 91、E741 16、E128 5）——
  这是我自己写出来的债，列为后续「只降不升」的起点。

## 八、本环自身缺陷（判据类 8 条、操作类 4 条）

判据类：

1. faces 电池第一版把「clean 期望被拒」写成 REFUSE，于是 F1 的假阳性被记成「判据坏了」而不是产品缺陷；
   改成候选／符合预期／夹具非法三栏划分，并加「三栏相加=全部用例」的自证才算对。
2. F5 主张的是文案形状，判定却写成「报没报错」——恒绿了一整轮；单独加 `tuple[` 外泄的形状判据后才抓到 C12。
   同一坑（token-presence 证明不了结构）我这轮又踩了一次。
3. F1 最初的夹具用 `return ""` 冒充 Callback，返回值本身就不合法，把真诊断混进假阳性；
   重做基座 `def mk(cb: Callback, n: int) -> Callback` 才把两件事分开。
4. 去重第一版拿机制文本前 24 字符比对 ⇒ 退化成比文件名，18 张卡被判近亲；改成
   「反引号内代码符号＋路径段分栏」后剩 5 组进表、12 条逐条裁决（两处口径不同：表是共享代码符号的
   近亲对，注是每个被点名的既有号都要写一句为什么不判重），每组不写裁决就拒。
5. D13 的复现谓词读错容器（`measured` vs 行本身）⇒ rc=2 自曝；同时暴露错误原因没落到输出行上。
6. 我一度想给 F3 用「赋值处会报」当对照：Call 实参类型这一带根本没有可报的同族形状，
   对照必须是「该位置可被观察」的证据，改成实参位的元数违例对照才成立。
7. declared 第一版把「探针崩溃」也读成结论（D16 用了不存在的类、D17 用 `startswith('if (')`
   把函数体内的 if 当成模块级）⇒ 补了「非零退出或未吐 JSON 一律降级 not_measured」的硬门，
   并把 D17 换成按花括号净深判定。
8. 驱动脚本自身引入 112 条软 lint（含 E741 用 `l` 当变量名 16 处），与仓库风格规范相悖，是我欠的。

操作类：

1. Bash 工具的 cwd 会在调用之间回到仓库根，我按相对路径写的命令有一条打到不存在的文件；改绝对路径复跑。
2. 两次把 `python x.py | head` 的退出码当成 x.py 的退出码（那个 0 是 head 的）——第二次当场复核才发现。
3. heredoc 里带反斜杠的补丁第三次踩坑（`\\n` 被吃掉造成 SyntaxError），最后改走 Edit 工具。
4. 根收口器我先跑了两次：第一次被 L4 产物门拒（报告还没落盘，它就要报告文件存在），补完报告再跑第二次
   才过。第二次把 8 个已归档分支的链又重放了一遍，多出 48 条幂等拒绝（见 §十一 前两条归因）——
   拒得对，但这条噪声是我造成的；顺序应是「报告→根收口」一次到位，已把这条写进 R4-修复 的操作纪律。

## 九、要谁裁决

1. **BUG-61/62/63 的修法半径**：三处都要在分析器里补「可调用签名」与共享的「兼容性谓词」，
   会让**存量合法程序**开始报错。R3 语料 79 个 `.cypy` 零命中，但仓外用户语料未知。
   是否随 `--check-only` 的严格档位放闸，请指挥官定。
2. **BUG-65 的文档侧**（`SYNTAX/appendix-C` 与状态表共 7 行）属冻结面：按红线我只入账挂账。
   D04 的 `i32` 一族二选一：在文档里降级，还是在类型系统里补齐？
3. **BUG-70（3000 行红线）**：拆分 `parser.py`／`cython_generator.py` 是不可逆大改，本环只挂账。
   是否排一个专门的结构轮？
4. **D18 与 BUG-69 的真编译验证**需要跑两次真实编译（会写 `.pyd`，不动 git）：授权我在 R4-验证做吗？

## 十、转结

转 R4-修复：BUG-61..BUG-64 按根因逐单修，每单配成对锁与回退矩阵（摘实现必红）；
BUG-65..BUG-70 先分「下一环可改（docs／bridge）」与「交人工（冻结面／不可逆）」两栏。
转 R4-验证：D18 的两次编译实测、`appendix-C`《已实现的限制修复》14 行逐行复测、
BUG-69 的真 MSVC 编译验证。转 R4-打磨：驱动面软 lint 债 112 条只降不升、
`hunt_r4_*` 脚本里的 E741/E128 清账。
## 十一、被拒原文逐字 + 规格点名工具的实际承担者

`call_log` 从盘上按 `params_json.task_id` 前缀数，不按计划、不回忆：本环 T0r74 树共
{{.fist-loop-20260927/hunt_r4_calllog_tally.json|stages.T0r74.rows}} 行调用，其中
{{.fist-loop-20260927/hunt_r4_calllog_tally.json|stages.T0r74.refused}} 行被服务端拒，
按原文去重是 {{.fist-loop-20260927/hunt_r4_calllog_tally.json|distinct_refusal_texts}} 条，逐字如下。
**两个口径要分清**：页脚 `refusal_kinds=30` 是根收口件里记下的**那一次上卷**被拒列表长度；
下表是 T0r74 前缀在整棵树上**累计**
{{.fist-loop-20260927/hunt_r4_calllog_tally.json|stages.T0r74.refused}} 条按原文去重后的
{{.fist-loop-20260927/hunt_r4_calllog_tally.json|distinct_refusal_texts}} 种，二者不是同一个数，也不该相等。

{{.fist-loop-20260927/hunt_r4_calllog_tally.json|refusals_md}}

三条要说清楚的归因：

1. `非法验收: 任务处于 [已完成]，需先 submit`（16 次）与 `语料 … 已通过审核，无需重复创建`／
   `当前状态为 [approved]`（各 16 次）**不是产品缺陷**：是我为了补 L4 产物门，把根收口器在
   已经归档的 8 个分支上重跑了一遍，幂等守卫照拒。拒得对，重跑是我的操作债（§八 操作类已记）。
2. 根上那 3 条 `任务 [T0r74] 未开启 Omega 强验证（description 缺少 [omega:required] 标记）`
   是**结构性的**：模板建的根任务 description 里没有 `[omega:required]`，16 张叶与 8 个分支都开了强验证，
   唯独根开不了——我无权改根 description 之外的账（改它要 reject 回退，风险大于收益），
   所以根这一层的 omega 复验只能由叶与分支承担，这一条继续挂账（既有记录见 R1–R3 同款 6 条）。
3. 规格点名的 `laya` / `issue_up` 这两个**工具名在本 build 里不存在**（`call_log` 精确名 0 命中）。
   承担同一能力的是：`laya_decide`（本环
   {{.fist-loop-20260927/hunt_r4_calllog_tally.json|spec_named_carriers.laya.this_stage_total}} 次）
   与 `publish` + `report_bug`（本环
   {{.fist-loop-20260927/hunt_r4_calllog_tally.json|spec_named_carriers.issue_up.this_stage_total}} 次）。
   `call_log` 工具本身我也真打了一次（不是自读 sqlite）：客户端回包
   {{.fist-loop-20260927/hunt_r4_calllog_tally.json|spec_named_carriers.call_log.carriers.call_log.client_rows_returned}}
   行，其中含 T0r74 的
   {{.fist-loop-20260927/hunt_r4_calllog_tally.json|spec_named_carriers.call_log.carriers.call_log.client_visible_T0r74_rows}}
   行 ≥ sqlite 同口径行数，两边读数一致才算这条成立。

页脚（从判据件反解，不手填）：
