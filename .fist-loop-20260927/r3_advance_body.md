## 一、结论

R3-推进（根任务 `T0r73`，8 法 / 8 枝 / 16 叶）按指挥官的裁决**把半径钉在「文档已声明、代码未实现」这一条**上：
`SYNTAX/12-type-alias.md` 把 `type Callback = Callable[[int], str]` 与 `def process(callback: Callback)`
写成受支持语法，而 `SYNTAX/appendix-C-features.md` 又把 `Callable[[T], R] 函数类型标注` 列进「已知限制（尚未实现）」
—— 两行原文都逐字贴在 `advance_r3_scope_face.json:frozen_doc_rows`。

本环落地的就是那一条缺口的**最小可证部分**：在分析层补 `Callable[[T1..Tn], R]` 的**入参元数判定**。

| 主张 | 状态 | 依据（判据件实测） |
|---|---|---|
| 元数不符必报 | ✅ 已生效（5 类违例全报） | `violation_total={{advance_r3_arity.json|violation_total}}`、报错原文 `{{advance_r3_arity.json|measured_message}}` |
| 正确调用必不报（成对） | ✅ | `clean_cases_green={{advance_r3_arity.json|clean_cases_green}}` |
| 形状不认识就跳过（不误判） | ✅ 4 类形状留实测 | `skipped_shapes={{advance_r3_arity.json|skipped_shapes}}` |
| 每条报错带位点 | ✅ | `cases_with_locus={{advance_r3_arity.json|cases_with_locus}}` |
| codegen 产物一字未动 | ✅ 差分自证 | `all_textual_identical={{advance_r3_codegen_diff.json|all_textual_identical}}`（{{advance_r3_codegen_diff.json|sources_scanned}} 档：4 档剥时间戳后逐字相同，另 1 档是**故意的违例夹具**，改后被新判定挡住 ⇒ 分栏见 §三-末） |
| 语料零新增红 | ✅ 两态对表 | `new_errors_outside_locks={{advance_r3_corpus.json|new_errors_outside_locks}}`（扫 {{advance_r3_corpus.json|samples_scanned}} 档） |
| 基线只升不降 | ✅ 地板 1929→{{advance_r3_baselines.json|pytest_floor}} | passed `{{advance_r3_baselines.json|pytest.passed}}`、collected `{{advance_r3_baselines.json|pytest.collected}}` |
| 改动半径 | ✅ 恰好 2 档 | `radius.count={{advance_r3_baselines.json|radius.count}}`、越界 `{{advance_r3_baselines.json|radius.unexpected}}` |
| 既有测试零删改（全量名字级） | ✅ 消失 0 / 杂散新增 0 | `disappeared={{advance_r3_irreversible.json|test_names_disappeared}}`、`added_stray={{advance_r3_irreversible.json|test_names_added_stray}}` |

**本环不产生缺陷单**（`ns=bugs` 里含 `[loop:R3-推进]` 的条数实测 0）：推进环做的是补齐声明过的语义，
不是修 bug。不可逆动作实测零执行（`executed_none={{advance_r3_irreversible.json|executed_none}}`，
`{{advance_r3_irreversible.json|items}}` 条逐点名），golden 基准零重注册、冻结文档零触碰。

## 二、声明与实测的对表（这是本环唯一的立单依据）

| 形状 | 文档 | 改前实测（`advance_r3_pre_baseline.json:analyzer_errors_before`） | 改后实测 |
|---|---|---|---|
| `def apply(f: Callable[[int], str]) -> str: return f(1, 2)` | SYNTAX/12 声明可用 | 静默通过、照常出码 | 报 `{{advance_r3_arity.json|measured_message}}` |
| `def apply(f: Callable[[int], str]) -> int: return f(1)` | 同上 | 已能报 `Return type mismatch`（返回类型推断本来就活着） | 同前，未被新判定遮蔽 |
| `Callable[[], int]` 被 `f()` 调用 | 文档未写 0 参例，但属同一形状族 | 不判 | 正确匹配 ⇒ 不报；`f(1)` ⇒ 报 expected 0, got 1 |
| `Callable`（裸）/`Callable[int]`（单槽） | **未声明** | 不判 | **仍不判**（宁可不判也不误判） |
| `Callable[..., int]` | **未声明**，且 parser 直接拒 | `{{advance_r3_scope_face.json|variadic_probe_outcome}}` | 本环不动词法，记挂账 |

