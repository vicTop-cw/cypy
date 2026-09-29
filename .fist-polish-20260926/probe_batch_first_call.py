#!/usr/bin/env python3
"""Attribute the `--batch` first-call timeout: server-side or client-side?

Measured on the raw frame stream (not through pfist.Client), with a wall-clock deadline per call,
so the three failure shapes pfist.py collapses into one message stay separate:
  EOF            -> stdout closed with no matching frame (process died / pipe broken)
  unmatched-only -> lines arrived but none matched the id (their kinds are reported)
  deadline       -> no line at all before the deadline (blocking readline in pfist hides this)

Windows: `select` cannot poll pipes, so lines are pulled by a daemon reader thread into a Queue.

All four scenarios are side-effect-free:
  A read-only `bug_list` as the FIRST tools/call after an UNREAD initialize (the --batch shape)
  B same, but with the initialize response consumed first
  C `report_bug` with a payload the server *rejects* (absolute project_dir) as first call
  D replay of `pfist.py --batch` with that same rejected payload, capturing its verbatim text

Run: python .fist-polish-20260926/probe_batch_first_call.py
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

SERVER_JS = r"E:\IDEProjects\AI\FIST-Mbt\_build\js\debug\build\cmd\main\main.js"
SERVER_CWD = r"E:\IDEProjects\AI\Cypy"
ROOT = r"E:\IDEProjects\AI\Cypy"
HERE = os.path.join(ROOT, ".fist-polish-20260926")
PROTOCOL = "2026-07-28"
CLIENT_INFO = {"name": "cypy-polish-probe", "version": "1"}
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
}
DEADLINE_S = 25.0
_EOF = object()


def write_frame(proc, mid, method, params):
    params = dict(params)
    params["_meta"] = META
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method,
                                 "params": params}, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def reader(proc, out):
    while True:
        line = proc.stdout.readline()
        if not line:
            out.put(_EOF)
            return
        out.put(line)


def drain_until(pred, q, deadline):
    """Return (frame, n_lines, kinds, kind) with kind in matched / EOF / deadline."""
    n, kinds = 0, []
    while True:
        left = deadline - time.time()
        if left <= 0:
            return None, n, kinds, "deadline"
        try:
            item = q.get(timeout=left)
        except queue.Empty:
            return None, n, kinds, "deadline"
        if item is _EOF:
            return None, n, kinds, "EOF"
        n += 1
        try:
            frame = json.loads(item.strip())
        except (json.JSONDecodeError, TypeError):
            kinds.append("non-json")
            continue
        kinds.append(f"id={frame.get('id')}" + (":error" if "error" in frame else ":result"))
        if pred(frame):
            return frame, n, kinds, "matched"


def scenario(name, consume_initialize, tool_args):
    proc = subprocess.Popen(["node", SERVER_JS], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=SERVER_CWD, encoding="utf-8", errors="replace", bufsize=1)
    q = queue.Queue()
    threading.Thread(target=reader, args=(proc, q), daemon=True).start()
    t0 = time.time()
    write_frame(proc, 1, "initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                        "clientInfo": CLIENT_INFO})
    init_note = "unread (left in the buffer, exactly like pfist.py main())"
    if consume_initialize:
        _, n, kinds, kind = drain_until(lambda f: f.get("id") == 1, q,
                                        time.time() + DEADLINE_S)
        init_note = f"consumed kind={kind} lines={n} {kinds} in {time.time()-t0:.2f}s"
    t_send = time.time()
    write_frame(proc, 2, "tools/call", {"name": tool_args[0], "arguments": tool_args[1]})
    frame, n, kinds, kind = drain_until(lambda f: f.get("id") == 2, q, t_send + DEADLINE_S)
    elapsed = time.time() - t_send
    alive = proc.poll() is None
    stderr_tail = ""
    if not alive:
        stderr_tail = (proc.stderr.read() or "")[-500:]
    proc.terminate()
    text = ""
    if frame and "result" in frame:
        content = (frame["result"] or {}).get("content") or []
        text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
    return {
        "scenario": name, "first_call": kind, "lines": n, "frame_kinds": kinds,
        "elapsed_s": round(elapsed, 2), "deadline_s": DEADLINE_S,
        "server_alive_after": alive, "initialize": init_note,
        "result_text_head": text[:200],
        "error": (frame or {}).get("error"),
        "stderr_tail": stderr_tail,
    }


def main():
    rejected = {
        "project_dir": r"E:\IDEProjects\AI\Cypy",
        "summary": "probe: absolute project_dir must be rejected",
        "detail": "probe only — expected bug_project_dir_ok rejection, no ledger write",
        "severity": "low", "publish_task": False,
    }
    ledger = os.path.join(ROOT, "memory", "bugs.md")
    before = open(ledger, encoding="utf-8").read().count("\n## BUG-")
    db = os.path.join(ROOT, "fist-mbt.db")
    db_before = (os.path.getmtime(db), os.path.getsize(db))

    results = [
        scenario("A bug_list first call after UNREAD initialize", False,
                 ("bug_list", {"project_dir": ".", "namespace": "cypy-polish-20260926"})),
        scenario("B bug_list first call after CONSUMED initialize", True,
                 ("bug_list", {"project_dir": ".", "namespace": "cypy-polish-20260926"})),
        scenario("C rejected report_bug as first call after UNREAD initialize", False,
                 ("report_bug", dict(rejected, now=datetime.now(
                     timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))),
    ]

    batch_file = os.path.join(HERE, "probe_batch_payload.json")
    json.dump([{"tool": "report_bug", "args": rejected}],
              open(batch_file, "w", encoding="utf-8"), ensure_ascii=False)
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "pfist.py"), "--batch", batch_file],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=400)
    results.append({
        "scenario": "D pfist.py --batch replay (rejected report_bug payload)",
        "rc": p.returncode, "elapsed_s": round(time.time() - t0, 2),
        "stdout_head": (p.stdout or "")[:500], "stderr_head": (p.stderr or "")[:300],
    })

    after = open(ledger, encoding="utf-8").read().count("\n## BUG-")
    db_after = (os.path.getmtime(db), os.path.getsize(db))
    out = {
        "stamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server_js": {"mtime": os.path.getmtime(SERVER_JS), "size": os.path.getsize(SERVER_JS)},
        "cypy_ledger_bugs_before": before, "cypy_ledger_bugs_after": after,
        "cypy_db_before": list(db_before), "cypy_db_after": list(db_after),
        "cypy_db_untouched": db_before == db_after,
        "results": results,
    }
    json.dump(out, open(os.path.join(HERE, "probe_batch_first_call.out.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in results:
        print(f"{r['scenario'][:52]:54s} {r.get('first_call') or 'rc=' + str(r.get('rc')):9s} "
              f"lines={r.get('lines')} {r.get('elapsed_s')}s")
    print(f"ledger {before} -> {after}; db_untouched={out['cypy_db_untouched']}")


if __name__ == "__main__":
    main()
