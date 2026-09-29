#!/usr/bin/env python3
"""改产品码前先落一份**全量受版本控制文件**的快照，避免"不可逆的格式化"再发生。

触发原因：本轮把 `cypyc/parser/parser.py`、`cypyc/parser/macro_expander.py` 传给了 `black`，
两档本身带着数千行未格式化存量债 ⇒ black 整档重写（parser.py 相对 HEAD 的改动行数
425 → 1885）。事前没有任何副本（索引==HEAD、IDE file-history 无今日快照），**不可回滚**。
教训钉成机制：任何后续改动前先 `python snapshot_tracked.py <标签>`，快照落在
`.fist-loop-20260927/snapshots/<标签>/` 下并自证文件数与字节数。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
# 刻意落在仓库外：快照目录若进 repo，会让并发 lane 的"新文件未进索引"类守卫一次性踩到几千个文件
SHOTS = Path(r"E:\IDEProjects\AI\_cypy_snapshots")


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "manual"
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    tracked = [x for x in r.stdout.split(chr(0)) if x.strip()]
    extra = []
    for pat in ("tests/test_loop_20260927_*.py",):
        extra += [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.glob(pat)]
    names = sorted(set(tracked) | set(extra))
    out = SHOTS / label
    out.mkdir(parents=True, exist_ok=True)
    copied, missing, bytes_total = 0, [], 0
    for rel in names:
        src = ROOT / rel
        if not src.is_file():
            missing.append(rel)
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        copied += 1
        bytes_total += src.stat().st_size
    doc = {
        "label": label,
        "tracked_names": len(names),
        "copied": copied,
        "bytes": bytes_total,
        "missing": missing[:10],
        "target": str(out),
    }
    if copied != len(names) - len(missing) or copied == 0:
        doc["refuse"] = (
            f"快照文件数不自证：copied={copied} names={len(names)} missing={len(missing)}"
        )
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    return 1 if "refuse" in doc else 0


if __name__ == "__main__":
    sys.exit(main())
