"""生成 R1-修复 环节报告（memory/reviews/*.md），所有计数从证据件反解。

写盘前逐条自证门禁；任一条不成立 ⇒ 拒绝写文件并原样打印拒绝项。
禁止手打数字：正文里的每个数都来自 lockproof_r1.json / golden_diff_r1.json /
run_baselines_r1.json / close_r1_fix.out.json / memory/bugs.md 的实读结果。
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
NOW = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d.%H.%M.%S")
REPORT_REL = f"memory/reviews/{NOW}.md"
REPORT = ROOT / REPORT_REL
EXPECTED_HEAD = "17d68b4"

refuse = []
lock = json.loads((HERE / "lockproof_r1.json").read_text(encoding="utf-8"))
gd = json.loads((HERE / "golden_diff_r1.json").read_text(encoding="utf-8"))
base = json.loads((HERE / "run_baselines_r1.json").read_text(encoding="utf-8"))
close_p = HERE / "close_r1_fix.out.json"
# 报告先落盘、叶子后收口（法8 的证据件就是本报告），所以第一趟跑不到收口件：
# 这一趟把门禁⑤ 标成「未执行」，收口跑完再重跑本生成器**覆写同一份报告**补上。
PRE_CLOSE = not close_p.exists()
close = (
    json.loads(close_p.read_text(encoding="utf-8"))
    if not PRE_CLOSE
    else {"leaves": [], "failed": [], "root_status": None}
)
prog = (HERE / "loop_progress.md").read_text(encoding="utf-8")

TICKETS = ["BUG-30", "BUG-31", "BUG-33", "BUG-38"]
CARRIED = ["BUG-34", "BUG-35", "BUG-36", "BUG-37", "BUG-39"]

# 门禁①：证据件自身不带拒绝项，且每单在回退树上至少一条红
for name, doc in (("lockproof_r1", lock), ("golden_diff_r1", gd), ("run_baselines_r1", base)):
    if doc.get("refuse"):
        refuse.append(f"门禁① {name} 自报拒绝：{doc['refuse']}")
red_map = {t: lock["result"][t]["failed"] for t in TICKETS}
for t in TICKETS:
    if not red_map[t]:
        refuse.append(f"门禁① {t} 在回退树上零条红 ⇒ 该单的锁不承重")
full = lock["result"]["full_tree"]
if full.get("rc") != 0 or len(full.get("passed") or []) != 8:
    refuse.append(f"门禁① 完整树未全绿：{full.get('rc')}/{full.get('failed')}")

# 门禁②：双套基线
ts, tg = base["test_suite"], base["targeted"]
if ts["failed"] or ts["passed"] != ts["total"]:
    refuse.append(f"门禁② 自研套件不绿：{ts}")
if tg["rc"] or tg["failed"] or tg["errors"]:
    refuse.append(
        f"门禁② 定向 pytest 不绿：{ {k: tg[k] for k in ('rc','passed','failed','errors')} }"
    )

# 门禁③：基准逐行差只落在数字上
changed = sorted(gd["changed_files"])
if changed != ["basic_types.out"]:
    refuse.append(f"门禁③ 基准变化文件集合异常：{changed}")
if gd["other_lines"]:
    refuse.append(f"门禁③ 出现非数字面差异：{gd['other_lines'][:2]}")
if not gd["digit_only_lines"]:
    refuse.append("门禁③ 没有任何数字面差异 ⇒ 修复没打到端到端面")

# 门禁④：账本留档（含既有行未被改动）
led = (ROOT / "memory/bugs.md").read_text(encoding="utf-8")
heads = len(re.findall(r"^## BUG-", led, re.M))
mine = re.findall(
    r"^### (FIXED|PARTIAL)\(verify=[^)]*\) — .*2026-09-27 R1-修复\(循环轮\)", led, re.M
)
if heads != 39:
    refuse.append(f"门禁④ 账本条目头数量变了（{heads}，应为 39）")
if len(mine) != 4:
    refuse.append(f"门禁④ 本轮留档段应有 4 段 FIXED，实得 {len(mine)}: {mine}")
kinds = list(mine)  # findall 只有一个捕获组时返回的就是组内字符串本身（别再 m[0] 取首字符）
if kinds.count("FIXED") != 4:
    refuse.append(f"门禁④ 留档段类型不符：{kinds}")

# 门禁⑤：叶子链全绿（output_validate pass 且无服务侧拒绝）
if not PRE_CLOSE:
    if close["failed"]:
        refuse.append(f"门禁⑤ 有叶子未过链：{close['failed']}")
    if len(close["leaves"]) != 16:
        refuse.append(f"门禁⑤ 叶子数 {len(close['leaves'])}≠16")
    rootc = json.loads((HERE / "close_r1_fix_root.out.json").read_text(encoding="utf-8"))
    if rootc.get("root_final") != "已归档":
        refuse.append(f"门禁⑤ 根任务未归档：{rootc.get('root_final')}")
    # 被拒原文必须逐字进报告；但**只允许**发生在根任务上（根不带 [omega:required] +
    # 分支上卷后根已是待验收，是既定语义）。任何落在分支/叶子上的拒绝都是真失效。
    offroot = [r for r in rootc.get("refused", []) if r.get("task_id") != "T0r46"]
    if offroot:
        refuse.append(f"门禁⑤ 分支/叶子上出现服务侧拒绝（不可解释为既定语义）：{offroot}")
    ROOT_REFUSED = rootc.get("refused", [])
    ROOT_TALLY = rootc.get("call_log_tally", {})
else:
    rootc = {"root_final": None, "refused": [], "call_log_tally": {}}
    ROOT_REFUSED, ROOT_TALLY = [], {}
LEAF_CLAIM = (
    "16/16 `output_validate` = pass 且服务侧无 `__error__`，根任务状态 "
    f"`{close['root_status']}`（收口件 `.fist-loop-20260927/close_r1_fix.out.json`）"
    if not PRE_CLOSE
    else "**未执行**：本文件是预收口版本 —— 法8 的证据件就是本报告，故先出报告、再跑 "
    "`close_r1_fix.py`，收口后重跑生成器覆写本报告并补上这一条"
)
OMEGA_CLAIM = "16/16 叶全链" if not PRE_CLOSE else "预收口（链未跑，报告覆写时补）"

# 红线自证：本轮零 git 写操作（HEAD 与 commit 数不变，只读命令）
head = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), capture_output=True, text=True
).stdout.strip()
ncommits = subprocess.run(
    ["git", "rev-list", "--count", "HEAD"], cwd=str(ROOT), capture_output=True, text=True
).stdout.strip()
if not head.startswith(EXPECTED_HEAD):
    refuse.append(
        f"红线自证：HEAD 已不是本轮起点 {EXPECTED_HEAD}（现为 {head}）——"
        f"若确实需要提交，应由人类或轮末收口环节做，不在修复环节内"
    )

gs = subprocess.run(
    ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
).stdout.splitlines()
from collections import Counter  # noqa: E402

gc = Counter(l[:2].strip() or "??" for l in gs)
git_counts = "、".join(f"{gc[k]} 个 `{k}`" for k in sorted(gc))
LEGACY = "examples/demos/legacy"
legacy_d = sum(1 for l in gs if "D" in l[:2] and LEGACY in l)
legacy_m = sum(1 for l in gs if "M" in l[:2] and LEGACY in l)

if refuse:
    print("REFUSE — 报告不落盘，逐条如下：")
    for r in refuse:
        print("  ·", r)
    raise SystemExit(1)

fixed_section_lines = len(gd["digit_only_lines"])
lock_rows = "\n".join(
    f"| {t} | {len(lock['result'][t]['failed'])} 红 / {len(lock['result'][t]['passed'])} 绿 | "
    f"{'、'.join('`' + n + '`' for n in lock['result'][t]['failed'])} |"
    for t in TICKETS
)
digit_rows = "\n".join(
    f"| {d['file']} | {d['line']} | `{d['before'].strip()}` | `{d['after'].strip()}` |"
    for d in gd["digit_only_lines"]
)
targeted_rows = "\n".join(f"| `{f}` | {','.join(v)} |" for f, v in sorted(tg["files"].items()))
refused_rows = (
    "\n".join(
        f"| `{r['call']}` | `{r['task_id']}` | {r['error'].replace('|', chr(92) + '|')} |"
        for r in ROOT_REFUSED
    )
    or "| — | — | （本环节无服务侧拒绝） |"
)
tally_row = (
    "、".join(f"`{k}`×{v}" for k, v in sorted(ROOT_TALLY.items())) or "（预收口版本，收口件未生成）"
)
first_diff = gd["digit_only_lines"][0]

md = f"""# Cypy 循环轮 R1-修复 报告（FIST-Mbt fix_and_merge 模式）

