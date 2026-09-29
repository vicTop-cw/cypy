"""R12 承重矩阵：把本轮新加的三处接线逐个摘掉，证明"锁不红"不是运气。

规矩（既往轮踩出来的）：
 · 每格动手前先断言锚点在目标文件里**恰好命中 1 次**，替换后必须与原文不同（防 `replace(...,1)` 式假变异）；
 · 每格带**身份探针**：摘掉的那一处在副本树里必须读成"不在了"，否则是"我以为我改了"；
 · 必须有一格"只改注释"的对照 ⇒ 它的红数必须是 0，否则说明尺子在数散文而不是数行为；
 · 全量套件跑着的时候不要动产品源码（本件只在副本树上动）；
 · 副本树里先清 `__pycache__`，否则上一格编译好的 .pyc 会让下一格读到旧码。
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
LOGS = HERE / "logs"
NEED_DIRS = ["cypyc", "tests", "corpus", "scripts"]
NEED_FILES = ["pyproject.toml", "conftest.py", "pytest.ini", "setup.cfg"]

TC = "cypyc/analyzer/type_checker.py"

# ① 注解位接线（`_visit_GenericType` 元数判定之后那两行）
ANN_NEW = """                # SYNTAX/11「类型约束」：注解位写的类型实参也要过声明界（`let x: Num<str>` 违界要红）
                self._check_declared_bounds(
                    decl, dict(zip(list(getattr(decl, "generic_params", []) or []), generic_params)),
                    node)
"""
# ② 构造位接线
CTOR_NEW = """        # 类/结构体的显式类型实参：界判定在此完成。函数由 `_visit_Call` 里那份统一判
        # （那里的 `inferred_types` 可能就是这个 binding，重复判会得到两条同事实的账）。
        if func_name not in self.func_defs:
            self._check_declared_bounds(decl, binding, node)
"""
# ③ 字面量位：退回本轮摘掉的那份窄复制（只认单名界）
LIT_NEW = """                # 检查泛型参数约束：复用调用位那一份判定。原来这里只认单名界
                # （`getattr(constraint_ast, 'id')` 对 `T: int | float` 取到 None ⇒ 静默放行），
                # 联合/trait/typeclass/F-bounded 四类界现在三处使用位口径一致。
                self._check_declared_bounds(struct_def, inferred_types, node)
"""
LIT_OLD = """                # 检查泛型参数约束（R10 之前的窄复制：只认单名界）
                for param, inferred_type in inferred_types.items():
                    if param in generic_constraints:
                        constraint_type_ast = generic_constraints[param]
                        constraint_type_name = getattr(constraint_type_ast, 'id', None)
                        if constraint_type_name and inferred_type.name != constraint_type_name:
                            line = node.line if hasattr(node, 'line') else 0
                            col = node.col if hasattr(node, 'col') else 0
                            self.errors.append(
                                f"Generic constraint violation: type '{inferred_type.name}' does not "
                                f"satisfy constraint '{constraint_type_name}' for parameter '{param}' "
                                f"at {line}:{col}")
"""
# ④ 共用件整体短路
HELPER_NEW = """        constraints = getattr(decl, "generic_constraints", {}) or {}
        if not constraints:
            return
"""
HELPER_OLD = """        constraints = getattr(decl, "generic_constraints", {}) or {}
        if True:  # 变异格：短路整个共用件（等价于"三处接线都在但没人判"）
            return
        if not constraints:
            return
