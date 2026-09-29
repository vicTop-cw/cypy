# Cypy 自驱组合环 R13 —— 容器元素位判定与类型别名代入到底

- 轮次：R13（推进 → 寻虫 → 修复 → 验证 → 打磨 → 推进）
- 日期：2026-09-29（UTC）
- FIST 根单：`T0r119`（ns `cypy-loop-20260929`，描述内嵌身份标记 `R13-RING-T0r119`）
- 靶面选定依据：R12 收口时列的 R13 入口第 1 条（泛型类型别名面，当时入账为 BUG-136）
- 出口件：本文件；判据件 `corpus/cypy.container.elements.json`；锁 `tests/test_container_elements_r13.py`
- 本轮**未提交、未推送**（仓库现状 200 来条脏路径里混着别家泳道的改动，交回人工裁决后再动 git）

## 1. 靶面：一句话说明本轮在打什么

`SYNTAX/12-type-alias.md` 的「类型别名特性」表里写着
**「类型安全：类型别名是类型的别名，不是新类型，编译时完全等价」**。
本轮开工时按上一轮的探针（`.fist-loop-20260929/probe_r13_type_alias.py`，12 形）把它当成
「别名收下了但参数从不代入」入账为 BUG-136。**这个机制判断是错的**，本轮第一件事就是把它推翻并
换成实测出来的三条真根因：

| 真根因 | 位置 | 症状形状 | 归属 |
|--------|------|----------|------|
| 同名容器「名字对上就放行」，元素位整体不判 | `cypyc/analyzer/type_checker.py:889-891`、`:970-975` | `let bad: tuple<bool, int> = (True, "x")` 与**非别名**的 `list<int> = ["s"]` 同样 errors=0 | BUG-137（本轮 FIXED） |
| 别名右端里出现的**其它别名**不展开 | `_substitute_type` 的 `GenericType` 分支 | `type Triple<T> = Pair<Pair<T>>` + 正确字面量被拒 ⇒ **假阳性** | BUG-138（本轮 FIXED） |
| `UnionType` 节点在代入时整条不认 | `_substitute_type` 缺分支 ⇒ 返回 `None` ⇒ 声明类型为空 | `type Maybe<T> = T \| None` + `Maybe<int> = "s"` errors=0 | BUG-139（本轮 FIXED） |

同族的 (d) 类型实参不存在 ⇒ 与既有 BUG-122 同形（不重复入账）；(e) 裸用 `Pair` 得 0 诊断
⇒ 是**既有测试钉住的行为**（`tests/test_new_features_boundary.py:167`
`test_generic_type_alias_without_params` 断言 errors==0），不是缺陷；
(f) 定义侧带约束界 `type Num<T: int | float> =` 解析失败 ⇒ 仍开，BUG-136 抬头保持 `OPEN`。

## 2. 决策（自主裁决，前后自洽）

| 编号 | 决策 | 理由 |
|------|------|------|
| D-0 | 规范先行：`SYNTAX/02-type-annotations.md` 新增「容器元素位判定」规则 1-6，再动实现 | 与 R11/R12 同形；规则 4-6 明写**不判的一面**，免得把保守实现读成已闭合 |
| D-1 | 判定与记帐分开：`_slot_incompatible`（纯判定）/ `_first_bad_element`（逐位）/ `_check_container_elements`（唯一记帐出口） | 判定要能递归复用（嵌套），记帐要能去重（同事实不叠第二笔） |
| D-2 | 赋值位与返回位**各接一行**，不许一边判一边不判 | 只钉一边时，另一边被删也不会红（矩阵 M2 证明返回位这半边真承重） |
| D-3 | 保守集：只有两侧元素名都在闭合标量表内才允许报「名不同即不兼容」 | 用户类/trait/subtype/别名的可达关系不在本轮半径内；误报会打断既有 2325 条锁，漏报有账可查 |
| D-4 | `dict` 键值位**明确排除**在本节之外 | 字典字面量根本不推断类型（`_visit` 对 DictLiteral 返回 `None`），拿不存在的实得类型去比只会造出假绿 |
| D-5 | 别名展开到底，但自指停在原地（`_alias_stack` 名链守卫） | `type Loop<T> = Loop<T>` 若不设防会把分析器打成 RecursionError；停止展开是既有行为，不新增主张 |
| D-6 | 不新造消息合成点：容器元素诊断走 `kind: expected X, got Y at L:C` 模板 | 与 BUG-64（`_mismatch`/`_type_display` 统一出口）一致，产物里不外泄内部编码 |
| D-7 | 联合别名的**成员元素位**（`ListOrSet<int>` 收 `["s"]`）本轮**不做** | 要动 `_type_in_union` 的语义，它是十几处共用的判据；本轮半径已经很大 ⇒ 另计开项 |
| D-8 | BUG-136 不冒充关闭：追**改判段**而不是 `### FIXED` | 机制栏错了要改正、(a)(b)(c) 转给 137/138、(e) 是既有测试钉住的行为、(f) 仍开 ⇒ 抬头仍 `OPEN` |
| D-9 | 禁 commit/禁推送不变；本轮全部证据按 tag 落唯一文件名 | 与既往轮一致；脏树里混着别家泳道改动，交回人工再定 |

