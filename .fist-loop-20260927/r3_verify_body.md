## 一、本环口径

验证环的交付物不是「又跑了一遍测试」，而是**独立出题**：不复用 R3-修复 环的任何判据件、
不读它的结论字段来给自己打分。三件事各自有承重结构：

1. **逐单回退矩阵**——把六件修复逐个改回修前文本，看该件的回归锁是否真的变红。
   「今天全绿」在这类主张里是零证据；只有回退能红，锁才在拦这条缺陷。
2. **调用面复验**——从入口（`python -m cypyc.cli` 子进程、`cypy_bridge` 真实构造、
   带 `PYTHONHASHSEED` 的子进程、真实 AST 上的 checker）打进去，脚本与修复环不同、
   旗标组合不同、图不同、种子不同。
3. **上一环报告与账本的自洽审计**——把别人说过的话当被测对象：页脚每条数字回判据件反解、
   被拒原文双向集合对表、账本 `### FIXED` 段里的复跑命令当场再跑并比对退出码。

快照树自证身份用两重：静态（6 个被测模块的 `__file__` 必须落在快照树内，实得
`{{verify_r3_matrix.json|identity}}` 个）+ 因果（工作区 7 个产品/测试文件全程 sha 不变
`{{verify_r3_matrix.json|workspace_sha_after_unchanged}}` ⇒ 红只可能来自快照里被 mutation 的那份码，
跑错副本的话整行红不了、矩阵自我作废）。

## 二、逐单回退矩阵（正面证据）

前提格先立：快照树里本轮 17 条锁全绿（`{{verify_r3_matrix.json|premise.passed}}` passed /
`--collect-only` 实收 `{{verify_r3_matrix.json|premise.collected}}` / 红 `{{verify_r3_matrix.json|premise.reds}}`）。
底树与 `git archive HEAD` 的差别见 §六 第 1 条（run1 已归档，不重跑冒充）。

| 缺陷 | 反向补丁数 | 该件变红的正例锁 | 对照锁是否被牵连 | 其余各件是否被牵连 | mutation 后 sha 复原 |
|---|---|---|---|---|---|
| BUG-55 | `{{verify_r3_matrix.json|per_bug.BUG-55.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-55.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-55.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-55.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-55.sha_equal}}` |
| BUG-56 | `{{verify_r3_matrix.json|per_bug.BUG-56.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-56.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-56.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-56.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-56.sha_equal}}` |
| BUG-57 | `{{verify_r3_matrix.json|per_bug.BUG-57.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-57.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-57.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-57.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-57.sha_equal}}` |
| BUG-58 | `{{verify_r3_matrix.json|per_bug.BUG-58.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-58.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-58.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-58.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-58.sha_equal}}` |
| BUG-59 | `{{verify_r3_matrix.json|per_bug.BUG-59.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-59.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-59.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-59.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-59.sha_equal}}` |
| BUG-60 | `{{verify_r3_matrix.json|per_bug.BUG-60.applied}}` | `{{verify_r3_matrix.json|per_bug.BUG-60.pos_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-60.ctl_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-60.collateral_red}}` | `{{verify_r3_matrix.json|per_bug.BUG-60.sha_equal}}` |

矩阵合格 `{{verify_r3_matrix.json|rows}}`/6 行（每行都要求：锚点计数先相等才替换、
mutation 后 `py_compile` 必过、该件正例锁 ≥1 红、该件对照锁 0 红、其余四件 0 连带）；
sha 逐字复原 `{{verify_r3_matrix.json|sha_verified_rows}}`/6 行，`all_restored={{verify_r3_matrix.json|all_restored}}`。

**上一环主张的回算**（法 8）：六件的声明侧今天仍在盘上
`{{verify_r3_matrix.json|declared_side_still_true}}`/6（每条都是重新从盘面算的字面判据，不是引用旧件），
上一环页脚的 flip/kept_red 主张重跑寻虫环同夹具后成立
`{{verify_r3_matrix.json|carried_claims}}`/6——四件（C1/C3/C4/C6）现在探针退出码为「不现形」，
两件（C5/C8）仍是「现形」，与「只修了声明侧那一半」的自述一致，**没有**把它们写成已修。

