# R2-修复（fix_and_merge）正文

环节口径：本环**动产品码**。半径 = 上一环（R2-寻虫）我自己入账的 4 单 + 从 R1 转结下来的 2 单
（BUG-39、BUG-35），共 6 单；其余按 §六 转结，不混进本环。
`HEAD` 保持 {{fix_r2_baselines.json|git.head}}（红线：不 add / 不 commit / 不 push，
本环实测暂存区 {{fix_r2_baselines.json|git.staged}} 个文件）。

## 一、本环做了什么

- 6 单全部落到**调用面可复跑**的形状：`cypyc transpile`/`cypyc hook …` 子进程、包级 API 的
  `hasattr` 探测、产物 .pyx 的签名行，**没有一条**判据是"源码里出现了某个字样"。
- 每单配**成对对照**（回退本单时对照必须仍为绿），并新增 {{fix_r2_lockproof.json|full_tree.collected}} 条永久回归
  （`tests/test_loop_20260927_fix_r2.py`）。
- 改动面（mtime 反解，含并发 lane 的在飞文件）{{fix_r2_baselines.json|radius.count}} 个文件，
  本单亲笔 7 个：`cython_generator.py`、`parser.py`、`cypy_hook/hook.py`、`cypyc/cli.py`、
  `cypy_hook/__init__.py`、`docs/USAGE.md`、`tests/test_loop_20260927_fix_r2.py`。
  归不到本单的照列在 §四，不据此宣告"只有我在动"。

## 二、逐单落地

| 单 | 缺陷形状 | 修在哪 | 锁/对照 | 只回退本单的结果 |
|----|----------|--------|---------|-------------------|
| BUG-44 | 静默错产物：struct 的 `@staticmethod`/`@classmethod` 被注入 `self` | `cython_generator.py`：新增 `_decorator_names`/`_is_selfless_method`，self 注入改判「已声明 self 或 非绑定」；`binding(False)` 只挂绑定方法 | 锁 2 / 对照 1 | {{fix_r2_lockproof_revert_bug44.json|red_locks}} |
| BUG-45 | 导入即 NameError：`= __implicit_default__` 生成成裸名 | 同上：`_param_default_str` 脱糖成 `Type.__implicit_default__()`；`parser._parse_params` 对无注解者给带行列诊断 | 锁 2 / 对照 1 | {{fix_r2_lockproof_revert_bug45.json|red_locks}} |
| BUG-39 | 静默错产物：顶层 `return` rc=0 且原样写进 .pyx | `parser._parse_return_stmt` 补 `_require_function_scope`（`defer` 一直在用它） | 锁 1 / 对照 1 | {{fix_r2_lockproof_revert_bug39.json|red_locks}} |
| BUG-35 | 归桶撒谎：解析/生成异常被写成「读取文件错误」 | `cypy_hook/hook.py::transpile_file`：读文件单独 `except OSError`，外层兜底改「编译错误」 | 锁 1 / 对照 1 | {{fix_r2_lockproof_revert_bug35.json|red_locks}} |
| BUG-46 | 两命令互相否定（install 报 [OK] 零持久化、status 报未装） | `cypyc/cli.py` 三条横幅限定「当前进程」+ `docs/USAGE.md` 2.6 删掉未实现的 sitecustomize 承诺 | 锁 2 / 对照 1 | {{fix_r2_lockproof_revert_bug46.json|red_locks}} |
| BUG-47 | 手册承诺的包级 API 不可用 | `cypy_hook/__init__.py` 再导出 3 个函数并补 `__all__` | 锁 2 / 对照 0（探测自带 `is_hook_installed_v2` 反证） | {{fix_r2_lockproof_revert_bug47.json|red_locks}} |

BUG-46 取的是原单给的 **b) 收窄声明**，不是 a) 真做持久化：写用户 site-packages/.pth 属改本机
Python 环境，在本轮红线里是不可逆动作 ⇒ 只挂账（§七 裁决项 1）。选 b 的连带好处是零环境副作用，
代价是"按手册装完就生效"这句话被删掉了——它本来也不成立。

BUG-35 是**部分修**：分桶已修且带行列；200 层括号那类 `RecursionError` 仍无深度守卫，
这半边按"入账未修"转结（§六），条目在账本里仍是 `OPEN`（账本无 close API，FIXED 段只表意不表状态）。

## 三、锁死是不是承重的（回退矩阵）