## 3. 寻虫与半径

### 3.1 成对探针（先证「读取通道没坏」，再谈「它不判」）

`.fist-loop-20260929/probe_r13_container.py` 走 `scripts/omega_gate.py` 的**同一份** `execute()`，
39 形分五栏：`CTRL_*`（读取通道对照）、`P*`（非别名容器基线）、`A*`（同形走别名）、
`G*`（收紧后必须仍绿的占位）、`N*/U*`（别名展开与联合形态）。
探针自带三组会红的门：`must_be_red_but_silent` / `must_stay_green_now_red` / 崩溃计数。

```
CONCLUSION r13_container_probe tag=c1 cases=39 red=18 crashed=[] flipped=7 must_be_red_but_silent=[] must_stay_green_now_red=[] parse_failures=['A10_alias_bound_decl'] out=r13_container_probe_c1.json
CONCLUSION probe_rerun_determinism b2_vs_c1 identical_bytes=True sha=072e72cf85199d06
```

上面两行逐字取自 `logs/r13_probe_c1.out`（复跑件与 b2 的 json **按字节相同** ⇒ 这把尺可复现）。
首跑（tag=b1，31 形）时 `G08/G09` 两格被判"该绿却红"——那是本腿探针写坏了形状
（`class Dog:` 的字段我按记忆写成 `var n: str`），被自己的 `must_stay_green` 门当场抓住；
该次打印没有落盘，所以此处**不逐字引用**它，只在 §6.4 第 1 条记这件事。
`A10` 的 `parse_failures` 是**产品行为**（带界别名不解析），不是尺坏。

### 3.2 改判 BUG-136 的证据链

负向对照必须成对，所以每条都跑了「走别名」与「不走别名」两形：

| 观察 | 非别名形状 | 别名形状 | 结论 |
|------|-----------|----------|------|
| 元组第二位类型不符 | `P01` errors=0 | `A01` errors=0 | 根因在容器位，与别名无关 |
| 元组个数不符 | `P08` errors=0 | — | 同上 |
| 别名 arity | — | `A06` 报 `Type alias 'Result' expects 1 generic parameter(s), but got 2` | 别名**参数表在读** ⇒ 「从不代入」为假 |
| 标量别名 | — | `A09` 报 `Type mismatch: expected int, got str` | 非泛型别名**会展开** |
| 别名套别名 | — | `A07`/`N02` 报 `expected Pair[Pair[int]], got tuple<…>` | 代入了一层；没展开的那一层造出**假阳性** |

假阳性的**身份隔离**（先证不是本腿改动带来的）：
`.fist-loop-20260929/logs/r13_nested_alias_fp_a1.json` 把新加的 `_check_container_elements`
monkeypatch 成空操作再跑同一形状，诊断逐字不变（`identical_with_new_judge_off=True`）。

### 3.3 存量半径（改动前先数，不靠"改完看看"）

- 真实项目码里的泛型别名只有 `examples/demos/data_structures/type_alias_demo.cypy`（4 份声明 + 6 处使用），
  且 4 处使用字面量逐一体型正确 ⇒ 收紧不会把 demo 打成红；
- 测试码里的泛型别名：`tests/test_new_features_boundary.py`（4 支，其中 `:167` 断言裸用 `Maybe` 得 **0** 诊断）、
  `tests/test_generic_types.py`（三处声明，函数体只有注释 ⇒ 实际无断言）、`tests/test_parser_union.py:59`、
  `tests/test_incremental.py:115`；
- 全仓**没有** `type Name<T: Bound> =` 的源（解析失败的那一形）；
- 名字撞车要小心：`Result`/`Pair`/`Wrapper`/`List` 同时是 enum/struct/class 名 ⇒ 收口口径按「声明种类」分栏。

