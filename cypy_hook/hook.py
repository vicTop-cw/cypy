import sys
import os
import re
import time
import subprocess
import sysconfig
import importlib.util
import importlib.machinery
import shutil
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field


def extension_suffix() -> str:
    """本解释器加载可扩展模块时真正使用的后缀（EXT_SUFFIX）。

    Windows 非自由线程构建是 ``.cp313-win_amd64.pyd``，Linux 是
    ``.cpython-313-x86_64-linux-gnu.so``，macOS 是 ``.cpython-312-darwin.so``，
    自由线程构建带 ``t``（``.cp313t-win_amd64.pyd``），stable ABI 是 ``.abi3.so/pyd``。
    以前这里等价于硬编码 ``-win_amd64.pyd``，产物名与解释器实际接受的 ABI 标签
    无关，因此在任何非 “Windows x64 + 常规 GIL 构建” 上都找不到产物。
    """
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if suffix:
        return str(suffix)
    candidates = list(getattr(importlib.machinery, "EXTENSION_SUFFIXES", []) or [])
    if candidates:
        return candidates[0]
    return ".pyd"


def extension_filename(module_name: str) -> str:
    """由 module_name 推导构建产物文件名（module_name + EXT_SUFFIX）。"""
    return "%s%s" % (module_name, extension_suffix())


def extension_suffixes() -> Tuple[str, ...]:
    """当前解释器接受的全部扩展后缀（按长度降序，便于先匹配更具体的）。"""
    suffixes = set(getattr(importlib.machinery, "EXTENSION_SUFFIXES", ()) or ())
    suffixes.add(extension_suffix())
    suffixes.update({".pyd", ".so", ".dll"})
    return tuple(sorted((s for s in suffixes if s), key=len, reverse=True))


def module_name_from_filename(filename: str) -> str:
    """从扩展模块文件名还原可导入的模块名。

    去掉解释器真实的扩展后缀与 ABI 标签：

        hello.cp313-win_amd64.pyd                 -> hello
        hello.cpython-313-x86_64-linux-gnu.so     -> hello
        hello.cp313t-win_amd64.pyd（自由线程）     -> hello
        hello.abi3.pyd / hello.so / hello         -> hello
        pkg.hello.cp313-win_amd64.pyd             -> pkg.hello

    旧实现用 ``^([a-zA-Z_][a-zA-Z0-9_]*)(\\.cp\\d+-\\w+)?$`` 只能解析
    ``<name>.cp<XY>-<tag>`` 这一种形状，Linux/macOS/musl/自由线程/abi3 文件名
    都会退化成带点的垃圾名（例如 ``hello.cpython-313-x86_64-linux-gnu``），
    导致 spec_from_file_location 用错模块名。
    """
    base = os.path.basename(filename)
    for suffix in extension_suffixes():
        if suffix and base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    else:
        base = os.path.splitext(base)[0]

    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*(?:\.(?!cpython-|pypy-|abi3|cp\d)[a-zA-Z_][a-zA-Z0-9_]*)*)(?:\.(?:(?:cpython|pypy|cp\d+[dt]?)[-_][a-zA-Z0-9_-]+|abi3\d*|pyd|so))?$', base)
    if match:
        return match.group(1)
    return base


def build_isolated_command(*script_args: str) -> List[str]:
    """构造「在产物目录内跑 setup.py」的子进程命令行，且不把该目录塞进 sys.path[0]。

    根因（T0r258.4.2 / 冻结的 7 份 traceback 基准）：解释器运行 `python setup.py`
    时默认把「脚本所在目录」插到 sys.path[0]，而这里的脚本目录就是编译产物目录。
    只要产物目录里存在与 stdlib 撞名的扩展模块（examples/struct.cypy 编出的
    `output/struct.cp313-win_amd64.pyd`），setup.py 的
    `import setuptools -> _distutils_hack -> distutils.archive_util -> zipfile -> struct`
    就会命中那个 .pyd，并在其模块初始化期崩溃（`AttributeError: 'dict' object has no
    attribute 'width'`），把整段回溯当成「编译错误」塞进每个后续示例的结果里。

    `-P`（PEP 680 之外的 sys.path 安全开关，CPython 3.11+）与 `PYTHONSAFEPATH=1`
    都用于取消这条隐式 sys.path 注入；老解释器不认识 `-P`，故按版本加旗标，
    环境变量则无条件设置（不认识的解释器直接忽略）。
    """
    cmd = [sys.executable]
    if sys.version_info >= (3, 11):
        cmd.append("-P")
    cmd.extend(script_args)
    return cmd


