"""测试构建块语法(~: 和 *:)解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, BuildBlockExpr


def test_build_call_simple():
    """测试调用构建块 ~: - x = callee ~: 块体"""
    source = '''def test():
    x = make_point ~:
        (1, 2)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert len(func_def.body) == 1
    
    assign = func_def.body[0]
    assert assign.kind == "Assign"
    assert assign.target.id == "x"
    
    # 验证调用表达式
    call = assign.value
    assert call.kind == "Call"
    assert call.func.id == "make_point"
    assert len(call.args) == 1
    
    # 验证构建块
    build_block = call.args[0]
    assert isinstance(build_block, BuildBlockExpr)
    assert build_block.block_type == BuildBlockExpr.BUILD_CALL


def test_build_call_with_multiple_statements():
    """测试调用构建块 ~: 包含多个语句"""
    source = '''def test():
    result = add ~:
        a = 1
        b = 2
        (a, b)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    assign = func_def.body[0]
    call = assign.value
    
    assert call.kind == "Call"
    assert call.func.id == "add"
    
    build_block = call.args[0]
    assert isinstance(build_block, BuildBlockExpr)
    assert len(build_block.body) == 3  # 3个语句


def test_build_gen_simple():
    """测试生成器构建块 *: - x = callee *: 块体"""
    source = '''def test():
    gen = make *:
        yield (1,)
        yield (2,)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    assign = func_def.body[0]
    assert assign.kind == "Assign"
    assert assign.target.id == "gen"
    
    # 验证调用表达式
    call = assign.value
    assert call.kind == "Call"
    assert call.func.id == "make"
    
    # 验证构建块
    build_block = call.args[0]
    assert isinstance(build_block, BuildBlockExpr)
    assert build_block.block_type == BuildBlockExpr.BUILD_GEN


def test_build_gen_with_return():
    """测试生成器构建块 *: 包含return"""
    source = '''def test():
    gen = make *:
        return (1,)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    func_def = ast.body[0]
    assign = func_def.body[0]
    call = assign.value
    
    assert call.kind == "Call"
    build_block = call.args[0]
    assert isinstance(build_block, BuildBlockExpr)
    assert build_block.block_type == BuildBlockExpr.BUILD_GEN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])