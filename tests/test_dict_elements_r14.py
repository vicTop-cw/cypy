"""R14 回归锁：字典字面量的类型推断与键值位判定（SYNTAX/02「字典字面量的键值位判定」，BUG-141）。

钉住六件产品事实：
1. 字面量必须推断出 `dict<K, V>` —— 过去这一层返回 None，声明侧的键值位**无从比较**（BUG-141 根因）；
2. `dict` 进入元素位判定集合：键位＝第 1 位、值位＝第 2 位，文案点名 key/value 而不是「element 1/2」；
3. 塌位是放行而不是拒绝：空字面量、混形键/值、`object`、用户类一律 0 诊断 ——
   这一栏同时是「不许顺手扩大拒绝面」的边界，缺了它这条收紧就会拿既有语料换 false positive；
4. 数值阶梯与标量位同一条：`dict<str, float>` 收 `{"a": 1}` 合法，`dict<str, int>` 收 `{"a": 1.5}` 要报；
5. 别名（`type Count = dict<str, int>`）与嵌套（`dict<str, list<int>>`、dict 套 dict）都走同一把尺；
6. 赋值位与返回位共用一份判定 ⇒ 两半都要有正反例，且同一个事实只记一笔。
"""

from __future__ import annotations

import re
from pathlib import Path

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

ROOT = Path(__file__).resolve().parents[1]
TC = "cypyc/analyzer/type_checker.py"
MANUAL = "SYNTAX/02-type-annotations.md"

VALUE_WRONG = 'def f() -> int:\n    let x: dict<str, int> = {"a": "b"}\n    return 0\n'
KEY_WRONG = 'def f() -> int:\n    let x: dict<int, str> = {"a": "b"}\n    return 0\n'
RETURN_WRONG = 'def f() -> dict<str, int>:\n    return {"a": "b"}\n'
CORRECT = 'def f() -> int:\n    let x: dict<str, int> = {"a": 1}\n    return 0\n'


def errors(src: str) -> list[str]:
    tc = TypeChecker()
    tc.check(Parser(list(Lexer(src).tokenize())).parse())
    return list(tc.errors)


def dict_diags(src: str) -> list[str]:
    return [e for e in errors(src) if "dict key" in e.lower() or "dict value" in e.lower()]


# —— 规则 2：键位与值位各自判定，文案点名 key/value ——


def test_dict_value_slot_mismatch_is_reported():
    diags = dict_diags(VALUE_WRONG)
    assert len(diags) == 1, diags
    assert "Dict value type mismatch: expected int, got str" in diags[0]


def test_dict_key_slot_mismatch_is_reported():
    diags = dict_diags(KEY_WRONG)
    assert len(diags) == 1, diags
    assert "Dict key type mismatch: expected int, got str" in diags[0]


def test_bool_key_under_str_is_reported():
    diags = dict_diags("def f() -> int:\n    let x: dict<str, int> = {True: 1}\n    return 0\n")
    assert len(diags) == 1, diags
    assert "Dict key type mismatch: expected str, got bool" in diags[0]


def test_diagnostic_carries_line_and_column():
    (diag,) = dict_diags(VALUE_WRONG)
    assert re.search(r" at \d+:\d+$", diag), diag


def test_return_position_reports_dict_value():
    diags = dict_diags(RETURN_WRONG)
    assert len(diags) == 1, diags
    assert "Return dict value type mismatch" in diags[0]


def test_return_position_accepts_correct_literal():
    assert errors('def f() -> dict<str, int>:\n    return {"a": 1}\n') == []


# —— 规则 1：字面量真的被推断出来（BUG-141 的根因面）——


def test_inferred_value_slot_reaches_a_later_assignment():
    # 打到调用面：函数体内的局部量在出作用域后不留 `type_map`，
    # 所以"推断件真的产出了类型"要由**下一个声明位**来见证 —— 而不是查内部表。
    src = 'def f() -> int:\n    let d = {"a": "b"}\n    let y: dict<str, int> = d\n    return 0\n'
    diags = dict_diags(src)
    assert len(diags) == 1, diags
    assert "Dict value type mismatch: expected int, got str" in diags[0]


def test_inference_is_not_merely_object():
    # 判别性对照：若字面量只塌成 object，第二个声明位会**放行**（object 一律不报）。
    # 这里期望报 ⇒ 推断出来的是 `dict<str, int>` 本身，不是"未知"。
    src = 'def f() -> int:\n    let d = {"a": 1}\n    let y: dict<str, str> = d\n    return 0\n'
    diags = dict_diags(src)
    assert len(diags) == 1, diags
    assert "expected str, got int" in diags[0]


def test_empty_literal_reaches_later_slot_as_placeholder():
    src = "def f() -> int:\n    let d = {}\n    let y: dict<str, int> = d\n    return 0\n"
    assert errors(src) == []