改前的"哪些是活的、哪些是缺的"是**逐格跑出来的**，不是照 appendix-C 那行字抄的：
返回类型推断其实早已生效（`type_checker.py` 里那条分支），真正缺的只有入参形状这一层。
如果只按文档那行"尚未实现"去实现一整层函数类型系统，就会顺手做出未被声明的东西——
这正是指挥官把半径限死的原因。

## 三、落地内容（只有 2 档文件）

`cypyc/analyzer/type_checker.py`：加两个私有辅助 + 一行调用。
- `_callable_declared_params(args)`：把 `Callable[[T1, T2], R]` 的 `generic_params = [tuple[T1,T2], R]`
  这一实测形状解出声明入参表；**解不出来返回 None**（调用方据此跳过）。
- `_check_callable_arity(node, args)`：只在实参是纯位置形式时比较个数；
  遇到关键字实参（parser 表示成**首元素为 str 的元组**）直接不判。
- 调用点：`Callable` 分支里 `ret = args[-1]` 之前插一行，不改返回类型推断的语义。

`tests/test_loop_20260927_advance_r3.py`：新增 {{advance_r3_locks.json|new_locks}} 条回归锁（文件表格里逐条写清
"钉住的主张"和"若被回退会怎样"）。产品文件的改前快照固化在 `advance_r3_before/type_checker.py`
（从 `tmp_advance/before/` 复制而来，快照树会被清理而对照件不能跟着没；sha `{{advance_r3_pre_baseline.json|type_checker_sha_before}}`，
改后 `{{advance_r3_arity.json|type_checker_sha_now}}`），禁 commit 的仓里 HEAD 不等于开工基线，
所以 before 快照才是主证据。

产物差分分两栏，不是一栏"全都要出码"：`{{advance_r3_codegen_diff.json|refused_expected_total}}` 档是
**违例夹具**（`ctl_callable_arity_bad.cypy`），它改前静默出码（`pyx_before` 里有它的产物、开工前件记的分析层
报错为空），改后**必须**被新判定挡住——脚本核的是"挡住它的那句话就是 `Callable arity mismatch`"，
被别的错误挡住也算判据不合格；其余 `{{advance_r3_codegen_diff.json|identical_total}}` 档要求剥掉两行时间戳后
逐字相同。两栏加起来必须等于清单总数 `{{advance_r3_codegen_diff.json|sources_scanned}}`，少一档就是有个源没进任何栏。

## 四、承重证明（回退矩阵 + 产物差分 + 语料对表）

| 组 | mutation | 期望变红的锁 | 必须仍绿 | 结果 |
|---|---|---|---|---|
| G1 | 摘掉那一行调用 | 违例必报 / 0 参违例 / 别名形状 / 两条错共存 | 跳过形状、正确调用、关键字、产物回退 | 红＝预期 |
| G2 | 把"不认识"当成零参判定 | 只有『形状不认识就不判』 | 其余 8 条（4 违例 + 正确调用 + 0 参匹配 + 关键字 + 产物回退） | 红＝预期 |
| G3 | 关键字实参不再跳过（还原上一版过滤器） | 只有『关键字调用不判』 | 4 条违例锁 + 跳过形状 | 红＝预期 |
| G4 | 判定过严：忘掉声明表最后一项是返回类型 | 9 条全红（宽爆破组） | 无 | 红＝预期 |
| C1 | **只加一行注释** | 无 | {{advance_r3_lockproof.json|premise.passed}} 条全绿 | 绿＝预期 |

