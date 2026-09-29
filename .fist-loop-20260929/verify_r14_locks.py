"""R14 承重矩阵：把字典推断件与键值位接线逐个摘掉，证明本轮新增的锁不是运气。

骨架沿用 R13 那份（被实测走通的），锚点全部取自现状字节。七格（L0 现树 + 5 格承重 + 1 格对照）：
 M1 字面量退回「不推断」（只改那一行 return ⇒ 单变量变异），
 M2 把 dict 摘出判定集合，
 M3 撤掉数值阶梯取最宽那支，
 M4 撤掉 dict 的 key/value 文案分支（只动措辞判据，不动判定），
 M5 摘掉赋值位调用（证明 dict 也靠这一行），
 M6 只改整行注释对照（必须 0 红，否则尺子在数散文）。
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
SPEC_OP = "cypy.dict.elements"
LOCK_TESTS = "tests/test_dict_elements_r14.py"

DICT_RETURN = (
    '        return Type("dict", generic_params=[self._slot_lub(keys), self._slot_lub(values)])\n'
)
DICT_RETURN_NONE = "        return None  # 变异格：字面量退回「不推断」\n"

CONTAINER_SET = "    _ELEMENT_CHECKED_CONTAINERS = ('list', 'set', 'tuple', 'Array', 'dict')\n"
CONTAINER_SET_NO_DICT = "    _ELEMENT_CHECKED_CONTAINERS = ('list', 'set', 'tuple', 'Array')\n"

LUB_NUMERIC = "        if names <= set(self._NUMERIC_WIDENING):\n"
LUB_NO_NUMERIC = "        if False:  # 变异格：数值串不再取阶梯最宽\n"

DICT_WORDING = "            if want.name == 'dict' and idx in (1, 2):\n"
DICT_WORDING_OFF = "            if False:  # 变异格：dict 的位名退回 element N\n"

LET_CALL = """                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self._check_container_elements(declared_type, value_type, node)
                    self.type_map[node.name] = declared_type
"""
LET_PLAIN = """                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self.type_map[node.name] = declared_type
"""

# 对照格的锚**从产品文件里现取**（上一版我凭记忆手敲了整行注释，少打"类型"两个字 ⇒ count=0，
# 断言当场拒跑）。定位词只负责找到那一行，命中数不是 1 就停手；变异 = 在该行内部替换一个词。
_hits = [ln for ln in (ROOT / TC).read_text(encoding="utf-8").splitlines(True) if "同一把尺" in ln]
assert len(_hits) == 1, f"对照格定位词命中 {len(_hits)} 次 ⇒ 不唯一，停手"
COMMENT_LINE = _hits[0]
COMMENT_MUTATED = COMMENT_LINE.replace("同一把尺", "同一把尺子")
assert COMMENT_MUTATED != COMMENT_LINE, "假变异：替换后与原文逐字相同"

CELLS = {
    "M1 字面量退回不推断": [(TC, DICT_RETURN, DICT_RETURN_NONE)],
    "M2 把 dict 摘出判定集合": [(TC, CONTAINER_SET, CONTAINER_SET_NO_DICT)],
    "M3 撤掉数值阶梯取最宽": [(TC, LUB_NUMERIC, LUB_NO_NUMERIC)],
    "M4 撤掉 dict 位名文案分支": [(TC, DICT_WORDING, DICT_WORDING_OFF)],
    "M5 摘掉赋值位调用": [(TC, LET_CALL, LET_PLAIN)],
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
    base = ROOT / f".r14_matrix_{os.getpid()}"
    rep = {"pid": os.getpid(), "cells": {}}
    rep["cells"]["L0 现树（应全绿）"] = cell(base, "L0", [])
    for name, edits in CELLS.items():
        rep["cells"][name] = cell(base, name, edits)
    shutil.rmtree(base, ignore_errors=True)
    (HERE / "verify_r14_matrix.json").write_text(
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
