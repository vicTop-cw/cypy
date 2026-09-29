"""五环判据件的共用骨架：结果记账器 + 三种工具输出解析 + 快照复制。

写它的理由不是「整洁」，而是同一份解析逻辑在 48 个 `verify_r4_*.py` / 41 个 `fix_r4_*.py`
里各抄了一遍，每抄一遍就多一处「格式假设变了没人知道」的地方（R4 连着栽过 `pytest -q`
不打印 collected、`cl` 的 cp936 输出、`-v` 的状态位在 nodeid 之后这三类）。

本件由 `polish_r4_debt.py` 用**同一批真实输入**逐个核对过与旧内联实现等价（等价证据在那件里），
所以旧件可以逐步换过来而不改变判定；本轮先在自家新件里用起来，其余重复逐条留债点名。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

PYTEST_SUMMARY = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)")
KV = re.compile(r"(\w+)[=:\s]\s*(\d+)")


def record(checks: list, refuses: list, label: str, got, want, why) -> None:
    """判据记账器：got != want 就同时进 checks 与 refuses（一条判据都不许只数不判）。"""
    checks.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        refuses.append(f"{label}: got={got!r} want={want!r}（{why}）")


def parse_pytest_summary(text: str) -> dict:
    """把 `pytest -q` 的摘要行解析成计数字典；全绿态不打印 collected 行，所以这里不猜收集数。"""
    out = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    line = next((ln for ln in reversed(text.splitlines())
                 if re.search(r"\d+ (passed|failed|error)", ln)), "")
    for n, kind in PYTEST_SUMMARY.findall(line):
        key = "errors" if kind.startswith("error") else kind
        out[key] = out.get(key, 0) + int(n)
    out["summary_line"] = line
    return out


def parse_kv_line(line: str) -> dict:
    return {k: int(v) for k, v in KV.findall(line or "")}


def collect_nodeids(text: str) -> int:
    """收集数只走 `--collect-only -q` 的 nodeid 计数（数 `N collected` 在绿树下恒 0）。"""
    return len([ln for ln in text.splitlines() if "::" in ln])


def copy_tree(src: Path, dst: Path, suffixes: tuple) -> int:
    """按后缀复制一棵树（判据用快照树取数的最小骨架），返回复制的文件数。"""
    n = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or (suffixes and f.suffix not in suffixes):
            continue
        rel = f.relative_to(src)
        if any(part in {"__pycache__", ".git", ".pytest_cache"} for part in rel.parts[:-1]):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        n += 1
    return n
