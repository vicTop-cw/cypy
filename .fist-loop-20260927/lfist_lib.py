"""Shared shim: the polish-lane stdio client, re-labelled for the loop lane's namespace.

The server build, its cwd (Cypy root) and every discipline baked into pfist.py (explicit
`now`, relative-only `project_dir`) stay identical; only NAMESPACE/CLIENT_INFO change, so
this lane's task tree can never interleave with the closed polish lane's tasks.
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, ".fist-polish-20260926")
    ),
)
import pfist  # noqa: E402

NAMESPACE = "cypy-loop-20260927"
pfist.NAMESPACE = NAMESPACE
CLIENT_INFO = {"name": "cypy-loop", "version": "1.0.0"}
PROTOCOL_VERSION = pfist.PROTOCOL_VERSION

# 上游 09-28 03:20Z 重建把服务入口从 `cmd/main/main.js` 移到了 `cmd/cli/cli.js`，
# 且裸跑只打 help（stdio 服务必须 `serve`）。旧入口现在是坏的 ESM（`require is not defined`
# in ES module scope，main.js:1194），照旧路径起进程只会得到 "stdout closed (EOF)"。
# 只在本 lane 的 shim 里换入口：`.fist-polish-20260926/pfist.py` 是已收口 lane 的共用件，
# 不在本环半径里改它。
SERVER_JS = r"E:\IDEProjects\AI\FIST-Mbt\_build\js\debug\build\cmd\cli\cli.js"


class Client(pfist.Client):
    """同一条协议，只换进程 argv（其余 _send/_recv/call/close 全部沿用父类）。"""

    def __init__(self, timeout: int = 180):
        if not os.path.exists(SERVER_JS):
            sys.exit(f"[lfist] missing server build: {SERVER_JS}")
        if os.path.exists(pfist.PATCH_SCRIPT):
            subprocess.run([sys.executable, pfist.PATCH_SCRIPT],
                           cwd=os.path.dirname(os.path.dirname(pfist.PATCH_SCRIPT)),
                           capture_output=True)
        self.proc = subprocess.Popen(
            ["node", SERVER_JS, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=pfist.SERVER_CWD,
            encoding="utf-8", errors="replace")
        self.timeout = timeout
        self._id = 0
        self._line_q = None
        self._last_recv = ""


utc_now = pfist.utc_now
