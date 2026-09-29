"""R13 承重矩阵：把本轮加的接线逐个摘掉，证明本轮新增的锁与语料不是运气。

骨架沿用 R12 那份（被实测走通的），但锚点是本轮从 `type_checker.py` 现状字节里取的，
不复制上一轮的任何"事实"。六格：
 M1 赋值位调用、M2 返回位调用、M3 逐位扫描短路（调用还在但没人判）、
 M4 撤掉 `UnionType` 分支（BUG-139 的修法）、M5 撤掉别名展开（BUG-138 的修法）、
 M6 只改注释对照（必须 0 红，否则说明尺子在数散文）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# SYNTAX/ 必须在列：本轮有一支锁拿手册的闭合标量表与代码常量对表（规则 5 的双向门），
# 少拷一个目录就会让它在副本树里必红 —— L0 现树格把这件事抓了出来。
NEED_DIRS = ["cypyc", "tests", "corpus", "scripts", "SYNTAX"]
NEED_FILES = ["pyproject.toml", "conftest.py", "pytest.ini", "setup.cfg"]
TC = "cypyc/analyzer/type_checker.py"
SPEC_OP = "cypy.container.elements"
LOCK_TESTS = "tests/test_container_elements_r13.py"

LET_CALL = """                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self._check_container_elements(declared_type, value_type, node)
                    self.type_map[node.name] = declared_type
"""
LET_PLAIN = """                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self.type_map[node.name] = declared_type
"""
RET_CALL = """                    self._check_container_elements(
                        self.current_function_return_type, value_type, node, 'Return ')
                    return value_type
"""
RET_PLAIN = """                    return value_type
"""
SCAN_HEAD = """        gp = list(got.generic_params or [])
        if not wp or not gp:
            return None          # 规则 4：值侧没有元素信息 ⇒ 占位形态
        for i in range(min(len(wp), len(gp))):
"""
SCAN_SHORT = """        gp = list(got.generic_params or [])
        if True:  # 变异格：逐位扫描短路（等价于"助手都在但没人扫"）
            return None
        if not wp or not gp:
            return None          # 规则 4：值侧没有元素信息 ⇒ 占位形态
        for i in range(min(len(wp), len(gp))):
"""
UNION_BRANCH = """        if hasattr(type_node, 'kind') and type_node.kind == 'UnionType':
            # 与 `_get_type_from_node` 的联合分支同形：名字仍是 object，成员交给 `_type_in_union`
            members = []
            for member in (getattr(type_node, 'types', None) or []):
                substituted = self._substitute_type(member, param_map, _alias_stack)
                if substituted:
                    members.append(substituted)
            return Type("object", union_members=members) if members else None
"""
GENERIC_EXPAND = """            expanded = self._expand_nested_alias(
                type_node.name, substituted_params, _alias_stack)
            if expanded is not None:
                return expanded
            return Type(type_node.name, generic_params=substituted_params)
