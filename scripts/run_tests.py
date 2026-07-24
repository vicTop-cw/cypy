#!/usr/bin/env python3
"""
测试运行脚本
运行 Cypy 测试套件并可选同步 DEMO

使用方式:
    python scripts/run_tests.py               # 运行所有测试
    python scripts/run_tests.py --suite parser # 运行指定套件
    python scripts/run_tests.py --sync-demo   # 运行测试并同步 DEMO
    python scripts/run_tests.py --verbose     # 详细输出
"""
import argparse
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_suite.core.runner import TestRunner
from test_suite.utils.demo_writer import DemoWriter


def main():
    parser = argparse.ArgumentParser(
        description="Cypy Test Suite Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--suite",
        help="Run specific test suite (parser/analyzer/codegen/integration)",
        choices=["parser", "analyzer", "codegen", "integration"],
        nargs='+'
    )
    
    parser.add_argument(
        "--sync-demo",
        action="store_true",
        help="Sync passed tests as DEMO examples"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--demo-dir",
        help="DEMO output directory",
        default=os.path.join(os.path.dirname(__file__), '..', 'DEMO')
    )
    
    args = parser.parse_args()
    
    # 导入测试套件
    from test_suite.suites.parser_suite import parser_suite
    from test_suite.suites.analyzer_suite import analyzer_suite
    from test_suite.suites.codegen_suite import codegen_suite
    from test_suite.suites.integration_suite import integration_suite
    
    suite_map = {
        "parser": parser_suite,
        "analyzer": analyzer_suite,
        "codegen": codegen_suite,
        "integration": integration_suite
    }
    
    runner = TestRunner()
    
    if args.suite:
        for suite_name in args.suite:
            if suite_name in suite_map:
                runner.add_suite(suite_map[suite_name])
            else:
                print(f"Error: Unknown suite '{suite_name}'", file=sys.stderr)
                return 1
    else:
        runner.add_suites([parser_suite, analyzer_suite, codegen_suite, integration_suite])
    
    print("=" * 60)
    print("Running Cypy Test Suite...")
    print("=" * 60)
    
    # 运行测试
    result = runner.run_all()
    
    # 保存结果用于报告生成
    runner.results = result.results
    
    # 生成报告
    report = runner.generate_report(verbose=args.verbose)
    print(report)
    
    print("")
    print(f"✓ Passed: {result.passed}")
    print(f"✗ Failed: {result.failed}")
    print(f"~ Skipped: {result.skipped}")
    print(f"⏱  Elapsed: {result.elapsed:.2f}s")
    
    # 同步 DEMO
    if args.sync_demo:
        print("")
        print("=" * 60)
        print("Syncing DEMO examples...")
        print("=" * 60)
        
        demo_writer = DemoWriter(args.demo_dir)
        demo_results = result.get_demo_results()
        
        if demo_results:
            synced = demo_writer.sync_from_tests(demo_results)
            
            for category, files in synced.items():
                print(f"\nCategory: {category}")
                for filepath in files:
                    filename = os.path.basename(filepath)
                    print(f"  ✓ {filename}")
            
            total_demos = sum(len(files) for files in synced.values())
            print(f"\n✓ Total {total_demos} DEMO files synced")
        else:
            print("No DEMO examples found in test results")
    
    # 返回退出码
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
