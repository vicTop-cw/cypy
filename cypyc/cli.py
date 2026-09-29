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


# BUG-85：子解析器侧的 -o/-v 一律用 SUPPRESS（见 parse_args），谁没写就不往命名空间里落，
# 解析完再按这里的口径补默认值。`hook` 的兼容面历史上默认 build，保持不变。
_COMMAND_OUTPUT_DEFAULTS = {"hook": "build"}
_DEFAULT_OUTPUT_DIR = "output"


def _configure_streams() -> None:
    """将 stdout/stderr 重配置为 UTF-8（errors='replace'），
    避免在 GBK 等控制台编码下打印中文错误信息或 Unicode 符号时崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError, AttributeError):
                pass


def print_success(message: str) -> None:
    """打印成功消息"""
    print(colored(f"[OK] {message}", Color.GREEN))


def print_error(message: str) -> None:
    """打印错误消息"""
    print(colored(f"[FAIL] {message}", Color.RED), file=sys.stderr)


def print_warning(message: str) -> None:
    """打印警告消息"""
    print(colored(f"[WARN] {message}", Color.YELLOW))


def print_info(message: str) -> None:
    """打印信息消息"""
    print(colored(f"[INFO] {message}", Color.BLUE))


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
    # BUG-85：全局与子命令两侧的 -o/-v 一律用 SUPPRESS —— 子解析器会把带 default 的同名选项
    # 重新播种回主命名空间（本机 CPython 3.13 实测：_SubParsersAction 先在**新的**子命名空间里
    # 解析，再把全部键 setattr 回来，子命令的默认值因此覆盖写在子命令**前面**的
    # `cypyc -o DIR transpile x.cypy`，`cypyc -v compile …` 也不打步骤）。
    # SUPPRESS 让「没写」与「写了默认值」可区分，缺省值由 parse_args 末尾按文档口径补齐。
    parser.add_argument(
        "-o", "--output",
        help="Output directory for generated files (default: output)",
        default=argparse.SUPPRESS,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory (default: output)",
        default=argparse.SUPPRESS,
    )
    transpile_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory (default: output)",
        default=argparse.SUPPRESS,
    )
    compile_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory (default: output)",
        default=argparse.SUPPRESS,
    )
    build_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory (default: output)",
        default=argparse.SUPPRESS,
    )
    run_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory for compiled files (default: output)",
        default=argparse.SUPPRESS,
    )
    watch_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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
        help="Output directory (default: build)",
        default=argparse.SUPPRESS,
    )
    hook_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
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

    ns = parser.parse_args(args)

    # BUG-85：-o/-v 在两侧都是 SUPPRESS，所以「谁都没写」才在这里补文档默认值；
    # 写在子命令前面的全局值不会再被子命令的 default 抹掉，两边都写时子命令侧胜出
    # （argparse 的 last-wins：子命名空间最后才 setattr 回主命名空间）。
    if not hasattr(ns, "output"):
        ns.output = _COMMAND_OUTPUT_DEFAULTS.get(ns.command, _DEFAULT_OUTPUT_DIR)
    if not hasattr(ns, "verbose"):
        ns.verbose = False

    return ns


def _report_cache_clear(report) -> int:
    """`hook clear-cache` 的回执：报的数必须等于真删掉的数，删不动的要写出原因（BUG-87）。

    旧实现无条件打印「cleared successfully」，而哈希子目录里的 .pyd/.c/setup.py/build
    一个都没动 —— 用户读到的是成功，磁盘上留着的是旧产物。
    """
    for path, reason in report.failed:
        print(f"  {colored('-', Color.RED)} {path}: {reason}")

    if report.failed:
        print_error(
            f"Cypy compilation cache NOT fully cleared: removed {len(report.removed)} "
            f"file(s), {len(report.failed)} still in place "
            f"(scanned {os.getcwd()})"
        )
        print(
            f"  {colored('Hint:', Color.YELLOW)} a loaded .pyd is locked by its process — "
            f"close the interpreter that imported it and run again"
        )
        return 1

    print_success(
        f"Cypy compilation cache cleared: removed {len(report.removed)} file(s) "
        f"from {len(report.roots)} cache dir(s) under {os.getcwd()}"
    )
    return 0


def main() -> int:
    # 在任意输出之前重配置标准流编码，避免 GBK 控制台打印中文/Unicode 时崩溃
    _configure_streams()
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
            print("[OK] Cypy import hook registered for the current process")
            print("  Nothing is written to disk: the hook dies with this process.")
            print("  To enable it in your own process, call cypy_hook.install_hook() at startup.")
            return 0

        elif args.hook_command == "uninstall":
            from cypy_hook.hook import uninstall_hook
            uninstall_hook()
            print("[OK] Cypy import hook unregistered for the current process")
            return 0

        elif args.hook_command == "status":
            from cypy_hook.hook import is_hook_installed
            if is_hook_installed():
                print("[OK] Cypy import hook is active in the current process")
            else:
                print("[INFO] Cypy import hook is not active in the current process")
                print("  Cypy writes no persistent registration:")
                print("  the hook lives or dies with the process that installed it.")
            return 0
        
        elif args.hook_command == "clear-cache":
            from cypy_hook.hook import CypyCacheManager
            return _report_cache_clear(CypyCacheManager().clear_cache())
        
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


def _read_cli_source(path: str):
    """读源文件文本；失败时打印错误并返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        print_error(f"Cannot read source: {exc}")
        return None


