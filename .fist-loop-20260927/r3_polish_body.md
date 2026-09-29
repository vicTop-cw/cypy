## 一、结论

R3-打磨（根任务 `T0r72`，8 法 / 8 枝 / 16 叶）**本环改动全部落地且三套判据体系复算未回落**：
新增 `{{polish_r3_locks.json|polish_locks}}` 条回归锁（连同 R3-修复 的
`{{polish_r3_locks.json|fix_r3_locks}}` 条共 `{{polish_r3_locks.json|declared_total}}` 条，
当场跑绿 `{{polish_r3_locks.json|collected_and_passed}}` 条），
回退矩阵 `{{polish_r3_lockproof.json|groups_ok}}/{{polish_r3_lockproof.json|groups_total}}` 组合格
（`{{polish_r3_lockproof.json|revert_groups_ok}}` 组 mutation 各自打红对应锁、
`{{polish_r3_lockproof.json|control_groups_ok}}` 组「只改注释」对照必须全绿），
改动半径实测 `{{polish_r3_baselines.json|radius.count}}` 个文件且逐档归属本单（越界
`{{polish_r3_baselines.json|radius.unexpected}}`、清单未落地 `{{polish_r3_baselines.json|radius.missing}}`，两个空表）。

不新增语义、不扩功能面：本环只做「测试夹具质量 / 缺锁的形状 / 入口 API 门面 / 文档-帮助-argparse 对表 /
lint 与行尾策略」五件事；冻结面（`PROJECT-SPEC/`、`SYNTAX/`）在开工窗口内被触碰的文件
`{{polish_r3_irreversible.json|detail[5].evidence.files_touched_in_stage_window}}` 个（详见 §五）。

| 主张 | 状态 | 依据（判据件实测） |
|---|---|---|
| BUG-55 锁夹具换成 SYNTAX/11 冻结形 | ✅ 已生效（盘上） | `frozen_fixture_swapped={{polish_r3_locks.json|frozen_fixture_swapped}}` |
| 非冻结形被 parser 容忍这件事**不静默** | ✅ 已留对照锁 | `nonfrozen_control_kept={{polish_r3_locks.json|nonfrozen_control_kept}}` |
| 三条新锁（bridge 生成 setup / bridge decline / importlib 取子模块） | ✅ 已生效且有回退证明 | `new_locks={{polish_r3_locks.json|new_locks}}`、`each_new_lock_red_when_reverted={{polish_r3_locks.json|each_new_lock_red_when_reverted}}` |
| CLI 停止直调私有 `_parse_and_analyze` | ✅ 已生效（调用面） | `cli_no_private_call={{polish_r3_api.json|cli_no_private_call}}`、残留 `{{polish_r3_api.json|cli_private_occurrences}}` 处 |
| USAGE / --help / argparse 三向一致 | ✅ 守卫可复跑 | `flags_three_way={{polish_r3_docs.json|flags_three_way}}`、`guard_rerunnable={{polish_r3_docs.json|guard_rerunnable}}` |
| lint 存量只减不增 | ⚠ 持平未减 | `reduced_by={{polish_r3_lint.json|reduced_by}}`、`e501_within_baseline={{polish_r3_lint.json|e501_within_baseline}}`；本环没减也没增，见 §六-3 |
| 行尾策略只点名不动刀 | ✅ 未整档重排 | `no_bulk_reformat={{polish_r3_eol.json|no_bulk_reformat}}`、混用文件仍 `{{polish_r3_eol.json|mixed_files_now_count}}` 个 |
| 基线只升不降 | ✅ pytest 下限 1920→1929 | passed `{{polish_r3_baselines.json|pytest.passed}}` / collected `{{polish_r3_baselines.json|pytest.collected}}` |

**没有**任何缺陷单在本环被关闭：打磨环不产生 BUG 卡，只把 R3-验证 交回的四条输入落进锁与门面。
不可逆动作（commit / push / tag / 删分支 / 删档 / 改冻结文档 / 整档 formatter）零执行旗标
`executed_none={{polish_r3_irreversible.json|executed_none}}`、被执行清单
`{{polish_r3_irreversible.json|executed}}`，逐条自证见 §五。

