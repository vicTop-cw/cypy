#!/usr/bin/env python3
"""Dump every raw stdout frame the server emits for a single report_bug call.

The batch driver collapses 'no frame matched my id' into a timeout error, which hides
whether the server crashed, replied to a different id, or sent nothing at all.
"""
import json
import subprocess
import sys
import time

sys.path.insert(0, r"E:\IDEProjects\AI\Cypy\.fist-polish-20260926")
from pfist import SERVER_JS, SERVER_CWD, PATCH_SCRIPT, NAMESPACE, PROTOCOL_VERSION, CLIENT_INFO  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

payload = json.load(open(r"E:\IDEProjects\AI\Cypy\.fist-polish-20260926\bugs_batch.json", encoding="utf-8"))
args = dict(payload[0]["args"])
args.setdefault("namespace", NAMESPACE)
args.setdefault("project_dir", ".")

proc = subprocess.Popen(["node", SERVER_JS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, cwd=SERVER_CWD, encoding="utf-8", errors="replace",
                        bufsize=1)
subprocess.run([sys.executable, PATCH_SCRIPT], capture_output=True)


def send(method, params, mid):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params},
                                ensure_ascii=False) + "\n")
    proc.stdin.flush()


send("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                    "clientInfo": CLIENT_INFO}, 1)
time.sleep(1.0)
send("tools/call", {"name": "report_bug", "arguments": {
    "project_dir": ".",
    "summary": "[probe] .fist-polish-20260926/probe_report_bug.py 单发探测",
    "detail": "诊断 report_bug 无响应：本条为探测写入，可忽略/删除。",
    "severity": "low",
    "publish_task": False,
    "now": "2026-09-26T05:31:00Z",
    "_meta": {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
    }}}, 2)

deadline = time.time() + 45
while time.time() < deadline:
    line = proc.stdout.readline()
    if not line:
        print("EOF on stdout; returncode =", proc.poll(), file=sys.stderr)
        break
    print("FRAME:", line.strip()[:900])
    if proc.poll() is not None:
        break
print("alive?", proc.poll() is None)
err = ""
if proc.poll() is not None:
    err = proc.stderr.read() or ""
print("STDERR tail:", err[-1500:])
proc.kill()
