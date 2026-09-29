"""开工基线快照：HEAD 身份 + 被测量面清单（尺寸:mtime）。

为什么要它：本仓 HEAD 是 2026-08-17，而盘面带着 09 月三轮未提交的改动 ⇒ `git archive HEAD`
出的树不能当"上一轮代码"。回退矩阵/锁承重的底树一律用这份盘面快照，HEAD 只作身份记录。
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TRACKED_DIRS = ("cypyc", "cypy_bridge", "cypy_hook", "tests", "examples", "scripts", "test_suite", "SYNTAX")
SUFFIXES = (".py", ".cypy", ".md", ".sh", ".out")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", "node_modules"}
OUT = HERE / "baseline_snapshot.json"


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    refuse: list[str] = []
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    staged = [ln for ln in lines if ln[0] != " "]
    untracked = [ln for ln in lines if ln.startswith("??")]
    manifest: dict[str, str] = {}
    for d in TRACKED_DIRS:
        base = ROOT / d
        if not base.is_dir():
            refuse.append(f"被测量面目录缺失：{d}")
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in SUFFIXES:
                continue
            if SKIP_DIRS & set(p.relative_to(base).parts):
                continue
            st = p.stat()
            manifest[str(p.relative_to(ROOT)).replace("\\", "/")] = f"{st.st_size}:{int(st.st_mtime)}"
    if len(manifest) < 200:
        refuse.append(f"清单只有 {len(manifest)} 项，覆盖面判据（>=200）不成立 ⇒ 扫描面本身坏了")
    payload = {
        "started_utc": utcnow(),
        "head": head,
        "head_commit_date": subprocess.run(
            ["git", "log", "-1", "--format=%ci"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "porcelain_total": len(lines),
        "porcelain_staged": len(staged),
        "porcelain_untracked": len(untracked),
        "manifest_files": len(manifest),
        "manifest": manifest,
        "refuse": refuse,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"baseline head={head[:7]} commit_date={payload['head_commit_date']} "
          f"porcelain={len(lines)}(staged={len(staged)},untracked={len(untracked)}) "
          f"manifest={len(manifest)} refuse={len(refuse)}")
    for r in refuse:
        print("REFUSE:", r)
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
