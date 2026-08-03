"""测试联合类型代码生成功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def _get_generator(source: str) -> CythonGenerator:
    """获取代码生成器并生成代码"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CythonGenerator()
    generator.generate(ast)
    return generator


class TestUnionTypeCodeGen:
    """测试联合类型代码生成"""

    def test_simple_union_type(self):
        """测试简单的联合类型代码生成"""
        source = '''
type Number = int | float

let x: Number = 42
'''
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        # 验证代码生成
        assert 'x' in result
        # 验证联合类型被转换为 object
        assert 'object' in result

    def test_union_type_multiple_types(self):
        """测试多类型联合类型代码生成"""
        source = '''
type Value = int | str | float

let v: Value = "hello"
'''
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        assert 'v' in result
        assert 'object' in result

    def test_union_type_in_function(self):
        """测试函数中的联合类型代码生成"""
        source = '''
type MaybeNumber = int | float

def process(value: MaybeNumber) -> MaybeNumber:
    return value

let result = process(42)
'''
        generator = _get_generator(source)
        result = "\n".join(generator.output)
        assert 'process' in result
        assert 'object' in result


class TestUnionTypeWithTypeChecker:
    """测试联合类型与类型检查器的集成"""

    def test_union_type_checking(self):
        """测试联合类型的类型检查"""
        source = '''
type Number = int | float

let x: Number = 42
let y: Number = 3.14
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()
        checker = TypeChecker()
        checker.check(ast)
        
        # 应该没有错误
        assert len(checker.errors) == 0, f"Type check errors: {checker.errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
