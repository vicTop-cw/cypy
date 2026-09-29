"""R5-修复 词法面回归锁：BUG-75（`^` 异或 / `~` 取反不可达）与 BUG-79（`**=`/`&=`/`|=` 从不发 token）。

两张单的主张同形：「文档声明了，实现没做到」⇒ 锁钉的是声明面，不是实现面。

| 单 | 声明处 | 正例锁 |
|----|--------|--------|
| BUG-75 | `SYNTAX/12-operators.md:57/58`，优先级表 `:179` | `^` 进中缀位、`~` 进一元位 ⇒ 出码 |
| BUG-79 | `SYNTAX/12-operators.md:85/88/89` 的等价式 | 三者发复合赋值 token，且降成文档写的等价式 |

对照锁（必须仍然成立，防「只放开词位了事」）：

- BUG-75：`x^` 构建值后缀、`^:` 索引构建块（`SYNTAX/13-build-blocks.md`）、`^=` 词位一律不动
- BUG-79：同族 `+= -= *= /= //= %= <<= >>=` 的词位与出码逐字不变

夹具形状照抄判据件：`.fist-loop-20260927/hunt_r5_codegen.py` 的 C02（`a **= y` / 同族 `a += y`）
与 `.fist-loop-20260927/advance_r4_probe/p05_bitop.cypy`（`print(a ^ b)`、`~a`）。
"""

from __future__ import annotations

import pytest

from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer, TokenType
from cypyc.parser.parser import BinOp, Name, Parser, ReturnStmt, UnaryOp

FN = "def f(a: int, b: int) -> int:\n"
AUG_FN = "def f(a: int, y: int) -> int:\n"

# 新词位按名字取：常量还没建起来时红要落在断言行，不是 AttributeError
XOR = "XOR"
POW_ASSIGN = "POW_ASSIGN"
BITAND_ASSIGN = "BITAND_ASSIGN"
BITOR_ASSIGN = "BITOR_ASSIGN"


def _tok(name: str):
    return getattr(TokenType, name, None)


def _types(src: str) -> list:
    return [t.type for t in Lexer(src).tokenize()]


def _parse(src: str):
    """返回 (Module 或 None, 失败原因)——解析失败以值传递，让红是断言级。"""
    try:
        return Parser(Lexer(src).tokenize()).parse(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _lower(src: str):
    """词法→语法→出码整条路；任一步炸了就返回 (None, 原因)。"""
    ast, err = _parse(src)
    if ast is None:
        return None, err
    try:
        return CythonGenerator().generate(ast), None
    except Exception as exc:
        return None, f"codegen {type(exc).__name__}: {exc}"


def _body(product: str) -> str:
    """产物开头是模块 docstring 与导入头，判据只看 `def ` 之后的函数体。"""
    i = product.find("def ")
    return product[i:] if i >= 0 else product


def _returned_expr(ast):
    func = ast.body[0]
    ret = func.body[-1]
    assert isinstance(ret, ReturnStmt), f"末条语句不是 return：{ret}"
    return ret.value


# ---------------------------------------------------------------------------
# BUG-79：`**=` / `&=` / `|=` 复合赋值
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,want",
    [
        ("a **= y", POW_ASSIGN),
        ("a &= y", BITAND_ASSIGN),
        ("a |= y", BITOR_ASSIGN),
    ],
)
def test_bug79_lexer_emits_declared_augassign_token(src, want):
    """声明表里的这三个复合赋值必须有独立词位，不能拆成「运算符 + ASSIGN」。"""
    got = _types(src)
    assert _tok(want) is not None, f"TokenType 缺 {want}：词法器根本没有这个 token 类型"
    assert _tok(want) in got, f"`{src}` 词法为 {got}，没发 {_tok(want)}"
    assert TokenType.ASSIGN not in got, f"`{src}` 仍被拆成两词位 {got}（parser 只认 AUG_ASSIGN）"


@pytest.mark.parametrize(
    "src,want",
    [
        ("a += y", "PLUS_ASSIGN"),
        ("a -= y", "MINUS_ASSIGN"),
        ("a *= y", "MUL_ASSIGN"),
        ("a /= y", "DIV_ASSIGN"),
        ("a //= y", "FLOORDIV_ASSIGN"),
        ("a %= y", "MOD_ASSIGN"),
        ("a <<= y", "LSHIFT_ASSIGN"),
        ("a >>= y", "RSHIFT_ASSIGN"),
    ],
)
def test_bug79_augassign_family_still_lexed(src, want):
    """同族 8 个是今天就好用的对照：补分支不许把它们打断。"""
    assert _tok(want) in _types(src), f"同族 `{src}` 的词位被打断（应仍发 {want}）"