底树说明：**不能拿 HEAD 当底树**——`17d68b4` 之后还压着 09-26 轮与 R1 轮的未提交改动，
HEAD 码跑不动当前 tests。所以底树 = 当前工作树的必要子集（`cypyc/`、`cypy_hook/`、`cypy_bridge/`、
`docs/`、`tests/test_loop_20260927_fix_r2.py`），回退 = 逐单把「修复后文本 → 修复前文本」精确替换，
每处 `count==1` 才落，并二次校验"修复前文本确实回来了"。

判据与结果（`fix_r2_lockproof.py`）：

- 完整树：{{fix_r2_lockproof.json|full_tree.collected}} 条全收集、rc={{fix_r2_lockproof.json|full_tree.rc}}，末行 `{{fix_r2_lockproof.json|full_tree.line}}`；
- 逐单回退：每单自己的锁**至少 1 条转红**（红条数见 §二末列）；
- 混因：回退任一单时**别单**的用例红数 —— 整套判据的拒绝清单是
  `{{fix_r2_lockproof.json|refuse}}`（空 ⇒ 六单归因互不污染）；
- 对照：回退本单时本单对照仍绿（第一版不满足，见 §五 第 2/3 条）。
- 第 7 组 `macro_exemption`（3 条）**不参与逐单回退**：它锁的是"别把守卫做过头"，
  只有把 `body_scope` 免役拆掉才会红 ⇒ 它参与混因与收集检查，不参与"回退本单必转红"。

## 四、三套基线、lint 与 git 红线（同一时刻复算）

| 体系 | 实测 | 下限/期望 |
|------|------|-----------|
| pytest 全量 | `{{fix_r2_baselines.json|pytest.line}}` | ≥ {{fix_r2_baselines.json|pytest.floor}}（= R1-推进 1868 + 本轮 18 条锁，只升不降） |
| 自研套件 | `{{fix_r2_baselines.json|suite.line}}` | 47/47 全绿 |
| e2e golden | `{{fix_r2_baselines.json|e2e.line}}` | PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0 |
| 作用域化 lint | 亲笔行 {{fix_r2_lint.json|authored_lines_checked}} 条，违例 `{{fix_r2_lint.json|refuse}}` | 本轮亲笔行零违例；整档存量债（854 条）不记在本单名下 |
| git 红线 | HEAD `{{fix_r2_baselines.json|git.head}}`，暂存 {{fix_r2_baselines.json|git.staged}} 文件，脏行 {{fix_r2_baselines.json|git.dirty_rows}} | 不 add/commit/push；脏行数含并发 lane |

同一次复算被**两个独立进程**各自跑了一遍（第二次是我为排除上一轮 `1885 passed` 与收集数 `1886` 不一致而并发起的第二把）：两把都是 `1886 passed / collected 1886 / 47 ‖ 25 PASS`，差值只剩耗时（`346.48s` 与 `327.53s`）⇒ 那条不一致是并发采集时的一次瞬时少收，不是用例失踪；自证的机制是 `fix_r2_baselines.py` 把 `collected` 与 `passed` 钉成同一时刻的两个读数。

基准**未重注册**：本环改了 struct 方法产物形状，但 25 份端到端基准的输出逐字不变
（`PASS=25 FAIL=0`）⇒ 说明改动没触及示例程序的运行面，无需 `--update`。

## 五、本轮自身缺陷（14 条：8 条判据缺陷 + 6 条操作缺陷，其中 2 条已入账 BUG-50/51）

1. 回退脚本对 `hook.py` 的桶名锚点**缩进写错**（12 空格写成 16）⇒ `count==0` 直接 REFUSE；
   改成整块锚定后又发现那 3 行 `except Exception as e: / result.errors.append(f"编译错误: {e}") /
   return result` 在文件里出现**两次**（`transpile_file` 与编译 .pyd 的路径同形）⇒ 必须带更长上下文
   锚定。`count==1` 断言是唯一挡住它的东西。
2. BUG-44 的**对照**里混进了修复依赖断言（`binding(False)` 总数 == 1）⇒ 回退本单时对照也红，
   被"判据4"抓到；计数移进锁、对照只断言绑定方法那半边。
3. BUG-46 的对照探针走 `cypy_hook.is_hook_installed`（包级 API）⇒ 回退 BUG-47 会把它带红（跨单耦合）；
   改走 `cypy_hook.hook` 后两单归因分开。
4. BUG-44 首版夹具把 struct 绑定方法写成**隐式 self**（`def shifted(dx: int)` + 体内 `self.x`）⇒
   CLI 报 `Undefined name 'self'`，差点被当成本轮引入的回归。查 SYNTAX/06d 才确认文档形状是
   **显式 self**；改写夹具后绿。附带产出一条观察（不是本单主张）：隐式 self 写法在类型检查面走不通。
