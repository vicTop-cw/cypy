"""测试 async/await 语法解析"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser


def test_async_func_def():
    """测试 async 函数定义"""
    source = '''async def fetch_data(url: str) -> str:
    result = await get(url)
    return result'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    # 验证 AST 结构
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.name == "fetch_data"
    assert func_def.is_async == True
    assert len(func_def.params) == 1
    assert func_def.params[0].name == "url"
    
    # 验证 await 表达式
    await_expr = func_def.body[0].value
    print(f"DEBUG: await_expr = {await_expr}")
    print(f"DEBUG: await_expr.kind = {await_expr.kind}")
    assert await_expr.kind == "AwaitExpr"
    assert await_expr.value.kind == "Call"
    assert await_expr.value.func.id == "get"


def test_async_func_with_yield():
    """测试 async 函数中的 yield（协程生成器）"""
    source = '''async def async_generator():
    for i in range(5):
        await async_sleep(1)
        yield i'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    func_def = ast.body[0]
    assert func_def.kind == "FuncDef"
    assert func_def.name == "async_generator"
    assert func_def.is_async == True


if __name__ == "__main__":
    test_async_func_def()
    print("test_async_func_def passed")
    
    test_async_func_with_yield()
    print("test_async_func_with_yield passed")
    
    print("All tests passed!")
