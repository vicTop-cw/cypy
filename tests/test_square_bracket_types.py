"""方括号泛型类型标注测试

验证 Cypy 支持 Python 习惯的方括号下标泛型写法
（list[int]、dict[str, int]、Optional[int]、Callable[[int], int] 等），
与既有的尖括号泛型（list<int>）并存。
"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypy_hook.hook import CypyHook


def _analyze(source: str) -> TypeChecker:
    """解析 + 类型检查，返回类型检查器（便于断言无错误）"""
    lexer = Lexer(source)
    ast = Parser(lexer.tokenize()).parse()
    tc = TypeChecker()
    tc.check(ast)
    return tc


def _transpile_ok(source: str) -> None:
    """端到端转译（分析 + 代码生成）必须成功且无错误"""
    r = CypyHook().transpile(source)
    assert r.success, f"transpile failed: {r.errors}"
    assert r.errors == [], f"unexpected errors: {r.errors}"


# ---- 1. 解析：方括号泛型应得到 GenericType 节点 ----

def _type_name(node):
    return getattr(node, 'name', None) or getattr(node, 'id', None)


def test_list_int_square_bracket_parses():
    ast = Parser(Lexer("def f() -> list[int]:\n    return []").tokenize()).parse()
    fn = ast.body[0]
    assert isinstance(fn.return_type, object)
    assert getattr(fn.return_type, 'name', None) == 'list'
    assert [_type_name(a) for a in getattr(fn.return_type, 'args', [])] == ['int']


def test_dict_square_bracket_parses():
    ast = Parser(Lexer("def f() -> dict[str, int]:\n    return {}").tokenize()).parse()
    fn = ast.body[0]
    assert getattr(fn.return_type, 'name', None) == 'dict'
    assert [_type_name(a) for a in getattr(fn.return_type, 'args', [])] == ['str', 'int']


def test_callable_with_list_arg_parses():
    ast = Parser(Lexer("def f() -> Callable[[int], int]:\n    return 0").tokenize()).parse()
    fn = ast.body[0]
    rt = fn.return_type
    assert getattr(rt, 'name', None) == 'Callable'
    # 首参是类型元组，用 GenericType('tuple', ...) 承载
    first = getattr(rt, 'args', [])[0]
    assert getattr(first, 'name', None) == 'tuple'
    assert [_type_name(a) for a in getattr(first, 'args', [])] == ['int']


# ---- 2. 分析：方括号泛型类型标注不得报未知类型错误 ----

@pytest.mark.parametrize("annotation,body", [
    ("list[int]", "return []"),
    ("dict[str, int]", "return {}"),
    ("set[int]", "return set()"),
    ("tuple[int, str]", "return (1, 'a')"),
    ("Optional[int]", "return 1"),
    ("Union[int, str]", "return 1"),
])
def test_square_bracket_annotation_analyzes(annotation, body):
    src = f"def f() -> {annotation}:\n    {body}\n"
    tc = _analyze(src)
    assert tc.errors == [], f"errors for {annotation}: {tc.errors}"


# ---- 3. 端到端：代码生成支持方括号泛型（Optional/Callable 回退为 object）----

def test_square_bracket_e2e_codegen():
    src = '''
def apply(fn: Callable[[int], int], x: int) -> int:
    return fn(x)

def double(n: int) -> int:
    return n * 2

def total(xs: list[int]) -> int:
    s: int = 0
    for v in xs:
        s = s + v
    return s

def g() -> None:
    apply(double, 3)
    total([1, 2, 3])
    return
'''
    _transpile_ok(src)


# ---- 4. 调用 Callable 类型变量应返回其声明的返回类型 ----

def test_call_callable_variable_returns_declared_type():
    src = '''
def apply(fn: Callable[[int], int], x: int) -> int:
    return fn(x)

def double(n: int) -> int:
    return n * 2

def use() -> None:
    apply(double, 3)
    return
'''
    # 此前会误报 “Return type mismatch: expected int, got Callable[...]”
    _transpile_ok(src)


def test_call_callable_with_two_args_returns_declared_type():
    src = '''
def run(fn: Callable[[int, str], bool], a: int, b: str) -> bool:
    return fn(a, b)

def checker(a: int, b: str) -> bool:
    return a > 0 and b != ""

def use() -> None:
    run(checker, 1, "x")
    return
'''
    _transpile_ok(src)
