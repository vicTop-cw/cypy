# R3-寻虫（bug hunt）报告 — 2026-09-27

`[loop:20260927-loop:R3-寻虫]` 根单 `{{.fist-loop-20260927/close_r3_hunt.out.json|root_task}}` ·
执行人 cypy-hunter · omega 强验证 / laya / issue_up / call_log 全开 ·
本轮**不修产品码**（修复是下一环的半径）。

## 一、先清点，再取虫

狩猎面轮换到 R1/R2 没深挖的**声明面矛盾**：`cypyc/transformer/`、`cypyc/analyzer/`、
`cypyc/project/`、`cypy_bridge/`、`cypyc/cli.py`。清点件 `hunt_r3_scan.json` 实测：

- 符号台账覆盖 {{.fist-loop-20260927/hunt_r3_scan.json|files}} 档 `.py`（类/模块级函数/公开符号逐档列表），
  并把每档**模块 docstring 里的编号规则**原样抄下来（后面判"规则有没有实现"要用）；
- CLI 对外承诺按调用面取：`python -m cypyc --help` rc
  {{.fist-loop-20260927/hunt_r3_scan.json|cli_declared.top_help_rc}}，子命令
  `{{.fist-loop-20260927/hunt_r3_scan.json|cli_declared.subcommands}}`；
  `transpile --help` rc {{.fist-loop-20260927/hunt_r3_scan.json|cli_declared.transpile_help_rc}}，
  真读到的旗标集 `{{.fist-loop-20260927/hunt_r3_scan.json|cli_declared.transpile_flags}}`。

为什么先清点：不先立台账，"我没找到缺陷"和"我没找"在盘上是同一个样子。

## 二、确诊 6 条并已入账（BUG-55..60）

每条都给三样：**与它矛盾的那句声明**（file:line）、**成对判据的实测**（pos 现形 / ctl 不现形）、
**能一键复跑的命令**（`hunt_r3_repro.py <ID>`，退出码 0=现形 / 1=不现形 / 2=夹具坏了）。

| 号 | 主张 | 声明面（矛盾之处） | 严重度 | 复现退出码 |
|----|------|--------------------|--------|------------|
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C1.rpc_bug_id}} | `GenericTransformer` 读 `type_params`，而 parser 的泛型节点带的是 `generic_params` ⇒ 泛型收集恒为空 | generic_transformer.py:5 自称『注册泛型参数』，:39 读 `type_params` | medium | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C1.rc}} |
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C3.rpc_bug_id}} | `cypyc transpile` 的 `--check-only/--emit-ast/--generate-setup/--emit-cython` 无人读，读它们的是只能从不可达 `else` 进入的 `run_default` | `transpile --help` 把四个旗标承诺给用户（见 §一 实测旗标集） | medium | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C3.rc}} |
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C4.rpc_bug_id}} | `CUnion` 的 docstring 示例 `CUnion(int, float)` 一跑就抛（对 Python 内建类型取 `ctypes.sizeof`） | union.py:23-31/:179 的示例文本本身就是对外唯一用法说明 | low | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C4.rc}} |
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C5.rpc_bug_id}} | `realloc(ptr, 0)` 先 free 再 `return None`，而签名是 `-> int`、文档只说返回地址；同族 `malloc(0)` 是抛 MemoryError | memory.py:195 注解与 :196-216 行为互斥 | medium | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C5.rc}} |
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C6.rpc_bug_id}} | `get_compilation_order` 把环内模块塞进 `set` 再 extend ⇒ 有环时推荐编译序随进程哈希种子漂移 | module_dependency_graph.py:200 只承诺『跳过循环中的模块』，没承诺任意序 | medium | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C6.rc}} |
| {{.fist-loop-20260927/hunt_r3_filed.json|by_id.C8.rpc_bug_id}} | `build_block_checker` 模块 docstring 规则 2『指针语法只能在构建块内部使用』没有实现（两个 visitor 只留『移除』注释，不 append error） | 规则清单在**模块** docstring :5-6，实现在 :75-84 | low | {{.fist-loop-20260927/hunt_r3_repro.json|by_id.C8.rc}} |

成对判据的实测原文（pos 必须现形、ctl 必须不现形，两档齐全才算确诊；逐字来自 `hunt_r3_confirm.json`）：

- C1 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C1.pos.observed}}`
  ⇒ ctl（换成带 `type_params` 的假节点）`{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C1.ctl.observed}}`
- C3 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C3.pos.observed}}`
  ⇒ ctl（调用面 `--help` 实测）`{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C3.ctl.observed}}`