## 二、八法逐条落地

**法 1 锁夹具换冻结形**。R3-验证 查出 `tests/test_loop_20260927_fix_r3.py` 的泛型锁用了
`generic struct Box<T>`，而 SYNTAX/11 的冻结形是 `struct Box<T>` ⇒ 那条锁钉的是"parser 今天恰好容忍"的写法，
不是文档承诺的写法。现在夹具改成冻结形，并且**没有**把非冻结形悄悄删掉不用：另立一条现状锁
`test_polish_parser_currently_tolerates_non_frozen_keyword` 钉住"今天仍容忍"这件事，
将来谁让 parser 拒绝它，这条会红并提醒改口径，而不是等一个人读文档时才发现。

**法 2 补三条新锁**（对应 R3-验证 的三条"测到了但没锁"）：
`--bridge --generate-setup` 出可解析 setup.py、`--bridge --emit-cython` 必须明确 decline 而非静默换语言、
`cypy_bridge.union` 子模块经 `importlib` 取到的是**模块**（旧包 `__init__` 会用同名函数遮蔽它）。
回退矩阵逐组摘掉对应实现 ⇒ 对应锁变红（`.fist-loop-20260927/polish_r3_lockproof.json`：
前提 `{{polish_r3_lockproof.json|premise.passed}}` 条全绿起跑、
收尾 `{{polish_r3_lockproof.json|after_restore.passed}}` 条全绿，
工作区未被驱动改动 `workspace_untouched={{polish_r3_lockproof.json|workspace_untouched}}`）。
`{{polish_r3_locks.json|polish_locks}}` 条新锁里 `{{polish_r3_locks.json|each_new_lock_red_when_reverted}}` 条有"回退必红"证明，
其余按性质点名（一条反方向对照、一条现状探针），清单写在
`polish_r3_locks.json:revert_uncovered_locks = {{polish_r3_locks.json|revert_uncovered_locks}}`，
没被含糊成"全部有证明"。

**法 3 文档-帮助-argparse 三向一致**。守卫用 AST 从 `parse_args` 里按 `add_parser` 分段取旗标，
再和 `docs/USAGE.md` 里 `cypyc <子命令> …` 行、以及五个子命令 `--help` 的真实输出对表：
幽灵旗标 `{{polish_r3_docs.json|phantom}}`、未文档化 `{{polish_r3_docs.json|undocumented}}`、
`--help` 与 argparse 不一致 `{{polish_r3_docs.json|help_mismatch}}`（三个空表）。
通用旗标 `--output/--verbose` 走选项表
（`universal_flags_documented_in_table={{polish_r3_docs.json|universal_flags_documented_in_table}}`），
不在每条示例行里重复。本轮补上的文档行是 `--emit-code`（Cython 模式下与 `--emit-cython` 同义）。

**法 4 入口 API 打磨**。`CypyHook` 只有私有 `_parse_and_analyze`（`cypy_hook/hook.py:221`），
而全仓唯一外部调用点在 `cypyc/cli.py:495`。新增公开 `analyze_only()` 做**纯委托**：
干净源码错误清单 `{{polish_r3_api.json|clean_errors}}`、坏源码报错
`{{polish_r3_api.json|broken_error_count}}` 条，且与私有实现结果逐字相等
（`delegation_equal_on_broken={{polish_r3_api.json|delegation_equal_on_broken}}`）⇒ 语义一字没动。
CLI 侧被改动的行只有 `{{polish_r3_api.json|cli_lines_touched}}`，残留私有调用
`{{polish_r3_api.json|cli_private_occurrences}}` 处；`--check-only` 仍
rc=`{{polish_r3_api.json|cli_check_only_rc}}` 且零产物（`{{polish_r3_api.json|cli_check_only_artifacts}}`）。

