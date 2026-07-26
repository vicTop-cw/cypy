import sys
import os
import subprocess
import importlib.util
import shutil
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
        self._incremental_compiler = None
    
    def _get_incremental_compiler(self):
        """懒加载增量编译器"""
        if self._incremental_compiler is None:
            from cypyc.incremental import IncrementalCompiler
            self._incremental_compiler = IncrementalCompiler()
        return self._incremental_compiler

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

    def transpile_file(self, source_path: str, incremental: bool = True) -> CompileResult:
        """转译单个文件"""
        result = CompileResult(success=False)
        result.steps.append(f"开始转译文件: {source_path}")

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source = f.read()

            # 增量编译检查
            if incremental:
                incremental_compiler = self._get_incremental_compiler()
                
                # 先解析获取AST
                from cypyc.parser.preprocessor import Preprocessor
                from cypyc.parser.lexer import Lexer
                from cypyc.parser.parser import Parser
                
                preprocessor = Preprocessor()
                processed_source = preprocessor.process(source)
                
                lexer = Lexer(processed_source)
                tokens = list(lexer.tokenize())
                
                parser = Parser(tokens)
                ast = parser.parse()
                
                # 分析增量编译结果
                inc_result = incremental_compiler.analyze_changes(source_path, ast)
                
                if inc_result.cache_hit:
                    self._log(f"增量编译: 缓存命中，跳过编译")
                    result.steps.append("增量编译: 缓存命中，使用缓存结果")
                    
                    # 检查缓存的.pyd文件是否存在
                    cache_manager = CypyCacheManager()
                    cached_pyd = cache_manager.get_cached_pyd(source_path)
                    if cached_pyd and os.path.exists(cached_pyd):
                        result.success = True
                        result.steps.append("增量编译: 缓存的.pyd文件有效")
                        # 设置pyd_path以便上层compile_to_pyd可以使用
                        result.pyd_path = cached_pyd
                        return result
                
                self._log(f"增量编译: 需要重新编译，受影响定义: {inc_result.affected_definitions}")
                result.steps.append(f"增量编译: 受影响定义数: {len(inc_result.affected_definitions)}")
            
            # 执行正常转译
            result = self.transpile(source)
            
            if result.success and result.cython_code:
                os.makedirs(self.output_dir, exist_ok=True)
                # 处理不同的源文件扩展名
                basename = os.path.basename(source_path)
                if basename.endswith(".cypy"):
                    pyx_filename = basename.replace(".cypy", ".pyx")
                elif basename.endswith(".py"):
                    pyx_filename = basename.replace(".py", ".pyx")
                else:
                    pyx_filename = basename + ".pyx"
                
                pyx_path = os.path.join(self.output_dir, pyx_filename)
                with open(pyx_path, "w", encoding="utf-8") as f:
                    f.write(result.cython_code)
                result.pyx_path = pyx_path
                result.steps.append(f"Cython文件已生成: {pyx_path}")

                # 更新增量编译缓存
                if incremental:
                    incremental_compiler = self._get_incremental_compiler()
                    incremental_compiler.update_cache(source_path, ast, result.cython_code)

            return result

        except Exception as e:
            result.errors.append(f"读取文件错误: {e}")
            return result

    # ==================== 模式2：一步到位自动处理模式 ====================

    def compile_to_pyd(self, source_path: str, output_dir: str = None, force_recompile: bool = False) -> CompileResult:
        """
        一步到位自动处理模式：转译并编译为.pyd文件
        
        参数：
            source_path: 源文件路径
            output_dir: 输出目录（可选，默认为self.output_dir）
            force_recompile: 是否强制重新编译（跳过增量编译缓存）
            
        返回：
            CompileResult: 包含编译结果、文件路径、错误信息和处理步骤
        """
        result = CompileResult(success=False)
        result.steps.append("=== 一步到位编译模式 ===")
        result.steps.append(f"开始处理文件: {source_path}")

        # 使用参数output_dir或回退到实例属性
        actual_output_dir = output_dir if output_dir else self.output_dir
        
        try:
            # Step 1: 转译（需要临时设置output_dir）
            self._log("Step 1: Transpiling...")
            old_output_dir = self.output_dir
            self.output_dir = actual_output_dir
            try:
                pyx_result = self.transpile_file(source_path, incremental=not force_recompile)
            finally:
                self.output_dir = old_output_dir
            result.steps.extend(pyx_result.steps)
            
            if not pyx_result.success:
                result.errors = pyx_result.errors
                return result
            
            # 如果缓存命中，直接返回已有的.pyd路径
            if pyx_result.pyd_path:
                result.pyd_path = pyx_result.pyd_path
                result.success = True
                result.steps.append(f"使用缓存的.pyd文件: {result.pyd_path}")
                return result

            pyx_path = pyx_result.pyx_path
            if not pyx_path:
                result.errors.append("未生成.pyx文件")
                return result
            
            # Step 2: 生成setup.py
            self._log("Step 2: Generating setup.py...")
            from cypyc.codegen.setup_generator import SetupGenerator
            setup_generator = SetupGenerator()
            module_name = os.path.basename(pyx_path).replace(".pyx", "")
            setup_generator.set_module_name(module_name)
            setup_generator.add_source(pyx_path)
            setup_code = setup_generator.generate()
            
            setup_path = os.path.join(actual_output_dir, "setup.py")
            with open(setup_path, "w", encoding="utf-8") as f:
                f.write(setup_code)
            result.steps.append(f"setup.py已生成: {setup_path}")

            # Step 3: 编译为.pyd
            self._log("Step 3: Compiling to .pyd...")
            
            old_cwd = os.getcwd()
            temp_build_dir = None
            
            try:
                # 检查目标.pyd文件是否存在（可能被锁定）
                target_pyd_name = f"{module_name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd"
                target_pyd_path = os.path.join(actual_output_dir, target_pyd_name)
                is_locked = os.path.exists(target_pyd_path)
                
                if is_locked:
                    # 文件被锁定，使用临时目录编译
                    import tempfile
                    temp_build_dir = tempfile.mkdtemp()
                    # 复制setup.py和.pyx文件到临时目录
                    shutil.copy(os.path.join(old_cwd, actual_output_dir, "setup.py"), temp_build_dir)
                    shutil.copy(pyx_path, temp_build_dir)
                    os.chdir(temp_build_dir)
                    self._log(f"Using temp directory for compilation due to file lock: {temp_build_dir}")
                else:
                    os.chdir(actual_output_dir)
                
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
                current_dir = os.getcwd()
                for root, dirs, files in os.walk(current_dir):
                    for file in files:
                        if file.endswith(".pyd") or file.endswith(".so"):
                            pyd_files.append(os.path.join(root, file))
                
                if pyd_files:
                    temp_pyd_path = pyd_files[0]
                    
                    if is_locked:
                        # 将新编译的.pyd文件复制到目标位置
                        shutil.copy(temp_pyd_path, target_pyd_path)
                        result.pyd_path = target_pyd_path
                        self._log(f"Copied new .pyd to target location")
                    else:
                        result.pyd_path = temp_pyd_path
                    
                    result.steps.append(f".pyd文件已生成: {result.pyd_path}")
                else:
                    result.errors.append("未找到生成的.pyd文件")
                    return result

            finally:
                os.chdir(old_cwd)
                # 清理临时目录
                if temp_build_dir and os.path.exists(temp_build_dir):
                    try:
                        shutil.rmtree(temp_build_dir)
                    except:
                        pass

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
            
            # 正确提取模块名
            # .pyd文件名格式: {module_name}.cp{py_version}-{platform}.pyd
            basename = os.path.basename(pyd_path)
            # 去掉扩展名
            name_without_ext = basename.replace(".pyd", "").replace(".so", "")
            # 提取真正的模块名（去掉.cpXX-win_amd64等后缀）
            import re
            match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)(\.cp\d+-\w+)?$', name_without_ext)
            if match:
                module_name = match.group(1)
            else:
                module_name = name_without_ext
            
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

    def compile_and_import(self, source_code: str, module_name: str = "cypy_module", incremental: bool = True) -> Tuple[CompileResult, Any]:
        """
        Hook集成模式：编译cypy代码并返回可导入的模块
        
        参数：
            source_code: Cypy源代码
            module_name: 模块名称
            incremental: 是否使用增量编译
        
        返回：
            Tuple[CompileResult, Any]: 编译结果和模块对象
        """
        result = CompileResult(success=False)
        result.steps.append("=== Hook集成模式 ===")
        result.steps.append(f"开始编译代码片段，模块名: {module_name}")

        try:
            # Step 1: 创建临时文件（不使用with块，避免Windows文件锁定问题）
            import tempfile
            tmp_dir = tempfile.mkdtemp()
            
            try:
                source_path = os.path.join(tmp_dir, f"{module_name}.cypy")
                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(source_code)
                
                self._log("Step 1: Created temporary source file")
                
                # Step 2: 编译为.pyd（支持增量编译）
                compile_result = self.compile_to_pyd(source_path, output_dir=tmp_dir, force_recompile=not incremental)
                result.steps.extend(compile_result.steps)
                
                if not compile_result.success or not compile_result.pyd_path:
                    result.errors = compile_result.errors
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
                
                return result, module
                
            finally:
                # 尝试清理临时目录，但忽略Windows文件锁定错误
                try:
                    import shutil
                    shutil.rmtree(tmp_dir)
                except PermissionError:
                    # .pyd文件被锁定，忽略错误（系统会自动清理临时目录）
                    pass

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