- C4 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C4.pos.observed}}`
  ⇒ ctl `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C4.ctl.observed}}`
- C5 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C5.pos.observed}}`
  ⇒ ctl `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C5.ctl.observed}}`
- C6 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C6.pos.observed}}`
  ⇒ ctl `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C6.ctl.observed}}`
- C8 pos `{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C8.pos.observed}}`
  ⇒ ctl（另一条规则确实在报）`{{.fist-loop-20260927/hunt_r3_confirm.json|by_id.C8.ctl.observed}}`

入账自证：`hunt_r3_filed.json` 里 6 条 `summary_on_disk=true`、
账本号增量 `{{.fist-loop-20260927/hunt_r3_filed.json|new_numbers}}`
（条目数 {{.fist-loop-20260927/hunt_r3_filed.json|entries_before}} →
{{.fist-loop-20260927/hunt_r3_filed.json|entries_after}}），
且入账条数与号增量必须相等这条本身是硬门（不等就 refuse 落盘）。

## 三、撤回 2 条（不占号）与"为什么不占"

| 候选 | 我一度以为 | 撤回理由（读它自己的定位声明） |
|------|------------|--------------------------------|
| C2 comptime 不读 `Param.default_value` | 静默降级 = 缺陷 | `SYNTAX/19-comptime.md:22` 自己写着『**编译期函数**：`comptime def` 语法未实现』、:43 状态表同样标 `未实现` ⇒ 求值器少绑一个默认参数发生在**公开承认没实现**的特性内部。冻结文档我也改不动。判档 `DESIGN` |
| C7 `topological_sort` 前段 in_degree 是死码 | 子代理称"first 8 lines unreachable in effect" | 换成 AST 口径实测：`pass`-only 循环 0 个、`in_degree` 的 Load 计数 6 ⇒ 主张不成立。判档 `REJECTED` |

复现件对这两条的退出码：C7 = `{{.fist-loop-20260927/hunt_r3_repro.json|by_id.C7.rc}}`（1=不现形），
C2 = `{{.fist-loop-20260927/hunt_r3_repro.json|by_id.C2.rc}}`（DESIGN 不锁退出码：形状在不在都对，
**但它不该占号**）。

子代理主张与亲测结论的逐条对账在 `hunt_r3_subagent_claims.json`：8 条里我确认 6 条、
推翻 1 条、按设计撤回 1 条，另把我自己探针的历史误判单独成栏（§五）。

## 四、三套基线、改动半径与 git 红线（同一时刻复算）

| 体系 | 实测 | 下限/期望 |
|------|------|-----------|
| pytest 全量 | `{{.fist-loop-20260927/hunt_r3_baselines.json|pytest.line}}` | ≥ {{.fist-loop-20260927/hunt_r3_baselines.json|pytest.floor}}（= R2-推进收口值，本环**不该**新增也不许掉）；收集 {{.fist-loop-20260927/hunt_r3_baselines.json|pytest.collected}} |
| 自研套件 | `{{.fist-loop-20260927/hunt_r3_baselines.json|suite.line}}` | 47/47 |
| e2e golden | `{{.fist-loop-20260927/hunt_r3_baselines.json|e2e.line}}` | PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0 |
| git 红线 | HEAD `{{.fist-loop-20260927/hunt_r3_baselines.json|git.head}}`，暂存 {{.fist-loop-20260927/hunt_r3_baselines.json|git.staged}}，脏行 {{.fist-loop-20260927/hunt_r3_baselines.json|git.dirty_rows}} | 不 add/commit/push |
| 改动半径 | {{.fist-loop-20260927/hunt_r3_baselines.json|radius.count}} 档；归不到本单的 `{{.fist-loop-20260927/hunt_r3_baselines.json|radius.unclaimed_by_this_lane}}` | **寻虫环半径应为空**：`cypyc/`、`tests/`、`docs/`、`scripts/`、`examples/` 在 20:20 之后 0 改动（本单在驱动里声明的文件数为 0，见 `hunt_r3_baselines.py` 的 `MINE`） |

"本环没动产品码"这条负面主张不是我自己说的：时间窗起点 20:20 晚于上一环最后一次半径内改动（20:09），
按 mtime 正面扫出来是 0 档 ⇒ 若我动了码，这一栏会直接把文件名点出来。

## 五、本环自身缺陷（判据/工具 8 条 + 操作 5 条，共 13 条）

1. **子代理主张不能直接入账**：它给的 8 条里 2 条不成立（C7 死码假、C2 撞自述未实现），
   而 C6 它写的"5 seeds ⇒ 5 个不同顺序"用的是**同进程**换 `PYTHONHASHSEED`——那个做法测不出东西。
   ⇒ 一律亲测复算，并把"子代理说／我测到"两栏分开留档。
2. **探针自己炸了 5 条时，全红是判据坏了**：v1 里 `Parser(src)` 直接喂源码（真签名是
   `Parser(Lexer(src).tokenize())`）、把运行时模块写成 `cypyc.runtime`（实在 `cypy_bridge/`）、
   `cli.subparsers` 当模块属性取。⇒ 每条候选的 file:line 我要自己读第二遍，不抄它的定位。
3. **同进程改 `PYTHONHASHSEED` 造出假阴性**：C6 在 v1 判成"不现形"，因为字符串哈希在解释器启动时
   就定了；改 v2 起 5 个独立子进程才现形。⇒ 凡"随哈希种子变化"的判据必须是多进程。
4. **读错 docstring 层级造出假阳性撤回**：v3 拿 `inspect.getdoc(类)` 找规则清单 ⇒ 读空，
   于是把 C8 判成 REJECTED，差点漏掉一条真缺陷；规则写在**模块** docstring。
   ⇒ "声明面"取证要先把声明所在的层级钉明（模块/类/函数三处），并让"文本存在"成为判据的一档。
5. **判据分档不够细会把三种结论挤成一桶**：v1/v2 只有一个 `REJECTED-OR-UNSURE` 桶，
   于是"主张被推翻"和"我的对照没成立"分不清。⇒ 拆成 `confirm` / `check-only` / `declared-scope`
   三种模式（后者专给"读自己的定位声明"这种形状），四档结论 CONFIRMED/DESIGN/REJECTED/PROBE-BROKEN。
6. **`refuse` 规则太宽：探针炸了 5 条仍然 rc=0**：v2 的拒绝条件只有"无一 CONFIRMED"。
   ⇒ 改成"只要还有 PROBE-BROKEN 就整件判红"，因为那种情况下 CONFIRMED 的数量不可信。
7. **入账 detail 里的"复现命令"跑不动**：我一开始把 detail 的复现写成嵌套引号的
   `python -X utf8 -c "…"`，在 Windows/Git Bash 上多半直接语法炸（这平台已经记过一轮反引号坑）。
   ⇒ 独立件 `hunt_r3_repro.py <ID>` + 三态退出码，且 `hunt_r3_repro.json` 逐条实跑过一遍，
   退出码与确诊口径不一致就 refuse（"可复跑"从形容词变成判据）。
8. **批量改脚本时多行字符串匹配连翻三次车**：同一批替换里，两处 `old in text` 断言失败、
   一处把 `\n` 写成了真换行导致目标文件语法坏掉（写盘在前、`ast.parse` 在后 ⇒ 坏件真落盘了）。
   ⇒ 改脚本文件一律**按行号手术 + 每次 `ast.parse` 校验**，且校验放在写盘之前。
9. **`report_bug` 的 severity 只吃英文枚举、必填键是 `summary`**（不是 title）：本环按上一环教训
   直接用英文枚举与 `summary`，一次通过 6 单；但账本 md 里的中文严重度栏会误导后续读取 ⇒
   已在 detail 里同时给出 file:line 与实测原文，避免有人只按中文栏筛。
10. **门禁的作用域写宽了一档**：⑨ 号我写成"每一档都 pos+ctl 齐全"，实跑得 false —— 因为撤回的
    C7（pos 刻意不成立才叫推翻）与 DESIGN 的 C2 本来就不满足这个合取。
    ⇒ 断言要按**结论子集**取量（`all_confirmed_pairs_ok`），并把撤回项单独列成
    `non_confirmed_pairs` 供人复核；"整件为假"和"我以为整件为真、其实只该对确认子集为真"
    是两种错，后者是**门禁在说谎**，比红更坏。
11. **我把钟点手敲成 UTC 戳**：入账驱动里 `NOW = "2026-09-27T12:45:00Z"` 是我手填的，
    而 6 条账本条目的实际落盘戳逐字是
    `{{.fist-loop-20260927/hunt_r3_filed.json|ledger_stamps}}`（服务端写盘瞬间）⇒ 我的证据件比
    它描述的事件早 69-70 秒。条目戳不归我改（也没 API 改），改的是**驱动**：`NOW` 取
    `lfist_lib.utc_now()`，并新增"从账本反解的戳必须每条都拿得到"的硬门（拿不到就 refuse）。
    ⇒ 手敲的时间戳必然与写盘瞬间不一致，这不是精度问题，是"证据件说的时间不是事件的时间"。
12. **我读定位声明只读到模块 docstring，没读冻结面**：C8 入账时我写的是"要么补实现，要么改文档口径"，
    当时我没翻 `SYNTAX/04-pointer-types.md:105`（『指针只能在函数作用域内使用』）与 :131
    （规则表同句）。冻结文档说的是**函数作用域**，不是"构建块内部" ⇒ checker 那句"移除限制"其实
    更贴近冻结语义，真矛盾只在 checker 自己的模块 docstring。方向因此定了：**改口径（非冻结面）**，
    补实现反而会撞 36 处既有用法并违反冻结语义。
    ⇒ "先读它自己的定位声明"要读到**层级的最上头**（SYNTAX/PROJECT-SPEC > 模块 docstring > 函数 docstring），
    只读紧邻文本会把一条设计放松报成缺陷，还会把修复方向指反。
13. **我给收口驱动传了它根本没有的旗标**：`close_stage_generic.py … --dry-run` —— 该文件里
    `grep dry` 零命中 ⇒ 它按真实路径把 16 叶链跑完并落库（结果本身是本轮要做的动作，无害），
    但"以为在预检"和"已经提交"之间原本没有任何护栏。⇒ 两个收口驱动现在都会
    `REFUSE — 本驱动不收旗标，收到 ['--dry-run']`（已用同一条命令做必然违例对照，
    它在 import 阶段就退，不发 RPC）。未知旗标静默吞掉是收口型控件最坏的一种缺陷。

## 六、账本与收口

- `memory/bugs.md` 新增 6 条 `## BUG-5x … OPEN`（由 `report_bug` 服务端落盘，号 55..60），
  本环**不追加** `### FIXED` 段——修复在下一环，`OPEN` 才是本轮的诚实状态。
