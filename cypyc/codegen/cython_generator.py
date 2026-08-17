import re
from typing import Any, List, Dict, Set
from cypyc.parser.parser import (
    ASTNode, Module, FuncDef, LetStmt, ReturnStmt, IfStmt, ForStmt, WhileStmt,
    BinOp, UnaryOp, Call, Name, Constant, Attribute, Subscript, StructDef,
    StructField, EnumDef, EnumVariant, DeferStmt,     DerefExpr, PointerType, DictLiteral,
    RefType, GenericType, TraitDef, ImplStmt, MetaBlock, GuardStmt, ComptimeStmt,
    BuildBlockExpr, CastExpr, ClassDef, Import, FromImport, ExceptionDef,
    SuiteDef, TestDef, SetupStmt, TeardownStmt, ListComp, ComptimeFuncDef,
    ArrayPattern, SlicePattern, StructPattern, TypePattern, DictPattern, AsPattern,
    ExtractorPattern, RangePattern, UnionType, TypeClassDef, TypeClassImpl,
    BreakStmt, ContinueStmt, GlobalStmt, NonlocalStmt, VecType, VecLiteral, PipeExpr,
    MacroDef, MacroCall, DuckDef, DuckRequirement,
    BuildValueExpr, IfExp, AwaitExpr, BacktickBlock
)
from cypyc.codegen.type_mapper import TypeMapper


import os
import time
import platform

