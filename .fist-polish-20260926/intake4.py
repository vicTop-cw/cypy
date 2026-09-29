#!/usr/bin/env python3
"""Fourth-pass intake: GilState.__exit__ replaces the user's exception with NoGilError.

Same contract as intake.py / intake2.py / intake3.py — server cwd is the Cypy root so
`project_dir="."` writes `memory/bugs.md`; reconcile by `summary` first so a re-run never
double-books; read the id with the `bug_id`-or-`id` fallback (BUG-13 on FIST-Mbt's side).

Filed only because the repro is deterministic: `.fist-polish-20260926/repro_sweep4_nogil.py`
printed `escaped exception type = NoGilError`, and the locking test was written and run RED
against the unfixed source first
(`pytest_fourth_sweep_red.log` → 1 failed, 1 passed, 22 deselected).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

FINDINGS = [
    {
        "summary": "[error-masking] cypy_bridge/nogil.py:73 GilState.__exit__ 无条件 acquire，"
                   "with 体内提前归还 GIL 后再抛用户异常时，退出路径用 NoGilError('GIL is not "
                   "released') 顶掉用户异常——同一族的嵌套覆盖问题本模块已在 NoGilContext 修过，"
                   "GilState 这条退出路径漏修",
        "severity": "medium",
        "detail": (
            "现象: GilState.__exit__（:73-76）直接 self.acquire()，而 acquire()（:58-59）在 "
            "_released 已为 False 时抛 NoGilError。因此 "
            "`with GilState() as st: st.acquire(); raise ValueError(...)` 这种「区域内提前归还 "
            "GIL」的合法写法，退出时 __exit__ 抛出的 NoGilError 会替换正在传播的 ValueError，"
            "用户既拿不到自己的异常类型，也看不到自己的消息；异常链里只留下 'GIL is not released'。\n"
            "复现（确定性，零依赖）: python .fist-polish-20260926/repro_sweep4_nogil.py "
            "→ `escaped exception type = NoGilError`、`[repro A] ... REPRODUCED`。"
            "同脚本的 B 项（nogil_thread 一次性调用是否泄漏执行器线程）实测没有复现——"
            "12 次调用只余 1 个临时 worker，会被回收，故 B 按误报不入账。\n"
            "锁死回归: tests/test_polish_20260926.py::"
            "test_bug12_gilstate_exit_does_not_replace_user_exception（改前红："
            "AssertionError: GIL 退出路径把用户的 ValueError 换成了 NoGilError）+ ::"
            "test_bug12_gilstate_exit_still_restores_state（防过度修复：退出时仍须把 "
            "released 复位，改前即绿，改后仍绿）。\n"
            "影响: cypy_bridge 公开导出 GilState/release_gil/acquire_gil（__init__.py:119-121、"
            "224-226），任何用它包 CPU 密集段并在段内手动归还 GIL 的调用方，报错信息都会指向 "
            "nogil 本身而不是真正的失败点，排查方向被带偏；与本轮 BUG-4/BUG-9「异常在兜底路径"
            "变形或消失」同族，但这条不是静默吞掉，是替换。\n"
            "建议: __exit__ 里改为 `if self._released: self.acquire()`，保持 return False "
            "（不吞任何异常），不改 release/acquire 自身的报错语义，也不改 nogil 的对外契约。"
        ),
    },
]


def bug_id_of(row):
    return row.get("bug_id") or row.get("id")


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake4", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {}
    for r in before:
        known[(r.get("summary") or "").strip()] = bug_id_of(r)
    mapping, failures = [], []
    for spec in FINDINGS:
        summary = spec["summary"]
        if summary in known:
            mapping.append({"bug_id": known[summary], "task_id": None,
                            "summary": summary, "fired": False, "note": "already in ledger"})
            continue
        out = c.call("report_bug", {
            "project_dir": ".", "summary": summary, "detail": spec["detail"],
            "severity": spec["severity"], "publish_task": True,
            "reported_by": "cypy-polisher", "now": utc_now()})
        if not isinstance(out, dict) or not (out.get("bug_id") or out.get("id")):
            failures.append({"summary": summary, "reply": out})
            continue
        mapping.append({"bug_id": bug_id_of(out), "task_id": out.get("task_id"),
                        "summary": summary, "fired": True})

    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip(): bug_id_of(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map4.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} fired={m['fired']} "
              f"{m['summary'][:60]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