def _transpile_emit_ast(source_path: str) -> int:
    """`--emit-ast`：打印解析后的 AST 概要（帮助文本承诺的 AST representation）。"""
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import ASTNode, Parser
    from cypyc.parser.preprocessor import Preprocessor

    text = _read_cli_source(source_path)
    if text is None:
        return 1
    try:
        ast = Parser(list(Lexer(Preprocessor().process(text)).tokenize())).parse()
    except Exception as exc:  # noqa: BLE001 — 解析失败要以退出码交代，不是 traceback
        print_error(f"AST dump failed: {exc}")
        return 1

    print(f"\n{colored('AST:', Color.BOLD)} {source_path}")
    stack = [(ast, 0)]
    seen = set()
    while stack:
        node, depth = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        label = getattr(node, "kind", type(node).__name__)
        name = getattr(node, "name", None)
        row = "  " * depth + (f"{label} {name}" if name else label)
        line_no = getattr(node, "line", None)
        if isinstance(line_no, int):
            row += f"  @ {line_no}:{getattr(node, 'col', '?')}"
        print(row)
        children = []
        for value in vars(node).values():
            if isinstance(value, ASTNode):
                children.append((value, depth + 1))
            elif isinstance(value, list):
                children.extend((item, depth + 1) for item in value
                                if isinstance(item, ASTNode))
        stack.extend(reversed(children))
    return 0


def _transpile_check_only(args) -> int:
    """`--check-only`：只做静态分析，不落任何产物（帮助文本承诺的口径）。"""
    from cypy_hook.hook import CypyHook

    text = _read_cli_source(args.source)
    if text is None:
        return 1
    hook = CypyHook()
    hook.set_verbose(args.verbose)
    _, errors = hook.analyze_only(text)
    if errors:
        print_error(f"Static analysis found {len(errors)} problem(s):")
        for error in errors:
            print(f"  {colored('-', Color.RED)} {error}")
        return 1
    print_success("Static analysis passed (no code generated)")
    return 0


