"""
断言系统 - 硬断言和软断言
参照 lang-zone/hermes 的 assert/check 设计
"""
import sys
from typing import Any, Callable, Optional, Type


class Assert:
    """硬断言 - 失败时抛出 AssertionError，终止测试"""
    
    @staticmethod
    def equal(actual: Any, expected: Any, message: str = None):
        """相等检查"""
        if actual != expected:
            msg = message or f"Assertion failed: {actual!r} != {expected!r}"
            raise AssertionError(msg)
    
    @staticmethod
    def not_equal(actual: Any, expected: Any, message: str = None):
        """不相等检查"""
        if actual == expected:
            msg = message or f"Assertion failed: {actual!r} == {expected!r}"
            raise AssertionError(msg)
    
    @staticmethod
    def true(condition: bool, message: str = None):
        """真值检查"""
        if not condition:
            msg = message or "Assertion failed: condition is False"
            raise AssertionError(msg)
    
    @staticmethod
    def false(condition: bool, message: str = None):
        """假值检查"""
        if condition:
            msg = message or "Assertion failed: condition is True"
            raise AssertionError(msg)
    
    @staticmethod
    def is_none(value: Any, message: str = None):
        """None 检查"""
        if value is not None:
            msg = message or f"Assertion failed: {value!r} is not None"
            raise AssertionError(msg)
    
    @staticmethod
    def is_not_none(value: Any, message: str = None):
        """非 None 检查"""
        if value is None:
            msg = message or "Assertion failed: value is None"
            raise AssertionError(msg)
    
    @staticmethod
    def contains(container: Any, item: Any, message: str = None):
        """包含检查"""
        if item not in container:
            msg = message or f"Assertion failed: {item!r} not in {container!r}"
            raise AssertionError(msg)
    
    @staticmethod
    def raises(exc_type: Type[Exception], fn: Callable, message: str = None):
        """异常检查"""
        try:
            fn()
            msg = message or f"Assertion failed: {exc_type.__name__} was not raised"
            raise AssertionError(msg)
        except exc_type:
            pass
        except Exception as e:
            msg = message or f"Assertion failed: expected {exc_type.__name__}, got {type(e).__name__}: {e}"
            raise AssertionError(msg)
    
    @staticmethod
    def almost_equal(actual: float, expected: float, tolerance: float = 1e-9, message: str = None):
        """近似相等检查（浮点）"""
        if abs(actual - expected) > tolerance:
            msg = message or f"Assertion failed: {actual} != {expected} (tolerance={tolerance})"
            raise AssertionError(msg)


class Check:
    """软断言 - 失败时打印警告，继续执行"""
    
    _failures = []
    
    @staticmethod
    def reset():
        """重置失败记录"""
        Check._failures.clear()
    
    @staticmethod
    def get_failures():
        """获取所有失败记录"""
        return list(Check._failures)
    
    @staticmethod
    def equal(actual: Any, expected: Any, message: str = None):
        """相等检查"""
        if actual != expected:
            msg = message or f"Check failed: {actual!r} != {expected!r}"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def not_equal(actual: Any, expected: Any, message: str = None):
        """不相等检查"""
        if actual == expected:
            msg = message or f"Check failed: {actual!r} == {expected!r}"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def true(condition: bool, message: str = None):
        """真值检查"""
        if not condition:
            msg = message or "Check failed: condition is False"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def false(condition: bool, message: str = None):
        """假值检查"""
        if condition:
            msg = message or "Check failed: condition is True"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def is_none(value: Any, message: str = None):
        """None 检查"""
        if value is not None:
            msg = message or f"Check failed: {value!r} is not None"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def is_not_none(value: Any, message: str = None):
        """非 None 检查"""
        if value is None:
            msg = message or "Check failed: value is None"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def contains(container: Any, item: Any, message: str = None):
        """包含检查"""
        if item not in container:
            msg = message or f"Check failed: {item!r} not in {container!r}"
            Check._failures.append(msg)
            print(f"⚠ CHECK FAILED: {msg}", file=sys.stderr)
    
    @staticmethod
    def has_failures() -> bool:
        """是否有失败"""
        return len(Check._failures) > 0
