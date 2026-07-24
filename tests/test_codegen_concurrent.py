"""测试 spawn/go 并发代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_bridge.compiler import CCodeGenerator


def test_spawn_expr_codegen():
    """测试 spawn 表达式代码生成"""
    source = '''def worker(id: int):
    print(id)

def main():
    spawn worker(1)
    spawn worker(2)'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    # 调试：检查AST结构
    print("=== AST structure ===")
    for i, stmt in enumerate(ast.body):
        print(f"  {i}: {stmt.kind} - {stmt.name if hasattr(stmt, 'name') else ''}")
        if hasattr(stmt, 'body'):
            for j, s in enumerate(stmt.body):
                if hasattr(s, 'kind'):
                    print(f"    body[{j}]: {s.kind}")
    
    c_code = codegen.generate(ast, "test_mod")
    
    # 调试：打印生成的代码的前5000字符
    print("=== Generated C code (first 5000 chars) ===")
    print(c_code[:5000])
    print("=== End ===")
    
    # 验证 spawn 生成了线程创建代码
    assert "PyThread_start_new_thread" in c_code
    assert "PyEval_ReleaseThread" in c_code
    assert "PyEval_AcquireThread" in c_code


def test_go_expr_codegen():
    """测试 go 表达式代码生成"""
    source = '''def task():
    print("running")

def main():
    go task()'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证 go 生成了线程创建代码
    assert "PyThread_start_new_thread" in c_code
    assert "// 使用线程池执行 go 协程" in c_code


if __name__ == "__main__":
    test_spawn_expr_codegen()
    print("test_spawn_expr_codegen passed")
    
    test_go_expr_codegen()
    print("test_go_expr_codegen passed")
    
    print("All tests passed!")
