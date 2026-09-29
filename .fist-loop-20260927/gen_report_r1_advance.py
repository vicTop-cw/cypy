"""生成 R1-推进 环节报告：所有数字从取证件反解，任一条不成立就拒绝落盘。

用法：python gen_report_r1_advance.py <报告名(不带目录与扩展名)>

本轮的两条"必须成立否则不许自称落地"的硬门写死在这里：
 ① 9 条候选每条都要有**文档行号 + CLI rc + 成对对照**（子代理清单只当线索，不当结论）；
 ② 两条补口都要在**回退树**上让自己的锁转红、且不牵连对方（混因的红不能归给这一单）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
L = ".fist-loop-20260927/"
FLOOR = 1868
NAME = sys.argv[1] if len(sys.argv) > 1 else None
if not NAME:
    raise SystemExit("REFUSE — 必须传报告名")
REPORT_REL = f"memory/reviews/{NAME}.md"
refuse = []


def load(fname, required=True):
    p = HERE / fname if not fname.startswith("..") else ROOT / fname
    if not p.exists():
        if required:
            refuse.append(f"取证件不在盘上：{fname}")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


ver = load("advance_verify_r1.json")
lock = load("advance_lockproof_r1.json")
base = load("advance_baselines_r1.json")
filed = load("advance_file_bugs_r1.json")
close_p = HERE / "close_r1_advance.out.json"
PRE_CLOSE = not close_p.exists()
cl = (
    json.loads(close_p.read_text(encoding="utf-8"))
    if not PRE_CLOSE
    else {"leaves": [], "failed": []}
)
rootc = load("close_r1_advance_root.out.json", required=not PRE_CLOSE) if not PRE_CLOSE else {}

for fname, doc in (
    ("advance_verify_r1", ver),
    ("advance_lockproof_r1", lock),
    ("advance_baselines_r1", base),
):
    for r in (doc or {}).get("refuse", []):
        refuse.append(f"{fname} 自报拒绝：{r}")

# ---- ① 清单面：9 条、每条有文档行号与对照 ----
rows = ver.get("rows") or []
if len(rows) != 9:
    refuse.append(f"判据① 候选条数不是 9：{len(rows)}")
for r in rows:
    de = (r.get("doc_evidence") or [{}])[0]
    if not de.get("found") or not de.get("quoted_line"):
        refuse.append(f"判据① 候选 #{r.get('id')} 的声明句没回核到原文：{de}")
    prs = (r.get("matcher_control") or {}).get("pairs") or []
    if not prs or not all(p.get("catches_positive") and p.get("misses_negative") for p in prs):
        refuse.append(f"判据① 候选 #{r.get('id')} 的 matcher 对照不齐（正例必抓/反例必不抓）")
verdicts = {r["id"]: r["verdict"] for r in rows}
if verdicts.get(1) != "works" or verdicts.get(5) != "works":
    refuse.append(f"判据② #1/#5 收口时应为 works，实测 {verdicts.get(1)}/{verdicts.get(5)}")
gaps_left = sorted(i for i, v in verdicts.items() if v != "works")
silent_left = [i for i in gaps_left if verdicts[i] == "gap-silent"]
if silent_left != [3, 4]:
    refuse.append(f"判据② 剩余静默型缺口应为 [3,4]（已入账 BUG-44/45），实测 {silent_left}")

# ---- ③ 账本：两条静默缺口必须是可见条目 ----
bugs_md = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
for need in ("BUG-44", "BUG-45"):
    if f"## {need}" not in bugs_md:
        refuse.append(f"判据③ 账本里找不到 {need} 的可见条目头（隐形标题会让它从 bug_list 消失）")
tail_ids = [x.split("|")[0] for x in (filed.get("bug_list_tail") or [])]
for need in ("BUG-44", "BUG-45"):
    if need not in tail_ids:
        refuse.append(f"判据③ {need} 没出现在 bug_list 回读里：{tail_ids[-6:]}")

# ---- ④ 回退树证红 ----
full = lock.get("full_tree") or {}
if full.get("rc") != 0 or len(full.get("passed") or []) < 6:
    refuse.append(f"判据④ 完整树不绿：{full}")
logs = sorted((p.name for p in HERE.glob("advance_lockproof_reverted_ADV-*.log")))
if len(logs) != 2:
    refuse.append(f"判据④ 回退树日志不是 2 份：{logs}")
REVERTED_LINES = {}
for who, expect_red in (("ADV-1", 2), ("ADV-2", 2)):
    lp = HERE / f"advance_lockproof_reverted_{who}.log"
    txt = lp.read_text(encoding="utf-8", errors="replace") if lp.exists() else ""
    m = re.search(r"(\d+) failed, (\d+) passed", txt)
    REVERTED_LINES[who] = m.group(0) if m else "（日志里没有摘要行）"
    if not m or int(m.group(1)) != expect_red or int(m.group(2)) != 4:
        refuse.append(f"判据④ {who} 回退树不是「恰 {expect_red} 红 4 绿」：{REVERTED_LINES[who]}")

# ---- ⑤⑥ 文档双向一致 + 半径 ----
docx = base.get("doc_example") or {}
if docx.get("rc") != 0 or not docx.get("emit_has_block_call"):
    refuse.append(f"判据⑤ 文档原文例子没过 CLI：{docx}")
rad = base.get("radius") or {}
EXPECT2 = ["cypyc/codegen/cython_generator.py", "cypyc/parser/parser.py"]
if sorted(rad.get("expected") or []) != EXPECT2:
    refuse.append(f"判据⑥ 预期改动面写错：{rad.get('expected')}")
if rad.get("product_files_touched_this_stage") != rad.get("expected"):
    refuse.append(f"判据⑥ 本轮实际动过的产品文件与预期不一致：{rad}")
if rad.get("new_token_or_class_defs_in_my_hunks"):
    refuse.append(f"判据⑥ 我的改动里出现新增语法单元：{rad['new_token_or_class_defs_in_my_hunks']}")

# ---- ⑦ 三套基线与收集数 ----
pf = base.get("pytest") or {}
if pf.get("passed") is None or pf["passed"] < FLOOR:
    refuse.append(f"判据⑦ pytest 通过数不足 {FLOOR}：{pf}")
if pf.get("failed_or_error"):
    refuse.append(f"判据⑦ pytest 有红/错：{pf['failed_or_error']} {pf.get('failed_tests')}")
if (base.get("suite") or {}).get("green") is not True or (base.get("suite") or {}).get("rc") != 0:
    refuse.append(f"判据⑦ 自研套件不绿：{base.get('suite')}")
if "PASS=25 FAIL=0" not in ((base.get("e2e") or {}).get("line") or ""):
    refuse.append(f"判据⑦ 端到端基准不是 25/25：{base.get('e2e')}")
if (base.get("collection") or {}).get("count") != 6:
    refuse.append(f"判据⑦ 新文件收集到的锁数不是 6：{base.get('collection')}")
if (base.get("lint") or {}).get("attributable_to_this_round"):
    refuse.append(
        f"判据⑦ 本轮自己写的代码有 lint 违例：{base['lint']['attributable_to_this_round']}"
    )
if (base.get("black") or {}).get("rc") != 0:
    refuse.append(f"判据⑦ 本轮新写的文件不是 black 干净：{base.get('black')}")

head = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), capture_output=True, text=True
).stdout.strip()
if head != "17d68b4":
    refuse.append(
        f"红线核对：本轮起点 HEAD 应是 17d68b4，实为 {head}（有别的提交进来，须重算基线）"
    )

if not PRE_CLOSE:
    if cl.get("failed"):
        refuse.append(f"判据⑧ 叶子未过链：{cl['failed']}")
    if len(cl.get("leaves", [])) != 16:
        refuse.append(f"判据⑧ 叶子数 {len(cl.get('leaves', []))}≠16")
    if rootc.get("root_final") != "已归档":
        refuse.append(f"判据⑧ 根任务未归档：{rootc.get('root_final')}")

if refuse:
    print(json.dumps({"REFUSE — 报告不落盘": refuse}, ensure_ascii=False, indent=1))
    sys.exit(1)


def q(x) -> str:
    return str(x).replace("|", chr(92) + "|")


now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
leaf_claim = (
    "未执行（预收口）"
    if PRE_CLOSE
    else (
        f"{len(cl['leaves']) - len(cl['failed'])}/{len(cl['leaves'])} `output_validate=pass`，"
        f"服务侧 0 ERR，根任务 `{rootc.get('root_final')}`"
    )
)
VERDICT_CN = {
    "works": "已实现（本轮补口后）",
    "gap-parse": "显式解析失败（未实现）",
    "gap-silent": "静默错产物（未实现，已入账）",
    "not-declared": "文档未声明",
}
cand_rows = "\n".join(
    f"| {r['id']} | {q(r['name'])} | `{q((r['doc_evidence'] or [{}])[0]['where'])}` | "
    f"{q((r['doc_evidence'] or [{}])[0]['quoted_line'])[:58]} | rc={r['probe']['rc']} | "
    f"**{q(VERDICT_CN.get(r['verdict'], r['verdict']))}** |"
    for r in rows
)
left_table = "\n".join(
    f"| {i} | {q(next(r['name'] for r in rows if r['id'] == i))} | {q(verdicts[i])} | "
    f"{q(next((r['probe']['cli_error_first'] for r in rows if r['id'] == i), '') or '—')} |"
    for i in gaps_left
)
refused_rows = (
    "\n".join(
        f"| `{r.get('call')}` | `{q(r.get('task_id'))}` | {q(r.get('error'))} |"
        for r in (rootc.get("refused") or [])
    )
    or "（本轮收口链上没有出现任何被拒调用）"
)
tally = "、".join(f"`{k}`×{v}" for k, v in (rootc.get("call_log_tally") or {}).items()) or "—"
doc_q = "\n".join(f"  {ln}" for ln in (docx.get("quoted") or []))

md = f"""# R1-推进（advance）环节报告 · {NAME}