def _transpile_generate_setup(output_dir: str, artifact_path: str) -> int:
    """`--generate-setup`：在产物同目录写一个可直接 build_ext 的 setup.py。"""
    from cypyc.codegen.setup_generator import SetupGenerator

    module_name = os.path.splitext(os.path.basename(artifact_path))[0]
    generator = SetupGenerator()
    generator.set_module_name(module_name)
    generator.add_source(artifact_path)
    setup_path = os.path.join(output_dir, "setup.py")
    try:
        with open(setup_path, "w", encoding="utf-8") as f:
            f.write(generator.generate())
    except OSError as exc:
        print_error(f"Cannot write setup.py: {exc}")
        return 1
    print_success(f"setup.py written: {setup_path}")
    return 0


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

    if args.emit_ast:
        rc = _transpile_emit_ast(args.source)
        if rc:
            return rc

    if args.check_only:
        return _transpile_check_only(args)

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

            if args.emit_cython:
                print_info("--emit-cython does not apply in --bridge mode; "
                           "the emitted language is C")

            if args.emit_code:
                print(f"\n{colored('Generated C code:', Color.BOLD)}")
                print(colored("=" * 60, Color.CYAN))
                print(c_code)
                print(colored("=" * 60, Color.CYAN))

            if args.generate_setup:
                return _transpile_generate_setup(args.output, c_path)

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

            if (args.emit_code or args.emit_cython) and result.cython_code:
                print(f"\n{colored('Generated Cython code:', Color.BOLD)}")
                print(colored("=" * 60, Color.CYAN))
                print(result.cython_code)
                print(colored("=" * 60, Color.CYAN))

            if args.generate_setup:
                return _transpile_generate_setup(args.output, result.pyx_path)

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

    # hook.run() 把 run_module 的异常塞进 result.errors 后仍返回 success=True，
    # 只看 success 会把「编译产物加载失败」报成执行成功（曾使 13 个 golden 在绿灯下烂掉）。
    if result.success and not result.errors:
        print(f"[OK] Execution successful")
        print(f"  Output: {output}")
        
        if args.verbose:
            print("\nProcessing steps:")
            for i, step in enumerate(result.steps, 1):
                print(f"  {i}. {step}")
        
        return 0
    else:
        print(f"[FAIL] Execution failed:")
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
        print(f"[OK] Compilation successful")
        print(f"  Output: {result.pyx_path}")
        
        if args.emit_cython and result.cython_code:
            print("\nGenerated Cython code:")
            print("=" * 60)
            print(result.cython_code)
            print("=" * 60)
        
        return 0
    else:
        print(f"[FAIL] Compilation failed:")
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
    
    # 创建热重载引擎：产物发布到 -o 指定的目录，并把每批结果打到 stdout
    engine = HotReloadEngine(hook, artifact_dir=args.output)

    def report_reload(result):
        names = [os.path.basename(p) for p in result.published_artifacts]
        if names:
            print(f"[Watch] Published {len(names)} artifact(s) to {args.output}: "
                  f"{', '.join(names)}")
        else:
            print(f"[Watch] No artifacts published (batch had no successful compile)")
        if result.errors:
            for error in result.errors:
                print(f"[Watch]   - {error}")

    try:
        # 启动热重载引擎
        engine.start([args.source], on_reload=report_reload, debounce_delay=args.debounce)
        
        # 保持运行，等待用户中断
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n\nStopping hot reload server...")
                break
        
        engine.stop()
        print("[OK] Hot reload server stopped")
        return 0
        
    except Exception as e:
        print(f"[FAIL] Hot reload server failed:")
        print(f"  - {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def _check_scope(compiler, entry, checked):
    """按 `--entry` 裁剪 `build --check-only` 的检查范围（BUG-89）。

    口径与全量 build 的 `ProjectCompiler.build(entry_point=…)` 一致：入口模块 + 它的传递依赖。
    返回 `(scope, reason)`：entry 解析不出任何模块时 reason 非空，调用方据此**失败**，
    而不是悄悄退回成整项目检查——那正是承诺失效的样子。
    """
    if not entry:
        return list(checked), None

    deps = compiler.get_dependency_graph().get_transitive_dependencies(entry)
    scope = [name for name in checked if name == entry or name in deps]
    if not scope:
        return [], (
            f"entry_point {entry!r} resolved to nothing: it is not a discovered "
            f"module of this project (known modules: {sorted(checked)})"
        )
    return scope, None


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

        # BUG-89：检查范围同样受 --entry 约束（docs/USAGE.md:102「仅 main 模块及其依赖」）。
        # 旧分支自成一段、从不读 args.entry，所以 --check-only --entry X 扫的永远是全项目。
        scope, reason = _check_scope(compiler, args.entry, list(compiler._ast_cache))
        if reason:
            print_error(reason)
            return 1

        if args.entry:
            print_info(
                f"Checking {len(scope)} module(s) in entry scope of "
                f"{args.entry!r}: {', '.join(scope)}"
            )
        else:
            print_info(f"Checking {len(scope)} module(s) (whole project)")

        all_ok = True
        for module_name in scope:
            ok, errors = compiler.type_check_module(module_name)
            if ok:
                print_success(f"{module_name}: type check passed")
            else:
                print_error(f"{module_name}: type check failed")
                for err in errors:
                    print(f"  {colored('-', Color.RED)} {err}")
                all_ok = False

        if all_ok:
            print_success("All modules in scope passed type checking")
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
                print(f"    {colored('[OK]', Color.GREEN)} {mod} -> {pyd}")
            return 0
        else:
            print_error(f"Build failed in {result.total_time:.2f}s")
            _report_build_failures(result)
            return 1


def _report_build_failures(result) -> None:
    """把 `ProjectCompileResult` 的失败原因原样打到屏幕上（BUG-88）。

    `errors` 的键不只有模块名：入口点被拒是 `_entry_point`、成环被丢弃是 `_cycles`、
    模块名冲突是 `_discovery`、什么都没编译是 `_`。旧实现只遍历 `failed_modules`，
    于是这些键里的句子永远打印不出来，屏幕上只剩 `Failed modules (0)` 配 rc=1。
    """
    failed = list(result.failed_modules)
    if failed:
        print(f"\n  Failed modules ({len(failed)}):")
        for mod in failed:
            print(f"    {colored('[FAIL]', Color.RED)} {mod}")
            for err in result.errors.get(mod, []):
                print(f"      {err}")

    reasons = {key: errs for key, errs in result.errors.items() if key not in failed}
    if reasons:
        print(f"\n  Reason(s) ({len(reasons)}):")
        for key in sorted(reasons):
            for err in reasons[key]:
                print(f"    {colored('-', Color.RED)} {err}")
    elif not failed:
        print(
            f"\n  {colored('Reason(s) (0):', Color.YELLOW)} the build reported failure but "
            f"recorded no module and no reason — rerun with -v for the compiler log"
        )


if __name__ == "__main__":
    sys.exit(main())
