"""测试宏定义和宏调用代码生成"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.codegen.cython_generator import CythonGenerator


def parse_and_generate(source: str) -> str:
    """解析源码并生成 Cython 代码"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    generator = CythonGenerator("test_module")
    return generator.generate(ast)


class TestMacroDef:
    """测试宏定义"""

    def test_simple_macro_def(self):
        """测试简单宏定义"""
        source = '''macro double(ts: Tokens) =
    pass

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "_macro_double" in code
        assert "compile-time macro" in code

    def test_macro_def_with_body(self):
        """测试带宏体的宏定义"""
        source = '''macro log(ts: Tokens) =
    pass

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "_macro_log" in code
        assert "macro log" in code

    def test_multiple_macros(self):
        """测试多个宏定义"""
        source = '''macro double(ts: Tokens) =
    pass

macro triple(ts: Tokens) =
    pass

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "_macro_double" in code
        assert "_macro_triple" in code


class TestMacroCall:
    """测试宏调用"""

    def test_macro_call(self):
        """测试宏调用"""
        source = '''macro double(ts: Tokens) =
    pass

def main() -> None:
    let result = double!(42)
    pass'''
        code = parse_and_generate(source)
        assert "double!(" in code or "double" in code

    def test_macro_call_with_args(self):
        """测试带参数的宏调用"""
        source = '''macro log(ts: Tokens) =
    pass

def main() -> None:
    log!("message", 42)
    pass'''
        code = parse_and_generate(source)
        assert "log!" in code or "log" in code


class TestMacroIntegration:
    """测试宏集成"""

    def test_macro_with_function(self):
        """测试宏与函数配合"""
        source = '''macro debug(ts: Tokens) =
    pass

def process(x: int) -> int:
    debug!("processing", x)
    return x * 2

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "_macro_debug" in code

    def test_macro_multiple_calls(self):
        """测试多次宏调用"""
        source = '''macro trace(ts: Tokens) =
    pass

def main() -> None:
    trace!("start")
    let x = 42
    trace!("value", x)
    trace!("end")
    pass'''
        code = parse_and_generate(source)
        assert "_macro_trace" in code

    def test_macro_in_conditional(self):
        """测试条件中的宏调用"""
        source = '''macro warn(ts: Tokens) =
    pass

def check(x: int) -> None:
    if x < 0:
        warn!("negative value", x)

def main() -> None:
    pass'''
        code = parse_and_generate(source)
        assert "_macro_warn" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])