"""R6 锁承重矩阵：把本轮三处修复分别在**副本树**里逐格摘掉，当前 tests 必须至少转红一条。

为什么不能用 `git archive HEAD`：本仓 HEAD 是 2026-08-17，而盘面带着 09 月四轮未提交改动，
HEAD 树里根本没有 `tests/test_pattern_positional_struct.py` 要针对的那份实现。
⇒ 底树 = 盘面快照（只复制三包 + 本轮新增的两个判据文件 + test_boundary_comprehensive.py）。

三格各自只摘**一个**变量（防上游崩溃遮住下游）：
  L1 生成器：`_record_pattern_shape(name, stmt)` 两处调用 → 摘掉（等于回到只读 .body 的旧采集）
  L2 分析器：`_visit_Pattern` 的「未登记才补 object」→ 改回无条件 `Type("int")`
  L3 测试遮蔽：`…ShadowedOnce` 两个类名 → 改回同名（遮蔽复现）
每格都跑同一套判据命令并留 rc 与逐字红条；另配一格「只改注释」的正向对照，
证明摘除动作本身没有因为语法错而假红。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TREE = HERE / "lockproof_tree"
OUT = HERE / "verify_r6_locks.json"
PKG_DIRS = ("cypyc", "cypy_bridge", "cypy_hook")
TEST_FILES = ("tests/test_pattern_positional_struct.py", "tests/test_fist_driver_protocol.py",
              "tests/test_boundary_comprehensive.py", "tests/conftest.py")
COMMANDS = {
    "L1": ["-m", "pytest", "tests/test_pattern_positional_struct.py", "-q", "--tb=line"],
    "L2": ["-m", "pytest", "tests/test_pattern_positional_struct.py", "-q", "--tb=line"],
    "L3": ["-m", "pytest", "tests/test_boundary_comprehensive.py", "-q", "-k",
            "ShadowedOnce"],
}


def build_tree() -> None:
    if TREE.exists():
        shutil.rmtree(TREE)
    TREE.mkdir(parents=True)
    for d in PKG_DIRS:
        shutil.copytree(ROOT / d, TREE / d,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "output"))
    for f in TEST_FILES:
        src = ROOT / f
        if not src.exists():
            continue
        dst = TREE / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())


def edit(rel: str, old: str, new: str, expect: int) -> int:
    p = TREE / rel
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    assert n == expect, f"{rel}: 锚点命中 {n}，预期 {expect} ⇒ 该格不作数（可能改到了别处）"
    p.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
    return n


def run(label: str) -> dict:
    proc = subprocess.run([sys.executable, "-X", "utf8", *COMMANDS[label]], cwd=TREE,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300)
    blob = (proc.stdout or "") + (proc.stderr or "")
    last = [ln for ln in blob.splitlines() if " passed" in ln or " failed" in ln
            or "error" in ln.lower()]
    import re as _re
    sel = _re.search(r"(\d+) selected", blob)
    fail = _re.search(r"(\d+) failed", blob)
    return {"rc": proc.returncode, "summary_line": last[-1].strip() if last else blob[-160:],
            "selected": int(sel.group(1)) if sel else None,
            "failed": int(fail.group(1)) if fail else 0,
            "red_nodes": [ln for ln in blob.splitlines() if ln.startswith("FAILED")][:6]}


def identity() -> dict:
    """身份探针：确认真跑的是副本树，而不是盘面（否则整份矩阵零证据）。"""
    code = ("import cypyc, cypyc.analyzer.type_checker as tc, pathlib;"
            "print(cypyc.__file__); print(tc.__file__)")
    proc = subprocess.run([sys.executable, "-c", code], cwd=TREE, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return {"rc": proc.returncode, "paths": proc.stdout.split()}


def main() -> int:
    report: dict = {"tree": str(TREE), "cells": {}, "refuse": []}
    build_tree()
    report["identity"] = identity()
    norm = lambda x: x.replace("\\", "/").replace("\\\\", "/").lower()
    if norm(str(TREE)) not in norm("/".join(report["identity"]["paths"])):
        report["refuse"].append(f"副本树身份不成立：{report['identity']}")

    # L1 摘生成器采集
    edit("cypyc/codegen/cython_generator.py",
         "                self._record_pattern_shape(name, stmt)\n", "", 2)
    report["cells"]["L1_codegen_collect_removed"] = run("L1")
    # 下一格重建整棵树，避免多因混在一格
    build_tree()

    # L2 摘分析器
    edit("cypyc/analyzer/type_checker.py",
         "        if getattr(node, 'name', None) and node.name not in self.type_map:\n"
         "            self.type_map[node.name] = Type(\"object\")",
         "        self.type_map[node.name] = Type(\"int\")", 1)
    report["cells"]["L2_slot_type_removed"] = run("L2")
    build_tree()

    # L3 复现遮蔽
    edit("tests/test_boundary_comprehensive.py", "class TestPointerBoundaryShadowedOnce(",
         "class TestPointerBoundary(", 1)
    edit("tests/test_boundary_comprehensive.py", "class TestPipelineBoundaryShadowedOnce(",
         "class TestPipelineBoundary(", 1)
    report["cells"]["L3_shadow_restored"] = run("L3")
    build_tree()

    # 正向对照：只改注释，必须仍然全绿（否则上面三格的红可能只是语法错/树坏了）
    edit("cypyc/codegen/cython_generator.py", "    def _record_pattern_shape(self, name: str, node: Any) -> None:",
         "    def _record_pattern_shape(self, name: str, node: Any) -> None:  # canary: 仅签名行不动语义", 1)
    report["cells"]["C_comment_only_must_be_green"] = run("L1")

    for cell, res in report["cells"].items():
        if cell.startswith("C_"):
            if res["rc"] != 0:
                report["refuse"].append(f"正向对照（只改注释）却 rc={res['rc']} ⇒ 红是尺坏了：{res['summary_line']}")
        elif res["failed"] == 0 and (res["selected"] is None or res["selected"] > 0):
            # 红 = 有失败条数；L3 那格的红是「遮蔽后 0 条被收集」，用 selected==0 判，不能拿 rc 判
            # （pytest 对 `0 selected` 的退出码仍是 0）
            report["refuse"].append(f"{cell} 摘掉修复后仍无红条（rc={res['rc']} failed={res['failed']} "
                                    f"selected={res['selected']}）⇒ 该锁不承重")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1)[:2600])
    print("LOCKPROOF", "PASS" if not report["refuse"] else "FAIL",
          "refuse=", len(report["refuse"]))
    for r in report["refuse"]:
        print("REFUSE:", r)
    return 1 if report["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
