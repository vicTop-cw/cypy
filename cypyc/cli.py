import argparse
import sys
import os
from typing import Optional


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    # 如果没有传入参数，从sys.argv获取（去掉第一个元素即程序名）
    if args is None:
        args = sys.argv[1:]
    
    # 预处理：如果第一个参数是.cypy文件且不是子命令，自动添加transpile前缀
    if args and len(args) > 0:
        first_arg = args[0]
        subcommands = {"transpile", "compile", "run", "hook"}
        # 检查第一个参数是否是.cypy文件（不是子命令）
        if first_arg not in subcommands and (first_arg.endswith(".cypy") or first_arg.endswith(".py")):
            args = ["transpile"] + args
    
    parser = argparse.ArgumentParser(
        prog="cypyc",
        description="Cypy compiler - A Python-like language that compiles to Cython",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # 子命令：transpile, compile, run, hook
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # 默认命令参数（当没有子命令时使用）
    parser.add_argument(
        "-o", "--output",
        help="Output directory for generated files",
        default="output",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s 0.1.0",
    )

    # transpile 子命令
    transpile_parser = subparsers.add_parser(
        "transpile",
        help="Transpile Cypy source to Cython",
    )
    transpile_parser.add_argument(
        "source",
        help="Path to the .cypy source file",
    )
    transpile_parser.add_argument(
        "-o", "--output",
        help="Output directory",
        default="output",
    )
    transpile_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    transpile_parser.add_argument(
        "--emit-code",
        action="store_true",
        help="Print generated Cython code",
    )
    # 原有选项（保留兼容）
    transpile_parser.add_argument(
        "--generate-setup",
        action="store_true",
        help="Generate setup.py for Cython compilation",
    )
    transpile_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only perform static analysis, don't generate code",
    )
    transpile_parser.add_argument(
        "--emit-ast",
        action="store_true",
        help="Print AST representation",
    )
    transpile_parser.add_argument(
        "--emit-cython",
        action="store_true",
        help="Print generated Cython code",
    )

    # compile 子命令
    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile Cypy source to .pyd file",
    )
    compile_parser.add_argument(
        "source",
        help="Path to the .cypy source file",
    )
    compile_parser.add_argument(
        "-o", "--output",
        help="Output directory",
        default="output",
    )
    compile_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # run 子命令
    run_parser = subparsers.add_parser(
        "run",
        help="Compile and run Cypy code",
    )
    run_parser.add_argument(
        "source",
        help="Path to the .cypy source file",
    )
    run_parser.add_argument(
        "func",
        nargs="?",
        help="Function name to run (default: main)",
        default="main",
    )
    run_parser.add_argument(
        "-o", "--output",
        help="Output directory",
        default="output",
    )
    run_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )

    # hook 子命令
    hook_parser = subparsers.add_parser(
        "hook",
        help="Run Cypy hook for Python integration",
    )
    hook_parser.add_argument(
        "source",
        nargs="?",
        help="Path to .cypy source file or directory",
    )
    hook_parser.add_argument(
        "-o", "--output",
        help="Output directory",
        default="build",
    )
    hook_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    hook_parser.add_argument(
        "--transpile-only",
        action="store_true",
        help="Only transpile to Cython, don't compile",
    )
    hook_parser.add_argument(
        "--compile",
        action="store_true",
        help="Compile to .pyd file",
    )
    hook_parser.add_argument(
        "--run",
        help="Run the specified function after compilation",
    )
    hook_parser.add_argument(
        "--eval",
        help="Evaluate Cypy code directly",
    )

    return parser.parse_args(args)


def main() -> int:
    try:
        args = parse_args()
    except SystemExit as e:
        # argparse在没有参数或参数错误时会调用sys.exit(2)
        # 我们捕获这个异常并返回适当的错误码
        if e.code == 2:
            # 参数错误，返回1表示失败
            return 1
        raise

    if not args.source and not hasattr(args, 'eval'):
        print("Error: No source file provided", file=sys.stderr)
        return 1

    # 根据命令类型执行不同操作
    if args.command == "hook":
        # 调用hook模块
        from cypy_hook.hook import CypyHook
        hook = CypyHook()
        
        # 将hook参数转换为列表格式
        hook_args = []
        if args.source:
            hook_args.append(args.source)
        if args.output:
            hook_args.extend(["-o", args.output])
        if args.verbose:
            hook_args.append("-v")
        if args.transpile_only:
            hook_args.append("--transpile-only")
        if args.compile:
            hook_args.append("--compile")
        if args.run:
            hook_args.extend(["--run", args.run])
        if args.eval:
            hook_args.extend(["--eval", args.eval])
        
        return hook.run_cli(hook_args)

    elif args.command == "transpile":
        return run_transpile(args)

    elif args.command == "compile":
        return run_compile(args)

    elif args.command == "run":
        return run_run(args)

    else:
        # 默认行为：兼容旧版CLI
        return run_default(args)


