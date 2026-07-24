"""测试 async/await 代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_bridge.compiler import CCodeGenerator


def test_async_func_codegen():
    """测试 async 函数代码生成"""
    source = '''async def fetch_data(url: str) -> str:
    result = await get(url)
    return result'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证协程结构体和状态机框架
    assert "_fetch_data_Coroutine" in c_code
    assert "PyObject_HEAD" in c_code
    assert "_coro_state" in c_code
    assert "_finished" in c_code
    assert "switch(coro->_coro_state)" in c_code
    assert "case 0:" in c_code
    assert "case 1:" in c_code
    assert "fetch_data_create" in c_code
    assert "fetch_data_resume" in c_code
    assert "PyExc_StopAsyncIteration" in c_code


def test_async_func_with_multiple_await():
    """测试包含多个await的async函数"""
    source = '''async def process():
    a = await task1()
    b = await task2(a)
    return a + b'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证多个await生成多个case
    assert "_process_Coroutine" in c_code
    assert "case 0:" in c_code
    assert "case 1:" in c_code
    assert "case 2:" in c_code
    # 验证await关键字被正确处理
    assert "// await" in c_code


if __name__ == "__main__":
    test_async_func_codegen()
    print("test_async_func_codegen passed")
    
    test_async_func_with_multiple_await()
    print("test_async_func_with_multiple_await passed")
    
    print("All tests passed!")
