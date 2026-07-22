import re
from typing import Iterator, Tuple, Optional


class TokenType:
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"

    IDENTIFIER = "IDENTIFIER"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"

    PLUS = "PLUS"
    MINUS = "MINUS"
    MUL = "MUL"
    DIV = "DIV"
    MOD = "MOD"
    POW = "POW"

    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    SUBTYPE = "SUBTYPE"

    ASSIGN = "ASSIGN"
    PLUS_ASSIGN = "PLUS_ASSIGN"
    MINUS_ASSIGN = "MINUS_ASSIGN"
    MUL_ASSIGN = "MUL_ASSIGN"
    DIV_ASSIGN = "DIV_ASSIGN"

    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    DEREF = "DEREF"
    PIPE = "PIPE"
    PIPE_GT = "PIPE_GT"

    DOT = "DOT"
    COMMA = "COMMA"
    COLON = "COLON"
    SEMICOLON = "SEMICOLON"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    AT = "AT"
    ARROW = "ARROW"
    BUILD_ASSIGN = "BUILD_ASSIGN"  # =:
    BUILD_CALL = "BUILD_CALL"      # ~:
    BUILD_GEN = "BUILD_GEN"        # *:
    BUILD_VALUE = "BUILD_VALUE"    # ^
    TILDE = "TILDE"                # ~

    IF = "IF"
    ELIF = "ELIF"
    ELSE = "ELSE"
    FOR = "FOR"
    WHILE = "WHILE"
    BREAK = "BREAK"
    CONTINUE = "CONTINUE"
    RETURN = "RETURN"
    DEF = "DEF"
    CLASS = "CLASS"
    STRUCT = "STRUCT"
    ENUM = "ENUM"
    TRAIT = "TRAIT"
    IMPL = "IMPL"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    IMPORT = "IMPORT"
    FROM = "FROM"
    AS = "AS"
    TYPE = "TYPE"
    VAR = "VAR"
    LET = "LET"
    VAL = "VAL"
    CONST = "CONST"
    DEFER = "DEFER"
    POINTER = "POINTER"
    REF = "REF"
    MUT = "MUT"
    IS = "IS"
    IN = "IN"
    FOR_KW = "FOR_KW"
    META = "META"
    CONSTRAINT = "CONSTRAINT"
    ABSTRACT = "ABSTRACT"
    SUBTYPE_KW = "SUBTYPE_KW"
    DISPATCH = "DISPATCH"
    NEVER = "NEVER"


class Token:
    def __init__(self, type: str, value: str, line: int, col: int):
        self.type = type
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"Token({self.type}, {repr(self.value)}, {self.line}:{self.col})"


