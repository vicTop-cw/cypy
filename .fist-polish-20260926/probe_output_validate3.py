#!/usr/bin/env python3
"""Decide whether `not_contains` binds, using a marker that is verifiably present.

Previous run's "not_contains 违例" control was invalid: the probe string was written on one line
while the real source splits it across lines 79-80, so `pass` was the *correct* verdict. This
script only uses markers counted in the same process immediately before each call, so the expected
verdict is derived from bytes rather than from memory.

Questions still open after run 2:
  * does not_contains fail when the marker really is there?
  * is an unknown field name (typo `contans`, or the `invariant` we passed in run 1) hard-gated,
    or silently degraded to existence-only?
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
# markers we assert about below; each is counted from the real file before the RPC
NM_EXIT = "def __exit__"
NM_ENTER = "def __enter__"


def count(rel, needle):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read().count(needle)


def brief(rep):
    if not isinstance(rep, dict):
        return {"raw": str(rep)[:200]}
    return {"verdict": rep.get("verdict"), "layer": rep.get("evidence_layer"),
            "passed": rep.get("passed"), "failed": rep.get("failed"),
            "checks": [{"a": c.get("artifact"), "ok": c.get("ok"),
                        "d": (c.get("detail") or "")[:160]} for c in rep.get("checks") or []],
            "note": (rep.get("note") or "")[:200], "err": rep.get("__error__")}


def main() -> int:
    pre = {f"{NOGIL}::{NM_EXIT}": count(NOGIL, NM_EXIT),
           f"{NOGIL}::{NM_ENTER}": count(NOGIL, NM_ENTER),
           f"{REG}::{PRESENT}": count(REG, PRESENT),
           f"{REG}::{ABSENT}": count(REG, ABSENT)}
    for k, v in pre.items():
        print(f"count {k} = {v}")
    if pre[f"{NOGIL}::{NM_EXIT}"] == 0:
        print("缺前提：not_contains 目标串不在文件里，对照无意义")
        return 2

    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-ovprobe3", "version": "1"}})
    cases = []

    def run(name, artifacts, expect, **extra):
        args = {"artifacts": artifacts, "project_dir": ".", "now": utc_now(), **extra}
        rep = c.call("output_validate", args, timeout=90)
        got = rep.get("verdict") if isinstance(rep, dict) else "error"
        cases.append({"case": name, "expect": expect, "got": got, "agree": got == expect,
                      "pre": pre, "artifacts": artifacts,
                      "reply": brief(rep)})
        print(f"[{'OK ' if got == expect else 'DIFF'}] {name:38s} expect={expect:5s} got={got}")
        for ch in cases[-1]["reply"].get("checks", []):
            print(f"        {ch['a']} ok={ch['ok']} :: {ch['d']}")
        if cases[-1]["reply"].get("note"):
            print(f"        note: {cases[-1]['reply']['note']}")

    run("not_contains 真违例(必 fail)", [{"path": NOGIL, "not_contains": NM_EXIT}], "fail")
    run("not_contains 真满足", [{"path": NOGIL, "not_contains": ABSENT}], "pass")
    run("not_contains + contains 混合",
        [{"path": NOGIL, "contains": NM_ENTER, "not_contains": NM_EXIT}], "fail")
    run("未知字段 contans(拼错)", [{"path": REG, "contans": ABSENT}], "fail")
    run("未知字段 invariant", [{"path": REG, "invariant": "必须包含 " + ABSENT}], "fail")
    run("未知字段 + 合法 contains 同时给",
        [{"path": REG, "contains": PRESENT, "invariant": ABSENT}], "pass")
    c.close()
    json.dump(cases, open(os.path.join(HERE, "probe_output_validate3.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    diff = [x["case"] for x in cases if not x["agree"]]
    print(f"\ncases={len(cases)} 与预期不符={len(diff)} {diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