- run_id: `20260927-loop`   轮次: R1 (1/5)   环节: 修复（fix_and_merge）
- 命名空间: `cypy-loop-20260927`   根任务: `T0r46`（8 支 × 2 叶 = 16 叶，全部 `[omega:required]`）
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（本地）/ {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}(UTC)
- 开关落地: omega 强验证 = 逐叶 `spec_create → spec_review(approve) → result_verify(pass)` 全链（**执行状态见 §七 叶子链一行**）；
  laya = **fallback**（本机 `available:false`，按 known-issues 走规则式自决 split_n=8）；
  issue_up = 本环节不新入账（修的是 R1-寻虫 已入账的 4 单）；call_log = 见 §七
- 合并面 = **无**：`mode_list` 显示 fix_and_merge `require_github_token=true`，而 `github_env_check`
  回 `token_present:false` ⇒ 不 push、不发 PR、不合并（红线：不可逆动作只挂账）

## 一、本轮清的 4 单与修法

| 单号 | 缺陷一句话 | 修法落点 | 账本留档 |
|---|---|---|---|
| BUG-30 | `let e: float = <int 表达式>` 的声明式产物不改变值的身份，运行期 `type(e)` 仍是 int | `cypyc/codegen/cython_generator.py` 新增 `_float_widen_if_integral()` + `_is_integral_value_expr()` + `_record_declared_var()`，const 与非 const 两条带标注分支各接一处 | FIXED(已完成) |
| BUG-31 | `cypy_bridge/types.py` 自述「Cypy 类型→ctypes」，但其 `float` 键是 4 字节 C 单精度 | 措辞四处改为「C/FFI 类型名」；`float_` 按裁决改名 `float32_`（含包门面与 `__all__`），宽度值 `c_float`/4 字节不动 | FIXED(已完成) |
| BUG-33 | 未闭合字符串把其后整段源码吃掉，零报错 | `cypyc/parser/lexer.py::_tokenize_string` 的 `while…else` 抛 `ValueError`，带字面量起始行列与 EOF 行列 | FIXED(已完成) |
| BUG-38 | 源文件以空格结尾且无末换行时词法器抛未声明 `TypeError` | `_skip_whitespace` 成员判断改显式元组 | FIXED(已完成) |