合格组数 `{{advance_r3_locks.json|groups_ok}}/{{advance_r3_locks.json|groups_total}}`，被某组 mutation
打红过的锁 `{{advance_r3_locks.json|revert_covered}}/{{advance_r3_locks.json|lock_names_total}}` 条，
未覆盖集合 `{{advance_r3_locks.json|revert_uncovered_locks}}` —— 空表意味着不存在"写着锁但摘掉实现也不会红"
的装饰性锁（G4 连产物回退那条都打红，因为它跑的是一个**合法**程序的出码）。
窄性断言 `{{advance_r3_locks.json|narrowness_asserts}}` 处全过（`must_stay_green_all_ok={{advance_r3_locks.json|must_stay_green_all_ok}}`）。
身份探针：`{{advance_r3_locks.json|identity}}` 4 个模块的 `__file__` 全落在快照树内
（跑的不是工作区/已安装副本）；复原后 `{{advance_r3_locks.json|after_restore.passed}}` 条全绿；
快照树自删 `snap_left={{advance_r3_locks.json|snap_left}}`；工作区未被驱动改动
`workspace_untouched={{advance_r3_locks.json|workspace_untouched}}`。

**产物面**：同一批源在改前/改后各出一次 `.pyx`，剥掉 `__compile_time__`/`__generated_at__`
两行（`stripped_line_markers={{advance_r3_codegen_diff.json|stripped_line_markers}}`）后逐字相同
⇒ 本环没往 codegen 里塞任何东西，`Callable` 参数仍按既有语义回退成无标注（`def apply(f):`）。

**语料面**：扫描器（`.fist-loop-20260927/advance_r3_corpus_scan.py`）在同一棵快照树的**三种状态**下各跑一次
（摘掉判定 / 复原 / 故意改宽），对 {{advance_r3_corpus.json|samples_scanned}} 个 `.cypy` 逐档比错误集：
真实语料里被新判定影响的档 `{{advance_r3_corpus.json|files_changed}}` 个、新增的非 arity 错误
`{{advance_r3_corpus.json|new_errors_outside_locks}}`（口径 `scan_dirs={{advance_r3_corpus.json|scan_dirs}}`）。

这句话本来是可以"零变化"蒙过去的——第一版敏感性对照跑出来**恰好是 0**，逼我去查原因，
发现真实语料里只有两行 `type Callback = Callable[[int], str]` 的**声明**、压根没有经由它的调用点，
所以"零新增红"当时没有任何观察力。补法：往快照树的 `examples/` 里放两份见证夹具（工作区的 examples
一个字节没动，夹具随快照树删除），三栏结果照抄进件：违例档在复原态必报
`{{advance_r3_corpus.json|witness.bad_restored}}`、在摘掉判定的 mutation 态必不报
`{{advance_r3_corpus.json|witness.bad_mutation}}`、合规档两态都不报
`{{advance_r3_corpus.json|witness.ok_restored}}`；再把判定故意改宽扫一次，合规档必须**冒出**
arity 行（`{{advance_r3_corpus.json|sensitivity_probe.new_error_kinds}}` 类新错误，
全部经新判定产生 `{{advance_r3_corpus.json|sensitivity_probe.all_through_the_check}}`）——
这一条不成立就说明扫描器根本看不见 arity 行，前面的"零变化"是恒绿格。

## 五、三套判据体系与红线（同一批连续复算）

| 体系 | 下限 | 实测 |
|---|---|---|
| pytest | `{{advance_r3_baselines.json|pytest_floor}}`（= 上一环 1929 + 新锁 {{advance_r3_baselines.json|floor_raised}}） | passed `{{advance_r3_baselines.json|pytest.passed}}` / collected `{{advance_r3_baselines.json|pytest.collected}}`，其中本轮新锁在全量收集里现形 `{{advance_r3_baselines.json|pytest.advance_locks_collected}}` 条 |
| 自研套件 | 47/47 | `{{advance_r3_baselines.json|suite.fields.Passed}}/{{advance_r3_baselines.json|suite.fields.Total}}`，Failed `{{advance_r3_baselines.json|suite.fields.Failed}}` |
| e2e golden | 25/25 | PASS `{{advance_r3_baselines.json|e2e.fields.PASS}}`、FAIL `{{advance_r3_baselines.json|e2e.fields.FAIL}}`、UNREG `{{advance_r3_baselines.json|e2e.fields.UNREG/RUNFAIL}}`、WARN `{{advance_r3_baselines.json|e2e.fields.WARN}}` |

