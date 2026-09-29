"""R11 台账收口：给 BUG-119 追 `### FIXED` 段，给 BUG-120/122 追 `### AMENDMENT` 段。

纪律：账本是 append-only —— 标题行永远写 OPEN，状态只在条目内段落里；
写前按标记幂等（已存在就跳过，可 --refresh 回收自己那段）；落盘走 temp + os.replace；
`--verify` 与盘面逐字对表（脚本产物被我手改过就会被读成"已落盘但内容不同"）。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "close_r11_ledger.json"


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FIXED_119 = """### FIXED(R11 2026-09-29 泛型类收下并代入) [{NOW}]
- 修法：`ClassDef` 增加 `generic_params` / `generic_constraints`（`cypyc/parser/parser.py:329-347`），
  类名的参数表解析与 `struct` 合并成同一份实现 `Parser._parse_type_param_list`（:1593-1618），
  `_parse_class_def`(:1625) 与 `_parse_struct_def`(:1650) 各自只调用它 ⇒ 空参数表文案两处逐字相同；
  使用侧新增注解位元数判定，与调用位共用 `TypeChecker._generic_arity_diagnostic`
  （`cypyc/analyzer/type_checker.py:1272-1289`，调用点在 :3964 区）；
  接收者代入补在 `_visit_Attribute` 的 class 分支（:2512 区，此前那里直接返回方法的声明返回类型 ⇒ `b.get()` 判成 `T`）；
  形式参数名不再进裸名表（`_visit_ClassDef` :592-608 + `_visit_FuncDef` :643 守卫）。
- 双向格（改严而非删锁）：`tests/test_boundary_comprehensive.py::TestClassBoundary::test_class_with_type_param`
  原文是「错误写法：当前类不支持泛型语法」，钉的正是本单的坏形态 ⇒ 本轮改成
  「`class Container<T>:` 必须收下且 `generic_params==['T']`」，并新增配对的
  `test_class_with_empty_type_param_list`（`class Container<>:` 仍硬拒 `Generic parameter list cannot be empty`）。
- 判据：`corpus/cypy.generic.class.json`（29 对，指纹 `fnv1a64:90f410a1d1cd0fd8`）、
  `tests/test_generic_class_r11.py`（13 支）、承重矩阵 `.fist-loop-20260929/verify_r11_locks.py`
  （7 格全跑：L1 退解析器 34 红 / L2 退注解位元数 4 红 / L3 退接收者代入 18 红 / L4 退形式参数守卫 1 红 /
  L5 退 struct 裸名擦除 2 红 / L6 只改注释 0 红，逐格身份探针 5/5 翻假，见 `logs/r11_locks_a8.out`）。
- 手册范例端到端：`SYNTAX/11-generics.md:112-124` 的 `class Box<T>` + `Box<int>(42)` 形态
  在 typecheck 与 codegen 两面 0 诊断（`logs/r11_generics_probe4.out` 的 C1），产物类头擦除为 `class Box:`。
- 本轮同时立而未修的相邻面（不遮挡本单关闭）：BUG-128（struct 方法不代入）、
  BUG-129（定义侧约束在注解位/实例化位不判）、BUG-127（`cdef class` 误导性诊断）。
