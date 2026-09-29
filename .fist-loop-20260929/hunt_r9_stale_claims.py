"""R9 开工测量：三条 open 主张今天到底还成立吗（逐格给可复跑证据，不靠回忆）。

为什么要先测：账本里 BUG-98/101/104 都在说「corpus/ 与 tests/regression/ 在本仓不存在」——
这条在 R8 之后**事实已经不成立**；而 BUG-96/99/102 说的「产物发不存在的 __f{i}」，
R8 的 `_positional_fields` + corpus #10/#17 两格（not_contains __f0）可能已经把它带走了。
「删除/关闭」必须是被测量打出来的，不是被我推定的。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".fist-loop-20260929" / "hunt_r9_stale_claims.json"
sys.path.insert(0, str(ROOT))

rep: dict = {"cells": []}


def cell(name: str, **kw) -> None:
    rep["cells"].append({"name": name, **kw})
    print(f"[{name}] " + json.dumps(kw, ensure_ascii=False)[:520])


# A) 「corpus/ 与 tests/regression/ 不存在」——现在存在吗，跑批还绿吗
corpus = sorted(p.name for p in (ROOT / "corpus").glob("*.json")) if (ROOT / "corpus").is_dir() else []
regr = sorted(p.name for p in (ROOT / "tests" / "regression").glob("*.py")) if (
    ROOT / "tests" / "regression").is_dir() else []
cell("A1 目录存在", corpus_files=corpus, regression_files=regr,
     corpus_dir_exists=(ROOT / "corpus").is_dir(), regr_dir_exists=(ROOT / "tests" / "regression").is_dir())

p = subprocess.run([sys.executable, "-X", "utf8", "scripts/omega_gate.py"], cwd=ROOT,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
tail = [ln for ln in (p.stdout + p.stderr).splitlines() if ln.startswith("CONCLUSION")]
cell("A2 Ω-gate 可跑", rc=p.returncode, conclusion=tail[-1] if tail else (p.stdout + p.stderr)[-200:])

p2 = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/regression",
                     "-p", "no:cacheprovider", "-q", "--no-header"], cwd=ROOT,
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
out2 = p2.stdout + p2.stderr
cell("A3 回归件可跑", rc=p2.returncode,
     summary=next((ln.strip() for ln in reversed(out2.splitlines()) if "passed" in ln), "")[:160])

# B) BUG-96/99/102 的正身主张：无 __unapply__ 且实参元数 > 字段数 ⇒ 产物发 `.__f{i}`
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402
from cypyc.analyzer.type_checker import TypeChecker  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402

SRC_B = '''
struct E:
    a: int
    b: int

def g(e: E) -> int:
    match e:
        case E(1, 2, 3):
            return 3
        case _:
            return 0
'''
ast = Parser(list(Lexer(SRC_B).tokenize())).parse()
tc = TypeChecker()
tc.check(ast)
code = CythonGenerator().generate(ast)
faccess = [ln.strip() for ln in code.splitlines() if "__f" in ln]
arity = [e for e in tc.errors if "Positional pattern" in e]
cell("B1 元数>字段数 的产物面", diagnostics=arity, lines_with__f=faccess,
     claim_holds=bool(faccess), diag_count=len(arity))

# C) BUG-71：切片表达式被判成容器元素类型（仓内 DEMO 为证）
demos = sorted(p.name for p in (ROOT / "demo").glob("*.cypy")) if (ROOT / "demo").is_dir() else []
cell("C0 demo 目录", files=demos[:12], n=len(demos))
SRC_C = '''
def f(xs: list<int>) -> int:
    ys: list<int> = xs[1:3]
    return len(ys)
'''
ast_c = Parser(list(Lexer(SRC_C).tokenize())).parse()
tc_c = TypeChecker()
tc_c.check(ast_c)
cell("C1 切片赋值", errors=[e for e in tc_c.errors if "Return type" in e or "mismatch" in e or "Slice" in e],
     all_errors=tc_c.errors[:6], claim_holds=bool(tc_c.errors))

OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
by_name = {c["name"]: c for c in rep["cells"]}
gate_rc = by_name["A2 Ω-gate 可跑"]["rc"]
holds_b = by_name["B1 元数>字段数 的产物面"]["claim_holds"]
holds_c = by_name["C1 切片赋值"]["claim_holds"]
print(f"CONCLUSION cells={len(rep['cells'])} corpus_exists={bool(corpus)} regr_exists={bool(regr)} "
      f"gate_rc={gate_rc} bug71_still_holds={holds_c} bugeta_claim_still_holds={holds_b}")