5. lint 判据把 flake8 的 `%(text)s` 当成**物理行文本**（它其实是诊断文案）⇒ 按文本匹配永不命中，
   是恒绿形状；改成 `%(row)s` + 自己回读文件，并加"必然违例"自检（120 列赋值行必须被抓到，
   实测 `{{fix_r2_lint_selftest.json|selftest}}`）。
6. lint 判据的锚点串里多打了一个转义引号 ⇒ 报"亲笔行缺失"。**这是判据自己写错**，
   与 R1 第 8 条同型（凭记忆写 needle）：本轮改为起跑先量（`fix_r2_needles.py`），24 条 needle 全部命中才发收口调用。
7. 用 `cmd &` 启的后台任务在工具调用返回时被回收 ⇒ `e2e_after.log`/`suite_after.log` 留 0 字节，
   看着像"跑了但没结果"。换成 run_in_background 托管并把日志落在仓库内路径。
8. **（操作缺陷，已入账 BUG-50）**为格式化本轮脚本，我把两档**存量未格式化**的产品文件
   （`cypyc/parser/parser.py`、`cypyc/parser/macro_expander.py`）一起传给了 `black` ⇒ 被整档重写，
   相对 HEAD 的改动行数 425 → 1885（本单对 parser.py 的真实意图只有 4 处、约 19 行）。
   **损失不可回滚**，三条反证当场可查：索引 blob 与 `HEAD:` blob 同哈希（`fe5a888…`，从未 `git add`）、
   IDE `file-history` 今天 16:00 之后没有该档的任何快照（全量 `find` 只命中工作区那一份）、
   `git archive HEAD` 类快照树只含 HEAD（不含 09-26/R1 的未提交工作）。
   三套基线随后全绿只证明**行为**未变，不证明文本层与评审面未受损 ⇒ 交人工裁决（§七 裁决项 4）。
   机制化补救：新增 `.fist-loop-20260927/snapshot_tracked.py` —— 改产品码前把 `git ls-files -z` 全集
   复制到**仓库外** `E:/IDEProjects/AI/_cypy_snapshots/<标签>/`（放仓库外是为了不把几百个新文件
   踩进并发 lane 的索引守卫），并自证 `copied/names/missing`。该脚本顺带量到另一件与本轮无关、
   但影响提交决策的事实：**10 个受版本控制的文件在工作树里是"已删除未提交"状态**
   （`examples/demos/legacy/**` 9 个 + `examples/struct.cypy`），不是本单删的。
9. **（操作缺陷，已入账 BUG-51）**BUG-39 首版把「函数体之外」的作用域判定直接套到 `return` 上，
   吃掉了宏体与宏展开片段里合法的 `return`（`macro m(ts: Tokens) -> Tokens = return ts`），
   展开路径还把异常吞成一条 warn ⇒ **整条宏调用从产物里消失**。首版"波及面实测"只跑了
   `examples/` 27 份就写下了过强的结论，真信号来自随后的全量 pytest。
   修回：`Parser(body_scope=...)` 只对宏体/展开片段放宽，`_scope_stack` 不动（`_is_module_level()`
   的语义保持原样，宏体里仍可生成 `struct`/`impl`）；补 3 条永久锁（见 §二 表格下方与 §三 的
   `macro_exemption` 组）。
10. **（操作缺陷，未入账——它是流程性的）**一次"看着是空操作"的 Edit（把 `# ---- BUG-35` 段落标题
    末尾的换行一起吃掉）把下一行 `def test_bug35_...` **并进了注释里** ⇒ 该用例从收集里**静默消失**，
    而"全绿"照旧（消失的用例不会失败）。抓到它的不是测试，是两样东西：
    作用域化 lint 判据的 **E501**（合并出来的那行 118 列）与 `fix_r2_lockproof.py` 里
    写死的 **`collected >= 18`** 计数门。⇒ 口径补一条：**新增测试必须配收集数下限**，
    否则"删掉一条测试"在整套门禁里是零成本的。
11. **（操作缺陷，同一族的第二次）**紧接着又跑了 `black .fist-loop-20260927/*.py` ⇒
    black 自述 **35 files reformatted**（清单与命令见 `.fist-loop-20260927/r2fix/black_sweep.txt`）。
    范围只在本 lane 自己的临时工作区：这些脚本**未纳入版本控制**（`git ls-files` 不含它们 ⇒
    我给自己立的快照机制也覆盖不到），行为不变（black 只重排文本），且本环后面要用的三个驱动
    `close_stage_generic.py` / `report_kit.py` / `check_claims.py` 都在"left unchanged"那 32 个里，
    收口链未受影响（收口跑完即为证据）。记这条是为了口径：
    **"只格式化我写的文件"这句话本身不够**——要说清范围、在不在版本控制里、有没有快照，
    否则同一个错误会在第二个目录上再犯一次。
