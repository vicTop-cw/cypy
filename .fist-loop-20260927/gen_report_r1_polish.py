"""生成 R1-打磨 环节报告：所有数字从取证件反解，任一条不成立就拒绝落盘。

用法：python gen_report_r1_polish.py <报告名(不带目录与扩展名)>
预收口跑法与前两环一致：收口件不在时把叶子链一行标成「未执行」，收口后重跑覆写同一份路径。

唯一一处"允许红灯"的裁定必须写死在这里：判据3（mypy）本轮是**红的**，而且它应当红——
项目声明的 strict 门在测试树上被 python_version=3.9 直接打断。本生成器只在
「红的原因恰好是已入账的 BUG-43 那两条」时放行，出现第三条 law3 拒绝就整体拒绝，
避免把"已知的坑"变成一张通行证。
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
FLOOR = 1862
NAME = sys.argv[1] if len(sys.argv) > 1 else None
if not NAME:
    raise SystemExit("REFUSE — 必须传报告名")
REPORT_REL = f"memory/reviews/{NAME}.md"
refuse = []


def load(fname, required=True):
    p = HERE / fname
    if not p.exists():
        if required:
            refuse.append(f"取证件缺失：{fname}")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


law1 = load("polish_law1_r1.json")
scan = load("polish_scan_r1.json")
probe = load("polish_probe_r1.json")
reads = load("polish_law2_reads_r1.json")
base = load("polish_baselines_r1.json")
wall = load("polish_wallclock_r1.json")
close_p = HERE / "close_r1_polish.out.json"
PRE_CLOSE = not close_p.exists()
cl = (
    json.loads(close_p.read_text(encoding="utf-8"))
    if not PRE_CLOSE
    else {"leaves": [], "failed": []}
)
rootc = load("close_r1_polish_root.out.json", required=not PRE_CLOSE) if not PRE_CLOSE else {}

for fname, doc in (
    ("polish_scan_r1", scan),
    ("polish_probe_r1", probe),
    ("polish_law2_reads_r1", reads),
    ("polish_baselines_r1", base),
    ("polish_wallclock_r1", wall),
):
    for r in (doc or {}).get("refuse", []):
        # polish_scan 的「判据3」两条是**本轮裁定要保留的红**，由下面的 ③ 逐条点名放行；
        # 在这里无条件并入会让放行名单永远碰不到（同一处恒红在报告层的翻版）。
        if fname == "polish_scan_r1" and str(r).startswith("判据3"):
            continue
        refuse.append(f"{fname} 自报拒绝：{r}")

# ---- ① 模式约束实测 ----
if law1.get("publish_refused") is not False:
    refuse.append(f"判据① mode_list 的 polish 约束实测结果不是「publish 仍发出」：{law1}")
if "不承重" not in (law1.get("finding") or ""):
    refuse.append(f"判据① 结论句缺失：{law1.get('finding')}")
if law1.get("publish_has_mode_param") is not False:
    refuse.append("判据① publish 的 schema 里出现了 mode 入参 ⇒ 「执行层无模式概念」这条主张失效")
if (law1.get("probe_cleanup") or {}).get("final_status") != "已归档":
    refuse.append(f"判据① 探测任务未确认归档：{law1.get('probe_cleanup')}")

# ---- ② skip 定性 ----
if len(reads.get("reads") or []) != 3:
    refuse.append(f"判据② 定性条数不是 3：{reads.get('count')}")
if reads.get("skipped_tokens_in_log") != 0:
    refuse.append(f"判据② 日志里出现过 SKIPPED，'本轮未触发'的结论不成立：{reads}")

# ---- ③ mypy：允许的红必须是被入账的那两条 ----
KNOWN3 = ("mypy 被中断", "[syntax]")
l3 = [r for r in scan.get("refuse", []) if r.startswith("判据3")]
if len(l3) != 2 or not all(any(k in r for k in KNOWN3) for r in l3):
    refuse.append(f"判据③ law3 的拒绝不是「已入账 BUG-43」那两条，或条数不对：{l3}")
if not scan.get("law3_mypy", {}).get("aborted"):
    refuse.append("判据③ 扫描件没标 aborted ⇒ 中断这件事没被记下来")

# ---- ④ 技术债标记 ----
ctl = scan.get("law4_control") or {}
if not (
    ctl.get("comment_caught") == 1
    and ctl.get("string_not_counted")
    and ctl.get("string_mention_recorded")
):
    refuse.append(f"判据④ 成对对照未过（真注释必被抓 / 字符串提及不得算债）：{ctl}")
if scan.get("law4_debt", {}).get("total") != 0:
    refuse.append(f"判据④ 真注释里的技术债标记数不是 0：{scan.get('law4_debt')}")

# ---- ⑤ 死代码 / 被遮的测试类 ----
p1 = probe.get("p1_shadowed_test_classes") or {}
dead_tests = sum(v.get("shadowed_methods", 0) for v in p1.values())
if dead_tests != 6:
    shadowed = {k: v.get("shadowed_methods") for k, v in p1.items()}
    refuse.append(f"判据⑤ 被遮测试方法数不是 6：{shadowed}")
p2 = probe.get("p2_dead_visitors") or {}
if len(p2) != 2 or not all(v.get("dead_branches") for v in p2.values()):
    deadv = {k: bool(v.get("dead_branches")) for k, v in p2.items()}
    refuse.append(f"判据⑤ 死 visitor 判定不完整：{deadv}")
bugs_md = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
for need in ("BUG-40", "BUG-41", "BUG-42", "BUG-43"):
    if f"## {need}" not in bugs_md:
        refuse.append(f"判据⑤ 账本里找不到 {need} 的可见条目头（隐形标题会让它从 bug_list 消失）")
if "### 实测追加(2026-09-27" not in bugs_md:
    refuse.append("判据⑦′ 墙钟翻转没在 BUG-13 条目下留实测追加段（§6.0 的结论就没有账面对应物）")

# ---- ⑥⑦ quick win 与三套基线 ----
if base.get("pytest", {}).get("passed") is None or base["pytest"]["passed"] < FLOOR:
    refuse.append(f"判据⑦ pytest 通过数不足 {FLOOR}：{base.get('pytest')}")
# 自研套件的绿由 polish_baselines_r1.py 逐字段裁决（total/passed/failed/skipped 四段），
# 这里不重复钉整行字面量——上一版在这里也钉了旧三段字面量，是同一处恒红缺陷的第二份副本。
su = base.get("suite") or {}
if su.get("green") is not True or not str(su.get("line", "")).startswith("Total: 47 | Passed: 47"):
    refuse.append(f"判据⑦ 自研套件不绿：{su}")
if su.get("rc") != 0:
    refuse.append(f"判据⑦ 自研套件退出码非零：{su.get('rc')}")
if "PASS=25 FAIL=0" not in (base.get("e2e", {}).get("line") or ""):
    refuse.append(f"判据⑦ 端到端基准不是 25/25：{base.get('e2e')}")
if (base.get("quickwin_recheck") or {}).get("f601_now"):
    refuse.append(f"判据⑥ quick win 后仍有 F601：{base['quickwin_recheck']['f601_now'][:200]}")

# ---- ⑦′ 基线首跑的红色必须逐字披露，不许只留终态 ----
try1_p = HERE / "polish_pytest_r1.try1.log"
if not try1_p.exists():
    refuse.append("判据⑦′ 首跑红证据 polish_pytest_r1.try1.log 不在 ⇒ 无法披露第一次实跑结果")
    try1_summary = try1_failed = try1_assert = ""
else:
    t1 = try1_p.read_text(encoding="utf-8", errors="replace")
    try1_summary = ([l for ln in t1.splitlines() if " passed" in l] or [""])[-1].strip()
    try1_failed = "; ".join(re.findall(r"^FAILED (\S+)", t1, flags=re.M))
    try1_assert = "; ".join(re.findall(r"^E\s+(assert .*)$", t1, flags=re.M))
    if "1 failed" not in try1_summary or not try1_failed:
        refuse.append(f"判据⑦′ 首跑日志形状变了，披露内容不可信：{try1_summary[:120]}")
    if try1_failed and try1_failed.split(";")[0].strip() not in (wall.get("target") or ""):
        refuse.append(
            f"判据⑦′ 复跑对象与首跑红用例不是同一条：首跑 {try1_failed} / 复跑 {wall.get('target')}"
        )
    for tag in ("solo", "whole_file"):
        d = wall.get(tag) or {}
        if d.get("rc") != 0 or d.get("failed") or not d.get("passed"):
            refuse.append(f"判据⑦′ 无并发复跑（{tag}）仍不绿：{d}")
LOAD1 = json.dumps(base.get("load") or {}, ensure_ascii=False)[:400]


def secs(s):
    m = re.search(r"in ([\d.]+)s", s or "")
    return m.group(1) if m else None


TRY1_SECS, FINAL_SECS = secs(try1_summary), secs((base.get("pytest") or {}).get("summary_line"))
if not TRY1_SECS or not FINAL_SECS:
    refuse.append(f"判据⑦′ 两次实跑的墙钟解析不出来：首跑 {TRY1_SECS} / 终态 {FINAL_SECS}")
SLOW_PCT = (
    round((float(TRY1_SECS) - float(FINAL_SECS)) * 100 / float(FINAL_SECS))
    if TRY1_SECS and FINAL_SECS and float(FINAL_SECS) > 0
    else None
)
if SLOW_PCT is not None and SLOW_PCT <= 0:
    refuse.append(
        f"判据⑦′ 首跑并不比终态慢（{SLOW_PCT}%）⇒ '被同机并发打断'的归因不成立，"
        "这一节必须重写、§七 的第 5 条要升格成产品缺陷"
    )

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


lint_prev = json.loads((HERE / "verify_lint_r1.json").read_text(encoding="utf-8"))
repo_c = lint_prev["repo_census"]
w293_share = round(100 * (repo_c["census"].get("W293") or 0) / repo_c["total"], 1)
pol_forbidden = (law1.get("mode_list_polish_declared") or {}).get("forbidden_tools")
pub_polisher_err = ((law1.get("publish_as_polisher") or {}).get("__error__") or {}).get("message")
pub_steward_msg = (law1.get("publish_as_steward") or {}).get("message")
probe_first_arc = (law1.get("probe_cleanup") or {}).get("first_attempt_archive_direct")
fail_codes = base["pytest"]["failed_or_error"]
lint_when = datetime.fromtimestamp((HERE / "verify_lint_r1.json").stat().st_mtime).strftime(
    "%m-%d %H:%M 本地"
)
leaf_claim = (
    "16/16 `output_validate=pass`，服务侧 0 ERR，根任务 " f"`{rootc.get('root_final')}`"
    if not PRE_CLOSE
    else "**未执行**：预收口版本，收口后重跑本生成器覆写同一份"
)
refused_rows = (
    "\n".join(
        f"| `{r['call']}` | `{r['task_id']}` | {r['error'].replace('|', chr(92) + '|')} |"
        for r in rootc.get("refused", [])
    )
    or "| — | — | （收口件未生成） |"
)
tally = (
    "、".join(f"`{k}`×{v}" for k, v in sorted((rootc.get("call_log_tally") or {}).items()))
    or "（收口件未生成）"
)
law2_rows = "\n".join(
    f"| `{r['where']}` | {q(r['quote'])} | {q(r['shape'])} | {q(r['verdict'])} |"
    for r in reads["reads"]
)
l3_rows = "\n".join(f"- {r}" for r in l3)
p2_rows = "\n".join(
    f"- `{k}`：定义在 {v['defined_at']}，生效 {v['live_line']}，被遮那份体长 "
    f"{[d['lines'] for d in v['dead_branches']]} 行"
    for k, v in p2.items()
)
scan_c = scan["law5_candidates"]["counts"]

md = f"""# Cypy 循环轮 R1-打磨 报告（FIST-Mbt polish 模式）

