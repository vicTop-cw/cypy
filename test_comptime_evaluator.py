"""测试编译期求值器的增强功能"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser, Constant, BinOp, UnaryOp, Call, Name
from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator, evaluate_comptime


def _parse_and_get_evaluator(source: str):
    """解析源代码并返回 AST 和求值器"""
    lexer = Lexer(source)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    evaluator = ComptimeEvaluator()
    return ast, evaluator


class TestComptimeArithmetic:
    """测试编译期算术运算"""

    def test_basic_arithmetic(self):
        """测试基本算术运算"""
        evaluator = ComptimeEvaluator()
        
        # 测试加法
        a = Constant(10)
        b = Constant(20)
        op = BinOp(a, '+', b)
        result = evaluator.evaluate(op)
        assert result == 30
        
        # 测试乘法
        op2 = BinOp(a, '*', b)
        result2 = evaluator.evaluate(op2)
        assert result2 == 200
        
        # 测试除法
        op3 = BinOp(b, '/', a)
        result3 = evaluator.evaluate(op3)
        assert result3 == 2.0

    def test_bitwise_operations(self):
        """测试位运算"""
        evaluator = ComptimeEvaluator()
        
        a = Constant(0b1010)  # 10
        b = Constant(0b1100)  # 12
        
        # 位与
        op = BinOp(a, '&', b)
        result = evaluator.evaluate(op)
        assert result == 8  # 0b1000
        
        # 位或
        op2 = BinOp(a, '|', b)
        result2 = evaluator.evaluate(op2)
        assert result2 == 14  # 0b1110
        
        # 位异或
        op3 = BinOp(a, '^', b)
        result3 = evaluator.evaluate(op3)
        assert result3 == 6  # 0b0110

    def test_unary_operations(self):
        """测试一元运算"""
        evaluator = ComptimeEvaluator()
        
        a = Constant(42)
        
        # 取反
        op = UnaryOp('-', a)
        result = evaluator.evaluate(op)
        assert result == -42
        
        # 逻辑非
        op2 = UnaryOp('not', Constant(True))
        result2 = evaluator.evaluate(op2)
        assert result2 == False


class TestComptimeBuiltins:
    """测试编译期内置函数"""

    def test_math_functions(self):
        """测试数学函数"""
        evaluator = ComptimeEvaluator()
        
        # 测试 abs
        abs_call = Call(Name('abs'), [Constant(-42)])
        result = evaluator.evaluate(abs_call)
        assert result == 42
        
        # 测试 round
        round_call = Call(Name('round'), [Constant(3.14)])
        result2 = evaluator.evaluate(round_call)
        assert result2 == 3
        
        # 测试 min/max
        min_call = Call(Name('min'), [Constant(3), Constant(1), Constant(2)])
        result3 = evaluator.evaluate(min_call)
        assert result3 == 1
        
        max_call = Call(Name('max'), [Constant(3), Constant(1), Constant(2)])
        result4 = evaluator.evaluate(max_call)
        assert result4 == 3

    def test_type_conversion(self):
        """测试类型转换"""
        evaluator = ComptimeEvaluator()
        
        # int 转换
        int_call = Call(Name('int'), [Constant(3.14)])
        result = evaluator.evaluate(int_call)
        assert result == 3
        
        # float 转换
        float_call = Call(Name('float'), [Constant(42)])
        result2 = evaluator.evaluate(float_call)
        assert result2 == 42.0
        
        # str 转换
        str_call = Call(Name('str'), [Constant(42)])
        result3 = evaluator.evaluate(str_call)
        assert result3 == "42"
        
        # bool 转换
        bool_call = Call(Name('bool'), [Constant(0)])
        result4 = evaluator.evaluate(bool_call)
        assert result4 == False

    def test_list_functions(self):
        """测试列表函数"""
        evaluator = ComptimeEvaluator()
        
        # 测试 len
        len_call = Call(Name('len'), [Constant([1, 2, 3, 4, 5])])
        result = evaluator.evaluate(len_call)
        assert result == 5
        
        # 测试 sorted
        sorted_call = Call(Name('sorted'), [Constant([3, 1, 4, 1, 5, 9])])
        result2 = evaluator.evaluate(sorted_call)
        assert result2 == [1, 1, 3, 4, 5, 9]
        
        # 测试 reversed
        reversed_call = Call(Name('reversed'), [Constant([1, 2, 3])])
        result3 = evaluator.evaluate(reversed_call)
        assert result3 == [3, 2, 1]
        
        # 测试 enumerate
        enumerate_call = Call(Name('enumerate'), [Constant(['a', 'b', 'c'])])
        result4 = evaluator.evaluate(enumerate_call)
        assert result4 == [(0, 'a'), (1, 'b'), (2, 'c')]

    def test_math_constants(self):
        """测试数学常量相关函数"""
        evaluator = ComptimeEvaluator()
        
        # 测试 sqrt
        sqrt_call = Call(Name('sqrt'), [Constant(16)])
        result = evaluator.evaluate(sqrt_call)
        assert result == 4.0
        
        # 测试 pow
        pow_call = Call(Name('pow'), [Constant(2), Constant(10)])
        result2 = evaluator.evaluate(pow_call)
        assert result2 == 1024


class TestComptimeLoops:
    """测试编译期循环语句"""

    def test_for_loop(self):
        """测试 for 循环"""
        source = """
