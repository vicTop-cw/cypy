"""项目级编译器 - 统一编译整个项目的所有模块

核心流程：
1. 扫描项目目录下的所有 .cypy 文件
2. 解析 import/from 语句，构建模块依赖图
3. 拓扑排序确定编译顺序
4. 第一遍：收集所有模块的类型导出到 TypeRegistry
5. 第二遍：按依赖顺序逐模块进行类型检查和代码生成
6. 输出编译产物 (.pyd 文件)
"""

import os
import sys
import time
import importlib
import importlib.util
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from .type_registry import TypeRegistry, ModuleTypeInfo, TypeExport
from .module_dependency_graph import ModuleDependencyGraph


@dataclass
class ProjectCompileResult:
    """项目级编译结果"""
    success: bool
    compiled_modules: List[str] = field(default_factory=list)
    failed_modules: List[str] = field(default_factory=list)
    errors: Dict[str, List[str]] = field(default_factory=dict)
    pyd_paths: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    compilation_order: List[str] = field(default_factory=list)
    cycles_detected: List[List[str]] = field(default_factory=list)
    total_time: float = 0.0
    type_registry_stats: Dict[str, int] = field(default_factory=dict)


class ProjectCompiler:
    """项目级编译器

    使用方式:
        compiler = ProjectCompiler(project_root="path/to/project")
        result = compiler.build()

    或指定入口文件:
        result = compiler.build(entry_point="main.cypy")
    """

    def __init__(self, project_root: str = None, output_dir: str = "output",
                 verbose: bool = False):
        self._project_root = os.path.abspath(project_root or os.getcwd())
        self._output_dir = os.path.abspath(output_dir)
        self._verbose = verbose

        self._type_registry = TypeRegistry()
        self._dependency_graph = ModuleDependencyGraph()
        self._source_files: Dict[str, str] = {}  # module_name -> file_path
        self._ast_cache: Dict[str, any] = {}  # module_name -> AST

        os.makedirs(self._output_dir, exist_ok=True)

    def _log(self, message: str) -> None:
        if self._verbose:
            print(f"[ProjectCompiler] {message}")

    def discover_modules(self, directory: str = None) -> Dict[str, str]:
        """扫描目录，发现所有 .cypy 模块"""
        scan_dir = os.path.abspath(directory or self._project_root)
        discovered = {}

        self._log(f"Scanning directory: {scan_dir}")

        for root, dirs, files in os.walk(scan_dir):
            # 跳过常见的排除目录
            dirs[:] = [d for d in dirs if d not in (
                '__pycache__', '.git', 'output', 'build', '.cypy_cache',
                'node_modules', '.venv', 'venv'
            )]

            for file in files:
                if file.endswith('.cypy'):
                    file_path = os.path.abspath(os.path.join(root, file))
                    module_name = self._path_to_module_name(file_path, scan_dir)
                    discovered[module_name] = file_path
                    self._log(f"  Found module: {module_name} ({file_path})")

        self._source_files = discovered
        return discovered

    def _path_to_module_name(self, file_path: str, base_dir: str) -> str:
        """将文件路径转换为模块名"""
        rel_path = os.path.relpath(file_path, base_dir)
        # 移除 .cypy 扩展名
        if rel_path.endswith('.cypy'):
            rel_path = rel_path[:-5]
        # 将路径分隔符替换为点
        module_name = rel_path.replace(os.sep, '.').replace('/', '.')
        # __init__ 特殊处理
        if module_name.endswith('.__init__'):
            module_name = module_name[:-9]  # 移除 .__init__
        if module_name == '__init__':
            module_name = os.path.basename(base_dir)
        return module_name

    def _module_name_to_path(self, module_name: str) -> Optional[str]:
        """将模块名转换为文件路径"""
        if module_name in self._source_files:
            return self._source_files[module_name]

        # 尝试查找
        for name, path in self._source_files.items():
            if name == module_name:
                return path

        return None

    def parse_all_modules(self) -> Dict[str, any]:
        """解析所有模块，构建 AST"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser

        ast_cache = {}

        for module_name, file_path in self._source_files.items():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()

                lexer = Lexer(source)
                tokens = list(lexer.tokenize())
                parser = Parser(tokens)
                ast = parser.parse()

                ast_cache[module_name] = ast
                self._ast_cache[module_name] = ast
                self._log(f"  Parsed: {module_name}")

            except Exception as e:
                self._log(f"  Error parsing {module_name}: {e}")

        return ast_cache

    def build_dependency_graph(self) -> ModuleDependencyGraph:
        """从 AST 构建模块依赖图"""
        from cypyc.parser.parser import Import, FromImport

        self._dependency_graph.clear()

        # 第一遍：注册所有模块
        for module_name, file_path in self._source_files.items():
            self._dependency_graph.add_module(module_name, file_path)

        # 第二遍：分析依赖关系
        for module_name, ast in self._ast_cache.items():
            imports = self._extract_imports(ast)
            for target_module, names in imports:
                # 解析目标模块名
                resolved_name = self._resolve_import_target(target_module, module_name)
                if resolved_name and resolved_name in self._source_files:
                    self._dependency_graph.add_dependency(module_name, resolved_name)
                    self._type_registry.add_import(module_name, resolved_name, names)
                    self._log(f"  {module_name} imports {resolved_name}: {names}")

        return self._dependency_graph

    def _extract_imports(self, ast: any) -> List[Tuple[str, List[str]]]:
        """从 AST 中提取导入信息"""
        from cypyc.parser.parser import Import, FromImport as ParsedFromImport

        imports = []
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, Import):
                    # import module
                    imports.append((stmt.module, ['*']))
                elif isinstance(stmt, ParsedFromImport):
                    # from module import name1, name2
                    imports.append((stmt.module, stmt.names))
                # 也处理 Import/ImportFrom (旧版 AST 兼容)
                elif hasattr(stmt, 'kind'):
                    if stmt.kind == 'Import':
                        for alias in getattr(stmt, 'names', []):
                            if hasattr(alias, 'name'):
                                imports.append((alias.name, ['*']))
                            elif isinstance(alias, str):
                                imports.append((alias, ['*']))
                    elif stmt.kind == 'ImportFromStmt':
                        module = getattr(stmt, 'module', '')
                        names = getattr(stmt, 'names', [])
                        if module:
                            imports.append((module, names))
        return imports

    def _resolve_import_target(self, import_path: str, current_module: str) -> Optional[str]:
        """解析导入路径到模块名"""
        # 直接匹配
        if import_path in self._source_files:
            return import_path

        # 尝试相对导入
        if import_path.startswith('.'):
            # 相对导入
            parts = import_path.lstrip('.').split('.')
            dot_count = len(import_path) - len(import_path.lstrip('.'))

            # 获取当前模块的父级路径
            current_parts = current_module.split('.')
            if dot_count <= len(current_parts):
                base_parts = current_parts[:len(current_parts) - dot_count + 1]
                resolved = '.'.join(base_parts + parts)
                if resolved in self._source_files:
                    return resolved
        else:
            # 绝对导入 - 在所有模块中查找
            for mod_name in self._source_files:
                if mod_name == import_path or mod_name.endswith('.' + import_path):
                    return mod_name

        return None

    def collect_type_exports(self) -> TypeRegistry:
        """第一遍：收集所有模块的类型导出"""
        from cypyc.parser.parser import (
            StructDef, ClassDef, FuncDef, TraitDef,
            EnumDef, TypeAlias, ExceptionDef, ComptimeFuncDef
        )

        self._log("Collecting type exports...")

        for module_name, ast in self._ast_cache.items():
            mod_info = self._type_registry.register_module(
                module_name, self._source_files.get(module_name, "")
            )

            if not hasattr(ast, 'body'):
                continue

            for stmt in ast.body:
                if isinstance(stmt, StructDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='struct',
                        module=module_name,
                        field_types={
                            f.name: self._get_field_type(f)
                            for f in (stmt.fields or [])
                        } if stmt.fields else None,
                        generic_params=stmt.generic_params or None,
                    ))

                elif isinstance(stmt, ClassDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='class',
                        module=module_name,
                        field_types={
                            f.name: self._get_field_type(f)
                            for f in (stmt.body or [])
                            if hasattr(f, 'kind') and f.kind == 'ClassField'
                        } if hasattr(stmt, 'body') else None,
                    ))

                elif isinstance(stmt, FuncDef):
                    return_type = None
                    if stmt.return_type:
                        return_type = self._get_type_str(stmt.return_type)

                    param_types = []
                    for p in (stmt.params or []):
                        if hasattr(p, 'type_annotation') and p.type_annotation:
                            param_types.append(self._get_type_str(p.type_annotation))
                        else:
                            param_types.append('Any')

                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='function',
                        module=module_name,
                        return_type=return_type,
                        param_types=param_types,
                    ))

                elif isinstance(stmt, TraitDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='trait',
                        module=module_name,
                        generic_params=stmt.generic_params or None,
                    ))

                elif isinstance(stmt, EnumDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='enum',
                        module=module_name,
                    ))

                elif isinstance(stmt, ExceptionDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='exception',
                        module=module_name,
                    ))

                elif hasattr(stmt, 'kind') and stmt.kind == 'TypeAlias':
                    target_type = None
                    if hasattr(stmt, 'target'):
                        target_type = self._get_type_str(stmt.target)
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='type_alias',
                        module=module_name,
                        return_type=target_type,
                    ))

                elif isinstance(stmt, ComptimeFuncDef):
                    self._type_registry.add_export(module_name, TypeExport(
                        name=stmt.name,
                        kind='comptime_func',
                        module=module_name,
                    ))

            self._log(f"  Collected exports from {module_name}")

        return self._type_registry

    def _get_field_type(self, field: any) -> str:
        """获取字段的类型字符串"""
        if hasattr(field, 'type_annotation') and field.type_annotation:
            return self._get_type_str(field.type_annotation)
        return 'Any'

    def _get_type_str(self, type_node: any) -> str:
        """获取类型节点的字符串表示"""
        if type_node is None:
            return 'Any'
        if hasattr(type_node, 'kind'):
            if type_node.kind == 'Identifier':
                return getattr(type_node, 'id', 'Any')
            elif type_node.kind == 'TypeAnnotation':
                if hasattr(type_node, 'annotation_type'):
                    return self._get_type_str(type_node.annotation_type)
        if hasattr(type_node, 'id'):
            return type_node.id
        if hasattr(type_node, 'value'):
            return str(type_node.value)
        return 'Any'

    def type_check_module(self, module_name: str) -> Tuple[bool, List[str]]:
        """对单个模块进行类型检查（使用 TypeRegistry 解析跨模块类型）"""
        from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
        from cypyc.analyzer.type_checker import TypeChecker

        errors = []
        try:
            ast = self._ast_cache.get(module_name)
            if ast is None:
                return False, ["No AST for module"]

            # 运行作用域分析
            scope_analyzer = ScopeAnalyzer()
            scope_analyzer.analyze(ast)

            # 运行类型检查
            type_checker = TypeChecker()
            # 将 TypeRegistry 传递给类型检查器（如果支持）
            if hasattr(type_checker, 'set_type_registry'):
                type_checker.set_type_registry(self._type_registry)
            type_checker.check(ast)

            # 收集类型检查错误
            if hasattr(type_checker, 'errors'):
                errors.extend(type_checker.errors)

            return len(errors) == 0, errors

        except Exception as e:
            return False, [str(e)]

    def compile_module(self, module_name: str) -> Tuple[bool, Optional[str], List[str]]:
        """编译单个模块为 .pyd (使用已有的 AST 生成 Cython 代码直接编译)"""
        from cypyc.codegen.cython_generator import CythonGenerator
        from cypyc.codegen.setup_generator import SetupGenerator
        import subprocess

        errors = []
        try:
            ast = self._ast_cache.get(module_name)
            if ast is None:
                return False, None, ["No AST for module"]

            # Step 1: 代码生成 (使用已有的 AST)
            generator = CythonGenerator()
            generator.generate(ast)
            cython_code = "\n".join(generator.output)

            # Step 2: 生成 .pyx 文件
            module_output_dir = os.path.join(self._output_dir, module_name.replace('.', os.sep))
            os.makedirs(module_output_dir, exist_ok=True)

            pyx_filename = f"{module_name.split('.')[-1]}.pyx"
            pyx_path = os.path.join(module_output_dir, pyx_filename)
            with open(pyx_path, 'w', encoding='utf-8') as f:
                f.write(cython_code)

            # Step 3: 生成 setup.py 并编译
            setup_gen = SetupGenerator()
            setup_gen.set_module_name(module_name.split('.')[-1])
            setup_gen.add_source(pyx_path)
            setup_path = os.path.join(module_output_dir, "setup.py")
            with open(setup_path, 'w', encoding='utf-8') as f:
                f.write(setup_gen.generate())

            # Step 4: 运行编译
            old_cwd = os.getcwd()
            try:
                os.chdir(module_output_dir)
                result = subprocess.run(
                    [sys.executable, "setup.py", "build_ext", "--inplace"],
                    capture_output=True,
                    timeout=120,
                )

                # 以字节读取并容错解码，避免 Windows 下默认 GBK 编码导致的
                # UnicodeDecodeError（编译器输出可能含非 GBK 字节）
                raw_err = result.stderr if isinstance(result.stderr, bytes) else result.stderr.encode("utf-8", "replace")
                stderr_text = raw_err.decode("utf-8", "replace")

                if result.returncode != 0:
                    errors.append(f"Build failed: {stderr_text[-500:]}")
                    return False, None, errors

                # Step 5: 查找生成的 .pyd 文件
                pyd_files = []
                for root, dirs, files in os.walk(module_output_dir):
                    for file in files:
                        if file.endswith(".pyd") or file.endswith(".so"):
                            pyd_files.append(os.path.abspath(os.path.join(root, file)))

                if pyd_files:
                    return True, pyd_files[0], []
                else:
                    errors.append("No .pyd file generated")
                    return False, None, errors

            finally:
                os.chdir(old_cwd)

        except Exception as e:
            return False, None, [str(e)]

    def build(self, entry_point: str = None) -> ProjectCompileResult:
        """执行项目级编译

        Args:
            entry_point: 入口模块名（可选）。如果指定，只编译该模块及其依赖

        Returns:
            ProjectCompileResult 编译结果
        """
        start_time = time.time()
        result = ProjectCompileResult(success=False)

        self._log("=" * 60)
        self._log("Project Build Starting")
        self._log("=" * 60)

        # Step 1: 发现模块
        self._log("Step 1: Discovering modules...")
        self.discover_modules()
        if not self._source_files:
            result.errors['_'] = ["No .cypy files found"]
            return result

        # Step 2: 解析所有模块
        self._log("Step 2: Parsing all modules...")
        self.parse_all_modules()

        # Step 3: 构建依赖图
        self._log("Step 3: Building dependency graph...")
        dep_graph = self.build_dependency_graph()
        compilation_order, cycles = dep_graph.topological_sort()
        result.compilation_order = compilation_order
        result.cycles_detected = cycles

        if cycles:
            result.warnings.append(
                f"Circular dependencies detected: {cycles}"
            )
            self._log(f"Warning: Circular dependencies detected: {cycles}")

        # Step 4: 收集类型导出
        self._log("Step 4: Collecting type exports...")
        self.collect_type_exports()
        result.type_registry_stats = self._type_registry.get_stats()

        # Step 5: 确定要编译的模块范围
        modules_to_compile = compilation_order
        if entry_point:
            # 只编译入口模块及其依赖
            entry_deps = self._dependency_graph.get_transitive_dependencies(entry_point)
            modules_to_compile = [
                m for m in compilation_order
                if m == entry_point or m in entry_deps
            ]

        # Step 6: 逐模块类型检查和编译
        self._log(f"Step 5: Compiling {len(modules_to_compile)} modules...")
        result.success = True

        for module_name in modules_to_compile:
            self._log(f"  Compiling: {module_name}")

            # 类型检查 (失败时记录警告但仍尝试编译)
            type_ok, type_errors = self.type_check_module(module_name)
            if not type_ok:
                result.warnings.extend(type_errors)
                self._log(f"    Type check warnings: {type_errors[:2]}")
                # 继续尝试编译 - 类型检查警告不阻止编译

            # 代码生成和编译
            compile_ok, pyd_path, compile_errors = self.compile_module(module_name)
            if compile_ok:
                result.compiled_modules.append(module_name)
                result.pyd_paths[module_name] = pyd_path
                self._log(f"    Compiled: {pyd_path}")
                if not type_ok:
                    # 编译成功但类型检查有警告 → 标记为部分成功
                    pass
            else:
                result.failed_modules.append(module_name)
                result.errors[module_name] = compile_errors
                result.success = False
                self._log(f"    Compilation failed: {compile_errors}")

        result.total_time = time.time() - start_time

        self._log(f"Build {'succeeded' if result.success else 'failed'} "
                   f"in {result.total_time:.2f}s")
        self._log(f"  Compiled: {len(result.compiled_modules)} modules")
        self._log(f"  Failed: {len(result.failed_modules)} modules")

        return result

    def get_incremental_changes(self, changed_files: Set[str]) -> Dict[str, Set[str]]:
        """计算增量编译时需要重新编译的模块

        Args:
            changed_files: 变更的文件路径集合

        Returns:
            Dict mapping changed file -> set of affected module names
        """
        affected = {}

        for file_path in changed_files:
            abs_path = os.path.abspath(file_path)
            module_name = self._dependency_graph.get_module_by_path(abs_path)

            if module_name:
                # 更新该模块的 AST
                if module_name in self._source_files:
                    try:
                        self._reparse_module(module_name)
                    except Exception:
                        pass

                # 获取受影响的所有模块
                affected_modules = self._dependency_graph.get_affected_modules({module_name})
                affected[file_path] = affected_modules

        return affected

    def _reparse_module(self, module_name: str) -> None:
        """重新解析单个模块"""
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser

        file_path = self._source_files.get(module_name)
        if not file_path or not os.path.exists(file_path):
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()

        lexer = Lexer(source)
        tokens = list(lexer.tokenize())
        parser = Parser(tokens)
        ast = parser.parse()

        self._ast_cache[module_name] = ast

        # 更新类型注册表
        self._type_registry.invalidate_module(module_name)
        self.collect_type_exports()

    def get_type_registry(self) -> TypeRegistry:
        """获取类型注册表"""
        return self._type_registry

    def get_dependency_graph(self) -> ModuleDependencyGraph:
        """获取模块依赖图"""
        return self._dependency_graph
