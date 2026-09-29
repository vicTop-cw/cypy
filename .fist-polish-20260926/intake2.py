#!/usr/bin/env python3
"""Second sweep intake: the `except Exception: pass` sites the first round left behind.

Same contract as intake.py — server cwd is the Cypy root so `project_dir="."` writes
`memory/bugs.md`; reconcile by `summary` first so a re-run never double-books; read the id
with the `bug_id`-or-`id` fallback (BUG-11 on FIST-Mbt's side: writer and reader disagree).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import pfist  # noqa: E402
from pfist import Client, utc_now  # noqa: E402

RED = ".fist-polish-20260926/pytest_second_sweep_red.log"

FINDINGS = [
    {
        "summary": "[silent-fail] cypyc/incremental/hot_reload.py:253 "
                   "HotReloadEngine 的模块级状态快照/回滚仍是 `except Exception: pass`，"
                   "BUG-5 的修复只覆盖了 CypyProxyModule 那一份平行实现",
        "severity": "medium",
        "detail": (
            "现象: `_save_module_state()`(:248-254) 与 `_restore_module_state()`(:276-279) "
            "对 getattr/setattr 失败一律 `pass`，而同文件同族缺陷 BUG-5 只改了代理模块路径的 "
            "`_save_state/_restore_state`（helper `_warn_state` 就在 :53）。\n"
            f"复现（确定性，零依赖）: `pytest tests/test_polish_20260926.py -q -k "
            f"'bug9_module or bug10'` → 4 failed，capsys 的 stderr 为空串；原始输出 {RED}。\n"
            "影响: 热重载带着状态空洞继续跑——模块全局被静默丢弃或写不回去，用户只看到『重载成功』；"
            "与本轮 BUG-3/BUG-4/BUG-5/BUG-6/BUG-7/BUG-8 同族。\n"
            "建议: 两处 except 复用已有的 `_warn_state()`，不改快照/回滚语义与返回值。"
        ),
    },
    {
        "summary": "[silent-fail] cypyc/incremental/hot_reload.py:457 "
                   "热重载把依赖分析与增量缓存更新的解析失败整段吞掉（:332 与 :457 两处，注释即『解析失败不影响热重载』）",
        "severity": "medium",
        "detail": (
            "现象: `_analyze_module_dependencies()` 的函数体整块包在 try 里、`except Exception: pass`"
            "（:433-458），`_compile_and_reload_module()` 更新增量缓存的那段同样静默（:325-333）。"
            "解析或 analyze_changes 一旦抛错，模块级反向依赖图就缺边，后续热重载只重编触发文件本身、"
            "漏掉依赖方——漏重载比报错更难查。\n"
            f"复现（确定性，零依赖）: monkeypatch `cypyc.parser.parser.Parser` 抛错后调用两个入口，"
            f"stderr 全空；见 {RED} 里 test_bug10_dependency_analysis_parse_failure_warns 与 "
            "test_bug10_cache_update_parse_failure_warns 两条 failed。\n"
            "影响: 增量/热重载的正确性静默降级；BUG-3 修的是 project_compiler 那份重解析，"
            "hot_reload 这两份是同一缺陷类的未覆盖面。\n"
            "建议: 两处各打一条点名 阶段/源文件/底层异常 的 stderr 告警，不改控制流"
            "（仍继续热重载），彻底上报到 diagnostics 属语义面变更需另立单。"
        ),
    },
]


def bug_id_of(row):
    return row.get("bug_id") or row.get("id")


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake2", "version": "1"}})

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
        if not isinstance(out, dict) or not out.get("bug_id"):
            failures.append({"summary": summary, "reply": out})
            continue
        mapping.append({"bug_id": out["bug_id"], "task_id": out.get("task_id"),
                        "summary": summary, "fired": True})

    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip(): bug_id_of(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    for m in mapping:
        if not m["fired"]:
            continue
        m["task_id"] = m["task_id"] or None
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map2.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} fired={m['fired']} {m['summary'][:60]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
