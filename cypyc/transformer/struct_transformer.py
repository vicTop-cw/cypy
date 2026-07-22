from typing import Any, List
from cypyc.parser.parser import ASTNode, Module, StructDef


class StructTransformer:
    def __init__(self):
        self.structs: List[StructDef] = []

    def transform(self, node: ASTNode) -> ASTNode:
        self._visit(node)
        return node

    def _visit(self, node: ASTNode) -> None:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            getattr(self, method)(node)
        else:
            self._visit_children(node)

    def _visit_children(self, node: ASTNode) -> None:
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)

    def _visit_Module(self, node: Module) -> None:
        for stmt in node.body:
            self._visit(stmt)

    def _visit_StructDef(self, node: StructDef) -> None:
        self.structs.append(node)
        for field in node.fields:
            self._visit(field)
