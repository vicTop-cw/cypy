from typing import Dict, List, Any, Optional
# `_nominal_subtype_assignment` 的「值表达式未显式给出」哨兵（None 本身是合法取值）
_UNSET = object()
from cypyc.parser.parser import ASTNode, Module, FuncDef, LetStmt, ReturnStmt, BinOp, UnaryOp, Call, Name, Constant, PointerType, CastExpr, StructDef, ClassDef, TraitDef, ExceptionDef, EnumDef, ComptimeFuncDef, ArrayPattern, SlicePattern, StructPattern, TypePattern, DictPattern, AsPattern, ExtractorPattern, RangePattern, IfStmt, LambdaExpr, GenericType, TypeClassDef, TypeClassImpl, DuckDef, DuckRequirement
from cypyc.utils.ast_utils import ASTUtils


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
                self.generic_params == other.generic_params and
                # union_members 必须参与比较：Union/Optional 都编码为
                # Type('object', union_members=[...])，成员列表是它们唯一的区分量。
                # 省略它会让 Optional[int] == Optional[str] == object == Any 全部成立。
                self.union_members == other.union_members)

    # 显式声明不可哈希：定义了 __eq__ 而不定义 __hash__ 时 Python 会把 __hash__
    # 置为 None（与可变字段一致的正确行为）。这里写出来，避免有人顺手加一个
    # 漏掉 union_members 的 __hash__，造成 hash 与 eq 不一致。
    __hash__ = None

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
        # 可调用签名注册表（BUG-61）：`type_map[函数名]` 存的是**返回类型**，
        # 它没法回答「这个函数能接受几个什么类型的实参」，也没法回答
        # 「把函数名当值传出去时它是什么类型」——于是元数判定挂错表（`mk(one, 1)` 被判
        # `expected 1`）、实参类型无人比对、函数名作返回值被判成它的返回类型。
        # 这里按 SYNTAX/12 声明的 `Callable[[T1, T2], R]` **同一种形状**登记签名：
        # Type('Callable', generic_params=[Type('tuple', generic_params=[参数...]), 返回])，
        # 因此 `_callable_declared_params` 与既有的 Callable 判定共用同一套机制（INV：一个入口）。
        self.callable_sigs: Dict[str, Type] = {}
        # 同一批函数的元数区间 (必填下界, 上界)：有默认值的参数可省，独立存是因为
        # `Type` 的形状要与 `Callable[[T], R]` 的编码完全一致，不能塞私货。
        self.callable_arity: Dict[str, tuple] = {}
        # Trait 定义注册表（用于泛型约束检查）
        self.trait_defs: Dict[str, Any] = {}
        # Trait 实现注册表（用于检查类型是否实现了 trait）
        self.trait_impls: Dict[str, List[str]] = {}  # {trait_name: [type_name1, type_name2, ...]}
        # 类型别名定义注册表（用于泛型类型别名替换）
        self.type_alias_defs: Dict[str, Any] = {}  # {alias_name: TypeAlias node}
        # 命名约束注册表（SYNTAX/33 §2 / §5：constraint 是「名字 -> 成员集合」的一对多映射，
        # 与别名的「名字 -> 单个类型节点」不同构，因此**不复用** type_alias_defs ——
        # 否则 _get_type_from_node 遇到约束名会返回一个并不存在的类型，
        # 直接制造 C-2.1 要杜绝的假报错。键必须是 str（INV-3：Type 不可哈希）。
        self.constraint_defs: Dict[str, Any] = {}  # {constraint_name: ConstraintDef node}
        # 名义子类型注册表（SYNTAX/33 §3 / §5）。**边**不在这里：§5 明写「subtype 不新增
        # 注册表：把边写进现成的 inheritance_map」，由 `_is_subtype`（唯一入口，INV-2）自动
        # 生效。这张表只登记**声明本身**（name -> SubtypeDef 节点），因为有三处判定必须要
        # 知道「这个名字是 subtype 而不是 class」：
        #   * S-4.1/S-4.3 codegen 零运行时表示 ⇒ `isinstance(x, Meter)` 必须编译期报错
        #   * S-5.1 `impl Trait for Meter` 必须拒绝
        #   * S-3.3 兄弟 subtype 之间不可直转
        # 键必须是 str（INV-3：`Type.__hash__ = None`，不可当 dict key）。
        self.subtype_defs: Dict[str, Any] = {}  # {subtype_name: SubtypeDef node}
        # subtype 的直接基类型名（收集遍写、`_finalize_subtype_edges` 读）：
        # 声明顺序可以是 `subtype A <: B` 在 `subtype B <: float` 之前，
        # 所以继承闭包必须等整张表收齐后再算。
        self._subtype_edges: Dict[str, str] = {}
        # 别名/枚举名集合：pass 1 就能确定，供 S-1.2 判定基类型的**种类**
        # （`type_alias_defs` 要到第二遍才填，用它会漏掉「subtype 声明在别名之前」）
        self._type_alias_names: set = set()
        self.enum_type_names: set = set()
        # 诊断去重（同一 subtype 声明只报一次环/深度）
        self._subtype_reported: set = set()
        # 非致命告警通道（CompileResult 目前只上送 errors，见 SYNTAX/33 §5 的落地缺口）
        self.warnings: List[str] = []
        # 诊断去重：同一约束名在值位置只报一次（C-2.1），同一调用点只报第一条违例（C-5.5）
        self._constraint_value_position_reported: set = set()
        self._bound_violation_reported_nodes: set = set()
        self._circular_constraint_reported: set = set()
        # 正在遍历的泛型声明（class）的形式类型参数名：`-> T` 里的 T 不是返回类型（SYNTAX/11「泛型类」规则 4）
        self._generic_formal_params: List[str] = []
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
        # 每轮检查重置诊断去重状态（SYNTAX/33 C-2.1 / C-5.5）
        self._constraint_value_position_reported = set()
        self._bound_violation_reported_nodes = set()
        self._circular_constraint_reported = set()
        self._visit(node)
        # 注解形态闭集校验（SYNTAX/02 R7 补条款；BUG-34/BUG-108 的拒绝面）
        self._validate_annotation_shapes(node)
        # 所有 duck 约束定义完成后，统一校验引用（允许跨 meta 块前向引用）
        self._validate_duck_references()
        return self.type_map

    # SYNTAX/02「注解形态闭集（R7 补）」：只有这些节点算类型形态
    ANNOTATION_TYPE_KINDS = ("Name", "GenericType", "PointerType", "UnionType", "RefType")
    ANNOTATION_SHAPE_HINTS = {
        "Constant": "类型名或 list<int> / tuple<int, int> / dict<str, int>",
        "List": "list<int>", "ListComp": "list<int>",
        "DictLiteral": "dict<str, int>", "Tuple": "tuple<int, int>",
    }

    def _check_annotation_shape(self, ann: Any) -> None:
        """校验注解是不是「类型形态」，字面量形态必须诊断（SYNTAX/02 注解形态闭集）。

        历史缺陷（BUG-34/BUG-108）：`xs: [int]` 被 parser 编成 `Constant(value=[Name(int)])`，
        分析器完全不认，生成器末路 `str(node)` 于是把 `Constant(line=2, col=9)` 当类型名写进 .pyx，
        产物必编译失败而 CLI 仍回 rc=0。这里补拒绝面，文案点名正确写法并带行列。
        未知节点形态一律放行（不发明拒绝）——生成器侧已退化成 object，不会再漏 repr。
        """
        if ann is None or not isinstance(ann, ASTNode):
            return
        kind = getattr(ann, "kind", None)
        if kind in self.ANNOTATION_TYPE_KINDS:
            nested = list(getattr(ann, "args", None) or [])
            base = getattr(ann, "base_type", None)
            if base is not None:
                nested.append(base)
            nested.extend(getattr(ann, "types", None) or [])
            for sub in nested:
                self._check_annotation_shape(sub)
            return
        hint = self.ANNOTATION_SHAPE_HINTS.get(kind)
        if hint is None:
            return
        value = getattr(ann, "value", None)
        for sub in (value if isinstance(value, (list, tuple)) else []):
            self._check_annotation_shape(sub)
        self.errors.append(
            f"Invalid type annotation at {getattr(ann, 'line', 0)}:{getattr(ann, 'col', 0)}"
            f" (期望 {hint}，实际是 {kind} 字面量形态)")

    def _validate_annotation_shapes(self, node: Any) -> None:
        """遍历 AST 上所有携带 `type_annotation` 的节点做形态校验。

        `comptime:` 行内形式（`comptime: [1, 2]`）天然不受本节约束：ComptimeStmt 不携带
        `type_annotation` 字段（实测 97 份可解析语料里 3 个 ComptimeStmt 节点、0 个带该字段），
        不需要额外的类型跳过。既有锁
        tests/analyzer/test_r5_fix_comptime_types.py::test_bug83_inline_form_control_still_clean
        与 tests/test_annotation_shape.py::test_comptime_inline_form_is_not_an_annotation 认领该行为。
        """
        stack = [node]
        seen = set()
        while stack:
            cur = stack.pop()
            if not isinstance(cur, ASTNode) or id(cur) in seen:
                continue
            seen.add(id(cur))
            ann = getattr(cur, "type_annotation", None)
            if ann is not None:
                self._check_annotation_shape(ann)
            for value in vars(cur).values():
                if isinstance(value, ASTNode):
                    stack.append(value)
                elif isinstance(value, (list, tuple)):
                    stack.extend(v for v in value if isinstance(v, ASTNode))
                elif isinstance(value, dict):
                    stack.extend(v for v in value.values() if isinstance(v, ASTNode))


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
                # SYNTAX/33 C-2.2 表第 4 行（实测基线 B5）的前提：`class Dog(Pet)` 的
                # 继承边必须真的进 inheritance_map，否则 _is_subtype 的那条继承分支
                # 是死代码、子类永远满足不了父类界。
                base_names = []
                for base in (getattr(stmt, 'bases', None) or []):
                    bname = getattr(base, 'id', None) or getattr(base, 'name', None)
                    if bname and bname not in base_names:
                        base_names.append(bname)
                if base_names:
                    self._register_inheritance(stmt.name, base_names)
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
                # BUG-21: GenericType（`impl Show for Box<T>`）没有 .id，默认分支
                # str(node) 会把 "GenericType(line=5, col=15)" 当成类型名登记，
                # 于是这条实现在约束检查里永远匹配不上。口径与 codegen 侧
                # cython_generator.py:482-486 一致：泛型取基类型名。
                for_type_name = (getattr(stmt.for_type, 'id', None)
                                 or getattr(stmt.for_type, 'name', None)
                                 or str(stmt.for_type))
                if trait_name not in self.trait_impls:
                    self.trait_impls[trait_name] = []
                if for_type_name not in self.trait_impls[trait_name]:
                    self.trait_impls[trait_name].append(for_type_name)
            elif hasattr(stmt, 'kind') and stmt.kind == 'TypeAlias':
                # 注册类型别名
                self._type_alias_names.add(stmt.name)
                target_type = self._get_type_from_node(stmt.target)
                if target_type:
                    self.type_map[stmt.name] = target_type
            elif hasattr(stmt, 'kind') and stmt.kind == 'ConstraintDef':
                # 注册命名约束（SYNTAX/33 §5：注册位置照抄 type_alias_defs 那一处）。
                # **不**写 type_map：约束不是类型（C-2.1），写进去就等于允许
                # `let x: Numeric` 这种值位置用法。收集遍只做注册，
                # 成员合法性/环检测留给第二遍的 _visit_ConstraintDef。
                self.constraint_defs[stmt.name] = stmt
            elif hasattr(stmt, 'kind') and stmt.kind == 'SubtypeDef':
                # 注册名义子类型（SYNTAX/33 §5 的 subtype 列）。
                # **必须**写 type_map：`let m: Meter` 的声明类型要解析成 `Type("Meter")`
                # 本身而不是它的基类型 —— 这正是与 `type Meter = float`（别名，解析成
                # `Type("float")`）的唯一分歧点，也是 S-3.4「别名给不出方向性」的落点。
                self.subtype_defs[stmt.name] = stmt
                self.type_map[stmt.name] = Type(stmt.name)
                base_name = getattr(stmt.base, 'id', None) or getattr(stmt.base, 'name', None)
                if base_name:
                    self._subtype_edges[stmt.name] = str(base_name)
            elif isinstance(stmt, EnumDef):
                # 注册枚举类型
                self.enum_type_names.add(stmt.name)
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
        
        # 名义子类型的继承闭包：S-7.1 允许 `subtype A <: B` 写在 `subtype B <: float`
        # 之前，所以「边」必须等整张表收齐后再展开成传递闭包并入 inheritance_map。
        self._finalize_subtype_edges()

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
    
    def _visit_ClassDef(self, node: ClassDef) -> None:
        """泛型类的类体遍历（SYNTAX/11「泛型类」规则 4）。

        遍历形状与从前一致（照旧走 `_visit_children`），只是把所属类声明的类型参数名记成
        **形式参数**：`def get(self) -> T` 里的 `T` 不是返回类型。函数名表是按裸名建的
        （`type_map['get']`），承载不了接收者的代入 —— 把形式参数登记进去，任何一次
        `get()` 都会报「expected int, got T」。真正的代入发生在 `_visit_Attribute`
        （按接收者的类型实参逐位替换），这里只负责让名字表不外泄形式参数名。
        """
        params = list(getattr(node, 'generic_params', []) or [])
        prev = self._generic_formal_params
        if params:
            self._generic_formal_params = sorted(set(prev) | set(params))
        try:
            self._visit_children(node)
        finally:
            self._generic_formal_params = prev

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
        if return_type is not None and return_type.name in self._generic_formal_params:
            # 名字表按裸名建，装不下接收者的代入 ⇒ 形式参数一律登记成未知（object），
            # 由 `_visit_Attribute` 那条按类型实参代入的真形去判（SYNTAX/11「泛型类」规则 4）。
            return_type = Type("object")
        self.current_function_return_type = return_type
        # BUG-61：函数名要有「可调用签名」，`type_map[名字]` 只有返回类型，判不了元数与实参
        self._register_callable(node, return_type)

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
                # 即使没有类型注解，也注册为 object 类型，确保参数在作用域中可见。
                # 但 `self` 例外：它由接收者提供，`_visit_StructDef`/`_visit_ClassDef`/impl
                # 已经把它绑成接收者类型；再用 object 覆盖，成员的类型就永远查不出来（BUG-63）。
                if param.name == "self" and "self" in self.type_map:
                    pass
                else:
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

    def _bound_names_of_pattern(self, pattern: Any) -> List[str]:
        """从解构模式中提取被绑定的变量名（let (a, b) / let [a, *rest] / let {..} 等）"""
        names: List[str] = []
        if pattern is None:
            return names
        if isinstance(pattern, str):
            if pattern and pattern != '_':
                names.append(pattern)
            return names
        if isinstance(pattern, (list, tuple)):
            for p in pattern:
                names.extend(self._bound_names_of_pattern(p))
            return names
        if isinstance(pattern, ArrayPattern):
            for e in pattern.elements:
                names.extend(self._bound_names_of_pattern(e))
            if pattern.rest_name:
                names.append(pattern.rest_name)
            return names
        if isinstance(pattern, SlicePattern):
            if pattern.name:
                names.append(pattern.name)
            return names
        if isinstance(pattern, DictPattern):
            for _k, v in pattern.pairs:
                names.extend(self._bound_names_of_pattern(v))
            if pattern.rest_name:
                names.append(pattern.rest_name)
            return names
        if isinstance(pattern, AsPattern):
            names.extend(self._bound_names_of_pattern(pattern.pattern))
            if pattern.name and pattern.name != '_':
                names.append(pattern.name)
            return names
        name = getattr(pattern, 'name', None)
        if isinstance(name, str) and name and name != '_':
            names.append(name)
            return names
        nid = getattr(pattern, 'id', None)
        if isinstance(nid, str) and nid and nid != '_':
            names.append(nid)
        return names

    def _visit_LetStmt(self, node: LetStmt) -> None:
        # 元组/列表解包：let (a, b) = ... 时 node.name 为模式（列表或 ArrayPattern 等）
        if not isinstance(node.name, str):
            declared_type = self._get_type_from_node(node.type_annotation)
            value_type = self._visit(node.value) if node.value else None
            element_types = []
            if value_type and value_type.name == 'tuple' and value_type.generic_params:
                element_types = value_type.generic_params
            for i, nm in enumerate(self._bound_names_of_pattern(node.name)):
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
            # SYNTAX/33 §3.3：名义子类型的可赋值方向（上转隐式、下转必须 `as`）。
            # 只有当声明类型或值类型之一是 subtype 时才会返回非 None，
            # 其余语料一律落回下面的原有分支（对既有行为零影响）。
            if declared_type and value_type and declared_type != value_type:
                _nominal = self._nominal_subtype_assignment(node, declared_type, value_type)
                if _nominal is not None:
                    self.type_map[node.name] = declared_type
                    self.mutable_map[node.name] = node.mutable
                    return
            if declared_type and value_type and declared_type != value_type:
                # 值为 object/Any（动态类型或未知返回）时，采用声明类型，避免误报
                if value_type.name in ('object', 'Any'):
                    self.type_map[node.name] = declared_type
                # 联合类型：值必须匹配任一成员，否则报错（必须在 object 宽松分支之前判定）
                elif declared_type.union_members:
                    if self._type_in_union(value_type, declared_type):
                        self.type_map[node.name] = declared_type
                    else:
                        self._mismatch("Type mismatch", declared_type, value_type, node)
                # object/Any 类型可以接受任何类型赋值（Scala 风格）
                elif declared_type.name == 'object' or declared_type.name == 'Any':
                    self.type_map[node.name] = declared_type
                # 允许指针类型匹配（void* 可以赋值给 int* 等）
                elif declared_type.is_pointer and value_type.is_pointer:
                    self.type_map[node.name] = declared_type
                # 同名单容器（list/dict/tuple/set/Pair 等），声明带参数时采用声明的精确类型。
                # 覆盖：空容器构造器 list[object]、嵌套 list[list[object]]、dict/set/Pair 的无参形式等。
                # 「采用声明类型」不等于「元素位也放行」——后者交 SYNTAX/02 的元素判定（BUG-137）。
                elif declared_type.name == value_type.name and declared_type.generic_params:
                    self._check_container_elements(declared_type, value_type, node)
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
                            self._mismatch("Type mismatch", declared_type, value_type, node)
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
                            self._mismatch("Type mismatch", declared_type, value_type, node)
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
            # 声明要的是 Callable、返回的是函数名 ⇒ 比可调用签名而不是它的返回类型（BUG-61/C03）
            value_type = self._value_type_for_declared(self.current_function_return_type,
                                                      node.value, value_type)
            if self.current_function_return_type and value_type:
                # 联合返回类型：显式校验成员，避免被下面的 object 宽松分支放过
                if self.current_function_return_type.union_members:
                    if self._type_in_union(value_type, self.current_function_return_type):
                        return value_type
                    self._mismatch("Return type mismatch", self.current_function_return_type,
                                                   value_type, node)
                    return value_type
                target_name = self.current_function_return_type.name
                # 声明为 object 或 type 时接受任意返回类型
                if target_name in ('object', 'type'):
                    return value_type
                # 返回值为 object（无法精确推断）时放行，避免误报
                if value_type.name in ('object', 'Any'):
                    return value_type
                # 返回值是容器（含空容器构造器 list[object]、无参 dict/set/Pair、嵌套
                # list[list[object]]、含 None/object 参数的元组等），而声明为带参数的
                # 同名容器时，采用声明的精确类型，避免误报
                # 同上：采用声明类型不等于放弃元素位判定（SYNTAX/02，BUG-137）
                if (target_name == value_type.name
                        and target_name in ('list', 'dict', 'tuple', 'set', 'Pair', 'Array')
                        and self.current_function_return_type.generic_params):
                    self._check_container_elements(
                        self.current_function_return_type, value_type, node, 'Return ')
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
                # SYNTAX/33 §3.3：subtype 参与返回类型时走**同一张**方向表
                # （S-3.1 上转隐式放行；下转必须显式 `as`，报同一模板诊断）。
                _nominal_ret = self._nominal_subtype_assignment(
                    node, self.current_function_return_type, value_type, node.value)
                if _nominal_ret is not None:
                    return value_type
                # 允许数值类型的隐式转换：bool → int → float → double
                numeric_types = {'bool', 'int', 'float', 'double'}
                if target_name in numeric_types and value_type.name in numeric_types:
                    type_order = ['bool', 'int', 'float', 'double']
                    value_idx = type_order.index(value_type.name)
                    target_idx = type_order.index(target_name)
                    if value_idx > target_idx:
                        # 向下转换需要显式转换
                        self._mismatch("Return type mismatch", self.current_function_return_type,
                                                   value_type, node)
                elif self.current_function_return_type != value_type:
                    self._mismatch("Return type mismatch", self.current_function_return_type,
                                                   value_type, node)
            return value_type
        # 无返回值，检查是否是 void 返回类型
        if self.current_function_return_type and self.current_function_return_type.name != 'None':
            self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got None at {node.line}:{node.col}")
        return Type("None")

    def _visit_BinOp(self, node: BinOp) -> Optional[Type]:
        left_type = self._visit(node.left)
        right_type = self._visit(node.right)

        if left_type and right_type:
            # 成员 / 身份 运算结果恒为 bool（用户无法改变其返回类型）
            if node.op in ('in', 'is', 'not in', 'is not', 'not is'):
                return Type('bool')

            # 比较 / 相等：默认 bool；但当操作数为自定义类型且重载了对应
            # dunder 方法、其声明返回类型为非 bool（如 SQL 表达式树
            # col == 5 -> ClauseElement）时，采用声明的返回类型，
            # 使 (col == 5) & (col2 > 18) 之类的链式表达式类型自洽（BUG-023 动机）。
            if node.op in ('==', '!=', '<', '>', '<=', '>='):
                custom = self._comparison_override_result_type(node.op, left_type, right_type)
                return custom if custom is not None else Type('bool')

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

    _CMP_OP_DUNDERS = {
        '==': '__eq__', '!=': '__ne__', '<': '__lt__',
        '>': '__gt__', '<=': '__le__', '>=': '__ge__',
    }

    def _comparison_override_result_type(self, op: str, left_type: Type,
                                         right_type: Type) -> Optional[Type]:
        """若比较运算符的操作数为自定义 struct/class 且重载了对应 dunder 方法、
        其声明返回类型为非 bool/None/object 的具体类型，则返回该类型；否则 None。

        左操作数优先（`a == b` 调用 `a.__eq__(b)`），未命中再看右操作数。
        """
        dunder = self._CMP_OP_DUNDERS.get(op)
        if dunder is None:
            return None
        for tname in (left_type.name, right_type.name):
            methods = self.magic_methods.get(tname)
            if not methods:
                continue
            method = methods.get(dunder)
            if method is None:
                continue
            rt = self._get_type_from_node(getattr(method, 'return_type', None))
            if rt is not None and rt.name not in ('bool', 'None', 'object', ''):
                return rt
        return None

    def _visit_UnaryOp(self, node: UnaryOp) -> Optional[Type]:
        return self._visit(node.operand)

    def _value_type_for_declared(self, declared: Any, node: Any, visited: Optional[Type]):
        """按**声明侧**决定值类型：声明是 `Callable` 且值是个函数名 ⇒ 用它的可调用签名。"""
        if isinstance(declared, Type) and declared.name == "Callable" \
                and isinstance(node, Name) and node.id in self.callable_sigs:
            return self.callable_sigs[node.id]
        return visited

    def _register_callable(self, node, return_type: Optional[Type]) -> None:
        """把 `def f(a: T1, b: T2) -> R` 登记成与 `Callable[[T1, T2], R]` **同一种形状**的签名。

        缺注解的参数按 `object` 处理（既有宽松分支一致）；带泛型参数、变长位置/关键字参数、
        或 `.` 分隔符的函数**整条不登记** —— 那种形状 SYNTAX 没声明判定口径，
        宁可不判也不误判（与 `_callable_declared_params` 的取舍同源）。
        """
        name = getattr(node, "name", None)
        if not name or getattr(node, "generic_params", None):
            return
        params = list(getattr(node, "params", None) or [])
        for p in params:
            if getattr(p, "is_var_positional", False) or getattr(p, "is_var_keyword", False) \
                    or getattr(p, "is_dot_separator", False):
                return
        declared: List[Type] = []
        required = 0
        for p in params:
            pt = self._get_type_from_node(getattr(p, "type_annotation", None))
            declared.append(pt if pt is not None else Type("object"))
            if getattr(p, "default_value", None) is None:
                required += 1
        # 方法是 `接收者.名` 的调用面，而注册表的键是裸名 —— 用裸名登记会和同名自由函数
        # 互相顶掉（谁后定义谁生效），误报比不报更糟。方法签名这一层走 RC3 的属性解析。
        if params and getattr(params[0], "name", None) == "self":
            return
        self.callable_sigs[name] = Type(
            "Callable",
            generic_params=[Type("tuple", generic_params=declared),
                            return_type or Type("object")])
        self.callable_arity[name] = (required, len(declared))

    def _mismatch(self, kind: str, want: Any, got: Any, node: Any) -> None:
        """诊断文案统一出口（BUG-64）：类型一律经 `_type_display`，内部编码不外泄。"""
        self.errors.append(
            f"{kind}: expected {self._type_display(want)}, "
            f"got {self._type_display(got)} at {node.line}:{node.col}")

    def _type_display(self, t: Any) -> str:
        """给用户看的类型名（BUG-64）：内部编码 `tuple[...]` 不许出现在诊断文案里。

        这里只做**显示**，判定仍然走 `Type` 对象本身 —— 反过来（拿字符串比对判定）会把
        显示层的措辞变化变成语义变化。
        """
        if not isinstance(t, Type):
            return str(t)
        if t.name == "Callable" and t.generic_params:
            params = self._callable_declared_params(t.generic_params)
            ret = t.generic_params[-1]
            if params is not None:
                inner = ", ".join(self._type_display(p) for p in params)
                return f"Callable[[{inner}], {self._type_display(ret)}]"
        prefix = ("ref " if t.is_ref else "") + ("*" if t.is_pointer else "")
        if t.union_members:
            inner = ", ".join(self._type_display(m) for m in t.union_members)
            return f"Union[{inner}]"
        if t.generic_params:
            inner = ", ".join(self._type_display(p) for p in t.generic_params
                              if isinstance(p, Type) or isinstance(p, str))
            return f"{prefix}{t.name}[{inner}]"
        return f"{prefix}{t.name}"

    def _callable_signature_assignable(self, want: Type, got: Type) -> bool:
        """`Callable` 与 `Callable` 之间的兼容：同元数、逐位参数兼容、返回同类型。

        参数用**同序同位**的协变近似（不是逆变）：这与既有 `_check_callable_arity`
        一样只在「形状对不上」时报错，逆变规则 SYNTAX 未声明 ⇒ 不在本环引入。
        """
        w = self._callable_declared_params(want.generic_params)
        g = self._callable_declared_params(got.generic_params)
        if w is None or g is None or len(w) != len(g):
            return False
        for wp, gp in zip(w, g):
            if self._callable_arg_mismatch(wp, gp):
                return False
        wr, gr = want.generic_params[-1], got.generic_params[-1]
        return not self._callable_arg_mismatch(wr, gr)

    def _callable_arg_mismatch(self, want: Type, got: Type) -> bool:
        """两侧都是具体类型且互不兼容才算不匹配；动态值一律放行（既有宽松分支）。"""
        if not isinstance(want, Type) or not isinstance(got, Type):
            return False
        if want.union_members or got.union_members:
            return False
        if want.name in ("object", "Any") or got.name in ("object", "Any", "None", "Null"):
            return False
        if want.name == "Callable" or got.name == "Callable":
            if want.name == "Callable" and got.name == "Callable":
                return not self._callable_signature_assignable(want, got)
            return True
        if want.is_pointer and got.is_pointer:
            return False
        if want.is_pointer != got.is_pointer:
            return True
        if want.name == got.name:
            # 同名容器（list[int] vs list[str]）既有代码里也是宽松的，别在这里收紧
            return False
        order = ["bool", "int", "float", "double"]
        if want.name in order and got.name in order and order.index(got.name) <= order.index(want.name):
            return False
        try:
            return not self._is_subtype(got, want)
        except Exception:
            return False

    def _call_is_judgable(self, node: Call) -> bool:
        """build block / 管道**脱糖**出来的调用是「裸名 + 没有位置信息」的组合：形状是脱糖造的、
        报错也指不回源码 ⇒ 不判。真实源码里的 `self.cb(1, 2)` 同样没有位置（parser 不给
        Attribute 调用记行列），但它是用户写的形状 ⇒ 必须可判，所以豁免只按这一**组合**。
        """
        if getattr(node, "line", 0) or getattr(node, "col", 0):
            return True
        return not hasattr(node.func, "id")

    def _check_callable_arg_types(self, node: Call, declared: list, arg_types: list) -> None:
        if not self._call_is_judgable(node):
            return
        # 形状有歧义一律不判（与 `_check_callable_arity` 同一条取舍）：括号元组字面量在
        # parser 里就是 Python tuple，与关键字实参同形 ⇒ 判了会把 `f((1, 2))` 报成实参类型错。
        if any(isinstance(a, tuple) for a in node.args):
            return
        for idx, (want, got) in enumerate(zip(declared, arg_types)):
            got = self._value_type_for_declared(want, node.args[idx], got)
            # 括号元组字面量与「一次给多个实参」在 parser 里同形（`f((1, 2))`），
            # 分不清用户是想传一个 tuple 还是想传两个 ⇒ 实参是裸 tuple 时不判
            # ——这与 R3 在元数那一层「形状对不上就不判」是同一条取舍。
            if getattr(want, "name", None) != "tuple" and isinstance(got, Type) \
                    and got.name == "tuple":
                continue
            if self._callable_arg_mismatch(want, got):
                self.errors.append(
                    f"Argument {idx + 1} type mismatch: expected "
                    f"{self._type_display(want)}, got {self._type_display(got)} "
                    f"at {node.line}:{node.col}")

    def _callable_declared_params(self, args) -> Optional[list]:
        """取 `Callable[[T1, T2], R]` 声明的入参类型列表。

        `_get_type_from_node` 把方括号里的参数表包成一个 `tuple` 型：generic_params 形如
        `[tuple[T1, T2], R]`。形状不是这个模样时返回 None —— 调用方据此**跳过判定**，
        宁可不报也不误报（`Callable` 的变长/畸形写法 SYNTAX 未声明，不在本环语义内）。
        """
        if not isinstance(args, (list, tuple)) or len(args) < 2:
            return None
        first = args[0]
        if isinstance(first, Type) and first.name == 'tuple':
            return list(first.generic_params or [])
        return None

    def _check_callable_arity(self, node: Call, args, bounds=None) -> None:
        """SYNTAX/12 声明了 `Callable[[T], R]` 标注，附录 C 却把它列在「尚未实现」里。
        这里补上入参元数这一层：实参与声明不一致才报错。

        关键字实参在 parser 里是 `('name', value)` 这种**首元素为 str 的元组**，
        而括号元组字面量 `f((1, 2))` 是单个表达式节点 ⇒ 只按前者识别。
        声明是位置参数表，混用关键字实参时对不上形状 ⇒ 这种调用一律不判。
        `bounds` 是 `(下界, 上界)`：带默认值的函数可以少给，缺省按精确匹配。
        """
        declared = self._callable_declared_params(args)
        if declared is None:
            return
        positional = []
        for a in node.args:
            if isinstance(a, tuple) and len(a) == 2 and isinstance(a[0], str):
                return
            positional.append(a)
        lo, hi = bounds if bounds else (len(declared), len(declared))
        if not (lo <= len(positional) <= hi):
            self.errors.append(
                f"Callable arity mismatch: expected {lo if lo == hi else f'{lo}..{hi}'}, "
                f"got {len(positional)} at {node.line}:{node.col}"
            )

    def _generic_arity_diagnostic(self, name: str, params: List[str], n_args: int,
                                  line: int, col: int) -> Optional[str]:
        """声明侧类型参数表 vs 使用侧类型实参个数的比对。

        SYNTAX/11 的「调用点的类型实参」规则 2 与「泛型类」规则 3 共用这一份文案 ——
        两处各写一份正是本轮要防的失效形状（同一事实两个读法）。
        """
        if not params:
            return (f"Type arguments on non-generic '{name}': it declares no type parameter, "
                    f"got {n_args} at {line}:{col}")
        if n_args != len(params):
            return (f"Type argument count mismatch: '{name}' declares {len(params)} "
                    f"type parameter(s), got {n_args} at {line}:{col}")
        return None

    def _check_declared_bounds(self, decl: Any, binding: Dict[str, "Type"],
                               node: Any) -> None:
        """使用侧的类型实参要过**声明界**（`T: int | float` / `T: Trait` / `T: Container[T]`）。

        判定整个复用函数调用位那一份 `_check_generic_constraint` —— 注解位/实例化位各写一份
        收窄版正是 BUG-129 的失效形状（字面量位那份只认单名界，`T: int | float` 静默放行）。
        注解位节点会被多处重复访问 ⇒ 按整条消息去重，不叠第二条同事实的账。
        """
        constraints = getattr(decl, "generic_constraints", {}) or {}
        if not constraints:
            return
        marked = len(self.errors)
        for param, arg_type in binding.items():
            if param in constraints and arg_type is not None:
                self._check_generic_constraint(param, arg_type, constraints[param], node)
        fresh = self.errors[marked:]
        if fresh:
            del self.errors[marked:]
            for msg in fresh:
                if msg not in self.errors:
                    self.errors.append(msg)

    def _bind_explicit_type_args(self, node: Call, func_name: str) -> Optional[Dict[str, "Type"]]:
        """调用点显式类型实参的判定与代入（SYNTAX/11「调用点的类型实参」规则 2/5）。

        返回 `{类型参数名: Type}`；被调方没有类型参数或调用点没写实参时返回 None。
        副作用只在"写了实参"时发生：元数不符、非泛型被调方挂实参 ⇒ 各报一条诊断。
        """
        type_args = getattr(node, "type_args", None) or []
        if not type_args:
            return None
        decl = (self.func_defs.get(func_name) or self.struct_defs.get(func_name)
                or self.class_defs.get(func_name))
        if decl is None:
            return None  # 名字未解析成功时由 `Undefined name` 那条负责，这里不再叠一条
        params = list(getattr(decl, "generic_params", []) or [])
        line = getattr(node, "line", 0)
        col = getattr(node, "col", 0)
        diag = self._generic_arity_diagnostic(func_name, params, len(type_args), line, col)
        if diag:
            self.errors.append(diag)
        if not params:
            return None
        binding: Dict[str, "Type"] = {}
        for param, arg_node in zip(params, type_args):
            t = self._get_type_from_node(arg_node)
            binding[param] = t if t is not None else Type("object")
        # 类/结构体的显式类型实参：界判定在此完成。函数由 `_visit_Call` 里那份统一判
        # （那里的 `inferred_types` 可能就是这个 binding，重复判会得到两条同事实的账）。
        if func_name not in self.func_defs:
            self._check_declared_bounds(decl, binding, node)
        return binding

    def _visit_Call(self, node: Call) -> Optional[Type]:
        func_type = self._visit(node.func)
        # 处理参数：支持位置参数和关键字参数；位置实参的**类型**要留给元数/兼容判定
        arg_types: List[Optional[Type]] = []
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                self._visit(arg[1])
            else:
                # 位置参数
                arg_types.append(self._visit(arg))

        # 属性位上的可调用体（`self.cb(1, 2)`）与名字调用共用同一套判定（BUG-63 的 C11 面）：
        # 接收者上的字段声明成 `Callable` 时，元数与实参类型同样要判。
        if isinstance(func_type, Type) and func_type.name == "Callable" \
                and not hasattr(node.func, "id") and self._call_is_judgable(node):
            callable_declared = self._callable_declared_params(func_type.generic_params)
            if callable_declared is not None:
                self._check_callable_arity(node, func_type.generic_params)
                self._check_callable_arg_types(node, callable_declared, arg_types)
            ret = func_type.generic_params[-1] if func_type.generic_params else None
            if isinstance(ret, Type):
                return ret
        
        # 如果 func 是简单名称
        if hasattr(node.func, 'id'):
            func_name = node.func.id
            # S-4.3：`isinstance(x, <subtype>)` 必须编译期报错 —— subtype 是「零运行时
            # 表示」的声明（S-4.1），放任会得到 codegen 的 `_cypy_is_instance_of` 里
            # `globals().get('Meter') is None -> return False` 那种恒假的静默误判
            # （实测基线 X4）。
            if func_name == 'isinstance':
                self._check_isinstance_on_subtype(node)

            # 检查是否是泛型函数调用（需要推断类型参数）
            # SYNTAX/11「调用点的类型实参」规则 2/5：写了显式实参就按声明顺序代入（元数在此判定），
            # 没写才走原来的统一化推断。返回值同时用于下面 `generic_params` 那支。
            explicit_binding = self._bind_explicit_type_args(node, func_name)
            if func_name in self.func_defs:
                func_def = self.func_defs[func_name]
                generic_params = getattr(func_def, 'generic_params', [])
                generic_constraints = getattr(func_def, 'generic_constraints', {})
                
                if generic_params:
                    if explicit_binding:
                        inferred_types = explicit_binding
                    else:
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
            
            # 用户定义的函数：判定走**可调用签名**（BUG-61/62），不再走 `type_map[名字]`
            # ——那里存的只是返回类型，用它判元数会把 `mk(one, 1)` 判成 `expected 1`。
            if func_name in self.callable_sigs:
                sig = self.callable_sigs[func_name]
                declared = self._callable_declared_params(sig.generic_params)
                if declared is not None and self._call_is_judgable(node):
                    self._check_callable_arity(node, sig.generic_params,
                                               self.callable_arity.get(func_name))
                    self._check_callable_arg_types(node, declared, arg_types)
                ret = sig.generic_params[-1] if sig.generic_params else None
                return ret if isinstance(ret, Type) else Type("object")

            # 先检查是否是用户定义的函数
            if func_name in self.type_map:
                t = self.type_map[func_name]
                # 变量类型为 Callable[...] 时，调用应返回其返回类型（最后一个类型参数）
                if getattr(t, 'name', None) == 'Callable':
                    args = getattr(t, 'args', None) or getattr(t, 'generic_params', None)
                    if args:
                        self._check_callable_arity(node, args)
                        declared = self._callable_declared_params(args)
                        if declared is not None:
                            self._check_callable_arg_types(node, declared, arg_types)
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
        # char / void 是 SYNTAX/04-pointer-types.md 里列出的指针基类型
        # （:59 `def allocate_buffer(size: int) -> *char:`、:87 `let void_ptr: *void = …`），
        # 名字表缺席会让同一符号的返回注解位被误判 Undefined name（BUG-84）。
        # 只补这两张文档列过的名字：long/short/unsigned 在 SYNTAX/*.md 里查无此名，不进表。
        builtin_types = ['int', 'float', 'double', 'bool', 'str', 'None', 'Exception', 'list',
                         'dict', 'set', 'tuple', 'object', 'Any', 'Never', 'Nothing', 'Null',
                         'Callable', 'callable', 'char', 'void']
        builtin_constants = ['True', 'False', '__main__', 'null']
        builtin_functions = ['print', 'len', 'malloc', 'free', 'sizeof', 'addr', 'ord', 'range', 'type',
                             'sorted', 'isinstance', 'getattr', 'hash', 'id', 'super', 'abs', 'min', 'max',
                             'sum', 'any', 'all', 'enumerate', 'zip', 'map', 'filter', 'reversed',
                             'repr', 'open', 'iter',
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

        # S-5.1 / 裁决 D-6：`impl Trait for <subtype>` v1 拒绝（必须在「空实现直接登记」
        # 那条捷径**之前**，否则 `impl Show for Cent: pass` 会静默注册进 trait_impls）
        if self._check_impl_on_subtype(node):
            return
        
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

    # ---------------------------------------------------------------- 命名约束
    # SYNTAX/33 §2：constraint 是「界」而不是「类型」。这里三件事共用同一批助手：
    #   * C-1.2 / C-2.5 成员合法性（必须是已声明的类型名）
    #   * C-2.3 / C-2.4 成员并集展开 + 环检测（指名路径）
    #   * C-2.1 约束名出现在值位置 = 编译期错误

    #: 可作为约束成员的内置标量/容器名（C-1.2 的第一类成员）
    _CONSTRAINT_BUILTIN_NAMES = {
        'int', 'float', 'double', 'long', 'char', 'bool', 'str', 'bytes', 'None',
        'object', 'Any', 'list', 'dict', 'set', 'tuple', 'Exception',
        'Never', 'Nothing', 'Null',
    }

    def _member_type_name(self, member: Any) -> Optional[str]:
        """C-1.2：成员只允许「类型名 [+ 实参]」——Name 或 GenericType，其余一律拒绝。"""
        kind = getattr(member, 'kind', None)
        if kind == 'Name':
            return str(member.id)
        if kind == 'GenericType':
            # 2.2.1 / 裁决 D-2：带实参的成员只比头部名
            return str(member.name)
        return None

    def _is_declared_type_name(self, name: str) -> bool:
        """名字是否是「本模块里已声明的类型」——C-2.5 的判定集合。"""
        if not name:
            return False
        if name in self._CONSTRAINT_BUILTIN_NAMES or name in self._known_type_names:
            return True
        if name in self.constraint_defs:
            return True
        if name in self.subtype_defs:
            return True
        if (name in self.class_defs or name in self.struct_defs
                or name in self.trait_defs or name in self.duck_constraints
                or name in self.type_classes):
            return True
        # EnumDef / ExceptionDef / 用户类都在收集遍写进 type_map
        return name in self.type_map

    def _expand_constraint_members(self, name: str, chain: Optional[List[str]] = None):
        """C-2.3 传递展开 + C-2.4 环检测。

        Returns:
            (按声明顺序去重后的成员类型名列表, 环路径列表或 None)
            环路径形如 ['A', 'B', 'A']，用于 `circular constraint definition: A -> B -> A`。
        """
        path = list(chain or [])
        if name in path:
            return [], path[path.index(name):] + [name]
        node = self.constraint_defs.get(name)
        if node is None:
            return [], None
        path.append(name)
        members: List[str] = []
        seen = set()
        for member in getattr(node, 'members', []) or []:
            member_name = self._member_type_name(member)
            if not member_name:
                continue
            if member_name in self.constraint_defs:
                nested, cycle = self._expand_constraint_members(member_name, path)
                if cycle:
                    return [], cycle
                for n in nested:
                    if n not in seen:
                        seen.add(n)
                        members.append(n)
            elif member_name not in seen:
                seen.add(member_name)
                members.append(member_name)
        return members, None

    def _report_constraint_in_value_position(self, name: str, line: int, col: int) -> None:
        """C-2.1：`let x: Numeric` / `def f(v: Numeric)` / `as Numeric` / `list<Numeric>`
        全部必须编译期报错——约束没有可替换的目标（它的展开是**一组**候选类型，
        不是单个类型），所以别名能做的事约束故意不能做。"""
        key = (name, line, col)
        if key in self._constraint_value_position_reported:
            return
        self._constraint_value_position_reported.add(key)
        self.errors.append(
            f"'{name}' is a constraint, not a type: it can only appear as a generic "
            f"bound 'T: {name}'. For a usable union type write "
            f"'type {name} = int | float'. Use 'constraint' as a bound only "
            f"(SYNTAX/33 C-2.1) at {line}:{col}"
        )

    def _check_constraint_definition(self, node: Any) -> None:
        """`constraint Name = A | B` 声明本身的合法性（C-1.2 / C-2.3 / C-2.4 / C-2.5）。"""
        members = getattr(node, 'members', []) or []
        names: List[str] = []
        for member in members:
            member_name = self._member_type_name(member)
            if member_name is None:
                # C-1.2：*int / [T] / {k: v} / 字面量类型都不是「类型名」
                self.errors.append(
                    f"constraint '{node.name}' member "
                    f"'{self._constraint_member_text(member)}' is not a type name: "
                    f"members must be plain type names like 'int' or 'Pet', "
                    f"not pointer/container/literal types (SYNTAX/33 C-1.2) "
                    f"at {getattr(member, 'line', node.line)}:"
                    f"{getattr(member, 'col', node.col)}"
                )
                continue
            if member_name in self.constraint_defs or member_name == node.name:
                names.append(member_name)
                continue
            if not self._is_declared_type_name(member_name):
                self.errors.append(
                    f"constraint '{node.name}' references undefined type "
                    f"'{member_name}' (not a builtin, class, struct, enum, subtype or "
                    f"constraint in this module) at {getattr(member, 'line', node.line)}:"
                    f"{getattr(member, 'col', node.col)}"
                )
                continue
            names.append(member_name)
        # C-2.4：环（含自引用 `constraint Bad = int | Bad`），必须指名路径
        _, cycle = self._expand_constraint_members(node.name)
        if cycle:
            rendered = ' -> '.join(cycle)
            if rendered not in self._circular_constraint_reported:
                self._circular_constraint_reported.add(rendered)
                self.errors.append(
                    f"circular constraint definition: {rendered} at {node.line}:{node.col}")
            return
        # C-6 / §2.6 接口：与同名 duck 约束冲突时**名义优先**，并报 warning 说明遮蔽
        if node.name in self.duck_constraints:
            self.warnings.append(
                f"constraint '{node.name}' shadows the duck constraint of the same name; "
                f"the nominal constraint wins in bound checks (SYNTAX/33 §2.6) "
                f"at {node.line}:{node.col}")

    def _constraint_member_text(self, member: Any) -> str:
        """把成员节点渲染成人读文本，用于 C-1.2 诊断（'*int' / '[T]' 等）。"""
        kind = getattr(member, 'kind', None)
        if kind == 'PointerType':
            return '*%s' % self._constraint_member_text(getattr(member, 'base_type', None))
        if kind == 'Name':
            return str(member.id)
        if kind == 'GenericType':
            return '%s[...]' % member.name
        if kind == 'UnionType':
            return ' | '.join(self._constraint_member_text(t) for t in member.types)
        if member is None:
            return '?'
        return str(getattr(member, 'id', getattr(member, 'value', kind or member)))

    def _visit_ConstraintDef(self, node: Any) -> None:
        """处理命名约束声明：注册 + 声明合法性检查（第二遍）。"""
        self.constraint_defs[node.name] = node
        self._check_constraint_definition(node)

    # ---------------------------------------------------------------- 名义子类型
    # SYNTAX/33 §3：`subtype Name <: Base` 是「同一种表示、不同的身份」。
    # 四条地基：
    #   S-2.2  `_is_subtype` 是唯一真源 —— 边进 inheritance_map，不新增第二套判定
    #   S-3.3  可赋值方向单向（上转隐式、下转必须 `as`、兄弟不可直转）
    #   S-4.1  零运行时表示 —— 所以 isinstance/impl 这类「运行时身份」用法必须编译期拒绝
    #   S-7.2  链有硬上限（继承递归必须有终止保证）

    #: S-7.2 的链深度上限（**subtype 名**的个数，不含终点的基类型）
    SUBTYPE_CHAIN_LIMIT = 8

    #: S-1.2 允许作基类型的内置标量名
    _SUBTYPE_BUILTIN_BASES = {
        'int', 'float', 'double', 'long', 'short', 'char', 'bool', 'str', 'bytes',
    }

    def _subtype_base_kind(self, base_name: str) -> str:
        """直接基类型的**种类**（S-1.2 的白名单 + D-5 的别名拒绝 + S-7.3 未声明）。"""
        if not base_name:
            return 'none'
        if base_name in self.subtype_defs:
            return 'subtype'
        if base_name in self.class_defs:
            return 'class'
        if base_name in self.struct_defs:
            return 'struct'
        if base_name in self.enum_type_names:
            return 'enum'
        if base_name in self._SUBTYPE_BUILTIN_BASES:
            return 'builtin'
        if base_name in ('object', 'Any', 'Never', 'Nothing', 'Null', 'None'):
            return 'top'
        # 以下是「存在但不能当基类型」的四类，各自一条定向诊断
        if base_name in self.trait_defs:
            return 'trait'
        if base_name in self.constraint_defs:
            return 'constraint'
        if base_name in self._type_alias_names or base_name in self.type_alias_defs:
            return 'alias'
        if base_name in self.duck_constraints:
            return 'duck'
        return 'unknown'

    def _subtype_ancestor_chain(self, name: str):
        """沿 subtype 边向上走（S-7.1 链式 / S-1.3 环 / S-7.2 深度）。

        Returns:
            (祖先名列表，状态)，状态为 None（正常）/ 'circular' / 'deep'。
            列表含终点的那个非 subtype 基类型，例如 `A <: B <: float` 的 A 得到
            `['B', 'float']`；环/超限时列表带完整路径，用于诊断里指名（同 C-2.4 模板）。
        """
        chain: List[str] = []
        seen = {name}
        cur = name
        subtypes = 1
        while True:
            base = self._subtype_edges.get(cur)
            if not base:
                return chain, None
            if base in seen:
                return chain + [base], 'circular'
            chain.append(base)
            seen.add(base)
            if base not in self.subtype_defs:
                return chain, None      # 终点：基类型不是 subtype
            subtypes += 1
            if subtypes > self.SUBTYPE_CHAIN_LIMIT:
                return chain, 'deep'
            cur = base

    def _subtype_chain_status(self, name: str) -> str:
        """一条 subtype 链的**唯一**判定：'ok' / 'no_base' / 'bad_base:<kind>' /
        'circular' / 'deep'。`_check_subtype_definition`（出诊断）与
        `_finalize_subtype_edges`（进 inheritance_map）共用，避免两套结论。"""
        base = self._subtype_edges.get(name)
        if not base:
            return 'no_base'
        kind = self._subtype_base_kind(base)
        if kind not in ('builtin', 'class', 'struct', 'enum', 'subtype'):
            return 'bad_base:' + kind
        _, problem = self._subtype_ancestor_chain(name)
        return problem or 'ok'

    def _subtype_direct_base(self, name: str) -> Optional[str]:
        return self._subtype_edges.get(name)

    def _subtype_runtime_name(self, name: str) -> str:
        """S-4.2：subtype 的运行时身份**就是**沿链下降到第一个非 subtype 的名字。"""
        cur = self._subtype_edges.get(name)
        seen = {name}
        while cur and cur in self.subtype_defs and cur not in seen:
            seen.add(cur)
            cur = self._subtype_edges.get(cur)
        return cur or 'object'

    def _common_subtype_base(self, left: str, right: str) -> str:
        """两个 subtype 的**最近**共同基类型（S-3.3 的诊断要指名它，不能只说「不行」）。"""
        def chain_of(name: str) -> List[str]:
            out: List[str] = []
            cur = name
            seen = set()
            while cur and cur not in seen:
                seen.add(cur)
                out.append(cur)
                cur = self._subtype_edges.get(cur)
            return out
        left_chain, right_chain = chain_of(left), chain_of(right)
        for candidate in left_chain:
            if candidate in right_chain:
                return candidate
        return left_chain[-1] if left_chain else '?'

    def _finalize_subtype_edges(self) -> None:
        """S-2.2：把 subtype 边并进现成的 `inheritance_map`，展开成**传递闭包**。

        `_is_subtype` 的继承分支只比直接父类名，因此 S-7.1 的 `A <: B <: float` 要让
        `_is_subtype(A, float)` 成立，就得在这里把整条链摊进 A 的父类列表。
        这**不是**第二套可赋值判定（INV-2 禁的是判定分支，不是数据）：判定的入口仍然只有
        `_is_subtype` 一个。坏链（未声明基类型 / trait / 环 / 超限）不进闭包，
        它们的诊断由 `_check_subtype_definition` 出。
        """
        for name in self.subtype_defs:
            if self._subtype_chain_status(name) != 'ok':
                continue
            ancestors, _ = self._subtype_ancestor_chain(name)
            merged = list(self.inheritance_map.get(name, []))
            for anc in ancestors:
                if anc and anc not in merged:
                    merged.append(anc)
            self.inheritance_map[name] = merged

    def _subtype_error(self, message: str) -> None:
        """subtype 诊断去重：环会被链上的每个节点各报一次，同文案只留一条。"""
        if message in self._subtype_reported:
            return
        self._subtype_reported.add(message)
        self.errors.append(message)

    def _check_subtype_definition(self, node: Any) -> None:
        """`subtype Name <: Base` 声明自身的合法性：S-1.2 / S-1.3 / S-7.2 / S-7.3。"""
        name = node.name
        line, col = node.line, node.col
        base_node = getattr(node, 'base', None)
        base_kind = getattr(base_node, 'kind', None)
        # S-1.2：基类型必须是**单个类型名**。联合形态在 parser 就硬拒（S-1.2 的
        # `subtype N <: int | float`），这里再钉一次，绝不退回「只吃左半、右半掉在原地
        # 变成一句裸表达式」的静默吞。
        if base_kind in ('UnionType', 'PointerType', 'RefType', 'VecType'):
            self._subtype_error(
                f"subtype '{name}' may not have a '{base_kind}' base type: the base must be "
                f"a single type name (a builtin scalar, class, struct, enum or another "
                f"subtype), other forms are not allowed (SYNTAX/33 S-1.2) at {line}:{col}")
            return
        if base_kind == 'GenericType':
            rendered = getattr(base_node, 'name', '?')
            self._subtype_error(
                f"subtype '{name}' may not derive from the generic application "
                f"'{rendered}<...>': a nominal subtype needs one representable base type, "
                f"generic arguments are not allowed (SYNTAX/33 S-1.2); use the bare name or "
                f"declare a struct at {getattr(base_node, 'line', line)}:"
                f"{getattr(base_node, 'col', col)}")
            return
        base = self._subtype_edges.get(name)
        if not base:
            self._subtype_error(
                f"subtype '{name}' has no base type name at {line}:{col}")
            return
        status = self._subtype_chain_status(name)
        if status.startswith('bad_base:'):
            kind = status.split(':', 1)[1]
            if kind == 'trait':
                self._subtype_error(
                    f"subtype '{name}' may not have trait '{base}' as its base: a trait is an "
                    f"interface with no runtime representation, and a nominal subtype must "
                    f"derive from exactly one representable type (SYNTAX/33 S-1.2) -- traits "
                    f"are not allowed as a base; use 'class {base}' plus inheritance if you "
                    f"need shared behaviour at {line}:{col}")
            elif kind == 'constraint':
                self._subtype_error(
                    f"subtype '{name}' may not derive from constraint '{base}': a constraint "
                    f"is a generic bound, not a type, so it cannot be a base "
                    f"(SYNTAX/33 S-1.2, C-2.1); constraints are not allowed here -- list "
                    f"the concrete types instead at {line}:{col}")
            elif kind == 'alias':
                self._subtype_error(
                    f"subtype '{name}' may not derive from type alias '{base}' (ruling D-5 / "
                    f"SYNTAX/33 S-1.2): an alias is replaced by its target, so the nominal "
                    f"identity would drift with the alias definition -- aliases are not "
                    f"allowed as a base; derive from the target type itself at {line}:{col}")
            elif kind == 'duck':
                self._subtype_error(
                    f"subtype '{name}' may not derive from duck constraint '{base}': a duck "
                    f"constraint is a structural predicate, not a representable type "
                    f"(SYNTAX/33 S-1.2) at {line}:{col}")
            elif kind == 'top':
                self._subtype_error(
                    f"subtype '{name}' may not have '{base}' as its base: '{base}' is the top "
                    f"type, so nominal derivation from it carries no information -- every "
                    f"value already is one (SYNTAX/33 S-1.2); it is not allowed as a base; "
                    f"derive from a concrete representation (int, float, str, a class, a "
                    f"struct or another subtype) at {line}:{col}")
            else:
                self._subtype_error(
                    f"subtype '{name}' refers to unknown base type '{base}' (not a builtin, "
                    f"class, struct, enum or subtype in this module, and unions / generic "
                    f"applications / traits / constraints / type aliases are not allowed as "
                    f"a base) at {line}:{col}")
            return
        if status == 'circular':
            chain, _ = self._subtype_ancestor_chain(name)
            self._subtype_error(
                f"circular subtype definition: {' -> '.join([name] + chain)} "
                f"(a subtype chain must terminate at a representable type; self-reference is "
                f"circular too) at {line}:{col}")
            return
        if status == 'deep':
            chain, _ = self._subtype_ancestor_chain(name)
            self._subtype_error(
                f"subtype chain too deep (limit {self.SUBTYPE_CHAIN_LIMIT}): "
                f"{' -> '.join([name] + chain)} (SYNTAX/33 S-7.2) at {line}:{col}")
            return

    def _visit_SubtypeDef(self, node: Any) -> None:
        """处理名义子类型声明：注册（收集遍已完成）+ 声明合法性检查（第二遍）。"""
        self.subtype_defs[node.name] = node
        self._check_subtype_definition(node)

    # ---- S-3 可赋值方向 ------------------------------------------------------

    def _is_fresh_literal(self, value_node: Any) -> bool:
        """字面量没有名义身份：`let m: Meter = 2.5` 成立，`let m: Meter = f` 不成立。

        这正是 S-3.4 要区分的东西 —— 别名 `type Meter = float` 时两个方向**都**静默通过
        （实测基线 S2），所以只有字面量这一类被放行，才不会把 subtype 又退化回别名。
        """
        kind = getattr(value_node, 'kind', None)
        if kind == 'Constant':
            return isinstance(getattr(value_node, 'value', None),
                              (bool, int, float, str, bytes))
        if kind == 'UnaryOp' and getattr(value_node, 'op', '') in ('-', '+'):
            return self._is_fresh_literal(getattr(value_node, 'operand', None))
        return False

    def _nominal_subtype_assignment(self, node: Any, declared_type: Type,
                                    value_type: Type, value_expr: Any = _UNSET
                                    ) -> Optional[bool]:
        """SYNTAX/33 §3.3 的方向表，返回 True=放行 / False=已报错 / None=与本条无关。

        ```
        Meter → float（基类型）     隐式，允许          S-3.1
        float → Meter（子类型）     必须 `as`           S-3.2 / S-3.2.1
        Meter → object / Any       隐式，允许（top）    S-3.1
        ```
        判定仍然只有 `_is_subtype` 一个入口（INV-2）；这里只决定「不放行时说什么」。
        两侧都不是 subtype 时**必须**返回 None，让原有的宽松分支（object/None/容器
        归一/`__implicit_into__`）原样生效 —— 这是本次改动对既有语料零影响的前提。
        `let` 与 `return` 共用这一张表（返回值就是赋给结果变量），所以 `value_expr`
        缺省时从 node 上取 `.value`。
        """
        d, v = declared_type.name, value_type.name
        if d not in self.subtype_defs and v not in self.subtype_defs:
            return None
        if self._is_subtype(value_type, declared_type):
            return True                                     # S-3.1 上转 / 同身份
        if v in ('object', 'Any', 'None', 'Null'):
            return None       # 动态值与空值沿用既有的宽松分支，不在此处收紧
        # S-3.3 的赋值面：`m = k`（两个兄弟身份）与 `m as k` 一样必须拒绝 ——
        # 「防止兄弟混用」就是这类声明存在的全部意义，只在 `as` 上拦、在赋值上放行
        # 等于没做。
        if (v in self.subtype_defs and d in self.subtype_defs
                and not self._is_subtype(declared_type, value_type)):
            self.errors.append(
                f"cannot assign '{v}' to '{d}': nominal subtypes of the same base are not "
                f"mutually comparable (SYNTAX/33 S-3.3); go through the base "
                f"'{self._common_subtype_base(d, v)}' "
                f"({'x as ' + self._common_subtype_base(d, v) + ' as ' + d}) if that is "
                f"really what you mean at {getattr(node, 'line', 0)}:"
                f"{getattr(node, 'col', 0)}")
            return False
        if d not in self.subtype_defs:
            return None       # 只有值是 subtype 的其它不匹配：交回原有的 Type mismatch
        source = getattr(node, 'value', None) if value_expr is _UNSET else value_expr
        base = self._subtype_edges.get(d)
        # 字面量没有名义身份：`let m: Meter = 2.5` / `let a: A = 1.0`（A<:B<:float，
        # S-7.1 链上的**任一**基类型都能吃掉这个字面量）。
        if self._is_fresh_literal(source):
            ancestors, _ = self._subtype_ancestor_chain(d)
            for anc in ancestors:
                if anc and self._is_subtype(value_type, Type(anc)):
                    return True
        if base and self._is_subtype(declared_type, value_type):
            value_text = getattr(source, 'id', None) or 'value'
            self.errors.append(
                f"cannot assign '{v}' to '{d}': '{d}' is a nominal subtype of '{base}'"
                f"{' (SYNTAX/33 S-7.1 chain)' if base in self.subtype_defs else ''}; "
                f"downcast requires an explicit '{value_text} as {d}'. A nominal type does "
                f"not flow back into its base on its own -- with 'type {d} = {base}' both "
                f"directions would pass silently, which is exactly what S-3.4 refuses at "
                f"{getattr(node, 'line', 0)}:{getattr(node, 'col', 0)}")
            return False
        return None

    # ---- S-4.3 / S-5.1：零运行时表示的两个必拒用法 --------------------------

    def _report_subtype_has_no_runtime_identity(self, type_name: str, use: str,
                                                line: int, col: int) -> None:
        """S-4.3 的唯一文案：subtype 没有运行时类型对象（`isinstance` 与类型模式共用）。"""
        runtime = self._subtype_runtime_name(type_name)
        self.errors.append(
            f"'{type_name}' is a subtype with no runtime type object (SYNTAX/33 S-4.1): "
            f"its runtime type is '{runtime}', so {use} can only ever be a silent guess. "
            f"Use the base type ('{runtime}') there, or promote '{type_name}' to a "
            f"'struct' if you need runtime identity at {line}:{col}")

    def _check_isinstance_on_subtype(self, node: Any) -> None:
        """`isinstance(m, Meter)` 必须编译期报错（S-4.3）。

        实测基线 X4：放任不管会得到 `_cypy_is_instance_of` 的
        `globals().get('Meter') is None -> return False` —— 一个**恒假**的静默误判。
        """
        seen = set()
        for arg in (getattr(node, 'args', None) or [])[1:]:
            type_name = getattr(arg, 'id', None)
            if not type_name or type_name not in self.subtype_defs or type_name in seen:
                continue
            seen.add(type_name)
            self._report_subtype_has_no_runtime_identity(
                type_name, f"isinstance(..., {type_name})",
                getattr(arg, 'line', node.line), getattr(arg, 'col', node.col))

    def _check_impl_on_subtype(self, node: Any) -> Optional[bool]:
        """S-5.1 / 裁决 D-6：`impl Trait for <subtype>` v1 拒绝。

        这是实测出来的硬约束而不是审美：trait 的运行时判定用
        `type(obj).__name__ in _cypy_trait_registry[trait]`
        （cython_generator.py 的 `_emit_trait_isinstance_support`）。subtype 的运行时名
        就是基类型名（S-4.2），于是注册 'Meter' **永远匹配不上**（静默失效）；
        为了让它匹配而改注册基类型，又会把所有基类型值都判成实现了该 trait（语义泄漏）。
        """
        for_type_name = getattr(node.for_type, 'id', str(node.for_type))
        if for_type_name not in self.subtype_defs:
            return False
        runtime = self._subtype_runtime_name(for_type_name)
        trait_name = node.trait_name
        self.errors.append(
            f"cannot implement trait '{trait_name}' for '{for_type_name}': "
            f"'{for_type_name}' is a nominal subtype with no runtime identity (its runtime "
            f"type is '{runtime}'), so the trait registry would either never match it or "
            f"capture every '{runtime}' value (SYNTAX/33 S-5.1, ruling D-6); implement "
            f"'{trait_name}' for '{runtime}' instead, or declare '{for_type_name}' as a "
            f"struct at {node.line}:{node.col}")
        return True


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
                
                # 检查泛型参数约束：复用调用位那一份判定。原来这里只认单名界
                # （`getattr(constraint_ast, 'id')` 对 `T: int | float` 取到 None ⇒ 静默放行），
                # 联合/trait/typeclass/F-bounded 四类界现在三处使用位口径一致。
                self._check_declared_bounds(struct_def, inferred_types, node)
                
                # 构建泛型参数列表
                generic_args = []
                for param in generic_params:
                    generic_args.append(inferred_types.get(param, Type(param)))
                
                return Type(struct_name, generic_params=generic_args)
        
        return Type(struct_name)

    def _visit_DictLiteral(self, node: Any) -> Optional[Type]:
        """字典字面量推断出 ``dict<K, V>``（SYNTAX/02「字典字面量的键值位判定」规则 1）。

        BUG-141 的根因就在这一层缺失：`_visit` 没有 DictLiteral 分支 ⇒ 落到 `_visit_children`
        返回 None ⇒ `let x: dict<str, int> = {"a": "b"}` 连「实得类型」都没有，
        声明侧的键值位无从比较（`_check_container_elements` 里 dict 那一格因此永不触发）。
        """
        keys, values = [], []
        for pair in list(getattr(node, 'pairs', []) or []):
            if isinstance(pair, (tuple, list)) and len(pair) == 2:
                keys.append(self._visit(pair[0]))
                values.append(self._visit(pair[1]))
        return Type("dict", generic_params=[self._slot_lub(keys), self._slot_lub(values)])

    def _slot_lub(self, parts: list) -> Type:
        """键位/值位各自的「最宽可表类型」：同形取该类型并保留参数，数值串取阶梯最宽，
        其余塌成 ``object``。塌位是**放行**而不是拒绝（规则 1 末句、规则 6 的有账漏报）。"""
        known = [p for p in parts
                 if p is not None and p.name not in ('object', 'Any')
                 and not getattr(p, 'union_members', None)]
        if not known:
            return Type("object")
        names = {p.name for p in known}
        if len(names) == 1:
            head = known[0]
            if len({self._type_display(x) for x in known}) == 1:
                return Type(head.name, generic_params=list(head.generic_params or []))
            return Type(head.name)   # 同名不同参（{"a": [1], "b": ["s"]}）⇒ 参数位按占位放行
        if names <= set(self._NUMERIC_WIDENING):
            widest = max(known, key=lambda x: self._NUMERIC_WIDENING.index(x.name))
            return Type(widest.name)
        return Type("object")

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
                # 裸名接收者（`let w: Wrap = Wrap()`）没有类型实参可代入 ⇒ 形式参数按擦除（object）处理，
                # 与上面 class 分支同一条规则 3；从前这里登记成 `Type(param)`，把 `T` 当返回类型外泄。
                for param in getattr(struct_def, 'generic_params', []):
                    self.type_map[param] = Type("object")
                
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

                # 成员名不在字段表里（`self.x = ...` 在 `__init__` 里赋的隐式成员、方法名等）
                # 时给 object：返回 None 会让上层把「不知道」当成左操作数的类型用，
                # `group in self.group_memberships` 就被判成 str 而不是 bool（实测假阳性）。
                return result_type if result_type is not None else Type("object")
            
            # 检查类定义
            if vname in self.class_defs:
                # SYNTAX/11「泛型类」规则 4：与上面的 struct 分支同一份代入逻辑 ——
                # 先把所属类声明的类型参数登记成类型名，再用接收者的类型实参按声明顺序逐位代入，
                # 然后才解析成员。此前这里直接 `_get_type_from_node(方法的 return_type)`，
                # 于是 `b: Box<int>` 上的 `b.get()` 报成 `T`（手册范例被判红）。
                # 字段是 `.body` 里的 LetStmt，不是 `.fields`（R8 的读取形状教训，parser.py:329）。
                class_def = self.class_defs[vname]
                declared = list(getattr(class_def, 'generic_params', []) or [])
                old_type_map = self.type_map.copy()
                for param in declared:
                    # 裸名（`let b: Box = Box(1)`）按擦除处理：形式参数名不是类型，
                    # 不能当成成员/方法的返回类型外泄成诊断（规则 3 的后半句）。
                    self.type_map[param] = Type("object")
                for i, param in enumerate(declared):
                    if i < len(value_type.generic_params or []):
                        self.type_map[param] = value_type.generic_params[i]
                try:
                    for body_stmt in class_def.body:
                        if isinstance(body_stmt, LetStmt) and body_stmt.name == node.attr:
                            result_type = self._visit(body_stmt.type_annotation)
                            if result_type is not None:
                                return result_type
                        elif isinstance(body_stmt, FuncDef) and body_stmt.name == node.attr:
                            result_type = self._get_type_from_node(body_stmt.return_type)
                            if result_type is not None:
                                return result_type
                finally:
                    self.type_map = old_type_map
            
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
            if k in ('Pattern', 'SlicePattern'):
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

        # SYNTAX/33 §3.3 的方向表同样管**再赋值**：`m = f`（float → Meter）与
        # `let m: Meter = f` 必须是同一判定，否则名义性在第二个赋值上就漏了。
        # 两侧都不是 subtype 时 `_nominal_subtype_assignment` 返回 None，
        # 而 cypyc 今天对普通赋值本来就不做类型检查（见 SYNTAX/33 P-1.9 的诚实条款），
        # 所以这条对既有语料零影响。
        if value_type is not None:
            for nm in self._extract_bind_names(node.target):
                declared = self.type_map.get(nm)
                if isinstance(declared, Type):
                    self._nominal_subtype_assignment(node, declared, value_type,
                                                     node.value)

        return value_type

    @staticmethod
    def _is_unpack_target(target: Any) -> bool:
        """判断 for 循环目标是否为解包形态（多目标或模式解包）"""
        if isinstance(target, (list, tuple)):
            return len(target) > 1
        return getattr(target, 'kind', None) in (
            'ArrayPattern', 'TuplePattern', 'SlicePattern', 'Pattern', 'StarExpr')

    def _visit_ForStmt(self, node: Any) -> None:
        """处理 for 循环，注册循环变量（支持解构目标）"""
        iter_type = self._visit(node.iter) if node.iter else None
        elem_type = None
        if iter_type is not None and getattr(iter_type, 'generic_params', None):
            elem_type = iter_type.generic_params[0]
        # 解包目标（`for k, v in pairs`）：循环变量绑定的是元素内部的子项，
        # 需要再下钻一层；无法下钻时退化为 object，避免误报类型不匹配。
        if self._is_unpack_target(node.target):
            if elem_type is not None and getattr(elem_type, 'generic_params', None):
                elem_type = elem_type.generic_params[0]
            else:
                elem_type = None
        for nm in self._extract_bind_names(node.target):
            if elem_type is not None:
                self.type_map[nm] = elem_type
            elif iter_type is not None and getattr(iter_type, 'name', '') == 'int':
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
        """处理 comptime: 块，访问块内语句（含内部 def）

        `comptime:` **块形式**是文档写明未实现的形态（SYNTAX/19-comptime.md:42）：
        这里给一条带行列号、措辞含「未实现」的诊断（BUG-83 的缺陷是用户只拿到
        `'list' object has no attribute '__dict__'` 这种内部异常文本）。块内语句不再
        往下 visit —— 求值侧不会执行它们，继续 visit 只会在同一处叠出重复诊断。
        """
        # 局部导入：诊断文案与求值侧共用一处真源，也避开 analyzer 包内的成环风险
        from cypyc.analyzer.comptime_evaluator import comptime_block_not_implemented

        block = getattr(node, "body", None)
        if block is None:
            block = getattr(node, "expr", None)
        if isinstance(block, list):
            self.errors.append(str(comptime_block_not_implemented(block)))
            return
        if block is not None:
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

        # S-3.3：兄弟 subtype 之间**永不**可直转。单位/权限/索引这类声明存在的全部意义
        # 就是防止兄弟混用，允许 `m as Kilometer` 就等于没做名义化。
        # 两步 `m as float as Kilometer` 仍然放行：那一句显式承认了「我在跨基类型」。
        if (value_type and value_type.name in self.subtype_defs
                and target_type.name in self.subtype_defs
                and value_type.name != target_type.name
                and not self._is_subtype(target_type, value_type)
                and not self._is_subtype(value_type, target_type)):
            self.errors.append(
                f"cannot cast '{value_type.name}' to '{target_type.name}': nominal subtypes "
                f"of the same base are not mutually comparable (SYNTAX/33 S-3.3); cast "
                f"through the base "
                f"'{self._common_subtype_base(value_type.name, target_type.name)}' in two "
                f"steps if that is really what you mean at {node.line}:{node.col}")
            return None

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
        # S-5.3 / S-2.1：subtype 的结构与基类型**完全同构**（S-4.1 就是「零表示变化」），
        # 所以 `duck Numeric` 对 `Cents <: int` 必须判定为满足 —— 沿链下降到第一个非
        # subtype 的名字，再走原有的结构性检查。不这么做就等于让 §3.2.1 的同构承诺在
        # duck 这一侧失守。
        if inferred_type.name in self.subtype_defs:
            runtime = self._subtype_runtime_name(inferred_type.name)
            if runtime and runtime != inferred_type.name:
                return self._type_satisfies_duck(
                    Type(runtime, is_pointer=inferred_type.is_pointer,
                         is_ref=inferred_type.is_ref,
                         generic_params=inferred_type.generic_params), duck_name)
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
            # `T: list<int>` 这类「带实参的类型名界」既不是 duck 也不是 typeclass：
            # 走 C-2.2 的满足关系（2.2.1 / 裁决 D-2：只比头部名，元素类型不检查）。
            # 不这么做就会得到实测基线 B6 —— `T: list<int>` 对 `list[int]` 实参硬报错。
            if (typeclass_name in self.constraint_defs
                    or (typeclass_name not in self.type_classes
                        and typeclass_name not in self.trait_defs)):
                self._check_bound_satisfaction(param_name, inferred_type, constraint_ast,
                                               [typeclass_name], node, line, col)
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
            # 基本类型约束 / 命名约束 / duck 约束检查
            self._check_bound_satisfaction(param_name, inferred_type, constraint_ast,
                                           constraint_names, node, line, col)

    def _check_bound_satisfaction(self, param_name: str, inferred_type: Type,
                                  constraint_ast: Any, constraint_names: List[str],
                                  node: Any, line: int, col: int) -> None:
        """C-2.2 的满足关系：``A satisfies N  ⟺  ∃ m ∈ members(N) : _is_subtype(A, m)``。

        这里替掉了原来那行 `if inferred_type.name in constraint_names`（裸字符串比较），
        它是实测基线 B4（bool 不满足 int 界）/ B5（子类不满足父类界）/
        B6（list[int] 不满足 list<int> 界）的共同根因：绕开了 `_is_subtype`
        就等于在编译器里养了第二套可赋值性判据（INV-2 禁止的就是这个）。
        命名约束与内联联合在这里走同一段代码，因此 C-4.1 的「同义」是结构性保证，
        不是两份并行的实现。
        """
        # C-6 / 裁决 D-3：`T: (A, B)` 今天会被 parser 静默吃成 Constant（B8），
        # analyzer 侧再钉一次，绝不退回「把垃圾节点字符串化后放行」。
        if getattr(constraint_ast, 'kind', None) == 'Constant':
            found = self._constraint_member_text(constraint_ast)
            self.errors.append(
                f"multiple generic bounds are not supported: got '{found}'. Use one "
                f"constraint name, or an inline union 'T: int | float', or a 'duck' "
                f"constraint for structural requirements (see SYNTAX/27-constraints.md) "
                f"at {line}:{col}")
            return

        # 成员展开（C-2.3 传递 + C-2.4 环检测）
        member_names: List[str] = []
        for cn in constraint_names:
            if cn in self.constraint_defs:
                expanded, cycle = self._expand_constraint_members(cn)
                if cycle:
                    rendered = ' -> '.join(cycle)
                    if rendered not in self._circular_constraint_reported:
                        self._circular_constraint_reported.add(rendered)
                        self.errors.append(
                            f"circular constraint definition: {rendered} at {line}:{col}")
                    return
                candidates = expanded
            else:
                candidates = [cn]
            for m in candidates:
                if m and m not in member_names:
                    member_names.append(m)

        # C-4.1：命名界与内联界只差「名字那一栏」——命名时用约束名，内联时保留
        # 摊开的联合（今天 B3 的文案就是这个形状，不退化）。
        if len(constraint_names) == 1 and constraint_names[0] in self.constraint_defs:
            display_name = constraint_names[0]
        else:
            display_name = ' | '.join(cn for cn in constraint_names if cn)

        # duck 成员：结构性判定（SYNTAX/33 §2.2 表 + 与 27-constraints.md 的分工）
        for cn in constraint_names:
            if cn in self.duck_constraints and self._type_satisfies_duck(inferred_type, cn):
                return

        for member_name in member_names:
            if self._bound_member_satisfied(inferred_type, member_name):
                return

        self._report_bound_violation(param_name, inferred_type, display_name,
                                     member_names, node, line, col)

    def _bound_member_satisfied(self, inferred_type: Type, member_name: str) -> bool:
        """单个成员的满足判定（必须走 `_is_subtype` 这个唯一入口，INV-2）。

        泛型成员按**头部名**比较（`list[int]` 满足成员 `list`，也满足 `list<int>`），
        这是 §2.2.1 / 裁决 D-2 明写的宽松，不是隐藏缺陷：codegen 今天把
        `generic_params` 整体丢弃（降级成 `ctypedef object`），元素级检查会得到
        「编译期拒绝、产物里根本没有这个信息」的空转判据。

        头部名先经过 `Type(inferred_type.name)` 归一：容器实参在检查器里的类型是
        `list[int]`，而界只关心 `list` 这个头（同上）。
        """
        if not member_name:
            return False
        if member_name in self.duck_constraints and self._type_satisfies_duck(
                inferred_type, member_name):
            return True
        actual = self._bare_container_type(inferred_type)
        declared = self._bare_container_type(Type(member_name))
        if self._is_subtype(actual, declared):
            return True
        # 容器实参（list[int] / list / List[int]）：只比头部名，元素类型 deferred
        if (actual.generic_params and declared.generic_params
                and actual.name == declared.name):
            return True
        if (actual.generic_params and not declared.generic_params
                and actual.name == declared.name):
            return True
        return False

    #: 归一为小写的「容器头部名」——`list[int]` 的检查器类型头就是 `list`
    def _bare_container_type(self, ty: Type) -> Type:
        return Type(ty.name, is_pointer=ty.is_pointer, is_ref=ty.is_ref)

    def _report_bound_violation(self, param_name: str, inferred_type: Type,
                                display_name: str, member_names: List[str],
                                node: Any, line: int, col: int) -> None:
        """SYNTAX/33 C-5 的唯一诊断模板。

        * C-5.1 位置必须是调用点的真实 line/col（`at 0:0` 让 IDE 与增量编译都无法定位）
        * C-5.2 必须摊开成员（`(allowed: int | float)`），否则命名约束相对别名没有增益
        * C-5.3 `{actual}` 是推断后的类型名，不是 object
        * C-5.4 保留 `does not satisfy constraint '<name>'` 子串（日志/热重载告警可 grep）
        * C-5.5 同一调用点只报第一条
        """
        if node is not None:
            marker = id(node)
            if marker in self._bound_violation_reported_nodes:
                return
            self._bound_violation_reported_nodes.add(marker)
        allowed = ' | '.join(member_names) if member_names else '(no members)'
        message = (
            f"Generic constraint violation: type '{inferred_type.name}' does not satisfy "
            f"constraint '{display_name}' (allowed: {allowed}) for parameter '{param_name}'"
        )
        callee = getattr(getattr(node, 'func', None), 'id', None)
        decl = self.func_defs.get(callee) if callee else None
        if decl is not None:
            message += (f", in call to '{callee}' declared at line {decl.line}, "
                        f"col {decl.col}")
        else:
            message += f", in call to '{callee or '<unknown>'}'"
        message += f", reported at line {line}, col {col}"
        self.errors.append(message)

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
            # C-2.1：约束**不是类型**，出现在任何值类型位置都是编译期错误。
            # 必须排在 type_alias_defs 之前且分开两张表：把约束塞进别名表会得到
            # 「int 不满足 Numeric」那种假报错（实测基线 B2）。
            if node.id in self.constraint_defs:
                self._report_constraint_in_value_position(
                    node.id, getattr(node, 'line', 0), getattr(node, 'col', 0))
                return Type(node.id)
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

            # SYNTAX/11「泛型类」规则 3：注解位的类型实参个数由声明侧参数表决定。
            # 同一节点可能被多处访问，文案自带行列 ⇒ 按整条消息去重，不叠第二条同事实的账。
            decl = self.class_defs.get(node.name) or self.struct_defs.get(node.name)
            if decl is not None:
                diag = self._generic_arity_diagnostic(
                    node.name, list(getattr(decl, "generic_params", []) or []),
                    len(generic_params), getattr(node, "line", 0), getattr(node, "col", 0))
                if diag and diag not in self.errors:
                    self.errors.append(diag)
                # SYNTAX/11「类型约束」：注解位写的类型实参也要过声明界（`let x: Num<str>` 违界要红）
                self._check_declared_bounds(
                    decl, dict(zip(list(getattr(decl, "generic_params", []) or []), generic_params)),
                    node)

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

    # ---------------------------------------------------------------- 容器元素位
    # SYNTAX/02「容器元素位判定」（R13 补，BUG-137）：`_visit_LetStmt` 与 `_visit_ReturnStmt`
    # 各有一条「容器同名即放行」的分支，它们自己的注释只点名三种该放行的形态
    # （空容器构造器 / 嵌套无参 / 含 None-object 参数），却把「元素类型确实不同」也一起吞了。
    # 下面三个助手把这条收窄到注释点名的范围，判定与记帐分开：
    #   * `_slot_incompatible`  —— 单个元素位的纯判定（保守集见规则 5）
    #   * `_first_bad_element`  —— 容器逐位扫描，返回第一处不兼容位
    #   * `_check_container_elements` —— 唯一记帐出口（按整条消息去重，同事实不叠第二笔）

    #: 元素位参与判定的容器名。`dict` 自 R14 起进入本集合（SYNTAX/02「字典字面量的键值位判定」）：
    #: 键位是第 1 位、值位是第 2 位，用的还是下面同一把尺；此前排除它的理由（字面量不推断类型）已补上。
    _ELEMENT_CHECKED_CONTAINERS = ('list', 'set', 'tuple', 'Array', 'dict')

    #: 保守集（规则 5）：只有两侧元素名都落进这张闭合标量表，才允许报「名字不同即不兼容」
    _SCALAR_ELEMENT_NAMES = ('bool', 'int', 'long', 'float', 'double', 'char', 'str', 'bytes')

    #: 数值加宽阶梯（规则 3），与标量位同一条单向顺序
    _NUMERIC_WIDENING = ('bool', 'int', 'float', 'double')

    def _slot_incompatible(self, want: Any, got: Any):
        """单个元素位是否**确定**不兼容：是则返回 ``(want, got)``，否则 ``None``。

        一律保守：拿不准（联合位、非闭合标量、值侧缺元素信息）都放行 —— 误报会打断既有锁，
        漏报则记在 BUG-137 的「未覆盖」栏里。
        """
        if want is None or got is None:
            return None
        if want.name in ('object', 'Any', 'type') or got.name in ('object', 'Any'):
            return None
        if want.name in self._ELEMENT_CHECKED_CONTAINERS and want.name == got.name:
            # 嵌套容器（规则 2 末句）：递归下沉一层，元素位对齐后才谈类型
            found = self._first_bad_element(want, got)
            return None if found is None else (found[1], found[2])
        if want.union_members or got.union_members:
            return None          # 联合位交回原有的 union 分支，不在这里二次判定
        if want.name == got.name:
            return None
        if want.name in self._NUMERIC_WIDENING and got.name in self._NUMERIC_WIDENING:
            if self._NUMERIC_WIDENING.index(got.name) <= self._NUMERIC_WIDENING.index(want.name):
                return None      # 单向加宽
            return (want, got)
        if want.name in self._SCALAR_ELEMENT_NAMES and got.name in self._SCALAR_ELEMENT_NAMES:
            return (want, got)
        return None

    def _first_bad_element(self, want: Type, got: Type):
        """同名容器逐位扫描，返回 ``(序号, 期望元素, 实得元素)``；全放行则 ``None``。"""
        wp = list(want.generic_params or [])
        gp = list(got.generic_params or [])
        if not wp or not gp:
            return None          # 规则 4：值侧没有元素信息 ⇒ 占位形态
        for i in range(min(len(wp), len(gp))):
            bad = self._slot_incompatible(wp[i], gp[i])
            if bad:
                return (i + 1, bad[0], bad[1])
        return None

    @staticmethod
    def _sentence(text: str) -> str:
        """诊断句首字母大写：`where` 传 'Return ' 时要读作 'Return element 2 …'。"""
        return text[:1].upper() + text[1:]

    def _check_container_elements(self, want: Type, got: Type, node: Any,
                                  where: str = '') -> bool:
        """同名容器赋值/返回位的元素判定（SYNTAX/02「容器元素位判定」），返回是否记了账。

        调用点仍按原样登记声明类型 ⇒ 一条错只报一次，不制造级联误报。
        """
        if want is None or got is None:
            return False
        if want.name not in self._ELEMENT_CHECKED_CONTAINERS or want.name != got.name:
            return False
        wp = list(want.generic_params or [])
        gp = list(got.generic_params or [])
        if not wp or not gp:
            return False
        if want.name == 'tuple' and len(wp) != len(gp):
            # 定长容器的个数不符是**事实**，与元素名是否可判无关
            kind = self._sentence(f"{where}tuple element count mismatch")
            diag = (f"{kind}: expected {len(wp)}, got {len(gp)} "
                    f"at {node.line}:{node.col}")
        else:
            found = self._first_bad_element(want, got)
            if found is None:
                return False
            idx, we, ge = found
            slot = f"element {idx}"
            if want.name == 'dict' and idx in (1, 2):
                slot = "dict key" if idx == 1 else "dict value"
            kind = self._sentence(f"{where}{slot} type mismatch")
            diag = (f"{kind}: expected {self._type_display(we)}, "
                    f"got {self._type_display(ge)} at {node.line}:{node.col}")
        if diag in self.errors:
            return True
        self.errors.append(diag)
        return True

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
    
    def _substitute_type(self, type_node: Any, param_map: Dict[str, Type],
                         _alias_stack: tuple = ()) -> Optional[Type]:
        """递归替换类型节点中的泛型参数

        Args:
            type_node: 类型节点
            param_map: 泛型参数映射 {param_name: concrete_type}
            _alias_stack: 正在展开的别名名链（`type Loop<T> = Loop<T>` 这类自指靠它止损）

        Returns:
            替换后的具体类型

        R13 补两条（BUG-138 / BUG-139）：右端里出现的**其它别名**要展开到底 ——
        只代入一层会得到 `Pair[Pair[int]]` 这种「看着是类型、其实没解开」的形状，
        正确的 `Triple<int>` 字面量因此被拒；`UnionType` 过去整条分支都不认，
        `type Maybe<T> = T | None` 代入后返回 ``None`` ⇒ 声明类型为空 ⇒ 任意值放行。
        """
        if isinstance(type_node, Name):
            # 如果是泛型参数，替换为具体类型
            if type_node.id in param_map:
                return param_map[type_node.id]
            expanded = self._expand_nested_alias(type_node.id, [], _alias_stack)
            if expanded is not None:
                return expanded
            return Type(type_node.id)

        if isinstance(type_node, PointerType):
            base_type = self._substitute_type(type_node.base_type, param_map, _alias_stack)
            if base_type:
                return Type(base_type.name, is_pointer=True)
            return None

        if hasattr(type_node, 'kind') and type_node.kind == 'UnionType':
            # 与 `_get_type_from_node` 的联合分支同形：名字仍是 object，成员交给 `_type_in_union`
            members = []
            for member in (getattr(type_node, 'types', None) or []):
                substituted = self._substitute_type(member, param_map, _alias_stack)
                if substituted:
                    members.append(substituted)
            return Type("object", union_members=members) if members else None

        if hasattr(type_node, 'kind') and type_node.kind == 'GenericType':
            # 递归替换泛型类型的参数
            substituted_params = []
            for arg in type_node.args:
                substituted_arg = self._substitute_type(arg, param_map, _alias_stack)
                if substituted_arg:
                    substituted_params.append(substituted_arg)
            expanded = self._expand_nested_alias(
                type_node.name, substituted_params, _alias_stack)
            if expanded is not None:
                return expanded
            return Type(type_node.name, generic_params=substituted_params)

        # 对于其他类型，返回原始名称
        if hasattr(type_node, 'id'):
            return Type(type_node.id)

        return None

    def _expand_nested_alias(self, name: str, args: List[Type],
                             _alias_stack: tuple) -> Optional[Type]:
        """把别名右端里出现的**另一个别名**展开成它自己的具体类型。

        返回 ``None`` 表示「不是别名 / 展不开」，调用方按原样保留 ``Name<实参…>``：
        实参个数不符要交回 `_substitute_generic_alias` 既有的 arity 诊断，
        名字已在展开栈上则是自指别名 —— 停在这里，不递归成 RecursionError。
        """
        alias_def = self.type_alias_defs.get(name)
        if alias_def is None or name in _alias_stack:
            return None
        declared = list(getattr(alias_def, 'generic_params', []) or [])
        if len(declared) != len(args):
            return None
        mapping = dict(zip(declared, args))
        return self._substitute_type(alias_def.target, mapping, _alias_stack + (name,))

    def _pattern_slot_types(self, type_name: Any) -> list:
        """位置模式各槽位的类型：提取器返回元组优先，其次字段声明顺序。

        SYNTAX/17-pattern-matching.md 的提取器优先级（__match_args__ < __unapply__ <
        __unapply_seq__ < __unwarp__）决定了「`case Email(user, domain)` 里 user 是什么类型」，
        旧实现根本不看这里，绑定名会落到未定义名的默认类型上，把有效程序判成
        「Return type mismatch: expected str, got int」（memory/bugs.md BUG-37）。
        解不出来时返回空表，由调用方按 object 放行——宁可不判，也不造假阳性。
        """
        if not isinstance(type_name, str):
            return []
        decl = self.struct_defs.get(type_name) or self.class_defs.get(type_name)
        if decl is None:
            return []
        members = list(getattr(decl, 'methods', None) or []) + list(getattr(decl, 'body', None) or [])
        for m in members:
            if getattr(m, 'name', None) not in ('__unapply__', '__unapply_seq__', '__unwarp__',
                                                '__match_args__'):
                continue
            ret = getattr(m, 'return_type', None)
            if ret is None:
                continue
            candidates = getattr(ret, 'types', None) or [ret]
            for cand in candidates:
                # GenericType 把实参存在 `.args`（parser.py:820-824），
                # 类型注解节点用 `.id`（Name）或 `.name`（GenericType）。
                params = getattr(cand, 'args', None) or getattr(cand, 'generic_params', None) or []
                if params:
                    slots_out = []
                    for p in params:
                        pname = getattr(p, 'id', None) or getattr(p, 'name', None)
                        slots_out.append(Type(pname) if pname else Type("object"))
                    return slots_out
        slots = []
        for f in self._positional_fields(decl):
            ann = getattr(f, 'type_annotation', None)
            name = getattr(ann, 'id', None) or getattr(ann, 'name', None)
            slots.append(Type(name) if name else Type("object"))
        return slots

    NON_FIELD_KINDS = ("FuncDef", "ClassDef", "StructDef", "TraitDef", "ImplBlock",
                       "ComptimeStmt", "EnumDef")

    def _positional_fields(self, decl: Any) -> list:
        """位置槽位对应的字段节点，struct 与 class 同规则（SYNTAX/17 规则 2、6）。

        StructDef 把成员放在 `.fields`/`.methods`，ClassDef 只有一个 `.body`
        （parser.py 里 ClassDef 的实例属性是 name/bases/body/is_cdef）——
        只看 `.fields` 会让 class 的槽位数恒空，`case C(x, y)` 的元数检查被静默跳过。
        `__`-包围的类属性（`__match_args__`）是模式元数据、不是数据字段，两侧共用
        `ASTUtils.is_positional_member` 判据，避免各写一遍再漂移。
        """
        def keep(member: Any) -> bool:
            return ASTUtils.is_positional_member(getattr(member, 'name', None))

        fields = [f for f in (getattr(decl, 'fields', None) or []) if keep(f)]
        if fields:
            return fields
        out = []
        for member in (getattr(decl, 'body', None) or []):
            if getattr(member, 'kind', None) in self.NON_FIELD_KINDS:
                continue
            if getattr(member, 'name', None) is None and getattr(member, 'target', None) is None:
                continue
            if not keep(member):
                continue
            out.append(member)
        return out

    def _bind_pattern_names(self, pattern: Any, subject_type: Any) -> None:
        """从匹配模式中收集绑定变量名并注册到当前作用域（用于 case 体内引用）。"""
        if pattern is None:
            return
        kind = getattr(pattern, 'kind', None)
        if kind == 'Name':
            if pattern.id != '_':
                self.type_map[pattern.id] = subject_type or Type("object")
        elif kind == 'Pattern':
            if getattr(pattern, 'name', None) not in (None, '_'):
                self.type_map[pattern.name] = subject_type or Type("object")
        elif kind == 'ExtractorPattern':
            slots = self._pattern_slot_types(getattr(pattern, 'type_name', None))
            for i, arg in enumerate(getattr(pattern, 'args', []) or []):
                slot_type = slots[i] if i < len(slots) else (subject_type or Type("object"))
                if hasattr(arg, 'kind'):
                    self._bind_pattern_names(arg, slot_type)
        elif kind == 'StructPattern':
            for arg in getattr(pattern, 'args', []) or []:
                if hasattr(arg, 'kind'):
                    self._bind_pattern_names(arg, subject_type)
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
        """处理模式绑定（match case 中的变量绑定）

        绑定名的类型由 `_bind_pattern_names` 按「提取器返回元组 / 字段声明顺序」登记；
        旧实现在这里无条件写 `Type("int")`（注释自称"暂定"），把已解析出的槽位类型覆盖掉，
        于是 `case Email(user, domain): return user` 被判
        「Return type mismatch: expected str, got int」而拒绝编译（memory/bugs.md BUG-37）。
        名称未被登记过时按 object 放行：宁可不判，也不造假阳性。
        """
        if getattr(node, 'name', None) and node.name not in self.type_map:
            self.type_map[node.name] = Type("object")

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
        # S-4.3 的最后一条：`match` 的类型模式与 `isinstance` 同源 —— 它编译成对
        # 运行时类型对象的判断，而 subtype 故意没有那个对象（S-4.1），所以同一条拒绝。
        if node.type_name in self.subtype_defs:
            self._report_subtype_has_no_runtime_identity(
                node.type_name, f"the type pattern 'case {node.type_name} ...'",
                node.line, node.col)
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
        
        # 元数校验（SYNTAX/17「位置模式的元数与槽位规则」R7 补条款 / BUG-92 的拒绝面）：
        # 槽位数取自提取器优先级或字段声明数；类型在本模块不可见时不报（交运行期解包路径）。
        slots = self._pattern_slot_types(node.type_name)
        if slots and len(node.args) > len(slots):
            self.errors.append(
                f"Positional pattern '{node.type_name}' has {len(node.args)} slot(s) but type "
                f"'{node.type_name}' unpacks only {len(slots)} at {node.line}:{node.col}")

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
        """下标返回容器内元素类型；**切片返回被切容器自身的类型**（SYNTAX/14 切片语法节）。

        解析器把切片形态落成普通 dict（`{'slice': True, 'start':…, 'end':…, 'step':…}`）而不是 ASTNode，
        所以形态判断必须在「取元素类型」之前，否则 `xs[1:3]` 会被判成 `list<int>` 的元素类型 `int`。
        """
        base_type = self._visit(node.value)
        # 访问下标表达式（slice 可能是 dict 等，仅对 AST 节点递归访问）
        if hasattr(node.slice, 'kind'):
            self._visit(node.slice)
        if base_type is None:
            return Type("object")

        if self._is_slice_form(node.slice):
            return base_type

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
    def _is_slice_form(slice_node: Any) -> bool:
        """切片形态就是解析器落的那个 dict（`cypyc/parser/parser.py:3952-3991` 的 `{"slice": True, …}`）；
        语言里没有独立的 `Slice` AST 节点，所以形态判断只有这一支。"""
        return isinstance(slice_node, dict) and slice_node.get("slice") is True

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