地板不是抄上一环：`PYTEST_FLOOR = 1929 + 盘上现数的 def test_`，数不出 9 条就当场拒。
测量窗口 `{{advance_r3_baselines.json|started_at_utc}}` → `{{advance_r3_baselines.json|finished_at_utc}}`，
各格自带 `at_utc`。git 红线 `all_ok={{advance_r3_baselines.json|git.all_ok}}`。

亲笔面分两种口径，不用一个数字混过去：本轮**新写的整档**（新锁文件）按仓库口径（flake8 100 列）
必须零违例 `{{advance_r3_baselines.json|lint.own_new_file}}`；本轮**改到的既有档**只对本窗口新加的行
负责 —— `{{advance_r3_baselines.json|lint.product_face}}` 那一格里 `violations_on_my_lines=0`、
整档违例数只减不增（before→now 两数并列），快照身份由 sha 自证（与 `advance_r3_pre_baseline.json`
同值）。"行号过滤"这层配了一对对照，防止它靠空集蒙绿：往开工前快照尾部插一条 130 字符的行
⇒ E501 必须被抓，插一条合规行 ⇒ 必须不误抓，实测 `{{advance_r3_baselines.json|lint.canary}}`。

**驱动面自己也要称**：本环 9 个 `advance_r3_*.py` 走历轮沿用的硬码门（E9/W605/F821 @200 列），
实测 `hard_violations={{advance_r3_driver_lint.json|hard_violations}}`；软码（E501/E201/F401 等）
本轮**不清理但逐码计数存债** `{{advance_r3_driver_lint.json|soft_by_code}}`（清单
`{{advance_r3_driver_lint.json|drivers}}` 档全覆盖），扫描器另配一条已知超长行的对照
（`canary_caught={{advance_r3_driver_lint.json|canary_caught}}`）——否则"驱动零硬违例"和"债只剩 0"
这两种情况我分不出来。R4/R5 打磨环拿这份件当"只减不增"的对照物。

**call_log 对账**：`T0r73` 前缀共 `{{r3_advance_calllog_tally.json|stages['T0r73 R3-推进（含 16 叶 + 8 支 + 根上卷）'].total}}`
次调用，成功 `{{r3_advance_calllog_tally.json|stages['T0r73 R3-推进（含 16 叶 + 8 支 + 根上卷）'].ok}}`、
被拒 `{{r3_advance_calllog_tally.json|stages['T0r73 R3-推进（含 16 叶 + 8 支 + 根上卷）'].refused}}`
（就是根上卷那 6 条既定语义拒绝，逐字见 §被拒原文）；分组按 `params_json.task_id` 反解而不是按标签或回忆，
过滤器自带一条必然不存在的前缀当对照（`control_absent_prefix_rows={{r3_advance_calllog_tally.json|control_absent_prefix_rows}}`）。
`issue_up` 在本构建里数出 `{{r3_advance_calllog_tally.json|issue_up_tool_rows}}` 行 ⇒ 它不是工具名，
开单走 tasks 表，这里如实上报而不谎称"已开启"。

## 六、不可逆动作面与挂账

`{{advance_r3_irreversible.json|items}}` 条：live `{{advance_r3_irreversible.json|live_probe_items}}`、
derived `{{advance_r3_irreversible.json|derived_items}}`、manifest `{{advance_r3_irreversible.json|manifest_items}}`；
判据通道自测（注入一条"被执行了"的假探针）`caught={{advance_r3_irreversible.json|self_test.caught}}`；
被执行 `{{advance_r3_irreversible.json|executed}}`。

- commit / push / add / tag：HEAD 仍是 `17d68b4`，暂存区 0 行，`refs/tags` 开工后新增 0，
  push 由"本地领先数与上一环相等 ＋ `origin/master` 的 reflog 顶条早于开工"两半共同证明。
