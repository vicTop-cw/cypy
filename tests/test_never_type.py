import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestNeverType(unittest.TestCase):
    def test_never_return_type(self):
        """测试 Never 作为返回类型"""
        source = "def never(msg: str) -> Never:\n    panic(msg)\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("NoReturn", code)

    def test_never_type_in_function(self):
        """测试 Never 类型在函数中的使用"""
        source = "def panic(message: str) -> Never:\n    raise ValueError(message)\n\ndef fail() -> Never:\n    raise RuntimeError(\"failed\")\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("NoReturn", code)

    def test_never_type_annotation(self):
        """测试 Never 作为变量类型注解"""
        source = "def get_error() -> Never:\n    raise RuntimeError(\"error\")\n\nresult: Never = get_error()\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("NoReturn", code)


if __name__ == "__main__":
    unittest.main()