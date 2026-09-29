#!/usr/bin/env python3
"""Seventh-pass closure: claim -> execute -> submit -> verify for every ticket BUG-15..29.

The ticket ids are reverse-parsed from intake_map7.json (the ledger's own reply), never
hand-written -- a past pass hand-copied a mapping file and then reported "13 in DB vs 12 in
map" as a ledger defect. Verifier identity is the polisher; `verify` rolls the parent up.

Each deliverable names the repro evidence, the exact files touched, and the locking test, so
the acceptance judge (gate ②) can be recomputed from this text plus the pytest log.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

BUGS = {
 "BUG-15": (["cypyc/parser/lexer.py:538 (判定切片 2->3 字符)"],
            ["tests/test_polish_20260926_pass7.py::test_bug15_stray_double_backtick_does_not_swallow_rest_of_file",
             "tests/test_polish_20260926_pass7.py::test_bug15_real_triple_backtick_block_still_lexes_as_macro_block"]),
 "BUG-16": (["cypyc/parser/parser.py:1374-1382 (成员装饰器改用独立局部名 member_decorators)"],
            ["tests/test_polish_20260926_pass7.py::test_bug16_value_struct_keeps_decorators_when_a_member_is_decorated",
             "tests/test_polish_20260926_pass7.py::test_bug16_struct_def_does_not_inherit_a_member_decorator"]),
 "BUG-17": (["cypyc/project/project_compiler.py:666 (全不匹配时返回 None)"],
            ["tests/test_polish_20260926_pass7.py::test_bug17_pick_extension_returns_none_for_unrelated_artifacts",
             "tests/test_polish_20260926_pass7.py::test_bug17_pick_extension_still_prefers_the_matching_artifact"]),
 "BUG-18": (["cypyc/incremental/incremental_manager.py:311-320 (比对依赖 file_hash)"],
            ["tests/test_polish_20260926_pass7.py::test_bug18_changed_dependency_invalidates_the_importer",
             "tests/test_polish_20260926_pass7.py::test_bug18_unchanged_dependency_stays_a_cache_hit",
             "tests/test_polish_20260926_pass7.py::test_bug18_dependency_without_any_cache_entry_is_still_changed"]),
 "BUG-19": (["cypyc/codegen/cython_generator.py:1284-1296 (插入点移到指令块之后)"],
            ["tests/test_polish_20260926_pass7.py::test_bug19_owned_import_is_inserted_below_cython_directives"]),
 "BUG-20": (["cypyc/analyzer/comptime_evaluator.py:158-177 (Attribute 调路由到方法表)",
             "cypyc/analyzer/comptime_evaluator.py:171-175 (未知属性沿用返回 None 的降级口径)"],
            ["tests/test_polish_20260926_pass7.py::test_bug20_comptime_can_evaluate_attribute_method_calls",
             "tests/test_polish_20260926_pass7.py::test_bug20_builtin_name_calls_are_untouched",
             "tests/test_polish_20260926_pass7.py::test_bug20_unknown_attribute_method_degrades_to_none_without_raising"]),
 "BUG-21": (["cypyc/analyzer/type_checker.py:432-436 (泛型 impl 注册基类型名)"],
            ["tests/test_polish_20260926_pass7.py::test_bug21_generic_impl_registers_the_base_type_name"]),
 "BUG-22": (["cypyc/parser/lexer.py:653-662 (承认 fr/rf 组合，拒绝 rr/ff)"],
            ["tests/test_polish_20260926_pass7.py::test_bug22_string_prefixes_lex_as_one_string_token (7 参数化)",
             "tests/test_polish_20260926_pass7.py::test_bug22_two_char_names_are_not_swallowed_as_prefixes"]),
 "BUG-23": (["cypy_bridge/pointer.py:321-330 (c_void_p 分支提到 hasattr 之前)"],
            ["tests/test_polish_20260926_pass7.py::test_bug23_addr_of_void_p_returns_pointed_value_including_null",
             "tests/test_polish_20260926_pass7.py::test_bug23_addr_of_scalar_still_returns_storage_address"]),
 "BUG-24": (["cypy_hook/hook.py:1020-1024 (按 basename(dirname(root)) 判 __pycache__)"],
            ["tests/test_polish_20260926_pass7.py::test_bug24_clear_all_cache_actually_removes_cached_files"]),
 "BUG-25": (["cypy_bridge/compiler.py:3766 与 :3807 (两处写盘补 encoding='utf-8')"],
            ["tests/test_polish_20260926_pass7.py::test_bug25_generated_c_and_setup_are_written_as_utf8"]),
 "BUG-26": (["cypy_bridge/compiler.py:3833 (产物扫描接受 .so/.dll)"],
            ["tests/test_polish_20260926_pass7.py::test_bug26_artifact_scan_accepts_non_windows_extensions"]),
 "BUG-27": (["cypyc/incremental/hot_reload.py:530 (set().union 允许空 results)"],
            ["tests/test_polish_20260926_pass7.py::test_bug27_delete_only_batch_does_not_blame_the_user_callback"]),
 "BUG-28": (["cypyc/utils/indent_detector.py:1-2 与 :30-38 (宽度取观测值 GCD)"],
            ["tests/test_polish_20260926_pass7.py::test_bug28_normalize_preserves_structure_of_two_space_sources",
             "tests/test_polish_20260926_pass7.py::test_bug28_four_space_and_six_space_styles_unchanged"]),
 "BUG-29": (["cypy_hook/hook.py:836-841 (source 为 None 时先给用法提示)"],
            ["tests/test_polish_20260926_pass7.py::test_bug29_bare_hook_command_reports_usage_not_a_traceback"]),
}

REPRO = {"BUG-15": "repro_pass7b.out.json:lex_backtick", "BUG-16": "repro 实跑：控制组含 __eq__、加装饰成员后消失",
         "BUG-17": "repro_pass7.out.json:bug16_pick_extension", "BUG-18": "读码 + repro_pass7b incremental_staleness",
         "BUG-19": "repro_pass7.out.json:bug19_addr / repro_pass7c owned_import", "BUG-20": "读码 :455-461 + :188-276 表",
         "BUG-21": "repro 实跑：trait_impls['Show']==['GenericType(line=5, col=15)']", "BUG-22": "repro 实跑：fr 前缀拆成 IDENTIFIER",
         "BUG-23": "repro_pass7.out.json:bug19_addr", "BUG-24": "repro_pass7.out.json:bug15_clear_cache",
         "BUG-25": "子进程实测 preferred=cp936 + UnicodeEncodeError", "BUG-26": "repro_pass7.out.json:bug18_pyd_only",
         "BUG-27": "读码 :530 空 results + :535 except 归因", "BUG-28": "repro_pass7.out.json:bug20_normalize",
         "BUG-29": "repro_pass7.out.json:bug21_isfile_none"}


def main() -> int:
    mapping = json.load(open(os.path.join(HERE, "intake_map7.json"), encoding="utf-8"))["mapping"]
    tickets = {m["bug_id"]: m["task_id"] for m in mapping if m.get("task_id")}
    missing = [b for b in BUGS if b not in tickets]
    if missing:
        print(f"REFUSE: intake_map7.json 里没有这些单的 task_id: {missing}")
        return 2

    log = []
    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close7", "version": "1"}})
    for bug, (files, tests) in BUGS.items():
        tid = tickets[bug]
        deliverable = (
            f"[{bug}] 复现依据: {REPRO.get(bug, 'repro_pass7*.out.json')}；"
            f"改动文件（本单全部）: {'; '.join(files)}；"
            f"锁死回归（{len(tests)} 条，除注明参数化外逐条实跑绿）: {'; '.join(tests)}；"
            f"基线不回落证据: .fist-polish-20260926/pytest_final_sweep7.log（全量）"
            f" + markers_now_p2.json（标记面）+ scripts/run_tests.py 47/47。"
            f"零付费 API：复现与研判均由执行 agent 本机脚本与读码完成。")
        steps = []
        for tool, args in [("claim", {"task_id": tid, "assignee": "cypy-polisher"}),
                           ("execute", {"task_id": tid, "deliverable": deliverable}),
                           ("submit", {"task_id": tid}),
                           ("verify", {"task_id": tid, "verifier": "cypy-polisher"})]:
            out = c.call(tool, args)          # pfist stamps a real `now` per write call
            ok = isinstance(out, dict) and "__error__" not in out
            steps.append({"tool": tool, "ok": ok, "reply": str(out)[:300]})
            if not ok:
                break
        log.append({"bug": bug, "task_id": tid, "steps": steps,
                    "green": all(s["ok"] for s in steps)})
        print(f"{bug:8s} {tid:7s} " + " ".join(f"{s['tool']}={'ok' if s['ok'] else 'RED'}" for s in steps))
        for s in steps:
            if not s["ok"]:
                print(f"    ! {s['tool']} 原始回复: {s['reply']}")
    c.close()
    json.dump(log, open(os.path.join(HERE, "close_fixes7.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    green = [r["bug"] for r in log if r["green"]]
    print(f"closed_green={len(green)}/{len(BUGS)} -> {green}")
    return 0 if len(green) == len(BUGS) else 1


if __name__ == "__main__":
    sys.exit(main())
