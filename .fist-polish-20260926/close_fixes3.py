#!/usr/bin/env python3
"""Close the third-sweep fix ticket (BUG-11 -> T0r16).

close_fixes.py / close_fix8.py / close_fixes2.py are left untouched. Run only after the
terminal full-suite number exists, because a 已完成 ticket cannot be amended (gotcha 33).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = json.load(open(os.path.join(HERE, "intake_map3.json"), encoding="utf-8"))["mapping"]
POLISHER = "cypy-polisher"

DELIVERABLE = (
    "改动文件：cypyc/project/project_compiler.py"
    "（type_check_module 内 :541 `errors.extend(scope_analyzer.errors)` + "
    ":555 `errors = list(dict.fromkeys(errors))` 按序去重）\n"
    "新增回归：tests/test_polish_20260926.py::test_bug11_project_type_check_reports_scope_errors"
    " + ::test_bug11_type_level_name_collision_is_reported（各 1 条，共 2 条）\n"
    "修复口径：不新增判定规则、不新增诊断文案、不改 TypeChecker —— 只把 ScopeAnalyzer 已经算出来"
    "却被丢掉的诊断上达到调用面（cypyc/cli.py:737 的 --check-only、project_compiler.py:768 的 "
    "build()），并按序去重两条通道逐字相同的诊断（如 Undefined name）。"
    "与单文件管线 cypy_hook/hook.py:250-257 的既有口径对齐，消除『同一份源码两个入口相反裁决』。\n"
    "取证探针：python .fist-polish-20260926/probe_scope_drop.py → 三条 DROPPED"
    "（dup_func / dup_subtype_class / dup_type_constraint 的 type_check_module 返回 "
    "ok=True errors=[]），对照组 uses_undefined 一条不丢（TypeChecker 自己会报同一句）。\n"
    "RED：改前 `pytest tests/test_polish_20260926.py -q -k bug11` → 2 failed, 20 deselected"
    "（证据 .fist-polish-20260926/pytest_third_sweep_red.log；两条用例各自带前提自证断言，"
    "先确认 ScopeAnalyzer 真的报出了该名字，再判调用面）\n"
    "开关对照：把新增两行退回改前形态 → 同 2 failed 且失败用例名逐条相同"
    "（.fist-polish-20260926/pytest_switchoff_bug11.log），恢复后文件 md5 "
    "167b194f99634b280cc3096237bcddc7 与改前记录字节一致\n"
    "GREEN：改后 `pytest tests/test_polish_20260926.py tests/test_project_compiler.py "
    "tests/test_cli.py tests/test_demos.py -q` → 414 passed, 0 failed\n"
    "调用面复核（不只测库函数）：`python .fist-polish-20260926/probe_cli_check_e2e.py` 真起 "
    "`python -m cypyc build <临时项目> --check-only -o <临时输出>` → exit 1，stdout 打印 "
    "`Name 'f' is already declared in this scope (line 5, col 5)`；源与输出都在临时目录，"
    "仓库 `output/`、`dist/` 未写（原始输出 `.fist-polish-20260926/probe_cli_check_e2e.out`）\n"
    "基线不回落（本单收尾时的终态实测）：`pytest tests/ -q` → 1 failed, 1813 passed, "
    "collected 1814（`.fist-polish-20260926/pytest_final_sweep4.log`）——唯一红条是 "
    "tests/test_golden_anchor_probes.py::TestGoldenPairing::test_every_example_has_golden，"
    "缺 `examples/subtype_units.out`：属上一轮在途产物与「examples/ 不动」的冲突，"
    "本单不顺手注册基准。自研体系 `python scripts/run_tests.py` → Total 47 / Passed 47 / "
    "Failed 0（`.fist-polish-20260926/test_suite_after_sweep3.log`）"
)


def main():
    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close3", "version": "1"}})
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
        step("execute", {"task_id": tid, "deliverable": DELIVERABLE, "now": utc_now()},
             f"{bug}:execute")
        step("submit", {"task_id": tid, "now": utc_now()}, f"{bug}:submit")
        step("verify", {"task_id": tid, "verifier": POLISHER, "now": utc_now()}, f"{bug}:verify")
        step("get", {"task_id": tid}, f"{bug}:final")

    root = step("get", {"task_id": "T0"}, "root:T0")
    c.close()
    json.dump(log, open(os.path.join(HERE, "close_fixes3.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bad = [e["tag"] for e in log
           if isinstance(e["result"], dict) and e["result"].get("__error__")]
    print("errors:", bad or "none")
    print("root T0 status:", (root or {}).get("status") if isinstance(root, dict) else root)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
