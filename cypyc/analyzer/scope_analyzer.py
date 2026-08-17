from typing import Dict, List, Set, Any
from cypyc.parser.parser import ASTNode, Module, FuncDef, ClassDef, StructDef, LetStmt, Name, ExceptionDef, GoStmt, SpawnStmt, ArrayPattern, SlicePattern, StructPattern, TypePattern, DictPattern, AsPattern, ExtractorPattern, RangePattern, DuckDef


class Symbol:
    def __init__(self, name: str, kind: str, node: ASTNode, scope: "Scope"):
        self.name = name
        self.kind = kind
        self.node = node
        self.scope = scope


class Scope:
    def __init__(self, parent: "Scope" = None, kind: str = "global"):
        self.parent = parent
        self.kind = kind
        self.symbols: Dict[str, Symbol] = {}
        self.children: List["Scope"] = []

    def add_symbol(self, name: str, kind: str, node: ASTNode) -> Symbol:
        symbol = Symbol(name, kind, node, self)
        self.symbols[name] = symbol
        return symbol

    def lookup(self, name: str) -> Symbol:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def create_child(self, kind: str) -> "Scope":
        child = Scope(self, kind)
        self.children.append(child)
        return child


class ScopeAnalyzer:
    def __init__(self):
        self.root_scope = Scope(kind="module")
        self.current_scope = self.root_scope
        self.errors: List[str] = []
        # 注册内置类型和函数
        self._register_builtins()
        # 是否在 meta block 中（meta block 中允许前向引用）
        self.in_meta_block = False
        # 作为类型注解使用时视为已定义的内建/泛型类型名
        self._known_type_names = {
            'Callable', 'callable', 'Tuple', 'Optional', 'Union', 'List',
            'Dict', 'Set', 'Generator', 'Iterable', 'Iterator', 'Sequence',
        }
        # 用户定义种类（用于重复定义检测）
        self._user_def_kinds = {'function', 'class', 'struct', 'trait',
                                'typeclass', 'enum'}
        self._builtin_names: set = set()
    
    def _register_builtins(self):
        """注册内置类型和函数到根作用域"""
        builtins = [
            ('int', 'type'),
            ('float', 'type'),
            ('double', 'type'),
            ('bool', 'type'),
            ('str', 'type'),
            ('None', 'type'),
            ('Exception', 'type'),
            ('list', 'type'),
            ('dict', 'type'),
            ('set', 'type'),
            ('tuple', 'type'),
            ('Callable', 'type'),
            ('callable', 'type'),
            ('object', 'type'),
            ('Any', 'type'),
            ('Nothing', 'type'),
            ('Null', 'type'),
            # 常见内置异常类型
            ('ValueError', 'type'),
            ('TypeError', 'type'),
            ('RuntimeError', 'type'),
            ('IndexError', 'type'),
            ('KeyError', 'type'),
            ('AttributeError', 'type'),
            ('IOError', 'type'),
            ('OSError', 'type'),
            ('FileNotFoundError', 'type'),
            ('PermissionError', 'type'),
            ('OverflowError', 'type'),
            ('ZeroDivisionError', 'type'),
            ('KeyboardInterrupt', 'type'),
            ('StopIteration', 'type'),
            ('AssertionError', 'type'),
            ('NotImplementedError', 'type'),
            # 内置函数
            ('print', 'function'),
            ('len', 'function'),
            ('malloc', 'function'),
            ('free', 'function'),
            ('sizeof', 'function'),
            ('addr', 'function'),
            ('ord', 'function'),
            ('range', 'function'),
            ('type', 'function'),
            ('sorted', 'function'),
            ('isinstance', 'function'),
            ('getattr', 'function'),
            ('hash', 'function'),
            ('super', 'function'),
            ('abs', 'function'),
            ('min', 'function'),
            ('max', 'function'),
            ('sum', 'function'),
            ('any', 'function'),
            ('all', 'function'),
            ('enumerate', 'function'),
            ('zip', 'function'),
            ('map', 'function'),
            ('filter', 'function'),
            ('reversed', 'function'),
            ('True', 'constant'),
            ('False', 'constant'),
            ('null', 'constant'),
            ('_', 'wildcard'),
            ('__name__', 'variable'),
            ('__main__', 'constant'),
        ]
        for name, kind in builtins:
            self.root_scope.add_symbol(name, kind, None)
        self._builtin_names = {name for name, _ in builtins}

    def _check_redefinition(self, name: str, node: ASTNode) -> bool:
        """检测同名用户定义重复声明（跳过内置名）。"""
        if not name or name in self._builtin_names:
            return False
        existing = self.current_scope.symbols.get(name)
        if existing is not None and existing.kind in self._user_def_kinds:
            self.errors.append(
                f"Name '{name}' is already declared in this scope "
                f"(line {node.line}, col {node.col})")
            return True
        return False

    def analyze(self, node: ASTNode) -> Scope:
        self._visit(node)
        return self.root_scope

    def _visit(self, node: ASTNode) -> None:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            getattr(self, method)(node)
        else:
            self._visit_children(node)

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

    def _visit_Module(self, node: Module) -> None:
        for stmt in node.body:
            self._visit(stmt)

    def _visit_FuncDef(self, node: FuncDef) -> None:
        # 检测 property 装饰器（@property / @x.setter / @x.deleter）：
        # 同名 getter/setter 是合理定义，不应报重复声明
        is_property = False
        if hasattr(node, 'decorators') and node.decorators:
            for decorator in node.decorators:
                dname = self._decorator_name(decorator)
                if dname in ('property', 'setter', 'deleter'):
                    is_property = True
                    break

        if node.name and not is_property:
            self._check_redefinition(node.name, node)
        # 检查是否有 @python 装饰器
        has_python_decorator = False
        if hasattr(node, 'decorators') and node.decorators:
            for decorator in node.decorators:
                decorator_name = getattr(decorator.name, 'id', str(decorator.name))
                if decorator_name == 'python':
                    has_python_decorator = True
                    break
        
        # 如果是 @python 装饰的函数，只注册函数名，跳过函数体分析
        if has_python_decorator:
            self.current_scope.add_symbol(node.name, "function", node)
            return
        
        self.current_scope.add_symbol(node.name, "function", node)
        func_scope = self.current_scope.create_child("function")
        self.current_scope = func_scope

        # 注册泛型参数作为类型别名
        for param in getattr(node, 'generic_params', []):
            func_scope.add_symbol(param, "type", node)

        # 在注册泛型参数之后访问返回类型（可能引用泛型参数）
        if hasattr(node, 'return_type') and node.return_type:
            self._visit(node.return_type)

        # 检查是否是类方法（当前作用域是 class）
        is_class_method = self.current_scope.parent and self.current_scope.parent.kind == "class"
        
        # 类方法自动注册 self 参数（如果方法还没有第一个参数是 self）
        has_self_param = node.params and node.params[0].name == 'self'
        if is_class_method and not has_self_param:
            from cypyc.parser.parser import Param
            self_param = Param('self', None, line=0, col=0)
            func_scope.add_symbol('self', "parameter", self_param)

        for param in node.params:
            func_scope.add_symbol(param.name, "parameter", param)
            # 访问参数的类型注解
            if hasattr(param, 'type_annotation') and param.type_annotation:
                self._visit(param.type_annotation)

        for stmt in node.body:
            self._visit(stmt)

        self.current_scope = func_scope.parent

    @staticmethod
    def _decorator_name(decorator: Any) -> str:
        """从装饰器节点提取名称：@property -> 'property'；@x.setter -> 'setter'"""
        name = getattr(decorator, 'name', None)
        if name is None:
            return ''
        if hasattr(name, 'id'):
            return name.id
        if hasattr(name, 'attr'):
            return name.attr
        if hasattr(name, 'name'):
            return name.name
        return str(name)

    def _visit_ClassDef(self, node: ClassDef) -> None:
        self._check_redefinition(node.name, node)
        self.current_scope.add_symbol(node.name, "class", node)
        class_scope = self.current_scope.create_child("class")
        self.current_scope = class_scope

        for stmt in node.body:
            self._visit(stmt)

        self.current_scope = class_scope.parent

    def _visit_StructDef(self, node: StructDef) -> None:
        # 检查结构体是否在模块顶级定义
        if self.current_scope.kind != "module":
            self.errors.append(f"Struct '{node.name}' can only be defined at module level (line {node.line}, col {node.col})")
            return
        
        self._check_redefinition(node.name, node)
        self.current_scope.add_symbol(node.name, "struct", node)
        struct_scope = self.current_scope.create_child("struct")
        self.current_scope = struct_scope

        # 注册泛型参数作为类型别名
        for param in node.generic_params:
            struct_scope.add_symbol(param, "type", node)

        for field in node.fields:
            struct_scope.add_symbol(field.name, "field", field)
            # 显式访问字段的类型注解（在结构体作用域内）
            if hasattr(field, 'type_annotation') and field.type_annotation:
                self._visit(field.type_annotation)

        self.current_scope = struct_scope.parent

    def _visit_EnumDef(self, node: Any) -> None:
        """处理枚举定义"""
        # 检查枚举是否在模块顶级定义
        if self.current_scope.kind != "module":
            self.errors.append(f"Enum '{node.name}' can only be defined at module level (line {node.line}, col {node.col})")
            return
        
        self._check_redefinition(node.name, node)
        self.current_scope.add_symbol(node.name, "enum", node)

    def _visit_TraitDef(self, node: Any) -> None:
        """处理 trait 定义，确保只能在模块顶级定义"""
        if self.current_scope.kind != "module":
            self.errors.append(f"Trait '{node.name}' can only be defined at module level (line {node.line}, col {node.col})")
            return
        
        self._check_redefinition(node.name, node)
        self.current_scope.add_symbol(node.name, "trait", node)

    def _visit_ImplStmt(self, node: Any) -> None:
        """处理 impl 实现，确保只能在模块顶级定义"""
        if self.current_scope.kind != "module":
            self.errors.append(f"impl for '{node.for_type}' can only be defined at module level (line {node.line}, col {node.col})")
            return

        # 将 for_type 中可能携带的泛型参数（如 Wrapper<T>）注册到模块作用域，
        # 以便 impl 块体内的方法可以引用这些类型参数。
        if getattr(node, 'for_type', None):
            for gp in self._generic_params_from_type(node.for_type):
                self.current_scope.add_symbol(gp, "type", node)

        # 访问 trait 名称和实现类型
        self._visit(node.for_type)
        # 在独立子作用域中检查实现方法，避免不同类型（如 Color 与 Wrapper）
        # 的同名方法在模块作用域中误报“重复声明”
        impl_scope = self.current_scope.create_child("impl")
        self.current_scope = impl_scope
        for m in getattr(node, 'methods', []) or []:
            self._visit(m)
        self.current_scope = impl_scope.parent

    def _generic_params_from_type(self, typ: Any) -> List[str]:
        """从类型表达式（字符串或 AST 节点）中提取泛型参数名，如 Wrapper<T> -> ['T']"""
        params: List[str] = []
        if typ is None:
            return params
        if isinstance(typ, str):
            # 形如 Wrapper<T> 或 Container<T, U>
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

    def _visit_TypeClassDef(self, node: Any) -> None:
        """处理 typeclass 定义，注册泛型参数并访问方法体"""
        self._check_redefinition(node.name, node)
        self.current_scope.add_symbol(node.name, "typeclass", node)
        tc_scope = self.current_scope.create_child("typeclass")
        self.current_scope = tc_scope
        for gp in getattr(node, 'generic_params', []) or []:
            gp_name = gp['name'] if isinstance(gp, dict) and 'name' in gp else gp
            if gp_name and gp_name != '_':
                tc_scope.add_symbol(gp_name, "type", node)
        for m in getattr(node, 'methods', []) or []:
            self._visit(m)
        self.current_scope = tc_scope.parent

    def _visit_TypeClassImpl(self, node: Any) -> None:
        """处理 impl typeclass X for Y，注册泛型参数并访问方法体"""
        # target_type 可能携带泛型，如 Wrapper<T>
        for gp in self._generic_params_from_type(getattr(node, 'target_type', None)):
            self.current_scope.add_symbol(gp, "type", node)
        # 实现块自身声明的泛型参数（如 impl typeclass Eq<U> for Wrapper<U>）
        for gp in getattr(node, 'generic_params', []) or []:
            gp_name = gp['name'] if isinstance(gp, dict) and 'name' in gp else gp
            if gp_name and gp_name != '_':
                self.current_scope.add_symbol(gp_name, "type", node)
        # 方法名限定在独立子作用域，避免不同实现类型（如 Color 与 Wrapper）
        # 的同名方法在模块作用域中误报“重复声明”
        impl_scope = self.current_scope.create_child("typeclass")
        self.current_scope = impl_scope
        for m in getattr(node, 'methods', []) or []:
            self._visit(m)
        self.current_scope = impl_scope.parent

    def _visit_LambdaExpr(self, node: Any) -> None:
        """处理 lambda 表达式，注册参数并访问函数体"""
        lambda_scope = self.current_scope.create_child("lambda")
        self.current_scope = lambda_scope
        for p in getattr(node, 'params', []) or []:
            pname = getattr(p, 'name', None) or (getattr(p, 'id', None) if hasattr(p, 'id') else None)
            if pname and pname != '_':
                lambda_scope.add_symbol(pname, "variable", node)
        if hasattr(node, 'body') and node.body is not None:
            self._visit(node.body)
        self.current_scope = lambda_scope.parent

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
                        self.current_scope.add_symbol(var_name, "variable", node)
            else:
                self._visit(item)
        for stmt in getattr(node, 'body', []) or []:
            self._visit(stmt)

    def _visit_ComptimeFuncDef(self, node: Any) -> None:
        """处理 comptime def，注册函数名与参数并访问函数体"""
        name = getattr(node, 'name', None)
        if name:
            self.current_scope.add_symbol(name, "function", node)
        fn_scope = self.current_scope.create_child("function")
        self.current_scope = fn_scope
        for p in getattr(node, 'params', []) or []:
            pname = getattr(p, 'name', None) or (getattr(p, 'id', None) if hasattr(p, 'id') else None)
            if pname and pname != '_':
                fn_scope.add_symbol(pname, "variable", node)
        ret = getattr(node, 'return_type', None)
        if ret is not None:
            self._visit(ret)
        body = getattr(node, 'body', None)
        if isinstance(body, list):
            for stmt in body:
                self._visit(stmt)
        elif body is not None:
            self._visit(body)
        self.current_scope = fn_scope.parent

    def _visit_MacroDef(self, node: Any) -> None:
        """处理 macro 定义，注册宏名（去掉可能的 ! 后缀）"""
        name = getattr(node, 'name', None)
        if name:
            base = name[:-1] if name.endswith('!') else name
            self.current_scope.add_symbol(base, "macro", node)

    def _visit_MacroCall(self, node: Any) -> None:
        """处理宏调用，仅访问参数，宏名作为字符串不查作用域"""
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

    def _visit_MetaBlock(self, node: Any) -> None:
        """处理 meta 块，确保只能在模块顶级定义"""
        if self.current_scope.kind != "module":
            self.errors.append(f"meta block can only be defined at module level (line {node.line}, col {node.col})")
            return
        
        # 设置在 meta block 中标志
        self.in_meta_block = True
        for stmt in node.body:
            self._visit(stmt)
        self.in_meta_block = False

    def _visit_DuckDef(self, node: DuckDef) -> None:
        """处理 duck 约束定义，注册到当前作用域"""
        self.current_scope.add_symbol(node.name, "duck", node)
        # duck 约束的类型参数和需求在类型检查阶段处理

    def _visit_ExceptionDef(self, node: ExceptionDef) -> None:
        """处理异常类型定义"""
        self.current_scope.add_symbol(node.name, "exception", node)
        # 创建异常作用域
        exc_scope = self.current_scope.create_child("exception")
        self.current_scope = exc_scope
        # 注册字段
        for field in node.fields:
            if hasattr(field, 'name'):
                exc_scope.add_symbol(field.name, "field", field)
                if hasattr(field, 'type_annotation') and field.type_annotation:
                    self._visit(field.type_annotation)
        self.current_scope = exc_scope.parent

    def _visit_SuiteDef(self, node: Any) -> None:
        """测试套件定义：建立独立作用域，隔离各 test 内的变量声明"""
        suite_scope = self.current_scope.create_child("suite")
        self.current_scope = suite_scope
        for stmt in node.body:
            self._visit(stmt)
        self.current_scope = suite_scope.parent

    def _visit_TestDef(self, node: Any) -> None:
        """测试用例定义：建立独立作用域，避免不同 test 间 let 变量冲突"""
        test_scope = self.current_scope.create_child("test")
        self.current_scope = test_scope
        for stmt in node.body:
            self._visit(stmt)
        self.current_scope = test_scope.parent

    def _visit_SetupStmt(self, node: Any) -> None:
        """套件初始化块"""
        for stmt in node.body:
            self._visit(stmt)

    def _visit_TeardownStmt(self, node: Any) -> None:
        """套件清理块"""
        for stmt in node.body:
            self._visit(stmt)

    def _visit_TypeAlias(self, node: Any) -> None:
        """处理类型别名定义"""
        self.current_scope.add_symbol(node.name, "type", node)
        # 注册泛型参数作为类型别名
        if hasattr(node, 'generic_params') and node.generic_params:
            for param in node.generic_params:
                self.current_scope.add_symbol(param, "type", node)

    def _extract_names(self, node: Any) -> List[str]:
        """从赋值/解构目标中提取所有被绑定的变量名"""
        names: List[str] = []
        if node is None:
            return names
        if isinstance(node, str):
            if node and node != '_':
                names.append(node)
            return names
        if isinstance(node, (list, tuple)):
            for e in node:
                names.extend(self._extract_names(e))
            return names
        if hasattr(node, 'kind'):
            k = node.kind
            if k == 'Name':
                if node.id != '_':
                    names.append(node.id)
                return names
            if k == 'Pattern':
                if getattr(node, 'name', None) and node.name != '_':
                    names.append(node.name)
                return names
            if k in ('TupleExpr', 'ListExpr'):
                els = getattr(node, 'elements', None) or getattr(node, 'elts', None) or []
                for el in els:
                    names.extend(self._extract_names(el))
                return names
            if k == 'Constant' and isinstance(node.value, (tuple, list)):
                for el in node.value:
                    names.extend(self._extract_names(el))
                return names
            if k in ('ArrayPattern', 'TuplePattern'):
                ps = getattr(node, 'patterns', None) or getattr(node, 'elements', None) or []
                for p in ps:
                    names.extend(self._extract_names(p))
                return names
            if k == 'StarExpr':
                inner = getattr(node, 'value', None) or getattr(node, 'expr', None)
                if inner is not None:
                    names.extend(self._extract_names(inner))
                return names
        if hasattr(node, 'id'):
            if node.id != '_':
                names.append(node.id)
            return names
        return names

    def _visit_LetStmt(self, node: LetStmt) -> None:
        # 采用函数/模块级作用域：允许同名变量重复声明（符合 Python 语义），
        # 不再对“已声明”报错，避免 suite/test/分支块中的 let 互相冲突。
        for nm in self._extract_names(node.name):
            if nm not in self.current_scope.symbols:
                self.current_scope.add_symbol(nm, "variable", node)
        if node.value:
            self._visit(node.value)

    def _visit_GoStmt(self, node: GoStmt) -> None:
        """处理 go 语句 - 轻量级协程"""
        if hasattr(node, 'body') and node.body:
            # 块形式：go: body...
            # 创建新作用域，因为块体是独立的执行上下文
            go_scope = self.current_scope.create_child("go")
            self.current_scope = go_scope
            for stmt in node.body:
                self._visit(stmt)
            self.current_scope = go_scope.parent
        elif hasattr(node, 'target') and node.target:
            # 调用形式：go func(args) 或表达式形式：go expr
            self._visit(node.target)
            for arg in getattr(node, 'args', []):
                self._visit(arg)

    def _visit_SpawnStmt(self, node: SpawnStmt) -> None:
        """处理 spawn 语句 - 重量级线程"""
        if hasattr(node, 'body') and node.body:
            # 块形式：spawn: body...
            spawn_scope = self.current_scope.create_child("spawn")
            self.current_scope = spawn_scope
            for stmt in node.body:
                self._visit(stmt)
            self.current_scope = spawn_scope.parent
        elif hasattr(node, 'target') and node.target:
            # 调用形式：spawn func(args) 或表达式形式：spawn expr
            self._visit(node.target)
            for arg in getattr(node, 'args', []):
                self._visit(arg)

    def _visit_Name(self, node: Name) -> None:
        # meta block 中允许前向引用，不检查名称是否定义
        if self.in_meta_block:
            return
        name = node.id
        # 宏调用形式：name!（如 double_value!）去掉 ! 后查宏定义
        if isinstance(name, str) and name.endswith('!'):
            base = name[:-1]
            if self.current_scope.lookup(base) or base in self._known_type_names:
                return
            name = base
        if self.current_scope.lookup(name):
            return
        # 已知类型名（内建类型、泛型容器、callable 等）作为注解使用时视为已定义
        if name in self._known_type_names:
            return
        self.errors.append(f"Undefined name '{node.id}' at {node.line}:{node.col}")

    def _visit_Assign(self, node: Any) -> None:
        # 先注册目标变量（支持单个变量及解构赋值，并支持自引用如 result = match...）
        for nm in self._extract_names(node.target):
            if nm in self.current_scope.symbols:
                continue
            # 若父作用域已存在该变量，视为对外部变量的重新赋值，不重复注册
            if self.current_scope.parent and self.current_scope.parent.lookup(nm):
                continue
            self.current_scope.add_symbol(nm, "variable", node)
        # 再访问 value
        if node.value:
            self._visit(node.value)

    def _visit_ForStmt(self, node: Any) -> None:
        """处理 for 循环，注册循环变量到作用域"""
        # 先访问迭代对象
        self._visit(node.iter)
        
        # 注册循环变量（支持单个变量及解构目标）
        for nm in self._extract_names(node.target):
            if nm not in self.current_scope.symbols:
                self.current_scope.add_symbol(nm, "variable", node)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_ListComp(self, node: Any) -> None:
        """处理列表推导式，注册循环变量到作用域"""
        # 处理每个生成器
        for gen in node.generators:
            if len(gen) >= 2:
                target, iter_expr = gen[0], gen[1]
                # 先访问迭代对象
                self._visit(iter_expr)
                
                # 注册循环变量 - target可能是字符串或元组
                if isinstance(target, str):
                    self.current_scope.add_symbol(target, "variable", node)
                elif isinstance(target, tuple):
                    # 元组解构，每个元素都是变量名
                    for name in target:
                        if isinstance(name, str):
                            self.current_scope.add_symbol(name, "variable", node)
                
                # 处理 if 条件列表
                if len(gen) > 2 and gen[2]:
                    for if_expr in gen[2]:
                        self._visit(if_expr)
        
        # 访问元素表达式
        self._visit(node.elt)

    def _visit_WhileStmt(self, node: Any) -> None:
        """处理 while 循环，访问条件和循环体"""
        # 先访问条件表达式
        self._visit(node.test)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_Call(self, node: Any) -> None:
        self._visit(node.func)
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                self._visit(arg[1])
            else:
                # 位置参数
                self._visit(arg)

    def _visit_MatchStmt(self, node: Any) -> None:
        """处理 match 语句"""
        self._visit(node.subject)
        for case in node.cases:
            # 访问 pattern（包含变量绑定）
            if hasattr(case, 'pattern') and case.pattern:
                pattern = case.pattern
                # 如果 pattern 是字典（case pattern if condition），获取真正的 pattern
                if isinstance(pattern, dict) and 'pattern' in pattern:
                    pattern = pattern['pattern']
                # 如果 pattern 是列表（元组模式）或 ArrayPattern（数组模式），递归访问每个元素
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
            if hasattr(case, 'condition') and case.condition:
                self._visit(case.condition)
            for stmt in case.body:
                self._visit(stmt)

    def _visit_GuardStmt(self, node: Any) -> None:
        """处理 guard 语句"""
        # GuardStmt 使用 test 字段而非 condition
        if hasattr(node, 'test') and node.test:
            self._visit(node.test)
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
        for stmt in node.body:
            self._visit(stmt)

    def _visit_Pattern(self, node: Any) -> None:
        """处理模式绑定（match case 中的变量绑定）"""
        self.current_scope.add_symbol(node.name, "variable", node)

    def _visit_SlicePattern(self, node: Any) -> None:
        """处理切片模式（.. 或 ..var）"""
        # 如果有变量名，创建变量绑定
        if node.name is not None:
            self.current_scope.add_symbol(node.name, "variable", node)

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
        # 将类型名称注册为已使用（用于检查类型是否定义）
        self._visit(Name(node.type_name, node.line, node.col))
        # 将绑定的变量注册到当前作用域
        self.current_scope.add_symbol(node.name, "variable", node)

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
        # 将绑定的变量注册到当前作用域
        self.current_scope.add_symbol(node.name, "variable", node)

    def _visit_DictPattern(self, node: DictPattern) -> None:
        """处理字典模式（case {"key": value, **rest}:）"""
        # 访问每个键值对的模式
        for key_pattern, value_pattern in node.pairs:
            self._visit(key_pattern)
            self._visit(value_pattern)
        # 如果有剩余绑定，注册到当前作用域
        if node.rest_name:
            self.current_scope.add_symbol(node.rest_name, "variable", node)

    def _visit_ExtractorPattern(self, node: ExtractorPattern) -> None:
        """处理提取器模式（参考Scala的unapply，如 Email(user, domain)）
        
        优先级：__match_args__ < __unapply__ < __unapply_seq__ < __unwarp__
        
        提取器模式中的变量需要注册到当前作用域。
        """
        # 将类型名称注册为已使用
        self._visit(Name(node.type_name, node.line, node.col))
        
        # 访问每个参数模式，注册变量绑定
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
        # 访问上下界表达式
        self._visit(node.lower)
        self._visit(node.upper)

    def _visit_Subscript(self, node: Any) -> None:
        """处理下标访问"""
        self._visit(node.value)
        if hasattr(node.slice, 'kind'):
            self._visit(node.slice)

    def _visit_FromImport(self, node: Any) -> None:
        """处理 from module import names 语句，注册导入的名称到当前作用域"""
        for name in getattr(node, 'names', []):
            self.current_scope.add_symbol(name, "function", None)
    
    def _visit_Import(self, node: Any) -> None:
        """处理 import module 语句，注册模块名称到当前作用域"""
        module_name = getattr(node, 'module', '')
        if module_name:
            self.current_scope.add_symbol(module_name, "module", None)
    
    def _visit_MetaBlock(self, node: Any) -> None:
        """处理 meta block，允许前向引用"""
        self.in_meta_block = True
        for stmt in node.body:
            self._visit(stmt)
        self.in_meta_block = False
