"""
Trait 转换器

处理 trait 定义和实现的转换，包括：
- 注册 trait 定义
- 处理 impl 块
"""

from typing import List, Any
from cypyc.parser.parser import ASTNode


class TraitTransformer:
    """Trait 转换器"""
    
    def __init__(self):
        self.traits: List[Any] = []
        self.impl_blocks: List[Any] = []
        self.errors: List[str] = []
    
    def transform(self, ast: ASTNode) -> ASTNode:
        """转换 AST，处理 trait 定义
        
        Args:
            ast: AST 根节点
            
        Returns:
            转换后的 AST
        """
        self._collect_traits(ast)
        return ast
    
    def _collect_traits(self, node: ASTNode) -> None:
        """收集所有 trait 定义和 impl 块
        
        Args:
            node: AST 节点
        """
        class_name = node.__class__.__name__
        if 'Trait' in class_name:
            self.traits.append(node)
        elif 'Impl' in class_name:
            self.impl_blocks.append(node)
        
        # 递归处理子节点
        for attr_name in dir(node):
            if attr_name.startswith('_') or attr_name in ('line', 'col', 'type_name'):
                continue
            try:
                value = getattr(node, attr_name)
            except (AttributeError, TypeError):
                continue
            if isinstance(value, ASTNode):
                self._collect_traits(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ASTNode):
                        self._collect_traits(item)
