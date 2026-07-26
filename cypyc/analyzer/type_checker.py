from typing import Dict, List, Any, Optional
from cypyc.parser.parser import ASTNode, Module, FuncDef, LetStmt, ReturnStmt, BinOp, UnaryOp, Call, Name, Constant, PointerType, CastExpr, StructDef, ClassDef, TraitDef, ExceptionDef


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
        # 是否在 meta block 中（meta block 中允许前向引用）
        self.in_meta_block = False
        # 函数定义注册表（用于泛型函数类型推断）
        self.func_defs: Dict[str, FuncDef] = {}
        # Trait 定义注册表（用于泛型约束检查）
        self.trait_defs: Dict[str, Any] = {}
        # Trait 实现注册表（用于检查类型是否实现了 trait）
        self.trait_impls: Dict[str, List[str]] = {}  # {trait_name: [type_name1, type_name2, ...]}
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
                    if has_python_decorator:
                        self.type_map[stmt.name] = Type("object")
            elif isinstance(stmt, TraitDef):
                # 注册 trait 定义
                self.trait_defs[stmt.name] = stmt
                # 初始化 trait 实现列表
                if stmt.name not in self.trait_impls:
                    self.trait_impls[stmt.name] = []
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
        
        # 第二遍：检查所有语句（包括函数体）
        self.collecting = False
        for stmt in node.body:
            self._visit(stmt)

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
                self.type_map[param.name] = param_type
            else:
                # 即使没有类型注解，也注册为 object 类型，确保参数在作用域中可见
                self.type_map[param.name] = Type("object")

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
                    elif value_type.name == 'None':
                        # None 可以赋值给任何类型（与 Python 行为一致）
                        self.type_map[node.name] = declared_type
                    else:
                        self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
            elif not declared_type and value_type:
                # 渐进式类型：未标注类型的变量使用 object 类型
                # 即使有初始值，也不推断类型
                self.type_map[node.name] = Type("object")
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
                # 允许 object 类型转换为任意类型（用于 @python 装饰器函数的返回值）
                if value_type.name == 'object':
                    return value_type
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
            # 处理 'in' 操作符（成员检测）
            if node.op == 'in':
                return Type('bool')
            
            # 处理 'is' 操作符（身份检测）
            if node.op == 'is':
                return Type('bool')
            
            # 渐进式类型：允许 object 类型参与任何操作（动态行为）
            if left_type.name == 'object' or right_type.name == 'object':
                return Type('object')
            
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
                    # 推断泛型参数类型
                    inferred_types = {}
                    # 提取参数类型（忽略关键字参数名称）
                    arg_types = []
                    for arg in node.args:
                        if isinstance(arg, tuple) and len(arg) == 2:
                            arg_types.append(self._visit(arg[1]))
                        else:
                            arg_types.append(self._visit(arg))
                    
                    # 根据参数类型推断泛型参数
                    for i, param in enumerate(func_def.params):
                        if i < len(arg_types) and arg_types[i]:
                            param_type_name = getattr(param.type_annotation, 'id', None)
                            if param_type_name in generic_params:
                                inferred_types[param_type_name] = arg_types[i]
                    
                    # 检查泛型参数约束
                    for param, inferred_type in inferred_types.items():
                        if param in generic_constraints:
                            constraint_type_ast = generic_constraints[param]
                            # 获取约束类型名称列表（支持联合类型和 trait）
                            constraint_type_names = []
                            is_trait_constraint = False
                            
                            if hasattr(constraint_type_ast, 'kind') and constraint_type_ast.kind == 'UnionType':
                                # 联合类型：int | float
                                for t in constraint_type_ast.types:
                                    constraint_type_names.append(getattr(t, 'id', str(t)))
                            else:
                                # 单一类型或 trait
                                constraint_name = getattr(constraint_type_ast, 'id', str(constraint_type_ast))
                                constraint_type_names.append(constraint_name)
                                # 检查是否是 trait 约束
                                if constraint_name in self.trait_defs:
                                    is_trait_constraint = True
                            
                            # 检查推断类型是否满足约束
                            if is_trait_constraint:
                                # trait 约束：检查类型是否实现了该 trait
                                trait_name = constraint_type_names[0]
                                if inferred_type.name not in self.trait_impls.get(trait_name, []):
                                    line = node.line if hasattr(node, 'line') else 0
                                    col = node.col if hasattr(node, 'col') else 0
                                    self.errors.append(f"Generic constraint violation: type '{inferred_type.name}' does not implement trait '{trait_name}' for parameter '{param}' at {line}:{col}")
                            else:
                                # 类型约束：检查推断类型是否在允许的类型列表中
                                if inferred_type.name not in constraint_type_names:
                                    line = node.line if hasattr(node, 'line') else 0
                                    col = node.col if hasattr(node, 'col') else 0
                                    constraint_str = ' | '.join(constraint_type_names)
                                    self.errors.append(f"Generic constraint violation: type '{inferred_type.name}' does not satisfy constraint '{constraint_str}' for parameter '{param}' at {line}:{col}")
                    
                    # 返回推断后的函数返回类型
                    if func_def.return_type:
                        return_type = self._get_type_from_node(func_def.return_type)
                        # 如果返回类型是泛型参数本身（如 T），直接返回推断的类型
                        if return_type and return_type.name in inferred_types:
                            return inferred_types[return_type.name]
                        # 更新返回类型的泛型参数
                        if return_type and return_type.generic_params:
                            updated_generic = []
                            for gp in return_type.generic_params:
                                if gp.name in inferred_types:
                                    updated_generic.append(inferred_types[gp.name])
                                else:
                                    updated_generic.append(gp)
                            return_type.generic_params = updated_generic
                        return return_type
                    return Type("None")
            
            # 先检查是否是用户定义的函数
            if func_name in self.type_map:
                return self.type_map[func_name]
            
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
                            # 使用函数名的位置作为错误位置
                            line = node.func.line if hasattr(node.func, 'line') else node.line
                            col = node.func.col if hasattr(node.func, 'col') else node.col
                            self.errors.append(f"addr() cannot take address of {arg_type.name} at {line}:{col}")
                return Type("void", is_pointer=True)
            # 内置类型转换函数
            elif func_name in ['int', 'float', 'double', 'str', 'bool']:
                return Type(func_name)
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
        
        # 如果 func 是属性访问（方法调用），返回属性类型
        if func_type:
            return func_type
        
        return Type("None")

    def _visit_Name(self, node: Name) -> Optional[Type]:
        if node.id in self.type_map:
            return self.type_map[node.id]
        # 检查是否是内置类型、常量和内置函数
        builtin_types = ['int', 'float', 'double', 'bool', 'str', 'None', 'Exception', 'list']
        builtin_constants = ['True', 'False', '__main__']
        builtin_functions = ['print', 'len', 'malloc', 'free', 'sizeof', 'addr', 'ord', 'range', 'type']
        # 模块级魔法变量
        module_magic = ['__name__']
        # 通配符 _ 在 match case 中不报错
        if node.id == '_':
            return Type("object")
        if node.id in builtin_types:
            return Type(node.id)
        if node.id in builtin_constants:
            return Type("bool" if node.id in ['True', 'False'] else "str")
        if node.id in builtin_functions:
            return Type("None")
        if node.id in module_magic:
            return Type("str")
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
        if value_type and value_type.name in self.struct_defs:
            struct_def = self.struct_defs[value_type.name]
            
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
        if value_type and value_type.name in self.class_defs:
            class_def = self.class_defs[value_type.name]
            for body_stmt in class_def.body:
                if isinstance(body_stmt, LetStmt) and body_stmt.name == node.attr:
                    return self._visit(body_stmt.type_annotation)
                elif isinstance(body_stmt, FuncDef) and body_stmt.name == node.attr:
                    return self._get_type_from_node(body_stmt.return_type)
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
                # 检查变量是否不可变（let 声明的变量）
                if target_name in self.mutable_map and not self.mutable_map[target_name]:
                    self.errors.append(f"Immutable variable '{target_name}' cannot be reassigned at {node.line}:{node.col}")
                
                # 变量已存在，检查类型兼容性
                target_type = self.type_map[target_name]
                if value_type and target_type != value_type:
                    # 允许数值类型的隐式转换（int → float）
                    numeric_types = {'int', 'float', 'double'}
                    # 允许 void* 隐式转换为任何其他指针类型
                    is_void_ptr_conversion = (value_type.name == 'void' and value_type.is_pointer and 
                                             target_type.is_pointer)
                    if not ((target_type.name in numeric_types and 
                            value_type.name in numeric_types and
                            (value_type.name == 'int' and target_type.name == 'float')) or 
                            is_void_ptr_conversion):
                        self.errors.append(f"Type mismatch in assignment: expected {target_type}, got {value_type} at {node.line}:{node.col}")
            else:
                # 变量不存在，添加到作用域
                # 渐进式类型：未标注类型的变量使用 object 类型
                self.type_map[target_name] = Type("object")
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
            elif iter_type and iter_type.name == 'int':
                # 如果迭代对象是返回 int 的生成器，循环变量也是 int
                self.type_map[target_name] = Type('int')
            else:
                # 默认类型为 object
                self.type_map[target_name] = Type('object')
        else:
            # 访问迭代对象（如果没有目标变量）
            self._visit(node.iter)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_WhileStmt(self, node: Any) -> None:
        """处理 while 循环"""
        # 访问条件表达式
        self._visit(node.test)
        
        # 访问循环体
        for stmt in node.body:
            self._visit(stmt)

    def _visit_IfStmt(self, node: Any) -> None:
        """处理 if 语句"""
        # 访问条件表达式
        self._visit(node.test)
        
        # 访问 if 分支
        for stmt in node.body:
            self._visit(stmt)
        
        # 访问 elif/else 分支（elif 作为嵌套 IfStmt 在 orelse 中）
        if hasattr(node, 'orelse') and node.orelse:
            for stmt in node.orelse:
                self._visit(stmt)

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
                        element_types.append(Type("int"))
                    elif isinstance(item, float):
                        element_types.append(Type("float"))
                    elif isinstance(item, str):
                        element_types.append(Type("str"))
                    elif isinstance(item, bool):
                        element_types.append(Type("bool"))
                    elif isinstance(item, ASTNode):
                        # 递归访问 ASTNode 元素，获取其完整类型
                        item_type = self._visit(item)
                        if item_type:
                            element_types.append(item_type)
                        else:
                            element_types.append(Type("object"))
                    else:
                        element_types.append(Type("object"))
                # 使用最具体的类型
                if all(t.name == "int" and not t.generic_params for t in element_types):
                    return Type("list", generic_params=[Type("int")])
                elif all(t.name in ("int", "float") and not t.generic_params for t in element_types):
                    return Type("list", generic_params=[Type("float")])
                elif len(element_types) > 0 and all(t == element_types[0] for t in element_types):
                    # 所有元素类型相同（包括嵌套泛型类型）
                    return Type("list", generic_params=[element_types[0]])
                else:
                    # 混合类型或无法统一，使用 object
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
                # 检查基础类型是否为Python对象类型
                python_types = {'str', 'list', 'dict', 'tuple', 'object', 'set'}
                if base_type.name in python_types:
                    self.errors.append(f"Cannot declare pointer to Python object type '{base_type.name}' at {node.line}:{node.col}")
                    return None
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

    def _visit_MatchStmt(self, node: Any) -> None:
        """处理 match 语句"""
        # 访问匹配表达式
        self._visit(node.subject)
        
        # 访问各个 case 分支
        for case in node.cases:
            # 访问 pattern（包含变量绑定）
            if hasattr(case, 'pattern') and case.pattern:
                pattern = case.pattern
                # 如果 pattern 是字典（case pattern if condition），获取真正的 pattern
                if isinstance(pattern, dict) and 'pattern' in pattern:
                    pattern = pattern['pattern']
                # 如果 pattern 是列表（元组/列表模式），递归访问每个元素
                if isinstance(pattern, list):
                    for p in pattern:
                        if hasattr(p, 'kind'):
                            self._visit(p)
                else:
                    self._visit(pattern)
            # 访问 case 条件（如果有）
            if hasattr(case, 'condition') and case.condition:
                self._visit(case.condition)
            # 访问 case 体
            for stmt in case.body:
                self._visit(stmt)

    def _visit_GuardStmt(self, node: Any) -> None:
        """处理 guard 语句"""
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

    def _visit_Subscript(self, node: Any) -> Optional[Type]:
        """处理下标访问"""
        base_type = self._visit(node.value)
        # 访问下标表达式
        self._visit(node.slice)
        # 返回基类型的元素类型（如果是列表）
        if base_type and base_type.name == "list" and base_type.generic_params:
            return base_type.generic_params[0]
        return base_type

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
