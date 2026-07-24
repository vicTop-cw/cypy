from typing import Dict, List, Any, Optional
from cypyc.parser.parser import ASTNode, Module, FuncDef, LetStmt, ReturnStmt, BinOp, UnaryOp, Call, Name, Constant, PointerType, CastExpr, StructDef, ClassDef


class Type:
    def __init__(self, name: str, is_pointer: bool = False, is_ref: bool = False, generic_params: List['Type'] = None):
        self.name = name
        self.is_pointer = is_pointer
        self.is_ref = is_ref
        self.generic_params = generic_params or []

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
        }
        self.mutable_map: Dict[str, bool] = {}  # 跟踪变量是否可变
        self.current_function_return_type: Optional[Type] = None
        self.errors: List[str] = []
        # 魔法方法注册表：记录类型的 __cast__/__try_cast__ 等方法
        self.magic_methods: Dict[str, Dict[str, FuncDef]] = {}  # {type_name: {method_name: FuncDef}}
        # 结构体定义注册表
        self.struct_defs: Dict[str, StructDef] = {}
        # 类定义注册表
        self.class_defs: Dict[str, ClassDef] = {}
        # 策略栈（用于递归防护）
        self.active_strategies: List[str] = []
        self.strategy_depth: int = 0
        self.max_strategy_depth: int = 5
        # 是否在收集阶段（第一遍）
        self.collecting: bool = False

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

    def check(self, node: ASTNode) -> None:
        self._visit(node)

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
                # 收集结构体中的魔法方法
                for field in stmt.fields:
                    if isinstance(field, FuncDef):
                        if field.name.startswith('__') and field.name.endswith('__'):
                            self.magic_methods[stmt.name][field.name] = field
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
                # 注册函数名到类型映射（函数类型用返回类型表示）
                return_type = self._get_type_from_node(stmt.return_type)
                if return_type:
                    self.type_map[stmt.name] = return_type
        
        # 第二遍：检查所有语句（包括函数体）
        self.collecting = False
        for stmt in node.body:
            self._visit(stmt)

    def _visit_FuncDef(self, node: FuncDef) -> None:
        old_return_type = self.current_function_return_type
        return_type = self._get_type_from_node(node.return_type)
        self.current_function_return_type = return_type

        # 在保存旧映射之前，将函数名注册到全局作用域
        if return_type:
            self.type_map[node.name] = return_type

        # 保存旧的类型和可变性映射，进入新作用域
        old_type_map = self.type_map.copy()
        old_mutable_map = self.mutable_map.copy()

        for param in node.params:
            param_type = self._get_type_from_node(param.type_annotation)
            if param_type:
                self.type_map[param.name] = param_type

        for stmt in node.body:
            self._visit(stmt)

        # 恢复旧的映射，退出作用域
        self.type_map = old_type_map
        self.mutable_map = old_mutable_map
        self.current_function_return_type = old_return_type

    def _visit_LetStmt(self, node: LetStmt) -> None:
        declared_type = self._get_type_from_node(node.type_annotation)
        if node.value:
            value_type = self._visit(node.value)
            if declared_type and value_type and declared_type != value_type:
                # 允许指针类型匹配（void* 可以赋值给 int* 等）
                if declared_type.is_pointer and value_type.is_pointer:
                    self.type_map[node.name] = declared_type
                # 允许数值类型的隐式转换（int → float）
                else:
                    numeric_types = {'int', 'float', 'double'}
                    if declared_type.name in numeric_types and value_type.name in numeric_types:
                        if value_type.name == 'int' and declared_type.name == 'float':
                            # int 可以隐式转换为 float
                            self.type_map[node.name] = declared_type
                        elif value_type.name == 'int' and declared_type.name == 'double':
                            # int 可以隐式转换为 double
                            self.type_map[node.name] = declared_type
                        elif value_type.name == 'float' and declared_type.name == 'double':
                            # float 可以隐式转换为 double
                            self.type_map[node.name] = declared_type
                        else:
                            self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
                    else:
                        self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
            elif not declared_type and value_type:
                if value_type.is_pointer:
                    self.errors.append(f"Pointer variable '{node.name}' requires explicit type annotation at {node.line}:{node.col}")
                else:
                    self.type_map[node.name] = value_type
        if declared_type and node.name not in self.type_map:
            self.type_map[node.name] = declared_type
        # 跟踪变量可变性（val = 不可变, let = 可变）
        self.mutable_map[node.name] = node.mutable

    def _visit_ReturnStmt(self, node: ReturnStmt) -> Optional[Type]:
        if node.value:
            value_type = self._visit(node.value)
            if self.current_function_return_type and value_type:
                # 允许数值类型的隐式转换（int → float）
                numeric_types = {'int', 'float', 'double'}
                target_name = self.current_function_return_type.name
                if not (target_name in numeric_types and 
                        value_type.name in numeric_types and
                        (value_type.name == 'int' and target_name == 'float')):
                    if self.current_function_return_type != value_type:
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
            # 数值类型可以隐式转换（int + float = float）
            numeric_types = {'int', 'float', 'double'}
            if left_type.name in numeric_types and right_type.name in numeric_types:
                # 允许数值类型混合运算
                if left_type.name == 'float' or right_type.name == 'float' or right_type.name == 'double':
                    return Type('float')
                return Type('int')
            elif left_type != right_type:
                self.errors.append(f"Type mismatch in binary operation: {left_type} {node.op} {right_type} at {node.line}:{node.col}")

        return left_type

    def _visit_UnaryOp(self, node: UnaryOp) -> Optional[Type]:
        return self._visit(node.operand)

    def _visit_Call(self, node: Call) -> Optional[Type]:
        self._visit(node.func)
        for arg in node.args:
            self._visit(arg)
        
        if hasattr(node, 'func') and hasattr(node.func, 'id'):
            func_name = node.func.id
            # 先检查是否是用户定义的函数
            if func_name in self.type_map:
                return self.type_map[func_name]
            
            # 内置函数
            if func_name == 'malloc':
                return Type("void", is_pointer=True)
            elif func_name == 'sizeof':
                return Type("int")
            elif func_name == 'addr':
                return Type("void", is_pointer=True)
            # 内置类型转换函数
            elif func_name in ['int', 'float', 'double', 'str', 'bool']:
                return Type(func_name)
            # 内置函数
            elif func_name == 'print':
                return Type("None")
            elif func_name == 'len':
                return Type("int")
        
        return Type("None")

    def _visit_Name(self, node: Name) -> Optional[Type]:
        if node.id in self.type_map:
            return self.type_map[node.id]
        # 检查是否是内置类型、常量和内置函数
        builtin_types = ['int', 'float', 'double', 'bool', 'str', 'None']
        builtin_constants = ['True', 'False']
        builtin_functions = ['print', 'len', 'malloc', 'sizeof', 'addr']
        if node.id in builtin_types:
            return Type(node.id)
        if node.id in builtin_constants:
            return Type("bool")
        if node.id in builtin_functions:
            return Type("None")
        # 收集阶段不报错（允许前向引用）
        if self.collecting:
            return None
        self.errors.append(f"Undefined name '{node.id}' at {node.line}:{node.col}")
        return None

    def _visit_StructDef(self, node: Any) -> None:
        """处理结构体定义，为方法中的 self 设置类型"""
        # 访问字段
        for field in node.fields:
            self._visit(field)
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

    def _visit_StructLiteral(self, node: Any) -> Optional[Type]:
        """处理结构体字面量，返回结构体类型"""
        return Type(node.struct_name)

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
        """处理属性访问，返回属性类型"""
        value_type = self._visit(node.value)
        if value_type and value_type.name in self.struct_defs:
            struct_def = self.struct_defs[value_type.name]
            for field in struct_def.fields:
                if field.name == node.attr:
                    return self._visit(field.type_annotation)
        return None

    def _visit_Assign(self, node: Any) -> Optional[Type]:
        # 先访问 value，确保右边的表达式先被检查
        value_type = None
        if node.value:
            value_type = self._visit(node.value)
        
        # 处理赋值目标
        if hasattr(node.target, 'id'):
            target_name = node.target.id
            
            if target_name in self.type_map:
                # 变量已存在，检查类型兼容性
                target_type = self.type_map[target_name]
                if value_type and target_type != value_type:
                    # 允许数值类型的隐式转换（int → float）
                    numeric_types = {'int', 'float', 'double'}
                    if not (target_type.name in numeric_types and 
                            value_type.name in numeric_types and
                            (value_type.name == 'int' and target_type.name == 'float')):
                        self.errors.append(f"Type mismatch in assignment: expected {target_type}, got {value_type} at {node.line}:{node.col}")
            else:
                # 变量不存在，添加到作用域
                if value_type:
                    if value_type.is_pointer:
                        self.errors.append(f"Pointer variable '{target_name}' requires explicit type annotation at {node.line}:{node.col}")
                    else:
                        self.type_map[target_name] = value_type
                        self.mutable_map[target_name] = True
        
        # 检查不可变变量的重新赋值
        if hasattr(node.target, 'id'):
            target_name = node.target.id
            if target_name in self.mutable_map and not self.mutable_map[target_name]:
                self.errors.append(f"Immutable variable '{target_name}' cannot be reassigned at {node.line}:{node.col}")
        
        return value_type

    def _visit_ForStmt(self, node: Any) -> None:
        """处理 for 循环，注册循环变量"""
        # 获取循环变量名称
        if hasattr(node.target, 'id'):
            target_name = node.target.id
            # 从迭代对象推断类型
            iter_type = self._visit(node.iter)
            if iter_type and hasattr(iter_type, 'generic_params') and iter_type.generic_params:
                # 泛型列表，获取元素类型
                element_type = iter_type.generic_params[0]
                self.type_map[target_name] = element_type
            else:
                # 默认类型为 object
                self.type_map[target_name] = Type('object')
        else:
            # 访问迭代对象（如果没有目标变量）
            self._visit(node.iter)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_CastExpr(self, node: CastExpr) -> Optional[Type]:
        """处理类型转换表达式"""
        # 检查值的类型
        value_type = self._visit(node.value)
        
        # 获取目标类型
        target_type = self._get_type_from_node(node.target_type)
        if not target_type:
            target_type = Type(node.target_type.id) if hasattr(node.target_type, 'id') else Type(str(node.target_type))
        
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
        
        # 对于基本类型，允许隐式转换
        if value_type:
            numeric_types = {'int', 'float', 'double'}
            if value_type.name in numeric_types and target_type.name in numeric_types:
                return target_type
        
        return target_type

    def _visit_Constant(self, node: Constant) -> Optional[Type]:
        if isinstance(node.value, int):
            return Type("int")
        if isinstance(node.value, float):
            return Type("float")
        if isinstance(node.value, str):
            return Type("str")
        if isinstance(node.value, bool):
            return Type("bool")
        if isinstance(node.value, list):
            # 推断列表元素类型
            if node.value:
                element_types = []
                for item in node.value:
                    if isinstance(item, int):
                        element_types.append("int")
                    elif isinstance(item, float):
                        element_types.append("float")
                    elif isinstance(item, str):
                        element_types.append("str")
                    elif isinstance(item, bool):
                        element_types.append("bool")
                    else:
                        element_types.append("object")
                # 使用最具体的类型
                if all(t == "int" for t in element_types):
                    return Type("list", generic_params=[Type("int")])
                elif all(t in ("int", "float") for t in element_types):
                    return Type("list", generic_params=[Type("float")])
                else:
                    return Type("list", generic_params=[Type("object")])
            else:
                # 空列表，默认 object
                return Type("list", generic_params=[Type("object")])
        return None

    def _get_type_from_node(self, node: Optional[ASTNode]) -> Optional[Type]:
        if node is None:
            return None
        if isinstance(node, Name):
            if node.id in self.type_map:
                return self.type_map[node.id]
            return Type(node.id)
        if isinstance(node, PointerType):
            base_type = self._get_type_from_node(node.base_type)
            if base_type:
                return Type(base_type.name, is_pointer=True)
            return None
        if hasattr(node, 'kind') and node.kind == 'GenericType':
            # 处理泛型类型如 list[int]
            generic_params = []
            for arg in node.args:
                arg_type = self._get_type_from_node(arg)
                if arg_type:
                    generic_params.append(arg_type)
            return Type(node.name, generic_params=generic_params)
        return None
