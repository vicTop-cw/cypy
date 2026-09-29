"""R13 入口探针：`SYNTAX/02-type-annotations.md:92` 承诺的「泛型类型别名」在调用面是什么形态。

走 Ω-gate 同一份 `execute()`（不另起一套管线，免得探针的"绿"是探针自己的绿）；
只打元信息（stage / errors 计数 / 前两条消息），不回显环境内容。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))

import omega_gate as og  # noqa: E402

CASES = {
    "A_basic_alias": "type Point = tuple<int, int>\n\norigin: Point = (0, 0)\n",
    "B_generic_alias": "type Result<T> = tuple<bool, T>\n\nsuccess: Result<int> = (True, 42)\n",
    "C_alias_bound_use": 'type Num<T: int | float> = tuple<bool, T>\n\nn: Num<str> = (True, "x")\n',
    "D_two_uses": 'type Result<T> = tuple<bool, T>\n\na: Result<int> = (True, 1)\nb: Result<str> = (False, "s")\n',
    "E_alias_to_generic_class": (
        "class Box<T>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"
        'type Boxed<T> = Box<T>\n\nb: Boxed<str> = Box("s")\n'
    ),
    "F_alias_codegen": "type Result<T> = tuple<bool, T>\n\nsuccess: Result<int> = (True, 42)\n",
    # 成对反例：正向的 0 诊断不说明"代入了"，只有**该红的红了**才说明别名被解析并替换。
    "G_wrong_inner": 'type Result<T> = tuple<bool, T>\n\nbad: Result<int> = (True, "x")\n',
    "H_wrong_flag": "type Result<T> = tuple<bool, T>\n\nbad: Result<int> = (1, 2)\n",
    "I_unknown_in_alias": "type Result<T> = tuple<bool, T>\n\nbad: Result<NotAType> = (True, 1)\n",
    "J_alias_wrong_kind": 'type Pair<T> = tuple<T, T>\n\nbad: Pair<int> = (1, "s")\n',
    "K_alias_arity_use": "type Pair<T> = tuple<T, T>\n\nbad: Pair = (1, 2)\n",
    "L_plain_class_control": (
        "class Box<T>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"
        "b: Box<str> = Box(1)\n"
    ),
}

out = {}
for name, src in CASES.items():
    op = "codegen" if name.startswith("F_") else "typecheck"
    obs = og.execute({"op": op, "src": src})
    out[name] = {
        "stage": obs["stage"],
        "errors_n": len(obs["errors"]),
        "first_two": [str(e)[:140] for e in obs["errors"][:2]],
        "code_lines": obs["code"].count("\n") + 1 if obs.get("code") else 0,
        "class_fields": sorted(obs.get("class_fields") or {}),
    }

print(json.dumps(out, ensure_ascii=False, indent=1))
crashed = [k for k, v in out.items() if "crash" in v["stage"] or v["stage"] == "parse"]
zero = [k for k, v in out.items() if v["stage"] == "ok" and v["errors_n"] == 0]
print(
    "CONCLUSION cases=%d parse_or_crash=%s zero_diag=%s" % (len(CASES), [k for k in crashed], zero)
)