- golden 基准：开工窗口内被触碰的 `examples/*.out` = `{{advance_r3_irreversible.json|golden_baseline_touched}}`
  —— 空表就是空表；扩覆盖面属交裁决动作，推进环不自己 `--update`。
- 冻结文档：PROJECT-SPEC / SYNTAX 在开工窗口内被触碰 0 档；
  相对 HEAD 的既有漂移（2 档 +41/−11）照旧只记上界，分不出是谁改的就不冒充"本轮已核对"。
- 既有函数/类零删除：`{{advance_r3_irreversible.json|removed_definitions}}`，
  改动行数 `{{advance_r3_irreversible.json|changed_lines_in_product}}`（上限 40），
  对照的是固化的开工前快照（sha `{{advance_r3_irreversible.json|before_snapshot_sha}}`，
  与 `advance_r3_pre_baseline.json` 同值才准比）。
- 既有测试**逐名**对照（不是只数数）：消失名 `{{advance_r3_irreversible.json|test_names_disappeared}}`、
  新增名 `{{advance_r3_irreversible.json|test_names_added}}` 条且全部来自本轮点名的锁文件；
  对照集是上一环留存的全量 `--collect-only` 日志，名字数与该环件里的 collected 先对齐才成立。
- 半径：`{{advance_r3_irreversible.json|radius_window}}` ⊆ 本环清单。

**挂账 / 交人工裁决（本环不动手）**：

1. 类型别名在**产物签名**里塌成无标注（`ctypedef object Callback` + `def process(cb)`），
   分析层已能顺着别名查元数，但 Cython 侧等距传递需要给函数类型选一个可落地的表示 —— 属新语义；
2. `Callable[..., R]` 变长写法：实测 parser 直接 `Unexpected token DOT_DOT`，而 SYNTAX 里搜不到这种写法
   ⇒ 它不是「已声明」，本环按裁决不碰词法；
3. 实参**类型**判定：需要先把赋值处那套类型兼容级联抽成共用谓词（现在散在 `type_checker.py` 五六个分支里），
   属重构决定。
   另外 appendix-C 的「尚未实现」那一行现在变陈旧了，改它属冻结面 ⇒ 只点名，不动刀。

## 七、本环自身缺陷（判据与工具类 / 操作类）

判据与工具类：

1. **第一版过滤器会把元组字面量当关键字实参**：我先按 `isinstance(a, tuple) and len(a)==2` 剔，
   实测 `f((1, 2))` 在 parser 里是**单个表达式节点**、`f(x=1)` 才是首元素为 str 的元组 ⇒ 旧写法让
   `f(x=1)` 被计成 0 个实参、当场误报。这条不是猜出来的：G3 组把过滤器还原成旧写法，
   只有『关键字调用不判』那条锁变红，才算把它钉住。
2. **"摘掉调用点"这一组 mutation 的期望红集我一开始写少了 1 条**（漏了『两条错共存』那条），
   跑出来 unexpected-red 为空、missing 非空 ⇒ 门禁报"期望变红的锁没红"。
   期望集必须逐条从锁名映射来写，不能凭"这条测的是元数、那条测的是返回"这种直觉分类。
3. **成对性判据如果只读件里的旗标就是恒绿格**：`clean_cases_green=true` 可以是被写进去的字符串。
   自审因此改成**当场再跑一次 `analyze_only`**（违例必报 + 正确必不报各一次），
   旗标只当索引；产物差分同样重剥时间戳再比，不采信件里自己写的 `identical`。
4. **半径主张不能反过来用 mutation 树的 mtime**：语料对表要在"摘掉判定"和"复原"两种状态下扫同一棵树，
   我第一版把两次扫描写在同一状态里（都在复原态），差集恒空 ⇒ "零新增红"成了恒真格。
   现在按组打标（`scan=True` 的那组先扫 mutation 态，收尾再扫复原态）并断言两态文件数相等。