def run_transpile(args):
    """执行转译命令"""
    from cypy_hook.hook import CypyHook
    
    print(f"Transpiling {args.source}...")
    print(f"Output directory: {args.output}")

    hook = CypyHook()
    hook.set_output_dir(args.output)
    hook.set_verbose(args.verbose)
    
    result = hook.transpile_file(args.source)
    
    if result.success:
        print(f"✓ Transpiled successfully")
        print(f"  Output: {result.pyx_path}")
        
        if args.emit_code and result.cython_code:
            print("\nGenerated Cython code:")
            print("=" * 60)
            print(result.cython_code)
            print("=" * 60)
        
        return 0
    else:
        print(f"✗ Transpile failed:")
        for error in result.errors:
            print(f"  - {error}")
        return 1


def run_compile(args):
    """执行编译命令"""
    from cypy_hook.hook import CypyHook
    
    print(f"Compiling {args.source}...")
    print(f"Output directory: {args.output}")

    hook = CypyHook()
    hook.set_output_dir(args.output)
    hook.set_verbose(args.verbose)
    
    result = hook.compile_to_pyd(args.source)
    
    if result.success:
        print(f"✓ Compiled successfully")
        print(f"  .pyd file: {result.pyd_path}")
        
        if args.verbose:
            print("\nProcessing steps:")
            for i, step in enumerate(result.steps, 1):
                print(f"  {i}. {step}")
        
        return 0
    else:
        print(f"✗ Compile failed:")
        for error in result.errors:
            print(f"  - {error}")
        
        if args.verbose:
            print("\nProcessing steps before failure:")
            for i, step in enumerate(result.steps, 1):
                print(f"  {i}. {step}")
        
        return 1


def run_run(args):
    """执行运行命令"""
    from cypy_hook.hook import CypyHook
    
    print(f"Running {args.source}...")
    print(f"Output directory: {args.output}")

    hook = CypyHook()
    hook.set_output_dir(args.output)
    hook.set_verbose(args.verbose)
    
    result, output = hook.run(args.source, args.func)
    
    if result.success:
        print(f"✓ Execution successful")
        print(f"  Output: {output}")
        
        if args.verbose:
            print("\nProcessing steps:")
            for i, step in enumerate(result.steps, 1):
                print(f"  {i}. {step}")
        
        return 0
    else:
        print(f"✗ Execution failed:")
        for error in result.errors:
            print(f"  - {error}")
        
        if args.verbose:
            print("\nProcessing steps before failure:")
            for i, step in enumerate(result.steps, 1):
                print(f"  {i}. {step}")
        
        return 1


def run_default(args):
    """默认命令执行（兼容旧版）"""
    print(f"Compiling {args.source}...")
    print(f"Output directory: {args.output}")

    if args.verbose:
        print(f"Verbose mode enabled")
        print(f"Generate setup: {args.generate_setup}")
        print(f"Check only: {args.check_only}")
        print(f"Emit AST: {args.emit_ast}")
        print(f"Emit Cython: {args.emit_cython}")

    # 兼容旧版行为：仅转译
    from cypy_hook.hook import CypyHook
    
    hook = CypyHook()
    hook.set_output_dir(args.output)
    hook.set_verbose(args.verbose)
    
    result = hook.transpile_file(args.source)
    
    if result.success:
        print(f"✓ Compilation successful")
        print(f"  Output: {result.pyx_path}")
        
        if args.emit_cython and result.cython_code:
            print("\nGenerated Cython code:")
            print("=" * 60)
            print(result.cython_code)
            print("=" * 60)
        
        return 0
    else:
        print(f"✗ Compilation failed:")
        for error in result.errors:
            print(f"  - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
