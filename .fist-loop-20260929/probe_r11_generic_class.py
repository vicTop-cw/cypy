"""R11 寻虫腿探针：泛型类 / 泛型特质（SYNTAX/11:107-125、:149-150）在真实管线上的**实测**形态。

尺子沿用 `scripts/omega_gate.execute()` ⇒ 探针观测与 Ω-gate 判据同源，不会出现两套事实。
本件只打印观测，不写期望（期望在 corpus 里，由 `make_corpus_r11.py` 实测后生成）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

CLS = "class Box<T>:\n    def __init__(self, content: T):\n        self.content = content\n\n    def get(self) -> T:\n        return self.content\n\n"

CASES = {
    # 手册 :112-124 的完整范例（逐字取自 SYNTAX/11 代码块）
    "C1_manual_example": CLS + "def f() -> int:\n    let int_box: Box<int> = Box<int>(42)\n    return int_box.get()\n",
    # 定义侧四种形态
    "C2_multi_params": "class Pair<T, U>:\n    def first(self) -> T:\n        return self.a\n\n",
    "C3_constrained": "class Num<T: int | float>:\n    def v(self) -> T:\n        return self.x\n\n",
    "C4_extends": CLS.replace("class Box<T>:", "class Box<T> extends Base:") + "def f() -> int:\n    return 0\n",
    "C5_paren_base": CLS.replace("class Box<T>:", "class Box<T>(Base):") + "def f() -> int:\n    return 0\n",
    "C6_cdef_class": CLS.replace("class Box<T>:", "cdef class Box<T>:") + "def f() -> int:\n    return 0\n",
    "C7_field_in_body": "class Box<T>:\n    content: T\n\n    def get(self) -> T:\n        return self.content\n\n",
    "C8_empty_param_list": "class Box<>:\n    def get(self) -> int:\n        return 0\n\n",
    # 使用侧形态
    "C9_bare_name_use": CLS + "def f() -> int:\n    let b: Box = Box(1)\n    return 0\n",
    "C10_arity_over": CLS + "def f() -> int:\n    let b: Box<int> = Box<int, str>(42)\n    return 0\n",
    "C11_undefined_typearg": CLS + "def f() -> int:\n    let b: Box<int> = Box<Mystery>(42)\n    return 0\n",
    "C12_nested_generic_ann": CLS + "def f() -> int:\n    xs: list<Box<int>> = []\n    return 0\n",
    "C13_param_ann": CLS + "def use(b: Box<int>) -> int:\n    return b.get()\n\n",
    "C14_method_typearg": CLS + "def f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get<int>()\n",
    # 对照：已可用的 struct 泛型 与 未收口的 trait 泛型
    "C15_struct_control": "struct Wrap<T>:\n    value: T\n\n\ndef f() -> int:\n    return 0\n",
    "C16_trait_abstract": "trait Container<T>:\n    def get(self, index: int) -> T\n\n\ndef f() -> int:\n    return 0\n",
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
                print(f"  code_len={len(obs['code'])}")
                for ln in obs["code"].splitlines():
                    if ln.strip():
                        print(f"  CODE: {ln}")
                print(f"  class_fields={obs['class_fields']}")
        try:
            ast = og.compile_src(src)
            print(f"  AST body kinds={[type(n).__name__ for n in ast.body]}")
            for n in ast.body:
                if type(n).__name__ in ("ClassDef", "StructDef", "TraitDef", "FuncDef"):
                    print(f"    {type(n).__name__} name={getattr(n, 'name', '?')} "
                          f"generic_params={getattr(n, 'generic_params', '<no attr>')!r} "
                          f"constraints={getattr(n, 'generic_constraints', '<no attr>')!r}")
                    if type(n).__name__ == "ClassDef":
                        print(f"    ClassDef body kinds={[type(c).__name__ for c in n.body]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  AST-ERR {type(exc).__name__}: {exc}")
    print("CONCLUSION probe_cases=" + str(len(only)))
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({k: {"src": v} for k, v in CASES.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
