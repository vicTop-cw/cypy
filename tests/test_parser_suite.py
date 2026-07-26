"""测试 suite 和 test 关键字语法解析（参照 lang-zone/hermes 设计）"""

from cypyc.parser.parser import Parser
from cypyc.parser.lexer import Lexer


def test_suite_basic():
    """测试基本的 suite 语法"""
    source = '''suite MathTests:
    test add_positive_numbers:
        assert 1 + 1 == 2'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    suite_def = ast.body[0]
    assert suite_def.kind == "SuiteDef"
    assert suite_def.name == "MathTests"
    assert len(suite_def.body) == 1
    
    test_def = suite_def.body[0]
    assert test_def.kind == "TestDef"
    assert test_def.name == "add_positive_numbers"


def test_suite_with_multiple_tests():
    """测试包含多个测试用例的 suite"""
    source = '''suite MathTests:
    test add:
        assert 1 + 2 == 3
    
    test subtract:
        assert 5 - 3 == 2
    
    test multiply:
        assert 2 * 3 == 6'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    suite_def = ast.body[0]
    assert suite_def.kind == "SuiteDef"
    assert len(suite_def.body) == 3
    
    test_names = [t.name for t in suite_def.body if t.kind == "TestDef"]
    assert test_names == ["add", "subtract", "multiply"]


def test_suite_with_setup_teardown():
    """测试包含 setup 和 teardown 的 suite"""
    source = '''suite DatabaseTests:
    setup:
        print("Connecting to database")
    
    test query_users:
        assert True
    
    teardown:
        print("Disconnecting from database")'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    suite_def = ast.body[0]
    assert suite_def.kind == "SuiteDef"
    
    # 检查 setup、test、teardown 的顺序
    assert suite_def.body[0].kind == "SetupStmt"
    assert suite_def.body[1].kind == "TestDef"
    assert suite_def.body[1].name == "query_users"
    assert suite_def.body[2].kind == "TeardownStmt"


def test_standalone_test():
    """测试独立的 test 语法（不在 suite 中）"""
    source = '''test simple_assert:
    assert True'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    test_def = ast.body[0]
    assert test_def.kind == "TestDef"
    assert test_def.name == "simple_assert"


def test_suite_nested_tests():
    """测试 suite 中测试用例的嵌套语句"""
    source = '''suite LogicTests:
    test conditional_logic:
        if True:
            assert True
        else:
            assert False
    
    test loop_test:
        for i in range(3):
            assert i < 3'''

    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()

    suite_def = ast.body[0]
    assert suite_def.kind == "SuiteDef"
    assert len(suite_def.body) == 2
    
    # 验证第一个测试有 if 语句
    first_test = suite_def.body[0]
    assert first_test.kind == "TestDef"
    assert first_test.body[0].kind == "IfStmt"
    
    # 验证第二个测试有 for 语句
    second_test = suite_def.body[1]
    assert second_test.kind == "TestDef"
    assert second_test.body[0].kind == "ForStmt"
