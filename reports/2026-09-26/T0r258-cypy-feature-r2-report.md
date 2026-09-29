# Cypy 自驱特性轮 R2 · 中期报告（FIST `cron-cypy`，根任务 `T0r258`）

日期：2026-09-26 ｜ 驱动：FIST-Mbt `task_plan_deep` + Omega 强验证 + `call_log`
任务包：`Gen_Prompts/20260926.R2-cypy-feature-round.md` ｜ 轮次类型：**新特性**（依
`Gen_Prompts/_meta_prompt.md` 的反「修复循环」配额：R1/T0r61 与前一个提交都是修复类）

本报告只写**带命令的实测事实**。每条数字都在本机重跑过，命令与产物路径一并给出。

---

## 一、判据锚点（开工前基线 → 本轮复测）

| 锚点 | 命令 | R2 开工前（任务包 §一） | 本轮复测 | 产物 |
|---|---|---|---|---|
| A1 e2e golden | `bash scripts/e2e_golden.sh` | `PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1` exit 0 | **`PASS=23 FAIL=0 UNREG/RUNFAIL=0 WARN=0` exit 0** | `output/e2e_after_rereg.txt` |
| A2 全量 pytest | `python -m pytest -q tests test_suite` | 1681 passed / 0 failed | **1706 passed / 0 failed / 0 skipped** `in 433.04s` exit 0 | `output/pytest_r2_f42.txt` |
| A3 R1 自门控脚本 | `python Find_BUG/audit_2026q3/repro_gate.py repro_ scripts` | 31 个脚本决定性 | **`scripts=31 mismatches=0` exit 0**，31 条全部 `exit=0 -> fixed` | `output/a3_after_selffix.txt` |
| A4 golden 厚度 | `python Find_BUG/audit_2026q3/repro_gate.py feat_anchor_ fixed` | 缺陷在（exit 1） | **exit 0**：`有约束力锚点 23 / 23`、`NOT-REPRODUCED —— 全部 23 条 golden 达到厚度阈值` | `output/feat_anchor_01_after3.txt` |
| A5 特性探针 | `.../repro_gate.py feat_constraint_ feat_subtype_ feat_dispatch_ feat_docs_ scripts` | — | **`scripts=15 mismatches=0` exit 0**，15 条全部 `exit=1 -> reproduces`（三件套确实零实现） | `output/gates_r2_f42.txt` |

A1 的「22 → 23」不是多跑了一个示例，而是**同一条判据从假绿变成咬得住**（见 §二），
其中原 22 条 PASS 里只有 13 条真的约束了实现。

> 口径提示：A2 的 1706 是 **F4 收口时刻**的数（10:3x）。在那之后本又落了 5 条用例
> —— `test_golden_anchor_probes.py` 的 stdlib 撞名机检（+1）与
> `tests/test_type_system_spec_integrity.py`（+4，F3.2 的规范自洽门），
> 所以下一位读者看到的 A2 应当 ≥ 1711；F1/F2 实现单元还会继续抬高它，
> **回归线是「0 failed / 0 skipped」和「不许低于自己上一条测得的数」，不是这个 1706。**

**本轮终态（12:3x–12:4x 串行复测，原文在 `output/fist/r2_f12_verify.log`）**：
A1 `PASS=24 FAIL=0 UNREG/RUNFAIL=0 WARN=0` exit 0；A2 `1745 passed in 535.70s`（0 failed / 0 skipped，
≥ 上一条测得的 1711 ✓）；A3 `scripts=31 mismatches=0` exit 0；A4 `scripts=1 mismatches=0` exit 0
且 `有约束力锚点 24 / 24`；A5 按语料原命令 `feat_constraint_ fixed` → `scripts=6 mismatches=0` exit 0（六条探针全 exit 0）；
`feat_docs_ scripts` → exit 0；`feat_subtype_ scripts` → 5 条全部 `exit=1 -> reproduces`（F2 未开工的直接证据）。
A1 从 23 变 24 是**新增了一个有真实输出的示例**，同时 23 份既有 golden 与开工快照逐字节相同（§4.5）。

---

## 二、F4 判据咬合（`T0r258.4.1` 审计 → `T0r258.4.2` 加固 + 清污 + 重注册）

### 2.1 四条独立断链（任一存在时「全绿」都不构成证据）

| ID | 断链 | 修法 |
|---|---|---|
| LINK-1 | `cypyc/__main__.py` 只有裸 `main()`，丢弃返回码 → `python -m cypyc run` **恒 exit 0**，判据的 `RUNFAIL` 分支是死代码 | 改 `sys.exit(main())`（`cypyc/__main__.py:13`，+10/−1 含理由注释） |
| LINK-2 | CLI 失败横幅 `[FAIL] Execution failed:` 及其后的 traceback 被 `strip_debug` 当成「程序 stdout」写进 golden 并判 PASS | 先去 ANSI 色码，再从**行首** `[FAIL] ` 截断到 EOF；且原始输出命中该横幅即判 FAIL，**拒绝 `--update` 写盘** |
| LINK-3 | 空 / 纯空白 golden「比对通过」即算绿（`new_syntax_features.out` = 1 字节换行） | 空基准不算绿；`--update` 时输出为空直接 FAIL 拒绝注册 |
| LINK-4 | 末行门控只看 `fail` → `UNREG/RUNFAIL/WARN` 记录后整体仍 exit 0 | 门控同时看 `fail/runfail/warn`；附加：golden 内嵌本机绝对路径判 FAIL（换机必失配） |