def build_isolated_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """子进程环境副本 + PYTHONSAFEPATH=1（见 build_isolated_command 的说明）。"""
    merged = dict(os.environ if env is None else env)
    merged["PYTHONSAFEPATH"] = "1"
    return merged


def _path_under(path, directory: str) -> bool:
    """path 是否位于 directory 之内（用于判断产物是否还在临时构建目录里）。"""
    if not path or not directory:
        return False
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(directory)]) == os.path.abspath(directory)
    except ValueError:
        return False


def _safe_rmtree(path: str, max_retries: int = 5, delay: float = 0.1) -> None:
    """健壮地删除目录，容忍 Windows 上刚导入的 .pyd 文件锁。

    在 Windows 上，模块被 import 后其 .pyd 文件会被锁定，立即删除会抛出
    PermissionError。稍作等待后操作系统通常会释放锁，因此这里做有限次重试，
    重试仍失败则静默放弃（避免中断编译/热重载流程）。
    """
    for attempt in range(max_retries):
        try:
            if path and os.path.exists(path):
                shutil.rmtree(path)
            return
        except (PermissionError, OSError):
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                pass


def pick_built_extension(candidates: List[str], module_name: str,
                         prefer_dir: str) -> Optional[str]:
    """在构建产物里挑选本次真正的扩展模块文件。

    优先级（越靠前越可信）：
      1. ``prefer_dir``（``build_ext --inplace`` 的工作目录）下，名字正好是
         ``module_name + EXT_SUFFIX`` 的文件
      2. ``prefer_dir`` 下任何以 ``module_name`` 为词干名的扩展文件
      3. 子目录（如 ``build/lib.win-amd64-cpython-313``）下名字正好匹配的文件
      4. 其余任何一个词干名匹配的扩展文件

    没有任何匹配时返回 None（调用方据此报“未找到产物”，而不是回报一个错名字）。
    """
    if not candidates:
        return None

    want = extension_filename(module_name)
    prefer_abs = os.path.abspath(prefer_dir) if prefer_dir else ""

    def is_prefer_dir(path: str) -> bool:
        return os.path.dirname(path) == prefer_abs

    def stem(path: str) -> str:
        return module_name_from_filename(path)

    for cond in (
        lambda p: is_prefer_dir(p) and os.path.basename(p) == want,
        lambda p: is_prefer_dir(p) and stem(p) == module_name,
        lambda p: os.path.basename(p) == want,
        lambda p: stem(p) == module_name,
    ):
        for path in candidates:
            if cond(path):
                return path
    return None


class FunctionNotFoundError(RuntimeError):
    """请求的入口函数在编译产物里不存在（与加载/执行失败区分开）。"""


