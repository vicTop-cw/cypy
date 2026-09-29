#!/usr/bin/env python3
"""Re-probe `output_validate` with the *documented* artifact fields.

First pass used `check_key` + `invariant` on file artifacts; the tool's own description says file
artifacts take {path, contains?, not_contains?, min_chars?} and that `check_key` only references
`external_results`. So the first pass proved nothing about the gate — my parameter names were
wrong (the classic self-inflicted "the tool ignores scope" case). This run answers two questions
with paired positive/negative controls:
  1. do contains / not_contains / min_chars / check_key actually bind? (they must fail when violated)
  2. what happens to an *unknown* field name — hard-gate degraded to existence-only, or rejected?
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
from pfist import Client, utc_now  # noqa: E402

REG = "tests/test_polish_20260926.py"
NOGIL = "cypy_bridge/nogil.py"
PRESENT = "def test_bug12_gilstate_exit_does_not_replace_user_exception"
ABSENT = "def test_zzz_definitely_not_in_this_repo"
MARK = "if self._released: self.acquire()"


def brief(rep):
    if not isinstance(rep, dict):
        return {"raw": str(rep)[:200]}
    return {"verdict": rep.get("verdict"), "layer": rep.get("evidence_layer"),
            "passed": rep.get("passed"), "failed": rep.get("failed"),
            "checks": [{"a": c.get("artifact"), "ok": c.get("ok"),
                        "d": (c.get("detail") or "")[:120]} for c in rep.get("checks") or []],
            "note": (rep.get("note") or "")[:160], "err": rep.get("__error__")}


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-ovprobe2", "version": "1"}})
    cases = []

    def run(name, artifacts, expect, **extra):
        args = {"artifacts": artifacts, "project_dir": ".", "now": utc_now(), **extra}
        rep = c.call("output_validate", args, timeout=90)
        got = rep.get("verdict") if isinstance(rep, dict) else "error"
        cases.append({"case": name, "expect": expect, "got": got,
                      "agree": got == expect, "artifacts": artifacts,
                      "extra": {k: v for k, v in extra.items() if k != "now"},
                      "reply": brief(rep)})
        print(f"[{'OK ' if got == expect else 'DIFF'}] {name:34s} expect={expect:5s} got={got}")
        for ch in cases[-1]["reply"].get("checks", []):
            print(f"        {ch['a']} ok={ch['ok']} :: {ch['d']}")
        if cases[-1]["reply"].get("note"):
            print(f"        note: {cases[-1]['reply']['note']}")

    run("contains 命中", [{"path": REG, "contains": PRESENT}], "pass")
    run("contains 不命中(必须 fail)", [{"path": REG, "contains": ABSENT}], "fail")
    run("not_contains 违例(必须 fail)", [{"path": NOGIL, "not_contains": MARK}], "fail")
    run("not_contains 满足", [{"path": NOGIL, "not_contains": ABSENT}], "pass")
    run("min_chars 过大(必须 fail)", [{"path": NOGIL, "min_chars": 10 ** 9}], "fail")
    run("min_chars 合理", [{"path": NOGIL, "min_chars": 10}], "pass")
    run("external check_key ok", [{"check_key": "pytest"}], "pass",
        external_results={"pytest": {"ok": True, "stdout": "24 passed"}})
    run("external check_key fail(必须 fail)", [{"check_key": "pytest"}], "fail",
        external_results={"pytest": {"ok": False, "stdout": "1 failed"}})
    run("external check_key 缺失(必须 fail)", [{"check_key": "nope"}], "fail",
        external_results={"pytest": {"ok": True}})
    run("未知字段名 contans(拼错)", [{"path": REG, "contans": ABSENT}], "fail")
    run("未知字段名 invariant", [{"path": REG, "invariant": "必须包含 " + ABSENT}], "fail")
    run("空 artifacts 数组", [], "fail")
    run("path 缺失只给 contains", [{"contains": PRESENT}], "fail")
    c.close()
    json.dump(cases, open(os.path.join(HERE, "probe_output_validate2.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    diff = [x["case"] for x in cases if not x["agree"]]
    print(f"\ncases={len(cases)} 与预期不符={len(diff)} {diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
