import unittest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.analyzer.defer_analyzer import DeferAnalyzer


class TestScopeAnalyzer(unittest.TestCase):
    def test_undefined_variable(self):
        source = "let x = y\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        analyzer = ScopeAnalyzer()
        analyzer.analyze(ast)

        self.assertEqual(len(analyzer.errors), 1)
        self.assertIn("Undefined name 'y'", analyzer.errors[0])

    def test_duplicate_declaration(self):
        source = "let x = 1\nlet x = 2\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        analyzer = ScopeAnalyzer()
        analyzer.analyze(ast)

        self.assertEqual(len(analyzer.errors), 1)
        self.assertIn("already declared", analyzer.errors[0])


class TestTypeChecker(unittest.TestCase):
    def test_type_inference(self):
        source = "let x = 42\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        checker = TypeChecker()
        checker.check(ast)

        self.assertEqual(len(checker.errors), 0)
        self.assertIn("x", checker.type_map)

    def test_return_type_mismatch(self):
        source = "def foo() -> int:\n    return 'hello'\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        checker = TypeChecker()
        checker.check(ast)

        self.assertEqual(len(checker.errors), 1)
        self.assertIn("Return type mismatch", checker.errors[0])


class TestDeferAnalyzer(unittest.TestCase):
    def test_break_in_defer(self):
        source = "def foo():\n    defer:\n        break\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        analyzer = DeferAnalyzer()
        analyzer.analyze(ast)

        self.assertEqual(len(analyzer.errors), 1)
        self.assertIn("Cannot use 'break' inside defer", analyzer.errors[0])

    def test_return_in_defer(self):
        source = "def foo():\n    defer:\n        return\n"
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()

        analyzer = DeferAnalyzer()
        analyzer.analyze(ast)

        self.assertEqual(len(analyzer.errors), 1)
        self.assertIn("Cannot use 'return' inside defer", analyzer.errors[0])


if __name__ == "__main__":
    unittest.main()
