#!/usr/bin/env python3
"""BUG-31 evidence: cypy_bridge still gives Cypy `float` a 4-byte width after the double ruling.

The ruling unified `cypyc`'s two type maps. This checks the *other* package that claims to map
Cypy types -- `cypy_bridge/types.py:43` (`cypy_to_ctypes`) -- and measures the damage on a
documented API surface (`cdef_union("int", "float")`, the form written in its own docstring).

No compiler and no C library involved: the point is that the two maps disagree for the same
declared type name, and that a user-visible value changes when it crosses the bridge map.
"""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from cypyc.codegen.type_mapper import TypeMapper as CompilerTypeMapper        # noqa: E402
from cypy_bridge.types import _type_mapper as bridge_mapper                   # noqa: E402
from cypy_bridge.union import cdef_union                                      # noqa: E402

VALUE = 0.1


def main() -> int:
    cm = CompilerTypeMapper()
    bridge_float = bridge_mapper.to_ctypes("float")
    bridge_double = bridge_mapper.to_ctypes("double")
    u_float = cdef_union("int", "float")
    u_float.value = VALUE
    u_double = cdef_union("double")
    u_double.value = VALUE

    evidence = {
        "cypy_float_in_compiler": [cm.to_cython("float"), cm.to_c("float")],
        "cypy_float_in_bridge": bridge_float.__name__,
        "cypy_double_in_bridge": bridge_double.__name__,
        "sizeof_bridge_float": ctypes.sizeof(bridge_float),
        "sizeof_bridge_double": ctypes.sizeof(bridge_double),
        "roundtrip_via_float_member": repr(float(u_float.value)),
        "roundtrip_via_double_member": repr(float(u_double.value)),
        "site": "cypy_bridge/types.py:43（cypy_to_ctypes[\"float\"] = ctypes.c_float）、"
                "消费面 :80/:86/:114/:211 与 union.py:50 / generics.py:51 / pointer.py:101",
        "docstring_usage": 'cdef_union("int", "float") —— cypy_bridge/union.py:164 自己的示例形态',
    }
    if ctypes.sizeof(bridge_float) == ctypes.sizeof(bridge_double):
        raise SystemExit("REFUSE: 两张表已不再分叉，本单前提不成立")
    if evidence["roundtrip_via_float_member"] == evidence["roundtrip_via_double_member"]:
        raise SystemExit(f"REFUSE: 两个成员读回同一个值，用户可见面未证成: {evidence}")
    if ["double", "double"] != evidence["cypy_float_in_compiler"]:
        raise SystemExit(f"REFUSE: 编译器侧 float 已不是双精度，裁决前提变了: {evidence}")
    (HERE / "repro_pass9.out.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