- 环节：第 1 轮第 5 环（寻虫→修复→验证→打磨→**推进**）；根任务 `T0r54`；执行人 `cypy-advancer`
- 时间盒：≤100 分钟；半径裁定：**只做 SYNTAX 已声明、实现缺失的项**，不加未被文档声明的新功能，不动冻结语义
- 生成时刻：{now}；所有数字从盘上取证件反解，不由人手抄
- 取证件：`{L}advance_verify_r1.json`（9 条候选复算）、`{L}advance_lockproof_r1.json`（回退树证红）、
  `{L}advance_baselines_r1.json`（三套基线 + 文档双向核对 + 半径）、`{L}advance_file_bugs_r1.json`（入账回读）

## 一、清单：子代理给的 9 条候选，逐条自己打到 CLI 上复算

开工纪律（写在这里以免事后辩解）： hunting 环节的清单是**线索不是结论**——上一轮的教训是形状推断会把
无关表格行当成语法承诺。故每条候选都要同时过两关：文档指定行 ±3 内出现声明句原文（A 关），
以及一条最小 .cypy 源码在 `python -m cypyc transpile` 上的实际 rc 与**产物文本**（B 关）。

| # | 特性 | 声明处 | 声明句原文（回核） | CLI rc | 复算判定 |
|---|---|---|---|---|---|
{cand_rows}

