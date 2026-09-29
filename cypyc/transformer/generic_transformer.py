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
        # parser 给泛型节点（FuncDef/StructDef）用的属性名是 `generic_params`，
        # `type_params` 是 DuckDef 那一族的叫法 ⇒ 只读其中一个会静默漏收。
        params = getattr(node, 'generic_params', None) or getattr(node, 'type_params', None)
        if params:
            self.generic_defs.append(node)
        
        # 递归处理子节点
        for attr_name in dir(node):
            if attr_name.startswith('_') or attr_name in ('line', 'col', 'type_name'):
                continue
            try:
                value = getattr(node, attr_name)
            except (AttributeError, TypeError):
                continue
            if isinstance(value, ASTNode):
                self._collect_generics(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ASTNode):
                        self._collect_generics(item)
