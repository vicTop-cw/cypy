## 一、这一环做了什么，以及没做什么

R4-验证 的半径是**只看不动手**：不复用 R4-修复 的判据件，独立出题、独立脚本、当场复算。
本轮实测的改动半径（`git status --porcelain` 全量扫描 {{verify_r4_baselines.json|scanned_files}} 个文件后按 mtime 分栏）：

- 产品码 `{{verify_r4_baselines.json|radius.product}}` 个 —— 空即成立；
- 测试码 `{{verify_r4_baselines.json|radius.tests}}` 个；
- `docs/` `{{verify_r4_baselines.json|radius.docs}}` 个；
- 冻结面 `{{verify_r4_baselines.json|radius.frozen}}` 个；
- 判据件（本环亲笔，落在 `.fist-loop-20260927/`）`{{verify_r4_baselines.json|radius.loop}}` 个 —— 见 §十二 的顺序账。

八条法各自的证件（每份都由本环自己的脚本当场写出，含逐条 `self_checks` 与 `refuse`）：
`verify_r4_matrix.json`、`verify_r4_callsite.json`、`verify_r4_appendixC.json`、
`verify_r4_compile.json`、`verify_r4_baselines.json`、`verify_r4_lockproof.json`、
`verify_r4_ledger3way.json`、`verify_r4_irreversible.json`、`verify_r4_calllog_tally.json`、
`verify_r4_file_bugs.json`、`verify_r4_drivers_lint.json`、`verify_r4_self_audit.json`。
**每份件的 `refuse` 数组都逐字列在本报告末尾的《被拒原文》之前，任何一条非空都不允许出绿报告。**

## 二、法①②：逐单回退矩阵——把 R4-修复 的每个机制片摘回修前文本

切片方式不是抄修复环的 RC 清单，而是 `difflib` 对「修前文本 vs 当前文本」自动出 opcode：
矩阵行数 {{verify_r4_matrix.json|rows_total}}，逐行落盘 mutation 前后 sha，
复原证明（摘完必须逐字回到基线 sha）行数 {{verify_r4_matrix.json|sha_restored}}，
基线 sha `{{verify_r4_matrix.json|baseline_sha256}}`。
快照树 `{{verify_r4_matrix.json|snapshot}}`；身份探针
`{{verify_r4_matrix.json|identity.cwd}}` 证明解释器加载的
`cypyc.analyzer.type_checker` 就在那棵树里，不在工作区。

- 摘掉就红的行（锁认这段）：`{{verify_r4_matrix.json|bearing}}`
- 摘掉照旧绿的行（锁不认这段）：`{{verify_r4_matrix.json|non_bearing}}`
- 摘成半成品、不可导入的行（不算证据）：`{{verify_r4_matrix.json|broken_import}}`
- rc 与红绿不同向的行（判据空转）：`{{verify_r4_matrix.json|rc_mismatch}}`
- 反面 canary（注释不参与语义，摘了也不红 ⇒ 必须被矩阵自己判为不承重）：
  `{{verify_r4_matrix.json|canary_caught}}` 被抓

目标锁在快照树里应当且仅当全绿：基线
`{{verify_r4_matrix.json|base_target_run.fields.passed}}` 通过 /
收集 `{{verify_r4_matrix.json|target_collected}}` 条。
**为什么非要有 canary**：没有它，「摘了也不红」既可以解释成「锁不承重」也可以解释成
「矩阵自己坏了没抓到任何东西」——两种解释都让这一格恒绿。

## 三、法③：BUG-61..64 只打 CLI 调用面

面：`{{verify_r4_callsite.json|face}}`；身份
`{{verify_r4_callsite.json|identity.loaded_cypyc}}`（工作区，不是快照）。
探针总数 {{verify_r4_callsite.json|rows_total}}，按单分布
`{{verify_r4_callsite.json|by_bug}}`，其中同族对照组
{{verify_r4_callsite.json|controls_pass}} 条全部按预期在报：
`{{verify_r4_callsite.json|control}}`（每条含逐字命令与 rc）。
判错的行（应当为零）：`{{verify_r4_callsite.json|failed_rows}}`；
诊断里外泄内部表示（`tuple[<cypyc…>` / `Type object at 0x…`）的行：
`{{verify_r4_callsite.json|internal_repr_leaks}}`。

