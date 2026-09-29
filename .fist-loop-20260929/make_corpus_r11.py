"""R11 判据层：新增 Ω-spec `cypy.generic.class`（SYNTAX/11「泛型类的判定口径」规则 1-5）。

每条测试对的 expected 都是**实测值**：落盘前逐条用 `omega_gate.execute + judge` 复核，
观测与断言不一致就拒绝生成（并打印实际观测，便于把断言改到真相上，而不是改产品凑断言）。
正例必配反例半边 —— 只验正例的话，把成员类型退化成 `object` 也能全绿，那是假绿。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

OUT = ROOT / "corpus" / "cypy.generic.class.json"

# 手册 SYNTAX/11:112-124 的范例（`__init__` 形态）与 `.body` 里 LetStmt 字段的形态
BOX_INIT = ("class Box<T>:\n    def __init__(self, content: T):\n        self.content = content\n\n"
            "    def get(self) -> T:\n        return self.content\n\n\n"
            "def f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get()\n")
BOX_FIELD = ("class Box<T>:\n    content: T\n\n    def get(self) -> T:\n        return self.content\n\n")
PAIR_FIELD = ("class Pair<T, U>:\n    a: T\n    b: U\n\n    def first(self) -> T:\n        return self.a\n\n"
              "    def second(self) -> U:\n        return self.b\n\n")
NUM_CONSTR = "class Num<T: int | float>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"
EXTENDS = "class Box<T> extends Base:\n    def get(self) -> T:\n        return self.content\n\n"
PAREN_BASE = "class Box<T>(Base):\n    def get(self) -> T:\n        return self.content\n\n"
EMPTY = "class Box<>:\n    def get(self) -> int:\n        return 0\n\n"
PLAIN = ("class Plain:\n    content: int\n\n    def get(self) -> int:\n        return self.content\n\n")
WRAP = ("struct Wrap<T>:\n    value: T\n\n    def get(self) -> T:\n        return self.value\n\n")


def cls(body: str, use: str) -> str:
    return body + "\n" + use


USE_GET_OK = cls(BOX_FIELD, "def f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get()\n")
USE_GET_STR = cls(BOX_FIELD, 'def f() -> str:\n    let b: Box<str> = Box<str>("x")\n    return b.get()\n')
USE_GET_BAD = cls(BOX_FIELD, 'def f() -> int:\n    let b: Box<str> = Box<str>("x")\n    return b.get()\n')
USE_FIELD_BAD = cls(BOX_FIELD, "def f() -> str:\n    let b: Box<int> = Box<int>(42)\n    return b.content\n")
USE_BARE = cls(BOX_FIELD, "def f() -> int:\n    let b: Box = Box(1)\n    return b.get()\n")
USE_ARITY_OVER = cls(BOX_FIELD, "def f() -> int:\n    let b: Box<int> = Box<int, str>(42)\n    return 0\n")
USE_ANN_ARITY = cls(BOX_FIELD, "def f() -> int:\n    let b: Box<int, str> = Box<int>(42)\n    return 0\n")
NONGEN_USE = cls(PLAIN, "def f() -> int:\n    let p: Plain<int> = Plain()\n    return 0\n")
USE_PAIR2 = cls(PAIR_FIELD, "def f() -> int:\n    let p: Pair<int, str> = Pair()\n    return p.second()\n")
USE_PAIR_OK = cls(PAIR_FIELD, "def f() -> str:\n    let p: Pair<int, str> = Pair()\n    return p.second()\n")
USE_NESTED_ANN = cls(BOX_FIELD, "def f() -> int:\n    bs: list<Box<int>> = []\n    return 0\n")
USE_LIST_RETURN = ("class Bag<T>:\n    def all(self) -> list<T>:\n        return self.items\n\n\n"
                   "def f() -> int:\n    let g: Bag<int> = Bag()\n    return g.all()\n")
USE_DEEP_CHAIN = ("class Link<T>:\n    def next(self) -> Link<T>:\n        return self\n\n\n"
                  "def f() -> int:\n    let l: Link<int> = Link()\n    return l.next().next()\n")
USE_DEEP_CHAIN_OK = ("class Link<T>:\n    def next(self) -> Link<T>:\n        return self\n\n\n\n"
                   "def g() -> Link<int>:\n    let l: Link<int> = Link()\n    return l.next()\n")
WRAP_BARE = cls(WRAP, "def f() -> int:\n    let w: Wrap = Wrap()\n    return w.value\n")
WRAP_SUBST = cls(WRAP, "def f() -> str:\n    let w: Wrap<int> = Wrap(1)\n    return w.value\n")

PAIRS = [
    # —— 规则 1：定义侧三种前缀 + 约束 + 多参数 ——
    {"input": {"op": "typecheck", "src": BOX_INIT}, "expected": {"errors": 0, "stage": "ok"}},
    {"input": {"op": "typecheck", "src": NUM_CONSTR}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": EXTENDS}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": PAREN_BASE}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": PLAIN}, "expected": {"errors": 0}},
    # 空参数表：语法级硬拒，文案与 struct 同源（规则 2「一份实现两处用」的可检面）
    {"input": {"op": "typecheck", "src": EMPTY},
     "error": {"stage": "parse", "contains": ["Generic parameter list cannot be empty"],
               "matches": r"at \d+:\d+"}},
    {"input": {"op": "typecheck", "src": "struct Box<>:\n    value: int\n\n"},
     "error": {"stage": "parse", "contains": ["Generic parameter list cannot be empty"]}},

    # —— 规则 3：使用侧元数（注解位与调用位同一对文案）+ 裸名按擦除 ——
    {"input": {"op": "typecheck", "src": USE_GET_OK}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": USE_ARITY_OVER},
     "error": {"contains": ["Type argument count mismatch: 'Box' declares 1 type parameter(s), got 2"],
               "matches": r"at \d+:\d+"}},
    {"input": {"op": "typecheck", "src": USE_ANN_ARITY},
     "error": {"contains": ["Type argument count mismatch: 'Box' declares 1 type parameter(s), got 2"]}},
    {"input": {"op": "typecheck", "src": NONGEN_USE},
     "error": {"contains": ["Type arguments on non-generic 'Plain': it declares no type parameter, got 1"]}},
    {"input": {"op": "typecheck", "src": USE_BARE}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": USE_NESTED_ANN}, "expected": {"errors": 0}},

    # —— 规则 4：代入按声明顺序逐位，正例必配反例 ——
    {"input": {"op": "typecheck", "src": USE_GET_STR}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": USE_GET_BAD},
     "error": {"contains": ["Return type mismatch: expected int, got str"], "min_count": 1}},
    {"input": {"op": "typecheck", "src": USE_FIELD_BAD},
     "error": {"contains": ["Return type mismatch: expected str, got int"]}},
    {"input": {"op": "typecheck", "src": USE_PAIR2},
     "error": {"contains": ["Return type mismatch: expected int, got str"]}},
    # 形式参数名不得外泄成类型（`got T` 这一族诊断必须绝迹）
    {"input": {"op": "typecheck", "src": USE_GET_BAD},
     "error": {"no_diagnostic_contains": ["got T at", "got T,"]}},
    {"input": {"op": "typecheck", "src": USE_BARE},
     "expected": {"errors": 0, "no_arity_diagnostic": True}},
    # 代入要真的改类型：容器返回 `list<T>` 时按 list 形判，不能退化成 object
    {"input": {"op": "typecheck", "src": USE_LIST_RETURN},
     "error": {"min_count": 1, "contains": ["Return type mismatch: expected int, got"]}},
    # 接收者链式代入：`l.next()` 是 `Link<int>`，再 `.next()` 仍是 `Link<int>` ⇒ 判红是对的
    {"input": {"op": "typecheck", "src": USE_DEEP_CHAIN},
     "error": {"contains": ["Return type mismatch: expected int, got Link[int]"],
               "matches": r"at \d+:\d+"}},
    {"input": {"op": "typecheck", "src": USE_DEEP_CHAIN_OK}, "expected": {"errors": 0}},

    # —— 规则 2 的后半句：class 与 struct 共用一份代入实现（对称的成对两格）——
    {"input": {"op": "typecheck", "src": WRAP_SUBST},
     "error": {"contains": ["Return type mismatch: expected str, got int"]}},
    {"input": {"op": "typecheck", "src": WRAP_BARE}, "expected": {"errors": 0}},

    # —— 规则 5：产物必须擦除（只在有效程序上验，避免 not_contains 恒真）——
    {"input": {"op": "codegen", "src": BOX_INIT},
     "expected": {"errors": 0, "contains": ["class Box:", "def get(self):"],
                  "not_contains": ["Box<T>", "<int>", "-> T", "(int(),"]}},
    {"input": {"op": "codegen", "src": USE_PAIR_OK},
     "expected": {"contains": ["class Pair:"], "not_contains": ["Pair<T", "T, U", "[int]"]}},
    {"input": {"op": "codegen", "src": NUM_CONSTR},
     "expected": {"contains": ["class Num:"], "not_contains": ["Num<T", "int | float"]}},
    # 元数不符的程序不得产出"看起来正常"的类体
    {"input": {"op": "codegen", "src": USE_ARITY_OVER},
     "error": {"stage": "typecheck", "contains": ["Type argument count mismatch"]}},
    # 字段表：class 的成员在 `.body`（LetStmt），Ω-gate 的 class_fields 观测量必须看得见
    {"input": {"op": "codegen", "src": USE_GET_OK},
     "expected": {"class_fields": {"Box": ["content"]}}},
]

SPEC = {
    "op": "cypy.generic.class",
    "version": "1.0",
    "definition": {
        "signature": "class Name<T, U: Bound>[:|（Base）| extends Base] ；"
                     "let b: Name<a1, a2> = Name<a1, a2>(args) ；b.member / b.method() 按位代入",
        "note": "SYNTAX/11「泛型类的判定口径」规则 1-5：定义侧三种前缀与约束由 `_parse_type_param_list`"
                "一处实现（struct 同源）；使用侧元数由 `_generic_arity_diagnostic` 一处实现（调用点同源）；"
                "接收者的类型实参按声明顺序逐位代入成员/方法类型，裸名按擦除（object）；"
                "产物类头不留类型参数，也不留形式参数名。",
    },
    "preconditions": ["类声明带 generic_params（`class Box<T>:` 及两种带基类的前缀）",
                      "类型实参是 `_parse_type()` 可解析的类型表达式",
                      "class 的成员是 `.body` 里的 LetStmt / FuncDef（不是 `.fields`）"],
    "laws": ["SYNTAX/11 泛型类的判定口径 规则 1", "SYNTAX/11 泛型类的判定口径 规则 2",
             "SYNTAX/11 泛型类的判定口径 规则 3", "SYNTAX/11 泛型类的判定口径 规则 4",
             "SYNTAX/11 泛型类的判定口径 规则 5"],
    "tests": PAIRS,
    "fingerprint": "fnv1a64:PENDING",
}


def main() -> int:
    bad = []
    for i, pair in enumerate(PAIRS):
        side = "error" if "error" in pair else "expected"
        obs = og.execute(pair["input"])
        ok, why = og.judge(pair[side], obs)
        if ok is not True:
            bad.append(f"#{i} {pair['input']['op']} stage={obs['stage']} "
                       f"errors={obs['errors'][:2]} -> ok={ok} why={why}")
    if bad:
        for b in bad:
            print("MISMATCH", b)
        print(f"CONCLUSION refuse={len(bad)} 条断言与实测不符 ⇒ 不改 corpus/")
        return 1
    OUT.write_text(json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"WROTE {OUT.name} cases={len(PAIRS)} all_verified_against_live_pipeline=yes")
    print("CONCLUSION wrote=1 specs=1 pairs=" + str(len(PAIRS))
          + " next=python scripts/omega_gate.py --seal --op cypy.generic.class")
    return 0


if __name__ == "__main__":
    sys.exit(main())