@dataclass
class CacheClearReport:
    """`CypyCacheManager.clear_cache()` 的回执：删掉了什么、什么删不动、为什么。

    BUG-87 的口径来源：旧实现返回 None，CLI 于是无条件打印「cleared successfully」，
    而磁盘上的产物还留着。有了这张单子，「报几个」与「删了几个」是同一件事。
    """

    removed: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)
    roots: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


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
            type_map = type_checker.check(ast)
            if type_checker.errors:
                errors.extend(type_checker.errors)

            self._log("Step 5.5: Pointer checking...")
            pointer_checker = PointerChecker()
            pointer_checker.check(ast, type_map)
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

    def analyze_only(self, source: str) -> Tuple[Any, List[str]]:
        """只做解析 + 静态分析，返回 (AST, 错误列表)，不生成任何代码。

        这是 `_parse_and_analyze` 的公开门面：外部调用方（如 `cypyc transpile --check-only`）
        不该依赖下划线开头的内部方法。语义与 `_parse_and_analyze` 逐字一致。
        """
        return self._parse_and_analyze(source)

    def transpile(self, source: str, source_path: str = None) -> CompileResult:
        """
        基础转译测试模式：仅将.cypy代码转译为Cython代码

        :param source_path: 源文件路径；BUG-90 的调用方侧——生成器拿不到路径时不发
            `__name__`/`__file__`，所以由知道路径的入口（`transpile_file`）把它传进来。
            缺省 None 保持「无源路径 ⇒ 不伪造身份」的语义。
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
            generator = CythonGenerator(source_path)
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
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    source = f.read()
            except OSError as read_err:
                # 只有 I/O 失败才归入「读取文件错误」：解析/生成异常此前也被写成本桶，
                # 用户看到的首行会是「读取文件错误: Expected ...」这类与文件无关的诊断
                result.errors.append(f"读取文件错误: {read_err}")
                return result

            ast = None
            # 增量编译检查
            if incremental:
                incremental_compiler = self._get_incremental_compiler()
                
                # 先快速检查缓存有效性（不需要解析AST）
                cached_entry = incremental_compiler.check_cache_validity(source_path)
                
                if cached_entry:
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
                
                # 需要重新编译，解析AST
                self._log("增量编译: 缓存未命中，开始解析")
                result.steps.append("增量编译: 缓存未命中，开始解析")
                
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
                self._log(f"增量编译: 需要重新编译，受影响定义: {inc_result.affected_definitions}")
                result.steps.append(f"增量编译: 受影响定义数: {len(inc_result.affected_definitions)}")
            
            # 执行正常转译
            transpile_result = self.transpile(source, source_path=source_path)
            
            # 合并结果（避免覆盖result对象）
            result.success = transpile_result.success
            result.cython_code = transpile_result.cython_code
            result.errors = transpile_result.errors
            result.steps.extend(transpile_result.steps)
            
            if result.success and result.cython_code:
                # output_dir 为空时回退到 'output'，避免 makedirs('') 抛错
                effective_output_dir = self.output_dir or "output"
                try:
                    os.makedirs(effective_output_dir, exist_ok=True)
                    # 处理不同的源文件扩展名
                    basename = os.path.basename(source_path)
                    if basename.endswith(".cypy"):
                        pyx_filename = basename.replace(".cypy", ".pyx")
                    elif basename.endswith(".py"):
                        pyx_filename = basename.replace(".py", ".pyx")
                    else:
                        pyx_filename = basename + ".pyx"
                    
                    pyx_path = os.path.join(effective_output_dir, pyx_filename)
                    with open(pyx_path, "w", encoding="utf-8") as f:
                        f.write(result.cython_code)
                    result.pyx_path = pyx_path
                    result.steps.append(f"Cython文件已生成: {pyx_path}")

                    # 更新增量编译缓存
                    if incremental and ast:
                        incremental_compiler = self._get_incremental_compiler()
                        incremental_compiler.update_cache(source_path, ast, result.cython_code)
                except Exception as write_err:
                    # 写入 .pyx 失败时必须标记失败，否则上层会误判为成功
                    result.success = False
                    result.errors.append(f"生成.pyx文件错误: {write_err}")
                    return result

            return result

        except Exception as e:
            result.errors.append(f"编译错误: {e}")
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

        # 使用参数output_dir或回退到实例属性（为空时回退到 'output'）
        actual_output_dir = output_dir if output_dir else (self.output_dir or "output")
        
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
            pyx_path = os.path.abspath(pyx_path)
            
            # Step 2: 生成setup.py
            self._log("Step 2: Generating setup.py...")
            from cypyc.codegen.setup_generator import SetupGenerator
            setup_generator = SetupGenerator()
            module_name = os.path.basename(pyx_path).replace(".pyx", "")
            setup_generator.set_module_name(module_name)
            setup_generator.add_source(os.path.basename(pyx_path))
            setup_code = setup_generator.generate()
            
            setup_path = os.path.join(actual_output_dir, "setup.py")
            with open(setup_path, "w", encoding="utf-8") as f:
                f.write(setup_code)
            result.steps.append(f"setup.py已生成: {setup_path}")

            # Step 3: 编译为.pyd
            self._log("Step 3: Compiling to .pyd...")
            
            old_cwd = os.getcwd()
            temp_build_dir = None
            # 绝对化必须在任何 chdir 之前完成：actual_output_dir 是相对路径，
            # 一旦切进临时构建目录再 abspath，它会指向不存在的 <tmp>/output。
            out_dir_abs = os.path.abspath(actual_output_dir)
            
            try:
                # 确保输出目录存在
                os.makedirs(actual_output_dir, exist_ok=True)
                
                # 检查目标扩展模块文件是否存在（可能被锁定）。
                # 文件名由本解释器的 EXT_SUFFIX 推导，绝不再写死 win_amd64/.pyd。
                target_pyd_name = extension_filename(module_name)
                target_pyd_path = os.path.join(out_dir_abs, target_pyd_name)
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
                    os.chdir(os.path.abspath(actual_output_dir))
                
                compile_cmd = build_isolated_command(
                    "setup.py", "build_ext", "--inplace"
                )
                process = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    timeout=120,
                    env=build_isolated_env()
                )

                # 以字节读取并容错解码，避免 Windows 下默认 GBK 编码导致的
                # UnicodeDecodeError（编译器输出可能含非 GBK 字节）
                raw_out = process.stdout if isinstance(process.stdout, bytes) else process.stdout.encode("utf-8", "replace")
                raw_err = process.stderr if isinstance(process.stderr, bytes) else process.stderr.encode("utf-8", "replace")
                stdout_text = raw_out.decode("utf-8", "replace")
                stderr_text = raw_err.decode("utf-8", "replace")

                if process.returncode != 0:
                    result.errors.append(f"编译错误: {stderr_text}")
                    result.steps.append(f"编译失败: {process.returncode}")
                    return result

                result.steps.append(f"编译成功: {stdout_text[:200]}...")

                # Step 4: 查找工具链真正生成的扩展模块，并采用它的真实文件名
                #（旧实现把产物改名成 `<name>.cpXY-win_amd64.pyd` 这种平台字面量，
                #  于是 Linux/macOS/自由线程/abi3 上产物被复制到一个错误名字并回报该路径。）
                pyd_files = []
                search_dir = os.getcwd()
                for root, dirs, files in os.walk(search_dir):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for file in files:
                        if file.endswith(extension_suffixes()):
                            pyd_files.append(os.path.abspath(os.path.join(root, file)))

                produced = pick_built_extension(pyd_files, module_name, search_dir)
                if produced:
                    if os.path.dirname(produced) == out_dir_abs:
                        # 产物已经在输出目录（--inplace），保持它的真名，不重命名
                        result.pyd_path = produced
                    else:
                        dest = os.path.join(out_dir_abs, os.path.basename(produced))
                        if os.path.abspath(dest) != produced:
                            try:
                                shutil.copy2(produced, dest)
                            except OSError as copy_exc:
                                # 目标名字可能被占用（旧产物已加载进本进程）。
                                # 此时保留临时目录里的真产物并让 finally 跳过清理，
                                # 否则回报一个已被删除的路径。
                                result.steps.append(f"复制产物失败，使用原始路径: {copy_exc}")
                                dest = produced
                        result.pyd_path = dest
                    self._log(f"Adopted produced extension: {result.pyd_path}")
                else:
                    result.errors.append("未找到生成的.pyd文件")
                    return result

                result.steps.append(f"扩展模块已生成: {result.pyd_path}")

            finally:
                os.chdir(old_cwd)
                # 清理临时目录（容忍Windows文件锁定）；但若回报的产物仍在其中，
                # 删掉它就会让 pyd_path 指向不存在的文件（导入报 DLL load failed）。
                if temp_build_dir and not _path_under(result.pyd_path, temp_build_dir):
                    _safe_rmtree(temp_build_dir)

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
        module_dir = os.path.dirname(pyd_path)

        # 由产物文件名还原真正的模块名：先去掉解释器实际的扩展后缀
        #（.pyd/.so/.dll 与 EXT_SUFFIX），再剥掉 ABI 标签
        #（cpXY-win_amd64 / cpython-3XX-<triplet> / cpXYt-… / abi3）。
        module_name = module_name_from_filename(pyd_path)

        # 添加模块目录到sys.path —— 只在「导入 + 调用」期间挂载，结束时务必摘掉：
        # 产物目录里可能存在与 stdlib 撞名的扩展模块（output/struct.*.pyd 曾毒死
        # setup.py 与任何后续 `import zipfile`），把它长期留在 sys.path 上等于把
        # 同一个地雷交给本进程的下一句 import。
        inserted = module_dir not in sys.path
        if inserted:
            sys.path.insert(0, module_dir)

        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, pyd_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 调用函数
            if hasattr(module, func_name):
                func = getattr(module, func_name)
                return func(*args, **kwargs)
            else:
                raise FunctionNotFoundError(f"模块中不存在函数: {func_name}")

        except FunctionNotFoundError:
            raise
        except Exception as e:
            raise RuntimeError(f"运行模块错误: {e}")
        finally:
            if inserted and module_dir in sys.path:
                sys.path.remove(module_dir)

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
            except FunctionNotFoundError as e:
                # 模块级程序在 import 阶段已经跑完，缺入口函数不算执行失败
                #（15/22 个 examples 靠显式 main 出输出，其余靠模块级语句出输出）
                result.steps.append(f"模块无 {func_name} 入口，已按模块级执行: {e}")
                return result, None
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
                # 清理临时目录（容忍Windows文件锁定：导入后的.pyd可能被锁，稍后重试）
                _safe_rmtree(tmp_dir)

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

        # BUG-29: source 是可选位置参数，`cypyc hook` 不带文件时它是 None，
        # os.path.isfile(None) 抛裸 TypeError；这里应当给出用法提示。
        if parsed_args.source is None:
            print("Error: no source file given (try: cypyc hook <file.cypy> [--compile] [--run <fn>])",
                  file=sys.stderr)
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
            except (json.JSONDecodeError, IOError) as exc:
                import sys
                print(f"[cypy][warn] cython manifest 无法读取，按无缓存重新编译: "
                      f"{manifest_path} ({exc})", file=sys.stderr)
        return {}
    
    def _save_manifest(self, source_path: str, manifest: Dict) -> None:
        """保存manifest文件"""
        manifest_path = self._get_manifest_path(source_path)
        import json
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    
    def is_cypy_file(self, source_path: str) -> bool:
        """检查文件是否是Cypy文件（首行为#!bin cypy）

        BUG-86：这里必须按 `utf-8-sig` 读——按 `utf-8` 读时带 BOM 的文件首行是
        `\\ufeff#!bin cypy`，与标记逐字比较恒不相等，`find_spec` 于是判定「不是 Cypy 模块」
        并**静默放行**：文件被当成普通 .py 执行，既不编译也不给任何诊断，而同一个文件
        `cypyc transpile` 是成功的。`utf-8-sig` 对无 BOM 的文件是恒等变换（解码器只在
        开头见到 BOM 时才吞掉它），所以两条路径都按文档口径走。
        """
        if not os.path.exists(source_path):
            return False
        try:
            with open(source_path, "r", encoding="utf-8-sig") as f:
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
    
    def _remove_file(self, path: str, report: CacheClearReport) -> bool:
        """删一个文件并把结果如实记进回执（删不动时记录 `异常类型: 原因`）。"""
        try:
            os.remove(path)
        except OSError as exc:
            report.failed.append((path, f"{type(exc).__name__}: {exc}"))
            return False
        report.removed.append(path)
        return True

    def _clear_tree(self, directory: str, report: CacheClearReport) -> None:
        """自底向上清空一棵目录树：每个文件逐个记账，只摘掉因此变空的目录。

        Windows 上被本进程加载过的 .pyd 删不动（PermissionError）。这里不整树 rmtree，
        正是为了让「删掉的」与「删不动的」分别落到回执里，而不是全有或全无。
        """
        for root, dirs, files in os.walk(directory, topdown=False):
            for name in files:
                self._remove_file(os.path.join(root, name), report)
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass  # 目录里还留着删不动的文件，保留并由回执说明
        try:
            os.rmdir(directory)
        except OSError:
            pass

    @staticmethod
    def _find_cache_roots(start: str) -> List[str]:
        """找出 start 之下所有 `<模块目录>/__pycache__/cypy` 缓存根。"""
        found: List[str] = []
        if not os.path.isdir(start):
            return found
        for root, dirs, _files in os.walk(start):
            if os.path.basename(root) == "__pycache__" and "cypy" in dirs:
                found.append(os.path.join(root, "cypy"))
                dirs.remove("cypy")  # 整棵都要清，不必再往下走
        return found

    @staticmethod
    def _base_cache_dir_for(source_path: str) -> str:
        """source_path 对应的缓存根，**不**像 _get_base_cache_dir 那样顺手把目录建出来。"""
        return os.path.join(os.path.dirname(os.path.abspath(source_path)),
                            "__pycache__", "cypy")

    def _clear_single(self, source_path: str, report: CacheClearReport) -> None:
        """清掉单个源文件的缓存：产物所在的哈希子目录整体清空（含 .c/setup.py/build）。"""
        base_dir = self._base_cache_dir_for(source_path)
        manifest = self._load_manifest(source_path)
        source_key = os.path.abspath(source_path)
        entry = manifest.get(source_key) or {}

        targets: List[str] = []
        pyd_path = entry.get("pyd_path")
        if pyd_path:
            pyd_abs = os.path.abspath(pyd_path)
            if _path_under(pyd_abs, base_dir):
                targets.append(os.path.dirname(pyd_abs))
            elif os.path.exists(pyd_abs):
                targets.append(pyd_abs)
        if not targets and os.path.isdir(base_dir) and os.path.exists(source_path):
            # manifest 丢了/坏了也要能清掉这个模块留下的中间产物
            try:
                digest = self._compute_hash(source_path)[:16]
            except OSError:
                digest = ""
            if digest:
                for name in sorted(os.listdir(base_dir)):
                    if name.startswith(digest):
                        targets.append(os.path.join(base_dir, name))

        failures_before = len(report.failed)
        for target in targets:
            if os.path.isdir(target):
                self._clear_tree(target, report)
            elif os.path.exists(target):
                self._remove_file(target, report)

        # 只在确实清干净时才销掉 manifest 条目：留着删不动的文件却把账擦了，
        # 下次构建就找不到那个 .pyd（与 cypy_bridge 的 BUG-1 同一口径）。
        if source_key in manifest and len(report.failed) == failures_before:
            del manifest[source_key]
            self._save_manifest(source_path, manifest)

    def clear_cache(self, source_path: str = None) -> CacheClearReport:
        """清除缓存，并如实回报删了哪些文件、哪些删不动（BUG-87）。

        旧实现只删 `__pycache__/cypy` **根下**的 .pyd/.so/manifest.json，而真正的产物写在
        哈希子目录 `__pycache__/cypy/<hash>/` 里（.pyd/.c/setup.py/build/…），于是清完
        manifest 没了、产物原地留着，CLI 还无条件打「[OK] … cleared successfully」。
        """
        report = CacheClearReport()
        if source_path:
            self._clear_single(source_path, report)
            return report

        for base_dir in self._find_cache_roots(os.getcwd()):
            report.roots.append(base_dir)
            self._clear_tree(base_dir, report)
        return report


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