**法 5 lint 存量只减不增**。口径先钉住：仓库 `pyproject.toml` 的 `[tool.flake8] max-line-length = 100`，
尺子与配置一致（pre-baseline 里 `yardstick_is_repo_config=true`）。硬违例
E9=`{{polish_r3_lint.json|hard_violations.E9}}`、W605=`{{polish_r3_lint.json|hard_violations.W605}}`、
F821=`{{polish_r3_lint.json|hard_violations.F821}}`；E501 存量
`{{polish_r3_lint.json|e501_total_before}}` → `{{polish_r3_lint.json|e501_total_now}}`，
涉及文件 `{{polish_r3_lint.json|e501_files_before}}` → `{{polish_r3_lint.json|e501_files_now}}`，
逐文件无上升（`e501_grew={{polish_r3_lint.json|e501_grew}}`）。
可比性自证：基线键形状是 `{{polish_r3_lint.json|baseline_path_style}}`，归一后与现值交集
`{{polish_r3_lint.json|files_compared_against_baseline}}` 个文件，基线之外新增
`{{polish_r3_lint.json|new_files_not_in_baseline}}`。亲笔新文件零违例
（`own_file_clean={{polish_r3_lint.json|own_file_clean}}`）——这条**当场抓到了我自己写的两条 112/101 列长行**，见 §六-3。

**法 6 行尾策略只点名不动刀**。实测盘面三档计数（改前基线）：纯 CRLF
`{{polish_r3_eol.json|eol_before_snapshot.crlf_only}}`、纯 LF
`{{polish_r3_eol.json|eol_before_snapshot.lf_only}}`、逐行混用
`{{polish_r3_eol.json|eol_before_snapshot.mixed}}`；本轮跑完混用仍是
`{{polish_r3_eol.json|mixed_files_now_count}}` 个（`{{polish_r3_eol.json|mixed_files_manifest}}`）。
本轮新文件强制纯 LF（`new_file_profile={{polish_r3_eol.json|new_file_profile}}`），
四个被改文件逐档与改前快照比对，改动行数：
`cypyc/cli.py` `{{polish_r3_eol.json|changed_lines_per_file[cypyc/cli.py]}}`、
`cypy_hook/hook.py` `{{polish_r3_eol.json|changed_lines_per_file[cypy_hook/hook.py]}}`、
`docs/USAGE.md` `{{polish_r3_eol.json|changed_lines_per_file[docs/USAGE.md]}}`、
`tests/test_loop_20260927_fix_r3.py`
`{{polish_r3_eol.json|changed_lines_per_file[tests/test_loop_20260927_fix_r3.py]}}`，
单档上限 `{{polish_r3_eol.json|cap_per_file}}` ⇒ 超上限即判"像整档重排"；行尾类别漂移
`{{polish_r3_eol.json|line_ending_class_drift}}`。

**法 7 三套判据体系与红线复算**。见 §四。

**法 8 改动半径与报告自洽**。见 §三、§六。

## 三、锁的承重证明（不是"跑绿"就算）

| 组 | mutation | 期望变红的锁 | 其余锁 | 结果 |
|---|---|---|---|---|
| G1 | 夹具退回 `generic struct` | 冻结形锁 | — | 红＝预期 |
| G2 | 撤回 `--emit-code` 文档行 | 三向一致（完整性方向） | 反方向锁 + bridge setup 锁**必须仍绿** | 红＝预期 |
| G3 | CLI 退回直调私有 | 调用面锁 | — | 红＝预期 |
| G4 | 摘掉公开门面 | 门面锁 | 调用面文本锁仍绿；两条 BUG-56 check-only 锁同因连带（白名单记因） | 红＝预期 |
| G5 | 让同名函数重新遮蔽子模块 | importlib 锁 | BUG-57 doc 锁同因连带（白名单记因） | 红＝预期 |
| G6 | 摘掉 bridge 的 generate-setup 接线 | bridge setup 锁 | — | 红＝预期 |
| G7 | 摘掉 bridge 的明确 decline | bridge decline 锁 | — | 红＝预期 |
| C1 | **只加一行注释** | 无 | `{{polish_r3_lockproof.json|premise.passed}}` 条全绿 | 绿＝预期 |

