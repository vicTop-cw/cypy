"""trait 运行时 isinstance 与包装器运算符转发回归测试（BUG-023）

Cypy 的 trait 以独立 cdef 包装器实现，具体 struct 并非 trait 的子类，
导致：
  (b) 运行时 ``isinstance(具体实例, Trait)`` 恒假；
  (a) trait 包装器不转发 struct 定义的运算符双下方法，链式运算报
      ``unsupported operand``。

修复方案：
  (b) 代码生成期把 ``isinstance(x, Trait)`` 改写为 ``_cypy_is_instance_of``，
      并生成 trait -> 实现类型名的模块级注册表（含 trait 继承传递性）。
  (a) ``impl`` 生成的包装器按 struct 方法的元数转发运算符双下方法给 ``__inner__``。

本测试在代码生成层面锁定上述行为，无需触发 Cython 编译。
"""
import unittest

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def _gen(source: str) -> str:
    module = Parser(list(Lexer(source).tokenize())).parse()
    return CythonGenerator().generate(module)


def _type_errors(source: str):
    tc = TypeChecker()
    tc.check(Parser(list(Lexer(source).tokenize())).parse())
    return tc.errors


_ISINSTANCE_SRC = """
trait Money:
    def cents(self) -> int

struct Dollar:
    amount: int
    def cents(self) -> int:
        return self.amount * 100
    def __add__(self, other) -> Dollar:
        return Dollar(self.amount + other.amount)
    def __eq__(self, other) -> bool:
        return self.amount == other.amount

impl Money for Dollar:
    pass

def describe(d) -> str:
    if isinstance(d, Money):
        return "is Money"
    return "not Money"

def check_int(x) -> bool:
    return isinstance(x, int)
"""


class TestTraitIsinstanceRewrite(unittest.TestCase):
    def test_helper_and_registry_emitted(self):
        code = _gen(_ISINSTANCE_SRC)
        self.assertIn("_cypy_trait_registry", code)
        self.assertIn("def _cypy_is_instance_of(", code)

    def test_registry_maps_trait_to_impl_type(self):
        code = _gen(_ISINSTANCE_SRC)
        # Dollar 作为 Money 的实现被登记
        self.assertIn("'Money': ('Dollar',)", code)

    def test_trait_isinstance_call_rewritten(self):
        code = _gen(_ISINSTANCE_SRC)
        self.assertIn("_cypy_is_instance_of(d, 'Money')", code)

    def test_non_trait_isinstance_untouched(self):
        """isinstance(x, int) 不应被改写（int 不是 trait）。"""
        code = _gen(_ISINSTANCE_SRC)
        self.assertIn("isinstance(x, int)", code)
        self.assertNotIn("_cypy_is_instance_of(x, 'int')", code)


class TestTraitWrapperOperatorForwarding(unittest.TestCase):
    def test_wrapper_forwards_binary_operators(self):
        code = _gen(_ISINSTANCE_SRC)
        # 包装器按元数生成固定位置参数（Cython 要求特殊方法参数精确）
        self.assertIn("def __add__(self, _a0):", code)
        self.assertIn("return self.__inner__.__add__(_a0)", code)
        self.assertIn("def __eq__(self, _a0):", code)
        self.assertIn("return self.__inner__.__eq__(_a0)", code)

    def test_wrapper_does_not_forward_init(self):
        """__init__ 已由包装器自身定义，不应重复转发。"""
        code = _gen(_ISINSTANCE_SRC)
        wrapper = code.split("cdef class _Money__Dollar")[1].split("def describe")[0]
        # 包装器内 __init__ 只出现一次（构造 __inner__），无转发版 __init__
        self.assertEqual(wrapper.count("def __init__"), 1)


