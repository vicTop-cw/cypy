"""循环轮 R1-修复（2026-09-27）的回归锁：BUG-30 / BUG-31 / BUG-33 / BUG-38，每单至少 1 条。

口径与 `tests/test_polish_20260926_pass7.py` 一致：每条锁死该缺陷本身（拿修复前的产品
代码跑必然红），并配一条**对照**用例，防止「改坏了别处」或「判据恒绿」被当成修好。
BUG-31 本轮只落措辞（改名会打断按名导入的既有用例，已交裁决），故其锁是「口径声明 +
宽度未被顺手改动」两条，不断言改名结果。
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402
from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402


def _parse(src: str):
    return Parser(Lexer(src).tokenize()).parse()


def _cython(src: str) -> str:
    out = CythonGenerator().generate(_parse(src))
    return out if isinstance(out, str) else getattr(out, "cython_code", "")


# ---------------------------------------------------------------- BUG-30 codegen:1161/1246
_FLOAT_WIDEN_SRC = """
def main() -> int:
    let a: int = 42
    let b: float = 3.14
    let e: float = a
    let f: double = a + a
    return 0
"""


def test_bug30_int_initializer_to_float_gets_explicit_double_cast():
    code = _cython(_FLOAT_WIDEN_SRC)
    assert (
        "e: double = <double>a" in code
    ), f"int 初值赋给 float 声明没有补显式强转，运行期 type(e) 仍是 int（BUG-30）\n{code}"
    assert (
        "f: double = <double>(a + a)" in code
    ), "复合整数表达式必须带括号强转，否则 `<double>a + a` 语义被改"


def test_bug30_widening_does_not_touch_non_integrals():
    """对照锁：float 字面量、float+float、int→int 三种形态不得被顺手包上 <double>。"""
    code = _cython("""
def main() -> int:
    let a: int = 42
    let b: float = 3.14
    let c: double = 2.71828
    let g: float = 1.5
    let h: float = b + c
    let k: int = a
    return 0
""")
    assert "g: double = 1.5" in code
    assert "h: double = b + c" in code
    assert "k: int = a" in code
    assert "<double>" not in code, code


# ---------------------------------------------------------------- BUG-31 cypy_bridge/types.py
def test_bug31_bridge_mapping_declares_ffi_key_space_and_renamed_alias():
    """口径锁：自述必须说明键空间是 C/FFI 类型名，且同字不同宽的 `float_` 已改名。"""
    import cypy_bridge
    import cypy_bridge.types as bt

    assert (
        "本模块的映射键是 **C/FFI 类型名**" in bt.__doc__
    ), "模块 docstring 不再声明键空间口径（BUG-31 措辞半）"
    assert "将 C/FFI 类型名转换为 ctypes 类型" in bt.TypeMapper.to_ctypes.__doc__
    assert hasattr(bt, "float32_"), "单精度别名未按裁决改名（BUG-31 改名半）"
    assert not hasattr(bt, "float_"), "旧名 float_ 仍在，与 Cypy float（8 字节）继续撞名"
    assert cypy_bridge.float32_ is bt.float32_, "包门面没跟着改名"


def test_bug31_width_of_bridge_float_is_unchanged():
    """对照锁：改名不改宽度——`float` 键仍是 c_float/4 字节（跨 ABI 宽度口径未动）。"""
    import cypy_bridge.types as bt

    assert bt.TypeMapper().to_ctypes("float") is ctypes.c_float
    assert ctypes.sizeof(bt.float32_) == 4
    assert bt.TypeMapper().to_ctypes("double") is ctypes.c_double


# ---------------------------------------------------------------- BUG-33 lexer.py:_tokenize_string
def test_bug33_unterminated_string_raises_with_position():
    src = 'def main() -> int:\n    let s: str = "abc\n    return 0\n'
    with pytest.raises(ValueError) as ei:
        # tokenize() 是生成器：不迭代就什么都不发生，锁必须真消费一遍
        list(Lexer(src).tokenize())
    msg = str(ei.value)
    assert "Unterminated string literal" in msg, f"未闭合字面量没有指名道姓的诊断，实际：{msg}"
    assert "2:18" in msg, f"诊断必须带字面量起始行列，实际：{msg}"


def test_bug33_closed_string_still_lexes():
    """对照锁：真闭合的字符串不受影响，且未闭合诊断不是「任何输入都抛」。"""
    toks = list(Lexer('def main() -> int:\n    let s: str = "abc"\n    return 0\n').tokenize())
    assert any(getattr(t, "value", None) == "abc" for t in toks)


# ---------------------------------------------------------------- BUG-38 lexer.py:_skip_whitespace
def test_bug38_trailing_spaces_at_eof_do_not_crash():
    src = "def main() -> int:\n    return 0   "
    toks = list(Lexer(src).tokenize())
    assert toks, "EOF 前空格导致词法整体失败"


def test_bug38_trailing_space_parses_like_the_newline_version():
    """对照锁：末行有没有换行，**语法树**必须同型（token 流差异是实现细节，不断言）。"""
    no_nl = _dump(_parse("def main() -> int:\n    return 0   "))
    with_nl = _dump(_parse("def main() -> int:\n    return 0   \n"))
    assert no_nl == with_nl, f"末行无换行的读法丢了结构：\n{no_nl}\n!=\n{with_nl}"


def _dump(node) -> str:
    """把 AST 规范化成可比较的文本（忽略行号/列号类字段）。"""
    if isinstance(node, list):
        return "[" + ",".join(_dump(x) for x in node) + "]"
    kind = getattr(node, "kind", None) or type(node).__name__
    fields = getattr(node, "__dict__", None)
    if fields is None:
        return f"{kind}:{node!r}"
    parts = []
    for key in sorted(fields):
        if key in ("line", "col", "position", "token", "source"):
            continue
        parts.append(f"{key}={_dump(fields[key])}")
    return f"{kind}({','.join(parts)})"