## 4. 修法与落点

| 落点 | 干了什么 |
|------|----------|
| `cypyc/analyzer/type_checker.py:4035-4042` | 三张常量表：`_ELEMENT_CHECKED_CONTAINERS`（`list/set/tuple/Array`，**不含 dict**）、`_SCALAR_ELEMENT_NAMES`（保守集，与手册逐字对表）、`_NUMERIC_WIDENING`（单向加宽） |
| `:4044` `_slot_incompatible` | 单个元素位的纯判定：占位放行、同名容器递归下沉、联合位交回原分支、加宽放行、仅两侧都是闭合标量且不同名才判死 |
| `:4070` `_first_bad_element` | 逐位扫描，返回 `(序号, 期望元素, 实得元素)`；两侧任一没有元素信息 ⇒ `None` |
| `:4083` `_sentence` / `:4087` `_check_container_elements` | 唯一记帐出口：定长容器先报个数，否则报第一处元素位；整串去重 ⇒ 同事实不叠第二笔 |
| `:890` 赋值位、`:973` 返回位 | 各接一行；仍按原样登记声明类型 ⇒ 一条错只报一次、不制造级联误报 |
| `:4174` `_substitute_type` 的 `UnionType` 分支 | 与 `_get_type_from_node:3951` 同形（`Type("object", union_members=…)`），成员先各自代入 |
| `:4202` `_expand_nested_alias` | 别名右端里的别名展开到底；`_alias_stack` 名链守卫自指；实参个数不符交回既有 arity 诊断 |

诊断文案样例（逐字来自 b2 探针）：

```
Element 2 type mismatch: expected int, got str at 2:9
Return element 1 type mismatch: expected int, got float at 3:1
Tuple element count mismatch: expected 2, got 1 at 2:9
Type mismatch: expected Union[int, None], got str at 4:9
```

## 5. 验证

### 5.1 判据层（Ω-gate 与语料）

- 新增 Ω-spec `corpus/cypy.container.elements.json`：28 对，指纹 `fnv1a64:7349f8d14b3fc9fc`；
  生成件 `.fist-loop-20260929/make_corpus_r13.py` **不走** `omega_gate.py --seal`
  （那条命令会把 `corpus/` 下每一份 spec 重写一遍），只给自己这份算指纹，
  并落盘前后各扫一次目录哈希自证 `others_untouched=True drift=[]`；
- 台账地板同批上调：`FLOOR_SPECS 6→7`、`FLOOR_CASES 123→151`（`tests/regression/test_corpus_pairs.py:33-34`）；
- 终值：`CONCLUSION specs=7 cases=151 passed=151 failed=0 refused=0 accuracy=100.00% rc=0`。

### 5.2 承重矩阵（`verify_r13_locks.py`，副本树，7 格）

| 格 | 动的地方 | pytest 红 | Ω-gate 失 | 身份探针 |
|----|----------|-----------|-----------|----------|
| L0 | 现树（应全绿） | 0 | 0 | — |
| M1 | 摘掉赋值位调用 | 20 | 9 | `anchor_gone=true` |
| M2 | 摘掉返回位调用 | 5 | 2 | `anchor_gone=true` |
| M3 | 逐位扫描短路 | 21 | 10 | `anchor_gone=true` |
| M4 | 撤掉 `UnionType` 代入 | 2 | 1 | `anchor_gone=true` |
| M5 | 撤掉别名展开 | 4 | 2 | `anchor_gone=true` |
| M6 | 只改注释（对照） | 0 | 0 | `code_unchanged=true` + 注释确实变了 |

```
CONCLUSION cells=7 load_bearing_cells=5 all_red=True comment_control_zero_red=True bad=[] rc=0
```

L0 第一次跑是**红的**：本腿那支「手册闭合标量表 ↔ 代码常量」的对表锁看不见手册 ——
副本树只拷了 `cypyc/tests/corpus/scripts`，没拷 `SYNTAX/`。补目录后 L0 归零，矩阵才算有分母。

### 5.3 四套全量（先测半径，再跑终版）

