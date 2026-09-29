"""生成 corpus/ 下两份 Ω-spec JSON（PROJECT-SPEC/05 §2 的字段形状）。

为什么用生成器而不是手写 JSON：JSON 不允许相邻字符串跨行拼接，手写两份各 15+ 条、
每条内嵌 .cypy 源码转义的文档，出错方式是「静默少一条用例」而不是报错。
生成器落盘后立即回读并 `json.loads` 校验、逐条断言测试对数量与 op 名，写坏就当场拒绝。

期望值来源（不是照着实现编的）：
- `SYNTAX/02-type-annotations.md`「注解形态闭集（R7 补）」规则 1-4；
- `SYNTAX/17-pattern-matching.md`「位置模式的元数与槽位规则（R7 补）」；
- 源码语料取自已入库的回归锁 `tests/test_pattern_positional_struct.py` / `tests/test_annotation_shape.py`。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"

EXTRACTOR_SRC = '''struct Email:
    address: str

    def __unapply__(self) -> tuple<str, str> | None:
        if '@' in self.address:
            parts = self.address.split('@')
            return (parts[0], parts[1])
        return None

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
'''

PLAIN_STRUCT_SRC = '''struct Email:
    address: str
    alias: str

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
'''

METHOD_FIRST_SRC = '''struct Shape:
    def area(self) -> int:
        return self.w * self.h

    w: int
    h: int

def describe(s: Shape) -> str:
    match s:
        case Shape(3, 4):
            return "three-four"
        case _:
            return "other"
'''

CLASS_METHOD_SRC = '''class Box:
    def open(self) -> str:
        return "opened"

    def label(self) -> str:
        return "box"

def peek(b: Box) -> str:
    match b:
        case Box(1, 2):
            return "one-two"
        case _:
            return "other"
'''

OVER_SRC = '''struct E:
    a: int

def g(e: E) -> str:
    match e:
        case E(x, y):
            return "two"
        case _:
            return "none"
'''

THIRTYTWO_SRC = ('struct E:\n    a: int\n\ndef g(e: E) -> str:\n    match e:\n        case E('
                  + ", ".join(f"v{i}" for i in range(32)) + '):\n            return "many"\n'
                  '        case _:\n            return "none"\n')

ZERO_SRC = '''struct E:
    a: int

def g(e: E) -> str:
    match e:
        case E():
            return "zero"
        case _:
            return "none"
'''

UNDER_SRC = '''struct E:
    a: int
    b: str

def g(e: E) -> str:
    match e:
        case E(x):
            return x
        case _:
            return "none"
'''

UNKNOWN_TYPE_SRC = '''def g(e):
    match e:
        case Unknown(x):
            return x
        case _:
            return "none"
'''

MIXED_SRC = '''struct E:
    a: int
    b: int

def g(e: E) -> int:
    match e:
        case E(3, y):
            return y
        case _:
            return 0
'''

MATCH_ARGS_SRC = """struct Point:
    x: int
    y: int

    __match_args__ = ("x", "y")

"""
MATCH_TWO_SRC = MATCH_ARGS_SRC + """def g(p: Point) -> int:
    match p:
        case Point(a, b):
            return a
        case _:
            return 0
"""
MATCH_THREE_SRC = MATCH_ARGS_SRC + """def g(p: Point) -> int:
    match p:
        case Point(a, b, c):
            return a
        case _:
            return 0
