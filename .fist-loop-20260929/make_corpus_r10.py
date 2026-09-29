"""R10 判据层：新增 Ω-spec `cypy.generic.callsite`（SYNTAX/11「调用点的类型实参」规则 1-5）。

每条测试对的 expected 都是**实测值**（本脚本落盘前会逐条跑 `omega_gate.execute` 复核，
观测与写下的断言不一致就直接拒绝生成），不许"先写理想值再让门禁去红"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

OUT = ROOT / "corpus" / "cypy.generic.callsite.json"

ID = "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    n: int = identity<int>(42)\n    return n\n"
PAIR = ("def pair<T, U>(first: T, second: U) -> tuple<T, U>:\n    return (first, second)\n\n\n"
        "def f() -> int:\n    p: tuple<int, str> = pair<int, str>(42, \"a\")\n    return 0\n")
FOO = ("struct Foo:\n    value: int\n\n\ndef identity<T>(x: T) -> T:\n    return x\n\n\n"
       "def f():\n    v = Foo(value=1)\n    return identity<Foo>(v)\n")
BOX = "struct Box<T>:\n    value: T\n\n\ndef f():\n    b = Box<int>(value=100)\n    return b.value\n"
BAD_SUB = ("def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> str:\n"
           "    s: str = identity<int>(\"Alice\")\n    return s\n")
BAD_ARITY = ("def pair<T, U>(first: T, second: U) -> tuple<T, U>:\n    return (first, second)\n\n\n"
             "def f() -> int:\n    return pair<int>(42)\n")
NONGEN = "def mk(a: int) -> int:\n    return a\n\n\ndef f() -> int:\n    return mk<int>(1)\n"
CONSTR = ("def process<T: int | float>(value: T) -> T:\n    return value\n\n\n"
          "def f() -> str:\n    return process<str>(\"hello\")\n")
CMP = ("def f(xs: list<int>, ys: list<int>) -> int:\n"
       "    if len(xs) < len(ys):\n        return 1\n    return 0\n")
NESTED = ("def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n"
          "    n: int = identity<int>(identity<int>(42))\n    return n\n")
# —— 边界形态（探针实测得到，不是设想）——
ID_EMPTY = "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    return identity<>(1)\n"
ID_TRAILING = "def identity<T>(x: T) -> T:\n    return x\n\n\ndef f() -> int:\n    return identity<int,>(1)\n"
NONGEN_TWO = "def mk(a: int) -> int:\n    return a\n\n\ndef f() -> int:\n    return mk<int, str>(1)\n"
NESTED_ARG = ("def identity<T>(x: T) -> T:\n    return x\n\n\ndef f(xs: list<int>) -> list<list<int>>:\n"
              "    return identity<list<list<int>>>(xs)\n")
DICT_ARG = ("def identity<T>(x: T) -> T:\n    return x\n\n\ndef f(d: dict[str, int]) -> dict[str, int]:\n"
            "    return identity<dict[str, int]>(d)\n")
UNION_ARG = ("def identity<T>(x: T) -> T:\n    return x\n\n\ndef f(v: int) -> int | float:\n"
             "    return identity<int | float>(v)\n")

PAIRS = [
    # —— 规则 1/3：调用点尖括号是类型实参表，多于一项也要收下 ——
    {"input": {"op": "typecheck", "src": ID}, "expected": {"errors": 0}},
    {"input": {"op": "typecheck", "src": PAIR}, "expected": {"errors": 0, "stage": "ok"}},
    # 对照半边：同一位置的 `<…>` 若是比较运算，新前视不得把它吃掉
    {"input": {"op": "typecheck", "src": CMP}, "expected": {"errors": 0}},
    # —— 规则 2：元数与非泛型被调方 ——
    {"input": {"op": "typecheck", "src": BAD_ARITY},
     "error": {"contains": ["Type argument count mismatch: 'pair' declares 2 type parameter(s), got 1"],
               "matches": r"at \d+:\d+"}},
    {"input": {"op": "typecheck", "src": NONGEN},
     "error": {"contains": ["Type arguments on non-generic 'mk': it declares no type parameter, got 1"],
               "matches": r"at \d+:\d+"}},
    # —— 规则 5：代入优先于推断，且与约束一起判 ——
    {"input": {"op": "typecheck", "src": BAD_SUB},
     "error": {"contains": ["Type mismatch: expected str, got int"], "matches": r"at \d+:\d+"}},
    {"input": {"op": "typecheck", "src": CONSTR},
     "error": {"contains": ["Generic constraint violation"], "min_count": 1}},
    # —— 规则 4：产物必须擦除（既不留下标，也不插对类型名的零参调用）——
    {"input": {"op": "codegen", "src": ID},
     "expected": {"contains": ["n: int = identity(42)"], "not_contains": ["(int(), identity"], "errors": 0}},
    {"input": {"op": "codegen", "src": FOO},
     "expected": {"contains": ["return identity(v)"], "not_contains": ["(Foo(),", "identity[Foo]"], "errors": 0}},
    {"input": {"op": "codegen", "src": PAIR},
     "expected": {"contains": ["pair(42, 'a')"], "not_contains": ["(int(),", "pair<int"], "errors": 0}},
    {"input": {"op": "codegen", "src": BOX},
     "expected": {"contains": ["b = Box(value=100)"], "not_contains": ["(int(),", "Box<int>"], "errors": 0}},
    {"input": {"op": "codegen", "src": NESTED},
     "expected": {"contains": ["identity(identity(42))"], "not_contains": ["(int(),", "(identity,"], "errors": 0}},
    # 反例半边：元数不符的程序不得生成"看起来正常"的产物（codegen 停在 typecheck 阶段）
    {"input": {"op": "codegen", "src": BAD_ARITY},
     "error": {"stage": "typecheck", "contains": ["Type argument count mismatch"]}},
    # 未擦除形态的运行期含义 = 把类型名当零参函数调用；这条把"过去长什么样"钉成不会复活的反面
    {"input": {"op": "codegen_unchecked", "src": FOO},
     "expected": {"not_contains": ["(Foo(),", "Foo()"], "contains": ["identity(v)"]}},

    # —— 边界审视（本环新增形态的输入域四类：空 / 非法 / 嵌套极值 / 复合类型）——
    # 空类型实参表：必须语法级硬拒，而不是"能吃但无人管"
    {"input": {"op": "typecheck", "src": ID_EMPTY},
     "error": {"stage": "parse", "contains": ["Unexpected token GT"]}},
    # 尾逗号形态：同样硬拒（不收 → 不做"逗号可省略"的隐式扩张）
    {"input": {"op": "typecheck", "src": ID_TRAILING},
     "error": {"stage": "parse", "contains": ["Unexpected token COMMA"]}},
    # 非泛型被调方挂两个实参：元数文案要如实报 2
    {"input": {"op": "typecheck", "src": NONGEN_TWO},
     "error": {"contains": ["Type arguments on non-generic 'mk': it declares no type parameter, got 2"]}},
    # 嵌套类型实参（`list<list<int>>` 三连 `>`）：解析收下且按位代入
    {"input": {"op": "typecheck", "src": NESTED_ARG}, "expected": {"errors": 0}},
    # 多元类型表达式作为**一个**实参（`dict[str, int]`）：逗号在方括号内不得当表分隔符
    {"input": {"op": "typecheck", "src": DICT_ARG}, "expected": {"errors": 0}},
    # 联合类型作为实参（`int | float`）：代入后返回类型即联合本身
    {"input": {"op": "typecheck", "src": UNION_ARG}, "expected": {"errors": 0}},
    # 资源极限一类：本形态是编译期语法/代入判定，无堆、无循环、无 I/O ⇒ 不适用，
    # 依据写进本轮报告 §3.4（不做无法判定的断言，也不放恒真门）
]

SPEC = {
    "op": "cypy.generic.callsite",
    "version": "1.0",
    "definition": {
        "signature": "f<A, B>(args) -> 代入后的返回类型；产物里的调用形如 f(args)",
        "note": "SYNTAX/11「调用点的类型实参」规则 1-5：调用点尖括号只有类型实参这一种解释"
                "（`<checker>` 在定义侧且 v1 不支持，SYNTAX/33 P-1.8）；元数按被调方声明判定；"
                "产物必须擦除，既不得留下标形态也不得插入对类型名的零参调用。",
    },
    "preconditions": ["被调方是带 generic_params 的 def / struct / class",
                      "类型实参是 `_parse_type()` 可解析的类型表达式"],
    "laws": ["SYNTAX/11 调用点的类型实参 规则 1", "SYNTAX/11 调用点的类型实参 规则 2",
             "SYNTAX/11 调用点的类型实参 规则 3", "SYNTAX/11 调用点的类型实参 规则 4",
             "SYNTAX/11 调用点的类型实参 规则 5"],
    "tests": PAIRS,
    "fingerprint": "fnv1a64:PENDING",
}


def main() -> int:
    # 落盘前自证：每条断言都要能被 omega_gate.judge 判成 True，否则拒绝生成 spec
    bad = []
    for i, pair in enumerate(PAIRS):
        side = "error" if "error" in pair else "expected"
        obs = og.execute(pair["input"])
        ok, why = og.judge(pair[side], obs)
        if ok is not True:
            bad.append(f"#{i} {pair['input']['op']} -> {ok} {why}")
    if bad:
        for b in bad:
            print("MISMATCH", b)
        print(f"CONCLUSION refuse=生成的断言有 {len(bad)} 条与实测不符 ⇒ 不改 corpus/")
        return 1
    OUT.write_text(json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"WROTE {OUT.name} cases={len(PAIRS)} all_verified_against_live_pipeline=yes")
    print("CONCLUSION wrote=1 specs=1 pairs=" + str(len(PAIRS)) + " next=python scripts/omega_gate.py --seal --op cypy.generic.callsite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
