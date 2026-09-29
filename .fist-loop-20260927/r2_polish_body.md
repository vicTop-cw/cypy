# R2-打磨（polish）正文

环节口径：半径 = **不改变对外语义的可验证收敛**。本环动了产品码，但只动了一种东西——被同名后定义
遮蔽的死代码。三件事：① 清偿 BUG-42（删两处死副本，先证哪份生效）；② 机制化一条结构判据，让
BUG-42 的形状回不来；③ 给 R2-验证 指出的 class 侧空白面补永久回归锁。
`HEAD` 保持 `{{.fist-loop-20260927/polish_r2_baselines.json|git.head}}`（红线：不 add / 不 commit /
不 push，实测暂存区 {{.fist-loop-20260927/polish_r2_baselines.json|git.staged}} 个文件）。

## 一、本环做了什么

- **先量后删**：判"哪份生效"不靠阅读顺序，用两条独立口径咬合——AST 里同一类体内的同名
  `FunctionDef` 行号候选，与运行时 `类.__dict__[名].__code__.co_firstlineno`。前者给
  `[1418, 2084]` / `[484, 926]`，后者给
  `{{.fist-loop-20260927/polish_r2_evidence.json|live['CythonGenerator._visit_ExprStmt'].live_firstlineno}}` /
  `{{.fist-loop-20260927/polish_r2_evidence.json|live['ScopeAnalyzer._visit_MetaBlock'].live_firstlineno}}`
  ⇒ 要删的是**前一份**。（证据件 `polish_r2_evidence.json` 是删前留档，`refuse=[]`。）
- **删除只走驱动**：`polish_r2_cut.py` 落盘前后各断言一次——锚点唯一、切片不含活份标记、
  `new != src`、`ast.parse` 通过、同名 def 计数 2→1、回读仍匹配不到被删块。任一条不过就整体拒绝。
- **删除面**：`{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_expr_stmt.rel}}` 行
  `{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_expr_stmt.removed_range}}`
  （{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_expr_stmt.removed_lines}} 行，sha8
  `{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_expr_stmt.removed_sha8}}`）；
  `{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_meta_block.rel}}` 行
  `{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_meta_block.removed_range}}`
  （{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_meta_block.removed_lines}} 行，sha8
  `{{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_meta_block.removed_sha8}}`）。
  合计 {{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_expr_stmt.removed_lines}}+
  {{.fist-loop-20260927/polish_r2_cut.json|measures.bug42_meta_block.removed_lines}} 行，被删文本
  **逐字留档**在 `polish_r2_cut.json` 的 `measures.*.removed_text`，要回放可原样取回。
- **新增 8 条永久锁**（`tests/test_polish_20260927_r2.py`）：结构门 1 + 其合成违例 1 +
  class 侧空白面 2 + 生效性绑定 1 + 守卫存活成对 1 + 活份仍做事 2。

## 二、两处死码各自的来历与"删了会丢什么"

BUG-42 原单明写"不断言哪份是意图"。本环用 `git log -S`（只读）把来历量出来，再回答"会不会丢东西"：

| 位置 | 死份独有逻辑 | 来历（`git log -S`） | 删除的影响 |
|------|--------------|----------------------|------------|
| `CythonGenerator._visit_ExprStmt` | 无独有逻辑：`elif getattr(node, 'value', None) is not None` 与它自己的 `if inner is not None` **同条件** ⇒ 构造上不可达 | 两份都随 `17d68b4`(2026-08-17) 一次进来 ⇒ 重复是那次重构的产物 | 零影响；活份（宏展开那条路径）行号由 2084 上移到
  `{{.fist-loop-20260927/polish_r2_after.json|bound_after._visit_ExprStmt}}` |
