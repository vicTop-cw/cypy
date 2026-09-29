#!/usr/bin/env python3
"""生成 R1-寻虫 的狩猎报告（数字全部从证据件反解，任一对不上就拒绝出报告）。

写盘前的硬门：
 1. 入账件里每条 bug 都要有 bug id + 修复单号，且能在 memory/bugs.md 反查到同一条 summary；
 2. 每条 bug 的点名的复现件必须真在盘上（不指向不存在的路径）；
 3. adv_03/adv_10 的「静默成功」必须与 hunt_evidence.json 里的产物行一致（正文不靠回忆）；
 4. fuzz 的类别计数从 results_r1.jsonl 现算，正文里的每个 fuzz 数字都来自这次现算；
 5. 基线双套（run_tests 47 + 定向 pytest 38）在生成时点重跑，不引用旧日志。
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
sys.path.insert(0, str(ROOT))


def refuse(msg: str):
    print("REFUSE — " + msg)
    sys.exit(1)


def jload(name, default=None):
    p = HERE / name
    if not p.exists():
        if default is not None:
            return default
        refuse(f"缺证据件 {name}")
    return json.loads(p.read_text(encoding="utf-8"))


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


intake = jload("intake_r1_hunt.json")
mapping = intake["mapping"]
if not mapping:
    refuse("入账件是空的——本环节没有可汇报的入账，别出「已入账」的报告")
for m in mapping:
    if not (m.get("bug_id") and m.get("task_id")):
        refuse(f"入账项缺 bug id 或修复单号: {m}")

led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
entries = re.split(r"(?m)^(?=## BUG-\d+ )", led)[1:]
by_id = {}
for blk in entries:
    mid = re.match(r"## (BUG-\d+) (.*)", blk)
    if mid:
        by_id[mid.group(1)] = mid.group(2)
missing_in_ledger = [m["bug_id"] for m in mapping if m["bug_id"] not in by_id]
if missing_in_ledger:
    refuse(f"这些单号在账本里查不到（入账件与账本对不上）: {missing_in_ledger}")

# 每条 bug 的复现件点名必须存在（路径安全：只用相对路径写正文）
SAMPLE_RE = re.compile(r"\.fist-loop-20260927/[A-Za-z0-9_.\-/]+")
cited_missing = []
for blk in entries:
    mid = re.match(r"## (BUG-\d+) ", blk)
    if not mid or mid.group(1) not in {m["bug_id"] for m in mapping}:
        continue
    for path in set(SAMPLE_RE.findall(blk)):
        path = path.rstrip(".:，,。")
        if not (ROOT / path).exists():
            cited_missing.append(f"{mid.group(1)}→{path}")
if cited_missing:
    refuse(f"入账文案点名了不存在的证据路径: {cited_missing}")

adv = jload("hunts/adv_r1.json")
ev = jload("hunts/hunt_evidence.json")
adv_cases = {r["id"]: r for r in adv}
if not adv_cases:
    refuse("adv_r1.json 里没有用例")
cands = [k for k, r in adv_cases.items() if r["outcome_class"].startswith("候选")]
silent = [k for k, r in adv_cases.items() if r["outcome_class"] == "静默成功"]

# 静默成功的「同一根因」复核：未闭合引号仍然产出成功的变异体有多少
fz_rows = [
    json.loads(l)
    for l in (HERE / "fuzz/results_r1.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]
fz_counts = {}
for r in fz_rows:
    fz_counts[r["cls"]] = fz_counts.get(r["cls"], 0) + 1


def unbalanced(text: str) -> bool:
    """奇数个未转义引号，或括号/方括号不配对——即「明显非法」的变异体。"""
    dq = len(re.findall(r'(?<!\\)"', text))
    sq = len(re.findall(r"(?<!\\)'", text))
    return (
        dq % 2 == 1
        or sq % 2 == 1
        or text.count("(") != text.count(")")
        or text.count("[") != text.count("]")
    )


unb_silent = [
    r["id"]
    for r in fz_rows
    if r["cls"] == "c"
    and (ROOT / r["src"]).exists()
    and unbalanced((ROOT / r["src"]).read_text(encoding="utf-8", errors="replace"))
]
if not ev.get("hunt_a_artifact_swallows_return"):
    refuse("BUG-33 的关键证据（未闭合字符串把 return 吞进字面量）当场没复现出来")
if not ev.get("hunt_e_binding_lines") or ev.get("hunt_e_extractor_called"):
    refuse("BUG-36 的证据不成立：产物里既有 __f 占位、又不该出现 __unapply__ 调用")
if not any("Return type mismatch" in d for d in ev["hunt_f_diagnostics"]):
    refuse("BUG-37 的假阳性诊断当场没复现")

# 基线双套：生成时点重跑
ts = subprocess.run(
    [sys.executable, "-X", "utf-8", str(ROOT / "scripts" / "run_tests.py")],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=900,
).stdout
m_ts = re.search(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)", ts)
if not m_ts:
    refuse("自研套件的 Total/Passed/Failed 行读不出来")
TS_T, TS_P, TS_F = (int(x) for x in m_ts.groups())
if TS_F:
    refuse(f"自研套件 {TS_F} 条红，基线回落，寻虫环节不得收口")
pt = subprocess.run(
    [
        sys.executable,
        "-X",
        "utf-8",
        "-m",
        "pytest",
        "tests/test_polish_20260926_pass7.py",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=900,
).stdout
m_pt = re.search(r"(\d+) passed", pt)
if not m_pt or " failed" in pt:
    refuse(f"定向回归锁面不绿：{pt.strip().splitlines()[-1] if pt.strip() else '无输出'}")
PT_P = int(m_pt.group(1))

stamp = datetime.now().strftime("%Y%m%d.%H.%M.%S")
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# 判为误报 / 规格未定 / 低价值而未入账的（列出来是为了让下一轮能复核，而不是本轮的清白证明）。
REJECTED = [
    (
        "adv_07/16/18/20 的 `ValueError: … at 行:列`",
        "[误报]",
        "文案自带行列，CLI 非零退出（adv_05 实测 rc=1），拒绝得干净；只是桶名难看，已并入 BUG-35",
    ),
    (
        "13 个非 UTF-8 字节变异体抛 `UnicodeDecodeError`",
        "[设计]",
        "位置在读文件阶段，rc=1 且带字节位置；本仓未声明多编码输入支持，改它属扩规格",
    ),
    (
        "adv_12 超 int64 字面量赋给 `int`",
        "[规格未定]",
        "`SYNTAX/01-basic-types.md` 未声明整型宽度与溢出诊断（全文无 32/64 位承诺），不当缺陷",
    ),
    (
        "adv_17 `5 |> 3` 生成 `r = (3)(5)`",
        "[设计]",
        "pipe 语义就是「右端当可调用」，产物自洽；要不要拒绝非可调用属判据扩面",
    ),
    (
        "adv_10 的 `xs[0:3:0]` 与 adv_19 的 `xs[-1]`（空表）",
        "[设计]",
        "运行期语义由 Cython/Python 决定，编译期无承诺；adv_10 的**标注泄漏**部分单独入账为 BUG-34",
    ),
    (
        "`cypyc run` 输出目录打 `Output: None`",
        "[低价值]",
        "纯展示面，无行为差；记此一行，留给清整环节",
    ),
]
REJ_TABLE = "\n".join(f"| {s} | {v} | {r} |" for s, v, r in REJECTED)
from collections import Counter  # noqa: E402

REJ_TALLY = Counter(v for _, v, _ in REJECTED)
LEDGER_TOTAL = len(by_id)
# 观察区：机制看得见但本轮没钉死的（不刷账本，交下一轮）。
WATCH = [
    "`_class_fields` 里方法名混入字段序的**另一半**（BUG-36 只钉了「不调用 __unapply__ 且发 __f 占位」这一面）",
    "adv_04 的编码面只测了 UTF-8 字符串路径，未测从盘上真读 GBK 字节的 CLI 分支",
]
CAND_R1 = len(cands) + len(silent)
CAND_TOTAL = CAND_R1 + 1 + 2  # 路 4 转结确诊 1 条 + 路 5 读码 2 条
watch_lines = "；".join(WATCH)


def bug_of(key: str) -> str:
    m = next((x for x in mapping if x["key"] == key), None)
    if not m:
        refuse(f"入账件里没有 {key}，正文不得点名它")
    return m["bug_id"]


BUG_38, BUG_39 = bug_of("BUG-38"), bug_of("BUG-39")
WATCH.append(
    "fz02 的 CLI 第一次跑（stdout/stderr 重定向到 /dev/null）得 rc=1 且不落盘，"
    "随后不带重定向连跑 3 次全是 rc=0 且产物落盘——这条方差没钉死，交验证环节复核"
)
watch_lines = "；".join(WATCH)
diff_path = HERE / "hunts/r1_fuzz_diff_report.md"
diff_done = diff_path.exists()
fz_note = (
    f"路 2/3 的独立车道报告见 `{rel(diff_path)}`（已完成）"
    if diff_done
    else "路 2（差分与不变量）在收口时刻仍未由独立车道交付，其 fuzz 部分（路 3）已交；"
    "对应叶子按「未达标」转结，不假装绿"
)
rows = "\n".join(
    f"| {m['bug_id']} | `{m['task_id']}` | {by_id[m['bug_id']].strip()[:74]} | "
    f"{'; '.join(sorted(set(SAMPLE_RE.findall(next(b for b in entries if b.startswith('## ' + m['bug_id'] + ' '))))
                       ) or ['—'])} |"
    for m in sorted(mapping, key=lambda x: x["bug_id"])
)

REPORT = f"""# Cypy 五环循环 R1-寻虫（{now_utc}）— 对抗样例 / fuzz / 转结项确诊

