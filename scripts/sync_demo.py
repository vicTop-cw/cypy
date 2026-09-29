#!/usr/bin/env python3
"""
DEMO 同步脚本
将测试通过的代码自动写入 DEMO 目录

使用方式:
    python scripts/sync_demo.py               # 同步所有测试通过的示例
    python scripts/sync_demo.py --category parser # 同步指定分类
    python scripts/sync_demo.py --clean       # 清理所有 DEMO
"""
import argparse
import sys
import os

# 修复 Windows 控制台编码问题（GBK 无法输出 ✓/⚠ 等 Unicode 字符）
# ——与 scripts/run_tests.py:17-22 对齐；此前 --category integration 同步 3 个
# DEMO 成功后会在打印 ✓ 时 UnicodeEncodeError 崩溃。
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from test_suite.core.runner import TestRunner
from test_suite.utils.demo_writer import DemoWriter


def main():
    parser = argparse.ArgumentParser(
        description="Cypy DEMO Sync Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--category",
        help="Sync specific category (parser/analyzer/codegen/integration)",
        choices=["parser", "analyzer", "codegen", "integration"]
    )
    
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean all DEMO files"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all DEMO files"
    )
    
    parser.add_argument(
        "--demo-dir",
        help="DEMO directory",
        default=os.path.join(os.path.dirname(__file__), '..', 'examples', 'demos', 'legacy')
    )
    
    args = parser.parse_args()
    
    demo_writer = DemoWriter(args.demo_dir)
    
    if args.clean:
        print(f"Cleaning DEMO directory: {demo_writer.demo_dir}")
        deleted = demo_writer.clean_demo(args.category)
        print(f"✓ Deleted {deleted} files")
        return 0
    
    if args.list:
        print(f"Listing DEMO files in: {demo_writer.demo_dir}")
        demos = demo_writer.list_demos(args.category)
        
        if demos:
            for demo in demos:
                print(f"  {demo}")
        else:
            print("  No DEMO files found")
        
        print(f"\nTotal: {len(demos)} files")
        return 0
    
    # 默认：运行测试并同步 DEMO
    print("=" * 60)
    print("Running tests and syncing DEMO...")
    print("=" * 60)
    
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
    
    if args.category:
        if args.category in suite_map:
            runner.add_suite(suite_map[args.category])
        else:
            print(f"Error: Unknown category '{args.category}'", file=sys.stderr)
            return 1
    else:
        runner.add_suites([parser_suite, analyzer_suite, codegen_suite, integration_suite])
    
    # 运行测试
    result = runner.run_all()
    
    print(f"\nTest Results:")
    print(f"  Passed: {result.passed}")
    print(f"  Failed: {result.failed}")
    print(f"  Skipped: {result.skipped}")
    
    # 获取 DEMO 结果
    demo_results = result.get_demo_results()
    
    if demo_results:
        print(f"\nSyncing {len(demo_results)} DEMO examples...")
        
        # 如果指定了分类，过滤
        if args.category:
            demo_results = [r for r in demo_results if r.demo_category == args.category]
        
        synced = demo_writer.sync_from_tests(demo_results)
        
        for category, files in synced.items():
            print(f"\nCategory: {category}")
            for filepath in files:
                filename = os.path.basename(filepath)
                print(f"  ✓ {filename}")
        
        total_demos = sum(len(files) for files in synced.values())
        print(f"\n✓ Total {total_demos} DEMO files synced")
        
        # FIX T0r61.5.2 (defect 4): DemoWriter 只写不删——把目录中"本次运行没有任何
        # 测试生成点"的文件列为 orphan 报告出来，让流水线的漂移可见、可被守卫测试钉住。
        generated = {os.path.abspath(p) for files in synced.values() for p in files}
        orphans = [p for p in demo_writer.list_demos(args.category)
                   if os.path.abspath(p) not in generated]
        if orphans:
            print(f"\n⚠ {len(orphans)} DEMO file(s) have no generating site in this run "
                  "(stale/orphan; DemoWriter never deletes):")
            for path in orphans:
                print(f"  ? {path}")
    else:
        print("\nNo DEMO examples found")
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
