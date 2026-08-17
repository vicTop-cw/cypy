"""测试联合类型代码生成"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


def parse_and_generate(source: str) -> str:
    """解析源码并生成 Cython 代码"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    generator = CythonGenerator("test_module")
    return generator.generate(ast)


class TestUnionType:
    """测试联合类型声明"""

    def test_union_type_two_types(self):
        """测试两种类型的联合"""
        source = '''def main() -> None:
    let value: int | float = 42
    pass'''
        code = parse_and_generate(source)
        assert "object" in code
        # union 类型当前降级为 object（保 cdef 签名安全）

    def test_union_type_with_none(self):
        """测试带 None 的联合类型"""
        source = '''def main() -> None:
    let name: str | None = get_name()
    pass'''
        code = parse_and_generate(source)
        assert "object" in code

    def test_union_type_three_types(self):
        """测试三种类型的联合"""
        source = '''def main() -> None:
    let value: int | float | str = get_value()
    pass'''
        code = parse_and_generate(source)
        assert "object" in code


class TestUnionTypeInFunctions:
    """测试函数中的联合类型"""

    def test_union_type_parameter(self):
        """测试联合类型作为函数参数"""
        source = '''def process(input: str | int) -> str:
    return str(input)

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "def process(input):" in code

    def test_union_type_return(self):
        """测试联合类型作为返回值"""
        source = '''def find_user(user_id: int) -> str | None:
    if user_id > 0:
        return "Alice"
    return None

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "def find_user(user_id):" in code

    def test_union_type_both(self):
        """测试参数和返回值都是联合类型"""
        source = '''def convert(value: int | float) -> str | None:
    if value > 0:
        return str(value)
    return None

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "def convert(value):" in code


class TestUnionTypeWithIsinstance:
    """测试与 isinstance 配合使用"""

    def test_isinstance_narrowing(self):
        """测试 isinstance 类型收窄"""
        source = '''def handle(value: int | str) -> str:
    if isinstance(value, int):
        return str(value * 2)
    else:
        return value.upper()

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "isinstance" in code

    def test_multiple_isinstance(self):
        """测试多个 isinstance 检查"""
        source = '''def process(value: int | float | str) -> str:
    if isinstance(value, int):
        return f"int: {value}"
    elif isinstance(value, float):
        return f"float: {value}"
    else:
        return f"str: {value}"

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "isinstance" in code


class TestUnionTypeCodegen:
    """测试联合类型代码生成细节"""

    def test_union_type_comment(self):
        """测试生成的注释包含类型信息"""
        source = '''def main() -> None:
    let value: int | float = 42
    pass'''
        code = parse_and_generate(source)
        # union 类型当前降级为 object；类型信息仅在源码层面保留
        assert "value: object" in code

    def test_union_type_no_runtime_check(self):
        """测试联合类型降级为 object"""
        source = '''def main() -> None:
    let value: str | int = get_value()
    pass'''
        code = parse_and_generate(source)
        assert "value: object = get_value()" in code
        assert "object" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])