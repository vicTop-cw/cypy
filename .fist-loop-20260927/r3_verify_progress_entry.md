
### R3-验证（第 3 轮第 3 环）· 收口记录 · 根 `T0r71`

- 报告：`memory/reviews/20260928.01.25.00.md`（`[selfdrive-verify]` 页脚）；判据件 6 张：
  `verify_r3_matrix.json` / `verify_r3_callsite.json` / `verify_r3_report_audit.json` /
  `verify_r3_baselines.json` / `verify_r3_irreversible.json` / `verify_r3_self_audit.json`。
- **逐单回退矩阵**：`rows=6/6`、`identity=6`（6 个被测模块 `__file__` 落在快照树）、
  `sha_verified_rows=6/6`、`all_restored=1`；每行「字面锚点计数 ==1 才替换 → `py_compile` →
  跑锁 → 按 mutation 前字节回写 → sha256 逐字比对」。该件另含 **恒真格自检**：
  mutation 后文本与原文逐字相同即判该行空转并拒（防"针没打到却报绿"）。
- **底树改判**：run1 用 `git archive HEAD` 造出与 mutation 无关的假红
  （`AttributeError: 'function' object has no attribute 'union'` ⇒ HEAD 的包 `__init__` 仍把同名函数
  导在子模块之前），已归档 `verify_r3_matrix_run1_headbase.json` + `r3verify_logs/premise_run1_headbase.log`；
  权威底树 = `git ls-files` 全集按盘上内容复制 + 本轮 7 档覆盖（tracked 却已不在盘上的 10 档点名）。
- **前提格**：快照树里 `17 passed / --collect-only 实收 17 / 红 []`；身份的第二重是**因果证明**——
  工作区 7 档全程 sha 不变 ⇒ 红只可能来自快照码（跑错副本就整行红不了，矩阵自我作废）。
- **上一环主张回算**：`carried_claims=6/6`（重跑寻虫环同夹具：C1/C3/C4/C6 现形→不现形，
  C5/C8 仍现形，与页脚 flips/kept_red 自述一致）、`declared_side_still_true=6/6`（逐件从盘面字面重算）。
- **调用面独立复验**：16 条全真（含 `--bridge --generate-setup` 组合、`--bridge --emit-cython`
  必须明确decline、realloc 全生命周期 `malloc→realloc→memset→读回 b'AAAA'→free`、
  `get_type_hints` 对象相等、另外 6 个哈希种子 + 双环新图、冻结形 `struct Box<T>` 走 CLI 出码）。
- **审计上一环报告与账本**：计数反解 `23/23` 相等；被拒原文**双向**集合对表（吞/造/改字都抓）；
  账本 6 段 `### FIXED` 的复跑命令当场跑，退出码与该段自述 `after rc` 相符 `6/6`。
- **自我审计（本轮报告同一把尺子）**：`verify_r3_self_audit.json`（页脚每条数字反解再对表一遍）；页脚每条数字都必须从五张判据件反解相等。
- **三套基线（run2 权威批次，refuse=[]）**：窗口 `2026-09-27T17:33:11Z → 17:43:38Z`，各格自记 `at_utc`；
  pytest `1920 passed in 355.38s`（`--collect-only` 实收 1920，下限 1920）/ 自研
  `Total: 47 | Passed: 47 | Failed: 0 | Skipped: 0` / e2e `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`
  （该格时刻由证据文件 mtime 反解并写明方法，见下条缺陷）；HEAD 仍 `17d68b4`、暂存 0、
  脏行 166、tracked 却不在盘上的 10 档点名。
  **run1 已归档**（`verify_r3_baselines_run1.json` + `r3verify_logs_run1/`）：它的 `own_snapshot_gone`
  格拿 `git worktree list` 找 `tmp_verify` 子串 ⇒ 恒真（快照树从来不是 worktree），修成数盘上目录
  （run2 实测 `own_snapshot_dirs_left: []`）后重跑；`lint.files` 也从 6 涨到 8（本环新增驱动都入 lint 面）。
- **半径（负面主张正面测）**：`radius.count=0`、`radius_claim_ok=1`——验证环不动产品码，
  由 7 个可维护目录里 mtime ≥ 开工时刻（`2026-09-27T17:01:14Z`）反解，不由自述。
- **不可逆动作**：点名 `10` 条，`live_probe=9 / manifest=1`（PR/外部可见动作只能给清单级证据并写明原因），
  `executed_none=1`；`issue_up` 这一名称在本 FIST 构建的 30 个工具里**不存在**，
  最近似是 `report_bug`（bug 上报）+ `publish`（任务上报）⇒ 由寻虫/修复环承担，验证环不冒充"已开"。
- **本环自身缺陷 14 条**（判据/工具 10 + 操作 4）进 §六，六条值得跨轮记住：
  ① 禁 commit 的仓里回退矩阵的底树必须是**盘面快照**，`git archive HEAD` 会造混因红；
  ② `pytest -q` 全通过态不打印 `collected` ⇒ 收集数只能 `--collect-only` 数 nodeid（否则绿树恒红）；
  ③ 反解出**空清单**是判据坏了的第一个信号，必须写成 refuse 而不是"对方说谎"；
  ④ 报"入口做不到 X"前先证明输入形状出自冻结规范（`generic struct` 不在 SYNTAX/11，
  而上一环的锁夹具用的正是它 ⇒ 转结 R4）；
  ⑤ 报告里的**时间状语也是主张**——"同一时刻复算"实际是跨 10.5 分钟的一批连续跑，
  措辞必须降到盘面能证明的程度（各格自记 `at_utc` + 窗口字段）；
  ⑥ 同形 `return` 的批量补丁 `replace(..., 1)` 只吃掉第一处 ⇒ "每格自记时刻"当时只落地两格，
  第三格靠证据文件 mtime 反解补上并在件里写明方法（不冒充驱动自记）。
- 时间盒：17:01 开工（根发布）→ 17:45 起收口，取证面 ≈ 44 分钟、含两套全量各约 6~9 分钟；
  终版时刻见页脚 `generated_at`。

转结新增（R4 输入）：parser 容忍 SYNTAX 未定义的 `generic struct` 形且错误要到分析层才露出
（真发现，交 R4-寻虫定性）；BUG-55 回归锁夹具应换成冻结形 `struct Box<T>`；
取子模块建议统一 `importlib`（`from cypy_bridge import union as union_mod` 在旧 `__init__` 下被函数遮蔽）；
`--bridge --generate-setup` 组合是否升格成回归锁；SYNTAX 两档相对 HEAD 的既存漂移（41 增/11 删）
要不要回退——连同历轮未提交成果一起处置。

**顺手纠一条历轮转结里的措辞债**：上一环写的是「仓库内 CRLF/LF 混用文件（`cypy_bridge/union.py`、
`cypyc/analyzer/scope_analyzer.py` 等）」，字节级实测是 **39 个纯 CRLF / 203 个纯 LF / 只有 1 个逐行混用**
（`tests/test_new_features_boundary.py`）。`union.py` 与 `scope_analyzer.py` 都是**纯 CRLF**，
不是「同一文件里两种行尾混着」——真实缺陷形状是**仓库级不统一**，打磨面的口径因此改成
「新文件统一 LF + 存量按清单交裁决」，而不是按混用去逐文件重排（基线已冻结在
`r3_polish_pre_baseline.json`：E501 355 条/48 文件、E9/W605 0 条，口径与 `pyproject.toml` 的
`max-line-length = 100` 一致）。