窄性断言（`must_stay_green`）`{{polish_r3_locks.json|narrowness_asserts}}` 处全过
（`must_stay_green_all_ok={{polish_r3_locks.json|must_stay_green_all_ok}}`），
同因连带白名单逐条写了"为什么这是同一个原因"而不是"跨件污染"（`polish_r3_lockproof.json:groups.*.same_cause_reds`）。
快照树跑完自删：`snap_left={{polish_r3_lockproof.json|snap_left}}`
（这条曾经恒真过，改成数盘上目录后才抓到 7 个历次失败留下的临时树，见 §六-2）。
两把锁文件在证据落盘那一刻的身份：`{{polish_r3_locks.json|lock_file_sha256}}`
（同一棵树上的回退矩阵、证据件与本报告三处引用同一 sha，防止"拿旧绿交新账"）。

## 四、三套判据体系（同一批连续复算）

| 体系 | 命令 | 下限 | 实测 |
|---|---|---|---|
| pytest | `python -X utf8 -m pytest tests/ -q -p no:cacheprovider --no-header -o addopts=` | 1929 | passed `{{polish_r3_baselines.json|pytest.passed}}`、collected `{{polish_r3_baselines.json|pytest.collected}}`、rc `{{polish_r3_baselines.json|pytest.rc}}`、failed `{{polish_r3_baselines.json|pytest.failed}}` |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | 47/47 | `{{polish_r3_baselines.json|suite.fields.Passed}}/{{polish_r3_baselines.json|suite.fields.Total}}`，Failed `{{polish_r3_baselines.json|suite.fields.Failed}}` |
| e2e golden | `bash scripts/e2e_golden.sh` | 25/25 | PASS `{{polish_r3_baselines.json|e2e.fields.PASS}}`、FAIL `{{polish_r3_baselines.json|e2e.fields.FAIL}}`、UNREG/RUNFAIL `{{polish_r3_baselines.json|e2e.fields.UNREG/RUNFAIL}}`、WARN `{{polish_r3_baselines.json|e2e.fields.WARN}}` |

收集数下限的意义：**新增测试如果从收集里静默消失，它不会失败，只会让全套"照样绿"**。
所以这里同时断言本轮新锁在全量收集里现形
`{{polish_r3_baselines.json|pytest.polish_locks_collected}}` 条（驱动里的下限格
`POLISH_LOCK_NODEIDS_MIN=9`），且 `passed ≤ collected` 由件内自证格守着
（`other_counts={{polish_r3_baselines.json|pytest.other_counts}}`）。
测量窗口 `{{polish_r3_baselines.json|started_at_utc}}` → `{{polish_r3_baselines.json|finished_at_utc}}`，
各格自带 `at_utc`，所以"同一时刻"按窗口读、不按秒读。git 红线格
`all_ok={{polish_r3_baselines.json|git.all_ok}}`（HEAD / 暂存区 / 他人 worktree / 临时树四项）。

## 五、不可逆动作面：逐条点名，实测零执行

`{{polish_r3_irreversible.json|items}}` 条：live 探针 `{{polish_r3_irreversible.json|live_probe_items}}`、
derived `{{polish_r3_irreversible.json|derived_items}}`、manifest `{{polish_r3_irreversible.json|manifest_items}}`；
判据通道自测（注入一条"被执行了"的假探针）`caught={{polish_r3_irreversible.json|self_test.caught}}`
——**能红的判据才算判据**。

- `git commit`：HEAD 实测 `{{polish_r3_irreversible.json|detail[0].evidence.head}}`，仍是本轮底树 `17d68b4`。
- `git push`：本仓**有**上游 `{{polish_r3_irreversible.json|detail[1].evidence.upstream}}`，
  所以"不可能推"这句不成立 ⇒ 改测两半：本地领先数
  `{{polish_r3_irreversible.json|detail[1].evidence.ahead_of_upstream_now}}`
  与上一环实测 `{{polish_r3_irreversible.json|detail[1].evidence.ahead_at_prev_stage}}` 相等，
  且远端跟踪 ref 的 reflog 顶条（`{{polish_r3_irreversible.json|detail[1].evidence.remote_reflog_parsed}}`
  解析成功）时间早于开工。
