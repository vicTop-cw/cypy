"""R11 验证腿：变异矩阵 —— 证明 R11 的锁与 Ω-spec `cypy.generic.class` 是**承重的**。

七格（每格一棵独立树，树名带 pid 防并发掏空；禁 commit 的红线不变，只在副本树上动手）：
 L0 live（本轮修复后）                    ⇒ 期望 0 红
 L1 只退解析器（类不收参数表）              ⇒ 期望泛型类那几支红
 L2 只退注解位元数门                        ⇒ 期望 arity 双向锁红
 L3 只退接收者代入（class 分支回到旧三行）   ⇒ 期望代入/手册范例锁红
 L4 只退形式参数守卫（删守卫 + 删 _visit_ClassDef）⇒ 期望名字表锁红
 L5 只退 struct 裸名擦除（object → Type(param)）⇒ 期望 struct 对照锁红
 L6 只改注释（语义逐字不变，对照格）        ⇒ 期望 0 红：尺子没在数我的散文

锚点纪律（上一版矩阵把这三条踩了一遍，见 logs/r11_locks_a1.out 的 L2/L3/L4 ruler_crash）：
 · 锚的**文本**不手抄 —— 从盘面文件里按起止针切出来，切不到就 refuse；
 · 区间用行数判，不用字符偏移（`index()` 给的是字符）；
 · 身份探针要摘得准：`_parse_type_param_list(name_token)` 那行 class/struct 两处都有，
   拿它当身份 ⇒ 退掉 class 那处也读成 True（恒真探针，等于没探）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = ["cypyc", "cypy_bridge", "scripts", "corpus", "tests", "examples", "SYNTAX", "PROJECT-SPEC"]
SUITE = ["tests/test_generic_class_r11.py", "tests/regression/test_corpus_pairs.py",
         "tests/test_generic_callsite_r10.py"]
PARSER = "cypyc/parser/parser.py"
CHECKER = "cypyc/analyzer/type_checker.py"
LOG = ROOT / ".fist-loop-20260929" / "logs" / "r11_locks_matrix_a2.json"


def block(text: str, start_sub: str, end_sub: str, max_lines: int) -> str:
    """从盘面文本里切出 [起点所在行, 终点所在行] 的整块。

    起点针允许多处命中（如 `_parse_type_param_list(name_token)` 在 class 与 struct 两处逐字相同），
    靠"终点针在 max_lines 行内跟随"来消歧 ⇒ 满足条件的起点必须恰好一个，否则 refuse。
    """
    lines = text.splitlines()
    cands = []
    for i, ln in enumerate(lines):
        if start_sub not in ln:
            continue
        rel = next((m for m in range(i, min(i + max_lines + 1, len(lines))) if end_sub in lines[m]), None)
        if rel is not None:
            cands.append((i, rel))
    assert len(cands) == 1, f"起点+终点组合命中 {len(cands)} 处（应为 1）：{start_sub!r} → {end_sub!r}"
    i, rel = cands[0]
    out = "\n".join(lines[i:rel + 1])
    assert text.count(out) == 1, "切出的块在文件里不唯一 ⇒ 起点/终点选错"
    return out


def copy_tree(dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in KEEP:
        shutil.copytree(ROOT / name, dst / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pytest.ini", "pyproject.toml", "setup.py", "conftest.py", "mypy.ini"):
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, dst / f)


def apply_faces(dst: Path, faces) -> list:
    log = []
    for rel, old, new in faces:
        p = dst / rel
        t = p.read_text(encoding="utf-8")
        n = t.count(old)
        assert n == 1, f"锚点 {rel} 命中 {n} 次（必须恰好 1 次）：{old[:60]!r}"
        p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
        after = p.read_text(encoding="utf-8")
        if new:
            assert new in after
        compile(after, str(p), "exec")
        log.append({"file": rel, "needle": old[:48].replace("\n", "\\n"), "lines": old.count("\n") + 1})
    return log


def run_pytest(dst: Path) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", *SUITE,
                        "-p", "no:cacheprovider", "--tb=no", "-rf"],
                       cwd=str(dst), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    out = r.stdout + r.stderr
    failed = sorted({m for m in re.findall(r"(?m)^FAILED (\S+)", out)})
    return {"rc": r.returncode, "failed_ids": failed, "n_failed": len(failed),
            "crash": r.returncode not in (0, 1),
            "collect_errors": len(re.findall(r"(?m)^ERROR ", out)),
            "summary_line": (re.findall(r"=+ .*(?:failed|passed|error).*?=+", out) or [""])[-1],
            "n_passed": (int(re.search(r"(\d+) passed", out).group(1))
                         if re.search(r"(\d+) passed", out) else None)}


def identity(dst: Path) -> dict:
    pa = (dst / PARSER).read_text(encoding="utf-8")
    tc = (dst / CHECKER).read_text(encoding="utf-8")
    return {"parser_class_records_params": "generic_params=generic_params, generic_constraints="
                                          "generic_constraints," in pa,
            "checker_annotation_gate": "decl = self.class_defs.get(node.name) or self.struct_defs" in tc,
            "checker_receiver_substitution": "declared = list(getattr(class_def, 'generic_params', [])"
                                             " or [])" in tc,
            "checker_formal_guard": "return_type.name in self._generic_formal_params" in tc,
            "checker_struct_erasure": ("for param in getattr(struct_def, 'generic_params', []):\n"
                                       '                    self.type_map[param] = Type("object")') in tc}


def main() -> int:
    live_pa = (ROOT / PARSER).read_text(encoding="utf-8")
    live_tc = (ROOT / CHECKER).read_text(encoding="utf-8")

    # —— 从盘面反解锚（不手抄），并留下逐格的旧形态 ——
    A1 = block(live_pa, "self._parse_type_param_list(name_token)", "bases = []", 3)
    A1_OLD = "        bases = []"
    A2 = block(live_pa, "name_token.value, bases, body, name_token.line", "        )", 3)
    A2_OLD = ("            name_token.value, bases, body, name_token.line, name_token.col, "
              "is_cdef=is_cdef\n        )")
    B1 = block(live_tc, "「泛型类」规则 3：注解位", "self.errors.append(diag)", 12) + "\n\n"
    B2 = block(live_tc, "class_def = self.class_defs[vname]", "self.type_map = old_type_map", 25)
    B2_OLD = ("                class_def = self.class_defs[vname]\n"
              "                for body_stmt in class_def.body:\n"
              "                    if isinstance(body_stmt, LetStmt) and body_stmt.name == node.attr:\n"
              "                        return self._visit(body_stmt.type_annotation)\n"
              "                    elif isinstance(body_stmt, FuncDef) and body_stmt.name == node.attr:\n"
              "                        return self._get_type_from_node(body_stmt.return_type)")
    B3 = block(live_tc, "in self._generic_formal_params:", 'return_type = Type("object")', 6)
    B4 = block(live_tc, "for param in getattr(struct_def, 'generic_params', []):",
               'self.type_map[param] = Type("object")', 2)
    B4_OLD = B4.replace('Type("object")', "Type(param)")

    CASES = {
        "L0": {"label": "L0 live（修复后）", "faces": [], "expect_min": 0},
        "L1": {"label": "L1 只退解析器", "faces": [(PARSER, A1, A1_OLD), (PARSER, A2, A2_OLD)],
               "expect_min": 3, "expect_identity_false": "parser_class_records_params"},
        "L2": {"label": "L2 只退注解位元数门", "faces": [(CHECKER, B1, "")],
               "expect_min": 1, "expect_identity_false": "checker_annotation_gate"},
        "L3": {"label": "L3 只退接收者代入", "faces": [(CHECKER, B2, B2_OLD)],
               "expect_min": 2, "expect_identity_false": "checker_receiver_substitution"},
        "L4": {"label": "L4 只退形式参数守卫", "faces": [(CHECKER, B3, "")],
               "expect_min": 1, "expect_identity_false": "checker_formal_guard"},
        "L5": {"label": "L5 只退 struct 裸名擦除", "faces": [(CHECKER, B4, B4_OLD)],
               "expect_min": 1, "expect_identity_false": "checker_struct_erasure"},
        "L6": {"label": "L6 只改注释（对照格）",
               "faces": [(CHECKER, block(live_tc, "遍历形状与从前一致", "遍历形状与从前一致", 0),
                          "        遍历形状与从前一致（照旧走 `_visit_children`），差别是把类声明的类型参数名记下来。")],
               "expect_min": 0, "must_be_zero": True},
    }

    rep = {"pid": os.getpid(), "cases": {}, "anchors": {
        k: v for k, v in {"A1": A1, "A2": A2, "B1": B1, "B2": B2, "B3": B3, "B4": B4}.items()}}
    base = ROOT / f".lockproof_r11_{os.getpid()}"
    for key, spec in CASES.items():
        dst = base / key
        copy_tree(dst)
        try:
            rep["cases"][key] = {"mutations": apply_faces(dst, spec["faces"])}
        except AssertionError as exc:
            rep["cases"][key] = {"ruler_crash": str(exc), "label": spec["label"]}
            continue
        res = run_pytest(dst)
        res["identity"] = identity(dst)
        res["label"] = spec["label"]
        rep["cases"][key].update(res)

    cells = [c for c in rep["cases"].values() if "rc" in c]
    live = rep["cases"].get("L0", {})
    gates = {
        "cells_run": len(cells),
        "cells_expected": len(CASES),
        "l0_zero_red": live.get("n_failed") == 0 and not live.get("crash"),
        "l0_identity_all_true": all(live.get("identity", {}).values()),
        "no_ruler_crash": all("ruler_crash" not in c and not c.get("crash")
                              and c.get("collect_errors", 0) == 0 for c in rep["cases"].values()),
        "comment_only_control_zero_red": rep["cases"].get("L6", {}).get("n_failed") == 0,
    }
    load = {}
    for key in ("L1", "L2", "L3", "L4", "L5"):
        c = rep["cases"].get(key, {})
        need = CASES[key]["expect_min"]
        probe = CASES[key].get("expect_identity_false")
        load[key] = {"n_failed": c.get("n_failed"), "required_min": need,
                     "identity_flipped": (c.get("identity", {}).get(probe) is False) if probe else None,
                     "first_ids": c.get("failed_ids", [])[:3],
                     "red_ids": c.get("failed_ids", [])[:]}
    gates["load_bearing_every_cell"] = all(
        (v["n_failed"] or 0) >= v["required_min"] for v in load.values())
    gates["identity_flipped_every_cell"] = all(
        v["identity_flipped"] is True for k, v in load.items() if v["identity_flipped"] is not None)
    rep["load_bearing"] = load
    rep["gates"] = gates
    LOG.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    for key, c in rep["cases"].items():
        print(f"{key} {c.get('label','')} | red={c.get('n_failed')} rc={c.get('rc')} "
              f"crash={c.get('crash')} ids={c.get('failed_ids', [])[:3]}")
    print("GATES " + json.dumps(gates, ensure_ascii=False))
    ok = (gates["cells_run"] == gates["cells_expected"] and gates["l0_zero_red"]
          and gates["l0_identity_all_true"] and gates["no_ruler_crash"]
          and gates["load_bearing_every_cell"] and gates["identity_flipped_every_cell"]
          and gates["comment_only_control_zero_red"])
    n_cells = gates["cells_run"]
    n_probed = sum(1 for v in load.values() if v["identity_flipped"] is not None)
    n_flipped = sum(1 for v in load.values() if v["identity_flipped"] is True)
    n_bearing = sum(1 for v in load.values() if (v["n_failed"] or 0) >= v["required_min"])
    print(f"CONCLUSION cells={n_cells}/{gates['cells_expected']} "
          f"load_bearing={n_bearing}/{len(load)} identity_flips={n_flipped}/{n_probed} "
          f"comment_control_zero_red={gates['comment_only_control_zero_red']} rc={0 if ok else 1}")
    shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