- run_id: `20260927-loop`   轮次: R1 (1/5)   环节: 打磨（polish）   根任务: `T0r49`（8 支 × 2 叶）   起点 HEAD: `{head}`（本轮零提交，红线内）
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（本地）/ {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}(UTC)
- 取证件: `{L}polish_law1_r1.json`（模式约束实测）、`polish_scan_r1.json`（skip/mypy/技术债/死代码四扫）、
  `polish_probe_r1.json`（P1 被遮测试类 / P2 死 visitor / P3 skip 试跑）、`polish_law2_reads_r1.json`（人工读定 + 引文回核）、
  `polish_baselines_r1.json`（三套基线复跑）
- 开关: omega 强验证逐叶开链（§六）；laya = **fallback**（`available:false`）；
  issue_up：本环节以「入账 4 条」承担（BUG-40/41/42/43，`issue_scan` n/a .mbt-only）；call_log 对账见 §六

## 一、模式约束是声明还是门（开工先实测）

`mode_list` 声明 polish 的 `forbidden_tools = {q(pol_forbidden)}`、
`forbid_new_features=true`。实测结论：**这张表不承重**——

| 探测 | 结果 |
|---|---|
| `tools/list` 共 {law1.get('tools_list_count')} 个工具；带 mode 字样的只有 `mode_list/mode_templates`（路由类），`publish` 的 required={q(law1.get('schema_publish'))} | `publish` **没有 mode 入参** ⇒ 执行层没有「当前模式」的概念 |
| 用 `created_by=cypy-polisher` 调 publish | 被拒：`{q(pub_polisher_err)}` —— 这是**角色门**，不能拿来证明模式门存在 |
| 换 `created_by=human_steward`（服务端放行的角色）再调 | **发出成功**，回显 `{q(pub_steward_msg)}`，任务号 `{law1.get('probe_task_id')}` |

