"""测试 TypeClass 代码生成功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, TypeClassDef, TypeClassImpl
from cypyc.codegen.cython_generator import CythonGenerator


def _parse_source(source: str):
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    return parser.parse()


def _generate_code(source: str) -> str:
    ast = _parse_source(source)
    generator = CythonGenerator("test.py")
    return generator.generate(ast)


class TestTypeClassCodeGen:
    """测试 TypeClass 代码生成"""

    def test_typeclass_def_generates_cdef_class(self):
        """测试 TypeClass 定义生成 cdef class"""
        source = '''
typeclass Show:
    def show(self) -> str
'''
        output = _generate_code(source)
        assert "cdef class Show" in output
        assert "cpdef str show" in output
        assert "NotImplementedError" in output

    def test_typeclass_impl_generates_wrapper(self):
        """测试 TypeClass 实现生成包装类"""
        source = '''
typeclass Show:
    def show(self) -> str

struct Point:
    x: float

impl typeclass Show for Point:
    def show(self) -> str:
        return str(self.x)
'''
        output = _generate_code(source)
        assert "cdef class Show" in output
        assert "TypeClass_Show_impl_Point" in output
        assert "cpdef str show" in output

    def test_typeclass_with_generics_codegen(self):
        """测试带泛型的 TypeClass 代码生成"""
        source = '''
typeclass Container<T>:
    def get(self) -> T
    def put(self, value: T) -> None
'''
        output = _generate_code(source)
        assert "cdef class Container" in output
        assert "cpdef T get" in output
        assert "cpdef None put" in output

    def test_multiple_typeclass_codegen(self):
        """测试多个 TypeClass 的代码生成"""
        source = '''
typeclass Show:
    def show(self) -> str

typeclass Eq:
    def eq(self, other: object) -> bool
'''
        output = _generate_code(source)
        assert "cdef class Show" in output
        assert "cdef class Eq" in output
        assert "cpdef str show" in output
        assert "cpdef bool eq" in output
