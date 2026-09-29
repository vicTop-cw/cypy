#!/usr/bin/env python3
"""FIST-Mbt MCP driver for the Cypy pipeline (stdio JSON-RPC).

Usage:
  python scripts/fist.py list-tools          # 握手探针：解不出非空工具清单就非 0 退出
  python scripts/fist.py <tool> '<json-arguments>'
  python scripts/fist.py <tool> --file args.json
  python scripts/fist.py --batch calls.json   # [{"tool":..,"args":{..}}, ...] in one server process

All arguments get `created_by`/`now` defaults injected only when the caller omits
them; nothing else is rewritten, so the FIST audit trail stays attributable.

Protocol note (upstream 0.3.4, MCP 2026-07-28): the handshake is stateless — every
request carries `_meta`, and `initialize` is no longer a method (-32601 "Method not
found: initialize"). The authoritative server artifact is `cmd/cli/cli.js`, which
only serves over stdio when given the `serve` subcommand (bare run prints help).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERVER_JS = os.environ.get(
    "FIST_SERVER_JS",
    r"E:\IDEProjects\AI\FIST-Mbt\_build\js\debug\build\cmd\cli\cli.js")
# 服务进程的工作目录决定任务库落在哪：<SERVER_CWD>/fist-mbt.db 是本项目的账本，
# 不是兄弟仓 FIST-Mbt 的那一份（上游 FIST-Mbt/fist-mbt.db 混进了别的工程的 ns）。
SERVER_CWD = os.environ.get("FIST_SERVER_CWD") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
PATCH_SCRIPT = os.environ.get(
    "FIST_PATCH_SCRIPT",
    r"E:\IDEProjects\AI\FIST-Mbt\scripts\patch_esm_main.py")
# 一次会话只服务一个命名空间/项目根；跨项目复用同一驱动，避免每个项目复制一份脚本。
NAMESPACE = os.environ.get("FIST_NAMESPACE", "cron-cypy")
# `project_dir` 必须相对 SERVER_CWD：服务端对越界的绝对路径直接拒写。
PROJECT_DIR = os.environ.get("FIST_PROJECT_DIR", ".")
PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": os.environ.get("FIST_CLIENT", "cypy-selfdrive"), "version": "1.0.0"}
REQUIRED_TOOLS = ("publish", "claim", "execute", "submit", "verify", "run_check",
                  "omega_verify", "omega_spec_create", "laya_decide", "call_log",
                  "report_bug", "bug_list")


class FistClient:
    def __init__(self, timeout: int = 120):
        if not os.path.exists(SERVER_JS):
            sys.exit(f"[fist] missing server build: {SERVER_JS}\n"
                     f"        run: (cd {os.path.dirname(os.path.dirname(PATCH_SCRIPT))} "
                     f"&& moon build --target js)")
        # `moon build` regenerates the ESM entry without the CJS `require("node:sqlite")`
        # shim, which breaks mizchi/sqlite; the upstream patch script re-injects it (idempotent).
        if os.path.exists(PATCH_SCRIPT):
            subprocess.run([sys.executable, PATCH_SCRIPT],
                           cwd=os.path.dirname(os.path.dirname(PATCH_SCRIPT)),
                           capture_output=True)
        # 裸跑 cli.js 只打 help，stdio 服务必须显式 `serve`。
        self.proc = subprocess.Popen(
            ["node", SERVER_JS, "serve"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=SERVER_CWD, encoding="utf-8", errors="replace",
        )
        self.timeout = timeout
        self._id = 0

    def _send(self, method: str, params: dict) -> int:
        self._id += 1
        msg_id = self._id
        params = dict(params)
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
        }
        frame = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return msg_id

    def _recv(self, msg_id: int, timeout: int):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                return None
            try:
                frame = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if frame.get("id") == msg_id:
                return frame
        return None

    def call(self, tool: str, arguments: dict, timeout: int | None = None):
        arguments = dict(arguments)
        call_timeout = arguments.pop("_timeout", None)
        # `_omit_defaults` 是退出键，不是参数：只发给不声明 namespace/project_dir 的工具
        # （task_plan_deep/laya_decide/loop_create/call_log）时必须关掉注入，
        # 否则服务端按 BUG-23 的口径直接拒收未知键（回执点名「参数名不被接受」）。
        omit_defaults = bool(arguments.pop("_omit_defaults", False)) or bool(
            arguments.pop("_omit_namespace", False))
        if not omit_defaults:
            if "namespace" not in arguments and "ns" not in arguments:
                arguments = {**arguments, "namespace": NAMESPACE}
            if "project_dir" not in arguments:
                arguments = {**arguments, "project_dir": PROJECT_DIR}
        frame = self._recv(self._send("tools/call", {"name": tool, "arguments": arguments}),
                           call_timeout or timeout or self.timeout)
        if frame is None:
            if self.proc.poll() is not None:
                return {"__error__": f"server exited ({self.proc.returncode}) during {tool}: "
                        + (self.proc.stderr.read() or "")[-1500:]}
            return {"__error__": f"no response from {tool} within timeout"}
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
    client = FistClient()
    if argv[0] == "list-tools":
        frame = client._recv(client._send("tools/list", {}), 60)
        err = (frame or {}).get("error")
        tools = (frame or {}).get("result", {}).get("tools", [])
        names = {t.get("name") for t in tools}
        client.close()
        if frame is None or err or not tools:
            print("[fist] handshake FAILED: frame={} error={} tools={}".format(
                "none" if frame is None else "reply", err, len(tools)), file=sys.stderr)
            return 1
        missing = [n for n in REQUIRED_TOOLS if n not in names]
        for t in sorted(tools, key=lambda x: x["name"]):
            print(f"{t['name']}\t{t.get('description', '')[:150]}")
        print(f"# {len(tools)} tools; cwd={SERVER_CWD}; missing={missing}", file=sys.stderr)
        if missing:
            print(f"[fist] required tools absent from this build: {missing}", file=sys.stderr)
            return 1
        return 0

    if argv[0] == "--batch":
        with open(argv[1], encoding="utf-8") as fh:
            calls = json.load(fh)
        results = []
        for spec in calls:
            out = client.call(spec["tool"], spec.get("args", {}))
            results.append({"tool": spec["tool"], "result": out})
            if isinstance(out, dict) and "__error__" in out:
                break
        client.close()
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    tool = argv[0]
    rest = argv[1:]
    arguments = {}
    if rest:
        if rest[0] == "--file":
            with open(rest[1], encoding="utf-8") as fh:
                arguments = json.load(fh)
        else:
            arguments = json.loads(rest[0])
    out = client.call(tool, arguments)
    client.close()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if isinstance(out, dict) and "__error__" in out else 0


if __name__ == "__main__":
    sys.exit(main())