12. **收口规格的法名里钉了过时数字**（判据文本缺陷，本条当场补）。`close_r2_fix.json` 的 L7/L8 是
   在锁数还是 15、pytest 下限还是 1883 时写的，之后测试涨到 18 条、下限改到 1886，我只重量了
   证据件的 needle/min_chars（24 条全命中），**没有重量法名里的数字**，于是这两条被原样发到服务端：
   - `L7 三套基线与改动半径：pytest ≥1883、自研 47/47、e2e 25/25、HEAD 仍 17d68b4、亲笔行 lint 零违例`
   - `L8 锁死承重：6 单回退矩阵逐单转红、零混因、对照仍绿、15 条全收集，且有必然违例自检`

   实测值是 `pytest 1886 passed`（收集 1886）与本轮新增 **18** 条锁 ⇒ 法名偏松（1883/15 是更低的门），
   不会放过坏产物，但**账面文字与实测不同源**。服务端 120 个工具里没有任何一个能改
   `description`（见 `report_bug` 的 Omega 链教训），这两行不可撤回 ⇒ 真值以本报告、
   `memory/bugs.md` 的 FIXED 段与门禁表 ①⑩（分别读 `full_tree.collected`≥15 实测 18、
   `pytest.passed`≥1886）为准。口径补一条：**"起跑先量"要覆盖所有会被引用的文本，
   包括我自己写在标题/法名里的数字**，不只覆盖 needle。
13. **（操作缺陷）根任务上卷驱动不可重入，我按错误顺序跑了两次**：`close_root_generic.py` 的根 L4
   产物门要求报告文件已在盘上，而我在报告尚未生成时先发第一次 ⇒ 第一次已经把 8 支分支
   execute→submit→Omega 链上卷完、根任务也 claim/execute/submit 到 `待验收`，
   然后才在 L4 门前 `REFUSE`（RC=2，不写 `close_r2_fix_root.out.json`）。
   补出报告后重跑第二次，驱动不知道"已经做过"，于是产生 **30 条被拒**，全部是"已完成/状态不对"一族，
   逐字（节选，全量见 §被拒原文）：
   - `omega_spec_create T0r56.1 → 语料 [spec:T0r56.1:r1] 已通过审核，无需重复创建`
   - `verify T0r56.1 → 非法验收: 任务处于 [已完成]，需先 submit`
   - `claim T0r56 → 非法迁移: claim 要求状态 [待领取]，当前是 [待验收]`
   - `omega_spec_create T0r56 → 任务 [T0r56] 未开启 Omega 强验证（description 缺少 [omega:required] 标记），无需创建语料`

   终态经 sqlite 逐号核对无损坏：根 `T0r56=已归档`（assignee/completed_by 均为 `cypy-fixer`）、
   8 支分支 `已完成`、16 张叶子 `已完成`，`leaves_done=16`。教训口径：
   **收口三步的顺序是「阶段链 → 报告落盘 → 根上卷」**，且"重跑一次驱动"不是幂等操作——
   服务端拒绝不可撤回，重入前要先读状态而不是靠驱动自己判断。
14. **（操作缺陷）审计器的窗口判据把 carry 名单读成"已修"，我修它时又写坏了自己的脚本**：
   `check_claims.py` 的 A 类规则原来取「`BUG-N` 前后各 80 字符」窗口里出现修复词就算主张——
   页脚那一行里 `carry=` 段的每个号都离 `fixed=` 不足 80 字符 ⇒ 首次实跑把转结单
   BUG-48 报成了"报告说它已修"（**假红**：它明明写在 §六 转结栏）。修法不是放宽而是收窄到位：
   ① 页脚按结构化清单取号（截到下一个空白，不吃 `carry=` 段）；② 散文里修复词必须在
   该号 40 字符内，且**中间不夹别的 BUG 号**；③ 含 `fixed=` 的整行不参与散文扫描；
   ④ 逐字引用的服务端原文写在围栏代码块里，A 类先摘掉围栏与行内码再看主张
   （B/C 类仍读全文 ⇒ 把编造的号藏进反引号这条路不成立）。
   配三向自检，用例与实测存在 `.fist-loop-20260927/check_claims_selftest.json`：
   合成号"已修"必被抓、`carry` 名单必不算主张、围栏里的引用必不算主张，三条都过
   （`check_claims.py --selftest` 的 `refuse` 为空）。改完对本报告的实测是
   被声称已修的号恰好 6 个（35/39/44/45/46/47）且 6 条都有 FIXED 段、`refuse=[]`。
   同一批修补里我又犯了记录过的老毛病：heredoc 里的换行转义被外层字符串吃掉 ⇒
   写出的脚本有两处字符串断行（`SyntaxError`），且 `write_text` 排在 `ast.parse` 之前，
   坏内容先落了盘。这次 30 秒内自查恢复（按行索引重写 + `chr(10)`，改完再 parse），
   但要写进口径：**改脚本必须"先在内存里 parse，通过才落盘"**，否则
   这类未纳入版本控制的守卫文件坏起来没有任何回滚点。