判据形状本身也被这两条对照兜住：每条候选的 matcher 都配「正例必抓 / 修复前形状必不抓」，
其中**反例是固定的修复前文本**，不是本次产物——拿产物当反例等于让判据跟着结论改，
第一版就是这么把已经修好的 #1 判成"matcher 不可信"的。

## 二、落地的两条补口（都打到调用面，不是"模块里有函数"）

### ADV-1 `raise X from e`（声明处 `SYNTAX/16-exceptions.md:111`）

- 复算到的原状态：`gap-silent` —— transpile rc=0、横幅 `[OK] Transpiled successfully`，
  但产物里 `raise RuntimeError('Failed to load data')` 后面**没有** `from e`（`cause` 字段被丢）。
- 改动：`cypyc/codegen/cython_generator.py` 的 `_visit_RaiseStmt` 读 `node.cause`，补出 ` from <原因>`（4 行）。
  解析器早就存了 `cause`（`cypyc/parser/parser.py:2334-2343`），丢在代码生成层。
- 收口状态：`works`；且 `python -m cypyc run` 的执行面里 `r.__cause__` 打出 `nope`（修复前是 `None`）。

### ADV-2 `let x =:`（声明处 `SYNTAX/13-build-blocks.md:74`）

- 复算到的原状态：`gap-parse` —— `Expected NEWLINE, got BUILD_ASSIGN at 1:12`。
- 改动：`cypyc/parser/parser.py` 的 `_parse_let_stmt` 认 `=:`，并**脱糖成裸形 `x =:` 的 AST**
  （`Assign(Name, BuildBlockExpr)`）。这不是省事：LetStmt 的 codegen 走 `_expr_to_str`，
  直接把 def 块压成一行废码 `result = def _bb_0():    x: int = 10 ...`（实测过），
  而 Assign 路径已有正确产出；文档 13 号自己写的就是"构建块自动将最后表达式赋值给左侧变量"。
