# R2-验证（verify）正文

环节口径：本环**不动产品码**。任务是独立复算上一环的结论、并对 R2-修复 的 6 单做对抗复测。
`HEAD` 保持 {{verify_r2_baselines.json|git.head}}，暂存区 {{verify_r2_baselines.json|git.staged}} 个文件
（红线：不 add / 不 commit / 不 push）。

## 一、本环做了什么

- 三套基线各起干净子进程**独立复算**（不复用修复环的数字）：
  pytest `{{verify_r2_baselines.json|pytest.line}}`（收集 {{verify_r2_baselines.json|pytest.collected}} 条），
  自研 `{{verify_r2_baselines.json|suite.line}}`，e2e `{{verify_r2_baselines.json|e2e.line}}`；
  拒绝清单 `{{verify_r2_baselines.json|refuse}}`。
- 27 条对抗探针（`verify_r2_probe.py`，独立夹具、只用调用面读数）：
  `{{verify_r2_probe.json|refuse}}` ⇒ R2-修复 的 6 单在本环自己构造的形状下**没有一条被推翻**。
- 账本三向对照（`verify_r2_ledger3way.py`）：账本 {{verify_r2_ledger3way.json|ledger.entries}} 条、
  带 `task_id` 的 {{verify_r2_ledger3way.json|ledger.with_task_id}} 条、带 FIXED 段
  {{verify_r2_ledger3way.json|ledger.fixed_sections}} 条；服务端 ns `bugs`
  {{verify_r2_ledger3way.json|server.bug_tasks}} 行。
- 入账 1 条新缺陷 **BUG-52**（medium，`T0r58`）：项目声明的 formatter 口径与仓库状态不兼容。
- 自曝并处置 1 次**双发事故**（BUG-53/`T0r59`），处置方式见 §五 第 2 条。

## 二、对 6 单的对抗复测（逐条给"我自己构造的形状"）

| 单 | 本环新构造的形状 | 实测 |
|----|------------------|------|
| BUG-44 | struct 里 `@staticmethod blank(n: int = 3)` + `@classmethod make(cls, tag: str = "x")` + 绑定方法 `shout` | `def blank(n=3):`、`def make(cls, tag="x"):` 均无注入的 `self`；`shout` 仍带 `self` 且只有它挂 `@cython.binding(False)`（`P1.*` 四条全绿） |
| BUG-44 空白面 | **class（非 struct）**里的 `@staticmethod`/`@classmethod`（修复环只改 struct 分支） | `def version():` 无 self、`def named(cls, tag):` 保留显式 `cls`（与 SYNTAX/08:123 的文档形状一致）、`bump` 仍带 self（`P2.*` 全绿）⇒ 这一面不是缺陷，但**修复环没有锁它**，转结见 §六 |
| BUG-45 | 参数位 `cfg: Point = __implicit_default__`（文档形状） | 产物 `Point.__implicit_default__()`（`P3.param_desugared` 绿） |
| BUG-45 边界 | 局部绑定位 `p: Point = __implicit_default__` | rc=1，诊断 `Undefined name '__implicit_default__' at 7:16`。SYNTAX/06d:40-53 只在**参数位**给过示例 ⇒ 本环**不占号**，作为观察项留在 `P3b.observation_only` |
| BUG-39/51 | 模块级 `return 0`、class 体内 `return 1`、宏体 `macro emit(ts: Tokens) -> Tokens =` + `return ts` | 前两者 rc≠0（带行列），宏体 rc=0（`P4.*` 三条成对全绿）⇒ 守卫既不过头也不足 |
| BUG-35 | 语法错误源 vs 根本不存在的源 | 语法错误不再被写成「读取文件错误」，缺文件仍是该桶（`P5.*` 成对绿） |
| BUG-46/47 | `hook install` 与 `hook status` 各起新进程 + 第三方进程 `import cypy_hook` | install 横幅含 "current process"、status 不再谎报 [OK]、包级三函数可导入（`P6.*` 三条绿） |

## 三、新入账：BUG-52（formatter 声明与仓库状态不兼容）

复跑口径（两条命令，本环实测）：

- `python -X utf8 -m black --line-length 100 --check cypyc cypy_bridge scripts tests` ⇒
  **{{verify_r2_file_bug52.json|measure.reformat}} files would be reformatted,
  {{verify_r2_file_bug52.json|measure.unchanged}} left unchanged**（这些目录共
  {{verify_r2_file_bug52.json|measure.py_files}} 个 `.py`）
- 本轮改动半径内 7 个 `.py`：不满足的是 `cypyc/cli.py`、`cypy_hook/hook.py`、
  `cypyc/codegen/cython_generator.py`（其余 4 个干净）⇒ **债在文件级，不在 R2-修复 的亲笔行**

为什么这不只是格式洁癖：`pyproject.toml:49-50` 声明了 `[tool.black] line-length = 100`，
`PROJECT-SPEC/02-命名与源码规范.md:46` 要求「提交前跑 lint/format（如项目配置）」⇒
contributor 照字面执行 `black .` 就会重写 {{verify_r2_file_bug52.json|measure.reformat}} 个文件。
BUG-50 正是这句话在两个文件上的单机版本。

