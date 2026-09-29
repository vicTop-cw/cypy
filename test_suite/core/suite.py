"""
Suite 类 - 测试套件管理
参照 lang-zone/hermes 的 suite 语法设计
"""
from typing import List, Callable, Optional
from .assertions import Check
from .test import Test, TestResult


class Suite:
    def __init__(self, name: str):
        self.name = name
        self.tests: List[Test] = []
        self.setup_fn: Optional[Callable] = None
        self.teardown_fn: Optional[Callable] = None
        # FIX T0r61.5.2 (defect 1): 正在执行的 Test。测试体内需要给“当前测试”
        # 挂 DEMO 元数据时，必须用 suite.current_test，而不是 suite.tests[-1]
        # （tests 列表在 import 期注册、run() 期间不再变化，tests[-1] 恒为最后一个 Test）。
        self.current_test: Optional[Test] = None
    
    def add_test(self, test: Test) -> None:
        """添加测试用例"""
        self.tests.append(test)
    
    def test(self, name: str):
        """装饰器：添加测试用例"""
        def decorator(fn):
            self.tests.append(Test(name, fn))
            return fn
        return decorator
    
    def setup(self, fn):
        """装饰器：设置套件级初始化"""
        self.setup_fn = fn
        return fn
    
    def teardown(self, fn):
        """装饰器：设置套件级清理"""
        self.teardown_fn = fn
        return fn
    
    def run(self) -> 'SuiteResult':
        """运行整个测试套件"""
        results = []
        passed = 0
        failed = 0
        skipped = 0
        
        # 执行 setup
        if self.setup_fn:
            try:
                self.setup_fn()
            except Exception as e:
                return SuiteResult(
                    suite_name=self.name,
                    results=[],
                    passed=0,
                    failed=1,
                    skipped=0,
                    error=f"Setup failed: {e}"
                )
        
        # 执行所有测试
        for test in self.tests:
            # FIX T0r61.5.2 (defect 1): 在调用 test.run() 前发布“正在执行的 Test”，
            # 让测试体可以把 DEMO 元数据挂到自己身上（suite.current_test）。
            self.current_test = test
            # FIX T0r61.5.2 (defect 3): 软断言(Check)此前从未参与判定，
            # Suite.run() 现在在每个测试结束后咨询 Check.has_failures()。
            Check.reset()
            result = test.run()
            if result.status == 'passed' and Check.has_failures():
                result.status = 'failed'
                failures = Check.get_failures()
                result.message = "Soft check failures: " + "; ".join(failures)
            Check.reset()
            results.append(result)
            if result.status == 'passed':
                passed += 1
            elif result.status == 'failed':
                failed += 1
            elif result.status == 'skipped':
                skipped += 1
        
        self.current_test = None
        
        # 执行 teardown
        if self.teardown_fn:
            try:
                self.teardown_fn()
            except Exception as e:
                # teardown 失败不影响测试结果，但记录警告
                pass
        
        return SuiteResult(
            suite_name=self.name,
            results=results,
            passed=passed,
            failed=failed,
            skipped=skipped
        )
    
    def __repr__(self) -> str:
        return f"Suite(name='{self.name}', tests={len(self.tests)})"


class SuiteResult:
    """测试套件运行结果"""
    def __init__(
        self,
        suite_name: str,
        results: List[TestResult],
        passed: int,
        failed: int,
        skipped: int,
        error: str = None
    ):
        self.suite_name = suite_name
        self.results = results
        self.passed = passed
        self.failed = failed
        self.skipped = skipped
        self.error = error
    
    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped
    
    @property
    def success(self) -> bool:
        return self.failed == 0 and self.error is None
