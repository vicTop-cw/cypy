"""R7+R8 锁承重矩阵：在副本树上逐格摘掉本环亲笔的判据面改动（R7 四处 + R8 一处），证明每条锁真的承重。

尺的形状（R6 矩阵的三条教训都在这里落地）：
1. 底树 = 盘面快照（`git archive HEAD` 会混进 8 月的旧码，本环改的是分析器/生成器，混因会造假红），
   副本树整体复制 `cypyc/` + `tests/` + 配置文件，起跑先做身份探针（`cypyc.__file__` 必须落在树内）；
2. 每格只摘一个变量，锚点必须先证 `count == 1`，摘完立刻按字节摘回并复核；
3. 判据取「汇总行的 N failed」而不是 rc（rc=0/5 都可能对应 0 selected）；
   并配一格「只动注释」的对照——对照若红，说明红的是尺不是锁。
4. M4 的第一版针是「kind 不等于 ComptimeStmt 就跳过」那道守卫；矩阵实测它不承重，进一步核过全语料
   （97 份可解析文件、3 个 ComptimeStmt 节点、0 个携带 type_annotation，
   见 logs/r7_comptime_fact_a1.txt）后确认是死代码，已删除；本文件的 M4 换成元数比较条件本身。
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
TREE = HERE / "lockproof_r7"
OUT = HERE / "verify_r7_locks.json"
LOGS = HERE / "logs"

GEN = "cypyc/codegen/cython_generator.py"
TCH = "cypyc/analyzer/type_checker.py"

# 每格：(格名, 目标文件, 唯一锚点, 替换成什么, 跑哪些测试)
MUTATIONS = [
    ("M1 生成器末路回到 str(node)", GEN,
     '        return "object"\n\n    def _trait_class_ref',
     '        return str(node)\n\n    def _trait_class_ref',
     ["tests/test_annotation_shape.py"]),
    ("M2 摘掉注解闭集校验挂钩", TCH,
     "        self._validate_annotation_shapes(node)",
     "        pass  # mutation: _validate_annotation_shapes disabled",
     ["tests/test_annotation_shape.py"]),
    ("M3 摘掉位置模式元数诊断", TCH,
     '                f"Positional pattern \'{node.type_name}\' has {len(node.args)} slot(s) but type "',
     '                f"MUTATED-NO-DIAG {node.type_name} "',
     ["tests/test_extractor_pattern.py"]),
    ("M4 让元数比较条件永假", TCH,
     "        if slots and len(node.args) > len(slots):",
     "        if False:  # mutation: arity comparison disabled",
     ["tests/test_extractor_pattern.py"]),
    ("M5 class 位置槽位退回 fields-only", TCH,
     "        for f in self._positional_fields(decl):",
     "        for f in (getattr(decl, 'fields', None) or []):  # mutation: R8 前的旧行为",
     ["tests/regression/test_corpus_pairs.py"]),
    ("C 对照：只动一行注释", GEN,
     "# BUG-34/BUG-108）：分析器已经拒绝非法标注形态，这里再退化成 object，",
     "# BUG-34/BUG-108）：分析器已经拒绝非法标注形态，这里再退化成 object，（对照格只改注释）",
     ["tests/test_annotation_shape.py"]),
]


def build_tree() -> None:
    if TREE.exists():
        shutil.rmtree(TREE)
    TREE.mkdir(parents=True)
    for d in ("cypyc", "tests", "corpus", "scripts"):
        shutil.copytree(ROOT / d, TREE / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pyproject.toml", "setup.cfg", "pytest.ini", "conftest.py"):
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, TREE / f)
    (TREE / "memory").mkdir(exist_ok=True)


def read(rel: str) -> str:
    return (TREE / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    tmp = TREE / (rel + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, TREE / rel)


def identity_probe() -> tuple:
    p = subprocess.run([sys.executable, "-X", "utf8", "-c",
                        "import cypyc, cypyc.analyzer.type_checker as t, cypyc.codegen.cython_generator as g;"
                        "print(cypyc.__file__);print(t.__file__);print(g.__file__)"],
                       cwd=TREE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    paths = [ln.strip() for ln in p.stdout.splitlines() if ln.strip().endswith(".py")]
    ok = p.returncode == 0 and len(paths) == 3 and all(
        str(Path(x).resolve()).startswith(str(TREE.resolve())) for x in paths)
    return ok, paths, p.returncode


def run_pytest(files: list) -> dict:
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", *files, "-p", "no:cacheprovider",
                        "--tb=line"],
                       cwd=TREE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    # 计数只认「汇总行」的形状（`=== 3 failed, 41 passed in 0.44s ===`）。
    # R8 a2 轮实测教训：原先对整段 stdout 做 `(\d+) error` 检索，被 corpus 断言 repr 里的
    # `checker.errors` 文本喂出 11 ⇒ M5 被误判成「尺坏了」，而 failed+passed=44=collected 明明自洽。
    summary = next((ln.strip() for ln in reversed(out.splitlines())
                    if re.search(r"^=+ .*(failed|passed|error).* in .* =+$", ln)), "")

    def num(pat: str) -> int:
        m = re.search(pat, summary)
        return int(m.group(1)) if m else 0

    failed = num(r"(\d+) failed")
    passed = num(r"(\d+) passed")
    errors = num(r"(\d+) error")
    skipped = num(r"(\d+) skipped")
    collected_m = re.search(r"collected (\d+)", out)
    collected = int(collected_m.group(1)) if collected_m else -1
    arith_ok = collected < 0 or (failed + passed + skipped + errors) == collected
    stray = [ln.strip()[:120] for ln in out.splitlines() if re.search(r"\d+ error", ln)][:3]
    internal = "INTERNALERROR" in out or "Traceback (most recent call last)" in out.split("====")[-1]
    return {"rc": p.returncode, "failed": failed, "passed": passed, "errors": errors,
            "skipped": skipped, "collected": collected,
            "count_arith_ok": arith_ok,
            "stray_error_lines": stray,
            "collect_or_internal_errors": errors if not arith_ok else 0,
            "internal_error": internal,
            "summary_line": summary[:160]}


def main() -> int:
    LOGS.mkdir(exist_ok=True)
    build_tree()
    id_ok, id_paths, id_rc = identity_probe()
    rep = {"tree": TREE.relative_to(ROOT).as_posix(), "identity_ok": id_ok,
           "identity_paths": id_paths, "identity_rc": id_rc, "cells": []}
    if not id_ok:
        rep["refuse"] = "身份探针不过 ⇒ 副本树没被真正使用，整份矩阵不作数"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1

    for name, rel, anchor, replacement, files in MUTATIONS:
        src = read(rel)
        n = src.count(anchor)
        cell = {"cell": name, "file": rel, "anchor_count": n, "tests": files}
        if n != 1:
            cell.update({"verdict": "锚点不唯一 ⇒ 本格拒跑", "carries": False})
            rep["cells"].append(cell)
            continue
        write(rel, src.replace(anchor, replacement, 1))
        res = run_pytest(files)
        back = read(rel)
        assert back != src and replacement in back, name
        write(rel, src)
        restored = read(rel) == src
        cell["run"] = res
        cell["restored_bytes_identical"] = restored
        if name.startswith("C "):
            carries = res["failed"] == 0 and res["rc"] == 0
            cell["verdict"] = ("对照绿（尺没坏）" if carries
                               else f"对照红了 {res['failed']} ⇒ 红的是尺，本矩阵全部改判")
        else:
            if res.get("collect_or_internal_errors") or not res.get("count_arith_ok", True):
                carries, cell["verdict"] = False, "尺坏了：出现 error/内部错误或计数不自洽，本格读数不作数"
            else:
                carries = res["failed"] >= 1 and not res["internal_error"]
                cell["verdict"] = ("承重：摘掉即红" if carries
                                   else "不承重：摘掉仍全绿 ⇒ 该锁没锁住任何东西")
        cell["carries"] = carries
        rep["cells"].append(cell)
        (LOGS / f"r7_lock_{name.split()[0]}.txt").write_text(
            json.dumps(cell, ensure_ascii=False, indent=1), encoding="utf-8")

    control = next((c for c in rep["cells"] if c["cell"].startswith("C ")), None)
    rep["control_green"] = bool(control and control.get("carries"))
    rep["load_bearing"] = [c["cell"] for c in rep["cells"]
                           if not c["cell"].startswith("C ") and c.get("carries")]
    rep["not_load_bearing"] = [c["cell"] for c in rep["cells"]
                               if not c["cell"].startswith("C ") and not c.get("carries")]
    # 摘回自证：两个被改过的文件在副本树里必须与盘面逐字节相同（活树本身没被碰过）
    same = {rel: (TREE / rel).read_bytes() == (ROOT / rel).read_bytes()
            for rel in (GEN, TCH)}
    rep["tree_restores_byte_identical"] = same
    if not all(same.values()):
        rep["refuse"] = f"副本树未摘回：{[k for k, v in same.items() if not v]}"
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in rep["cells"]:
        print(f"{c['cell']:<34} anchor={c['anchor_count']} "
              f"run={c.get('run', {}).get('failed', '-')}/{c.get('run', {}).get('passed', '-')} "
              f"restored={c.get('restored_bytes_identical', '-')} verdict={c['verdict']}")
    print(f"CONCLUSION control_green={rep['control_green']} "
          f"load_bearing={len(rep['load_bearing'])}/{len(MUTATIONS) - 1} not_load_bearing={rep['not_load_bearing']} "
          f"anchor_cells_refused={[c['cell'] for c in rep['cells'] if c['anchor_count'] != 1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