- `git add`：暂存区 `{{polish_r3_irreversible.json|detail[2].evidence.staged_count}}` 行，
  脏行 `{{polish_r3_irreversible.json|detail[2].evidence.dirty_rows}}` 条是历轮未提交成果（只挂账不提交）。
- `git tag`：`refs/tags` 总数 `{{polish_r3_irreversible.json|detail[3].evidence.tag_total}}`，
  开工后新增 `{{polish_r3_irreversible.json|detail[3].evidence.created_after_stage_start}}`。
- 删分支 / 合并 PR：清单级——开工前没留 branch 清单快照，删除会连 reflog 一起消失，
  事后探针证不了"没删过"，只能记当下 `{{polish_r3_irreversible.json|detail[4].evidence.branch_count}}`
  个分支与所在 `{{polish_r3_irreversible.json|detail[4].evidence.current_branch}}`。
- 冻结文档：PROJECT-SPEC / SYNTAX 在开工窗口内被触碰 `{{polish_r3_irreversible.json|detail[5].evidence.files_touched_in_stage_window}}` 个。
- 既有漂移 `{{polish_r3_irreversible.json|detail[6].evidence.files}}` 档
  `+{{polish_r3_irreversible.json|detail[6].evidence.added}}/-{{polish_r3_irreversible.json|detail[6].evidence.removed}}`
  原样挂账（见下）。
- 删档：` D`/`AD` 行数 `{{polish_r3_irreversible.json|detail[7].evidence.deleted_rows_now}}`，
  与上一环实测 `{{polish_r3_irreversible.json|detail[7].evidence.deleted_rows_at_prev_stage}}` 相等。
- 整档 formatter：由半径反解，开工窗口内被触碰的半径文件
  `{{polish_r3_irreversible.json|radius_window}}` ⊆ 本环清单。
- 弱化既有测试：被改的 `test_loop_20260927_fix_r3.py` 改前
  `{{polish_r3_irreversible.json|detail[9].evidence.names_before}}` 条 `def test_`、
  改后 `{{polish_r3_irreversible.json|detail[9].evidence.names_after}}` 条、消失
  `{{polish_r3_irreversible.json|detail[9].evidence.disappeared}}` 条。
- 别人的 worktree `{{polish_r3_baselines.json|git.worktrees[1]}}` 仍在
  `{{polish_r3_baselines.json|git.worktrees}}` 列表里；临时快照树残留
  `{{polish_r3_baselines.json|git.temp_snapshots_left}}`。
- 任务库：call_log 现 `{{polish_r3_irreversible.json|detail[11].evidence.call_log_rows_now}}` 行 ≥
  上一环收口实测 `{{polish_r3_irreversible.json|detail[11].evidence.call_log_rows_at_prev_closure}}`（只增不减）；
  `issue_up` 在本 FIST 构建里**不是工具名**，命中 `{{polish_r3_irreversible.json|detail[11].evidence.issue_up_tool_rows}}` 行
  ⇒ 如实上报，不改口径、不换个名字交差。

**挂账（不执行，交人工裁决）**：`SYNTAX/01-basic-types.md`、`SYNTAX/appendix-A-keywords.md`
相对 HEAD 的既有漂移仍在。这条只能**清单级**自证：diff-vs-HEAD 分不出是谁改的
（历轮未提交与本轮在同一个 diff 里），所以只记上界，不取交集，也不冒充"本轮已核对"。

## 六、本环自身缺陷（判据与工具类 / 操作类）

判据与工具类：