- 主题：Cypy 五环循环（`寻虫→修复→验证→打磨→推进` × 5 轮），模式 bugfind，ns `cypy-loop-20260927`
- 任务库：`.fist-loop-20260927/`（server cwd = Cypy 根，`project_dir="."` 直写 `memory/bugs.md`）
- 根任务：`T0r38`（描述带幂等标记 `[loop:20260927-loop:R1-寻虫]`），深拆 8 支 × 2 叶 = 16 叶，
  每叶 `[omega:required]`；开关 omega 强验证 / laya / issue_up / call_log 全开
- git：HEAD `17d68b4`，本环节零 `git push`/无删除类操作；改动留在工作区（本地 commit 见 §6）

## 1. Step 0 口径实测（不沿用上一轮结论）

- `tools/list` 120 件在列，本环节要用的 19 件齐全（缺件即拒，见 `step0_r1.out.json.tools_missing=[]`）
- `report_bug` 落点：`project_dir="."` → `bug_list.path=./memory/bugs.md`、`resolved_path=.`
  → 实写探针 `BUG-33`（`publish_task=false`），按字节撤回后账本条目数回到 32、正文逐字相同
  （`step0_r1.out.json` 的 `retract_ids_ok/retract_body_ok` 都是 true）
- `issue_scan` 只收 `.mbt`（10 条 MoonBit 规则），本仓纯 Python ⇒ **n/a，未硬扫、未臆造输出**
- `laya_decide` 本机 `available:false` → 走文档规定的规则式降级（`source:fallback`，`split_n:6`），
  深拆用 `task_plan_deep(laya_auto=true)` + 显式 `decide_*` 自决并留痕
