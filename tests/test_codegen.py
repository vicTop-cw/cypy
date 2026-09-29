import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.codegen.type_mapper import TypeMapper
from cypyc.codegen.setup_generator import SetupGenerator


class TestCythonGenerator(unittest.TestCase):
    def test_generate_function(self):
        source = "def foo(x: int) -> int:\n    return x\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        generator = CythonGenerator()
        code = generator.generate(ast)

        self.assertIn("def foo(x):", code)
        self.assertIn("return x", code)

    def test_generate_let_stmt(self):
        source = "let x = 42\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        generator = CythonGenerator()
        code = generator.generate(ast)

        self.assertIn("x = 42", code)


class TestTypeMapper(unittest.TestCase):
    def test_cypy_to_cython(self):
        mapper = TypeMapper()
        self.assertEqual(mapper.to_cython("int"), "int")
        # BUG-14 裁决（2026-09-26）：Cypy 的 float 跟随 Python 双精度。
        self.assertEqual(mapper.to_cython("float"), "double")
        self.assertEqual(mapper.to_cython("str"), "str")

    def test_cypy_to_c(self):
        mapper = TypeMapper()
        self.assertEqual(mapper.to_c("int"), "int")
        self.assertEqual(mapper.to_c("float"), "double")
        self.assertEqual(mapper.to_c("bool"), "bint")

    def test_add_custom_type(self):
        mapper = TypeMapper()
        mapper.add_custom_type("MyType", "MyType", "my_type_t")
        self.assertEqual(mapper.to_cython("MyType"), "MyType")
        self.assertEqual(mapper.to_c("MyType"), "my_type_t")


class TestSetupGenerator(unittest.TestCase):
    def test_generate_setup(self):
        generator = SetupGenerator()
        generator.set_module_name("mymodule")
        generator.add_source("mymodule.pyx")

        setup_code = generator.generate()

        self.assertIn("from setuptools import setup, Extension", setup_code)
        self.assertIn("name='mymodule'", setup_code)
        self.assertIn("sources=['mymodule.pyx']", setup_code)


if __name__ == "__main__":
    unittest.main()
