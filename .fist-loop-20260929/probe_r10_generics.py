"""寻虫腿探针：泛型（SYNTAX/11）在真实管线上的**实测**形态，不写期望、只打印观测。

复用 `scripts/omega_gate.py` 的 `execute()` ⇒ 探针观测与 Ω-gate 判据同一把尺子，
不会出现"探针绿、门禁红"的两套事实。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

CASES = {
    "G1_identity_int": "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    n: int = identity<int>(42)\n    return n\n",
    "G2_identity_str": "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> str:\n    s: str = identity<str>(\"Alice\")\n    return s\n",
    "G3_infer_list": "def get_first<T>(items: list<T>) -> T:\n    return items[0]\n\n\ndef f() -> int:\n    xs: list<int> = [1, 2, 3]\n    return get_first(xs)\n",
    "G4_bad_constraint": "def process<T: int | float>(value: T) -> T:\n    return value\n\n\ndef f() -> str:\n    return process<str>(\"hello\")\n",
    "G5_ok_constraint": "def process<T: int | float>(value: T) -> T:\n    return value\n\n\ndef f() -> int:\n    return process<int>(42)\n",
    "G6_generic_class": "class Box<T>:\n    def __init__(self, content: T):\n        self.content = content\n\n    def get(self) -> T:\n        return self.content\n\n\ndef f() -> int:\n    b: Box<int> = Box<int>(42)\n    return b.get()\n",
    "G7_multi_params": "def pair<T, U>(first: T, second: U) -> tuple<T, U>:\n    return (first, second)\n\n\ndef f() -> int:\n    p: tuple<int, str> = pair<int, str>(42, \"a\")\n    return 0\n",
    "G8_arity_mismatch": "def pair<T, U>(first: T, second: U) -> tuple<T, U>:\n    return (first, second)\n\n\ndef f() -> int:\n    return pair<int>(42)\n",
    "G9_typearg_vs_param": "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    return identity<int>(\"oops\")\n",
    "G10_generic_trait": "trait Container<T>:\n    def get(self, index: int) -> T:\n\n\ndef f() -> int:\n    return 0\n",
    "G11_call_undeclared_generic": "def f() -> int:\n    return mystery<int>(42)\n",
    "G12_generic_return_mismatch": "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    s: str = identity<int>(\"Alice\")\n    return 0\n",
    "G13_nested_generic": "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    xs: list<int> = [1, 2]\n    y: list<int> = identity[list[int]](xs)\n    return len(y)\n",
    "G14_generic_struct": "struct Wrap<T>:\n    value: T\n\n\ndef f() -> int:\n    return 0\n",
    "G15_typeparam_used_in_body": "def dup<T>(x: T) -> T:\n    return x + x\n\n\ndef f() -> int:\n    return dup<int>(2)\n",
}

if __name__ == "__main__":
    only = sys.argv[1:] or sorted(CASES)
    for name in only:
        src = CASES[name]
        for op in ("typecheck", "codegen"):
            obs = og.execute({"op": op, "src": src})
            print("=" * 78)
            print(f"{name} | op={op} | stage={obs['stage']} | errors={len(obs['errors'])}")
            for e in obs["errors"][:6]:
                print(f"  ERR: {e}")
            if op == "codegen":
                head = [ln for ln in obs["code"].splitlines() if "identity" in ln or "def " in ln][:8]
                print(f"  code_len={len(obs['code'])}")
                for ln in head:
                    print(f"  CODE: {ln}")
        # 解析后的 AST 形状：泛型参数到底落到了哪里
        try:
            ast = og.compile_src(src)
            kinds = [getattr(n, "kind", type(n).__name__) for n in ast.body]
            print(f"  AST body kinds={kinds}")
            for n in ast.body:
                if getattr(n, "kind", "") in ("FunctionDef", "ClassDef", "StructDef"):
                    tp = getattr(n, "type_params", None)
                    print(f"    {n.kind} name={getattr(n,'name','?')} type_params={tp!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  AST-ERR {type(exc).__name__}: {exc}")
    print("CONCLUSION probe_cases=" + str(len(only)))
    Path(__file__).with_suffix(".json").write_text(json.dumps(
        {k: {"src": v} for k, v in CASES.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