## 四、BUG-50 损害面的复核（本环给出的新数）

以 HEAD 为底、`difflib` 数改动行，并把 HEAD 版本先过一遍同配置 black 再比：

| 文件 | 对 HEAD 的文本差 | 对 `black(HEAD)` 的差 | 其中纯排版 |
|------|------------------|------------------------|------------|
| `cypyc/parser/parser.py` | {{verify_r2_probe.json|probes['P9.black_noise_split'].parser_py.vs_head_raw}} | {{verify_r2_probe.json|probes['P9.black_noise_split'].parser_py.vs_head_after_black}} | {{verify_r2_probe.json|probes['P9.black_noise_split'].parser_py.attributable_to_formatting}} |
| `cypyc/parser/macro_expander.py` | {{verify_r2_probe.json|probes['P9.black_noise_split'].macro_expander_py.vs_head_raw}} | {{verify_r2_probe.json|probes['P9.black_noise_split'].macro_expander_py.vs_head_after_black}} | {{verify_r2_probe.json|probes['P9.black_noise_split'].macro_expander_py.attributable_to_formatting}} |

两条修正性结论（都比 BUG-50 卡片里的原说法更准）：

1. **HEAD 不是 black 之前的底**：`P7` 实测对 HEAD 的 AST 节点直方图差
   {{verify_r2_probe.json|probes['P7.semantic_vs_text'].parser_py.ast_hist_delta}}
   个节点（`{{verify_r2_probe.json|probes['P7.semantic_vs_text'].parser_py.text_lines_delta}}`
   行文本差）⇒ 这里面混着 09-26 与 R1 两轮**未提交的功能代码**。所以"1885 行都是 black 造成的"
   这句在本环被否掉，正确的拆法是上表（parser.py 约 {{verify_r2_probe.json|probes['P9.black_noise_split'].parser_py.attributable_to_formatting}} 行是排版噪声）。
2. BUG-50 的**不可回滚性仍然成立**：仓库外快照 `snapshot_tracked.py` 是在 black 之后跑的，
   没有任何一份 pre-black 文本存在（IDE 当日无快照、索引 blob == HEAD blob）。
   给 §七 裁决项 4 的新信息是：选项 b（重放那 4 处）现在**有可算的落点**——
   以 `black(HEAD)` 为底重放即可复现 {{verify_r2_probe.json|probes['P9.black_noise_split'].parser_py.attributable_to_formatting}} 行噪声被剔除后的形状。

## 五、本轮自身缺陷（8 条：4 条判据缺陷 + 4 条操作缺陷）

1. **夹具撞词被读成回归**：`def go()` 撞上 SYNTAX/20 的并发关键字（诊断
   `Expected IDENTIFIER, got GO at 16:5`）、`string` 应为 `str`、宏写成 `macro … : ` 而非
   `macro … = `。三者都是我的夹具错，不是产品缺陷——与 R2-修复 §五 第 4 条同型。
   补救是把文档形状抄进探针头注（`verify_r2_probe.py` 已写）。
