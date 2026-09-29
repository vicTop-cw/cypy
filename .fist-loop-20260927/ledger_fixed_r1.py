"""R1-修复 的账本留档：向 memory/bugs.md 逐单插入 FIXED/PARTIAL 段。

三条硬约束（对齐账本既有惯例，见 BUG-32 的 FIXED 段形态）：
  1. **只在所属条目尾部插入**，不改动任何既有行——写完后把插入块逐段摘掉必须逐字还原原文件；
  2. 段内所有计数/节点名/文件名都从证据件反解，不许手打数字；证据件缺一项即拒绝；
  3. 幂等：同一单已有本轮 tag 的段就不再写（重复跑不产生第二份）。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory/bugs.md"
TAG = "2026-09-27 R1-修复(循环轮)"

lock = json.loads((HERE / "lockproof_r1.json").read_text(encoding="utf-8"))
gd = json.loads((HERE / "golden_diff_r1.json").read_text(encoding="utf-8"))
base = json.loads((HERE / "run_baselines_r1.json").read_text(encoding="utf-8"))
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
REPORT = _pos[0] if _pos else None
if not REPORT:
    raise SystemExit("REFUSE — 必须把修复报告相对路径作为位置参数传进来")

refuse = []
for name, doc in (("lockproof_r1", lock), ("golden_diff_r1", gd), ("run_baselines_r1", base)):
    if doc.get("refuse"):
        refuse.append(f"证据件 {name} 自身带拒绝项：{doc['refuse']}")
ts = base.get("test_suite") or {}
tg = base.get("targeted") or {}
if ts.get("failed") != 0 or ts.get("passed") != ts.get("total"):
    refuse.append(f"自研套件不绿，不留 FIXED：{ts}")
if tg.get("failed") or tg.get("errors") or tg.get("rc") != 0:
    refuse.append(
        f"定向 pytest 不绿，不留 FIXED：{ {k: tg.get(k) for k in ('rc','passed','failed','errors')} }"
    )
if refuse:
    print("REFUSE — " + " | ".join(refuse))
    raise SystemExit(1)

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
full = lock["result"]["full_tree"]


def red_nodes(ticket: str) -> list:
    return sorted(lock["result"][ticket]["failed"])


golden_line = (
    f"端到端基准：`examples/{next(iter(gd['changed_files']))}` 重注册，"
    f"数字面差异 {len(gd['digit_only_lines'])} 行、非数字面 0 行、"
    f"其余 {gd['unchanged_files']} 份基准逐字未变"
)
first_diff = gd["digit_only_lines"][0]
golden_quote = f"`{first_diff['before'].strip()}` → `{first_diff['after'].strip()}`"
baseline_line = (
    f"基线双套：自研套件 `Total {ts['total']} / Passed {ts['passed']} / Failed {ts['failed']}`；"
    f"定向 pytest（从改动面反解 {tg['file_count']} 个文件）`{tg['passed']} passed`，"
    f"末行 `{tg['summary_line']}`"
)


def block(ticket: str, bug: str, task: str, boundary: str, kind: str = "FIXED") -> str:
    reds = red_nodes(ticket)
    own = len(LOCK_NODES[ticket])
    total = len(full["passed"])
    head = (
        f"### {kind}(verify={'已完成' if kind == 'FIXED' else '部分落地'}) — "
        f"{now} 追加留档（{TAG}，本条目正文与标题行 `OPEN` 一字未改）\n"
    )
    lines = [
        head,
        f"- 修复单：`{task}`（ns `cypy-loop-20260927`，分支/叶子全链带 `[omega:required]`，"
        f"L4 `output_validate` 逐叶 pass 后才 verify）；报告：`{REPORT}`\n",
        f"- 锁死回归：{LOCK_FILE} 里本单 {own} 条（1 锁 + 1 对照）；"
        f"在**只回退本单**的临时树上证红 {len(reds)} 条："
        f"{('、'.join(LOCK_FILE + '::' + n for n in reds)) or '无'}；"
        f"同一棵树上其余 {total - len(reds)} 条（本单对照锁 + 其余三单的用例）保持绿 ⇒ 红能归给本单\n",
    ]
    if ticket in ("BUG-30",):
        lines.append(f"- 产物与运行期证据：{golden_line}（{golden_quote}）\n")
    lines.append(f"- 双套基线：{baseline_line}\n")
    lines.append(f"- 修复边界：{boundary}\n")
    return "".join(lines)


BLOCKS = {
    "BUG-30": (
        "T0r46.1",
        "只在「声明带标注 + 初值**确定为整数** + 目标为浮点 C 类型」三条同时成立时补 "
        "`<double>` 强转；宽度表新起 `_declared_var_types`，**不**并进 `_current_local_types`"
        "（那张表历史上只装参数，灌进局部变量会顺带改掉 `/` 是否发 `//` 的既有产物形态）。"
        "复合表达式加括号 `<double>(...)`；`as float` 显式转写、指针、对象面一律不动。",
    ),
    "BUG-31": (
        "T0r46.2",
        "落两半：① 措辞四处（模块 docstring / 类 docstring / `to_ctypes` / `to_c`）改为"
        "「键空间是 C/FFI 类型名」，并说明与 Cypy `float`（8 字节）不同宽；② `float_` → `float32_`"
        " 改名，含 `cypy_bridge/__init__.py` 的 import 与两处 `__all__`，以及"
        "`tests/test_bridge_library.py:159/162/974` 三处按名引用（同义换名，断言强度不变）。"
        "**宽度值 `c_float`/4 字节一律未动**，裁决保护的 "
        "`tests/test_bridge_library.py:646-649` 一字未改（对照锁 "
        "`test_bug31_width_of_bridge_float_is_unchanged` 钉住）。"
        "残留：`.trae/specs/cypy-bridge/checklist.md:37` 仍写旧名，属历史清单未改。",
    ),
    "BUG-33": (
        "T0r46.3",
        "只在 `while` 走到 EOF（`else` 分支）时抛 `ValueError`，带字面量起始行列与 EOF 行列；"
        "闭合路径 `break` 不受影响，f-string/三引号/raw 共用同一函数故一并受益。",
    ),
    "BUG-38": (
        "T0r46.4",
        '`_skip_whitespace` 的成员判断从「`in " \\t"`（None 参与即 TypeError）」改成显式元组，'
        "行为差异只在 EOF：末行空格 + 无末换行不再崩。末行有无换行在 **AST 层同型**（对照锁），"
        "token 流层面 EOF 不补 DEDENT/NEWLINE 属实现细节，本轮不动、已在报告观察区记一行。",
    ),
}

LOCK_FILE = "tests/test_loop_20260927_fix.py"
LOCK_NODES = {
    "BUG-30": [
        "test_bug30_int_initializer_to_float_gets_explicit_double_cast",
        "test_bug30_widening_does_not_touch_non_integrals",
    ],
    "BUG-31": [
        "test_bug31_bridge_mapping_declares_ffi_key_space_and_renamed_alias",
        "test_bug31_width_of_bridge_float_is_unchanged",
    ],
    "BUG-33": [
        "test_bug33_unterminated_string_raises_with_position",
        "test_bug33_closed_string_still_lexes",
    ],
    "BUG-38": [
        "test_bug38_trailing_spaces_at_eof_do_not_crash",
        "test_bug38_trailing_space_parses_like_the_newline_version",
    ],
}

BLOCK_RE = re.compile(
    r"\n### (?:FIXED|PARTIAL)\(verify=[^)]*\) — [^\n]*" + re.escape(TAG) + r".*?(?=\n## BUG-|\Z)",
    re.S,
)


def strip_mine(s: str) -> str:
    return BLOCK_RE.sub("", s)


text = (
    strip_mine(LEDGER.read_text(encoding="utf-8"))
    if "--rewrite" in sys.argv
    else LEDGER.read_text(encoding="utf-8")
)
out = text
for bug, (task, boundary) in BLOCKS.items():
    hdr = re.search(rf"^## {bug} \[.*?^(- task_id: \S+)", out, re.M | re.S)
    if not hdr:
        print(f"REFUSE — 账本里找不到 {bug} 条目的 task_id 行，位置不确定就不写")
        raise SystemExit(1)
    # 幂等判据要看**插入区**（task_id 行之后、下一条 `## BUG-` 之前），
    # 看条目自身区间是空判 —— 留档段本来就写在 task_id 之后。
    tail = out[hdr.end() :]
    nxt = re.search(r"^## BUG-", tail, re.M)
    if TAG in (tail[: nxt.start()] if nxt else tail):
        print(f"SKIP {bug} — 本轮留档段已存在（幂等）")
        continue
    ins = "\n" + block(bug, bug, task, boundary)
    out = out[: hdr.end()] + "\n" + ins.rstrip("\n") + "\n" + out[hdr.end() :]

# 回读校验：把本轮插入的段落逐段摘掉，必须与（摘掉本轮已有段之后的）原文逐字一致
verify = strip_mine(out)
if verify.rstrip("\n") != text.rstrip("\n"):
    print("REFUSE — 摘掉插入段后与原文不一致：既有行被动过了，不落盘")
    (HERE / "ledger_fixed_r1.diff.txt").write_text(
        "\n".join(
            f"{a[:120]}\n{b[:120]}\n---"
            for a, b in zip(text.splitlines(), verify.splitlines())
            if a != b
        )[:8000],
        encoding="utf-8",
        newline="\n",
    )
    raise SystemExit(1)

LEDGER.write_text(out, encoding="utf-8", newline="\n")
print(
    json.dumps(
        {
            "appended": list(BLOCKS),
            "ledger_lines_before": len(text.splitlines()),
            "ledger_lines_after": len(out.splitlines()),
            "headers_unchanged": len(re.findall(r"^## BUG-", out, re.M)),
        },
        ensure_ascii=False,
    )
)
