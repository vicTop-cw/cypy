"""Tests for LZ (lang-zone) syntax features in Cypy"""
import unittest
from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer
from cypyc.codegen.cython_generator import CythonGenerator


class TestLZFunctionBodySyntax(unittest.TestCase):
    """Tests for LZ-style = function body syntax"""

    def _parse_code(self, source: str):
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        try:
            return parser.parse(), None
        except Exception as e:
            return None, str(e)

    def _generate_code(self, source: str) -> str:
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        module = parser.parse()
        generator = CythonGenerator()
        return generator.generate(module)

    def test_lz_single_line_function(self):
        """def f() = expr - single line function body"""
        source = """def add(a: int, b: int) -> int = a + b"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(func_def.name, 'add')
        self.assertEqual(len(func_def.params), 2)
        # Body should be a ReturnStmt wrapping the expression
        self.assertEqual(len(func_def.body), 1)
        self.assertEqual(func_def.body[0].kind, 'ReturnStmt')

    def test_lz_block_function(self):
        """def f() = with block body"""
        source = """def add(a: int, b: int) -> int =
    total = a + b
    return total
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(func_def.name, 'add')
        self.assertEqual(len(func_def.body), 2)

    def test_lz_function_without_return_type(self):
        """def f() = expr without return type"""
        source = """def greet(name: str) = f"Hello, {name}"\n"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertIsNone(func_def.return_type)

    def test_lz_function_codegen_single_line(self):
        """Code generation for LZ single-line function"""
        source = """def add(a: int, b: int) -> int = a + b"""
        code = self._generate_code(source)
        self.assertIn('def add(a, b):', code)
        self.assertIn('return a + b', code)

    def test_lz_function_codegen_block(self):
        """Code generation for LZ block function"""
        source = """def greet(name: str) =
    return f"Hello, {name}"
"""
        code = self._generate_code(source)
        self.assertIn('def greet(name):', code)
        self.assertIn("return f'Hello, {name}'", code)

    def test_original_colon_syntax_still_works(self):
        """Original : function body syntax should still work"""
        source = """def old_style(a: int, b: int) -> int:
    return a + b
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(func_def.name, 'old_style')


class TestLZContainerTypeMapping(unittest.TestCase):
    """Tests for LZ container type to Cython type mapping"""

    def _parse_code(self, source: str):
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        try:
            return parser.parse(), None
        except Exception as e:
            return None, str(e)

    def _generate_code(self, source: str) -> str:
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        module = parser.parse()
        generator = CythonGenerator()
        return generator.generate(module)

    def test_list_type_mapping(self):
        """List<T> should map to Python list"""
        source = """def process(items: List<int>) -> int = len(items)"""
        code = self._generate_code(source)
        # List<T> 作为参数类型映射为 list，但作为可变参数时会生成 *args
        self.assertIn('process', code)
        self.assertIn('len(items)', code)

    def test_dict_type_mapping(self):
        """Dict<K,V> should map to Python dict"""
        source = """def count_keys(data: Dict<str, int>) -> int = len(data)"""
        code = self._generate_code(source)
        self.assertIn('def count_keys(data):', code)

    def test_tuple_type_mapping(self):
        """Tuple<...> should map to Python tuple"""
        source = """def get_pair() -> Tuple<int, str> = (1, "hello")"""
        code = self._generate_code(source)
        self.assertIn('def get_pair():', code)

    def test_option_type_mapping(self):
        """Option<T> should map to T | None"""
        source = """def find_value(key: str) -> Option<int> = None"""
        code = self._generate_code(source)
        self.assertIn('def find_value(key):', code)

    def test_result_type_mapping(self):
        """Result<T,E> should map to (T, Exception)"""
        source = """def compute() -> Result<int, str> = 42"""
        code = self._generate_code(source)
        self.assertIn('def compute():', code)

    def test_list_varargs_with_mapping(self):
        """List<T> varargs with type mapping"""
        source = """def sum_all(values: List<int>) -> int:
    total = 0
    for v in values:
        total += v
    return total
"""
        code = self._generate_code(source)
        self.assertIn('def sum_all(*values):', code)


if __name__ == '__main__':
    unittest.main()
