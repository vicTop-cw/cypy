"""测试 global/nonlocal 语法解析和代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, GlobalStmt, NonlocalStmt
from cypyc.codegen.cython_generator import CythonGenerator
import unittest


class TestGlobalNonlocal(unittest.TestCase):

    def _parse(self, source: str):
        tokens = list(Lexer(source).tokenize())
        return Parser(tokens).parse()

    def _generate(self, source: str) -> str:
        ast = self._parse(source)
        gen = CythonGenerator()
        return gen.generate(ast)

    def test_global_keyword_exists(self):
        """测试 global 关键字被正确识别"""
        tokens = list(Lexer("global x").tokenize())
        self.assertEqual(tokens[0].type, 'GLOBAL')

    def test_nonlocal_keyword_exists(self):
        """测试 nonlocal 关键字被正确识别"""
        tokens = list(Lexer("nonlocal x").tokenize())
        self.assertEqual(tokens[0].type, 'NONLOCAL')

    def test_parse_global_single(self):
        """测试解析单个 global 声明"""
        ast = self._parse("def f():\n    global x")
        func_def = ast.body[0]
        global_stmt = func_def.body[0]
        self.assertIsInstance(global_stmt, GlobalStmt)
        self.assertEqual(global_stmt.names, ['x'])

    def test_parse_global_multiple(self):
        """测试解析多个 global 声明"""
        ast = self._parse("def f():\n    global x, y, z")
        func_def = ast.body[0]
        global_stmt = func_def.body[0]
        self.assertIsInstance(global_stmt, GlobalStmt)
        self.assertEqual(global_stmt.names, ['x', 'y', 'z'])

    def test_parse_nonlocal_single(self):
        """测试解析单个 nonlocal 声明"""
        ast = self._parse("def f():\n    nonlocal x")
        func_def = ast.body[0]
        nonlocal_stmt = func_def.body[0]
        self.assertIsInstance(nonlocal_stmt, NonlocalStmt)
        self.assertEqual(nonlocal_stmt.names, ['x'])

    def test_parse_nonlocal_multiple(self):
        """测试解析多个 nonlocal 声明"""
        ast = self._parse("def f():\n    nonlocal a, b")
        func_def = ast.body[0]
        nonlocal_stmt = func_def.body[0]
        self.assertIsInstance(nonlocal_stmt, NonlocalStmt)
        self.assertEqual(nonlocal_stmt.names, ['a', 'b'])

    def test_codegen_global(self):
        """测试 global 声明的代码生成"""
        code = self._generate("def f():\n    global counter\n    counter += 1")
        self.assertIn("global counter", code)

    def test_codegen_nonlocal(self):
        """测试 nonlocal 声明的代码生成"""
        code = self._generate("def f():\n    nonlocal x\n    x += 1")
        self.assertIn("nonlocal x", code)

    def test_codegen_global_multiple(self):
        """测试多个 global 声明的代码生成"""
        code = self._generate("def f():\n    global a, b, c")
        self.assertIn("global a, b, c", code)

    def test_global_in_class_method(self):
        """测试在类方法中使用 global"""
        source = """class MyClass:
    def method():
        global state
        state = 42"""
        ast = self._parse(source)
        code = self._generate(source)
        self.assertIn("global state", code)


if __name__ == "__main__":
    unittest.main()