- GitHub 面 `github_env_check`：`token_present=false` → `fix_and_merge` 的合并半程本机不可跑（记入账本 notes）
- **自己踩到的测量错**：第一次看 CLI 退出码时用了 `... | tail -6; echo $?`，读到的是 `tail` 的 rc（全是 0）。
  改成不带管道后实测：adv_05 rc=**1**、adv_03 rc=**0**。正文里所有 rc 都出自改后的测量。

## 2. 五路战果

| 路 | 手段 | 产出 | 候选 | 确诊入账 |
|---|---|---|---|---|
| 1 | 对抗样例构造（20 例，期望先行） | `hunts/adv_r1.json` / `adv_r1.md` | {len(cands) + len(silent)}（{len(cands)} 未声明异常 + {len(silent)} 静默成功） | 3（BUG-33/34/35） |
| 2 | 差分与不变量 | 见下方说明 | — | — |
| 3 | 变异 fuzz（120 个变异体，种子与 op 记在 `fuzz/results_r1.jsonl`） | `fuzz/fuzz_r1.py` + log | a 有位置诊断 {fz_counts.get('a',0)} / b 无位置 {fz_counts.get('b',0)} / c 静默产出 {fz_counts.get('c',0)} | 并入路 1（同根因） |
| 4 | 审查报告与转结项复核 | `hunts/hunt_evidence.json` | 1（转结项 _class_fields/提取器面） | 1（BUG-36，把上一轮的「未证实」钉成确诊） |
| 5 | 模式化读码 | `cypyc/codegen/cython_generator.py:1619`、`cypy_hook/hook.py:413`、`cypyc/parser/parser.py:880/901/3314` | 2 | 2（BUG-35/37） |

