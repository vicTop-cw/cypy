import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestMetaBlock(unittest.TestCase):
    def test_meta_block_with_duck(self):
        """测试 meta 块中的 duck 约束定义"""
        source = "meta:\n    duck Number:\n        a + b -> Self\n        a - b -> Self\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # meta块不生成运行时代码，但应该能正确解析
        self.assertIsNotNone(ast)

    def test_meta_block_with_duck_reference(self):
        """测试 meta 块中的 duck 引用约束（替代旧 subtype）"""
        source = "meta:\n    duck Animal:\n        name: str\n\n    duck Dog:\n        Animal\n        bark(self) -> str\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)

    def test_meta_block_with_duck_method(self):
        """测试 meta 块中的 duck 方法约束（替代旧 dispatch）"""
        source = "meta:\n    duck Shape:\n        area(self) -> float\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)

    def test_meta_block_multiple_items(self):
        """测试 meta 块包含多个 duck 定义"""
        source = "meta:\n    duck Number:\n        a + b -> Self\n\n    duck Animal:\n        name: str\n\n    duck Greeter:\n        greet(self) -> str\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)


class TestMetaASTNodes(unittest.TestCase):
    def test_meta_block_structure(self):
        """测试 meta 块结构解析"""
        source = "meta:\n    duck Number:\n        a + b -> Self\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        # 检查meta块是否被正确解析
        meta_nodes = [stmt for stmt in ast.body if hasattr(stmt, 'kind') and stmt.kind == 'MetaBlock']
        self.assertEqual(len(meta_nodes), 1)


if __name__ == "__main__":
    unittest.main()
