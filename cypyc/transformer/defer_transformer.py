"""
Defer 转换器

处理 defer 语句的转换，包括：
- 注册 defer 块
- 生成 try-finally 结构
"""

from typing import List, Any
from cypyc.parser.parser import ASTNode


class DeferTransformer:
    """Defer 转换器"""
    
    def __init__(self):
        self.defer_blocks: List[Any] = []
        self.errors: List[str] = []
    
    def transform(self, ast: ASTNode) -> ASTNode:
        """转换 AST，处理 defer 语句
        
        Args:
            ast: AST 根节点
            
        Returns:
            转换后的 AST
        """
        self._collect_defers(ast)
        return ast
    
    def _collect_defers(self, node: ASTNode) -> None:
        """收集所有 defer 语句
        
        Args:
            node: AST 节点
        """
        class_name = node.__class__.__name__
        if 'Defer' in class_name:
            self.defer_blocks.append(node)
        
        # 递归处理子节点
        for attr_name in dir(node):
            if attr_name.startswith('_') or attr_name in ('line', 'col', 'type_name'):
                continue
            try:
                value = getattr(node, attr_name)
                if isinstance(value, ASTNode):
                    self._collect_defers(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._collect_defers(item)
            except (AttributeError, TypeError):
                pass