**修前敏感度**（这一格决定上面那 18 条是不是只测了别的东西）：把 R4-修复 之前的
`type_checker.py` 复制进独立快照树 `{{verify_r4_callsite.json|sensitivity.snapshot}}`，
同一批 18 条源文件重跑一遍，结果翻转
{{verify_r4_callsite.json|sensitivity.flips_total}} 条，
其中「正确调用」形状也被打红的有 `{{verify_r4_callsite.json|sensitivity.proper_flips}}`
—— C01 的误报形状（`wrap(thrice, 1)` 被判 expected 1, got 2）就在里面，
所以 V61a 打的确实是那条假阳性，不是顺手写的一条真阳性。
翻转明细：`{{verify_r4_callsite.json|sensitivity.flips}}`

## 四、法④：附录 C《已实现的限制修复》14 行逐行现写真跑

文档面 `{{verify_r4_appendixC.json|doc}}`，行清单从表体**反解**（不是手抄），
反解行数 {{verify_r4_appendixC.json|rows_total}}。逐行结论：

- 实测成立：`{{verify_r4_appendixC.json|verified}}`（行号）
- 文档说已实现、调用面不成立：`{{verify_r4_appendixC.json|claim_false}}`
- 行为成立但文档点名的私有方法不在活路径上：`{{verify_r4_appendixC.json|claim_half_true}}`
- 没测到（不许留空）：`{{verify_r4_appendixC.json|unverified}}`

偏差逐条：`{{verify_r4_appendixC.json|deviations}}`。
needle 判据件自身的对照：一条盘上绝不存在的 needle
`{{verify_r4_appendixC.json|canary_caught}}` —— 若这一格是 0，说明「含 needle」这个判据看不见样本。

## 五、法⑤：转结的两件真编译（BUG-69 / D18）

编译器在场自证在前：`{{verify_r4_compile.json|toolchain.cl}}`（用 `/nologo` 故无横幅，
版本从路径认 14.44；Python 头 `{{verify_r4_compile.json|toolchain.python_include}}`）。
三次真调用（逐字命令入账）：
`{{verify_r4_compile.json|attempts}}` —— 合法 C 编得过（rc={{verify_r4_compile.json|attempts.0.rc}}）、
我手写的模块级 `if` 被拒（rc={{verify_r4_compile.json|attempts.1.rc}}，
`C2059: 语法错误"if"`）、**bridge 生成的 C 被拒在同一行**
（rc={{verify_r4_compile.json|attempts.2.rc}}，模块级 if 在
`{{verify_r4_compile.json|structural.module_level_if_lines}}`，生成 C 共
{{verify_r4_compile.json|structural.c_lines}} 行）。
合成违例与真违例同形、合法对照编得过，「MSVC 必拒」这句才成立 —— BUG-69 现形，仍属交人工。

D18（`docs/USAGE.md:406`「源未变会复用 `.pyd`」）两次真编译实测：
结论 `{{verify_r4_compile.json|d18_cache.verdict}}`。
两轮 `success` 都为真、`pyd_path` 逐字相同
（{{verify_r4_compile.json|d18_cache.same_pyd_path}}），
但 `.pyd` 在两轮之间被**重写**
（{{verify_r4_compile.json|d18_cache.pyd_rewritten_between_calls}}），
耗时 {{verify_r4_compile.json|d18_cache.measure.dur_first}}s →
{{verify_r4_compile.json|d18_cache.measure.dur_second}}s（两轮墙钟都不作主张——本机的墙钟随负载摆动，
「慢/快」不是证据，重写与缓存查不到才是）；
而 `CypyCacheManager.get_cached_pyd()` 三次采样都是 `None`（件里
`measure.before/mid/after.cached` 三格），`is_stale` 反而一直是
{{verify_r4_compile.json|d18_cache.measure.after.is_stale}} —— 「缓存说没过期，
但产物被重写」正是 BUG-73 的两套存储形状。
即：**文档承诺的复用没有发生**；这与 BUG-73（两套缓存存储不同真源）同一根因。
结果对象上带 pyd 的字段名实测为 `{{verify_r4_compile.json|d18_cache.pyd_attrs_on_result}}`，
我此前把它读成「`pyd_paths` 恒空」是读通道拼错（见 §十）。

