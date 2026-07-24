"""测试新关键字和特性的词法分析"""

import pytest
from cypyc.parser.lexer import Lexer, TokenType


def test_new_keywords_recognized():
    """测试新关键字能被正确识别"""
    source = "guard macro comptime spawn go case vec"
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    
    token_types = [t.type for t in tokens if t.type != TokenType.NEWLINE]
    
    assert TokenType.GUARD in token_types
    assert TokenType.MACRO in token_types
    assert TokenType.COMPTIME in token_types
    assert TokenType.SPAWN in token_types
    assert TokenType.GO in token_types
    assert TokenType.CASE in token_types
    assert TokenType.VEC in token_types


def test_fat_arrow():
    """测试 => 符号能被正确识别"""
    source = "case 1 => 2"
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    
    token_types = [t.type for t in tokens if t.type != TokenType.NEWLINE]
    
    assert TokenType.FAT_ARROW in token_types


def test_triple_backtick():
    """测试三反引号代码块能被正确解析"""
    source = '```print("hello")```'
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    
    backtick_tokens = [t for t in tokens if t.type == TokenType.BACKTICK_BLOCK]
    assert len(backtick_tokens) == 1
    assert backtick_tokens[0].value == 'print("hello")'


def test_triple_backtick_multiline():
    """测试多行三反引号代码块"""
    source = '''```
def foo():
    return 1
```'''
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    
    backtick_tokens = [t for t in tokens if t.type == TokenType.BACKTICK_BLOCK]
    assert len(backtick_tokens) == 1
    expected = 'def foo():\n    return 1'
    assert backtick_tokens[0].value == expected


def test_new_keywords_in_context():
    """测试新关键字在实际代码上下文中的识别"""
    source = '''def test_guard():
    guard x != 0 else None
    return x

macro hello()->Tokens = return ```print("hello")```

comptime:
    FIB_10 = 55

h = spawn:
    expensive()

go async_func()

match x:
    case 1 => "one"
    case 2 => "two"

v = vec[int, 4]()'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    
    token_types = [t.type for t in tokens]
    
    assert TokenType.GUARD in token_types
    assert TokenType.MACRO in token_types
    assert TokenType.COMPTIME in token_types
    assert TokenType.SPAWN in token_types
    assert TokenType.GO in token_types
    assert TokenType.CASE in token_types
    assert TokenType.VEC in token_types
    assert TokenType.FAT_ARROW in token_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
