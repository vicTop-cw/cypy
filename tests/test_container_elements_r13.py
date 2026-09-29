"""R13 回归锁：容器元素位判定 + 别名展开到底（SYNTAX/02「容器元素位判定」，BUG-137/138/139）。

钉住五件产品事实：
1. 同名容器不再是「名字对上就放行」——逐位要判，定长容器还要判个数（BUG-137）；
2. 该放行的四类占位（值侧无元素信息 / object / None / 声明侧 object）必须继续 0 诊断，
   否则这条收紧就是在拿既有语料换 false positive；
3. 赋值位与返回位共用同一份判定 ⇒ 两半都要有正反例（只钉一边，另一边删掉也不会红）；
4. 别名右端里出现的**其它别名**要展开到底（BUG-138 是一起假阳性：正确程序被拒），
   自指别名必须停在原地而不是 RecursionError；
5. 联合形态的别名要真的代入（BUG-139：过去整条不认 ⇒ 任意值放行）。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

ROOT = Path(__file__).resolve().parents[1]

RESULT_ALIAS = "type Result<T> = tuple<bool, T>\n\n"
PAIR_ALIAS = "type Pair<T> = tuple<T, T>\n\n"
SCALAR_DICT = 'def f() -> int:\n    let x: dict<str, int> = {"a": "b"}\n    return 0\n'


def errors(src: str) -> list[str]:
    tc = TypeChecker()
    tc.check(Parser(list(Lexer(src).tokenize())).parse())
    return list(tc.errors)


def element_diags(src: str) -> list[str]:
    return [e for e in errors(src) if "element" in e.lower()]


# —— 规则 1：定长容器的个数与逐位（BUG-137 正身）——


def test_tuple_second_element_mismatch_is_reported():
    diags = element_diags(
        'def f() -> int:\n    let bad: tuple<bool, int> = (True, "x")\n    return 0\n'
    )
    assert len(diags) == 1, diags
    assert "Element 2 type mismatch: expected int, got str" in diags[0]
    assert diags[0].endswith("at 2:9"), diags[0]


def test_tuple_first_element_mismatch_is_reported():
    diags = element_diags("def f() -> int:\n    let bad: tuple<bool, int> = (1, 2)\n    return 0\n")
    assert len(diags) == 1, diags
    assert "Element 1 type mismatch: expected bool, got int" in diags[0]


def test_tuple_arity_mismatch_is_reported():
    diags = element_diags("def f() -> int:\n    let bad: tuple<int, int> = (1,)\n    return 0\n")
    assert len(diags) == 1, diags
    assert "Tuple element count mismatch: expected 2, got 1" in diags[0]


def test_tuple_matching_literal_stays_clean():
    assert errors("def f() -> int:\n    let ok: tuple<bool, int> = (True, 2)\n    return 0\n") == []


# —— 规则 2：变长容器与嵌套 ——


def test_list_element_mismatch_is_reported():
    assert element_diags('def f() -> int:\n    let bad: list<int> = ["s"]\n    return 0\n')


def test_nested_list_element_mismatch_is_reported():
    diags = element_diags('def f() -> int:\n    let bad: list<list<int>> = [["s"]]\n    return 0\n')
    assert len(diags) == 1, diags
    assert "expected int, got str" in diags[0]


def test_nested_list_matching_literal_stays_clean():
    assert (
        errors("def f() -> int:\n    let ok: list<list<int>> = [[1], [2, 3]]\n    return 0\n") == []
    )


# —— 规则 3：数值加宽单向 ——


def test_numeric_widening_inside_container_is_allowed():
    assert errors("def f() -> int:\n    let ok: list<float> = [1, 2]\n    return 0\n") == []


def test_numeric_narrowing_inside_container_is_reported():
    assert element_diags("def f() -> int:\n    let bad: list<int> = [1.5]\n    return 0\n")


# —— 规则 4：四类占位必须继续放行（收紧不许造出 false positive）——


@pytest.mark.parametrize(
    "src",
    [
        "def f() -> int:\n    let x: list<int> = list()\n    return 0\n",
        'def f() -> int:\n    let x: list<list<int>> = [["s"], [1]]\n    return 0\n',
        "def f() -> int:\n    let x: tuple<bool, int> = (True, None)\n    return 0\n",
        'def f() -> int:\n    let x: list<int> = [1, "s"]\n    return 0\n',
        "def f() -> int:\n    let x: set<int> = set()\n    return 0\n",
        'def f() -> int:\n    let x: list<object> = ["s"]\n    return 0\n',
    ],
)
def test_placeholder_forms_stay_clean(src: str):
    assert errors(src) == [], src


# —— 规则 5：保守集（刻意的漏报，形状要钉住不许漂移成误报）——


def test_user_type_elements_are_lenient():
    assert (
        errors(
            "class Dog:\n    n: str\n\ndef f() -> int:\n    let x: list<Dog> = [Dog()]\n    return 0\n"
        )
        == []
    )


def test_trait_element_is_lenient_by_design():
    # `list<Speak> = [Dog()]` 至今静默：两侧都不是闭合标量名 ⇒ 规则 5 放行。
    # 这条断言不是"证明它对了"，而是钉住"我们知道这里漏判"，扩面时它会先红。
    assert (
        errors(
            "trait Speak:\n    def say(self) -> int\n\n"
            "class Dog:\n    n: str\n\ndef f() -> int:\n"
            "    let x: list<Speak> = [Dog()]\n    return 0\n"
        )
        == []
    )


def test_closed_scalar_set_matches_the_manual():
    """规则 5 的闭合标量表：手册列的名与代码里的元组必须逐项相等（双向）。"""
    doc = (ROOT / "SYNTAX" / "02-type-annotations.md").read_text(encoding="utf-8")
    hit = re.search(r"闭合标量表\s*(?:\n\s*)?（([^）]+)）", doc)
    assert hit, "手册里找不到「闭合标量表（…）」那一格 ⇒ 规则 5 的措辞漂了，代码这张表失去依据"
    listed = set(re.findall(r"`([^`]+)`", hit.group(1)))
    assert listed == set(
        TypeChecker._SCALAR_ELEMENT_NAMES
    ), f"手册列 {sorted(listed)} vs 代码 {sorted(TypeChecker._SCALAR_ELEMENT_NAMES)}"


# —— 规则 6（R13 版）：dict 键值位曾明确不在本节范围 —— R14 起该豁免作废，断言反向 ——


def test_dict_value_slot_is_required_since_r14():
    """R13 当时钉的是「零诊断」；R14 补上字典字面量推断件后**这条豁免作废**（SYNTAX/02 R14 节规则 5）。

    这里按"只许收紧"改写：同一条形现在必须有 1 条诊断，且文案点名 dict value。
    反向（把断言放宽回 0）不允许 —— 那会静默放过 BUG-141。
    """
    diags = [e for e in errors(SCALAR_DICT) if "dict value" in e.lower()]
    assert len(diags) == 1, diags
    assert "Dict value type mismatch: expected int, got str" in diags[0]


# —— 返回位与赋值位共用一份判定 ——


def test_return_position_reports_element():
    diags = element_diags('def f() -> tuple<bool, int>:\n    return (True, "x")\n')
    assert len(diags) == 1, diags
    assert "Return element 2 type mismatch" in diags[0]


def test_return_position_reports_narrowing():
    assert element_diags("def f() -> list<int>:\n    return [1.5]\n")


def test_return_position_valid_container_stays_clean():
    assert errors("def f() -> list<int>:\n    return [1, 2]\n") == []


def test_both_call_sites_share_one_implementation():
    src = inspect.getsource(TypeChecker)
    let_site = "self._check_container_elements(declared_type, value_type, node)"
    ret_site = "self._check_container_elements(\n                        self.current_function_return_type, value_type, node, 'Return ')"
    assert src.count(let_site) == 1, "赋值位的调用点漂了"
    assert src.count(ret_site) == 1, "返回位的调用点漂了（改成一行写也要同步这条针）"


# —— 别名展开到底（BUG-138）——


def test_generic_alias_substitutes_before_comparing():
    diags = element_diags(
        RESULT_ALIAS + 'def f() -> int:\n    let bad: Result<int> = (True, "x")\n    return 0\n'
    )
    assert len(diags) == 1, diags
    assert "Element 2 type mismatch: expected int, got str" in diags[0]


def test_generic_alias_valid_literal_stays_clean():
    assert (
        errors(
            RESULT_ALIAS + "def f() -> int:\n    let ok: Result<int> = (True, 2)\n    return 0\n"
        )
        == []
    )


def test_nested_alias_expands_fully_for_valid_program():
    src = (
        PAIR_ALIAS + "type Triple<T> = Pair<Pair<T>>\n\n"
        "def f() -> int:\n    let ok: Triple<int> = ((1, 2), (3, 4))\n    return 0\n"
    )
    assert errors(src) == [], "别名套别名没展开会把正确程序判成类型不符（BUG-138 的假阳性正身）"


def test_nested_alias_reports_the_inner_element():
    src = (
        PAIR_ALIAS + "type Triple<T> = Pair<Pair<T>>\n\n"
        'def f() -> int:\n    let bad: Triple<int> = ((1, 2), ("x", 4))\n    return 0\n'
    )
    diags = element_diags(src)
    assert len(diags) == 1, diags
    assert "Element 2 type mismatch: expected int, got str" in diags[0]


def test_scalar_alias_inside_alias_target_expands():
    src = (
        "type ID = int\ntype Row = tuple<ID, int>\n\n"
        'def f() -> int:\n    let bad: Row = ("a", 1)\n    return 0\n'
    )
    diags = element_diags(src)
    assert len(diags) == 1, diags
    assert "expected int, got str" in diags[0]


def test_self_referential_alias_does_not_recurse():
    src = "type Loop<T> = Loop<T>\n\ndef f() -> int:\n    let x: Loop<int> = 1\n    return 0\n"
    try:
        diags = errors(src)
    except RecursionError as exc:  # pragma: no cover - 只在守卫失效时到这儿
        pytest.fail(f"自指别名把分析器打成 RecursionError：{exc}")
    assert any("Type mismatch: expected Loop[int], got int" in d for d in diags), diags


def test_alias_arity_diagnostic_is_not_duplicated():
    src = (
        RESULT_ALIAS + "def f() -> int:\n    let bad: Result<int, int> = (True, 1)\n    return 0\n"
    )
    diags = [e for e in errors(src) if "generic parameter" in e]
    assert len(diags) == 1, diags


# —— 联合形态别名要代入（BUG-139）——


def test_union_shaped_alias_rejects_foreign_value():
    src = (
        'type Maybe<T> = T | None\n\ndef f() -> int:\n    let bad: Maybe<int> = "s"\n    return 0\n'
    )
    diags = errors(src)
    assert len(diags) == 1, diags
    assert "Union[int, None]" in diags[0] and "got str" in diags[0]


@pytest.mark.parametrize("literal", ["None", "3"])
def test_union_shaped_alias_accepts_its_members(literal: str):
    src = (
        f"type Maybe<T> = T | None\n\ndef f() -> int:\n"
        f"    let ok: Maybe<int> = {literal}\n    return 0\n"
    )
    assert errors(src) == [], src


def test_union_of_containers_accepts_matching_member():
    src = (
        "type ListOrSet<T> = list<T> | set<T>\n\ndef f() -> int:\n"
        "    let x: ListOrSet<int> = [1, 2]\n    return 0\n"
    )
    assert errors(src) == []


def test_union_member_element_positions_are_still_open():
    # `ListOrSet<int> = ["s"]` 仍静默：`_type_in_union` 只比成员 `.name`。
    # 钉成断言而不是"没人注意到"，扩面那天这条会先红。
    src = (
        "type ListOrSet<T> = list<T> | set<T>\n\ndef f() -> int:\n"
        '    let bad: ListOrSet<int> = ["s"]\n    return 0\n'
    )
    assert errors(src) == []


# —— 判定与记帐的边界 ——


def test_dict_is_now_in_the_checked_container_list():
    """R13 钉的是「dict 不在集合里」，R14 起断言反向：它**在**。

    两条锁的函数名一并改成与断言一致的说法 —— 名字与断言互相矛盾是文档缺陷，
    留着旧名不是「兼容」，只是把矛盾传给下一个读代码的人。
    """
    assert "dict" in TypeChecker._ELEMENT_CHECKED_CONTAINERS
    assert "tuple" in TypeChecker._ELEMENT_CHECKED_CONTAINERS


def test_same_fact_is_not_billed_twice():
    src = 'def f() -> int:\n    let bad: tuple<bool, int> = (True, "x")\n    return 0\n'
    assert len(element_diags(src)) == 1
    tc = TypeChecker()
    ast = Parser(list(Lexer(src).tokenize())).parse()
    tc.check(ast)
    tc.check(ast)  # 同一 AST 再访一遍：重复诊断必须去重
    assert len([e for e in tc.errors if "Element 2" in e]) == 1, tc.errors
