"""测试SIMD向量代码生成"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_bridge.compiler import CCodeGenerator


def test_simd_vec_literal_codegen():
    """测试SIMD向量字面量代码生成"""
    source = '''def test_simd():
    v = vec![1.0, 2.0, 3.0, 4.0]
    u = vec![5.0; 4]
    return 0'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证SIMD向量类型定义已生成
    assert "VecFloat32_4" in c_code
    assert "VecInt32_4" in c_code
    
    # 验证向量创建辅助函数已生成
    assert "_vec_make_f32_4" in c_code
    assert "_vec_splat_f32" in c_code
    
    # 验证向量运算辅助函数已生成
    assert "_vec_add_f32" in c_code
    assert "_vec_mul_f32" in c_code
    assert "_vec_dot_f32" in c_code
    
    print("test_simd_vec_literal_codegen passed")


def test_simd_vec_types():
    """测试SIMD向量类型别名生成"""
    source = '''type Vec4f = vec[float; 4]
type Vec4i = vec[int; 4]

def test_vec_types(v: Vec4f):
    return 0'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证类型别名已生成
    assert "VecFloat32_4" in c_code
    
    print("test_simd_vec_types passed")


def test_simd_operations():
    """测试SIMD向量运算代码生成"""
    source = '''def test_vec_ops():
    a = vec![1.0, 2.0, 3.0, 4.0]
    b = vec![5.0, 6.0, 7.0, 8.0]
    c = a + b
    d = a * b
    return 0'''
    
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    codegen = CCodeGenerator()
    c_code = codegen.generate(ast, "test_mod")
    
    # 验证向量运算辅助函数已生成
    assert "_vec_add_f32" in c_code
    assert "_vec_mul_f32" in c_code
    
    print("test_simd_operations passed")


if __name__ == "__main__":
    test_simd_vec_literal_codegen()
    test_simd_vec_types()
    test_simd_operations()
    print("All SIMD tests passed!")