- 验收判据因此是**双向差分**：`let result =:` 与 `result =:` 的产物必须逐行相同
  （`test_bug_adv2_let_and_bare_forms_emit_identically`），而不是"`let` 那侧产物里有没有 result 字样"。
- 文档原文例子（逐字送进 CLI，未做任何"顺手修正"）：
{doc_q}

  结果：rc={docx.get('rc')}，产物结构含块定义后赋值调用 = {docx.get('emit_has_block_call')}。

## 三、锁死回归与回退树证红（HEAD 码 + 当前测试，逐单回退）

新增 `tests/test_loop_20260927_advance.py`：6 条 = 2 条锁 + 2 条差分/运行时 + 2 条对照。

| 树 | 结果 | 读法 |
|---|---|---|
| 完整树（不改任何东西） | `{q((full.get('line') or ''))}`，逐条 PASSED {len(full.get('passed') or [])} 条 | 6 条都在跑 |
| 回退 ADV-1 | `{q(REVERTED_LINES.get('ADV-1'))}`（log 末行原文） | 红的恰是 ADV-1 的锁；ADV-2 与两条对照全绿 ⇒ 不混因 |
| 回退 ADV-2 | `{q(REVERTED_LINES.get('ADV-2'))}`（log 末行原文） | 红的恰是 ADV-2 的锁；ADV-1 侧不受牵连 |

回退是**按文本针**做的，针之前先断言"命中且只命中 1 处"（`advance_lockproof_r1.py` 的 `build_tree`）——
`_parse_let_stmt` 附近那段形状在本文件里出现了 4 次，不锚定就会静默针到别处，造出假绿冒充证红。

## 四、半径核对（本轮到底动了什么，用 mtime 而不是 git diff 说话）

工作树里还压着上一轮未提交的改动，所以"本轮改了哪些产品文件"不能拿 `git diff` 当账——
那会把别人轮的改动算进来（判据坏不是代码坏）。这里用 mtime ≥ 打磨收口时刻 归属：

