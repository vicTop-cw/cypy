#!/usr/bin/env python3
"""R2-打磨 生效性证据：把"谁被谁遮住"做成数出来的事实，而不是 flake8 的一句 F811。

三条独立口径必须互相咬合，否则视为判据坏了：
 1) AST：同一类体内同名 FunctionDef 的出现行号与体长；
 2) 运行时：`类.__dict__[名].__code__.co_firstlineno` 给出真正生效的那一份；
 3) 行数：被遮住那份的函数体行数（判断"丢了多少逻辑"，不断言哪份是意图）。
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "polish_r2_evidence.json"

TARGETS = {
    "cypyc/codegen/cython_generator.py": "cypyc.codegen.cython_generator",
    "cypyc/analyzer/scope_analyzer.py": "cypyc.analyzer.scope_analyzer",
}


def scan(path: Path) -> dict:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        seen: dict = {}
        for item in cls.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.setdefault(item.name, []).append(item)
        for name, defs in seen.items():
            if len(defs) > 1:
                out[f"{cls.name}.{name}"] = {
                    "class_lineno": cls.lineno,
                    "definitions": [
                        {
                            "lineno": d.lineno,
                            "end_lineno": getattr(d, "end_lineno", None),
                            "body_lines": (getattr(d, "end_lineno", d.lineno) or d.lineno) - d.lineno,
                        }
                        for d in defs
                    ],
                }
    return out


def main() -> int:
    doc = {"refuse": [], "files": {}, "live": {}, "symbol_set": {}}
    for rel, mod in TARGETS.items():
        p = ROOT / rel
        if not p.exists():
            doc["refuse"].append(f"文件不在盘上：{rel}")
            continue
        doc["files"][rel] = scan(p)

    sys.path.insert(0, str(ROOT))
    for rel, mod in TARGETS.items():
        m = importlib.import_module(mod)
        cls_name, meth = None, None
        for key in doc["files"].get(rel, {}):
            cls_name, meth = key.split(".")
            cls = getattr(m, cls_name, None)
            fn = getattr(cls, meth, None) if cls else None
            live = getattr(getattr(fn, "__code__", None), "co_firstlineno", None)
            doc["live"][key] = {
                "class_dict_identity": bool(cls and meth in cls.__dict__),
                "live_firstlineno": live,
                "candidates": [d["lineno"] for d in doc["files"][rel][key]["definitions"]],
            }
            if live not in [d["lineno"] for d in doc["files"][rel][key]["definitions"]]:
                doc["refuse"].append(f"{key}：生效行号 {live} 不在 AST 候选里 ⇒ 两条口径不咬合")
            if live == doc["files"][rel][key]["definitions"][0]["lineno"]:
                doc["refuse"].append(f"{key}：生效的是第一份 ⇒ 第二份才是死码，本环不该删第一份")

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", "import cypyc.codegen.cython_generator, sys"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    doc["import_clean_rc"] = proc.returncode

    out = OUT
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    print(json.dumps({"refuse": doc["refuse"], "dup": {k: list(v) for k, v in doc["files"].items()}},
                     ensure_ascii=False)[:900])
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