| 体系 | 半径轮（只含产品改动，`logs/r13_pytest_b2.log` 等） | 终版（含本轮锁与语料） |
|------|----------------------------------------------------|------------------------|
| pytest | 2325 passed（501.25s，`pytest_rc=0`） | 2390 passed（378.86s，`pytest_final_rc=0`） |
| 自研套件 `scripts/run_tests.py` | `Total: 47 \| Passed: 47 \| Failed: 0` | 同一件（`logs/r13_suite_b2.log`，起跑时新语料已在盘上） |
| Ω-gate 全 spec | 首次跑 `--op all` 打出 `specs=0` 且 rc=1 ⇒ 该读数**作废**（我的旗拼错，门禁自己拒了空跑） | `CONCLUSION specs=7 cases=151 passed=151 failed=0 refused=0 accuracy=100.00% rc=0` |
| `bash scripts/e2e_golden.sh` | `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0` | 同一件 |

2325 → 2390 的差额是 +28 新语料对与 +37 新锁用例（31 支函数 + 2 处参数化展开），
两边都由收集数反解，不手加。

### 5.4 作废与不采信读数

- `logs/r13_gate_b2.log`：`specs=0`，是我 `--op all` 的旗用错（`--op` 要的是具体 op），
  该文件留在盘上只为记录「门禁拒绝给空跑打分」；有效读数是 `logs/r13_gate_b3.log`；
- b1 探针（31 形）里 `G08/G09` 两格红是本腿探针形状写错（`var n: str`），不作为产品信号；
  有效探针是 b2（39 形，三组门全过），c1 是它的可复现复跑（两份 json 逐字节相同）。

### 5.5 收口子腿（收根之后）复跑了哪几套、没跑哪几套

子腿动的文件只有 `.fist-loop-20260929/` 下这几件与本报告：
`fill_r13_report.py`、`r13_self_certify.py`、`derive_r13_card_ids.py`、`verify_r13_report.py`、
`run_r13_ring.py`（拆掉被拒文案的打印截断）——
`cypyc/`、`tests/`、`corpus/`、`SYNTAX/` 一字未动。因此**跑得起的先跑**，跑不到的照实写：

| 体系 | 子腿是否复跑 | 逐字读数（`logs/r13_subleg_b1.out`） |
|------|--------------|--------------------------------------|
| R13 锁 + 语料地板（pytest 选面） | 复跑 | `============================= 191 passed in 0.58s =============================` |
| Ω-gate 全 spec | 复跑 | `CONCLUSION specs=7 cases=151 passed=151 failed=0 refused=0 accuracy=100.00% rc=0` |
| 自研套件 `scripts/run_tests.py` | 复跑 | `✓ Passed: 47` / `✗ Failed: 0` / `~ Skipped: 0` |
| 引用核验件（含 4 条注入对照） | 复跑 | `CONCLUSION checks=41 failed=0 canaries=['canary_fake_bug_id_is_caught', 'canary_stalled_root_is_not_closed', 'canary_window_lookup_miss_is_not_credited', 'canary_fake_cited_file_is_caught'] rc=0` |
| pytest 全量 2390 | **未复跑** | 沿用 §5.3 的终版读数；子腿没碰产品码与测试，重跑一遍 378s 不增加证据 |
| e2e golden 25 | **未复跑** | 同上，沿用 `PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0` |

核验件那条是 `--selftest` 档：四条假针（不存在的编号、不存在的文件名、`find` 落空的窗口、
把停滞根当已完成）全部被抓，其余判定未被我改坏 ⇒ 这张尺子不是装饰。
不动点另算一支（见 §6.3 末）：把核验件自己的结论抄进报告这件事，插入前后各跑一次，两次结论行逐字相同。

份数分栏，别混着说：开批门（`--stage close`）读的是 **33 张门**那一份（读数留在
`ring_r13_close_a1.json` 的 `entry_gate.observed.citation_check`，`failed=0` 才放行）；
收口之后又给尺子补了三张门（风格红必须可归因、账面现态回库复算、点名文件必须存在）⇒ 终版 **37 张**。
所以"收口时被合格门放行"与"现在这份报告被 37 张门验过"是两件事，两份读数都在盘上。

## 6. 账面

### 6.1 缺陷账（`memory/bugs.md`）