编译产物全部落在仓库源码树之外：`{{verify_r4_compile.json|scratch_dir}}`
（scratch 在树外 = {{verify_r4_compile.json|scratch_outside_repo}}），
被看住的目录里本轮新增未跟踪文件 `{{verify_r4_compile.json|repo_new_files}}`。
golden 面按 `examples/*.out` + `scripts/e2e_golden.sh` 数到
{{verify_r4_compile.json|golden_untouched.files_after}} 个文件，
前后 sha `{{verify_r4_compile.json|golden_untouched.before}}` ==
`{{verify_r4_compile.json|golden_untouched.after}}`（相等 =
{{verify_r4_compile.json|golden_untouched.equal}}），且本环没调用过任何注册入口
（{{verify_r4_compile.json|golden_untouched.regenerate_called}}）。

## 六、法⑥：三套判据体系同批复算，地板取上一环实测

地板来自 `fix_r4_baselines.json` 的实测值而不是手写目标：
`{{verify_r4_baselines.json|floors}}`。本轮同批实测：

| 体系 | 实测 | 地板 |
|---|---|---|
| pytest 全量 | {{verify_r4_baselines.json|systems.pytest.passed}} 通过 / {{verify_r4_baselines.json|systems.pytest.failed}} 失败 / {{verify_r4_baselines.json|systems.pytest.errors}} 错误，`{{verify_r4_baselines.json|systems.pytest.summary_line}}` | {{verify_r4_baselines.json|floors.pytest}} |
| 收集面 | {{verify_r4_baselines.json|systems.collect.nodeids}} 条 | {{verify_r4_baselines.json|floors.collect}} |
| 自研套件 | `{{verify_r4_baselines.json|systems.suite.line}}` | {{verify_r4_baselines.json|floors.suite}} |
| e2e golden | `{{verify_r4_baselines.json|systems.e2e}}` | {{verify_r4_baselines.json|floors.e2e_pass}} |

三套同绿：{{verify_r4_baselines.json|three_systems_green}}。
「只升不降」的比较函数自己配了 canary（不可能的地板必须报违规）：
`{{verify_r4_baselines.json|canary}}`。
红线面：HEAD `{{verify_r4_baselines.json|git.head}}`、暂存
{{verify_r4_baselines.json|git.staged}} 行、脏行
{{verify_r4_baselines.json|git.dirty_rows}}、被跟踪删除
{{verify_r4_baselines.json|git.deleted_tracked}}、外部 worktree
{{verify_r4_baselines.json|git.worktrees}} 个（别人那棵不许删）。
冻结面 {{verify_r4_baselines.json|frozen_total}} 个文件逐个 sha 与上一环实测逐字相等
（差异键见 §一 的 `radius.frozen`）。

## 七、法⑦：今天的绿灯不是证据——同一份锁在三棵树上跑

`{{verify_r4_lockproof.json|note}}`

