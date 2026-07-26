"""AST 差异比较器 - 识别定义级别的变化"""

import hashlib
from typing import Dict, Set, Any, Optional
from cypyc.parser.parser import ASTNode, FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef


class ASTDiffer:
    """AST 差异比较器"""
    
    def __init__(self):
        self.changed_definitions: Set[str] = set()
        self.added_definitions: Set[str] = set()
        self.removed_definitions: Set[str] = set()
    
    def _compute_definition_hash(self, node: ASTNode) -> str:
        """计算定义节点的哈希值"""
        content = []
        
        if isinstance(node, FuncDef):
            content.append(f"func:{node.name}")
            content.append(f"params:{len(node.params)}")
            for param in node.params:
                content.append(f"param:{param.name}:{self._type_to_str(getattr(param, 'type_annotation', None))}")
            content.append(f"return:{self._type_to_str(node.return_type)}")
            content.append(f"body:{len(node.body)}")
            # 简单计算函数体的哈希
            for stmt in node.body:
                content.append(self._node_to_hash(stmt))
        
        elif isinstance(node, StructDef):
            content.append(f"struct:{node.name}")
            content.append(f"generics:{','.join(node.generic_params)}")
            content.append(f"fields:{len(node.fields)}")
            for field in node.fields:
                if hasattr(field, 'name'):
                    content.append(f"field:{field.name}:{self._type_to_str(getattr(field, 'type_annotation', None))}")
        
        elif isinstance(node, EnumDef):
            content.append(f"enum:{node.name}")
            content.append(f"variants:{len(node.variants)}")
            for variant in node.variants:
                content.append(f"variant:{variant.name}")
        
        elif isinstance(node, TypeAlias):
            content.append(f"alias:{node.name}")
            content.append(f"target:{self._node_to_hash(node.target)}")
        
        elif isinstance(node, ExceptionDef):
            content.append(f"exception:{node.name}")
            content.append(f"base:{self._type_to_str(node.base_type)}")
        
        elif isinstance(node, TraitDef):
            content.append(f"trait:{node.name}")
            content.append(f"methods:{len(node.methods)}")
        
        return hashlib.md5('|'.join(content).encode()).hexdigest()
    
    def _type_to_str(self, type_node: Any) -> str:
        """将类型节点转换为字符串"""
        if type_node is None:
            return "None"
        if hasattr(type_node, 'id'):
            return type_node.id
        if hasattr(type_node, 'value'):
            return str(type_node.value)
        return str(type_node)
    
    def _node_to_hash(self, node: Any) -> str:
        """将节点转换为哈希字符串"""
        if node is None:
            return "None"
        if isinstance(node, ASTNode):
            if hasattr(node, 'kind'):
                return f"{node.kind}:{hash(str(node))}"
            return f"{type(node).__name__}:{hash(str(node))}"
        return str(hash(str(node)))
    
    def _extract_definitions(self, ast: Any) -> Dict[str, Any]:
        """从 AST 中提取所有顶层定义"""
        definitions = {}
        
        if hasattr(ast, 'body'):
            for stmt in ast.body:
                if isinstance(stmt, (FuncDef, StructDef, EnumDef, TypeAlias, ExceptionDef, TraitDef)):
                    definitions[stmt.name] = stmt
        
        return definitions
    
    def compare(self, old_ast: Any, new_ast: Any) -> bool:
        """比较两个 AST，返回是否有变化"""
        old_defs = self._extract_definitions(old_ast)
        new_defs = self._extract_definitions(new_ast)
        
        old_names = set(old_defs.keys())
        new_names = set(new_defs.keys())
        
        # 新增的定义
        self.added_definitions = new_names - old_names
        # 删除的定义
        self.removed_definitions = old_names - new_names
        
        # 检查变化的定义
        for name in old_names & new_names:
            old_hash = self._compute_definition_hash(old_defs[name])
            new_hash = self._compute_definition_hash(new_defs[name])
            if old_hash != new_hash:
                self.changed_definitions.add(name)
        
        return len(self.changed_definitions) > 0 or len(self.added_definitions) > 0 or len(self.removed_definitions) > 0
    
    def get_changed_definitions(self) -> Set[str]:
        """获取所有变化的定义名称（包括新增和修改）"""
        return self.changed_definitions | self.added_definitions
    
    def get_removed_definitions(self) -> Set[str]:
        """获取所有删除的定义名称"""
        return self.removed_definitions
    
    def is_changed(self, name: str) -> bool:
        """检查指定名称的定义是否发生变化"""
        return name in self.changed_definitions or name in self.added_definitions
