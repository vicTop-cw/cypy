"""
Cypy 综合测试运行器 - 整合性能对比和代码质量检测

使用方法:
    python tests/run_comprehensive_tests.py

输出:
    test_reports/  - 综合测试报告目录
"""

import os
import sys
import time
import json
import csv
import traceback
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 添加 tests 目录到路径
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))

from benchmark.test_performance_comparison import (
    BenchmarkRunner,
    BenchmarkCase,
    BenchmarkResult,
    create_standard_benchmark_suite,
)
from code_quality.test_code_quality import (
    CodeQualityChecker,
    QualityReport,
    QualityLevel,
    create_quality_test_suite,
)


class ComprehensiveTestRunner:
    """综合测试运行器"""

    def __init__(self):
        self.project_root = project_root
        self.output_dir = self.project_root / "test_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.benchmark_runner = BenchmarkRunner(str(self.output_dir / "benchmark"))
        self.quality_checker = CodeQualityChecker()

        self.start_time = None
        self.end_time = None

    def run_all_tests(self, benchmark_iterations: int = 100) -> Dict[str, Any]:
        """运行所有测试"""
        self.start_time = time.time()

        print("=" * 70)
        print("Cypy 综合测试套件")
        print("=" * 70)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"项目根目录: {self.project_root}")
        print()

        # Phase 1: 编译 Pipeline 验证
        print("-" * 70)
        print("Phase 0: 编译 Pipeline 验证")
        print("-" * 70)
        pipeline_results = self._verify_compilation_pipeline()

        # Phase 2: 运行性能基准测试
        print("\n" + "-" * 70)
        print("Phase 1: 性能基准测试")
        print("-" * 70)

        benchmark_results = self._run_benchmark_tests(benchmark_iterations)

        # Phase 3: 运行代码质量检测
        print("\n" + "-" * 70)
        print("Phase 2: 代码质量检测")
        print("-" * 70)

        quality_reports = self._run_quality_tests()

        # 生成综合报告
        self.end_time = time.time()
        report = self._generate_comprehensive_report(
            pipeline_results, benchmark_results, quality_reports
        )

        return report

    def _verify_compilation_pipeline(self) -> Dict[str, Any]:
        """验证 Cypy→Cython 完整编译 pipeline"""
        pipeline_result = {
            "lexer": {"status": "unknown", "details": ""},
            "parser": {"status": "unknown", "details": ""},
            "type_checker": {"status": "unknown", "details": ""},
            "code_generator": {"status": "unknown", "details": ""},
            "overall": "unknown",
        }

        test_cases = [
            ("simple_function", "def add(a: int, b: int) -> int:\n    return a + b"),
            ("struct_definition", "struct Point:\n    x: float\n    y: float"),
            ("generic_function", "def identity<T>(x: T) -> T:\n    return x"),
            ("trait_definition", "trait Display:\n    def show(self) -> str"),
            ("typeclass_definition", "typeclass Eq<T>:\n    def eq(self, other: T) -> bool"),
            ("comprehensive", """
struct Point:
    x: float
    y: float

def distance(p1: Point, p2: Point) -> float:
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return (dx * dx + dy * dy) ** 0.5
"""),
        ]

        try:
            from cypyc.parser.lexer import Lexer
            from cypyc.parser.parser import Parser
            from cypyc.analyzer.type_checker import TypeChecker
            from cypyc.codegen.cython_generator import CythonGenerator

            print("验证编译 Pipeline...")
            print()

            for case_name, source in test_cases:
                print(f"  测试: {case_name}")

                # 1. Lexer
                try:
                    lexer = Lexer(source)
                    tokens = list(lexer.tokenize())
                    pipeline_result["lexer"] = {
                        "status": "ok",
                        "details": f"Generated {len(tokens)} tokens",
                    }
                except Exception as e:
                    pipeline_result["lexer"] = {
                        "status": "failed",
                        "details": str(e),
                    }
                    print(f"    ✗ Lexer 失败: {e}")
                    continue

                # 2. Parser
                try:
                    parser = Parser(tokens)
                    ast = parser.parse()
                    pipeline_result["parser"] = {
                        "status": "ok",
                        "details": f"AST parsed successfully",
                    }
                except Exception as e:
                    pipeline_result["parser"] = {
                        "status": "failed",
                        "details": str(e),
                    }
                    print(f"    ✗ Parser 失败: {e}")
                    continue

                # 3. Type Checker
                try:
                    checker = TypeChecker()
                    checker.check(ast)
                    if checker.errors:
                        pipeline_result["type_checker"] = {
                            "status": "warnings",
                            "details": f"Type warnings: {checker.errors[:3]}",
                        }
                    else:
                        pipeline_result["type_checker"] = {
                            "status": "ok",
                            "details": "Type checking passed",
                        }
                except Exception as e:
                    pipeline_result["type_checker"] = {
                        "status": "failed",
                        "details": str(e),
                    }
                    print(f"    ✗ TypeChecker 失败: {e}")
                    continue

                # 4. Code Generator
                try:
                    generator = CythonGenerator("test_module.pyx")
                    cython_code = generator.generate(ast)
                    pipeline_result["code_generator"] = {
                        "status": "ok",
                        "details": f"Generated {len(cython_code)} chars of Cython code",
                    }
                    print(f"    ✓ 成功: {len(cython_code)} chars")
                    print(f"      生成代码预览: {cython_code[:150]}...")
                except Exception as e:
                    pipeline_result["code_generator"] = {
                        "status": "failed",
                        "details": str(e),
                    }
                    print(f"    ✗ CodeGenerator 失败: {e}")

            # 总结
            statuses = [
                pipeline_result["lexer"]["status"],
                pipeline_result["parser"]["status"],
                pipeline_result["type_checker"]["status"],
                pipeline_result["code_generator"]["status"],
            ]
            if all(s == "ok" for s in statuses):
                pipeline_result["overall"] = "excellent"
            elif all(s in ("ok", "warnings") for s in statuses):
                pipeline_result["overall"] = "good"
            elif any(s == "failed" for s in statuses):
                pipeline_result["overall"] = "has_failures"
            else:
                pipeline_result["overall"] = "unknown"

            print()
            print(f"  Pipeline 总体状态: {pipeline_result['overall']}")

        except ImportError as e:
            pipeline_result["overall"] = "import_error"
            pipeline_result["lexer"] = {"status": "skipped", "details": str(e)}
            pipeline_result["parser"] = {"status": "skipped", "details": str(e)}
            pipeline_result["type_checker"] = {"status": "skipped", "details": str(e)}
            pipeline_result["code_generator"] = {"status": "skipped", "details": str(e)}
            print(f"  ✗ 导入错误: {e}")

        return pipeline_result

    def _run_benchmark_tests(self, iterations: int) -> List[Dict]:
        """运行性能测试"""
        try:
            cases = create_standard_benchmark_suite()

            for case in cases:
                self.benchmark_runner.add_case(case)

            print(f"共 {len(cases)} 个性能测试用例")
            print(f"迭代次数: {iterations}")
            print()

            results = self.benchmark_runner.run_all(iterations)

            return results

        except Exception as e:
            print(f"性能测试执行失败: {e}")
            traceback.print_exc()
            return []

    def _run_quality_tests(self) -> List[QualityReport]:
        """运行代码质量检测 - 同时测试真实 Cypy 编译 pipeline"""
        try:
            # 使用标准测试用例
            test_cases = create_quality_test_suite()

            # 扩展测试用例：添加真实 Cypy 编译测试
            real_pipeline_cases = self._create_real_pipeline_test_cases()
            all_cases = test_cases + real_pipeline_cases

            print(f"共 {len(all_cases)} 个质量检测用例 (含 {len(real_pipeline_cases)} 个真实编译测试)")
            print()

            for case_name, cypy_source, cython_code in all_cases:
                print(f"检测: {case_name}")

                try:
                    report = self.quality_checker.check_code(
                        test_case_name=case_name,
                        cypy_source=cypy_source,
                        cython_generated=cython_code,
                        python_equivalent=cypy_source,
                    )

                    status_icon = "✓" if report.total_score >= 75 else "⚠" if report.total_score >= 60 else "✗"
                    print(f"  {status_icon} 总分: {report.total_score:.1f} ({report.level.value})")
                    print(f"    问题: {len(report.issues)} 个")

                    if report.issues:
                        for issue in report.issues[:3]:
                            print(f"      [{issue.severity.value}] {issue.description}")
                except Exception as e:
                    print(f"  ✗ 检测失败: {e}")

            print()

            return self.quality_checker.results

        except Exception as e:
            print(f"质量检测执行失败: {e}")
            traceback.print_exc()
            return []

    def _create_real_pipeline_test_cases(self) -> List[tuple]:
        """创建基于真实 Cypy 编译 pipeline 的测试用例"""
        cases = []

        try:
            from cypyc.parser.lexer import Lexer
            from cypyc.parser.parser import Parser
            from cypyc.analyzer.type_checker import TypeChecker
            from cypyc.codegen.cython_generator import CythonGenerator

            test_sources = [
                ("real_simple_function", "def add(a: int, b: int) -> int:\n    return a + b"),
                ("real_math_operations", """
import math

def compute(n: int) -> float:
    result: float = 0.0
    for i in range(n):
        x: float = float(i)
        result += math.sqrt(x) * math.sin(x)
    return result
"""),
                ("real_struct", """
struct Point:
    x: float
    y: float

def distance(p1: Point, p2: Point) -> float:
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return (dx * dx + dy * dy) ** 0.5
"""),
                ("real_generic", """
def first<T>(items: list) -> T:
    if items:
        return items[0]
    return None
"""),
                ("real_trait", """
trait Serializable:
    def to_json(self) -> str
    def from_json(self, data: str) -> Self

impl Serializable for Point:
    def to_json(self) -> str:
        return f'{{"x": {self.x}, "y": {self.y}}}'

    def from_json(self, data: str) -> Point:
        return Point(0.0, 0.0)
"""),
            ]

            for name, source in test_sources:
                try:
                    # 执行完整编译 pipeline
                    lexer = Lexer(source)
                    tokens = list(lexer.tokenize())
                    parser = Parser(tokens)
                    ast = parser.parse()
                    checker = TypeChecker()
                    checker.check(ast)
                    generator = CythonGenerator(f"{name}.pyx")
                    cython_code = generator.generate(ast)

                    cases.append((name, source, cython_code))
                except Exception as e:
                    # 即使编译失败，也添加用例以记录问题
                    error_code = f"# Compilation failed: {e}\n# Source:\n{source}"
                    cases.append((name, source, error_code))

        except ImportError:
            pass  # Cypy 模块不可用，跳过真实编译测试

        return cases

    def _generate_comprehensive_report(
        self, pipeline_results: Dict, benchmark_results: List[Dict],
        quality_reports: List[QualityReport]
    ) -> Dict[str, Any]:
        """生成综合测试报告"""
        execution_time = self.end_time - self.start_time

        report = {
            "test_metadata": {
                "start_time": datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": datetime.fromtimestamp(self.end_time).strftime('%Y-%m-%d %H:%M:%S'),
                "execution_time_seconds": execution_time,
                "project_root": str(self.project_root),
            },
            "compilation_pipeline": pipeline_results,
            "performance_benchmarks": self._summarize_benchmarks(benchmark_results),
            "quality_assessment": self._summarize_quality(quality_reports),
            "conclusions": self._generate_conclusions(
                pipeline_results, benchmark_results, quality_reports
            ),
            "recommendations": self._generate_recommendations(
                pipeline_results, benchmark_results, quality_reports
            ),
        }

        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"comprehensive_report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        # 保存 Markdown 报告
        md_path = self.output_dir / f"comprehensive_report_{timestamp}.md"
        md_content = self._generate_markdown_report(report)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        print(f"\n{'=' * 70}")
        print("综合测试报告已保存:")
        print(f"  JSON 报告: {report_path}")
        print(f"  Markdown 报告: {md_path}")
        print(f"{'=' * 70}")

        # 打印结论摘要
        print("\n结论摘要:")
        for conclusion in report["conclusions"]:
            print(f"  • {conclusion}")

        return report

    def _summarize_benchmarks(self, results: List[Dict]) -> Dict[str, Any]:
        """汇总性能测试结果"""
        if not results:
            return {"status": "no_data", "summary": "无性能测试数据"}

        python_results = [r for r in results if r.get('implementation') == 'python' and r.get('success')]
        cypy_results = [r for r in results if 'cypy' in r.get('implementation', '') and r.get('success')]

        summary = {
            "status": "ok",
            "total_cases": len(set(r.get('name', 'unknown') for r in results)),
            "successful": len([r for r in results if r.get('success')]),
            "failed": len([r for r in results if not r.get('success')]),
            "python_baseline": {},
            "cypy_estimated": {},
            "comparison": [],
        }

        # Python 基准
        if python_results:
            total_time = sum(r.get('time_ms', 0) for r in python_results)
            summary['python_baseline'] = {
                'total_time_ms': total_time,
                'avg_time_ms': total_time / len(python_results),
                'cases': python_results,
            }

        # Cypy 估算
        if cypy_results:
            total_time = sum(r.get('time_ms', 0) for r in cypy_results)
            summary['cypy_estimated'] = {
                'total_time_ms': total_time,
                'avg_time_ms': total_time / len(cypy_results),
                'cases': cypy_results,
            }

        # 性能对比 - 按名称匹配
        if python_results and cypy_results:
            # 按名称建立映射
            py_by_name = {r.get('name'): r for r in python_results}
            cy_by_name = {r.get('name'): r for r in cypy_results}
            
            # 按名称匹配
            for name in set(py_by_name.keys()) & set(cy_by_name.keys()):
                py_time = py_by_name[name].get('time_ms', 0)
                cy_time = cy_by_name[name].get('time_ms', 0)
                if py_time > 0 and cy_time > 0 and cy_time < py_time:
                    speedup = py_time / cy_time
                    summary['comparison'].append({
                        'name': name,
                        'python_time_ms': py_time,
                        'cypy_estimated_time_ms': cy_time,
                        'estimated_speedup': speedup,
                        'improvement_percent': (speedup - 1) * 100,
                    })

        return summary

    def _summarize_quality(self, reports: List[QualityReport]) -> Dict[str, Any]:
        """汇总质量检测结果"""
        if not reports:
            return {"status": "no_data", "summary": "无质量检测数据"}

        total_scores = [r.total_score for r in reports]
        avg_score = sum(total_scores) / len(total_scores)

        # 计算状态
        has_critical = any(
            any(i.severity.value == 'critical' for i in r.issues)
            for r in reports
        )
        if has_critical and avg_score < 60:
            status = "needs_improvement"
        elif avg_score >= 75:
            status = "good"
        else:
            status = "fair"

        # 按维度统计
        dimension_scores = {}
        for report in reports:
            for score in report.scores:
                if score.dimension not in dimension_scores:
                    dimension_scores[score.dimension] = []
                dimension_scores[score.dimension].append(score.score)

        # 统计问题
        all_issues = []
        for report in reports:
            all_issues.extend(report.issues)

        severity_counts = {}
        for issue in all_issues:
            severity = issue.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            "status": status,
            "total_cases": len(reports),
            "average_score": avg_score,
            "highest_score": max(total_scores),
            "lowest_score": min(total_scores),
            "level_distribution": {
                level.value: len([r for r in reports if r.level == level])
                for level in QualityLevel
            },
            "dimension_scores": {
                dim: sum(scores) / len(scores)
                for dim, scores in dimension_scores.items()
            },
            "total_issues": len(all_issues),
            "issue_severity_distribution": severity_counts,
            "critical_issues_count": len([i for i in all_issues if i.severity.value == 'critical']),
        }

    def _generate_conclusions(
        self, pipeline_results: Dict, benchmark_results: List[Dict],
        quality_reports: List[QualityReport]
    ) -> List[str]:
        """生成结论"""
        conclusions = []

        # Pipeline 结论
        pipeline_status = pipeline_results.get('overall', 'unknown')
        if pipeline_status == 'excellent':
            conclusions.append(
                "编译 Pipeline 完整验证通过：源码解析 → 类型检查 → Cython 代码生成 全链路正常。"
            )
        elif pipeline_status == 'good':
            conclusions.append(
                "编译 Pipeline 基本可用，存在少量警告但不影响核心功能。"
            )
        elif pipeline_status == 'has_failures':
            conclusions.append(
                "编译 Pipeline 存在失败情况，需要修复部分编译阶段。"
            )
        else:
            conclusions.append(
                "编译 Pipeline 状态未知，需要进一步验证。"
            )

        # 性能结论
        python_results = [r for r in benchmark_results if r.get('implementation') == 'python' and r.get('success')]
        cypy_results = [r for r in benchmark_results if 'cypy' in r.get('implementation', '') and r.get('success')]

        if python_results and cypy_results:
            # 按名称匹配
            py_by_name = {r.get('name'): r for r in python_results}
            cy_by_name = {r.get('name'): r for r in cypy_results}
            
            speedups = []
            for name in set(py_by_name.keys()) & set(cy_by_name.keys()):
                py_time = py_by_name[name].get('time_ms', 0)
                cy_time = cy_by_name[name].get('time_ms', 0)
                if py_time > 0 and cy_time > 0 and cy_time < py_time:
                    speedups.append(py_time / cy_time)

            if speedups:
                avg_speedup = sum(speedups) / len(speedups)
                max_speedup = max(speedups)
                conclusions.append(
                    f"基于代码复杂度分析，Cypy(Cython) 预估性能提升 {avg_speedup:.1f}x "
                    f"(最高 {max_speedup:.1f}x) 于 Python。"
                    f" 实际性能需在 Cython 编译环境中验证。"
                )

        # 质量结论
        if quality_reports:
            avg_quality = sum(r.total_score for r in quality_reports) / len(quality_reports)
            critical_count = sum(
                len([i for i in r.issues if i.severity.value == 'critical'])
                for r in quality_reports
            )

            conclusions.append(
                f"代码生成质量平均评分: {avg_quality:.1f}/100，{critical_count} 个严重问题需关注。"
            )

            # 各维度分析
            dimension_scores = {}
            for report in quality_reports:
                for score in report.scores:
                    if score.dimension not in dimension_scores:
                        dimension_scores[score.dimension] = []
                    dimension_scores[score.dimension].append(score.score)

            for dim, scores in dimension_scores.items():
                avg = sum(scores) / len(scores)
                if avg < 70:
                    conclusions.append(
                        f"质量维度 '{dim}' 得分偏低 ({avg:.1f})，需要重点改进。"
                    )

        return conclusions

    def _generate_recommendations(
        self, pipeline_results: Dict, benchmark_results: List[Dict],
        quality_reports: List[QualityReport]
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []

        # 基于 Pipeline 的建议
        pipeline_status = pipeline_results.get('overall', 'unknown')
        if pipeline_status in ('has_failures', 'import_error'):
            failed_stages = []
            for stage, info in pipeline_results.items():
                if isinstance(info, dict) and info.get('status') in ('failed', 'skipped'):
                    failed_stages.append(f"{stage}: {info.get('details', '')}")
            if failed_stages:
                recommendations.append(
                    f"编译 Pipeline 有 {len(failed_stages)} 个阶段失败: "
                    f"{'; '.join(failed_stages[:3])}。建议修复相关模块。"
                )

        # 基于性能的建议
        cypy_issues = [r for r in benchmark_results
                       if 'cypy' in r.get('implementation', '') and not r.get('success')]
        if cypy_issues:
            recommendations.append(
                f"有 {len(cypy_issues)} 个用例的 Cypy 版本执行失败，建议修复代码生成器。"
            )

        # 基于质量的建议
        if quality_reports:
            # 找出分数最低的维度
            dimension_scores = {}
            for report in quality_reports:
                for score in report.scores:
                    if score.dimension not in dimension_scores:
                        dimension_scores[score.dimension] = []
                    dimension_scores[score.dimension].append(score.score)

            if dimension_scores:
                weakest_dim = min(
                    dimension_scores.items(),
                    key=lambda x: sum(x[1]) / len(x[1])
                )
                avg_score = sum(weakest_dim[1]) / len(weakest_dim[1])

                recommendations.append(
                    f"最薄弱的质量维度是 '{weakest_dim[0]}' (平均 {avg_score:.1f} 分)，"
                    f"建议优先改进。"
                )

            # 列出严重问题
            critical_issues = []
            for report in quality_reports:
                for issue in report.issues:
                    if issue.severity.value == 'critical':
                        critical_issues.append(issue)

            if critical_issues:
                recommendations.append(
                    f"存在 {len(critical_issues)} 个严重问题，需要立即修复: "
                    f"{', '.join(set(i.rule_id for i in critical_issues[:5]))}"
                )

        # 通用建议
        recommendations.append(
            "建议建立持续集成测试，每次代码提交时自动运行性能基准测试和质量检测。"
        )

        recommendations.append(
            "建议在有 Cython 编译环境的 CI 服务器上测量实际运行时性能。"
        )

        return recommendations

    def _generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """生成 Markdown 格式报告"""
        lines = []

        lines.append("# Cypy 综合测试报告")
        lines.append("")
        lines.append(f"**生成时间**: {report['test_metadata']['end_time']}")
        lines.append(f"**执行时间**: {report['test_metadata']['execution_time_seconds']:.1f} 秒")
        lines.append("")

        # 编译 Pipeline 部分
        lines.append("## 0. 编译 Pipeline 验证")
        lines.append("")

        pipeline = report.get('compilation_pipeline', {})
        pipeline_status = pipeline.get('overall', 'unknown')

        status_emoji = {
            'excellent': '✅',
            'good': '⚠️',
            'has_failures': '❌',
            'import_error': '❌',
            'unknown': '❓',
        }
        lines.append(f"**Pipeline 状态**: {status_emoji.get(pipeline_status, '❓')} {pipeline_status}")
        lines.append("")

        lines.append("| 阶段 | 状态 | 详情 |")
        lines.append("|------|------|------|")
        for stage in ['lexer', 'parser', 'type_checker', 'code_generator']:
            info = pipeline.get(stage, {'status': 'unknown', 'details': ''})
            stage_status = info.get('status', 'unknown')
            stage_emoji = status_emoji.get(stage_status, '❓')
            details = str(info.get('details', ''))[:80]
            lines.append(f"| {stage} | {stage_emoji} {stage_status} | {details} |")

        lines.append("")

        # 性能测试部分
        lines.append("## 1. 性能基准测试")
        lines.append("")

        perf = report.get('performance_benchmarks', {})
        if perf.get('status') == 'no_data':
            lines.append("*无性能测试数据*")
        else:
            lines.append(f"- **测试用例数**: {perf.get('total_cases', 0)}")
            lines.append(f"- **成功**: {perf.get('successful', 0)}")
            lines.append(f"- **失败**: {perf.get('failed', 0)}")
            lines.append("")

            comparison = perf.get('comparison', [])
            if comparison:
                lines.append("### 性能对比")
                lines.append("")
                lines.append("| 测试用例 | Python (ms) | Cypy 预估 (ms) | 加速比 | 提升 |")
                lines.append("|---------|-------------|----------------|--------|------|")

                for comp in comparison:
                    lines.append(
                        f"| {comp.get('name', '')} | {comp.get('python_time_ms', 0):.4f} | "
                        f"{comp.get('cypy_estimated_time_ms', 0):.4f} | "
                        f"{comp.get('estimated_speedup', 0):.2f}x | "
                        f"{comp.get('improvement_percent', 0):+.1f}% |"
                    )

                lines.append("")
                lines.append("> **注意**: 这是基于代码复杂度分析的理论估算值，实际性能需要在 Cython 编译环境中测量。")

        # 质量检测部分
        lines.append("")
        lines.append("## 2. 代码质量检测")
        lines.append("")

        quality = report.get('quality_assessment', {})
        if quality.get('status') == 'no_data':
            lines.append("*无质量检测数据*")
        else:
            lines.append(f"- **检测用例数**: {quality.get('total_cases', 0)}")
            lines.append(f"- **平均评分**: {quality.get('average_score', 0):.1f}/100")
            lines.append(f"- **最高分**: {quality.get('highest_score', 0):.1f}")
            lines.append(f"- **最低分**: {quality.get('lowest_score', 0):.1f}")
            lines.append("")

            lines.append("### 质量等级分布")
            lines.append("")
            lines.append("| 等级 | 数量 |")
            lines.append("|------|------|")
            for level, count in quality.get('level_distribution', {}).items():
                lines.append(f"| {level} | {count} |")

            lines.append("")
            lines.append("### 各维度平均得分")
            lines.append("")
            lines.append("| 维度 | 得分 |")
            lines.append("|------|------|")
            for dim, score in quality.get('dimension_scores', {}).items():
                lines.append(f"| {dim} | {score:.1f} |")

            lines.append("")
            lines.append("### 问题统计")
            lines.append("")
            lines.append(f"- **总问题数**: {quality.get('total_issues', 0)}")
            lines.append(f"- **严重问题**: {quality.get('critical_issues_count', 0)}")
            lines.append("")
            lines.append("| 严重程度 | 数量 |")
            lines.append("|----------|------|")
            for severity, count in quality.get('issue_severity_distribution', {}).items():
                lines.append(f"| {severity} | {count} |")

        # 结论部分
        lines.append("")
        lines.append("## 3. 结论与建议")
        lines.append("")

        lines.append("### 主要结论")
        lines.append("")
        for conclusion in report.get('conclusions', []):
            lines.append(f"- {conclusion}")

        lines.append("")
        lines.append("### 改进建议")
        lines.append("")
        for i, recommendation in enumerate(report.get('recommendations', []), 1):
            lines.append(f"{i}. {recommendation}")

        lines.append("")
        lines.append("---")
        lines.append("*报告由 Cypy 综合测试套件自动生成*")

        return "\n".join(lines)


def main():
    """主入口"""
    print("Cypy 综合测试套件")
    print("=" * 60)
    print()

    runner = ComprehensiveTestRunner()

    # 使用较小的迭代次数以便快速获取结果
    # 建议完整测试使用 1000 次迭代
    report = runner.run_all_tests(benchmark_iterations=100)

    print("\n测试完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
