"""R11 修复面实测：接收者代入（class 与 struct 同一把尺子）。

成对设计：每个"代入生效"的正例都配一个"必须仍然红"的反例 ——
只验正例的话，把返回类型退化成 `object` 也能全绿，那是假绿。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

BOX = "class Box<T>:\n    content: T\n\n    def get(self) -> T:\n        return self.content\n\n"
WRAP = "struct Wrap<T>:\n    value: T\n\n    def get(self) -> T:\n        return self.value\n\n"
PLAIN = "class Plain:\n    content: int\n\n    def get(self) -> int:\n        return self.content\n\n"

CASES = {
    "S1_manual_example": BOX + "def f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get()\n",
    "S2_field_ok": BOX + "def f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.content\n",
    "S3_field_bad": BOX + "def f() -> str:\n    let b: Box<int> = Box<int>(42)\n    return b.content\n",
    "S4_method_subst_ok": BOX + "def f() -> str:\n    let b: Box<str> = Box<str>(\"x\")\n    return b.get()\n",
    "S5_method_subst_bad": BOX + "def f() -> int:\n    let b: Box<str> = Box<str>(\"x\")\n    return b.get()\n",
    "S6_bare_class_erased": BOX + "def f() -> int:\n    let b: Box = Box(1)\n    return b.get()\n",
    "S7_plain_regression_ok": PLAIN + "def f() -> int:\n    let p: Plain = Plain()\n    return p.get()\n",
    "S8_plain_regression_bad": PLAIN + "def f() -> str:\n    let p: Plain = Plain()\n    return p.content\n",
    "S9_struct_parity_ok": WRAP + "def f() -> int:\n    let w: Wrap<int> = Wrap(1)\n    return w.value\n",
    "S10_struct_parity_bad": WRAP + "def f() -> str:\n    let w: Wrap<int> = Wrap(1)\n    return w.value\n",
    "S11_nested_generic": BOX + "def f() -> int:\n    bs: list<Box<int>> = []\n    return 0\n",
    "S12_two_params": "class Pair<T, U>:\n    a: T\n    b: U\n\n    def first(self) -> T:\n        return self.a\n\n"
                      + "def f() -> int:\n    let p: Pair<int, str> = Pair()\n    return p.first()\n",
    "S13_two_params_bad": "class Pair<T, U>:\n    a: T\n    b: U\n\n    def second(self) -> U:\n        return self.b\n\n"
                          + "def f() -> int:\n    let p: Pair<int, str> = Pair()\n    return p.second()\n",
}

if __name__ == "__main__":
    for name in sorted(CASES):
        obs = og.execute({"op": "typecheck", "src": CASES[name]})
        code = og.execute({"op": "codegen", "src": CASES[name]})
        hdr_lines = [ln for ln in code["code"].splitlines()
                     if ln.startswith(("class ", "cdef class ", "    def ", "     def "))]
        print(f"{name} | stage={obs['stage']} | err={len(obs['errors'])} "
              f"| codegen_stage={code['stage']}")
        for e in obs["errors"]:
            print(f"  ERR: {e}")
        if code["code"]:
            print(f"  HEADERS: {hdr_lines}")
            body = [ln for ln in code["code"].splitlines() if "def f" in ln or "return" in ln]
            print(f"  CALLSITE: {body[-3:]}")
    print("CONCLUSION cases=%d" % len(CASES))