- 实际动过：`{q(json.dumps(rad.get('product_files_touched_this_stage'), ensure_ascii=False))}`
- 预期：`{q(json.dumps(rad.get('expected'), ensure_ascii=False))}`
- 我的改动里新增的语法单元（class/TokenType 成员）：`{q(json.dumps(rad.get('new_token_or_class_defs_in_my_hunks'), ensure_ascii=False))}` ⇒ 空
- 新增锁文件：`tests/test_loop_20260927_advance.py`（只加不减，未动任何既有用例）
- 本轮自己的代码 lint（`flake8 --max-line-length=100`，项目 `[tool.*]` 声明宽度）：
  作用域 {(base.get('lint') or {}).get('scanned_files')} 个文件（产品 2 + 新测试 1 + lane 取证件 6），
  归到本轮的违例 `{q(json.dumps((base.get('lint') or {}).get('attributable_to_this_round'), ensure_ascii=False))}`；
  唯一豁免：报告生成器里嵌的是 markdown 表格行，只放过它的 E501
  （{q(json.dumps((base.get('lint') or {}).get('e501_only_exempted_files'), ensure_ascii=False))}，
  被放过的条数 {(base.get('lint') or {}).get('exempted_hits')}）——点名而不是静默过滤。
- `black --check` 对整篇新写的 {(base.get('black') or {}).get('files')} 个文件：rc={(base.get('black') or {}).get('rc')}
  （既有产品文件不在这条断言里——全仓有 4 个文件本来就要整档重排，那是 §八 转结里的裁决项，不是本轮的债）。

## 五、三套基线（只升不降）

| 判据 | 命令 | 结果 |
|---|---|---|
| pytest 全量 | `python -X utf8 -m pytest tests/ -q` | **{pf.get('passed')} passed / 红错 {q(pf.get('failed_or_error'))}**（rc={pf.get('rc')}），下限 {FLOOR} = 打磨终态 1862 + 本轮 6 条锁 |
| 自研套件 | `python -X utf8 scripts/run_tests.py` | `{q((base.get('suite') or {}).get('line'))}`（rc={(base.get('suite') or {}).get('rc')}，逐字段裁决 {(base.get('suite') or {}).get('verdict')}） |
| 端到端基准（不带 --update） | `bash scripts/e2e_golden.sh` | `{q((base.get('e2e') or {}).get('line'))}`（rc={(base.get('e2e') or {}).get('rc')}） |
| 新文件被收集 | `pytest tests/test_loop_20260927_advance.py --collect-only -q` | {q((base.get('collection') or {}).get('count'))} 条 |

末行原文（防"解析器坏了"）：`{q(pf.get('summary_line'))}`
SKIPPED 行数：{pf.get('skipped_lines')}；负载快照（`lane_load.py`，本轮改进后的探针）：
`{q(json.dumps(base.get('load') or {}, ensure_ascii=False)[:220])}`

## 六、本轮抓到并修回的**判据自身**缺陷（八条）

1. **token-presence matcher 放过废码**：`let x =:` 第一版判据是"产物里出现 `result` 字样"，
   于是 `result = def _bb_0():    x: int = 10 ...` 这种一行压平的非法产物被判成 works。
   换成结构判据 `(?m)^result = _bb_\\d+\\(\\)$` + 与裸形的**逐行差分**才抓到。
2. **拿本次产物当 matcher 的反例**：修好之后产物必然匹配自己的 want，于是对照报"matcher 不可信"，
   把已完成的补口打成判据故障。反例改成固定的"修复前形状"文本。
3. **`pytest -v` 的行形状读错**：证红驱动按 `^PASSED <id>` 找通过行，而真实形状是
   `<id> PASSED [ 16%]` ⇒ 6 条全绿的完整树被读成"未收集"，反而去拒绝一个正确结论。
4. **参数名按上轮形状猜**：`report_bug` 这次用 `title` 被协议级拒绝
   （`缺必填参数 summary（schema.required 已声明，BUG-19 硬门）`），改成 `summary` 才入账；
   同一条教训在第 57 坑里已经记过一次（`memory_consolidate`），说明"上次这么调过"永远需要现问 `tools/list`。
