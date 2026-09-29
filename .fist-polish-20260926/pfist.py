#!/usr/bin/env python3
"""Polish-round driver (ns=cypy-polish-20260926) — isolated from the cron-cypy lane.

Differences from scripts/fist.py (which stays owned by the production lane):
  * SERVER_CWD is the Cypy root, so the task DB is <root>/fist-mbt.db (a *new* file,
    not E:/IDEProjects/AI/FIST-Mbt/fist-mbt.db) and `project_dir="."` resolves to the
    Cypy root for every tool family -- which is the only form `report_bug` accepts
    (bug tools reject absolute paths while memory tools accept them; see BUG-5).
  * every write call gets an explicit `now` stamped from the real UTC clock of this
    process, read immediately before the call. Never a synthetic monotone counter:
    fabricated clocks wrote future timestamps into the production ledger this morning.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_EOF = object()

SERVER_JS = r"E:\IDEProjects\AI\FIST-Mbt\_build\js\debug\build\cmd\main\main.js"
SERVER_CWD = r"E:\IDEProjects\AI\Cypy"           # decision recorded in the polish report
PATCH_SCRIPT = r"E:\IDEProjects\AI\FIST-Mbt\scripts\patch_esm_main.py"
NAMESPACE = "cypy-polish-20260926"
PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "cypy-polish", "version": "1.0.0"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Client:
    def __init__(self, timeout: int = 180):
        if not os.path.exists(SERVER_JS):
            sys.exit(f"[pfist] missing server build: {SERVER_JS}")
        if os.path.exists(PATCH_SCRIPT):
            subprocess.run([sys.executable, PATCH_SCRIPT], cwd=os.path.dirname(
                os.path.dirname(PATCH_SCRIPT)), capture_output=True)
        self.proc = subprocess.Popen(
            ["node", SERVER_JS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=SERVER_CWD, encoding="utf-8", errors="replace")
        self.timeout = timeout
        self._id = 0
        self._line_q = None
        self._last_recv = ""

    def _lines(self):
        """Lazy reader thread: readline() must not block past the deadline.

        Windows cannot select() on pipes, so a daemon thread owns the single reader.
        """
        if self._line_q is None:
            self._line_q = queue.Queue()

            def pump():
                while True:
                    line = self.proc.stdout.readline()
                    self._line_q.put(line if line else _EOF)
                    if not line:
                        return
            threading.Thread(target=pump, daemon=True).start()
        return self._line_q

    def _send(self, method, params):
        self._id += 1
        mid = self._id
        params = dict(params)
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
        }
        try:
            self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method,
                                              "params": params}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except OSError as exc:
            # a dead server used to surface as a raw traceback here, which made the
            # "server exited" branch below unreachable -- report it as a result instead
            self._last_recv = f"write failed: {exc}"
            return None
        return mid

    def _recv(self, mid, timeout):
        import time
        deadline = time.time() + timeout
        skipped = []
        while True:
            left = deadline - time.time()
            if left <= 0:
                self._last_recv = f"deadline after {timeout}s (skipped: {skipped or 'none'})"
                return None
            try:
                line = self._lines().get(timeout=left)
            except queue.Empty:
                self._last_recv = f"deadline after {timeout}s, zero lines (skipped: {skipped or 'none'})"
                return None
            if line is _EOF:
                self._last_recv = "stdout closed (EOF)"
                return None
            try:
                frame = json.loads(line.strip())
            except json.JSONDecodeError:
                skipped.append("non-json")
                continue
            if frame.get("id") == mid:
                self._last_recv = "matched"
                return frame
            skipped.append(f"id={frame.get('id')}"
                           + (":error" if "error" in frame else ":result"))

    def call(self, tool, arguments, timeout=None):
        arguments = dict(arguments)
        client_timeout = arguments.pop("_timeout", None)
        arguments.setdefault("namespace", NAMESPACE)
        arguments.setdefault("project_dir", ".")
        if tool not in ("list", "get", "bug_list", "call_log", "issue_scan", "board_ascii",
                        "output_validate", "heartbeat") and "now" not in arguments:
            arguments["now"] = utc_now()          # real clock, per-call, never synthetic
        mid = self._send("tools/call", {"name": tool, "arguments": arguments})
        frame = None if mid is None else self._recv(
            mid, client_timeout or timeout or self.timeout)
        if frame is None:
            if self.proc.poll() is not None:
                return {"__error__": f"server exited ({self.proc.returncode}) during {tool}: "
                        + (self.proc.stderr.read() or "")[-1200:]}
            # EOF / deadline / unmatched-frames stay distinguishable: collapsing them into one
            # message is what made the batch timeout undiagnosable this round.
            return {"__error__": f"no response from {tool}: {self._last_recv}"}
        if "error" in frame:
            return {"__error__": frame["error"]}
        content = (frame.get("result") or {}).get("content") or []
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"__text__": text}

    def close(self):
        for kill in (self.proc.terminate, self.proc.kill):
            try:
                kill()
                self.proc.wait(timeout=5)
                return
            except Exception:
                continue


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    c = Client()
    c._send("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                           "clientInfo": CLIENT_INFO})
    if argv[0] == "list-tools":
        frame = c._recv(c._send("tools/list", {}), 60)
        tools = (frame or {}).get("result", {}).get("tools", [])
        names = sorted(t["name"] for t in tools)
        print("\n".join(names))
        print(f"# {len(names)} tools; cwd={SERVER_CWD}", file=sys.stderr)
        c.close()
        return 0
    if argv[0] == "--batch":
        calls = json.load(open(argv[1], encoding="utf-8"))
        results = []
        failed = False
        for spec in calls:
            out = c.call(spec["tool"], spec.get("args", {}))
            results.append({"tool": spec["tool"], "result": out})
            if isinstance(out, dict) and "__error__" in out:
                failed = True
                break
        c.close()
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 1 if failed else 0        # the single-call path already did this; batch did not
    out = c.call(argv[0], json.loads(argv[1]) if len(argv) > 1 else {})
    c.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if isinstance(out, dict) and "__error__" in out else 0


if __name__ == "__main__":
    sys.exit(main())
