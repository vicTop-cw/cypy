from typing import Dict, List, Any, Optional
from cypyc.parser.parser import ASTNode, Module, FuncDef, LetStmt, ReturnStmt, BinOp, UnaryOp, Call, Name, Constant, PointerType, CastExpr, StructDef, ClassDef, TraitDef, ExceptionDef, EnumDef, ComptimeFuncDef, ArrayPattern, SlicePattern, StructPattern, TypePattern, DictPattern, AsPattern, ExtractorPattern, RangePattern, IfStmt, LambdaExpr, GenericType, TypeClassDef, TypeClassImpl, DuckDef, DuckRequirement


class Type:
    def __init__(self, name: str, is_pointer: bool = False, is_ref: bool = False,
                 generic_params: List['Type'] = None, union_members: List['Type'] = None):
        self.name = name
        self.is_pointer = is_pointer
        self.is_ref = is_ref
        self.generic_params = generic_params or []
        # 联合类型成员（仅当本类型代表 UnionType 时有意义，名称仍为 object 以保持 codegen 兼容）
        self.union_members = union_members or []

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return False
        return (self.name == other.name and
                self.is_pointer == other.is_pointer and
                self.is_ref == other.is_ref and
                self.generic_params == other.generic_params)

    def __repr__(self) -> str:
        prefix = ""
        if self.is_ref:
            prefix = "ref "
        if self.is_pointer:
            prefix = "*"
        if self.generic_params:
            params_str = "[" + ", ".join(str(p) for p in self.generic_params) + "]"
            return f"{prefix}{self.name}{params_str}"
        return f"{prefix}{self.name}"


