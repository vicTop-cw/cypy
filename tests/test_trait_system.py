import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cypyc.parser import Parser, Lexer
from cypyc.parser.parser import get_ast_cache
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def test_basic_trait_definition():
    """测试基本特质定义"""
    source = "trait Printable:\n    def print(self) -> None:\n        pass"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    assert 'Printable' in type_checker.trait_defs
    assert 'Printable' in type_checker.type_map
    print("✓ test_basic_trait_definition passed")


def test_trait_with_default_impl():
    """测试带默认实现的特质"""
    source = "trait Comparable<T>:\n    def compare(self, other: T) -> int:\n        pass\n    def equals(self, other: T) -> bool:\n        return False"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    assert 'Comparable' in type_checker.trait_defs
    assert 'T' in type_checker.type_map
    print("✓ test_trait_with_default_impl passed")


def test_trait_inheritance():
    """测试特质继承"""
    source = "trait Readable:\n    def read(self) -> str:\n        pass\n\ntrait Writable:\n    def write(self, data: str) -> None:\n        pass\n\ntrait ReadWrite extends Readable, Writable:\n    pass"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    assert 'ReadWrite' in type_checker.trait_defs
    trait = type_checker.trait_defs['ReadWrite']
    assert len(trait.super_traits) == 2
    print("✓ test_trait_inheritance passed")


def test_trait_implementation():
    """测试特质实现"""
    source = "trait Printable:\n    def print(self) -> None:\n        pass\n\nstruct Point:\n    x: int\n    y: int\n\nimpl Printable for Point:\n    def print(self) -> None:\n        print(f\"Point: ({self.x}, {self.y})\")"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    assert 'Point' in type_checker.trait_impls.get('Printable', [])
    print("✓ test_trait_implementation passed")


def test_generic_trait_implementation():
    """测试泛型特质实现"""
    source = "trait Container<T>:\n    def add(self, item: T) -> None:\n        pass\n    def size(self) -> int:\n        pass\n\nstruct List<T>:\n    items: list<T>\n\nimpl Container<T> for List<T>:\n    def add(self, item: T) -> None:\n        self.items.append(item)\n    def size(self) -> int:\n        return len(self.items)"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    assert 'Container' in type_checker.trait_defs
    print("✓ test_generic_trait_implementation passed")


def test_missing_method_implementation():
    """测试缺少方法实现的错误检测"""
    source = "trait Printable:\n    def print(self) -> None:\n        pass\n    def format(self) -> str:\n        pass\n\nstruct Point:\n    x: int\n    y: int\n\nimpl Printable for Point:\n    def print(self) -> None:\n        print(f\"Point: ({self.x}, {self.y})\")"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 1
    assert 'missing method' in type_checker.errors[0]
    assert 'format' in type_checker.errors[0]
    print("✓ test_missing_method_implementation passed")


def test_wrong_parameter_count():
    """测试参数数量错误的检测"""
    source = "trait Printable:\n    def print(self, prefix: str) -> None:\n        pass\n\nstruct Point:\n    x: int\n    y: int\n\nimpl Printable for Point:\n    def print(self) -> None:\n        print(f\"Point: ({self.x}, {self.y})\")"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 1
    assert 'wrong number of parameters' in type_checker.errors[0]
    print("✓ test_wrong_parameter_count passed")


def test_return_type_mismatch():
    """测试返回类型不匹配的检测"""
    source = "trait Printable:\n    def format(self) -> str:\n        pass\n\nstruct Point:\n    x: int\n    y: int\n\nimpl Printable for Point:\n    def format(self) -> int:\n        return 42"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 1
    assert 'Return type mismatch' in type_checker.errors[0]
    print("✓ test_return_type_mismatch passed")


def test_trait_as_type_annotation():
    """测试特质作为类型注解"""
    source = "trait Logger:\n    def log(self, message: str) -> None:\n        pass\n\nstruct ConsoleLogger:\n    pass\n\nimpl Logger for ConsoleLogger:\n    def log(self, message: str) -> None:\n        print(f\"[LOG] {message}\")\n\ndef process(data: str, logger: Logger) -> None:\n    logger.log(f\"Processing: {data}\")"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    print("✓ test_trait_as_type_annotation passed")


def test_generic_constraint_with_trait():
    """测试泛型特质约束"""
    source = "trait Comparable:\n    def compare(self, other: object) -> int:\n        pass\n\ndef compare_items<T: Comparable>(a: T, b: T) -> int:\n    return 0"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    assert len(type_checker.errors) == 0, f"Type checker errors: {type_checker.errors}"
    print("✓ test_generic_constraint_with_trait passed")


def test_cython_generation_trait():
    """测试 Cython 代码生成"""
    source = "trait Printable:\n    def print(self) -> None:\n        pass\n\nstruct Point:\n    x: int\n    y: int\n\nimpl Printable for Point:\n    def print(self) -> None:\n        print(f\"Point: ({self.x}, {self.y})\")"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator("test_trait.cypy")
    cython_code = generator.generate(ast)
    
    assert 'cdef class Printable' in cython_code
    assert 'cdef void** __vtable__' in cython_code
    assert '_Printable__Point' in cython_code
    print("✓ test_cython_generation_trait passed")


if __name__ == "__main__":
    print("Running trait system tests...\n")
    
    tests = [
        test_basic_trait_definition,
        test_trait_with_default_impl,
        test_trait_inheritance,
        test_trait_implementation,
        test_generic_trait_implementation,
        test_missing_method_implementation,
        test_wrong_parameter_count,
        test_return_type_mismatch,
        test_trait_as_type_annotation,
        test_generic_constraint_with_trait,
        test_cython_generation_trait,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)