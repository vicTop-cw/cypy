# div-tools - 可复用辅助工具
# 这些工具可以在多个项目中复用

from typing import List, Any, Optional


class ASTUtils:
    """AST 工具类 - 提供通用的 AST 操作方法"""
    
    @staticmethod
    def get_children(node: Any) -> List[Any]:
        """获取节点的所有子节点"""
        children = []
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if hasattr(value, 'kind'):
                    children.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if hasattr(item, 'kind'):
                            children.append(item)
        return children

    @staticmethod
    def walk(node: Any, callback: Any) -> None:
        """深度优先遍历 AST"""
        callback(node)
        for child in ASTUtils.get_children(node):
            ASTUtils.walk(child, callback)

    @staticmethod
    def collect_nodes(node: Any, kind: str) -> List[Any]:
        """收集所有指定类型的节点"""
        result = []
        def callback(n: Any) -> None:
            if hasattr(n, 'kind') and n.kind == kind:
                result.append(n)
        ASTUtils.walk(node, callback)
        return result

    @staticmethod
    def find_node(node: Any, kind: str) -> Optional[Any]:
        """查找第一个指定类型的节点"""
        if hasattr(node, 'kind') and node.kind == kind:
            return node
        for child in ASTUtils.get_children(node):
            found = ASTUtils.find_node(child, kind)
            if found:
                return found
        return None

    @staticmethod
    def count_nodes(node: Any) -> int:
        """计算 AST 节点总数"""
        count = 1
        for child in ASTUtils.get_children(node):
            count += ASTUtils.count_nodes(child)
        return count
