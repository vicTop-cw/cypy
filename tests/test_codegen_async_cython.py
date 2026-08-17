"""测试 async/await 在 CythonGenerator 中的代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator
import unittest


class TestCodegenAsync(unittest.TestCase):

    def _generate(self, source: str) -> str:
        tokens = list(Lexer(source).tokenize())
        ast = Parser(tokens).parse()
        gen = CythonGenerator()
        return gen.generate(ast)

    def test_async_func_generates_async_def(self):
        """测试 async 函数生成 async def"""
        code = self._generate("async def fetch():\n    return 42")
        self.assertIn("async def fetch():", code)

    def test_async_func_with_params(self):
        """测试带参数的 async 函数"""
        code = self._generate("async def fetch(url: str) -> str:\n    return url")
        self.assertIn("async def fetch(url):", code)

    def test_await_expr_codegen(self):
        """测试 await 表达式的代码生成"""
        code = self._generate("async def fetch():\n    result = await get_data()\n    return result")
        self.assertIn("await get_data()", code)

    def test_async_with_multiple_await(self):
        """测试多个 await 表达式"""
        source = """async def process():
    a = await task1()
    b = await task2(a)
    return a + b"""
        code = self._generate(source)
        self.assertIn("await task1()", code)
        self.assertIn("await task2(a)", code)

    def test_async_nested(self):
        """测试嵌套 async 函数"""
        source = """async def outer():
    async def inner():
        return 42
    return await inner()"""
        code = self._generate(source)
        self.assertIn("async def outer():", code)
        self.assertIn("async def inner():", code)
        self.assertIn("await inner()", code)

    def test_sync_func_not_async(self):
        """测试普通函数不生成 async def"""
        code = self._generate("def normal():\n    return 42")
        self.assertIn("def normal():", code)
        self.assertNotIn("async def normal", code)

    def test_await_in_expr_to_str(self):
        """测试 await 在表达式上下文中"""
        source = """async def fetch():
    print(await get_data())"""
        code = self._generate(source)
        self.assertIn("await get_data()", code)


if __name__ == "__main__":
    unittest.main()
