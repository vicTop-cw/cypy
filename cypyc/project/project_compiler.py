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
        # 解析失败的模块（诊断用；旧实现只在 verbose 日志里提一句就静默跳过）
        self._parse_errors: Dict[str, str] = {}
        # 由 `__init__.cypy` 得到的模块名（包），相对导入的基准层级需要这个信息
        self._package_modules: Set[str] = set()
        # 规范文件路径 -> 模块名（仅登记未被遮蔽的条目）
        self._path_to_module: Dict[str, str] = {}
        # 模块名冲突（`foo.cypy` 与 `foo/__init__.cypy`）：被遮蔽的文件与冲突记录
        self._shadowed_files: Dict[str, str] = {}
        self._name_collisions: List[Dict[str, str]] = []
        # 导入解析诊断（未找到 / 歧义 / 越过顶层包）
        self._import_diagnostics: List[str] = []

        os.makedirs(self._output_dir, exist_ok=True)

    def _log(self, message: str) -> None:
        if self._verbose:
            print(f"[ProjectCompiler] {message}")

    def discover_modules(self, directory: str = None) -> Dict[str, str]:
        """扫描目录，发现所有 .cypy 模块

        一个模块名可能对应两个文件：`foo.cypy` 与 `foo/__init__.cypy`。
        旧实现直接 `discovered[module_name] = file_path`，后遍历到的那个静默覆盖前一个，
        于是某个源文件凭空从项目里消失（既没有诊断也没有构建失败），而且结果依赖
        os.walk 的遍历顺序。

        现在的规则：
        * 遍历顺序确定化（dirs / files 排序），同样的目录树永远得到同样的结果；
        * 按 CPython 的语义 **包优先**：`__init__.cypy` 取得规范名 `foo`；
        * 被遮蔽的文件不会被丢弃——它以 `<name>@shadowed:<相对路径>` 的键继续出现在
          返回值中，同时记入 `self._name_collisions`，`build()` 会据此报错并终止构建。
        """
        scan_dir = os.path.abspath(directory or self._project_root)
        discovered: Dict[str, str] = {}
        # module_name -> (file_path, is_package)
        canonical: Dict[str, Tuple[str, bool]] = {}

        self._package_modules = set()
        self._path_to_module = {}
        self._shadowed_files = {}
        self._name_collisions = []

        self._log(f"Scanning directory: {scan_dir}")

        for root, dirs, files in os.walk(scan_dir):
            # 跳过常见的排除目录（排序保证遍历确定性）
            dirs[:] = sorted(d for d in dirs if d not in (
                '__pycache__', '.git', 'output', 'build', '.cypy_cache',
                'node_modules', '.venv', 'venv'
            ))

            for file in sorted(files):
                if not file.endswith('.cypy'):
                    continue

                file_path = os.path.abspath(os.path.join(root, file))
                module_name = self._path_to_module_name(file_path, scan_dir)
                is_package = file == '__init__.cypy'

                existing = canonical.get(module_name)
                if existing is None:
                    canonical[module_name] = (file_path, is_package)
                    discovered[module_name] = file_path
                    self._path_to_module[file_path] = module_name
                    if is_package:
                        self._package_modules.add(module_name)
                    self._log(f"  Found module: {module_name} ({file_path})")
                    continue

                prev_path, prev_is_package = existing
                if is_package and not prev_is_package:
                    # 包优先：__init__.cypy 接管规范名，原先的模块文件转为被遮蔽
                    shadowed_path = prev_path
                    canonical[module_name] = (file_path, True)
                    discovered[module_name] = file_path
                    self._package_modules.add(module_name)
                    self._path_to_module[file_path] = module_name
                    self._path_to_module.pop(prev_path, None)
                else:
                    shadowed_path = file_path

                shadow_key = "%s@shadowed:%s" % (
                    module_name,
                    os.path.relpath(shadowed_path, scan_dir).replace(os.sep, "."),
                )
                discovered[shadow_key] = shadowed_path
                self._shadowed_files[shadow_key] = shadowed_path
                self._name_collisions.append({
                    "module_name": module_name,
                    "kept": discovered[module_name],
                    "shadowed": shadowed_path,
                })
                self._log(f"  Module-name collision on {module_name!r}: "
                          f"kept {discovered[module_name]}, shadowed {shadowed_path}")

        self._source_files = discovered
        return discovered

    def _is_package_module(self, module_name: str) -> bool:
        """该模块名是否来自某个目录的 `__init__.cypy`（即一个包）"""
        return module_name in self._package_modules

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
        self._parse_errors = {}

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
                # 记录而不是只打日志：模块解析失败会让它从类型注册表和依赖图里消失
                self._parse_errors[module_name] = str(e)
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

    def _note_import_diagnostic(self, message: str) -> None:
        """记录一条导入解析诊断（未找到 / 歧义 / 越过顶层包），同一信息只记一次"""
        if message not in self._import_diagnostics:
            self._import_diagnostics.append(message)
            self._log(f"  Import diagnostic: {message}")

    def _resolve_import_target(self, import_path: str, current_module: str) -> Optional[str]:
        """把导入路径解析成项目内的模块名

        * 相对导入：按 CPython 的层级语义推导（见 :meth:`_resolve_relative_import`），
          返回推导出的名字——是否存在由调用方判断（依赖图只对真实存在的模块建边）。
        * 绝对导入：只接受精确模块名，或按项目根解析出的候选路径；
          不再用 `mod_name.endswith('.' + import_path)` 这种模糊后缀匹配
          （它会把 `pkg.mod` 绑到毫不相关的 `vendor.pkg.mod`，
          同名模块存在多个时还会静默取 os.walk 的第一个命中）。
          找不到或有多个候选时输出诊断并返回 None。
        """
        if not import_path:
            return None

        # 相对导入
        if import_path.startswith('.'):
            return self._resolve_relative_import(import_path, current_module)

        candidates: List[str] = []

        # 1) 精确模块名
        if import_path in self._source_files and '@shadowed:' not in import_path:
            candidates.append(import_path)

        # 2) 按项目根解析成路径（`a.b` -> <root>/a/b.cypy 或 <root>/a/b/__init__.cypy）
        rel = import_path.replace('.', os.sep)
        for path in (os.path.join(self._project_root, rel + '.cypy'),
                     os.path.join(self._project_root, rel, '__init__.cypy')):
            name = self._path_to_module.get(os.path.abspath(path))
            if name and name not in candidates:
                candidates.append(name)

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            self._note_import_diagnostic(
                f"ambiguous import {import_path!r} in {current_module!r}: "
                f"multiple candidates {sorted(candidates)}"
            )
            return None

        self._note_import_diagnostic(
            f"import {import_path!r} in {current_module!r} not found in project "
            f"(it is not a .cypy module of this project)"
        )
        return None

    def _resolve_relative_import(self, import_path: str,
                                 current_module: str) -> Optional[str]:
        """解析 `.`/`..` 形式的相对导入

        CPython 语义：level=N 的基准是“把当前模块往上剥 N-1 层后所在的那个包”。
        也就是说，非包模块 `a.b.c` 里 `from .sib import y` 的基准是父包 `a.b`
        （剥掉的层数是 N），而包自身 `a.b`（来自 `__init__.cypy`）里同样的写法
        基准是 `a.b`（剥掉的层数是 N-1）。旧实现只有一条
        `current_parts[:len - dot_count + 1]` 公式——那是包专用的，
        因为 :meth:`_path_to_module_name` 把 `__init__` 的信息抹掉了；
        于是叶子模块的相对导入整体下了一层，`pkg.sub.leaf` 里的 `.sib`
        被解析成 `pkg.sub.leaf.sib`（解析不到，依赖边被静默丢弃），
        `pkg.sub.leaf` 里的 `..sib` 被解析成 **错误的** `pkg.sub.sib`。
        现在把“是不是包”从发现阶段带下来，两种情形各自正确。
        """
        stripped = import_path.lstrip('.')
        tail = stripped.split('.') if stripped else []
        dot_count = len(import_path) - len(stripped)

        current_parts = current_module.split('.')
        # 包自身就是基准（少剥一层）
        keep = len(current_parts) - dot_count + (1 if self._is_package_module(current_module) else 0)

        if keep < 0:
            self._note_import_diagnostic(
                f"attempted relative import {import_path!r} beyond top-level package "
                f"(in {current_module!r})"
            )
            return None

        base_parts = current_parts[:keep]
        target_parts = base_parts + tail
        if not target_parts:
            self._note_import_diagnostic(
                f"attempted relative import with no known parent package "
                f"(in {current_module!r})"
            )
            return None

        return '.'.join(target_parts)

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
        """获取类型节点的字符串表示

        解析器类型位置产出的 kind 是 Name / GenericType / UnionType / PointerType /
        RefType / VecType / Constant。旧实现里 ``kind == Identifier`` 与
        ``kind == TypeAnnotation`` 两个分支从不命中——parser.py 从不产出这两种 kind
        （IDENTIFIER 只是 lexer 的 token 类型，落到 AST 就是 Name），真正生效的一直是
        末尾的 ``hasattr(type_node, 'id')`` 兜底，因此删掉死分支并补上此前被漏掉的
        GenericType / UnionType / PointerType / VecType / 列表常量：
        ``Vec[int]`` 以前返回 'Any'，``-> [int]``（Constant 包了一个 Name 列表）
        以前返回 repr 出来的垃圾串 '[Name(line=1, col=20)]'。
        """
        if type_node is None:
            return 'Any'
        if isinstance(type_node, str):
            return type_node

        kind = getattr(type_node, 'kind', None)

        if kind == 'GenericType':
            args = getattr(type_node, 'args', None) or []
            name = str(getattr(type_node, 'name', 'Any'))
            if args:
                return "%s[%s]" % (name, ",".join(self._get_type_str(a) for a in args))
            return name

        if kind == 'UnionType':
            types = getattr(type_node, 'types', None) or []
            if types:
                return " | ".join(self._get_type_str(t) for t in types)
            return 'Any'

        if kind in ('PointerType', 'RefType'):
            return "*%s" % self._get_type_str(getattr(type_node, 'base_type', None))

        if kind == 'VecType':
            return "vec[%s; %s]" % (self._get_type_str(getattr(type_node, 'element_type', None)),
                                     getattr(type_node, 'size', 0))

        if hasattr(type_node, 'id'):
            return type_node.id

        if hasattr(type_node, 'value'):
            value = type_node.value
            if isinstance(value, (list, tuple)):
                # 形如 `-> [int]` 的列表类型标注：逐个元素递归，避免 repr 泄漏 AST 对象
                return "[%s]" % ",".join(self._get_type_str(v) for v in value)
            return str(value)

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
            errors.extend(scope_analyzer.errors)

            # 运行类型检查
            type_checker = TypeChecker()
            # 将 TypeRegistry 传递给类型检查器（如果支持）
            if hasattr(type_checker, 'set_type_registry'):
                type_checker.set_type_registry(self._type_registry)
            type_checker.check(ast)

            # 收集类型检查错误
            if hasattr(type_checker, 'errors'):
                errors.extend(type_checker.errors)

            # 作用域与类型两条通道对同一处会给出逐字相同的诊断（如 Undefined name）
            errors = list(dict.fromkeys(errors))
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
            # BUG-90：项目模式知道每个模块的源路径，必须传给生成器——否则产物里没有
            # `__name__`/`__file__`（生成器在无路径时不伪造身份）。
            generator = CythonGenerator(self._source_files.get(module_name))
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
                # 与 cypy_hook.hook.compile_to_pyd 同一套 sys.path 隔离：
                # 产物目录里与 stdlib 撞名的 .pyd 不得进入 setup.py 的导入路径。
                from cypy_hook.hook import build_isolated_command, build_isolated_env
                result = subprocess.run(
                    build_isolated_command("setup.py", "build_ext", "--inplace"),
                    capture_output=True,
                    timeout=120,
                    env=build_isolated_env(),
                )

                # 以字节读取并容错解码，避免 Windows 下默认 GBK 编码导致的
                # UnicodeDecodeError（编译器输出可能含非 GBK 字节）
                raw_err = result.stderr if isinstance(result.stderr, bytes) else result.stderr.encode("utf-8", "replace")
                stderr_text = raw_err.decode("utf-8", "replace")

                if result.returncode != 0:
                    errors.append(f"Build failed: {stderr_text[-500:]}")
                    return False, None, errors

                # Step 5: 查找生成的扩展模块（名字由解释器的 EXT_SUFFIX 决定，
                # 不是固定的 .pyd；同时优先 --inplace 落在模块目录里的本次产物）
                pyd_files = []
                for root, dirs, files in os.walk(module_output_dir):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for file in files:
                        if file.endswith((".pyd", ".so", ".dll")):
                            pyd_files.append(os.path.abspath(os.path.join(root, file)))

                picked = self._pick_extension(pyd_files, module_name, module_output_dir)
                if picked:
                    return True, picked, []
                else:
                    errors.append("No .pyd file generated")
                    return False, None, errors

            finally:
                os.chdir(old_cwd)

        except Exception as e:
            return False, None, [str(e)]

    @staticmethod
    def _pick_extension(candidates: List[str], module_name: str,
                        output_dir: str) -> Optional[str]:
        """在本次构建的产物里挑出真正属于 module_name 的扩展模块

        旧实现取 `pyd_files[0]`：遍历顺序决定结果，目录里残留的历史产物也可能被当成
        本次产物回报。这里按 “本目录 > build/ 子目录” 和 “模块名 + EXT_SUFFIX > 同名前缀”
        排序挑选。
        """
        if not candidates:
            return None

        import sysconfig
        suffix = sysconfig.get_config_var("EXT_SUFFIX") or ".pyd"
        stem = module_name.split('.')[-1]
        out_abs = os.path.abspath(output_dir)

        def score(path: str) -> Tuple[int, int]:
            here = 0 if os.path.dirname(path) == out_abs else 1
            named = 0 if os.path.basename(path) == stem + suffix else 1
            return here + named, here

        for path in sorted(candidates, key=lambda p: (score(p), p)):
            base = os.path.basename(path)
            if base == stem or base.startswith(stem + "."):
                return path
        # BUG-17: 名字全不匹配时必须返回 None —— 兜底返回 sorted()[0] 会把
        # 别的模块或历史残留的 .pyd 当成本次该模块的产物，令「No .pyd file
        # generated」永不触发，与本函数 docstring 声明的挑选目的相反。
        return None

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

        # 模块名冲突（foo.cypy 与 foo/__init__.cypy 归一到同一个名字）：
        # 让构建确定性地失败，而不是按 os.walk 顺序“留下一个、静默丢掉另一个”。
        if self._name_collisions:
            result.errors['_discovery'] = [
                "module name collision: %r is provided by both %s and %s "
                "(package __init__ wins; the shadowed file is registered as %s and is "
                "not importable - rename one of them)"
                % (c["module_name"], c["kept"], c["shadowed"],
                   "%s@shadowed:..." % c["module_name"])
                for c in self._name_collisions
            ]
            self._log(f"Error: module name collisions: {self._name_collisions}")
            result.total_time = time.time() - start_time
            return result

        # Step 2: 解析所有模块
        self._log("Step 2: Parsing all modules...")
        self.parse_all_modules()
        for _name, _err in sorted(self._parse_errors.items()):
            result.warnings.append(
                f"module {_name!r} failed to parse and is skipped "
                f"(no type exports, no dependency edges): {_err}"
            )

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

        # 导入解析诊断（未找到 / 歧义）作为警告暴露出来，不再静默
        result.warnings.extend(self._import_diagnostics)

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
            if not modules_to_compile:
                result.errors['_entry_point'] = [
                    f"entry_point {entry_point!r} resolved to nothing: it is not a "
                    f"discovered module of this project "
                    f"(known modules: {sorted(self._source_files)})"
                ]

        # 被拓扑排序（Kahn）丢弃的模块 = 还留在环里的模块，绝不等于“编译过了”
        dropped_by_cycle = [
            m for m in self._source_files
            if m not in compilation_order and '@shadowed:' not in m
        ]
        if dropped_by_cycle:
            result.errors['_cycles'] = [
                f"{len(dropped_by_cycle)} module(s) were dropped from the compilation "
                f"order because they take part in a dependency cycle: "
                f"{sorted(dropped_by_cycle)} (cycles: {cycles})"
            ]

        # Step 6: 逐模块类型检查和编译
        self._log(f"Step 5: Compiling {len(modules_to_compile)} modules...")

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
                self._log(f"    Compilation failed: {compile_errors}")

        # 成功与否在编译循环 **之后** 计算：
        # 旧实现在循环之前无条件 `result.success = True`，于是 modules_to_compile 为空
        # （entry_point 写错、或全部模块都在环里被 Kahn 丢弃）时
        # 回报 success=True / compiled_modules=[] / errors={}，CLI 打印 “Build succeeded”
        # 而实际什么都没编译。
        if modules_to_compile and not result.compiled_modules and not result.errors:
            result.errors['_'] = ["no module was compiled"]
        result.success = bool(result.compiled_modules) and not result.errors

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
                    except Exception as exc:
                        import sys
                        print(f"[cypy][warn] 模块 {module_name} 增量重解析失败，"
                              f"本次仍使用陈旧 AST，请全量重编以确认: {exc}",
                              file=sys.stderr)

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