"""
GENERIC_PLAIN = """            return Type(type_node.name, generic_params=substituted_params)
"""
# 对照格只能钉注释行本身：`LET_CALL` 那段锚点里没有注释，"只改注释"就无从谈起。
COMMENT_LINE = (
    "# 「采用声明类型」不等于「元素位也放行」——后者交 SYNTAX/02 的元素判定（BUG-137）。\n"
)
COMMENT_MUTATED = COMMENT_LINE.replace("元素判定", "元素位判定")
assert (ROOT / TC).read_text(encoding="utf-8").count(COMMENT_LINE) == 1, "对照格锚点不唯一"

CELLS = {
    "M1 摘掉赋值位调用": [(TC, LET_CALL, LET_PLAIN)],
    "M2 摘掉返回位调用": [(TC, RET_CALL, RET_PLAIN)],
    "M3 逐位扫描短路": [(TC, SCAN_HEAD, SCAN_SHORT)],
    "M4 撤掉 UnionType 代入（BUG-139）": [(TC, UNION_BRANCH, "")],
    "M5 撤掉别名展开（BUG-138）": [(TC, GENERIC_EXPAND, GENERIC_PLAIN)],
    "M6 只改注释（对照格，必须 0 红）": [(TC, COMMENT_LINE, COMMENT_MUTATED)],
}


def copy_tree(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for d in NEED_DIRS:
        shutil.copytree(ROOT / d, dst / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in NEED_FILES:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, dst / f)


def clean_pyc(dst: Path) -> None:
    for p in dst.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for p in dst.rglob("*.pyc"):
        try:
            os.unlink(p)
        except OSError:
            pass


def run_pytest(dst: Path) -> dict:
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            LOCK_TESTS,
            "tests/regression/test_corpus_pairs.py",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            "-rf",
            "-q",
        ],
        cwd=str(dst),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    out = r.stdout + r.stderr
    failed = sorted({m for m in re.findall(r"(?m)^FAILED (\S+)", out)})
    return {
        "rc": r.returncode,
        "n_failed": len(failed),
        "failed_ids": failed[:10],
        "crash": r.returncode not in (0, 1),
        "summary": (re.findall(r"=+ .*(?:failed|passed|error).*?=+", out) or [""])[-1],
    }


def run_gate(dst: Path) -> dict:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/omega_gate.py", "--op", SPEC_OP],
        cwd=str(dst),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = r.stdout + r.stderr
    conc = [ln for ln in out.splitlines() if ln.startswith("CONCLUSION")]
    m = re.search(r"cases=(\d+) passed=(\d+) failed=(\d+)", conc[-1] if conc else "")
    return {
        "rc": r.returncode,
        "conclusion": conc[-1] if conc else out[-200:],
        "failed": int(m.group(3)) if m else None,
    }


def strip_comments(text: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", text)


def apply_edits(dst: Path, edits) -> list:
    applied = []
    for rel, old, new in edits:
        p = dst / rel
        t = p.read_text(encoding="utf-8")
        n = t.count(old)
        if n != 1:
            raise SystemExit(f"锚点 {rel}::{old[:44]!r} 命中 {n} 次，期望 1 ⇒ 停手，这一格不算变异")
        mutated = t.replace(old, new)
        if mutated == t:
            raise SystemExit(f"{rel} 替换后与原文逐字相同 ⇒ 假变异，拒收这一格")
        p.write_text(mutated, encoding="utf-8", newline="\n")
        applied.append({"rel": rel, "anchor": old[:48], "delta_len": len(old) - len(new)})
    return applied


def identity(dst: Path, edits) -> list:
    rows = []
    for rel, old, new in edits:
        t = (dst / rel).read_text(encoding="utf-8")
        comment_only = strip_comments(old) == strip_comments(new)
        if comment_only:
            rows.append(
                {
                    "rel": rel,
                    "kind": "只改注释",
                    "code_unchanged": strip_comments(t)
                    == strip_comments((ROOT / rel).read_text(encoding="utf-8")),
                    "comment_actually_changed": old != new and new in t,
                }
            )
        elif new == "":
            rows.append({"rel": rel, "kind": "摘除", "anchor_gone": old not in t})
        else:
            rows.append({"rel": rel, "kind": "替换", "anchor_gone": old not in t})
    return rows


def cell(base: Path, name: str, edits) -> dict:
    dst = base / re.sub(r"\W+", "_", name)
    copy_tree(dst)
    clean_pyc(dst)
    applied = apply_edits(dst, edits)
    clean_pyc(dst)
    ident = identity(dst, edits)
    if any(r.get("kind") == "只改注释" for r in ident) and not all(
        r.get("code_unchanged") and r.get("comment_actually_changed") for r in ident
    ):
        raise SystemExit(f"{name} 的对照格没做到「代码逐字未变 + 注释确实变了」⇒ 这格不作数")
    return {"edits": applied, "identity": ident, "pytest": run_pytest(dst), "gate": run_gate(dst)}


def main() -> int:
    base = ROOT / f".r13_matrix_{os.getpid()}"
    rep = {"pid": os.getpid(), "cells": {}}
    rep["cells"]["L0 现树（应全绿）"] = cell(base, "L0", [])
    for name, edits in CELLS.items():
        rep["cells"][name] = cell(base, name, edits)
    shutil.rmtree(base, ignore_errors=True)
    (HERE / "verify_r13_matrix.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    bad = []
    live = rep["cells"]["L0 现树（应全绿）"]
    if live["pytest"]["n_failed"] or live["pytest"]["crash"] or live["gate"]["failed"]:
        bad.append("L0 现树不绿 ⇒ 矩阵分母不可信")
    load = []
    for name, c in rep["cells"].items():
        if name.startswith("L0"):
            continue
        comment_only = any(r.get("kind") == "只改注释" for r in c["identity"])
        if comment_only:
            if c["pytest"]["n_failed"] != 0 or c["gate"]["failed"]:
                bad.append(f"{name} 只改注释却有红 ⇒ 尺子在数散文")
            continue
        load.append(name)
        if c["pytest"]["n_failed"] == 0:
            bad.append(f"{name} 摘掉后 pytest 0 红 ⇒ 锁不承重")
        if not c["gate"]["failed"]:
            bad.append(f"{name} 摘掉后 Ω-gate 0 失 ⇒ 语料不承重")
        if not all(r.get("anchor_gone", True) for r in c["identity"]):
            bad.append(f"{name} 身份探针没翻假 ⇒ 改动没落到被读的那份")
    for name, c in rep["cells"].items():
        print(
            f"{name}: pytest_red={c['pytest']['n_failed']} gate_failed={c['gate']['failed']} "
            f"identity={json.dumps(c['identity'], ensure_ascii=False)[:120]}"
        )
        print(f"    FAILED例: {c['pytest']['failed_ids'][:4]}")
    print(
        f"CONCLUSION cells={len(rep['cells'])} load_bearing_cells={len(load)} "
        f"all_red={all(rep['cells'][n]['pytest']['n_failed'] > 0 for n in load)} "
        f"comment_control_zero_red={rep['cells']['M6 只改注释（对照格，必须 0 红）']['pytest']['n_failed'] == 0} "
        f"bad={json.dumps(bad, ensure_ascii=False)} rc={0 if not bad else 1}"
    )
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
