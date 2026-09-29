"""R13 的 Ω-spec 语料：容器元素位 + 别名展开的成对判据（`corpus/cypy.container.elements.json`）。

刻意**不走** `omega_gate.py --seal`：那条命令会把 `corpus/` 下**每一份** spec 重写一遍
（`for p in files: p.write_text(...)`），而其余六份是既往轮的基线。这里只给自己这份算指纹，
并且落盘前后各扫一次全目录哈希，证明"别人那份一个字节都没动"。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS = ROOT / "corpus"
NAME = "cypy.container.elements.json"
OUT = CORPUS / NAME

_spec = importlib.util.spec_from_file_location("omega_gate", ROOT / "scripts" / "omega_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

TC = "typecheck"


def pos(src: str, reason: str) -> dict:
    return {"input": {"op": TC, "src": src}, "expected": {"errors": 0}, "why": reason}


def neg(src: str, contains: list, reason: str, errors: int = 1, matches: str = "") -> dict:
    err = {"errors": errors, "contains": contains}
    if matches:
        err["matches"] = matches
    return {"input": {"op": TC, "src": src}, "error": err, "why": reason}


TESTS = [
    # ---- 规则 1：定长容器的个数与逐位 ----
    neg(
        'def f() -> int:\n    let bad: tuple<bool, int> = (True, "x")\n    return 0\n',
        ["Element 2 type mismatch: expected int, got str"],
        "元组第二位声明 bool,int 却收 str ⇒ 必须点名元素位与实际类型",
    ),
    neg(
        "def f() -> int:\n    let bad: tuple<bool, int> = (1, 2)\n    return 0\n",
        ["Element 1 type mismatch: expected bool, got int"],
        "元组第一位 bool 收 int ⇒ 标量位不同名即不兼容（两侧都在闭合标量表内）",
    ),
    neg(
        "def f() -> int:\n    let bad: tuple<int, int> = (1,)\n    return 0\n",
        ["Tuple element count mismatch: expected 2, got 1"],
        "定长容器个数不符是事实，与元素名可否判定无关",
    ),
    # ---- 规则 2：变长容器与嵌套 ----
    neg(
        'def f() -> int:\n    let bad: list<int> = ["s"]\n    return 0\n',
        ["Element 1 type mismatch: expected int, got str"],
        "list 元素位必须跟声明的元素类型比",
    ),
    neg(
        'def f() -> int:\n    let bad: list<list<int>> = [["s"]]\n    return 0\n',
        ["Element 1 type mismatch: expected int, got str"],
        "嵌套 list 要下沉一层再判（外层元素两侧都带参数 ⇒ 不是占位）",
    ),
    # ---- 规则 3：数值加宽单向 ----
    pos(
        "def f() -> int:\n    let ok: list<float> = [1, 2]\n    return 0\n",
        "bool→int→float→double 单向加宽在元素位同样成立",
    ),
    neg(
        "def f() -> int:\n    let bad: list<int> = [1.5]\n    return 0\n",
        ["Element 1 type mismatch: expected int, got float"],
        "向下收窄（float→int）在元素位要报，与标量位同一条阶梯",
    ),
    # ---- 规则 4：四类占位一律放行 ----
    pos(
        "def f() -> int:\n    let x: list<int> = list()\n    return 0\n",
        "空容器构造器：值侧没有元素信息 ⇒ 占位放行",
    ),
    pos(
        'def f() -> int:\n    let x: list<list<int>> = [["s"], [1]]\n    return 0\n',
        "嵌套 heterogeneous ⇒ 内层塌成无参 list ⇒ 占位放行",
    ),
    pos(
        "def f() -> int:\n    let x: tuple<bool, int> = (True, None)\n    return 0\n",
        "含 None 的元组：值侧 None 成员放行（该分支注释点名的形态）",
    ),
    pos(
        'def f() -> int:\n    let x: list<int> = [1, "s"]\n    return 0\n',
        "字面量 heterogeneous ⇒ list<object> ⇒ object 占位放行",
    ),
    pos(
        "def f() -> int:\n    let x: set<int> = set()\n    return 0\n",
        "无参 set() ⇒ 值侧没有元素信息",
    ),
    # ---- 规则 5：保守集（非闭合标量一律放行）----
    pos(
        "class Dog:\n    n: str\n\ndef f() -> int:\n    let x: list<Dog> = [Dog()]\n    return 0\n",
        "用户类元素：两侧同名 ⇒ 放行",
    ),
    pos(
        "trait Speak:\n    def say(self) -> int\n\n"
        "class Dog:\n    n: str\n\ndef f() -> int:\n"
        "    let x: list<Speak> = [Dog()]\n    return 0\n",
        "trait 与用户类元素名不同 ⇒ 保守放行（漏报记在 BUG-137 的未覆盖栏）",
    ),
    # ---- 规则 6：dict 键值位不在本节范围 ----
    pos(
        'def f() -> int:\n    let x: dict<str, int> = {"a": "b"}\n    return 0\n',
        "字典字面量至今不推断类型 ⇒ 拿不存在的实得类型比只会造出假绿",
    ),
    # ---- 返回位与声明位共用同一份判定 ----
    pos("def f() -> list<int>:\n    return [1, 2]\n", "返回位正确形状不得报"),
    neg(
        'def f() -> tuple<bool, int>:\n    return (True, "x")\n',
        ["Return element 2 type mismatch: expected int, got str"],
        "返回位必须走同一份元素判定，文案点名 Return",
    ),
    neg(
        "def f() -> list<int>:\n    return [1.5]\n",
        ["Return element 1 type mismatch: expected int, got float"],
        "返回位收窄同判",
    ),
    # ---- 别名代入（BUG-129 的正身 + BUG-138/139）----
    pos(
        "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n"
        "    let ok: Result<int> = (True, 2)\n    return 0\n",
        "别名代入后正确字面量不得报（正向对照：证明不是整条语法没实现）",
    ),
    neg(
        "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n"
        '    let bad: Result<int> = (True, "x")\n    return 0\n',
        ["Element 2 type mismatch: expected int, got str"],
        "别名右端的 T 要真的换成 int 之后再比元素位",
    ),
    pos(
        "type Pair<T> = tuple<T, T>\ntype Triple<T> = Pair<Pair<T>>\n\ndef f() -> int:\n"
        "    let ok: Triple<int> = ((1, 2), (3, 4))\n    return 0\n",
        "别名套别名必须展开到底（BUG-138 的假阳性正身：正确程序被拒）",
    ),
    neg(
        "type Pair<T> = tuple<T, T>\ntype Triple<T> = Pair<Pair<T>>\n\ndef f() -> int:\n"
        '    let bad: Triple<int> = ((1, 2), ("x", 4))\n    return 0\n',
        ["Element 2 type mismatch: expected int, got str"],
        "展开到底之后，内层真错要报出精确元素位而不是粗报文",
    ),
    neg(
        "type ID = int\ntype Row = tuple<ID, int>\n\ndef f() -> int:\n"
        '    let bad: Row = ("a", 1)\n    return 0\n',
        ["Element 1 type mismatch: expected int, got str"],
        "标量别名出现在别名右端里也要展开（ID⇒int）",
    ),
    neg(
        "type Loop<T> = Loop<T>\n\ndef f() -> int:\n" "    let x: Loop<int> = 1\n    return 0\n",
        ["Type mismatch: expected Loop[int], got int"],
        "自指别名停在原地展开：既不 RecursionError 也不把自己解成 int",
    ),
    pos(
        "type Maybe<T> = T | None\n\ndef f() -> int:\n"
        "    let ok: Maybe<int> = None\n    return 0\n",
        "联合形态别名代入后 None 成员合法",
    ),
    pos(
        "type Maybe<T> = T | None\n\ndef f() -> int:\n"
        "    let ok: Maybe<int> = 3\n    return 0\n",
        "联合形态别名代入后成员类型本身合法",
    ),
    neg(
        "type Maybe<T> = T | None\n\ndef f() -> int:\n"
        '    let bad: Maybe<int> = "s"\n    return 0\n',
        ["Type mismatch: expected Union[int, None], got str"],
        "联合形态的别名过去整条不代入 ⇒ 任意值放行（BUG-139 的正身）",
    ),
    pos(
        "type ListOrSet<T> = list<T> | set<T>\n\ndef f() -> int:\n"
        "    let x: ListOrSet<int> = [1, 2]\n    return 0\n",
        "demo 自己的形状：联合成员名对上即放行（元素位另单，见 BUG-139 未覆盖栏）",
    ),
]

SPEC = {
    "op": "cypy.container.elements",
    "version": "1.0",
    "preconditions": [
        "注解与字面量都是 `SYNTAX/02` 文档化的容器形态（`list<…>` / `tuple<…>` / 具名别名）",
        "值侧推断出了元素类型（`_visit` 对 Tuple/ListLiteral 返回带 `generic_params` 的 Type）",
        "两侧元素名都落在 `_SCALAR_ELEMENT_NAMES` 闭合标量表内，或两侧同名容器",
    ],
    "laws": [
        "SYNTAX/02 容器元素位判定 规则 1/2/3：定长判个数与逐位、变长判元素位、数值加宽单向",
        "SYNTAX/02 容器元素位判定 规则 4：四类占位（无元素信息 / object / None / 声明侧 object）一律放行",
        "SYNTAX/02 容器元素位判定 规则 5-6：非闭合标量保守放行；dict 键值位不在本节范围",
        "SYNTAX/12 类型别名「类型安全·编译时完全等价」：别名右端要展开到底（含别名套别名、联合形态）",
        "赋值位与返回位共用 `_check_container_elements` 一份判定 ⇒ 两侧不得一边判一边不判",
    ],
    # 用例级 `why` 只服务本脚本的可读性：既有 123 例的键集是 {input, expected|error}，
    # 多一个键就是给下游按形状解析的件埋雷 ⇒ 落盘前剥掉，理由留在 laws 与报告里。
    "tests": [{k: v for k, v in t.items() if k != "why"} for t in TESTS],
}
SPEC["fingerprint"] = gate.fnv1a64(gate.seal_payload(SPEC))


def dir_hashes() -> dict:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        for p in sorted(CORPUS.glob("*.json"))
    }


def main() -> int:
    if OUT.exists():
        print(f"SKIP {OUT.name} 已存在（幂等：不重复覆盖基线）")
        return 0
    before = dir_hashes()
    OUT.write_text(
        json.dumps(SPEC, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    after = dir_hashes()
    untouched = {k: v for k, v in before.items() if k != OUT.name}
    drift = [k for k, v in untouched.items() if after.get(k) != v]
    reparsed = json.loads(OUT.read_text(encoding="utf-8"))
    fp_ok = reparsed["fingerprint"] == gate.fnv1a64(gate.seal_payload(reparsed))
    print(
        f"CONCLUSION make_corpus_r13 cases={len(TESTS)} fp={SPEC['fingerprint']} "
        f"fp_selfcheck={fp_ok} others_untouched={not drift} "
        f"specs_before={len(before)} specs_after={len(after)} drift={drift}"
    )
    return 0 if (fp_ok and not drift) else 1


if __name__ == "__main__":
    raise SystemExit(main())
