import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestMetaBlock(unittest.TestCase):
    def test_meta_block_with_constraint(self):
        source = "meta:\n    constraint Number = int | float\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # meta块不生成运行时代码，但应该能正确解析
        self.assertIsNotNone(ast)

    def test_meta_block_with_subtype(self):
        source = "struct Animal:\n    pass\n\nstruct Dog:\n    pass\n\nmeta:\n    subtype Dog <: Animal\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)

    def test_meta_block_with_dispatch(self):
        source = "struct Circle:\n    radius: float\n\nstruct Rectangle:\n    width: float\n    height: float\n\nmeta:\n    dispatch area(a: Circle) -> float\n    dispatch area(a: Rectangle) -> float\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)

    def test_meta_block_multiple_items(self):
        source = "meta:\n    constraint Number = int | float\n    subtype Dog <: Animal\n    dispatch greet(a: Dog) -> str\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIsNotNone(ast)


class TestMetaASTNodes(unittest.TestCase):
    def test_meta_block_structure(self):
        source = "meta:\n    constraint Number = int | float\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        # 检查meta块是否被正确解析
        meta_nodes = [stmt for stmt in ast.body if hasattr(stmt, 'kind') and stmt.kind == 'MetaBlock']
        self.assertEqual(len(meta_nodes), 1)


if __name__ == "__main__":
    unittest.main()