## 三、调用面独立复验

`verify_r3_callsite.py` 是本环新写的件，与修复环的 `fix_r3_evidence.py` 无共享代码；
只读盘面，输出物落在 `.fist-loop-20260927/tmp_verify/callsite/`（不在改动半径目录内）。
共 `{{verify_r3_callsite.json|checks}}` 条检查，全真 `{{verify_r3_callsite.json|checks_all_true}}`，
失败清单 `{{verify_r3_callsite.json|failed_checks}}`。与修复环锁的不同形处：

- 旗标组合多了一格 `--bridge --generate-setup`（上一环只锁了 Cython 模式那条路），
  以及 `--bridge --emit-cython` 必须**明确说不适用**而不是静默；
- `realloc` 用 `typing.get_type_hints` 的**对象相等**（不是字符串比对），并真的
  `malloc(16)→realloc(·,128)→memset→读回 b'AAAA'→free` 走一遍完整生命周期；
- `CUnion` 三种形状（ctypes 类型 / C 类型名 / `union()`）都赋 `3.5` 回读并比 size；
- 编译序换了**另外 6 个哈希种子**（2/3/5/11/13/12345）与一张**双环+链**的新图；
- 泛型走真实 `transpile` 入口出码（用的是 SYNTAX/11 的冻结形 `struct Box<T>`，
  不是上一环锁里那个 `generic struct` ——见 §六 第 4 条与 §七 转结）。

## 四、上一环报告与账本的自洽审计

被审对象：`memory/reviews/20260928.00.20.00.md`（R3-修复 报告）+ `memory/bugs.md` 的 6 个
`### FIXED(修复=已完成)` 段。

- 页脚/正文计数反解：`{{verify_r3_report_audit.json|counts}}`/`{{verify_r3_report_audit.json|counts_total}}`
  条相等，`counts_all_equal={{verify_r3_report_audit.json|counts_all_equal}}`。逐条来源写在
  `verify_r3_report_audit.json:detail`（每条都标了「依据哪个件的哪个字段」），
  包含 `locks=17(pos=11,ctl=6)` 对测试文件 `def test_` 实际计数、`radius=7` 对半径件、
  `flips/kept_red` 对翻转件的 `after_rc`、`judge-defects/op-defects` 对报告《六》段的编号条数。
- 被拒原文：报告《被拒原文》表与 `close_r3_fix_root.out.json:refused` 做**双向**集合对表
  （吞一条、多一条、改一个字都算不符）→ `{{verify_r3_report_audit.json|refusal_table}}`。
- 账本复跑：6 段 `### FIXED` 各自的「复跑」命令当场再跑，退出码必须等于该段自己声明的
  `after rc` → 实跑 `{{verify_r3_report_audit.json|repro_reruns}}` 段、相符
  `{{verify_r3_report_audit.json|repro_reruns_match_claim}}` 段。

## 五、三套判据体系与红线（一批连续复算，各格自记时刻）

这一批不是"同一秒"：三套体系是**连续复算**，各格自带 `at_utc`；本件窗口
`{{verify_r3_baselines.json|started_at_utc}}` → `{{verify_r3_baselines.json|finished_at_utc}}`，
开工时刻 `{{verify_r3_baselines.json|stage_start_utc}}`。凡是"同一时刻"的说法一律按这个窗口读
（上一环报告用了"同一时刻复算"字样，实际记的是起跑时刻 ⇒ 本轮把措辞降到盘面能证明的程度，见 §六 第 9 条）。

| 体系 | 命令 | 实测 |
|---|---|---|
| pytest | `python -X utf8 -m pytest tests/ -q -p no:cacheprovider --no-header -o addopts=` | `{{verify_r3_baselines.json|pytest.line}}`，下限 {{verify_r3_baselines.json|pytest.floor}}，`--collect-only` 实收 {{verify_r3_baselines.json|pytest.collected}} |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | `{{verify_r3_baselines.json|suite.line}}` |
| e2e golden | `bash scripts/e2e_golden.sh` | `{{verify_r3_baselines.json|e2e.line}}` |