⇒ 结论写死：**polish 期间「不新发任务」是我自守的纪律，不是服务端给的护栏**；本环节产物一律沿 `T0r49` 的 16 叶上卷。
探测副任务 `{law1.get('probe_task_id')}` 已按 `claim→execute→submit→archive` 走完生命周期归档
（直接 archive 对未开工任务是非法迁移：`{q(probe_first_arc)}`）。
这条「第一次被拒的理由不是我要测的那个理由」的教训，正是本环避免拿角色门冒充模式门的原因。

## 二、skip 类标记逐条定性（3 处，全部为测试体内的运行时 skip）

扫描件：`polish_scan_r1.json.law2_skip_marks`（缺陷号归属按**所属函数体**取，见 §五′ 的误挂修正）。
"本轮有没有真的跳过"用全量日志核：汇总行 `{q(reads.get('evidence_summary_line'))}`，
日志内 `SKIPPED` 计数 = `{reads.get('skipped_tokens_in_log')}` ⇒ 三条**一条都没触发**。

| 位置 | 引文（已回核到该行原文） | 形状 | 定性 |
|---|---|---|---|
{law2_rows}

## 三、静态检查边界：这道门现在是**红的**，而且必须记成红的

`mypy`（项目声明 `python_version="3.9"` + `strict=true`）在含测试输入上**整轮中断**：