- 三向对照 `hunt_r3_ledger3way.json`：md 条目
  {{.fist-loop-20260927/hunt_r3_ledger3way.json|ledger.entries}} 条、FIXED 段
  {{.fist-loop-20260927/hunt_r3_ledger3way.json|ledger.fixed_sections}} 段、sqlite bug 任务
  {{.fist-loop-20260927/hunt_r3_ledger3way.json|server.bug_tasks}} 个，拒绝清单
  `{{.fist-loop-20260927/hunt_r3_ledger3way.json|refuse}}`
  （仍是沿前三环定性的 4 条孤儿 T0r2-T0r5，本环未新增孤儿）。
- 收口链：16 叶 8 枝 `{{.fist-loop-20260927/close_r3_hunt.out.json|leaves}}` 条走完
  claim→omega→execute→submit→output_validate→omega_result_verify→verify，失败叶子
  `{{.fist-loop-20260927/close_r3_hunt.out.json|failed}}` 条；根终态
  `{{.fist-loop-20260927/close_r3_hunt_root.out.json|root_final}}`，上卷被拒
  `{{.fist-loop-20260927/close_r3_hunt_root.out.json|refused}}`——
  上卷驱动本环只跑一次（结构性合法拒绝：根 6 条、枝干 0 条；枝干上出现任何一条都意味着驱动被重跑）。