| 读数 | 值 | 口径 |
|------|-----|------|
| `## BUG-` 抬头数 | 141 | 本轮 137 → 141（+3 新单 +1 张账面完整性单） |
| 去重后编号数 | 140 | 与抬头数差 1 ⇒ 账上有**重复号** `## BUG-96`（两条并存，见下）⇒ 另立 BUG-140 |
| 开口块数 | 40 | 3 张新单同轮 FIXED ⇒ 净增只有 BUG-140（入账未修） |
| `### FIXED` 段数 | 93 | 90 → 93（+3 本轮关闭段） |
| `### 改判` 段数 | 1 | 新增形状：不改抬头、不关闭，只更正机制并指认去向 |
| 严重度分布（开口） | low 11 / medium 24 / high 5 | 本轮新立 2 high + 1 medium 全部同轮关闭；净增 medium 1 条 = BUG-140 |
| 泛型/别名族开口 | 7 条（120+121+122+128+134+135+136） | 由核验件按"无 `### FIXED/DUPLICATE`"反解；137/138/139 已闭不入此列 |
| 重复编号 | `BUG-96` 两次（第 2747 行 `[medium] …Z` 与第 2868 行 `[high] …+00:00`） | 入账为 BUG-140（medium，**不改账**：改号会让既有引用悬空，合并会把两种严重度压成一条 ⇒ 交回人工裁决） |

四张新单：BUG-137（high，容器元素位）、BUG-138（high，别名套别名 ⇒ 假阳性）、
BUG-139（medium，联合形态别名不代入）、BUG-140（medium，台账重复编号，入账未修）；
改判单：BUG-136（仍 OPEN，只剩 (f) 带界别名面）。
入账与关闭都用 `reported_key` 反查编号，不手写 `## BUG-NN`。反解件 `derive_r13_card_ids.py`
逐张卡要求「该键在台账里只命中一个 `## BUG-` 块」，命中数不是 1 就翻红（首跑见 `logs/r13_cardids_a1.out`）：

```
R13-CONTAINER-ELEMENT-NO-CHECK -> BUG-137 FIXED (one_block=True)
R13-NESTED-ALIAS-NOT-EXPANDED -> BUG-138 FIXED (one_block=True)
R13-UNION-SHAPED-ALIAS-NO-SUBST -> BUG-139 FIXED (one_block=True)
R13-GENERIC-TYPE-ALIAS-NO-SUBST -> BUG-136 AMENDED-OPEN (one_block=True)
R13-LEDGER-DUPLICATE-BUG-ID -> BUG-140 OPEN (one_block=True)
HEADERS 141 UNIQUE 140 DUP ['BUG-96']
CONCLUSION r13_card_ids cards=5 mismatches=[] duplicate_ids=['BUG-96'] rc=0
```

`HEADERS 141 UNIQUE 140` 与 §6.1 表里的两个读数同源：这张反解件顺带把重复号也印了出来，
所以"抬头 141 / 去重 140"不是我从别处抄来的。
入账回执本身（`logs/r13_leddup_a1.out`）另有一条 `VERBATIM` 行贴出 BUG-140 的原文卡片正文。

三向对照（md ↔ `bug_list` ↔ `call_log`）——**首跑 a1 的回执已不可复核**：`OUT` 当时写死成
`file_r13_container_bugs.json`，a2 复跑把它原地盖掉了（§6.4 第 7 条），
所以这里**不**引用 a1 的取号行，只引用现在盘上还在的那两份：
上面那段 `reported_key` 反解（`logs/r13_cardids_a1.out`）证明 137/138/139 三张卡各只命中一个块，
下条是**幂等复跑取证**（守卫让它变成 `filed=0 skipped=3`，不重发单据），逐字取自 `logs/r13_filed_a3.out`：

```
CONCLUSION r13_filed tag=a3 filed=0 skipped=3 refused=0 new_ids=[] bug_list_count=141 headers=141->141 report_bug_rows=43 db=fist-mbt.db(exists) three_way_ok=True out=file_r13_container_bugs_a3.json
```

顺带记一笔债：这份 a3 回执的**文件名**已带 tag（`out=file_r13_container_bugs_a3.json`），
是修掉"同名覆盖"之后才有的形状；a1 那份取号瞬间**永久丢失**，只能标为不可复核。

台账腿自证（`amend_r13_ledger.py --refresh`，`logs/r13_ledger_c1.out`）：段落戳唯一且形状合法、
派生数逐字落进段落；首装档是「开口 −3 / FIXED +3」，回收档（本条）账变全为零——
换掉的只是自己那段，不是新关一单：

```
CONCLUSION r13_ledger touched=4 ids=['137', '138', '139', '136'] headers=141 open=40 fixed=93 amend=1 refresh=True derived=D
```

### 6.2 FIST 账面

- 根单：`publish_parallel` 建 `T0r119`，描述首行带 `[omega:required]` 与身份标记 `R13-RING-T0r119`；
- 拆解：`task_plan_deep`（`split_n=3`、`omega_strong_verify=True`、`boundary_probe=True`），
  回读 `rows=17 leaves=12 boundary=6 faces_missing=0`；