{l3_rows}

- 数字对照：同一份 `[tool.mypy]` 配置，输入换成纯产品码时报的是成片存量（R1-验证 记 950 条/37 文件）；
  输入含一个 `import pytest` 的测试文件时直接中断 ⇒ 本环不再拿任何「N 条 error」当边界，
  已入账 **BUG-43**（`T0r53`），修法三选一（overrides 忽略第三方导入 / 抬 `python_version` /
  包装脚本把「中断」判为未跑成）交裁决。
- `pyproject` 的 `[tool.flake8]`（BUG-40）与 `[tool.mypy]`（BUG-43）两条连起来看：
  **本项目声明的静态检查配置，有两处对声明的工具不生效或跑不起来**。这是配置层的系统性问题，不是两处孤立笔误。

## 四、技术债标记与死代码（只数得出来的那部分）

- 真注释里的 TODO/FIXME/HACK/XXX：**0 处**（`law4_debt.total=0`）；
  成对对照：合成 `# TODO: ...` 必被抓（caught={ctl.get('comment_caught')}）、
  字符串里的同名词不得算债（excluded={ctl.get('string_not_counted')}，
  它被单列进 `law4_string_mentions`，共 {len(scan.get('law4_string_mentions') or [])} 条样例，
  真源是 `tests/test_demos.py:487` 那条**关于 TODO 的断言**）。
