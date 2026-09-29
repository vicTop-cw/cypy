#!/usr/bin/env python3
"""Loop-lane driver (ns=cypy-loop-20260927) — 5 rounds x 5 modes over Cypy.

Reuses ../.fist-polish-20260926/pfist.py verbatim (same server build, server cwd = Cypy
root, explicit `now` per call, `project_dir` only relative) and swaps only the namespace,
so this lane's task tree can never interleave with the closed polish lane's tasks.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, ".fist-polish-20260926")
    ),
)
import pfist  # noqa: E402
import lfist_lib  # noqa: E402

pfist.NAMESPACE = "cypy-loop-20260927"
pfist.CLIENT_INFO = {"name": "cypy-loop", "version": "1.0.0"}
# 入口换到 cli.js + serve 之后，本 lane 的 Client 统一由 lfist_lib 提供（见那里的注释）；
# pfist.main() 读的是模块全局 Client，所以这里换掉它，手动探针才不会走旧入口。
pfist.Client = lfist_lib.Client

if __name__ == "__main__":
    sys.exit(pfist.main())
