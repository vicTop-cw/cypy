from typing import Iterator, List, Optional, Any
from .lexer import Token, TokenType


class ASTNode:
    def __init__(self, kind: str, line: int = 0, col: int = 0):
        self.kind = kind
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"{self.kind}(line={self.line}, col={self.col})"


class Module(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("Module", line, col)
        self.body = body


class Import(ASTNode):
    def __init__(self, module: str, alias: Optional[str] = None, line: int = 0, col: int = 0):
        super().__init__("Import", line, col)
        self.module = module
        self.alias = alias


class FromImport(ASTNode):
    def __init__(self, module: str, names: List[str], line: int = 0, col: int = 0):
        super().__init__("FromImport", line, col)
        self.module = module
        self.names = names


class StructDef(ASTNode):
    def __init__(self, name: str, fields: List[Any], line: int = 0, col: int = 0):
        super().__init__("StructDef", line, col)
        self.name = name
        self.fields = fields


class StructField(ASTNode):
    def __init__(self, name: str, type_annotation: Optional[Any], mutable: bool = False, line: int = 0, col: int = 0):
        super().__init__("StructField", line, col)
        self.name = name
        self.type_annotation = type_annotation
        self.mutable = mutable


class EnumDef(ASTNode):
    def __init__(self, name: str, variants: List[Any], line: int = 0, col: int = 0):
        super().__init__("EnumDef", line, col)
        self.name = name
        self.variants = variants


class EnumVariant(ASTNode):
    def __init__(self, name: str, value: Optional[Any] = None, line: int = 0, col: int = 0):
        super().__init__("EnumVariant", line, col)
        self.name = name
        self.value = value


class TraitDef(ASTNode):
    def __init__(self, name: str, methods: List[Any], line: int = 0, col: int = 0):
        super().__init__("TraitDef", line, col)
        self.name = name
        self.methods = methods


class FuncDef(ASTNode):
    def __init__(self, name: str, params: List[Any], return_type: Optional[Any], body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("FuncDef", line, col)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body


class Param(ASTNode):
    def __init__(self, name: str, type_annotation: Optional[Any], is_mut: bool = False, is_ref: bool = False, line: int = 0, col: int = 0):
        super().__init__("Param", line, col)
        self.name = name
        self.type_annotation = type_annotation
        self.is_mut = is_mut
        self.is_ref = is_ref


class ClassDef(ASTNode):
    def __init__(self, name: str, bases: List[Any], body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("ClassDef", line, col)
        self.name = name
        self.bases = bases
        self.body = body


class TypeAlias(ASTNode):
    def __init__(self, name: str, target: Any, line: int = 0, col: int = 0):
        super().__init__("TypeAlias", line, col)
        self.name = name
        self.target = target


class LetStmt(ASTNode):
    def __init__(self, name: str, type_annotation: Optional[Any], value: Optional[Any], mutable: bool = False, line: int = 0, col: int = 0):
        super().__init__("LetStmt", line, col)
        self.name = name
        self.type_annotation = type_annotation
        self.value = value
        self.mutable = mutable


class DeferStmt(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("DeferStmt", line, col)
        self.body = body


class ReturnStmt(ASTNode):
    def __init__(self, value: Optional[Any], line: int = 0, col: int = 0):
        super().__init__("ReturnStmt", line, col)
        self.value = value


class IfStmt(ASTNode):
    def __init__(self, test: Any, body: List[ASTNode], orelse: Optional[List[ASTNode]] = None, line: int = 0, col: int = 0):
        super().__init__("IfStmt", line, col)
        self.test = test
        self.body = body
        self.orelse = orelse


class ForStmt(ASTNode):
    def __init__(self, target: Any, iter: Any, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("ForStmt", line, col)
        self.target = target
        self.iter = iter
        self.body = body


class WhileStmt(ASTNode):
    def __init__(self, test: Any, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("WhileStmt", line, col)
        self.test = test
        self.body = body


class BreakStmt(ASTNode):
    def __init__(self, line: int = 0, col: int = 0):
        super().__init__("BreakStmt", line, col)


class ContinueStmt(ASTNode):
    def __init__(self, line: int = 0, col: int = 0):
        super().__init__("ContinueStmt", line, col)


class ExprStmt(ASTNode):
    def __init__(self, value: Any, line: int = 0, col: int = 0):
        super().__init__("ExprStmt", line, col)
        self.value = value


class Assign(ASTNode):
    def __init__(self, target: Any, value: Any, line: int = 0, col: int = 0):
        super().__init__("Assign", line, col)
        self.target = target
        self.value = value


class BinOp(ASTNode):
    def __init__(self, left: Any, op: str, right: Any, line: int = 0, col: int = 0):
        super().__init__("BinOp", line, col)
        self.left = left
        self.op = op
        self.right = right


class UnaryOp(ASTNode):
    def __init__(self, op: str, operand: Any, line: int = 0, col: int = 0):
        super().__init__("UnaryOp", line, col)
        self.op = op
        self.operand = operand


class Call(ASTNode):
    def __init__(self, func: Any, args: List[Any], line: int = 0, col: int = 0):
        super().__init__("Call", line, col)
        self.func = func
        self.args = args


class Attribute(ASTNode):
    def __init__(self, value: Any, attr: str, line: int = 0, col: int = 0):
        super().__init__("Attribute", line, col)
        self.value = value
        self.attr = attr


class Subscript(ASTNode):
    def __init__(self, value: Any, slice: Any, line: int = 0, col: int = 0):
        super().__init__("Subscript", line, col)
        self.value = value
        self.slice = slice


class Name(ASTNode):
    def __init__(self, id: str, line: int = 0, col: int = 0):
        super().__init__("Name", line, col)
        self.id = id


class Constant(ASTNode):
    def __init__(self, value: Any, line: int = 0, col: int = 0):
        super().__init__("Constant", line, col)
        self.value = value


class PointerType(ASTNode):
    def __init__(self, base_type: Any, line: int = 0, col: int = 0):
        super().__init__("PointerType", line, col)
        self.base_type = base_type


class DerefExpr(ASTNode):
    def __init__(self, operand: Any, line: int = 0, col: int = 0):
        super().__init__("DerefExpr", line, col)
        self.operand = operand


class GenericType(ASTNode):
    def __init__(self, name: str, args: List[Any], line: int = 0, col: int = 0):
        super().__init__("GenericType", line, col)
        self.name = name
        self.args = args


class ImplStmt(ASTNode):
    def __init__(self, trait_name: str, for_type: Any, methods: List[Any], line: int = 0, col: int = 0):
        super().__init__("ImplStmt", line, col)
        self.trait_name = trait_name
        self.for_type = for_type
        self.methods = methods


class MetaBlock(ASTNode):
    def __init__(self, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("MetaBlock", line, col)
        self.body = body


class BuildBlockExpr(ASTNode):
    """构建块表达式 - 闭包无参函数，内部默认unsafe"""
    BUILD_ASSIGN = "assign"    # =: 变量构建块
    BUILD_CALL = "call"        # ~: 调用构建块
    BUILD_GEN = "generator"    # *: 生成器调用构建块
    
    def __init__(self, block_type: str, body: List[ASTNode], line: int = 0, col: int = 0):
        super().__init__("BuildBlockExpr", line, col)
        self.block_type = block_type
        self.body = body


class BuildValueExpr(ASTNode):
    """构建值表达式 - 使用 ^ 符号获取构建值"""
    def __init__(self, operand: Any, line: int = 0, col: int = 0):
        super().__init__("BuildValueExpr", line, col)
        self.operand = operand


class ConstraintDef(ASTNode):
    def __init__(self, name: str, types: List[Any], line: int = 0, col: int = 0):
        super().__init__("ConstraintDef", line, col)
        self.name = name
        self.types = types


class SubtypeDecl(ASTNode):
    def __init__(self, subtype: str, supertype: str, line: int = 0, col: int = 0):
        super().__init__("SubtypeDecl", line, col)
        self.subtype = subtype
        self.supertype = supertype


class DispatchDecl(ASTNode):
    def __init__(self, func_name: str, params: List[Param], return_type: Optional[Any], line: int = 0, col: int = 0):
        super().__init__("DispatchDecl", line, col)
        self.func_name = func_name
        self.params = params
        self.return_type = return_type


class Parser:
    def __init__(self, tokens: Iterator[Token]):
        self.tokens = list(tokens)
        self.pos = 0
        self._scope_stack = []  # 作用域跟踪栈，记录当前嵌套深度和类型
        self._in_function = False  # 是否在函数内部（用于defer检查）
    
    def _push_scope(self, scope_type: str):
        """进入新的作用域"""
        self._scope_stack.append(scope_type)
        if scope_type in ('func', 'method'):
            self._in_function = True
    
    def _pop_scope(self):
        """退出当前作用域"""
        if self._scope_stack:
            scope_type = self._scope_stack.pop()
            if scope_type in ('func', 'method') and not any(s in ('func', 'method') for s in self._scope_stack):
                self._in_function = False
    
    def _is_module_level(self) -> bool:
        """检查是否在模块顶级"""
        return len(self._scope_stack) == 0
    
    def _require_module_level(self, construct_name: str, token: Token):
        """要求必须在模块顶级，否则抛出错误"""
        if not self._is_module_level():
            raise ValueError(f"{construct_name} must be defined at module level, found at {token.line}:{token.col}")
    
    def _require_function_scope(self, construct_name: str, token: Token):
        """要求必须在函数内部，否则抛出错误"""
        if not self._in_function:
            raise ValueError(f"{construct_name} must be used inside a function, found at {token.line}:{token.col}")

    def _current(self) -> Token:
        if self.pos >= len(self.tokens):
            return Token(TokenType.EOF, "", 0, 0)
        return self.tokens[self.pos]

    def _peek(self) -> Optional[Token]:
        if self.pos + 1 < len(self.tokens):
            return self.tokens[self.pos + 1]
        return None

    def _consume(self, expected_type: Optional[str] = None) -> Token:
        token = self._current()
        if expected_type and token.type != expected_type:
            raise ValueError(f"Expected {expected_type}, got {token.type} at {token.line}:{token.col}")
        self.pos += 1
        return token

    def _expect(self, expected_type: str) -> Token:
        token = self._consume(expected_type)
        return token

    def parse(self) -> Module:
        body = []
        while self._current().type != TokenType.EOF:
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        return Module(body)

    def _parse_statement(self) -> Optional[ASTNode]:
        token = self._current()
        if token.type == TokenType.NEWLINE:
            self._consume()
            return None
        if token.type == TokenType.INDENT:
            self._consume()
            return None
        if token.type == TokenType.DEDENT:
            self._consume()
            return None

        if token.type == TokenType.DEF:
            return self._parse_func_def()
        if token.type == TokenType.CLASS:
            return self._parse_class_def()
        if token.type == TokenType.STRUCT:
            return self._parse_struct_def()
        if token.type == TokenType.ENUM:
            return self._parse_enum_def()
        if token.type == TokenType.TRAIT:
            return self._parse_trait_def()
        if token.type == TokenType.IMPL:
            return self._parse_impl_stmt()
        if token.type == TokenType.LET:
            return self._parse_let_stmt()
        if token.type == TokenType.VAR:
            return self._parse_var_stmt()
        if token.type == TokenType.VAL:
            return self._parse_val_stmt()
        if token.type == TokenType.IDENTIFIER:
            peek_token = self._peek()
            if peek_token and peek_token.type == TokenType.COLON:
                return self._parse_typed_var()
        if token.type == TokenType.META:
            return self._parse_meta_block()
        if token.type == TokenType.RETURN:
            return self._parse_return_stmt()
        if token.type == TokenType.IF:
            return self._parse_if_stmt()
        if token.type == TokenType.FOR:
            return self._parse_for_stmt()
        if token.type == TokenType.WHILE:
            return self._parse_while_stmt()
        if token.type == TokenType.BREAK:
            return self._parse_break_stmt()
        if token.type == TokenType.CONTINUE:
            return self._parse_continue_stmt()
        if token.type == TokenType.DEFER:
            return self._parse_defer_stmt()
        if token.type == TokenType.IMPORT:
            return self._parse_import()
        if token.type == TokenType.FROM:
            return self._parse_from_import()
        if token.type == TokenType.TYPE:
            return self._parse_type_alias()

        return self._parse_expr_stmt()

    def _parse_func_def(self) -> FuncDef:
        self._consume(TokenType.DEF)
        name_token = self._consume(TokenType.IDENTIFIER)
        
        generic_params = []
        if self._current().type == TokenType.LBRACKET:
            self._consume()
            while self._current().type != TokenType.RBRACKET:
                generic_params.append(self._consume(TokenType.IDENTIFIER).value)
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        self._expect(TokenType.LPAREN)
        params = self._parse_params()
        self._expect(TokenType.RPAREN)
        return_type = None
        if self._current().type == TokenType.ARROW:
            self._consume()
            return_type = self._parse_type()
        self._expect(TokenType.COLON)
        self._push_scope("func")
        body = self._parse_block()
        self._pop_scope()
        return FuncDef(name_token.value, params, return_type, body, name_token.line, name_token.col)

    def _parse_params(self) -> List[Param]:
        params = []
        if self._current().type != TokenType.RPAREN:
            while True:
                is_mut = False
                is_ref = False
                if self._current().type == TokenType.MUT:
                    is_mut = True
                    self._consume()
                if self._current().type == TokenType.REF:
                    is_ref = True
                    self._consume()
                name_token = self._consume(TokenType.IDENTIFIER)
                type_annotation = None
                if self._current().type == TokenType.COLON:
                    self._consume()
                    type_annotation = self._parse_type()
                params.append(Param(name_token.value, type_annotation, is_mut, is_ref, name_token.line, name_token.col))
                if self._current().type != TokenType.COMMA:
                    break
                self._consume()
        return params

    def _parse_class_def(self) -> ClassDef:
        self._consume(TokenType.CLASS)
        name_token = self._consume(TokenType.IDENTIFIER)
        bases = []
        if self._current().type == TokenType.EXTENDS:
            self._consume()
            bases = self._parse_type_list()
        if self._current().type == TokenType.IMPLEMENTS:
            self._consume()
            bases.extend(self._parse_type_list())
        self._expect(TokenType.COLON)
        self._push_scope("class")
        body = self._parse_block()
        self._pop_scope()
        return ClassDef(name_token.value, bases, body, name_token.line, name_token.col)

    def _parse_struct_def(self) -> StructDef:
        self._consume(TokenType.STRUCT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("struct", name_token)
        
        generic_params = []
        if self._current().type == TokenType.LBRACKET:
            self._consume()
            if self._current().type == TokenType.RBRACKET:
                raise ValueError(f"Generic parameter list cannot be empty at {name_token.line}:{name_token.col}")
            while self._current().type != TokenType.RBRACKET:
                generic_params.append(self._consume(TokenType.IDENTIFIER).value)
                if self._current().type == TokenType.COMMA:
                    self._consume()
            self._consume()
        
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        fields = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            field_name_token = self._consume(TokenType.IDENTIFIER)
            type_annotation = None
            if self._current().type == TokenType.COLON:
                self._consume()
                type_annotation = self._parse_type()
            fields.append(StructField(field_name_token.value, type_annotation, False, field_name_token.line, field_name_token.col))
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return StructDef(name_token.value, fields, name_token.line, name_token.col)

    def _parse_enum_def(self) -> EnumDef:
        self._consume(TokenType.ENUM)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("enum", name_token)
        self._expect(TokenType.COLON)
        self._expect(TokenType.INDENT)
        variants = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            if self._current().type == TokenType.NEWLINE:
                self._consume()
                continue
            variant_name_token = self._consume(TokenType.IDENTIFIER)
            value = None
            if self._current().type == TokenType.ASSIGN:
                self._consume()
                value = self._parse_expression()
            variants.append(EnumVariant(variant_name_token.value, value, variant_name_token.line, variant_name_token.col))
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return EnumDef(name_token.value, variants, name_token.line, name_token.col)

    def _parse_trait_def(self) -> TraitDef:
        self._consume(TokenType.TRAIT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("trait", name_token)
        self._expect(TokenType.COLON)
        methods = self._parse_block()
        return TraitDef(name_token.value, methods, name_token.line, name_token.col)

    def _parse_let_stmt(self) -> LetStmt:
        self._consume(TokenType.LET)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        self._expect(TokenType.NEWLINE)
        # let 声明的是可变变量
        return LetStmt(name_token.value, type_annotation, value, True, name_token.line, name_token.col)

    def _parse_var_stmt(self) -> LetStmt:
        self._consume(TokenType.VAR)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        self._expect(TokenType.NEWLINE)
        return LetStmt(name_token.value, type_annotation, value, True, name_token.line, name_token.col)

    def _parse_val_stmt(self) -> LetStmt:
        self._consume(TokenType.VAL)
        name_token = self._consume(TokenType.IDENTIFIER)
        type_annotation = None
        if self._current().type == TokenType.COLON:
            self._consume()
            type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return LetStmt(name_token.value, type_annotation, value, False, name_token.line, name_token.col)

    def _parse_typed_var(self) -> LetStmt:
        name_token = self._consume(TokenType.IDENTIFIER)
        self._consume(TokenType.COLON)
        type_annotation = self._parse_type()
        value = None
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return LetStmt(name_token.value, type_annotation, value, True, name_token.line, name_token.col)

    def _parse_return_stmt(self) -> ReturnStmt:
        self._consume(TokenType.RETURN)
        value = None
        if self._current().type not in (TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            value = self._parse_expression()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ReturnStmt(value, self._current().line, self._current().col)

    def _parse_if_stmt(self) -> IfStmt:
        self._consume(TokenType.IF)
        test = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("if")
        body = self._parse_block()
        self._pop_scope()
        orelse = None
        if self._current().type == TokenType.ELIF:
            orelse = [self._parse_if_stmt()]
        elif self._current().type == TokenType.ELSE:
            self._consume()
            self._expect(TokenType.COLON)
            self._push_scope("if")
            orelse = self._parse_block()
            self._pop_scope()
        return IfStmt(test, body, orelse, self._current().line, self._current().col)

    def _parse_for_stmt(self) -> ForStmt:
        self._consume(TokenType.FOR)
        target = self._parse_expression()
        self._expect(TokenType.IN)
        iter = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("for")
        body = self._parse_block()
        self._pop_scope()
        return ForStmt(target, iter, body, self._current().line, self._current().col)

    def _parse_while_stmt(self) -> WhileStmt:
        self._consume(TokenType.WHILE)
        test = self._parse_expression()
        self._expect(TokenType.COLON)
        self._push_scope("while")
        body = self._parse_block()
        self._pop_scope()
        return WhileStmt(test, body, self._current().line, self._current().col)

    def _parse_break_stmt(self) -> BreakStmt:
        self._consume(TokenType.BREAK)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return BreakStmt()

    def _parse_continue_stmt(self) -> ContinueStmt:
        self._consume(TokenType.CONTINUE)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ContinueStmt()

    def _parse_defer_stmt(self) -> DeferStmt:
        self._consume(TokenType.DEFER)
        self._require_function_scope("defer", self._current())
        
        # 支持两种形式：
        # 1. defer free(ptr)  - 单行形式
        # 2. defer:          - 块形式
        #       free(ptr)
        if self._current().type == TokenType.COLON:
            self._consume()
            body = self._parse_block()
        else:
            # 单行形式：解析表达式直到换行
            expr = self._parse_expression()
            body = [expr]
            # 消费换行符
            if self._current().type == TokenType.NEWLINE:
                self._consume()
        
        return DeferStmt(body, self._current().line, self._current().col)

    def _parse_impl_stmt(self) -> ImplStmt:
        self._consume(TokenType.IMPL)
        trait_name_token = self._consume(TokenType.IDENTIFIER)
        self._require_module_level("impl", trait_name_token)
        if self._current().type == TokenType.FOR_KW or self._current().type == TokenType.FOR:
            self._consume()
        for_type = self._parse_type()
        self._expect(TokenType.COLON)
        methods = self._parse_block()
        return ImplStmt(trait_name_token.value, for_type, methods, trait_name_token.line, trait_name_token.col)

    def _parse_meta_block(self) -> MetaBlock:
        self._consume(TokenType.META)
        self._require_module_level("meta", self._current())
        self._expect(TokenType.COLON)
        body = []
        self._expect(TokenType.INDENT)
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            token = self._current()
            if token.type == TokenType.CONSTRAINT:
                body.append(self._parse_constraint())
            elif token.type == TokenType.SUBTYPE_KW:
                body.append(self._parse_subtype())
            elif token.type == TokenType.DISPATCH:
                body.append(self._parse_dispatch())
            elif token.type == TokenType.ABSTRACT:
                body.append(self._parse_abstract())
            elif token.type == TokenType.NEWLINE:
                self._consume()
            else:
                raise ValueError(f"Unexpected token {token.type} in meta block at {token.line}:{token.col}")
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return MetaBlock(body, 0, 0)

    def _parse_constraint(self) -> ConstraintDef:
        self._consume(TokenType.CONSTRAINT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._expect(TokenType.ASSIGN)
        types = []
        while True:
            types.append(self._parse_type())
            if self._current().type == TokenType.PIPE:
                self._consume()
            else:
                break
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ConstraintDef(name_token.value, types, name_token.line, name_token.col)

    def _parse_subtype(self) -> SubtypeDecl:
        self._consume(TokenType.SUBTYPE_KW)
        subtype_token = self._consume(TokenType.IDENTIFIER)
        self._expect(TokenType.SUBTYPE)
        supertype_token = self._consume(TokenType.IDENTIFIER)
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return SubtypeDecl(subtype_token.value, supertype_token.value, subtype_token.line, subtype_token.col)

    def _parse_dispatch(self) -> DispatchDecl:
        self._consume(TokenType.DISPATCH)
        func_name_token = self._consume(TokenType.IDENTIFIER)
        self._expect(TokenType.LPAREN)
        params = self._parse_params()
        self._expect(TokenType.RPAREN)
        return_type = None
        if self._current().type == TokenType.ARROW:
            self._consume()
            return_type = self._parse_type()
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return DispatchDecl(func_name_token.value, params, return_type, func_name_token.line, func_name_token.col)

    def _parse_abstract(self) -> ASTNode:
        self._consume(TokenType.ABSTRACT)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._expect(TokenType.NEWLINE)
        return Name(name_token.value, name_token.line, name_token.col)

    def _parse_import(self) -> Import:
        self._consume(TokenType.IMPORT)
        module = self._parse_identifier()
        alias = None
        if self._current().type == TokenType.AS:
            self._consume()
            alias = self._parse_identifier()
        self._expect(TokenType.NEWLINE)
        return Import(module, alias, self._current().line, self._current().col)

    def _parse_from_import(self) -> FromImport:
        self._consume(TokenType.FROM)
        module = self._parse_identifier()
        self._expect(TokenType.IMPORT)
        names = []
        while self._current().type == TokenType.IDENTIFIER:
            names.append(self._consume().value)
            if self._current().type == TokenType.COMMA:
                self._consume()
            else:
                break
        self._expect(TokenType.NEWLINE)
        return FromImport(module, names, self._current().line, self._current().col)

    def _parse_type_alias(self) -> TypeAlias:
        self._consume(TokenType.TYPE)
        name_token = self._consume(TokenType.IDENTIFIER)
        self._expect(TokenType.EQ)
        target = self._parse_type()
        self._expect(TokenType.NEWLINE)
        return TypeAlias(name_token.value, target, name_token.line, name_token.col)

    def _parse_expr_stmt(self) -> ASTNode:
        value = self._parse_expression()
        if self._current().type == TokenType.ASSIGN:
            self._consume()
            right_value = self._parse_expression()
            # 允许 Name 和 DerefExpr 作为赋值目标
            if isinstance(value, (Name, DerefExpr)):
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                return Assign(value, right_value, value.line, value.col)
        # 处理复合赋值 (+=, -=, *=, /=)
        compound_ops = {
            TokenType.PLUS_ASSIGN: "+",
            TokenType.MINUS_ASSIGN: "-",
            TokenType.MUL_ASSIGN: "*",
            TokenType.DIV_ASSIGN: "/",
        }
        if self._current().type in compound_ops:
            op = compound_ops[self._current().type]
            self._consume()
            right_value = self._parse_expression()
            if isinstance(value, Name):
                if self._current().type == TokenType.NEWLINE:
                    self._consume()
                return Assign(value, BinOp(value, op, right_value), value.line, value.col)
        # 处理变量构建块 =:
        if self._current().type == TokenType.BUILD_ASSIGN:
            self._consume()
            if isinstance(value, Name):
                build_block = self._parse_build_block(BuildBlockExpr.BUILD_ASSIGN)
                return Assign(value, build_block, value.line, value.col)
            else:
                raise ValueError(f"Left side of =: must be a variable name at {self._current().line}:{self._current().col}")
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        return ExprStmt(value, value.line, value.col)

    def _parse_expression(self) -> ASTNode:
        return self._parse_or_expr()

    def _parse_or_expr(self) -> ASTNode:
        left = self._parse_and_expr()
        while self._current().type == TokenType.OR:
            op = self._consume().value
            right = self._parse_and_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_and_expr(self) -> ASTNode:
        left = self._parse_not_expr()
        while self._current().type == TokenType.AND:
            op = self._consume().value
            right = self._parse_not_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_not_expr(self) -> ASTNode:
        if self._current().type == TokenType.NOT:
            op = self._consume().value
            operand = self._parse_not_expr()
            return UnaryOp(op, operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_bitwise_or()
        while self._current().type in (TokenType.EQ, TokenType.NE, TokenType.LT, TokenType.LE, TokenType.GT, TokenType.GE):
            op = self._consume().value
            right = self._parse_bitwise_or()
            left = BinOp(left, op, right)
        return left

    def _parse_bitwise_or(self) -> ASTNode:
        left = self._parse_bitwise_and()
        while self._current().type == TokenType.PIPE:
            op = self._consume().value
            right = self._parse_bitwise_and()
            left = BinOp(left, op, right)
        return left

    def _parse_bitwise_and(self) -> ASTNode:
        left = self._parse_shift_expr()
        while self._current().type == TokenType.AND:
            op = self._consume().value
            right = self._parse_shift_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_shift_expr(self) -> ASTNode:
        return self._parse_pipeline_expr()

    def _parse_pipeline_expr(self) -> ASTNode:
        left = self._parse_additive_expr()
        while self._current().type == TokenType.PIPE_GT:
            self._consume()
            right = self._parse_call()
            left = Call(right, [left])
        return left

    def _parse_additive_expr(self) -> ASTNode:
        left = self._parse_multiplicative_expr()
        while self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._consume().value
            right = self._parse_multiplicative_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_multiplicative_expr(self) -> ASTNode:
        left = self._parse_unary_expr()
        while self._current().type in (TokenType.MUL, TokenType.DIV, TokenType.MOD):
            op = self._consume().value
            right = self._parse_unary_expr()
            left = BinOp(left, op, right)
        return left

    def _parse_unary_expr(self) -> ASTNode:
        if self._current().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._consume().value
            operand = self._parse_unary_expr()
            return UnaryOp(op, operand)
        if self._current().type == TokenType.DEREF:
            self._consume()
            operand = self._parse_unary_expr()
            return DerefExpr(operand)
        return self._parse_power_expr()

    def _parse_power_expr(self) -> ASTNode:
        base = self._parse_call()
        # 处理后缀构建值操作符 ^
        while self._current().type == TokenType.BUILD_VALUE:
            self._consume()
            base = BuildValueExpr(base)
        while self._current().type == TokenType.POW:
            op = self._consume().value
            exp = self._parse_unary_expr()
            base = BinOp(base, op, exp)
        return base

    def _parse_call(self) -> ASTNode:
        func = self._parse_primary()
        while self._current().type == TokenType.LPAREN:
            self._consume()
            args = []
            if self._current().type != TokenType.RPAREN:
                while True:
                    args.append(self._parse_expression())
                    if self._current().type != TokenType.COMMA:
                        break
                    self._consume()
            self._expect(TokenType.RPAREN)
            func = Call(func, args)
        
        # 处理调用构建块 ~: 和生成器调用构建块 *:
        if self._current().type == TokenType.BUILD_CALL:
            self._consume()
            build_block = self._parse_build_block(BuildBlockExpr.BUILD_CALL)
            return Call(func, [build_block])
        if self._current().type == TokenType.BUILD_GEN:
            self._consume()
            build_block = self._parse_build_block(BuildBlockExpr.BUILD_GEN)
            return Call(func, [build_block])
        
        return func

    def _parse_primary(self) -> ASTNode:
        token = self._current()
        if token.type == TokenType.INTEGER:
            self._consume()
            return Constant(int(token.value), token.line, token.col)
        if token.type == TokenType.FLOAT:
            self._consume()
            return Constant(float(token.value), token.line, token.col)
        if token.type == TokenType.STRING:
            self._consume()
            return Constant(token.value, token.line, token.col)
        if token.type == TokenType.IDENTIFIER:
            self._consume()
            return Name(token.value, token.line, token.col)
        if token.type == TokenType.NEVER:
            self._consume()
            return Name("Never", token.line, token.col)
        if token.type == TokenType.LPAREN:
            self._consume()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return expr
        if token.type == TokenType.LBRACKET:
            self._consume()
            elements = []
            if self._current().type != TokenType.RBRACKET:
                while True:
                    elements.append(self._parse_expression())
                    if self._current().type != TokenType.COMMA:
                        break
                    self._consume()
            self._expect(TokenType.RBRACKET)
            return Constant(elements, token.line, token.col)
        raise ValueError(f"Unexpected token {token.type} at {token.line}:{token.col}")

    def _parse_type(self) -> ASTNode:
        base = self._parse_primary()
        while self._current().type == TokenType.MUL:
            self._consume()
            base = PointerType(base, base.line, base.col)
        if self._current().type == TokenType.LBRACKET:
            self._consume()
            args = []
            if self._current().type != TokenType.RBRACKET:
                while True:
                    args.append(self._parse_type())
                    if self._current().type == TokenType.COMMA:
                        self._consume()
                    else:
                        break
            else:
                raise ValueError(f"Generic type parameter list cannot be empty at {base.line}:{base.col}")
            self._expect(TokenType.RBRACKET)
            if isinstance(base, Name):
                return GenericType(base.id, args, base.line, base.col)
            else:
                raise ValueError(f"Generic type must be a name at {base.line}:{base.col}")
        return base

    def _parse_type_list(self) -> List[ASTNode]:
        types = []
        while self._current().type == TokenType.IDENTIFIER:
            types.append(self._parse_type())
            if self._current().type == TokenType.COMMA:
                self._consume()
            else:
                break
        return types

    def _parse_block(self) -> List[ASTNode]:
        self._expect(TokenType.INDENT)
        body = []
        while self._current().type not in (TokenType.DEDENT, TokenType.EOF):
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        if self._current().type == TokenType.DEDENT:
            self._consume()
        return body

    def _parse_build_block(self, block_type: str) -> BuildBlockExpr:
        """解析构建块体 - 内部默认unsafe，允许指针语法"""
        # 构建块后面必须换行并缩进
        if self._current().type == TokenType.NEWLINE:
            self._consume()
        body = self._parse_block()
        return BuildBlockExpr(block_type, body, self._current().line, self._current().col)

    def _parse_identifier(self) -> str:
        token = self._consume(TokenType.IDENTIFIER)
        return token.value
