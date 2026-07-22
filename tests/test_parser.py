import unittest
from cypyc.parser.lexer import Lexer, TokenType
from cypyc.parser.parser import Parser, Module, FuncDef, LetStmt, ReturnStmt, BinOp, Name, Constant


class TestLexer(unittest.TestCase):
    def test_tokenize_identifier(self):
        lexer = Lexer("foo")
        tokens = list(lexer.tokenize())
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].value, "foo")

    def test_tokenize_integer(self):
        lexer = Lexer("42")
        tokens = list(lexer.tokenize())
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].type, TokenType.INTEGER)
        self.assertEqual(tokens[0].value, "42")

    def test_tokenize_float(self):
        lexer = Lexer("3.14")
        tokens = list(lexer.tokenize())
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].type, TokenType.FLOAT)
        self.assertEqual(tokens[0].value, "3.14")

    def test_tokenize_string(self):
        lexer = Lexer('"hello"')
        tokens = list(lexer.tokenize())
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].type, TokenType.STRING)
        self.assertEqual(tokens[0].value, "hello")

    def test_tokenize_arithmetic(self):
        lexer = Lexer("a + b * c")
        tokens = list(lexer.tokenize())
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[1].type, TokenType.PLUS)
        self.assertEqual(tokens[2].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[3].type, TokenType.MUL)
        self.assertEqual(tokens[4].type, TokenType.IDENTIFIER)


class TestParser(unittest.TestCase):
    def test_parse_module(self):
        source = "def foo():\n    return 42\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        self.assertIsInstance(ast, Module)
        self.assertEqual(len(ast.body), 1)

    def test_parse_func_def(self):
        source = "def foo(x: int) -> int:\n    return x\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        func = ast.body[0]
        self.assertIsInstance(func, FuncDef)
        self.assertEqual(func.name, "foo")
        self.assertEqual(len(func.params), 1)
        self.assertEqual(func.params[0].name, "x")

    def test_parse_let_stmt(self):
        source = "let x = 42\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        stmt = ast.body[0]
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "x")
        self.assertIsInstance(stmt.value, Constant)
        self.assertEqual(stmt.value.value, 42)

    def test_parse_binary_op(self):
        source = "a + b * c\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        stmt = ast.body[0]
        self.assertIsInstance(stmt.value, BinOp)
        self.assertEqual(stmt.value.op, "+")
        self.assertIsInstance(stmt.value.left, Name)
        self.assertEqual(stmt.value.left.id, "a")


if __name__ == "__main__":
    unittest.main()
