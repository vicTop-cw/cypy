"""测试 spawn 并发任务解析"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_spawn_block_form():
    """测试 spawn 块形式解析"""
    source = '''def func():
    spawn:
        printf("running in background")
        compute()'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 检查函数体中有 spawn 语句
    spawn_stmts = [s for s in func_def.body if hasattr(s, 'kind') and s.kind == "SpawnStmt"]
    assert len(spawn_stmts) == 1
    
    spawn_stmt = spawn_stmts[0]
    assert spawn_stmt.target is None
    assert spawn_stmt.args == []
    assert len(spawn_stmt.body) == 2


def test_spawn_call_form():
    """测试 spawn 调用形式解析"""
    source = '''def func():
    spawn background_task(arg1, arg2)'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    spawn_stmts = [s for s in func_def.body if hasattr(s, 'kind') and s.kind == "SpawnStmt"]
    assert len(spawn_stmts) == 1
    
    spawn_stmt = spawn_stmts[0]
    assert spawn_stmt.target is not None
    assert len(spawn_stmt.args) == 2
    assert spawn_stmt.body == []


def test_spawn_expression_form():
    """测试 spawn 作为表达式使用"""
    source = '''def func():
    task = spawn background_task()
    return task'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    assert len(ast.body) == 1
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    
    # 检查是否有 spawn 语句（作为表达式出现在赋值中）
    spawn_exprs = []
    for stmt in func_def.body:
        if hasattr(stmt, 'kind') and stmt.kind == 'Assign':
            if hasattr(stmt.value, 'kind') and stmt.value.kind == 'SpawnStmt':
                spawn_exprs.append(stmt.value)
    assert len(spawn_exprs) == 1


def test_spawn_outside_function_error():
    """测试在函数外使用 spawn 应该报错"""
    source = '''spawn:
    printf("error")'''
    
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    
    with pytest.raises(ValueError, match="spawn must be used inside a function"):
        parser.parse()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
