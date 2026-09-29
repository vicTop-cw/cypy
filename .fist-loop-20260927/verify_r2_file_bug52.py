#!/usr/bin/env python3
"""R2-验证 入账 BUG-52：项目声明了 black 口径但仓库 91% 文件不满足，照规范跑 format 会产生巨量 diff。

入账口径沿用前几轮：detail 必带**当场可复跑的命令 + file:line 来历 + 什么现象不算证明**。
这条与 BUG-40（flake8 配置不生效）同族，与 BUG-50（black 整档重写不可回滚）互为因果。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
OUT = HERE / "verify_r2_file_bug52.json"

SUMMARY = (
    "[构建/规范配置] pyproject 声明了 [tool.black] line-length=100，但 156 个 .py 里 142 个不满足，"
    "照 PROJECT-SPEC/02 跑 format 会产出巨量不可复审的 diff"
)


def measure() -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "black",
            "--line-length",
            "100",
            "--check",
            "cypyc",
            "cypy_bridge",
            "scripts",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+) files? would be reformatted, (\d+) files? would be left unchanged", out)
    counted = subprocess.run(
        ["bash", "-c", "find cypyc cypy_bridge scripts tests -name '*.py' | wc -l"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    radius = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "black",
            "--line-length",
            "100",
            "--check",
            "cypyc/cli.py",
            "cypy_hook/hook.py",
            "cypyc/codegen/cython_generator.py",
            "cypyc/parser/parser.py",
            "cypyc/parser/macro_expander.py",
            "cypy_hook/__init__.py",
            "tests/test_loop_20260927_fix_r2.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    rout = (radius.stdout or "") + (radius.stderr or "")
    dirty = sorted(set(re.findall(r"would reformat (\S+)", rout)))
    clean = sorted(set(re.findall(r"left unchanged", rout)))
    return {
        "rc": proc.returncode,
        "reformat": int(m.group(1)) if m else -1,
        "unchanged": int(m.group(2)) if m else -1,
        "py_files": int(counted.stdout.strip() or -1),
        "radius_dirty": dirty,
        "radius_clean_cnt": len(clean),
        "ver": subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "black", "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip(),
    }


def main() -> int:
    mm = measure()
    probe = json.loads((HERE / "verify_r2_probe.json").read_text(encoding="utf-8"))
    noise = probe["probes"]["P9.black_noise_split"]
    detail = f"""现象（两条口径当场可复跑，全部在本工作树实测）：
  $ python -X utf8 -m black --line-length 100 --check cypyc cypy_bridge scripts tests
  {mm['reformat']} files would be reformatted, {mm['unchanged']} files would be left unchanged
  $ find cypyc cypy_bridge scripts tests -name "*.py" | wc -l   → {mm['py_files']}
  ↑ 声明口径覆盖不到 {mm['reformat']}/{mm['py_files']} 个文件（{round(100 * mm['reformat'] / max(mm['py_files'], 1))}%）；本机 black：{mm['ver']}

声明处（逐字）：
  pyproject.toml:49-50  [tool.black] / line-length = 100
  PROJECT-SPEC/02-命名与源码规范.md:46  “提交前跑 lint/format（如项目配置），0 warning 优先。”
contributor 照这条跑 `black .` 得到的不是"通过"，而是把 {mm['reformat']} 个文件整档重写。

本轮改动半径（同一命令、只列半径内 7 个 .py）：不满足的是 {json.dumps(mm['radius_dirty'], ensure_ascii=False)}，
其余 {mm['radius_clean_cnt']} 个干净 —— 也就是说 R2-修复 的亲笔行是干净的，**债在文件级不在本环**。

为什么这条不是"格式洁癖"而是可量化的损失（R2-验证 的 P9 实测，件 `verify_r2_probe.json`）：
  以 HEAD 为底，`cypyc/parser/parser.py` 文本差 {noise['cypyc/parser/parser.py']['vs_head_raw']} 行；
  先把 HEAD 版本按同一配置过一遍 black 再比，只差 {noise['cypyc/parser/parser.py']['vs_head_after_black']} 行
  ⇒ 其中 {noise['cypyc/parser/parser.py']['attributable_to_formatting']} 行纯属排版噪声，真实内容增量（09-26/R1 未提交工作 +
  本环 4 处）只有 {noise['cypyc/parser/parser.py']['vs_head_after_black']} 行。`macro_expander.py` 同型：{noise['cypyc/parser/macro_expander.py']['vs_head_raw']} →
  {noise['cypyc/parser/macro_expander.py']['vs_head_after_black']}（排版占 {noise['cypyc/parser/macro_expander.py']['attributable_to_formatting']}）。
