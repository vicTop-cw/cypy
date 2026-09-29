#!/usr/bin/env python3
"""收口 spec 的 needle/min_chars 先量再写：预检失败一个服务端调用都不发。"""

import json
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
CAND = [
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug44.json",
        "test_bug44_struct_selfless_methods_drop_injected_self",
    ),
    (".fist-loop-20260927/fix_r2_lockproof_revert_bug44.json", "red_locks"),
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug45.json",
        "test_bug45_implicit_default_without_annotation_is_diagnosed",
    ),
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug39.json",
        "test_bug39_toplevel_return_is_diagnosed_at_cli",
    ),
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug35.json",
        "test_bug35_parse_diagnosis_is_not_bucketed_as_read_error",
    ),
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug46.json",
        "test_bug46_usage_doc_matches_the_narrowed_claim",
    ),
    (
        ".fist-loop-20260927/fix_r2_lockproof_revert_bug47.json",
        "test_bug47_package_level_hook_api_exists",
    ),
    (".fist-loop-20260927/fix_r2_lockproof.json", '"refuse": []'),
    (".fist-loop-20260927/fix_r2_lint.json", "authored_lines_checked"),
    (".fist-loop-20260927/fix_r2_lint_selftest.json", "selfprobe-caught"),
    (".fist-loop-20260927/fix_r2_baselines.json", "17d68b4"),
    (".fist-loop-20260927/fix_r2_baselines.json", "unclaimed_by_this_lane"),
    ("tests/test_loop_20260927_fix_r2.py", "def origin():"),
    ("tests/test_loop_20260927_fix_r2.py", "Config.__implicit_default__()"),
    ("tests/test_loop_20260927_fix_r2.py", "must be used inside a function"),
    ("tests/test_loop_20260927_fix_r2.py", "读取文件错误"),
    ("tests/test_loop_20260927_fix_r2.py", "current process"),
    ("tests/test_loop_20260927_fix_r2.py", "is_hook_installed_v2"),
    ("docs/USAGE.md", "不写盘、不跨进程生效"),
    ("cypy_hook/__init__.py", "is_hook_installed"),
    ("cypyc/parser/parser.py", "needs a parameter type"),
    ("cypyc/codegen/cython_generator.py", "_is_selfless_method"),
    ("cypyc/cli.py", "registered for the current process"),
    ("cypy_hook/hook.py", "OSError as read_err"),
]
rows = []
for rel, needle in CAND:
    p = ROOT / rel
    if not p.exists():
        rows.append({"file": rel, "exists": False, "size": 0, "hits": 0})
        continue
    text = p.read_text(encoding="utf-8")
    rows.append(
        {
            "file": rel,
            "exists": True,
            "size": len(text),
            "hits": text.count(needle),
            "needle": needle[:44],
        }
    )
print(json.dumps(rows, ensure_ascii=False, indent=1))