## 七、未做与转结 / 交人类裁决

| 项 | 为什么不进本环 |
|----|----------------|
| 6 条入账缺陷的修复 | 寻虫环禁改产品码；BUG-55/56/58/59 都要动实现语义，属 R3-修复半径 |
| BUG-57 走"让示例成立"还是"改示例" | `cypy_bridge/union.py` 的 docstring 是对外承诺，改示例=缩承诺（需裁决）；让示例成立=给内建类型做 ctypes 映射（改语义）⇒ 两案都交人工；BUG-60 已按 §五 第 12 条定方向：改 checker 模块 docstring 口径（非冻结面），因为 `SYNTAX/04:105/:131` 只约束函数作用域 |
| BUG-56 的 `run_default` 是否整个删掉 | 四个旗标的实现体在 `run_default`/`run_build` 里；删分支=缩减对外 CLI 面，属不可逆动作 ⇒ 只挂账 |
| BUG-59 的编译序稳定性要不要进 golden | 若要"同图同序"成为对外契约，需要一条跨进程判据并可能改 golden 注册口径 ⇒ 与 BUG-54 同一裁决面 |
| 轮末本地 commit + 本地 tag | 仍压在 09-26 与各环未提交改动（脏行见 §四），"哪些文件该进这次提交"要先有人答 ⇒ 挂账，不自行 `git add` |
