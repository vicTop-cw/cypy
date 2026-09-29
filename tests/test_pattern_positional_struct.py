"""struct 位置模式的调用面回归锁（memory/bugs.md BUG-36 / BUG-37，2026-09-29 R6）。

两条锁各自对应一处根因，且都设计成「回退本轮修复即变红」：

BUG-37（`type_checker._visit_Pattern`）：绑定名曾被无条件写成 `Type("int")`
（注释自称"暂定"），把槽位类型覆盖掉 ⇒ `case Email(user, domain): return user`
被判「Return type mismatch: expected str, got int」，连 transpile 都过不去。
回退它 ⇒ 本文件第 1/2 条红。

BUG-36（`cython_generator._collect_module_info`）：StructDef 的成员在 `.fields`/`.methods`
而**不在** `.body`（parser.py:117-135），旧实现只遍历 `.body` ⇒ 既检测不到 `__unapply__`，
也拿不到字段名，位置模式退化为访问不存在的 `__f0/__f1`。
回退它 ⇒ 本文件第 3/4/5 条红。

第 6 条把「方法名不算位置字段」钉住：旧实现把 body 里任何有 name 的成员都收进 fields，
`case P(3, 4)` 会拿去和绑定方法比较（恒 False、零诊断）。
"""

from __future__ import annotations

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

EXTRACTOR_SRC = '''struct Email:
    address: str

    def __unapply__(self) -> tuple<str, str> | None:
        if '@' in self.address:
            parts = self.address.split('@')
            return (parts[0], parts[1])
        return None

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
'''

PLAIN_STRUCT_SRC = '''struct Email:
    address: str
    alias: str

def classify(e: Email) -> str:
    match e:
        case Email(user, domain):
            return user
        case _:
            return "none"
'''

METHOD_FIRST_SRC = '''struct Shape:
    def area(self) -> int:
        return self.w * self.h

    w: int
    h: int

def describe(s: Shape) -> str:
    match s:
        case Shape(3, 4):
            return "three-four"
        case _:
            return "other"
'''

CLASS_METHOD_SRC = '''class Box:
    def open(self) -> str:
        return "opened"

    def label(self) -> str:
        return "box"

def peek(b: Box) -> str:
    match b:
        case Box(1, 2):
            return "one-two"
        case _:
            return "other"
'''


def parse(source: str):
    return Parser(list(Lexer(source).tokenize())).parse()


def check(source: str):
    checker = TypeChecker()
    checker.check(parse(source))
    return checker


def gen(source: str):
    return CythonGenerator().generate(parse(source))


# ---------------------------------------------------------------- BUG-37 面

def test_positional_binding_takes_slot_type_not_int():
    """`__unapply__ -> tuple<str, str>` 的两个槽位必须是 str，不能是 int 占位。

    观测通道说明：`type_map` 在离开函数作用域后会回收绑定名，所以这里直接问
    `_pattern_slot_types`（单元面 input→expected），端到端那一面由
    `errors == []` 与 `test_wrong_return_type_still_reported` 两格夹住。
    """
    checker = check(EXTRACTOR_SRC)
    assert checker.errors == [], f"有效程序被判错：{checker.errors}"
    slots = checker._pattern_slot_types("Email")
    assert [s.name for s in slots] == ["str", "str"], slots


def test_positional_binding_falls_back_to_field_order_without_extractor():
    """没有 `__unapply__` 时按字段声明顺序给类型（address/alias 都是 str）。"""
    checker = check(PLAIN_STRUCT_SRC)
    assert checker.errors == [], f"有效程序被判错：{checker.errors}"
    slots = checker._pattern_slot_types("Email")
    assert [s.name for s in slots] == ["str", "str"], slots


def test_wrong_return_type_still_reported():
    """反向对照：槽位类型收紧后，真类型错误仍须报出（否则上面两条只是把门拆了）。"""
    source = EXTRACTOR_SRC.replace("def classify(e: Email) -> str:",
                                   "def classify(e: Email) -> int:")
    checker = check(source)
    assert any("Return type mismatch" in e for e in checker.errors), checker.errors


# ---------------------------------------------------------------- BUG-36 面

def test_struct_extractor_is_called_not_phantom_attr():
    code = gen(EXTRACTOR_SRC)
    assert "__unapply__()" in code, "SYNTAX/17 要求 __unapply__ 优先"
    assert ".__f0" not in code and ".__f1" not in code, f"产物仍含幽灵属性访问：{code}"


def test_struct_field_order_drives_positional_pattern():
    code = gen(PLAIN_STRUCT_SRC)
    assert "user = _match_subject_1.address" in code, code
    assert "domain = _match_subject_1.alias" in code, code
    assert ".__f" not in code, code


def test_methods_are_not_positional_fields():
    """方法名混进 fields 时，`case Shape(3, 4)` 会比到绑定方法本身（恒 False 且零诊断）。"""
    generator = CythonGenerator()
    generator.generate(parse(METHOD_FIRST_SRC))
    assert generator._class_fields["Shape"] == ["w", "h"], generator._class_fields
    code = gen(METHOD_FIRST_SRC)
    assert ".area ==" not in code and ".__f0" not in code, code


def test_class_methods_excluded_from_positional_fields():
    generator = CythonGenerator()
    generator.generate(parse(CLASS_METHOD_SRC))
    assert "open" not in generator._class_fields.get("Box", [])
    assert "label" not in generator._class_fields.get("Box", [])


def test_this_file_collects_its_locks():
    import inspect

    collected = [n for n, f in globals().items()
                 if n.startswith("test_") and inspect.isfunction(f)]
    assert len(collected) >= 7, f"只收集到 {len(collected)} 条：{sorted(collected)}"