"""

CELLS = {
    "M1 摘掉注解位接线": [(TC, ANN_NEW, "")],
    "M2 摘掉显式实参构造位接线": [(TC, CTOR_NEW, "")],
    "M3 字面量位退回窄复制": [(TC, LIT_NEW, LIT_OLD)],
    "M4 共用件短路（三处接线全成装饰）": [(TC, HELPER_NEW, HELPER_OLD)],
    "M5 只改注释（对照格，必须 0 红）": [
        (TC, ANN_NEW, ANN_NEW.replace("违界要红", "违界要报出来"))
    ],
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
    (dst / "memory").mkdir(exist_ok=True)
    if (ROOT / "memory" / "bugs.md").exists():
        shutil.copy2(ROOT / "memory" / "bugs.md", dst / "memory" / "bugs.md")


def clean_pyc(dst: Path) -> None:
    for p in dst.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for p in dst.rglob("*.pyc"):
        try:
            os.unlink(p)
        except OSError:
            pass


def run_pytest(dst: Path) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/test_generic_bounds_r12.py",
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
        env=env,
    )
    out = r.stdout + r.stderr
    failed = sorted({m for m in re.findall(r"(?m)^FAILED (\S+)", out)})
    return {
        "rc": r.returncode,
        "n_failed": len(failed),
        "failed_ids": failed[:12],
        "crash": r.returncode not in (0, 1),
        "summary": (re.findall(r"=+ .*(?:failed|passed|error).*?=+", out) or [""])[-1],
    }


def run_gate(dst: Path) -> dict:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
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


def apply_edits(dst: Path, edits) -> list:
    applied = []
    for rel, old, new in edits:
        p = dst / rel
        t = p.read_text(encoding="utf-8")
        n = t.count(old)
        if n != 1:
            raise SystemExit(f"锚点 {rel}::{old[:40]!r} 命中 {n} 次，期望 1 ⇒ 停手，这一格不算变异")
        mutated = t.replace(old, new)
        if mutated == t:
            raise SystemExit(f"{rel} 替换后与原文逐字相同 ⇒ 假变异，拒收这一格")
        p.write_text(mutated, encoding="utf-8", newline="\n")
        applied.append({"rel": rel, "anchor": old[:52], "removed_len": len(old) - len(new)})
    return applied


def strip_comments(text: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", text)


def identity(dst: Path, edits) -> list:
    """身份探针：先按"剔掉注释后代码是否变化"分类（不是按字符串相等 —— 改注释也是不等），
    再分别验：真变异 ⇒ 锚点必须从被读的那份里消失；注释变异 ⇒ 代码必须逐字未变。"""
    rows = []
    for rel, old, new in edits:
        t = (dst / rel).read_text(encoding="utf-8")
        code_only_mutation = strip_comments(old) == strip_comments(new)
        if new == "" and not code_only_mutation:
            rows.append({"rel": rel, "kind": "摘除", "anchor_gone": old not in t})
        elif code_only_mutation:
            rows.append(
                {
                    "rel": rel,
                    "kind": "只改注释",
                    "code_unchanged": strip_comments(t)
                    == strip_comments((ROOT / rel).read_text(encoding="utf-8")),
                    "comment_actually_changed": old != new and new in t,
                }
            )
        else:
            rows.append({"rel": rel, "kind": "替换", "anchor_gone": new in t})
    return rows


def main() -> int:
    base = ROOT / f".r12_matrix_{os.getpid()}"
    rep = {"pid": os.getpid(), "cells": {}}
    live = copy_and_run(base / "L0")
    rep["cells"]["L0 现树（应全绿）"] = live
    for name, edits in CELLS.items():
        dst = base / re.sub(r"\W+", "_", name)
        copy_tree(dst)
        clean_pyc(dst)
        applied = apply_edits(dst, edits)
        clean_pyc(dst)
        py, gate = run_pytest(dst), run_gate(dst)
        rep["cells"][name] = {
            "edits": applied,
            "identity": identity(dst, edits),
            "pytest": py,
            "gate": gate,
        }
    shutil.rmtree(base, ignore_errors=True)
    (HERE / "verify_r12_matrix.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    bad = []
    if live["pytest"]["n_failed"] or live["pytest"]["crash"]:
        bad.append("L0 现树不绿 ⇒ 矩阵分母不可信")
    for name, cell in rep["cells"].items():
        if name.startswith("L0"):
            continue
        mutates_comment = any(r.get("kind") == "只改注释" for r in cell["identity"])
        if mutates_comment:
            if cell["pytest"]["n_failed"] != 0:
                bad.append(f"{name} 只改注释却有红 ⇒ 尺子在数散文")
        else:
            if cell["pytest"]["n_failed"] == 0:
                bad.append(f"{name} 摘掉后 0 红 ⇒ 锁不承重")
            if not all(r.get("anchor_gone", True) for r in cell["identity"]):
                bad.append(f"{name} 身份探针没翻假 ⇒ 改动没落到被读的那份")
    for name, cell in rep["cells"].items():
        if name.startswith("L0"):
            print(
                f"L0 {name}: pytest={cell['pytest']['summary']} gate={cell.get('gate', {}).get('conclusion')}"
            )
            continue
        print(
            f"{name}: pytest_red={cell['pytest']['n_failed']} gate_failed={cell['gate']['failed']} "
            f"identity={json.dumps(cell['identity'], ensure_ascii=False)[:150]}"
        )
        print(f"    FAILED例: {cell['pytest']['failed_ids'][:4]}")
    load = [
        n
        for n, c in rep["cells"].items()
        if not n.startswith("L0") and not any(r.get("kind") == "只改注释" for r in c["identity"])
    ]
    print(
        f"CONCLUSION cells={len(rep['cells'])} load_bearing_cells={len(load)} "
        f"all_red={all(rep['cells'][n]['pytest']['n_failed'] > 0 for n in load)} "
        f"comment_control_zero_red={rep['cells']['M5 只改注释（对照格，必须 0 红）']['pytest']['n_failed'] == 0} "
        f"bad={json.dumps(bad, ensure_ascii=False)} rc={0 if not bad else 1}"
    )
    return 0 if not bad else 1


def copy_and_run(tag: Path) -> dict:
    copy_tree(tag)
    clean_pyc(tag)
    out = {"pytest": run_pytest(tag), "gate": run_gate(tag), "identity": [{"anchor_gone": True}]}
    return out


if __name__ == "__main__":
    sys.exit(main())
