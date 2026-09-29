"""R11 回归锁：泛型类（SYNTAX/11「泛型类的判定口径」规则 1-5）。

钉住的五件产品事实，逐条都是本轮实测从"坏形态"翻过来的：
1. `class Box<T>:` 三种前缀（裸名 / `(Base)` / `extends Base`）此前一律 `Expected COLON, got LT`；
2. 定义侧参数表与 `struct` 共用 `_parse_type_param_list` ⇒ 空参数表的文案两处逐字相同；
3. 使用侧元数（注解位与调用位）共用 `_generic_arity_diagnostic` ⇒ 两条文案全仓只有一处产生；
4. 接收者的类型实参按声明顺序逐位代入成员/方法类型；裸名按擦除，**形式参数名 `T` 不得外泄成诊断**；
5. 产物类头擦除类型参数（`class Box:`），且泛型类的方法名不得以 `T` 进裸名表。

正例必配反例：只验"代入后不报错"的话，把成员类型退化成 `object` 也能全绿，那是假绿。
"""

from __future__ import annotations

import re

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ClassDef, Parser

BOX_INIT = """class Box<T>:
    def __init__(self, content: T):
        self.content = content

    def get(self) -> T:
        return self.content


def f() -> int:
    let b: Box<int> = Box<int>(42)
    return b.get()
"""
BOX_FIELD = ("class Box<T>:\n    content: T\n\n    def get(self) -> T:\n        return self.content\n\n")
PAIR_FIELD = ("class Pair<T, U>:\n    a: T\n    b: U\n\n    def first(self) -> T:\n        return self.a\n\n"
              "    def second(self) -> U:\n        return self.b\n\n")
WRAP_FIELD = ("struct Wrap<T>:\n    value: T\n\n    def get(self) -> T:\n        return self.value\n\n")
PLAIN = ("class Plain:\n    content: int\n\n    def get(self) -> int:\n        return self.content\n\n")


def _parse(src: str):
    return Parser(list(Lexer(src).tokenize())).parse()


def _check(src: str) -> list:
    tc = TypeChecker()
    tc.check(_parse(src))
    return tc.errors


def _check_tc(src: str) -> TypeChecker:
    tc = TypeChecker()
    tc.check(_parse(src))
    return tc


def _parse_error(src: str) -> str:
    """语法级硬拒：解析器 raise ValueError，取消息文本（与 omega_gate 的 parse 阶段同形状）。"""
    try:
        _parse(src)
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"预期解析被拒，实际通过：{src[:40]!r}")


def _gen(src: str) -> str:
    return CythonGenerator().generate(_parse(src))


def _first_classdef(src: str) -> ClassDef:
    return next(n for n in _parse(src).body if isinstance(n, ClassDef))


# —— 规则 1：定义侧三种前缀 ——
def test_generic_class_parses_three_prefix_forms():
    body = "    def get(self) -> T:\n        return self.c\n\n"
    for src, expect_bases in (("class Box<T>:\n" + body, False),
                              ("class Box<T> extends Base:\n" + body, True),
                              ("class Box<T>(Base):\n" + body, True)):
        node = _first_classdef(src)
        assert node.generic_params == ["T"], src
        assert bool(node.bases) is expect_bases, (src[:24], node.bases)


def test_generic_class_records_params_and_constraints():
    node = _first_classdef("class Num<T: int | float>:\n    v: T\n\n")
    assert node.generic_params == ["T"]
    assert set(node.generic_constraints) == {"T"}, node.generic_constraints
    two = _first_classdef(PAIR_FIELD)
    assert two.generic_params == ["T", "U"]
    # 非泛型类的默认值必须是空表/空字典，不能是 None（读取点按真值判断）
    plain = _first_classdef(PLAIN)
    assert plain.generic_params == [] and plain.generic_constraints == {}


# —— 规则 2：一份实现两处用（class 与 struct 的文案逐字相同）——
def test_empty_param_list_wording_is_shared_with_struct():
    cls_err = _parse_error("class Box<>:\n    def get(self) -> int:\n        return 0\n\n")
    struct_err = _parse_error("struct Box<>:\n    value: int\n\n")
    assert "Generic parameter list cannot be empty" in cls_err, cls_err
    assert "Generic parameter list cannot be empty" in struct_err, struct_err
    assert cls_err.split(" at ")[0] == struct_err.split(" at ")[0], (cls_err, struct_err)
    for e in (cls_err, struct_err):
        assert re.search(r"at \d+:\d+", e), e


def test_arity_wording_is_shared_between_annotation_and_callsite():
    callsite = _check(BOX_FIELD + "\ndef f() -> int:\n    let b: Box<int> = Box<int, str>(42)\n    return 0\n")
    ann = _check(BOX_FIELD + "\ndef f() -> int:\n    let b: Box<int, str> = Box<int>(42)\n    return 0\n")
    needle = "Type argument count mismatch: 'Box' declares 1 type parameter(s), got 2"
    assert any(needle in e for e in callsite), callsite
    assert any(needle in e for e in ann), ann
    # 元数诊断各只报一条：同一事实不得在两个读取点各写一遍账
    assert sum(needle in e for e in callsite) == 1, callsite
    assert sum(needle in e for e in ann) == 1, ann


def test_non_generic_class_rejects_type_arguments():
    errs = _check(PLAIN + "\ndef f() -> int:\n    let p: Plain<int> = Plain()\n    return 0\n")
    assert any("Type arguments on non-generic 'Plain': it declares no type parameter, got 1" in e
               for e in errs), errs