class TypeChecker:
    def __init__(self):
        self.type_map: Dict[str, Type] = {
            "int": Type("int"),
            "float": Type("float"),
            "double": Type("double"),
            "bool": Type("bool"),
            "str": Type("str"),
            "None": Type("None"),
            "object": Type("object"),
            "Any": Type("object"),  # Scala 风格的 Any 类型
            "Nothing": Type("Nothing"),  # Scala 风格的底部类型
            "Null": Type("Null"),  # Scala 风格的空值类型
            # 内置容器类型
            "dict": Type("dict"),
            "set": Type("set"),
            "tuple": Type("tuple"),
            # 内置异常类型
            "Exception": Type("Exception"),
            "ValueError": Type("ValueError"),
            "TypeError": Type("TypeError"),
            "RuntimeError": Type("RuntimeError"),
            "IndexError": Type("IndexError"),
            "KeyError": Type("KeyError"),
            "AttributeError": Type("AttributeError"),
            "IOError": Type("IOError"),
            "OSError": Type("OSError"),
            "FileNotFoundError": Type("FileNotFoundError"),
            "PermissionError": Type("PermissionError"),
            "OverflowError": Type("OverflowError"),
            "ZeroDivisionError": Type("ZeroDivisionError"),
            "KeyboardInterrupt": Type("KeyboardInterrupt"),
            "StopIteration": Type("StopIteration"),
            "AssertionError": Type("AssertionError"),
            "NotImplementedError": Type("NotImplementedError"),
        }
        self.mutable_map: Dict[str, bool] = {}  # 跟踪变量是否可变
        self.current_function_return_type: Optional[Type] = None
        self.errors: List[str] = []
        # 魔法方法注册表：记录类型的 __cast__/__try_cast__ 等方法
        self.magic_methods: Dict[str, Dict[str, FuncDef]] = {}  # {type_name: {method_name: FuncDef}}
        # 隐式复制标记：当变量需要 __implicit_copy__ 时设为 True
        self._implicit_copy_needed: bool = False
        # 隐式转换标记：{var_name: (source_type, target_type)}
        self._implicit_conversions: Dict[str, tuple] = {}
        # 结构体定义注册表
        self.struct_defs: Dict[str, StructDef] = {}
        # 类定义注册表
        self.class_defs: Dict[str, ClassDef] = {}
        # 继承链：{child_type: [parent_types...]}
        self.inheritance_map: Dict[str, List[str]] = {}
        # 是否在 meta block 中（meta block 中允许前向引用）
        self.in_meta_block = False
        # 作为类型注解使用时视为已定义的内建/泛型类型名
        self._known_type_names = {
            'Callable', 'callable', 'Tuple', 'Optional', 'Union', 'List',
            'Dict', 'Set', 'Generator', 'Iterable', 'Iterator', 'Sequence',
        }
        # 函数定义注册表（用于泛型函数类型推断）
        self.func_defs: Dict[str, FuncDef] = {}
        # Trait 定义注册表（用于泛型约束检查）
        self.trait_defs: Dict[str, Any] = {}
        # Trait 实现注册表（用于检查类型是否实现了 trait）
        self.trait_impls: Dict[str, List[str]] = {}  # {trait_name: [type_name1, type_name2, ...]}
        # 类型别名定义注册表（用于泛型类型别名替换）
        self.type_alias_defs: Dict[str, Any] = {}  # {alias_name: TypeAlias node}
        # Duck 约束注册表（用于鸭子类型约束检查）
        self.duck_constraints: Dict[str, Dict[str, Any]] = {}  # {constraint_name: constraint_info}
        # 编译期函数注册表（用于类型检查和求值）
        self.comptime_funcs: Dict[str, ComptimeFuncDef] = {}  # {func_name: ComptimeFuncDef}
        # 策略栈（用于递归防护）
        self.active_strategies: List[str] = []
        self.strategy_depth: int = 0
        self.max_strategy_depth: int = 5
        # 是否在收集阶段（第一遍）
        self.collecting: bool = False
        # 类型类注册表（Type Class）
        # {type_class_name: {param_name: TypeConstraint}}
        self.type_classes: Dict[str, Dict[str, Any]] = {}
        # 类型类实例注册表
        # {(type_class_name, type_name): ImplDef}
        self.type_class_instances: Dict[tuple, Any] = {}
        # 类型类方法解析缓存
        # {(type_class_name, method_name, type_name): FuncDef}
        self.type_class_method_cache: Dict[tuple, FuncDef] = {}
        # 双向类型检查：期望类型栈
        self._expected_type_stack: List[Type] = []

    def _enter_strategy(self, strategy_name: str) -> bool:
        """进入策略，返回是否允许执行（用于递归防护）"""
        if strategy_name in self.active_strategies:
            return False
        if self.strategy_depth >= self.max_strategy_depth:
            return False
        self.active_strategies.append(strategy_name)
        self.strategy_depth += 1
        return True
    
    def _exit_strategy(self, strategy_name: str) -> None:
        """退出策略"""
        if strategy_name in self.active_strategies:
            self.active_strategies.remove(strategy_name)
        if self.strategy_depth > 0:
            self.strategy_depth -= 1

    # ========== Type Class 支持 ==========

    def register_type_class(self, name: str, params: Dict[str, Any]) -> None:
        """注册类型类定义
        
        Args:
            name: 类型类名称
            params: 类型参数约束 {param_name: constraint}
        """
        self.type_classes[name] = params

    def register_type_class_instance(self, type_class_name: str, type_name: str, impl_node: Any) -> None:
        """注册类型类实例
        
        Args:
            type_class_name: 类型类名称
            type_name: 实现类型
            impl_node: impl 节点
        """
        key = (type_class_name, type_name)
        if key in self.type_class_instances:
            # 检查歧义
            self.errors.append(
                f"Ambiguous type class instance: multiple implementations of "
                f"'{type_class_name}' for type '{type_name}'"
            )
        else:
            self.type_class_instances[key] = impl_node
            # 清除方法缓存
            self.type_class_method_cache.clear()

    def resolve_type_class_method(self, type_class_name: str, method_name: str, type_name: str) -> Optional[FuncDef]:
        """解析类型类方法调用
        
        查找顺序：
        1. 缓存查找
        2. 精确类型查找
        3. 父类型查找（继承层次）
        4. 默认实现查找
        
        Args:
            type_class_name: 类型类名称
            method_name: 方法名
            type_name: 当前类型
            
        Returns:
            找到的方法定义，或 None
        """
        cache_key = (type_class_name, method_name, type_name)
        if cache_key in self.type_class_method_cache:
            return self.type_class_method_cache[cache_key]
        
        # 精确类型查找
        impl_key = (type_class_name, type_name)
        if impl_key in self.type_class_instances:
            impl = self.type_class_instances[impl_key]
            method = self._find_method_in_node(impl, method_name)
            if method:
                self.type_class_method_cache[cache_key] = method
                return method
        
        # 父类型查找（支持继承层次的类型类解析）
        if type_name in self.inheritance_map:
            for parent in self.inheritance_map[type_name]:
                parent_key = (type_class_name, parent)
                if parent_key in self.type_class_instances:
                    # 检查是否有更具体的实现（避免歧义）
                    has_more_specific = False
                    for t in self.type_class_instances:
                        if t[0] == type_class_name and t[1] != parent:
                            if parent in self.inheritance_map.get(t[1], []):
                                has_more_specific = True
                                break
                    
                    if not has_more_specific:
                        impl = self.type_class_instances[parent_key]
                        method = self._find_method_in_node(impl, method_name)
                        if method:
                            self.type_class_method_cache[cache_key] = method
                            return method
        
        return None

    def _find_method_in_node(self, node: Any, method_name: str) -> Optional[FuncDef]:
        """在 impl 节点中查找指定方法
        
        Args:
            node: impl 节点
            method_name: 方法名
            
        Returns:
            方法定义，或 None
        """
        if hasattr(node, 'methods'):
            for method in node.methods:
                if hasattr(method, 'name') and method.name == method_name:
                    return method
        if hasattr(node, 'body'):
            for stmt in node.body:
                if hasattr(stmt, 'name') and stmt.name == method_name:
                    return stmt
        return None

    def check_type_class_resolution(self, type_class_name: str, type_name: str) -> bool:
        """检查类型是否实现了指定的类型类
        
        Args:
            type_class_name: 类型类名称
            type_name: 类型名称
            
        Returns:
            True 如果类型实现了该类型类
        """
        # 检查直接实现
        if (type_class_name, type_name) in self.type_class_instances:
            return True
        
        # 检查父类型实现
        if type_name in self.inheritance_map:
            for parent in self.inheritance_map[type_name]:
                if (type_class_name, parent) in self.type_class_instances:
                    return True
        
        return False

    def check(self, node: ASTNode) -> Dict[str, 'Type']:
        self._visit(node)
        # 所有 duck 约束定义完成后，统一校验引用（允许跨 meta 块前向引用）
        self._validate_duck_references()
        return self.type_map

    def _validate_duck_references(self) -> None:
        """校验 duck 约束之间的引用是否都已定义（在全部定义完成后执行，
        以支持前向引用与跨 meta 块引用）

        知名 duck 约束（见 _KNOWN_DUCK_NAMES，如 Sized）视为内建，
        即使未在当前文件显式定义也允许被引用。
        """
        for name, info in self.duck_constraints.items():
            for req in info.get("requirements", []) or []:
                if getattr(req, 'kind', None) == "reference" and \
                        req.name not in self.duck_constraints and \
                        req.name not in self._KNOWN_DUCK_NAMES:
                    self.errors.append(
                        f"Duck constraint '{name}' references undefined constraint '{req.name}' at line {req.line}"
                    )

    def _visit(self, node: ASTNode) -> Optional[Type]:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        return self._visit_children(node)

    def _visit_children(self, node: ASTNode) -> Optional[Type]:
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)
        return None

    def _visit_Module(self, node: Module) -> None:
        # 第一遍：收集结构体、类和函数定义（不检查函数体）
        self.collecting = True
        for stmt in node.body:
            if isinstance(stmt, StructDef):
                self.struct_defs[stmt.name] = stmt
                # 初始化魔法方法注册表
                if stmt.name not in self.magic_methods:
                    self.magic_methods[stmt.name] = {}
                # 收集结构体中的魔法方法（从 methods 中收集）
                for method in stmt.methods:
                    if isinstance(method, FuncDef):
                        if method.name.startswith('__') and method.name.endswith('__'):
                            self.magic_methods[stmt.name][method.name] = method
                # 注册结构体类型到类型映射
                self.type_map[stmt.name] = Type(stmt.name)
            elif isinstance(stmt, ClassDef):
                self.class_defs[stmt.name] = stmt
                if stmt.name not in self.magic_methods:
                    self.magic_methods[stmt.name] = {}
                for body_stmt in stmt.body:
                    if isinstance(body_stmt, FuncDef):
                        if body_stmt.name.startswith('__') and body_stmt.name.endswith('__'):
                            self.magic_methods[stmt.name][body_stmt.name] = body_stmt
                # 注册类类型到类型映射
                self.type_map[stmt.name] = Type(stmt.name)
            elif isinstance(stmt, FuncDef):
                # 注册函数定义（用于泛型函数类型推断）
                self.func_defs[stmt.name] = stmt
                # 在处理返回类型之前，先注册泛型参数作为类型
                for param in getattr(stmt, 'generic_params', []):
                    self.type_map[param] = Type(param)
                # 注册函数名到类型映射（函数类型用返回类型表示）
                return_type = self._get_type_from_node(stmt.return_type)
                if return_type:
                    self.type_map[stmt.name] = return_type
                else:
                    # 检查是否有 @python 装饰器，如果有但没有返回类型，使用 object 类型
                    has_python_decorator = False
                    if hasattr(stmt, 'decorators') and stmt.decorators:
                        for decorator in stmt.decorators:
                            decorator_name = getattr(decorator.name, 'id', str(decorator.name))
                            if decorator_name == 'python':
                                has_python_decorator = True
                                break
                    # 所有函数都必须注册到 type_map，确保后续引用时能找到
                    self.type_map[stmt.name] = Type("object")
            elif isinstance(stmt, TraitDef):
                # 注册 trait 定义
                self.trait_defs[stmt.name] = stmt
                # 初始化 trait 实现列表
                if stmt.name not in self.trait_impls:
                    self.trait_impls[stmt.name] = []
                # 注册泛型参数作为类型
                for param in getattr(stmt, 'generic_params', []):
                    self.type_map[param] = Type(param)
                # 注册 trait 类型到类型映射
                self.type_map[stmt.name] = Type(stmt.name)
            elif hasattr(stmt, 'kind') and stmt.kind == 'TypeClassDef':
                # 注册 TypeClass 定义
                self.register_type_class(stmt.name, getattr(stmt, 'generic_constraints', {}))
                # 注册泛型参数作为类型
                for param in getattr(stmt, 'generic_params', []):
                    self.type_map[param] = Type(param)
                # 注册 TypeClass 类型到类型映射
                self.type_map[stmt.name] = Type(stmt.name)
            elif isinstance(stmt, ExceptionDef):
                # 注册异常类型定义
                self.type_map[stmt.name] = Type(stmt.name)
            elif hasattr(stmt, 'kind') and stmt.kind == 'ImplStmt':
                # 注册 trait 实现
                trait_name = stmt.trait_name
                for_type_name = getattr(stmt.for_type, 'id', str(stmt.for_type))
                if trait_name not in self.trait_impls:
                    self.trait_impls[trait_name] = []
                if for_type_name not in self.trait_impls[trait_name]:
                    self.trait_impls[trait_name].append(for_type_name)
            elif hasattr(stmt, 'kind') and stmt.kind == 'TypeAlias':
                # 注册类型别名
                target_type = self._get_type_from_node(stmt.target)
                if target_type:
                    self.type_map[stmt.name] = target_type
            elif isinstance(stmt, EnumDef):
                # 注册枚举类型
                self.type_map[stmt.name] = Type(stmt.name)
            elif isinstance(stmt, ComptimeFuncDef):
                # 注册编译期函数
                self.comptime_funcs[stmt.name] = stmt
                # 将编译期函数名注册到类型映射中，以便在 comptime 表达式中调用
                return_type = self._get_type_from_node(stmt.return_type)
                if return_type:
                    self.type_map[stmt.name] = return_type
                else:
                    self.type_map[stmt.name] = Type("object")
        
        # 第二遍：检查所有语句（包括函数体）
        self.collecting = False
        for stmt in node.body:
            self._visit(stmt)

    def _visit_ComptimeFuncDef(self, node: ComptimeFuncDef) -> None:
        """类型检查编译期函数"""
        # 编译期函数的类型检查与普通函数类似，但不生成运行时代码
        old_type_map = self.type_map.copy()
        old_mutable_map = self.mutable_map.copy()
        
        # 注册参数类型
        for param in node.params:
            param_type = self._get_type_from_node(param.type_annotation)
            if param_type:
                self.type_map[param.name] = param_type
            else:
                self.type_map[param.name] = Type("object")
        
        # 检查函数体
        for stmt in node.body:
            self._visit(stmt)
        
        # 恢复旧的映射
        self.type_map = old_type_map
        self.mutable_map = old_mutable_map
    
    def _visit_FuncDef(self, node: FuncDef) -> None:
        # 检查是否有 @python 装饰器
        has_python_decorator = False
        if hasattr(node, 'decorators') and node.decorators:
            for decorator in node.decorators:
                decorator_name = getattr(decorator.name, 'id', str(decorator.name))
                if decorator_name == 'python':
                    has_python_decorator = True
                    break
        
        # 如果是 @python 装饰的函数，跳过类型检查（允许 Python 动态特性）
        if has_python_decorator:
            # 只注册函数名到类型映射，不检查函数体
            return_type = self._get_type_from_node(node.return_type)
            if return_type:
                self.type_map[node.name] = return_type
            else:
                self.type_map[node.name] = Type("object")
            return
        
        old_return_type = self.current_function_return_type
        self.current_function_name = node.name
        
        # 保存旧的类型和可变性映射，进入新作用域
        old_type_map = self.type_map.copy()
        old_mutable_map = self.mutable_map.copy()

        # 注册泛型参数作为类型（在处理返回类型之前）
        for param in getattr(node, 'generic_params', []):
            self.type_map[param] = Type(param)

        # 现在可以处理返回类型了
        return_type = self._get_type_from_node(node.return_type)
        self.current_function_return_type = return_type

        # 在保存旧映射之前，将函数名注册到全局作用域
        if return_type:
            old_type_map[node.name] = return_type

        for param in node.params:
            param_type = self._get_type_from_node(param.type_annotation)
            if param_type:
                # 如果参数是 ref，检查类型合法性
                if getattr(param, 'is_ref', False):
                    # 检查基础类型是否为Python对象类型（引用不支持Python对象）
                    python_types = {'str', 'list', 'dict', 'tuple', 'object', 'set'}
                    if param_type.name in python_types:
                        self.errors.append(f"Cannot declare reference to Python object type '{param_type.name}' for parameter '{param.name}' at {param.line}:{param.col}")
                    # 检查基础类型是否已经是引用类型（不允许 ref ref T）
                    if param_type.is_ref:
                        self.errors.append(f"Cannot declare reference to reference type for parameter '{param.name}' at {param.line}:{param.col}")
                    param_type = Type(param_type.name, is_ref=True)
                self.type_map[param.name] = param_type
            else:
                # 即使没有类型注解，也注册为 object 类型，确保参数在作用域中可见
                self.type_map[param.name] = Type("object")

        # 存储所有 return 语句的引用，用于后续类型推断
        return_stmts = []
        
        def collect_return_stmts(stmts):
            """递归收集所有 return 语句节点（不访问）"""
            for stmt in stmts:
                if isinstance(stmt, ReturnStmt) and stmt.value:
                    return_stmts.append(stmt)
                elif isinstance(stmt, IfStmt):
                    # IfStmt: 收集 if 分支和 else 分支中的 return
                    collect_return_stmts(stmt.body)
                    if stmt.orelse:
                        collect_return_stmts(stmt.orelse)
                elif hasattr(stmt, 'body'):
                    # 其他有 body 属性的语句（如 WhileStmt, ForStmt 等）
                    collect_return_stmts(stmt.body)

        # 收集 return 语句节点
        collect_return_stmts(node.body)
        
        # 访问函数体（这会在 type_map 中注册变量）
        for stmt in node.body:
            self._visit(stmt)

        # 如果没有显式返回类型注解，尝试从 return 语句推断
        if not return_type and return_stmts:
            # 函数体已访问，变量已在 type_map 中，可以安全地推断 return 类型
            return_types = []
            for ret_stmt in return_stmts:
                # 直接使用 body 访问阶段记录的返回类型，避免二次访问导致的作用域问题
                ret_type = getattr(ret_stmt, '_inferred_return_type', None)
                if ret_type is None and ret_stmt.value is not None:
                    ret_type = self._visit(ret_stmt.value)
                if ret_type:
                    return_types.append(ret_type)
            
            if return_types:
                inferred_return = self._find_common_type(return_types)
                self.current_function_return_type = inferred_return
                old_type_map[node.name] = inferred_return
            else:
                old_type_map[node.name] = Type("object")
        elif not return_type:
            # 没有 return 语句，推断为 None
            self.current_function_return_type = Type("None")
            old_type_map[node.name] = Type("None")

        # 恢复旧的映射，退出作用域
        self.type_map = old_type_map
        self.mutable_map = old_mutable_map
        self.current_function_return_type = old_return_type

    def _visit_LambdaExpr(self, node: LambdaExpr) -> Optional[Type]:
        """类型检查 Lambda 表达式
        
        Lambda 参数类型推断策略：
        1. 如果参数有类型注解，使用注解的类型
        2. 如果参数没有类型注解，初始设为 object 类型
        3. 从 Lambda 函数体的使用上下文推断参数类型（双向类型检查）
        
        Lambda 返回类型推断策略：
        1. 从函数体表达式的类型推断
        2. 如果函数体是语句块，从 return 语句推断
        """
        # 保存旧的类型映射
        old_type_map = self.type_map.copy()
        old_mutable_map = self.mutable_map.copy()
        old_return_type = self.current_function_return_type
        
        # 处理参数
        param_types = []
        for param in node.params:
            param_type = self._get_type_from_node(param.type_annotation)
            if param_type:
                param_types.append(param_type)
                self.type_map[param.name] = param_type
            else:
                # 无类型注解的参数，初始推断为 object
                param_types.append(Type("object"))
                self.type_map[param.name] = Type("object")
        
        # 推断返回类型
        return_type = None
        if isinstance(node.body, ASTNode):
            return_type = self._visit(node.body)
        elif hasattr(node.body, '__iter__'):
            # 语句块：收集 return 语句
            return_types = []
            
            def collect_returns(stmts):
                for stmt in stmts:
                    if isinstance(stmt, ReturnStmt) and stmt.value:
                        # 优先使用 body 访问阶段记录的返回类型，避免二次访问的作用域问题
                        ret_type = getattr(stmt, '_inferred_return_type', None)
                        if ret_type is None:
                            ret_type = self._visit(stmt.value)
                        if ret_type:
                            return_types.append(ret_type)
            
            collect_returns(node.body)
            
            if return_types:
                return_type = self._find_common_type(return_types)
            else:
                return_type = Type("None")
        
        if not return_type:
            return_type = Type("object")
        
        self.current_function_return_type = return_type
        
        # 恢复旧的映射
        self.type_map = old_type_map
        self.mutable_map = old_mutable_map
        self.current_function_return_type = old_return_type
        
        # Lambda 表达式的类型是函数类型
        # 使用 => 表示函数类型，如 (int) => int
        return Type("lambda", generic_params=[*param_types, return_type])

    def _visit_LetStmt(self, node: LetStmt) -> None:
        # 元组解包：let (a, b) = ... 时 node.name 为列表
        if isinstance(node.name, list):
            declared_type = self._get_type_from_node(node.type_annotation)
            value_type = self._visit(node.value) if node.value else None
            element_types = []
            if value_type and value_type.name == 'tuple' and value_type.generic_params:
                element_types = value_type.generic_params
            for i, nm in enumerate(node.name):
                if declared_type:
                    self.type_map[nm] = declared_type
                elif i < len(element_types):
                    self.type_map[nm] = element_types[i]
                else:
                    self.type_map[nm] = Type("object")
                self.mutable_map[nm] = node.mutable
            return
        declared_type = self._get_type_from_node(node.type_annotation)
        if node.value:
            value_type = self._visit(node.value)
            if declared_type and value_type and declared_type != value_type:
                # 值为 object/Any（动态类型或未知返回）时，采用声明类型，避免误报
                if value_type.name in ('object', 'Any'):
                    self.type_map[node.name] = declared_type
                # 联合类型：值必须匹配任一成员，否则报错（必须在 object 宽松分支之前判定）
                elif declared_type.union_members:
                    if self._type_in_union(value_type, declared_type):
                        self.type_map[node.name] = declared_type
                    else:
                        self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
                # object/Any 类型可以接受任何类型赋值（Scala 风格）
                elif declared_type.name == 'object' or declared_type.name == 'Any':
                    self.type_map[node.name] = declared_type
                # 允许指针类型匹配（void* 可以赋值给 int* 等）
                elif declared_type.is_pointer and value_type.is_pointer:
                    self.type_map[node.name] = declared_type
                # 同名单容器（list/dict/tuple/set/Pair 等），声明带参数时采用声明的精确类型。
                # 覆盖：空容器构造器 list[object]、嵌套 list[list[object]]、dict/set/Pair 的无参形式等。
                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self.type_map[node.name] = declared_type
                # 允许泛型类型兼容：list 与 list[Type] 兼容（使用更具体的类型）
                elif declared_type.name == value_type.name and not declared_type.generic_params and value_type.generic_params:
                    self.type_map[node.name] = value_type  # 使用带 generic_params 的更具体类型
                # 允许数值类型的隐式转换：bool → int → float → double
                else:
                    numeric_types = {'bool', 'int', 'float', 'double'}
                    if declared_type.name in numeric_types and value_type.name in numeric_types:
                        type_order = ['bool', 'int', 'float', 'double']
                        value_idx = type_order.index(value_type.name)
                        target_idx = type_order.index(declared_type.name)
                        if value_idx <= target_idx:
                            self.type_map[node.name] = declared_type
                        else:
                            self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
                    elif value_type.name == 'None' or value_type.name == 'Null':
                        # None/Null 可以赋值给任何类型
                        self.type_map[node.name] = declared_type
                    elif declared_type.name == 'object' or declared_type.name == 'Any':
                        # object 类型可以接受任何类型
                        self.type_map[node.name] = declared_type
                    else:
                        # 检查是否有 __implicit_into__ 方法可以转换
                        if self._check_implicit_conversion(value_type, declared_type, node):
                            self.type_map[node.name] = declared_type
                        # 检查是否有 __guarded_pred__/__guarded_action__ 守卫策略
                        elif self._check_guarded_conversion(value_type, declared_type, node):
                            self.type_map[node.name] = declared_type
                        else:
                            self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
            elif not declared_type and value_type:
                # 从初始化值推断类型
                # 检查是否需要 __implicit_copy__（当赋值给不同变量时）
                if value_type.name in self.magic_methods:
                    magic_map = self.magic_methods[value_type.name]
                    if '__implicit_copy__' in magic_map:
                        # 标记需要生成隐式复制代码
                        self.type_map[node.name] = value_type
                        self._implicit_copy_needed = True
                    else:
                        self.type_map[node.name] = value_type
                else:
                    self.type_map[node.name] = value_type
        if declared_type and node.name not in self.type_map:
            self.type_map[node.name] = declared_type
        # 兜底：如果变量名还没有被注册，注册为 object 类型
        if node.name not in self.type_map:
            self.type_map[node.name] = Type("object")
        # 跟踪变量可变性（let = 不可变, var = 可变）
        self.mutable_map[node.name] = node.mutable

    def _visit_ReturnStmt(self, node: ReturnStmt) -> Optional[Type]:
        if node.value:
            value_type = self._visit(node.value)
            # 记录推断出的返回类型，供后续返回类型推断阶段直接读取，
            # 避免二次访问 return 表达式时遇到的作用域已切换问题（闭包/赋值变量）。
            node._inferred_return_type = value_type
            if self.current_function_return_type and value_type:
                # 联合返回类型：显式校验成员，避免被下面的 object 宽松分支放过
                if self.current_function_return_type.union_members:
                    if self._type_in_union(value_type, self.current_function_return_type):
                        return value_type
                    self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got {value_type} at {node.line}:{node.col}")
                    return value_type
                target_name = self.current_function_return_type.name
                # 声明为 object 时接受任意返回类型
                if target_name == 'object':
                    return value_type
                # 返回值为 object（无法精确推断）时放行，避免误报
                if value_type.name in ('object', 'Any'):
                    return value_type
                # 返回值是容器（含空容器构造器 list[object]、无参 dict/set/Pair、嵌套
                # list[list[object]]、含 None/object 参数的元组等），而声明为带参数的
                # 同名容器时，采用声明的精确类型，避免误报
                if (target_name == value_type.name
                        and target_name in ('list', 'dict', 'tuple', 'set', 'Pair', 'Array')
                        and self.current_function_return_type.generic_params):
                    return value_type
                # 裸容器声明（如 list）兼容其带参版本（list[object] 等）
                if (target_name in ('list', 'dict', 'tuple', 'set', 'Pair', 'Array')
                        and value_type.name == target_name
                        and value_type.generic_params):
                    return value_type
                # 返回值类型实现了声明的 trait（子类型关系），允许
                if (target_name in self.trait_defs
                        and value_type.name in self.trait_impls.get(target_name, [])):
                    return value_type
                # 允许数值类型的隐式转换：bool → int → float → double
                numeric_types = {'bool', 'int', 'float', 'double'}
                if target_name in numeric_types and value_type.name in numeric_types:
                    type_order = ['bool', 'int', 'float', 'double']
                    value_idx = type_order.index(value_type.name)
                    target_idx = type_order.index(target_name)
                    if value_idx > target_idx:
                        # 向下转换需要显式转换
                        self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got {value_type} at {node.line}:{node.col}")
                elif self.current_function_return_type != value_type:
                    self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got {value_type} at {node.line}:{node.col}")
            return value_type
        # 无返回值，检查是否是 void 返回类型
        if self.current_function_return_type and self.current_function_return_type.name != 'None':
            self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got None at {node.line}:{node.col}")
        return Type("None")

    def _visit_BinOp(self, node: BinOp) -> Optional[Type]:
        left_type = self._visit(node.left)
        right_type = self._visit(node.right)

        if left_type and right_type:
            # 比较 / 相等 / 成员 / 身份 运算结果恒为 bool
            if node.op in ('==', '!=', '<', '>', '<=', '>=', 'in', 'is',
                           'not in', 'is not', 'not is'):
                return Type('bool')

            # 逻辑运算（and / or）结果用于布尔上下文，放宽返回 object
            if node.op in ('and', 'or'):
                return Type('object')

            # 渐进式类型：允许 object 类型参与任何操作（动态行为）
            if left_type.name == 'object' or right_type.name == 'object':
                return Type('object')

            # 数值类型可以隐式转换（bool → int → float → double）
            numeric_types = {'bool', 'int', 'float', 'double'}
            if left_type.name in numeric_types and right_type.name in numeric_types:
                # 运算结果取两个操作数中更高的类型
                type_order = ['bool', 'int', 'float', 'double']
                result_type = type_order[max(type_order.index(left_type.name),
                                             type_order.index(right_type.name))]
                return Type(result_type)

            # 字符串乘法：str * int -> str（重复字符串）
            if node.op == '*' and left_type.name == 'str' and right_type.name == 'int':
                return Type('str')

            # 列表乘法：list * int -> list（重复列表）
            if node.op == '*' and left_type.name == 'list' and right_type.name == 'int':
                return left_type

            # 序列拼接：list + list, str + str, tuple + tuple
            if node.op == '+' and left_type.name == right_type.name:
                if left_type.name in {'list', 'str', 'tuple'}:
                    return left_type

            # 类型不兼容检查：仅当两个操作数均为已知内建类型且组合非法时报错。
            # object/Any（动态类型）与自定义类一律跳过，避免误报。
            _known = {'int', 'float', 'complex', 'double', 'str', 'list',
                      'tuple', 'set', 'dict', 'bool', 'bytes', 'bytearray'}
            if left_type.name in _known and right_type.name in _known:
                _num = {'bool', 'int', 'float', 'complex', 'double'}
                _seq = {'list', 'tuple', 'set'}
                if node.op == '+':
                    _ok = (left_type.name in _num and right_type.name in _num) \
                        or (left_type.name == 'str' and right_type.name == 'str') \
                        or (left_type.name in _seq and right_type.name in _seq)
                    if not _ok:
                        self.errors.append(
                            f"Type mismatch: operator '+' cannot be applied to "
                            f"{left_type.name} and {right_type.name} (line {node.line})")
                elif node.op == '*':
                    _ok = (left_type.name in _num and right_type.name in _num) \
                        or (left_type.name == 'str' and right_type.name in _num) \
                        or (left_type.name in _seq and right_type.name in _num)
                    if not _ok:
                        self.errors.append(
                            f"Type mismatch: operator '*' cannot be applied to "
                            f"{left_type.name} and {right_type.name} (line {node.line})")
                elif node.op in ('-', '/', '//', '%', '**'):
                    if not (left_type.name in _num and right_type.name in _num):
                        self.errors.append(
                            f"Type mismatch: operator '{node.op}' cannot be applied to "
                            f"{left_type.name} and {right_type.name} (line {node.line})")

            # 其他运算（如 ** 等）对未知类型组合放宽处理，返回 object 而不报错
            return Type('object')

        return left_type if left_type is not None else right_type

    def _visit_UnaryOp(self, node: UnaryOp) -> Optional[Type]:
        return self._visit(node.operand)

    def _visit_Call(self, node: Call) -> Optional[Type]:
        func_type = self._visit(node.func)
        # 处理参数：支持位置参数和关键字参数
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                self._visit(arg[1])
            else:
                # 位置参数
                self._visit(arg)
        
        # 如果 func 是简单名称
        if hasattr(node.func, 'id'):
            func_name = node.func.id
            
            # 检查是否是泛型函数调用（需要推断类型参数）
            if func_name in self.func_defs:
                func_def = self.func_defs[func_name]
                generic_params = getattr(func_def, 'generic_params', [])
                generic_constraints = getattr(func_def, 'generic_constraints', {})
                
                if generic_params:
                    # 双向检查：尝试从上下文获取期望类型辅助推断
                    expected = self._get_expected_type_from_context(node)
                    if expected:
                        # 使用期望类型辅助推断
                        inferred_types = self._infer_generic_types_with_expected(
                            func_def, node.args, generic_params, expected
                        )
                    else:
                        # 使用统一化算法推断泛型参数类型
                        inferred_types = self._infer_generic_types(func_def, node.args, generic_params)
                    
                    # 增强的泛型约束检查 - 支持多重约束和 F-bounded 多态
                    for param, inferred_type in inferred_types.items():
                        if param in generic_constraints:
                            constraint_ast = generic_constraints[param]
                            self._check_generic_constraint(param, inferred_type, constraint_ast, node)
                    
                    # 返回推断后的函数返回类型
                    if func_def.return_type:
                        return_type = self._get_type_from_node(func_def.return_type)
                        if return_type:
                            # 替换返回类型中的所有泛型参数
                            return self._substitute_generic_params(return_type, inferred_types)
                        return Type("object")
                    return Type("object")
            
            # 先检查是否是用户定义的函数
            if func_name in self.type_map:
                t = self.type_map[func_name]
                # 变量类型为 Callable[...] 时，调用应返回其返回类型（最后一个类型参数）
                if getattr(t, 'name', None) == 'Callable':
                    args = getattr(t, 'args', None) or getattr(t, 'generic_params', None)
                    if args:
                        ret = args[-1]
                        # args 已是 Type 对象（由 _get_type_from_node 转换而来）
                        if isinstance(ret, Type):
                            return ret
                        return self._get_type_from_node(ret)
                return t
            
            # 内置函数
            if func_name == 'malloc':
                return Type("void", is_pointer=True)
            elif func_name == 'sizeof':
                return Type("int")
            elif func_name == 'addr':
                # addr() 只能接受原生类型或指针类型，不能接受 Python 对象
                if node.args:
                    arg_type = self._visit(node.args[0])
                    if arg_type:
                        # 允许的类型：原生类型（int, float, double, bool）和指针类型
                        allowed_types = ['int', 'float', 'double', 'bool']
                        if arg_type.is_pointer or arg_type.name in allowed_types:
                            return Type("void", is_pointer=True)
                        else:
                            # 放宽：允许对普通类型取地址（示意性 demo 不强制）
                            pass
                return Type("void", is_pointer=True)
            # 内置类型转换函数
            elif func_name in ['int', 'float', 'double', 'str', 'bool']:
                return Type(func_name)
            # list() 函数：创建列表
            elif func_name == 'list':
                if node.args:
                    arg_type = self._visit(node.args[0])
                    if arg_type:
                        # 如果参数已经是列表类型，返回相同类型的列表
                        if arg_type.name == 'list' and arg_type.generic_params:
                            return Type("list", generic_params=arg_type.generic_params)
                        # 如果参数是可迭代的，返回以该类型为元素的列表
                        return Type("list", generic_params=[arg_type])
                return Type("list", generic_params=[Type("object")])
            # 内置函数
            elif func_name == 'print':
                return Type("None")
            elif func_name == 'len':
                return Type("int")
            # range() 返回可迭代的整数序列
            elif func_name == 'range':
                return Type("list", generic_params=[Type("int")])
            elif func_name == 'type':
                # type(expr) 返回表达式的类型
                if node.args:
                    arg_type = self._visit(node.args[0])
                    return arg_type
                return Type("None")
        
        # 如果 func 是属性访问形式（如 math.cos(x)），处理常见模块函数
        if hasattr(node.func, 'value') and hasattr(node.func, 'attr'):
            module_name = node.func.value.id if hasattr(node.func.value, 'id') else None
            attr_name = node.func.attr
            
            # 常见数学模块函数映射
            math_functions = {
                'sqrt': Type("float"),
                'sin': Type("float"),
                'cos': Type("float"),
                'tan': Type("float"),
                'log': Type("float"),
                'exp': Type("float"),
                'abs': Type("float"),
                'pow': Type("float"),
                'pi': Type("float"),
                'e': Type("float"),
                'floor': Type("int"),
                'ceil': Type("int"),
                'sqrt': Type("float"),
                'sin': Type("float"),
                'cos': Type("float"),
            }
            
            if module_name == 'math' and attr_name in math_functions:
                return math_functions[attr_name]
        
        # 如果 func 是属性访问（方法调用），返回属性类型
        if func_type:
            return func_type
        
        # 无法确定调用返回类型时，回退为 object（而非 None），
        # 避免“返回类型不匹配”的误报（分析器无法为未知方法/函数证明具体类型）
        return Type("object")

    def _visit_Name(self, node: Name) -> Optional[Type]:
        if node.id in self.type_map:
            return self.type_map[node.id]
        # 检查是否是内置类型、常量和内置函数
        builtin_types = ['int', 'float', 'double', 'bool', 'str', 'None', 'Exception', 'list',
                         'dict', 'set', 'tuple', 'object', 'Any', 'Nothing', 'Null',
                         'Callable', 'callable']
        builtin_constants = ['True', 'False', '__main__', 'null']
        builtin_functions = ['print', 'len', 'malloc', 'free', 'sizeof', 'addr', 'ord', 'range', 'type',
                             'sorted', 'isinstance', 'getattr', 'hash', 'super', 'abs', 'min', 'max',
                             'sum', 'any', 'all', 'enumerate', 'zip', 'map', 'filter', 'reversed',
                             'bool', 'int', 'float', 'str', 'list', 'dict', 'set', 'tuple']
        # 模块级魔法变量
        module_magic = ['__name__']
        # 通配符 _ 在 match case 中不报错
        if node.id == '_':
            return Type("object")
        # 宏调用形式：name!（如 double_value!）去掉 ! 后查宏定义
        if isinstance(node.id, str) and node.id.endswith('!'):
            base = node.id[:-1]
            if base in self.type_map or base in self._known_type_names:
                return Type("object")
            node = Name(base, node.line, node.col)
        if node.id in builtin_types:
            return Type(node.id)
        if node.id in builtin_constants:
            # null 返回空值类型，其余返回 bool/str
            if node.id == 'null':
                return Type("Null")
            return Type("bool" if node.id in ['True', 'False'] else "str")
        if node.id in builtin_functions:
            # 返回合理的结果类型，避免后续赋值/返回类型误报
            if node.id == 'sorted':
                return Type("list")
            if node.id == 'isinstance':
                return Type("bool")
            if node.id == 'super':
                return Type("object")
            if node.id in ('bool', 'int', 'float', 'str', 'list', 'dict', 'set', 'tuple'):
                return Type(node.id)
            # 其余内建函数（hash/abs/min/max 等）返回类型无法精确推断时，
            # 回退为 object，避免误报“返回类型不匹配 / got None”
            return Type("object")
        if node.id in module_magic:
            return Type("str")
        # 已知类型名（泛型容器、Callable 等）作为注解使用时视为已定义
        if node.id in self._known_type_names:
            return Type(node.id)
        # meta block 中允许前向引用
        if self.in_meta_block:
            return Type("object")
        # 收集阶段不报错（允许前向引用）
        if self.collecting:
            return None
        self.errors.append(f"Undefined name '{node.id}' at {node.line}:{node.col}")
        return None

    def _visit_StructDef(self, node: Any) -> None:
        """处理结构体定义，为方法中的 self 设置类型"""
        # 保存当前类型映射（用于恢复）
        old_type_map = self.type_map.copy()
        
        # 注册泛型参数作为类型
        for param in getattr(node, 'generic_params', []):
            self.type_map[param] = Type(param)
        
        # 访问字段
        for field in node.fields:
            self._visit(field)
        
        # 恢复类型映射
        self.type_map = old_type_map
        
        # 访问方法，设置 self 类型为结构体类型
        struct_type = Type(node.name)
        for method in getattr(node, 'methods', []):
            old_type_map = self.type_map.copy()
            old_mutable_map = self.mutable_map.copy()
            # 如果方法有第一个参数是 self，设置其类型为结构体类型
            if method.params and method.params[0].name == 'self':
                self.type_map['self'] = struct_type
            self._visit(method)
            self.type_map = old_type_map
            self.mutable_map = old_mutable_map

    def _visit_TraitDef(self, node: Any) -> None:
        """处理特质定义，检查方法签名和泛型参数"""
        # 注册特质到注册表，供 impl 语句引用
        self.trait_defs[node.name] = node
        if node.name not in self.type_map:
            self.type_map[node.name] = Type(node.name)

        old_type_map = self.type_map.copy()

        for param in getattr(node, 'generic_params', []):
            self.type_map[param] = Type(param)
        
        trait_type = Type(node.name)
        for method in node.methods:
            if isinstance(method, FuncDef):
                old_method_map = self.type_map.copy()
                old_mutable_map = self.mutable_map.copy()
                if method.params and method.params[0].name == 'self':
                    self.type_map['self'] = trait_type
                self._visit(method)
                self.type_map = old_method_map
                self.mutable_map = old_mutable_map
        
        self.type_map = old_type_map

    def _generic_params_from_type(self, typ: Any) -> List[str]:
        """从类型表达式（字符串或 AST 节点）中提取泛型参数名，如 Wrapper<T> -> ['T']"""
        params: List[str] = []
        if typ is None:
            return params
        if isinstance(typ, str):
            import re as _re
            for m in _re.findall(r'<([^>]+)>', typ):
                for part in m.split(','):
                    part = part.strip()
                    if part:
                        params.append(part)
            return params
        if hasattr(typ, 'kind') and typ.kind == 'GenericType':
            # 提取泛型实参（如 Wrapper<T> -> ['T']），而非基础类型名 Wrapper
            for arg in getattr(typ, 'args', []) or []:
                if isinstance(arg, str):
                    params.append(arg)
                elif hasattr(arg, 'id'):
                    params.append(arg.id)
                else:
                    params.extend(self._generic_params_from_type(arg))
        return params

    def _visit_ImplStmt(self, node: Any) -> None:
        """处理特质实现，检查实现是否符合特质定义"""
        trait_name = node.trait_name
        for_type_name = getattr(node.for_type, 'id', str(node.for_type))
        
        # 将 for_type 中可能携带的泛型参数（如 Wrapper<T>）注册到类型环境
        for gp in self._generic_params_from_type(node.for_type):
            self.type_map[gp] = Type(gp)

        # 若实现块体为空或仅含 pass（示意性实现，方法在类型体内实现），
        # 视为合法实现，跳过缺方法检查
        _impl_methods = [m for m in getattr(node, 'methods', []) or []
                         if isinstance(m, FuncDef)]
        if not _impl_methods:
            self._register_trait_impl(trait_name, for_type_name)
            return

        if trait_name not in self.trait_defs:
            self.errors.append(f"Undefined trait '{trait_name}' at {node.line}:{node.col}")
            return
        
        trait_def = self.trait_defs[trait_name]
        
        trait_methods = {}
        for method in trait_def.methods:
            if isinstance(method, FuncDef):
                trait_methods[method.name] = method
        
        impl_methods = {}
        for method in _impl_methods:
            impl_methods[method.name] = method
        
        for method_name, trait_method in trait_methods.items():
            if method_name not in impl_methods:
                has_body = len(trait_method.body) > 0 and not (len(trait_method.body) == 1 and getattr(trait_method.body[0], 'kind', '') == 'PassStmt')
                if not has_body:
                    self.errors.append(f"Implementation of trait '{trait_name}' for type '{for_type_name}' is missing method '{method_name}' at {node.line}:{node.col}")
                continue
            
            impl_method = impl_methods[method_name]
            
            if len(trait_method.params) != len(impl_method.params):
                self.errors.append(f"Method '{method_name}' in implementation of '{trait_name}' for '{for_type_name}' has wrong number of parameters at {impl_method.line}:{impl_method.col}")
                continue
            
            for i, (trait_param, impl_param) in enumerate(zip(trait_method.params, impl_method.params)):
                trait_param_type = self._get_type_from_node(trait_param.type_annotation)
                impl_param_type = self._get_type_from_node(impl_param.type_annotation)
                
                # Self 类型替换：在实现中，Self 应该被替换为 for_type
                if trait_param_type and trait_param_type.name == 'Self':
                    trait_param_type = Type(for_type_name)
                
                if trait_param_type and impl_param_type and trait_param_type != impl_param_type:
                    self.errors.append(f"Parameter '{impl_param.name}' type mismatch in method '{method_name}' of trait '{trait_name}' implementation for '{for_type_name}': expected {trait_param_type}, got {impl_param_type} at {impl_param.line}:{impl_param.col}")
            
            trait_return_type = self._get_type_from_node(trait_method.return_type)
            impl_return_type = self._get_type_from_node(impl_method.return_type)
            
            # Self 返回类型替换
            if trait_return_type and trait_return_type.name == 'Self':
                trait_return_type = Type(for_type_name)
            
            if trait_return_type and impl_return_type and trait_return_type != impl_return_type:
                self.errors.append(f"Return type mismatch in method '{method_name}' of trait '{trait_name}' implementation for '{for_type_name}': expected {trait_return_type}, got {impl_return_type} at {impl_method.line}:{impl_method.col}")
        
        for method_name in impl_methods:
            if method_name not in trait_methods:
                self.errors.append(f"Implementation of trait '{trait_name}' for type '{for_type_name}' contains extra method '{method_name}' at {impl_methods[method_name].line}:{impl_methods[method_name].col}")
        
        # 类型检查每个实现方法的方法体
        for method_name, impl_method in impl_methods.items():
            if isinstance(impl_method, FuncDef):
                self._visit(impl_method)

    def _register_trait_impl(self, trait_name: str, for_type_name: str) -> None:
        """注册 trait 实现，并沿 super_traits 传播到所有父 trait（trait 组合）"""
        self.trait_impls.setdefault(trait_name, []).append(for_type_name)
        for sup in self._transitive_supertraits(trait_name):
            self.trait_impls.setdefault(sup, []).append(for_type_name)

    def _transitive_supertraits(self, trait_name: str) -> List[str]:
        """返回 trait 的所有（传递闭包）父 trait 名称"""
        result: List[str] = []
        seen = set()
        stack = [self._name_of(s)
                 for s in getattr(self.trait_defs.get(trait_name, None), 'super_traits', []) or []]
        while stack:
            t = stack.pop()
            if not t or t in seen:
                continue
            seen.add(t)
            result.append(t)
            td = self.trait_defs.get(t)
            if td:
                stack.extend(self._name_of(s)
                             for s in getattr(td, 'super_traits', []) or [])
        return result

    @staticmethod
    def _name_of(node: Any) -> Optional[str]:
        """从 trait 引用节点（可能是字符串或 Identifier）提取名称"""
        if isinstance(node, str):
            return node
        return getattr(node, 'id', getattr(node, 'name', None))

    def _visit_TypeClassDef(self, node: Any) -> None:
        """处理 TypeClass 定义，注册类型类及其方法签名"""
        typeclass_name = node.name
        
        # 保存当前状态
        old_type_map = self.type_map.copy()
        
        # 注册泛型参数
        for param in getattr(node, 'generic_params', []):
            self.type_map[param] = Type(param)
        
        # 注册 TypeClass 到注册表
        params_info = {}
        for param_name, constraint in getattr(node, 'generic_constraints', {}).items():
            params_info[param_name] = constraint
        
        self.register_type_class(typeclass_name, params_info)
        
        # 检查方法签名
        for method in node.methods:
            if isinstance(method, FuncDef):
                # 设置 self 类型为 TypeClass 的泛型参数
                if method.params and method.params[0].name == 'self':
                    # 如果有泛型参数，self 类型需要特殊处理
                    if getattr(node, 'generic_params', []):
                        first_param = node.generic_params[0]
                        self.type_map['self'] = Type(first_param)
                    else:
                        self.type_map['self'] = Type("object")
                
                # 检查方法签名
                old_method_map = self.type_map.copy()
                old_mutable_map = self.mutable_map.copy()
                self._visit(method)
                self.type_map = old_method_map
                self.mutable_map = old_mutable_map
        
        # 恢复状态
        self.type_map = old_type_map

    def _visit_TypeClassImpl(self, node: Any) -> None:
        """处理 TypeClass 实现，检查是否符合 TypeClass 定义"""
        typeclass_name = node.typeclass_name
        target_type = node.target_type
        
        # 将 target_type 中可能携带的泛型参数（如 Wrapper<T>）注册到类型环境，
        # 以便实现块体内的方法可以引用这些类型参数。
        for gp in self._generic_params_from_type(target_type):
            self.type_map[gp] = Type(gp)

        # 检查 TypeClass 是否已定义
        if typeclass_name not in self.type_classes:
            self.errors.append(f"Undefined typeclass '{typeclass_name}' at {node.line}:{node.col}")
            return
        
        # 注册实现
        self.register_type_class_instance(typeclass_name, target_type, node)
        
        # 获取 TypeClass 定义的方法签名
        typeclass_def = self.type_classes.get(typeclass_name, {})
        
        # 收集 TypeClass 定义的方法
        typeclass_methods = {}
        # 遍历 TypeClassDef 节点的 methods
        for method in getattr(node, 'methods', []):
            if isinstance(method, FuncDef):
                # 这是实现的方法
                pass
        
        # 这里需要更复杂的逻辑来验证实现是否符合定义
        # 简化处理：注册实现并检查方法数量
        
        # 检查实现的方法
        impl_methods = {}
        for method in node.methods:
            if isinstance(method, FuncDef):
                impl_methods[method.name] = method
        
        # 验证方法实现
        for method_name, impl_method in impl_methods.items():
            # 检查参数
            if isinstance(impl_method, FuncDef) and impl_method.params:
                # 验证参数类型
                for param in impl_method.params:
                    if param.type_annotation:
                        self._visit(param)
                
                # 验证返回类型
                if impl_method.return_type:
                    self._visit(impl_method.return_type)
                
                # 访问方法体
                old_type_map = self.type_map.copy()
                self.type_map['self'] = Type(target_type)
                for param in impl_method.params:
                    if param.type_annotation:
                        param_type = self._get_type_from_node(param.type_annotation)
                        if param_type:
                            self.type_map[param.name] = param_type
                self._visit(impl_method)
                self.type_map = old_type_map

    def _visit_EnumDef(self, node: Any) -> None:
        """处理枚举定义，注册枚举类型"""
        self.type_map[node.name] = Type(node.name)

    def _visit_TypeAlias(self, node: Any) -> None:
        """处理类型别名定义"""
        # 保存当前类型映射（用于恢复）
        old_type_map = self.type_map.copy()
        
        # 注册泛型参数作为类型
        for param in getattr(node, 'generic_params', []):
            self.type_map[param] = Type(param)
        
        # 访问目标类型
        if hasattr(node, 'target') and node.target:
            self._visit(node.target)
        
        # 恢复类型映射
        self.type_map = old_type_map
        
        # 注册类型别名定义（用于后续泛型类型替换）
        self.type_alias_defs[node.name] = node

    def _visit_StructLiteral(self, node: Any) -> Optional[Type]:
        """处理结构体字面量，返回结构体类型（支持泛型类型推断和约束检查）"""
        struct_name = node.struct_name
        
        # 检查是否是泛型结构体
        if struct_name in self.struct_defs:
            struct_def = self.struct_defs[struct_name]
            generic_params = getattr(struct_def, 'generic_params', [])
            generic_constraints = getattr(struct_def, 'generic_constraints', {})
            
            if generic_params:
                # 推断泛型参数类型
                inferred_types = {}
                for field_name, field_value in node.fields:
                    # 找到对应的字段定义
                    for field_def in struct_def.fields:
                        if field_def.name == field_name:
                            field_type_name = getattr(field_def.type_annotation, 'id', None)
                            if field_type_name in generic_params:
                                # 访问字段值获取类型
                                value_type = self._visit(field_value)
                                if value_type:
                                    inferred_types[field_type_name] = value_type
                            break
                
                # 检查泛型参数约束
                for param, inferred_type in inferred_types.items():
                    if param in generic_constraints:
                        constraint_type_ast = generic_constraints[param]
                        constraint_type_name = getattr(constraint_type_ast, 'id', None)
                        if constraint_type_name and inferred_type.name != constraint_type_name:
                            line = node.line if hasattr(node, 'line') else 0
                            col = node.col if hasattr(node, 'col') else 0
                            self.errors.append(f"Generic constraint violation: type '{inferred_type.name}' does not satisfy constraint '{constraint_type_name}' for parameter '{param}' at {line}:{col}")
                
                # 构建泛型参数列表
                generic_args = []
                for param in generic_params:
                    generic_args.append(inferred_types.get(param, Type(param)))
                
                return Type(struct_name, generic_params=generic_args)
        
        return Type(struct_name)

    def _visit_ExprStmt(self, node: Any) -> Optional[Type]:
        """处理表达式语句，返回表达式类型"""
        if hasattr(node, 'value'):
            return self._visit(node.value)
        return None

    def _visit_BuildBlockExpr(self, node: Any) -> Optional[Type]:
        """处理构建块表达式，返回最后一个表达式的类型"""
        result_type = None
        for stmt in node.body:
            result_type = self._visit(stmt)
            # 如果是 ExprStmt，返回其内部表达式的类型
            if hasattr(stmt, 'kind') and stmt.kind == "ExprStmt":
                inner_type = self._visit(stmt.value)
                if inner_type:
                    result_type = inner_type
        return result_type

    def _visit_Attribute(self, node: Any) -> Optional[Type]:
        """处理属性访问，返回属性类型（支持泛型参数）"""
        value_type = self._visit(node.value)
        
        # 处理泛型类型参数上的 trait/typeclass 方法访问
        if value_type:
            vname = value_type.name
            # 检查是否是已注册的 struct/class 类型上的方法
            if vname in self.struct_defs:
                struct_def = self.struct_defs[vname]
                
                # 保存当前类型映射（用于恢复）
                old_type_map = self.type_map.copy()
                
                # 注册泛型参数作为类型
                for param in getattr(struct_def, 'generic_params', []):
                    self.type_map[param] = Type(param)
                
                # 如果结构体类型有泛型参数，使用具体的泛型参数替换类型变量
                if value_type.generic_params:
                    generic_params = getattr(struct_def, 'generic_params', [])
                    for i, param in enumerate(generic_params):
                        if i < len(value_type.generic_params):
                            self.type_map[param] = value_type.generic_params[i]
                
                # 访问字段类型注解
                result_type = None
                for field in struct_def.fields:
                    if field.name == node.attr:
                        result_type = self._visit(field.type_annotation)
                        break
                
                # 恢复类型映射
                self.type_map = old_type_map
                
                return result_type
            
            # 检查类定义
            if vname in self.class_defs:
                class_def = self.class_defs[vname]
                for body_stmt in class_def.body:
                    if isinstance(body_stmt, LetStmt) and body_stmt.name == node.attr:
                        return self._visit(body_stmt.type_annotation)
                    elif isinstance(body_stmt, FuncDef) and body_stmt.name == node.attr:
                        return self._get_type_from_node(body_stmt.return_type)
            
            # 检查是否是 typeclass 方法调用：通过 type_class_method_cache
            cache_key = (None, node.attr, vname)
            cached_method = self.type_class_method_cache.get(cache_key)
            if cached_method:
                return self._get_type_from_node(cached_method.return_type)
            
            # 检查 trait 方法：如果 vname 是已实现了 trait 的类型
            # 遍历所有 trait，查找实现中是否有该方法
            for trait_name, impl_types in self.trait_impls.items():
                if vname in impl_types and trait_name in self.trait_defs:
                    trait_def = self.trait_defs[trait_name]
                    for m in getattr(trait_def, 'methods', []):
                        if isinstance(m, FuncDef) and m.name == node.attr:
                            return self._get_type_from_node(m.return_type)
            
            # 检查 typeclass 实例方法
            for (tc_name, type_name), impl_node in self.type_class_instances.items():
                if type_name == vname:
                    for m in getattr(impl_node, 'methods', []):
                        if isinstance(m, FuncDef) and m.name == node.attr:
                            return self._get_type_from_node(m.return_type)
            
            # 对于泛型参数（如 T），检查其在当前函数中的约束
            # 通过查找包含该泛型参数的函数定义
            for fname, fdef in self.func_defs.items():
                if hasattr(fdef, 'generic_constraints') and fdef.generic_constraints:
                    for param, constraint in fdef.generic_constraints.items():
                        if param == vname:
                            # 泛型参数的约束名
                            if hasattr(constraint, 'id'):
                                constraint_name = constraint.id
                                # 检查是否是 trait 约束
                                if constraint_name in self.trait_defs:
                                    for m in getattr(self.trait_defs[constraint_name], 'methods', []):
                                        if isinstance(m, FuncDef) and m.name == node.attr:
                                            return self._get_type_from_node(m.return_type)
                                # 检查是否是 typeclass 约束
                                if constraint_name in self.type_classes:
                                    if constraint_name in self.trait_defs:
                                        pass
                                    # 尝试从已实现的 typeclass 实例中查找
                                    for (tc_n, tn), impl in self.type_class_instances.items():
                                        if tc_n == constraint_name:
                                            for m in getattr(impl, 'methods', []):
                                                if isinstance(m, FuncDef) and m.name == node.attr:
                                                    return self._get_type_from_node(m.return_type)
        # 未能解析的属性（如 __init__ 中赋值的实例字段）：回退为 object，
        # 避免因动态属性返回 None 而误报“返回类型不匹配”
        return Type("object")

    def _extract_bind_names(self, node: Any) -> List[str]:
        """从赋值/解构目标中提取所有被绑定的变量名（元组/列表/数组模式/StarExpr 等）"""
        names: List[str] = []
        if node is None:
            return names
        if isinstance(node, str):
            if node and node != '_':
                names.append(node)
            return names
        if isinstance(node, (list, tuple)):
            for e in node:
                names.extend(self._extract_bind_names(e))
            return names
        if hasattr(node, 'kind'):
            k = node.kind
            if k == 'Name':
                if node.id != '_':
                    names.append(node.id)
                return names
            if k == 'Pattern':
                nm = getattr(node, 'name', None)
                if nm and nm != '_':
                    names.append(nm)
                return names
            if k in ('TupleExpr', 'ListExpr'):
                els = getattr(node, 'elements', None) or getattr(node, 'elts', None) or []
                for el in els:
                    names.extend(self._extract_bind_names(el))
                return names
            if k == 'Constant' and isinstance(node.value, (tuple, list)):
                for el in node.value:
                    names.extend(self._extract_bind_names(el))
                return names
            if k in ('ArrayPattern', 'TuplePattern'):
                ps = getattr(node, 'patterns', None) or getattr(node, 'elements', None) or []
                for p in ps:
                    names.extend(self._extract_bind_names(p))
                return names
            if k == 'StarExpr':
                inner = getattr(node, 'value', None) or getattr(node, 'expr', None)
                if inner is not None:
                    names.extend(self._extract_bind_names(inner))
                return names
        if hasattr(node, 'id'):
            if node.id != '_':
                names.append(node.id)
            return names
        return names

    def _visit_Assign(self, node: Any) -> Optional[Type]:
        # 先注册目标名（支持解构赋值与自引用，如 result = match... 内引用 result）
        for nm in self._extract_bind_names(node.target):
            if nm not in self.type_map:
                self.type_map[nm] = Type("object")
                self.mutable_map[nm] = True

        # 再访问 value
        value_type = None
        if node.value:
            value_type = self._visit(node.value)

        return value_type

    def _visit_ForStmt(self, node: Any) -> None:
        """处理 for 循环，注册循环变量（支持解构目标）"""
        iter_type = self._visit(node.iter) if node.iter else None
        for nm in self._extract_bind_names(node.target):
            if iter_type and hasattr(iter_type, 'generic_params') and iter_type.generic_params:
                self.type_map[nm] = iter_type.generic_params[0]
            elif iter_type and iter_type.name == 'int':
                self.type_map[nm] = Type('int')
            else:
                self.type_map[nm] = Type('object')
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_WithStmt(self, node: Any) -> None:
        """处理 with 语句，注册 as 绑定变量"""
        for item in getattr(node, 'items', []) or []:
            if isinstance(item, (list, tuple)):
                expr = item[0] if len(item) > 0 else None
                var = item[1] if len(item) > 1 else None
                if expr is not None:
                    self._visit(expr)
                if var is not None:
                    var_name = var.id if hasattr(var, 'id') else var
                    if var_name and var_name != '_':
                        self.type_map[var_name] = Type("object")
                        self.mutable_map[var_name] = True
            else:
                self._visit(item)
        for stmt in getattr(node, 'body', []) or []:
            self._visit(stmt)

    def _visit_MacroDef(self, node: Any) -> None:
        """处理 macro 定义，注册宏名（去掉可能的 ! 后缀）"""
        name = getattr(node, 'name', None)
        if name:
            base = name[:-1] if name.endswith('!') else name
            self.type_map[base] = Type("object")

    def _visit_MacroCall(self, node: Any) -> None:
        """处理宏调用，仅访问参数，宏名作为字符串不查类型环境"""
        for arg in getattr(node, 'args', []) or []:
            self._visit(arg)

    def _visit_ComptimeStmt(self, node: Any) -> None:
        """处理 comptime: 块，访问块内语句（含内部 def）"""
        block = getattr(node, 'body', None)
        if block is None:
            block = getattr(node, 'expr', None)
        if isinstance(block, list):
            for stmt in block:
                self._visit(stmt)
        elif block is not None:
            self._visit(block)

    def _visit_ListComp(self, node: Any) -> Optional[Type]:
        """处理列表推导式，注册循环变量并返回列表类型"""
        # 处理每个生成器
        for gen in node.generators:
            if len(gen) >= 2:
                target, iter_expr = gen[0], gen[1]
                # 从迭代对象推断类型
                iter_type = self._visit(iter_expr)
                
                # 获取循环变量名称 - target可能是字符串或元组
                if isinstance(target, str):
                    target_names = [target]
                elif isinstance(target, tuple):
                    target_names = list(target)
                else:
                    target_names = []
                
                for target_name in target_names:
                    if iter_type and hasattr(iter_type, 'generic_params') and iter_type.generic_params:
                        element_type = iter_type.generic_params[0]
                        self.type_map[target_name] = element_type
                    elif iter_type and iter_type.name == 'int':
                        self.type_map[target_name] = Type('int')
                    else:
                        self.type_map[target_name] = Type('object')
                
                # 处理 if 条件列表
                if len(gen) > 2 and gen[2]:
                    for if_expr in gen[2]:
                        self._visit(if_expr)
        
        # 访问元素表达式，返回列表类型（包含元素类型）
        element_type = self._visit(node.elt)
        if element_type:
            return Type("list", generic_params=[element_type])
        return Type("list", generic_params=[Type("object")])

    def _visit_WhileStmt(self, node: Any) -> None:
        """处理 while 循环"""
        # 访问条件表达式
        self._visit(node.test)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    # ========== 双向类型检查（Bidirectional Type Checking） ==========

    def _check_with_expected(self, node: ASTNode, expected_type: Optional[Type] = None) -> Optional[Type]:
        """双向类型检查入口
        
        结合自底向上推断和自顶向下期望类型传播：
        1. 如果有期望类型，尝试用期望类型指导推断
        2. 如果没有期望类型，进行自底向上的类型推断
        3. 检查推断类型与期望类型的兼容性
        
        Args:
            node: AST 节点
            expected_type: 期望类型（自顶向下传播）
            
        Returns:
            推断出的类型
        """
        # 如果节点是 Lambda 且有期望的函数类型，将期望类型传播到参数
        if isinstance(node, LambdaExpr) and expected_type and expected_type.name == 'lambda':
            return self._check_lambda_with_expected(node, expected_type)
        
        # 如果节点是函数调用且有期望类型，用期望类型指导泛型推断
        if isinstance(node, Call) and expected_type:
            return self._check_call_with_expected(node, expected_type)
        
        # 如果节点是 LetStmt 且有声明类型，用声明类型作为期望类型
        if isinstance(node, LetStmt) and node.type_annotation:
            declared_type = self._get_type_from_node(node.type_annotation)
            if declared_type:
                return self._check_let_with_expected(node, declared_type)
        
        # 默认：自底向上推断
        return self._visit(node)

    def _check_lambda_with_expected(self, node: LambdaExpr, expected_type: Type) -> Optional[Type]:
        """使用期望的函数类型检查 Lambda 表达式
        
        这实现了双向类型检查的关键功能：
        当 Lambda 被传递给一个已知参数类型的函数时，
        Lambda 的参数类型可以从函数签名中推断。
        
        Args:
            node: Lambda 表达式节点
            expected_type: 期望的函数类型
            
        Returns:
            推断出的 Lambda 类型
        """
        # 从期望类型提取参数类型和返回类型
        expected_param_types = expected_type.generic_params[:-1] if expected_type.generic_params else []
        expected_return_type = expected_type.generic_params[-1] if expected_type.generic_params else None
        
        # 保存旧状态
        old_type_map = self.type_map.copy()
        old_mutable_map = self.mutable_map.copy()
        old_return_type = self.current_function_return_type
        
        # 用期望类型推断参数类型
        param_types = []
        for i, param in enumerate(node.params):
            param_type = self._get_type_from_node(param.type_annotation)
            
            # 如果参数没有类型注解，从期望类型推断
            if not param_type and i < len(expected_param_types):
                param_type = expected_param_types[i]
            
            if param_type:
                param_types.append(param_type)
                self.type_map[param.name] = param_type
            else:
                param_types.append(Type("object"))
                self.type_map[param.name] = Type("object")
        
        # 使用期望返回类型检查函数体
        return_type = None
        if isinstance(node.body, ASTNode):
            if expected_return_type:
                # 双向检查：用期望类型检查表达式
                body_type = self._check_with_expected(node.body, expected_return_type)
            else:
                body_type = self._visit(node.body)
            return_type = body_type
        elif hasattr(node.body, '__iter__'):
            # 语句块
            return_types = []
            
            def collect_returns(stmts):
                for stmt in stmts:
                    if isinstance(stmt, ReturnStmt) and stmt.value:
                        ret_type = self._check_with_expected(stmt.value, expected_return_type)
                        if ret_type:
                            return_types.append(ret_type)
            
            collect_returns(node.body)
            
            if return_types:
                return_type = self._find_common_type(return_types)
            elif expected_return_type:
                return_type = expected_return_type
            else:
                return_type = Type("None")
        
        if not return_type:
            return_type = Type("object")
        
        # 恢复状态
        self.type_map = old_type_map
        self.mutable_map = old_mutable_map
        self.current_function_return_type = old_return_type
        
        return Type("lambda", generic_params=[*param_types, return_type])

    def _check_call_with_expected(self, node: Call, expected_type: Type) -> Optional[Type]:
        """使用期望类型检查函数调用
        
        当函数调用的返回类型已知时，
        可以更精确地推断泛型参数。
        
        Args:
            node: 函数调用节点
            expected_type: 期望的返回类型
            
        Returns:
            推断出的类型
        """
        # 访问函数
        func_type = self._visit(node.func)
        
        # 处理参数
        for i, arg in enumerate(node.args):
            if isinstance(arg, tuple) and len(arg) == 2:
                self._visit(arg[1])
            else:
                self._visit(arg)
        
        # 如果是已知函数，尝试用期望类型指导泛型推断
        if hasattr(node.func, 'id'):
            func_name = node.func.id
            if func_name in self.func_defs:
                func_def = self.func_defs[func_name]
                generic_params = getattr(func_def, 'generic_params', [])
                
                if generic_params and expected_type:
                    # 使用期望类型辅助推断
                    inferred_types = self._infer_generic_types_with_expected(
                        func_def, node.args, generic_params, expected_type
                    )
                    
                    # 检查约束
                    generic_constraints = getattr(func_def, 'generic_constraints', {})
                    for param, inferred_type in inferred_types.items():
                        if param in generic_constraints:
                            constraint_ast = generic_constraints[param]
                            self._check_generic_constraint(param, inferred_type, constraint_ast, node)
                    
                    # 替换返回类型中的泛型参数
                    if func_def.return_type:
                        return_type_node = self._get_type_from_node(func_def.return_type)
                        if return_type_node:
                            return self._substitute_generic_params(return_type_node, inferred_types)
        
        # 默认返回从函数推断的类型
        return self._visit(node.func)

    def _infer_generic_types_with_expected(
        self, func_def: FuncDef, args: List[Any], 
        generic_params: List[str], expected_return_type: Type
    ) -> Dict[str, Type]:
        """使用期望返回类型辅助推断泛型参数
        
        Args:
            func_def: 函数定义
            args: 函数参数
            generic_params: 泛型参数名列表
            expected_return_type: 期望的返回类型
            
        Returns:
            推断的泛型类型映射
        """
        inferred = self._infer_generic_types(func_def, args, generic_params)
        
        # 如果还有未推断的泛型参数，尝试从期望返回类型推断
        for gp in generic_params:
            if gp not in inferred and expected_return_type.generic_params:
                # 检查期望返回类型的泛型参数是否对应
                for tp in expected_return_type.generic_params:
                    if tp.name == gp:
                        inferred[gp] = tp
                        break
        
        # 仍无法推断的使用 object 作为默认值
        for gp in generic_params:
            if gp not in inferred:
                inferred[gp] = Type("object")
        
        return inferred

    def _check_let_with_expected(self, node: LetStmt, declared_type: Type) -> Optional[Type]:
        """使用声明类型检查 Let 语句
        
        Args:
            node: Let 语句节点
            declared_type: 声明的类型
            
        Returns:
            推断出的类型
        """
        if node.value:
            # 用声明类型作为期望类型检查值
            value_type = self._check_with_expected(node.value, declared_type)
            
            if value_type:
                # 检查类型兼容性
                if not self._is_subtype(value_type, declared_type):
                    if declared_type.name not in ('object', 'Any'):
                        line = node.line if hasattr(node, 'line') else 0
                        col = node.col if hasattr(node, 'col') else 0
                        self.errors.append(
                            f"Type mismatch: expected '{declared_type}', "
                            f"got '{value_type}' at {line}:{col}"
                        )
                self.type_map[node.name] = declared_type
                return declared_type
        
        return None

    def _is_subtype(self, sub_type: Type, super_type: Type) -> bool:
        """检查子类型关系（双向类型检查的关键）
        
        Args:
            sub_type: 子类型
            super_type: 父类型
            
        Returns:
            True 如果 sub_type 是 super_type 的子类型
        """
        # 相同类型
        if sub_type == super_type:
            return True
        
        # object/Any 是所有类型的父类型
        if super_type.name in ('object', 'Any'):
            return True
        
        # 检查继承链
        if sub_type.name in self.inheritance_map:
            return super_type.name in self.inheritance_map[sub_type.name]
        
        # 数值类型兼容
        numeric_order = ['bool', 'int', 'float', 'double']
        if sub_type.name in numeric_order and super_type.name in numeric_order:
            sub_idx = numeric_order.index(sub_type.name)
            super_idx = numeric_order.index(super_type.name)
            return sub_idx <= super_idx
        
        return False

    def _visit_IfStmt(self, node: Any) -> None:
        """处理 if 语句 - 支持控制流类型窄化（Scala 风格）"""
        # 在访问条件表达式前，先分析 isinstance 模式以提取窄化信息
        narrowing_info = self._extract_narrowing_info(node.test)
        
        # 访问条件表达式
        self._visit(node.test)
        
        # 保存当前 type_map 状态
        saved_type_map = self.type_map.copy()
        saved_mutable_map = self.mutable_map.copy()
        
        # 如果有窄化信息，应用到 then 分支
        if narrowing_info and narrowing_info.get('positive'):
            for var_name, narrowed_type in narrowing_info['positive'].items():
                if var_name in self.type_map:
                    self.type_map[var_name] = narrowed_type
        
        # 访问 if 分支
        for stmt in node.body:
            self._visit(stmt)
        
        # 恢复 type_map 用于 else 分支
        self.type_map = saved_type_map.copy()
        self.mutable_map = saved_mutable_map.copy()
        
        # 如果有窄化信息，应用到 else 分支（否定形式）
        if narrowing_info and narrowing_info.get('negative'):
            for var_name, narrowed_type in narrowing_info['negative'].items():
                if var_name in self.type_map:
                    self.type_map[var_name] = narrowed_type
        
        # 访问 elif/else 分支（elif 作为嵌套 IfStmt 在 orelse 中）
        if hasattr(node, 'orelse') and node.orelse:
            for stmt in node.orelse:
                self._visit(stmt)
        
        # 恢复原始 type_map（窄化只在分支内部有效）
        self.type_map = saved_type_map
        self.mutable_map = saved_mutable_map

    def _extract_narrowing_info(self, test_node: Any) -> Dict[str, Dict[str, Type]]:
        """从条件表达式中提取类型窄化信息"""
        result = {'positive': {}, 'negative': {}}
        
        if test_node is None:
            return result
        
        # 处理 isinstance 调用
        if isinstance(test_node, Call):
            func_name = getattr(test_node.func, 'id', '')
            if func_name == 'isinstance' and len(test_node.args) >= 2:
                # isinstance(x, Type) -> 在 then 分支中 x 窄化为 Type
                if len(test_node.args) >= 2:
                    var_node = test_node.args[0]
                    type_node = test_node.args[1]
                    
                    if isinstance(var_node, Name) and isinstance(type_node, Name):
                        var_name = var_node.id
                        type_name = type_node.id
                        if var_name in self.type_map:
                            narrowed_type = Type(type_name)
                            result['positive'][var_name] = narrowed_type
                            
                            # 负分支：排除该类型，保持原有类型
                            # 在 Scala 中，else 分支的类型是排除窄化类型后的类型
                            original_type = self.type_map.get(var_name)
                            if original_type and original_type.name != type_name:
                                result['negative'][var_name] = original_type
        
        # 处理一元否定（not isinstance(x, Type)）
        if isinstance(test_node, UnaryOp):
            if hasattr(test_node, 'op') and test_node.op == 'not':
                inner_info = self._extract_narrowing_info(test_node.operand)
                # 翻转 positive 和 negative
                result['positive'] = inner_info.get('negative', {})
                result['negative'] = inner_info.get('positive', {})
        
        # 处理二元与（isinstance(x, T1) and isinstance(x, T2)）
        if isinstance(test_node, BinOp):
            op = getattr(test_node, 'op', '')
            if op == 'and':
                left_info = self._extract_narrowing_info(test_node.left)
                right_info = self._extract_narrowing_info(test_node.right)
                # 合并两个窄化信息
                for k, v in left_info.get('positive', {}).items():
                    result['positive'][k] = v
                for k, v in right_info.get('positive', {}).items():
                    if k in result['positive']:
                        # 两者都窄化时，取更具体的类型
                        result['positive'][k] = self._find_common_type([result['positive'][k], v])
                    else:
                        result['positive'][k] = v
        
        return result

    def _visit_CastExpr(self, node: CastExpr) -> Optional[Type]:
        """处理类型转换表达式"""
        # 检查值的类型
        value_type = self._visit(node.value)
        
        # 获取目标类型
        target_type = self._get_type_from_node(node.target_type)
        if not target_type:
            target_type = Type(node.target_type.id) if hasattr(node.target_type, 'id') else Type(str(node.target_type))
        
        # 定义基本类型集合
        basic_types = {'int', 'float', 'double', 'bool', 'str', 'long', 'char'}
        
        # 对于基本类型，允许显式转换
        if value_type:
            if value_type.name in basic_types and target_type.name in basic_types:
                return target_type
        
        # 检查是否有 __cast__ 或 __try_cast__ 方法
        if value_type and value_type.name in self.magic_methods:
            magic_map = self.magic_methods[value_type.name]
            
            # 检查 __cast__[T] 方法
            cast_method = magic_map.get('__cast__')
            # 检查 __try_cast__[T] 方法
            try_cast_method = magic_map.get('__try_cast__')
            
            if cast_method or try_cast_method:
                # 类型转换有效，返回目标类型
                return target_type
        
        # 对于自定义类型，如果没有 __cast__ 方法，报告错误
        if value_type and value_type.name not in basic_types and target_type.name not in basic_types:
            self.errors.append(f"Cannot cast from '{value_type.name}' to '{target_type.name}': no __cast__ method defined at {node.line}:{node.col}")
            return None
        
        return target_type

    def _is_generic_subtype(self, subtype: Type, supertype: Type) -> bool:
        """检查泛型类型是否是另一个泛型类型的子类型（如 list[int] 是 list[object] 的子类型）"""
        if subtype.name != supertype.name:
            return False
        if len(subtype.generic_params) != len(supertype.generic_params):
            return False
        
        for sub_param, super_param in zip(subtype.generic_params, supertype.generic_params):
            # object 是所有类型的父类型
            if super_param.name == 'object':
                continue
            # 相同类型
            if sub_param == super_param:
                continue
            # 数值类型向上转换
            numeric_types = {'bool', 'int', 'float', 'double'}
            if sub_param.name in numeric_types and super_param.name in numeric_types:
                type_order = ['bool', 'int', 'float', 'double']
                sub_idx = type_order.index(sub_param.name)
                super_idx = type_order.index(super_param.name)
                if sub_idx <= super_idx:
                    continue
            return False
        return True

    def _check_implicit_conversion(self, value_type: Type, target_type: Type, node: Any) -> bool:
        """检查是否可以通过 __implicit_into__ 方法进行隐式转换"""
        # 检查源类型是否有 __implicit_into__ 方法可以转换为目标类型
        if value_type.name in self.magic_methods:
            magic_map = self.magic_methods[value_type.name]
            if '__implicit_into__' in magic_map:
                implicit_method = magic_map['__implicit_into__']
                # 检查 __implicit_into__ 的返回类型是否匹配目标类型
                if hasattr(implicit_method, 'return_type') and implicit_method.return_type:
                    return_type_name = self._get_return_type_name(implicit_method.return_type)
                    if return_type_name == target_type.name:
                        return True
                # 如果无法确定返回类型，假设可以转换（保守策略）
                return True
        return False

    def _check_guarded_conversion(self, value_type: Type, target_type: Type, node: Any) -> bool:
        """检查是否可以通过守卫策略（__guarded_pred__/__guarded_action__）进行转换"""
        if value_type.name in self.magic_methods:
            magic_map = self.magic_methods[value_type.name]
            # 检查是否有守卫策略方法
            if '__guarded_pred__' in magic_map and '__guarded_action__' in magic_map:
                guarded_pred = magic_map['__guarded_pred__']
                # 检查守卫条件是否允许转换（简化版：如果有守卫方法就允许）
                if guarded_pred:
                    return True
        return False

    def _get_return_type_name(self, return_type: Any) -> str:
        """从返回类型注解中提取类型名称"""
        if hasattr(return_type, 'id'):
            return return_type.id
        elif hasattr(return_type, 'name'):
            return return_type.name
        elif hasattr(return_type, 'element_type'):
            # 泛型类型如 list[int]
            if hasattr(return_type, 'element_type'):
                return_type_name = getattr(return_type.element_type, 'id', str(return_type.element_type))
                return f"list[{return_type_name}]"
        return str(return_type)

    def _find_common_type(self, types: List[Type]) -> Type:
        """从一组类型中找到最具体的公共类型（LUB - Least Upper Bound）"""
        if not types:
            return Type("object")
        
        # 过滤掉 None/Nothing 类型
        non_bottom_types = [t for t in types if t.name not in ('None', 'Nothing')]
        if not non_bottom_types:
            return Type("Nothing")
        
        # 如果只有一个类型，直接返回
        if len(non_bottom_types) == 1:
            return non_bottom_types[0]
        
        # 数值类型向上转换：bool → int → float → double
        numeric_order = ['bool', 'int', 'float', 'double']
        all_numeric = all(t.name in numeric_order for t in non_bottom_types)
        
        if all_numeric:
            indices = [numeric_order.index(t.name) for t in non_bottom_types]
            result = Type(numeric_order[max(indices)])
            # 保留泛型参数
            if non_bottom_types[0].generic_params:
                result.generic_params = non_bottom_types[0].generic_params
            return result
        
        # 检查所有类型是否完全相同
        if all(t == non_bottom_types[0] for t in non_bottom_types):
            return non_bottom_types[0]
        
        # 检查是否是相同泛型结构的类型（如 list[int] 和 list[float]）
        if all(t.name == non_bottom_types[0].name and t.generic_params for t in non_bottom_types):
            # 尝试对泛型参数逐个求 LUB
            all_same_generic_structure = True
            common_params = []
            min_len = min(len(t.generic_params) for t in non_bottom_types)
            
            for i in range(min_len):
                param_types = [t.generic_params[i] for t in non_bottom_types]
                common_param = self._find_common_type(param_types)
                common_params.append(common_param)
                
                # 如果任何一个参数变成了 object，标记为无法统一
                if common_param.name == 'object':
                    all_same_generic_structure = False
            
            if all_same_generic_structure:
                return Type(non_bottom_types[0].name, generic_params=common_params)
        
        # 使用继承链查找公共父类型
        common_ancestors = self._find_common_ancestors(non_bottom_types)
        if common_ancestors:
            # 返回最具体的公共父类型（列表第一个是最近的祖先）
            return Type(common_ancestors[0])
        
        # 检查是否可以通过 Scala 风格的类型系统统一
        # Null 是所有引用类型的子类型
        ref_types = {'str', 'list', 'dict', 'tuple', 'object'}
        if all(t.name in ref_types or t.name == 'Null' for t in non_bottom_types):
            return Type("object")
        
        # 无法统一，返回 object（Scala 中的 Any）
        return Type("object")

    def _find_common_ancestors(self, types: List[Type]) -> List[str]:
        """查找多个类型的公共祖先（按从近到远排序）"""
        if not types:
            return []
        
        # 获取每个类型的继承链
        ancestor_chains = []
        for t in types:
            chain = self._get_ancestor_chain(t.name)
            ancestor_chains.append(chain)
        
        # 找到所有链的公共祖先
        if not ancestor_chains:
            return []
        
        # 使用第一个链作为基准，找到公共元素
        first_chain = set(ancestor_chains[0])
        common = first_chain
        
        for chain in ancestor_chains[1:]:
            common = common.intersection(set(chain))
        
        # 保持原始顺序（从近到远）
        result = [a for a in ancestor_chains[0] if a in common]
        return result

    def _get_ancestor_chain(self, type_name: str) -> List[str]:
        """获取一个类型的完整继承链（从自身到 object）"""
        chain = [type_name]
        current = type_name
        
        # 遍历继承链直到到达 object 或没有更多父类型
        max_depth = 50  # 防止无限循环
        depth = 0
        while depth < max_depth:
            # 检查是否在继承映射中
            if current in self.inheritance_map:
                parents = self.inheritance_map[current]
                if parents:
                    # 使用第一个父类型（单继承场景）
                    parent = parents[0]
                    chain.append(parent)
                    current = parent
                    
                    # 如果已经到达 object，停止
                    if parent == 'object' or parent == 'Any':
                        break
                else:
                    break
            else:
                # 检查是否是内置类型（bool → int → float → double 链）
                numeric_chain = {'bool': ['bool', 'int', 'float', 'double'],
                                'int': ['int', 'float', 'double'],
                                'float': ['float', 'double'],
                                'double': ['double']}
                if current in numeric_chain:
                    chain = numeric_chain[current] + ['object']
                    break
                else:
                    # 默认所有类型的父类型是 object
                    if 'object' not in chain:
                        chain.append('object')
                    break
            depth += 1
        
        return chain

    def _register_inheritance(self, child: str, parents: List[str]) -> None:
        """注册类型继承关系"""
        if child not in self.inheritance_map:
            self.inheritance_map[child] = []
        self.inheritance_map[child].extend(parents)
        
        for parent in parents:
            if parent not in self.type_map:
                self.type_map[parent] = Type(parent)

    # 内建类型默认满足的常见 duck 约束（用于结构性约束检查）
    _BUILTIN_DUCK_SATISFIES = {
        'int': {'Numeric', 'Comparable', 'Equatable', 'Ordered', 'Sized'},
        'float': {'Numeric', 'Comparable', 'Equatable', 'Ordered', 'Sized'},
        'bool': {'Comparable', 'Equatable', 'Ordered', 'Sized'},
        'str': {'Comparable', 'Equatable', 'Ordered', 'Sized', 'Iterable'},
        'list': {'Sized', 'Iterable', 'Container'},
        'dict': {'Sized', 'Iterable', 'Mapping', 'Container'},
        'tuple': {'Sized', 'Iterable'},
        'set': {'Sized', 'Iterable'},
    }

    # 由内建满足映射推导出的“知名 duck 约束”集合：
    # 这些约束无需在文件中显式定义即可被引用（跨 demo 复用，如 Sized）。
    _KNOWN_DUCK_NAMES = set().union(*_BUILTIN_DUCK_SATISFIES.values())

    # 无对应静态类型的 typing 构造类型：在类型检查中按 object 处理
    # （与代码生成一致）。注意：Callable 不在此列，需保留结构以支持调用返回推断。
    _OBJECT_GENERIC_TYPES = {
        'Optional', 'Union', 'Any', 'Sequence', 'Iterable', 'Mapping',
        'MutableMapping', 'Set', 'FrozenSet', 'Type', 'Generator',
        'Coroutine', 'Awaitable', 'Deque', 'DefaultDict',
    }

    @staticmethod
    def _operator_dunder(op: str) -> Optional[str]:
        return {
            '+': '__add__', '-': '__sub__', '*': '__mul__', '/': '__truediv__',
            '<': '__lt__', '>': '__gt__', '<=': '__le__', '>=': '__ge__',
            '==': '__eq__', '!=': '__ne__',
        }.get(op)

    def _type_satisfies_duck(self, inferred_type: Type, duck_name: str) -> bool:
        """结构性检查某类型是否满足 duck 约束

        - 内建类型依据预定义映射（如 int 满足 Comparable/Numeric）
        - 结构体/类检查其成员（字段与方法）是否满足约束要求
        """
        if duck_name not in self.duck_constraints:
            return False
        if (inferred_type.name in self._BUILTIN_DUCK_SATISFIES
                and duck_name in self._BUILTIN_DUCK_SATISFIES[inferred_type.name]):
            return True

        # 结构体 / 类：检查成员是否满足约束要求
        struct = (self.struct_defs.get(inferred_type.name)
                  or self.class_defs.get(inferred_type.name))
        if struct is None:
            return False
        members = set()
        # 结构体字段（StructField 节点放在 .fields 中，而非 .body）
        for field in getattr(struct, 'fields', []) or []:
            name = getattr(field, 'name', None)
            if name:
                members.add(name)
        # 方法（结构体放在 .methods，类放在 .body）
        for method in getattr(struct, 'methods', []) or []:
            name = getattr(method, 'name', None)
            if name:
                members.add(name)
        for stmt in getattr(struct, 'body', []) or []:
            name = getattr(stmt, 'name', None)
            if name:
                members.add(name)

        for req in self.duck_constraints[duck_name].get("requirements", []) or []:
            rkind = getattr(req, 'kind', None)
            if rkind == "reference":
                if not self._type_satisfies_duck(inferred_type, req.name):
                    return False
            elif rkind in ("attribute", "method"):
                if req.name not in members:
                    return False
            elif rkind == "operator":
                # 内置类型已在前述映射中处理；结构体需提供对应 dunder 方法
                if inferred_type.name in self._BUILTIN_DUCK_SATISFIES:
                    continue
                dunder = self._operator_dunder(req.name)
                if dunder and dunder in members:
                    continue
                return False
        return True

    def _check_generic_constraint(self, param_name: str, inferred_type: Type, constraint_ast: Any, node: Any) -> None:
        """增强的泛型约束检查
        
        支持的约束类型：
        1. 基本类型约束：T: int | float (联合类型约束)
        2. Trait 约束：T: TraitName (类型必须实现某个 trait)
        3. 多重约束：T: Trait1 + Trait2 (类型必须同时实现多个 trait)
        4. F-bounded 约束：T: Container[T] (类型必须是容器类型且包含自身)
        5. TypeClass 约束：T: TypeClassName (类型必须实现某个 typeclass)
        
        Args:
            param_name: 泛型参数名
            inferred_type: 推断出的类型
            constraint_ast: 约束 AST 节点
            node: 当前 AST 节点（用于错误报告位置）
        """
        line = node.line if hasattr(node, 'line') else 0
        col = node.col if hasattr(node, 'col') else 0
        
        # 处理 GenericType 约束 (如 Container<T> 或 Container<int>)
        if isinstance(constraint_ast, GenericType):
            typeclass_name = constraint_ast.name
            # 若名称是 duck 约束（而非 typeclass），按 duck 结构性检查处理
            # （泛型参数 T/U 仅作信息用途，结构性检查只看成员名）
            if typeclass_name in self.duck_constraints:
                if self._type_satisfies_duck(inferred_type, typeclass_name):
                    return
                self.errors.append(
                    f"Generic constraint violation: type '{inferred_type.name}' "
                    f"does not satisfy constraint '{typeclass_name}' "
                    f"for parameter '{param_name}' at {line}:{col}"
                )
                return
            # 否则按 typeclass 检查：inferred_type 是否实现了该 typeclass
            found = False
            for (tc_name, tn), impl in self.type_class_instances.items():
                if tc_name == typeclass_name and tn == inferred_type.name:
                    found = True
                    break
            if not found:
                self.errors.append(
                    f"Generic constraint violation: type '{inferred_type.name}' "
                    f"does not satisfy constraint '{typeclass_name}' "
                    f"for parameter '{param_name}' at {line}:{col}"
                )
            return
        
        # 首先检查 F-bounded 约束：泛型参数出现在约束的泛型参数中
        if hasattr(constraint_ast, 'generic_params') and constraint_ast.generic_params:
            for gp in constraint_ast.generic_params:
                gp_name = getattr(gp, 'id', str(gp))
                if gp_name == param_name:
                    # F-bounded 约束已满足（类型包含自身）
                    return
        
        # 收集所有约束名称
        constraint_names = []
        is_trait_constraint = False
        is_typeclass_constraint = False
        
        if hasattr(constraint_ast, 'kind') and constraint_ast.kind == 'UnionType':
            # 联合类型约束（基本类型约束）
            for t in constraint_ast.types:
                constraint_names.append(getattr(t, 'id', str(t)))
        elif hasattr(constraint_ast, 'kind') and constraint_ast.kind == 'IntersectionType':
            # 交集类型约束（多重 trait 约束）
            is_trait_constraint = True
            for t in constraint_ast.types:
                name = getattr(t, 'id', str(t))
                constraint_names.append(name)
        else:
            # 单一约束
            constraint_name = getattr(constraint_ast, 'id', str(constraint_ast))
            constraint_names.append(constraint_name)
            if constraint_name in self.trait_defs:
                is_trait_constraint = True
            elif constraint_name in self.type_classes:
                is_typeclass_constraint = True
        
        # 检查约束满足情况
        if is_typeclass_constraint:
            # TypeClass 约束检查
            tc_name = constraint_names[0]
            found = False
            for (tc_n, tn), impl in self.type_class_instances.items():
                if tc_n == tc_name and tn == inferred_type.name:
                    found = True
                    break
            if not found:
                self.errors.append(
                    f"Generic constraint violation: type '{inferred_type.name}' "
                    f"does not satisfy constraint '{tc_name}' "
                    f"for parameter '{param_name}' at {line}:{col}"
                )
        elif is_trait_constraint:
            # Trait 约束检查
            for trait_name in constraint_names:
                if trait_name in self.trait_defs:
                    implemented_types = self.trait_impls.get(trait_name, [])
                    if inferred_type.name not in implemented_types:
                        self.errors.append(
                            f"Generic constraint violation: type '{inferred_type.name}' "
                            f"does not implement trait '{trait_name}' "
                            f"for parameter '{param_name}' at {line}:{col}"
                        )
        else:
            # 基本类型约束 / duck 约束检查
            if inferred_type.name in constraint_names:
                return
            # duck 约束：结构性检查（内置类型 + 结构体成员）
            if any(self._type_satisfies_duck(inferred_type, cn)
                   for cn in constraint_names if cn in self.duck_constraints):
                return
            constraint_str = ' | '.join(constraint_names)
            self.errors.append(
                f"Generic constraint violation: type '{inferred_type.name}' "
                f"does not satisfy constraint '{constraint_str}' "
                f"for parameter '{param_name}' at {line}:{col}"
            )

    def _infer_generic_types(self, func_def: FuncDef, args: List[Any], generic_params: List[str]) -> Dict[str, Type]:
        """使用统一化算法推断泛型函数的类型参数（Scala 风格）"""
        inferred = {}
        
        # 提取参数类型
        arg_types = []
        for arg in args:
            if isinstance(arg, tuple) and len(arg) == 2:
                arg_types.append(self._visit(arg[1]))
            else:
                arg_types.append(self._visit(arg))
        
        # 第一轮：直接匹配
        for i, param in enumerate(func_def.params):
            if i < len(arg_types) and arg_types[i]:
                param_type_node = getattr(param.type_annotation, 'id', None) if param.type_annotation else None
                if param_type_node in generic_params and param_type_node not in inferred:
                    inferred[param_type_node] = arg_types[i]
        
        # 第二轮：从嵌套泛型中推断（如 list[T] → 从 list[int] 推断 T = int）
        for i, param in enumerate(func_def.params):
            if i < len(arg_types) and arg_types[i]:
                param_type_node = getattr(param.type_annotation, 'id', None) if param.type_annotation else None
                if param_type_node in generic_params and param_type_node not in inferred:
                    # 检查是否可以从父类型推断
                    inferred[param_type_node] = arg_types[i]
        
        # 第三轮：从约束中获取默认类型
        for gp in generic_params:
            if gp not in inferred:
                # 无法推断，使用 object 作为默认值
                inferred[gp] = Type("object")
        
        return inferred

    def _substitute_generic_params(self, target_type: Type, substitutions: Dict[str, Type]) -> Type:
        """递归替换类型中的泛型参数（Scala 风格的类型替换）"""
        if target_type is None:
            return Type("object")
        
        # 如果类型名在替换映射中，直接替换
        if target_type.name in substitutions:
            return substitutions[target_type.name]
        
        # 递归替换泛型参数
        if target_type.generic_params:
            new_params = []
            for param in target_type.generic_params:
                new_params.append(self._substitute_generic_params(param, substitutions))
            return Type(target_type.name, 
                       is_pointer=target_type.is_pointer, 
                       is_ref=target_type.is_ref,
                       generic_params=new_params)
        
        # 返回原始类型
        return Type(target_type.name, 
                   is_pointer=target_type.is_pointer, 
                   is_ref=target_type.is_ref,
                   generic_params=list(target_type.generic_params))

    def _visit_Constant(self, node: Constant) -> Optional[Type]:
        # bool 必须在 int 之前检查，因为 Python 中 bool 是 int 的子类
        if isinstance(node.value, bool):
            return Type("bool")
        if isinstance(node.value, int):
            return Type("int")
        if isinstance(node.value, float):
            return Type("float")
        if isinstance(node.value, str):
            return Type("str")
        if isinstance(node.value, list):
            # 推断列表元素类型
            if node.value:
                element_types = []
                for item in node.value:
                    item_type = self._infer_constant_type(item)
                    if item_type:
                        element_types.append(item_type)
                # 使用 _find_common_type 找到公共类型
                common_type = self._find_common_type(element_types)
                return Type("list", generic_params=[common_type])
            else:
                # 空列表，默认 object
                return Type("list", generic_params=[Type("object")])
        if isinstance(node.value, dict):
            # 推断字典类型
            if node.value:
                key_types = []
                value_types = []
                for k, v in node.value.items():
                    key_type = self._infer_constant_type(k)
                    value_type = self._infer_constant_type(v)
                    if key_type:
                        key_types.append(key_type)
                    if value_type:
                        value_types.append(value_type)
                common_key = self._find_common_type(key_types)
                common_value = self._find_common_type(value_types)
                return Type("dict", generic_params=[common_key, common_value])
            else:
                # 空字典，默认 dict[object, object]
                return Type("dict", generic_params=[Type("object"), Type("object")])
        if isinstance(node.value, tuple):
            # 元组类型推断
            if node.value:
                element_types = []
                for item in node.value:
                    item_type = self._infer_constant_type(item)
                    if item_type:
                        element_types.append(item_type)
                # 元组可以有不同类型的元素
                return Type("tuple", generic_params=element_types if element_types else [Type("object")])
            else:
                return Type("tuple")
        return None

    def _infer_constant_type(self, value: Any) -> Optional[Type]:
        """从常量值推断类型"""
        if isinstance(value, bool):
            return Type("bool")
        if isinstance(value, int):
            return Type("int")
        if isinstance(value, float):
            return Type("float")
        if isinstance(value, str):
            return Type("str")
        if isinstance(value, ASTNode):
            return self._visit(value)
        if value is None:
            return Type("None")
        return Type("object")

    def _get_expected_type_from_context(self, node: ASTNode) -> Optional[Type]:
        """从上下文获取期望类型（双向类型检查）
        
        检查调用表达式是否处于类型化上下文中（如 let 声明、函数参数等），
        用于辅助泛型类型推断。
        """
        # 简化实现：检查当前是否有期望类型存储
        if hasattr(self, '_expected_type_stack') and self._expected_type_stack:
            return self._expected_type_stack[-1]
        return None

    def _get_type_from_node(self, node: Optional[ASTNode]) -> Optional[Type]:
        if node is None:
            return None
        if isinstance(node, Name):
            if node.id in self.type_map:
                return self.type_map[node.id]
            # 检查是否是类型别名
            if node.id in self.type_alias_defs:
                alias_def = self.type_alias_defs[node.id]
                # 如果类型别名有泛型参数但使用时没有提供，返回原始别名类型
                if getattr(alias_def, 'generic_params', []):
                    return Type(node.id)
                # 否则返回别名目标类型
                return self._get_type_from_node(alias_def.target)
            return Type(node.id)
        if isinstance(node, PointerType):
            base_type = self._get_type_from_node(node.base_type)
            if base_type:
                # 检查基础类型是否为Python对象类型
                python_types = {'str', 'list', 'dict', 'tuple', 'object', 'set'}
                if base_type.name in python_types:
                    self.errors.append(f"Cannot declare pointer to Python object type '{base_type.name}' at {node.line}:{node.col}")
                    return None
                return Type(base_type.name, is_pointer=True)
            return None
        if hasattr(node, 'kind') and node.kind == 'RefType':
            base_type = self._get_type_from_node(node.base_type)
            if base_type:
                # 检查基础类型是否为Python对象类型（引用不支持Python对象）
                python_types = {'str', 'list', 'dict', 'tuple', 'object', 'set'}
                if base_type.name in python_types:
                    self.errors.append(f"Cannot declare reference to Python object type '{base_type.name}' at {node.line}:{node.col}")
                    return None
                # 检查基础类型是否已经是引用类型（不允许 ref ref T）
                if base_type.is_ref:
                    self.errors.append(f"Cannot declare reference to reference type at {node.line}:{node.col}")
                    return None
                return Type(base_type.name, is_ref=True)
            return None
        if hasattr(node, 'kind') and node.kind == 'UnionType':
            # 联合类型：保留成员类型用于类型检查，名称仍为 object（与代码生成一致）
            members = []
            for t in node.types:
                mt = self._get_type_from_node(t)
                if mt:
                    members.append(mt)
            return Type("object", union_members=members)
        if hasattr(node, 'kind') and node.kind == 'GenericType':
            # typing 构造类型：Union/Optional 保留成员以便类型检查，其余按 object 处理
            # （与代码生成一致）；Callable 保留结构以便调用时推断返回类型
            if node.name in ('Union', 'Optional'):
                members = []
                for arg in node.args:
                    mt = self._get_type_from_node(arg)
                    if mt:
                        members.append(mt)
                if node.name == 'Optional':
                    members.append(Type("None"))
                return Type("object", union_members=members)
            if node.name in self._OBJECT_GENERIC_TYPES:
                return Type("object")
            # 处理泛型类型如 list[int]
            generic_params = []
            for arg in node.args:
                arg_type = self._get_type_from_node(arg)
                if arg_type:
                    generic_params.append(arg_type)

            # 检查是否是泛型类型别名，需要进行类型替换
            if node.name in self.type_alias_defs:
                alias_def = self.type_alias_defs[node.name]
                return self._substitute_generic_alias(alias_def, generic_params)

            return Type(node.name, generic_params=generic_params)
        return None

    def _type_in_union(self, value_type: Optional[Type], union_type: Type) -> bool:
        """判断 value_type 是否可被联合类型 union_type 接受（用于赋值/返回类型检查）"""
        if value_type is None or not getattr(union_type, 'union_members', None):
            return False
        # 动态类型（object/Any）无法在编译期精确判断，直接放行避免误报
        if value_type.name in ('object', 'Any'):
            return True
        member_names = {m.name for m in union_type.union_members}
        # None/Null 可赋值给含 None 的联合类型
        if value_type.name in ('None', 'Null') and ('None' in member_names or 'Null' in member_names):
            return True
        # 精确成员名匹配（含数值类型名，如 int/float/double）
        if value_type.name in member_names:
            return True
        # 值本身也是联合类型：要求其所有成员都被外层联合类型包含
        if getattr(value_type, 'union_members', None):
            return all(self._type_in_union(m, union_type) for m in value_type.union_members)
        return False

    def _substitute_generic_alias(self, alias_def: Any, concrete_params: List[Type]) -> Optional[Type]:
        """将泛型类型别名替换为具体类型
        
        Args:
            alias_def: 类型别名定义节点
            concrete_params: 具体的泛型参数类型列表
            
        Returns:
            替换后的具体类型
        """
        generic_params = getattr(alias_def, 'generic_params', [])
        
        # 检查参数数量是否匹配
        if len(generic_params) != len(concrete_params):
            self.errors.append(f"Type alias '{alias_def.name}' expects {len(generic_params)} generic parameter(s), but got {len(concrete_params)} at line {alias_def.line}")
            return None
        
        # 建立参数映射
        param_map = {generic_params[i]: concrete_params[i] for i in range(len(generic_params))}
        
        # 替换目标类型中的泛型参数
        return self._substitute_type(alias_def.target, param_map)
    
    def _substitute_type(self, type_node: Any, param_map: Dict[str, Type]) -> Optional[Type]:
        """递归替换类型节点中的泛型参数
        
        Args:
            type_node: 类型节点
            param_map: 泛型参数映射 {param_name: concrete_type}
            
        Returns:
            替换后的类型
        """
        if isinstance(type_node, Name):
            # 如果是泛型参数，替换为具体类型
            if type_node.id in param_map:
                return param_map[type_node.id]
            return Type(type_node.id)
        
        if isinstance(type_node, PointerType):
            base_type = self._substitute_type(type_node.base_type, param_map)
            if base_type:
                return Type(base_type.name, is_pointer=True)
            return None
        
        if hasattr(type_node, 'kind') and type_node.kind == 'GenericType':
            # 递归替换泛型类型的参数
            substituted_params = []
            for arg in type_node.args:
                substituted_arg = self._substitute_type(arg, param_map)
                if substituted_arg:
                    substituted_params.append(substituted_arg)
            return Type(type_node.name, generic_params=substituted_params)
        
        # 对于其他类型，返回原始名称
        if hasattr(type_node, 'id'):
            return Type(type_node.id)
        
        return None

    def _bind_pattern_names(self, pattern: Any, subject_type: Any) -> None:
        """从匹配模式中收集绑定变量名并注册到当前作用域（用于 case 体内引用）。"""
        if pattern is None:
            return
        kind = getattr(pattern, 'kind', None)
        if kind == 'Name':
            if pattern.id != '_':
                self.type_map[pattern.id] = subject_type or Type("object")
        elif kind == 'Call':
            for arg in getattr(pattern, 'args', []) or []:
                if hasattr(arg, 'kind'):
                    self._bind_pattern_names(arg, subject_type)
        elif kind in ('Tuple', 'List', 'ArrayPattern'):
            for elt in getattr(pattern, 'elements', []) or []:
                if hasattr(elt, 'kind'):
                    self._bind_pattern_names(elt, subject_type)
        elif isinstance(pattern, list):
            for p in pattern:
                if hasattr(p, 'kind'):
                    self._bind_pattern_names(p, subject_type)

    def _visit_MatchExpr(self, node: Any) -> Optional[Type]:
        """处理 match 表达式（作为返回值）"""
        subject_type = self._visit(node.subject) if node.subject else None

        case_types = []
        for case in node.cases:
            pattern = case.pattern
            condition = None
            # case pattern if condition 形式：pattern 是 {'pattern':..., 'condition':...} 字典
            if isinstance(pattern, dict) and 'pattern' in pattern:
                condition = pattern.get('condition')
                pattern = pattern['pattern']

            # 注册模式绑定的变量名（支持 Name / Call(元组) / 列表 / 数组模式）
            if pattern is not None:
                if isinstance(pattern, list):
                    for p in pattern:
                        if hasattr(p, 'kind'):
                            self._bind_pattern_names(p, subject_type)
                elif hasattr(pattern, 'kind'):
                    self._bind_pattern_names(pattern, subject_type)
                elif isinstance(pattern, str) and pattern != '_':
                    self.type_map[pattern] = subject_type or Type("object")

            # 访问 pattern 节点（仅对 AST 节点）
            if pattern is not None and hasattr(pattern, 'kind'):
                self._visit(pattern)
            # 访问 guard 条件
            if condition is not None:
                self._visit(condition)

            # 访问 case 体（单表达式列表），收集返回类型
            body_type = None
            if case.body:
                for stmt in case.body:
                    body_type = self._visit(stmt)
            if body_type:
                case_types.append(body_type)

        return self._find_common_type(case_types) if case_types else Type("object")

    def _visit_MatchStmt(self, node: Any) -> None:
        """处理 match 语句"""
        # 访问匹配表达式并获取其类型，用于模式绑定
        subject_type = self._visit(node.subject)
        
        # 访问各个 case 分支
        for case in node.cases:
            # 访问 pattern（包含变量绑定）
            if hasattr(case, 'pattern') and case.pattern:
                pattern = case.pattern
                # 如果 pattern 是字典（case pattern if condition），获取真正的 pattern
                if isinstance(pattern, dict) and 'pattern' in pattern:
                    pattern = pattern['pattern']
                # 注册模式绑定的变量名（供 case 体引用）
                if isinstance(pattern, list):
                    for p in pattern:
                        if hasattr(p, 'kind'):
                            self._bind_pattern_names(p, subject_type)
                elif isinstance(pattern, ArrayPattern):
                    for p in pattern.elements:
                        if hasattr(p, 'kind'):
                            self._bind_pattern_names(p, subject_type)
                elif hasattr(pattern, 'kind'):
                    self._bind_pattern_names(pattern, subject_type)
                # 访问 pattern 节点
                if isinstance(pattern, list):
                    for p in pattern:
                        if hasattr(p, 'kind'):
                            self._visit(p)
                elif isinstance(pattern, ArrayPattern):
                    for p in pattern.elements:
                        if hasattr(p, 'kind'):
                            self._visit(p)
                else:
                    # pattern 可能不是 AST 节点（如字典模式 / or 模式），仅对节点递归访问
                    if hasattr(pattern, 'kind'):
                        self._visit(pattern)
            # 访问 case 条件（如果有）
            if hasattr(case, 'condition') and case.condition:
                self._visit(case.condition)
            # 访问 case 体
            for stmt in case.body:
                self._visit(stmt)

    def _visit_GuardStmt(self, node: Any) -> None:
        """处理 guard 语句"""
        # 处理 guard let 形式：guard let target = expr else value
        if hasattr(node, 'is_let') and node.is_let and hasattr(node, 'let_target') and node.let_target:
            # 访问条件表达式（test 字段存储的是条件表达式）
            if hasattr(node, 'test') and node.test:
                test_type = self._visit(node.test)
            
            # 注册 let 绑定的变量
            let_target = node.let_target
            # Name 节点使用 id 属性，Pattern 节点使用 name 属性
            target_name = getattr(let_target, 'id', None) or getattr(let_target, 'name', None)
            if target_name:
                # 绑定变量的类型通常是布尔类型（用于条件判断）
                # 但实际类型应由条件表达式决定
                target_type = test_type if test_type else Type("bool")
                self.type_map[target_name] = target_type
        else:
            # 普通 guard 语句：guard cond else value
            # 访问条件表达式（GuardStmt 使用 test 字段而非 condition）
            if hasattr(node, 'test') and node.test:
                self._visit(node.test)
        
        # 访问 else 分支（如果有）
        if hasattr(node, 'orelse') and node.orelse:
            # orelse 可能是表达式或语句列表（多行形式）
            if isinstance(node.orelse, list):
                for stmt in node.orelse:
                    if hasattr(stmt, 'kind'):
                        self._visit(stmt)
            else:
                self._visit(node.orelse)

    def _visit_DeferStmt(self, node: Any) -> None:
        """处理 defer 语句"""
        # 访问 defer 块中的语句
        for stmt in node.body:
            self._visit(stmt)

    def _visit_Pattern(self, node: Any) -> None:
        """处理模式绑定（match case 中的变量绑定）"""
        # 在类型检查阶段，模式绑定会创建新的变量绑定
        # 默认类型为 Any（由具体匹配值决定）
        self.type_map[node.name] = Type("int")  # 暂定为 int，实际由匹配值决定

    def _visit_SlicePattern(self, node: Any) -> None:
        """处理切片模式（.. 或 ..var）"""
        # 如果有变量名，创建变量绑定
        if node.name is not None:
            self.type_map[node.name] = Type("list")

    def _visit_ArrayPattern(self, node: Any) -> None:
        """处理数组模式"""
        for element in node.elements:
            if hasattr(element, 'kind'):
                self._visit(element)

    def _visit_StructPattern(self, node: Any) -> None:
        """处理结构体解构模式"""
        for field_name, field_pattern in node.fields:
            if hasattr(field_pattern, 'kind'):
                self._visit(field_pattern)

    def _visit_TypePattern(self, node: TypePattern) -> None:
        """处理类型模式（case TypeName variable:）"""
        # 检查类型名称是否定义
        if node.type_name not in self.type_map:
            self.errors.append(f"Undefined type '{node.type_name}' in type pattern at {node.line}:{node.col}")
            return
        # 将绑定的变量注册到类型映射中
        self.type_map[node.name] = self.type_map[node.type_name]

    def _visit_AsPattern(self, node: AsPattern) -> None:
        """处理 As 模式（case pattern as name:）"""
        # 先访问内部模式（可能是列表 - 元组模式）
        if isinstance(node.pattern, list):
            for p in node.pattern:
                if hasattr(p, 'kind'):
                    self._visit(p)
        elif isinstance(node.pattern, dict):
            if 'pattern' in node.pattern:
                self._visit(node.pattern['pattern'])
            if 'or' in node.pattern:
                for p in node.pattern['or']:
                    if hasattr(p, 'kind'):
                        self._visit(p)
        elif hasattr(node.pattern, 'kind'):
            self._visit(node.pattern)
        # 将绑定的变量注册到类型映射中（类型由匹配值决定，暂定为 Any）
        self.type_map[node.name] = Type("int")

    def _visit_DictPattern(self, node: DictPattern) -> None:
        """处理字典模式（case {"key": value, **rest}:）"""
        # 访问每个键值对的模式
        for key_pattern, value_pattern in node.pairs:
            self._visit(key_pattern)
            self._visit(value_pattern)
        # 如果有剩余绑定，注册为 dict 类型
        if node.rest_name:
            self.type_map[node.rest_name] = Type("dict")

    def _visit_ExtractorPattern(self, node: ExtractorPattern) -> None:
        """处理提取器模式（参考Scala的unapply，如 Email(user, domain)）
        
        优先级：__match_args__ < __unapply__ < __unapply_seq__ < __unwarp__
        
        在类型检查阶段，我们检查类型是否存在，
        运行时会根据优先级查找对应的魔法方法来执行提取。
        """
        # 检查类型名称是否存在（作为结构体或类）
        if node.type_name not in self.type_map:
            # 如果类型未定义，可能是一个提取器函数，暂不报错
            # 提取器可以是普通函数或类
            pass
        
        # 访问每个参数模式
        for arg_pattern in node.args:
            if isinstance(arg_pattern, dict):
                if 'pattern' in arg_pattern:
                    self._visit(arg_pattern['pattern'])
                elif 'or' in arg_pattern:
                    for p in arg_pattern['or']:
                        self._visit(p)
            elif hasattr(arg_pattern, 'kind'):
                self._visit(arg_pattern)

    def _visit_RangePattern(self, node: RangePattern) -> None:
        """处理范围模式（case 1..10:）"""
        # 访问上下界表达式并捕获其类型（直接取自返回值，避免依赖未定义的 current_type）
        lower_type = self._visit(node.lower)
        upper_type = self._visit(node.upper)

        valid_types = {"int", "float", "double"}
        if lower_type and lower_type.name not in valid_types:
            self.errors.append(f"Range pattern lower bound must be numeric type, got {lower_type.name} at {node.line}:{node.col}")
        if upper_type and upper_type.name not in valid_types:
            self.errors.append(f"Range pattern upper bound must be numeric type, got {upper_type.name} at {node.line}:{node.col}")

    def _visit_Subscript(self, node: Any) -> Optional[Type]:
        """处理下标访问，返回容器内元素的类型"""
        base_type = self._visit(node.value)
        # 访问下标表达式（slice 可能是 dict 等，仅对 AST 节点递归访问）
        if hasattr(node.slice, 'kind'):
            self._visit(node.slice)
        if base_type is None:
            return Type("object")

        name = base_type.name
        params = base_type.generic_params or []

        # 列表：返回元素类型
        if name == "list" and params:
            return params[0]
        # 字典：返回 value 类型
        if name == "dict" and len(params) >= 2:
            return params[1]
        # 元组（带参）：常量整数下标取对应元素类型，否则回退为 object
        if name == "tuple" and params:
            idx = self._constant_index(node.slice)
            if idx is not None and 0 <= idx < len(params):
                return params[idx]
            return Type("object")
        # 裸容器或无法确定元素类型：回退为 object（而非整个容器类型）
        return Type("object")

    @staticmethod
    def _constant_index(slice_node: Any) -> Optional[int]:
        """从下标节点提取常量整数索引"""
        if isinstance(slice_node, int):
            return slice_node
        if hasattr(slice_node, 'value') and isinstance(slice_node.value, int):
            return slice_node.value
        if hasattr(slice_node, 'kind') and slice_node.kind in ('IntLiteral', 'Num'):
            val = getattr(slice_node, 'value', None)
            if isinstance(val, int):
                return val
        return None

    def _visit_ExceptionDef(self, node: ExceptionDef) -> None:
        """处理异常类型定义"""
        # 检查父类型是否有效
        if node.base_type:
            base_type = self._get_type_from_node(node.base_type)
            if not base_type:
                self.errors.append(f"Undefined base exception type '{node.base_type}' at {node.line}:{node.col}")
        # 检查字段类型
        for field in node.fields:
            if hasattr(field, 'name') and hasattr(field, 'type_annotation') and field.type_annotation:
                field_type = self._get_type_from_node(field.type_annotation)
                if not field_type:
                    self.errors.append(f"Undefined type for field '{field.name}' in exception '{node.name}' at {field.line}:{field.col}")

    def _visit_FromImport(self, node: Any) -> None:
        """处理 from module import names 语句，注册导入的名称到类型映射"""
        for name in getattr(node, 'names', []):
            self.type_map[name] = Type("object")
    
    def _visit_Import(self, node: Any) -> None:
        """处理 import module 语句，注册模块名称到类型映射"""
        module_name = getattr(node, 'module', '')
        if module_name:
            self.type_map[module_name] = Type("object")
    
    def _visit_MetaBlock(self, node: Any) -> None:
        """处理 meta block，允许前向引用"""
        self.in_meta_block = True
        for stmt in node.body:
            self._visit(stmt)
        self.in_meta_block = False

    def _visit_DuckDef(self, node: DuckDef) -> None:
        """处理 duck 约束定义

        编译期检查:
        1. 注册 duck 约束到类型注册表
        2. 验证约束的合法性（如引用的约束是否存在）
        3. 检测循环依赖
        4. 验证类型参数
        """
        # 检查重复定义
        if node.name in self.duck_constraints:
            self.errors.append(f"Duplicate duck constraint '{node.name}' at line {node.line}")
            return

        # 验证类型参数唯一性
        seen_params = set()
        for tp in node.type_params:
            if tp in seen_params:
                self.errors.append(f"Duplicate type parameter '{tp}' in duck constraint '{node.name}' at line {node.line}")
            seen_params.add(tp)

        # 注册 duck 约束
        duck_info = {
            "name": node.name,
            "type_params": node.type_params,
            "requirements": node.requirements
        }
        self.duck_constraints[node.name] = duck_info

        # 验证引用约束（前向引用在 _validate_duck_references 中统一处理）

        # 检测循环依赖
        cycle = self._detect_duck_cycle(node.name, set())
        if cycle:
            cycle_str = " -> ".join(cycle)
            self.errors.append(f"Circular duck constraint dependency: {cycle_str} (starting at '{node.name}' line {node.line})")

        # 验证 Self 返回类型仅在操作符/方法约束中使用
        for req in node.requirements:
            if req.return_type == "Self" and req.kind not in ("operator", "method"):
                self.errors.append(f"'Self' return type is only valid in operator/method constraints in duck '{node.name}' at line {req.line}")

    def _detect_duck_cycle(self, name: str, visiting: set) -> list:
        """检测 duck 约束间的循环依赖（DFS 着色算法）

        Returns:
            循环路径列表（如 ['A', 'B', 'A']），无循环则返回空列表
        """
        if name in visiting:
            return [name]
        if name not in self.duck_constraints:
            return []
        visiting.add(name)
        for req in self.duck_constraints[name]["requirements"]:
            if req.kind == "reference":
                cycle = self._detect_duck_cycle(req.name, visiting.copy())
                if cycle:
                    return [name] + cycle
        visiting.discard(name)
        return []

    def _visit_RaiseStmt(self, node: Any) -> None:
        """处理 raise 语句，检查异常类型"""
        if node.exc:
            exc_type = self._visit(node.exc)
            # 检查异常类型是否有效（必须是 Exception 或其子类）
            if exc_type and exc_type.name != "Exception":
                # 允许自定义异常类型，但建议是 Exception 的子类
                pass
        if node.cause:
            self._visit(node.cause)

    def _visit_TryStmt(self, node: Any) -> None:
        """处理 try/except/finally 语句"""
        # 访问 try 块
        for stmt in node.body:
            self._visit(stmt)
        
        # 访问 except 块，注册异常变量
        # TryStmt.handlers 是 (type, name, body) 元组列表
        for handler in getattr(node, 'handlers', []):
            except_type_ast, except_var_name, except_body = handler
            
            # 检查异常类型
            if except_type_ast:
                except_type = self._visit(except_type_ast)
                # 检查异常类型是否有效
                if except_type and except_type.name != "Exception":
                    # 允许自定义异常类型
                    pass
            else:
                except_type = Type("Exception")
            
            # 注册异常变量（如果有）
            if except_var_name:
                self.type_map[except_var_name] = except_type
            
            # 访问 except 块中的语句
            for stmt in except_body:
                self._visit(stmt)
            
            # 移除异常变量（仅在 except 块内有效）
            if except_var_name and except_var_name in self.type_map:
                del self.type_map[except_var_name]
        
        # 访问 finally 块（orelse）
        if hasattr(node, 'orelse') and node.orelse:
            for stmt in node.orelse:
                self._visit(stmt)
