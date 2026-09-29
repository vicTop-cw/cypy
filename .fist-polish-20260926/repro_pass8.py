#!/usr/bin/env python3
"""BUG-30 evidence: a declared floating local gets no coercion when the source is an int.

Discovered while re-registering the end-to-end goldens under the commander's float=double ruling:
`examples/basic_types.out` line 5 moved from `auto(int to float): 42.0` to `... : 42`. That is not a
last-digit change, so it was chased down instead of accepted.

Discriminator (one build, no variant recompiles): `let e: float = a` and `let d: double = a` with
`a: int = 42`. Both now print `42` with `type=<class 'int'>`, i.e. the hole belongs to the
`double` path (which the ruling moved `float` onto), not to the ruling's arithmetic.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")

SRC = (
    "def main() -> None:\n"
    "    let a: int = 42\n"
    "    let e: float = a\n"
    "    let d: double = a\n"
    "    let g: float = 1.5\n"
    '    print(f"float-from-int: value={e} type={type(e)}")\n'
    '    print(f"double-from-int: value={d} type={type(d)}")\n'
    '    print(f"float-from-float-lit: value={g} type={type(g)}")\n'
)

sys.path.insert(0, str(ROOT))
from cypyc.codegen.cython_generator import CythonGenerator      # noqa: E402
from cypyc.parser.lexer import Lexer                             # noqa: E402
from cypyc.parser.parser import Parser                           # noqa: E402


def generated(src: str) -> str:
    out = CythonGenerator().generate(Parser(Lexer(src).tokenize()).parse())
    return out if isinstance(out, str) else out.cython_code


def main() -> int:
    code = generated(SRC)
    decls = [ln.strip() for ln in code.splitlines()
             if ln.strip().startswith(("e:", "d:", "g:", "cdef double", "cdef float"))]

    tmp = HERE / "tmp_float"
    tmp.mkdir(exist_ok=True)
    probe = tmp / "repro_pass8.cypy"
    probe.write_text(SRC, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, "-m", "cypyc", "run", str(probe),
                        "-o", str(tmp / "out8")],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    run_out = (r.stdout or "") + (r.stderr or "")
    lines = [ln for ln in run_out.splitlines() if "from-" in ln]

    evidence = {
        "run_exit": r.returncode,
        "generated_declarations": decls,
        "uses_annotation_form": any(ln.startswith(("e:", "d:")) for ln in decls),
        "emits_cdef_form": any(ln.startswith("cdef ") for ln in decls),
        "runtime": lines,
        "float_and_double_agree": ("value=42 type=<class 'int'>" in "".join(lines)
                                   and "".join(lines).count("value=42 type=<class 'int'>") == 2),
        "float_literal_still_float": "value=1.5 type=<class 'float'>" in "".join(lines),
        "site": "cypyc/codegen/cython_generator.py:1170 / :1255（`name: <ctype> = value` 注解形式）"
                "，对照 :1168 / :1253 的 `cdef <ctype> name = value`",
    }
    if r.returncode != 0:
        evidence["raw_tail"] = run_out[-1200:]
        print(json.dumps(evidence, ensure_ascii=False, indent=1))
        raise SystemExit("REFUSE: 探针没跑起来，不能据以确诊")
    if not (evidence["float_and_double_agree"] and evidence["float_literal_still_float"]
            and evidence["uses_annotation_form"]):
        evidence["raw_tail"] = run_out[-1200:]
        print(json.dumps(evidence, ensure_ascii=False, indent=1))
        raise SystemExit("REFUSE: 三条判据没有同时成立（行为与假设不符，不该入账）")
    (HERE / "repro_pass8.out.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