git 红线：HEAD `{{verify_r3_baselines.json|git.head_ok}}`（仍是 `17d68b4`）、暂存区为空
`{{verify_r3_baselines.json|git.staged_zero}}`、脏行 `{{verify_r3_baselines.json|git.dirty_rows}}`、
其中 tracked 删除 `{{verify_r3_baselines.json|git.deleted_tracked}}`（历轮未提交，本环没动）、
别人的 worktree 仍在 `{{verify_r3_baselines.json|git.foreign_worktree_present}}`、
自己的快照树已清 `{{verify_r3_baselines.json|git.own_snapshot_gone}}`。

**负面主张正面测**：本环改动半径实测 `{{verify_r3_baselines.json|radius.count}}` 个文件
（判据：7 个可维护目录里 mtime ≥ 开工时刻的 `.py/.md/.cypy/.sh/.toml`），
`radius_claim_ok={{verify_r3_baselines.json|radius_claim_ok}}`——验证环不修产品码这件事
由文件系统反解，不由我自述。lint 面：本环亲笔的 `{{verify_r3_baselines.json|lint.files}}` 个驱动
E9/W605/F821 硬违例 `{{verify_r3_baselines.json|lint.hard_violations}}` 条
（解析行数与输出行数不等即判废，见 `lint.detail`）。

## 六、本环自身缺陷（判据/工具与操作分栏，逐条留字）

判据与工具类：

1. 矩阵底树第一版用 `git archive HEAD` 是错的：红线禁止 commit ⇒ HEAD 缺历轮未提交成果，
   run1 里 `test_bug57_union_docstrings_...` 因 `AttributeError: 'function' object has no attribute 'union'`
   而红（HEAD 的 `cypy_bridge/__init__.py` 还把 `union` 导成函数、遮蔽同名子模块），与任何 mutation 无关。
   底树改判为「tracked 文件的工作区内容 + 本轮新增文件」，run1 整体归档为
   `verify_r3_matrix_run1_headbase.json` + `r3verify_logs/premise_run1_headbase.log`，不拿它当本轮证据。
   副产品：这一格反过来证明了「HEAD 里还没有历轮修复」这件事本身是挂账项（见 §七）。
2. `-q` 的**通过态不打印 collected 行**，我却拿 `collected<17` 当夹具判据 ⇒ 6 行全被判成
   「夹具坏了」的假红（而 `17 passed` 就在同一份输出里）。换成 `--collect-only -q` 数 nodeid
   + `passed+红数` 双计数，两个数都必须等于 17。
3. 矩阵驱动初版含死代码（一段 `for rel, patch_info ...` 的空转嵌套）和一处只在 CRLF 文件下
   才构造锚点的半截逻辑；改成 LF/CRLF 两种形态各自数锚点、计数不符立即拒行而不是猜。
   教训同上一环：`py_compile` 抓不住语义死码，锚点计数才抓得住。
4. 调用面夹具第一版用了**非冻结形** `generic struct Box<T>`（SYNTAX/11 里没有 `generic` 关键字，
   泛型靠 `<T>` 表达），于是把「我自己的夹具坏了」误报成「CLI 出不了泛型码」。
   读文档 + 双形实测（两种形状 parser 都收、只有冻结形走通 CLI）之后才改判。
   顺手记下真发现：parser 容忍那个非冻结形，失败要到分析层才以 `Undefined name 'generic'` 露出。
5. 报告审计第一版读 `flips[*].after.rc`，真实形状是扁平的 `after_rc` ⇒ 反解出**空清单**，
   于是把报告说成「flips 一条都不对」。修法是加形状自检：`flips` 为空即拒、条目缺 `after_rc` 即拒，
   这样「判据自己坏了」会先于「报告撒谎」暴露。
6. 不可逆探针第一版把 git 的 `LF will be replaced by CRLF` 警告（走 stderr）并进路径清单，
   冻结文档格因此多出一个假条目 ⇒ 主张「文件数」的判据必须 stdout/stderr 分道，已加 `sh_stdout()`。
