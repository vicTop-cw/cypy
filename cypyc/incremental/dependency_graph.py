"""依赖图构建器 - 追踪定义之间的依赖关系"""

from typing import Any, Dict, Set, List, Optional
from cypyc.parser.parser import ASTNode, FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef


class DependencyGraph:
    """定义级别的依赖图"""

    # 标识符节点的类型词表：parser 把标识符降级为 kind="Name" 的 Name 节点
    # (cypyc/parser/parser.py, class Name)，载荷在 .id 上；解析结果里从来不存在
    # kind="Identifier" 的节点（IDENTIFIER 只是 lexer 的 token 类型）。
    # 'Identifier' 作为别名保留，兼容手工构造/历史遗留节点，不再作为唯一匹配项。
    _IDENTIFIER_KINDS = frozenset({'Name', 'Identifier'})

    def __init__(self):
        # 依赖映射: definition_name -> set(dependent_definition_names)
        self._dependencies: Dict[str, Set[str]] = {}
        # 反向依赖映射: definition_name -> set(definitions_that_depend_on_it)
        self._reverse_dependencies: Dict[str, Set[str]] = {}
        # 定义类型映射: definition_name -> definition_type
        self._definition_types: Dict[str, str] = {}

    @classmethod
    def _node_identifier(cls, value: Any) -> Optional[str]:
        """若 value 是承载标识符的节点则返回其 .id，否则返回 None"""
        if isinstance(value, ASTNode) and getattr(value, 'kind', None) in cls._IDENTIFIER_KINDS:
            identifier = getattr(value, 'id', None)
            if isinstance(identifier, str):
                return identifier
        return None

    def _extract_identifier_usage(self, node: ASTNode) -> Set[str]:
        """从AST节点中提取所有标识符使用"""
        identifiers = set()
        
        if isinstance(node, ASTNode):
            # 节点自身就是标识符（例如字段/参数/返回类型直接就是 Name 注解）
            own_identifier = self._node_identifier(node)
            if own_identifier is not None:
                identifiers.add(own_identifier)

            # 遍历所有属性
            for attr_name in dir(node):
                if attr_name.startswith('_'):
                    continue
                
                attr_value = getattr(node, attr_name)
                
                # 如果是标识符节点（Name，兼容 Identifier）
                identifier = self._node_identifier(attr_value)
                if identifier is not None:
                    identifiers.add(identifier)
                
                # 如果是列表或元组，递归处理
                elif isinstance(attr_value, (list, tuple)):
                    for item in attr_value:
                        identifiers.update(self._extract_identifier_usage(item))
                
                # 如果是ASTNode，递归处理
                elif isinstance(attr_value, ASTNode):
                    identifiers.update(self._extract_identifier_usage(attr_value))
        
        return identifiers

    @staticmethod
    def _exclude_self_and_generics(definition: ASTNode, dependencies: Set[str]) -> Set[str]:
        """排除定义自身名称与其泛型形参（泛型形参不是真实依赖，见 FuncDef 分支）"""
        excluded = {definition.name}
        excluded.update(getattr(definition, 'generic_params', None) or [])
        return dependencies - excluded

    def _analyze_definition_dependencies(self, definition: ASTNode) -> Set[str]:
        """分析单个定义的依赖关系"""
        dependencies = set()
        
        if isinstance(definition, FuncDef):
            # 函数体中的标识符使用
            body_usage = self._extract_identifier_usage(definition)
            
            # 参数类型注解中的依赖
            for param in definition.params:
                if hasattr(param, 'type_annotation'):
                    dependencies.update(self._extract_identifier_usage(param.type_annotation))
            
            # 返回类型中的依赖
            if definition.return_type:
                dependencies.update(self._extract_identifier_usage(definition.return_type))
            
            # 泛型参数约束中的依赖
            for constraint in definition.generic_constraints.values():
                dependencies.update(self._extract_identifier_usage(constraint))
            
            # 合并并排除函数自身名称和泛型参数
            dependencies = self._exclude_self_and_generics(definition, dependencies | body_usage)
        
        elif isinstance(definition, StructDef):
            # 字段类型注解中的依赖
            for field in definition.fields:
                if hasattr(field, 'type_annotation'):
                    dependencies.update(self._extract_identifier_usage(field.type_annotation))
            
            # 泛型参数约束中的依赖
            for constraint in definition.generic_constraints.values():
                dependencies.update(self._extract_identifier_usage(constraint))
            
            # 方法中的依赖
            for method in definition.methods:
                dependencies.update(self._analyze_definition_dependencies(method))
            
            # 排除结构体自身名称和泛型参数
            dependencies = self._exclude_self_and_generics(definition, dependencies)
        
        elif isinstance(definition, EnumDef):
            # 变体值中的依赖
            for variant in definition.variants:
                if variant.value:
                    dependencies.update(self._extract_identifier_usage(variant.value))
            
            # 排除枚举自身名称
            dependencies -= {definition.name}
        
        elif isinstance(definition, TypeAlias):
            # 目标类型中的依赖
            if hasattr(definition, 'target'):
                dependencies.update(self._extract_identifier_usage(definition.target))
            
            # 泛型参数约束中的依赖
            if hasattr(definition, 'generic_constraints'):
                for constraint in definition.generic_constraints.values():
                    dependencies.update(self._extract_identifier_usage(constraint))
            
            # 排除类型别名自身名称和泛型参数
            dependencies = self._exclude_self_and_generics(definition, dependencies)
        
        elif isinstance(definition, ExceptionDef):
            # 基础类型中的依赖
            if definition.base_type:
                dependencies.update(self._extract_identifier_usage(definition.base_type))
            
            # 字段类型注解中的依赖
            for field in definition.fields:
                if hasattr(field, 'type_annotation'):
                    dependencies.update(self._extract_identifier_usage(field.type_annotation))
            
            # 排除异常自身名称
            dependencies -= {definition.name}
        
        elif isinstance(definition, TraitDef):
            # 方法中的依赖
            for method in definition.methods:
                dependencies.update(self._analyze_definition_dependencies(method))
            
            # 排除trait自身名称和泛型参数
            dependencies = self._exclude_self_and_generics(definition, dependencies)
        
        return dependencies
    
    def build_from_ast(self, ast: ASTNode) -> None:
        """从AST构建依赖图"""
        # 清空现有图
        self._dependencies.clear()
        self._reverse_dependencies.clear()
        self._definition_types.clear()
        
        if not hasattr(ast, 'body'):
            return
        
        # 第一步：收集所有顶层定义
        definitions: Dict[str, ASTNode] = {}
        
        for stmt in ast.body:
            if isinstance(stmt, (FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef)):
                definitions[stmt.name] = stmt
                # 记录定义类型
                self._definition_types[stmt.name] = stmt.kind
        
        # 第二步：分析每个定义的依赖关系
        for name, definition in definitions.items():
            dependencies = self._analyze_definition_dependencies(definition)
            
            # 过滤掉未定义的标识符（可能是内置类型或外部导入）
            valid_dependencies = dependencies & definitions.keys()
            
            self._dependencies[name] = valid_dependencies
            
            # 更新反向依赖
            for dep_name in valid_dependencies:
                if dep_name not in self._reverse_dependencies:
                    self._reverse_dependencies[dep_name] = set()
                self._reverse_dependencies[dep_name].add(name)
    
    def get_dependencies(self, definition_name: str) -> Set[str]:
        """获取指定定义直接依赖的定义名称"""
        return self._dependencies.get(definition_name, set())
    
    def get_dependents(self, definition_name: str) -> Set[str]:
        """获取直接依赖于指定定义的定义名称"""
        return self._reverse_dependencies.get(definition_name, set())
    
    def get_transitive_dependents(self, definition_name: str) -> Set[str]:
        """获取传递依赖于指定定义的所有定义名称（包括间接依赖）"""
        visited = set()
        result = set()
        queue = [definition_name]
        
        while queue:
            current = queue.pop(0)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # 获取直接依赖于当前定义的定义
            dependents = self.get_dependents(current)
            
            for dependent in dependents:
                if dependent not in result:
                    result.add(dependent)
                    queue.append(dependent)
        
        return result
    
    def get_affected_definitions(self, changed_definitions: Set[str]) -> Set[str]:
        """获取所有受变更影响的定义（包括传递依赖）"""
        affected = set(changed_definitions)
        
        for changed_name in changed_definitions:
            affected.update(self.get_transitive_dependents(changed_name))
        
        return affected
    
    def get_all_definitions(self) -> Set[str]:
        """获取所有定义名称"""
        return set(self._dependencies.keys())
    
    def get_definition_type(self, name: str) -> Optional[str]:
        """获取定义类型"""
        return self._definition_types.get(name)
    
    def is_empty(self) -> bool:
        """检查依赖图是否为空"""
        return len(self._dependencies) == 0
    
    def clear(self) -> None:
        """清空依赖图"""
        self._dependencies.clear()
        self._reverse_dependencies.clear()
        self._definition_types.clear()
    
    def __repr__(self) -> str:
        """返回依赖图的字符串表示"""
        lines = ["DependencyGraph:"]
        for name, deps in sorted(self._dependencies.items()):
            deps_str = ", ".join(sorted(deps)) if deps else "(none)"
            lines.append(f"  {name} -> [{deps_str}]")
        return "\n".join(lines)