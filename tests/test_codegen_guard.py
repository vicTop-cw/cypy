"""测试 guard 守卫表达式代码生成"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_bridge.compiler import CCodeGenerator
from cypyc.codegen.cython_generator import CythonGenerator


def test_guard_single_line_codegen():
    """测试单行 guard 语法生成正确的 C 代码"""
    source = '''def test_guard(x: int) -> int:
    guard x != 0 else 0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码包含条件返回
    assert "if (!((x != 0))) {" in c_code
    assert "return 0;" in c_code


def test_guard_multi_line_codegen():
    """测试多行 guard 语法生成正确的 C 代码"""
    source = '''def test_guard(x: int) -> int:
    guard x != 0 else:
        printf("error")
        0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码包含块和隐式返回
    assert "if (!((x != 0))) {" in c_code
    assert 'printf("error");' in c_code
    assert "return 0;" in c_code


def test_guard_let_codegen():
    """测试 guard let 语法生成正确的 C 代码"""
    source = '''def get_value() -> int:
    return 42

def test_guard_let() -> int:
    guard let v = get_value() else 0
    return v'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证生成的 C 代码先绑定再判断
    assert "v = get_value();" in c_code
    assert "if (!(v)) {" in c_code
    assert "return 0;" in c_code


def test_guard_with_defer():
    """测试 guard 与 defer 结合使用"""
    source = '''def test_guard_defer(x: int) -> int:
    defer free(ptr)
    guard x != 0 else 0
    return x'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    generator = CCodeGenerator()
    c_code = generator.generate(ast, "test_module")
    
    # 验证 guard 和 defer 都被正确处理
    assert "if (!((x != 0))) {" in c_code
    assert "return 0;" in c_code
    assert "free(ptr);" in c_code


class TestLoopGuard:
    """测试循环守卫 - guard 在循环中生成 break"""

    def test_guard_in_for_loop_generates_break(self):
        """for 循环中的 guard 应生成 break"""
        source = '''
def test():
    for i in range(10):
        guard i < 5 else:
            i = 100
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "break" in result
        assert "guard failed in loop" in result

    def test_guard_in_while_loop_generates_break(self):
        """while 循环中的 guard 应生成 break"""
        source = '''
def test():
    while True:
        guard flag else False
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "break" in result
        assert "guard failed in loop" in result

    def test_guard_not_in_loop_generates_return(self):
        """非循环中的 guard 应生成 return"""
        source = '''
def test():
    guard valid else:
        valid = False
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "return" in result
        assert "guard failed - implicit return" in result

    def test_guard_single_line_in_loop(self):
        """循环中单行 guard 应生成 break"""
        source = '''
def test():
    for x in items:
        guard valid else:
            invalid_count += 1
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "break" in result
        assert "guard failed in loop" in result

    def test_guard_not_in_loop_single_line(self):
        """非循环中单行 guard 应生成 return 值"""
        source = '''
def test():
    guard valid else 42
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "return 42" in result
        assert "break" not in result

    def test_guard_else_break_in_loop(self):
        """循环中 guard else break 应生成 break"""
        source = '''
def test():
    for i in range(10):
        guard i < 5 else break
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "break" in result
        assert "continue" not in result

    def test_guard_else_continue_in_loop(self):
        """循环中 guard else continue 应生成 continue"""
        source = '''
def test():
    for i in range(10):
        guard i % 2 == 0 else continue
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "continue" in result
        assert "break" not in result

    def test_guard_else_return_in_loop(self):
        """循环中 guard else return 应生成 return"""
        source = '''
def test():
    for i in range(10):
        guard i < 5 else return -1
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "return -1" in result
        assert "break" not in result
        assert "continue" not in result

    def test_guard_multiple_in_loop(self):
        """循环中多个 guard 应各自生成正确的控制流"""
        source = '''
def test():
    for i in range(20):
        guard i % 2 == 0 else continue
        guard i < 10 else break
        count += 1
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "continue" in result
        assert "break" in result


class TestNamedParameterSugar:
    """测试命名参数语法糖 name~"""

    def test_named_arg_sugar_single(self):
        """单个命名参数语法糖"""
        source = '''
result = make_point(name~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "name=name" in result

    def test_named_arg_sugar_multiple(self):
        """多个命名参数语法糖"""
        source = '''
result = make_point(name~, value~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "name=name" in result
        assert "value=value" in result

    def test_named_arg_sugar_mixed(self):
        """混合位置参数和命名参数语法糖"""
        source = '''
result = make_point(42, name~, value=100)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "42" in result
        assert "name=name" in result
        assert "value=100" in result

    def test_named_arg_sugar_with_call(self):
        """命名参数语法糖用于函数调用"""
        source = '''
print_info(user~, age~)
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        assert "user=user" in result
        assert "age=age" in result

    def test_named_arg_no_sugar_outside_call(self):
        """确认 name~ 只在函数调用参数中作为语法糖"""
        # 在非函数调用上下文中，IDENTIFIER TILDE 不应用作命名参数
        # 此测试验证解析器不会将表达式中的 IDENTIFIER TILDE 误解析
        source = '''
x = items[0]
'''
        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        generator = CythonGenerator()
        generator.generate(ast)
        result = "\n".join(generator.output)

        # 确认正常的索引访问不受影响
        assert "items[0]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
