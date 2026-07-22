from cypyc.parser.lexer import Lexer, TokenType
from cypyc.parser.parser import Parser

# 测试变量构建块 =:
source1 = """x =:
    y = 1
    if y > 3:
        y -= 1
        return y^
    y^
"""

# 测试调用构建块 ~:
source2 = """def f[R](a: int) -> R = 0
x = f ~:
    y = 1
    if y > 3:
        y -= 1
        return (y^,)
    (y^,)
"""

# 测试生成器调用构建块 *:（注意 *: 前面有两个空格）
source3 = """def f[R](a: int) -> R = 0
xs = f  *:
    for i in [1, 2, 3]:
        i += 1
        yield (i^,)
    return
"""

# 测试指针类型不被错误识别为构建块
source4 = """def allocate() -> int*:
    ptr: int* = NULL
    return ptr
"""

def test_build_assign_tokens():
    print("Testing BUILD_ASSIGN token...")
    lexer = Lexer(source1)
    tokens = list(lexer.tokenize())
    token_types = [t.type for t in tokens]
    
    # 应该包含 BUILD_ASSIGN 而不是 ASSIGN + COLON
    assert TokenType.BUILD_ASSIGN in token_types, f"Expected BUILD_ASSIGN in {token_types}"
    print("✓ BUILD_ASSIGN token correctly identified")

def test_build_call_tokens():
    print("Testing BUILD_CALL token...")
    lexer = Lexer(source2)
    tokens = list(lexer.tokenize())
    token_types = [t.type for t in tokens]
    
    # 应该包含 BUILD_CALL
    assert TokenType.BUILD_CALL in token_types, f"Expected BUILD_CALL in {token_types}"
    print("✓ BUILD_CALL token correctly identified")

def test_build_gen_tokens():
    print("Testing BUILD_GEN token...")
    lexer = Lexer(source3)
    tokens = list(lexer.tokenize())
    token_types = [t.type for t in tokens]
    
    # 应该包含 BUILD_GEN
    assert TokenType.BUILD_GEN in token_types, f"Expected BUILD_GEN in {token_types}"
    print("✓ BUILD_GEN token correctly identified")

def test_pointer_not_build_block():
    print("Testing pointer type not confused with build block...")
    lexer = Lexer(source4)
    tokens = list(lexer.tokenize())
    token_types = [t.type for t in tokens]
    
    # 不应该包含 BUILD_GEN，应该是普通的 MUL + COLON
    assert TokenType.BUILD_GEN not in token_types, f"BUILD_GEN should not be in {token_types}"
    print("✓ Pointer type correctly not identified as build block")

if __name__ == "__main__":
    test_build_assign_tokens()
    test_build_call_tokens()
    test_build_gen_tokens()
    test_pointer_not_build_block()
    print("\nAll build block tests passed!")
