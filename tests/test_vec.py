"""测试 Vec 向量类型代码生成"""

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


class TestVecType:
    """测试 Vec 类型声明"""

    def test_vec_type_declaration(self):
        """测试 vec[T; N] 类型声明"""
        source = '''def main() -> None:
    let v: vec[int; 4] = vec![1, 2, 3, 4]
    pass'''
        code = parse_and_generate(source)
        assert "v: list = [1, 2, 3, 4]" in code

    def test_vec_float_type(self):
        """测试浮点向量类型"""
        source = '''def main() -> None:
    let v: vec[float; 3] = vec![1.0, 2.0, 3.0]
    pass'''
        code = parse_and_generate(source)
        assert "v: list = [1.0, 2.0, 3.0]" in code

    def test_vec_type_cython_mapping(self):
        """测试 Vec 类型映射到 list"""
        source = '''def main() -> None:
    let v: vec[int; 4] = vec![1, 2, 3, 4]
    pass'''
        code = parse_and_generate(source)
        assert "list" in code


class TestVecLiteral:
    """测试 Vec 字面量"""

    def test_vec_literal_explicit(self):
        """测试显式元素列表"""
        source = '''def main() -> None:
    let v = vec![1, 2, 3, 4]
    pass'''
        code = parse_and_generate(source)
        assert "[1, 2, 3, 4]" in code

    def test_vec_literal_repeat(self):
        """测试重复值形式"""
        source = '''def main() -> None:
    let v = vec![0; 5]
    pass'''
        code = parse_and_generate(source)
        assert "[0] * 5" in code or "[0, 0, 0, 0, 0]" in code

    def test_vec_literal_single_element(self):
        """测试单元素向量"""
        source = '''def main() -> None:
    let v = vec![42]
    pass'''
        code = parse_and_generate(source)
        assert "[42]" in code

    def test_vec_in_function(self):
        """测试在函数中使用向量"""
        source = '''def process(items: list) -> int:
    total = 0
    for x in items:
        total = total + x
    return total

def main() -> int:
    let v = vec![1, 2, 3, 4, 5]
    return process(v)'''
        code = parse_and_generate(source)
        assert "process(v)" in code


class TestVecIntegration:
    """测试 Vec 类型集成"""

    def test_vec_with_type_annotation(self):
        """测试带类型注解的向量"""
        source = '''def main() -> int:
    let nums: vec[int; 5] = vec![10, 20, 30, 40, 50]
    return nums[0]'''
        code = parse_and_generate(source)
        assert "nums: list = [10, 20, 30, 40, 50]" in code

    def test_vec_multiple_variables(self):
        """测试多个向量变量"""
        source = '''def main() -> None:
    let a = vec![1, 2]
    let b = vec![3, 4]
    let c = vec![5, 6]
    pass'''
        code = parse_and_generate(source)
        assert "a = [1, 2]" in code
        assert "b = [3, 4]" in code
        assert "c = [5, 6]" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])