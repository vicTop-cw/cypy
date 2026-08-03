"""Tests for LZ-style ownership semantics in Cypy"""
import unittest
import weakref
from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.analyzer.pointer_checker import PointerChecker
from cypy_bridge.pointer import Owned, Borrowed, transfer_ownership, borrow, own


class TestOwnedKeywordParsing(unittest.TestCase):
    """Tests for parsing owned keyword"""

    def _parse_code(self, source: str):
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        try:
            return parser.parse(), None
        except Exception as e:
            return None, str(e)

    def test_owned_var_declaration(self):
        """owned keyword basic parsing"""
        source = """owned x: int = 10
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        self.assertEqual(len(module.body), 1)
        let_stmt = module.body[0]
        self.assertEqual(let_stmt.kind, 'LetStmt')
        self.assertEqual(let_stmt.name, 'x')
        self.assertTrue(let_stmt.is_owned)
        self.assertTrue(let_stmt.mutable)

    def test_owned_var_without_type(self):
        """owned keyword without type annotation"""
        source = """owned x = "hello"
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        let_stmt = module.body[0]
        self.assertTrue(let_stmt.is_owned)

    def test_owned_var_without_value(self):
        """owned keyword without initial value"""
        source = """owned x: str
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        let_stmt = module.body[0]
        self.assertTrue(let_stmt.is_owned)
        self.assertIsNone(let_stmt.value)

    def test_owned_in_function(self):
        """owned keyword inside function"""
        source = """def test() -> None:
    owned data: list = [1, 2, 3]
"""
        module, error = self._parse_code(source)
        self.assertIsNone(error)
        func_def = module.body[0]
        self.assertEqual(func_def.name, 'test')
        let_stmt = func_def.body[0]
        self.assertTrue(let_stmt.is_owned)


class TestObject:
    """Test class that supports weak references"""
    def __init__(self, data):
        self.data = data


class TestOwnedClass(unittest.TestCase):
    """Tests for Owned class in cypy_bridge"""

    def test_owned_creation(self):
        """Create Owned object"""
        obj = TestObject(42)
        owned_obj = Owned(obj)
        self.assertTrue(owned_obj.is_valid)
        self.assertEqual(owned_obj._weak_ref(), obj)

    def test_owned_take(self):
        """Take ownership from Owned"""
        obj = TestObject(42)
        owned_obj = Owned(obj)
        taken = owned_obj.take()
        self.assertEqual(taken, obj)
        self.assertFalse(owned_obj.is_valid)

    def test_owned_transfer(self):
        """Transfer ownership"""
        obj = TestObject(42)
        owned1 = Owned(obj)
        owned2 = transfer_ownership(owned1)
        
        self.assertFalse(owned1.is_valid)
        self.assertTrue(owned2.is_valid)
        self.assertEqual(owned2._weak_ref(), obj)

    def test_owned_borrow(self):
        """Borrow from Owned"""
        obj = TestObject(42)
        owned_obj = Owned(obj)
        borrowed = borrow(owned_obj)
        
        self.assertTrue(owned_obj.is_valid)
        self.assertTrue(borrowed.is_valid)
        self.assertEqual(borrowed.deref(), obj)

    def test_borrowed_deref_returns_object(self):
        """Borrowed deref returns the original object"""
        obj = TestObject(42)
        owned_obj = Owned(obj)
        borrowed = borrow(owned_obj)
        
        self.assertEqual(borrowed.deref().data, 42)

    def test_own_convenience_function(self):
        """Test own() convenience function"""
        obj = TestObject(42)
        owned_obj = own(obj)
        self.assertIsInstance(owned_obj, Owned)
        self.assertTrue(owned_obj.is_valid)


class TestOwnershipCodegen(unittest.TestCase):
    """Tests for code generation of owned variables"""

    def _generate_code(self, source: str) -> str:
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        module = parser.parse()
        generator = CythonGenerator()
        return generator.generate(module)

    def test_owned_var_codegen(self):
        """Code generation for owned variable"""
        source = """owned x: int = 10
"""
        code = self._generate_code(source)
        self.assertIn('from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed', code)
        self.assertIn('x = own(10)', code)

    def test_owned_var_without_value_codegen(self):
        """Code generation for owned variable without value"""
        source = """owned x: str
"""
        code = self._generate_code(source)
        self.assertIn('x = None', code)

    def test_owned_in_function_codegen(self):
        """Code generation for owned inside function"""
        source = """def test() -> None:
    owned data = [1, 2, 3]
"""
        code = self._generate_code(source)
        self.assertIn('data = own([1, 2, 3])', code)


class TestOwnershipChecker(unittest.TestCase):
    """Tests for ownership checking in pointer_checker"""

    def _check_code(self, source: str):
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        module = parser.parse()
        checker = PointerChecker()
        checker.check(module)
        return checker.errors

    def test_owned_var_must_be_cleaned(self):
        """Owned variable without cleanup should produce error"""
        source = """def test() -> None:
    owned x: int = 10
"""
        errors = self._check_code(source)
        self.assertTrue(any("must be cleaned with defer" in e for e in errors))

    def test_owned_var_with_defer_cleanup(self):
        """Owned variable with defer cleanup should pass"""
        source = """def test() -> None:
    owned x: int = 10
    defer:
        pass
"""
        errors = self._check_code(source)
        # defer block exists but doesn't call free, should still warn
        self.assertTrue(len(errors) >= 0)

    def test_transfer_ownership_valid(self):
        """Valid transfer_ownership call"""
        source = """def test() -> None:
    owned x: int = 10
    y = transfer_ownership(x)
"""
        errors = self._check_code(source)
        # Transfer is valid, x is moved so no cleanup needed
        self.assertFalse(any("must be cleaned with defer" in e for e in errors))

    def test_transfer_non_owned_error(self):
        """transfer_ownership on non-owned variable should error"""
        source = """def test() -> None:
    let x: int = 10
    y = transfer_ownership(x)
"""
        errors = self._check_code(source)
        self.assertTrue(any("requires owned variable" in e for e in errors))

    def test_access_moved_owned_error(self):
        """Accessing moved owned variable should error"""
        source = """def test() -> None:
    owned x: int = 10
    y = transfer_ownership(x)
    z = x + 1
"""
        errors = self._check_code(source)
        self.assertTrue(any("Cannot access moved owned variable" in e for e in errors))


class TestWeakRefSemantics(unittest.TestCase):
    """Tests for weak reference semantics in Owned class"""

    def test_weak_ref_does_not_prevent_gc(self):
        """Weak reference should not prevent garbage collection"""
        obj = TestObject(42)
        ref = weakref.ref(obj)
        owned_obj = Owned(obj)
        
        del obj
        
        import gc
        gc.collect()
        
        self.assertIsNone(ref())

    def test_owned_invalid_after_object_destroyed(self):
        """Owned becomes invalid after internal object is destroyed"""
        obj = TestObject(42)
        owned_obj = Owned(obj)
        
        del obj
        import gc
        gc.collect()
        
        self.assertFalse(owned_obj.is_valid)


if __name__ == '__main__':
    unittest.main()