5. **"扩作用域"把两类归属口径叠在一起**：为了不再漏文件，我把本轮写过的**所有**文件（含两个既有
   产品文件）放进同一张 `OWN_FILES` 表，而循环里"在表里就算我的"那条分支先于行区间判定命中 ⇒
   `cython_generator.py` 的 673 条**存量** E501/W293 全被判成"本轮违例"。改成两套口径分开：
   整篇新写的文件全算，只改了几个区间的既有文件**只算落在亲笔行区间内**的（区间由补丁全文
   在文件里"恰好命中 1 处"定位，命中数≠1 直接判废）。
6. **`--collect-only -q` 在本项目里不输出 `id::name`**：`pyproject` 的 addopts 带 `-v` ⇒ 收集结果打成
   `<Function test_…>` 树，按 `::test_` 数锁数得 0，把"6 条锁都在跑"判成"一根没跑"。
   现在显式 `-o addopts=` 并把两种形状都认（`::(test_…)` 与 `<Function (test_…)>`）后取并集。
7. **扫描器不扫自己**：判据 7e 的"本轮自己写的代码零 lint 违例"用的 `AUTHORED_WHOLE` 清单
   漏了**运行这条判据的那个文件本身**（`advance_baselines_r1.py`），于是它自己第 310 行的
   `E741 ambiguous variable name 'l'` 永远抓不到——正是"清单口径漏一个文件 ⇒ 手工改动无人认领"的复发。
   把自己加进清单后当场抓到并改名为 `x`。同一次收口里 `close_root_generic.py` 还有
   `E122`（我手拆 SQL 字符串时续行没缩进）与 black 要重排，两条都是这条门禁补上后**先红后绿**，
   不是放宽判据：修法是把文件补进被扫清单、把代码改干净，而不是删判据或降下限。
8. **收口 spec 的 needle 凭记忆写**：`close_r1_advance.json` 里我钉了 `neg_before_fix` 与 `red_locks`
   两个字符串，而盘上 JSON 的实际字段分别是 `matcher_control` 和**根本没有** `red_locks`
   （证红结果只 print 到 stdout，没进件）。通用驱动的先预检把这两条挡在收口之前
   （`REFUSE — 证据件预检未过`，一个服务端调用都没发）。修法不是改 needle 迁就件，
   而是让件补上应有的字段：`advance_lockproof_r1.py` 现在把每条回退树的
   `red_locks / mixed_cause_with_other / tree_result` 写进 JSON 并重跑取证。
   §七 ⑧ 的"16 叶全过"是在**补齐证据件之后**重跑的链，不是把钉不住的叶删掉。

## 七、门禁与自证

| 门禁 | 内容 | 状态 |
|---|---|---|
| ① | 9 条候选每条有文档行号 + CLI rc + 成对对照 | ✅ 全部复算，`advance_verify_r1.json` |
| ② | 剩余静默型缺口恰为 #3/#4（已入账 BUG-44/45） | ✅ |
| ③ | 账本可见条目头 + `bug_list` 回读两面都看得到 | ✅ |
| ④ | 完整树 6 绿；两条补口各自回退恰红自己且不混因 | ✅ |
| ⑤ | 文档原文例子（13 号 `let result =:` 块）过 CLI 且产物结构正确 | ✅ |
| ⑥ | 半径：本轮只动两个既有函数体，无新增语法单元 | ✅ |
| ⑦ | 三套基线不回落（{pf.get('passed')}≥{FLOOR}、47/47、25/25）+ 新锁被收集 6 条 + 本轮 lint 零违例 | ✅ |
| ⑧ | 16 叶 omega 链与根归档 | {leaf_claim} |

### 7.1 收口链上的被拒原文（逐字，一条不吞）

| 调用 | 任务 | 服务端原文 |
|---|---|---|
{refused_rows}

另外两条**开工期**被拒（不属于收口链，但同样逐字留档）：
`report_bug(summary?)` 的协议级拒绝原文见 §六 第 4 条。