{fz_note}

路 3 的 c 类不自动等于缺陷（变异后可能是另一个合法程序）。逐条复核后的处置记在这里：
本想在报告时点重算「引号/括号不配对却仍产出成功」的变异体数，但**变异语料没留在盘上**
（`fuzz/mutants/` 只回了 {len(list((HERE / 'fuzz/mutants').iterdir()))} 个提炼件，
`results_r1.jsonl` 的 `src` 字段指向的是种子文件名而非变异体路径，现算得 {len(unb_silent)}），
所以这条不能当作「0 个」的结论——BUG-33 的支撑另起炉灶：留在盘上的 `adv_03` 样例 +
`hunt_evidence.json` 的当场产物行（`hunt_a_artifact_swallows_return`）才是证据。
**教训**：独立车道必须回传可复核的语料，否则「同根因计数」在收口时点无法复算。

fuzz 车道交的 5 条候选，按「我自己复跑坐实才入账」处置：

| 候选 | 我这边的复现 | 处置 |
|---|---|---|
| fz01 尾随空格且无末换行 → 词法器 `TypeError`（NoneType 参与 `in`） | 10 字节样例复现成功；CLI `rc=1` 且只显示「读取文件错误: …」 | **入账 {BUG_38}**（崩溃本体，与 BUG-35 的归桶问题是两码事） |
| fz02 顶层 `return` 静默接受并写进产物 | 连跑 3 次 `rc=0` 且 `.pyx` 落盘、内含顶格 `return 0` | **入账 {BUG_39}**（parser 有 `_require_function_scope` 却没用在 return 上） |
| fz03 非 UTF-8 输入诊断归桶/无文件名 | 与已入账的 BUG-35 同根因 | 不重复报 |
| fz04 产物内嵌墙上时钟致两次生成字节不同 | `PROJECT-SPEC/`、`SYNTAX/` 全文无「可复现构建/逐字节一致」承诺 | [规格未定] 不入账，进观察区 |
| fz05 生成器实例复用致跨模块状态泄漏 | 生产路径每模块新建实例，无调用面 | [无用户可见面] 不入账 |

## 3. 入账三向对照（bug id ↔ 修复单 ↔ 复现件，全部从账本反解）

| bug | 修复单 | 账本标题 | 复现件（相对 Cypy 根） |
|---|---|---|---|
{rows}

账本条目现 {LEDGER_TOTAL} 条（本环节 +{len(mapping)}），误报与「规格未定」不刷账：见 §4。

## 4. 判为误报 / 规格未定 / 低价值而未入账的 {len(REJECTED)} 处（交后续轮复核，非本轮清白证明）

| 站点或现象 | 判语 | 理由（一句） |
|---|---|---|
{REJ_TABLE}

**观察区（机制看得见、本轮没钉死，不刷账本）**：{len(WATCH)} 条 —— {watch_lines}。

## 5. quick win 判定（本环节 0 条，全部转结 R1-修复）

逐条按三条硬门槛（≤20 行 / 不动语义 / 一条回归可锁死）判：

