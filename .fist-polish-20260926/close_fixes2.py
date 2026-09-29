#!/usr/bin/env python3
"""Close the second-sweep fix tickets (BUG-9 -> T0r14, BUG-10 -> T0r15).

close_fixes.py / close_fix8.py are left untouched; this driver walks only the two new tickets
and dumps every raw reply so the report table can be reconciled against bugs.md.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = json.load(open(os.path.join(HERE, "intake_map2.json"), encoding="utf-8"))["mapping"]
POLISHER = "cypy-polisher"

DELIVERABLE = {
    "BUG-9": (
        "改动文件：cypyc/incremental/hot_reload.py"
        "（_save_module_state :253 / _restore_module_state :278 的 except 分支改为调用既有 _warn_state）\n"
        "新增回归：tests/test_polish_20260926.py::test_bug9_module_state_snapshot_warns + "
        "::test_bug9_module_state_restore_warns\n"
        "修复口径：快照/回滚的控制流与返回值不变（仍跳过该属性、仍写 _module_state），只把"
        "被吞掉的 getattr/setattr 失败点名到 stderr；helper 复用第一轮 BUG-5 已经落在同文件的"
        "`_warn_state`，不新增语义。\n"
        "RED：改前 `pytest tests/test_polish_20260926.py -q -k 'bug9_module or bug10'` → 4 failed，"
        "capsys.err 为空串（证据 .fist-polish-20260926/pytest_second_sweep_red.log）\n"
        "GREEN：改后 `pytest tests/test_polish_20260926.py -q` → 20 passed"
    ),
    "BUG-10": (
        "改动文件：cypyc/incremental/hot_reload.py"
        "（_compile_and_reload_module 缓存更新段 :332 / _analyze_module_dependencies 整段 :457 "
        "的 except 改为新增模块级 helper _warn_parse，点名 阶段+源文件+底层异常）\n"
        "新增回归：tests/test_polish_20260926.py::test_bug10_dependency_analysis_parse_failure_warns + "
        "::test_bug10_cache_update_parse_failure_warns\n"
        "修复口径：热重载继续执行（不抛、不改返回值），只补告警；缓存缺边/依赖边缺失从『不可见』变『可见』。\n"
        "RED：改前同 4 failed / stderr ''；缓存段这条还做了一次开关对照——把 :332 的告警退回 `pass` "
        "后 `pytest -k cache_update` → 1 failed，恢复后 → 1 passed（证明判据真的绑定在该站点，"
        "而不是被失败分支提前 return 绕过）。\n"
        "GREEN：改后 `pytest tests/test_polish_20260926.py -q` → 20 passed"
    ),
}


def main():
    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close2", "version": "1"}})
    log = []

    def step(tool, args, tag):
        out = c.call(tool, args)
        log.append({"tag": tag, "result": out})
        print(f"{tag:34s} {str(out)[:110]}")
        return out

    for row in MAP:
        bug, tid = row["bug_id"], row["task_id"]
        if not tid:
            step("get", {"task_id": f"{bug}"}, f"{bug}:no-task-id")
            continue
        step("claim", {"task_id": tid, "assignee": POLISHER, "now": utc_now()}, f"{bug}:claim")
        step("execute", {"task_id": tid, "deliverable": DELIVERABLE[bug], "now": utc_now()},
             f"{bug}:execute")
        step("submit", {"task_id": tid, "now": utc_now()}, f"{bug}:submit")
        step("verify", {"task_id": tid, "verifier": POLISHER, "now": utc_now()}, f"{bug}:verify")
        step("get", {"task_id": tid}, f"{bug}:final")

    root = step("get", {"task_id": "T0"}, "root:T0")
    c.close()
    json.dump(log, open(os.path.join(HERE, "close_fixes2.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bad = [e["tag"] for e in log
           if isinstance(e["result"], dict) and e["result"].get("__error__")]
    print("errors:", bad or "none")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
