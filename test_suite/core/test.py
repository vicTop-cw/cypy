"""
Test 类 - 测试用例管理
参照 lang-zone/hermes 的 test 语法设计
"""
import traceback
from typing import Callable, Optional


class Test:
    def __init__(self, name: str, fn: Callable):
        self.name = name
        self.fn = fn
        # FIX T0r61.5.2 (defect 2): 实例标志位改名为 `skipped`。
        # 原名 `self.skip` 会遮蔽下面同名方法 skip()，导致
        # Test(name, fn).skip(reason) 抛出 TypeError: 'bool' object is not callable。
        self.skipped = False
        self.skip_reason = ""
        self.demo_category = None
        self.demo_name = None
        self.demo_source = None
    
    def skip_if(self, condition: bool, reason: str = "") -> 'Test':
        """条件跳过"""
        if condition:
            self.skipped = True
            self.skip_reason = reason
        return self
    
    def skip(self, reason: str = "") -> 'Test':
        """无条件跳过"""
        self.skipped = True
        self.skip_reason = reason
        return self
    
    def with_demo(self, category: str, name: str, source: str) -> 'Test':
        """关联 DEMO 代码"""
        self.demo_category = category
        self.demo_name = name
        self.demo_source = source
        return self
    
    def run(self) -> 'TestResult':
        """运行单个测试用例"""
        if self.skipped:
            return TestResult(
                suite_name="",
                test_name=self.name,
                status='skipped',
                message=self.skip_reason
            )
        
        try:
            self.fn()
            return TestResult(
                suite_name="",
                test_name=self.name,
                status='passed',
                demo_category=self.demo_category,
                demo_name=self.demo_name,
                demo_source=self.demo_source
            )
        except AssertionError as e:
            return TestResult(
                suite_name="",
                test_name=self.name,
                status='failed',
                message=str(e),
                traceback=traceback.format_exc()
            )
        except Exception as e:
            return TestResult(
                suite_name="",
                test_name=self.name,
                status='failed',
                message=f"Unexpected error: {e}",
                traceback=traceback.format_exc()
            )
    
    def __repr__(self) -> str:
        return f"Test(name='{self.name}', skipped={self.skipped})"


class TestResult:
    """测试用例运行结果"""
    def __init__(
        self,
        suite_name: str,
        test_name: str,
        status: str,
        message: str = None,
        traceback: str = None,
        demo_category: str = None,
        demo_name: str = None,
        demo_source: str = None
    ):
        self.suite_name = suite_name
        self.test_name = test_name
        self.status = status  # 'passed', 'failed', 'skipped'
        self.message = message
        self.traceback = traceback
        self.demo_category = demo_category
        self.demo_name = demo_name
        self.demo_source = demo_source
    
    @property
    def success(self) -> bool:
        return self.status == 'passed'
    
    @property
    def has_demo(self) -> bool:
        return self.demo_category is not None and self.demo_source is not None
    
    def __repr__(self) -> str:
        return f"TestResult({self.test_name}: {self.status})"
