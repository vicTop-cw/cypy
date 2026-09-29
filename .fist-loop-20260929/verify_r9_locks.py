"""R9 承重矩阵：证明本轮两条修复各自的锁「摘掉即红」，而不是只多了一组恒绿断言。

底树 = 当前盘面复制（本仓禁 commit，HEAD 是 08-17，不能拿 `git archive HEAD` 当底树）。
每进程一棵树（固定路径的快照树会被并发 rmtree 掏空），摘回后逐字节比对。
变异只落在副本树上，活树在本次 pytest 运行期间一律不动。
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
TREE = HERE / f"lockproof_r9_{os.getpid()}"
OUT = HERE / "verify_r9_locks.json"
COPY_SET = ("cypyc", "scripts", "corpus", "tests/regression", "tests/__init__.py", "pyproject.toml",
            "conftest.py")

MUTATIONS = [
    ("S1 切片形态判断恒假（退回「切片当元素」）", "cypyc/analyzer/type_checker.py",
     '        return isinstance(slice_node, dict) and slice_node.get("slice") is True',
     '        return False  # mutation S1'),
    ("S2 越界槽位退回发 `__f{i}` 成员访问", "cypyc/codegen/cython_generator.py",
     """                if fields_known and i >= len(fields):
                    conds.append("False")
                    continue""",
     """                if False:
                    conds.append("False")
                    continue"""),
]

CONTROL = ("C 对照：只动一行注释", "cypyc/analyzer/type_checker.py",
           "        解析器把切片形态落成普通 dict", "        解析器把切片形态落成普通字典")


def build_tree() -> None:
    if TREE.exists():
        shutil.rmtree(TREE)
    TREE.mkdir(parents=True)
    for rel in COPY_SET:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = TREE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    # 本矩阵只跑 corpus 回归件与 Ω-gate，不需要整棵 tests 树（gate 自己就是判据面）


def identity_probe() -> tuple:
    code = (
        "import importlib.util,json,sys;sys.path.insert(0,r'%s');"
        "spec=importlib.util.spec_from_file_location('g',r'%s');"
        "g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g);"
        "print('TREE='+g.__file__)"
    ) % (str(TREE), str(TREE / "scripts" / "omega_gate.py"))
    p = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=TREE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    got = (p.stdout + p.stderr)
    # 反斜杠归一化要同时作用在 needle 与**被测输出**上：只 replace 自己写的 needle，
    # 而 node/python 打出来的是 `E:\\...` 原生分隔符 ⇒ 探针恒假、整份矩阵被自己拒跑。
    norm = lambda s: s.replace("\\", "/").lower()
    hit = norm(str(TREE)) in norm(got)
    return hit, got[-200:], p.returncode


def run_gate() -> dict:
    p = subprocess.run([sys.executable, "-X", "utf8", "scripts/omega_gate.py"], cwd=TREE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    concl = next((ln.strip() for ln in reversed(out.splitlines()) if ln.startswith("CONCLUSION")), "")
    m = dict(re.findall(r"(\w+)=(\d+|100\.\d+%)", concl))
    fail_rows = [ln.strip()[:150] for ln in out.splitlines() if ln.strip().startswith("FAIL")]
    return {"rc": p.returncode, "conclusion": concl, "counts": m,
            "failed_rows": fail_rows, "n_fail_rows": len(fail_rows)}


def read(rel: str) -> str:
    return (TREE / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (TREE / rel).write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    build_tree()
    id_ok, id_out, id_rc = identity_probe()
    rep = {"tree": TREE.name, "identity_ok": id_ok, "identity_rc": id_rc,
           "identity_tail": id_out[-160:], "cells": []}
    if not id_ok:
        rep["refuse"] = "身份探针不过 ⇒ 副本树没被真正使用，整份矩阵不作数"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1

    base = run_gate()
    rep["baseline"] = base
    carries, not_carry = [], []
    for name, rel, anchor, repl in MUTATIONS + [CONTROL]:
        src = read(rel)
        n = src.count(anchor)
        cell = {"cell": name, "file": rel, "anchor_count": n}
        if n != 1:
            cell["verdict"] = "锚点不唯一 ⇒ 本格拒跑"
            rep["cells"].append(cell)
            not_carry.append(name)
            continue
        write(rel, src.replace(anchor, repl, 1))
        res = run_gate()
        mutated = read(rel)
        assert mutated != src and repl in mutated, name
        write(rel, src)
        restored = read(rel) == src
        cell.update({"run": res, "restored_bytes_identical": restored})
        if name.startswith("C "):
            green = res["rc"] == 0 and res["n_fail_rows"] == 0
            cell["verdict"] = "对照绿（尺没坏）" if green else f"对照红了 ⇒ 红的是尺：{res['conclusion']}"
            rep["control_green"] = green
        else:
            red = res["rc"] == 1 and res["n_fail_rows"] >= 1
            carries.append(name) if red else not_carry.append(name)
            cell["verdict"] = ("承重：摘掉即红 " + "；".join(r[:40] for r in res["failed_rows"][:2])
                               if red else f"不承重：摘掉仍 {res['conclusion']}")
        rep["cells"].append(cell)

    rep["load_bearing"] = carries
    rep["not_load_bearing"] = not_carry
    rep["control_green"] = rep.get("control_green", False)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for cell in rep["cells"]:
        print(cell["cell"], "| anchor=%s | rc=%s fails=%s | %s"
              % (cell.get("anchor_count"), (cell.get("run") or {}).get("rc"),
                 (cell.get("run") or {}).get("n_fail_rows"), cell.get("verdict", "")))
    print(f"CONCLUSION baseline={base['conclusion']} control_green={rep['control_green']} "
          f"load_bearing={len(carries)}/{len(MUTATIONS)} not_load_bearing={not_carry}")
    return 0 if (rep["control_green"] and not not_carry) else 1


if __name__ == "__main__":
    main()
