import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


class TestPointerOperations(unittest.TestCase):
    def test_deref_expression(self):
        source = "def get_value(ptr: int*):\n    return &ptr\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("return ptr[0]", code)

    def test_pointer_declaration(self):
        source = "def allocate() -> int*:\n    ptr: int* = NULL\n    return ptr\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef int* ptr", code)


class TestEnumTranslation(unittest.TestCase):
    def test_enum_definition(self):
        source = "enum Color:\n    RED\n    GREEN\n    BLUE\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("class Color(IntEnum):", code)
        self.assertIn("RED", code)
        self.assertIn("GREEN", code)
        self.assertIn("BLUE", code)

    def test_enum_with_values(self):
        source = "enum Status:\n    OK = 0\n    ERROR = 1\n    WARNING = 2\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("OK = 0", code)
        self.assertIn("ERROR = 1", code)


class TestLetValTranslation(unittest.TestCase):
    def test_val_immutable(self):
        source = "def func():\n    val x: int = 42\n    return x\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef int x = 42", code)

    def test_var_mutable(self):
        source = "def func():\n    var x: int = 10\n    x = x + 1\n    return x\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef int x = 10", code)
        self.assertIn("x = x + 1", code)


class TestPipelineOperator(unittest.TestCase):
    def test_pipeline_operator(self):
        source = "def process():\n    result = 42 |> double |> square\n    return result\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("square(double(42))", code)


class TestStructTranslation(unittest.TestCase):
    def test_struct_definition(self):
        source = "struct Point:\n    x: int\n    y: int\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef struct Point:", code)
        self.assertIn("cdef int x", code)
        self.assertIn("cdef int y", code)


if __name__ == "__main__":
    unittest.main()