"""LZ 风格可变参数测试"""
import unittest
from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer
from cypyc.codegen.cython_generator import CythonGenerator


class TestVarargsParser(unittest.TestCase):
    """可变参数解析测试"""
    
    def _parse_code(self, source: str):
        """辅助方法：解析代码"""
        try:
            lexer = Lexer(source)
            tokens = list(lexer.tokenize())
            parser = Parser(tokens)
            module = parser.parse()
            return module, None
        except Exception as e:
            return None, str(e)
    
    def test_list_var_positional(self):
        """测试 List<T> 安全收集模式"""
        source = """def sum_all(values: List<int>) -> int:
    total = 0
    for v in values:
        total += v
    return total
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(func_def.name, 'sum_all')
        self.assertEqual(len(func_def.params), 1)
        self.assertTrue(func_def.params[0].is_var_positional)
    
    def test_double_dot_separator(self):
        """测试双 .. 分隔符模式"""
        source = """def handler(a: int, .., b: str, ..):
    pass
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        # 参数应该是: a, .., b, ..
        dot_count = sum(1 for p in func_def.params if getattr(p, 'is_dot_separator', False))
        self.assertEqual(dot_count, 2)
    
    def test_single_dot_separator(self):
        """测试单 .. 分隔符"""
        source = """def proc(x: int, ..):
    pass
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        dot_count = sum(1 for p in func_def.params if getattr(p, 'is_dot_separator', False))
        self.assertEqual(dot_count, 1)
    
    def test_dot_with_type_annotation(self):
        """测试 .. 带类型注解"""
        source = """def log(..: Tuple<int, str>, ..):
    pass
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        dot_count = sum(1 for p in func_def.params if getattr(p, 'is_dot_separator', False))
        self.assertEqual(dot_count, 2)
    
    def test_list_with_regular_params(self):
        """测试 List<T> 与普通参数混合"""
        source = """def log(level: str, messages: List<str>) -> None:
    pass
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(len(func_def.params), 2)
        self.assertFalse(func_def.params[0].is_var_positional)
        self.assertTrue(func_def.params[1].is_var_positional)


class TestVarargsCodegen(unittest.TestCase):
    """可变参数代码生成测试"""
    
    def _generate_code(self, source: str) -> str:
        """辅助方法：生成 Cython 代码"""
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        module = parser.parse()
        generator = CythonGenerator()
        return generator.generate(module)
    
    def test_list_var_positional_codegen(self):
        """测试 List<T> 安全收集模式代码生成"""
        source = """def sum_all(values: List<int>) -> int:
    total = 0
    for v in values:
        total += v
    return total
"""
        code = self._generate_code(source)
        # 应该生成 *values 和 values = list(values)
        self.assertIn('*values', code)
        self.assertIn('values = list(values)', code)
    
    def test_double_dot_codegen(self):
        """测试双 .. 分隔符代码生成"""
        source = """def handler(a: int, .., b: str, ..):
    pass
"""
        code = self._generate_code(source)
        # 应该生成 *args 和 **kwargs
        self.assertIn('*args', code)
        self.assertIn('**kwargs', code)
    
    def test_list_with_regular_params_codegen(self):
        """测试 List<T> 与普通参数混合代码生成"""
        source = """def log(level: str, messages: List<str>) -> None:
    pass
"""
        code = self._generate_code(source)
        # 应该包含 level 参数和 *messages
        self.assertIn('level', code)
        self.assertIn('*messages', code)
        self.assertIn('messages = list(messages)', code)


if __name__ == '__main__':
    unittest.main()
