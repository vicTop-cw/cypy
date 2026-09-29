"""R14 字典字面量的成对探针：先数"现在静默的错形"，再验"收紧后该绿的还绿"。

为什么要成对：`dict<str, int> = {"a": "b"}` 现在是**静默**的（`_visit` 没有 `DictLiteral` 分支，
返回 None ⇒ LetStmt 那串 `if declared_type and value_type` 根本不进）。
只报"它不判"不够 —— 上一轮的教训是先证明读取通道看得见这类形状，才谈得上"不判"。

栏位：
 · `CTRL_*`  读取通道对照（现在就该红：标量错配 + R13 已修的元素位）；
 · `D*`      字典形状错 —— **修复前必须静默**（这一栏就是缺陷清单），修复后必须红；
 · `G*`      收紧后必须仍然全绿（空字面量、混形塌 object、单向加宽、用户类保守集、
             无声明的 let、注解位与返回位正确形）—— 它们同时是"不许顺手扩大拒绝面"的边界。
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
    # ---- 读取通道对照 ----
    "CTRL_scalar_mismatch": 'def f() -> int:\n    let n: int = "s"\n    return 0\n',
    "CTRL_list_elem_wrong": 'def f() -> int:\n    let bad: list<int> = ["s"]\n    return 0\n',
    # ---- 字典形状错：修复前静默 ⇒ 这一栏的静默数就是缺陷数 ----
    "D01_value_wrong": 'def f() -> int:\n    let x: dict<str, int> = {"a": "b"}\n    return 0\n',
    "D02_key_wrong": 'def f() -> int:\n    let x: dict<int, str> = {"a": "b"}\n    return 0\n',
    "D03_return_value_wrong": 'def f() -> dict<str, int>:\n    return {"a": "b"}\n',
    "D04_nested_list_wrong": 'def f() -> int:\n    let x: dict<str, list<int>> = {"a": ["s"]}\n    return 0\n',
    "D05_alias_dict_wrong": 'type Count = dict<str, int>\n\ndef f() -> int:\n    let bad: Count = {"a": "b"}\n    return 0\n',
    "D06_dict_of_dict_wrong": (
        'def f() -> int:\n    let x: dict<str, dict<str, int>> = {"a": {"b": "c"}}\n    return 0\n'
    ),
    "D07_bool_key_under_str": "def f() -> int:\n    let x: dict<str, int> = {True: 1}\n    return 0\n",
    # 混形里全是数值：值位取阶梯最宽（int,float → float），对着 `dict<str, int>` 就是收窄 ⇒ 该红。
    # 这一形是承重矩阵 M3（撤掉"数值阶梯取最宽"）在 Ω-gate 那半边**没有**语料喂出来的洞 ——
    # 矩阵把它抓出来了 ⇒ 补进探针与 spec，而不是让那一格只由 pytest 一支锁撑着。
    "D08_mixed_numeric_narrow": 'def f() -> int:\n    let x: dict<str, int> = {"a": 1, "b": 2.5}\n    return 0\n',
    # ---- 收紧后必须仍然全绿 ----
    # 混形（键或值不止一种类型）塌成 object ⇒ 保守放行，与 R13 的 `G04_mixed_collapse` 同族：
    # 这一形**故意**不红，它是"不许顺手扩大拒绝面"的边界，所以放在 G 栏而不是 D 栏。
    "G14_hetero_both": 'def f() -> int:\n    let x: dict<str, int> = {"a": 1, "b": "c", 3: 4}\n    return 0\n',
    # D08 的成对半边：同一个混形字面量对着 `dict<str, float>`（= 取到的最宽）必须绿 ——
    # 没有这一格，"取最宽"与"一律塌 object"两种实现看着都能过 D08。
    "G15_mixed_numeric_widening_ok": 'def f() -> int:\n    let x: dict<str, float> = {"a": 1, "b": 2.5}\n    return 0\n',
    "G01_empty_literal": "def f() -> int:\n    let x: dict<str, int> = {}\n    return 0\n",
    "G02_correct": 'def f() -> int:\n    let x: dict<str, int> = {"a": 1}\n    return 0\n',
    "G03_hetero_values": 'def f() -> int:\n    let x: dict<str, int> = {"a": 1, "b": "c"}\n    return 0\n',
    "G04_widening_value": 'def f() -> int:\n    let x: dict<str, float> = {"a": 1}\n    return 0\n',
    "G05_bool_widening": 'def f() -> int:\n    let x: dict<str, int> = {"a": True}\n    return 0\n',
    "G06_user_type_value": (
        "class Dog:\n    n: str\n\ndef f() -> int:\n"
        '    let x: dict<str, Dog> = {"a": Dog()}\n    return 0\n'
    ),
    "G07_untyped_let": 'def f() -> int:\n    let d = {"a": 1}\n    return 0\n',
    "G08_nested_correct": 'def f() -> int:\n    let x: dict<str, list<int>> = {"a": [1]}\n    return 0\n',
    "G09_dict_of_dict_ok": (
        'def f() -> int:\n    let x: dict<str, dict<str, int>> = {"a": {"b": 1}}\n    return 0\n'
    ),
    "G10_param_annotation": "def g(d: dict<str, int>) -> int:\n    return 0\n",
    "G11_empty_then_return": "def f() -> dict<str, int>:\n    let m: dict<str, int> = {}\n    return m\n",
    "G12_empty_untyped": "def f() -> int:\n    let d = {}\n    return 0\n",
    "G13_scalar_alias_dict": (
        "type ID = str\n\ndef f() -> int:\n" '    let x: dict<ID, int> = {"a": 1}\n    return 0\n'
    ),
}

# 修复前这一栏的静默形 = 缺陷清单；修复后必须全部转红。
MUST_RED = tuple(k for k in SRC if k.startswith("D"))
# `CTRL_*` 是"必须红"的读取通道对照，绝不能混进"该绿"栏 ——
# 初版把它们拼进 MUST_GREEN，于是 before 档报出 `green_now_red=[CTRL…]`：
# 尺子把"通道正常"读成了"我该绿的东西红了"，rc=1 红在自己身上（tag=a1 那份证据就是它）。
CTRL_RED = ("CTRL_scalar_mismatch", "CTRL_list_elem_wrong")
MUST_GREEN = tuple(k for k in SRC if k.startswith("G"))
# 修复前"该红却静默"是预期事件；用这张表把两栏的期望写成机器可读，而不是靠人记。
EXPECT_SILENT_BEFORE = MUST_RED


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "a1"
    phase = "after" if "--after" in sys.argv else "before"
    base = HERE / "logs" / "r14_dict_probe_a1.json"
    before = json.loads(base.read_text(encoding="utf-8")) if base.exists() else {}
    rows, flipped, crashed = {}, [], []
    for key, src in SRC.items():
        try:
            o = g.execute({"op": "typecheck", "src": src})
        except Exception as exc:
            crashed.append(f"{key}:{type(exc).__name__}")
            rows[key] = {"stage": "crash", "n": -1, "errs": [f"{type(exc).__name__}: {exc}"]}
            print(f"CRASH {key:24s} {type(exc).__name__}: {str(exc)[:70]}")
            continue
        errs = [e for e in o.get("errors", []) if e.strip()]
        rows[key] = {"stage": o.get("stage"), "n": len(errs), "errs": errs}
        b = before.get(key, {}).get("n")
        if b is not None and b != len(errs):
            flipped.append(f"{key}:{b}->{len(errs)}")
        mark = "RED " if errs else "ok  "
        print(
            f"{mark}{key:24s} {o.get('stage'):6s} n={len(errs)} :: {' | '.join(e.strip()[:70] for e in errs[:2])}"
        )
    silent = [k for k in MUST_RED if not rows[k]["n"] or rows[k]["stage"] == "crash"]
    broke = [k for k in MUST_GREEN if rows[k]["n"]]
    unparsed = [k for k, v in rows.items() if v["stage"] == "parse"]
    ctrl_silent = [k for k in CTRL_RED if not rows[k]["n"]]
    out = HERE / "logs" / f"r14_dict_probe_{tag}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if phase == "before":
        # 开工基线：D 栏**应当**大面积静默 —— 静默数就是这一轮要修的面；
        # 但 CTRL 栏若静默说明我的观测口径坏了，那份数一律不作数。
        print(
            f"CONCLUSION r14_dict_probe phase=before tag={tag} cases={len(rows)} "
            f"defect_silent={len(silent)}/{len(EXPECT_SILENT_BEFORE)} silent_ids={silent} "
            f"read_channel_broken={ctrl_silent} green_now_red={broke} crashed={crashed} "
            f"parse_failures={unparsed} out={out.name}"
        )
        return 1 if (ctrl_silent or broke or crashed or unparsed) else 0
    print(
        f"CONCLUSION r14_dict_probe phase=after tag={tag} cases={len(rows)} "
        f"must_be_red_but_silent={silent} must_stay_green_now_red={broke} "
        f"read_channel_broken={ctrl_silent} flipped_vs_before={len(flipped)} "
        f"flipped_ids={flipped} crashed={crashed} parse_failures={unparsed} out={out.name}"
    )
    return 1 if (silent or broke or crashed or unparsed or ctrl_silent) else 0


if __name__ == "__main__":
    raise SystemExit(main())
