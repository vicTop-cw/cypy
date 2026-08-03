import argparse
import sys
import os
import time
from typing import Optional


# 彩色输出工具
class Color:
    """终端颜色代码"""
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def colored(text: str, color: str) -> str:
    """给文本添加颜色"""
    return f"{color}{text}{Color.RESET}"


def print_success(message: str) -> None:
    """打印成功消息"""
    print(colored(f"✓ {message}", Color.GREEN))


def print_error(message: str) -> None:
    """打印错误消息"""
    print(colored(f"✗ {message}", Color.RED), file=sys.stderr)


def print_warning(message: str) -> None:
    """打印警告消息"""
    print(colored(f"⚠ {message}", Color.YELLOW))


def print_info(message: str) -> None:
    """打印信息消息"""
    print(colored(f"ℹ {message}", Color.BLUE))


def print_step(message: str, step: int = 0, total: int = 0) -> None:
    """打印步骤消息"""
    if step > 0 and total > 0:
        prefix = colored(f"[{step}/{total}]", Color.CYAN)
    else:
        prefix = colored("[*]", Color.CYAN)
    print(f"{prefix} {message}")


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
        help="Transpile Cypy source to Cython or C",
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
        help="Print generated code",
    )
    transpile_parser.add_argument(
        "--bridge",
        action="store_true",
        help="Use bridge compiler to generate C code instead of Cython",
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
    compile_parser.add_argument(
        "--bridge",
        action="store_true",
        help="Use bridge compiler instead of Cython",
    )

    # build 子命令 - 项目级编译
    build_parser = subparsers.add_parser(
        "build",
        help="Build entire project with cross-module type inference",
    )
    build_parser.add_argument(
        "source",
        nargs="?",
        help="Path to project directory (default: current directory)",
        default=".",
    )
    build_parser.add_argument(
        "-o", "--output",
        help="Output directory",
        default="output",
    )
    build_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    build_parser.add_argument(
        "--entry",
        help="Entry module name (compile only this module and its dependencies)",
        default=None,
    )
    build_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only perform type checking, don't generate code",
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

    # watch 子命令 - 热重载开发服务器
    watch_parser = subparsers.add_parser(
        "watch",
        help="Start hot reload development server",
    )
    watch_parser.add_argument(
        "source",
        nargs="?",
        help="Path to the directory to watch (default: current directory)",
        default=".",
    )
    watch_parser.add_argument(
        "-o", "--output",
        help="Output directory for compiled files",
        default="output",
    )
    watch_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=0.5,
        help="Debounce delay in seconds for file change events",
    )

    # hook 子命令
    hook_parser = subparsers.add_parser(
        "hook",
        help="Cypy hook for Python integration",
    )
    hook_subparsers = hook_parser.add_subparsers(dest="hook_command", help="Hook commands")
    
    # hook install 子命令
    install_parser = hook_subparsers.add_parser(
        "install",
        help="Install Cypy import hook for dynamic code awareness",
    )
    
    # hook uninstall 子命令
    uninstall_parser = hook_subparsers.add_parser(
        "uninstall",
        help="Uninstall Cypy import hook",
    )
    
    # hook status 子命令
    status_parser = hook_subparsers.add_parser(
        "status",
        help="Check if Cypy import hook is installed",
    )
    
    # hook clear-cache 子命令
    clear_cache_parser = hook_subparsers.add_parser(
        "clear-cache",
        help="Clear Cypy compilation cache",
    )
    
    # 原有hook参数（保留兼容）
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

    # 根据命令类型执行不同操作
    if args.command == "hook":
        # 处理新的hook子命令
        if args.hook_command == "install":
            from cypy_hook.hook import install_hook
            install_hook()
            print("✓ Cypy import hook installed successfully")
            print("  Now you can import .py files with '#!bin cypy' header directly")
            return 0
        
        elif args.hook_command == "uninstall":
            from cypy_hook.hook import uninstall_hook
            uninstall_hook()
            print("✓ Cypy import hook uninstalled successfully")
            return 0
        
        elif args.hook_command == "status":
            from cypy_hook.hook import is_hook_installed
            if is_hook_installed():
                print("✓ Cypy import hook is installed")
            else:
                print("✗ Cypy import hook is not installed")
            return 0
        
        elif args.hook_command == "clear-cache":
            from cypy_hook.hook import CypyCacheManager
            cache_manager = CypyCacheManager()
            cache_manager.clear_cache()
            print("✓ Cypy compilation cache cleared successfully")
            return 0
        
        # 原有hook参数（保留兼容）
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

    if not args.source and not hasattr(args, 'eval'):
        print("Error: No source file provided", file=sys.stderr)
        return 1

    elif args.command == "transpile":
        return run_transpile(args)

    elif args.command == "compile":
        return run_compile(args)

    elif args.command == "run":
        return run_run(args)

    elif args.command == "watch":
        return run_watch(args)

    elif args.command == "build":
        return run_build(args)

    else:
        # 默认行为：兼容旧版CLI
        return run_default(args)


