"""增强联合类型（UnionType）的类型检查测试。

验证 Cypy 现在能保留联合类型的成员信息，并在 let 声明与函数返回处
对值做成员校验：匹配任一成员即合法，否则报错。代码生成仍降级为 object。
"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker


def _check(source: str) -> TypeChecker:
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    tc = TypeChecker()
    tc.check(ast)
    return tc


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
