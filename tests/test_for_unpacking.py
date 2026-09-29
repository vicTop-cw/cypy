"""for 循环多目标解包回归测试（BUG-024）

此前 for 目标解析只支持单个变量，`for k, v in d.items():` 会报
`Expected IN, got COMMA`，导致字典遍历/元组解包完全不可用。
本测试覆盖：多目标、括号形式、尾随逗号、嵌套列表模式、*rest 剩余绑定
的解析、变量注册与 Cython 代码生成。
"""
import unittest

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, ForStmt, FuncDef, Name
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def _parse(source: str):
    return Parser(list(Lexer(source).tokenize())).parse()


def _func_body(source: str):
    module = _parse(source)
    funcs = [s for s in module.body if isinstance(s, FuncDef)]
    if not funcs:
        raise AssertionError("未找到 FuncDef")
    return module, funcs[0].body


def _for_target(body: str):
    module, stmts = _func_body(
        "def f(d: dict<str, int>) -> None:\n    " + body + "\n"
    )
    for stmt in stmts:
        if isinstance(stmt, ForStmt):
            return stmt.target
    raise AssertionError("未找到 ForStmt")


class TestForUnpackingParser(unittest.TestCase):
    def test_multi_target(self):
        target = _for_target("for k, v in d.items():\n        pass")
        self.assertIsInstance(target, list)
        self.assertEqual([t.id for t in target], ["k", "v"])

    def test_parenthesized_target(self):
        target = _for_target("for (k, v) in d.items():\n        pass")
        self.assertIsInstance(target, list)
        self.assertEqual(len(target), 2)

    def test_trailing_comma(self):
        target = _for_target("for k, v, in d.items():\n        pass")
        self.assertEqual([t.id for t in target], ["k", "v"])

    def test_star_rest(self):
        target = _for_target("for head, *tail in d.items():\n        pass")
        self.assertEqual(target[0].id, "head")
        self.assertEqual(getattr(target[1], "kind", None), "SlicePattern")
        self.assertEqual(target[1].name, "tail")

    def test_nested_list_pattern(self):
        target = _for_target("for k, [a, b] in d.items():\n        pass")
        self.assertEqual(getattr(target[1], "kind", None), "ArrayPattern")

    def test_single_target_unchanged(self):
        target = _for_target("for x in d.items():\n        pass")
        self.assertIsInstance(target, Name)
        self.assertEqual(target.id, "x")


class TestForUnpackingCodegen(unittest.TestCase):
    def _gen(self, body: str) -> str:
        module, _ = _func_body(
            "def f(d: dict<str, int>) -> None:\n    " + body + "\n"
        )
        return CythonGenerator().generate(module)

    def test_emits_tuple_unpack(self):
        code = self._gen("for k, v in d.items():\n        pass")
        self.assertIn("for (k, v) in", code)

    def test_emits_star_rest(self):
        code = self._gen("for head, *tail in d.items():\n        pass")
        self.assertIn("*tail", code)

    def test_single_target_not_wrapped(self):
        code = self._gen("for x in d.items():\n        pass")
        self.assertIn("for x in", code)


class TestForUnpackingAnalysis(unittest.TestCase):
    def _analyze(self, body: str):
        module, _ = _func_body(
            "def f(d: dict<str, int>) -> None:\n    " + body + "\n"
        )
        scope = ScopeAnalyzer().analyze(module)
        TypeChecker().check(module)
        return scope

    def test_star_rest_binding_registered(self):
        """`*tail` 必须注册为循环变量，否则报 Undefined name 'tail'。"""
        scope = self._analyze("for head, *tail in d.items():\n        pass")
        names = set()
        stack = [scope]
        while stack:
            cur = stack.pop()
            names |= set(getattr(cur, "symbols", {}) or {})
            stack.extend(getattr(cur, "children", []) or [])
        self.assertIn("tail", names)
        self.assertIn("head", names)

    def test_multi_target_binding_registered(self):
        scope = self._analyze("for k, v in d.items():\n        pass")
        names = set()
        stack = [scope]
        while stack:
            cur = stack.pop()
            names |= set(getattr(cur, "symbols", {}) or {})
            stack.extend(getattr(cur, "children", []) or [])
        self.assertIn("k", names)
        self.assertIn("v", names)


if __name__ == "__main__":
    unittest.main()
