from typing import Any, List
from cypyc.parser.parser import ASTNode, Module, TraitDef, ClassDef


class TraitTransformer:
    def __init__(self):
        self.traits: List[TraitDef] = []
        self.implementations: List[ClassDef] = []

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

    def _visit_TraitDef(self, node: TraitDef) -> None:
        self.traits.append(node)
        for method in node.methods:
            self._visit(method)

    def _visit_ClassDef(self, node: ClassDef) -> None:
        self.implementations.append(node)
        for stmt in node.body:
            self._visit(stmt)
