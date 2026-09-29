"""R1-修复 的「逐单回退树证红」：每单只撤销该单的改动，其余单的产品码保持已修状态。

判据（三条，缺一即整体失败）：
  1. 每单在自己的回退树上**至少 1 条锁转红**（否则锁不承重，是恒绿判据）；
  2. 每单的回退树上，**其他单**的锁必须全绿（否则锁之间混因，红证据不能归给这一单）；
  3. 完整树（不改任何东西）上 8 条全绿（证红用的树与验收用的树只差这一单的改动）。

临时树落在系统 temp，不进仓库；日志留在本目录 lockproof_r1.json 与逐单 pytest 输出。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"E:\IDEProjects\AI\Cypy")
HERE = Path(__file__).resolve().parent
PKGS = ["cypyc", "cypy_bridge", "cypy_hook"]
TESTFILE = "tests/test_loop_20260927_fix.py"

# 每单：{文件: [(修复后文本片段, 回退成什么)]}
REVERTS = {
    "BUG-30": {
        "cypyc/codegen/cython_generator.py": [
            ("value = self._float_widen_if_integral(node, cdef_type, value)", "pass"),
        ],
    },
    "BUG-31": {
        "cypy_bridge/types.py": [
            ("本模块的映射键是 **C/FFI 类型名**", "本模块的映射键是 **Cypy 类型名**"),
            ("负责 **C/FFI 类型名** 到 ctypes/C 类型的映射", "负责Cypy类型到ctypes/C类型的映射"),
            ("将 C/FFI 类型名转换为 ctypes 类型", "将Cypy类型转换为ctypes类型"),
            ("将 C/FFI 类型名转换为 C 类型字符串", "将Cypy类型转换为C类型字符串"),
            ("float32_ = ctypes.c_float", "float_ = ctypes.c_float"),
            ("    'float32_',", "    'float_',"),
        ],
        "cypy_bridge/__init__.py": [
            ("    float32_,", "    float_,"),
            ("    'float32_',", "    'float_',"),
        ],
    },
    "BUG-33": {
        "cypyc/parser/lexer.py": [
            (
                """        else:
            # BUG-33: 循环因走到 EOF 而结束（没 break 到闭合引号）。以前直接 return，
            # 未闭合的字面量会把其后整段源码吃进去——函数体静默消失、零报错、产物照写。
            raise ValueError(
                f"Unterminated string literal opened at {open_line}:{open_col}, "
                f"reached end of file at {self.line}:{self.col}")""",
                """        else:
            return result""",
            ),
        ],
    },
    "BUG-38": {
        "cypyc/parser/lexer.py": [
            ('while self._peek() in (" ", "\\t"):', 'while self._peek() in " \\t":'),
        ],
    },
}

LOCK_NODES = {
    "BUG-30": [
        "test_bug30_int_initializer_to_float_gets_explicit_double_cast",
        "test_bug30_widening_does_not_touch_non_integrals",
    ],
    "BUG-31": [
        "test_bug31_bridge_mapping_declares_ffi_key_space_and_renamed_alias",
        "test_bug31_width_of_bridge_float_is_unchanged",
    ],
    "BUG-33": [
        "test_bug33_unterminated_string_raises_with_position",
        "test_bug33_closed_string_still_lexes",
    ],
    "BUG-38": [
        "test_bug38_trailing_spaces_at_eof_do_not_crash",
        "test_bug38_trailing_space_parses_like_the_newline_version",
    ],
}


def build_tree(only: str | None) -> Path:
    """复制三个包 + 该测试文件到 temp 树；only=None 表示完整（已修）树。"""
    tmp = Path(tempfile.mkdtemp(prefix=f"cypy_lockproof_{(only or 'full')}_"))
    for pkg in PKGS:
        shutil.copytree(
            REPO / pkg, tmp / pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyd", "*.so")
        )
    (tmp / "tests").mkdir()
    shutil.copy(REPO / TESTFILE, tmp / TESTFILE)
    if only:
        for rel, pairs in REVERTS[only].items():
            path = tmp / rel
            text = path.read_text(encoding="utf-8")
            for new, old in pairs:
                hits = text.count(new)
                if hits == 0:
                    raise SystemExit(
                        f"[anchor-miss] {only}: 回退锚点在 {rel} 里零命中，"
                        f"锚点已失效（先证明 needle 在被读侧存在再谈回退）：\n{new[:80]}"
                    )
                text = text.replace(new, old)
            path.write_text(text, encoding="utf-8", newline="\n")
    return tmp


def run_pytest(tree: Path) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            TESTFILE,
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-rA",
        ],
        cwd=str(tree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    (HERE / f"lockproof_{tree.name}.log").write_text(out, encoding="utf-8", newline="\n")
    # pytest -rA 的结果行是 `PASSED path::name` / `FAILED path::name - 原因`（状态在前），
    # 上一版按 "path::name PASSED" 解析 ⇒ passed 恒空，把"8 passed"的绿树判成不绿。
    rows = re.findall(r"^(PASSED|FAILED)\s+\S*test_loop_20260927_fix\.py::(\w+)", out, re.M)
    passed = sorted(n for s, n in rows if s == "PASSED")
    failed = sorted(n for s, n in rows if s == "FAILED")
    if len(passed) + len(failed) != 8:
        return {
            "rc": proc.returncode,
            "passed": passed,
            "failed": failed,
            "parse_broken": f"结果行只解析到 {len(passed) + len(failed)}/8 条",
            "tail": out.strip().splitlines()[-6:],
        }
    return {
        "rc": proc.returncode,
        "passed": passed,
        "failed": failed,
        "tail": out.strip().splitlines()[-3:],
    }


def main() -> int:
    refuse = []
    result = {}

    full = build_tree(None)
    fr = run_pytest(full)
    result["full_tree"] = {"tree": full.name, **fr}
    if fr["rc"] != 0 or fr["failed"] or len(fr["passed"]) != 8:
        refuse.append(
            f"完整树未全绿：rc={fr['rc']} passed={len(fr['passed'])}/8 failed={fr['failed']} "
            f"——证红用的树必须先绿，否则下面的红不能归给任何一单：{fr['tail']}"
        )

    for ticket in REVERTS:
        tree = build_tree(ticket)
        r = run_pytest(tree)
        own = set(LOCK_NODES[ticket])
        others = {n for t, ns in LOCK_NODES.items() if t != ticket for n in ns}
        red_own = own & set(r["failed"])
        green_others = others - set(r["failed"])
        result[ticket] = {
            "tree": tree.name,
            "rc": r["rc"],
            "failed": r["failed"],
            "passed": r["passed"],
        }
        if not red_own:
            refuse.append(f"{ticket} 的回退树上自己的锁全绿 ⇒ 锁不承重")
        if green_others != others:
            refuse.append(f"{ticket} 的回退树上误伤了别单的锁：{sorted(others - green_others)}")
        if r["rc"] == 0:
            refuse.append(f"{ticket} 的回退树 rc=0（pytest 未失败）：{r['tail']}")

    out = HERE / "lockproof_r1.json"
    out.write_text(
        json.dumps({"refuse": refuse, "result": result}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "per_ticket": {
                    k: {"failed": v.get("failed"), "rc": v.get("rc")} for k, v in result.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    raise SystemExit(main())