| `ScopeAnalyzer._visit_MetaBlock` | **有**独有文案：`meta block can only be defined at module level (line …, col …)` | 活份来自 `915431e`(2026-07-26)，守卫份来自 `f6d498f`(2026-07-27) ⇒ **后写的守卫被放在了被遮蔽的位置**，从来没生效过 | 语义不丢：同一条校验在 parser 里另有实现（`_require_module_level("meta", …)`，HEAD 的 `cypyc/parser/parser.py:2405` 已存在），调用面实测 `def foo(): meta:` 仍报 `meta must be defined at module level, found at 2:9`，并已钉成锁 |

⇒ 本环唯一"可能丢功能"的那份（`_visit_MetaBlock` 守卫）被这样处置：**不恢复、不新增报错**（恢复它会
改变错误面形状，属修复/推进半径，不属打磨），但把它的文案留档 + 把"这条语义仍在别处生效"钉成永久锁。
是否要在 analyzer 侧也恢复这道守卫，交裁决（§七 裁决项 2）。

## 三、判据自己的对照（每条主张都要有"必被抓到"的那一半）

| 主张 | 对照 | 实测 |
|------|------|------|
| 结构判据不是恒绿 | 同一个类体内写两次同名方法必须红 | `test_shadow_detector_catches_a_synthetic_pair` 断言 `A.m@[2, 5]` 被抓到、单份不误抓 |
| 结构判据在本环之前**确实是红的** | 删除前跑，红文逐字点名两处 | `ScopeAnalyzer._visit_MetaBlock@[484, 926]`、`CythonGenerator._visit_ExprStmt@[1418, 2084]`（1 failed, 5 passed） |
| 删除驱动不是"改了个寂寞" | 重跑必须被幂等守卫拒绝并给出 rc=1 | `{{.fist-loop-20260927/polish_r2_cut_guard.json|rc_line}}`，拒绝原因逐字：`{{.fist-loop-20260927/polish_r2_cut_guard.json|observed.refuse}}` |
| "删了什么"不能只有驱动自己作证 | 换一路口径：从**仓库外快照**按驱动记的行区间切片，与 `removed_text` 逐字比 | 两档均为 `True`（`polish_r2_after.json` 的 `slice_from_snapshot_matches_removed_text`），且行数差
  `{{.fist-loop-20260927/polish_r2_after.json|files['cypyc/codegen/cython_generator.py'].line_delta}}` /
  `{{.fist-loop-20260927/polish_r2_after.json|files['cypyc/analyzer/scope_analyzer.py'].line_delta}}` 与声称删除行数吻合 |
| 删除不会让任何名字消失 | 模块级符号集合 + 每个类的方法名集合逐档相同 | `refuse=[]`；全树同名遮蔽计数
  `{{.fist-loop-20260927/polish_r2_after.json|tree_dupes}}` |
| 绑定的仍是活份（不钉行号，避免自撞） | 断言用实现里的独有字样：`_visit_ExprStmt` 含 `_expand_macro`、`_visit_MetaBlock` 不含 `can only be defined` | `test_bound_visitors_are_the_surviving_implementations`（删除前后都绿 ⇒ 它锁的是身份而不是行号） |
| lint 判据不是恒绿 | 120 列赋值行必须被抓到 | `{{.fist-loop-20260927/polish_r2_lint.json|selftest}}`；另配"干净样例不得误抓"`{{.fist-loop-20260927/polish_r2_lint.json|selftest_negative}}` |

## 四、三套基线、lint 与 git 红线（同一时刻复算）

