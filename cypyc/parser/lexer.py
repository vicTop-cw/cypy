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
    TRUE = "TRUE"
    FALSE = "FALSE"

    PLUS = "PLUS"
    MINUS = "MINUS"
    MUL = "MUL"
    DIV = "DIV"
    MOD = "MOD"
    POW = "POW"
    STAR_STAR = "STAR_STAR"

    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    SUBTYPE = "SUBTYPE"
    LSHIFT = "LSHIFT"  # <<
    RSHIFT = "RSHIFT"  # >>
    LSHIFT_ASSIGN = "LSHIFT_ASSIGN"  # <<=
    RSHIFT_ASSIGN = "RSHIFT_ASSIGN"  # >>=

    ASSIGN = "ASSIGN"
    PLUS_ASSIGN = "PLUS_ASSIGN"
    MINUS_ASSIGN = "MINUS_ASSIGN"
    MUL_ASSIGN = "MUL_ASSIGN"
    DIV_ASSIGN = "DIV_ASSIGN"
    MOD_ASSIGN = "MOD_ASSIGN"
    FLOORDIV = "FLOORDIV"
    FLOORDIV_ASSIGN = "FLOORDIV_ASSIGN"

    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    DEREF = "DEREF"
    PIPE = "PIPE"
    PIPE_GT = "PIPE_GT"

    DOT = "DOT"
    DOT_DOT = "DOT_DOT"  # .. 可变参数分隔符
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
    BUILD_INDEX = "BUILD_INDEX"    # ^: (lz 索引构建块)
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
    CDEF = "CDEF"
    STRUCT = "STRUCT"
    ENUM = "ENUM"
    TRAIT = "TRAIT"
    TYPECLASS = "TYPECLASS"
    IMPL = "IMPL"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    IMPORT = "IMPORT"
    FROM = "FROM"
    AS = "AS"
    TYPE = "TYPE"
    VAR = "VAR"
    LET = "LET"
    CONST = "CONST"
    DEFER = "DEFER"
    REF = "REF"
    MUT = "MUT"
    IS = "IS"
    IN = "IN"
    FOR_KW = "FOR_KW"
    META = "META"
    DUCK = "DUCK"
    NEVER = "NEVER"

    GUARD = "GUARD"
    MACRO = "MACRO"
    COMPTIME = "COMPTIME"
    SPAWN = "SPAWN"
    GO = "GO"
    CASE = "CASE"
    VEC = "VEC"
    MATCH = "MATCH"
    YIELD = "YIELD"
    ASSERT = "ASSERT"
    ASYNC = "ASYNC"
    AWAIT = "AWAIT"
    TRY = "TRY"
    EXCEPT = "EXCEPT"
    FINALLY = "FINALLY"
    RAISE = "RAISE"
    EXCEPTION = "EXCEPTION"
    WITH = "WITH"
    LAMBDA = "LAMBDA"
    NO_STRATEGY = "NO_STRATEGY"
    OWNED = "OWNED"
    SUITE = "SUITE"
    TEST = "TEST"
    SETUP = "SETUP"
    TEARDOWN = "TEARDOWN"
    DEL = "DEL"
    PASS = "PASS"
    GLOBAL = "GLOBAL"
    NONLOCAL = "NONLOCAL"

    FAT_ARROW = "FAT_ARROW"  # =>
    BANG = "BANG"  # !
    
    BACKTICK_BLOCK = "BACKTICK_BLOCK"  # ```...```


