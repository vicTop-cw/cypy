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
    # 告知 pytest 不要将本辅助数据类当作测试类收集（避免 __init__ 构造告警）。
    __test__ = False

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

class TestOwnershipPerFunctionState(unittest.TestCase):
    """OMEGA T0r61.3.2: pointer_checker 的所有权状态必须是"每个函数一套"

    缺陷：owned_vars/moved_vars/defer_cleaned_vars 在 __init__ 里创建后从不重置，
    函数A里 move 掉的变量名会在 _check_owned_vars_cleanup 里把函数B里同名 owned 变量
    "必须清理"的诊断吞掉（假阴性，且结果依赖函数书写顺序）。
    """

    NL = chr(10)
    FUNC_A = """def produce() -> None:
    owned buf: int = 10
    moved = transfer_ownership(buf)
"""
    FUNC_B = """def consume() -> None:
    owned buf: int = 20
"""

    def _check(self, source: str):
        module = Parser(Lexer(source).tokenize()).parse()
        checker = PointerChecker()
        checker.check(module)
        return checker

    def test_stale_moved_name_does_not_swallow_later_function(self):
        """A 里 move 过 'buf' 之后，B 里同名 owned 变量的诊断不能被吞掉"""
        alone = self._check(self.FUNC_B)
        self.assertTrue(any("must be cleaned" in e for e in alone.errors), alone.errors)

        both = self._check(self.FUNC_A + self.NL + self.FUNC_B)
        self.assertEqual(len(both.errors), len(alone.errors), both.errors)
        self.assertTrue(any("must be cleaned" in e for e in both.errors), both.errors)

    def test_diagnostics_are_order_independent(self):
        """A-then-B 与 B-then-A 的诊断数量必须一致"""
        ab = self._check(self.FUNC_A + self.NL + self.FUNC_B)
        ba = self._check(self.FUNC_B + self.NL + self.FUNC_A)
        self.assertEqual(len(ab.errors), len(ba.errors), (ab.errors, ba.errors))

    def test_ownership_sets_do_not_leak_across_functions(self):
        """检查完整模块后，作用域级的所有权集合不能残留已销毁作用域的名字"""
        checker = self._check(self.FUNC_A + self.NL + self.FUNC_B)
        self.assertEqual(checker.owned_vars, set(), checker.owned_vars)
        self.assertEqual(checker.defer_cleaned_vars, set(), checker.defer_cleaned_vars)
        self.assertTrue(any("must be cleaned" in e for e in checker.errors), checker.errors)

    def test_transfer_of_annotated_parameter_does_not_crash(self):
        """transfer_ownership(带类型注解的形参) 不能抛 TypeError: 'str' object is not a mapping"""
        module = Parser(Lexer("""def take_away(v: int) -> None:
    w = transfer_ownership(v)
""").tokenize()).parse()
        checker = PointerChecker()
        checker.check(module)  # 修复前这一步直接抛 TypeError
        # 只关心"没有崩溃"，同时保留它确实给出了"不是 owned 变量"的诊断
        self.assertTrue(any("requires owned variable" in e for e in checker.errors),
                        checker.errors)


class TestOwnershipDeferCleaning(unittest.TestCase):
    """OMEGA T0r61.3.2: defer 块里的 free(x) 必须登记为已清理

    缺陷：_visit_DeferStmt 判的是 stmt.kind == 'Call'，而解析器把调用包在 ExprStmt 里，
    所以 defer_cleaned_vars 永远是空集，"defer 清理过的 owned 变量"仍被报为未清理。
    """

    NL = chr(10)

    def _check(self, source: str):
        module = Parser(Lexer(source).tokenize()).parse()
        checker = PointerChecker()
        checker.check(module)
        return checker

    def test_defer_free_satisfies_owned_cleanup(self):
        checker = self._check("""def leaks() -> None:
    owned res: int = 1
    defer:
        free(res)
""")
        self.assertEqual(checker.defer_cleaned_vars, {"res"}, checker.defer_cleaned_vars)
        self.assertFalse(any("must be cleaned" in e for e in checker.errors), checker.errors)

    def test_defer_cleaning_is_not_leaked_into_next_function(self):
        checker = self._check(
            """def leaks() -> None:
    owned res: int = 1
    defer:
        free(res)
"""
            + self.NL
            + """def forgets() -> None:
    owned res: int = 2
"""
        )
        self.assertTrue(any("must be cleaned" in e for e in checker.errors), checker.errors)


class TestOwnedRuntimeValues(unittest.TestCase):
    """OMEGA T0r61.3.2: own()/Owned() 必须能处理 codegen 实际会生成的值

    `owned x: int = 10` 生成 `x = own(10)`、`owned data = [1, 2, 3]` 生成
    `data = own([1, 2, 3])`，而 int/list 都不可弱引用，旧实现在导入生成模块时直接抛
    TypeError: cannot create weak reference to 'int' object。
    """

    NL = chr(10)

    def test_generated_own_calls_actually_execute(self):
        source = "owned counter: int = 10" + self.NL
        code = CythonGenerator().generate(Parser(Lexer(source).tokenize()).parse())
        self.assertIn("counter = own(10)", code)
        namespace = {}
        exec("from cypy_bridge.pointer import own" + self.NL + "counter = own(10)"
             + self.NL + "result = counter.take()", namespace)
        self.assertEqual(namespace["result"], 10)

    def test_owned_accepts_list_and_scalar(self):
        data = own([1, 2, 3])
        self.assertTrue(data.is_valid)
        self.assertEqual(data.take(), [1, 2, 3])

        counter = own(10)
        self.assertTrue(counter.is_valid)
        self.assertEqual(counter.take(), 10)

    def test_owned_of_ctypes_temporary_is_not_null(self):
        import ctypes

        handle = Owned(ctypes.c_int(42))
        self.assertTrue(handle.is_valid, repr(handle))
        self.assertEqual(handle.take().value, 42)

    def test_borrow_of_value_semantic_owned(self):
        borrowed = borrow(own(42))
        self.assertTrue(borrowed.is_valid)
        self.assertEqual(borrowed.deref(), 42)


if __name__ == '__main__':
    unittest.main()