| 体系 | 实测 | 下限/期望 |
|------|------|-----------|
| pytest 全量 | `{{.fist-loop-20260927/polish_r2_baselines.json|pytest.line}}` | ≥ {{.fist-loop-20260927/polish_r2_baselines.json|pytest.floor}}（= R2-修复 1886 + 本环 8 条锁，只升不降）；收集数 {{.fist-loop-20260927/polish_r2_baselines.json|pytest.collected}}（rc_collect={{.fist-loop-20260927/polish_r2_baselines.json|pytest.collect_rc}}） |
| 自研套件 | `{{.fist-loop-20260927/polish_r2_baselines.json|suite.line}}` | 47/47 全绿 |
| e2e golden | `{{.fist-loop-20260927/polish_r2_baselines.json|e2e.line}}` | PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0 |
| 作用域化 lint | 亲笔行 {{.fist-loop-20260927/polish_r2_lint.json|authored_lines_checked}} 条，违例 `{{.fist-loop-20260927/polish_r2_lint.json|refuse}}` | 亲笔行零违例；两档产品码**新增行数** {{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/codegen/cython_generator.py'].added_lines}} / {{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/analyzer/scope_analyzer.py'].added_lines}}（纯删除）；存量违例只减不增：{{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/analyzer/scope_analyzer.py'].debt_before}}→{{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/analyzer/scope_analyzer.py'].debt_after}}（被删的 3 行里有超长行），`cython_generator.py` {{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/codegen/cython_generator.py'].debt_before}}→{{.fist-loop-20260927/polish_r2_lint.json|product_files['cypyc/codegen/cython_generator.py'].debt_after}} |
| git 红线 | HEAD `{{.fist-loop-20260927/polish_r2_baselines.json|git.head}}`，暂存 {{.fist-loop-20260927/polish_r2_baselines.json|git.staged}} 文件，脏行 {{.fist-loop-20260927/polish_r2_baselines.json|git.dirty_rows}} | 不 add/commit/push；脏行数含并发 lane |
| 改动半径 | {{.fist-loop-20260927/polish_r2_baselines.json|radius.count}} 个文件在盘上被本环时间窗覆盖，本单亲笔 3 档（两档产品码 + 1 档新测试） | 归不到本单的照列在 `radius.unclaimed_by_this_lane`，不据此宣告"只有我在动" |

基准**未重注册**：本环删的是从不执行的副本，产物字节面不应变化——三套体系末行逐字与上环同形即为证。

## 五、本轮自身缺陷（10 条：判据/工具 5 条 + 操作 5 条）

1. 新测试文件首版用了 `go` 作函数名 ⇒ `ValueError: Expected IDENTIFIER, got GO at 5:5`。这是**本轮第三类
   同一坑**（R2-修复 §五 第 4 条、R2-验证探针同因），根因是我把"文档里写过的关键字"当成可用标识符。
   机制化补救：以后凡在 Cypy 夹具里写函数名，先跑 `Lexer(...).tokenize()` 而不是先跑整条判据。
2. 新判据用了 `pytest.raises` 与 `inspect.getsource` 却没 import ⇒ **3 条判据当场红**，红的是我的判据自己。
   这轮抓得很快（先跑单文件再跑全量），但它再一次说明：**新写的判据在替产品码作证之前，先要自证跑得起来**。
3. 亲笔的 3 行超过项目声明的 100 列 ⇒ 被作用域化 lint 抓到（`E501@57/100/133`），修成多行字面量与显式变量。
   lint 这次没有当摆设，是它先于我发现问题。
4. 本环 spec 的「必须」句写成"BUG-42 的 FIXED 段挂在 **T0r58** 枝干"——那是 BUG-52 的任务号；本环根任务
   `T0r60`，BUG-42 条目自带 `task_id: T0r52`。**服务端描述不可改**（FIST 无 description 编辑 API），
   所以这里逐字承认错在 spec，而不修改已发布的法文；实际 FIXED 段落点见 §六 与账本。
5. `polish_r2_after.py` 首版留了两处占位/无意义表达式（一行 `for ... and [] or []: pass`、一处
   `x and [1418, 2084]` 的字符串拼接），若不 `--dry-run` 直接依赖就会产出一条**恒真的自证**。
   两处都在首次落盘前清掉，并把"重名塌缩记录必须逐字等于 `方法名:2->1`"补成硬断言。
6. 复算基线期间我又改了测试文件排版（第 3 条）⇒ 起跑那次跑的**不是最终文本**。处置：首跑留档为
   `polish_r2_baselines_run1.json`（末行 `1894 passed in 612.68s (0:10:12)`，`refuse=[]`），
   改完后**整档重跑**并以重跑为准（末行 `{{.fist-loop-20260927/polish_r2_baselines.json|pytest.line}}`）；
   两跑同为 1894/1894，互为独立佐证。教训写进口径：**基线跑到一半时不许再动被测量的文件**
   （要么先改完再跑，要么重跑），排版型改动也不例外——"语义等价"是我事后说的，不是当时量到的。
7. `git show HEAD:… > /tmp/head_cg.py` 之后 Python 读不到该文件（Git Bash 的 `/tmp` 与 Windows 侧路径
   不同域）⇒ 换成仓库内 `.fist-loop-20260927/r2polish/` 才可读。这与既有"Windows/Git Bash 工具坑"同源。
8. 收口驱动的 L4 产物门排在分支循环**之后**：我第一次跑上卷时报告还没落盘，驱动在跑完 8 个枝干之后
   才拒绝并退出——那一次的分支 omega 链已经落库，第二次重跑就吃了 24 条重入拒绝（分解见 §六）。
   这是**我的操作**造成的，不是服务端语义；但也暴露驱动不是事务性的，故把"L4 门前置"列为裁决项。
9. 报告装配器 `report_kit.py` 的根收口行读的是 `refused_count`，而 `close_root_generic.py` 写的是
   `refused` 列表 ⇒ 上一环（R2-验证）已发布的报告里那一格印成 `被拒 None 条`（该报告第 189 行），
   虽然同一报告下方的《被拒原文》表 6 条齐全，**汇总数字仍然撒了谎**。本环就地改成
   `refused_count` 缺失时回退 `len(refused)`，并用上一环的件复算：现在渲染
   `根 已归档 / 叶完成 16 / 被拒 6 条`。上一环那份报告**不重写**（它是当时实测的记录），
   在此逐字承认它有一处已知错印。
10. 两条门禁参数是**拍出来的**：`polish_r2_baselines.json` 的 `min_chars` 我写 1200，实测该件只有
    1055 字符 ⇒ 收口预检整体拒绝（预检是好的：一个服务端调用都没发）；门禁 ⑥/⑳ 同样按估数写了
    300/≥300，实测 299/166。⇒ 口径：**min_chars 与 min 门槛必须在件生成之后从盘面读出来再填**，
    不能按"这类文件大概多大"写。上一环踩过同型坑，这一环踩了三处，说明还没变成起跑默认动作。

## 六、账本与收口

- BUG-42 的 `### FIXED(打磨=已完成)` 段已追加进 `memory/bugs.md`，段内数字全部从证据件反解；
  条目正文与标题行的 `OPEN` 一字未改（账本无 close/edit API，FIXED 段只表意不表状态）。
  三向对照复算：账本条目 {{.fist-loop-20260927/verify_r2_ledger3way.json|ledger.entries}} 条、FIXED 段
  {{.fist-loop-20260927/verify_r2_ledger3way.json|ledger.fixed_sections}} 段、sqlite `bugs` 树任务
  {{.fist-loop-20260927/verify_r2_ledger3way.json|server.bug_tasks}} 个，拒绝清单
  `{{.fist-loop-20260927/verify_r2_ledger3way.json|refuse}}`。
- 收口链：16 张叶子（8 枝 × 2）全链 claim→omega_spec→execute→submit→output_validate→
  omega_result_verify→verify，`leaves` =
  {{.fist-loop-20260927/close_r2_polish.out.json|leaves}} 条、失败叶子
  {{.fist-loop-20260927/close_r2_polish.out.json|failed}} 条；根任务上卷终态
  `{{.fist-loop-20260927/close_r2_polish_root.out.json|root_final}}`、叶完成
  {{.fist-loop-20260927/close_r2_polish_root.out.json|leaves_done}}。

**根上卷被拒 {{.fist-loop-20260927/polish_r2_root_split.json|refused_total}} 条，分成两类，只有第一类是既定的**
（`polish_r2_root_split.json` 反解自 `close_r2_polish_root.out.json`，逐字原文见本报告《被拒原文》一节）：

- **结构性 6 条**（`{{.fist-loop-20260927/polish_r2_root_split.json|by_scope}}` 中的 root 那半边）：根任务 description 不带
  `[omega:required]` ⇒ `omega_spec_create/omega_spec_review/omega_result_verify` 各 1 条；叶级联把根推到 `待验收`
  ⇒ `claim/execute/submit` 各 1 条。这与 R2-验证 单次上卷实测的 6 条同形。
- **重入 24 条**（8 个枝干 × 3）：`{{.fist-loop-20260927/polish_r2_root_split.json|cause}}`
  ⇒ 枝干的 `omega_spec_create`（"语料已通过审核，无需重复创建"）、`omega_spec_review`
  （"当前状态为 [approved]"）、`verify`（"任务处于 [已完成]，需先 submit"）各 8 条。
  ⇒ **口径修正**：R2-修复 §五 第 13 条与我上一环写下的"合法基线 6 条 ⇒ 超过 6 就是有人重入过"
  方向对但把两类混成一类；正确的判法是**按 task 作用域分栏**看：root 那 6 条是既定的，
  branch 上任何一条都说明上卷驱动被重跑过。本轮就是那个"重跑"，责任人是我。
- 驱动本身的缺陷也被这条实测钉住了：`close_root_generic.py` 的 L4 产物门（报告必须已在盘上）
  排在**分支循环之后**，所以一次中止不是事务性的——分支链已经落库，重试必然吃重入拒绝。
  这条列入转结（§七 裁决项 5：要不要把 L4 门提到循环前，改动的是本 lane 的收口驱动而非产品码）。

## 七、未做与转结 / 交人类裁决

| 项 | 为什么不进本环 |
|----|----------------|
| 在 analyzer 侧恢复 `_visit_MetaBlock` 的模块级守卫 | 会**新增一类报错**，改变对外错误面 ⇒ 属修复/推进半径；本环只留档 + 钉"语义仍在"的锁 |
| `_visit_ExprStmt` 死份的 `_visit(inner)` 分发语义 | 死份从未执行，无法证明它"想做"什么；活份走 `_expr_to_str`。要不要让表达式语句按语句型分发，是语义决定 ⇒ 挂账 |
| 142 个文件的 formatter 债（BUG-50/52 的根） | 一次清 = 不可复审的巨大 diff，且本轮红线禁止大面积排版动作 ⇒ 仍待裁决 |
| BUG-48 `watch` 不重编译 | 属"已声明未实现"的功能补全 ⇒ 归下一环（推进）半径，本环不混做 |
| BUG-40/41/43、BUG-35 深嵌套半边、10 个"已删除未提交"文件 | 与上两环同因（配置口径 / 动既有测试 / 需判权威工作树）⇒ 继续挂账 |

交裁决（自动轮不代答）：

1. **轮末本地 commit + tag**：本树仍压着 09-26 轮与各环未提交改动（脏行见 §四），需要先答"哪一份是权威工作树"。
2. **`_visit_MetaBlock` 守卫**是否要在 analyzer 侧恢复（恢复 = 新增错误面，可能影响既有基准）。
3. **`_visit_ExprStmt` 两份的语义分歧**（表达式语句是否应按语句型分发）取哪一种。
4. BUG-50/52 的 formatter 债处置三选一（维持现状 / 原文重放 / 只加范围化 `black --check` 门禁）不变。
5. 收口驱动 `close_root_generic.py` 的 L4 产物门（报告必须已在盘上）要不要**前置到分支循环之前**？
   现状是"跑完 8 个枝干才发现报告不存在"，一次中止不是事务性的 ⇒ 重试必吃 24 条重入拒绝（§六）。
   改的是本 lane 的收口驱动而非产品码，但仍请确认，因为它会改变后续 8 个环节的收口形状。