call_log 最近 {rootc.get('call_log_rows') or 0} 行的工具分布：{tally}

## 八、转结（移交 R2）

1. **BUG-44/BUG-45 交 R2-修复**：都是"rc=0 但产物错"的静默型，同域（struct 方法签名与默认值脱糖），建议一起做。
2. **5 条显式未实现的声明面**（解析就报错，不占 bug 号，按推进半径转结）：

| # | 特性 | 判定 | CLI 原文 |
|---|---|---|---|
{left_table}

3. 上一轮遗留且本轮未触碰的裁决项原样结转：BUG-40/41/42/43、全仓 lint/black 规模、mypy 配置口径、
   模式约束不承重、`compare_elapsed < 5.0` 的墙钟时限。
4. 本轮把 `close_stage_generic.py` / `close_root_generic.py` 两份**通用**收口驱动落了地
   （叶子链与根上卷都改由 spec 驱动）：后面 14 个环节复用，减少"每轮手抄一份收口脚本"造成的口径漂移。

## 九、并发 lane 转述给我的主张（原文照录 + 我的实测，**不代签完成**）

对方要求"这条转达给 cypy-advancer 的反馈请写进你的终局报告"，并给了可标完成的结论。原文（逐字）：

> 已重新领取任务 T0a100.1.1。根因为通用词干 overlap + 大小写，与已上报的 Cypy 分支修复不同……
> 最终全量 pytest 回归：2052/2052 通过，golden 25/25，自研套件 47/47，未破坏任何已有测试。
> 现在补进仓库并挂回归锁

我在**收口前的主树**上打的实测（同一时刻、同一批文件，可复跑）：

| 主张 | 我的实测 | 结论 |
|---|---|---|
| "已入库/已落地" | 主树与 `E:/IDEProjects/AI/_cypy_head_baseline` 两棵树都查过：**都不存在 `cypyc/complete/`、`cypyc/fir/` 目录**；`FusedOp`、`fused_op`、`CompletionFixer` 三个符号在 `cypyc/` 与 `tests/` 下 grep 命中 **0 个文件** | 主树里看不到该实现 |
| "全量 pytest 2052/2052" | 本轮判据 7 的实测是 **{pf.get('passed')} passed**（`tests/` 100 个文件，HEAD 基线树 82 个文件） | 数量对不上，且我的树里没有多出的一批用例 |
| 谁的改动 | 打磨收口（本地 13:51:45）之后主树 `cypyc/**.py` 只有 **2 个**文件被动过：`cython_generator.py`、`parser.py`（就是我这两条补口） | 并发 lane 的产物**不在**本工作树 ⇒ 与我无混因 |

处置：按"验收要打到调用面"的口径，**我不替这条主张签"可标完成"**——它在盘上找不到载体（没有目录、没有可 import 的符号、没有对应用例），
只有对账不上的计数。转结给指挥官/人类裁决：要么给出该实现落在哪个树/哪个 commit 的路径，我按调用面重测后并入基线；
要么这条从"已落地"改记为"在另一条 lane 的临时树里，未入库"。**基线只升不降**：如果日后并入使 `tests/` 涨到 2052，
R2 的下限就从当日实测重新取，不沿用本轮的 {pf.get('passed')}。

```
[selfdrive-advance] round=R1 stage=推进 root=T0r54 landed=ADV-1,ADV-2 locks=6 filed=BUG-44,BUG-45 carry=declared-unimpl×5,BUG-44,BUG-45,r2-fixtures,peer-claim-unverified
```
"""
out = ROOT / REPORT_REL
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(md, encoding="utf-8", newline="\n")
print(
    json.dumps(
        {
            "report": REPORT_REL,
            "bytes": len(md.encode("utf-8")),
            "pytest_passed": pf.get("passed"),
            "landed": ["ADV-1", "ADV-2"],
            "gaps_left": gaps_left,
        },
        ensure_ascii=False,
    )
)