7. 同一条探针把「冻结文档相对 HEAD 的既存漂移」和「本环是否动过它们」混成一格，
   直接把本环判成「执行了不可逆动作」。拆成两格：本环窗口判据只看目录内最新 mtime；
   既存漂移单独立条点名（`SYNTAX/01-basic-types.md`、`SYNTAX/appendix-A-keywords.md`，
   mtime 全在 09-26、正文自带「实测快照（2026-09-26 11:24）」字样 ⇒ 归历轮未提交成果），
   交回裁决而不是冒充零漂移、也不是冒充本环违规。
8. 基线件的 `git.own_snapshot_gone` 第一版拿 `git worktree list` 的路径找子串 `tmp_verify` ⇒
   快照树从来不是 worktree，这一格**恒真**（恒真格不配当门禁，上一环刚为同一形状自记过债）。
   改成直接数 `tmp_verify/snap_*` 目录，并把「临时树没删」升成硬拒；快照树的清理也没放进
   矩阵驱动（跑完留了两棵），改由收口步删除后复跑基线件证明清零——本条同时是
   「临时树必删」这条纪律当场未达标，故 run1（含恒真格）整体归档 `verify_r3_baselines_run1.json`
   + `r3verify_logs_run1/`，权威数以 run2 为准。

9. 「同一时刻复算」这个词上一环和我都用了，但基线件的 `measured_at_utc` 记的是**起跑**时刻，
   而三套体系实际跨了约 12 分钟（pytest 全量 9 分钟 + 自研 + e2e）⇒ 那句话说得比盘面能证明的强。
   改法：每格自记 `at_utc`、件首写 `started_at_utc`/`finished_at_utc` 窗口与一句"这不是同一秒"的说明，
   正文措辞跟着降档。**报告里的时间状语也是主张**，同样要能被判据件反解。

10. e2e 格的 `at_utc` 在 run2 里漏记：`e2e_run()` 的 return 与 `suite_run()` 同形，第一版补丁
    只替换了前者所在的那一处（两处 return 文本几乎相同 ⇒ `replace(..., 1)` 只吃掉第一处），
    于是"每格自记时刻"这条改进只在两格里成立。修法：按 `REFUSE.append(f"e2e golden 不绿…")` 这样的
    **专属上下文**做锚点再替换，替换后逐格断言 `at_utc in doc`；本轮这一格先按证据文件 mtime 反解
    并在件里写明 `at_utc_method`（不冒充驱动自己记的）。同族教训：多处同形 return 的批量补丁，
    替换次数与"每处都改到"必须各自断言。

操作类：

11. 把 `verify_r3_irreversible.py` 写到了错误路径（`E:\IDEProjects\20260927-tmp-check\not-used\placeholder.py`，
   `file_path` 手打错），当场搬回 `.fist-loop-20260927/` 并删掉误建的空目录。
12. 清理内联 `import re` 的补丁脚本用普通字符串写含 `\{` 的替换文本，触发 SyntaxWarning 且
    **有一处替换静默没生效**（`__import__("re")` 残留）。`py_compile` 照样过 ⇒ 改完必须 grep 复验，
    不能只看编译结果。
13. 收口 spec 的 needle 一开始是「写完就交」的（没先证明每个 needle 真的在被读件里出现），
    补了一次 closer 同款预检（16 张叶子取用的 `law.artifacts` 全部 `hit=True`、件长 ≥300，
    基线件两格因未落盘而跳过）——这一步本应在写 spec 的同一轮里做，而不是收口前。
    教训：needle 型硬门的存在性检查是**零成本**的，不做就是把「服务端拒批」留到最贵的时刻。
14. 第一轮矩阵在前提格就拒（正确行为，但顺序浪费了一次全量跑）：驱动应先做「底树身份 + 前提全绿」
    再进 mutation 循环——已经是这个顺序，缺的是**先跑 1 行确认再跑 6 行**的短路口，下次加 `--one-row` 预检。

## 七、交回与转结

交回人工（本环零执行、零改动，只把状态点名）：

1. **冻结文档既存漂移**：`SYNTAX/01-basic-types.md`、`SYNTAX/appendix-A-keywords.md` 相对 HEAD 有
   41 增 / 11 删（历轮未提交）。要么认（连同历轮成果一起 commit），要么回退——只有 owner 能定。
