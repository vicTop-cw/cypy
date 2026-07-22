from typing import List, Any
from cypyc.parser.parser import ASTNode, Module, FuncDef, Param, LetStmt


class PointerChecker:
    def __init__(self):
        self.errors: List[str] = []
        self.pointer_vars: set = set()

    def check(self, node: ASTNode) -> None:
        self._visit(node)

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

    def _visit_FuncDef(self, node: FuncDef) -> None:
        for param in node.params:
            self._visit(param)
        for stmt in node.body:
            self._visit(stmt)

    def _visit_Param(self, node: Param) -> None:
        if node.is_ref:
            if not node.type_annotation:
                self.errors.append(f"Reference parameter '{node.name}' requires type annotation at {node.line}:{node.col}")

    def _visit_LetStmt(self, node: LetStmt) -> None:
        if node.value:
            self._visit(node.value)

    def _visit_Assign(self, node: Any) -> None:
        self._visit(node.target)
        self._visit(node.value)

    def _visit_Name(self, node: Any) -> None:
        pass

    def _visit_BinOp(self, node: Any) -> None:
        self._visit(node.left)
        self._visit(node.right)

    def _visit_UnaryOp(self, node: Any) -> None:
        self._visit(node.operand)

    def _visit_Call(self, node: Any) -> None:
        self._visit(node.func)
        for arg in node.args:
            self._visit(arg)
