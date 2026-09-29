"""R2-打磨 的回归锁：死代码遮蔽的结构判据 + class 侧非绑定方法的空白面 + 存活实现的形状。

三条纪律（都对应本轮真实踩过的坑）：
- 每条主张都配"必被抓到"或"必不误抓"的对照，只有正例的判据等于没有判据；
- 判据打在**调用面/AST 事实**上：`_visit_*` 是否仍写出正确产物、方法名是否仍在同一类体内出现两次；
- 删除死代码的前提是"生效的那一份"被证据钉住（`类.__dict__[名].__code__.co_firstlineno`），
  而不是"我看第二份顺眼"。
"""

import ast
import inspect
from pathlib import Path

import pytest

from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

ROOT = Path(__file__).resolve().parent.parent


def _emit(source: str) -> str:
    """与 CLI 同一条三段管线：Lexer → Parser → CythonGenerator。"""
    tree = Parser(list(Lexer(source).tokenize())).parse()
    gen = CythonGenerator()
    gen.generate(tree)
    return "\n".join(gen.output)


def _sig(text: str, name: str) -> list:
    want = f"def {name}("
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(want)]


def _duplicate_methods_in(src: str) -> list:
    """同一类体内出现两次以上的同名方法 ⇒ 前一份是永远不会被调用的死代码。"""
    out = []
    for cls in [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef)]:
        seen: dict = {}
        for item in cls.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen.setdefault(item.name, []).append(item.lineno)
        for name, lines in seen.items():
            if len(lines) > 1:
                out.append(f"{cls.name}.{name}@{lines}")
    return out


# ---------------------------------------------------- 判据 1：结构门（BUG-42 的机制化）
def test_product_code_has_no_shadowed_method_definitions():
    dup = []
    for path in sorted((ROOT / "cypyc").rglob("*.py")):
        if path.stat().st_size > 400_000:
            continue
        text = path.read_text(encoding="utf-8")
        for d in _duplicate_methods_in(text):
            dup.append(f"{path.relative_to(ROOT)}:{d}")
    assert not dup, f"产品码里仍有被遮蔽的同名方法（BUG-42 的形状回来了）：{dup[:6]}"


def test_shadow_detector_catches_a_synthetic_pair():
    """对照：上一条若是恒绿的，这条必须红——同一个类体内写两次同名方法必被抓到。"""
    src = "class A:\n    def m(self):\n        pass\n\n    def m(self):\n        pass\n"
    assert _duplicate_methods_in(src) == ["A.m@[2, 5]"], _duplicate_methods_in(src)
    assert _duplicate_methods_in("class A:\n    def m(self):\n        pass\n") == []


# ---------------------------------------------------- 判据 2：class 侧非绑定方法（R2-验证 指出的空白面）
CLASS_SIDES_SRC = '''
class Registry:
    count: int

    @staticmethod
    def version() -> int:
        return 7

    @classmethod
    def named(cls, tag: str) -> int:
        return 1

    def bump(self, by: int) -> int:
        return self.count + by
'''


def test_class_side_static_and_bound_signatures():
    emit = _emit(CLASS_SIDES_SRC)
    assert _sig(emit, "version") == ["def version():"], _sig(emit, "version")
    assert _sig(emit, "bump") == ["def bump(self, by):"], _sig(emit, "bump")


def test_class_side_classmethod_keeps_explicit_cls():
    """SYNTAX/08:123 的文档形状是显式 `cls`：不得被注入 self，也不得把 cls 吃掉。"""
    emit = _emit(CLASS_SIDES_SRC)
    assert _sig(emit, "named") == ["def named(cls, tag):"], _sig(emit, "named")


# ---------------------------------------------------- 判据 3：删掉死份后，存活实现仍做事
def test_expr_stmt_visitor_still_emits_the_call():
    src = (
        "def twice(n: int) -> int:\n"
        "    return n * 2\n\n\n"
        "def runner() -> int:\n"
        "    twice(3)\n"
        "    return 1\n"
    )
    emit = _emit(src)
    assert "twice(3)" in emit, [ln for ln in emit.splitlines() if "twice" in ln]


def test_live_meta_block_visitor_sets_and_clears_flag():
    """存活那份的语义是"允许前向引用"：模块级 meta 块不得报错，且标志位必须被复位。"""
    analyzer = ScopeAnalyzer()
    tree = Parser(list(Lexer("meta:\n    let n: int = 4\n").tokenize())).parse()
    analyzer.analyze(tree)
    assert analyzer.errors == [], analyzer.errors
    assert getattr(analyzer, "in_meta_block", False) is False


# ---------------------------------------- 判据 4：Python 实际绑定的是哪一份（生效性，不钉行号）
def test_bound_visitors_are_the_surviving_implementations():
    """删除的理由是"被遮蔽的一份从不执行"。这条锁把它翻成可复算的事实：
    类上绑定的 `_visit_ExprStmt` 必须是带宏展开的那份，`_visit_MetaBlock` 必须是设标志的那份。
    断言用**实现里的独有字样**而不是行号 ⇒ 删掉死份后本条仍应绿（不随行号漂移而假红）。"""
    expr_src = inspect.getsource(CythonGenerator._visit_ExprStmt)
    assert "_expand_macro" in expr_src, expr_src
    assert "_pending_copies" not in expr_src, expr_src

    meta_src = inspect.getsource(ScopeAnalyzer._visit_MetaBlock)
    assert "in_meta_block" in meta_src, meta_src
    assert "can only be defined" not in meta_src, meta_src


# ---------------------------------------- 判据 5：死份里的守卫意图并未随删除而丢失
def test_nested_meta_block_is_rejected_with_position():
    """被删的 `_visit_MetaBlock` 带着"只能模块顶级"的守卫；真守卫在 parser 里，删除前实测就生效。
    这条锁保证删除不会把"已声明的校验"删成"没人校验"——成对：反例必被抓，正例必不误抓。"""
    nested = "def foo():\n    meta:\n        let n: int = 4\n    return 1\n"
    with pytest.raises(ValueError) as excinfo:
        Parser(list(Lexer(nested).tokenize())).parse()
    message = str(excinfo.value)
    assert "module level" in message and "2:9" in message, message

    Parser(list(Lexer("meta:\n    let n: int = 4\n").tokenize())).parse()
