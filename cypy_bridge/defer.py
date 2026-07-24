"""
Cypy Bridge Defer Resource Management

提供与Cython等价的defer语句功能，支持自动资源清理。
"""

import sys
from typing import Any, Callable, List
from contextlib import contextmanager


class DeferManager:
    """defer管理器：管理defer语句的注册和执行"""
    
    _instance = None
    
    def __init__(self):
        self._defer_stack = []
    
    @classmethod
    def get_instance(cls):
        """获取全局defer管理器实例"""
        if cls._instance is None:
            cls._instance = DeferManager()
        return cls._instance
    
    def push(self, func: Callable, *args, **kwargs):
        """注册defer函数
        
        参数：
            func: 要延迟执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        """
        self._defer_stack.append((func, args, kwargs))
    
    def execute_all(self):
        """执行所有defer函数（按LIFO顺序）"""
        while self._defer_stack:
            func, args, kwargs = self._defer_stack.pop()
            try:
                func(*args, **kwargs)
            except Exception as e:
                # 记录错误但继续执行其他defer
                print(f"Defer execution error: {e}", file=sys.stderr)
    
    def clear(self):
        """清空defer栈（不执行）"""
        self._defer_stack = []
    
    @property
    def count(self):
        """返回defer栈中的函数数量"""
        return len(self._defer_stack)


@contextmanager
def defer_context():
    """defer上下文管理器
    
    用法：
        with defer_context():
            defer(some_function)
            # 代码执行...
        # 退出上下文时自动执行所有defer
    """
    manager = DeferManager.get_instance()
    try:
        yield
    finally:
        manager.execute_all()
        manager.clear()


def defer(func: Callable, *args, **kwargs):
    """注册defer函数（类似Go的defer语句）
    
    用法：
        def func():
            ptr = malloc(100)
            defer(free, ptr)
            # 使用ptr...
            # 函数退出时自动调用free(ptr)
    
    参数：
        func: 要延迟执行的函数
        *args: 函数参数
        **kwargs: 函数关键字参数
    """
    manager = DeferManager.get_instance()
    manager.push(func, *args, **kwargs)


class defer_scope:
    """defer作用域：在作用域结束时自动执行所有defer
    
    用法：
        def func():
            with defer_scope():
                ptr = malloc(100)
                defer(free, ptr)
                # 使用ptr...
            # 退出with块时自动调用free(ptr)
    """
    
    def __enter__(self):
        self._manager = DeferManager.get_instance()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._manager.execute_all()
        self._manager.clear()
        # 不抑制异常
        return False


class DeferGuard:
    """defer守卫：用于类方法中的defer管理
    
    用法：
        class Resource:
            def __init__(self):
                self._guard = DeferGuard()
            
            def allocate(self):
                self._ptr = malloc(100)
                self._guard.defer(free, self._ptr)
            
            def cleanup(self):
                self._guard.execute()
    """
    
    def __init__(self):
        self._defer_stack = []
    
    def defer(self, func: Callable, *args, **kwargs):
        """注册defer函数"""
        self._defer_stack.append((func, args, kwargs))
    
    def execute(self):
        """执行所有defer函数"""
        while self._defer_stack:
            func, args, kwargs = self._defer_stack.pop()
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"Defer execution error: {e}", file=sys.stderr)
    
    def clear(self):
        """清空defer栈"""
        self._defer_stack = []


def execute_defers():
    """执行所有已注册的defer函数"""
    manager = DeferManager.get_instance()
    manager.execute_all()
    manager.clear()


__all__ = [
    'defer',
    'DeferManager',
    'defer_scope',
    'defer_context',
    'DeferGuard',
    'execute_defers',
]
