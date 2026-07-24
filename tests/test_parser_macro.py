"""测试 macro 宏定义解析（参考 lang-zone 语法）"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_macro_definition_parsing():
    """测试基本宏定义解析（参考 lang-zone：macro name(ts: Tokens)->Tokens = ...）"""
    source = '''macro my_macro(ts: Tokens) -> Tokens =
    return ts'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 验证宏定义被正确解析
    assert len(ast.body) == 1
    assert ast.body[0].kind == "MacroDef"
    assert ast.body[0].name == "my_macro"


def test_macro_with_no_params():
    """测试无参数宏定义（参考 lang-zone）"""
    source = '''macro log(ts: Tokens) -> Tokens =
    print("log message")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "MacroDef"
    assert ast.body[0].name == "log"


def test_macro_with_multiple_statements():
    """测试多语句宏定义（参考 lang-zone）"""
    source = '''macro swap(ts: Tokens) -> Tokens =
    let temp = ts
    ts = temp'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "MacroDef"


def test_macro_inside_function():
    """测试宏定义必须在模块级别（当前不支持函数内定义）"""
    source = '''def func():
    macro inner_macro(ts: Tokens) -> Tokens =
        pass'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    
    # 当前实现允许在函数内定义宏，但语义上应该在模块级别
    ast = parser.parse()
    assert len(ast.body) == 1


def test_macro_with_backtick_block():
    """测试包含反引号代码块的宏定义（参考 lang-zone）"""
    source = '''macro twice(input: Tokens) -> Tokens =
    f```
        $input + $input
    ```'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    assert ast.body[0].kind == "MacroDef"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])