"""测试兜底守卫策略和递归防护机制"""
import pytest
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


def parse_and_generate(code: str) -> str:
    """解析并生成 Cython 代码"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 类型检查
    type_checker = TypeChecker()
    type_checker.check(ast)
    
    # 代码生成
    generator = CythonGenerator()
    return generator.generate(ast)


def test_guarded_pred_method():
    """测试 __guarded_pred__ 守卫条件方法"""
    code = """
class SafeConvertible:
    value: int

    def __guarded_pred__<bool>(self) -> bool:
        return self.value > 0

    def __guarded_action__<bool>(self) -> bool:
        return True

let s = SafeConvertible()
let b: bool = s  # 应该检查 __guarded_pred__
"""
    cython_code = parse_and_generate(code)
    assert '__guarded_pred__' in cython_code
    assert '__guarded_action__' in cython_code


def test_guarded_action_method():
    """测试 __guarded_action__ 守卫动作方法"""
    code = """
class RangeChecker:
    def __init__(self, value: int):
        self.value = value

    def __guarded_pred__<float>(self) -> bool:
        return self.value >= 0 and self.value <= 100

    def __guarded_action__<float>(self) -> float:
        return float(self.value) / 100.0

let rc = RangeChecker(50)
let ratio: float = rc  # 应该调用 __guarded_action__
"""
    cython_code = parse_and_generate(code)
    assert '__guarded_pred__' in cython_code
    assert '__guarded_action__' in cython_code


def test_recursive_protection_stack():
    """测试策略栈递归防护"""
    # 测试类型检查器的策略栈功能
    type_checker = TypeChecker()
    
    # 进入策略
    assert type_checker._enter_strategy('test_strategy') == True
    assert 'test_strategy' in type_checker.active_strategies
    assert type_checker.strategy_depth == 1
    
    # 再次进入同一策略应该被阻止
    assert type_checker._enter_strategy('test_strategy') == False
    
    # 退出策略
    type_checker._exit_strategy('test_strategy')
    assert 'test_strategy' not in type_checker.active_strategies
    assert type_checker.strategy_depth == 0


def test_recursive_protection_depth():
    """测试策略深度限制"""
    type_checker = TypeChecker()
    
    # 超过最大深度应该被阻止
    for i in range(type_checker.max_strategy_depth):
        strategy_name = f'strategy_{i}'
        assert type_checker._enter_strategy(strategy_name) == True
    
    # 再进入一个策略应该被阻止
    assert type_checker._enter_strategy('extra_strategy') == False
    
    # 退出所有策略
    for i in range(type_checker.max_strategy_depth):
        strategy_name = f'strategy_{i}'
        type_checker._exit_strategy(strategy_name)
    
    assert type_checker.strategy_depth == 0


def test_no_strategy_decorator():
    """测试 @no_strategy 装饰器（阻止策略应用）"""
    code = """
@no_strategy
def pure_function(x: int) -> int:
    return x + 1

class PureClass:
    @no_strategy
    def method(self) -> int:
        return 42
"""
    lexer = Lexer(code)
    tokens = list(lexer.tokenize())
    parser = Parser(tokens)
    ast = parser.parse()
    
    # 应该能够解析成功
    assert ast is not None
    assert len(ast.body) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