class CythonGenerator:
    def __init__(self, source_file: str = None):
        self.indent = 0
        self.output = []
        self.type_mapper = TypeMapper()
        self.in_cdef_context = False
        self.needs_libc_import = False  # 是否需要导入C标准库
        self._current_local_types = {}  # 当前函数内局部变量/参数名 -> Cython 类型字符串
        self.source_file = source_file  # 源文件路径
        # 模块符号收集
        self.public_symbols = []
        self.private_symbols = []
        self.imported_modules = []
        # 当前结构体名称（用于方法生成时添加self参数）
        self._current_struct_name = None
        # 类型别名注册表（用于在代码生成阶段展开类型别名）
        self.type_aliases: Dict[str, Any] = {}  # {alias_name: TypeAlias node}
        # 枚举类型注册表（用于类型转换时识别枚举）
        self.enum_defs: Dict[str, EnumDef] = {}  # {enum_name: EnumDef node}
        # 模块级变量注册表（用于在函数中添加global声明）
        self.module_vars: Set[str] = set()
        # 用户自定义的魔法属性（避免重复生成）
        self.user_defined_magic_attrs: Set[str] = set()
        # 魔法方法注册表：{type_name: {method_name: FuncDef}}
        self.magic_methods: Dict[str, Dict[str, Any]] = {}
        # 隐式转换记录：{var_name: (source_expr, source_type, target_type)}
        self._pending_conversions: Dict[str, tuple] = {}
        # 隐式复制记录：{var_name: source_expr}
        self._pending_copies: Dict[str, str] = {}
        # 循环嵌套深度（用于循环守卫生成 break 而不是 return）
        self._loop_depth: int = 0
        # 宏定义注册表：{macro_name: MacroDef node}
        self.macro_defs: Dict[str, MacroDef] = {}
        # 泛型参数集合（作为类型标识符时回退为 object）
        self._generic_params: Set[str] = set()
        # 提取器类型注册表：定义了 __unapply__/__unapply_seq__/__unwarp__/__match_args__ 的类型名
        self._extractor_types: Set[str] = set()
        # cdef struct 类型名（isinstance 不可用，类模式只做字段检查）
        self._struct_types: Set[str] = set()
        # 类/结构体字段顺序：{type_name: [field_name, ...]}（用于类模式位置参数绑定）
        self._class_fields: Dict[str, list] = {}
        # meta 块编译期命名空间（跨多个 meta 块共享，用于条件生成与常量求值）
        self._meta_namespace: Dict[str, Any] = {}
        # 构建块（=:）转换为嵌套函数时使用的唯一计数器
        self._bb_counter: int = 0
        # 被提升到函数开头的指针变量基类型映射：{name: base_type}
        self._hoisted_pointer_types: Dict[str, str] = {}
        # typing 构造类型在 cdef/cpdef 中不可用，回退为 object
        _object_generics = ('Callable', 'Optional', 'Union', 'Any', 'Sequence',
                            'Iterable', 'Mapping', 'MutableMapping', 'Set', 'FrozenSet',
                            'Type', 'Generator', 'Coroutine', 'Awaitable', 'Deque', 'DefaultDict')
        self._object_generic_types = set(_object_generics)
        for _t in _object_generics:
            self.type_mapper.add_custom_type(_t, 'object', 'object')

    def generate(self, node: ASTNode) -> str:
        self.output = []
        # 编译期宏展开：将反引号宏（@name!(...)）在代码生成前展开为真实语句。
        # 仅在 AST 含宏相关节点时执行，普通代码不受影响；字符串模板宏
        # （macro name = f"..."）不含 BacktickBlock，会被正常保留并继续由
        # 本生成器的 _expand_macro 处理。
        if self._contains_macro_nodes(node):
            from cypyc.parser.macro_expander import expand_macros
            node = expand_macros(node)
        # 首先收集所有类型别名定义
        self._collect_type_aliases(node)
        # 然后检测是否需要C库导入
        self._detect_libc_usage(node)
        self._visit(node)
        return "\n".join(self.output)

    @staticmethod
    def _contains_macro_nodes(node: ASTNode) -> bool:
        """快速判断 AST 是否包含需要在代码生成前展开的宏节点"""
        stack = [node]
        while stack:
            cur = stack.pop()
            if not isinstance(cur, ASTNode):
                continue
            kind = getattr(cur, 'kind', None)
            if kind in ('MacroDef', 'MacroCall', 'BacktickBlock', 'ComptimeStmt'):
                return True
            for attr in cur.__dict__.values():
                if isinstance(attr, ASTNode):
                    stack.append(attr)
                elif isinstance(attr, list):
                    stack.extend(a for a in attr if isinstance(a, ASTNode))
        return False
    
    def _collect_type_aliases(self, node: ASTNode) -> None:
        """收集所有类型别名定义到注册表"""
        if hasattr(node, 'kind') and node.kind == 'TypeAlias':
            self.type_aliases[node.name] = node
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._collect_type_aliases(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._collect_type_aliases(item)
    
    def _detect_libc_usage(self, node: ASTNode) -> None:
        """检测代码中是否使用了需要C标准库的函数"""
        if isinstance(node, Call) and hasattr(node.func, 'id'):
            if node.func.id in ('malloc', 'free', 'sizeof', 'addr'):
                self.needs_libc_import = True
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._detect_libc_usage(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._detect_libc_usage(item)
    
    def _check_is_generator(self, stmts: List[Any]) -> bool:
        """递归检查语句列表中是否包含 yield 语句"""
        for stmt in stmts:
            if hasattr(stmt, 'kind') and stmt.kind == 'YieldStmt':
                return True
            # 递归检查嵌套语句
            if hasattr(stmt, 'body') and isinstance(stmt.body, list):
                if self._check_is_generator(stmt.body):
                    return True
            # 检查 elif 和 else 分支
            if hasattr(stmt, 'orelse'):
                orelse = stmt.orelse
                if isinstance(orelse, list):
                    if self._check_is_generator(orelse):
                        return True
                elif hasattr(orelse, 'body') and isinstance(orelse.body, list):
                    if self._check_is_generator(orelse.body):
                        return True
        return False

    def _check_has_closure(self, stmts: List[Any]) -> bool:
        """递归检查语句列表中是否包含闭包（BuildBlockExpr），Cython cpdef 不支持闭包"""
        for stmt in stmts:
            if self._node_has_closure(stmt):
                return True
        return False

    def _node_has_closure(self, node: Any) -> bool:
        """检查单个节点是否包含闭包"""
        if node is None:
            return False
        # 嵌套的函数定义（FuncDef / AsyncFuncDef）会形成闭包，Cython 的 cpdef/cdef 不支持
        if getattr(node, 'kind', None) in ('FuncDef', 'AsyncFuncDef'):
            return True
        # lambda 表达式也是闭包，所在函数必须使用 def（cpdef 不支持闭包）
        if getattr(node, 'kind', None) == 'LambdaExpr':
            return True
        # spawn / go 块会生成嵌套函数（闭包），所在函数也必须使用 def
        if getattr(node, 'kind', None) in ('SpawnStmt', 'GoStmt'):
            return True
        if hasattr(node, 'kind') and node.kind == 'BuildBlockExpr':
            return self._build_block_generates_closure(node)
        # 检查函数调用中的参数
        if hasattr(node, 'args'):
            for arg in (node.args if isinstance(node.args, list) else []):
                if isinstance(arg, tuple) and len(arg) == 2:
                    if self._node_has_closure(arg[1]):
                        return True
                elif self._node_has_closure(arg):
                    return True
        # 检查属性节点
        if hasattr(node, 'value'):
            if self._node_has_closure(node.value):
                return True
        # 递归检查嵌套语句
        if hasattr(node, 'body'):
            body = node.body if isinstance(node.body, list) else [node.body]
            for item in body:
                if self._node_has_closure(item):
                    return True
        if hasattr(node, 'orelse'):
            orelse = node.orelse
            if isinstance(orelse, list):
                for item in orelse:
                    if self._node_has_closure(item):
                        return True
            elif hasattr(orelse, 'body'):
                if self._node_has_closure(orelse):
                    return True
        # 检查 Call 节点的 func 属性
        if hasattr(node, 'func'):
            if self._node_has_closure(node.func):
                return True
        return False

    def _build_block_generates_closure(self, node: Any) -> bool:
        """检查构建块是否会生成闭包（lambda），单表达式优化时不会生成"""
        block_type = getattr(node, 'block_type', None)
        if block_type not in (BuildBlockExpr.BUILD_ASSIGN, BuildBlockExpr.BUILD_CALL):
            return False
        # 检查是否为单表达式（无 lambda）
        has_complex = False
        expr_count = 0
        for stmt in (node.body or []):
            stmt_kind = getattr(stmt, 'kind', None)
            if stmt_kind == 'LetStmt':
                has_complex = True
            elif stmt_kind == 'ReturnStmt':
                if hasattr(stmt, 'value') and stmt.value:
                    expr_count += 1
                else:
                    has_complex = True
            elif stmt_kind == 'ExprStmt':
                inner = getattr(stmt, 'value', None)
                if inner is not None:
                    expr_count += 1
                else:
                    has_complex = True
            elif isinstance(stmt, (BinOp, UnaryOp, Call, Name, Constant)):
                expr_count += 1
            else:
                has_complex = True
        # 单表达式且无复杂语句 → 不生成闭包
        if not has_complex and expr_count <= 1:
            return False
        return True

    def _visit(self, node: ASTNode) -> Any:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        else:
            self._visit_children(node)
            return None

    def _visit_children(self, node: ASTNode) -> None:
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)

    def _write(self, text: str) -> None:
        if text:
            self.output.append("    " * self.indent + text)

    def _visit_Module(self, node: Module) -> None:
        # Cython 编译指令必须位于文件最顶部（在任何语句/文档字符串之前），否则会被忽略
        self._write("# cython: language_level=3")
        self._write("# cython: boundscheck=False")
        self._write("# cython: wraparound=False")
        # 注意：不使用 cdivision=True。Cypy 语义与 Python 一致，整数除零应触发
        # ZeroDivisionError 而非编译成 C 常量除零（会导致 C2124 编译错误）。
        self._write("# cython: initializedcheck=False")
        self._write("# cython: nonecheck=False")
        # 抑制某些仅作警告处理的诊断（如 match 后的不可达代码），避免被当作错误中断编译
        self._write("# cython: warn.unreachable=False")
        self._write("# cython: warn.undeclared=False")
        self._write("")
        self._write("# Generated by Cypy compiler")
        self._write('"""')
        self._write(f"Cython module compiled from Cypy source")
        self._write(f"Source file: {self.source_file or 'unknown'}")
        self._write('"""')
        self._write("")
        
        # 导入 cython 模块用于优化装饰器
        self._write("import cython")
        # 指针相关 C 函数（malloc/free/sizeof 等），按需可用
        self._write("from libc.stdlib cimport malloc, free")
        self._write("from libc.string cimport memset")
        self._write("")
        # 元编程内置常量（供 meta 块/__generated_at__ 等使用）
        self._write("import datetime as _cypy_dt")
        self._write("__generated_at__ = _cypy_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')")
        self._write("__module_version__ = '1.0.0'")
        self._write("")
        
        # 添加C标准库导入
        if self.needs_libc_import:
            # sizeof是Cython内置关键字，不需要导入
            self._write("from libc.stdlib cimport malloc, free")
            self._write("")
        
        # 第一遍：收集模块信息
        self._collect_module_info(node)
        
        # 生成模块级魔法属性
        self._generate_module_magic_attrs()
        
        # 第二遍：生成代码
        for stmt in node.body:
            self._visit(stmt)
    
    def _collect_module_info(self, node: Module) -> None:
        """收集模块级符号和导入信息"""
        for stmt in node.body:
            if isinstance(stmt, FuncDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
            elif isinstance(stmt, StructDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
                self._struct_types.add(name)
                # 检测提取器类型并收集字段顺序
                fields = []
                for m in (getattr(stmt, 'body', None) or []):
                    mname = getattr(m, 'name', None)
                    if mname in ('__unapply__', '__unapply_seq__', '__unwarp__', '__match_args__'):
                        self._extractor_types.add(name)
                        break
                    if mname:
                        fields.append(mname)
                if fields:
                    self._class_fields[name] = fields
            elif isinstance(stmt, ClassDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
                # 检测是否为提取器类型（定义了 __unapply__ 等方法）并收集字段顺序
                fields = []
                for m in (getattr(stmt, 'body', None) or []):
                    mname = getattr(m, 'name', None)
                    if mname in ('__unapply__', '__unapply_seq__', '__unwarp__', '__match_args__'):
                        self._extractor_types.add(name)
                        break
                    if mname:
                        fields.append(mname)
                if fields:
                    self._class_fields[name] = fields
            elif isinstance(stmt, EnumDef):
                name = stmt.name
                self.enum_defs[name] = stmt  # 注册枚举类型
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
            elif isinstance(stmt, LetStmt):
                name = stmt.name
                self.module_vars.add(name)  # 注册模块级变量
                # 检查是否是用户自定义的魔法属性
                if name in ('__all__', '__private__', '__deps__'):
                    self.user_defined_magic_attrs.add(name)
            elif isinstance(stmt, TraitDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
            elif isinstance(stmt, TypeClassDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
            elif isinstance(stmt, Import):
                module_name = stmt.module
                if module_name not in self.imported_modules:
                    self.imported_modules.append(module_name)
            elif isinstance(stmt, FromImport):
                module_name = stmt.module
                if module_name not in self.imported_modules:
                    self.imported_modules.append(module_name)
            elif isinstance(stmt, MacroDef):
                self.macro_defs[stmt.name] = stmt
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
            elif isinstance(stmt, ComptimeFuncDef):
                name = stmt.name
                if name.startswith('_'):
                    self.private_symbols.append(name)
                else:
                    self.public_symbols.append(name)
    
    def _generate_module_magic_attrs(self) -> None:
        """生成模块级魔法属性"""
        # 获取模块名（从文件名提取）
        module_name = "unknown"
        if self.source_file:
            module_name = os.path.splitext(os.path.basename(self.source_file))[0]
        
        # 文件路径
        file_path = self.source_file or ""
        
        # 包信息
        package_name = ""
        path_value = "None"
        if self.source_file:
            dir_name = os.path.dirname(self.source_file)
            init_file = os.path.join(dir_name, "__init__.py")
            if os.path.exists(init_file):
                package_name = os.path.basename(dir_name)
                path_value = f"['{dir_name}']"
        
        # 编译时间
        compile_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        # 目标平台
        target_platform = f"{platform.machine()}-{platform.system().lower()}"
        
        # 生成魔法属性（始终生成这些基础属性）
        self._write(f"__name__ = \"{module_name}\"")
        self._write(f"__file__ = \"{file_path}\"")
        self._write(f"__package__ = \"{package_name}\"")
        self._write(f"__path__ = {path_value}")
        self._write(f"__compile_time__ = \"{compile_time}\"")
        self._write(f"__target__ = \"{target_platform}\"")
        self._write(f"__profile__ = \"debug\"")
        
        # __all__：公开API列表（不含_前缀，包含魔法方法）
        # 仅在用户未自定义时自动生成
        if '__all__' not in self.user_defined_magic_attrs:
            all_list = [s for s in self.public_symbols if not s.startswith('_') or (s.startswith('__') and s.endswith('__'))]
            all_str = ', '.join(f'"{s}"' for s in all_list)
            self._write(f"__all__ = [{all_str}]")
        
        # __private__：私有符号列表（_前缀）
        # 仅在用户未自定义时自动生成
        if '__private__' not in self.user_defined_magic_attrs:
            private_str = ', '.join(f'"{s}"' for s in self.private_symbols if s.startswith('_') and not (s.startswith('__') and s.endswith('__')))
            self._write(f"__private__ = [{private_str}]")
        
        # __deps__：依赖模块列表
        # 仅在用户未自定义时自动生成
        if '__deps__' not in self.user_defined_magic_attrs:
            deps_str = ', '.join(f'"{s}"' for s in self.imported_modules)
            self._write(f"__deps__ = [{deps_str}]")
        
        self._write("")

    def _visit_Decorator(self, node: Any) -> None:
        """生成装饰器的 Cython 代码"""
        decorator_str = f"@{self._expr_to_str(node.name)}"
        if node.args:
            args_str = ", ".join(self._expr_to_str(arg) for arg in node.args)
            decorator_str += f"({args_str})"
        self._write(decorator_str)

    def _generate_param_strings(self, node: FuncDef, is_struct_method: bool, has_self: bool, use_types: bool = False) -> List[str]:
        """生成参数字符串列表，处理可变参数和分隔符"""
        params = []
        
        # 结构体方法自动添加 self 参数（如果还没有）
        if is_struct_method and not has_self:
            if use_types:
                params.append(f"{self._current_struct_name} self")
            else:
                params.append("self")
        
        # 统计分隔符数量
        dot_separator_count = sum(1 for p in node.params if getattr(p, 'is_dot_separator', False))
        has_double_dot = dot_separator_count >= 2
        
        # 跟踪是否已经添加了 *args 和 **kwargs
        added_var_positional = False
        added_var_keyword = False
        
        for param in node.params:
            # 跳过 .. 分隔符（它们只是语法标记，不生成代码）
            if getattr(param, 'is_dot_separator', False):
                continue
            
            # 处理 *args（可变位置参数）
            if getattr(param, 'is_var_positional', False):
                params.append(f"*{param.name}")
                added_var_positional = True
                continue
            
            # 处理 **kwargs（可变关键字参数）
            if getattr(param, 'is_var_keyword', False):
                params.append(f"**{param.name}")
                added_var_keyword = True
                continue
            
            # 普通参数
            if use_types and param.type_annotation:
                param_str = f"{self._type_to_str(param.type_annotation)} {param.name}"
                # 如果参数是 ref，添加 & 后缀（C++ 引用语法）
                if getattr(param, 'is_ref', False):
                    param_str = f"{self._type_to_str(param.type_annotation)}& {param.name}"
                # 跟踪指针参数名（供指针算术/指针比较的 NULL 转换使用）
                if isinstance(param.type_annotation, PointerType):
                    base = param.type_annotation.base_type
                    self._hoisted_pointer_types[param.name] = self._type_to_str(base) if base is not None else "void"
            else:
                param_str = param.name
            
            params.append(param_str)
        
        # 双 .. 模式：自动添加 *args 和 **kwargs（如果还没有）
        if has_double_dot and not added_var_positional:
            params.append("*args")
        if has_double_dot and not added_var_keyword:
            params.append("**kwargs")
        
        return params
    
    def _visit_FuncDef(self, node: FuncDef) -> None:
        # 泛型参数在签名/体内作为类型标识符时回退为 object
        saved_generic_params = set(self._generic_params)
        if node.generic_params:
            self._generic_params |= set(node.generic_params)

        # 检查是否有 @python 装饰器
        has_python_decorator = False
        other_decorators = []
        if hasattr(node, 'decorators') and node.decorators:
            for decorator in node.decorators:
                decorator_name = getattr(decorator.name, 'id', str(decorator.name))
                if decorator_name == 'python':
                    has_python_decorator = True
                else:
                    other_decorators.append(decorator)
        
        # 生成非 @python 装饰器
        for decorator in other_decorators:
            self._visit_Decorator(decorator)
        
        has_type_annotation = any(p.type_annotation for p in node.params if not getattr(p, 'is_dot_separator', False)) or node.return_type

        # 检测是否包含指针类型参数/返回值：指针类型必须生成强类型签名
        # （int* 无法转为 Python 对象，普通无类型 def 参数会编译失败）
        def _is_pointer_type(ann):
            return ann is not None and isinstance(ann, PointerType)
        has_pointer_param = any(_is_pointer_type(getattr(p, 'type_annotation', None)) for p in node.params)
        has_pointer_return = _is_pointer_type(node.return_type)
        has_pointer_type = has_pointer_param or has_pointer_return

        # never / Never 返回类型语义上表示“不返回”，必须显式保留为 NoReturn 注解
        # （即便普通模块级函数默认剥离类型注解，也要为 Never 特例保留）
        def _is_never_type(rt):
            if rt is None:
                return False
            return getattr(rt, 'id', None) in ('never', 'Never', 'NeverType')
        return_is_never = _is_never_type(node.return_type)
        
        # 处理 <checker> 参数检查站（定义时的 checker，在函数体开头自动调用）
        has_checker = node.params_checker is not None
        
        # 检查是否是结构体方法（如果是，需要添加 self 参数）
        is_struct_method = getattr(node, 'is_struct_method', False)
        
        # 检查方法是否已经有 self 参数
        has_self = node.params and node.params[0].name == 'self'
        
        # 检查是否是生成器函数（包含 yield 语句）
        # Cython 中 cpdef 函数不能包含 yield，必须使用 def
        is_generator = self._check_is_generator(node.body)
        
        # Cython 中 cpdef 函数不能包含闭包（lambda），必须使用 def
        has_closure = self._check_has_closure(node.body)
        
        # fn 严格模式函数：强制生成 cdef 代码
        is_fn = getattr(node, 'is_fn', False)
        
        # 统计分隔符数量（用于双 .. 模式激活 args/kwargs）
        dot_separator_count = sum(1 for p in node.params if getattr(p, 'is_dot_separator', False))
        has_double_dot = dot_separator_count >= 2

        # 嵌套函数（定义在其他函数体内）必须使用 def（Cython 不支持嵌套 cpdef/cdef）
        is_nested = getattr(self, '_func_depth', 0) > 0
        if is_nested:
            is_fn = False
            has_type_annotation = False

        # 特殊方法（__xxx__）在 cdef class 中必须使用 def，不能用 cpdef/cdef
        is_dunder = node.name.startswith('__') and node.name.endswith('__') and len(node.name) > 4
        if is_dunder:
            is_fn = False
            has_type_annotation = False

        # 普通（非 cdef）class 中的方法不能使用 cpdef/cdef，必须用 def
        # 但若函数包含指针类型参数/返回值，仍必须生成带类型签名（cdef/def+类型），
        # 否则 int* 无法作为 Python 对象传参而编译失败。
        in_cdef_class = getattr(self, '_in_cdef_class', False)
        if not in_cdef_class and not has_pointer_type:
            is_fn = False
            has_type_annotation = False

        # 带任意装饰器的函数（含 @cython.* ）不能使用 cpdef/cdef，必须用 def
        if hasattr(node, 'decorators') and node.decorators:
            is_fn = False
            has_type_annotation = False

        # 记录当前函数的参数类型，供代码生成推断（如 int/int 除法）
        saved_local_types = dict(self._current_local_types)
        for p in node.params:
            ann = getattr(p, 'type_annotation', None)
            if ann is not None:
                self._current_local_types[p.name] = self._sanitize_type(self._type_to_str(ann))

        # @python 装饰的函数生成纯 Python 代码
        if has_python_decorator:
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=False)
            
            params_str = ", ".join(params)
            if params_str:
                self._write(f"def {node.name}({params_str}):")
            else:
                self._write(f"def {node.name}():")
        elif getattr(node, 'is_async', False):
            # async 函数：Cython 的 async def 必须使用 def（不支持 cpdef/cdef）
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=False)
            params_str = ", ".join(params)
            if return_is_never:
                rt = self._type_to_str(node.return_type)
                if params_str:
                    self._write(f"async def {node.name}({params_str}) -> {rt}:")
                else:
                    self._write(f"async def {node.name}() -> {rt}:")
            elif params_str:
                self._write(f"async def {node.name}({params_str}):")
            else:
                self._write(f"async def {node.name}():")
        elif is_fn and not is_generator and not has_closure:
            # fn 函数强制生成 cdef（优化性能）
            return_type = ""
            if node.return_type:
                return_type = f" {self._type_to_str(node.return_type)}"
            
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=True)
            
            # 添加 @cython.inline 优化装饰器
            self._write("@cython.inline")
            self._write(f"cdef{return_type} {node.name}({', '.join(params)}):")
        elif has_pointer_type and not is_generator and not has_closure and not is_nested:
            # 含指针类型的函数：必须生成 cdef 强类型签名。cdef 函数保持 C 类型，
            # 调用时不会把 int* 等 C 类型装箱为 Python 对象（def 会失败）。
            return_type = ""
            if node.return_type:
                return_type = f" {self._type_to_str(node.return_type)}"
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=True)
            self._write(f"cdef{return_type} {node.name}({', '.join(params)}):")
        elif has_type_annotation and not is_generator and not has_closure and not is_nested:
            return_type = ""
            if node.return_type:
                return_type = f" {self._type_to_str(node.return_type)}"
            
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=True)
            
            # 添加 @cython.binding(False) 优化装饰器（仅对结构体方法）
            # 模块级函数不能使用此装饰器，否则无法作为模块属性访问
            if is_struct_method:
                self._write("@cython.binding(False)")
            self._write(f"cpdef{return_type} {node.name}({', '.join(params)}):")
        else:
            # 有闭包或无类型注解时使用 def（Cython cpdef 不支持闭包）
            use_types = has_type_annotation and has_closure
            params = self._generate_param_strings(node, is_struct_method, has_self, use_types=use_types)
            params_str = ", ".join(params)
            if return_is_never:
                rt = self._type_to_str(node.return_type)
                if params_str:
                    self._write(f"def {node.name}({params_str}) -> {rt}:")
                else:
                    self._write(f"def {node.name}() -> {rt}:")
            elif params_str:
                self._write(f"def {node.name}({params_str}):")
            else:
                self._write(f"def {node.name}():")
        
        self.indent += 1

        # 进入函数体，递增嵌套深度（用于嵌套函数检测）
        self._func_depth = getattr(self, '_func_depth', 0) + 1

        # 收集函数体内所有指针声明，统一提升到函数开头用 cdef 声明。
        # Cython 不允许在循环/条件语句内部使用 cdef 声明，故必须先提升。
        pointer_decls = self._collect_pointer_decls(node.body)
        old_hoisted = getattr(self, '_hoisted_pointer_names', set())
        self._hoisted_pointer_names = set(name for name, _ in pointer_decls)
        old_hoisted_types = getattr(self, '_hoisted_pointer_types', {})
        self._hoisted_pointer_types = dict((name, base) for name, base in pointer_decls)
        # 同时把函数的指针参数纳入，供指针比较 / 指针参数 NULL 转换使用
        if not hasattr(self, '_func_pointer_indices'):
            self._func_pointer_indices = {}
        func_ptr_indices = self._func_pointer_indices
        func_ptr_indices.setdefault(node.name, set())
        for pi, p in enumerate(node.params):
            if getattr(p, 'type_annotation', None) is not None and isinstance(p.type_annotation, PointerType):
                pbase = p.type_annotation.base_type
                self._hoisted_pointer_types[p.name] = self._type_to_str(pbase) if pbase is not None else "void"
                func_ptr_indices[node.name].add(pi)
        if pointer_decls:
            for name, base in pointer_decls:
                self._write(f"cdef {base} * {name}")

        # 收集函数体内被 addr()/& 取地址的变量名，这些变量必须声明为 cdef 才能取址
        old_addr_taken = getattr(self, '_addr_taken', set())
        self._addr_taken = self._collect_addr_names(node.body)

        # 分离defer语句和普通语句
        defer_stmts = []
        normal_stmts = []
        
        for stmt in node.body:
            if isinstance(stmt, DeferStmt):
                defer_stmts.append(stmt)
            else:
                normal_stmts.append(stmt)
        
        # 检测函数体中使用的模块级变量，添加global声明
        used_module_vars = self._find_used_module_vars(node.body)
        if used_module_vars:
            self._write(f"global {', '.join(sorted(used_module_vars))}")
        
        # 在函数体开头添加 checker 调用（如果有）
        if has_checker and node.params_checker:
            checker_call = f"{node.params_checker}()"
            self._write(checker_call)
        
        # 处理可变参数：List<T> 安全收集模式
        # *args 语法的参数已经是元组，List<T> 模式需要转换为 list
        for param in node.params:
            if getattr(param, 'is_var_positional', False) and param.name != 'args':
                # 将 *param.name 收集的元组转换为 list（List<T> 安全收集模式）
                self._write(f"{param.name} = list({param.name})")
        
        # 处理双 .. 模式：注入 args/kwargs 变量
        if has_double_dot:
            # 在双 .. 模式下，args 和 kwargs 已经通过 *args/**kwargs 收集
            # 不需要额外处理，Python/Cython 会自动处理
            pass
        
        # 检查是否有defer语句
        if defer_stmts:
            # 不在 try/finally 中包裹（Cython 不允许在 try 内声明 cdef 变量），
            # 改为在每个顶层 return 之前、以及函数体末尾注入 defer 语句（逆序执行）
            def _emit_deferred():
                for defer_stmt in reversed(defer_stmts):
                    for stmt in defer_stmt.body:
                        if isinstance(stmt, (Call, BinOp, UnaryOp, Name, Constant)):
                            self._write(self._expr_to_str(stmt))
                        else:
                            self._visit(stmt)

            emitted_at_return = False
            for stmt in normal_stmts:
                if isinstance(stmt, ReturnStmt):
                    # 在 return 之前执行 defer（每个 return 处各注入一次）
                    _emit_deferred()
                    emitted_at_return = True
                self._visit(stmt)
            # 仅在函数没有显式 return 时才在函数末尾注入（避免与 return 前的注入重复）
            if not emitted_at_return:
                _emit_deferred()
        else:
            # 没有defer语句，直接输出所有语句
            for stmt in node.body:
                self._visit(stmt)
        
        self.indent -= 1

        # 离开函数体，递减嵌套深度
        self._func_depth = getattr(self, '_func_depth', 0) - 1

        # 恢复提升的指针声明集合（避免泄露到外层/嵌套函数）
        self._hoisted_pointer_names = old_hoisted
        self._hoisted_pointer_types = old_hoisted_types
        self._addr_taken = old_addr_taken

        # 恢复泛型参数集合
        self._generic_params = saved_generic_params

        # 恢复局部类型记录
        self._current_local_types = saved_local_types

        self._write("")

    def _collect_addr_names(self, stmts) -> set:
        """递归收集函数体内被 addr() 或 & 取地址的变量名（这些变量必须声明为 cdef）。
        遍历函数体内所有 AST 节点（含 LetStmt/Assign 的 RHS），不进入嵌套函数/类作用域。"""
        names = set()

        def _scan(node):
            if node is None:
                return
            if isinstance(node, list):
                for item in node:
                    _scan(item)
                return
            if not hasattr(node, '__dict__'):
                return
            kind = getattr(node, 'kind', None)
            # 不进入嵌套函数/类（它们有独立作用域）
            if kind in ('FuncDef', 'ClassDef', 'StructDef', 'TypeClassDef', 'TraitDef'):
                return
            # addr(x) -> 收集 x
            if isinstance(node, Call) and getattr(getattr(node, 'func', None), 'id', None) == 'addr' \
                    and getattr(node, 'args', None):
                arg0 = node.args[0]
                if isinstance(arg0, tuple):
                    arg0 = arg0[1]
                if isinstance(arg0, Name):
                    names.add(arg0.id)
                elif isinstance(arg0, str):
                    names.add(arg0)
            # &(x) -> 收集 x
            if isinstance(node, UnaryOp) and getattr(node, 'op', None) == '&':
                operand = getattr(node, 'operand', None)
                if isinstance(operand, Name):
                    names.add(operand.id)
                elif isinstance(operand, str):
                    names.add(operand)
            # 递归进入所有子节点
            for attr, value in node.__dict__.items():
                if attr.startswith('_'):
                    continue
                _scan(value)

        for s in (stmts or []):
            _scan(s)
        return names
        for s in (stmts or []):
            if s is None:
                continue
            kind = getattr(s, 'kind', None)
            # 不进入嵌套函数/类（它们有自己的作用域）
            if kind in ('FuncDef', 'ClassDef', 'StructDef', 'TypeClassDef', 'TraitDef'):
                continue
            # addr(x) -> 收集 x
            if kind == 'ExprStmt':
                val = getattr(s, 'value', None)
                if isinstance(val, Call) and getattr(getattr(val, 'func', None), 'id', None) == 'addr' \
                        and getattr(val, 'args', None):
                    arg0 = val.args[0]
                    if isinstance(arg0, tuple):
                        arg0 = arg0[1]
                    if isinstance(arg0, Name):
                        names.add(arg0.id)
                    elif isinstance(arg0, str):
                        names.add(arg0)
                # &(x) -> 收集 x
                if isinstance(val, UnaryOp) and getattr(val, 'op', None) == '&':
                    operand = getattr(val, 'operand', None)
                    if isinstance(operand, Name):
                        names.add(operand.id)
                    elif isinstance(operand, str):
                        names.add(operand)
            # 递归进入可包含语句的块
            nested = []
            if kind == 'MatchStmt':
                for c in getattr(s, 'cases', []) or []:
                    nested.append(getattr(c, 'body', None))
            elif kind == 'IfStmt':
                nested.append(getattr(s, 'body', None))
                nested.append(getattr(s, 'orelse', None))
            elif kind == 'ForStmt':
                nested.append(getattr(s, 'body', None))
            elif kind == 'WhileStmt':
                nested.append(getattr(s, 'body', None))
            elif kind == 'TryStmt':
                nested.append(getattr(s, 'body', None))
                for h in getattr(s, 'handlers', []) or []:
                    nested.append(getattr(h, 'body', None))
                nested.append(getattr(s, 'finalbody', None))
            elif kind == 'WithStmt':
                nested.append(getattr(s, 'body', None))
            for sub in nested:
                names |= self._collect_addr_names(sub)
        return names

    def _collect_pointer_decls(self, stmts, seen=None):
        """收集函数体内所有指针 let 声明（name, base_type），不包含嵌套函数/类作用域。"""
        if seen is None:
            seen = set()
        decls = []
        for s in (stmts or []):
            if s is None:
                continue
            kind = getattr(s, 'kind', None)
            # 不进入嵌套函数/类（它们有自己的作用域）
            if kind in ('FuncDef', 'ClassDef', 'StructDef', 'TypeClassDef', 'TraitDef'):
                continue
            if kind == 'LetStmt' and isinstance(getattr(s, 'type_annotation', None), PointerType) and isinstance(s.name, str):
                if s.name not in seen:
                    seen.add(s.name)
                    decls.append((s.name, self._type_to_str(s.type_annotation.base_type)))
            # 递归进入可包含语句的块
            nested = []
            if kind == 'MatchStmt':
                for c in getattr(s, 'cases', []) or []:
                    nested.append(getattr(c, 'body', []) or [])
                    nested.append(getattr(c, 'orelse', []) or [])
            else:
                for attr in ('body', 'orelse', 'finalbody'):
                    x = getattr(s, attr, None)
                    if isinstance(x, list):
                        nested.append(x)
            for sub in nested:
                decls.extend(self._collect_pointer_decls(sub, seen))
        return decls

    def _visit_LetStmt(self, node: LetStmt) -> None:
        is_const = getattr(node, 'is_const', False)
        is_owned = getattr(node, 'is_owned', False)
        
        # 检查是否是解构绑定（name 不是字符串）
        is_pattern = not isinstance(node.name, str)
        
        # 指针声明：若已被提升到函数开头，这里只做普通赋值（或声明但不带 cdef）
        is_hoisted_pointer = (isinstance(node.type_annotation, PointerType)
                              and node.name in getattr(self, '_hoisted_pointer_names', set()))
        if is_hoisted_pointer:
            if node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                # malloc 返回 void*，赋值给已提升的指针变量时需转换到目标基类型
                if isinstance(node.value, Call) and getattr(getattr(node.value, 'func', None), 'id', None) == 'malloc':
                    base = getattr(self, '_hoisted_pointer_types', {}).get(node.name)
                    if base:
                        value = value.replace('<void*>', f'<{base}*>', 1)
                self._write(f"{node.name} = {value}")
            # 无初始值时已在函数开头用 cdef 声明，这里无需再写
            return
        # 仅当变量名为普通字符串时才查询待处理记录；
        # 解构绑定（let (a, b) = ...）的 name 是模式列表，不能作为 dict 键
        _name_is_str = isinstance(node.name, str)
        needs_implicit_copy = _name_is_str and self._pending_copies.get(node.name) is not None
        needs_implicit_conversion = _name_is_str and self._pending_conversions.get(node.name) is not None
        
        if is_const:
            # 解构绑定不支持 const
            if is_pattern:
                self._write(f"# Warning: const with destructuring not supported")
            if node.type_annotation:
                cdef_type = self._sanitize_type(self._type_to_str(node.type_annotation))
                if isinstance(node.type_annotation, PointerType):
                    # 指针变量必须用 cdef 声明：cdef int * p
                    base = self._type_to_str(node.type_annotation.base_type)
                    self._hoisted_pointer_types[node.name] = base
                    if node.value:
                        value = self._expr_to_str(node.value)
                        if needs_implicit_conversion:
                            value = self._generate_implicit_conversion(node, value)
                        self._write(f"cdef {base} * {node.name} = {value}")
                    else:
                        self._write(f"cdef {base} * {node.name}")
                elif node.value:
                    value = self._expr_to_str(node.value)
                    # 如果需要隐式转换，添加转换代码
                    if needs_implicit_conversion:
                        value = self._generate_implicit_conversion(node, value)
                    # 被 addr()/& 取地址的变量必须声明为 cdef 才能取址
                    if node.name in getattr(self, '_addr_taken', set()):
                        self._write(f"cdef {cdef_type} {node.name} = {value}")
                    else:
                        self._write(f"{node.name}: {cdef_type} = {value}")
                else:
                    if node.name in getattr(self, '_addr_taken', set()):
                        self._write(f"cdef {cdef_type} {node.name}")
                    else:
                        self._write(f"{node.name}: {cdef_type}")
            else:
                if node.value:
                    value = self._expr_to_str(node.value)
                    self._write(f"{node.name} = {value}")
                else:
                    self._write(f"{node.name} = None")
            return
        
        if is_owned:
            # 解构绑定不支持 owned
            if is_pattern:
                self._write(f"# Warning: owned with destructuring not supported")
            self._ensure_owned_import()
            
            if node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                self._write(f"{node.name} = own({value})")
            else:
                self._write(f"{node.name} = None")
            return
        
        # 处理解构绑定
        if is_pattern:
            if node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                pattern_str = self._pattern_to_str(node.name)
                self._write(f"{pattern_str} = {value}")
            return
        
        if self.indent == 0:
            if node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                # 如果需要隐式复制，生成 __implicit_copy__ 调用
                if needs_implicit_copy:
                    value = f"{self._pending_copies[node.name]}.__implicit_copy__()"
                # 如果需要隐式转换，生成转换代码
                elif needs_implicit_conversion:
                    value = self._generate_implicit_conversion(node, value)
                self._write(f"{node.name} = {value}")
            else:
                self._write(f"{node.name} = None")
        elif node.type_annotation:
            cdef_type = self._sanitize_type(self._type_to_str(node.type_annotation))
            if isinstance(node.type_annotation, PointerType):
                base = self._type_to_str(node.type_annotation.base_type)
                if node.value:
                    if isinstance(node.value, ComptimeStmt):
                        value = self._expr_to_str(node.value.expr)
                    else:
                        value = self._expr_to_str(node.value)
                    # malloc 返回 void*，赋值给指针变量时需转换到目标基类型
                    if isinstance(node.value, Call) and getattr(getattr(node.value, 'func', None), 'id', None) == 'malloc':
                        value = value.replace('<void*>', f'<{base}*>', 1)
                    if needs_implicit_conversion:
                        value = self._generate_implicit_conversion(node, value)
                    self._write(f"cdef {base} * {node.name} = {value}")
                else:
                    self._write(f"cdef {base} * {node.name}")
            elif node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                # 如果需要隐式转换，生成转换代码
                if needs_implicit_conversion:
                    value = self._generate_implicit_conversion(node, value)
                # 被 addr()/& 取地址的变量必须声明为 cdef 才能取址
                if node.name in getattr(self, '_addr_taken', set()):
                    self._write(f"cdef {cdef_type} {node.name} = {value}")
                else:
                    self._write(f"{node.name}: {cdef_type} = {value}")
            else:
                if node.name in getattr(self, '_addr_taken', set()):
                    self._write(f"cdef {cdef_type} {node.name}")
                else:
                    self._write(f"{node.name}: {cdef_type}")
        else:
            if node.value:
                if isinstance(node.value, ComptimeStmt):
                    value = self._expr_to_str(node.value.expr)
                else:
                    value = self._expr_to_str(node.value)
                # 如果需要隐式复制，生成 __implicit_copy__ 调用
                if needs_implicit_copy:
                    value = f"{self._pending_copies[node.name]}.__implicit_copy__()"
                # 如果需要隐式转换，生成转换代码
                elif needs_implicit_conversion:
                    value = self._generate_implicit_conversion(node, value)
                self._write(f"{node.name} = {value}")
            else:
                self._write(f"{node.name}")
        
        # 清理待处理记录（解构绑定的 name 非字符串，跳过）
        if _name_is_str:
            if node.name in self._pending_copies:
                del self._pending_copies[node.name]
            if node.name in self._pending_conversions:
                del self._pending_conversions[node.name]

    def _ensure_owned_import(self) -> None:
        """确保导入所有权相关的函数"""
        if 'from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed' not in self.output:
            self.output.insert(0, 'from cypy_bridge.pointer import own, transfer_ownership, borrow, Owned, Borrowed')

    def _generate_implicit_conversion(self, node: Any, value_expr: str) -> str:
        """生成隐式转换代码，调用 __implicit_into__ 或守卫策略"""
        conversion_info = self._pending_conversions.get(node.name)
        if not conversion_info:
            return value_expr
        
        source_type, target_type = conversion_info
        
        # 检查源类型是否有 __implicit_into__ 方法
        if source_type in self.magic_methods:
            magic_map = self.magic_methods[source_type]
            if '__implicit_into__' in magic_map:
                # 生成 __implicit_into__ 调用
                return f"{value_expr}.__implicit_into__()"
            
            if '__guarded_action__' in magic_map:
                # 生成守卫策略调用
                return f"{value_expr}.__guarded_action__()"
        
        # 如果没有找到魔法方法，返回原始表达式
        return value_expr

    def register_magic_methods(self, magic_methods: Dict[str, Dict[str, Any]]) -> None:
        """注册魔法方法信息到代码生成器"""
        self.magic_methods = magic_methods

    def register_pending_operations(self, pending_copies: Dict[str, str], pending_conversions: Dict[str, tuple]) -> None:
        """注册待处理的隐式操作"""
        self._pending_copies = pending_copies
        self._pending_conversions = pending_conversions

    def _visit_ExprStmt(self, node: Any) -> None:
        """表达式语句：解包内部节点并写出（使用 _visit 以正确分发语句型节点）"""
        inner = getattr(node, 'value', None)
        if inner is not None:
            self._visit(inner)
        elif getattr(node, 'value', None) is not None:
            self._visit(node.value)

    def _visit_PassStmt(self, node: Any) -> None:
        """pass 语句"""
        self._write("pass")

    def _visit_ReturnStmt(self, node: ReturnStmt) -> None:
        if node.value:
            self._write(f"return {self._expr_to_str(node.value)}")
        else:
            self._write("return")

    def _visit_IfStmt(self, node: IfStmt) -> None:
        self._write(f"if {self._expr_to_str(node.test)}:")
        self.indent += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent -= 1
        if node.orelse:
            self._write("else:")
            self.indent += 1
            for stmt in node.orelse:
                self._visit(stmt)
            self.indent -= 1

    def _visit_ForStmt(self, node: ForStmt) -> None:
        self._write(f"for {self._expr_to_str(node.target)} in {self._expr_to_str(node.iter)}:")
        self.indent += 1
        self._loop_depth += 1  # 进入循环
        for stmt in node.body:
            self._visit(stmt)
        self._loop_depth -= 1  # 退出循环
        self.indent -= 1

    def _visit_WhileStmt(self, node: WhileStmt) -> None:
        self._write(f"while {self._expr_to_str(node.test)}:")
        self.indent += 1
        self._loop_depth += 1  # 进入循环
        for stmt in node.body:
            self._visit(stmt)
        self._loop_depth -= 1  # 退出循环
        self.indent -= 1

    def _visit_BreakStmt(self, node: Any) -> None:
        self._write("break")

    def _visit_ContinueStmt(self, node: Any) -> None:
        self._write("continue")

    def _visit_GlobalStmt(self, node: GlobalStmt) -> None:
        self._write(f"global {', '.join(node.names)}")

    def _visit_NonlocalStmt(self, node: NonlocalStmt) -> None:
        self._write(f"nonlocal {', '.join(node.names)}")

    def _visit_MatchStmt(self, node: Any) -> None:
        """生成 match/case 语句的 Cython 代码（编译为 if/elif 链，Cython 不支持原生 match）"""
        subject_str = self._expr_to_str(node.subject)
        self._match_counter = getattr(self, '_match_counter', 0) + 1
        subject_var = f"_match_subject_{self._match_counter}"

        self._write(f"{subject_var} = {subject_str}")
        # 先为每个 case 计算匹配信息；提取器模式会产生 pre 临时变量赋值。
        # 注意：这些 pre 必须放在 if/elif 链之前，因为 Python/Cython 不允许
        # 在 if/elif 分支之间插入语句（否则后续 elif 会变成语法错误）。
        all_pre = []
        cases_info = []
        for case in node.cases:
            cond, bindings, submap, pre = self._pattern_match_info(subject_var, case.pattern)
            all_pre.extend(pre)
            cases_info.append((cond, bindings, case.body))
        for ps in all_pre:
            self._write(ps)
        for i, (cond, bindings, body) in enumerate(cases_info):
            if i == 0:
                self._write(f"if {cond}:")
            else:
                self._write(f"elif {cond}:")
            self.indent += 1
            for b in bindings:
                self._write(b)
            for stmt in body:
                self._visit(stmt)
            self.indent -= 1

        if node.orelse:
            self._write("else:")
            self.indent += 1
            for stmt in node.orelse:
                self._visit(stmt)
            self.indent -= 1

    def _pattern_match_info(self, subject_var: str, pattern: Any):
        """返回 (condition_str, [binding_stmts], {name: access_expr}, [pre_stmts])
        供 match 分支使用。pre_stmts 为分支条件求值前需执行的临时变量赋值。"""
        def _merge(c, b, s, p):
            return c, list(b), dict(s), list(p)
        if isinstance(pattern, dict):
            if 'condition' in pattern:
                inner_cond, inner_bind, inner_sub, inner_pre = self._pattern_match_info(subject_var, pattern['pattern'])
                guard = self._substitute_names(self._expr_to_str(pattern['condition']), inner_sub)
                return (f"({inner_cond}) and ({guard})", inner_bind, inner_sub, inner_pre)
            if 'or' in pattern:
                conds, binds, subs, pres = [], [], {}, []
                for p in pattern['or']:
                    c, b, s, pr = self._pattern_match_info(subject_var, p)
                    conds.append(c)
                    binds.extend(b)
                    subs.update(s)
                    pres.extend(pr)
                return ("(" + " or ".join(conds) + ")", binds, subs, pres)
        if isinstance(pattern, RangePattern):
            lower = self._expr_to_str(pattern.lower)
            upper = self._expr_to_str(pattern.upper)
            return (f"{lower} <= {subject_var} < {upper}", [], {}, [])
        if isinstance(pattern, TypePattern):
            cond = f"isinstance({subject_var}, {pattern.type_name})"
            if pattern.name and pattern.name != '_':
                return (cond, [f"{pattern.name} = {subject_var}"], {pattern.name: subject_var}, [])
            return (cond, [], {}, [])
        if hasattr(pattern, 'kind') and pattern.kind == "Pattern":
            if pattern.name == '_' or pattern.name is None:
                return ("True", [], {}, [])
            if pattern.name in ('None', 'True', 'False', 'Ellipsis'):
                literal = {'None': 'None', 'True': 'True', 'False': 'False', 'Ellipsis': 'Ellipsis'}[pattern.name]
                return (f"{subject_var} == {literal}", [], {}, [])
            return ("True", [f"{pattern.name} = {subject_var}"], {pattern.name: subject_var}, [])
        if isinstance(pattern, Constant):
            return (f"{subject_var} == {repr(pattern.value)}", [], {}, [])
        if isinstance(pattern, list):
            conds = [f"isinstance({subject_var}, tuple)", f"len({subject_var}) == {len(pattern)}"]
            binds, subs, pres = [], {}, []
            for i, e in enumerate(pattern):
                ec, eb, es, ep = self._pattern_match_info(f"{subject_var}[{i}]", e)
                conds.append(ec)
                binds.extend(eb)
                subs.update(es)
                pres.extend(ep)
            return (" and ".join(conds), binds, subs, pres)
        if isinstance(pattern, ArrayPattern):
            has_star = any(getattr(e, 'kind', None) == 'SlicePattern' for e in pattern.elements)
            if not has_star:
                conds = [f"isinstance({subject_var}, (list, tuple))", f"len({subject_var}) == {len(pattern.elements)}"]
                binds, subs, pres = [], {}, []
                for i, e in enumerate(pattern.elements):
                    ec, eb, es, ep = self._pattern_match_info(f"{subject_var}[{i}]", e)
                    conds.append(ec)
                    binds.extend(eb)
                    subs.update(es)
                    pres.extend(ep)
                return (" and ".join(conds), binds, subs, pres)
            # 含 *rest（SlicePattern）的序列模式
            star_idx = next(i for i, e in enumerate(pattern.elements)
                            if getattr(e, 'kind', None) == 'SlicePattern')
            num_after = len(pattern.elements) - star_idx - 1
            conds = [f"isinstance({subject_var}, (list, tuple))",
                     f"len({subject_var}) >= {len(pattern.elements) - 1}"]
            binds, subs, pres = [], {}, []
            for i, e in enumerate(pattern.elements):
                if getattr(e, 'kind', None) == 'SlicePattern':
                    if e.name:
                        if num_after > 0:
                            slice_expr = f"{subject_var}[{i}:len({subject_var})-{num_after}]"
                        else:
                            slice_expr = f"{subject_var}[{i}:]"
                        binds.append(f"{e.name} = {slice_expr}")
                        subs[e.name] = slice_expr
                else:
                    if i > star_idx:
                        pos = f"len({subject_var}) - {num_after} + {i - star_idx - 1}"
                        sub_expr = f"{subject_var}[{pos}]"
                    else:
                        sub_expr = f"{subject_var}[{i}]"
                    ec, eb, es, ep = self._pattern_match_info(sub_expr, e)
                    conds.append(ec)
                    binds.extend(eb)
                    subs.update(es)
                    pres.extend(ep)
            return (" and ".join(conds), binds, subs, pres)
        if hasattr(pattern, 'kind') and pattern.kind == "StructPattern":
            conds = [f"isinstance({subject_var}, {pattern.struct_name})"]
            binds, subs, pres = [], {}, []
            for field_name, field_pattern in pattern.fields:
                fc, fb, fs, fp = self._pattern_match_info(f"{subject_var}.{field_name}", field_pattern)
                conds.append(fc)
                binds.extend(fb)
                subs.update(fs)
                pres.extend(fp)
            return (" and ".join(conds), binds, subs, pres)
        if isinstance(pattern, AsPattern):
            inner_cond, inner_bind, inner_sub, inner_pre = self._pattern_match_info(subject_var, pattern.pattern)
            binds = list(inner_bind)
            subs = dict(inner_sub)
            pres = list(inner_pre)
            if pattern.name and pattern.name != '_':
                binds.append(f"{pattern.name} = {subject_var}")
                subs[pattern.name] = subject_var
            return (inner_cond, binds, subs, pres)
        if isinstance(pattern, ExtractorPattern):
            return self._extractor_match_info(subject_var, pattern)
        if isinstance(pattern, DictPattern):
            conds = [f"isinstance({subject_var}, dict)"]
            binds, subs, pres = [], {}, []
            keys = []
            for key_pat, val_pat in pattern.pairs:
                key_repr = self._expr_to_str(key_pat)
                keys.append(key_repr)
                conds.append(f"{key_repr} in {subject_var}")
                vc, vb, vs, vp = self._pattern_match_info(f"{subject_var}[{key_repr}]", val_pat)
                binds.extend(vb)
                subs.update(vs)
                pres.extend(vp)
                if vc != "True":
                    conds.append(f"({vc})")
            if pattern.rest_name:
                rest_expr = f"{{k: v for k, v in {subject_var}.items() if k not in ({', '.join(keys)})}}"
                binds.append(f"{pattern.rest_name} = {rest_expr}")
                subs[pattern.rest_name] = rest_expr
            return (" and ".join(conds), binds, subs, pres)
        if isinstance(pattern, Attribute):
            # 命名常量 / 属性模式（如 case Color.Red:）：等价于等值比较
            attr_str = self._expr_to_str(pattern)
            return (f"{subject_var} == {attr_str}", [], {}, [])
        return ("True", [], {}, [])

    def _extractor_match_info(self, subject_var: str, pattern: Any):
        """为提取器模式生成条件与绑定。
        - 若该类型是注册过的提取器（定义了 __unapply__ 等），按解包逻辑处理（支持嵌套）。
        - 否则视为类模式（class pattern）：仅做 isinstance 检查，并将各参数名绑定到对应属性。
        """
        type_name = getattr(pattern, 'type_name', None)
        if type_name not in self._extractor_types:
            # 类/结构体模式：按字段顺序检查各位置参数（常量比较 / 捕获绑定）
            fields = self._class_fields.get(type_name, [])
            conds = []
            if type_name not in self._struct_types:
                conds.append(f"isinstance({subject_var}, {type_name})")
            binds, subs = [], {}
            for i, arg in enumerate(pattern.args):
                field_name = fields[i] if i < len(fields) else f"__f{i}"
                if isinstance(arg, Constant):
                    conds.append(f"{subject_var}.{field_name} == {repr(arg.value)}")
                elif hasattr(arg, 'kind') and arg.kind == "Pattern":
                    if arg.name not in ('_', None):
                        binds.append(f"{arg.name} = {subject_var}.{field_name}")
                        subs[arg.name] = f"{subject_var}.{field_name}"
                else:
                    # 嵌套模式：递归检查
                    ec, eb, es, ep = self._pattern_match_info(f"{subject_var}.{field_name}", arg)
                    conds.append(ec)
                    binds.extend(eb)
                    subs.update(es)
            if not conds:
                conds = ["True"]
            return (" and ".join(conds), binds, subs, [])
        # 提取器模式：通过 __unapply__ 等解包
        self._extractor_counter = getattr(self, '_extractor_counter', 0) + 1
        tmp = f"_ext_{self._extractor_counter}"
        # 单行条件表达式选择解包方法（避免嵌套块导致缩进错位），分支短路求值
        pre = [f"{tmp} = ({subject_var}.__unapply__() if hasattr({subject_var}, '__unapply__') else "
               f"({subject_var}.__unapply_seq__() if hasattr({subject_var}, '__unapply_seq__') else "
               f"({subject_var}.__unwarp__() if hasattr({subject_var}, '__unwarp__') else "
               f"(type({subject_var}).__match_args__({subject_var}) if hasattr(type({subject_var}), '__match_args__') else None))))"]
        conds = [f"{tmp} is not None"]
        binds, subs = [], {}
        for i, arg in enumerate(pattern.args):
            val_var = f"{tmp}_a{i}"
            pre.append(f"{val_var} = ({tmp}[{i}] if isinstance({tmp}, (list, tuple)) else {tmp})")
            ac, ab, as_, apre = self._pattern_match_info(val_var, arg)
            pre.extend(apre)
            conds.append(ac)
            binds.extend(ab)
            subs.update(as_)
        cond = "(" + ") and (".join(conds) + ")" if len(conds) > 1 else conds[0]
        return (cond, binds, subs, pre)

    def _substitute_names(self, expr: str, submap: Dict[str, str]) -> str:
        """将表达式中的捕获变量名替换为其访问表达式（用于 guard 条件求值）"""
        if not submap:
            return expr
        for name in sorted(submap, key=len, reverse=True):
            expr = re.sub(r'\b' + re.escape(name) + r'\b', submap[name], expr)
        return expr
    
    def _assign_to_walrus(self, stmt: str):
        """将 'a = b' 形式的赋值语句转换为 walrus 表达式 '(a := b)'，用于注入到 lambda 中。"""
        s = stmt.strip()
        m = re.match(r'^([A-Za-z_]\w*)\s*=\s*(.+)$', s)
        if m:
            return f"({m.group(1)} := {m.group(2)})"
        return f"({s})"

    def _visit_MatchExpr(self, node: Any) -> str:
        """生成 match/case 表达式的 Cython 代码（返回值形式）
        通过 lambda + 三元链实现；提取器/嵌套模式的绑定（pre/binds）以 walrus 形式注入，
        并在 lambda 开头一次性求值所有提取器的解包 pre，使各分支的条件与绑定均可引用。"""
        subject_str = self._expr_to_str(node.subject)
        subject_var = f"_match_subject"

        # 收集所有 case 的 pre（提取器解包），在 lambda 开头一次性求值，供各分支条件/绑定引用
        all_pre = []
        for case in node.cases:
            _, _, _, pre = self._pattern_match_info(subject_var, case.pattern)
            all_pre.extend(pre or [])
        seen = set()
        all_pre_unique = []
        for p in all_pre:
            if p not in seen:
                seen.add(p)
                all_pre_unique.append(p)

        parts = [f"(lambda {subject_var}: ("]
        if all_pre_unique:
            pre_walruses = [self._assign_to_walrus(p) for p in all_pre_unique]
            parts.append("(" + ", ".join(pre_walruses) + "), ")

        n = len(node.cases)
        for i, case in enumerate(node.cases):
            body_expr = self._expr_to_str(case.body[0]) if case.body else "None"
            cond, binds, subs, pre = self._pattern_match_info(subject_var, case.pattern)
            # 将本分支的绑定以 walrus 注入到分支体（在条件满足后求值）
            walruses = [self._assign_to_walrus(b) for b in (binds or [])]
            if walruses:
                body_expr = "(" + ", ".join(walruses + [body_expr]) + ")[-1]"
            if i < n - 1:
                parts.append(f"{body_expr} if {cond} else ")
            else:
                parts.append(f"{body_expr}")
        parts.append(f")[-1])({subject_str})")
        return "".join(parts)
    
    def _pattern_to_condition(self, subject_var: str, pattern: Any) -> str:
        """将普通模式转换为条件表达式（用于 match 表达式）"""
        if isinstance(pattern, RangePattern):
            lower = self._expr_to_str(pattern.lower)
            upper = self._expr_to_str(pattern.upper)
            return f"{lower} <= {subject_var} < {upper}"
        if isinstance(pattern, dict):
            if 'condition' in pattern:
                inner_cond = self._pattern_to_condition(subject_var, pattern['pattern'])
                guard_cond = self._expr_to_str(pattern['condition'])
                return f"({inner_cond}) and ({guard_cond})"
            if 'or' in pattern:
                conds = [self._pattern_to_condition(subject_var, p) for p in pattern['or']]
                return "(" + " or ".join(conds) + ")"
        if hasattr(pattern, 'kind') and pattern.kind == "Constant":
            return f"{subject_var} == {repr(pattern.value)}"
        if hasattr(pattern, 'kind') and pattern.kind == "Pattern":
            if pattern.name in ('None', 'True', 'False', 'Ellipsis'):
                literal = {'None': 'None', 'True': 'True', 'False': 'False', 'Ellipsis': 'Ellipsis'}[pattern.name]
                return f"{subject_var} == {literal}"
            return "True"
        return "True"
    
    def _contains_extractor(self, pattern: Any) -> bool:
        """检查模式是否包含 ExtractorPattern"""
        if isinstance(pattern, ExtractorPattern):
            return True
        if isinstance(pattern, dict):
            if 'pattern' in pattern:
                return self._contains_extractor(pattern['pattern'])
            if 'or' in pattern:
                return any(self._contains_extractor(p) for p in pattern['or'])
        if isinstance(pattern, list):
            return any(self._contains_extractor(p) for p in pattern)
        if isinstance(pattern, AsPattern):
            return self._contains_extractor(pattern.pattern)
        if isinstance(pattern, ArrayPattern):
            return any(self._contains_extractor(e) for e in pattern.elements)
        if hasattr(pattern, 'args'):
            return any(self._contains_extractor(a) for a in pattern.args)
        return False
    
    def _extractor_pattern_condition(self, subject_var: str, pattern: Any) -> str:
        """生成提取器模式的条件表达式，实现优先级调度"""
        if isinstance(pattern, ExtractorPattern):
            return self._generate_extractor_condition(subject_var, pattern)
        if isinstance(pattern, dict):
            if 'condition' in pattern:
                inner_cond = self._extractor_pattern_condition(subject_var, pattern['pattern'])
                guard_cond = self._expr_to_str(pattern['condition'])
                return f"({inner_cond}) and ({guard_cond})"
            if 'or' in pattern:
                conds = [self._extractor_pattern_condition(subject_var, p) for p in pattern['or']]
                return "(" + " or ".join(conds) + ")"
        if isinstance(pattern, list):
            # 元组模式
            return self._generate_tuple_condition(subject_var, pattern)
        if isinstance(pattern, AsPattern):
            inner_cond = self._extractor_pattern_condition(subject_var, pattern.pattern)
            return inner_cond
        if isinstance(pattern, ArrayPattern):
            return self._generate_array_condition(subject_var, pattern)
        if isinstance(pattern, DictPattern):
            return self._generate_dict_condition(subject_var, pattern)
        if isinstance(pattern, TypePattern):
            return f"isinstance({subject_var}, {pattern.type_name})"
        if hasattr(pattern, 'kind') and pattern.kind == "Pattern":
            return "True"
        if hasattr(pattern, 'kind') and pattern.kind == "Constant":
            return f"{subject_var} == {repr(pattern.value)}"
        return "True"
    
    def _generate_extractor_condition(self, subject_var: str, pattern: ExtractorPattern) -> str:
        """生成提取器模式的优先级调度条件
        
        优先级：__unapply__ → __unapply_seq__ → __unwarp__ → __match_args__
        """
        type_name = pattern.type_name
        arg_patterns = pattern.args

        # 若该类型不是注册过的提取器，则视为类模式
        if type_name not in self._extractor_types:
            # cdef struct 不能用 isinstance；此处（表达式上下文）无法绑定字段，直接判真
            if type_name in self._struct_types:
                return "True"
            return f"isinstance({subject_var}, {type_name})"

        # 生成变量绑定代码
        bind_code = []
        arg_names = []
        
        for i, arg_pattern in enumerate(arg_patterns):
            if hasattr(arg_pattern, 'kind') and arg_pattern.kind == "Pattern":
                arg_names.append(arg_pattern.name)
            elif hasattr(arg_pattern, 'kind') and arg_pattern.kind == "Constant":
                arg_names.append(f"_extracted_{i}")
            else:
                arg_names.append(f"_extracted_{i}")
        
        # 构建优先级调度逻辑
        conditions = []
        
        # 1. __unapply__ 优先级最高
        conditions.append(
            f"hasattr({subject_var}, '__unapply__') and "
            f"({subject_var}.__unapply__() is not None)"
        )
        
        # 2. __unapply_seq__
        conditions.append(
            f"hasattr({subject_var}, '__unapply_seq__') and "
            f"({subject_var}.__unapply_seq__() is not None)"
        )
        
        # 3. __unwarp__
        conditions.append(
            f"hasattr({subject_var}, '__unwarp__')"
        )
        
        # 4. __match_args__ (Python 原生)
        conditions.append(
            f"hasattr(type({subject_var}), '__match_args__')"
        )
        
        condition_str = " or ".join(conditions)
        
        # 生成完整的条件表达式（包含类型检查和提取逻辑）
        full_condition = f"isinstance({subject_var}, {type_name}) and ({condition_str})"
        
        return full_condition

    def _generate_tuple_condition(self, subject_var: str, pattern: list) -> str:
        """生成元组模式匹配条件"""
        conditions = []
        conditions.append(f"isinstance({subject_var}, tuple)")
        conditions.append(f"len({subject_var}) == {len(pattern)}")
        for i, elem_pattern in enumerate(pattern):
            elem_var = f"{subject_var}[{i}]"
            if hasattr(elem_pattern, 'kind') and elem_pattern.kind == "Pattern":
                conditions.append(f"isinstance({elem_var}, {elem_pattern.name})")
            elif hasattr(elem_pattern, 'kind') and elem_pattern.kind == "Constant":
                conditions.append(f"{elem_var} == {repr(elem_pattern.value)}")
            elif isinstance(elem_pattern, dict):
                inner_cond = self._extractor_pattern_condition(elem_var, elem_pattern)
                conditions.append(f"({inner_cond})")
        return " and ".join(conditions)

    def _generate_array_condition(self, subject_var: str, pattern: 'ArrayPattern') -> str:
        """生成数组/列表模式匹配条件"""
        conditions = []
        conditions.append(f"isinstance({subject_var}, (list, tuple))")
        conditions.append(f"len({subject_var}) >= {len(pattern.elements)}")
        for i, elem_pattern in enumerate(pattern.elements):
            elem_var = f"{subject_var}[{i}]"
            if hasattr(elem_pattern, 'kind') and elem_pattern.kind == "Pattern":
                conditions.append(f"isinstance({elem_var}, {elem_pattern.name})")
            elif hasattr(elem_pattern, 'kind') and elem_pattern.kind == "Constant":
                conditions.append(f"{elem_var} == {repr(elem_pattern.value)}")
            elif isinstance(elem_pattern, dict):
                inner_cond = self._extractor_pattern_condition(elem_var, elem_pattern)
                conditions.append(f"({inner_cond})")
        if pattern.rest_name:
            conditions.append(f"len({subject_var}) > {len(pattern.elements)}")
        return " and ".join(conditions)

    def _generate_dict_condition(self, subject_var: str, pattern: 'DictPattern') -> str:
        """生成字典模式匹配条件"""
        conditions = []
        conditions.append(f"isinstance({subject_var}, dict)")
        for key_pattern, value_pattern in pattern.pairs:
            if hasattr(key_pattern, 'value'):
                key_str = repr(key_pattern.value)
            else:
                key_str = str(key_pattern)
            value_var = f"{subject_var}.get({key_str})"
            conditions.append(f"{key_str} in {subject_var}")
            if hasattr(value_pattern, 'kind') and value_pattern.kind == "Pattern":
                conditions.append(f"isinstance({value_var}, {value_pattern.name})")
            elif hasattr(value_pattern, 'kind') and value_pattern.kind == "Constant":
                conditions.append(f"{value_var} == {repr(value_pattern.value)}")
            elif isinstance(value_pattern, dict):
                inner_cond = self._extractor_pattern_condition(value_var, value_pattern)
                conditions.append(f"({inner_cond})")
        if pattern.rest_name:
            conditions.append(f"len({subject_var}) > {len(pattern.pairs)}")
        return " and ".join(conditions)
    
    def _pattern_to_str(self, pattern: Any) -> str:
        """将模式转换为字符串表示"""
        if isinstance(pattern, dict):
            if "condition" in pattern:
                # 带条件的模式：pattern if condition
                inner_pattern = self._pattern_to_str(pattern["pattern"])
                condition = self._expr_to_str(pattern["condition"])
                return f"{inner_pattern} if {condition}"
            if "or" in pattern:
                # OR 模式：pattern1 | pattern2
                pattern_strs = []
                for p in pattern["or"]:
                    pattern_strs.append(self._pattern_to_str(p))
                return " | ".join(pattern_strs)
        if isinstance(pattern, list):
            # 元组模式：(pattern1, pattern2, ...)
            pattern_strs = []
            for p in pattern:
                pattern_strs.append(self._pattern_to_str(p))
            return f"({', '.join(pattern_strs)})"
        if isinstance(pattern, ArrayPattern):
            # 数组/列表模式：[pattern1, pattern2, ...]
            pattern_strs = []
            for p in pattern.elements:
                pattern_strs.append(self._pattern_to_str(p))
            # 添加 *rest 剩余绑定
            if pattern.rest_name:
                pattern_strs.append(f"*{pattern.rest_name}")
            return f"[{', '.join(pattern_strs)}]"
        if isinstance(pattern, SlicePattern):
            # 切片模式：.. 转换为 *_（忽略），..var 转换为 *var（绑定）
            if pattern.name is None:
                return "*_"
            return f"*{pattern.name}"
        if hasattr(pattern, 'kind') and pattern.kind == "Pattern":
            # 变量模式
            return pattern.name
        if hasattr(pattern, 'kind') and pattern.kind == "StructPattern":
            # 结构体解构模式：Point { x, y } 或 Point { x: px, y: py }
            # 生成 Python 的类模式语法：Point(x=x, y=y) 或 Point(x=px, y=py)
            field_parts = []
            for field_name, field_pattern in pattern.fields:
                field_parts.append(f"{field_name}={self._pattern_to_str(field_pattern)}")
            if pattern.has_ellipsis:
                field_parts.append("**_")
            return f"{pattern.struct_name}({', '.join(field_parts)})"
        if isinstance(pattern, TypePattern):
            # 类型模式：case int x: 转换为 case int() as x:
            return f"{pattern.type_name}() as {pattern.name}"
        if isinstance(pattern, AsPattern):
            # As模式：case pattern as name:
            inner_pattern = self._pattern_to_str(pattern.pattern)
            return f"{inner_pattern} as {pattern.name}"
        if isinstance(pattern, DictPattern):
            # 字典模式：{"key": value, "key2": value2, **rest}
            parts = []
            for key_pattern, value_pattern in pattern.pairs:
                key_str = self._pattern_to_str(key_pattern)
                value_str = self._pattern_to_str(value_pattern)
                parts.append(f"{key_str}: {value_str}")
            if pattern.rest_name:
                parts.append(f"**{pattern.rest_name}")
            return f"{{{', '.join(parts)}}}"
        if isinstance(pattern, ExtractorPattern):
            # 提取器模式：参考Scala的unapply，如 Email(user, domain)
            # 优先级：__match_args__ < __unapply__ < __unapply_seq__ < __unwarp__
            # 生成 Python 的类模式语法，运行时会自动查找 __unapply__ / __match_args__
            arg_strs = []
            for arg in pattern.args:
                arg_strs.append(self._pattern_to_str(arg))
            return f"{pattern.type_name}({', '.join(arg_strs)})"
        if isinstance(pattern, RangePattern):
            # 范围模式：case 1..10: 转换为 case _ if 1 <= _ < 10:
            lower = self._expr_to_str(pattern.lower)
            upper = self._expr_to_str(pattern.upper)
            return f"_ if {lower} <= _ < {upper}"
        # 默认使用表达式转换
        return self._expr_to_str(pattern)

    def _visit_WithStmt(self, node: Any) -> None:
        """生成 with 语句的 Cython 代码"""
        items_str = []
        for item in node.items:
            expr = self._expr_to_str(item[0])
            if item[1]:
                items_str.append(f"{expr} as {item[1].id}")
            else:
                items_str.append(expr)
        self._write(f"with {', '.join(items_str)}:")
        self.indent += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent -= 1

    def _visit_DelStmt(self, node: Any) -> None:
        """生成 del 语句的 Cython 代码"""
        targets_str = ", ".join(self._expr_to_str(target) for target in node.targets)
        self._write(f"del {targets_str}")

    def _visit_ExprStmt(self, node: Any) -> None:
        value = node.value
        # 语句型宏：展开后可能是多行代码（如 debug_log），需按行写出以保持缩进
        # 兼容两种形式：显式 MacroCall 节点，或 func 为已定义宏名的普通 Call
        if isinstance(value, MacroCall):
            expanded = self._expand_macro(value.name, value.args)
            for line in expanded.split("\n"):
                self._write(line)
            return
        if self._is_macro_call(value):
            expanded = self._expand_macro(value.func.id, value.args)
            for line in expanded.split("\n"):
                self._write(line)
            return
        self._write(self._expr_to_str(value))

    def _emit_build_block_assign(self, target, block) -> None:
        """将 =: 构建块转换为嵌套函数调用：块内语句作为函数体，最后表达式作为返回值。"""
        name = f"_bb_{self._bb_counter}"
        self._bb_counter += 1
        self._write(f"def {name}():")
        self.indent += 1
        stmts = block.body
        for i, stmt in enumerate(stmts):
            sk = getattr(stmt, 'kind', None)
            if i == len(stmts) - 1:
                if sk == 'ReturnStmt':
                    self._visit(stmt)
                elif sk == 'ExprStmt':
                    self._write(f"return {self._expr_to_str(getattr(stmt, 'value', None))}")
                else:
                    self._visit(stmt)
            else:
                self._visit(stmt)
        self.indent -= 1
        if target is not None:
            self._write(f"{self._expr_to_str(target)} = {name}()")
        else:
            self._write(f"{name}()")

    def _is_rest_subscript(self, elt):
        """判断元素是否为 rest[0] 形式的剩余元素收集（rest 变量绑定到尾部切片）
        在解析中表现为 Subscript(value=Name('rest'), slice=0) 或 DerefExpr(operand=Name('rest'))"""
        kind = getattr(elt, 'kind', None)
        if kind == 'Subscript':
            val = getattr(elt, 'value', None)
            if not isinstance(val, Name):
                return None
            sl = getattr(elt, 'slice', None)
            if isinstance(sl, int) and sl == 0:
                return val.id
            if isinstance(sl, Constant) and getattr(sl, 'value', None) == 0:
                return val.id
            return None
        if kind == 'DerefExpr':
            op = getattr(elt, 'operand', None)
            if isinstance(op, Name):
                return op.id
            if isinstance(op, str):
                return op
        return None

    def _emit_list_rest_unpack(self, elts, value, rest_idx) -> None:
        """将 [first, rest[0]] = expr 转换为 first = tmp[0]; rest = tmp[1:]"""
        tmp = f"_rest_tmp_{self._bb_counter}"
        self._bb_counter += 1
        self._write(f"{tmp} = {self._expr_to_str(value)}")
        for j, elt in enumerate(elts):
            r = self._is_rest_subscript(elt)
            if r is not None:
                # rest[0] 收集剩余元素（从当前位置到末尾）
                self._write(f"{r} = {tmp}[{j}:]")
            else:
                self._write(f"{self._expr_to_str(elt)} = {tmp}[{j}]")

    def _visit_Assign(self, node: Any) -> None:
        # =: 构建块：内联转换为嵌套函数，避免把块内赋值/控制流丢失
        if isinstance(node.value, BuildBlockExpr) and \
                getattr(node.value, 'block_type', None) == BuildBlockExpr.BUILD_ASSIGN:
            self._emit_build_block_assign(node.target, node.value)
            return
        # 列表解包含 rest[0] 剩余元素收集：[first, rest[0]] = expr
        # LHS 列表字面量在 parser 中表现为 Constant(value=[...]) 或带 .elements 的节点
        tgt = node.target
        tgt_elts = None
        if hasattr(tgt, 'elements'):
            tgt_elts = getattr(tgt, 'elements', None) or []
        elif getattr(tgt, 'kind', None) == 'Constant' and isinstance(getattr(tgt, 'value', None), list):
            tgt_elts = getattr(tgt, 'value', None)
        if tgt_elts is not None:
            rest_idx = None
            for i, elt in enumerate(tgt_elts):
                if self._is_rest_subscript(elt) is not None:
                    rest_idx = i
                    break
            if rest_idx is not None:
                self._emit_list_rest_unpack(tgt_elts, node.value, rest_idx)
                return
        target = self._expr_to_str(node.target)
        if isinstance(node.value, ComptimeStmt):
            # comptime 在编译时求值，结果作为常量
            value = self._expr_to_str(node.value.expr)
        else:
            value = self._expr_to_str(node.value)
        # malloc 返回 void*，赋值给已提升的指针变量时需转换到目标基类型
        if isinstance(node.value, Call) and getattr(getattr(node.value, 'func', None), 'id', None) == 'malloc':
            base = getattr(self, '_hoisted_pointer_types', {}).get(target)
            if base:
                value = value.replace('<void*>', f'<{base}*>', 1)
        self._write(f"{target} = {value}")

    def _visit_StructDef(self, node: StructDef) -> None:
        # 结构体泛型参数在签名中作为类型标识符时回退为 object
        saved_generic_params = set(self._generic_params)
        if node.generic_params:
            self._generic_params |= set(node.generic_params)

        # 结构体字段是否含有 Python 对象类型（str/list/dict/等），C 结构体不支持
        from cypyc.parser.parser import StructField
        primitives = {
            'int', 'float', 'double', 'long', 'short', 'char', 'bint',
            'longlong', 'unsigned int', 'unsigned long', 'unsigned char',
            'unsigned short', 'unsigned longlong', 'size_t', 'Py_ssize_t',
            'long double', 'signed char', 'uint8', 'uint16', 'uint32', 'uint64',
            'int8', 'int16', 'int32', 'int64', 'float32', 'float64',
        }
        def _has_object_field(n):
            for f in n.fields:
                if isinstance(f, StructField) and getattr(f, 'type_annotation', None):
                    t = self._sanitize_type(self._type_to_str(f.type_annotation))
                    base = t.split('[')[0].strip()
                    if base not in primitives:
                        return True
            return False

        # 检查是否有 @value 装饰器
        has_value_decorator = False
        if hasattr(node, 'decorators') and node.decorators:
            for decorator in node.decorators:
                decorator_name = getattr(decorator.name, 'id', str(decorator.name))
                if decorator_name == 'value':
                    has_value_decorator = True
                    break
        
        # 如果结构体有方法或 @value 装饰器，使用 cdef class
        # 若结构体包含 Python 对象类型字段（str/list/dict 等），C 结构体不支持，
        # 也需改用 cdef class（扩展类型）
        use_class = has_value_decorator or (hasattr(node, 'methods') and node.methods) \
            or _has_object_field(node)
        
        if use_class:
            # 设置当前结构体名称，用于方法生成时添加 self 参数
            self._current_struct_name = node.name
            self._write(f"cdef class {node.name}:")
            self.indent += 1
            
            # 添加 __slots__ 优化内存使用
            field_names = [f.name for f in node.fields if isinstance(f, StructField)]
            if field_names:
                slots_str = ", ".join(f'"{f}"' for f in field_names)
                # 单元素时必须是 ("x",) 而非 ("x")，否则会被当作字符串迭代
                if len(field_names) == 1:
                    slots_str += ","
                self._write(f"__slots__ = ({slots_str})")
            
            # 生成字段 - cdef class 需要 cdef 前缀，使用 public 使字段可从 Python 访问
            for field in node.fields:
                if isinstance(field, StructField):
                    field_type = self._type_to_str(field.type_annotation) if field.type_annotation else "object"
                    self._write(f"cdef public {field_type} {field.name}")
            
            # 生成参数化 __init__ 方法用于初始化字段
            init_params = []
            init_body = []
            for field in node.fields:
                if isinstance(field, StructField):
                    param_name = field.name
                    if field.default_value is not None:
                        init_params.append(f"{param_name}={self._expr_to_str(field.default_value)}")
                        init_body.append(f"self.{param_name} = {param_name}")
                    else:
                        init_params.append(param_name)
                        init_body.append(f"self.{param_name} = {param_name}")
            
            # 添加 @cython.final 装饰器用于优化
            self._write("@cython.final")
            self._write(f"def __init__(self{', ' + ', '.join(init_params) if init_params else ''}):")
            self.indent += 1
            for line in init_body:
                self._write(line)
            self.indent -= 1
            
            # 如果有 @value 装饰器，生成自动方法
            if has_value_decorator:
                self._generate_value_methods(node)
            
            # 生成方法 - 标记为结构体方法，并添加 @cython.binding(False) 优化
            for method in node.methods:
                method.is_struct_method = True
                # 在访问方法之前添加优化装饰器
                self._write("@cython.binding(False)")
                self._visit(method)
            
            self.indent -= 1
            # 清除当前结构体名称
            self._current_struct_name = None
        else:
            self._write(f"cdef struct {node.name}:")
            self.indent += 1
            # 生成字段 - cdef struct 字段不需要 cdef 前缀
            for field in node.fields:
                if isinstance(field, StructField):
                    field_type = self._type_to_str(field.type_annotation) if field.type_annotation else "object"
                    if field.default_value is not None:
                        self._write(f"{field_type} {field.name} = {self._expr_to_str(field.default_value)}")
                    else:
                        self._write(f"{field_type} {field.name}")
            self.indent -= 1
        self._generic_params = saved_generic_params
        self._write("")
    
    def _generate_value_methods(self, node: StructDef) -> None:
        """为 @value 装饰的结构体生成自动方法"""
        field_names = [f.name for f in node.fields if isinstance(f, StructField)]
        
        # 生成 __eq__ 方法
        if field_names:
            eq_conditions = " and ".join([f"self.{f} == other.{f}" for f in field_names])
            self._write("def __eq__(self, other):")
            self.indent += 1
            self._write(f"if isinstance(other, {node.name}):")
            self.indent += 1
            self._write(f"return {eq_conditions}")
            self.indent -= 1
            self._write("return False")
            self.indent -= 1
        
        # 生成 __hash__ 方法
        if field_names:
            hash_values = ", ".join([f"hash(self.{f})" for f in field_names])
            self._write(f"def __hash__(self):")
            self.indent += 1
            self._write(f"return hash(({hash_values},))")
            self.indent -= 1
        
        # 生成 __repr__ 方法
        if field_names:
            repr_parts = ", ".join([f"{f}={{self.{f}!r}}" for f in field_names])
            self._write(f"def __repr__(self):")
            self.indent += 1
            self._write(f"return f'{node.name}({repr_parts})'")
            self.indent -= 1
        
        # 生成 __copy__ 方法
        if field_names:
            copy_args = ", ".join([f"{f}=self.{f}" for f in field_names])
            self._write(f"def __copy__(self):")
            self.indent += 1
            self._write(f"return {node.name}({copy_args})")
            self.indent -= 1

    def _visit_StructField(self, node: StructField) -> None:
        """生成结构体字段的 Cython 代码"""
        field_type = self._type_to_str(node.type_annotation) if node.type_annotation else "object"
        if node.default_value is not None:
            self._write(f"{field_type} {node.name} = {self._expr_to_str(node.default_value)}")
        else:
            self._write(f"{field_type} {node.name}")

    def _visit_EnumDef(self, node: EnumDef) -> None:
        self._write("from enum import IntEnum, auto")
        self._write("")
        self._write(f"class {node.name}(IntEnum):")
        self.indent += 1
        for variant in node.variants:
            if isinstance(variant, EnumVariant):
                if variant.value is not None:
                    self._write(f"{variant.name} = {self._expr_to_str(variant.value)}")
                else:
                    self._write(f"{variant.name} = auto()")
        self.indent -= 1
        self._write("")

    def _visit_EnumVariant(self, node: EnumVariant) -> None:
        """生成枚举变体的 Cython 代码"""
        if node.value is not None:
            self._write(f"{node.name} = {self._expr_to_str(node.value)}")
        else:
            self._write(f"{node.name}")

    def _visit_Import(self, node: Any) -> None:
        if node.alias:
            self._write(f"import {node.module} as {node.alias}")
        else:
            self._write(f"import {node.module}")
    
    def _visit_FromImport(self, node: Any) -> None:
        names_str = ", ".join(node.names)
        self._write(f"from {node.module} import {names_str}")
    
    def _visit_GuardStmt(self, node: GuardStmt) -> None:
        """生成 guard 语句的 Cython 代码
        
        循环守卫：在循环中使用 guard 时，生成 break 而不是 return
        
        LZ 语义:
        - 循环中 guard 失败 -> break (退出循环)
        - 非循环中 guard 失败 -> return (返回值或默认值)
        """
        in_loop = self._loop_depth > 0
        
        if node.is_let:
            # guard let target = expr else value
            target = self._expr_to_str(node.let_target)
            value = self._expr_to_str(node.test)
            self._write(f"{target} = {value}")
            self._write(f"if not {target}:")
            self.indent += 1
            self._generate_guard_else_block(node.orelse, in_loop)
            self.indent -= 1
        else:
            # guard cond else value
            test = self._expr_to_str(node.test)
            self._write(f"if not ({test}):")
            self.indent += 1
            self._generate_guard_else_block(node.orelse, in_loop)
            self.indent -= 1

    def _generate_guard_else_block(self, orelse: Any, in_loop: bool) -> None:
        """生成 guard else 块的代码
        
        参数:
            orelse: guard 的 else 分支（可能是列表或单个表达式）
            in_loop: 是否在循环中（决定生成 break 还是 return）
        """
        if isinstance(orelse, list):
            # 多行形式：else: 块体。块内最后一条“表达式语句”为隐式返回值
            last = orelse[-1] if orelse else None
            has_terminal = last is not None and getattr(last, 'kind', None) in ('ReturnStmt', 'BreakStmt', 'ContinueStmt', 'RaiseStmt')
            if has_terminal:
                for stmt in orelse:
                    self._visit(stmt)
            else:
                # 执行 else 块中的所有语句（多行形式），再生成退出语句
                for stmt in orelse:
                    self._visit(stmt)
                if not has_terminal:
                    if in_loop:
                        self._write("# guard failed in loop - implicit break")
                        self._write("break")
                    else:
                        self._write("# guard failed - implicit return")
                        self._write("return")
        elif isinstance(orelse, BreakStmt):
            # else break: 直接生成 break
            self._write(f"break")
        elif isinstance(orelse, ContinueStmt):
            # else continue: 直接生成 continue
            self._write(f"continue")
        elif isinstance(orelse, ReturnStmt):
            # else return [value]: 直接生成 return
            if orelse.value is not None:
                self._write(f"return {self._expr_to_str(orelse.value)}")
            else:
                self._write(f"return")
        else:
            # 单行形式：else expr（普通表达式）
            if in_loop:
                # 循环中 break，不输出 else 表达式
                self._write(f"# guard failed in loop - implicit break")
                self._write(f"break")
            else:
                # 非循环中 return 表达式值
                self._write(f"return {self._expr_to_str(orelse)}")

    def _visit_ComptimeStmt(self, node: ComptimeStmt) -> None:
        """生成 comptime 语句的 Cython 代码
        
        在编译期求值表达式，将结果替换为常量
        """
        from cypyc.analyzer.comptime_evaluator import evaluate_comptime
        
        # 尝试编译期求值
        result = evaluate_comptime(node.expr)
        
        if result is not None:
            # 求值成功，生成常量代码
            # 根据结果类型生成相应的代码
            if isinstance(result, str):
                self._write(f'"{result}"')
            elif isinstance(result, bool):
                self._write("True" if result else "False")
            elif isinstance(result, (int, float)):
                self._write(str(result))
            else:
                # 其他类型，使用 repr
                self._write(repr(result))
        else:
            # 求值失败，保留原表达式作为注释
            self._write(f"# comptime: {self._expr_to_str(node.expr)}")

    def _visit_ComptimeFuncDef(self, node: ComptimeFuncDef) -> None:
        """生成编译期函数的 Cython 代码
        
        编译期函数只在编译期执行，不生成运行时代码。
        但需要在代码生成阶段注册函数到求值器，以便后续 comptime 表达式可以调用。
        """
        # 编译期函数不生成运行时代码
        # 但我们需要注册它以便其他 comptime 表达式可以调用
        from cypyc.analyzer.comptime_evaluator import evaluate_comptime, register_comptime_functions
        from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator
        
        # 创建求值器并注册编译期函数
        evaluator = ComptimeEvaluator()
        evaluator.register_function(node)
        
        # 在代码中添加注释说明这是一个编译期函数
        self._write(f"# comptime def {node.name}(): (compiled at compile time)")

    def _visit_BuildBlockExpr(self, node: BuildBlockExpr) -> None:
        """生成构建块表达式的 Cython/Python 代码
        
        构建块将多条语句组合成一个表达式，返回最后一个表达式的值。
        
        LZ 语法:
        - =: 变量构建块: 无参闭包，块体末尾表达式作为返回值
        - ~: 调用构建块: 带参闭包，块体末尾返回元组/字典，自动拆包
        - ^: 索引构建块: 已在解析器中转换为 Subscript，此处不处理
        - *: 生成器构建块: 生成器闭包
        """
        if node.block_type == BuildBlockExpr.BUILD_ASSIGN:
            # =: 变量构建块
            # 单表达式: 直接返回值
            # 多语句: IIFE 模式 (lambda: (...)[-1])()
            expr_parts = []
            has_complex = False
            for stmt in node.body:
                stmt_kind = getattr(stmt, 'kind', None)
                if stmt_kind == 'LetStmt':
                    has_complex = True
                elif stmt_kind == 'ReturnStmt':
                    if hasattr(stmt, 'value') and stmt.value:
                        expr_parts.append(self._expr_to_str(stmt.value))
                elif stmt_kind == 'ExprStmt':
                    # 表达式语句: 提取内部表达式
                    inner = getattr(stmt, 'value', None)
                    if inner is not None:
                        expr_parts.append(self._expr_to_str(inner))
                    else:
                        has_complex = True
                elif isinstance(stmt, (BinOp, UnaryOp, Call, Name, Constant)):
                    expr_parts.append(self._expr_to_str(stmt))
                else:
                    has_complex = True
                    expr_str = self._stmt_to_expr(stmt)
                    if expr_str:
                        expr_parts.append(expr_str)
            
            # =: 构建块统一转换为嵌套函数调用，保证块内赋值/控制流不丢失
            self._emit_build_block_assign(None, node)
            
        elif node.block_type == BuildBlockExpr.BUILD_CALL:
            # ~: 调用构建块
            # 单表达式: 直接传递值 (无 lambda 包装)
            # 多语句: 生成 lambda 惰性求值
            expr_strs = []
            has_complex = False
            for stmt in node.body:
                stmt_kind = getattr(stmt, 'kind', None)
                if stmt_kind == 'LetStmt':
                    has_complex = True
                elif stmt_kind == 'ReturnStmt':
                    if hasattr(stmt, 'value') and stmt.value:
                        expr_strs.append(self._expr_to_str(stmt.value))
                elif stmt_kind == 'ExprStmt':
                    # 表达式语句: 提取内部表达式
                    inner = getattr(stmt, 'value', None)
                    if inner is not None:
                        expr_strs.append(self._expr_to_str(inner))
                    else:
                        has_complex = True
                elif isinstance(stmt, (BinOp, UnaryOp, Call, Name, Constant)):
                    expr_strs.append(self._expr_to_str(stmt))
                else:
                    has_complex = True
                    expr_str = self._stmt_to_expr(stmt)
                    if expr_str:
                        expr_strs.append(expr_str)
            
            if not has_complex and len(expr_strs) == 1:
                # 单表达式: 直接传递
                self._write(expr_strs[0])
            else:
                # 多语句: 使用 lambda 惰性求值
                self._write("lambda: (")
                self.indent += 1
                if expr_strs:
                    self._write(", ".join(expr_strs) + ",")
                self.indent -= 1
                self._write(")[-1]")
            
        elif node.block_type == BuildBlockExpr.BUILD_GEN:
            # *: 生成器构建块
            # 使用生成器表达式
            self._write("(")
            self.indent += 1
            
            gen_parts = []
            for stmt in node.body:
                stmt_kind = getattr(stmt, 'kind', None)
                if stmt_kind == 'ReturnStmt':
                    if hasattr(stmt, 'value') and stmt.value:
                        gen_parts.append(self._expr_to_str(stmt.value))
                elif isinstance(stmt, (BinOp, UnaryOp, Call, Name, Constant)):
                    gen_parts.append(self._expr_to_str(stmt))
                elif stmt_kind == 'YieldStmt':
                    if hasattr(stmt, 'value') and stmt.value:
                        gen_parts.append(f"({self._expr_to_str(stmt.value)} for _ in [0])")
            
            if gen_parts:
                self._write(", ".join(gen_parts))
            
            self.indent -= 1
            self._write(")")
        elif node.block_type == BuildBlockExpr.BUILD_INDEX:
            # ^: 索引构建块 - 已在解析器中转换为 Subscript
            # 此处不应到达，如果到达则回退处理
            if node.body and len(node.body) == 1:
                key_expr = self._expr_to_str(node.body[0])
                self._write(f"__getitem__({key_expr})")
            else:
                self._write("None")
        else:
            # 未知类型，回退方案
            self._write("None")
    
    def _let_stmt_to_expr(self, node: Any) -> str:
        """将 let 语句转换为赋值表达式"""
        name = getattr(node, 'name', '_tmp')
        value = None
        if hasattr(node, 'value') and node.value:
            value = self._expr_to_str(node.value)
        else:
            value = 'None'
        # 使用 := 海象运算符 (Python 3.8+)
        return f"({name} := {value})"
    
    def _stmt_to_expr(self, node: Any) -> str:
        """将语句转换为表达式（如果可能）"""
        stmt_kind = getattr(node, 'kind', None)
        if stmt_kind == 'Assign':
            # 赋值语句
            if hasattr(node, 'targets') and node.targets and hasattr(node, 'value'):
                target = node.targets[0]
                if hasattr(target, 'id'):
                    name = target.id
                elif hasattr(target, 'name'):
                    name = target.name
                else:
                    name = '_tmp'
                value = self._expr_to_str(node.value)
                return f"({name} := {value})"
        elif stmt_kind == 'ExprStmt':
            # 表达式语句
            if hasattr(node, 'value') and node.value:
                return self._expr_to_str(node.value)
        return None

    def _visit_ListComp(self, node: ListComp) -> None:
        """生成列表推导式的 Cython 代码"""
        # 元素表达式
        elt_str = self._expr_to_str(node.elt)
        
        # 生成器部分
        gen_parts = []
        for target, iter_expr, if_exprs in node.generators:
            if isinstance(target, tuple):
                target_str = ", ".join(target)
            else:
                target_str = target
            
            iter_str = self._expr_to_str(iter_expr)
            gen_part = f"for {target_str} in {iter_str}"
            
            # 添加 if 条件
            if if_exprs:
                if isinstance(if_exprs, list):
                    for if_expr in if_exprs:
                        if_str = self._expr_to_str(if_expr)
                        gen_part += f" if {if_str}"
                else:
                    if_str = self._expr_to_str(if_exprs)
                    gen_part += f" if {if_str}"
            
            gen_parts.append(gen_part)
        
        # 组合成列表推导式
        gen_str = " ".join(gen_parts)
        self._write(f"[{elt_str} {gen_str}]")

    def _visit_TraitDef(self, node: TraitDef) -> None:
        base_classes = [self._type_to_str(t) for t in node.super_traits]
        if not base_classes:
            base_classes = ["object"]

        # Cython 的 cdef class 只允许继承一个扩展类型（extension type）基类。
        # trait 组合（如 ReadWrite(Readable, Writable)）会产生多个 cdef 基类 -> 非法。
        # 解决：只保留第一个 super trait 作为 cdef 基类，其余 super trait 的方法合并进本 trait。
        all_methods = list(node.methods)
        if len(base_classes) > 1:
            seen = {m.name for m in all_methods if isinstance(m, FuncDef)}
            trait_defs = getattr(self, 'trait_defs', {})
            for st_name in base_classes[1:]:
                st_def = trait_defs.get(st_name)
                if st_def is not None:
                    for m in st_def.methods:
                        if isinstance(m, FuncDef) and m.name not in seen:
                            all_methods.append(m)
                            seen.add(m.name)
            base_classes = [base_classes[0]]

        bases_str = ", ".join(base_classes)
        self._write(f"cdef class {node.name}({bases_str}):")
        self.indent += 1

        # trait 的泛型参数（如 T）与 Self 伪类型在方法签名中无对应 C 类型，
        # 需加入 _generic_params 使其回退为 object（否则 Cython 报 'T' is not a type identifier）
        _saved_trait_generic = set(self._generic_params)
        if getattr(node, 'generic_params', None):
            self._generic_params |= set(node.generic_params)
        self._generic_params.add('Self')

        self._write("__slots__ = ('__vtable__',)")
        self._write("cdef void** __vtable__")
        
        for method in all_methods:
            if isinstance(method, FuncDef):
                return_type_str = self._type_to_str(method.return_type) if method.return_type else "void"
                return_type_str = self._normalize_method_type(return_type_str)
                # 跳过 self 参数，只处理方法的实际参数
                params_parts = []
                for p in method.params:
                    if p.name == 'self':
                        continue
                    param_type = self._type_to_str(p.type_annotation) if p.type_annotation else 'object'
                    params_parts.append(f"{self._normalize_method_type(param_type)} {p.name}")
                params_str = ", ".join(params_parts)
                if params_str:
                    params_str = f"self, {params_str}"
                else:
                    params_str = "self"
                
                has_body = len(method.body) > 0 and not (len(method.body) == 1 and getattr(method.body[0], 'kind', '') == 'PassStmt')
                
                # def 函数不能使用 cdef 风格的 `int name`，改用 -> 返回类型注解
                ret_ann = "" if return_type_str in ("void", "object", "") else f" -> {return_type_str}"
                
                if has_body:
                    self._write(f"def {method.name}({params_str}){ret_ann}:")
                    self.indent += 1
                    for stmt in method.body:
                        self._visit(stmt)
                    self.indent -= 1
                else:
                    self._write(f"def {method.name}({params_str}){ret_ann}:")
                    self.indent += 1
                    self._write(f"raise NotImplementedError(f\"{{type(self).__name__}} must implement '{method.name}'\")")
                    self.indent -= 1
        
        self._write(f"def __init__(self):")
        self.indent += 1
        self._write(f"self.__vtable__ = <void**>malloc({len(all_methods) + 1} * sizeof(void*))")
        vtable_index = 0
        for method in all_methods:
            if isinstance(method, FuncDef):
                self._write(f"self.__vtable__[{vtable_index}] = <void*>self.{method.name}")
                vtable_index += 1
        self._write(f"self.__vtable__[{vtable_index}] = NULL")
        self.indent -= 1
        
        # 添加 __dealloc__ 方法释放虚表内存
        self._write(f"def __dealloc__(self):")
        self.indent += 1
        self._write(f"if self.__vtable__ != NULL:")
        self.indent += 1
        self._write(f"free(self.__vtable__)")
        self._write(f"self.__vtable__ = NULL")
        self.indent -= 1
        self.indent -= 1

        # 恢复 trait 泛型参数上下文
        self._generic_params = _saved_trait_generic

        self.indent -= 1
        self._write("")

    def _type_has_generics(self, typename: str) -> bool:
        """判断类型字符串是否包含泛型标记（<...> 或 [...]）"""
        return '<' in typename or '[' in typename

    def _cdef_type_for_impl(self, typename: str) -> str:
        """cdef class 的属性/参数类型若包含泛型（如 Wrapper<T>、ListBox[T]），
        Cython 不支持，回退为 object；非泛型类型原样保留。
        """
        if self._type_has_generics(typename):
            return "object"
        return typename

    def _impl_class_name_part(self, typename: str) -> str:
        """将类型字符串中的泛型标记转换为合法标识符片段，用于拼接 cdef 类名"""
        return (typename
                .replace('<', '_').replace('>', '_')
                .replace('[', '_').replace(']', '_')
                .replace(', ', '_').replace(' ', '_'))

    def _visit_ImplStmt(self, node: ImplStmt) -> None:
        for_type = self._type_to_str(node.for_type) if isinstance(node.for_type, ASTNode) else str(node.for_type)
        trait_generic_str = ""
        if node.trait_generic_args:
            trait_generic_str = "[" + ", ".join(self._type_to_str(arg) for arg in node.trait_generic_args) + "]"
        
        impl_class_name = f"_{node.trait_name}{self._impl_class_name_part(trait_generic_str)}__{self._impl_class_name_part(for_type)}"
        
        self._write(f"cdef class {impl_class_name}({node.trait_name}):")
        self.indent += 1
        
        self._write(f"__slots__ = ('__inner__',)")
        self._write(f"cdef {self._cdef_type_for_impl(for_type)} __inner__")
        
        self._write(f"def __init__(self, {self._cdef_type_for_impl(for_type)} obj):")
        self.indent += 1
        self._write(f"self.__inner__ = obj")
        self._write(f"super().__init__()")
        self.indent -= 1
        
        method_impls = {m.name: m for m in node.methods if isinstance(m, FuncDef)}
        
        trait_def = None
        if hasattr(self, 'trait_defs') and node.trait_name in self.trait_defs:
            trait_def = self.trait_defs[node.trait_name]
        
        for method in node.methods:
            if isinstance(method, FuncDef):
                return_type_str = self._type_to_str(method.return_type) if method.return_type else "void"
                return_type_str = self._normalize_method_type(return_type_str)
                # 跳过 self 参数
                params_parts = []
                for p in method.params:
                    if p.name == 'self':
                        continue
                    param_type = self._type_to_str(p.type_annotation) if p.type_annotation else 'object'
                    params_parts.append(f"{self._normalize_method_type(param_type)} {p.name}")
                params_str = ", ".join(params_parts)
                if params_str:
                    params_str = f"self, {params_str}"
                else:
                    params_str = "self"
                
                self._write(f"cpdef {return_type_str} {method.name}({params_str}):")
                self.indent += 1
                for stmt in method.body:
                    self._visit(stmt)
                self.indent -= 1
        
        self.indent -= 1
        self._write("")

    def _visit_TypeClassDef(self, node: TypeClassDef) -> None:
        """生成 TypeClass 的 Cython 代码（对标 Rust trait / Scala Type Class）
        
        TypeClass 生成 cdef 抽象基类，方法签名作为抽象方法，
        子类通过 TypeClassImpl 提供具体实现。
        """
        bases_str = "object"
        
        # TypeClass 的泛型参数（如 T）与 callable 等伪类型在方法签名中无对应 C 类型，
        # 需加入 _generic_params 使其回退为 object
        _saved_tc_generic = set(self._generic_params)
        if getattr(node, 'generic_params', None):
            self._generic_params |= set(node.generic_params)
        self._generic_params.add('Self')

        self._write(f"cdef class {node.name}({bases_str}):")
        self.indent += 1
        
        # 虚表支持（用于运行时方法解析）
        self._write("__slots__ = ('__typeclass_vtable__',)")
        self._write("cdef void** __typeclass_vtable__")
        
        # 生成抽象方法签名
        for method in node.methods:
            if isinstance(method, FuncDef):
                return_type_str = self._type_to_str(method.return_type) if method.return_type else "void"
                return_type_str = self._normalize_method_type(return_type_str)
                params_parts = []
                for p in method.params:
                    if p.name == 'self':
                        continue
                    param_type = self._type_to_str(p.type_annotation) if p.type_annotation else "object"
                    param_type = self._normalize_method_type(param_type)
                    params_parts.append(f"{param_type} {p.name}")
                params_str = ", ".join(params_parts)
                if params_str:
                    params_str = f"self, {params_str}"
                else:
                    params_str = "self"
                
                # TypeClass 方法声明为抽象方法（用 def + 注解形式）
                ret_ann = "" if return_type_str in ("void", "object", "") else f" -> {return_type_str}"
                self._write(f"def {method.name}({params_str}){ret_ann}:")
                self.indent += 1
                self._write(f'raise NotImplementedError(f"{{type(self).__name__}} must implement {method.name}")')
                self.indent -= 1
        
        # 初始化虚表
        self._write(f"def __init__(self):")
        self.indent += 1
        self._write(f"self.__typeclass_vtable__ = <void**>malloc({len(node.methods) + 1} * sizeof(void*))")
        vtable_index = 0
        for method in node.methods:
            if isinstance(method, FuncDef):
                self._write(f"self.__typeclass_vtable__[{vtable_index}] = <void*>self.{method.name}")
                vtable_index += 1
        self._write(f"self.__typeclass_vtable__[{vtable_index}] = NULL")
        self.indent -= 1
        
        # 添加 __dealloc__ 方法释放虚表内存
        self._write(f"def __dealloc__(self):")
        self.indent += 1
        self._write(f"if self.__typeclass_vtable__ != NULL:")
        self.indent += 1
        self._write(f"free(self.__typeclass_vtable__)")
        self._write(f"self.__typeclass_vtable__ = NULL")
        self.indent -= 1
        self.indent -= 1

        # 恢复 TypeClass 泛型参数上下文
        self._generic_params = _saved_tc_generic

        self.indent -= 1
        self._write("")

    def _normalize_method_type(self, typename: str) -> str:
        """归一化方法签名中的类型：callable 等非 Cython 类型与泛型类型均回退为 object"""
        if typename in ('callable', 'function', 'Function', 'Any', 'object'):
            return "object"
        if self._type_has_generics(typename):
            return "object"
        return typename

    def _visit_TypeClassImpl(self, node: TypeClassImpl) -> None:
        """生成 TypeClass 实现的 Cython 代码
        
        为目标类型生成包装类，继承 TypeClass 并委托给内部对象。
        """
        target_type = self._type_to_str(node.target_type) if isinstance(node.target_type, ASTNode) else str(node.target_type)
        typeclass_name = node.typeclass_name

        # 泛型参数在签名中作为类型标识符时回退为 object
        saved_generic_params = set(self._generic_params)
        if node.generic_params:
            self._generic_params |= set(node.generic_params)
        if target_type in self._generic_params:
            target_type = "object"

        # 生成唯一的实现类名（泛型标记转为合法标识符片段）
        impl_class_name = f"__TypeClass_{typeclass_name}_impl_{self._impl_class_name_part(target_type)}"
        
        self._write(f"cdef class {impl_class_name}({typeclass_name}):")
        self.indent += 1
        
        self._write(f"__slots__ = ('__inner__',)")
        self._write(f"cdef {self._cdef_type_for_impl(target_type)} __inner__")
        
        self._write(f"def __init__(self, {self._cdef_type_for_impl(target_type)} obj):")
        self.indent += 1
        self._write(f"self.__inner__ = obj")
        self._write(f"super().__init__()")
        self.indent -= 1
        
        # 生成方法实现
        method_impls = {m.name: m for m in node.methods if isinstance(m, FuncDef)}
        
        for method in node.methods:
            if isinstance(method, FuncDef):
                return_type_str = self._type_to_str(method.return_type) if method.return_type else "void"
                return_type_str = self._normalize_method_type(return_type_str)
                params_parts = []
                for p in method.params:
                    if p.name == 'self':
                        continue
                    param_type = self._type_to_str(p.type_annotation) if p.type_annotation else "object"
                    params_parts.append(f"{self._normalize_method_type(param_type)} {p.name}")
                params_str = ", ".join(params_parts)
                if params_str:
                    params_str = f"self, {params_str}"
                else:
                    params_str = "self"
                
                self._write(f"cpdef {return_type_str} {method.name}({params_str}):")
                self.indent += 1
                for stmt in method.body:
                    self._visit(stmt)
                self.indent -= 1
        
        self._generic_params = saved_generic_params
        self.indent -= 1
        self._write("")

    def _emit_meta_assign(self, stmt, ns) -> None:
        """编译期求值 meta 块内的赋值，并将结果作为模块级常量输出"""
        # 兼容 ConstDecl / Assign / LetStmt 等不同节点
        name = getattr(stmt, 'name', None)
        if not isinstance(name, str):
            name = getattr(name, 'id', None)
        if name is None:
            # Assign 节点使用 .target（可能是 Name 或字符串）
            target = getattr(stmt, 'target', None)
            if isinstance(target, str):
                name = target
            elif target is not None:
                name = getattr(target, 'id', None)
        value = getattr(stmt, 'value', None)
        if name is None or value is None:
            return
        value_src = self._expr_to_str(value)
        # 求值以填入命名空间（供后续条件分支引用）
        try:
            val = eval(value_src, {"__builtins__": {}}, ns)
        except Exception:
            val = None
        ns[name] = val
        self._write(f"{name} = {value_src}")

    def _emit_meta_if(self, stmt, ns) -> None:
        """编译期求值 meta 块内的条件生成"""
        cond_src = self._expr_to_str(getattr(stmt, 'test', getattr(stmt, 'condition', None)))
        try:
            ok = bool(eval(cond_src, {"__builtins__": {}}, ns))
        except Exception:
            ok = False
        if ok:
            for s in (getattr(stmt, 'body', None) or []):
                if isinstance(s, DuckDef):
                    continue
                elif isinstance(s, FuncDef):
                    self._visit(s)
                elif getattr(s, 'kind', None) == 'IfStmt':
                    self._emit_meta_if(s, ns)
                else:
                    self._emit_meta_assign(s, ns)

    def _visit_MetaBlock(self, node: MetaBlock) -> None:
        """生成元编程块的 Cython 代码 - 处理 duck 约束与编译期求值"""
        self._write("# === Meta Block ===")
        self._write("_duck_registry = {}")

        ns = self._meta_namespace
        for stmt in node.body:
            if isinstance(stmt, DuckDef):
                self._visit_DuckDef(stmt)
            elif isinstance(stmt, FuncDef):
                # 编译期生成的模块级函数，直接输出为 def
                self._visit(stmt)
            elif getattr(stmt, 'kind', None) == 'IfStmt':
                # 条件生成（如 if HAS_FEATURES: CONFIG = {...}）
                self._emit_meta_if(stmt, ns)
            else:
                # 模块级常量声明（ConstDecl / Assign / LetStmt）
                self._emit_meta_assign(stmt, ns)

        self._write("")

    def _visit_DuckDef(self, node: DuckDef) -> None:
        """生成 duck 约束的 Cython 代码

        生成策略: 注释 + 运行时注册表
        注册表包含完整的约束元数据，供运行时反射使用。

        示例输出:
            # Duck constraint: Comparable
            #   Operator: <(a, b) -> bool
            #   Operator: >(a, b) -> bool
            _duck_registry['Comparable'] = {'type_params': [], 'requirements': [
                {'kind': 'operator', 'name': '<', 'params': ['a', 'b'], 'return_type': 'bool', 'is_unary': False},
                ...
            ]}
        """
        self._write(f"# Duck constraint: {node.name}")

        if node.type_params:
            params_str = ", ".join(node.type_params)
            self._write(f"#   Generic: <{params_str}>")

        for req in node.requirements:
            if req.kind == "operator":
                if req.is_unary:
                    self._write(f"#   Operator: {req.name}{req.params[0]} -> {req.return_type or 'Any'}")
                else:
                    params_str = ", ".join(req.params)
                    ret_str = f" -> {req.return_type}" if req.return_type else ""
                    self._write(f"#   Operator: {req.name}({params_str}){ret_str}")
            elif req.kind == "attribute":
                ret_str = f": {req.return_type}" if req.return_type else ""
                self._write(f"#   Attribute: {req.name}{ret_str}")
            elif req.kind == "method":
                params_str = ", ".join(req.params)
                ret_str = f" -> {req.return_type}" if req.return_type else ""
                self._write(f"#   Method: {req.name}({params_str}){ret_str}")
            elif req.kind == "reference":
                if req.generic_args and isinstance(req.generic_args, (list, tuple)):
                    args_str = ", ".join(req.generic_args)
                    self._write(f"#   Reference: {req.name}<{args_str}>")
                else:
                    self._write(f"#   Reference: {req.name}")

        # 生成完整的运行时注册表条目
        reqs_data = []
        for req in node.requirements:
            req_entry = {
                "kind": req.kind,
                "name": req.name,
                "params": req.params,
                "return_type": req.return_type,
                "generic_args": req.generic_args if isinstance(req.generic_args, (list, tuple)) else [],
                "is_unary": bool(req.is_unary)
            }
            reqs_data.append(req_entry)

        # 使用 repr() 生成合法的 Python 字典字面量（避免 json.dumps 的 false/true/null 不被 Cython 识别）
        reqs_json = repr(reqs_data)
        self._write(f"_duck_registry['{node.name}'] = {{'type_params': {node.type_params!r}, 'requirements': {reqs_json}}}")

    def _visit_LambdaExpr(self, node: Any) -> str:
        """生成 lambda 表达式的 Cython 代码"""
        params = []
        for param in node.params:
            if param.type_annotation:
                params.append(f"{param.name}: {self._type_to_str(param.type_annotation)}")
            else:
                params.append(param.name)
        params_str = ", ".join(params)
        return f"lambda {params_str}: {self._expr_to_str(node.body)}"

    def _visit_TryStmt(self, node: Any) -> None:
        """生成 try/except/finally 语句的 Cython 代码"""
        self._write("try:")
        self.indent += 1
        if node.body:
            for stmt in node.body:
                self._visit(stmt)
        else:
            self._write("pass")
        self.indent -= 1

        handlers = getattr(node, 'handlers', []) or []
        finally_body = getattr(node, 'orelse', None) or []

        # 处理 except 子句（handlers 为 (type, name, body) 列表）
        for handler in handlers:
            if isinstance(handler, (list, tuple)):
                exc_type, exc_name, except_body = (list(handler) + [None, None, None])[:3]
            else:
                exc_type = getattr(handler, 'type', None)
                exc_name = getattr(handler, 'name', None)
                except_body = getattr(handler, 'body', [])
            if exc_type is None:
                self._write("except:")
            else:
                exc_type_str = self._expr_to_str(exc_type) if hasattr(exc_type, 'kind') else str(exc_type)
                if exc_name:
                    self._write(f"except {exc_type_str} as {exc_name}:")
                else:
                    self._write(f"except {exc_type_str}:")
            self.indent += 1
            if except_body:
                for stmt in except_body:
                    self._visit(stmt)
            else:
                self._write("pass")
            self.indent -= 1

        # 处理 finally 子句
        if finally_body:
            self._write("finally:")
            self.indent += 1
            if finally_body:
                for stmt in finally_body:
                    self._visit(stmt)
            else:
                self._write("pass")
            self.indent -= 1

        # Cython 要求 try 至少跟随 except 或 finally
        if not handlers and not finally_body:
            self._write("except:")
            self.indent += 1
            self._write("pass")
            self.indent -= 1

    def _visit_RaiseStmt(self, node: Any) -> None:
        """生成 raise 语句的 Cython 代码"""
        if node.exc:
            self._write(f"raise {self._expr_to_str(node.exc)}")
        else:
            self._write("raise")

    def _visit_AssertStmt(self, node: Any) -> None:
        """生成 assert 语句的 Cython 代码"""
        if node.msg:
            self._write(f"assert {self._expr_to_str(node.test)}, {self._expr_to_str(node.msg)}")
        else:
            self._write(f"assert {self._expr_to_str(node.test)}")

    def _visit_YieldStmt(self, node: Any) -> None:
        """生成 yield 语句的 Cython 代码"""
        if node.is_from and node.value:
            self._write(f"yield from {self._expr_to_str(node.value)}")
        elif node.value:
            self._write(f"yield {self._expr_to_str(node.value)}")
        else:
            self._write("yield")

    def _visit_VecType(self, node: VecType) -> str:
        """VecType → Python list type"""
        return "list"

    def _visit_VecLiteral(self, node: VecLiteral) -> str:
        """VecLiteral → Python list literal"""
        elements_str = ", ".join(self._expr_to_str(e) for e in node.elements)
        if node.size and len(node.elements) == 1 and node.size > 1:
            elem = self._expr_to_str(node.elements[0])
            return f"[{elem}] * {node.size}"
        return f"[{elements_str}]"

    def _visit_DictLiteral(self, node: DictLiteral) -> str:
        """DictLiteral → Python dict literal"""
        parts = []
        for k, v in node.pairs:
            parts.append(f"{self._expr_to_str(k)}: {self._expr_to_str(v)}")
        return "{" + ", ".join(parts) + "}"

    def _visit_PipeExpr(self, node: PipeExpr) -> str:
        """PipeExpr → function call (already converted to Call by parser, fallback for direct usage)"""
        # 兜底处理：将 x |> f 转换为 f(x)
        value_str = self._expr_to_str(node.value)
        func = node.function
        if hasattr(func, 'kind') and func.kind == 'Call':
            # f(args) → f(x, args)
            args = [value_str] + [self._expr_to_str(a) for a in func.args]
            func_name = self._expr_to_str(func.func)
            return f"{func_name}({', '.join(args)})"
        elif hasattr(func, 'id'):
            return f"{func.id}({value_str})"
        else:
            # 函数表达式是 lambda 等复杂形式时必须加括号，否则 lambda x: f(g) 会被误解析为 lambda x: (f(g))
            func_str = self._expr_to_str(func)
            return f"({func_str})({value_str})"

    def _visit_MacroDef(self, node: MacroDef) -> None:
        """MacroDef → 编译期函数"""
        self._write(f"# macro {node.name} - compile-time macro")
        self._write(f"def _macro_{node.name}(ts):")
        self.indent += 1
        self._write("# Macro body evaluated at compile time")
        self._write("pass  # Macro expansion happens during parsing")
        self.indent -= 1
        self._write("")

    def _expand_macro(self, name: str, args) -> str:
        """编译期宏展开：将宏体模板中的 {param} 替换为调用实参的源码字符串。"""
        # 宏名可能带 ! 后缀（@name! 或 name! 语法），统一去除以便查表
        if isinstance(name, str):
            name = name.rstrip('!')
        mdef = self.macro_defs.get(name)
        if not mdef:
            # 未知宏：退化为函数调用（虽不可达，保证语法合法）
            args_str = ", ".join(self._expr_to_str(a) for a in args)
            return f"_macro_{name}({args_str})"
        params = []
        for p in (getattr(mdef, 'params', []) or []):
            if isinstance(p, dict):
                params.append(p.get('name'))
            elif hasattr(p, 'name'):
                params.append(p.name)
            else:
                params.append(str(p))
        arg_sources = [self._expr_to_str(a) for a in args]
        template = ""
        for stmt in (getattr(mdef, 'body', []) or []):
            if getattr(stmt, 'kind', None) == 'ExprStmt':
                val = getattr(stmt, 'value', None)
                if val is not None:
                    template += getattr(val, 'value', '') or ''
        for i, p in enumerate(params):
            if i < len(arg_sources):
                template = template.replace('{' + p + '}', arg_sources[i])
        return template

    def _visit_MacroCall(self, node: MacroCall) -> str:
        """MacroCall → 编译期展开为模板替换后的代码"""
        return self._expand_macro(node.name, node.args)

    def _is_macro_call(self, node) -> bool:
        """判断一个 Call 节点是否对应已定义的宏（而非普通函数）"""
        func = getattr(node, 'func', None)
        if not isinstance(func, Name):
            return False
        name = func.id.rstrip('!') if isinstance(func.id, str) else func.id
        return name in self.macro_defs

    def _visit_BuildValueExpr(self, node: BuildValueExpr) -> str:
        """BuildValueExpr → 值提取表达式"""
        return self._expr_to_str(node.operand)

    def _visit_AwaitExpr(self, node: AwaitExpr) -> str:
        """AwaitExpr → await 表达式（Cython 原生 async 支持）"""
        value_str = self._expr_to_str(node.value)
        return f"await {value_str}"

    def _visit_BacktickBlock(self, node: BacktickBlock) -> str:
        """BacktickBlock → 反引号代码块，运行时退化为字符串字面量"""
        return repr(node.content)

    def _visit_SpawnStmt(self, node: Any) -> None:
        """生成 spawn 语句的 Cython 代码"""
        # 确保导入 threading 模块（只导入一次）
        if 'threading' not in self.output:
            self._write("import threading")
        
        if hasattr(node, 'body') and node.body:
            # 块形式：spawn: body... 使用独立函数包装（lambda 元组包裹语句非法）
            counter = getattr(self, '_conc_counter', 0)
            self._conc_counter = counter + 1
            fname = f"_cypy_spawn_{counter}"
            self._write(f"def {fname}():")
            self.indent += 1
            for stmt in node.body:
                self._visit(stmt)
            self.indent -= 1
            self._write("")
            self._write(f"threading.Thread(target={fname}).start()")
        elif hasattr(node, 'target') and node.target:
            # 调用形式：spawn func(args)
            args_str = ", ".join(self._expr_to_str(arg) for arg in getattr(node, 'args', []))
            self._write(f"threading.Thread(target={self._expr_to_str(node.target)}, args=({args_str})).start()")

    def _visit_GoStmt(self, node: Any) -> None:
        """生成 go 语句的 Cython 代码 - 使用 asyncio 协程"""
        # 确保导入 asyncio 模块（只导入一次）
        if 'import asyncio' not in self.output:
            self._write("import asyncio")
        
        if hasattr(node, 'body') and node.body:
            # 块形式：go: body... 使用独立 async 函数包装
            counter = getattr(self, '_conc_counter', 0)
            self._conc_counter = counter + 1
            fname = f"_cypy_go_{counter}"
            self._write(f"async def {fname}():")
            self.indent += 1
            for stmt in node.body:
                self._visit(stmt)
            self.indent -= 1
            self._write("")
            self._write(f"asyncio.create_task({fname}())")
        elif hasattr(node, 'target') and node.target:
            # 调用形式：go func(args)
            args_str = ", ".join(self._expr_to_str(arg) for arg in getattr(node, 'args', []))
            self._write(f"asyncio.create_task({self._expr_to_str(node.target)}({args_str}))")

    def _visit_Pattern(self, node: Any) -> str:
        """生成模式绑定的 Cython 代码"""
        return node.name

    def _visit_TypeAlias(self, node: Any) -> None:
        """生成类型别名的 Cython 代码
        
        对于非泛型别名，使用 ctypedef 定义
        对于泛型别名，使用 Python 的 TypeVar 和 Union 来定义
        """
        target_type = self._type_to_str(node.target)
        if node.generic_params:
            # 泛型类型别名：使用 Python 的 typing 模块定义
            # 例如: type Maybe[T] = T | None
            # 生成: T = TypeVar('T'); Maybe = Union[T, None]
            self._write("# 泛型类型别名")
            self._write("from typing import TypeVar, Union")
            for param in node.generic_params:
                self._write(f"{param} = TypeVar('{param}')")
            self._write(f"{node.name} = Union[{target_type}]")
        else:
            # 非泛型类型别名：使用 ctypedef
            # 检查目标类型是否是指针或其他特殊类型
            if '*' in target_type or 'ref ' in target_type:
                # 对于指针类型，使用注释表示（Cython 不支持 ctypedef 指针别名）
                self._write(f"# type alias: {node.name} = {target_type}")
            else:
                # 使用 ctypedef 定义类型别名
                self._write(f"ctypedef {target_type} {node.name}")
        self._write("")
    
    def _visit_ExceptionDef(self, node: ExceptionDef) -> None:
        """生成异常类型的 Cython 代码"""
        base_type = self._type_to_str(node.base_type) if node.base_type else "Exception"
        self._write(f"cdef class {node.name}({base_type}):")
        self.indent += 1
        # 生成 __init__ 方法
        if node.fields:
            field_names = []
            field_types = []
            for field in node.fields:
                if hasattr(field, 'name'):
                    field_names.append(field.name)
                    field_type = self._type_to_str(field.type_annotation) if hasattr(field, 'type_annotation') and field.type_annotation else "object"
                    field_types.append(field_type)
                    self._write(f"cdef {field_type} {field.name}")
            
            # 生成 __init__ 方法
            params_str = ", ".join([f"{t} {n}" for t, n in zip(field_types, field_names)])
            self._write("")
            self._write(f"def __init__(self, {params_str}):")
            self.indent += 1
            self._write("super().__init__()")
            for name in field_names:
                self._write(f"self.{name} = {name}")
            self.indent -= 1
        else:
            self._write("pass")
        self.indent -= 1
        self._write("")

    def _visit_BinOp(self, node: BinOp) -> str:
        # 运算符优先级（从高到低）
        precedence = {
            '**': 5,
            '*': 4, '/': 4, '%': 4, '//': 4,
            '+': 3, '-': 3,
            '<<': 2, '>>': 2,
            '&': 1, '^': 1, '|': 1,
        }
        
        left_str = self._expr_to_str(node.left)
        right_str = self._expr_to_str(node.right)
        
        # 检查是否需要为左操作数添加括号
        if isinstance(node.left, BinOp):
            left_prec = precedence.get(node.left.op, 0)
            current_prec = precedence.get(node.op, 0)
            # 如果左操作数优先级低于当前运算符，或者是右结合的幂运算
            if left_prec < current_prec or (node.op == '**' and left_prec <= current_prec):
                left_str = f"({left_str})"
        
        # 检查是否需要为右操作数添加括号
        if isinstance(node.right, BinOp):
            right_prec = precedence.get(node.right.op, 0)
            current_prec = precedence.get(node.op, 0)
            # 如果右操作数优先级低于当前运算符，或者是幂运算（右结合）
            if right_prec < current_prec or (node.op == '**' and right_prec <= current_prec):
                right_str = f"({right_str})"
        
        # 处理 "not is" → "is not"（Python/Cython 语法要求）
        op = node.op
        if op == "not is":
            op = "is not"
        # int / int 使用整数除法（与类型检查器一致：int / int -> int）
        if op == '/' and self._is_int_expr(node.left) and self._is_int_expr(node.right):
            op = '//'

        # 指针算术：ptr + idx（idx 为 Python 对象时）必须把 idx 转换为 C 整数，
        # 否则 Cython 会尝试把指针转成 Python 对象做加法
        if op in ('+', '-'):
            hoisted = getattr(self, '_hoisted_pointer_types', {})
            left_is_ptr = left_str in hoisted
            right_is_ptr = right_str in hoisted
            if left_is_ptr and not right_is_ptr:
                right_str = f"<Py_ssize_t>({right_str})"
            elif right_is_ptr and not left_is_ptr:
                left_str = f"<Py_ssize_t>({left_str})"

        # 指针与 None/null 的相等比较：Cython 不允许 int* 与 Python None 比较，
        # 需把 None 转为 C 的 NULL（仅当另一侧为已知指针变量时）
        if op in ('==', '!=', 'is', 'is not'):
            hoisted = getattr(self, '_hoisted_pointer_types', {})
            if right_str == 'None' and left_str in hoisted:
                right_str = 'NULL'
            elif left_str == 'None' and right_str in hoisted:
                left_str = 'NULL'

        return f"{left_str} {op} {right_str}"

    def _visit_IfExp(self, node) -> str:
        """生成三元条件表达式的 Cython 代码"""
        body_str = self._expr_to_str(node.body)
        test_str = self._expr_to_str(node.test)
        orelse_str = self._expr_to_str(node.orelse)
        return f"({body_str} if {test_str} else {orelse_str})"

    def _visit_UnaryOp(self, node: UnaryOp) -> str:
        if node.op == 'not':
            return f"not {self._expr_to_str(node.operand)}"
        if node.op == '&':
            # Cypy 中 & 为解引用操作符（*ptr），等价于 ptr[0]
            operand = node.operand
            operand_str = self._expr_to_str(operand)
            return f"({operand_str})[0]"
        return f"{node.op}{self._expr_to_str(node.operand)}"

    def _visit_DerefExpr(self, node: DerefExpr) -> str:
        return f"{self._expr_to_str(node.operand)}[0]"

    def _visit_CastExpr(self, node: CastExpr) -> str:
        """生成类型转换表达式的 Cython 代码"""
        value_str = self._expr_to_str(node.value)
        target_type_str = self._type_to_str(node.target_type)
        
        # 使用 Cython 的类型转换语法：<T>value（兼容基本类型与指针/结构体）
        return f"<{target_type_str}>{value_str}"

    def _visit_Call(self, node: Call) -> str:
        # 处理显式 __cast__[T]() / __try_cast__[T]() 转换为 Cython 的 <T>obj 语法
        if isinstance(node.func, Subscript) and isinstance(getattr(node.func, 'value', None), Attribute) \
                and node.func.value.attr in ('__cast__', '__try_cast__'):
            obj_str = self._expr_to_str(node.func.value.value)
            type_str = self._type_to_str(node.func.slice)
            return f"<{type_str}>{obj_str}"

        # 处理参数：支持位置参数和关键字参数
        func_name = node.func.id if isinstance(node.func, Name) else None
        func_ptr_idxs = getattr(self, '_func_pointer_indices', {}).get(func_name, set()) if func_name else set()
        arg_strings = []
        for ai, arg in enumerate(node.args):
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                kw_name, kw_value = arg
                arg_strings.append(f"{kw_name}={self._expr_to_str(kw_value)}")
            else:
                # 位置参数
                arg_str = self._expr_to_str(arg)
                # 若实参是 null/Nothing/None 且对应形参为指针类型，则映射为 C 的 NULL
                # （Cython 不允许把 Python None 赋给 int* 等指针参数）
                is_null_literal = (isinstance(arg, Name) and arg.id in ('null', 'Nothing')) or \
                                  (isinstance(arg, Constant) and arg.value is None)
                if is_null_literal and ai in func_ptr_idxs:
                    arg_str = "NULL"
                arg_strings.append(arg_str)
        args = ", ".join(arg_strings)
        
        # 宏调用（无 ! 语法，func 为已定义宏名）：编译期展开
        if self._is_macro_call(node):
            return self._expand_macro(node.func.id, node.args)
        
        if hasattr(node.func, 'id'):
            func_name = node.func.id
            
            # 特殊处理内置函数
            if func_name == 'malloc':
                # malloc 返回 void*，需要类型转换
                return f"<void*>{func_name}({args})"
            elif func_name == 'sizeof':
                # sizeof 需要特殊处理，参数可能是类型或表达式
                return f"{func_name}({args})"
            elif func_name == 'addr':
                # addr(var) 转换为 &var；若 var 是指针则转 void*（T** 不能直接使用）
                if node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, tuple):
                        first_arg = first_arg[1]
                    first_str = self._expr_to_str(first_arg)
                    if isinstance(first_arg, Name) and first_arg.id in getattr(self, '_hoisted_pointer_types', {}):
                        return f"<void*>{first_str}"
                    return f"&{first_str}"
                return f"{func_name}({args})"
            elif func_name == 'free':
                return f"{func_name}({args})"
        
        # 如果有调用时的 checker，在调用前调用 checker
        # 使用逗号表达式：(checker(), func(args))[1] 获取函数调用结果
        if node.checker:
            return f"({node.checker}(), {self._expr_to_str(node.func)}({args}))[1]"

        func_node = node.func
        func_str = self._expr_to_str(func_node)
        # 函数表达式是 lambda / 调用 / 运算等复杂形式时必须加括号，
        # 否则 lambda x: f(g) 会被误解析为 lambda x: (f(g))
        if hasattr(func_node, 'kind') and func_node.kind not in ('Name', 'Attribute', 'Subscript'):
            func_str = f"({func_str})"
        return f"{func_str}({args})"

    def _visit_Name(self, node: Name) -> str:
        # Cypy 的 null 关键字映射到 Python 的 None
        if node.id in ('null', 'Nothing'):
            return "None"
        # 泛型类型参数作为值使用（如 U() 构造）时无对应运行时对象，回退为 object
        if node.id in getattr(self, '_generic_params', set()):
            return "object"
        return node.id

    def _visit_Constant(self, node: Constant) -> str:
        if isinstance(node.value, str):
            # 检查是否是 f-string
            prefix = getattr(node, 'prefix', None)
            if prefix == 'f':
                val = node.value
                # f-string 在解析期已被渲染为字符串，其中的指针表达式（如 {&p}、{p}、{p + 1}）仍是文本。
                # 指针/指针算术结果无法直接转换为 Python 对象打印，需转换为 void*。
                hoisted = getattr(self, '_hoisted_pointer_types', {})
                def _fix_addr(m):
                    expr = m.group(1).strip()
                    # &NAME 为解引用（ptr[0]），结果是普通值可直接打印
                    mm = re.match(r'^&\s*([A-Za-z_]\w*)$', expr)
                    if mm and mm.group(1) in hoisted:
                        return '{' + mm.group(1) + '[0]}'
                    # NAME 或 NAME +/- ...：指针（地址）或指针算术，需转 Py_ssize_t 才能打印
                    if '[' not in expr and '.' not in expr:
                        mm = re.match(r'^([A-Za-z_]\w*)\s*(?:[+\-]\s*[^\[\]]+)?$', expr)
                        if mm and mm.group(1) in hoisted:
                            return '{<Py_ssize_t>(' + expr + ')}'
                    return m.group(0)
                val = re.sub(r'\{([^}{]*)\}', _fix_addr, val)
                # 对 f-string 也使用 repr 以正确处理引号与转义字符
                return 'f' + repr(val)
            # 使用 repr 以正确处理引号、换行等转义字符
            return repr(node.value)
        if isinstance(node.value, bool):
            return "True" if node.value else "False"
        if isinstance(node.value, list):
            # 列表字面量：递归访问每个元素
            elements = []
            for item in node.value:
                if isinstance(item, ASTNode):
                    elements.append(self._expr_to_str(item))
                else:
                    elements.append(repr(item))
            return f"[{', '.join(elements)}]"
        if isinstance(node.value, tuple):
            # 元组字面量：递归访问每个元素
            elements = []
            for item in node.value:
                if isinstance(item, ASTNode):
                    elements.append(self._expr_to_str(item))
                else:
                    elements.append(repr(item))
            # 处理空元组和单元素元组
            if len(elements) == 0:
                return "()"
            elif len(elements) == 1:
                return f"({elements[0]},)"
            return f"({', '.join(elements)})"
        return repr(node.value)

    def _visit_StructLiteral(self, node: Any) -> str:
        """生成结构体字面量的 Cython 代码 - StructName {field1: value1, field2: value2}"""
        fields_str = ", ".join(f"{name}={self._expr_to_str(value)}" for name, value in node.fields)
        return f"{node.struct_name}({fields_str})"

    def _visit_Attribute(self, node: Any) -> str:
        return f"{self._expr_to_str(node.value)}.{node.attr}"

    def _visit_Subscript(self, node: Any) -> str:
        value_str = self._expr_to_str(node.value)
        # 处理切片语法 list[a:b:c]
        if isinstance(node.slice, dict) and node.slice.get('slice'):
            start = self._expr_to_str(node.slice['start']) if node.slice.get('start') is not None else ''
            end = self._expr_to_str(node.slice['end']) if node.slice.get('end') is not None else ''
            step = self._expr_to_str(node.slice['step']) if node.slice.get('step') is not None else ''
            if step:
                return f"{value_str}[{start}:{end}:{step}]"
            return f"{value_str}[{start}:{end}]"
        return f"{value_str}[{self._expr_to_str(node.slice)}]"

    def _visit_PointerType(self, node: PointerType) -> str:
        base_type = self._type_to_str(node.base_type)
        # Cython 要求指针类型带空格：int *p（而非 int*p）
        return f"{base_type} *"

    def _visit_RefType(self, node: RefType) -> str:
        base_type = self._type_to_str(node.base_type)
        return f"{base_type}&"

    def _visit_GenericType(self, node: GenericType) -> str:
        # typing 构造类型（Optional/Callable/Union 等）无 Cython 对应类型，回退为 object
        if node.name in self._object_generic_types:
            return "object"
        if node.name in self.type_aliases:
            alias_node = self.type_aliases[node.name]
            alias_params = alias_node.generic_params
            target_type = alias_node.target
            param_map = {}
            for i, param_name in enumerate(alias_params):
                if i < len(node.args):
                    param_map[param_name] = node.args[i]
            expanded_target = self._expand_type_with_params(target_type, param_map)
            return self._type_to_str(expanded_target)
        
        if self.type_mapper.is_lz_generic_type(node.name):
            type_args = [self._type_to_str(arg) for arg in node.args]
            return self.type_mapper.map_lz_generic_type(node.name, type_args)
        
        args = ", ".join(self._type_to_str(arg) for arg in node.args)
        return f"{node.name}[{args}]"
    
    def _expand_type_with_params(self, node: ASTNode, param_map: Dict[str, ASTNode]) -> ASTNode:
        """递归展开类型，将泛型参数替换为实际类型"""
        if isinstance(node, Name):
            # 如果是泛型参数，替换为实际类型
            if node.id in param_map:
                return param_map[node.id]
            return node
        if isinstance(node, GenericType):
            # 递归处理泛型类型的参数
            new_args = [self._expand_type_with_params(arg, param_map) for arg in node.args]
            return GenericType(node.name, new_args, node.line, node.col)
        if isinstance(node, PointerType):
            # 递归处理指针类型
            new_base = self._expand_type_with_params(node.base_type, param_map)
            return PointerType(new_base, node.line, node.col)
        # 其他类型直接返回
        return node

    def _expr_to_str(self, node: ASTNode) -> str:
        # 表达式语句节点：解包内部表达式
        if getattr(node, 'kind', None) == 'ExprStmt':
            return self._expr_to_str(getattr(node, 'value', None) or node)
        # go 调用形式作为表达式：asyncio.create_task(...)
        if getattr(node, 'kind', None) == 'GoStmt':
            if getattr(node, 'target', None) and getattr(node, 'body', None):
                counter = getattr(self, '_conc_counter', 0)
                self._conc_counter = counter + 1
                fname = f"_cypy_go_{counter}"
                self._write(f"async def {fname}():")
                self.indent += 1
                for stmt in node.body:
                    self._visit(stmt)
                self.indent -= 1
                self._write("")
                return f"asyncio.create_task({fname}())"
            args_str = ", ".join(self._expr_to_str(a) for a in getattr(node, 'args', []))
            return f"asyncio.create_task({self._expr_to_str(node.target)}({args_str}))"
        if isinstance(node, BinOp):
            return self._visit_BinOp(node)
        if isinstance(node, IfExp):
            return self._visit_IfExp(node)
        if isinstance(node, UnaryOp):
            return self._visit_UnaryOp(node)
        if isinstance(node, DerefExpr):
            return self._visit_DerefExpr(node)
        if isinstance(node, CastExpr):
            return self._visit_CastExpr(node)
        if isinstance(node, Call):
            return self._visit_Call(node)
        if isinstance(node, Name):
            return self._visit_Name(node)
        if isinstance(node, Constant):
            return self._visit_Constant(node)
        if isinstance(node, Attribute):
            return self._visit_Attribute(node)
        if isinstance(node, Subscript):
            return self._visit_Subscript(node)
        if isinstance(node, VecLiteral):
            return self._visit_VecLiteral(node)
        if isinstance(node, DictLiteral):
            return self._visit_DictLiteral(node)
        if isinstance(node, PipeExpr):
            return self._visit_PipeExpr(node)
        if isinstance(node, MacroCall):
            return self._visit_MacroCall(node)
        if isinstance(node, BuildValueExpr):
            return self._visit_BuildValueExpr(node)
        if isinstance(node, AwaitExpr):
            return self._visit_AwaitExpr(node)
        if isinstance(node, BacktickBlock):
            return self._visit_BacktickBlock(node)
        if isinstance(node, UnionType):
            return "object"
        if isinstance(node, VecType):
            return self._visit_VecType(node)
        if hasattr(node, "kind") and node.kind == "StructLiteral":
            return self._visit_StructLiteral(node)
        if hasattr(node, "kind") and node.kind == "BuildBlockExpr":
            # 构建块表达式需要特殊处理，直接调用 _visit_BuildBlockExpr
            old_output = self.output
            self.output = []
            old_indent = self.indent
            self.indent = 0
            try:
                self._visit_BuildBlockExpr(node)
                return "".join(self.output)
            finally:
                self.output = old_output
                self.indent = old_indent
        if isinstance(node, ListComp):
            # 列表推导式需要特殊处理，直接调用 _visit_ListComp
            old_output = self.output
            self.output = []
            old_indent = self.indent
            self.indent = 0
            try:
                self._visit_ListComp(node)
                return "".join(self.output)
            finally:
                self.output = old_output
                self.indent = old_indent
        if hasattr(node, "kind") and node.kind == "LambdaExpr":
            return self._visit_LambdaExpr(node)
        if hasattr(node, "kind") and node.kind == "Pattern":
            return self._visit_Pattern(node)
        if hasattr(node, "kind") and node.kind == "MatchExpr":
            return self._visit_MatchExpr(node)
        if hasattr(node, "id"):
            return node.id
        return str(node)

    def _sanitize_type(self, type_str: str) -> str:
        """移除类型字符串中的泛型下标（如 list[str] -> list），使其可作为注解使用。"""
        if type_str is None:
            return "object"
        # 去掉形如 [ ... ] 的泛型下标部分
        idx = type_str.find("[")
        if idx != -1:
            # 仅当 [ 前是字母/标识符时才截断，避免误伤普通表达式
            if idx > 0 and (type_str[idx - 1].isalnum() or type_str[idx - 1] in "_."):
                base = type_str[:idx].strip()
                if base:
                    return base
        return type_str

    def _is_int_expr(self, node: Any) -> bool:
        """判断表达式是否为整数类型（用于决定 / 是否生成 //）"""
        if node is None:
            return False
        if isinstance(node, Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return True
        if isinstance(node, Name):
            t = self._current_local_types.get(node.id)
            if t in ('int', 'long', 'short', 'char', 'longlong',
                     'unsigned int', 'unsigned long', 'unsigned char'):
                return True
            return False
        if isinstance(node, UnaryOp) and node.op in ('+', '-', '~'):
            return self._is_int_expr(node.operand)
        if isinstance(node, BinOp):
            return self._is_int_expr(node.left) and self._is_int_expr(node.right)
        return False

    def _type_to_str(self, node: ASTNode) -> str:
        if hasattr(node, 'id') and node.id in ('None', 'Nothing', 'null'):
            return "object"
        # never / Never 返回类型映射到 Python 的 NoReturn（表示该函数不返回）
        if hasattr(node, 'id') and node.id in ('never', 'Never', 'NeverType'):
            return "NoReturn"
        # 联合类型使用 object 表示（Cython 不支持原生联合类型）
        if isinstance(node, UnionType):
            # 在 Cython 中，联合类型使用 object 类型
            return "object"
        if isinstance(node, VecType):
            return self._visit_VecType(node)
        if isinstance(node, Name):
            # 检查是否是类型别名，如果是则展开
            if node.id in self.type_aliases:
                alias_node = self.type_aliases[node.id]
                return self._type_to_str(alias_node.target)
            # 检查是否是枚举类型，如果是则返回object（Cython中Python类不能直接作为cpdef参数类型）
            if node.id in self.enum_defs:
                return "object"
            # 泛型参数在 Cython 中无对应类型，回退为 object
            if node.id in self._generic_params:
                return "object"
            return self.type_mapper.to_cython(node.id)
        if isinstance(node, PointerType):
            return self._visit_PointerType(node)
        if isinstance(node, RefType):
            return self._visit_RefType(node)
        if isinstance(node, GenericType):
            return self._visit_GenericType(node)
        if hasattr(node, "id"):
            # 检查是否是类型别名
            if node.id in self.type_aliases:
                alias_node = self.type_aliases[node.id]
                return self._type_to_str(alias_node.target)
            # 检查是否是枚举类型
            if node.id in self.enum_defs:
                return "object"
            return self.type_mapper.to_cython(node.id)
        return str(node)

    def _visit_SuiteDef(self, node: SuiteDef) -> None:
        """生成测试套件定义的 Cython 代码"""
        self._write(f"# Suite: {node.name}")
        self._write(f"def suite_{node.name}():")
        self.indent += 1
        self._write("import sys")
        self._write("from cypy_test_suite import Suite")
        self._write(f"suite = Suite('{node.name}')")
        self._visit_children(node)
        self._write("return suite")
        self.indent -= 1
        self._write("")

    def _visit_TestDef(self, node: TestDef) -> None:
        """生成测试用例定义的 Cython 代码"""
        self._write(f"@suite.test('{node.name}')")
        self._write(f"def test_{node.name}():")
        self.indent += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent -= 1
        self._write("")

    def _visit_SetupStmt(self, node: SetupStmt) -> None:
        """生成测试套件初始化块的 Cython 代码"""
        self._write("@suite.setup")
        self._write("def _setup():")
        self.indent += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent -= 1
        self._write("")

    def _visit_TeardownStmt(self, node: TeardownStmt) -> None:
        """生成测试套件清理块的 Cython 代码"""
        self._write("@suite.teardown")
        self._write("def _teardown():")
        self.indent += 1
        for stmt in node.body:
            self._visit(stmt)
        self.indent -= 1
        self._write("")
    
    def _visit_ClassDef(self, node: ClassDef) -> None:
        """生成类定义的 Cython 代码"""
        is_cdef = getattr(node, 'is_cdef', False)
        
        if is_cdef:
            # Cython cdef class（更高效但不支持动态属性）
            bases_str = ""
            if node.bases:
                base_names = []
                for base in node.bases:
                    if hasattr(base, 'id'):
                        base_names.append(base.id)
                    elif hasattr(base, 'name'):
                        base_names.append(base.name)
                if base_names:
                    bases_str = f"({', '.join(base_names)})"
            
            self._write(f"cdef class {node.name}{bases_str}:")
        else:
            # 普通 Python class
            bases_str = ""
            if node.bases:
                base_names = []
                for base in node.bases:
                    if hasattr(base, 'id'):
                        base_names.append(base.id)
                    elif hasattr(base, 'name'):
                        base_names.append(base.name)
                if base_names:
                    bases_str = f"({', '.join(base_names)})"
            
            self._write(f"class {node.name}{bases_str}:")
        
        self.indent += 1

        # 记录是否处于 cdef class，供方法生成时决定 cpdef/def
        prev_in_cdef = getattr(self, '_in_cdef_class', False)
        self._in_cdef_class = is_cdef

        # 分离方法和其他语句
        methods = []
        other_stmts = []

        for stmt in node.body:
            if isinstance(stmt, FuncDef):
                methods.append(stmt)
            else:
                other_stmts.append(stmt)

        # 处理类属性（非方法的语句）
        for stmt in other_stmts:
            self._visit(stmt)

        # 生成方法
        for method in methods:
            if hasattr(method, 'is_struct_method'):
                method.is_struct_method = True
            self._visit_FuncDef(method)

        # 如果没有任何内容，添加 pass
        if not node.body:
            self._write("pass")

        self.indent -= 1
        self._in_cdef_class = prev_in_cdef
        self._write("")
    
    def _find_used_module_vars(self, body: List[ASTNode]) -> Set[str]:
        """递归查找函数体中使用的模块级变量"""
        used_vars = set()
        
        def visit_node(node):
            if isinstance(node, Name):
                if node.id in self.module_vars:
                    used_vars.add(node.id)
            if isinstance(node, LetStmt):
                # 局部变量声明，从搜索中排除
                pass
            elif hasattr(node, '__dict__'):
                for attr in dir(node):
                    if not attr.startswith('_'):
                        value = getattr(node, attr)
                        if isinstance(value, ASTNode):
                            visit_node(value)
                        elif isinstance(value, list):
                            for item in value:
                                if isinstance(item, ASTNode):
                                    visit_node(item)
        
        for stmt in body:
            visit_node(stmt)
        
        return used_vars