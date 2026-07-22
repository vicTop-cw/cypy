from typing import List, Any
from cypyc.parser.parser import ASTNode, Module, FuncDef, DeferStmt, BreakStmt, ContinueStmt, ReturnStmt


class DeferAnalyzer:
    def __init__(self):
        self.errors: List[str] = []
        self.in_defer = False

    def analyze(self, node: ASTNode) -> None:
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
        for stmt in node.body:
            self._visit(stmt)

    def _visit_DeferStmt(self, node: DeferStmt) -> None:
        old_in_defer = self.in_defer
        self.in_defer = True
        for stmt in node.body:
            self._visit(stmt)
        self.in_defer = old_in_defer

    def _visit_BreakStmt(self, node: BreakStmt) -> None:
        if self.in_defer:
            self.errors.append(f"Cannot use 'break' inside defer block at {node.line}:{node.col}")

    def _visit_ContinueStmt(self, node: ContinueStmt) -> None:
        if self.in_defer:
            self.errors.append(f"Cannot use 'continue' inside defer block at {node.line}:{node.col}")

    def _visit_ReturnStmt(self, node: ReturnStmt) -> None:
        if self.in_defer:
            self.errors.append(f"Cannot use 'return' inside defer block at {node.line}:{node.col}")

    def _visit_IfStmt(self, node: Any) -> None:
        self._visit(node.test)
        for stmt in node.body:
            self._visit(stmt)
        if node.orelse:
            for stmt in node.orelse:
                self._visit(stmt)

    def _visit_ForStmt(self, node: Any) -> None:
        self._visit(node.target)
        self._visit(node.iter)
        for stmt in node.body:
            self._visit(stmt)

    def _visit_WhileStmt(self, node: Any) -> None:
        self._visit(node.test)
        for stmt in node.body:
            self._visit(stmt)
