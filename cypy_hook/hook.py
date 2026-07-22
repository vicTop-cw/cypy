import sys
import os
import subprocess
import importlib.util
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass


@dataclass
class CompileResult:
    """编译结果数据类"""
    success: bool
    cython_code: Optional[str] = None
    pyx_path: Optional[str] = None
    pyd_path: Optional[str] = None
    errors: List[str] = None
    steps: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.steps is None:
            self.steps = []


class CypyHook:
    def __init__(self):
        self.source_dir = ""
        self.output_dir = ""
        self.verbose = False
        self._compiler = None

    def set_source_dir(self, path: str) -> None:
        self.source_dir = path

    def set_output_dir(self, path: str) -> None:
        self.output_dir = path

    def set_verbose(self, verbose: bool) -> None:
        self.verbose = verbose

    def _log(self, message: str) -> None:
        """记录并可选打印日志"""
        if self.verbose:
            print(f"[CypyHook] {message}")

    def _parse_and_analyze(self, source: str) -> Tuple[Any, List[str]]:
        """解析和分析源代码，返回AST和错误列表"""
        from cypyc.parser.preprocessor import Preprocessor
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
        from cypyc.analyzer.type_checker import TypeChecker
        from cypyc.analyzer.pointer_checker import PointerChecker
        from cypyc.analyzer.cycle_detector import CycleDetector
        from cypyc.analyzer.build_block_checker import BuildBlockChecker

        errors = []

        try:
            self._log("Step 1: Preprocessing...")
            preprocessor = Preprocessor()
            source = preprocessor.process(source)

            self._log("Step 2: Tokenizing...")
            lexer = Lexer(source)
            tokens = list(lexer.tokenize())

            self._log("Step 3: Parsing...")
            parser = Parser(tokens)
            ast = parser.parse()

            self._log("Step 4: Scope analysis...")
            scope_analyzer = ScopeAnalyzer()
            scope_analyzer.analyze(ast)
            if scope_analyzer.errors:
                errors.extend(scope_analyzer.errors)

            self._log("Step 5: Type checking...")
            type_checker = TypeChecker()
            type_checker.check(ast)
            if type_checker.errors:
                errors.extend(type_checker.errors)

            self._log("Step 5.5: Pointer checking...")
            pointer_checker = PointerChecker()
            pointer_checker.check(ast)
            if pointer_checker.errors:
                errors.extend(pointer_checker.errors)

            self._log("Step 6: Cycle detection...")
            cycle_detector = CycleDetector()
            has_cycle, cycle_path = cycle_detector.analyze(ast)
            if has_cycle:
                errors.append(cycle_detector.format_cycle_error(cycle_path))

            self._log("Step 7: Build block checking...")
            build_block_checker = BuildBlockChecker()
            build_block_checker.check(ast)
            if build_block_checker.errors:
                errors.extend(build_block_checker.errors)

            return ast, errors

        except Exception as e:
            errors.append(f"Compilation error: {e}")
            return None, errors

    # ==================== 模式1：基础转译测试模式 ====================

    def transpile(self, source: str) -> CompileResult:
        """
        基础转译测试模式：仅将.cypy代码转译为Cython代码
        
        返回：
            CompileResult: 包含转译结果、错误信息和处理步骤
        """
        result = CompileResult(success=False)
        result.steps.append("基础转译模式开始")

        try:
            self._log("=== 基础转译模式 ===")
            
            ast, errors = self._parse_and_analyze(source)
            if errors:
                result.errors = errors
                return result

            self._log("Step 8: Generating Cython code...")
            from cypyc.codegen.cython_generator import CythonGenerator
            generator = CythonGenerator()
            cython_code = generator.generate(ast)
            
            result.cython_code = cython_code
            result.success = True
            result.steps.append("转译成功完成")
            
            return result

        except Exception as e:
            result.errors.append(f"转译错误: {e}")
            return result

    def transpile_file(self, source_path: str) -> CompileResult:
        """转译单个文件"""
        result = CompileResult(success=False)
        result.steps.append(f"开始转译文件: {source_path}")

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source = f.read()

            result = self.transpile(source)
            
            if result.success and result.cython_code:
                os.makedirs(self.output_dir, exist_ok=True)
                pyx_path = os.path.join(
                    self.output_dir,
                    os.path.basename(source_path).replace(".cypy", ".pyx")
                )
                with open(pyx_path, "w", encoding="utf-8") as f:
                    f.write(result.cython_code)
                result.pyx_path = pyx_path
                result.steps.append(f"Cython文件已生成: {pyx_path}")

            return result

        except Exception as e:
            result.errors.append(f"读取文件错误: {e}")
            return result

    # ==================== 模式2：一步到位自动处理模式 ====================

    def compile_to_pyd(self, source_path: str) -> CompileResult:
        """
        一步到位自动处理模式：转译并编译为.pyd文件
        
        返回：
            CompileResult: 包含编译结果、文件路径、错误信息和处理步骤
        """
        result = CompileResult(success=False)
        result.steps.append("=== 一步到位编译模式 ===")
        result.steps.append(f"开始处理文件: {source_path}")

        try:
            # Step 1: 转译
            self._log("Step 1: Transpiling...")
            pyx_result = self.transpile_file(source_path)
            result.steps.extend(pyx_result.steps)
            
            if not pyx_result.success:
                result.errors = pyx_result.errors
                return result

            pyx_path = pyx_result.pyx_path
            
            # Step 2: 生成setup.py
            self._log("Step 2: Generating setup.py...")
            from cypyc.codegen.setup_generator import SetupGenerator
            setup_generator = SetupGenerator()
            module_name = os.path.basename(pyx_path).replace(".pyx", "")
            setup_code = setup_generator.generate(module_name, [pyx_path])
            
            setup_path = os.path.join(self.output_dir, "setup.py")
            with open(setup_path, "w", encoding="utf-8") as f:
                f.write(setup_code)
            result.steps.append(f"setup.py已生成: {setup_path}")

            # Step 3: 编译为.pyd
            self._log("Step 3: Compiling to .pyd...")
            old_cwd = os.getcwd()
            try:
                os.chdir(self.output_dir)
                compile_cmd = [
                    sys.executable, "setup.py", "build_ext", "--inplace"
                ]
                process = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if process.returncode != 0:
                    result.errors.append(f"编译错误: {process.stderr}")
                    result.steps.append(f"编译失败: {process.returncode}")
                    return result
                
                result.steps.append(f"编译成功: {process.stdout[:200]}...")

                # Step 4: 查找生成的.pyd文件
                pyd_files = []
                for root, dirs, files in os.walk(self.output_dir):
                    for file in files:
                        if file.endswith(".pyd") or file.endswith(".so"):
                            pyd_files.append(os.path.join(root, file))
                
                if pyd_files:
                    result.pyd_path = pyd_files[0]
                    result.steps.append(f".pyd文件已生成: {result.pyd_path}")
                else:
                    result.errors.append("未找到生成的.pyd文件")
                    return result

            finally:
                os.chdir(old_cwd)

            result.success = True
            return result

        except subprocess.TimeoutExpired:
            result.errors.append("编译超时")
            return result
        except Exception as e:
            result.errors.append(f"编译错误: {e}")
            return result

    def run_module(self, pyd_path: str, func_name: str, *args, **kwargs) -> Any:
        """
        运行已编译模块中的函数
        
        参数：
            pyd_path: .pyd文件路径
            func_name: 要调用的函数名
            *args, **kwargs: 函数参数
        
        返回：
            Any: 函数返回值
        """
        try:
            module_dir = os.path.dirname(pyd_path)
            module_name = os.path.basename(pyd_path).replace(".pyd", "").replace(".so", "")
            
            # 添加模块目录到sys.path
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
            
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, pyd_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 调用函数
            if hasattr(module, func_name):
                func = getattr(module, func_name)
                return func(*args, **kwargs)
            else:
                raise AttributeError(f"模块中不存在函数: {func_name}")
        
        except Exception as e:
            raise RuntimeError(f"运行模块错误: {e}")

    def run(self, source_path: str, func_name: str = None, *args, **kwargs) -> Tuple[CompileResult, Any]:
        """
        一步到位运行：转译、编译、运行
        
        参数：
            source_path: .cypy文件路径
            func_name: 要调用的函数名（可选）
            *args, **kwargs: 函数参数
        
        返回：
            Tuple[CompileResult, Any]: 编译结果和函数返回值
        """
        result = self.compile_to_pyd(source_path)
        
        if not result.success or not result.pyd_path:
            return result, None
        
        if func_name:
            try:
                self._log(f"Step 4: Running {func_name}...")
                output = self.run_module(result.pyd_path, func_name, *args, **kwargs)
                result.steps.append(f"函数调用成功: {func_name}")
                return result, output
            except Exception as e:
                result.errors.append(f"运行错误: {e}")
                return result, None
        
        return result, None

    # ==================== 模式3：Hook集成模式 ====================

    def compile_and_import(self, source_code: str, module_name: str = "cypy_module") -> Tuple[CompileResult, Any]:
        """
        Hook集成模式：编译cypy代码并返回可导入的模块
        
        参数：
            source_code: Cypy源代码
            module_name: 模块名称
        
        返回：
            Tuple[CompileResult, Any]: 编译结果和模块对象
        """
        result = CompileResult(success=False)
        result.steps.append("=== Hook集成模式 ===")
        result.steps.append(f"开始编译代码片段，模块名: {module_name}")

        try:
            # Step 1: 创建临时文件
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                source_path = os.path.join(tmp_dir, f"{module_name}.cypy")
                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(source_code)
                
                self._log("Step 1: Created temporary source file")
                
                # Step 2: 编译为.pyd
                old_output_dir = self.output_dir
                self.output_dir = tmp_dir
                
                compile_result = self.compile_to_pyd(source_path)
                result.steps.extend(compile_result.steps)
                
                if not compile_result.success or not compile_result.pyd_path:
                    result.errors = compile_result.errors
                    self.output_dir = old_output_dir
                    return result, None
                
                # Step 3: 导入模块
                self._log("Step 3: Importing module...")
                module_dir = os.path.dirname(compile_result.pyd_path)
                spec = importlib.util.spec_from_file_location(module_name, compile_result.pyd_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                result.success = True
                result.pyd_path = compile_result.pyd_path
                result.steps.append("模块导入成功")
                
                self.output_dir = old_output_dir
                return result, module

        except Exception as e:
            result.errors.append(f"Hook集成错误: {e}")
            return result, None

    def eval(self, source_code: str) -> Any:
        """
        直接求值cypy代码片段
        
        参数：
            source_code: Cypy源代码片段
        
        返回：
            Any: 最后一个表达式的值（如果有）
        """
        result, module = self.compile_and_import(source_code, "__cypy_eval__")
        
        if not result.success:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)
            return None
        
        # 尝试获取最后一个表达式的值
        if hasattr(module, "__result__"):
            return getattr(module, "__result__")
        
        return module

    # ==================== 原有方法 ====================

    def compile_file(self, source_path: str) -> Optional[str]:
        """原有方法：编译单个文件（兼容旧API）"""
        result = self.transpile_file(source_path)
        return result.pyx_path if result.success else None

    def compile_directory(self, dir_path: str = None) -> list:
        """原有方法：编译目录中的所有文件（兼容旧API）"""
        if dir_path is None:
            dir_path = self.source_dir

        results = []
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".cypy"):
                    source_path = os.path.join(root, file)
                    result = self.compile_file(source_path)
                    results.append(result)
        return results

    def run_cli(self, args: list) -> int:
        """CLI运行入口"""
        import argparse

        parser = argparse.ArgumentParser(
            description="Cypy preprocessor hook",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )

        parser.add_argument(
            "source",
            nargs="?",
            help="Path to .cypy source file or directory",
        )

        parser.add_argument(
            "-o", "--output",
            help="Output directory",
            default="build",
        )

        parser.add_argument(
            "-v", "--verbose",
            action="store_true",
            help="Verbose output",
        )

        parser.add_argument(
            "--transpile-only",
            action="store_true",
            help="Only transpile to Cython, don't compile",
        )

        parser.add_argument(
            "--compile",
            action="store_true",
            help="Compile to .pyd file",
        )

        parser.add_argument(
            "--run",
            help="Run the specified function after compilation",
        )

        parser.add_argument(
            "--eval",
            help="Evaluate Cypy code directly",
        )

        parsed_args = parser.parse_args(args)

        self.set_source_dir(parsed_args.source or ".")
        self.set_output_dir(parsed_args.output)
        self.set_verbose(parsed_args.verbose)

        if parsed_args.eval:
            result, module = self.compile_and_import(parsed_args.eval)
            if result.success:
                print("Evaluation successful")
                return 0
            else:
                for error in result.errors:
                    print(f"Error: {error}", file=sys.stderr)
                return 1

        if os.path.isfile(parsed_args.source):
            if parsed_args.transpile_only:
                result = self.transpile_file(parsed_args.source)
                if result.success:
                    print(f"Transpiled to {result.pyx_path}")
                    if result.cython_code:
                        print("\nGenerated Cython code:")
                        print("=" * 50)
                        print(result.cython_code)
                    return 0
                else:
                    for error in result.errors:
                        print(f"Error: {error}", file=sys.stderr)
                    return 1
            
            elif parsed_args.compile:
                result = self.compile_to_pyd(parsed_args.source)
                if result.success:
                    print(f"Compiled to {result.pyd_path}")
                    return 0
                else:
                    for error in result.errors:
                        print(f"Error: {error}", file=sys.stderr)
                    return 1
            
            elif parsed_args.run:
                result, output = self.run(parsed_args.source, parsed_args.run)
                if result.success:
                    print(f"Output: {output}")
                    return 0
                else:
                    for error in result.errors:
                        print(f"Error: {error}", file=sys.stderr)
                    return 1
            
            else:
                # 默认行为：仅转译
                result = self.transpile_file(parsed_args.source)
                return 0 if result.success else 1

        else:
            results = self.compile_directory(parsed_args.source)
            failures = [r for r in results if r is None]
            return 0 if not failures else 1


def main():
    hook = CypyHook()
    sys.exit(hook.run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
