"""编译期函数测试 - 验证 Cypy 编译器的 comptime def 功能"""

import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator, register_comptime_functions


def _get_type_checker(source: str) -> TypeChecker:
    """辅助函数：解析并检查代码，返回类型检查器"""
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    type_checker = TypeChecker()
    type_checker.check(ast)
    return type_checker


def _evaluate_comptime(source: str) -> any:
    """辅助函数：解析代码并执行编译期求值"""
    lexer = Lexer(source)
    parser = Parser(lexer.tokenize())
    ast = parser.parse()
    
    evaluator = ComptimeEvaluator()
    register_comptime_functions(ast, evaluator)
    
    return evaluator, ast


class TestComptimeFuncDefParsing:
    """编译期函数定义解析测试"""

    def test_simple_comptime_func(self):
        """简单编译期函数定义"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b
'''
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        # 验证解析成功且包含 ComptimeFuncDef
        from cypyc.utils.ast_utils import ASTUtils
        funcs = ASTUtils.collect_nodes(ast, 'ComptimeFuncDef')
        assert len(funcs) == 1
        assert funcs[0].name == 'add'
        assert len(funcs[0].params) == 2

    def test_comptime_func_without_return_type(self):
        """编译期函数无返回类型"""
        source = '''
comptime def add(a: int, b: int):
    return a + b
'''
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        from cypyc.utils.ast_utils import ASTUtils
        funcs = ASTUtils.collect_nodes(ast, 'ComptimeFuncDef')
        assert len(funcs) == 1
        assert funcs[0].return_type is None

    def test_comptime_func_empty_body(self):
        """编译期函数空体"""
        source = '''
comptime def noop():
    pass
'''
        lexer = Lexer(source)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        
        from cypyc.utils.ast_utils import ASTUtils
        funcs = ASTUtils.collect_nodes(ast, 'ComptimeFuncDef')
        assert len(funcs) == 1


class TestComptimeFuncEvaluation:
    """编译期函数求值测试"""

    def test_simple_add_function(self):
        """简单加法函数"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b

const RESULT: int = comptime: add(3, 5)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        # 调用编译期函数
        result = evaluator._call_comptime_function('add', [3, 5])
        assert result == 8

    def test_multiply_function(self):
        """乘法函数"""
        source = '''
comptime def multiply(a: int, b: int) -> int:
    return a * b
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('multiply', [4, 5])
        assert result == 20

    def test_function_with_local_variable(self):
        """带局部变量的函数"""
        source = '''
comptime def compute(a: int) -> int:
    let temp: int = a * 2
    return temp + 1
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('compute', [3])
        assert result == 7


class TestComptimeFuncWithIf:
    """编译期函数中的条件判断测试"""

    def test_if_statement(self):
        """if 语句"""
        source = '''
comptime def max(a: int, b: int) -> int:
    if a > b:
        return a
    else:
        return b
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('max', [5, 3])
        assert result == 5
        
        result = evaluator._call_comptime_function('max', [2, 7])
        assert result == 7

    def test_nested_if_statement(self):
        """嵌套 if 语句"""
        source = '''
comptime def compare(a: int, b: int) -> str:
    if a == b:
        return "equal"
    elif a > b:
        return "greater"
    else:
        return "less"
'''
        evaluator, ast = _evaluate_comptime(source)
        
        assert evaluator._call_comptime_function('compare', [3, 3]) == "equal"
        assert evaluator._call_comptime_function('compare', [5, 3]) == "greater"
        assert evaluator._call_comptime_function('compare', [2, 5]) == "less"


class TestComptimeFuncRecursion:
    """编译期函数递归测试"""

    def test_fibonacci(self):
        """斐波那契函数"""
        source = '''
comptime def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        # 测试小数值（斐波那契递归复杂度很高，使用较小的值）
        assert evaluator._call_comptime_function('fibonacci', [0]) == 0
        assert evaluator._call_comptime_function('fibonacci', [1]) == 1
        assert evaluator._call_comptime_function('fibonacci', [4]) == 3
        assert evaluator._call_comptime_function('fibonacci', [6]) == 8

    def test_factorial(self):
        """阶乘函数"""
        source = '''
comptime def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        # 使用较小的值测试递归
        assert evaluator._call_comptime_function('factorial', [0]) == 1
        assert evaluator._call_comptime_function('factorial', [1]) == 1
        assert evaluator._call_comptime_function('factorial', [2]) == 2
        assert evaluator._call_comptime_function('factorial', [3]) == 6


class TestComptimeFuncWithBuiltins:
    """编译期函数调用内置函数测试"""

    def test_use_len(self):
        """使用 len 函数"""
        source = '''
comptime def get_length(s: str) -> int:
    return len(s)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('get_length', ["hello"])
        assert result == 5

    def test_use_abs(self):
        """使用 abs 函数"""
        source = '''
comptime def absolute(value: int) -> int:
    return abs(value)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        assert evaluator._call_comptime_function('absolute', [-5]) == 5
        assert evaluator._call_comptime_function('absolute', [10]) == 10


class TestComptimeFuncInTypeChecker:
    """类型检查器中的编译期函数测试"""

    def test_register_comptime_func(self):
        """编译期函数注册到类型检查器"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b
'''
        tc = _get_type_checker(source)
        
        # 验证函数被注册
        assert 'add' in tc.comptime_funcs

    def test_comptime_func_params_type(self):
        """编译期函数参数类型检查"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b
'''
        tc = _get_type_checker(source)
        
        # 验证没有类型错误
        assert len(tc.errors) == 0


class TestComptimeFuncIntegration:
    """编译期函数集成测试"""

    def test_comptime_func_in_comptime_stmt(self):
        """在 comptime 语句中调用编译期函数"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b

const RESULT: int = comptime: add(10, 20)
'''
        tc = _get_type_checker(source)
        
        # 验证没有类型错误
        assert len(tc.errors) == 0
        
        # 验证编译期函数被注册
        assert 'add' in tc.comptime_funcs

    def test_multiple_comptime_funcs(self):
        """多个编译期函数"""
        source = '''
comptime def add(a: int, b: int) -> int:
    return a + b

comptime def multiply(a: int, b: int) -> int:
    return a * b

comptime def compute(a: int, b: int) -> int:
    return add(a, b) * multiply(a, b)
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('compute', [2, 3])
        assert result == (2 + 3) * (2 * 3) == 5 * 6 == 30


class TestComptimeFuncEdgeCases:
    """编译期函数边界情况测试"""

    def test_no_params(self):
        """无参数编译期函数"""
        source = '''
comptime def get_pi() -> float:
    return 3.141592653589793
'''
        evaluator, ast = _evaluate_comptime(source)
        
        result = evaluator._call_comptime_function('get_pi', [])
        assert abs(result - 3.141592653589793) < 1e-10

    def test_single_param(self):
        """单参数编译期函数"""
        source = '''
comptime def square(x: int) -> int:
    return x * x
'''
        evaluator, ast = _evaluate_comptime(source)
        
        assert evaluator._call_comptime_function('square', [5]) == 25


if __name__ == '__main__':
    pytest.main([__file__, '-v'])