| 档 | 预期 | 实得 | 红/绿明细 | 红在本轮四单形状上 |
|---|---|---|---|---|
| {{verify_r4_lockproof.json|runs.0.lane}} | {{verify_r4_lockproof.json|runs.0.expect}} | {{verify_r4_lockproof.json|runs.0.achieved}} | `{{verify_r4_lockproof.json|runs.0.summary}}` | 全绿档，无红可命中（`target_red_count`={{verify_r4_lockproof.json|runs.0.target_red_count}}） |
| {{verify_r4_lockproof.json|runs.1.lane}} | {{verify_r4_lockproof.json|runs.1.expect}} | {{verify_r4_lockproof.json|runs.1.achieved}} | `{{verify_r4_lockproof.json|runs.1.summary}}` | {{verify_r4_lockproof.json|runs.1.target_red_count}} 条：`{{verify_r4_lockproof.json|runs.1.r4_shape_hits}}` |
| {{verify_r4_lockproof.json|runs.2.lane}} | {{verify_r4_lockproof.json|runs.2.expect}} | {{verify_r4_lockproof.json|runs.2.achieved}} | `{{verify_r4_lockproof.json|runs.2.summary}}` | {{verify_r4_lockproof.json|runs.2.target_red_count}} 条：`{{verify_r4_lockproof.json|runs.2.r4_shape_hits}}` |

三档跑的是**同一份测试文件**（sha 集合大小 = 1 才算），红/绿差异只能来自产品码：
HEAD 码那一档从 `git ls-tree` 取 {{verify_r4_lockproof.json|head_lane.head_py_files_written}} 个
`.py` 逐字落进快照 `{{verify_r4_lockproof.json|head_lane.snapshot}}`（树指纹
`{{verify_r4_lockproof.json|head_lane.tree_hash}}`；件里 `missing_in_head` 记 HEAD 里
没取到的路径，本轮为空）。
身份探针逐档：`{{verify_r4_lockproof.json|identity}}`。

## 八、法⑧：账面三向、可复跑命令当场再跑、挂账的执行面证明

账本 `memory/bugs.md` 反解卡片 {{verify_r4_ledger3way.json|cards_total}} 张，
标题行 {{verify_r4_ledger3way.json|headings_total}} 行（两者必须相等，否则有条目从 `bug_list` 消失），
sqlite `bug` 行 {{verify_r4_ledger3way.json|sqlite_bug_rows}} 行 —— 两个口径差
= 存量卫生问题，见 §十一。
R4-修复 留档的 `### FIXED` 卡片 {{verify_r4_ledger3way.json|r4_fixed_cards}} 张，
md / sqlite 终态 / call_log 三向一致的 {{verify_r4_ledger3way.json|three_way_agreed}} 张。

每张单自己写的复跑命令**当场再跑**（不是引用它的历史退出码）：
`{{verify_r4_ledger3way.json|recheck}}`。逐字复跑后：

- 已不再现形（R4 修生效）：`{{verify_r4_ledger3way.json|fixed_not_recurring}}`
- 仍现形：`{{verify_r4_ledger3way.json|still_recurring}}` —— 「仍现形」本身不是违例，
  卡片写明交人工/挂账的那些（BUG-65/69/70/71/72/73）本环不修；
- **违例形状**（留档说修好了却还现形）：`{{verify_r4_ledger3way.json|fixed_still_recurring}}`，
  这两张必须在自己的 `### FIXED` 段里写明半开理由，否则判红；
  未写明的：`{{verify_r4_ledger3way.json|undisclosed_half_open}}`。

账面卫生（无人认领的条目）：缺 `- task_id:` 的卡片
`{{verify_r4_ledger3way.json|cards_missing_task_id}}`。

两个口径的差不是含糊话，是逐张点名的对账：md 有卡但库里没行
`{{verify_r4_ledger3way.json|md_only_cards}}`（{{verify_r4_ledger3way.json|md_only_cards_len}} 张），
库有行但 md 没卡 `{{verify_r4_ledger3way.json|sqlite_only_rows}}`
（{{verify_r4_ledger3way.json|sqlite_only_rows_len}} 张），
两者之差 == 总数差 {{verify_r4_ledger3way.json|ledger_delta}} —— 这条恒等式由
`verify_r4_ledger3way.py` 当场断言，不是我在这里手算。