# ==================== 代码动态感知系统 ====================

class CypyCacheManager:
    """缓存管理器：管理.pyd文件的缓存和变更检测"""
    
    def __init__(self):
        self._manifest_cache = {}
    
    def _get_base_cache_dir(self, source_path: str) -> str:
        """获取源文件对应的基础缓存目录（__pycache__/cypy/）"""
        source_dir = os.path.dirname(source_path)
        cache_dir = os.path.join(source_dir, "__pycache__", "cypy")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def _get_cache_dir(self, source_path: str) -> str:
        """获取源文件对应的缓存目录（包含哈希子目录）"""
        base_cache_dir = self._get_base_cache_dir(source_path)
        file_hash = self._compute_hash(source_path)
        # 使用哈希的前16位作为子目录名，避免Windows文件锁定问题
        cache_dir = os.path.join(base_cache_dir, file_hash[:16])
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def _get_manifest_path(self, source_path: str) -> str:
        """获取manifest文件路径"""
        base_cache_dir = self._get_base_cache_dir(source_path)
        return os.path.join(base_cache_dir, "manifest.json")
    
    def _compute_hash(self, source_path: str) -> str:
        """计算文件内容的SHA256哈希"""
        import hashlib
        with open(source_path, "rb") as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
    
    def _load_manifest(self, source_path: str) -> Dict:
        """加载manifest文件"""
        manifest_path = self._get_manifest_path(source_path)
        if os.path.exists(manifest_path):
            import json
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
    def _save_manifest(self, source_path: str, manifest: Dict) -> None:
        """保存manifest文件"""
        manifest_path = self._get_manifest_path(source_path)
        import json
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    
    def is_cypy_file(self, source_path: str) -> bool:
        """检查文件是否是Cypy文件（首行为#!bin cypy）"""
        if not os.path.exists(source_path):
            return False
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            return first_line == "#!bin cypy"
        except Exception:
            return False
    
    def is_stale(self, source_path: str) -> bool:
        """检查文件是否过期（需要重新编译）"""
        if not self.is_cypy_file(source_path):
            return False
        
        manifest = self._load_manifest(source_path)
        source_key = os.path.abspath(source_path)
        
        if source_key not in manifest:
            return True
        
        cached_info = manifest[source_key]
        current_hash = self._compute_hash(source_path)
        current_mtime = os.path.getmtime(source_path)
        
        # 检查哈希和修改时间
        if cached_info.get("hash") != current_hash:
            return True
        if cached_info.get("mtime", 0) != current_mtime:
            return True
        
        # 检查.pyd文件是否存在
        pyd_path = cached_info.get("pyd_path")
        if pyd_path and not os.path.exists(pyd_path):
            return True
        
        return False
    
    def get_cached_pyd(self, source_path: str) -> Optional[str]:
        """获取缓存的.pyd文件路径"""
        manifest = self._load_manifest(source_path)
        source_key = os.path.abspath(source_path)
        
        if source_key not in manifest:
            return None
        
        pyd_path = manifest[source_key].get("pyd_path")
        if pyd_path and os.path.exists(pyd_path):
            return pyd_path
        
        return None
    
    def cache_pyd(self, source_path: str, pyd_path: str) -> None:
        """缓存.pyd文件路径和相关信息"""
        manifest = self._load_manifest(source_path)
        source_key = os.path.abspath(source_path)
        
        manifest[source_key] = {
            "hash": self._compute_hash(source_path),
            "mtime": os.path.getmtime(source_path),
            "pyd_path": pyd_path,
            "timestamp": os.path.getmtime(pyd_path)
        }
        
        self._save_manifest(source_path, manifest)
    
    def clear_cache(self, source_path: str = None) -> None:
        """清除缓存"""
        if source_path:
            # 清除单个文件的缓存
            manifest = self._load_manifest(source_path)
            source_key = os.path.abspath(source_path)
            if source_key in manifest:
                pyd_path = manifest[source_key].get("pyd_path")
                if pyd_path and os.path.exists(pyd_path):
                    os.remove(pyd_path)
                del manifest[source_key]
                self._save_manifest(source_path, manifest)
        else:
            # 清除所有缓存（遍历所有__pycache__/cypy目录）
            for root, dirs, files in os.walk(os.getcwd()):
                if os.path.basename(root) == "cypy" and os.path.dirname(root) == "__pycache__":
                    for file in files:
                        if file.endswith(".pyd") or file.endswith(".so") or file == "manifest.json":
                            os.remove(os.path.join(root, file))