误伤防护（实测驱动）：横幅必须顶到行首才算命中（CLI 失败分支全部第 0 列输出）；绝对路径 needle
**不认正斜杠** —— `[A-Za-z]:[\\/]` 会在 `examples/concurrency.cypy` 打印的 `https://api.example.com/…`
的 `s:/` 处假报警，故只认 `X:\` 与 POSIX 家目录。

### 2.2 加固的证明 = 单调性（新判据跑旧基准，绿集合只准减）

同一批**旧** golden 上重跑加固后的判据（`output/e2e_before_rereg.txt`）：

```
PASS=22 FAIL=0 UNREG/RUNFAIL=0 WARN=1 exit 0     （加固前）
PASS=13 FAIL=9 UNREG/RUNFAIL=1  WARN=0 exit 1    （加固后，基准未动）
```

`grep -cE "^PASS"`=13、`^FAIL`=9、`^UNREG`=1、`^WARN`=0。**没有任何一条原 FAIL 变成 PASS**。
9 条 FAIL 的真实成分：8 条 `golden 内容是 CLI 失败诊断而不是程序输出`（其中 7 份逐字节相同的
编译崩溃回溯，sha256 前缀 `80a3b3f3f488`，2691 B —— `BUG-031` 记的是同批文件的 md5 前缀 `b4321a0bc7`，
两者是不同算法对同一事实）、1 条 `new_syntax_features` 与 1 字节基准不一致；UNREG 是改名后的
`struct_records.cypy`。

### 2.3 那 7 份共同 traceback 的根因（不是「示例写错了」）

`examples/struct.cypy` 编出 `output/struct.cp313-win_amd64.pyd`；构建期 `python setup.py` 把
**脚本所在目录**插进 `sys.path[0]`，于是 `setuptools → _distutils_hack → distutils.archive_util →
zipfile → struct` 命中那个 .pyd 并在模块初始化期崩溃（`AttributeError: 'dict' object has no
attribute 'width'`）。崩溃发生在装钩子阶段，所以**每个后续示例**都拿到同一段回溯，被判据当成
「程序 stdout」冻结成 7 份基准。登记为 `Find_BUG/BUGS.md` BUG-031/032。

两条防复发（本轮新增，均已实测）：
* 拆引信 + 建隔离：示例改名 `struct_records.cypy`；构建子进程统一走
  `cypy_hook/hook.py:build_isolated_command()`（CPython ≥ 3.11 加 `-P`）+ `build_isolated_env()`
  （`PYTHONSAFEPATH=1`），`cypyc/project/project_compiler.py` 同址改用；
* 全量清污核对（不是只改了撞名的那一个）：`output/` 现存 40 个扩展产物，
  「产物模块名遮蔽 stdlib」的集合实测为 **空**
  （`{p.name.split('.')[0] for p in Path('output').glob('*.pyd')} ∩ sys.stdlib_module_names == []`），
  `examples/` 顶层同样为 0；
* 机检化：`tests/test_golden_anchor_probes.py::test_no_example_name_collides_with_stdlib`
  （示例名撞 `sys.stdlib_module_names` 即红）。**开关对照实测**：当前示例集 → `[]`；
  把改名前的 `struct` 塞回同一表达式 → `['struct']`（needle 不空转）。

### 2.4 清污、语料与重注册（逐条审定 diff）

* 留档链：`Find_BUG/audit_2026q3/golden_before/`（23 份旧 `.out` + `e2e_golden.sh.orig` +
  `__main__.py.orig` + `new_syntax_features.cypy.orig`，`cp -a` 保留 mtime）、
  `corrupt_backup/`（NUL 污染的工作区副本，未提交内容没有被丢弃）；
* 改前核对：工作树 23 份 `.out` 与 `golden_before/` **全部逐字节一致**（`cmp` 全库循环，
  mismatches=0）→ 这份快照确实是本次重注册的 before 基线；
* 驱动体修复：6 个示例补 `def main() -> int:`（`cypyc run` 走 import + 调 `main()`，
  `if __name__` 守卫永不成立，原文件的 print 一行都跑不到）；`^:` / `~:` 的缺陷用例
  显式挂起到 `examples/_pending_build_blocks.cypy` / `_pending_type_defects.cypy`
  （借判据现成的 `_*) continue` 约定，不假装绿），对应 BUG-025~030；
* 重注册：`--update` 后与快照做全量 `cmp` → 变更集恰好 **9 CHG + 1 NEW**（就是 §2.2 那 9 条 +
  `struct_records`），**原先 PASS 的 13 条基准逐字节未变**；9 份新基准全部是程序自身 stdout。
  跨 8 天（9-18 基准 → 9-26 重跑）仍一致的 13 条，本身就是这些锚点确定性的证据。
* 如实记录两点：`examples/test_duck.cypy:73` 的 `sort` 是 HEAD 就有的占位实现（`return items`），
  golden 钉的是「passthrough」这一事实而不是「排序可用」；`generic.out` 与 9 月 18 日那份文本相同，
  是本次 `--update` 真实重跑的结果（打印文案与旧基准巧合，源→产物→运行→比对链条完整）。
* 不确定性扫描：`grep -lE '0x[0-9a-f]{6,}' examples/*.out` → 0 命中（无对象地址/时间戳/耗时类内容）。

### 2.5 判据的自检段也会说谎（本轮顺手修的第二类假证据）

`feat_anchor_01.py::criteria_health()` 原先按**字面措辞**判 LINK-2/LINK-3：加固后的脚本改用
行首横幅截断，它就反过来报「缺陷仍在」——一条会说谎的诊断。已改成判**能力**（strip_debug 里存在
`/^[[]FAIL` 截断规则 + `BANNER_RE` 出现在 UPDATE 分支之前 + `is_blank_text` 分别出现在 `--update`
与比对分支 + 末行门控同时含 `fail/runfail/warn`），git 入库项重编号为 LINK-5 以免与门控项撞名。
needle 只取代码不取注释（脚本头部注释里就有 `[FAIL] Execution failed:` 字样，按子串查会自己命中自己）。
反向对照测试 `tests/test_golden_anchor_probes.py::TestCriteriaHealthHonesty`（2 条）：拿加固前的
`golden_before/e2e_golden.sh.orig` 必须报回归、拿现在的必须报 OK。该文件用例数 5 → 7 → 8
（最后一条是 §2.3 的撞名机检），A2 的 1706 是在加到 7 条时测得。

### 2.6 判据工具自身的自指缺陷（A3 首跑恒红的原因）

`repro_gate.py` 的 runner 文件名命中的正是它自己的 `repro_` 前缀 → 把自己当被审脚本喂进去 →
打出 `usage` 的 exit 2 → 记为 `NO VERDICT` → 整条 A3 恒红。首跑实测：
`scripts=32 mismatches=1 FAILING: repro_gate.py`（`output/gates_r2_f42.txt`）。
已按「排除自身路径」修 `repro_gate.py`（而不是改文件名绕开）。**兄弟项目 `Actus` 的
`Find_BUG/actus_2026q3/repro_gate.py` 是同一份代码的副本，带同样缺陷**，留给 `cron-actus` 车道处理。

### 2.7 A1 的真实覆盖面（只报事实，不擅自扩面）

`git ls-files '*.cypy'` → 77（全部在 `examples/` 下），磁盘现存 75；判据只覆盖 `examples/*.cypy`
**顶层且非 `_` 前缀** = **23 条**；另有约 50 份 `examples/demos/**` 语料不在 A1 覆盖面内。
A2 命令里的第二个路径 `test_suite` 的 pytest 收集数实测为 **0**
（`python -m pytest -q --collect-only test_suite/` → "no tests collected"；原生套件文件叫
`*_suite.py`，由 `scripts/run_tests.py` 驱动），所以 A2 实际等于 `tests/`（收集 1706 == 全量数）。
这两条都是「判据覆盖面比名字看起来窄」的事实，本轮未扩面，登记为后续项。

### 2.8 勘误与越界（指挥官自查）

* **交付物缺事实**：`T0r258.4.2` 的 deliverable 记了示例改名与判据加固，**没写** BUG-031 的根因修复
  落在 `cypy_hook/hook.py` 与 `cypyc/project/project_compiler.py` —— 这两个文件**超出该叶子描述的
  文件边界**（`边界：examples/ + 新增审计脚本`）。改动本身经审：`-P` 按 `sys.version_info >= (3, 11)`
  才加、`PYTHONSAFEPATH` 无条件设置（老解释器忽略），并有 `TestBuildPathIsolation` /
  `TestStdlibNameCollision` 兜底，A1/A2/A3 全绿。越界事实与修复理由在此登记；`已完成` 任务的
  deliverable 没有合法回改迁移（FIST 无该路径），故以报告勘误入档，不做假 `reject` 仪式。
* **台账时间戳勘误**：R2 首波 6 行 `updated_at`（`T0r258.1.1/.2.1/.3.1/.4.1/.4.2/.5.1`）被驱动脚本
  自造的 `Clock` 写成**未来时间**（比真实 UTC 晚 7.5~8.3 小时；`call_log.ts` 才是服务端时钟，
  实测与真实 UTC 差 1 秒）。`T0r258.4.2` 经 `pause → resume → execute` 重新登记后已回到服务端
  真实时间（实测 `2026-09-26T02:37:54Z`）；其余 5 行留在原处（不可回改），后续批次一律省略 `now`。

### 2.9 需要人来关的一条（红线之内，本轮不动）

`scripts/e2e_golden.sh` 与全部 `examples/*.out` **都没有纳入 git**：

```
$ git ls-files scripts
scripts/run_tests.py
scripts/sync_demo.py
$ git ls-files --error-unmatch scripts/e2e_golden.sh
Did you forget to 'git add'?
```

也就是说：项目的**头号外部判据脚本 + 全部基准**只活在本地工作树，`git clean -f` 即可无痕消灭，
`--update` 也不留 diff。探针已把它变成机检项（LINK-5）。补它需要 `git add`（可逆），但项目红线是
「未经要求不 commit」，所以留给人决策。

---

## 三、三件套：规范、探针与裁决（F1.1 / F2.1 / F3.1 / F5.1 已完成）

`SYNTAX/33-type-constraints-subtypes-dispatch.md`（本轮建档）第一次给
`constraint Name = A | B` / `subtype A <: B` / `dispatch name(params) -> ret` 写了语义规范：
条款号 C-1..C-7 / S-1..S-7 / P-1..P-5，每条都配一个自门控探针（§6 条款↔探针映射表），
15 个探针当前**全部 exit 1（未实现）**——A5 已实测。文档侧同时纠正了两处失真：
`docs/SYNTAX_CHANGE_REVIEW.md:20-22` 的「✅ 完成」与 `SYNTAX_IMPLEMENTATION_STATUS.md:83-91`
的「❌ 未实现」不是同一件事（前者指文档动作栏），且前者 :52 声称规范在 `SYNTAX/27-constraints.md`
—— 那 475 行通篇是**已实现的 `duck`**，与三件套无关。`feat_docs_01.py` 把这类失真变成 X1~X8 机检。

实现单元开工前的 10 项待裁决（§7）已由指挥官在 **§7.1** 定稿，要点：
`constraint`/`subtype` 本轮进 `KEYWORDS`（`dispatch` 不进，避免悬空关键字），全库 `.cypy` grep 实测
10 个文件命中且全部是注释/字符串/fixtures 负例语料（`output/reserved_word_hits.txt`）→ 硬保留不破坏
任何可编译语料；多界组合 `T: A + B` / `(A, B)` **不支持但必须硬拒绝并指名替代方案**（今天是静默吞）；
泛型成员只比头部名（明写的宽松，不是隐藏缺陷）；`subtype` 保持**零运行时表示**，因此
**禁止 `subtype` 做 `dispatch` 的 arm 键**（这一条把 F2 与 F3 的语义矛盾从「实现冲突」降级为「规范边界」）；
`_user_def_kinds` 纳入 `'type'`（顺带修 B9）的前提是先跑全量 A1+A2 并登记打破的既有用例。

### 3.1 `T0r258.3.2` dispatch 规范定稿：已完成（派工失败，指挥官收尾）

派出的子代理改写完 §4.1/§4.4/§4.5/§4.6 正文后**因系统错误中止**（66 次工具调用、12 分钟、无最终报告）。
逐条核对磁盘状态发现三处遗留并由指挥官补齐：

| 遗留 | 补法 |
|---|---|
| 正文引用 `§4.4.1`、`§4.7` 与 `D-hdr/D-empty/D-mlt/D-ord/D-stray/D-mlvl/D-name/D-amb/D-none/D-key` —— 这些锚点**从未被写出来** | 新增 §4.4.1 诊断模板表（十条，全部满足 §2.5 C-5 的「真实 `file:line:col`、`at 0:0` 不合格、必须指名替代方案」）与 §4.7 开工清单（S1..S7，每片带现成 `file:line` 落点与红→绿探针） |
| §4.2 只有 4 条无编号要点，正文却按 `P-2.1/P-2.3/P-2.6` 引用它们（引用悬空，实现者按号找不到条款） | 补齐为 P-2.1..P-2.6，其中 P-2.3 落成**白名单形式**并写死「禁止 `subtype` 做 arm 键」（裁决 D-9 的落点） |
| §8 变更记录没写本轮 | 补 `T0r258.4.2`（§7.1 裁决）与 `T0r258.3.2`（§4 定稿）两条 |

中止的代理**没有**越界：`git status --porcelain docs` 零改动（它被明令不得碰 `docs/SYNTAX_CHANGE_REVIEW.md`，
那属于 `T0r258.5.2`），`SYNTAX/33-*.md` 仍是未跟踪新文件，`cypyc/` 未被它改动。

顺手修掉两处**同一类**判据缺陷（与 §2.5 同源，都会让「下一轮修好之后探针自杀成 exit 2」）：
`feat_dispatch_01.py` 把「`dispatch` 不是关键字」「无注解头被吞成两个 `ExprStmt`」写成 `control`，
而这两条恰恰是 S1/S2 要反转的**现状取证** → 改 `note()`；`feat_subtype_04.py` 的条款号 `S-3.6`
是 §6 索引表的错写（应为 `S-6`/§3.6），3 处已改。

新增长期机检 `tests/test_type_system_spec_integrity.py`（4 条，`4 passed in 0.09s`）：
规范里每个被引用的条款号/节号都必须有定义处（实测当前悬空数 **0**）；§7+§7.1 必须合起来裁完 D-0..D-9；
**开关对照**证明检测器真会咬（人造样本必须报出 `P-9.9` 与 `§9.2`，且不误报定义在标题/条目里的号）。
写这条门时自己踩到并当场纠正一次：`_defined()` 初版把「行内任意 `**ID**`」也当定义处 →
引用自己把自己定义掉，负向对照立刻报红（`assert 'P-9.9' in ['§9.2']`）。

deferred 面（没有冒充完成）：`dispatch`/`arm` **未进** `KEYWORDS`，无 `DispatchDecl` AST、无 codegen、
`examples/` 无 dispatch 语料。FIST 侧 `claim → execute → submit → omega_result_verify(approved)
→ run_check×2 passed → verify` 全链完成，`updated_at=2026-09-26T02:57:13Z`（服务端真实时钟）。

---

## 四、进行中与待办

| 叶子 | 状态 | 说明 |
|---|---|---|
| `T0r258.4.2` F4 判据咬合 | **已完成**（`run_check` 三条 `passed`：A4/A1/A3，服务端真实 spawn；`updated_at=2026-09-26T02:42:22Z`） | 见 §二 |
| `T0r258.3.2` F3 dispatch 规范定稿 | **已完成**（派工失败后由指挥官补齐，见 §3.1；两条 `run_check passed`） | 只写 `SYNTAX/33` §4 + §4.7；禁动 `docs/SYNTAX_CHANGE_REVIEW.md`（那是 F5.2 的）与 `cypyc/` |
| `T0r258.1.2` F1 constraint 实现 | **已完成**（`claim → execute → submit → omega_result_verify(approved) → run_check×5 全 passed → verify`；`deliverable=4364` 字符，`updated_at=2026-09-26T04:57:31Z` 与真实 UTC 差 23 秒 = 服务端盖章） | 四层全落 + 调用面回环（`examples/constraint_numeric.cypy` + golden 注册）；A1 `PASS=24`、A2 `1745 passed`、A3 `scripts=31 mismatches=0`、A4 `24/24 有约束力`、A5 `feat_constraint_ fixed 6/6 exit 0`。两处先红后绿的判据缺陷在我这边，见 §4.5；D-1 被实现方越序提前做了，见交付文案「缺口」① |
| `T0r258.2.2` F2 subtype 实现 | **派工中**（12:58 起，`general-purpose` 执行代理；库里此前为 `待领取`，语料 `spec:T0r258.2.2:r1` 已 approved） | 派工边界写死：禁动五份 `feat_subtype_*.py`（判据只读，疑似判据缺陷只上报不改）、禁动两份状态文档、禁做 `dispatch`、`e2e_golden.sh` 只读、A1~A5 严格串行、过 110 次工具调用必须停手回传实测进度 |
| `T0r258.5.2` F5 文档对齐 | **已完成**（`claim → execute → submit → omega_result_verify(approved) → run_check passed → verify`；`deliverable=3194` 字符，`updated_at=2026-09-26T04:58:07Z`） | 见 §4.1 / §4.1.1：残余 8 处归零 + 新增机检针 `feat_docs_02.py`（带删行/注入幽灵词两次开关对照） |

### 4.1 F5 文档一致性：子集完成 + 复核

`feat_docs_01.py` 实测：命中 **13 → 8**，其中 **X4 幽灵规范指针 / X5 幽灵文件 / X6 关键字声明全部清零**，
X7 四项统计数改为「文档 = 实测」全绿，断言总数 127 → 127（没有增删任何 ✅/❌ 行）。
残余 8 处**全部**是三件套状态行：X2 FALSE_TODO×4（`SYNTAX_IMPLEMENTATION_STATUS.md:105/106/291/292`
—— `constraint`/`subtype` 已在 11:2x 被 F1.2 送进 `KEYWORDS`，而状态行仍写 ❌）、
X1 FALSE_DONE×1 + X3 CONTRADICTION×3（`docs/SYNTAX_CHANGE_REVIEW.md:29` 的 ✅）。
这些**必须由对应实现叶子带着 A1~A4 数字同时翻两份文档**，单边改任何一侧都会留下 X3，
所以本叶子暂不验收，收口时与 F1.2/F2.2 一起闭合。派工边界已被遵守：该代理只改了
`CHANGELOG.md`、`docs/SYNTAX_CHANGE_REVIEW.md`、`SYNTAX_IMPLEMENTATION_STATUS.md`、
`SYNTAX/appendix-A-keywords.md` 四个文件（`git status --porcelain` 复核），
未跑 `cypyc`/`e2e_golden.sh`/`repro_gate.py`（避让并发构建目录）。

指挥官侧顺手修掉一处：`Find_BUG/BUGS.md:627` 汇总行写「Total: 23 fixed, 6 open」，
实测口径 `grep -c '^## BUG-'` = **32**、`.*FIXED` = **26**、`.*OPEN` = **6**，差 3 条修复未回写汇总；
已改为 26 并把口径命令写进该行本身（防再漂）。

### 4.1.1 F5.2 收口：残余 8 处归零（12:4x，带 F1.2 的验收号翻两份文档）

F1.2 的四条锚点实测到手后（A1 `PASS=24 FAIL=0 UNREG/RUNFAIL=0 WARN=0`、
A5 `repro_gate.py feat_constraint_ fixed` 6/6 exit 0、`tests/test_named_constraints.py` 收集 34 例、
`len(Lexer.KEYWORDS)`=65 且 `dispatch` False），一次把**两份文档的同一三条语法**改成三态：

| 语法 | `SYNTAX_IMPLEMENTATION_STATUS.md` | `docs/SYNTAX_CHANGE_REVIEW.md` | 依据 |
|---|---|---|---|
| `constraint` | ❌ → **✅ 已实现**（§2.4 与 §7 两处行都改） | ✅「仅规范」→ **✅ 规范已写且实现已落**（附 A1/A5 数字） | 四层落点 + 调用面 golden + 34 例回归 |
| `subtype` | ❌ → **⚠ 仅词法已收** | ✅「仅规范」→ **⚠ 只到词法层** | `subtype in KEYWORDS`=True 而 `SubtypeDecl` 不存在（`grep -c` = 0） |
| `dispatch` | ❌ 保持 | ✅「仅规范」→ **⚠ 仅规范已写** | `dispatch in KEYWORDS`=False、`cypyc/` 无落点 |

`python Find_BUG/audit_2026q3/repro_gate.py feat_docs_ scripts` → `scripts=1 mismatches=0`、
`feat_docs_01.py: exit=0 -> fixed`，探针 VERDICT 从「REPRODUCED 8 处」变为
「NOT-REPRODUCED —— 两份文档的 ✅/❌ 标记、规范文件指向与关键字存废均与代码实测一致」；
`过门规则命中: 无`。**这条绿不是判据变松**：`feat_docs_01.py` 一行没动（改动集只有两份 .md），
变的是被观测的文档与代码的事实。

两处措辞纪律值得记下来，因为它们是把「假话」改掉的真正动作：
① 原 `docs/SYNTAX_CHANGE_REVIEW.md:27-29` 把**规范状态**写在**实现状态**那一栏（"✅ 完成（仅指规范已写）"），
   机检只能读成"宣称完成"——这正是 X1/X3 的成因，不是探针过严；
② `SYNTAX_IMPLEMENTATION_STATUS.md:263` 原写 `test_constraint.py` **未建**（实测 `git ls-files | grep -c` = 0，
   这条今天仍然成立），但真实测试以另一个名字存在了，所以改成同时说清两件事：
   `tests/test_named_constraints.py` **已建**（328 行 / 收集 34 例），
   而叫 `test_constraint.py` 的文件**依然没有**（原实测值未变）。只写其中一半都会成为下一轮的假证据。

另：`SYNTAX_IMPLEMENTATION_STATUS.md` §2.4 小节标题「计划中（未实现）的特性」已改为
「三件套现状：constraint 已实现 / subtype 仅词法 / dispatch 仅规范」——小节标题是 X5/结构核对的锚点，
留着旧标题就等于让目录结构反驳内容。

### 4.2 F1 constraint 实现：首棒代理触顶中止，实测进度与剩余工作面

派出的 F1.2 实现在 **150 轮上限**处中止（159 次工具调用、44 分钟），最后一句是「Now the codegen layer」。
我没有按它的自述记账，而是直接量了判据与代码：

- `repro_gate.py feat_constraint_ scripts` → `scripts=6 mismatches=0`：**01/03/04/05/06 = exit 0（已绿）**，
  **02 = exit 1（仍红）**；
- `feat_constraint_02.py` 明细 → `checks=7 unmet=1`，唯一未达的是 **C-2.3 嵌套约束成员摊平**：
  `constraint Small = Numeric | str` 里成员 `Numeric` 被当未定义类型拒掉
  （`references undefined type 'Numeric' ... at 1:20`），且诊断打印 `(allowed: Numeric | str)` 而非摊平后的
  `int | float | str`；
- 静态落点已存在：`parser.py:263 ConstraintDef` / `:2857 _parse_constraint` / `:1060` 语句分派、
  `scope_analyzer.py:58 _user_def_kinds` 已含 `type/constraint/subtype`（**D-1 被提前做了**，
  我要求放最后以便分离波及 —— 记为一次越序）、`type_checker.py:114 constraint_defs` 注册表 +
  `:421-426/:1479-1598/:2658/:2767/:2785/:3018` 的判定与界检查；
- `grep -c ConstraintDef cypyc/codegen/cython_generator.py` → **0**：codegen 层（只发注释、不发 `ctypedef`）
  完全没做；调用面示例、golden 注册、长期回归测试也未做。

接手代理的边界已写成四条：修 C-2.3 摊平（不得回退 06 的环检测）、补 codegen 注释发射、
加 `examples/constraint_numeric.cypy`（必须真 `def main()`，并做 §6.1 的「命名界 ≡ 内联界逐字节相同」回环）、
补 `tests/` 长期回归；然后按 A1/A2/A3/A4 顺序串行复跑并抄 summary 原文。

### 4.3 FIST 侧写操作：外部阻塞已解除

11:3x 起 `E:/IDEProjects/AI/FIST-Mbt/_build/js/debug/build/` 被清空，同期 3 个 `moon.exe` 在跑
——**并发会话正在重建兄弟项目**。我不动它的构建产物，因此以下动作排队等待：
4 条缺陷上报（`output/fist/fistmbt_issue_batch.json` 已就绪）、`T0r258.5.2` 与 `T0r258.1.2` 的账、
聚合节点与根任务 `T0r258` 的上卷。判据本身不受影响（`e2e_golden.sh`/pytest/自门控脚本都在 Cypy 仓库内）。

11:46 兄弟会话把 `main.js`（2 348 033 字节）建回来了，队列开始排空：**上报通道已落账（见 §4.4）**，
FIST 写账（F5.2 / F1.2 / 上卷）等对应叶子的实测数字到位后逐条闭合。



### 4.4 FIST-Mbt 缺陷上报通道（依元指令启用）

驱动 FIST-Mbt 过程中实测到的**兄弟项目自身**缺陷，经 `report_bug` 追加到
`E:/IDEProjects/AI/FIST-Mbt/memory/bugs.md`（OPEN 账本），每条带 `file:line` + 可复跑命令 + 当次实测输出。
本轮**已落账 5 条**（`BUG-1`~`BUG-5`，清单与详情见 `output/fist/fistmbt_issue_batch.json`）：

| 严重度 | 缺陷 | 活证据 |
|---|---|---|
| high | 任务行时间戳由调用方 `now` 决定并真实写库，账本可被写成**未来时间** | `src/ops/audit.mbt:5` 设计注释 + 6 行 `updated_at` 比真实 UTC 晚 7.5~8.3 h，同期 `call_log.ts` 与真实 UTC 差 1 秒；新鲜度规则在 `src/engine/omega_gate.mbt:119` |
| medium | `retry` 之后登记不了交付物：`execute` 只接受 拆分中/已领取，而 `retry` 落在 执行中 | `src/core/core_task.mbt:368`（守卫文案）vs `:463`（已打回->执行中）vs `:493`（pause→resume 是唯一绕行） |
| medium | `audit_log` 作为治理查询面暴露却**不落库**，跨进程恒返回 `[]`（假空的审计证据） | 实测 `audit_log '{}'` → `[]`，同时刻 `call_log` 有当天上百条写入（cron-cypy 64 条）；`src/ops/audit.mbt:4` 自述「进程内追加式，不落库」 |
| high | `run_check` 用 `child_process.spawn` 执行任意命令，无白名单 / 无 workdir 约束 | `src/server/run_check_js.mbt:15` `js_run_command(cmd,args,workdir,timeout_ms)`；`grep -n 'allow\|whitelist\|白名单\|拒绝\|forbidden'` 该文件无命中；同类原语 `src/server/github_js.mbt:41,91`、`src/server/laya_js.mbt`（`sh -c` 形式更宽） |
| medium | `project_dir` **契约分裂**：bug 族强制相对，memory 族同名参数接受绝对并直接落盘；两边工具描述逐字相同 | 校验在 `src/server/bugreport.mbt:26-42`（调用点 `:234`/`:312` + `github_sync.mbt` 9 处），而 `src/server/memory.mbt:32` 无任何校验；实测 `memory_link` 传绝对 `project_dir` → `{"linked":true}` 且在 `<abs>/memory/links.md`（30 字节）落盘，`report_bug` 传同形态 → `ERROR -32000 非法 project_dir（拒绝绝对路径/穿越/盘符）`（文案不告知可接受形态） |

**落账实测**（11:52，构建回来后投递）：`python scripts/fist.py --batch output/fist/fistmbt_issue_batch.json`
→ 5 条依次返回 `{"bug_id":"BUG-1"…"BUG-5","status":"OPEN","path":"./memory/bugs.md"}`；
`E:/IDEProjects/AI/FIST-Mbt/memory/bugs.md` 实测 9 489 字节、`grep -n '^## BUG-'` = 5 行，
条头时间戳 `[2026-09-26T03:52:44Z]` 与当时 `date -u`（03:52:55Z）差 **11 秒**——即 §4.4 第 1 条缺陷的规避措施生效：
`report_bug` 省略 `now` 时由 `server.mbt:3964` 的 `now_default()` 服务端盖章。回读 `bug_list '{"project_dir":"."}'`
→ `count: 5`，通道端到端可用。

关键坑（决定了上面第 5 条）：**`project_dir` 必须是相对形态，且相对的是 server 进程 cwd**
（驱动 `scripts/fist.py:45-49` 以 `cwd=E:/IDEProjects/AI/FIST-Mbt` 起 `main.js`），所以 `project_dir="."`
才恰好写到兄弟项目自己的 `memory/`；绝对路径被拒，而 `scripts/fist.py:86-87` 会在缺省时注入**绝对的 Cypy 根**，
因此该参数不能省略。探针目录 `output/fist/abs_probe/` 已在取证后删除。



兄弟车道：`cron-actus/T0r126` 的引擎道修复单元按指挥官指令未派工（4 叶子留在待领取、
聚合与根留在拆分中），台账里没有虚假交付。

### 4.5 F1.2 接手回报：实现是好的，两处红在**我的判据**里

续派代理回报「A1 绿（PASS=24），A2 还在跑」就结束了 —— 我没按它的自述记账，直接把四条锚点串行复跑，
再逐条量红。**结论：实现侧完整（四层 + 调用面 + 24 条回归测试），两处红全部是判据缺陷，且都是我上一轮写的。**

| 红 | 真因（实测） | 处置 | 开/关对照复验 |
|---|---|---|---|
| A4 `feat_anchor_ fixed` → exit 1，`constraint_numeric.cypy R7 THIN(golden 6 行 < 输出语句 8 处)` | 输出语句 needle 写成 `(print\|printf\|echo)`，而 **Cypy 没有内建 `echo`**（`grep -rn "'echo'" cypyc/ --include=*.py` 无命中、不在 `Lexer.KEYWORDS`）；示例里的用户函数 `echo(...)` 嵌在 `print()` 内被计成 2 条，p 虚增到 8 | needle 只认真实存在的 `print\|printf` | 把 needle 改回旧值（写进 `count_sites.__globals__`，见下方坑）⇒ 精确复现 `P=8 G=6 RED:R7 THIN`，**其余 23 行逐字不变**；改后 24/24 有约束力 |
| A5 `feat_constraint_02.py` → exit 1，`checks=7 unmet=1` 指向 C-2.3 | 探针夹具**漏了 `DECL`**：`constraint Small = Numeric | str` 里的 `Numeric` 未定义，先撞的是 C-2.5「成员必须是已定义名字」，C-2.3 从未被观察到；且旧断言 `not u_float.success` 与自己注释里「摊平后含 float」互相矛盾 | 补 `DECL`、断言改成 int/float/str 三条全过，并**新增负例** `clamp([1,2])` 必须仍被拒（否则「摊平=来者不拒」会伪装成绿） | 内存里把 `_expand_constraint_members` 换成不递归的改前形态 ⇒ `checks=8 unmet=1` 且诊断回落到 `(allowed: Numeric \| str)`；恢复 ⇒ `unmet=0` 且 `(allowed: int \| float \| str)` |

顺手拆掉一条会腐烂的判据文案：`_feat_typesys_lib.py:215` 硬写
「this is the expected state of R2 unit 1; unit 2 turns it green」——任何未来探针变红都会打印这句关于**当轮计划**的假话，
已改为中性归因提示（红只说明 expect 未达成，归因看 detail）。

**做开关对照时踩到的工具事实（值得记进判据纪律）**：`runpy.run_path()` 返回的是模块 globals 的
**副本**，对它赋值 `ns["PRINT_SITE"] = ...` **不会**影响 `count_sites` 的实际查找
（`count_sites.__globals__ is ns` 实测 `False`），于是第一次对照跑出「OFF 与 ON 完全相同」——
这是个假的双向皆绿信号，若不追问就会把它记成「我的改动不影响任何锚点」。
正解：改 `func.__globals__` 本身；并且**「两遍输出完全相同」永远要先怀疑开关没生效**，
再检查 `is` 身份而不是只看结果（与 [[feedback-measure-baselines-before-criteria]] 第 34-40 轮那条同类）。

复跑数字（判据修好后，同一棵树）：`feat_constraint_ scripts` → `scripts=6 mismatches=0`（01~06 **全部 exit 0**）；
`feat_anchor_ fixed` → `scripts=1 mismatches=0`；`feat_subtype_ scripts` → 4 条**全部 exit 1 = 仍复现**
（F2 未开工的直接证据，也证明 F1 没有顺手把 subtype 实现了）；`repro_ scripts` → `scripts=31 mismatches=0`。
A1 的 `PASS=24` 与开工快照逐字节比对：24 份 golden 里**只有 `constraint_numeric.out` 是新增**，
其余 23 份与 10:0x 快照 `cmp` 全同 ⇒ 实现没有造成任何既有输出漂移。

---

## 五、台账与并发事实（自审）

* **命名空间纪律**：`python scripts/fist.py call_log '{"limit":400}'` 实测最近 400 条调用里
  `ns=cron-cypy` 64 条（全部是本流水线写入：`get/claim/execute/submit/omega_*/run_check/verify/
  pause/resume/board_ascii/list`）；同时出现的 `cron-tnr`/`cron-auto`/`cron-vq`/`scratch`/
  `E:/IDEProjects/ai/Pentad` 等 ns 属于**并发运行的其它流水线**（它们的 `watchdog_tick` 每 30 分钟
  打点一次），不是本车道越界写入。本轮没有任何一次写操作落到 `cron-actus`。
* **编译器车道独占**：F1.2（改 `cypyc/` 四层）与 F5.2（只改 `CHANGELOG.md`、`docs/`、
  `SYNTAX_IMPLEMENTATION_STATUS.md`、`SYNTAX/appendix-*.md`）并行派工，边界写死为
  「F5.2 不得碰 `cypyc/ examples/ scripts/ tests/ Find_BUG/`，不得跑 `cypyc`/`e2e_golden.sh`/
  `repro_gate`」，因为 `output/` 是单一构建目录，两条车道并发编译会互相污染测量。
* **禁止中途翻状态**：三件套的 ✅/❌ 行只允许由**对应实现叶子**带着自己的验收数字翻，
  否则就制造出本叶子存在的意义之外的那类失真（`docs/SYNTAX_CHANGE_REVIEW.md:20-22` 的 ✅ 事故）。
* **时间戳口径**：本轮之后所有 FIST 写操作**一律省略 `now`**，任务行时间由服务端盖章
  （`T0r258.4.2 updated_at=2026-09-26T02:42:22Z`、`T0r258.3.2 updated_at=2026-09-26T02:57:13Z`
  均为真实 UTC）；R2 首波 6 行由驱动脚本自造 `Clock` 写成的未来时间戳不可回改，勘误见 §2.8。