# —— 规则 3：裸名合法且按擦除 ——
def test_bare_generic_class_use_is_erased_not_diagnosed():
    src = BOX_FIELD + "\ndef f() -> int:\n    let b: Box = Box(1)\n    return b.get()\n"
    assert _check(src) == [], _check(src)


# —— 规则 4：代入按声明顺序逐位（正例 + 必然红的反例成对）——
def test_receiver_substitution_types_fields_and_methods():
    ok = BOX_FIELD + '\ndef f() -> str:\n    let b: Box<str> = Box<str>("x")\n    return b.get()\n'
    assert _check(ok) == [], _check(ok)
    bad = BOX_FIELD + '\ndef f() -> int:\n    let b: Box<str> = Box<str>("x")\n    return b.get()\n'
    assert any("expected int, got str" in e for e in _check(bad)), _check(bad)
    field_bad = BOX_FIELD + "\ndef f() -> str:\n    let b: Box<int> = Box<int>(42)\n    return b.content\n"
    assert any("expected str, got int" in e for e in _check(field_bad)), _check(field_bad)
    # 两个类型参数时按位取：second() 是 U=str，不跟着 T=int 走
    pair_bad = PAIR_FIELD + "\ndef f() -> int:\n    let p: Pair<int, str> = Pair()\n    return p.second()\n"
    assert any("expected int, got str" in e for e in _check(pair_bad)), _check(pair_bad)
    pair_ok = PAIR_FIELD + "\ndef f() -> str:\n    let p: Pair<int, str> = Pair()\n    return p.second()\n"
    assert _check(pair_ok) == [], _check(pair_ok)


def test_formal_parameter_name_never_leaks_as_a_type():
    for src in (BOX_INIT,
                BOX_FIELD + "\ndef f() -> int:\n    let b: Box = Box(1)\n    return b.get()\n",
                BOX_FIELD + "\ndef f() -> int:\n    let b: Box<str> = Box<str>(\"x\")\n    return b.get()\n"):
        for e in _check(src):
            assert "got T" not in e and "expected T" not in e, (src[:24], e)


def test_manual_generic_class_example_is_clean():
    """SYNTAX/11:112-124 的范例（`__init__` 形态）必须两面全绿 —— 手册抄进编译器就得能用。"""
    assert _check(BOX_INIT) == [], _check(BOX_INIT)
    code = _gen(BOX_INIT)
    assert code.strip(), "范例不得产出空码"
    assert "class Box:" in code, code


def test_generic_class_method_name_is_not_registered_as_formal_type():
    """裸名表承载不了接收者代入 ⇒ 泛型类的方法名只能登记成未知，不能登记成 `T`。"""
    _check(BOX_FIELD + "\ndef f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get()\n")
    tc = _check_tc("class Box<T>:\n    content: T\n\n    def get(self) -> T:\n        return self.content\n\n"
                   "class Bag<T>:\n    items: T\n\n    def get(self) -> T:\n        return self.items\n\n")
    got = tc.type_map.get("get")
    assert got is not None and got.name != "T", got
    # 非泛型类不受该守卫影响：名字表仍按声明返回类型登记
    plain_tc = _check_tc(PLAIN)
    assert plain_tc.type_map["get"].name == "int", plain_tc.type_map["get"]


# —— 规则 5：产物必须擦除 ——
def test_codegen_erases_type_parameters_in_class_header():
    code = _gen(BOX_FIELD + "\ndef f() -> int:\n    let b: Box<int> = Box<int>(42)\n    return b.get()\n")
    assert "class Box:" in code
    for needle in ("Box<T>", "<int>", "-> T", "class Box <"):
        assert needle not in code, needle
    pair_code = _gen(PAIR_FIELD + "\ndef f() -> int:\n    return 0\n")
    assert "class Pair:" in pair_code and "Pair<T" not in pair_code
    # 对照：擦除不等于"没出码"—— 字段表仍要看得见（class 的成员在 .body 的 LetStmt）
    assert CythonGenerator().generate(_parse(BOX_FIELD)).strip()


def test_class_members_are_read_from_body_not_fields():
    """class 的成员是 `.body` 里的 LetStmt —— 读取点若按 struct 的 `.fields` 形状取，
    字段表会静默变空（R8 的教训：`ClassDef` 的实例属性只有 name/bases/body/is_cdef，
    加上本轮的 generic_params/generic_constraints）。"""
    node = _first_classdef(BOX_FIELD)
    assert not hasattr(node, "fields"), "ClassDef 不该有 .fields；有就是读取点自造的形状"
    assert any(getattr(c, "name", None) == "content" for c in node.body)
    gen = CythonGenerator()
    gen.generate(_parse(BOX_FIELD))
    assert gen._class_fields.get("Box") == ["content"], gen._class_fields


# —— struct 侧的对称半边：字段访问代入仍在（本轮把裸名的形式参数外泄也一并收掉）——
def test_struct_field_substitution_still_judges():
    ok = WRAP_FIELD + "\ndef f() -> int:\n    let w: Wrap<int> = Wrap(1)\n    return w.value\n"
    assert _check(ok) == [], _check(ok)
    bad = WRAP_FIELD + '\ndef f() -> str:\n    let w: Wrap<int> = Wrap(1)\n    return w.value\n'
    assert any("expected str, got int" in e for e in _check(bad)), _check(bad)
    bare = WRAP_FIELD + "\ndef f() -> int:\n    let w: Wrap = Wrap()\n    return w.value\n"
    assert _check(bare) == [], _check(bare)
