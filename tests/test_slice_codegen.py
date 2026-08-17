"""测试切片语法和新增操作符的代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator
import unittest


class TestSliceCodegen(unittest.TestCase):

    def _generate(self, source: str) -> str:
        tokens = list(Lexer(source).tokenize())
        ast = Parser(tokens).parse()
        gen = CythonGenerator()
        return gen.generate(ast)

    def test_slice_middle(self):
        code = self._generate("x = items[1:5]")
        self.assertIn("items[1:5]", code)

    def test_slice_start_only(self):
        code = self._generate("x = items[2:]")
        self.assertIn("items[2:]", code)

    def test_slice_end_only(self):
        code = self._generate("x = items[:3]")
        self.assertIn("items[:3]", code)

    def test_slice_full(self):
        code = self._generate("x = items[:]")
        self.assertIn("items[:]", code)

    def test_slice_with_step(self):
        code = self._generate("x = items[::2]")
        self.assertIn("items[::2]", code)

    def test_slice_full_with_step(self):
        code = self._generate("x = items[1:10:2]")
        self.assertIn("items[1:10:2]", code)

    def test_index_access(self):
        code = self._generate("x = items[0]")
        self.assertIn("items[0]", code)

    def test_not_in_codegen(self):
        code = self._generate("x = a not in b")
        self.assertIn("a not in b", code)

    def test_not_is_codegen(self):
        code = self._generate("x = a not is b")
        # Cypy 的 "not is" 被规范化为 Python/Cython 标准的 "is not"
        self.assertIn("a is not b", code)

    def test_floor_div_codegen(self):
        code = self._generate("x = 7 // 2")
        self.assertIn("7 // 2", code)

    def test_floor_div_assign_codegen(self):
        code = self._generate("x //= 3")
        # 复合赋值被展开为 x = x // 3
        self.assertIn("x = x // 3", code)

    def test_mod_assign_codegen(self):
        code = self._generate("x %= 5")
        # 复合赋值被展开为 x = x % 5
        self.assertIn("x = x % 5", code)


if __name__ == "__main__":
    unittest.main()
