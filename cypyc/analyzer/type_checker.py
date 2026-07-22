from typing import Dict, List, Any, Optional
from cypyc.parser.parser import ASTNode, Module, FuncDef, LetStmt, ReturnStmt, BinOp, UnaryOp, Call, Name, Constant


class Type:
    def __init__(self, name: str, is_pointer: bool = False, is_ref: bool = False):
        self.name = name
        self.is_pointer = is_pointer
        self.is_ref = is_ref

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Type):
            return False
        return (self.name == other.name and
                self.is_pointer == other.is_pointer and
                self.is_ref == other.is_ref)

    def __repr__(self) -> str:
        prefix = ""
        if self.is_ref:
            prefix = "ref "
        if self.is_pointer:
            prefix = "*"
        return f"{prefix}{self.name}"


class TypeChecker:
    def __init__(self):
        self.type_map: Dict[str, Type] = {
            "int": Type("int"),
            "float": Type("float"),
            "str": Type("str"),
            "bool": Type("bool"),
            "None": Type("None"),
        }
        self.current_function_return_type: Optional[Type] = None
        self.errors: List[str] = []

    def check(self, node: ASTNode) -> None:
        self._visit(node)

    def _visit(self, node: ASTNode) -> Optional[Type]:
        method = f"_visit_{node.kind}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        return self._visit_children(node)

    def _visit_children(self, node: ASTNode) -> Optional[Type]:
        for attr in dir(node):
            if not attr.startswith("_"):
                value = getattr(node, attr)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)
        return None

    def _visit_Module(self, node: Module) -> None:
        for stmt in node.body:
            self._visit(stmt)

    def _visit_FuncDef(self, node: FuncDef) -> None:
        old_return_type = self.current_function_return_type
        self.current_function_return_type = self._get_type_from_node(node.return_type)

        for param in node.params:
            param_type = self._get_type_from_node(param.type_annotation)
            if param_type:
                self.type_map[param.name] = param_type

        for stmt in node.body:
            self._visit(stmt)

        self.current_function_return_type = old_return_type

    def _visit_LetStmt(self, node: LetStmt) -> None:
        declared_type = self._get_type_from_node(node.type_annotation)
        if node.value:
            value_type = self._visit(node.value)
            if declared_type and value_type and declared_type != value_type:
                self.errors.append(f"Type mismatch: expected {declared_type}, got {value_type} at {node.line}:{node.col}")
            elif not declared_type and value_type:
                self.type_map[node.name] = value_type

    def _visit_ReturnStmt(self, node: ReturnStmt) -> Optional[Type]:
        if node.value:
            value_type = self._visit(node.value)
            if self.current_function_return_type and value_type:
                if self.current_function_return_type != value_type:
                    self.errors.append(f"Return type mismatch: expected {self.current_function_return_type}, got {value_type} at {node.line}:{node.col}")
            return value_type
        return Type("None")

    def _visit_BinOp(self, node: BinOp) -> Optional[Type]:
        left_type = self._visit(node.left)
        right_type = self._visit(node.right)

        if left_type and right_type and left_type != right_type:
            self.errors.append(f"Type mismatch in binary operation: {left_type} {node.op} {right_type} at {node.line}:{node.col}")

        return left_type

    def _visit_UnaryOp(self, node: UnaryOp) -> Optional[Type]:
        return self._visit(node.operand)

    def _visit_Call(self, node: Call) -> Optional[Type]:
        self._visit(node.func)
        for arg in node.args:
            self._visit(arg)
        return Type("None")

    def _visit_Name(self, node: Name) -> Optional[Type]:
        if node.id in self.type_map:
            return self.type_map[node.id]
        return None

    def _visit_Constant(self, node: Constant) -> Optional[Type]:
        if isinstance(node.value, int):
            return Type("int")
        if isinstance(node.value, float):
            return Type("float")
        if isinstance(node.value, str):
            return Type("str")
        if isinstance(node.value, bool):
            return Type("bool")
        return None

    def _get_type_from_node(self, node: Optional[ASTNode]) -> Optional[Type]:
        if node is None:
            return None
        if isinstance(node, Name):
            if node.id in self.type_map:
                return self.type_map[node.id]
            return Type(node.id)
        return None