5. **亲笔面 lint 的口径我先写宽了**："本轮碰过的文件整档零违例"当场把 `type_checker.py` 第 4 行那两个
   既有 `F401` 记到本环头上——那是历轮遗留，不是本环写的行。收窄成"只对本窗口新加的行负责 ＋ 整档违例数
   只减不增（325→325）"之后，**没有**就地放水：配了一对注入对照（插一条 130 字符的行 ⇒ E501 必被抓；
   插一条合规行 ⇒ 必不误抓），并把对照用的快照 sha 钉成开工前件里那个值。顺带一条真违例是我自己的：
   新锁文件第 67 行 102 列，已折行重测。
6. **跨环取数第四次踩下标**：`prev_irr["detail"][7]…deleted_rows_now` 这次碰巧对上，但上一环件只要多一条
   探针就全体错位 ⇒ 换成按键搜索、缺键即拒；同一轮里报告占位还写过 `…|detail[8]|evidence|…` 这种带第二个
   竖线的非法语法（装配器会把 `|evidence|…` 当键名去找），已改成件内顶层键并加了两条下标无关的门禁。
7. **不可逆面原来没有"既有测试逐名对照"这一格**：历轮只比过本环点名锁的名字（17 名），推进环改了产品码，
   全量 1929 条里没有一条红线守着"别的档的用例被人删/改名"。补法不是又写一个自述旗标：拿上一环留存的
   全量 `--collect-only` 日志当对照集，先证明它反解出的名字数与该环件里 `collected` 相等，再两向比
   （消失集必须空、新增集必须全部来自本环点名的锁文件）。实测 `1929 → 1938`，消失 0，杂散新增 0。
8. **G2 那组的锚点我钉错了层**：回退点放在 `_callable_declared_params` 兜底的 `return None` 上，
   跑出来 9 条锁一条没红——那两个未声明形状早在 `len(args) < 2` 就返回了，根本走不到我改的那一行。
   是判据（"期望变红的锁没红"）当场抓住的，不是我看代码看出来的。**mutation 得先证明它碰得到代码路径，
   才谈得上证明锁承重。**
9. **"语料零新增红"当时是恒绿格**：第一版敏感性对照跑出 **0** 变化，逼我去查——真实语料里只有
    `type Callback = Callable[[int], str]` 两行**声明**，没有任何经由它的调用点。也就是说那个 0 既可以是
    "没影响"也可以是"看不见"。补了见证夹具 + 故意改宽的第三态之后，同一句"0 变化"才有观察力。
10. **跨环取数第五次踩键形状**：`prev_irr` 里我按上一环的写法找 `row_counts.call_log`，而上一环件里那格
    叫 `call_log_rows_now` ⇒ 找不到、当场拒。这次拒绝是好事：它把"清空任务库"那条降级成清单级，
    而不是拿一个 `None` 比较出"没执行"的假绿。
11. **产物差分那一栏我一开始把违例夹具也当成"必须能出码"**：`ctl_callable_arity_bad.cypy` 改后确实
   `rc=1`，判据当场叫——这次是**判据写错而不是产品坏**，但如果不叫就直接把违例样本排除掉，
   "codegen 一字未动"就会变成"我只比了没动的部分"。现在两栏各自带期望，且总数必须对得上清单。
12. **自审器第一版自己就是红的（20 格不齐），存档在 `advance_r3_self_audit_pass1.red.json`**：它沿用了
   验证环模板的《六》段标题（本环是《七》），又用 `detail[7]` 这种下标取上一环件的数，还把"合格组数==4"
    写成了常量。三份件都在盘上，所以这不是"事后找齐"而是**审计器与被审件同样需要成对对照**；修完后
    59 格全齐、`mismatched=[]`、`vacuous_gates=[]`。
13. **驱动文件自己的 lint 一直没人称过**：历轮驱动口径只跑硬码门（E9/W605/F821@200），本轮把 9 个驱动
    按仓库 100 列口径重新数一遍，数出 67 条软违例（E501 49 条为主）。我没有顺手清理（清理会改动本轮
    半径外的文件、并把时间盒吃光），但也不能让"零违例"这句话覆盖到没查过的面上 ⇒ 出
    `advance_r3_driver_lint.json` 逐码存债，交 R4/R5 打磨环按"只减不增"处理。