2. **历轮成果全在未提交状态**：HEAD 仍是 `17d68b4`，工作树 166 条脏行、10 个 tracked 文件在盘上已缺失。
   矩阵底树被迫用工作区内容而不是 HEAD，根因就是这条。是否给一次本地 commit + 本地 tag 的授权，
   按既往裁决（本地 tag 不必逐轮请示）我可以自办，但 commit 不在授权面内 ⇒ 继续挂账。
3. **BUG-58 的行为半、BUG-60 的强制检查半**：本环用矩阵证明了两件的锁确实钉住「声明侧」那一半
   （改回修前文本 ⇒ 该锁即红），未消除的另一半仍在裁决面，与上一环口径一致。

转结 R4（寻虫/修复/打磨的输入，本环只给盘面事实，不当已修）：

- parser 接受 SYNTAX/11 未定义的 `generic struct` 形，错误要到分析层才以 `Undefined name 'generic'`
  露出 ⇒ 是「词法容忍非冻结形」还是「文档漏述」，交 R4-寻虫定性。
- BUG-55 的回归锁夹具用的正是那个非冻结形；冻结形 `struct Box<T>` 同样能出该缺陷签名
  （实测 holders=1/collected=1）⇒ 打磨面可把锁换成冻结形，减少一处「测试教文档」。
- `from cypy_bridge import union as union_mod` 这类取模块的写法在旧 `__init__` 下会被同名函数遮蔽
  （run1 现场）⇒ 建议统一走 `importlib.import_module`，属打磨面。
- `--bridge --generate-setup` 组合此前无锁覆盖，本环调用面复验已含并通过；是否升格成回归锁
  交 R4-修复（新增锁要配「只改注释仍绿」的成对判据）。
- `CypyHook` 仍应由入口暴露 public `analyze_only()`（CLI 现在调私有 `_parse_and_analyze`）——沿用上一环挂账。

## 八、链路与开关证据（omega / laya / call_log / issue_up）

本环的工具面证据不看回忆，看 `call_log` 表（`.fist-loop-20260927/r3_verify_calllog_tally.json`，
窗口 `{{r3_verify_calllog_tally.json|window_utc}}`）：

- 总调用 `{{r3_verify_calllog_tally.json|calls_total}}`，其中被拒 `{{r3_verify_calllog_tally.json|calls_refused}}`
  ——恰等于根任务 `T0r71` 的 6 条**既定结构性**拒绝（`{{r3_verify_refusal_split.json|by_scope}}`：
  根 6 / 枝干 0 / 叶 0；枝干与叶级出现任何一条都意味着上卷驱动被重跑过）。
- **omega 强验证是全开的**：`omega_spec_create`、`omega_spec_review`、`omega_result_verify`
  各 `{{r3_verify_calllog_tally.json|by_tool.omega_spec_create.ok}}` 次成功
  = 16 张叶 + 8 支枝干全覆盖；`omega_status` 另查 16 次。
- `laya` 这一步是**实测降级**：`laya_decide` 调用 1 次成功，返回本机 `available=False`
  ⇒ 按模板走显式降级（`split_n=8` 由 leader 规则式自决并记 `source:self`），不是没调。
- `issue_up` 这个名字在本 FIST 构建的 30 个工具里**不存在**（`select distinct tool from call_log`
  全量列过一遍），最接近的是 `report_bug`（bug 上报）与 `publish`（任务上报，本环调用 1 次）。
  本环不冒充"开了 issue_up"；上报动作按环分工落在寻虫/修复环（BUG-55..60 的号就是那么来的）。

## 九、什么现象**不算**本环的证明

- 「快照树里 17 条锁全绿」不算——那只是矩阵的**前提格**；承重的是每行 mutation 后该件锁变红。
- 「该件锁变红」单独也不算——同一行还必须证明对照锁不红、其余四件不连带、且 sha 逐字复原
  （否则可能是我把文件改坏了）。
- 「报告里的数字与正文另一处一致」不算——必须回到判据件的字段（`verify_r3_report_audit.json:detail`
  每条都写了依据哪个件的哪个字段）。
- 「探针退出码翻了」不算声明侧的证据——BUG-58/BUG-60 只修了声明那一半，行为那一半的探针
  当场仍判"缺陷在"（C5/C8 现形），这条差异是**结论**不是漏洞。