class Lexer:
    KEYWORDS = {
        "if": TokenType.IF,
        "elif": TokenType.ELIF,
        "else": TokenType.ELSE,
        "for": TokenType.FOR,
        "while": TokenType.WHILE,
        "break": TokenType.BREAK,
        "continue": TokenType.CONTINUE,
        "return": TokenType.RETURN,
        "def": TokenType.DEF,
        "class": TokenType.CLASS,
        "struct": TokenType.STRUCT,
        "enum": TokenType.ENUM,
        "trait": TokenType.TRAIT,
        "impl": TokenType.IMPL,
        "implements": TokenType.IMPLEMENTS,
        "extends": TokenType.EXTENDS,
        "import": TokenType.IMPORT,
        "from": TokenType.FROM,
        "as": TokenType.AS,
        "type": TokenType.TYPE,
        "var": TokenType.VAR,
        "let": TokenType.LET,
        "val": TokenType.VAL,
        "const": TokenType.CONST,
        "defer": TokenType.DEFER,
        "pointer": TokenType.POINTER,
        "ref": TokenType.REF,
        "mut": TokenType.MUT,
        "is": TokenType.IS,
        "in": TokenType.IN,
        "meta": TokenType.META,
        "constraint": TokenType.CONSTRAINT,
        "abstract": TokenType.ABSTRACT,
        "subtype": TokenType.SUBTYPE_KW,
        "dispatch": TokenType.DISPATCH,
        "Never": TokenType.NEVER,
    }

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.indent_stack = [0]
        self._expect_indent = False  # 标记是否期望下一行增加缩进
        self._in_type_annotation = False  # 标记是否在箭头后的类型注解中
        self._indent_type = None  # 记录当前使用的缩进类型：'spaces' 或 'tabs'

    def _peek(self) -> Optional[str]:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]

    def _advance(self) -> str:
        char = self.source[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return char

    def _skip_whitespace(self) -> None:
        while self._peek() in " \t":
            self._advance()

    def _skip_comment(self) -> None:
        if self._peek() == "#":
            while self._peek() is not None and self._peek() != "\n":
                self._advance()

    def _tokenize_string(self) -> str:
        quote = self._advance()
        result = ""
        escaped = False
        while self._peek() is not None:
            char = self._advance()
            if escaped:
                result += char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                break
            else:
                result += char
        return result

    def _tokenize_number(self) -> Tuple[str, str]:
        result = ""
        has_dot = False
        has_exp = False
        while self._peek() is not None and (
            self._peek().isdigit() or self._peek() in ".eE"
        ):
            char = self._peek()
            if char == ".":
                if has_dot or has_exp:
                    break
                has_dot = True
            elif char in "eE":
                if has_exp:
                    break
                has_exp = True
                has_dot = True
            result += self._advance()
        if has_dot:
            return TokenType.FLOAT, result
        return TokenType.INTEGER, result

    def _tokenize_identifier(self) -> str:
        result = ""
        while self._peek() is not None and (
            self._peek().isalnum() or self._peek() == "_"
        ):
            result += self._advance()
        return result

    def _handle_newline(self) -> Iterator[Token]:
        self._advance()
        self._skip_comment()

        while self._peek() is not None and self._peek() in "\n\r":
            self._advance()
            self._skip_comment()

        indent = 0
        has_spaces = False
        has_tabs = False
        while self._peek() is not None and self._peek() in " \t":
            if self._peek() == "\t":
                indent += 4
                has_tabs = True
            else:
                indent += 1
                has_spaces = True
            self._advance()

        # 检测混合缩进
        if has_spaces and has_tabs:
            raise ValueError(f"Mixed indentation (spaces and tabs) at line {self.line}")

        # 设置缩进类型
        if indent > 0:
            current_indent_type = 'tabs' if has_tabs else 'spaces'
            if self._indent_type is None:
                self._indent_type = current_indent_type
            elif self._indent_type != current_indent_type:
                raise ValueError(f"Inconsistent indentation at line {self.line}: "
                               f"expected {self._indent_type}, got {current_indent_type}")

        # 检查缩进是否是4的倍数（标准缩进规则）
        if indent != 0 and indent % 4 != 0:
            raise ValueError(f"Invalid indentation level {indent} at line {self.line}. "
                           f"Indentation must be a multiple of 4")
        
        # 如果期望缩进（遇到块关键字后的冒号），下一行的缩进必须大于当前级别且增量为4
        if self._expect_indent:
            expected_indent = self.indent_stack[-1] + 4
            if indent != expected_indent:
                raise ValueError(f"Expected increased indentation at line {self.line}. "
                               f"Expected {expected_indent}, got {indent}")
            # 重置期望缩进标记
            self._expect_indent = False
        else:
            # 非期望缩进情况下，检查缩进是否在有效范围内
            # 如果缩进不为0且不在缩进栈中，说明缩进不一致
            if indent != 0 and indent not in self.indent_stack:
                valid_indents = sorted(self.indent_stack)
                raise ValueError(f"Invalid indentation level {indent} at line {self.line}. "
                               f"Expected one of {valid_indents}")

        # 弹出直到找到匹配的缩进级别
        while indent < self.indent_stack[-1]:
            self.indent_stack.pop()
            yield Token(TokenType.DEDENT, "", self.line, self.col)

        if indent > self.indent_stack[-1]:
            self.indent_stack.append(indent)
            yield Token(TokenType.INDENT, "", self.line, self.col)

        if self._peek() is not None and self._peek() != "#":
            yield Token(TokenType.NEWLINE, "", self.line, self.col)
        elif self._peek() is None:
            yield Token(TokenType.NEWLINE, "", self.line, self.col)

    def tokenize(self) -> Iterator[Token]:
        while self._peek() is not None:
            char = self._peek()

            if char == "\n":
                yield from self._handle_newline()
                continue

            if char in " \t":
                self._skip_whitespace()
                continue

            if char == "#":
                self._skip_comment()
                continue

            if char == '"' or char == "'":
                value = self._tokenize_string()
                yield Token(TokenType.STRING, value, self.line, self.col - len(value) - 2)
                continue

            if char.isdigit():
                token_type, value = self._tokenize_number()
                yield Token(token_type, value, self.line, self.col - len(value))
                continue

            if char.isalpha() or char == "_":
                value = self._tokenize_identifier()
                token_type = self.KEYWORDS.get(value, TokenType.IDENTIFIER)
                yield Token(token_type, value, self.line, self.col - len(value))
                continue

            if char == "+":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.PLUS_ASSIGN, "+=", self.line, self.col - 2)
                elif self._peek() == "+":
                    self._advance()
                    yield Token(TokenType.PLUS, "++", self.line, self.col - 2)
                else:
                    yield Token(TokenType.PLUS, "+", self.line, self.col - 1)
                continue

            if char == "-":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.MINUS_ASSIGN, "-=", self.line, self.col - 2)
                elif self._peek() == "-":
                    self._advance()
                    yield Token(TokenType.MINUS, "--", self.line, self.col - 2)
                elif self._peek() == ">":
                    self._advance()
                    yield Token(TokenType.ARROW, "->", self.line, self.col - 2)
                    # 箭头不打断块起始链，后续的类型和冒号仍然是块定义的一部分
                    self._prev_token_was_block_start = True
                else:
                    yield Token(TokenType.MINUS, "-", self.line, self.col - 1)
                continue

            if char == "*":
                # 构建块符号 *: 要求前面有空白（前后必须留白）
                prev_char = self.source[self.pos - 2] if self.pos >= 2 else ""
                has_prev_whitespace = prev_char in (" ", "\t", "\n", "(")
                
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.MUL_ASSIGN, "*=", self.line, self.col - 2)
                elif self._peek() == "*":
                    self._advance()
                    yield Token(TokenType.POW, "**", self.line, self.col - 2)
                elif self._peek() == ":" and has_prev_whitespace:
                    # 构建块符号 *: 必须前面有空白，后面有换行
                    self._advance()
                    next_char = self._peek()
                    if next_char in ("\n",):
                        yield Token(TokenType.BUILD_GEN, "*:", self.line, self.col - 2)
                        self._expect_indent = True
                    else:
                        # 符号后没有换行，作为普通的 * 和 :
                        yield Token(TokenType.MUL, "*", self.line, self.col - 2)
                        yield Token(TokenType.COLON, ":", self.line, self.col - 1)
                else:
                    yield Token(TokenType.MUL, "*", self.line, self.col - 1)
                continue

            if char == "/":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.DIV_ASSIGN, "/=", self.line, self.col - 2)
                elif self._peek() == "/":
                    self._advance()
                    while self._peek() is not None and self._peek() != "\n":
                        self._advance()
                    continue
                else:
                    yield Token(TokenType.DIV, "/", self.line, self.col - 1)
                continue

            if char == "=":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.EQ, "==", self.line, self.col - 2)
                elif self._peek() == ":":
                    # 检查符号后是否有换行（构建块符号必须后换行）
                    self._advance()
                    next_char = self._peek()
                    if next_char in ("\n",):
                        yield Token(TokenType.BUILD_ASSIGN, "=:", self.line, self.col - 2)
                        self._expect_indent = True
                    else:
                        # 符号后没有换行，作为普通的 = 和 :
                        yield Token(TokenType.ASSIGN, "=", self.line, self.col - 2)
                        yield Token(TokenType.COLON, ":", self.line, self.col - 1)
                else:
                    yield Token(TokenType.ASSIGN, "=", self.line, self.col - 1)
                continue

            if char == "!":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.NE, "!=", self.line, self.col - 2)
                else:
                    yield Token(TokenType.NOT, "!", self.line, self.col - 1)
                continue

            if char == "<":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.LE, "<=", self.line, self.col - 2)
                elif self._peek() == ":":
                    self._advance()
                    yield Token(TokenType.SUBTYPE, "<:", self.line, self.col - 2)
                else:
                    yield Token(TokenType.LT, "<", self.line, self.col - 1)
                continue

            if char == ">":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.GE, ">=", self.line, self.col - 2)
                else:
                    yield Token(TokenType.GT, ">", self.line, self.col - 1)
                continue

            if char == "&":
                self._advance()
                if self._peek() == "&":
                    self._advance()
                    yield Token(TokenType.AND, "&&", self.line, self.col - 2)
                else:
                    yield Token(TokenType.DEREF, "&", self.line, self.col - 1)
                continue

            if char == "|":
                self._advance()
                if self._peek() == "|":
                    self._advance()
                    yield Token(TokenType.OR, "||", self.line, self.col - 2)
                elif self._peek() == ">":
                    self._advance()
                    yield Token(TokenType.PIPE_GT, "|>", self.line, self.col - 2)
                else:
                    yield Token(TokenType.PIPE, "|", self.line, self.col - 1)
                continue

            if char == ".":
                self._advance()
                yield Token(TokenType.DOT, ".", self.line, self.col - 1)
                continue

            if char == ",":
                self._advance()
                yield Token(TokenType.COMMA, ",", self.line, self.col - 1)
                continue

            if char == ":":
                self._advance()
                yield Token(TokenType.COLON, ":", self.line, self.col - 1)
                # 检查冒号后面是否是换行（块定义）
                # 如果是换行，期望下一行增加缩进
                next_char = self._peek()
                if next_char == "\n":
                    self._expect_indent = True
                continue

            if char == ";":
                self._advance()
                yield Token(TokenType.SEMICOLON, ";", self.line, self.col - 1)
                continue

            if char == "(":
                self._advance()
                yield Token(TokenType.LPAREN, "(", self.line, self.col - 1)
                continue

            if char == ")":
                self._advance()
                yield Token(TokenType.RPAREN, ")", self.line, self.col - 1)
                continue

            if char == "[":
                self._advance()
                yield Token(TokenType.LBRACKET, "[", self.line, self.col - 1)
                continue

            if char == "]":
                self._advance()
                yield Token(TokenType.RBRACKET, "]", self.line, self.col - 1)
                continue

            if char == "{":
                self._advance()
                yield Token(TokenType.LBRACE, "{", self.line, self.col - 1)
                continue

            if char == "}":
                self._advance()
                yield Token(TokenType.RBRACE, "}", self.line, self.col - 1)
                continue

            if char == "@":
                self._advance()
                yield Token(TokenType.AT, "@", self.line, self.col - 1)
                continue

            if char == "~":
                self._advance()
                if self._peek() == ":":
                    # 检查符号后是否有换行（构建块符号必须后换行）
                    self._advance()
                    next_char = self._peek()
                    if next_char in ("\n",):
                        yield Token(TokenType.BUILD_CALL, "~:", self.line, self.col - 2)
                        self._expect_indent = True
                    else:
                        # 符号后没有换行，作为普通的 ~ 和 :
                        yield Token(TokenType.TILDE, "~", self.line, self.col - 2)
                        yield Token(TokenType.COLON, ":", self.line, self.col - 1)
                else:
                    yield Token(TokenType.TILDE, "~", self.line, self.col - 1)
                continue

            if char == "^":
                self._advance()
                yield Token(TokenType.BUILD_VALUE, "^", self.line, self.col - 1)
                continue

            self._advance()

        yield Token(TokenType.EOF, "", self.line, self.col)