@pytest.mark.parametrize(
    "src,want_line",
    [
        ("a **= y", "a = a ** y"),
        ("a &= y", "a = a & y"),
        ("a |= y", "a = a | y"),
        ("a += y", "a = a + y"),
    ],
)
def test_bug79_augassign_lowers_to_doc_equivalent(src, want_line):
    """文档「等价于」列就是判据：`x **= 3` ⇒ `x = x ** 3`（末条是同族对照）。"""
    product, err = _lower(AUG_FN + "    " + src + "\n    return a\n")
    assert product is not None, f"`{src}` 走不到出码：{err}"
    assert want_line in _body(product), f"产物缺文档等价式 `{want_line}`：\n{_body(product)}"


# ---------------------------------------------------------------------------
# BUG-75：二元 `^`（异或）与一元 `~`（取反）
# ---------------------------------------------------------------------------


def test_bug75_lexer_emits_infix_caret_token():
    """`a ^ b` 的 `^` 必须是中缀词位；同族 `&`/`|`/`<<`/`>>` 早就有。"""
    got = _types("a ^ b")
    assert _tok(XOR) is not None, "TokenType 缺 XOR：`^` 只作 BUILD_VALUE ⇒ 异或无 token 可发"
    assert _tok(XOR) in got, f"`a ^ b` 词法为 {got}，没发 {_tok(XOR)}"


def test_bug75_frozen_caret_lexemes_untouched():
    """对照锁：`^:` 索引构建块、`x^` 构建值后缀、`^=` 复合赋值三处词位一律不变。"""
    assert TokenType.BUILD_INDEX in _types("container ^:\n    key\n"), "^: 索引构建块被异或吞了"

    postfix = _types("y = x^\n")
    assert TokenType.BUILD_VALUE in postfix, f"构建值后缀 `x^` 被打断：{postfix}"
    assert _tok(XOR) not in postfix, f"构建值后缀 `x^` 被误判成异或：{postfix}"

    augassign = _types("x ^= y\n")
    assert (
        TokenType.BUILD_VALUE in augassign and TokenType.ASSIGN in augassign
    ), f"`^=` 词位被改动（另单管辖，本锁不许顺手动）：{augassign}"


def test_bug75_infix_xor_parses_to_binop():
    ast, err = _parse(FN + "    return a ^ b\n")
    assert ast is not None, f"`a ^ b` 仍解析失败：{err}"
    expr = _returned_expr(ast)
    assert isinstance(expr, BinOp), f"`a ^ b` 没落成二元运算：{expr}"
    assert expr.op == "^", f"`a ^ b` 的运算符是 {expr.op!r}，不是 '^'"


def test_bug75_unary_invert_parses_to_unaryop():
    ast, err = _parse(FN + "    return ~a\n")
    assert ast is not None, f"`~a` 仍解析失败：{err}"
    expr = _returned_expr(ast)
    assert isinstance(expr, UnaryOp), f"`~a` 没落成单元运算：{expr}"
    assert expr.op == "~", f"`~a` 的运算符是 {expr.op!r}，不是 '~'"


def test_bug75_xor_precedence_sits_between_bitwise_and_and_or():
    """`SYNTAX/12-operators.md:177-180`：`&`=6、`^`=7、`|`=8 ⇒ `&` 紧于 `^` 紧于 `|`，左结合。"""
    ast, err = _parse(FN + "    return a | b ^ a & b\n")
    assert ast is not None, f"`a | b ^ a & b` 解析失败：{err}"
    top = _returned_expr(ast)
    assert isinstance(top, BinOp) and top.op == "|", f"最外层应为 '|'：{top}"
    mid = top.right
    assert isinstance(mid, BinOp) and mid.op == "^", f"次外层应为 '^'：{mid}"
    assert isinstance(mid.right, BinOp) and mid.right.op == "&", f"`^` 右侧应为 '&'：{mid.right}"
    assert isinstance(mid.left, Name) and mid.left.id == "b", f"`^` 左侧应为 b：{mid.left}"


@pytest.mark.parametrize(
    "expr,want",
    [
        ("a ^ b", "a ^ b"),
        ("~a", "~a"),
        ("a & b", "a & b"),
        ("a | b", "a | b"),
        ("a << 2", "a << 2"),
        ("a >> 2", "a >> 2"),
    ],
)
def test_bug75_bitwise_ops_lower(expr, want):
    """整张位操作符表（`SYNTAX/12-operators.md:50-61`）都要能出码；后四条是同族对照。"""
    product, err = _lower(FN + "    return " + expr + "\n")
    assert product is not None, f"`{expr}` 走不到出码：{err}"
    assert want in _body(product), f"产物缺 `{want}`：\n{_body(product)}"