"""

CLASS_ARITY_SRC = '''class C:
    a: int

def g(c: C) -> str:
    match c:
        case C(x, y):
            return "two"
        case _:
            return "none"
'''

WILDCARD_SRC = '''struct E:
    a: int

def g(e: E) -> str:
    match e:
        case E(x):
            return x
        case _:
            return "none"
'''

NESTED_SRC = '''struct Inner:
    v: int

struct Outer:
    i: Inner

def g(o: Outer) -> int:
    match o:
        case Outer(Inner(z)):
            return z
        case _:
            return 0
'''

ANNOTATION_SPEC = {
    "op": "cypy.annotation.shape",
    "version": "1.0",
    "definition": {
        "signature": "decl ::= name ':' annotation ('=' expr)?; "
                     "annotation ::= Name | GenericType | PointerType | UnionType | RefType",
        "note": "依据 SYNTAX/02-type-annotations.md「注解形态闭集（R7 补，2026-09-29）」："
                "方括号/圆括号/花括号形态一律拒绝，诊断必须带 行:列 并点名正确写法；"
                "任何形态都不得把 AST 节点的 Python repr 写进产物。",
    },
    "preconditions": [
        "comptime 行内形式（`comptime: [1, 2]`）不是类型注解，不受本节约束",
        "生成器末路对未知形态只退化为 object（SYNTAX/02 该节规则 3）",
    ],
    "laws": ["L1-注解必须是类型形态", "L2-非法形态必须诊断且带行列", "L3-产物不得含 AST repr",
             "L4-comptime 整类排除"],
    "tests": [
        {"input": {"op": "typecheck", "src": "def f():\n    x: int = 1\n    return x\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: list<int> = [1, 2]\n    return x\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: tuple<int, int> = (1, 2)\n    return x\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def f():\n    m: dict<str, int> = {}\n    return m\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def f():\n    u: int | str = 1\n    return u\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def add(a: int, b: int) -> int:\n    return a + b\n"},
         "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "comptime: [1, 2]\n"}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: [int] = [1, 2]\n    return x\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: (int, str) = 1\n    return x\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": "def f():\n    m: {str: int} = 1\n    return m\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: 5 = 1\n    return x\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: list<[int]> = 1\n    return x\n"},
         "error": {"contains": ["Invalid type annotation"], "min_count": 1}},
        {"input": {"op": "typecheck",
                   "src": "def f():\n    x: " + "[" * 12 + "int" + "]" * 12 + " = 1\n    return x\n"},
         "error": {"contains": ["Invalid type annotation"], "min_count": 1}},
        {"input": {"op": "typecheck", "src": "def f():\n    x: = 1\n    return x\n"},
         "error": {"stage": "parse", "matches": r"at \d+:\d+"}},
        {"input": {"op": "codegen", "src": "def f():\n    x: list<int> = [1, 2]\n    return x\n"},
         "expected": {"not_contains": ["line=", "col=", "Constant(", "GenericType(", "List("]}},
        {"input": {"op": "codegen_unchecked", "src": "def f():\n    m: {str: int} = 1\n    return m\n"},
         "expected": {"contains": ["m: object"],
                      "not_contains": ["line=", "col=", "Constant(", "DictLiteral("]}},
        {"input": {"op": "codegen_unchecked", "src": "def f():\n    x: [int] = [1, 2]\n    return x\n"},
         "expected": {"not_contains": ["line=", "col=", "Constant(", "List("]}},
        {"input": {"op": "codegen", "src": "def f():\n    x: [int] = [1, 2]\n    return x\n"},
         "error": {"stage": "typecheck", "contains": ["Invalid type annotation"]}},
        # R8 寻虫：闭集里其余合法节点（RefType/PointerType(*void)/嵌套泛型/泛型的联合）
        # 用 no_diagnostic_contains 表达「本面不得出声」，避免被无关诊断（如赋值类型不符）冒充成失败。
        {"input": {"op": "typecheck", "src": "def f():\n    x: ref<int> = 1\n    return x\n"},
         "expected": {"no_diagnostic_contains": ["Invalid type annotation"]}},
        {"input": {"op": "typecheck", "src": "def f():\n    p: *void = 0\n    return p\n"},
         "expected": {"no_diagnostic_contains": ["Invalid type annotation"]}},
        {"input": {"op": "typecheck", "src": "def f():\n    g: list<list<int>> = []\n    return g\n"},
         "expected": {"no_diagnostic_contains": ["Invalid type annotation"]}},
        {"input": {"op": "typecheck",
                   "src": "def f():\n    t: tuple<int, int> | None = 0\n    return t\n"},
         "expected": {"no_diagnostic_contains": ["Invalid type annotation"]}},
        {"input": {"op": "typecheck", "src": "def f():\n    m: dict<str, [int]> = 1\n    return m\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": "def f():\n    t: tuple<int, [str]> = 0\n    return t\n"},
         "error": {"contains": ["Invalid type annotation"], "matches": r"at \d+:\d+"}},
    ],
    "fingerprint": "fnv1a64:PENDING",
}

# R9 规则 5/8 的形状：无 __unapply__ 且实参元数 > 字段数（常量实参那侧才会露出 `.__f{i}`）
OVER_ARITY_SRC = '''struct E:
    a: int
    b: int

def g(e: E) -> int:
    match e:
        case E(1, 2, 3):
            return 3
        case _:
            return 0
'''

PATTERN_SPEC = {
    "op": "cypy.pattern.positional",
    "version": "1.0",
    "definition": {
        "signature": "match(subject: T) case T(p0, p1, ...) -> bindings; "
                     "n = 可解包槽位数 = 提取器优先级或 .fields 声明数",
        "note": "依据 SYNTAX/17-pattern-matching.md「位置模式的元数与槽位规则（R7 补，2026-09-29）」："
                "槽位数来源优先级 __match_args__ < __unapply__ < __unapply_seq__ < __unwarp__，"
                "无提取器时按 .fields 声明序；实参元数 > n 必须诊断并带行列；方法名不占位置槽；"
                "类型不可见时不报元数错；产物不得出现 .__f{i}。",
    },
    "preconditions": [
        "subject 的类型在本模块可见，或作为运行期提取器处理",
        "实参元数 < n 不在强制诊断范围内（条款只强制大于）",
    ],
    "laws": ["L1-提取器优先", "L2-槽位数来源", "L3-超元必须诊断且带行列", "L4-方法名不是位置字段",
             "L5-绑定名类型取槽位类型", "L6-产物不得出现 __f{i}"],
    "tests": [
        {"input": {"op": "typecheck", "type_name": "Email", "src": EXTRACTOR_SRC},
         "expected": {"errors": 0, "slot_types": ["str", "str"]}},
        {"input": {"op": "typecheck", "type_name": "Email", "src": PLAIN_STRUCT_SRC},
         "expected": {"errors": 0, "slot_types": ["str", "str"]}},
        {"input": {"op": "codegen", "src": EXTRACTOR_SRC},
         "expected": {"contains": ["__unapply__()"], "not_contains": ["__f0", "__f1", "line="]}},
        {"input": {"op": "codegen", "type_name": "Shape", "src": METHOD_FIRST_SRC},
         "expected": {"contains": [".w == 3", ".h == 4"], "not_contains": ["area =="],
                      "class_fields": {"Shape": ["w", "h"]}}},
        {"input": {"op": "codegen", "src": CLASS_METHOD_SRC},
         "expected": {"fields_exclude": {"Box": ["open", "label"]}}},
        {"input": {"op": "typecheck", "src": OVER_SRC},
         "error": {"contains": ["Positional pattern 'E'"], "matches": r"unpacks only 1 at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": THIRTYTWO_SRC},
         "error": {"contains": ["Positional pattern 'E' has 32 slot(s)"], "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": ZERO_SRC}, "expected": {"errors": 0}},
        # 欠元：条款只强制「大于」，因此断言的是「不发元数诊断」而不是「零错误」——
        # `case E(x)` 让 x 取 0 号槽位 int，函数声明 -> str 时真报 Return type mismatch 才是对的（首轮跑批实测）。
        {"input": {"op": "typecheck", "src": UNDER_SRC}, "expected": {"no_arity_diagnostic": True}},
        {"input": {"op": "typecheck", "src": UNKNOWN_TYPE_SRC},
         "expected": {"no_arity_diagnostic": True}},
        {"input": {"op": "codegen", "src": MIXED_SRC}, "expected": {"not_contains": ["__f0", "__f1"]}},
        # R8 寻虫：class 与 struct 同规则（R6 的 `_record_pattern_shape` 两支共用），通配符与嵌套不吃槽位
        {"input": {"op": "typecheck", "src": CLASS_ARITY_SRC},
         "error": {"contains": ["Positional pattern 'C'"], "matches": r"unpacks only 1 at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": WILDCARD_SRC},
         "expected": {"no_diagnostic_contains": ["Positional pattern"]}},
        {"input": {"op": "typecheck", "type_name": "Point", "src": MATCH_TWO_SRC},
         "expected": {"errors": 0, "slot_types": ["int", "int"]}},
        {"input": {"op": "typecheck", "src": MATCH_THREE_SRC},
         "error": {"contains": ["Positional pattern 'Point' has 3 slot(s)"],
                   "matches": r"unpacks only 2 at \d+:\d+"}},
        {"input": {"op": "codegen", "src": MATCH_TWO_SRC},
         "expected": {"not_contains": ["__match_args__ =="], "class_fields": {"Point": ["x", "y"]}}},
        {"input": {"op": "codegen", "src": NESTED_SRC},
         "expected": {"no_diagnostic_contains": ["Positional pattern"],
                      "not_contains": ["__f0", "__f1"]}},
        # R9：规则 5/8 的落地形态 —— 元数越界不得生成成员访问，且该 case 恒不命中
        {"input": {"op": "typecheck", "src": OVER_ARITY_SRC},
         "error": {"contains": ["Positional pattern 'E' has 3 slot(s)"],
                   "matches": r"unpacks only 2 at \d+:\d+"}},
        # 用 codegen_unchecked：`codegen` 对已经报错的程序直接不出码（实测 `stage=typecheck`），
        # 那会让 not_contains 变成空集恒真 —— 越界槽位要检查的正是「硬出码时长什么样」。
        {"input": {"op": "codegen_unchecked", "src": OVER_ARITY_SRC},
         "expected": {"not_contains": ["__f0", "__f1", "__f2"], "contains": ["and False"]}},
    ],
    "fingerprint": "fnv1a64:PENDING",
}

# --- cypy.type.slice：SYNTAX/14「切片的类型规则（R9 补）」1-3 条 ---
SLICE_LIST_SRC = '''def f(xs: list<int>) -> int:
    ys: list<int> = xs[1:3]
    return len(ys)
'''
SLICE_TO_ELEM_SRC = '''def f(xs: list<int>) -> int:
    y: int = xs[1:3]
    return y
'''
INDEX_SRC = '''def f(xs: list<int>) -> int:
    y: int = xs[1]
    return y
'''
SLICE_FULL_SRC = '''def f(xs: list<int>) -> int:
    ys: list<int> = xs[:]
    return len(ys)
'''
SLICE_STEP_SRC = '''def f(xs: list<int>) -> int:
    ys: list<int> = xs[::2]
    return len(ys)
'''
SLICE_NEG_SRC = '''def f(xs: list<int>) -> int:
    ys: list<int> = xs[-2:]
    return len(ys)
'''
SLICE_STR_SRC = '''def f(s: str) -> str:
    t: str = s[1:3]
    return t
'''
SLICE_STR_TO_INT_SRC = '''def f(s: str) -> int:
    t: int = s[1:3]
    return t
'''

SLICE_SPEC = {
    "op": "cypy.type.slice",
    "version": "1.0",
    "definition": {
        "signature": "slice(container, start?, stop?, step?) -> same container type",
        "note": "SYNTAX/14 切片语法节的类型规则 1-2：切片结果是被切容器自身的类型；"
                "只有下标形态才降到元素类型。形态判据是解析器落地的 {\"slice\": True, …} dict。",
    },
    "preconditions": ["容器类型可解析（list<T> / str）", "切片形态与下标形态可按 AST 区分"],
    "laws": ["SYNTAX/14 切片规则 1", "SYNTAX/14 切片规则 2", "SYNTAX/14 切片规则 3"],
    "tests": [
        {"input": {"op": "typecheck", "src": SLICE_LIST_SRC}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": SLICE_FULL_SRC}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": SLICE_STEP_SRC}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": SLICE_NEG_SRC}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": SLICE_STR_SRC}, "expected": {"errors": 0}},
        {"input": {"op": "typecheck", "src": INDEX_SRC}, "expected": {"errors": 0}},
        # 成对的另一半：切片当元素用必须报出来，且报的是「切片是容器类型」而不是别的
        {"input": {"op": "typecheck", "src": SLICE_TO_ELEM_SRC},
         "error": {"contains": ["Type mismatch: expected int, got list[int]"],
                   "matches": r"at \d+:\d+"}},
        {"input": {"op": "typecheck", "src": SLICE_STR_TO_INT_SRC},
         "error": {"contains": ["Type mismatch: expected int, got str"], "matches": r"at \d+:\d+"}},
    ],
    "fingerprint": "fnv1a64:PENDING",
}

SPECS = [("cypy.annotation.shape", 24, ANNOTATION_SPEC), ("cypy.pattern.positional", 19, PATTERN_SPEC),
         ("cypy.type.slice", 8, SLICE_SPEC)]


def main() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    for op, expect_n, spec in SPECS:
        assert len(spec["tests"]) == expect_n, f"{op} 测试对 {len(spec['tests'])} != 台账 {expect_n}"
        text = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
        back = json.loads(text)
        assert back["op"] == op and len(back["tests"]) == expect_n, op
        (CORPUS / f"{op}.json").write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE corpus/{op}.json tests={expect_n} bytes={len(text.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