class Token:
    def __init__(self, type: str, value: str, line: int, col: int, prefix: str = None):
        self.type = type
        self.value = value
        self.line = line
        self.col = col
        self.prefix = prefix  # 用于三反引号代码块的f/r前缀

    def __repr__(self) -> str:
        if self.prefix:
            return f"Token({self.type}, {repr(self.value)}, {self.line}:{self.col}, prefix={repr(self.prefix)})"
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
        "typeclass": TokenType.TYPECLASS,
        "impl": TokenType.IMPL,
        "extends": TokenType.EXTENDS,
        "import": TokenType.IMPORT,
        "from": TokenType.FROM,
        "as": TokenType.AS,
        "type": TokenType.TYPE,
        "let": TokenType.LET,
        "const": TokenType.CONST,
        "defer": TokenType.DEFER,
        "mut": TokenType.MUT,
        "is": TokenType.IS,
        "in": TokenType.IN,
        "and": TokenType.AND,
        "or": TokenType.OR,
        "meta": TokenType.META,
        "duck": TokenType.DUCK,
        "Never": TokenType.NEVER,
        "guard": TokenType.GUARD,
        "macro": TokenType.MACRO,
        "comptime": TokenType.COMPTIME,
        "spawn": TokenType.SPAWN,
        "assert": TokenType.ASSERT,
        "go": TokenType.GO,
        "case": TokenType.CASE,
        "vec": TokenType.VEC,
        "match": TokenType.MATCH,
        "yield": TokenType.YIELD,
        "async": TokenType.ASYNC,
        "await": TokenType.AWAIT,
        "try": TokenType.TRY,
        "except": TokenType.EXCEPT,
        "finally": TokenType.FINALLY,
        "raise": TokenType.RAISE,
        "with": TokenType.WITH,
        "lambda": TokenType.LAMBDA,
        "owned": TokenType.OWNED,
        "suite": TokenType.SUITE,
        "test": TokenType.TEST,
        "setup": TokenType.SETUP,
        "teardown": TokenType.TEARDOWN,
        "del": TokenType.DEL,
        "not": TokenType.NOT,
        "pass": TokenType.PASS,
        "global": TokenType.GLOBAL,
        "nonlocal": TokenType.NONLOCAL,
        "True": TokenType.TRUE,
        "False": TokenType.FALSE,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
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
        self._in_backtick_block = False  # 标记是否在反引号代码块内部
        self._prev_token_was_block_start = False  # 标记前一个token是否是块起始

    def _peek(self) -> Optional[str]:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]

    def _peek_ahead(self, n: int) -> Optional[str]:
        """查看当前位置之后第n个字符"""
        target_pos = self.pos + n
        if target_pos >= len(self.source):
            return None
        return self.source[target_pos]

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

    def _tokenize_string(self, quote: str = None, consume_quote: bool = True) -> str:
        if quote is None:
            quote = self._advance()
        elif consume_quote:
            # quote 已经指定，消费它
            self._advance()
        # 如果 consume_quote=False，quote 已经被消费了，不需要再消费
        result = ""
        escaped = False
        while self._peek() is not None:
            char = self._advance()
            if escaped:
                # 处理转义序列
                if char == 't':
                    result += '\t'
                elif char == 'n':
                    result += '\n'
                elif char == 'r':
                    result += '\r'
                elif char == '\\':
                    result += '\\'
                elif char == '"':
                    result += '"'
                elif char == "'":
                    result += "'"
                else:
                    # 其他转义序列直接保留
                    result += '\\' + char
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                break
            else:
                result += char
        return result

    def _tokenize_triple_backtick(self) -> str:
        """解析三反引号代码字面量"""
        # 消费开头的三个反引号
        for _ in range(3):
            self._advance()
        
        result = ""
        while self._peek() is not None:
            # 检查是否到达结束的三反引号
            if self.source[self.pos:self.pos+3] == "```":
                break
            char = self._advance()
            result += char
        
        # 消费结束的三个反引号
        for _ in range(3):
            self._advance()
        
        return result

    def _tokenize_number(self) -> Tuple[str, str]:
        result = ""
        has_dot = False
        has_exp = False
        
        # 检查是否是 0x/0X（十六进制）或 0o/0O（八进制）或 0b/0B（二进制）
        if self._peek() == '0':
            self._advance()
            result = '0'
            next_char = self._peek()
            if next_char in ('x', 'X'):
                # 十六进制
                self._advance()
                result += next_char
                while self._peek() is not None and (
                    self._peek().isdigit() or self._peek().lower() in 'abcdef'
                ):
                    result += self._advance()
                return TokenType.INTEGER, result
            elif next_char in ('o', 'O'):
                # 八进制
                self._advance()
                result += next_char
                while self._peek() is not None and self._peek() in '01234567':
                    result += self._advance()
                return TokenType.INTEGER, result
            elif next_char in ('b', 'B'):
                # 二进制
                self._advance()
                result += next_char
                while self._peek() is not None and self._peek() in '01':
                    result += self._advance()
                return TokenType.INTEGER, result
            # 否则继续处理普通数字
        
        while self._peek() is not None and (
            self._peek().isdigit() or self._peek() in ".eE_"
        ):
            char = self._peek()
            if char == ".":
                if has_dot or has_exp:
                    break
                # 检查后面是否是另一个点（范围模式：1..10）
                if self._peek_ahead(1) == ".":
                    break
                has_dot = True
            elif char in "eE":
                if has_exp:
                    break
                has_exp = True
                has_dot = True
                result += self._advance()
                # 科学计数法中 e 后面可以有可选的正负号
                if self._peek() in "+-":
                    result += self._advance()
                continue
            elif char == "_":
                # 数字下划线分隔符，跳过不添加到结果
                self._advance()
                continue
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
        
        # 检查是否是带!后缀的标识符（转译期辅助）
        # 如 def name!(...)、@name!、x!
        # 注意：关键字（如vec）不应该带!后缀，因为vec!是vec + !用于向量字面量
        if self._peek() == "!" and result not in self.KEYWORDS:
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

        # 在反引号代码块内部，跳过缩进检查
        if self._in_backtick_block:
            if self._peek() is not None and self._peek() != "#":
                yield Token(TokenType.NEWLINE, "", self.line, self.col)
            elif self._peek() is None:
                yield Token(TokenType.NEWLINE, "", self.line, self.col)
            return
        
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
                # 检查是否是 f-string (支持 f, F, rf, fr, RF, FR)
                prefix = ''
                # 检查前一个字符
                if self.pos >= 1 and self.source[self.pos-1] in ('f', 'F'):
                    # f/F 前面必须是空白字符或行首才是 f-string
                    if self.pos == 1 or self.source[self.pos-2] in (' ', '\t', '\n', '\r', '(', '[', '{', '=', ',', '+', '-', '*', '/', '%', '^', '&', '|', '~', '<', '>', '!', '?', ':'):
                        prefix = self.source[self.pos-1]
                        # 检查是否是 rf/fr 组合
                        if self.pos >= 2 and self.source[self.pos-2] in ('r', 'R'):
                            prefix = self.source[self.pos-2] + prefix
                
                value = self._tokenize_string()
                if prefix:
                    yield Token(TokenType.STRING, value, self.line, self.col - len(value) - len(prefix) - 2, prefix=prefix)
                else:
                    yield Token(TokenType.STRING, value, self.line, self.col - len(value) - 2)
                continue

            if char == "`":
                # 检查是否是三反引号（用于宏代码捕获）
                if self.source[self.pos:self.pos+2] == "``":
                    # 三反引号代码块 - 解析为BACKTICK_BLOCK
                    start_line = self.line
                    start_col = self.col
                    self._advance()  # 第一个 `
                    self._advance()  # 第二个 `
                    self._advance()  # 第三个 `
                    
                    # 设置在反引号代码块内部的标志
                    self._in_backtick_block = True
                    
                    # 读取反引号块内容
                    content = ""
                    while self.pos < len(self.source):
                        if self.source[self.pos:self.pos+3] == "```":
                            # 找到结束的三反引号
                            self._advance()  # 第一个 `
                            self._advance()  # 第二个 `
                            self._advance()  # 第三个 `
                            break
                        content += self._advance()
                    
                    # 重置反引号代码块标志
                    self._in_backtick_block = False
                    
                    # 移除首尾换行符（符合 lang-zone 规范）
                    content = content.strip("\n")
                    
                    # 规范化缩进（textwrap.dedent 类似行为）
                    lines = content.split("\n")
                    if lines:
                        # 计算最小缩进（跳过空行）
                        min_indent = None
                        for line in lines:
                            if line.strip():
                                indent = len(line) - len(line.lstrip())
                                if min_indent is None or indent < min_indent:
                                    min_indent = indent
                        # 移除最小缩进
                        if min_indent and min_indent > 0:
                            lines = [line[min_indent:] if len(line) >= min_indent else line for line in lines]
                        # 移除末尾的空行
                        while lines and not lines[-1].strip():
                            lines.pop()
                        content = "\n".join(lines)
                    
                    yield Token(TokenType.BACKTICK_BLOCK, content, start_line, start_col)
                    continue
                else:
                    # 单个反引号作为普通字符处理
                    self._advance()
                    yield Token(TokenType.IDENTIFIER, "`", self.line, self.col - 1)
                    continue
            
            if char.isdigit():
                token_type, value = self._tokenize_number()
                yield Token(token_type, value, self.line, self.col - len(value))
                continue

            # 检查 f 或 r 前缀后是否紧跟三反引号（必须在标识符解析之前）
            # char 是当前字符，self.pos 指向当前字符位置，所以检查后面三个字符
            if char in ('f', 'r') and self.source[self.pos+1:self.pos+4] == "```":
                # f``` 或 r``` 形式
                prefix = char
                start_line = self.line
                start_col = self.col
                self._advance()  # 消费 f/r
                self._advance()  # 第一个 `
                self._advance()  # 第二个 `
                self._advance()  # 第三个 `
                
                # 设置在反引号代码块内部的标志
                self._in_backtick_block = True
                
                # 读取反引号块内容
                content = ""
                while self.pos < len(self.source):
                    if self.source[self.pos:self.pos+3] == "```":
                        # 找到结束的三反引号
                        self._advance()  # 第一个 `
                        self._advance()  # 第二个 `
                        self._advance()  # 第三个 `
                        break
                    content += self._advance()
                
                # 重置反引号代码块标志
                self._in_backtick_block = False
                
                # 移除首尾换行符（符合 lang-zone 规范）
                content = content.strip("\n")
                
                # 规范化缩进（textwrap.dedent 类似行为）
                lines = content.split("\n")
                if lines:
                    # 计算最小缩进（跳过空行）
                    min_indent = None
                    for line in lines:
                        if line.strip():
                            indent = len(line) - len(line.lstrip())
                            if min_indent is None or indent < min_indent:
                                min_indent = indent
                    # 移除最小缩进
                    if min_indent and min_indent > 0:
                        lines = [line[min_indent:] if len(line) >= min_indent else line for line in lines]
                    # 移除末尾的空行
                    while lines and not lines[-1].strip():
                        lines.pop()
                    content = "\n".join(lines)
                
                yield Token(TokenType.BACKTICK_BLOCK, content, start_line, start_col, prefix=prefix)
                continue

            if char.isalpha() or char == "_":
                # 检查是否是 f-string 前缀 (支持 f, F, rf, fr)
                if char in ('f', 'F', 'r', 'R') and self._peek_ahead(1) in ('"', "'", 'f', 'F'):
                    prefix_chars = char
                    # 检查组合前缀 (rf, fr)
                    if self._peek_ahead(1) in ('f', 'F'):
                        prefix_chars += self._peek_ahead(1)
                        self._advance()  # 消费第一个字符
                        self._advance()  # 消费第二个字符 (f/F)
                    else:
                        self._advance()  # 消费单个前缀字符
                    quote = self._peek()
                    value = self._tokenize_string(quote, consume_quote=True)
                    yield Token(TokenType.STRING, value, self.line, self.col - len(value) - len(prefix_chars), prefix=prefix_chars)
                    continue
                
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
                prev_char = self.source[self.pos - 1] if self.pos >= 1 else ""
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
                    # // 可以是整除运算符或整除赋值 //=
                    if self._peek() == "=":
                        self._advance()
                        yield Token(TokenType.FLOORDIV_ASSIGN, "//=", self.line, self.col - 3)
                    else:
                        yield Token(TokenType.FLOORDIV, "//", self.line, self.col - 2)
                else:
                    yield Token(TokenType.DIV, "/", self.line, self.col - 1)
                continue

            if char == "%":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.MOD_ASSIGN, "%=", self.line, self.col - 2)
                else:
                    yield Token(TokenType.MOD, "%", self.line, self.col - 1)
                continue

            if char == "=":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.EQ, "==", self.line, self.col - 2)
                elif self._peek() == ">":
                    # 处理 => 符号
                    self._advance()
                    yield Token(TokenType.FAT_ARROW, "=>", self.line, self.col - 2)
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
                    # 检查 = 后是否有换行（如 macro name = ... 或赋值语句）
                    if self._peek() == "\n":
                        self._expect_indent = True
                    yield Token(TokenType.ASSIGN, "=", self.line, self.col - 1)
                continue

            if char == "@":
                self._advance()
                yield Token(TokenType.AT, "@", self.line, self.col - 1)
                continue

            if char == "!":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.NE, "!=", self.line, self.col - 2)
                else:
                    # BANG 用于宏调用 @name! 和宏模板 def name!
                    yield Token(TokenType.BANG, "!", self.line, self.col - 1)
                continue

            if char == "<":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.LE, "<=", self.line, self.col - 2)
                elif self._peek() == ":":
                    self._advance()
                    yield Token(TokenType.SUBTYPE, "<:", self.line, self.col - 2)
                elif self._peek() == "<":
                    self._advance()
                    if self._peek() == "=":
                        self._advance()
                        yield Token(TokenType.LSHIFT_ASSIGN, "<<=", self.line, self.col - 3)
                    else:
                        yield Token(TokenType.LSHIFT, "<<", self.line, self.col - 2)
                else:
                    yield Token(TokenType.LT, "<", self.line, self.col - 1)
                continue

            if char == ">":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    yield Token(TokenType.GE, ">=", self.line, self.col - 2)
                elif self._peek() == ">":
                    self._advance()
                    if self._peek() == "=":
                        self._advance()
                        yield Token(TokenType.RSHIFT_ASSIGN, ">>=", self.line, self.col - 3)
                    else:
                        yield Token(TokenType.RSHIFT, ">>", self.line, self.col - 2)
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
                if self._peek() == ".":
                    self._advance()
                    yield Token(TokenType.DOT_DOT, "..", self.line, self.col - 2)
                else:
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
                if self._peek() == ":":
                    # 检查符号后是否有换行（构建块符号必须后换行）
                    self._advance()
                    next_char = self._peek()
                    if next_char in ("\n",):
                        # ^: 索引构建块 (lz)
                        yield Token(TokenType.BUILD_INDEX, "^:", self.line, self.col - 2)
                        self._expect_indent = True
                    else:
                        # 符号后没有换行，作为普通的 ^ 和 :
                        yield Token(TokenType.BUILD_VALUE, "^", self.line, self.col - 2)
                        yield Token(TokenType.COLON, ":", self.line, self.col - 1)
                else:
                    # 单独的 ^ 符号，用于构建值表达式
                    yield Token(TokenType.BUILD_VALUE, "^", self.line, self.col - 1)
                continue

            self._advance()

        yield Token(TokenType.EOF, "", self.line, self.col)