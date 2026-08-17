"""新增功能测试用例"""
import unittest
from cypyc.parser.lexer import Lexer, TokenType
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


class TestDefFunctionSystem(unittest.TestCase):
    """def 函数系统测试"""
    
    def test_def_keyword_parsing(self):
        """测试 def 关键字词法解析"""
        source = "def add(x: int, y: int) -> int:\n    return x + y"
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        def_tokens = [t for t in tokens if t.type == TokenType.DEF]
        self.assertEqual(len(def_tokens), 1)
        self.assertEqual(def_tokens[0].value, "def")
    
    def test_def_syntax_parsing(self):
        """测试 def 函数语法解析"""
        source = """
def add(x: int, y: int) -> int:
    return x + y
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        func_def = ast.body[0]
        self.assertEqual(func_def.name, "add")
    
    def test_def_codegen(self):
        """测试 def 函数代码生成"""
        source = """
def add(x: int, y: int) -> int:
    return x + y
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("def add(x, y):", code)


class TestStructMethods(unittest.TestCase):
    """结构体方法测试"""
    
    def test_struct_with_method_definition(self):
        """测试带方法的结构体定义"""
        source = """
struct Point:
    x: int
    y: int
    
    def distance(self, other: Point) -> double:
        return ((self.x - other.x)**2 + (self.y - other.y)**2)**0.5
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        struct_def = ast.body[0]
        self.assertEqual(len(struct_def.methods), 1)
        self.assertEqual(struct_def.methods[0].name, "distance")
    
    def test_struct_method_codegen(self):
        """测试结构体方法代码生成"""
        source = """
struct Point:
    x: int
    y: int
    
    def distance(self, other: Point) -> double:
        return ((self.x - other.x)**2 + (self.y - other.y)**2)**0.5
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        self.assertIn("cdef class Point", code)
        self.assertIn("def distance(self, other):", code)
    
    def test_struct_method_operator_precedence(self):
        """测试结构体方法中的运算符优先级"""
        source = """
struct Point:
    x: int
    y: int
    
    def compute(self) -> int:
        return self.x + self.y * 2
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # 验证运算符优先级：y * 2 应该先执行
        self.assertIn("self.x + self.y * 2", code)


class TestScopeRestrictions(unittest.TestCase):
    """作用域限制测试"""
    
    def test_struct_inside_function_error(self):
        """测试函数内定义结构体应该报错（解析阶段）"""
        source = """
def test():
    struct Point:
        x: int
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        with self.assertRaises(ValueError) as context:
            ast = parser.parse()
        self.assertIn("must be defined at module level", str(context.exception))
    
    def test_enum_inside_function_error(self):
        """测试函数内定义枚举应该报错（解析阶段）"""
        source = """
def test():
    enum Color:
        RED
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        with self.assertRaises(ValueError) as context:
            ast = parser.parse()
        self.assertIn("must be defined at module level", str(context.exception))


class TestBinOpPrecedence(unittest.TestCase):
    """二元运算符优先级测试"""
    
    def test_power_operator_precedence(self):
        """测试幂运算符优先级"""
        source = """
def test():
    return 2 + 3 ** 2
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # 验证 3 ** 2 先执行，不需要括号
        self.assertIn("2 + 3 ** 2", code)
    
    def test_additive_before_multiplicative(self):
        """测试加法和乘法的优先级"""
        source = """
def test():
    return (2 + 3) * 4
"""
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        generator = CythonGenerator()
        code = generator.generate(ast)
        # 验证括号被保留
        self.assertIn("(2 + 3) * 4", code)


if __name__ == "__main__":
    unittest.main()