1. **lint 判据拿反斜杠键去查正斜杠现值 ⇒ 48 个文件全被判成"凭空上涨"**。pre-baseline 落的是
   `cypy_bridge\compiler.py` 这种键，我的比较把现值归一成正斜杠却没归一基线，
   `baseline.get(f, 0)` 恒返回 0，于是 `grew` 里塞了整张表外加我的新文件——本来会写成"E501 全面恶化"。
   抓到它的是"每个 before 都恰好是 0"这个不像话的形状。已改成两侧同源归一，并加三条自证：
   基线自求和 == `e501_total`、文件数 == `files_with_e501`、**基线与现值交集 < 40 即判"口径没对上，本格不作数"**。
2. **锁驱动跑完不删快照树，`snap_left` 那格此前恒真**。上一环我把"临时树已清"写成从 `git worktree list`
   里找 `tmp_verify`——快照树从来不是 worktree，那格永远真。本轮改成数盘上 `snap_*` 目录，
   当场抓到 7 个历次失败运行留下的树（其中一个 33 MB）。**恒真的格子不配当门禁。**
3. **亲笔文件自己违反了自己量过的尺子**：新锁文件里两条 112/101 列长行被 flake8（仓库配置 100）抓到。
   不是判据坏，是我写的时候只按"读起来顺"排版。已折行，并**在同一棵树上重跑**回退矩阵与证据件
   （锁文件 sha 见 §三，两处引用同一串）。
4. **`api()` 第一条 `--check-only` 跑在夹具文件写盘之前**：那格读的是"文件不存在"的 rc，
   看着像"改门面后 CLI 形态变了"。删掉重复调用、先写文件再跑，并清空产物目录后重测。
5. **`locks()` 按 `must_stay_green` 取数，而被检件里那键叫 `must_stay_green_ok`** ⇒ 计数恒 0，
   "窄性断言 0 处"会被当成"没做窄性证明"。取件先证明键形状——这条我记过三次，本轮又踩一次。
6. **9 条新锁里只有 7 条有回退证明**：如果判据只写 `each_new_lock_red_when_reverted ≥ 1`，就是恒绿格。
   改成"未覆盖集合必须**恰好等于**点名的两条，否则拒"，并把理由写进件里。
7. **lint 只减不增这一格本环实测为"持平"**（`reduced_by={{polish_r3_lint.json|reduced_by}}`）：
   法 5 允许 0 不减，但报告不能把它写成"改善"。已按 ⚠ 标在 §一，并存入 §八 作为推进环可选项。
8. **写门禁时先写出了 19 条 `min: 0` 的恒绿格**。装配器的 `min` 是 `>=`，`min: 0` 对空表永远成立
   ⇒ "reds 为空""phantom 为空""refuse 为空"这类主张用 `min: 0` 就变成**永远不会红的门禁**。
   已全部换成 `equals: []` / `equals: {}` / `equals: 0`，并给自审加了一格
   "恒绿门禁格数必须为 0"（`polish_r3_self_audit.json:vacuous_gates`，门禁 ⑩-1 之外另数）——
   这条本身能红，因为它数的是 spec 而不是产物。
9. **叶子级 L4 证据早于收口件存在**：法 8 的第二张叶子（`T0r72.8.2`）用
   `polish_r3_self_audit.json` 当证据，而该件的 closure 反解格必须等收口后才算得出。
   处理方式是**两态各跑一次、同一落点**：`mode=pre-close` 先量判据件与散文（含"临时树当场重数"
   "AST 重取旗标""flake8 亲笔文件当场再跑"这些独立重算），收口后 `mode=post-close` 重跑并覆盖，
   补上全部页脚格。盘上最终留的是 post 态，服务端当时验过的是 pre 态——这层时间差不抹平，如实记在这里。
10. **页脚合成器不幂等，第二次跑就叠出同一行两个同名键**：它把新串拼在 `spec['footer']` 旧串后面，
    而旧串已经是上一轮合成结果 ⇒ 页脚里同时出现 `judge-defects=9` 与 `judge-defects=7`。
    自审按"后出现的取值"读，于是报了"页脚说 7、散文算得 9"——**这条红是真红**，
    抓到的是我自己造的第二份重复键。已改为只保留 `handoff=` 段作种子，并加两格守卫：
    种子串里混进 synthesized 键即拒、合成结果里同名键出现两次即拒。

