#!/usr/bin/env python3
"""Seventh-pass workspace snapshot.

The brief forbids git add/commit this round, and `examples/ dist/ output/` carry 56 lines of
earlier-pass dirt, so "this pass touched only X" cannot be proved by a clean tree. This script
freezes `git status --porcelain` plus (mtime, size) for every product/test .py before the pass
edits anything; the after-snapshot diffs against it to produce the deliverable file list.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PKGS = ["cypyc", "cypy_bridge", "cypy_hook", "tests", "test_suite", "memory"]


def snapshot() -> dict:
    git = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    dirty = [ln for ln in (git.stdout or "").splitlines() if ln.strip()]
    files = {}
    for pkg in PKGS:
        for p in sorted((ROOT / pkg).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            st = p.stat()
            files[str(p.relative_to(ROOT)).replace(os.sep, "/")] = [int(st.st_mtime), st.st_size]
    for rel in ("memory/bugs.md",):
        q = ROOT / rel
        if q.exists():
            st = q.stat()
            files[rel] = [int(st.st_mtime), st.st_size]
    # 裁决落地面会动到非 .py 产物（examples/*.out 基准、SYNTAX/*.md 冻结文档）。
    # 只统计 .py 会让「本轮改了哪些文件」的清单静默漏掉它们。
    for pat in (("examples", "*.out"), ("SYNTAX", "*.md"), ("PROJECT-SPEC", "*.md")):
        pkg, glob = pat
        for p in sorted((ROOT / pkg).glob(glob)):
            st = p.stat()
            files[str(p.relative_to(ROOT)).replace(os.sep, "/")] = [int(st.st_mtime), st.st_size]
    return {
        "taken_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "git_dirty_lines": len(dirty),
        "git_dirty": sorted(dirty),
        "py_files": files,
    }


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "ws_snapshot_pass7.json")
    data = snapshot()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"wrote {out}: dirty={data['git_dirty_lines']} files={len(data['py_files'])} "
          f"head={data['git_head'][:8]} at={data['taken_at_utc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
