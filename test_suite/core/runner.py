"""
测试运行器 - 管理和运行测试套件
"""
import time
from typing import List, Optional
from .suite import Suite, SuiteResult
from .test import TestResult


class TestRunner:
    def __init__(self):
        self.suites: List[Suite] = []
        self.results: List[SuiteResult] = []
    
    def add_suite(self, suite: Suite) -> None:
        """添加测试套件"""
        self.suites.append(suite)
    
    def add_suites(self, suites: List[Suite]) -> None:
        """添加多个测试套件"""
        self.suites.extend(suites)
    
    def run_all(self) -> 'RunResult':
        """运行所有测试套件"""
        start_time = time.time()
        all_results = []
        passed = 0
        failed = 0
        skipped = 0
        
        for suite in self.suites:
            result = suite.run()
            all_results.append(result)
            passed += result.passed
            failed += result.failed
            skipped += result.skipped
        
        elapsed = time.time() - start_time
        
        return RunResult(
            results=all_results,
            passed=passed,
            failed=failed,
            skipped=skipped,
            elapsed=elapsed
        )
    
    def run_suite(self, suite_name: str) -> Optional['RunResult']:
        """运行指定测试套件"""
        start_time = time.time()
        all_results = []
        passed = 0
        failed = 0
        skipped = 0
        
        for suite in self.suites:
            if suite.name == suite_name:
                result = suite.run()
                all_results.append(result)
                passed += result.passed
                failed += result.failed
                skipped += result.skipped
                break
        
        elapsed = time.time() - start_time
        
        if not all_results:
            return None
        
        return RunResult(
            results=all_results,
            passed=passed,
            failed=failed,
            skipped=skipped,
            elapsed=elapsed
        )
    
    def run_suites(self, suite_names: List[str]) -> 'RunResult':
        """运行多个指定测试套件"""
        start_time = time.time()
        all_results = []
        passed = 0
        failed = 0
        skipped = 0
        
        for suite in self.suites:
            if suite.name in suite_names:
                result = suite.run()
                all_results.append(result)
                passed += result.passed
                failed += result.failed
                skipped += result.skipped
        
        elapsed = time.time() - start_time
        
        return RunResult(
            results=all_results,
            passed=passed,
            failed=failed,
            skipped=skipped,
            elapsed=elapsed
        )
    
    def generate_report(self, verbose: bool = False) -> str:
        """生成测试报告"""
        if not self.results:
            return "No test results available"
        
        lines = []
        lines.append("=" * 60)
        lines.append("Cypy Test Suite Report")
        lines.append("=" * 60)
        
        total_passed = sum(r.passed for r in self.results)
        total_failed = sum(r.failed for r in self.results)
        total_skipped = sum(r.skipped for r in self.results)
        total = total_passed + total_failed + total_skipped
        
        for result in self.results:
            lines.append("")
            lines.append(f"Suite: {result.suite_name}")
            lines.append("-" * 40)
            lines.append(f"  Passed: {result.passed} | Failed: {result.failed} | Skipped: {result.skipped}")
            
            if verbose:
                for test_result in result.results:
                    status_icon = "✓" if test_result.status == 'passed' else "✗" if test_result.status == 'failed' else "~"
                    lines.append(f"    {status_icon} {test_result.test_name}: {test_result.status}")
                    if test_result.message:
                        lines.append(f"      Message: {test_result.message}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"Total: {total} | Passed: {total_passed} | Failed: {total_failed} | Skipped: {total_skipped}")
        if total > 0:
            percentage = (total_passed / total) * 100
            lines.append(f"Success Rate: {percentage:.2f}%")
        
        return "\n".join(lines)


class RunResult:
    """运行结果汇总"""
    def __init__(
        self,
        results: List[SuiteResult],
        passed: int,
        failed: int,
        skipped: int,
        elapsed: float
    ):
        self.results = results
        self.passed = passed
        self.failed = failed
        self.skipped = skipped
        self.elapsed = elapsed
    
    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped
    
    @property
    def success(self) -> bool:
        return self.failed == 0
    
    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100
    
    def get_demo_results(self) -> List[TestResult]:
        """获取所有带 DEMO 的通过测试"""
        demos = []
        for suite_result in self.results:
            for test_result in suite_result.results:
                if test_result.success and test_result.has_demo:
                    demos.append(test_result)
        return demos
    
    def __repr__(self) -> str:
        return f"RunResult(passed={self.passed}, failed={self.failed}, skipped={self.skipped}, elapsed={self.elapsed:.2f}s)"