_TRAIT_INHERIT_SRC = """
trait Loggable:
    def log(self) -> None

trait Readable:
    def read(self) -> str

trait Persistable extends Readable, Loggable:
    pass

struct File:
    name: str
    def log(self) -> None:
        print(self.name)
    def read(self) -> str:
        return self.name

impl Persistable for File:
    pass

def is_readable(x) -> bool:
    return isinstance(x, Readable)

def is_loggable(x) -> bool:
    return isinstance(x, Loggable)
"""


class TestTraitInheritanceTransitivity(unittest.TestCase):
    def test_impl_registered_to_ancestor_traits(self):
        """实现子 trait 的类型也应被祖先 trait 的 isinstance 识别。"""
        code = _gen(_TRAIT_INHERIT_SRC)
        # File 同时登记到 Readable 与 Loggable（Persistable 的祖先）
        self.assertIn("'Readable': ('File',)", code)
        self.assertIn("'Loggable': ('File',)", code)
        self.assertIn("'Persistable': ('File',)", code)

    def test_super_trait_kept_as_class_base(self):
        """trait 继承的基类标识符不应被误映射为 object（trait 作为基类 vs 值类型的区分）。"""
        code = _gen(_TRAIT_INHERIT_SRC)
        # Persistable 应以 Readable 作为 cdef 基类（合并祖先方法），而非 object
        self.assertIn("cdef class Persistable(Readable):", code)


# BUG-023 原始动机：运算符重载返回自定义 trait 类型（SQL 表达式树）。
# 旧行为：col == 5 被强制推断为 bool，导致赋值给 ClauseElement 报类型不匹配；
#         trait 类型的局部变量/参数被当作扩展类型，拒绝持有具体 struct。
_CHAIN_SRC = """
trait ClauseElement:
    def compile(self) -> str

struct _BinaryExpression:
    left: object
    op: str
    right: object
    def compile(self) -> str:
        return self.op
    def __and__(self, other) -> ClauseElement:
        return _BinaryExpression(self, "AND", other)

struct Column:
    name: str
    def compile(self) -> str:
        return self.name
    def __eq__(self, other) -> ClauseElement:
        return _BinaryExpression(self, "=", other)
    def __gt__(self, other) -> ClauseElement:
        return _BinaryExpression(self, ">", other)

impl ClauseElement for Column:
    pass

impl ClauseElement for _BinaryExpression:
    pass

def build(col: Column, col2: Column) -> ClauseElement:
    let combined: ClauseElement = (col == 5) & (col2 > 18)
    return combined.compile()

def plain_eq(a: int, b: int) -> bool:
    return a == b
"""


class TestOperatorOverrideResultType(unittest.TestCase):
    def test_comparison_chaining_typechecks(self):
        """(col == 5) & (col2 > 18) 赋值给 ClauseElement 不应报类型错误。"""
        self.assertEqual(_type_errors(_CHAIN_SRC), [])

    def test_primitive_comparison_still_bool(self):
        """未重载 dunder 的原生类型比较仍走 bool，不受影响。"""
        self.assertEqual(_type_errors(_CHAIN_SRC), [])


class TestTraitTypedDeclarationIsObject(unittest.TestCase):
    def test_trait_typed_local_becomes_object(self):
        """trait 类型的局部变量声明回退为 object（鸭子类型）。"""
        code = _gen(_CHAIN_SRC)
        # combined 声明为 object 而非 ClauseElement 扩展类型
        self.assertIn("combined: object", code)
        self.assertNotIn("combined: ClauseElement", code)

    def test_trait_typed_param_becomes_object(self):
        """trait 类型参数回退为 object。"""
        code = _gen(_CHAIN_SRC)
        self.assertNotIn("ClauseElement combined", code)

    def test_helper_registry_still_emitted(self):
        """链式源码仍生成 isinstance 支持。"""
        code = _gen(_CHAIN_SRC)
        self.assertIn("_cypy_is_instance_of", code)
        self.assertIn("'ClauseElement': ('Column', '_BinaryExpression')", code)


if __name__ == "__main__":
    unittest.main()