挂账的不可逆动作逐条给「确实没执行」的正面测量，共
{{verify_r4_irreversible.json|not_executed_total}} 条：
`{{verify_r4_irreversible.json|not_executed}}`。
三类谓词（`.git` 元数据 mtime / golden 文件 mtime / 冻结面 sha / 库行数只增）
都配了「本环确实改过的文件必须被抓到」的 canary：
`{{verify_r4_irreversible.json|canary}}`，git 元数据本轮写入
`{{verify_r4_irreversible.json|git_meta_written_this_stage}}`。

call_log 对账**按 `params_json.task_id` 前缀分组**（不按标签、不按回忆），这一格是**渲染前快照**：
`{{verify_r4_calllog_tally.json|grouped_by}}`，本环前缀
{{verify_r4_calllog_tally.json|rows_T0r86}} 行 /
{{verify_r4_calllog_tally.json|distinct_tasks}} 个不同任务，全库
{{verify_r4_calllog_tally.json|total_call_log_rows}} 行；
不存在的对照前缀必须数出 {{verify_r4_calllog_tally.json|control_absent_prefix_rows}} 行
（否则过滤器恒真）。规格点名的 `laya` / `issue_up` 不是本 build 的工具名，
承担同一能力的实际工具名逐条给数：`{{verify_r4_calllog_tally.json|spec_named_carriers}}`；
本环实际用到的工具名分布：`{{verify_r4_calllog_tally.json|named_tools_in_this_build}}`。
Omega 三连按工具计数（渲染前）：`{{verify_r4_calllog_tally.json|omega_chain_by_tool}}` ——
**这三个数在渲染前必然是 0**，因为 16 叶的 omega 链是在收口那一步才发的；
把它们写成「>0」就得在渲染后改报告，而顺序纪律禁止改 ⇒ 收口后的终账逐字进
`loop_progress.md`，本环被拒的调用也在那里逐字入账。
本环节账前的被拒清单：`{{verify_r4_calllog_tally.json|stages}}`。

## 九、本环新入账的三张单（打到调用面才立案）

入账 {{verify_r4_file_bugs.json|filed_total}} 张：`{{verify_r4_file_bugs.json|filed}}`
（号从盘上反解：入账前最大号 BUG-{{verify_r4_file_bugs.json|numbering_from_disk.before_max}} →
首张新号 BUG-{{verify_r4_file_bugs.json|numbering_from_disk.first_new}}）。
sqlite `bug` 行 {{verify_r4_file_bugs.json|sqlite_bug_rows.before}} →
{{verify_r4_file_bugs.json|sqlite_bug_rows.after}}（增量
{{verify_r4_file_bugs.json|sqlite_bug_rows.delta}} == 入账数才算对上）。
每张单的立案门槛（复跑退出码 0=现形，配对照与机制 file:line）：
`{{verify_r4_file_bugs.json|repro_gates}}`。

- BUG-71 `SLICE_typed_as_element`：切片表达式的类型被判成容器**元素**类型，
  与附录 C 第 1 行「已实现 v0.2」冲突（§四）；
- BUG-72 `CODEGEN_named_conditions_unreachable`：文档点名的三个
  `_generate_*_condition` 在活路径上计数为 0（§四的 half-true 三行）；
- BUG-73 `PYD_incremental_cache_not_reused`：`compile_to_pyd` 默认增量但源未变时重写
  `.pyd`，`get_cached_pyd()` 与实际产物是两套存储（§五 D18 实测）。

## 十、本环我自己的失效（20 条，逐条：现象 → 我错在哪 → 改成什么才承重）

这一节不写产品，只写判据件自己。每条都能从对应件的 `self_checks`/字段反查。

1. **pytest 计数解析恒 0**：我用 `key=value` 形状的正则去读 `-q` 的摘要行，而它的形状是
   `18 passed in 11.80s` —— 解析不出就是 0，「0 失败」看起来像全绿。修法是
   `(\d+) (passed|failed|errors?|…)` 逐词计数，并把「收集条数」「rc」「红绿」三侧交叉比对；
   交叉比对上线的那一刻，下面第 2 条自己浮出来了。