操作类：

1. **在上一环结论上续写措辞**：差点写"本仓无上游所以 push 不可能"——实测有 `origin/master`。
   负面主张的措辞必须先过一遍盘面再落纸，不能续写。
2. **返工四次同一棵判据树**：`snap_*` 恒真格、键形状、长行、`api()` 顺序各让我重跑了一遍
   回退矩阵或证据件。返工的是我的判据，不是产品码，但时间盒里该按"判据坏"计入（本环
   `{{polish_r3_lockproof.json|started_at_utc}}` → `{{polish_r3_baselines.json|finished_at_utc}}`）。
3. **临时快照树是"事后才发现没清"**：跑本轮第一次回退矩阵时才抓到 7 个历次失败留下的树
   （含一个 33 MB），说明上一环那句"临时树已清"当时是恒真格而不是实测。
   已把目录计数同时放进锁驱动、复算件与自审三处，任何一处不清就红。

## 七、汇报口径（给人看的三行）

- 做了什么：给 R3-验证 测到但没锁的 3 个形状补锁；把一条用了非冻结语法的夹具换成冻结语法并留现状对照；
  把 CLI 对私有方法的依赖换成公开门面；文档-帮助-argparse 做成可复跑的三向守卫；
  把"别整档交给 formatter"这条教训做成了 mtime + 单档行数上限两道硬门。
- 没做什么：不新增语义、不关缺陷单、不提交、不推送、不动冻结文档、不重排行尾。
- 要谁裁决：`SYNTAX/` 既有 +41/−11 漂移（accept 或 revert）；lint E501 存量
  `{{polish_r3_lint.json|e501_total_now}}` 条是否单开清理环；
  纯 CRLF 文件（基线 `{{polish_r3_eol.json|eol_before_snapshot.crlf_only}}` 个）的行尾策略
  （`.gitattributes` 或转换，均需人工点头）。

## 八、下一环（R3-推进）输入

1. 三套体系当前地板：pytest `{{polish_r3_baselines.json|pytest.passed}}`（collected
   `{{polish_r3_baselines.json|pytest.collected}}`）、套件 `{{polish_r3_baselines.json|suite.fields.Passed}}/{{polish_r3_baselines.json|suite.fields.Total}}`、
   e2e `{{polish_r3_baselines.json|e2e.fields.PASS}}/25` —— 推进环只准往上加，加之前先抬 `PYTEST_FLOOR`。
2. 取件必须**同源归一路径口径**（正/反斜杠）与键形状自证；新判据一律配"注入一条必红"的通道自测。
3. 收集数下限与新锁条数**成对**写进门禁；消失的用例不会失败，只会让全套照样绿。
4. 临时树自删要有盘上目录计数证明；`snap_left` 之类的格子必须能红。
5. 现状探针（"parser 今天仍容忍非冻结形"）在推进环要升级为决策：要么文档承认两种写法，
   要么让 parser 拒绝并同步改锁——不许长期挂着"知道但不处理"。
6. `docs/USAGE.md` 的三向守卫只覆盖 `cypyc` 命令行；`examples/` 与 `docs/` 其余文档的旗标一致性
   仍未纳入判据（本环不扩面，留给推进环或单独裁决）。

## 九、复跑命令（逐条可粘）

```
python -X utf8 .fist-loop-20260927/polish_r3_lockproof.py
python -X utf8 .fist-loop-20260927/polish_r3_evidence.py
python -X utf8 .fist-loop-20260927/polish_r3_irreversible.py
python -X utf8 .fist-loop-20260927/polish_r3_baselines.py
python -X utf8 -m pytest tests/test_loop_20260927_polish_r3.py tests/test_loop_20260927_fix_r3.py -q -p no:cacheprovider --no-header -o addopts=
python -X utf8 -m flake8 --max-line-length 100 cypyc cypy_hook cypy_bridge tests docs scripts examples
bash scripts/e2e_golden.sh
```
