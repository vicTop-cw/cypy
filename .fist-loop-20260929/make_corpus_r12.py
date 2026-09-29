"""R12 判据层：新增 Ω-spec `cypy.generic.bounds`（SYNTAX/11「类型约束」在使用侧的判定面，BUG-129）。

规矩沿用 R11：每条 expected 都是**实测值** —— 落盘前逐条走 `omega_gate.execute + judge` 复核，
有一条不符就拒绝写 corpus/（并打印实际观测，把断言改到真相上，而不是改产品凑断言）。
成对是硬要求：每个"违界必红"都配一个"合界必绿"的半边，否则把界判定整个删掉也能全绿。
覆盖面按**使用位 × 界的形态**两轴铺：注解位 / 显式类型实参构造位 ×（联合界 / 单名界 / trait 界 / typeclass 界）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as og  # noqa: E402

OUT = ROOT / "corpus" / "cypy.generic.bounds.json"
OP = "cypy.generic.bounds"

NUM_CLASS = (
    "class Num<T: int | float>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"
)
NUM_STRUCT = "struct NumS<T: int | float>:\n    v: T\n\n"
INT_ONLY = "struct One<T: int>:\n    v: T\n\n"
SHOW_TRAIT = "trait Show:\n    def show(self) -> int\n\n"
# trait 实现要写成 `impl Show for Impl:`，否则不会注册进 `trait_impls`（结构性匹配不算实现）
IMPL_SHOW = (
    "class Impl:\n    v: int\n\n\n"
    "impl Show for Impl:\n    def show(self) -> int:\n        return 1\n\n"
)
ONLY_TRAIT = (
    "class Only<T: Show>:\n    v: T\n\n" "    def pick(self) -> T:\n        return self.v\n\n"
)
# typeclass 的真实语法（`cypyc/parser/parser.py:1796` 声明 / :2871 实例）
NUMBER_TC = (
    "typeclass Number:\n    def plus(self) -> int\n\n\n"
    "impl typeclass Number for int:\n    def plus(self) -> int:\n        return 1\n\n"
)
ADDABLE = (
    "class Add<T: int>:\n    v: T\n\n" "    def add(self, o: T) -> T:\n        return self.v\n\n"
)
PLAIN_GEN = "class Pair<T>:\n    v: T\n\n    def get(self) -> T:\n        return self.v\n\n"


def use(decl: str, body: str) -> str:
    return decl + "\n\n" + body


VIOL_ANN = use(NUM_CLASS, "def f():\n    let x: Num<str> = Num(1)\n    return 0\n")
# 违界还会顺着成员代往下传：`x.get()` 的返回类型已是 str ⇒ 两条各归各的判据，都要在册
VIOL_ANN_CHAINED = use(
    NUM_CLASS, "def f() -> int:\n    let x: Num<str> = Num(1)\n    return x.get()\n"
)
OK_ANN = use(NUM_CLASS, "def f() -> int:\n    let x: Num<int> = Num(1)\n    return x.get()\n")
VIOL_ANN_S = use(NUM_STRUCT, "def f():\n    let x: NumS<str> = NumS(1)\n    return 0\n")
OK_ANN_S = use(NUM_STRUCT, "def f():\n    let x: NumS<float> = NumS(1)\n    return 0\n")
VIOL_ANN_MULTI = use(
    "class Two<T: int | float, U: str>:\n    a: T\n    b: U\n\n",
    'def f():\n    let x: Two<int, int> = Two(1, "s")\n    return 0\n',
)
OK_ANN_MULTI = use(
    "class Two<T: int | float, U: str>:\n    a: T\n    b: U\n\n",
    'def f():\n    let x: Two<float, str> = Two(1, "s")\n    return 0\n',
)
VIOL_EXPLICIT_CTOR = use(INT_ONLY, 'def f():\n    b = One<str>(v="s")\n    return 0\n')
OK_EXPLICIT_CTOR = use(INT_ONLY, "def f():\n    b = One<int>(v=1)\n    return 0\n")
VIOL_TRAIT_BOUND = use(
    SHOW_TRAIT + IMPL_SHOW + ONLY_TRAIT, "def f():\n    let x: Only<int> = Only(1)\n    return 0\n"
)
OK_TRAIT_BOUND = use(
    SHOW_TRAIT + IMPL_SHOW + ONLY_TRAIT, "def f():\n    let x: Only<Impl> = Only(1)\n    return 0\n"
)
VIOL_TYPECLASS_BOUND = use(
    NUMBER_TC + "class Cell<T: Number>:\n    v: T\n\n",
    'def f():\n    let c: Cell<str> = Cell("s")\n    return 0\n',
)
OK_TYPECLASS_BOUND = use(
    NUMBER_TC + "class Cell<T: Number>:\n    v: T\n\n",
    "def f():\n    let c: Cell<int> = Cell(1)\n    return 0\n",
)
NO_BOUND_OK = use(PLAIN_GEN, 'def f():\n    let p: Pair<str> = Pair("s")\n    return p.get()\n')
NO_BOUND_VIOL_SHAPE = use(
    PLAIN_GEN, 'def f() -> int:\n    let p: Pair<str> = Pair("s")\n    return p.get()\n'
)
# 元数错与违界错同时出现：两条各归各的判据，不许一条遮住另一条
BOTH_ARITY_AND_BOUND = use(NUM_CLASS, "def f():\n    let x: Num<str, int> = Num(1)\n    return 0\n")
# 构造位不写类型实参：声明界此刻无从判定（推断未接）⇒ 必须保持 0 诊断，别把 BUG-135 写成已过
INFER_NOT_YET = use(INT_ONLY, 'def f():\n    b = One(v="s")\n    return 0\n')

# 结构体字面量位（`Name {field: value}` ⇒ StructLiteral 节点）：本轮把这里的窄复制换成共用件，
# 于是 `T: int | float` 这类联合界第一次真的被判到（窄复制只认单名界 ⇒ 从前静默放行）
VIOL_LITERAL_UNION = use(NUM_STRUCT, 'def f():\n    a = NumS {v: "s"}\n    return 0\n')
OK_LITERAL_UNION = use(NUM_STRUCT, "def f():\n    a = NumS {v: 1}\n    return 0\n")
VIOL_LITERAL_SINGLE = use(INT_ONLY, 'def f():\n    a = One {v: "s"}\n    return 0\n')
OK_LITERAL_SINGLE = use(INT_ONLY, "def f():\n    a = One {v: 1}\n    return 0\n")

PAIRS = [
    {"input": {"op": "typecheck", "src": OK_ANN}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_ANN},
        "error": {
            "errors": 1,
            "contains": [
                "Generic constraint violation",
                "does not satisfy constraint 'int | float'",
                "(allowed: int | float)",
                "for parameter 'T'",
            ],
            "matches": r"reported at line \d+, col \d+",
        },
    },
    {
        "input": {"op": "typecheck", "src": VIOL_ANN_CHAINED},
        "error": {
            "errors": 2,
            "contains": [
                "does not satisfy constraint 'int | float'",
                "Return type mismatch: expected int, got str",
            ],
        },
    },
    {"input": {"op": "typecheck", "src": OK_ANN_S}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_ANN_S},
        "error": {"errors": 1, "contains": ["does not satisfy constraint 'int | float'"]},
    },
    {"input": {"op": "typecheck", "src": OK_ANN_MULTI}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_ANN_MULTI},
        "error": {
            "errors": 1,
            "contains": ["does not satisfy constraint 'str'", "for parameter 'U'"],
        },
    },
    {"input": {"op": "typecheck", "src": OK_EXPLICIT_CTOR}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_EXPLICIT_CTOR},
        "error": {
            "errors": 1,
            "contains": ["does not satisfy constraint 'int'", "in call to 'One'"],
        },
    },
    {"input": {"op": "typecheck", "src": OK_TRAIT_BOUND}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_TRAIT_BOUND},
        "error": {"errors": 1, "contains": ["does not implement trait 'Show'"]},
    },
    {"input": {"op": "typecheck", "src": OK_TYPECLASS_BOUND}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_TYPECLASS_BOUND},
        "error": {"errors": 1, "contains": ["Generic constraint violation", "'Number'"]},
    },
    {"input": {"op": "typecheck", "src": NO_BOUND_OK}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": NO_BOUND_VIOL_SHAPE},
        "error": {
            "errors": 1,
            "contains": ["Return type mismatch"],
            "not_contains": ["Generic constraint violation"],
        },
    },
    {
        "input": {"op": "typecheck", "src": BOTH_ARITY_AND_BOUND},
        "error": {
            "errors": 2,
            "contains": [
                "Type argument count mismatch",
                "does not satisfy constraint 'int | float'",
            ],
        },
    },
    {
        "input": {"op": "typecheck", "src": INFER_NOT_YET},
        "expected": {"errors": 0, "no_diagnostic_contains": ["Generic constraint violation"]},
    },
    {
        "input": {
            "op": "typecheck",
            "src": use(ADDABLE, "def f():\n    let a: Add<int> = Add(1)\n    return 0\n"),
        },
        "expected": {"errors": 0},
    },
    {
        "input": {
            "op": "typecheck",
            "src": use(ADDABLE, "def f():\n    let a: Add<str> = Add(1)\n    return 0\n"),
        },
        "error": {"errors": 1, "contains": ["does not satisfy constraint 'int'"]},
    },
    # 结构体字面量位（窄复制换成共用件后第一次可观测）
    {"input": {"op": "typecheck", "src": OK_LITERAL_UNION}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_LITERAL_UNION},
        "error": {
            "errors": 1,
            "contains": [
                "Generic constraint violation",
                "does not satisfy constraint 'int | float'",
            ],
            "matches": r"reported at line \d+, col \d+",
        },
    },
    {"input": {"op": "typecheck", "src": OK_LITERAL_SINGLE}, "expected": {"errors": 0}},
    {
        "input": {"op": "typecheck", "src": VIOL_LITERAL_SINGLE},
        "error": {"errors": 1, "contains": ["does not satisfy constraint 'int'"]},
    },
]

SPEC = {
    "op": OP,
    "preconditions": [
        "泛型声明带 `generic_constraints`（class 与 struct 两形同源）",
        "使用侧写了显式类型实参（注解位 `T<Args>` 或构造位 `Name<Args>(…)`）",
        "界的形态是 `_check_generic_constraint` 支持的四类：联合／单名／trait／typeclass",
    ],
    "laws": [
        "SYNTAX/11 类型约束：声明界在使用侧必判（BUG-129 的关闭面）",
        "SYNTAX/11 声明界在使用侧的判定 规则 1/2/3：注解位、显式实参构造位、结构体字面量位共用一份判定",
        "SYNTAX/11 泛型类的判定口径 规则 3/4：注解位与构造位共用同一份元数判定",
        "未写类型实参的构造位不做推断 ⇒ 不得凭空产诊断（该面另单 BUG-135）",
    ],
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
            bad.append(
                f"#{i} op={pair['input']['op']} stage={obs['stage']} errors={obs['errors']} "
                f"-> ok={ok} why={why}"
            )
    if bad:
        for b in bad:
            print("MISMATCH", b)
        print(f"CONCLUSION refuse={len(bad)} 条断言与实测不符 ⇒ 不写 corpus/")
        return 1
    OUT.write_text(
        json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"WROTE {OUT.name} cases={len(PAIRS)} all_verified_against_live_pipeline=yes")
    print(
        f"CONCLUSION wrote=1 specs=1 pairs={len(PAIRS)} "
        f"next=python scripts/omega_gate.py --seal --op {OP}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