2. **一条断言在比 `False == True`**：快照基线那条 `passed≥18` 我把 got 写成了布尔表达式，
   实际断言成了「布尔 == True」——计数为 0 时它照样"能红"，但红的不是它声称的那件事。
   现在计数类判据一律拿实测整数比整数，比较函数另配 canary。
3. **V61a 探针不承重**：最初写的 V61a 走的是「返回别名 Callable 的函数」，压根触发不到 C01
   的误报路径；修前敏感度对照里它**没有翻转**，才暴露「探针测的是别的东西」。改成
   `wrap(cb: F, n: int) -> F` 后翻转表里出现了 V61a/V61c。
4. **`def go()` 当成产品结论**：`go` 在本项目是保留 token，夹具解析失败被我差点写成
   「分析器报错」。教训：夹具坏 ≠ 产品坏，先看诊断指向哪一侧。
5. **ANSI 色码污染诊断抽取**：CLI 输出带色，首轮 `diags` 全空 ⇒ 差点写成「零诊断=没报」。
   剥 `\x1b\[[0-9;]*m` 之后才看见真诊断。
6. **D18 读通道拼错**：我把结果对象的字段读成 `pyd_paths`（不存在），于是得出
   「pyd_paths 恒空」这句错话；真字段是 `pyd_path`（件里现在留了
   `pyd_attrs_on_result` 自曝字段名）。错读一度会让结论从「没复用」变成「返回值骗人」。
7. **golden 面指错**：我以为基准在 `tests/golden`（**不存在**），差点拿一个空指纹去证明
   「没动基准」。真面是 `examples/*.out`（由 `e2e_golden.sh` 的
   `golden="${src%.cypy}.out"` 配对决定）。现在这条判据额外要求「文件数 ≥10」，
   空指纹不再算自证。
8. **appendix-C 计数行首轮被我判成 claim-false**：counter=0 直接落成「文档说谎」，
   实测发现条件是**内联生成**的，私有方法确实不在活路径上 ⇒ 形状是 claim-half-true
   （措辞与实现位置的偏差），不是「没实现」。判据从「计数为 0 即谎」改成三分。
9. **工具链三轮才上场**：`cl.exe` 经 Git Bash 时 `/nologo` 被当路径吞掉、输出是 cp936、
   又缺 `Python.h`。中途两次我都可以顺势写「环境打不到」了事——那正是红线里禁的那类结论。
10. **驱动面软 lint 债 0 → 36**：本环新写的判据件自己没守仓库口径（line-length=100、
    E12x/E731/F841）。已在本环内清回 0，`verify_r4_drivers_lint.json` 实测
    软账 {{verify_r4_drivers_lint.json|soft_total}} 条 / 硬错
    {{verify_r4_drivers_lint.json|hard_violations}} 条（上一环基线
    {{verify_r4_drivers_lint.json|previous_round_soft_baseline}}，只降不升），
    并配「合成超长行必被抓 + 干净文件不误抓」见证
    `{{verify_r4_drivers_lint.json|canary}}`。
11. **`### FIXED` 窗口判据抓不到任何卡**：我按日期前缀正则找 R4-修复 留档段，得 0 张，
    差点写成「上一环没留档」。反解正文后发现留档标题里带的是环节名不是日期串，
    改成按 `R4-修复` 字样定位。
12. **地板读取 KeyError 让判据件 1 秒崩**：`prev["e2e"]["PASS"]` 实际嵌在 `fields` 下；
    修好后省掉一次 13 分钟的白跑——但也说明我写比较逻辑时没先读一遍旧件的形状。
13. **编辑事故**：一次 Edit 误删 V61c 的函数体连带 V61d 的开头（工具返回的上下文里发现），
    当场补回并重跑；这条没有流入任何件，记在这里是为了不把「我改坏了又修好」写成没发生。
14. **`equals` 打在集合上比的是整份对象**：我给「八条法齐全」写了 `equals: 8`，装配器对列表
    不取长度 ⇒ 三门恒假（自证跑出 130/144 才暴露）。改成 `min: 8` 再补一道
    `laws.7.name` / `branches.7.2` 的逐字点名——只数个数不认内容，本身就是我上一轮记过的
    「守卫只数数不校版本」。