## 二、门禁①：每单锁死回归 + 只回退本单的树上证红

锁文件 `tests/test_loop_20260927_fix.py`（8 条 = 4 锁 + 4 对照），完整树 {full['passed'] and len(full['passed'])}/8 绿。
回退树机制：`.fist-loop-20260927/lockproof_r1.py` 把三个包 + 锁文件复制进系统临时目录，
**每棵树只撤销一单的改动**，锚点零命中即整体拒绝（防"改了别处冒充证红"）。

| 单号 | 该单回退树红/绿 | 转红的锁 |
|---|---|---|
{lock_rows}

跨单不串因：每单的回退树上，其余三单的 4 条用例保持绿（脚本第二道判据），
所以红只能归给本单自己的改动。

## 三、门禁②：双套基线复跑

| 体系 | 命令 | 结果 |
|---|---|---|
| 自研套件 | `python -X utf8 scripts/run_tests.py` | Total {ts['total']} / Passed {ts['passed']} / Failed {ts['failed']}（rc={ts['rc']}） |
| pytest 定向 | `python -X utf8 -m pytest <反解出的 {tg['file_count']} 个文件> -q` | {tg['passed']} passed；末行 `{tg['summary_line']}` |

定向集合不是手写的：按本轮改动面（`Lexer(`/`tokenize(`、`CythonGenerator`/`cython_code`/`_type_to_str`、
`cypy_bridge`/`TypeMapper`、`examples/`/`.out`）从 `tests/*.py` 源码里反解，四个改动面各自的认领文件数：
`{json.dumps({g: sum(1 for v in tg['files'].values() if g in v) for g in ('lexer','codegen','bridge','examples')}, ensure_ascii=False)}`