- `laya_decide`：`available:false` + `fallback`（no_sidecar 下的既有形态，照 R12 记流程账不装作有裁决）；
- `loop_*`：`cypy-selfdrive-ring-r13`，steps 六格与 R12 同种子，基线数从本轮日志与台账反解。
- 收口腿（`--stage close --tag a1`）：12 支叶 + 4 支枝干 + 根全部上卷到 `已完成`，
  `rollup={'已完成': 17}`、`non_closed=[]`、`pending_leaves=0`、`calls=89`、`refused=0`、
  `call_log_error_rows=0`、六格 `loop_tick` 全接受（§6.3 那条是它的逐字回执）。
- Omega 强验证的**账面存在性**按树复算（核验件现读 `fist-mbt.db`，不是抄回执）：
  `specs` 里 `spec=17`（每节点一条，含根与枝干）、`result=17`、`check=12`（每叶一条 `run_check` 落库）；
  三张门分别是 `ring_root_closed_now_in_db`、`omega_strong_verify_rows_cover_tree`、
  `check_rows_equal_leaf_count`，并配一根会红的对照 `canary_stalled_root_is_not_closed`
  （`T0r112` 根当下仍是 `拆分中` ⇒ 上面那句"已完成"不是把整库读成一锅粥）。
- 仍有两根**不收**：`T0r112`/`T0r113`（§8 记状态，不伪造交付物）。

### 6.3 本腿逐字回执

- 起手腿首跑（`--stage start --tag a1`）建根 + 拆解 + 挂判据，回执件 `ring_r13_start_a1.json`
  （`root=T0r119`、`tree_readback.rows=17`、`leaves=12`、`refusals=[]`）；
- 复跑（`--stage start --tag c1`，逐字取自 `logs/r13_ring_start_c1.out`）证明这条腿幂等：
  叶已是 `已领取`、`spec` 行已存在 ⇒ 只读不写：

```
CONCLUSION stage=start root=T0r119 rows=17 leaves=12 faces_missing=0 calls=2 refused=0 benign=0 tag=c1
```

- 收口腿逐字回执（src=`r13_ring_close_a1.out`，由 `fill_r13_report.py` 在收根之后回填；回执全文在 `ring_r13_close_a1.json`，本件不截断）：

```
CONCLUSION stage=close root=T0r119 root_status=已完成 rollup={'已完成': 17} non_closed=[] pending_leaves=0 calls=89 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 call_log_error_rows=0 old_needle_rows=0 suite=('47', '47', '0') golden=PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0 tag=a1
```

  `root_status=已完成`、树内终态 {'已完成': 17}、未闭合 []；被拒 0 条、幂等命中 0 条（条数不为 0 时逐条整条列在下面，绝不省略号）。

- 核验件逐字结论（src=`logs/r13_selfcertify_c1.out`，由 `r13_self_certify.py` 回填）：
  插入引用**前后各跑一次**，两次结论行逐字相同才算数 —— 这句引用一旦让核验件翻红，
  报告就回到插入前那一版，而不是留一句「核验件全绿」的假话：

```
CONCLUSION checks=38 failed=0 ledger_open=40 bug_ids=12 corpus_total=151 rc=0
```

  第二份同样的字节在同一次运行里（第二次跑的是已经带上这段引用的报告）⇒ 不是抄一次读数，是不动点。
  核验件 stdout 的 `PASS`/`FAIL`/`ORPHAN_QUOTE` 行不进证据面（`evidence_blob` 对本件日志只取结论行），
  否则我打印出来的孤儿会被下一次运行读成「证据里有了」。
### 6.4 本腿自犯的坏尺与坏模板（每条要么由现算/复跑**抓出**，要么是落盘前自己重读抓到的并标「自读」；条数不写死，见核验件反查）

1. **探针形状写错当成产品红**：`class Dog:` 的字段我按记忆写成 `var n: str`、泛型类写成
   `class Box[T]:` ⇒ 两格对照直接解析失败。抓它的是自己的 `must_stay_green_now_red` 门。
   教训复述：负面主张的对照组要先证明读取通道看得见样本。
2. **过宽的"未插值"针**：入账脚本用 `"{" in detail` 当门，被一条**合法**正文
   （`dict<str, int> = {"a": "b"}`）打回。改成只认 `\{标识符\}` 形状。
   同一形状的针在 `amend_r13_ledger.py` 里也提前从「本件段落不含任何花括号」降级为
   「不含未插值占位」，否则整档合法样例都会挡路。