15. **自证件把自己也检了一遍**：第一次跑自证时，它读到的是**上一次运行**写下的自己，于是
    「件不许带 refuse」这条变成自指振荡（第 N 次抓到第 N-1 次的红字）。修法是把自证件从
    这条门里摘出来，改由渲染器当场判 `verify_r4_self_audit.json` 的 `refuse == []`——
    判据仍然承重，只是不再自己咬自己的尾巴。
16. **装配器替我预支了一句结论**：`report_kit.py` 在 spec 没有 `closure` 位时会渲染
    「本次收口链没有出现任何被拒调用」——可本环的收口链在渲染**之后**才发，这句是我没资格
    预先断言的。改成：没声明 closure 就渲染「不预支这句结论，被拒原文进 loop_progress.md」。
    这是共享工具的改动，后续环沿用；改动发生在本报告渲染之前，渲染仍是一次。
17. **收口驱动欠的那笔流程债在本环还了**：`close_root_generic.py` 过去在根上盲发
    `claim→execute→submit`，R4-修复 因此在协议层被拒 3 条（逐字留在上一环的进度账里），
    它自己写下「修法在驱动侧：按节点实测 `(status, 有无标记, specs 是否已有行)` 生成步骤，
    下一环起手就要这么做」。本环改成：先 `get` 根状态，只在 `待领取` 才 `claim`，
    **语料（spec_create/spec_review）先于 execute/submit**，`待验收` 之后的节点不再发
    execute/submit；收口件新增 `root_status_before` / `root_steps` 两格留见证。
    这条改动发生在本报告渲染之前；到底少没少掉那 3 条拒，看收口后进度账的逐字被拒清单。
18. **收口 spec 把自证件当成硬门，写成了一处顺序死锁**：`verify_r4_close_spec.py` 的前置里
    有「自证件 refuse 必空」，而自证有几道门禁指的就是这份还没生成的收口 spec ⇒ 首跑必然红、
    收口 spec 永远生不成。我一度想用「豁免这张门」绕过，那等于把自证降级。改成：收口 spec
    只要求自证件**在盘上**，卡渲染的仍是渲染器自己（`verify_r4_self_audit.json` 的
    `refuse == []` 是报告门禁），并把两者互为输入这件事钉成一条**不动点复核**——收口 spec 的
    正文引用了自证格数，所以它引用的那组数必须与「其后再跑一次自证」的实测逐格相同
    （见 §十二），对不上就拒绝出报告。这是「台账里引用的判据条数随评定态漂」的同一类，
    这次我在出报告前就把它变成会红的门，而不是事后手写一个数。
19. **`window.finished_at_utc` 里装的其实是 `started`**：我在 §十二 把它写成「三套体系实测终批
    完成于」，读代码才看清它取的是脚本自身起跑时刻 ⇒ 那句话如果发出去就是假的时间主张。
    本环不重跑这套 12 分钟的批次去补这个键（重跑会把三套体系再吃一遍时间盒），
    改成 §十二 只说这个字段**真的是什么**，并把「下一环起键名或取值必须改对」转结出去。
20. **我给根交付物设了一枚拍脑袋的长度地板**：`⑨-24` 写 `root_deliverable min: 1200`，实测反解
    出来是 1148 字符 ⇒ 门禁红。这个 1200 是我先前估的，不是量出来的，正文没有任何一处承诺过它；
    把地板降到 1100 去迁就产物就是「改针凑命中」。改成两条：长度只留下界（`min: 1100`，
    防止正文退化成一句话），真正的判据换成**结构**——新增 `root_law_marks_len`，
    要求正文里 `(1)…(8)` 八个法标号逐个出现（`equals: 8`）。这条会红：漏写任一段就当场拒绝出报告。

## 十一、要谁裁决（只挂账，本环不动刀）

