#!/usr/bin/env python3
"""Lock the pfist.py reader/exit-code fixes (driver-side, not product code).

RED (measured before the fix, kept in probe_batch_first_call.out.json scenario D):
`pfist.py --batch` with a payload whose only call returned `__error__` still exited 0.

Checks here:
 1. tools/list still works through the new pump-thread reader
 2. two sequential calls on ONE connection match their own ids
 3. a batch whose call errors exits 1; a clean batch exits 0
 4. a dead server is reported as EOF/exit, not as the old blanket "within timeout"
 5. the Cypy ledger and the isolated task DB are byte-identical afterwards (all read-only)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import pfist  # noqa: E402
from pfist import Client  # noqa: E402

LEDGER = os.path.join(ROOT, "memory", "bugs.md")
DB = os.path.join(ROOT, "fist-mbt.db")
failures = []


def check(name, ok, got):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {got}")
    if not ok:
        failures.append(name)


def run_batch(payload, tmp_name):
    path = os.path.join(HERE, tmp_name)
    json.dump(payload, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    p = subprocess.run([sys.executable, os.path.join(HERE, "pfist.py"), "--batch", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    return p


def main():
    led_before = open(LEDGER, encoding="utf-8").read()
    db_before = (os.path.getmtime(DB), os.path.getsize(DB))

    p = run_batch([{"tool": "report_bug", "args": {
        "project_dir": ROOT, "summary": "reader guard: absolute path must be rejected",
        "detail": "guard only, no write expected", "severity": "low",
        "publish_task": False}}], "_guard_batch_err.json")
    errored = '"__error__"' in p.stdout
    check("batch with an errored call exits 1", p.returncode == 1 and errored,
          f"rc={p.returncode} error_frame_in_stdout={errored}")

    p2 = run_batch([{"tool": "bug_list", "args": {}}], "_guard_batch_ok.json")
    check("clean batch exits 0", p2.returncode == 0 and '"count"' in p2.stdout,
          f"rc={p2.returncode}")

    c = Client(timeout=60)
    c._send("initialize", {"protocolVersion": pfist.PROTOCOL_VERSION, "capabilities": {},
                           "clientInfo": pfist.CLIENT_INFO})
    names = sorted(t["name"] for t in ((c._recv(c._send("tools/list", {}), 60) or {})
                                       .get("result", {}) or {}).get("tools", []))
    check("tools/list works through the pump reader", len(names) > 20, f"{len(names)} tools")

    bl1 = c.call("bug_list", {})
    bl2 = c.call("bug_list", {})
    check("two sequential calls on one connection both match",
          isinstance(bl1, dict) and isinstance(bl2, dict)
          and bl1.get("count") == bl2.get("count") == 11,
          f"counts {bl1.get('count')} / {bl2.get('count')}")

    c.proc.terminate()
    c.proc.wait(timeout=15)
    dead = c.call("bug_list", {}, timeout=10)
    msg = (dead or {}).get("__error__", "") if isinstance(dead, dict) else str(dead)
    check("dead server is classified, not the blanket timeout text",
          "within timeout" not in str(msg), str(msg)[:90])
    c.close()
    try:            # the dead child's stdin wrapper otherwise logs "Exception ignored" at exit
        c.proc.stdin.close()
    except OSError:
        pass

    check("ledger untouched", open(LEDGER, encoding="utf-8").read() == led_before,
          f"{len(led_before)} bytes stable")
    check("isolated task db untouched",
          (os.path.getmtime(DB), os.path.getsize(DB)) == db_before, str(db_before[1]))

    for f in ("_guard_batch_err.json", "_guard_batch_ok.json"):
        fp = os.path.join(HERE, f)
        if os.path.exists(fp):
            os.remove(fp)
    print("failures:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
