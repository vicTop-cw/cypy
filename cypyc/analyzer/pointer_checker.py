from typing import List, Any, Dict
from cypyc.parser.parser import ASTNode, Module, FuncDef, Param, LetStmt, Name, PointerType


class PointerChecker:
    """指针操作检查器 - 验证指针操作的安全性"""
    
    # 可寻址的C类型
    ADDRESSABLE_TYPES = {'int', 'float', 'double', 'bool', 'char', 'long', 'short', 'void'}
    # Python对象类型（不可寻址）
    PYTHON_OBJECT_TYPES = {'str', 'list', 'dict', 'tuple', 'object', 'set'}
    
    def __init__(self):
        self.errors: List[str] = []
        self.pointer_vars: set = set()
        # 模块级别的类型映射
        self.module_type_map: Dict[str, Any] = {}
        # 当前作用域的变量类型映射（栈式管理）
        self.scope_type_stack: List[Dict[str, Any]] = []
        # 所有权变量跟踪
        self.owned_vars: set = set()
        # 已转移所有权的变量（不再有效）
        self.moved_vars: set = set()
        # defer语句中清理的变量
        self.defer_cleaned_vars: set = set()
        # 当前是否在defer块中
        self.in_defer = False

    def check(self, node: ASTNode, type_map: Dict[str, Any] = None) -> None:
        """检查AST中的指针操作和所有权语义
        
        参数：
            node: 要检查的AST节点
            type_map: 类型映射（变量名 -> 类型），用于获取模块级别的类型信息
        """
        if type_map:
            self.module_type_map = type_map
        self._visit(node)

    def _get_var_type(self, var_name: str) -> Any:
        """从当前作用域链中获取变量类型"""
        for scope in reversed(self.scope_type_stack):
            if var_name in scope:
                return scope[var_name]
        if var_name in self.module_type_map:
            return self.module_type_map[var_name]
        return None

    def _get_var_info(self, var_name: str) -> Dict[str, Any]:
        """获取变量的完整信息（类型、所有权等）"""
        for scope in reversed(self.scope_type_stack):
            if var_name in scope:
                info = scope[var_name]
                if isinstance(info, dict):
                    return info
                return {'type': info}
        if var_name in self.module_type_map:
            info = self.module_type_map[var_name]
            if isinstance(info, dict):
                return info
            return {'type': info}
        return {}

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
        func_scope: Dict[str, Any] = {}
        
        for param in node.params:
            if param.type_annotation:
                type_name = str(param.type_annotation)
                func_scope[param.name] = type_name
        
        self.scope_type_stack.append(func_scope)
        
        for stmt in node.body:
            self._visit(stmt)
        
        self._check_owned_vars_cleanup(func_scope)
        
        self.scope_type_stack.pop()

    def _check_owned_vars_cleanup(self, scope: Dict[str, Any]) -> None:
        """检查作用域内的owned变量是否都已清理"""
        for var_name, info in scope.items():
            if isinstance(info, dict) and info.get('is_owned', False):
                if var_name not in self.defer_cleaned_vars and var_name not in self.moved_vars:
                    self.errors.append(f"Owned variable '{var_name}' must be cleaned with defer or transferred before scope exit")

    def _visit_Param(self, node: Param) -> None:
        if node.is_ref:
            if not node.type_annotation:
                self.errors.append(f"Reference parameter '{node.name}' requires type annotation at {node.line}:{node.col}")

    def _visit_LetStmt(self, node: LetStmt) -> None:
        if node.type_annotation:
            self._visit(node.type_annotation)
        
        if node.type_annotation:
            type_name = str(node.type_annotation)
        else:
            type_name = "object"
        
        var_info = {
            'type': type_name,
            'is_owned': getattr(node, 'is_owned', False),
            'is_mutable': node.mutable,
            'is_const': node.is_const,
            'is_moved': False,
        }
        
        if self.scope_type_stack:
            current_scope = self.scope_type_stack[-1]
            current_scope[node.name] = var_info
            if var_info['is_owned']:
                self.owned_vars.add(node.name)
        else:
            self.module_type_map[node.name] = var_info
            if var_info['is_owned']:
                self.owned_vars.add(node.name)
        
        if node.value:
            self._visit(node.value)

    def _visit_PointerType(self, node: PointerType) -> None:
        """检查指针类型的基础类型是否合法"""
        base_type_name = str(node.base_type)
        
        if base_type_name in self.PYTHON_OBJECT_TYPES:
            self.errors.append(f"Cannot declare pointer to Python object type '{base_type_name}' at {node.line}:{node.col}")
        elif base_type_name not in self.ADDRESSABLE_TYPES and not base_type_name.endswith('*'):
            pass

    def _visit_Assign(self, node: Any) -> None:
        if hasattr(node, 'target') and hasattr(node.target, 'id'):
            var_name = node.target.id
            var_info = self._get_var_info(var_name)
            
            if var_info.get('is_owned', False) and var_info.get('is_moved', False):
                self.errors.append(f"Cannot assign to moved owned variable '{var_name}' at {node.line}:{node.col}")
        
        self._visit(node.target)
        self._visit(node.value)

    def _visit_Name(self, node: Any) -> None:
        """检查变量访问是否符合所有权规则"""
        var_name = node.id
        var_info = self._get_var_info(var_name)
        
        if var_info.get('is_owned', False) and var_info.get('is_moved', False):
            self.errors.append(f"Cannot access moved owned variable '{var_name}' at {node.line}:{node.col}")

    def _visit_BinOp(self, node: Any) -> None:
        self._visit(node.left)
        self._visit(node.right)

    def _visit_UnaryOp(self, node: Any) -> None:
        self._visit(node.operand)

    def _visit_Call(self, node: Any) -> None:
        self._visit(node.func)
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                self._visit(arg[1])
            else:
                self._visit(arg)
        
        if hasattr(node, 'func') and hasattr(node.func, 'id'):
            func_name = node.func.id
            if func_name in ('malloc', 'sizeof', 'free', 'addr', 'transfer_ownership', 'borrow', 'own'):
                if func_name == 'malloc':
                    self._check_malloc_call(node)
                elif func_name == 'sizeof':
                    self._check_sizeof_call(node)
                elif func_name == 'addr':
                    self._check_addr_call(node)
                elif func_name == 'transfer_ownership':
                    self._check_transfer_call(node)

    def _check_transfer_call(self, node: Any) -> None:
        """检查所有权转移调用"""
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"transfer_ownership() requires at least one argument at {node.line}:{node.col}")
            return
        
        arg = pos_args[0]
        if isinstance(arg, Name):
            var_name = arg.id
            var_info = self._get_var_info(var_name)
            
            if not var_info.get('is_owned', False):
                self.errors.append(f"transfer_ownership() requires owned variable, but '{var_name}' is not owned at {node.line}:{node.col}")
            
            if var_info.get('is_moved', False):
                self.errors.append(f"Cannot transfer ownership of already moved variable '{var_name}' at {node.line}:{node.col}")
            
            for scope in reversed(self.scope_type_stack):
                if var_name in scope:
                    scope[var_name] = {**scope[var_name], 'is_moved': True}
                    break
            if var_name in self.module_type_map:
                self.module_type_map[var_name] = {**self.module_type_map[var_name], 'is_moved': True}
            
            self.moved_vars.add(var_name)

    def _check_malloc_call(self, node: Any) -> None:
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"malloc() requires at least one argument at {node.line}:{node.col}")
            return
        
        arg = pos_args[0]
        if hasattr(arg, 'func') and hasattr(arg.func, 'id') and arg.func.id == 'sizeof':
            pass
        else:
            self.errors.append(f"malloc() argument should be sizeof() at {node.line}:{node.col}")

    def _check_sizeof_call(self, node: Any) -> None:
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"sizeof() requires at least one argument at {node.line}:{node.col}")
            return

    def _check_addr_call(self, node: Any) -> None:
        """检查addr()调用的参数是否为可寻址类型"""
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"addr() requires at least one argument at {node.line}:{node.col}")
            return
        
        arg = pos_args[0]
        
        if isinstance(arg, Name):
            var_name = arg.id
            
            var_type = self._get_var_type(var_name)
            
            if var_type:
                type_name = getattr(var_type, 'name', str(var_type))
                
                if type_name in self.PYTHON_OBJECT_TYPES:
                    self.errors.append(f"Cannot take address of Python object '{var_name}' (type '{type_name}') at {node.line}:{node.col}")
                elif type_name.endswith('*'):
                    pass
                elif type_name not in self.ADDRESSABLE_TYPES:
                    pass

    def _visit_DeferStmt(self, node: Any) -> None:
        """检查defer语句中的清理逻辑"""
        old_in_defer = self.in_defer
        self.in_defer = True
        
        for stmt in node.body:
            self._visit(stmt)
            
            if hasattr(stmt, 'kind') and stmt.kind == 'Call':
                if hasattr(stmt.func, 'id'):
                    func_name = stmt.func.id
                    if func_name == 'free':
                        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in stmt.args]
                        if pos_args and isinstance(pos_args[0], Name):
                            var_name = pos_args[0].id
                            self.defer_cleaned_vars.add(var_name)
        
        self.in_defer = old_in_defer