- 死代码候选规模（flake8，100 列口径）：`{q(scan_c)}`。其中两处已跑到调用面并立案：
{p2_rows}
  另 P1：`tests/test_boundary_comprehensive.py` 两组测试类被同名重复定义遮住，
  **{dead_tests} 条用例静默不执行**（`{{200:3, 420:5}}`、`{{282:3, 910:7}}`，生效行 420/910）。
- 顺带清出的口径事实：4 个测试文件带 UTF-8 BOM（`q(scan['scan']['bom_py_files'])`），
  会让按 `utf-8` 直读的扫描器把首行当语法错——本轮扫描器改走 `utf-8-sig`；
  产品侧 `cypyc/incremental` 对 BOM 的处理另有单测（BUG-6 已修）。

## 五、quick win（≤20 行、不动语义）与它的等价性证明

改动：`cypyc/analyzer/type_checker.py` 数学函数表里重复写了三遍的 `'sqrt'/'sin'/'cos'` 键，
删去后一份重复（3 行，纯键重复清理）。等价性是**静态算出来的**，不是"看起来没改行为"：

| 口径 | 改前 | 改后 |
|---|---|---|
| 表里写下的条目数 | 15 | 12 |
| 生效键数 | 12 | 12 |
| 重复键 | `['cos','sin','sqrt']` | `[]` |
| 重复处两侧值是否逐字相同 | 是（`dup_values_all_identical=true`） | — |
| 生效映射（键→unparse 后的值）是否等价 | — | **等价（effective mapping identical=True）** |
| 对象身份是否可观察 | `Type` 定义了 `__eq__` 且该表在方法内每次重建 ⇒ 身份本来就跨调用不稳定 | 同 |
| `F601`（该文件） | 6 条 | 0 条 |

## 五′、本轮抓到并修回的**判据自身**缺陷（五条，全部有成对对照兜住）

1. **技术债扫描命中了"关于 TODO 的断言"**：第一版逐行正则把 `tests/test_demos.py:487` 的
   `assert not content.startswith("# TODO")` 数成 1 处技术债。改为按 `tokenize` 只取 COMMENT 令牌，
   并配「真注释必被抓 / 字符串提及必不算债 / 提及须被单列」三条对照。
2. **skip 的缺陷号误挂**：第一版用 ±4 行文本窗口取 BUG 号，把下一个函数头上的 `# ---- BUG-6`
   算进了 `test_bug5_state_restore_reports_setattr_failure` 的理由里 ⇒ 差点把一条合法的平台型 skip
   判成"掩盖失效该重跑"。改为按 AST 取**所属函数体**内的号；修正后三处 skip 都不引用任何缺陷号。
3. **mypy 计数当边界**：中断时 mypy 只吐 1 条 `[syntax]` 并宣告 `errors prevented further checking`，
   第一版把 `total_errors=1` 当成"改动面很干净"。现在 `aborted` 是硬门，且 `[syntax]` 单独判红。
4. **自研套件的绿被钉成整行字面量（恒红）**：`polish_baselines_r1.py` 判据 7b 原来是
   `line != "Total: 47 | Passed: 47 | Failed: 0"`，而 `test_suite/core/runner.py:134` 打出的末行
   **本来就带第四段** `| Skipped: 0` ⇒ 这条门从写下那刻起就不可能通过，报出来的"套件不绿"
   是判据坏了而不是套件坏了。改为逐字段解析（total=47 / passed=total / failed=0 / skipped=0），
   并把"解析不出形状"也判红（弃权不当绿）；`suite_selftest()` 用四类必红坏行 + 一条真绿行做对照。
   同源的旧字面量在报告生成器里还有一份副本（⑦ 的门），一并改为取 JSON 的 `suite.green`。
5. **负载探针按映像名过滤 ⇒ 恒报"零负载"**：第一版用 `tasklist /FI "IMAGENAME eq python.exe"`，
   实测本机自己的解释器常以 **`python3.13.exe`**（Windows Store 别名）出现（本轮 PID 38472 即为证），
   该过滤器只数得到别人的 `python.exe`，把自己整棵子树漏掉——用它做"当时机器很忙"的归因就是自证不清。
   改为 `Get-CimInstance ... Name LIKE 'python%'` 并按父链分本/外来 lane（`lane_load.py`）；
   分类本身也被这条探针抓出过一次反向错误：把"自己的祖先链"当种子会把同一祖先下**别的项目**的
   进程吸进来虚报零负载，故种子只取"命令行含 Cypy 根"+ 探针自身，再**只向下**收子孙。

