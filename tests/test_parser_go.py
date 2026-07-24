"""测试 go 轻量级协程解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_go_block_form():
    """测试 go 块形式解析"""
    source = '''def func():
    go:
        printf("running in goroutine")
        process()'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 检查函数体中有 go 语句
    go_stmts = [s for s in func_def.body if hasattr(s, 'kind') and s.kind == "GoStmt"]
    assert len(go_stmts) == 1
    
    go_stmt = go_stmts[0]
    assert go_stmt.target is None
    assert go_stmt.args == []
    assert len(go_stmt.body) == 2


def test_go_call_form():
    """测试 go 调用形式解析"""
    source = '''def func():
    go coroutine_task(arg1, arg2)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    go_stmts = [s for s in func_def.body if hasattr(s, 'kind') and s.kind == "GoStmt"]
    assert len(go_stmts) == 1
    
    go_stmt = go_stmts[0]
    assert go_stmt.target is not None
    assert len(go_stmt.args) == 2
    assert go_stmt.body == []


def test_go_expression_form():
    """测试 go 作为表达式使用"""
    source = '''def func():
    task = go coroutine_task()
    return task'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 检查是否有 go 语句（作为表达式出现在赋值中）
    go_exprs = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'GoStmt':
                go_exprs.append(stmt.value)
    assert len(go_exprs) == 1


def test_go_outside_function_error():
    """测试在函数外使用 go 应该报错"""
    source = '''go:
    printf("error")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    
    with pytest.raises(ValueError, match="go must be used inside a function"):
        parser.parse()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
