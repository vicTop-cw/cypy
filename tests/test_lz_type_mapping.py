import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.codegen.type_mapper import TypeMapper


class TestLZTypeMapper(unittest.TestCase):
    def test_map_list_type(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("List", ["int"])
        self.assertEqual(result, "list")

    def test_map_option_type(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("Option", ["int"])
        self.assertEqual(result, "int | None")

    def test_map_option_empty(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("Option", [])
        self.assertEqual(result, "object")

    def test_map_result_type(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("Result", ["int", "str"])
        self.assertEqual(result, "(int, Exception)")

    def test_map_result_single_arg(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("Result", ["int"])
        self.assertEqual(result, "(int, Exception)")

    def test_map_dict_type(self):
        mapper = TypeMapper()
        result = mapper.map_lz_generic_type("Dict", ["str", "int"])
        self.assertEqual(result, "dict")

    def test_is_lz_generic_type(self):
        mapper = TypeMapper()
        self.assertTrue(mapper.is_lz_generic_type("List"))
        self.assertTrue(mapper.is_lz_generic_type("Option"))
        self.assertTrue(mapper.is_lz_generic_type("Result"))
        self.assertTrue(mapper.is_lz_generic_type("Dict"))
        self.assertFalse(mapper.is_lz_generic_type("Box"))
        self.assertFalse(mapper.is_lz_generic_type("int"))


class TestLZGenericTypeCodegen(unittest.TestCase):
    def _generate_code(self, source: str) -> str:
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        return generator.generate(ast)

    def test_list_return_type_generation(self):
        source = "def foo() -> List<int>:\n    return [1, 2, 3]\n"
        code = self._generate_code(source)
        self.assertIn("def foo():", code)

    def test_option_type_generation(self):
        source = "def foo(value: Option<int>) -> Option<str>:\n    return value\n"
        code = self._generate_code(source)
        self.assertIn("def foo(value):", code)

    def test_result_type_generation(self):
        source = "def foo() -> Result<int, str>:\n    return (42, None)\n"
        code = self._generate_code(source)
        self.assertIn("def foo():", code)

    def test_dict_type_generation(self):
        source = "def foo(data: Dict<str, int>) -> Dict<str, str>:\n    return data\n"
        code = self._generate_code(source)
        self.assertIn("def foo(data):", code)

    def test_option_in_struct_field(self):
        source = """
struct User:
    name: str
    age: Option<int>
"""
        code = self._generate_code(source)
        self.assertIn("int | None age", code)

    def test_option_return_type(self):
        source = "def find_user(id: int) -> Option<str>:\n    return None\n"
        code = self._generate_code(source)
        self.assertIn("def find_user(id):", code)

    def test_result_param_type(self):
        source = "def process(result: Result<int, str>) -> int:\n    return result[0]\n"
        code = self._generate_code(source)
        self.assertIn("def process(result):", code)

    def test_dict_nested_generic(self):
        source = "def foo(data: Dict<str, Option<int>>) -> Dict<str, Option<str>>:\n    return data\n"
        code = self._generate_code(source)
        self.assertIn("def foo(data):", code)

    def test_nested_option_return(self):
        source = "def get_items() -> Option<List<int>>:\n    return None\n"
        code = self._generate_code(source)
        self.assertIn("def get_items():", code)

    def test_mixed_types(self):
        source = "def complex_func(opt: Option<str>, res: Result<int, str>, dct: Dict<str, Option<int>>) -> Result<List<str>, Exception>:\n    return ([], None)\n"
        code = self._generate_code(source)
        self.assertIn("def complex_func(opt, res, dct):", code)


if __name__ == "__main__":
    unittest.main()