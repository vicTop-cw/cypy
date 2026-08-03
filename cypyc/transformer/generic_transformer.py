"""
Generic 转换器

处理泛型定义的转换，包括：
- 注册泛型参数
- 处理类型约束
"""

from typing import List, Any
from cypyc.parser.parser import ASTNode


class GenericTransformer:
    """Generic 转换器"""
    
    def __init__(self):
        self.generic_defs: List[Any] = []
        self.errors: List[str] = []
    
    def transform(self, ast: ASTNode) -> ASTNode:
        """转换 AST，处理泛型定义
        
        Args:
            ast: AST 根节点
            
        Returns:
            转换后的 AST
        """
        self._collect_generics(ast)
        return ast
    
    def _collect_generics(self, node: ASTNode) -> None:
        """收集所有泛型定义
        
        Args:
            node: AST 节点
        """
        # 检查是否有类型参数
        if hasattr(node, 'type_params') and node.type_params:
            self.generic_defs.append(node)
        
        # 递归处理子节点
        for attr_name in dir(node):
            if attr_name.startswith('_') or attr_name in ('line', 'col', 'type_name'):
                continue
            try:
                value = getattr(node, attr_name)
                if isinstance(value, ASTNode):
                    self._collect_generics(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._collect_generics(item)
            except (AttributeError, TypeError):
                pass