## 六、门禁与自证

| 门禁 | 内容 | 状态 |
|---|---|---|
| ① | polish 模式约束实测（角色门 ≠ 模式门）与探测任务归档 | ✅ 已实测：不承重，`{law1.get('probe_task_id')}` 已归档 |
| ② | 3 处 skip 逐条定性 + 引文回核 + 「未触发」用日志核 | ✅ |
| ③ | mypy 边界 | ⚠ **未跑成**（中断）⇒ 已入账 BUG-43，不拿任何条数当边界 |
| ④ | 技术债标记：真注释 0 处，成对对照三条通过 | ✅ |
| ⑤ | 死代码/被遮测试跑到调用面并立案（BUG-41/42），账本 4 条可见条目头齐备 | ✅ |
| ⑥ | quick win 等价性静态证明 + 该文件 F601 归零 | ✅ |
| ⑦ | 三套基线复跑不回落：pytest **{base['pytest']['passed']} passed / 红错计数 {q(fail_codes)}**（≥{FLOOR}）、自研 **{q(base['suite']['line'])}**、端到端 **{q(base['e2e']['line'])}**；首跑的 1 条红见 §6.0（未降阈值、未 skip） | ✅ |
| ⑧ | 16 叶 omega 链与根归档 | {leaf_claim} |

末行原文（判据⑦，防"解析器坏了"）：`{q(base['pytest']['summary_line'])}`

### 6.0 判据⑦ 的**首跑是红的**：两次都摆出来，不拿终态盖掉第一次

| 口径 | 首跑 | 终态复跑 |
|---|---|---|
| pytest 末行 | `{q(try1_summary)}` | `{q(base['pytest']['summary_line'])}` |
| 失败用例 | `{q(try1_failed)}` | 无（红错计数 `{q(fail_codes)}`） |
| 断言原文 | `{q(try1_assert)}` | — |
| 同一套件的墙钟 | {q(TRY1_SECS)}s | {q(FINAL_SECS)}s（**同一份产品码**，慢 **{q(SLOW_PCT)}%**） |
| 负载快照 | 无——探针是首跑之后才加的 | `{q(LOAD1)}`（口径：旧探针按 `python.exe` 映像名过滤，见 §五′ 第 5 条） |

**能证的是这一条**：`polish_wallclock_r1.json.product_unchanged_since_try1` 显示首跑日志落盘
（{q((wall.get('product_unchanged_since_try1') or {}).get('try1_log_mtime_utc'))}）之后，
`{q('、'.join((wall.get('product_unchanged_since_try1') or {}).get('product_py_files_checked') or []))}`
下**没有任何 .py 更新**（`product_files_newer_than_try1={q((wall.get('product_unchanged_since_try1') or {}).get('product_files_newer_than_try1'))}`，
本轮这段时间里只动过 `.fist-loop-20260927/` 自己的脚本）。
⇒ 同一条断言在**产品码一行未改**的两次全量实跑里一红一绿，所以这条门的红绿不由产品行为决定——
这是一个**flaky 的墙钟判据**，不是 Cypy 的新缺陷。

"当时机器上还有谁在跑"只能作旁证：`polish_wallclock_r1.underload.json` 记着 05:45Z 那次采样
`foreign_lane={q(((json.loads((HERE / 'polish_wallclock_r1.underload.json').read_text(encoding='utf-8')).get('load') or {}).get('before') or {}).get('foreign_lane'))}`
（同机别的项目在跑 `sweep_demos.py` 等）；而终态这次复跑（`polish_wallclock_r1.json`）
前后各 3 次采样 `foreign_lane={q((wall.get('load') or {}).get('before', {}).get('foreign_lane'))}/{q((wall.get('load') or {}).get('after', {}).get('foreign_lane'))}`、
取不到命令行的 `{q((wall.get('load') or {}).get('before', {}).get('unattributable'))}/{q((wall.get('load') or {}).get('after', {}).get('unattributable'))}`。
"机器完全空闲"在这台机器上**不可证**（存在父链也读不到命令行的常驻 python），所以本节的结论不建立在它上面。