comptime:
    result = 0
    for i in range(5):
        result = result + i
    result
"""
        ast, evaluator = _parse_and_get_evaluator(source)
        result = evaluate_comptime(ast, evaluator)
        # 0 + 1 + 2 + 3 + 4 = 10
        assert result == 10

    def test_while_loop(self):
        """测试 while 循环"""
        source = """
comptime:
    count = 0
    i = 0
    while i < 5:
        i = i + 1
        count = count + i
    count
"""
        ast, evaluator = _parse_and_get_evaluator(source)
        result = evaluate_comptime(ast, evaluator)
        # 1 + 2 + 3 + 4 + 5 = 15
        assert result == 15


class TestComptimeStringOperations:
    """测试编译期字符串操作"""

    def test_string_concat(self):
        """测试字符串拼接"""
        evaluator = ComptimeEvaluator()
        
        a = Constant("Hello, ")
        b = Constant("World!")
        op = BinOp(a, '+', b)
        result = evaluator.evaluate(op)
        assert result == "Hello, World!"

    def test_string_repeat(self):
        """测试字符串重复"""
        evaluator = ComptimeEvaluator()
        
        a = Constant("ab")
        b = Constant(3)
        op = BinOp(a, '*', b)
        result = evaluator.evaluate(op)
        assert result == "ababab"


class TestComptimeListOperations:
    """测试编译期列表操作"""

    def test_list_operations(self):
        """测试列表基本操作"""
        evaluator = ComptimeEvaluator()
        
        # 列表字面量
        lst = Constant([1, 2, 3, 4, 5])
        result = evaluator.evaluate(lst)
        assert result == [1, 2, 3, 4, 5]

    def test_list_concat(self):
        """测试列表拼接"""
        evaluator = ComptimeEvaluator()
        
        a = Constant([1, 2])
        b = Constant([3, 4])
        op = BinOp(a, '+', b)
        result = evaluator.evaluate(op)
        assert result == [1, 2, 3, 4]

    def test_list_repeat(self):
        """测试列表重复"""
        evaluator = ComptimeEvaluator()
        
        a = Constant([1, 2])
        b = Constant(3)
        op = BinOp(a, '*', b)
        result = evaluator.evaluate(op)
        assert result == [1, 2, 1, 2, 1, 2]


class TestComptimeFunctions:
    """测试编译期函数"""

    def test_comptime_with_if(self):
        """测试带条件的编译期代码"""
        source = """
comptime:
    x = 10
    if x > 5:
        result = "greater"
    else:
        result = "less"
    result
"""
        ast, evaluator = _parse_and_get_evaluator(source)
        result = evaluate_comptime(ast, evaluator)
        assert result == "greater"

    def test_comptime_with_else(self):
        """测试 else 分支"""
        source = """
comptime:
    x = 3
    if x > 5:
        result = "greater"
    else:
        result = "less"
    result
"""
        ast, evaluator = _parse_and_get_evaluator(source)
        result = evaluate_comptime(ast, evaluator)
        assert result == "less"


class TestComptimeConstants:
    """测试编译期常量"""

    def test_builtin_constants(self):
        """测试内置常量"""
        evaluator = ComptimeEvaluator()
        
        # True
        result = evaluator.evaluate(Name('True'))
        assert result == True
        
        # False
        result2 = evaluator.evaluate(Name('False'))
        assert result2 == False
        
        # None
        result3 = evaluator.evaluate(Name('None'))
        assert result3 is None

    def test_comparison(self):
        """测试比较运算（使用 BinOp）"""
        evaluator = ComptimeEvaluator()
        
        # 小于
        op = BinOp(Constant(3), '<', Constant(5))
        result = evaluator.evaluate(op)
        assert result == True
        
        # 大于
        op2 = BinOp(Constant(10), '>', Constant(5))
        result2 = evaluator.evaluate(op2)
        assert result2 == True
        
        # 等于
        op3 = BinOp(Constant(5), '==', Constant(5))
        result3 = evaluator.evaluate(op3)
        assert result3 == True
        
        # 不等于
        op4 = BinOp(Constant(3), '!=', Constant(5))
        result4 = evaluator.evaluate(op4)
        assert result4 == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
