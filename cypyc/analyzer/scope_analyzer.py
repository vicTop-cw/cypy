from typing import Dict, List, Set, Any
from cypyc.parser.parser import ASTNode, Module, FuncDef, ClassDef, StructDef, LetStmt, Name


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
    
    def _register_builtins(self):
        """注册内置类型和函数到根作用域"""
        builtins = [
            ('int', 'type'),
            ('float', 'type'),
            ('double', 'type'),
            ('bool', 'type'),
            ('str', 'type'),
            ('None', 'type'),
            ('print', 'function'),
            ('len', 'function'),
            ('malloc', 'function'),
            ('sizeof', 'function'),
            ('addr', 'function'),
        ]
        for name, kind in builtins:
            self.root_scope.add_symbol(name, kind, None)

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
        self.current_scope.add_symbol(node.name, "function", node)
        func_scope = self.current_scope.create_child("function")
        self.current_scope = func_scope

        for param in node.params:
            func_scope.add_symbol(param.name, "parameter", param)

        for stmt in node.body:
            self._visit(stmt)

        self.current_scope = func_scope.parent

    def _visit_ClassDef(self, node: ClassDef) -> None:
        self.current_scope.add_symbol(node.name, "class", node)
        class_scope = self.current_scope.create_child("class")
        self.current_scope = class_scope

        for stmt in node.body:
            self._visit(stmt)

        self.current_scope = class_scope.parent

    def _visit_StructDef(self, node: StructDef) -> None:
        self.current_scope.add_symbol(node.name, "struct", node)
        struct_scope = self.current_scope.create_child("struct")
        self.current_scope = struct_scope

        for field in node.fields:
            struct_scope.add_symbol(field.name, "field", field)

        self.current_scope = struct_scope.parent

    def _visit_LetStmt(self, node: LetStmt) -> None:
        if node.name in self.current_scope.symbols:
            self.errors.append(f"Variable '{node.name}' already declared in this scope at {node.line}:{node.col}")
        else:
            self.current_scope.add_symbol(node.name, "variable", node)
        if node.value:
            self._visit(node.value)

    def _visit_Name(self, node: Name) -> None:
        symbol = self.current_scope.lookup(node.id)
        if symbol is None:
            self.errors.append(f"Undefined name '{node.id}' at {node.line}:{node.col}")

    def _visit_Assign(self, node: Any) -> None:
        # 先访问 value，确保右边的表达式先被检查
        if node.value:
            self._visit(node.value)
        # 然后注册变量（如果是新变量）
        if hasattr(node.target, 'id'):
            target_name = node.target.id
            if target_name not in self.current_scope.symbols:
                # 检查父作用域中是否存在同名变量
                if self.current_scope.parent and self.current_scope.parent.lookup(target_name):
                    # 如果父作用域存在，说明是赋值给外部变量，不需要在当前作用域注册
                    pass
                else:
                    # 新变量，注册到当前作用域
                    self.current_scope.add_symbol(target_name, "variable", node)

    def _visit_ForStmt(self, node: Any) -> None:
        """处理 for 循环，注册循环变量到作用域"""
        # 先访问迭代对象
        self._visit(node.iter)
        
        # 注册循环变量
        if hasattr(node.target, 'id'):
            target_name = node.target.id
            self.current_scope.add_symbol(target_name, "variable", node)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_Call(self, node: Any) -> None:
        self._visit(node.func)
        for arg in node.args:
            self._visit(arg)
