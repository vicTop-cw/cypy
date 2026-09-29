"""R13 元素位判定的成对探针：同一批形状跑两次口径，并自带"该绿/该红"两组门。

形状分四栏，缺一不可：
 · `CTRL_*`  读取通道对照 —— 不红就说明我的观测口径坏了，后面所有读数都不作数；
 · `P*`      非别名容器基线（BUG-136 的"根因不在别名"就是靠这一栏立住的）；
 · `A*`      同形走泛型别名；
 · `G*`      收紧后**必须仍然全绿**的占位形态（`SYNTAX/02` 规则 3-5 点名的四类 + 用户类型保守集）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
import omega_gate as g  # noqa: E402

SRC = {
    # ---- 读取通道对照：不红即口径坏 ----
    "CTRL_scalar_mismatch": 'def f() -> int:\n    let n: int = "s"\n    return 0\n',
    # ---- 非别名容器基线 ----
    "P01_tuple_inner_wrong": 'def f() -> int:\n    let bad: tuple<bool, int> = (True, "x")\n    return 0\n',
    "P02_tuple_flag_wrong": "def f() -> int:\n    let bad: tuple<bool, int> = (1, 2)\n    return 0\n",
    "P03_list_elem_wrong": 'def f() -> int:\n    let bad: list<int> = ["s"]\n    return 0\n',
    "P05_dict_val_wrong": 'def f() -> int:\n    let bad: dict<str, int> = {"a": "b"}\n    return 0\n',
    "P06_unknown_in_tuple": "def f() -> int:\n    let bad: tuple<bool, NotAType> = (True, 1)\n    return 0\n",
    "P07_list_of_list_wrong": 'def f() -> int:\n    let bad: list<list<int>> = [["s"]]\n    return 0\n',
    "P08_tuple_arity_wrong": "def f() -> int:\n    let bad: tuple<int, int> = (1,)\n    return 0\n",
    "P09_return_elem_wrong": 'def f() -> tuple<bool, int>:\n    return (True, "x")\n',
    "P10_return_narrow": "def f() -> list<int>:\n    return [1.5]\n",
    # ---- 同形走别名 ----
    "A01_alias_inner_wrong": 'type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n    let bad: Result<int> = (True, "x")\n    return 0\n',
    "A02_alias_flag_wrong": "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n    let bad: Result<int> = (1, 2)\n    return 0\n",
    "A03_alias_ok": "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n    let ok: Result<int> = (True, 2)\n    return 0\n",
    "A04_alias_unknown_arg": "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n    let bad: Result<NotAType> = (True, 1)\n    return 0\n",
    "A05_alias_bare_use": "type Pair<T> = tuple<T, T>\n\ndef f() -> int:\n    let bad: Pair = (1, 2)\n    return 0\n",
    "A06_alias_arity_wrong": "type Result<T> = tuple<bool, T>\n\ndef f() -> int:\n    let bad: Result<int, int> = (True, 1)\n    return 0\n",
    "A07_alias_of_alias": 'type Pair<T> = tuple<T, T>\ntype Triple<T> = Pair<Pair<T>>\n\ndef f() -> int:\n    let bad: Triple<int> = ((1, 2), ("x", 4))\n    return 0\n',
    "A08_alias_in_param": "type Result<T> = tuple<bool, T>\n\ndef g(r: Result<int>) -> int:\n    return 0\n",
    "A09_alias_scalar_wrong": 'type My = int\n\ndef f() -> int:\n    let bad: My = "s"\n    return 0\n',
    "A10_alias_bound_decl": "type Num<T: int | float> = tuple<bool, T>\n\ndef f() -> int:\n    return 0\n",
    # ---- 收紧后必须仍然全绿 ----
    "G01_empty_ctor": "def f() -> int:\n    let x: list<int> = list()\n    return 0\n",
    "G02_nested_hetero": 'def f() -> int:\n    let x: list<list<int>> = [["s"], [1]]\n    return 0\n',
    "G03_tuple_none": "def f() -> int:\n    let x: tuple<bool, int> = (True, None)\n    return 0\n",
    "G04_mixed_collapse": 'def f() -> int:\n    let x: list<int> = [1, "s"]\n    return 0\n',
    "G05_widening": "def f() -> int:\n    let x: list<float> = [1, 2]\n    return 0\n",
    "G06_set_noarg": "def f() -> int:\n    let x: set<int> = set()\n    return 0\n",
    "G07_return_ok": "def f() -> list<int>:\n    return [1, 2]\n",
    "G08_user_types_lenient": "class Dog:\n    n: str\n\ndef f() -> int:\n    let x: list<Dog> = [Dog()]\n    return 0\n",
    "G09_trait_elem_lenient": (
        "trait Speak:\n    def say(self) -> int\n\n"
        "class Dog:\n    n: str\n\ndef f() -> int:\n"
        "    let x: list<Speak> = [Dog()]\n    return 0\n"
    ),
    "G10_dict_still_lenient": 'def f() -> int:\n    let x: dict<str, int> = {"a": "b"}\n    return 0\n',
    "G11_union_alias_use": "type ListOrSet<T> = list<T> | set<T>\n\ndef f() -> int:\n    let x: ListOrSet<int> = [1, 2]\n    return 0\n",
    # ---- 别名展开（BUG-138）与联合形态别名代入（BUG-139）----
    "N01_nested_alias_ok": "type Pair<T> = tuple<T, T>\ntype Triple<T> = Pair<Pair<T>>\n\ndef f() -> int:\n    let ok: Triple<int> = ((1, 2), (3, 4))\n    return 0\n",
    "N02_nested_alias_wrong": 'type Pair<T> = tuple<T, T>\ntype Triple<T> = Pair<Pair<T>>\n\ndef f() -> int:\n    let bad: Triple<int> = ((1, 2), ("x", 4))\n    return 0\n',
    "N03_scalar_alias_in_alias": 'type ID = int\ntype Row = tuple<ID, int>\n\ndef f() -> int:\n    let bad: Row = ("a", 1)\n    return 0\n',
    "N04_self_alias_no_hang": "type Loop<T> = Loop<T>\n\ndef f() -> int:\n    let x: Loop<int> = 1\n    return 0\n",
    "U01_maybe_wrong": 'type Maybe<T> = T | None\n\ndef f() -> int:\n    let bad: Maybe<int> = "s"\n    return 0\n',
    "U02_maybe_ok": "type Maybe<T> = T | None\n\ndef f() -> int:\n    let ok: Maybe<int> = None\n    return 0\n",
    "U03_maybe_int_ok": "type Maybe<T> = T | None\n\ndef f() -> int:\n    let ok: Maybe<int> = 3\n    return 0\n",
    "U04_listorset_elem_wrong": 'type ListOrSet<T> = list<T> | set<T>\n\ndef f() -> int:\n    let bad: ListOrSet<int> = ["s"]\n    return 0\n',
}

MUST_RED = (
    "CTRL_scalar_mismatch",
    "P01_tuple_inner_wrong",
    "P02_tuple_flag_wrong",
    "P03_list_elem_wrong",
    "P07_list_of_list_wrong",
    "P08_tuple_arity_wrong",
    "P09_return_elem_wrong",
    "P10_return_narrow",
    "A01_alias_inner_wrong",
    "A02_alias_flag_wrong",
    "A06_alias_arity_wrong",
    "A07_alias_of_alias",
    "N02_nested_alias_wrong",
    "N03_scalar_alias_in_alias",
    "U01_maybe_wrong",
)
MUST_GREEN = (
    "A03_alias_ok",
    "A08_alias_in_param",
    "G01_empty_ctor",
    "G02_nested_hetero",
    "G03_tuple_none",
    "G04_mixed_collapse",
    "G05_widening",
    "G06_set_noarg",
    "G07_return_ok",
    "G08_user_types_lenient",
    "G09_trait_elem_lenient",
    "G11_union_alias_use",
    "N01_nested_alias_ok",
    "U02_maybe_ok",
    "U03_maybe_int_ok",
)


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "a1"
    before_path = HERE / "logs" / "r13_alias_paired_a1.json"
    before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else {}
    rows, flipped, crashed = {}, [], []
    for key, src in SRC.items():
        try:
            o = g.execute({"op": "typecheck", "src": src})
        except Exception as exc:  # 自指别名之类会把分析器打成 RecursionError ⇒ 那是硬失效
            crashed.append(f"{key}:{type(exc).__name__}")
            rows[key] = {"stage": "crash", "n": -1, "errs": [f"{type(exc).__name__}: {exc}"]}
            print(f"CRASH {key:26s} {type(exc).__name__}: {str(exc)[:74]}")
            continue
        errs = [e for e in o.get("errors", []) if e.strip()]
        rows[key] = {"stage": o.get("stage"), "n": len(errs), "errs": errs}
        b = before.get(key, {}).get("n")
        if b is not None and b != len(errs):
            flipped.append(f"{key}:{b}->{len(errs)}")
        mark = "RED " if errs else "ok  "
        print(
            f"{mark}{key:26s} {o.get('stage'):6s} n={len(errs)} "
            f":: {' | '.join(e.strip()[:74] for e in errs[:2])}"
        )
    silent = [k for k in MUST_RED if not rows[k]["n"] or rows[k]["stage"] == "crash"]
    broke = [k for k in MUST_GREEN if rows[k]["n"]]
    unparsed = [k for k, v in rows.items() if v["stage"] == "parse"]
    out = HERE / "logs" / f"r13_container_probe_{tag}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"CONCLUSION r13_container_probe tag={tag} cases={len(rows)} "
        f"red={sum(1 for v in rows.values() if v['n'] > 0)} crashed={crashed} "
        f"flipped={len(flipped)} "
        f"must_be_red_but_silent={silent} must_stay_green_now_red={broke} "
        f"parse_failures={unparsed} out={out.name}"
    )
    return 1 if (silent or broke or crashed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