3. **中文串里嵌 ASCII 直引号 = SyntaxError**：本轮第 4 次踩（`"没有展开成 tuple<…>"`）。
   报出来的错指向下一行且提示 `invalid character '…'`，容易误判为编码问题。
4. **整档脏检当门**：`amend_r13_ledger.py` 初稿把「全档无坏戳/无占位」写进 ok 条件 ——
   那是拿别轮的缺陷当本件的门（R12 已为此返工过一次）。本轮开跑前就改成
   「门只钉本件亲笔段（`build()` 内逐段断言 + 逐字落盘计数），整档只印读数」。
5. **副本树少拷一个目录 ⇒ L0 恒红**：矩阵的 `copy_tree` 只拷 `cypyc/tests/corpus/scripts`，
   而本腿新写了一支「手册标量表 ↔ 代码常量」的对表锁 ⇒ 现树格里它是红的，
   连对照格（只改注释）也一起红。补 `SYNTAX` 后矩阵才有分母。
6. **三向对照只跑了两向**：`file_r13_container_bugs.py` 把 sqlite 路径写成 `HERE/"fist-mbt.db"`
   （真实库在仓库根）⇒ 文件不存在时那一栏键整个不落，而 ok 条件又没要求它 ⇒
   照样打印 `three_way_ok=True`。已改成「三向的基数键缺失即视为门坏」，并复跑取证
   （幂等守卫让复跑变成 `filed=0 skipped=3`，不重发单据）。
7. **门与证据同名 ⇒ 复跑原地覆盖**：上面那次复跑把 a1 的入账回执盖掉了。
   回执名改成 `file_r13_container_bugs_{tag}.json`；新单编号改从台账 `reported_key` 反解，
   不依赖那份被覆盖的件。
8. **"仍静默 N 形"混了两类事**：初版把正向对照（`A03_alias_ok`/`A08_alias_in_param` 本就该绿）
   和别单范围（`P05_dict_val_wrong`）写进同一句，读起来像"本单还剩 6 形没修"。
   现在按探针自己的 `MUST_GREEN` 分栏，`KEPT_GREEN` 与 `STILL_SILENT` 各一句。
9. **`--op all` 的空跑**：门禁给了 `specs=0 … rc=1`（拒绝对零判据打分），这是本轮唯一一次
   「尺子自己红在旗拼错」；作废该读数并复跑 b3。
10. **"逐字引用"只在 stdout 里活着**：报告初稿抄了 5 条 CONCLUSION（探针 b1/b2、矩阵、入账、台账、
    起手腿），核验件一次抓出 11 条孤儿——它们从没进过任何证据文件。
    修法是**复跑并 tee**（探针额外做一次"两次 json 按字节相同"的可复现门），而不是把引用删掉了事；
    b1 那种"当时红在尺子上"的一次性打印则明确标注不引用，只记事件。
11. **抬头数与编号数不是一回事**：核验件按 id 建字典后 `len(blocks)=139`，正则数抬头是 `141`——
    差 2 里藏着一个真缺陷（`## BUG-96` 复用了两次，字典静默吞掉一张）。
    现在两数并列成门（`unique_equals_headers_minus_dups` + `duplicate_ids_declared_and_filed`），
    抓到即入账（BUG-140），不改账。
12. **`--quiet` 把「红」变成不可归因**：核验件的风格门用 `black --check --quiet` 数脏文件，
    而 `--quiet` 连 `would reformat <文件>` 一起吞 ⇒ 实测 `rc=1` 而清单为空：门禁红了却指不出是谁红的。
    去掉 `--quiet`，并补一张 `black_failure_is_attributable`（rc≠0 且清单为空 ⇒ 判尺子坏，不判产品坏）。
13. **回填件的落点 needle 凭记忆连错两次**：`fill_r13_report.py` 先按「（L4 产物门的顺序要求）」找占位，
    可那对全角括号挂在**句首**（原文是「（报告先落盘、再收根…」），文案里根本没有「（L4」；
    退一步改成「产物门的顺序要求。」又漏了中间的 `）`。
    两次都是脚本**拒收**（打印「落点找不到 ⇒ 拒绝乱插」）而不是就近插入 —— 这个行为要保住；
    最终锚换成结构形状（从这条 bullet 吃到空行为止），不再猜文案。