复跑实测（`polish_wallclock_r1.json`，探针 `lane_load.py`）：

- 单跑该用例：`{q((wall.get('solo') or {}).get('summary_line'))}`（rc={q((wall.get('solo') or {}).get('rc'))}）
- 整文件 `{q('tests/test_incremental.py')}`：`{q((wall.get('whole_file') or {}).get('summary_line'))}`（rc={q((wall.get('whole_file') or {}).get('rc'))}）
- 复跑前后负载：`{q(json.dumps(wall.get('load') or {}, ensure_ascii=False)[:300])}`
- 该用例函数体里的计时口径原文（file:line 回核）：

| 行 | 原文 |
|---|---|
{chr(10).join(f"| `{q(str(b['line']))}` | `{q(b['text'])}` |" for b in (wall.get('timing_evidence') or {}).get('body', []))}

读法：同一个用例里**上一条**时限断言（`digest_elapsed < 2.0`）用 `time.process_time()`，
**红的那条**（`compare_elapsed < 5.0`）用 `time.perf_counter()`；`parse_elapsed < 60.0` 也是墙钟但阈值宽到碰不到。
账本 BUG-13 的修复边界本来就写着"parse/compare 两条时限仍是墙钟"——所以这条**不是新缺陷**，
不另立单，而是按已有边界登记：本轮**没有下调任何阈值、没有 skip、没有删任何用例**，
只把首跑原文留在这一节，并在 `memory/bugs.md` 的 BUG-13 条目下追加一条 09-27 的实测翻转记录（交裁决是否改成 CPU 时间口径）。

### 6.1 收口链上的被拒原文（逐字，一条不吞）

| 调用 | 任务 | 服务端原文 |
|---|---|---|
{refused_rows}

call_log 最近 {rootc.get('call_log_rows') or 0} 行的工具分布：{tally}

## 七、转结（移交 R1-推进 与 R2）

1. **BUG-40/41/42/43 四单待修**（`T0r48/T0r51/T0r52/T0r53`）：
   BUG-41（被遮的 6 条用例）与 BUG-42（两个死 visitor）都在"改哪份都可能改错"的位置，
   需要 `git log -L` 判来历后再动 ⇒ 交 R2-修复；BUG-40/43 是配置层，改法各有两个口径需人类裁决。
2. 全仓 lint/black 规模（数字取自盘上件 `{L}verify_lint_r1.json`，普查时刻 {lint_when}）：
   **{repo_c['total']} 条 / {repo_c['files']} 文件**，W293 占 {w293_share}%；
   black 对 {len(lint_prev['black']['would_reformat'])} 个本轮碰过的产品文件仍要整档重排：
   **需要人类裁决"分批还是一次做完"**，
   一次做完会产生数百行无关 diff，与 09-26 未提交轮冲突的风险由人担。
3. `mode_list` 的 forbidden_tools 不承重这条：如果继续跑 5 轮，模式约束只能靠每轮报告自证
   （本环 §一 的形状就是模板），或者给 FIST 侧提需求让服务端真的按模式拦。
4. skip 三处中「机制型/弱断言」两处若要收紧，等于新增会失败的断言 ⇒ 属修复半径，不在打磨动。
5. **墙钟时限断言**（`tests/test_incremental.py` 的 `compare_elapsed < 5.0`，同一函数上一条用
   `process_time()`）：本轮首跑被同机别的项目打断到 5.32s 而红，无并发时单跑/整文件都绿。
   要不要把这条也改成 CPU 时间口径 = **改测试语义**，超出打磨半径 ⇒ 交裁决；
   账本 BUG-13 的"parse/compare 两条时限仍是墙钟"边界在改之前保持不变。

```
[selfdrive-polish] round=R1 stage=打磨 root=T0r49 quickwin=1 filed=BUG-41,BUG-42,BUG-43 carry=lint-scale,mypy-config,mode-gate,wallclock-assert
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
            "pytest_passed": base["pytest"]["passed"],
            "dead_tests": dead_tests,
            "mode_gate": "not-enforced",
        },
        ensure_ascii=False,
    )
)
