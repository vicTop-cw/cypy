import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestGenericTypes(unittest.TestCase):
    def test_generic_struct(self):
        source = "struct Pair<T, U>:\n    first: T\n    second: U\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef class Pair:", code)

    def test_generic_function(self):
        source = "def identity<T>(value: T) -> T:\n    return value\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("identity", code)

    def test_generic_type_usage(self):
        source = "def create_pair():\n    p: Pair<int, str>\n    return p\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # 泛型参数在 cdef class 签名中被擦除为基类 Pair
        self.assertIn("p: Pair", code)


class TestTraitImplementation(unittest.TestCase):
    def test_trait_definition(self):
        source = "trait Drawable:\n    def draw() -> None:\n        pass\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef class Drawable", code)
        self.assertIn("def draw(self):", code)

    def test_trait_with_multiple_methods(self):
        source = "trait Shape:\n    def area() -> float:\n        pass\n    def perimeter() -> float:\n        pass\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("def area(self) -> float:", code)
        self.assertIn("def perimeter(self) -> float:", code)


class TestImplBlock(unittest.TestCase):
    def test_impl_block(self):
        source = "struct Circle:\n    radius: float\n\ntrait Shape:\n    def area() -> float:\n        pass\n\nimpl Shape for Circle:\n    def area() -> float:\n        return 3.14159 * radius * radius\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("_Shape__Circle", code)
        self.assertIn("cpdef float area", code)


if __name__ == "__main__":
    unittest.main()