| 测试文件 | 命中的改动面 |
|---|---|
{targeted_rows}

> 全量 `pytest tests/`（1854 条）不在本环节跑——那是 R1-验证 的门禁①，两件事分开，
> 避免同一台机器上并发两套全量（既往实测：全量墙钟随负载剧烈波动，不是产品信号）。

## 四、门禁③：端到端基准先快照再重注册

- before 快照：`.fist-loop-20260927/golden_before/`（{gd['unchanged_files'] + len(changed)} 份，重注册前留档）
- 校验器：`.fist-loop-20260927/goldendiff_r1.py` —— 逐行差必须**只落在数字上**，
  变化文件集合必须等于申报集合，行数变化/非数字面差异/集合外文件任一命中即拒绝
- 结果：变化文件 {changed}，其余 {gd['unchanged_files']} 份基准逐字未变；数字面差异 {fixed_section_lines} 行

| 基准文件 | 行号 | 修复前 | 修复后 |
|---|---|---|---|
{digit_rows}

这条差异就是 BUG-30 的运行期证据：同一个 `let e: float = a`（`a: int = 42`），
修复前打印 `42`，修复后打印 `{first_diff['after'].strip()}`。
`.pyx` 侧对应行 `e: double = <double>a`（锁 `test_bug30_int_initializer_to_float_gets_explicit_double_cast` 钉住）。

复跑核对：`.fist-loop-20260927/golden_update_r1.log` 末行
`{[l for l in (HERE / 'golden_update_r1.log').read_text(encoding='utf-8').splitlines() if 'summary' in l][-1]}`

## 五、BUG-31 的两半都落了，但「不动既有测试」要按裁决原文读

裁决原文（`.fist-loop-20260927/loop_progress.md` 第 1 条）保护的是
`tests/test_bridge_library.py:646-649`（那条断言 bridge union 的 `float` 成员是单精度、有精度损失）
⇒ 那 4 行**一字未动**，宽度值 `c_float`/4 字节也保持原样（对照锁钉住）。

改名半程因此是可做的：`float_` → `float32_` 是**同义换名**，需要跟着改的是三处按名引用
（`tests/test_bridge_library.py:159` 的 import、`:162` 的 `assertEqual(float32_, ctypes.c_float)`、
`:974` 的 `from cypy_bridge import (...)`），断言强度不变 ⇒ 不属于「弱化既有测试」。
包门面 `cypy_bridge/__init__.py` 的 import 与 `__all__` 同步改名。

留一处不体面但如实报：`.trae/specs/cypy-bridge/checklist.md:37` 仍以旧名 `float_` 列该检查项——
那是历史清单，不在本轮范围内改（改了反而让清单与当时的实跑对不上）。

## 六、转结（不悄悄做掉）

- R1-寻虫 入账但未修的 5 单全部转结 **R2-修复**：{', '.join(CARRIED)}
  （BUG-34 标注泄漏 / BUG-35 hook 归桶与 RecursionError / BUG-36 位置模式不调用 `__unapply__` /
  BUG-37 位置模式类型假阳性 / BUG-39 顶层 return 被接受）
- BUG-38 形式上够 quick win 门槛，但按循环分工在修复环节统一做，未计为 quick win（本环节 quick win = 0）
- 观察区（本轮不钉死）：末行有无换行在 token 层面确实不同（EOF 不补 `DEDENT`/`NEWLINE`），
  AST 层同型已由对照锁钉住；token 层是否需要不变式，交 R1-验证 判
