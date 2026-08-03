"""测试构建块代码生成功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


def _get_generator(source: str) -> CythonGenerator:
    """获取代码生成器并生成代码"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    generator.generate(ast)
    return generator


class TestBuildBlockCodeGen:
    """测试构建块代码生成"""

    def test_build_assign_block(self):
        """测试赋值构建块代码生成"""
        source = """
x =:
    y = 42
    y * 2
"""
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        # 验证代码生成
        assert 'x' in result

    def test_build_call_block(self):
        """测试调用构建块代码生成"""
        source = """
result ~:
    a = 10
    b = 20
    a + b
"""
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        # 验证代码生成
        assert 'result' in result

    def test_build_gen_block(self):
        """测试生成器构建块代码生成"""
        source = """
items *:
    i = 1
    i
"""
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        # 验证代码生成
        assert 'items' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