def test_slot_lub_takes_widest_numeric_in_literal():
    # `{"a": 1, "b": 2.5}` 的值位取阶梯最宽 ⇒ float；对着 `dict<str, int>` 就是收窄，要报
    diags = dict_diags(
        'def f() -> int:\n    let x: dict<str, int> = {"a": 1, "b": 2.5}\n    return 0\n'
    )
    assert len(diags) == 1, diags
    assert "expected int, got float" in diags[0]


def test_same_name_different_params_collapse_to_lenient():
    # 同名不同参（[1] 与 ["s"]）⇒ 参数位没有可靠答案 ⇒ 按占位放行，不猜
    assert (
        errors(
            'def f() -> int:\n    let x: dict<str, list<int>> = {"a": [1], "b": ["s"]}\n    return 0\n'
        )
        == []
    )


# —— 规则 3：塌位与保守集是**放行**，这一栏不许被收紧顺带扫红 ——


def test_empty_literal_is_lenient():
    assert errors("def f() -> int:\n    let x: dict<str, int> = {}\n    return 0\n") == []


def test_correct_literal_is_lenient():
    assert errors(CORRECT) == []


def test_heterogeneous_values_collapse_is_documented_miss():
    # 手册规则 6 的「有账漏报」：混形塌 object ⇒ 至今静默，钉成正向对照而不是当成已判
    assert (
        errors('def f() -> int:\n    let x: dict<str, int> = {"a": 1, "b": "c"}\n    return 0\n')
        == []
    )


def test_heterogeneous_keys_collapse_is_documented_miss():
    assert (
        errors('def f() -> int:\n    let x: dict<str, int> = {1: 1, "a": 2}\n    return 0\n') == []
    )


def test_numeric_widening_in_value_slot_is_lenient():
    assert errors('def f() -> int:\n    let x: dict<str, float> = {"a": 1}\n    return 0\n') == []


def test_bool_widening_in_value_slot_is_lenient():
    assert errors('def f() -> int:\n    let x: dict<str, int> = {"a": True}\n    return 0\n') == []


def test_scalar_narrowing_in_value_slot_is_reported():
    diags = dict_diags('def f() -> int:\n    let x: dict<str, int> = {"a": 1.5}\n    return 0\n')
    assert len(diags) == 1, diags
    assert "expected int, got float" in diags[0]


def test_user_type_value_is_lenient_by_design():
    src = (
        "class Dog:\n    n: str\n\ndef f() -> int:\n"
        '    let x: dict<str, Dog> = {"a": Dog()}\n    return 0\n'
    )
    assert errors(src) == []


def test_declared_object_dict_is_lenient():
    assert errors('def f() -> int:\n    let x: dict = {"a": "b"}\n    return 0\n') == []


# —— 规则 4：别名与嵌套走同一把尺 ——


def test_alias_shaped_dict_reports_value_slot():
    src = (
        "type Count = dict<str, int>\n\ndef f() -> int:\n"
        '    let bad: Count = {"a": "b"}\n    return 0\n'
    )
    diags = dict_diags(src)
    assert len(diags) == 1, diags


def test_nested_list_value_slot_is_reported():
    src = 'def f() -> int:\n    let x: dict<str, list<int>> = {"a": ["s"]}\n    return 0\n'
    diags = dict_diags(src)
    assert len(diags) == 1, diags


def test_nested_list_value_slot_accepts_correct():
    src = 'def f() -> int:\n    let x: dict<str, list<int>> = {"a": [1]}\n    return 0\n'
    assert errors(src) == []


def test_dict_of_dict_value_slot_is_reported():
    src = (
        'def f() -> int:\n    let x: dict<str, dict<str, int>> = {"a": {"b": "c"}}\n    return 0\n'
    )
    diags = dict_diags(src)
    assert len(diags) == 1, diags


def test_dict_of_dict_accepts_correct():
    src = 'def f() -> int:\n    let x: dict<str, dict<str, int>> = {"a": {"b": 1}}\n    return 0\n'
    assert errors(src) == []


# —— 规则 5/6：判定件只有一份，同一个事实不叠第二笔 ——


def test_both_call_sites_share_one_implementation():
    src = (ROOT / TC).read_text(encoding="utf-8")
    assert src.count("def _check_container_elements(") == 1
    assert src.count("def _visit_DictLiteral(") == 1
    assert src.count("def _slot_lub(") == 1
    assert src.count("self._slot_lub(") == 2


def test_same_fact_is_not_billed_twice():
    assert len(dict_diags(VALUE_WRONG)) == 1
    assert len([e for e in errors(VALUE_WRONG) if "Type mismatch" in e]) == 0


def test_dict_is_in_the_checked_container_set():
    assert "dict" in TypeChecker._ELEMENT_CHECKED_CONTAINERS


def test_manual_revokes_the_r13_dict_exemption():
    text = (ROOT / MANUAL).read_text(encoding="utf-8")
    assert "## 字典字面量的键值位判定（R14 补，2026-09-29）" in text
    assert "自本条起作废" in text
    # 手册里那句"锁死用例"指向的这份文件必须就是本文件（R13 曾把路径写成 tests/regression/…）
    assert "tests/test_dict_elements_r14.py" in text
    assert Path(__file__).name == "test_dict_elements_r14.py"