操作类：

1. **`Callable` 的"已声明未实现"我一开始读成整层函数类型系统**：照这个口径就要动 codegen 与词法，
   直接越出裁决半径。回读 appendix-C 与 SYNTAX/12 的原文、再逐形状实测，才把这一环收窄成"入参元数"。
   **凡"补齐声明"的单，先做形状级对表，再决定动哪一层。**
2. **时间盒**：根发布 `18:41:40Z` → 本报告终版见页脚 `generated_at`，全程 ≤100 分钟；
   期间三套体系复算各占约 7 / 1.5 / 2 分钟，返工只发生在我的判据与 mutation 期望集上。
3. **见证夹具第一版压根没解析成程序**：我写的是 `def go(f: TwoArg, ...)`，而 `go` 是 Cypy 的保留字
   ⇒ 扫出来是 `Compilation error: Expected IDENTIFIER, got GO`。如果当时只断言"有报错就行"，
   夹具就成了一台空转的机器。**夹具内容必须过一遍解析器才算数**，判据也得断言报错的**种类**而不是有无。

## 八、汇报口径（给人看的三行）

- 做了什么：把文档声明过、但分析层没判的 `Callable[[T...], R]` **入参元数**补上（含别名路径），
  并用 4 组 mutation、9 条成对锁、两态语料对表和逐字产物差分证明这块改动是**窄的、承重的、不外溢的**。
- 没做什么：不动 codegen 语义、不动词法、不动冻结文档、不重注册 golden、不提交、不推送、不开缺陷单。
- 要谁裁决：产物签名里的函数类型表示（别名塌缩成 object）；`Callable[..., R]` 变长写法要不要进词法与文档；
  实参**类型**判定要不要先把类型兼容级联抽成共用谓词（重构）。

## 九、下一环（R4）输入

1. 三套体系地板现在是 pytest `{{advance_r3_baselines.json|pytest.passed}}`（collected
   `{{advance_r3_baselines.json|pytest.collected}}`）、套件 `{{advance_r3_baselines.json|suite.fields.Passed}}/{{advance_r3_baselines.json|suite.fields.Total}}`、
   e2e `{{advance_r3_baselines.json|e2e.fields.PASS}}`/25；R4 只准往上加，加测试前先抬 `PYTEST_FLOOR`。
2. R4-寻虫可以把"函数类型这一层的其余缺口"当**候选面**去搜（别名签名塌缩、实参类型不符、
   把 `Callable` 当返回类型、`lambda`/闭包是否声明过），但每条要先做**文档声明对表**再定性；
   没声明的形状只能进挂账，不能当缺陷修。
3. 成对判据的写法已定型：**违例必报 + 正确必不报 + 未知形状不判**三栏都要有现跑证据，
   且 mutation 组要能只打红其中一栏。新写判定型特性时照抄这个模板。
4. 报告/审计仍是两态：收口前跑 pre（量判据件与散文），收口后跑 post（补页脚格），同一落点覆盖；
   时间差不抹平，在报告里点名。
5. 语料扫描器 `advance_r3_corpus_scan.py` 可复用：任何"新加诊断"的环都应当在改动前后两态扫同一棵树，
   差集只允许包含本环新加的错误行。

## 十、复跑命令（逐条可粘）

```
python -X utf8 .fist-loop-20260927/advance_r3_evidence.py
python -X utf8 .fist-loop-20260927/advance_r3_lockproof.py
python -X utf8 .fist-loop-20260927/advance_r3_irreversible.py
python -X utf8 .fist-loop-20260927/advance_r3_baselines.py
python -X utf8 .fist-loop-20260927/advance_r3_driver_lint.py
python -X utf8 .fist-loop-20260927/advance_r3_calllog_tally.py
python -X utf8 .fist-loop-20260927/advance_r3_self_audit.py
python -X utf8 -m pytest tests/test_loop_20260927_advance_r3.py -q -p no:cacheprovider --no-header -o addopts=
python -X utf8 .fist-loop-20260927/advance_r3_corpus_scan.py . r3_advance
```
