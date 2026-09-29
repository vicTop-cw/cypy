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
        self.execute_from(0)
    
    def execute_from(self, depth: int = 0):
        """只执行栈中第 depth 层以上的defer（按LIFO顺序）
        
        defer_context()/defer_scope() 是嵌套的：作用域管理器共用同一个单例栈，
        如果内层退出时把整条栈排空，就会提前执行*外层*登记的defer
        （典型后果：外层还打开着的文件被内层关掉 -> ValueError: I/O operation
        on closed file，且外层退出时自己的清理点已经消失）。
        因此每个作用域只负责自己进入之后登记的那些defer。
        
        参数：
            depth: 进入作用域时栈里已有的条目数，小于该数的条目保持不动
        """
        depth = max(0, min(int(depth), len(self._defer_stack)))
        while len(self._defer_stack) > depth:
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
    
    可以安全嵌套：内层只执行自己登记的defer，不会提前消耗外层的defer。
    """
    manager = DeferManager.get_instance()
    depth = manager.count  # 记录进入时的栈深，只清理这之上的条目
    try:
        yield
    finally:
        manager.execute_from(depth)


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
    
    可以安全嵌套：内层作用域只执行自己这一层的defer。
    """
    
    def __enter__(self):
        self._manager = DeferManager.get_instance()
        self._depth = self._manager.count  # 进入时的栈深 = 外层拥有的条目数
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._manager.execute_from(getattr(self, '_depth', 0))
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
