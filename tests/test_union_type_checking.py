"""增强联合类型（UnionType）的类型检查测试。

验证 Cypy 现在能保留联合类型的成员信息，并在 let 声明与函数返回处
对值做成员校验：匹配任一成员即合法，否则报错。代码生成仍降级为 object。

另外覆盖 Type.__eq__ 的联合成员比较（2026-Q3 审计 T0r61.2.2 缺陷 06）：
Union/Optional 都被编码成 Type('object', union_members=[...])，成员列表不参与
__eq__ 时 Optional[int] == Optional[str] == object == Any 全部成立。
"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import Type, TypeChecker


def _check(source: str) -> TypeChecker:
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    tc = TypeChecker()
    tc.check(ast)
    return tc


def _type_of(annotation_src: str) -> Type:
    """走真实构造点（type_checker 的 UnionType / GenericType 分支）拿到 Type。"""
    fn = Parser(Lexer(f"def f(x: {annotation_src}):\n    return 0\n").tokenize()).parse().body[0]
    return TypeChecker()._get_type_from_node(fn.params[0].type_annotation)


class TestUnionLetValid:
    """联合类型 let 声明中的合法赋值不应报错"""

    def test_int_or_str_with_int(self):
        tc = _check("def test():\n    let x: int | str = 5\n    return x\n")
        assert tc.errors == [], tc.errors

    def test_int_or_str_with_str(self):
        tc = _check('def test():\n    let x: int | str = "hi"\n    return x\n')
        assert tc.errors == [], tc.errors

    def test_int_or_float_or_str_with_float(self):
        tc = _check("def test():\n    let x: int | float | str = 1.5\n    return x\n")
        assert tc.errors == [], tc.errors

    def test_int_or_none_with_none(self):
        tc = _check("def test():\n    let x: int | None = None\n    return x\n")
        assert tc.errors == [], tc.errors

    def test_union_param(self):
        tc = _check("def f(x: int | str) -> None:\n    pass\n")
        assert tc.errors == [], tc.errors


class TestUnionLetInvalid:
    """联合类型 let 声明中的非法赋值应报错"""

    def test_int_or_str_with_float_rejected(self):
        tc = _check("def test():\n    let x: int | str = 5.0\n    return x\n")
        assert len(tc.errors) > 0, "float 不在 int | str 中，应报错"
        assert "Type mismatch" in tc.errors[0]

    def test_int_or_none_with_str_rejected(self):
        tc = _check('def test():\n    let x: int | None = "no"\n    return x\n')
        assert len(tc.errors) > 0, "str 不在 int | None 中，应报错"


class TestUnionReturnValid:
    """联合返回类型中的合法返回不应报错"""

    def test_return_int(self):
        tc = _check("def f() -> int | str:\n    return 5\n")
        assert tc.errors == [], tc.errors

    def test_return_str(self):
        tc = _check('def f() -> int | str:\n    return "x"\n')
        assert tc.errors == [], tc.errors

    def test_return_none_for_optional(self):
        tc = _check("def f() -> int | None:\n    return None\n")
        assert tc.errors == [], tc.errors


class TestUnionReturnInvalid:
    """联合返回类型中的非法返回应报错"""

    def test_return_float_rejected(self):
        tc = _check("def f() -> int | str:\n    return 5.0\n")
        assert len(tc.errors) > 0, "float 不在 int | str 返回类型中，应报错"
        assert "Return type mismatch" in tc.errors[0]


class TestSquareBracketUnion:
    """方括号 union 标注（typing 风格）同样参与成员校验"""

    def test_optional_int_valid(self):
        tc = _check("def test():\n    let x: Optional[int] = 5\n    return x\n")
        assert tc.errors == [], tc.errors

    def test_optional_int_invalid(self):
        tc = _check('def test():\n    let x: Optional[int] = "no"\n    return x\n')
        assert len(tc.errors) > 0, "str 不在 Optional[int] 中，应报错"

    def test_union_square_valid(self):
        tc = _check("def test():\n    let x: Union[int, str] = 5\n    return x\n")
        assert tc.errors == [], tc.errors

    def test_union_square_invalid(self):
        tc = _check("def test():\n    let x: Union[int, str] = 5.0\n    return x\n")
        assert len(tc.errors) > 0, "float 不在 Union[int, str] 中，应报错"


class TestTypeEquality:
    """Type.__eq__ 必须比较 union_members（缺陷 06）。"""

    def test_different_optional_members_are_not_equal(self):
        assert _type_of("Optional[int]") != _type_of("Optional[str]")

    def test_union_is_not_equal_to_optional(self):
        assert _type_of("Union[int, str]") != _type_of("Optional[int]")

    def test_union_is_not_equal_to_plain_object_or_any(self):
        # 三者 name 都是 'object'，只有成员列表能把它们区分开
        assert _type_of("Optional[int]") != _type_of("object")
        assert _type_of("Optional[int]") != _type_of("Any")
        assert _type_of("int | None") != _type_of("object")

    def test_same_members_stay_equal(self):
        assert _type_of("Optional[int]") == _type_of("Optional[int]")
        assert _type_of("Union[int, str]") == _type_of("Union[int, str]")
        assert _type_of("int | str") == _type_of("Union[int, str]")

    def test_non_union_behaviour_unchanged(self):
        assert _type_of("int") == _type_of("int")
        assert _type_of("int") != _type_of("str")
        assert _type_of("Optional[int]") != _type_of("int")
        assert _type_of("list[int]") == _type_of("list[int]")
        assert _type_of("list[int]") != _type_of("list[str]")

    def test_type_is_explicitly_unhashable(self):
        # 定义 __eq__ 而不定义 __hash__：显式写出，避免出现与 __eq__ 不一致的 __hash__
        assert Type.__hash__ is None
        with pytest.raises(TypeError):
            {hash(_type_of("Optional[int]"))}

    def test_eq_fix_moves_no_end_to_end_diagnostics(self):
        """钉桩：__eq__ 修复本身不改变端到端诊断。

        Optional[int] 赋给 Optional[str] 仍然不报错，这是另一个缺陷：
        type_checker.py:669-671 对 name in ('object','Any') 的声明无条件接受赋值
        （union_members 分支在它之后）。留给后续单元处理。
        """
        tc = _check("def f():\n    let a: Optional[int] = 1\n"
                    "    let b: Optional[str] = a\n    return b\n")
        assert tc.errors == [], tc.errors
        # 真正的成员校验仍然生效：非成员类型会报错
        bad = _check('def f():\n    let x: Optional[int] = "no"\n    return x\n')
        assert any("Type mismatch" in e for e in bad.errors), bad.errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