这正是 BUG-50 的放大器：一个未被门禁认领的 formatter 声明，让人有理由顺手 `black` 掉两档产品文件，
而全仓 91% 的文件都在同一个坑里。

不算证明（避免被误判成"已修"）：
 - 只对个别文件跑 `black` 让它变干净 ≠ 这条闭环 —— 声明是仓库级的；
 - 把 `[tool.black]` 段落删掉/改口 ≠ 修复（那是把声明改成既成事实，且与 BUG-40 的"配置不生效"是同一种回避）；
 - `black --check` 的 rc=1 只是本条的现象，不能反过来当判据。

修法（交裁决，三选一或组合，自动轮不独走）：
 a) 一次性全仓 `black` 提交（约 {mm['reformat']} 文件、数千行噪声）+ 之后把 `black --check` 设为 CI 硬门；
    这一条要人工批，因为一旦提交，任何未提交工作都无法与排版噪声区分（BUG-50 就是它的单机版本）；
 b) 只设**增量门**：对 `git diff` 命中的 hunk 跑 `black --check`（本轮 R2-修复 的作用域化 lint 判据已是这个形状），
    存量债列白名单，逐步收敛；
 c) 改声明：把 PROJECT-SPEC/02 的"跑 format"改成"新写/新改代码满足 formatter"，并在 pyproject 注明不追存量
    （冻结文档，需人工）。
同族参照：BUG-40（flake8 的 [tool.flake8] 因缺插件完全不生效）。"""

    c = lfist_lib.Client(timeout=240)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    c._recv(1, 60)
    r = c.call(
        "report_bug",
        {
            "summary": SUMMARY,
            "detail": detail,
            "severity": "medium",
            "project_dir": ".",
            "reported_by": "cypy-verifier",
            "publish_task": True,
            "now": lfist_lib.utc_now(),
        },
    )
    bug_id = r.get("bug_id")
    task_id = r.get("task_id")
    refuse = []
    if not bug_id:
        refuse.append(f"report_bug 没回 bug_id：{json.dumps(r, ensure_ascii=False)[:200]}")

    ledger = ROOT / "memory" / "bugs.md"
    txt = ledger.read_text(encoding="utf-8")
    if bug_id and f"## {bug_id} [" not in txt:
        refuse.append(f"账本里没有 {bug_id} 条目（report_bug 未落盘）")
    if task_id and bug_id:
        head = f"## {bug_id} ["
        i = txt.index(head)
        found = txt.find("\n## BUG-", i + len(head))
        nxt = len(txt) if found < 0 else found
        entry = txt[i:nxt]
        if "- task_id:" not in entry:
            patched = entry.rstrip("\n") + f"\n- task_id: {task_id}\n"
            txt = txt[:i] + patched + txt[nxt:]
            ledger.write_text(txt, encoding="utf-8", newline="\n")
        elif task_id not in txt[i:nxt]:
            refuse.append(f"{bug_id} 已有别的 task_id，不覆盖")

    bl = c.call("bug_list", {"project_dir": ".", "limit": 80, "now": lfist_lib.utc_now()})
    rows = bl.get("bugs") or bl.get("items") or bl or []
    found = [
        b for b in rows if isinstance(b, dict) and SUMMARY[:24] in json.dumps(b, ensure_ascii=False)
    ]
    if not found:
        refuse.append("bug_list 回读不到这条（隐形标题/未入列表）")

    doc = {
        "refuse": refuse,
        "measure": mm,
        "filed": {"bug_id": bug_id, "task_id": task_id, "severity": "medium"},
        "bug_list_hits": len(found),
        "black_noise_split": noise,
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {"refuse": refuse, "filed": doc["filed"], "bug_list_hits": len(found)},
            ensure_ascii=False,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
