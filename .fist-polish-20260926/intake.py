#!/usr/bin/env python3
"""Idempotent bug intake for the polish round.

Why not `pfist.py --batch`: the first batch fired a `report_bug` whose response frame
never came back ("no response from report_bug within timeout") even though the same
payload succeeds in ~0.2s when sent alone. A blind retry would duplicate a bug that had
in fact been written, so every fire is preceded by a `bug_list` reconciliation on the
summary text, and a failed call reconnects before the next one.

Outputs .fist-polish-20260926/intake_map.json  ->  [{bug_id, task_id, summary}]
Exit 0 only when all payloads are present in the ledger.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOADS = json.load(open(os.path.join(HERE, "bugs_batch.json"), encoding="utf-8"))


def bug_rows(c):
    out = c.call("bug_list", {})
    return (out or {}).get("bugs") or []


def summary_of(row):
    return (row.get("summary") or row.get("title") or "").strip()


def bug_id_of(row):
    # `report_bug` answers with `bug_id` but `bug_list` rows call the same thing `id`.
    return row.get("bug_id") or row.get("id")


def main():
    c = Client(timeout=90)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake", "version": "1"}})
    existing = {summary_of(r) for r in bug_rows(c)}
    mapping, failures = [], []

    for idx, spec in enumerate(PAYLOADS, start=1):
        args = dict(spec["args"])
        summary = args["summary"].strip()
        if summary in existing:
            row = next((r for r in bug_rows(c) if summary_of(r) == summary), {})
            mapping.append({"bug_id": bug_id_of(row), "task_id": row.get("task_id"),
                            "summary": summary, "fired": False, "note": "already in ledger"})
            continue
        if c.proc.poll() is not None:
            c.close()
            c = Client(timeout=90)
            c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                                   "clientInfo": {"name": "cypy-polish-intake", "version": "1"}})
        out = c.call("report_bug", args, timeout=60)
        if isinstance(out, dict) and ("__error__" in out or "bug_id" not in out):
            failures.append({"index": idx, "summary": summary, "result": out})
            continue
        mapping.append({"bug_id": out.get("bug_id"), "task_id": out.get("task_id"),
                        "summary": summary, "fired": True, "note": ""})
        existing.add(summary)

    after = bug_rows(c)
    c.close()
    json.dump({"payloads": len(PAYLOADS), "mapping": mapping, "failures": failures,
               "ledger_total": len(after)},
              open(os.path.join(HERE, "intake_map.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']}\t{m['task_id']}\t{'fired' if m['fired'] else m['note']}\t{m['summary'][:70]}")
    for f in failures:
        print("FAILED", f["index"], f["summary"][:70], json.dumps(f["result"], ensure_ascii=False)[:200])
    missing = [s["args"]["summary"].strip() for s in PAYLOADS
               if s["args"]["summary"].strip() not in {summary_of(r) for r in after}]
    print(f"ledger_total={len(after)} mapping={len(mapping)} failures={len(failures)} missing={len(missing)}")
    for m in missing:
        print("MISSING:", m[:70])
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
