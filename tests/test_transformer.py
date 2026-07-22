import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.transformer.struct_transformer import StructTransformer
from cypyc.transformer.enum_transformer import EnumTransformer
from cypyc.transformer.defer_transformer import DeferTransformer


class TestStructTransformer(unittest.TestCase):
    def test_transform_struct(self):
        source = "struct Point:\n    x: int\n    y: int\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        transformer = StructTransformer()
        result = transformer.transform(ast)

        self.assertEqual(len(transformer.structs), 1)
        self.assertEqual(transformer.structs[0].name, "Point")


class TestEnumTransformer(unittest.TestCase):
    def test_transform_enum(self):
        source = "enum Color:\n    RED\n    GREEN\n    BLUE\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        transformer = EnumTransformer()
        result = transformer.transform(ast)

        self.assertEqual(len(transformer.enums), 1)
        self.assertEqual(transformer.enums[0].name, "Color")


class TestDeferTransformer(unittest.TestCase):
    def test_transform_defer(self):
        source = "def foo():\n    defer:\n        print('cleanup')\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        transformer = DeferTransformer()
        result = transformer.transform(ast)

        self.assertEqual(len(transformer.defer_blocks), 1)


if __name__ == "__main__":
    unittest.main()
