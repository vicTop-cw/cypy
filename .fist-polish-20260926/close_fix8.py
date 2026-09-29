#!/usr/bin/env python3
"""Close the 8th fix ticket (BUG-8 -> T0r13) and merge results into close_fixes.out.json.

close_fixes.py stays untouched (it re-fires the 7 already-closed tickets and the archived T0);
this driver only walks the one new task, then reports its parent's state verbatim.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = json.load(open(os.path.join(HERE, "intake_map.json"), encoding="utf-8"))["mapping"]
POLISHER = "cypy-polisher"

ROW = next(r for r in MAP if r["bug_id"] == "BUG-8")
TID = ROW["task_id"]

DELIVERABLE = (
    f"BUG-8 -> {TID}\n"
    "改动文件：cypyc/parser/macro_expander.py (_reparse_code 的 except 分支 + 模块级 import sys)\n"
    "新增回归：tests/test_polish_20260926.py::test_bug8_macro_reparse_degradation_is_reported\n"
    "修复口径：降级语义不变（仍返回 BacktickBlock，23 条既有 macro 用例不动），只补一条点名"
    "行/列/原始代码/底层异常的 stderr 告警，使『整条宏语句从输出消失』可被看到。\n"
    "RED：修复前 `pytest tests/test_polish_20260926.py -q -k bug8` → 1 failed，capsys.err == ''；\n"
    "GREEN：修复后同文件 16 passed，且 tests/test_macro_expansion.py 23 passed（合计 39 passed）。"
)


def main():
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close8", "version": "1"}})
    log = []

    def step(tool, args, tag):
        out = c.call(tool, args)
        log.append({"tag": tag, "tool": tool,
                    "args": {k: v for k, v in args.items() if k != "deliverable"},
                    "result": out})
        return out

    step("claim", {"task_id": TID, "assignee": POLISHER}, f"BUG-8:claim")
    step("execute", {"task_id": TID, "deliverable": DELIVERABLE}, f"BUG-8:execute")
    step("submit", {"task_id": TID}, f"BUG-8:submit")
    step("verify", {"task_id": TID, "verifier": POLISHER}, f"BUG-8:verify")
    parent = step("get", {"task_id": TID}, f"BUG-8:get")
    c.close()

    path = os.path.join(HERE, "close_fixes.out.json")
    prior = json.load(open(path, encoding="utf-8"))
    known = {(e["tag"], e["tool"]) for e in prior}
    merged = prior + [e for e in log if (e["tag"], e["tool"]) not in known]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    for e in log:
        r = e["result"]
        note = (r.get("__error__") or r.get("status") or r.get("ok") or "") \
            if isinstance(r, dict) else str(r)[:80]
        print(f"{e['tag']:16s} {str(note)[:90]}")
    if isinstance(parent, dict):
        print(f"parent={parent.get('parent_id')} status={parent.get('status')}")
    bad = [e for e in log if isinstance(e["result"], dict) and "__error__" in e["result"]]
    print(f"steps={len(log)} errors={len(bad)} merged_rows={len(merged)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
