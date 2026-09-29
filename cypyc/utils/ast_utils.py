from typing import List, Any
from cypyc.parser.parser import ASTNode


class ASTUtils:
    @staticmethod
    def is_positional_member(name: Any) -> bool:
        """名字能否占一个位置槽（SYNTAX/17-pattern-matching.md「位置模式的元数与槽位规则」规则 6）。

        `__`-包围的类属性（`__match_args__` 等）是给模式匹配用的元数据，不是数据字段；
        把它算进槽位数会让 `case Point(a, b, c)` 通过元数检查并生成 `.__match_args__ ==` 比较。
        分析器与生成器共用这一个判据，避免两侧各写一遍再漂移。
        """
        return isinstance(name, str) and not (name.startswith("__") and name.endswith("__"))

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
