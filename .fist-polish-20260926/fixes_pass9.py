#!/usr/bin/env python3
"""Pass-9 patches: undo the collateral damage of the float=double ruling.

Two kinds of edits, deliberately kept apart:

1. One *product* fix (BUG-32): `_visit_ConstraintDef` echoes the constraint comment through
   `type_mapper`, so after the ruling the artifact printed `# constraint Numeric = int | double`
   for source that says `int | float`. The comment is a verbatim echo of the declaration
   (SYNTAX/33 §5), so it must use the declared names.
2. Six *test needles* that pinned the pre-ruling spelling (`float` / `<float>x` / `cpdef float`).
   These are invalidated by the commander's ruling itself, not weakened: each is retargeted to the
   ruled value, and the edit stays on the width token only.

Every edit is anchored with an expected hit count and re-verified after writing; CRLF files keep
their line endings.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")

# (rel, old, new, want, ticket)
EDITS = [
    ("cypyc/codegen/cython_generator.py",
     '        members = " | ".join(self._type_to_str(m) for m in getattr(node, \'members\', []) or [])\n'
     '        self._write(f"# constraint {node.name} = {members}")',
     '        # 这条注释是对声明的逐字回显（SYNTAX/33 §5）：**不过 type_mapper**，否则 BUG-14 裁决\n'
     '        # （float≡double）之后用户写 `int | float` 会得到 `int | double`。\n'
     '        # 但也不能无条件回显：S-4.1 规定子类型名不得出现在产物里，所以 subtype/alias 仍要\n'
     '        # 化成它的基类型**名字**（`Meter` → `float`），只有标量名保持原样。\n'
     '        members = " | ".join(self._constraint_member_name(m)\n'
     '                             for m in getattr(node, \'members\', []) or [])\n'
     '        self._write(f"# constraint {node.name} = {members}")\n'
     '        self._write("")\n'
     '\n'
     '    def _constraint_member_name(self, node: Any) -> str:\n'
     '        """约束成员的回显名：标量取声明时的原名，subtype/alias 递归化成基类型名。"""\n'
     '        for _ in range(8):                      # 链式 subtype（CentiMeter <: Meter <: float）\n'
     '            name = getattr(node, \'id\', None)\n'
     '            if not name:\n'
     '                break\n'
     '            base = self._subtype_to_base(name)\n'
     '            if base is not None:\n'
     '                node = base\n'
     '                continue\n'
     '            if name in self.type_aliases:\n'
     '                node = self.type_aliases[name].target\n'
     '                continue\n'
     '            return name\n'
     '        return self._type_to_str(node)', 1, "BUG-32"),

    ("tests/test_codegen.py",
     '        self.assertEqual(mapper.to_cython("float"), "float")',
     '        # BUG-14 裁决（2026-09-26）：Cypy 的 float 跟随 Python 双精度。\n'
     '        self.assertEqual(mapper.to_cython("float"), "double")', 1, "BUG-14 裁决落地"),

    ("tests/test_stage3.py",
     '        self.assertIn("def area(self) -> float:", code)',
     '        self.assertIn("def area(self) -> double:", code)', 1, "BUG-14 裁决落地"),
    ("tests/test_stage3.py",
     '        self.assertIn("def perimeter(self) -> float:", code)',
     '        self.assertIn("def perimeter(self) -> double:", code)', 1, "BUG-14 裁决落地"),
    ("tests/test_stage3.py",
     '        self.assertIn("cpdef float area", code)',
     '        self.assertIn("cpdef double area", code)', 1, "BUG-14 裁决落地"),

    ("tests/test_codegen_cast.py",
     '"<float>x" in cython_code',
     '"<double>x" in cython_code', 3, "BUG-14 裁决落地"),
]


def main() -> int:
    # 支持按序号补跑单条（前 5 条已落盘后重跑会因锚点消失而红，那是对的，别改成静默）。
    sel = {int(a) for a in sys.argv[1:]}
    applied, reds = [], []
    for idx, (rel, old, new, want, ticket) in enumerate(EDITS):
        if sel and idx not in sel:
            continue
        path = ROOT / rel
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        crlf = "\r\n" in text
        o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
        hits = text.count(o)
        if hits != want:
            reds.append(f"{ticket} {rel}: 锚点命中 {hits} 次，期望 {want} 次 —— 不落盘")
            continue
        if n.strip() and n in text and ticket == "BUG-32":
            reds.append(f"{ticket} {rel}: 新文本已在文件里（可能已经打过）—— 不落盘")
            continue
        path.write_bytes(text.replace(o, n).encode("utf-8"))
        after = (ROOT / rel).read_bytes().decode("utf-8")
        if (o in after) or (n not in after):
            reds.append(f"{ticket} {rel}: 写后复验失败")
            continue
        applied.append(f"{ticket} {rel} x{want} ({'CRLF' if crlf else 'LF'})")
    for a in applied:
        print("applied:", a)
    for r in reds:
        print("RED:", r)
    print(f"applied={len(applied)} reds={len(reds)}")
    return 1 if reds else 0


if __name__ == "__main__":
    sys.exit(main())