def run_transpile(args):
    """执行转译命令"""
    print(colored(f"\n{'='*60}", Color.BOLD))
    print(colored(f"  Cypy Transpiler", Color.BOLD))
    print(colored(f"{'='*60}\n", Color.BOLD))
    
    print_step(f"Source: {args.source}", 1, 3)
    print_step(f"Output: {args.output}", 2, 3)
    
    if args.bridge:
        print_step("Using bridge compiler mode", 3, 3)
    else:
        print_step("Using Cython compiler mode", 3, 3)

    if args.bridge:
        # 使用bridge编译器
        from cypyc.codegen.bridge_generator import BridgeCodegenAdapter
        
        adapter = BridgeCodegenAdapter()
        try:
            print_info("Transpiling to C code...")
            
            c_code = adapter.transpile_file(args.source)
            
            # 确保输出目录存在
            os.makedirs(args.output, exist_ok=True)
            
            # 保存C代码
            source_name = os.path.basename(args.source)
            if source_name.endswith('.cypy'):
                c_filename = source_name[:-5] + '.c'
            elif source_name.endswith('.py'):
                c_filename = source_name[:-3] + '.c'
            else:
                c_filename = source_name + '.c'
            
            c_path = os.path.join(args.output, c_filename)
            with open(c_path, 'w', encoding='utf-8') as f:
                f.write(c_code)
            
            print_success(f"Transpiled successfully (bridge mode)")
            print(f"  {colored('Output:', Color.CYAN)} {c_path}")
            
            if args.emit_code:
                print(f"\n{colored('Generated C code:', Color.BOLD)}")
                print(colored("=" * 60, Color.CYAN))
                print(c_code)
                print(colored("=" * 60, Color.CYAN))
            
            return 0
        except Exception as e:
            print_error(f"Transpile failed (bridge mode):")
            print(f"  {colored('-', Color.RED)} {str(e)}")
            return 1
    else:
        # 使用Cython编译器（原有逻辑）
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(args.output)
        hook.set_verbose(args.verbose)
        
        print_info("Transpiling to Cython code...")
        
        result = hook.transpile_file(args.source)
        
        if result.success:
            print_success("Transpiled successfully")
            print(f"  {colored('Output:', Color.CYAN)} {result.pyx_path}")
            
            if args.emit_code and result.cython_code:
                print(f"\n{colored('Generated Cython code:', Color.BOLD)}")
                print(colored("=" * 60, Color.CYAN))
                print(result.cython_code)
                print(colored("=" * 60, Color.CYAN))
            
            return 0
        else:
            print_error("Transpile failed:")
            for error in result.errors:
                print(f"  {colored('-', Color.RED)} {error}")
            return 1


def run_compile(args):
    """执行编译命令"""
    print(colored(f"\n{'='*60}", Color.BOLD))
    print(colored(f"  Cypy Compiler", Color.BOLD))
    print(colored(f"{'='*60}\n", Color.BOLD))
    
    print_step(f"Source: {args.source}", 1, 2)
    print_step(f"Output: {args.output}", 2, 2)

    if args.bridge:
        # 使用bridge编译器
        from cypyc.codegen.bridge_generator import BridgeCodegenAdapter
        
        adapter = BridgeCodegenAdapter()
        try:
            print_info("Compiling to .pyd file (bridge mode)...")
            
            pyd_path = adapter.compile_file(args.source, args.output)
            
            print_success(f"Compiled successfully (bridge mode)")
            print(f"  {colored('.pyd file:', Color.CYAN)} {pyd_path}")
            
            return 0
        except Exception as e:
            print_error(f"Compile failed (bridge mode):")
            print(f"  {colored('-', Color.RED)} {str(e)}")
            return 1
    else:
        # 使用Cython编译器（原有逻辑）
        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(args.output)
        hook.set_verbose(args.verbose)
        
        print_info("Compiling to .pyd file...")
        
        result = hook.compile_to_pyd(args.source)
        
        if result.success:
            print_success("Compiled successfully")
            print(f"  {colored('.pyd file:', Color.CYAN)} {result.pyd_path}")
            
            if args.verbose:
                print(f"\n{colored('Processing steps:', Color.BOLD)}")
                for i, step in enumerate(result.steps, 1):
                    print(f"  {colored(str(i) + '.', Color.CYAN)} {step}")
            
            return 0
        else:
            print_error("Compile failed:")
            for error in result.errors:
                print(f"  {colored('-', Color.RED)} {error}")
            
            if args.verbose:
                print(f"\n{colored('Processing steps before failure:', Color.BOLD)}")
                for i, step in enumerate(result.steps, 1):
                    print(f"  {colored(str(i) + '.', Color.CYAN)} {step}")
            
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