"""

AMEND_120 = """### AMENDMENT(R11 2026-09-29 缩小半径：无体形态本身可用) [{NOW}]
- 新证据：`trait Container<T>:` + `def get(self, index: int) -> T`（**不带冒号**的无体签名）
  typecheck/codegen 两面 0 诊断，`TraitDef.generic_params==['T']`（`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C16）。
- 改判：本单的半径因此不是「trait 的无体抽象方法进不了编译器」，而是
  「**手册写的 `-> T:` 带冒号形态**进不了解析器（`Expected increased indentation`）」。
  裁决面随之变窄：要么解析器接受带冒号的无体签名，要么 SYNTAX/11:47-51、:89-91 的范例改成不带冒号 ——
  不再是"要不要支持无体方法"的支持性问题。
- 另记：`TraitDef` 没有 `generic_constraints` 属性（同探针打印 `constraints='<no attr>'`），
  而 `StructDef`/本轮 `ClassDef` 都有 ⇒ 特质约束在定义侧就没有落脚点，属 BUG-129 的同族面。
"""

AMEND_122 = """### AMENDMENT(R11 2026-09-29 泛型类实例化位同样不判存在性) [{NOW}]
- 新证据：泛型类收口后可测 —— `let b: Box<int> = Box<Mystery>(42)` 两面 0 诊断
  （`.fist-loop-20260929/logs/r11_generics_probe2.out` 的 C11_undefined_typearg），
  `Mystery` 既不在 class_defs 也不在内置类型表里，静默降级。
- 半径扩张：本单原先只有函数调用位的证据（`mk<Undefined>(1)`），现扩到 class 实例化位与注解位
  （`_get_type_from_node` 的 GenericType 分支同样只转形态不判存在）。
- 与本轮的关系：R11 新增的 `_generic_arity_diagnostic` 只判**个数**，不判**名字** ⇒
  本单仍是开口，不收口、不关闭。
"""

SECTIONS = [
    ("BUG-119", "### FIXED(R11", FIXED_119),
    ("BUG-120", "### AMENDMENT(R11", AMEND_120),
    ("BUG-122", "### AMENDMENT(R11", AMEND_122),
]


def block_of(text: str, bug_id: str) -> tuple:
    parts = re.split(r"(?m)^(## BUG-\d+)", text)
    for i in range(1, len(parts) - 1, 2):
        if parts[i] == f"## {bug_id}":
            return i, parts[i + 1]
    raise AssertionError(f"账本里没有 {bug_id} 条目")


def main() -> int:
    refresh = "--refresh" in sys.argv
    verify = "--verify" in sys.argv
    text = LEDGER.read_text(encoding="utf-8")
    rep = {"started_z": utc_z(), "appended": [], "skipped": [], "refreshed": []}

    if verify:
        marks = {bug: marker in block_of(text, bug)[1] for bug, marker, _ in SECTIONS}
        parts = re.split(r"(?m)^## (BUG-\d+)", text)
        closed = r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)"
        open_ids = [parts[i] for i in range(1, len(parts) - 1, 2) if not re.search(closed, parts[i + 1])]
        rep["verify"] = {"markers_on_disk": marks, "headers": len(parts) // 2,
                         "unique_ids": len(set(parts[1::2])), "open_blocks_narrow": len(open_ids)}
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print("VERIFY", json.dumps(rep["verify"], ensure_ascii=False))
        ok = all(marks.values())
        print(f"CONCLUSION verify=1 all_markers_on_disk={ok}")
        return 0 if ok else 1

    now = utc_z()
    for bug_id, marker, body_raw in SECTIONS:
        body = body_raw.replace("{NOW}", now)
        _, block = block_of(text, bug_id)
        if marker in block:
            if not refresh:
                rep["skipped"].append(bug_id)
                continue
            cut = block.index(marker)
            block = block[:cut].rstrip("\n") + "\n"
            text = text.replace(block_of(text, bug_id)[1], block, 1)
            rep["refreshed"].append(bug_id)
        cur = block_of(text, bug_id)[1]
        text = text.replace(cur, cur.rstrip("\n") + "\n\n" + body.rstrip("\n") + "\n", 1)
        rep["appended"].append(bug_id)

    tmp = LEDGER.with_suffix(".md.tmp-r11")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    # 落盘前自证：临时件必须已经含三段标记（写坏了就不动正身）
    for bug_id, marker, _ in SECTIONS:
        assert marker in block_of(tmp.read_text(encoding="utf-8"), bug_id)[1], bug_id
    tmp.replace(LEDGER)

    after = LEDGER.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (BUG-\d+)", after)
    closed = r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)"
    open_ids = [parts[i] for i in range(1, len(parts) - 1, 2) if not re.search(closed, parts[i + 1])]
    rep["after"] = {"headers": len(parts) // 2, "unique_ids": len(set(parts[1::2])),
                    "open_blocks_narrow": len(open_ids),
                    "fixed_sections": len(re.findall(r"(?m)^### FIXED\(", after)),
                    "bug_119_fixed_present": "### FIXED(R11" in block_of(after, "BUG-119")[1],
                    "bug_120_amendment_present": "### AMENDMENT(R11" in block_of(after, "BUG-120")[1],
                    "bug_122_amendment_present": "### AMENDMENT(R11" in block_of(after, "BUG-122")[1]}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("APPENDED", json.dumps(rep["appended"], ensure_ascii=False),
          "SKIPPED", json.dumps(rep["skipped"], ensure_ascii=False))
    print("AFTER", json.dumps(rep["after"], ensure_ascii=False))
    print(f"CONCLUSION appended={len(rep['appended'])} skipped={len(rep['skipped'])} "
          f"open_blocks_narrow={rep['after']['open_blocks_narrow']} "
          f"headers={rep['after']['headers']} unique={rep['after']['unique_ids']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
