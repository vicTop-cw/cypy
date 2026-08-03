"""
Struct 转换器

处理 struct 定义的转换，包括：
- 注册 struct 类型
- 转换为内部表示
"""

from typing import List, Any
from cypyc.parser.parser import ASTNode, StructDef


class StructTransformer:
    """Struct 转换器"""
    
    def __init__(self):
        self.structs: List[StructDef] = []
        self.errors: List[str] = []
    
    def transform(self, ast: ASTNode) -> ASTNode:
        """转换 AST，处理 struct 定义
        
        Args:
            ast: AST 根节点
            
        Returns:
            转换后的 AST
        """
        self._collect_structs(ast)
        return ast
    
    def _collect_structs(self, node: ASTNode) -> None:
        """收集所有 struct 定义
        
        Args:
            node: AST 节点
        """
        if isinstance(node, StructDef):
            self.structs.append(node)
        
        # 递归处理子节点
        for attr_name in dir(node):
            if attr_name.startswith('_') or attr_name in ('line', 'col', 'type_name'):
                continue
            try:
                value = getattr(node, attr_name)
                if isinstance(value, ASTNode):
                    self._collect_structs(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._collect_structs(item)
            except (AttributeError, TypeError):
                pass