def run_watch(args):
    """执行热重载监控命令"""
    from cypy_hook.hook import CypyHook
    from cypyc.incremental import HotReloadEngine
    
    print("=" * 60)
    print("  Cypy Hot Reload Development Server")
    print("=" * 60)
    print(f"\nWatching directory: {args.source}")
    print(f"Output directory: {args.output}")
    print(f"Debounce delay: {args.debounce}s")
    print(f"\nPress Ctrl+C to stop\n")
    
    # 创建hook实例
    hook = CypyHook()
    hook.set_output_dir(args.output)
    hook.set_verbose(args.verbose)
    
    # 创建热重载引擎
    engine = HotReloadEngine(hook)
    
    try:
        # 启动热重载引擎
        engine.start([args.source])
        
        # 保持运行，等待用户中断
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n\nStopping hot reload server...")
                break
        
        engine.stop()
        print("✓ Hot reload server stopped")
        return 0
        
    except Exception as e:
        print(f"✗ Hot reload server failed:")
        print(f"  - {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def run_build(args):
    """执行项目级编译命令"""
    from cypyc.project import ProjectCompiler

    print(colored(f"\n{'='*60}", Color.BOLD))
    print(colored(f"  Cypy Project Build", Color.BOLD))
    print(colored(f"{'='*60}\n", Color.BOLD))

    project_root = os.path.abspath(args.source)
    if not os.path.isdir(project_root):
        print_error(f"Project directory not found: {project_root}")
        return 1

    print_step(f"Project root: {project_root}", 1, 5)
    print_step(f"Output directory: {args.output}", 2, 5)

    compiler = ProjectCompiler(
        project_root=project_root,
        output_dir=args.output,
        verbose=args.verbose,
    )

    if args.check_only:
        print_step("Mode: Type check only", 3, 5)
        print_step("Discovering modules...", 4, 5)

        modules = compiler.discover_modules()
        print_info(f"Found {len(modules)} modules")

        print_step("Parsing and type checking...", 5, 5)
        compiler.parse_all_modules()
        compiler.build_dependency_graph()
        compiler.collect_type_exports()

        # 类型检查所有模块
        all_ok = True
        for module_name in compiler._ast_cache:
            ok, errors = compiler.type_check_module(module_name)
            if ok:
                print_success(f"{module_name}: type check passed")
            else:
                print_error(f"{module_name}: type check failed")
                for err in errors:
                    print(f"  {colored('-', Color.RED)} {err}")
                all_ok = False

        if all_ok:
            print_success("All modules passed type checking")
            return 0
        else:
            print_error("Type checking failed")
            return 1
    else:
        print_step("Mode: Full build", 3, 5)
        print_step("Building project...", 4, 5)

        result = compiler.build(entry_point=args.entry)

        # 打印结果
        if result.cycles_detected:
            print_warning(f"Circular dependencies detected: {result.cycles_detected}")

        print_step(f"Compilation order: {' -> '.join(result.compilation_order)}", 5, 5)

        if result.success:
            print_success(f"Project built successfully in {result.total_time:.2f}s")
            print(f"\n  Compiled modules ({len(result.compiled_modules)}):")
            for mod in result.compiled_modules:
                pyd = result.pyd_paths.get(mod, "unknown")
                print(f"    {colored('✓', Color.GREEN)} {mod} -> {pyd}")
            return 0
        else:
            print_error(f"Build failed in {result.total_time:.2f}s")
            print(f"\n  Failed modules ({len(result.failed_modules)}):")
            for mod in result.failed_modules:
                print(f"    {colored('✗', Color.RED)} {mod}")
                for err in result.errors.get(mod, []):
                    print(f"      {err}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