## 六、未做与转结

| 项 | 为什么不进本环 |
|----|----------------|
| BUG-48 `watch` 不重编译 | CLI 没给 `HotReloadEngine.start` 传 `on_reload` 回调，属"已声明未实现"的功能补全 ⇒ 按裁定归**推进**半径（本环不混做） |
| BUG-49 过期实现状态栏 | 改的是 `SYNTAX/33` 的状态行措辞 ⇒ 冻结文档，只挂账（§七 裁决项 3） |
| BUG-40 flake8 配置不生效 | 二选一（加 `flake8-pyproject` 依赖 vs 搬 `.flake8`）是配置口径变更；本轮先用作用域化 lint 判据绕过，仍待裁决 |
| BUG-41 测试类同名遮蔽（6 条用例失踪） | 修法必然动既有测试（改名或删除），与本环红线互斥 ⇒ 交裁决 |
| BUG-42 产品码同名方法重复（死代码） | 要先 `git log -L` 判哪份是意图，属重构面 ⇒ 转结 |
| BUG-43 mypy 声明 python_version=3.9 整轮中断 | 配置口径 + 依赖里有 3.10 语法 ⇒ 交裁决 |
| BUG-35 的深嵌套 `RecursionError` 半边 | 需 parser 深度守卫（会改错误面形状），本环只修分桶 ⇒ 已在条目 FIXED 段明写"部分修" |
| struct 方法的隐式 self 写法 | 观察，未入账：`def m(dx: int)` 体内用 `self` 报 `Undefined name 'self'`；文档形状是显式 self，故不断言为缺陷 |
| 账本 4 条孤儿 bug task（`T0r2..T0r5`） | 收口尾声新跑的三向对照（`verify_r2_ledger3way.py`，只读取数）量到：服务端 ns `bugs` 有 47 行，账本 51 条里有 43 条带 `task_id`，这 4 行不被任何条目引用（状态都是 `已暂停`，来历指向 09-26 轮）。账本侧无 close/删除 API ⇒ 不在本环动它，交 R2-验证 定性 |
| BUG-44..51 是「只发卡未派生任务」 | 同一件三向对照反解 `call_log` 的 `report_bug` 回执：这 8 单的 `publish_task` 都没开 ⇒ 只有 bug 卡、没有可 claim 的任务行。本环的修复证据因此挂在 `T0r56.x` 枝干上而不是 bug 任务上（合法但两面账不互指），是否统一口径交 R2-验证/裁决 |

## 七、交人类裁决

1. BUG-46 的 a) 真做持久化注册（写用户 site-packages 的 `.pth`/`sitecustomize`）要不要做？
   自动轮不动用户环境；若批准，我按 `CYPY_HOOK_*` 环境变量注入测试目录实现，测试不碰真环境。
2. 轮末本地 commit + tag：本树 09-26 轮与 R1 轮的改动仍未提交（脏行见 §四），
   一次 bundled commit 会把并发 lane 的在飞改动记成本轮交付 ⇒ 需先答"哪一份是权威工作树"。
3. BUG-41/BUG-43 两类"动既有测试/动配置"的修法是否放行（红线：不弱化既有测试）。
4. **BUG-50 的处置**：`parser.py`/`macro_expander.py` 已被 `black` 整档重写且**不可回滚**。
   三条路请选一条：a) 接受现状（我在提交说明里把"19 行真实改动"与"整档重排"分开列）；
   b) 由持有原始文件的一方（09-26 轮 / R1 轮作者，或用户本地备份）给出原文，我重放那 4 处改动；
   c) 只补一条范围化 `black --check` 门禁（只判本轮改动的 hunk），文本维持现状。
   自动轮不再对这两档做任何排版动作。