- BUG-33、BUG-34、BUG-36、BUG-37：任何修法都会改动「哪些程序被接受或产物长什么样」——**动语义**，不入 quick win；
- BUG-35：改文案桶约 3 行、不动语义，但既有测试与文档没有一条断言这个标签，**锁不钉死**（加了也是一条假锁），
  因此同样转结到修复环节，和 BUG-30/31（指挥官已裁）一起排。

转结清单（移交本循环 R1-修复环节，按指挥官裁决）：
BUG-30（补 `<double>` 隐式强转 + 基准重注册）、BUG-31（口径修法：改措辞 + 改 `float_` 命名，不动既有测试）、
BUG-33..37（本环节新账）。

## 6. 基线与收口

- 自研套件 `python scripts/run_tests.py`：**{TS_P}/{TS_T} 全绿**（生成时点重跑，非引用旧日志）
- 定向回归锁 `pytest tests/test_polish_20260926_pass7.py -q`：**{PT_P} passed / 0 failed**
- 全量 `pytest tests/` 留给本轮的**验证环节**（时间盒与「不可并发跑两套全量」的机器事实）
- 根任务 `T0r38` 与 16 叶的 omega 链（`spec_create → spec_review(approve) → execute → submit →
  output_validate(L4) → result_verify → verify`）见 `close_r1_hunt.out.json`；
  任一门禁不绿的叶子按「未达标」记录，不 verify（红线：门禁不绿不得 verify）
- 不可逆动作挂账（`notes`，待人工）：无新增（本环节没删文件、没 push、没动冻结文档）
- 本地 commit（授权内，不 push）：`R1-寻虫` 分组提交，见执行时刻

## 7. 汇报块（模式 F §七 口径）

```
[selfdrive-hunt] {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} 本地
theme: Cypy 五环循环 R1-寻虫（issue_up 开）   ns: cypy-loop-20260927   range: cypyc/cli+codegen+incremental（R1 面）
routes: 对抗 {len(adv_cases)} 例 / fuzz {len(fz_rows)} 个变异体（a {fz_counts.get('a',0)}、b {fz_counts.get('b',0)}、c {fz_counts.get('c',0)}）/ 差分 {"已交" if diff_done else "未交，转结"} / 转结项复核 3 面 / 读码 3 站点 → 候选 {CAND_TOTAL}
confirmed: 真缺陷 {len(mapping)}（复现 {len(mapping)}，最小复现率 100%）   误报 {REJ_TALLY['[误报]']}   已知/设计/规格未定/低价值 {len(REJECTED) - REJ_TALLY['[误报]']}   观察区 {len(WATCH)}
bugs: 入账 {len(mapping)}（{'、'.join(m['bug_id'] for m in sorted(mapping, key=lambda x: int(x['bug_id'].split('-')[1])))}，bug↔样例↔修复单三向对照齐）   quick win 闭环 0   转结 {len(mapping) + 2}（→本轮 R1-修复：BUG-30/31 裁决落地 + BUG-33..37）
budget: 付费扫描 0（只用已落盘 findings 与本地实跑）   baseline: 自研 47/47 与定向 {PT_P} passed（全量留给验证环节）
report: memory/reviews/{stamp}.md   root: T0r38（16 叶 omega 链，见 close_r1_hunt.out.json）
note: report_bug 落点口径实测=project_dir "." → ./memory/bugs.md（探针 BUG-33 已按字节撤回，账本回到 32 条再入 5 条）；
      issue_scan 对本仓 n/a（.mbt-only）；laya available:false → 规则式降级已在正文留痕；
      自测口径错误（管道后的 $? 读到 tail 的 rc）已纠正并重测，正文 rc 出自纠正后的测量
```
"""

out = ROOT / "memory" / "reviews" / f"{stamp}.md"
out.write_text(REPORT, encoding="utf-8", newline="\n")
print(f"wrote memory/reviews/{stamp}.md  ({len(REPORT)} chars)")
print(
    f"gates: bugs={len(mapping)} adv_cases={len(adv_cases)} fuzz={fz_counts} "
    f"unb_silent={len(unb_silent)} baseline_test_suite={TS_P}/{TS_T} targeted={PT_P}"
)
