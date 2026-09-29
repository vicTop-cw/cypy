#!/usr/bin/env python3
"""Exercise FIST-Mbt's `output_validate` (the "修复单交付物硬门") over this round's tickets.

Why: the 12 fix tickets went claim → execute → submit → verify, but §四 lists output_validate as
the hard gate on deliverables, and this round never called it — so two things are unproven:
(a) whether the recorded deliverables still hold in the working tree (the fix marker is really in
    the file, the regression really is in tests/), and
(b) whether the gate has teeth at all (does it reject a missing file / a key that isn't there?).
If (b) fails, that is a FIST-Mbt defect and issue_up says it gets booked, not silently worked around.

Artifacts are derived from each ticket's own recorded `deliverable` text (close_fixes*.out.json),
never typed from memory. `stage=probe` does schema + one ticket so a wrong payload shape is caught
before 12+ calls go out.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
from pfist import Client, utc_now  # noqa: E402

BUGS_FIXED = [f"BUG-{i}" for i in range(1, 13)]
REG = "tests/test_polish_20260926.py"


def deliverables():
    out = {}
    for name in ("close_fixes.out.json", "close_fixes2.out.json", "close_fixes3.out.json",
                 "close_fixes4.out.json"):
        for e in json.load(open(os.path.join(HERE, name), encoding="utf-8")):
            tag = e["tag"]
            if not re.fullmatch(r"BUG-\d+:execute", tag):
                continue
            bid = tag.split(":")[0]
            r = e["result"]
            dl = r.get("deliverable") if isinstance(r, dict) else None
            if dl:
                out[bid] = {"task_id": r.get("id"), "deliverable": dl}
    missing = [b for b in BUGS_FIXED if b not in out]
    if missing:
        sys.exit(f"[probe_output_validate] 这些单没有 recorded deliverable：{missing}")
    return out


def artifacts_for(bid, dl):
    """(path, check_key) pairs read straight out of the ticket's own deliverable text."""
    line = next((l for l in dl.splitlines() if l.startswith("改动文件")), "")
    paths = [p for p in re.findall(r"[\w./-]+\.py", line)]
    # keys may be quoted anywhere in the deliverable (BUG-1's line has no backticks at all)
    spans = [s.strip() for s in re.findall(r"`([^`\n]+)`", dl) if s.strip()]
    arts, flagged = [], []
    for cand in paths:
        p = os.path.join(ROOT, cand.replace("/", os.sep))
        if not os.path.isfile(p) or "{" in cand:
            flagged.append(f"{cand}: 花括号glob或不在盘上")
            continue
        body = open(p, encoding="utf-8", errors="replace").read()
        key = next((s for s in spans if s != cand and len(s) > 6 and s in body), "")
        art = {"path": cand, "invariant": "本单交付物声称的改动确实落在该文件里"}
        if key:
            art["check_key"] = key
        else:
            flagged.append(f"{cand}: 交付物里没有可在该文件命中的 marker，只判存在/非空")
        arts.append(art)
    tests = re.findall(r"test_bug\d+_\w+", dl)
    if tests:
        body = open(os.path.join(ROOT, REG.replace("/", os.sep)), encoding="utf-8").read()
        hit = next((t for t in tests if f"def {t}" in body), "")
        if hit:
            arts.append({"path": REG, "check_key": hit,
                         "invariant": "锁死本单缺陷的回归用例确实存在于回归文件里"})
    return arts, flagged, spans


def evidence_for(bid, dl, spans):
    """L1 evidence: the ticket's own RED/GREEN lines plus a real log artifact it cites."""
    lines = [l.strip() for l in dl.splitlines()
             if l.strip().startswith(("RED", "GREEN", "开关对照", "取证探针"))]
    logs = [s for s in spans if ".log" in s or ".out" in s or ".py" in s]
    return "；".join(lines + [f"证据文件: {', '.join(logs)}" if logs else ""])



def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "probe"
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-ovprobe", "version": "1"}})
    mid = c._send("tools/list", {})
    lst = c._recv(mid, 120) or {}
    tools = (lst.get("result") or {}).get("tools") or []
    schema = next((t for t in tools if t.get("name") == "output_validate"), None)
    if not schema:
        sys.exit("[probe_output_validate] tools/list 里没有 output_validate")
    json.dump(schema, open(os.path.join(HERE, "probe_output_validate_schema.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)
    props = list((schema.get("inputSchema") or {}).get("properties") or {})
    required = (schema.get("inputSchema") or {}).get("required") or []
    print("output_validate properties:", props)
    print("output_validate required  :", required)

    dls = deliverables()
    targets = BUGS_FIXED[:1] if stage == "probe" else BUGS_FIXED
    results = []
    for bid in targets:
        tid = dls[bid]["task_id"]
        arts, flagged, spans = artifacts_for(bid, dls[bid]["deliverable"])
        ev = evidence_for(bid, dls[bid]["deliverable"], spans)
        if not arts:
            results.append({"bug": bid, "task": tid, "skipped": "取不到可用 artifacts",
                            "flagged": flagged})
            continue
        args = {"task_id": tid, "artifacts": arts, "evidence": ev, "require_evidence": True,
                "project_dir": ".", "namespace": "bugs", "now": utc_now()}
        rep = c.call("output_validate", args, timeout=90)
        entry = {"bug": bid, "task": tid, "artifacts": arts, "flagged": flagged,
                 "evidence_len": len(ev), "reply": rep}
        if stage != "probe":
            entry["neg_missing_file"] = c.call("output_validate", {
                **{k: v for k, v in args.items() if k != "now"}, "now": utc_now(),
                "artifacts": [{"path": "cypyc/does_not_exist_zzz.py",
                               "check_key": "whatever", "invariant": "不存在的产物必须被拒"}],
                "evidence": ev}, timeout=90)
            entry["neg_bad_key"] = c.call("output_validate", {
                **{k: v for k, v in args.items() if k != "now"}, "now": utc_now(),
                "artifacts": [{"path": REG, "check_key": "test_zzz_not_anywhere_in_repo",
                               "invariant": "文件里没有该串必须被拒"}],
                "evidence": ev}, timeout=90)
            entry["neg_no_evidence"] = c.call("output_validate", {
                **{k: v for k, v in args.items() if k != "now"}, "now": utc_now(),
                "evidence": ""}, timeout=90)
        results.append(entry)
        print(f"--- {bid} {tid} arts={len(arts)} ev={len(ev)}: "
              f"{json.dumps(rep, ensure_ascii=False)[:600]}")
        if stage != "probe":
            for k in ("neg_missing_file", "neg_bad_key", "neg_no_evidence"):
                print(f"    {k}: {json.dumps(results[-1][k], ensure_ascii=False)[:320]}")
    c.close()
    json.dump({"schema": schema, "stage": stage, "results": results},
              open(os.path.join(HERE, f"probe_output_validate_{stage}.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=2)
    print("saved:", f"probe_output_validate_{stage}.json", "entries:", len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
