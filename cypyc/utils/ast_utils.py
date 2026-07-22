from typing import List, Any
from cypyc.parser.parser import ASTNode


class ASTUtils:
    @staticmethod
    def get_children(node: ASTNode) -> List[ASTNode]:
        children = []
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    children.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            children.append(item)
        return children

    @staticmethod
    def walk(node: ASTNode, callback: Any) -> None:
        callback(node)
        for child in ASTUtils.get_children(node):
            ASTUtils.walk(child, callback)

    @staticmethod
    def collect_nodes(node: ASTNode, kind: str) -> List[ASTNode]:
        result = []
        def callback(n: ASTNode) -> None:
            if n.kind == kind:
                result.append(n)
        ASTUtils.walk(node, callback)
        return result

    @staticmethod
    def find_node(node: ASTNode, kind: str) -> ASTNode:
        if node.kind == kind:
            return node
        for child in ASTUtils.get_children(node):
            found = ASTUtils.find_node(child, kind)
            if found:
                return found
        return None

    @staticmethod
    def count_nodes(node: ASTNode) -> int:
        count = 1
        for child in ASTUtils.get_children(node):
            count += ASTUtils.count_nodes(child)
        return count

    @staticmethod
    def get_node_depth(node: ASTNode) -> int:
        depth = 0
        parent = getattr(node, "parent", None)
        while parent:
            depth += 1
            parent = getattr(parent, "parent", None)
        return depth
