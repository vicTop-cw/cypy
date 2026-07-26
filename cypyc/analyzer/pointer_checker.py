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

    def check(self, node: ASTNode, type_map: Dict[str, Any] = None) -> None:
        """检查AST中的指针操作
        
        参数：
            node: 要检查的AST节点
            type_map: 类型映射（变量名 -> 类型），用于获取模块级别的类型信息
        """
        if type_map:
            self.module_type_map = type_map
        self._visit(node)

    def _get_var_type(self, var_name: str) -> Any:
        """从当前作用域链中获取变量类型"""
        # 从最内层作用域开始查找
        for scope in reversed(self.scope_type_stack):
            if var_name in scope:
                return scope[var_name]
        # 在模块级别查找
        if var_name in self.module_type_map:
            return self.module_type_map[var_name]
        return None

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
        # 创建新的函数作用域
        func_scope: Dict[str, Any] = {}
        
        # 注册参数类型
        for param in node.params:
            if param.type_annotation:
                type_name = str(param.type_annotation)
                func_scope[param.name] = type_name
        
        # 压入作用域栈
        self.scope_type_stack.append(func_scope)
        
        # 访问函数体
        for stmt in node.body:
            self._visit(stmt)
        
        # 弹出作用域栈
        self.scope_type_stack.pop()

    def _visit_Param(self, node: Param) -> None:
        if node.is_ref:
            if not node.type_annotation:
                self.errors.append(f"Reference parameter '{node.name}' requires type annotation at {node.line}:{node.col}")

    def _visit_LetStmt(self, node: LetStmt) -> None:
        # 检查变量类型是否为指针类型
        if node.type_annotation:
            self._visit(node.type_annotation)
        
        # 注册变量类型到当前作用域
        if self.scope_type_stack:
            current_scope = self.scope_type_stack[-1]
            if node.type_annotation:
                type_name = str(node.type_annotation)
                current_scope[node.name] = type_name
            else:
                # 没有类型注解，默认视为 object 类型
                current_scope[node.name] = "object"
        
        if node.value:
            self._visit(node.value)
    
    def _visit_PointerType(self, node: PointerType) -> None:
        """检查指针类型的基础类型是否合法"""
        base_type_name = str(node.base_type)
        
        # 检查基础类型是否为Python对象类型
        if base_type_name in self.PYTHON_OBJECT_TYPES:
            self.errors.append(f"Cannot declare pointer to Python object type '{base_type_name}' at {node.line}:{node.col}")
        elif base_type_name not in self.ADDRESSABLE_TYPES and not base_type_name.endswith('*'):
            # 对于自定义类型，允许指针声明
            pass

    def _visit_Assign(self, node: Any) -> None:
        self._visit(node.target)
        self._visit(node.value)

    def _visit_Name(self, node: Any) -> None:
        pass

    def _visit_BinOp(self, node: Any) -> None:
        self._visit(node.left)
        self._visit(node.right)

    def _visit_UnaryOp(self, node: Any) -> None:
        self._visit(node.operand)

    def _visit_Call(self, node: Any) -> None:
        self._visit(node.func)
        for arg in node.args:
            if isinstance(arg, tuple) and len(arg) == 2:
                # 关键字参数：(name, value)
                self._visit(arg[1])
            else:
                # 位置参数
                self._visit(arg)
        
        if hasattr(node, 'func') and hasattr(node.func, 'id'):
            func_name = node.func.id
            if func_name in ('malloc', 'sizeof', 'free', 'addr'):
                if func_name == 'malloc':
                    self._check_malloc_call(node)
                elif func_name == 'sizeof':
                    self._check_sizeof_call(node)
                elif func_name == 'addr':
                    self._check_addr_call(node)

    def _check_malloc_call(self, node: Any) -> None:
        # 提取位置参数（忽略关键字参数）
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
        # 提取位置参数（忽略关键字参数）
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"sizeof() requires at least one argument at {node.line}:{node.col}")
            return

    def _check_addr_call(self, node: Any) -> None:
        """检查addr()调用的参数是否为可寻址类型"""
        # 提取位置参数（忽略关键字参数）
        pos_args = [arg[1] if isinstance(arg, tuple) and len(arg) == 2 else arg for arg in node.args]
        if not pos_args:
            self.errors.append(f"addr() requires at least one argument at {node.line}:{node.col}")
            return
        
        arg = pos_args[0]
        
        # 如果参数是变量名，检查其类型
        if isinstance(arg, Name):
            var_name = arg.id
            
            # 获取变量类型（从作用域链中查找）
            var_type = self._get_var_type(var_name)
            
            if var_type:
                # 获取类型名称
                type_name = getattr(var_type, 'name', str(var_type))
                
                # 检查是否为Python对象类型
                if type_name in self.PYTHON_OBJECT_TYPES:
                    self.errors.append(f"Cannot take address of Python object '{var_name}' (type '{type_name}') at {node.line}:{node.col}")
                elif type_name.endswith('*'):
                    # 指针类型可以取地址
                    pass
                elif type_name not in self.ADDRESSABLE_TYPES:
                    # 对于自定义类型或结构体，允许取地址
                    pass
            else:
                # 无法确定类型，跳过检查（可能是模块级变量或未声明的变量）
                pass