14. **被拒文案会在打印环节被截断**：`run_r13_ring.py` 原本 `print(..., reply_verbatim[:300])`，
    300 字之外只存在于回执 json ⇒ 报告若照抄打印行，得到的是一条「看着完整实则不可复核」的引用。
    现已去掉截断，回填件另加 `no_ellipsis_in_block` 门（自己那段里不许出现省略号）。
15. **不动点门自己差点先红一次**（自读抓到，没有门认领它）：初版顺序是「替换报告 ⇒ 跑第二遍 ⇒ 才写 log」，
    于是第二遍核验件在自己的证据面里找不到被报告引用的那句结论（引用了一件尚未写出的东西）。
    改成先把第一遍输出占住文件名、再替换报告、再跑第二遍；两遍的结论行必须逐字相同才算过。

## 7. 规范、文档与风格

- `SYNTAX/02-type-annotations.md`：新增「容器元素位判定（R13 补，2026-09-29）」规则 1-6，
  规则 4-6 明写不判的一面与放行理由；
- `SYNTAX_IMPLEMENTATION_STATUS.md`：`02-type-annotations.md` 行改写为
  「已闭环（R13）… 未闭环…」并点名 28 对 spec；
  `12-type-alias.md` 行从「✅ 完整 / 无」改为「⚠ 部分」并列出仍开的两面
  （带界别名不解析、联合成员元素位不判）⇒ 手册那句「编译时完全等价」现在才有判据支撑；
- `CHANGELOG.md`：R13 条目（新增判定件 + 三张单关闭 + BUG-136 改判）。

风格分两档主张，不写「全部文件已格式化」那种话：
本轮亲笔的 Python 件过 `black`/`isort`；`cypyc/analyzer/type_checker.py` 属仓库既有未格式化文件，
本轮**不交整档 formatter**（HEAD 副本整档重排会造出上千行不可回滚的噪声），
新增代码按周围风格手写并保持 `py_compile` 通过。

## 8. 未完项（不伪造关闭）

| 项 | 状态 | 为什么不顺手做掉 |
|----|------|------------------|
| 字典字面量不推断类型（`_visit` 对 DictLiteral 返回 `None`） | 开 | 要新增字面量类型推断，是另一条线；键值位判定等它 |
| `ListOrSet<int>` 收 `["s"]` 仍静默 | 开（D-7） | `_type_in_union` 被十几处共用，改它=换判据口径 |
| BUG-122 类型实参不判存在性 | 开 | 别名路径与非别名路径同形，一起改才有成对锁 |
| BUG-136(f) 带界别名 `type Num<T: Bound> =` 不解析 | 开 | 与 BUG-120/121 是同一族定义侧冒号形态，宜同批改 |
| BUG-135 / BUG-128 构造位与 struct 方法代入 | 开 | 同一推断层，半径大于本轮 |
| `T0r112` 待领取 15 / `T0r113` 待领取 4 | 未收 | 本轮复测 sqlite（`id=? or id like '根.%'` 按 status 分组）与 R12 同值：两根仍有 `拆分中` 枝干；待领取叶无退役出路（BUG-106），不伪造交付物 |
| BUG-140：台账里 `## BUG-96` 用了两次 | 入账未修 | 改号会让报告/FIXED 段/任务库 linked id 悬空，合并会压掉一种严重度 ⇒ 交回人工裁决 |
| 用户类/trait 元素位（`list<Speak> = [Dog()]`） | 刻意放行 | D-3 保守集；已钉成会红的锁，扩面那天先红 |

## 9. R14 入口（按收益排序）

1. 字典字面量类型推断（`dict<str, int>` 收 `{"a": "b"}` 要能判键值位）—— 本族最后一块静默面；
2. `_type_in_union` 升级为「成员整位可接受才算接受」⇒ 联合别名的元素位随之可判（D-7 的回补）；
3. BUG-120/121/122/136(f) 一批：定义侧冒号形态与类型实参存在性同批改，一次拿到成对锁；
4. BUG-135 + BUG-128 推断层（构造位不写类型实参）；
5. `T0r112`/`T0r113` 两根的待领取叶出路（要么给退役工具，要么按流程债正式记档）；
6. `tests/test_generic_types.py::TestGenericTypeAlias` 三支空壳用例（函数体只有注释）——
   本轮的锁已覆盖其意图，但空壳还在，收编而不是删；
7. BUG-140 的处置（重编号 vs 合并 vs 保留双条并在工具侧强制"按行取"）——需人工裁决，
   本轮已把「抬头数 ≠ 编号数」做成会红的门，不裁决它就每轮报一次。
