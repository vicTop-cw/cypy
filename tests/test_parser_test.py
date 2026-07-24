"""测试 @test 装饰器和 assert 语句解析"""

from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer


def test_assert_simple():
    """测试 assert 简单表达式"""
    source = '''def test():
    assert 1 + 1 == 2'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.body) == 1

    assert_stmt = func_def.body[0]
    assert assert_stmt.kind == "AssertStmt"
    assert assert_stmt.msg is None


def test_assert_with_message():
    """测试 assert 带错误消息"""
    source = '''def test():
    assert x > 0, "x must be positive"'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert_stmt = func_def.body[0]
    assert assert_stmt.kind == "AssertStmt"
    assert assert_stmt.msg is not None


def test_test_decorator():
    """测试 @test 装饰器"""
    source = '''@test
def test_add():
    assert 1 + 1 == 2'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.name == "test_add"
    assert len(func_def.decorators) == 1
    
    decorator = func_def.decorators[0]
    assert decorator.kind == "Decorator"
    assert decorator.name.id == "test"
    assert len(decorator.args) == 0


def test_test_decorator_with_args():
    """测试 @test(should_fail) 装饰器带参数"""
    source = '''@test(should_fail)
def test_should_fail():
    assert 1 == 2'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.decorators) == 1
    
    decorator = func_def.decorators[0]
    assert decorator.kind == "Decorator"
    # name 已经被提取为 Name 节点，args 包含装饰器参数
    assert decorator.name.id == "test"
    assert len(decorator.args) == 1


def test_multiple_decorators():
    """测试多个装饰器"""
    source = '''@test
@timeout(1000)
def test_fast():
    assert True'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.decorators) == 2
    
    # 第一个装饰器 @test 不带参数
    assert func_def.decorators[0].name.id == "test"
    # 第二个装饰器 @timeout(1000) 带参数，name 已经被提取为 Name 节点
    assert func_def.decorators[1].name.id == "timeout"
    assert len(func_def.decorators[1].args) == 1


def test_decorator_on_function_with_generic():
    """测试带泛型参数的函数上的装饰器"""
    source = '''@test
def test_generic[T]():
    assert True'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.name == "test_generic"
    assert len(func_def.decorators) == 1
    assert func_def.generic_params == ["T"]