2. **（操作缺陷）重跑未加幂等守卫的入账脚本 ⇒ 双发**：`verify_r2_file_bug52.py` 首跑
   `report_bug` 已成功（BUG-52/`T0r58` 落账），随后崩于取"下一条条目标题"的 `txt.index(...)`
   （账本最后一条没有后继标题）⇒ 证据件没写成。我按"失败=没发生"重跑同一条命令 ⇒
   又发一张逐字相同的 **BUG-53/**`T0r59`。服务端没有任何删除/合并/改 description 的 API，
   唯一可行处置是给后发那条追加 `### DUPLICATE` 段并指认正身（已做），
   `T0r59` 保持 `待领取` 但**不应被 claim**。机制化：入账/上卷类脚本一律先回读状态，
   并把"summary 命中数必须恰好为 1，否则 REFUSE"做成门禁。
3. **重复检测键截断造成 3 组假双发**：新加的 dup 判据最初用 `summary[:40]` 作键，
   把 BUG-3/BUG-11（同文件 `project_compiler.py` 的 `:826` 与 `:539`）和
   BUG-5/BUG-9/BUG-10（`hot_reload.py` 的 `:110`/`:253`/`:457`）并成"双发"⇒ **假红**。
   换成整条 summary 作键后只剩 BUG-52/53 这一对真双发（且已被 `### DUPLICATE` 放行）。
4. **`ast.dump` 分割假设错**：`P7` 第一版用 `dump.split("), (")` 数语义单元，
   Module 只有一个顶层节点 ⇒ 两档都数出 1、`ast_common_prefix=0`，看着像"语义没变"。
   换成节点类型直方图后才露出真实的千级差（进而发现第 6 条）。
5. **产物判据在空文本上恒真**：探针第一版没钉 `rc==0`，`pyx=""` 时
   `"X" not in text` 直接通过 ⇒ 差点把"编译失败没出产物"报成"产物里没有该字样"（绿）。
   补 `require_emit`（rc=0 且 .pyx>40 字符）后才拿到真信号。
6. **`CompletedProcess.data` 笔误 + heredoc 转义吞掉 `\n`**：前者 `AttributeError` 当场暴露；
   后者三次把生成的脚本写成断行字符串（`SyntaxError`），其中一次 `write_text` 排在
   `ast.parse` 之前，坏内容先覆盖了唯一副本（这类守卫脚本未纳入版本控制 ⇒ 无回滚点）。
   口径：**先在内存 parse 通过再落盘**；需要字面反斜杠时用 `chr(92)` 拼。
7. **三向对照的 `row_factory` 只设在旧连接上**：`call_log` 那段用 `con2` 却忘了
   `con2.row_factory = sqlite3.Row` ⇒ `r["ts"]` 抛 `TypeError` 被 `except Exception: continue`
   吞掉，`filed` 空表 ⇒ 8 条全部误判成"找不到回执"（假红）。与 R2-修复 §五 第 5 条同族
   （`%(text)s` 恒不命中）：**空的取数通道看起来和"没有违例"一模一样**。
8. **判据文案与实测数字不同源的余震**：R2-修复 的法名里钉着 1883/15（实测 1886/18），
   本环起 spec 时改成从证件反解，不再手抄数字；这条是上一环 §五 第 12 条的延续记录。

## 六、未做与转结

| 项 | 为什么不进本环 |
|----|----------------|
| class（非 struct）侧的 `@staticmethod`/`@classmethod` 无锁 | 复测**没抓到缺陷**（形状正确），但 18 条锁只覆盖 struct 分支 ⇒ 属"缺回归网"而非缺陷，交打磨环补锁 |
| `__implicit_default__` 在局部绑定位的形态 | 未文档化 + 已被显式诊断（rc=1 带行列），按口径只记观察不占号 |
| BUG-48 的 `watch` 不重编译 | 已声明未实现 ⇒ 推进半径 |
| BUG-52 的三选一修法 | 全仓 `black` 提交属人量级不可逆动作；增量门是配置变更；改声明要动 `PROJECT-SPEC/` ⇒ 三条都在裁决面 |
| 账本 4 条孤儿 task（`T0r2..T0r5`） | 逐号读过：`T0r2/T0r3` 是 09-26 探工具用的 `[probe]` 合成行，`T0r4/T0r5` 是 BUG-1 的重发残留（BUG-1 的正身是 `T0r6`）⇒ 服务端无删除 API，只能照列表披露，不据此宣告账本坏 |
| `fixed_but_still_marked_OPEN`=41、`bug_card_only`=8 | 都是账本无 close API 的既定形状（标题栏恒 `OPEN`），本环把它们**做成数出来的字段**而不是靠叙述 |

## 六b、对 R2-修复 报告的一处更正

R2-修复 §五 第 13 条把根上卷那 **30 条被拒**整体归因给"我重跑了驱动"。本环拿到了对照组：
`T0r57` 的根上卷**只跑了一次**（报告先落盘，再驱动），服务端仍回 **6 条**——
`claim/execute/submit → 非法迁移: … 当前是 [待验收]`（8 支分支全部 `已完成` 后根被级联推到 `待验收`）
与 `omega_spec_create/review/result_verify → 任务 [T0r57] 未开启 Omega 强验证`（根无 `[omega:required]`）。

⇒ 正确的拆法是：**6 条是既定语义**（R2-修复 那一次也一样会有），**其余 24 条才是重入产生**。
本环的 `refused_count=6` 因此不是"链坏"的信号，也不需要在 R2-修复 的报告里追加拒绝数；
但那条 §五 第 13 条的因果写得过宽，这里更正，并把它转成一条通用判据：
**根上卷的合法被拒基线是 6 条**，超过 6 才说明有人重入过（后续轮的报告按这个数核）。

## 七、交人类裁决

1. **BUG-52 选哪条修法**（全仓格式化提交 / 只设 hunk 级增量门 / 改规范措辞并在 pyproject 注明不追存量）。
   自动轮不独走：第一条会产生 {{verify_r2_file_bug52.json|measure.reformat}} 文件的巨量噪声，
   正是 BUG-50 的放大版。
2. **BUG-53/**`T0r59` 的处置：账本已标 `### DUPLICATE` 并指认正身 BUG-52，
   但服务端那一行仍是 `待领取`。要不要人工把它 reject/暂停？自动轮不动别人的账。
3. **BUG-50 的处置**沿 R2-修复 §七 第 4 条继续挂：本环补的可算落点（以 `black(HEAD)` 为底重放）
   是否作为选项 b 的执行方案。
4. **时间盒与门禁**：本环 2026-09-27T10:12Z 发根单、10:31Z 进入收口，墙钟约 19 分钟；
   其中三套基线独立复算一轮 ~8 分钟（pytest 全量本次 `{{verify_r2_baselines.json|pytest.line}}`，
   耗时随并发波动），门禁按原口径不缩；若要把每环压进更小的时间盒，
   只能砍探索深度，不能砍复算。