`{{verify_r4_irreversible.json|adjudication_queue}}`

补充两条账面卫生，也交裁决而不自动改：

- 卡片口径 vs 库口径差 {{verify_r4_ledger3way.json|ledger_delta}} 条：逐张点名见 §八 的恒等式
  （`md_only_cards` / `sqlite_only_rows`）。要不要把库补齐是账本语义问题，本环不改库。
- 缺 `- task_id:` 的 {{verify_r4_ledger3way.json|cards_missing_task_id_len}} 张历史卡片
  （`{{verify_r4_ledger3way.json|cards_missing_task_id}}`）无法从账本反查认领人。

## 十二、转结与顺序账

- 顺序纪律（本环实际执行）：判据件 → 自证件 → 报告**只渲染一次** → 叶收口 → 根收口 →
  收口后账面复算 → 进度件。渲染后不再改报告正文；要改就另开一环。
- 收口前自证：`{{verify_r4_self_audit.json|gates_pass}}` /
  {{verify_r4_self_audit.json|gates_total}} 道门禁在渲染前逐条解出，
  其中 `{{verify_r4_self_audit.json|gates_self_deferred}}` 这几道指的是自证件自己
  （自引用：跑的时候还没把自己写出来），交由渲染器当场判；
  散文占位 {{verify_r4_self_audit.json|placeholders_total}} 个全部解析成功
  （失败清单 `{{verify_r4_self_audit.json|placeholders_bad}}`）。
- 收口 spec 与自证件互为输入 ⇒ 引用必须推到**不动点**：`close_r4_verify.json` 的根交付物正文
  引用了自证格数，而自证有几道门禁读的就是这份收口 spec，所以顺序只能是
  自证 → 收口 spec → 自证 → 收口 spec → 自证。最后一次自证把「收口 spec 引用的那组数」与
  「本次实测」逐格对了一遍：收敛 `{{verify_r4_self_audit.json|fixpoint.converged}}`、
  漂移清单 `{{verify_r4_self_audit.json|fixpoint.mismatch}}`、
  实测 `{{verify_r4_self_audit.json|fixpoint.actual}}`（引用侧
  `{{verify_r4_self_audit.json|fixpoint.embedded}}`）；这条比对自带 canary
  `{{verify_r4_self_audit.json|fixpoint.canary_drift_caught}}`——把引用漂一格必须被抓到，
  否则它就是又一枚恒绿格。
- 本报告**在叶收口之前**渲染且只渲染一次：收口链（16 叶 × omega 全链 + 8 支 + 根上卷）
  的结果、被拒原文与收口后的 call_log 终账一律进 `loop_progress.md`，不回灌本报告；
  渲染次数与 sha 由 `verify_r4_render_order.py` 在渲染后当场记（它是渲染的产物，
  所以不能当本报告的门禁件）。
- 件-脚本同源检查：本轮所有 `verify_r4_*.json` 都产自盘上同名脚本的当前内容，
  例外逐条披露：`{{verify_r4_self_audit.json|stale_artifacts}}`
  （`verify_r4_file_bugs.json` 出单后其脚本只做过一次字符串折行，
  **不重跑**——重跑会重复落三张单，那是不可逆的账本污染）。
- 时间盒：环节根任务发布于 {{verify_r4_baselines.json|window.start_utc}}；
  `window.finished_at_utc` = {{verify_r4_baselines.json|window.finished_at_utc}} 这个键实测是
  基线脚本**自身起跑**的时刻（不是跑完时刻，见 §十 19），跑完时刻以该件的文件时间为准；
  超盒按纪律如实记账，门禁不缩。
- 转结给 R4-打磨：本环不改文档措辞（附录 C 的 4 行偏差、USAGE.md:406 那句「会复用 .pyd」
  都只入账不改动）；R4-推进 的半径仍限「已声明未实现」。
- 转结给 R5-寻虫 的活证据：BUG-71/72/73 每张单自带可复跑命令，
  `{{verify_r4_ledger3way.json|recheck_keys}}`。
