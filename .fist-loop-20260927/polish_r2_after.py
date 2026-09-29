#!/usr/bin/env python3
"""R2-打磨 的"删除之后"复算：符号集合不变、被删文本可独立反解、遮蔽计数归零。

与 `polish_r2_cut.py` 的分工：删除驱动自带断言，但那些断言是**它自己写的**——本脚本换一路口径
从**仓库外快照**（`E:/IDEProjects/AI/_cypy_snapshots/pre_polish_r2`，删前 323 个受版本控制文件）
反解"到底少了什么"，用来抓删除驱动自己的错：
 1) 顶层/类内符号**集合**逐档相同（BUG-42 只该削掉重名的一份，不该让任何名字消失）；
 2) 快照里按驱动记的行区间切出来的文本，必须与驱动写进证据的 `removed_text` **逐字相同**
    （否则驱动"删了什么"这句话只有它自己作证）；
 3) 全树同名方法遮蔽计数归零；
 4) 行数差 == 驱动记的删除行数，且仅这两档；其余档位若也变了 ⇒ 照列不认领（并发 lane）。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
SNAP = Path(r"E:\IDEProjects\AI\_cypy_snapshots\pre_polish_r2")
CUT = ROOT / ".fist-loop-20260927" / "polish_r2_cut.json"
OUT = ROOT / ".fist-loop-20260927" / "polish_r2_after.json"

EXPECTED = {
    "cypyc/codegen/cython_generator.py": {"name": "_visit_ExprStmt", "target": "bug42_expr_stmt"},
    "cypyc/analyzer/scope_analyzer.py": {"name": "_visit_MetaBlock", "target": "bug42_meta_block"},
}


def symbols(tree: ast.Module) -> dict:
    """模块级名字集合 + 每个类体内的方法名集合（用 set：重名塌缩，正是本环关心的口径）。"""
    mod = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mod.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    mod.add(tgt.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                mod.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            mod.add(node.target.id)
    classes = {}
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        methods = {}
        for item in cls.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[item.name] = methods.get(item.name, 0) + 1
        classes[cls.name] = methods
    return {"module": sorted(mod), "classes": classes}


def duplicates(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    syms = symbols(tree)["classes"]
    out = []
    for cls, methods in syms.items():
        for name, count in methods.items():
            if count > 1:
                out.append(f"{cls}.{name}x{count}")
    return out


def main() -> int:
    refuse: list = []
    notes: dict = {}
    if not SNAP.exists():
        print(json.dumps({"refuse": ["快照目录不在：加仓库外快照这一步没做"]}, ensure_ascii=False))
        return 1
    cut = json.loads(CUT.read_text(encoding="utf-8")) if CUT.exists() else {}
    if not cut or cut.get("dry_run"):
        refuse.append("删除证据缺失或是 dry-run 产物（不能拿 dry-run 当已落盘）")

    measures = cut.get("measures") or {}
    doc: dict = {"refuse": refuse, "files": {}, "dupes_after": {}, "tree_dupes": []}

    snap_files = sorted(p.relative_to(SNAP).as_posix() for p in SNAP.rglob("*.py"))
    for rel in snap_files:
        now_p = ROOT / rel
        snap_p = SNAP / rel
        if not now_p.exists():
            doc.setdefault("missing_now", []).append(rel)
            continue
        snap_lines = snap_p.read_text(encoding="utf-8", errors="replace").split("\n")
        now_text = now_p.read_text(encoding="utf-8", errors="replace")
        now_lines = now_text.split("\n")
        entry: dict = {
            "snap_lines": len(snap_lines),
            "now_lines": len(now_lines),
            "line_delta": len(now_lines) - len(snap_lines),
        }
        # 只有本环亲笔的两档才配让判据红；别档的符号变化多半是并发 lane 的在飞改动 ⇒ 照列不认领。
        mine = rel in EXPECTED

        def flag(msg: str, _mine: bool = mine, _rel: str = rel) -> None:
            (refuse if _mine else notes.setdefault(_rel, [])).append(msg)

        try:
            s_before = symbols(ast.parse("\n".join(snap_lines)))
            s_after = symbols(ast.parse(now_text))
        except SyntaxError as exc:
            flag(f"{rel} 解析破裂：{str(exc)[:120]}")
            doc["files"][rel] = entry
            continue
        entry["module_symbols_equal"] = s_before["module"] == s_after["module"]
        if s_before["module"] != s_after["module"]:
            flag(f"{rel} 模块级符号集合变了")
        if set(s_before["classes"]) != set(s_after["classes"]):
            flag(f"{rel} 类集合变了")
        for cls in set(s_before["classes"]) & set(s_after["classes"]):
            b, a = s_before["classes"][cls], s_after["classes"][cls]
            if set(b) != set(a):
                flag(f"{rel} 类 {cls} 的方法名集合变了：{sorted(set(b) ^ set(a))}")
            for name in sorted(set(b) & set(a)):
                if b[name] != a[name]:
                    entry.setdefault("multiplicity_changed", []).append(f"{cls}.{name}:{b[name]}->{a[name]}")
        if rel in EXPECTED:
            spec = EXPECTED[rel]
            rec = measures.get(spec["target"]) or {}
            entry["removed_range"] = rec.get("removed_range")
            entry["removed_lines_claimed"] = rec.get("removed_lines")
            entry["removed_sha8"] = rec.get("removed_sha8")
            lo, hi = (rec.get("removed_range") or [0, 0])[0] - 1, (rec.get("removed_range") or [0, 0])[1]
            sliced = "\n".join(snap_lines[lo:hi])
            entry["slice_from_snapshot_matches_removed_text"] = sliced == rec.get("removed_text")
            if sliced != rec.get("removed_text"):
                refuse.append(f"{rel} 快照按驱动行区间切出的文本 != 驱动记的 removed_text（驱动自证不可信）")
            if entry["line_delta"] != -(rec.get("removed_lines") or 0):
                refuse.append(f"{rel} 行数差 {entry['line_delta']} 与声称删除 {rec.get('removed_lines')} 不吻合")
            owner = next((c for c, m in s_before["classes"].items() if spec["name"] in m), "")
            want = f"{owner}.{spec['name']}:{s_before['classes'][owner][spec['name']]}->1"
            entry["multiplicity_expected"] = want
            if entry.get("multiplicity_changed") != [want]:
                refuse.append(
                    f"{rel} 重名塌缩记录不是唯一一条且逐字为 {want}：{entry.get('multiplicity_changed')}"
                )
            if len(entry.get("multiplicity_changed") or []) != 1:
                refuse.append(f"{rel} 本档只允许一处重名塌缩，实测 {entry.get('multiplicity_changed')}")
        doc["files"][rel] = entry

    for rel in sorted(EXPECTED):
        if rel not in doc["files"]:
            refuse.append(f"预期档位不在快照里：{rel}")

    tree_dupes = {}
    for path in sorted((ROOT / "cypyc").rglob("*.py")):
        d = duplicates(path)
        if d:
            tree_dupes[path.relative_to(ROOT).as_posix()] = d
    doc["tree_dupes"] = tree_dupes
    if tree_dupes:
        refuse.append(f"全树仍有同名遮蔽：{json.dumps(tree_dupes, ensure_ascii=False)[:200]}")

    other_deltas = {
        rel: e["line_delta"]
        for rel, e in doc["files"].items()
        if rel not in EXPECTED and e.get("line_delta")
    }
    doc["other_file_line_deltas"] = other_deltas

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/test_polish_20260927_r2.py", "-q",
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    doc["polish_tests"] = {"rc": proc.returncode, "line": tail[-1] if tail else ""}
    if proc.returncode != 0:
        refuse.append(f"本轮新增回归锁未全绿：{doc['polish_tests']['line']}")

    probe = subprocess.run(
        [sys.executable, "-X", "utf8", "-c",
         "import json;"
         "from cypyc.codegen.cython_generator import CythonGenerator as G;"
         "from cypyc.analyzer.scope_analyzer import ScopeAnalyzer as S;"
         "print(json.dumps({'_visit_ExprStmt':G._visit_ExprStmt.__code__.co_firstlineno,"
         "'_visit_MetaBlock':S._visit_MetaBlock.__code__.co_firstlineno}))"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    doc["bound_after"] = json.loads(probe.stdout.strip().splitlines()[-1]) if probe.returncode == 0 else {}
    if probe.returncode != 0:
        refuse.append("绑定探针重跑失败：产品码在删除后导不起来了")

    doc["concurrent_symbol_notes"] = notes
    doc["refuse"] = refuse
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    print(json.dumps({
        "refuse": refuse,
        "tree_dupes": tree_dupes,
        "bound_after": doc["bound_after"],
        "expected_deltas": {r: doc["files"].get(r, {}).get("line_delta") for r in EXPECTED},
        "other_file_line_deltas": len(other_deltas),
        "polish_tests": doc["polish_tests"],
    }, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