class CypyMetaPathFinder:
    """MetaPathFinder：拦截Python导入并识别Cypy文件"""
    
    def __init__(self):
        self.cache_manager = CypyCacheManager()
        self.hook = CypyHook()
    
    def find_spec(self, fullname, path, target=None):
        """查找模块规范"""
        if path is None:
            path = sys.path
        
        parts = fullname.split('.')
        module_name = parts[-1]
        
        for search_path in path:
            # 构建可能的文件路径
            py_path = os.path.join(search_path, f"{module_name}.py")
            
            if os.path.exists(py_path) and self.cache_manager.is_cypy_file(py_path):
                # 这是一个Cypy文件，返回自定义Loader
                return importlib.util.spec_from_loader(
                    fullname,
                    CypyLoader(py_path, self.cache_manager, self.hook),
                    origin=py_path
                )
        
        return None


class CypyLoader:
    """Loader：加载Cypy编译生成的模块"""
    
    def __init__(self, source_path: str, cache_manager: CypyCacheManager, hook: CypyHook):
        self.source_path = source_path
        self.cache_manager = cache_manager
        self.hook = hook
    
    def create_module(self, spec):
        """创建模块对象"""
        return None  # 使用默认行为
    
    def exec_module(self, module):
        """执行模块"""
        source_path = self.source_path
        
        # 检查是否需要编译
        pyd_path = self.cache_manager.get_cached_pyd(source_path)
        
        if pyd_path is None or self.cache_manager.is_stale(source_path):
            # 需要重新编译
            cache_dir = self.cache_manager._get_cache_dir(source_path)
            
            # 编译为.pyd
            result = self.hook.compile_to_pyd(source_path, output_dir=cache_dir)
            
            if not result.success or not result.pyd_path:
                error_msg = "\n".join(result.errors)
                raise CypyImportError(f"Failed to compile Cypy file '{source_path}':\n{error_msg}")
            
            pyd_path = result.pyd_path
            
            # 缓存.pyd路径
            self.cache_manager.cache_pyd(source_path, pyd_path)
        
        # 导入编译后的.pyd模块
        module_dir = os.path.dirname(pyd_path)
        
        # 添加模块目录到sys.path以便导入依赖
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        
        try:
            spec = importlib.util.spec_from_file_location(module.__name__, pyd_path)
            
            if spec is None or spec.loader is None:
                raise CypyImportError(f"Failed to create spec for '{pyd_path}'")
            
            compiled_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(compiled_module)
            
            # 将编译模块的所有属性复制到目标模块
            module.__dict__.update(compiled_module.__dict__)
            
        finally:
            # 清理sys.path
            if module_dir in sys.path:
                sys.path.remove(module_dir)


class CypyImportError(Exception):
    """Cypy导入错误"""
    pass


# ==================== Hook注册API ====================

_cypy_finder = None


def install_hook():
    """安装Cypy导入钩子"""
    global _cypy_finder
    if _cypy_finder is None:
        _cypy_finder = CypyMetaPathFinder()
        sys.meta_path.insert(0, _cypy_finder)


def uninstall_hook():
    """卸载Cypy导入钩子"""
    global _cypy_finder
    if _cypy_finder is not None and _cypy_finder in sys.meta_path:
        sys.meta_path.remove(_cypy_finder)
        _cypy_finder = None


def is_hook_installed() -> bool:
    """检查钩子是否已安装"""
    global _cypy_finder
    return _cypy_finder is not None and _cypy_finder in sys.meta_path


def main():
    hook = CypyHook()
    sys.exit(hook.run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