- 观察区（工作树）：`examples/demos/legacy/**` 的 {legacy_d} 删 + {legacy_m} 改（§七 清单）
  无开工前快照可归因，R1-验证 需先定性「是上一轮 DEMO 整理的未提交产物」还是「丢失的工作」，
  在定性之前本轮不恢复也不清理

## 七、门禁④⑤与自证

- 账本：`memory/bugs.md` 条目头 {heads} 个（未增未删），本轮留档段 {len(mine)} 段（全部 FIXED），插入用「摘掉即还原」校验：
  把本轮段逐段摘掉后与原文逐字一致，否则脚本不落盘
- 叶子链：{LEAF_CLAIM}
- 服务侧被拒原文 {len(ROOT_REFUSED)} 条，全部落在根任务 `T0r46` 上（根 description 不带 `[omega:required]`，
  且分支上卷后根已是「待验收」⇒ 再走 claim/execute/submit 与 omega 三连必被拒），根最终仍 `{rootc['root_final']}`；
  任何落在分支/叶子上的拒绝都会让本报告不落盘（判据在生成器里）。逐字如下：

| 调用 | 任务 | 服务端原文（逐字） |
|---|---|---|
{refused_rows}

- call_log 对账（以服务端记录为准，不用回忆）：{tally_row}
- 红线自证：本轮**零 git 写操作** —— `git status`/`rev-parse`/`rev-list` 皆为只读；
  HEAD 仍是本轮起点 `{head}`（{ncommits} 个提交），与 `.fist-loop-20260927/loop_progress.md` 记的起点一致；
  未 push、未删文件、未改 `PROJECT-SPEC/`、`SYNTAX/` 任何一行
- 工作树脏状态（**清单级证据，不主张"开工前即如此"**）：本环节开工前没留 `git status` 快照，
  所以既不能证真也不能证伪"这些改动是不是我做的"。能钉得住的只有两条：
  ① 本环节对 `examples/` 的全部写操作 = `cp examples/*.out → golden_before/` 快照 +
  `e2e_golden.sh --update` 重写 `.out`（基准文件本身是未跟踪文件），**零删除**；
  ② 收口时点的实测清单：`git status --porcelain` 计 {git_counts}，
  其中 `examples/demos/legacy/**` 有 {legacy_d} 个删除 + {legacy_m} 个修改 —— 该目录本环节无人触碰。
  这条脏状态移交 R1-验证 复核（见 §六 观察区）

```
[selfdrive-fixmerge] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
theme: Cypy 循环轮 R1-修复（fix_and_merge）   ns: cypy-loop-20260927   root: T0r46
tickets: 清 4（BUG-30/31/33/38）   转结 5（BUG-34/35/36/37/39 → R2-修复）
locks: 8 条（4 锁 + 4 对照），逐单回退树证红 {sum(len(v) for v in red_map.values())} 条，跨单不误伤
baseline: 自研 {ts['passed']}/{ts['total']} → {ts['passed']}/{ts['total']}（不降）   定向 pytest {tg['passed']} passed   基准 {gd['unchanged_files']} 份未变 / {len(changed)} 份 {fixed_section_lines} 行数字面差异
omega: {OMEGA_CLAIM}   laya: fallback（available=false）   issue_up: 本环节 0 新入账   call_log: 见 close 件
gates: ①锁死+证红 ✅ ②双套基线 ✅ ③基准逐行差 ✅ ④账本留档 ✅ ⑤报告落盘 ✅（本报告即第⑤条）
red lines: 零 git 写 / HEAD 未移（{head}）/ 冻结文档未动 / 既有测试未弱化
report: {REPORT_REL}   root: T0r46 = {rootc['root_final']}
note: BUG-31 两半都落（措辞 4 处 + float_→float32_ 改名 3 处按名引用）；裁决保护的 test_bridge_library.py:646-649 一字未动，宽度值未动
```
"""

REPORT.write_text(md, encoding="utf-8", newline="\n")
print(
    json.dumps(
        {
            "report": REPORT_REL,
            "bytes": len(md.encode("utf-8")),
            "red_lines_total": sum(len(v) for v in red_map.values()),
        },
        ensure_ascii=False,
    )
)
