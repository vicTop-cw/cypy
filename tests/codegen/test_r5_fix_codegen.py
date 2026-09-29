"""R5-修复 的回归锁：codegen 侧七张单，逐单配「正例必须成立 / 对照必须仍成立」。

| 单 | 根因（机制栏见 memory/bugs.md） | 正例锁 | 对照锁 |
|----|--------------------------------|--------|--------|
| BUG-74 | `^=` 的左操作数被包进 BuildValueExpr 后，落码只取 operand | `x ^= 5` → `x = x ^ 5` | `x = 5` / `b: int = a` 不变 |
| BUG-76 | 清理只注入**顶层** return 之前，嵌套出口（if/for 里的 return）跳过 | 2 个出口 ⇒ 清理 2 次 | 单出口仍只 1 次、多 defer 仍逆序 |
| BUG-78 | 扁平优先级表 + 只在 `right_prec < current_prec` 补括号 | 五族同形全部保括号 | 左结合链不被多括号 |
| BUG-80 | 只摘**顶层** DeferStmt，嵌套 defer 就地发射 | `if`/`for` 里的 defer 在体末执行 | 顶层 defer 的既有搬移不变 |
| BUG-81 | comptime 结果落码走 `repr(...)`，容器里的 AST 节点 repr 泄进产物 | 产物是可编译字面量、无内部表示 | 标量折叠（3/42）不变 |
| BUG-82 | comptime 字符串用 `f'"{result}"'` 直插，不走 repr 路径 | 不出现 `"a"b"`；不占 docstring 位 | 整数 comptime 仍折叠 |
| BUG-90 | 产物写死身份，且调用方也不把源路径交给生成器 | 无路径不伪造；有路径是真值可 round-trip；hook 入口带真路径 | 无路径入口不造；同段元数据照旧 |

夹具逐字取自判据件（`.fist-loop-20260927/hunt_r5_codegen.py` 的 c01/c03/c04/c05 与
`advance_r4_dormant.py` 的 SHAPES），避免锁与量尺各造一套形状。
"""

from __future__ import annotations

import ast

import pytest

from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Constant, Parser

# --------------------------------------------------------------------------- 夹具
XOR_AUG = "def f(x: int) -> int:\n    x ^= 5\n    return x\n"
XOR_AUG_VAR = "def f(x: int, y: int) -> int:\n    x ^= y\n    return x\n"
PLAIN_ASSIGN = "def f(x: int) -> int:\n    x = 5\n    return x\n"
BUILD_VALUE_RHS = "def f(a: int) -> int:\n    let b: int = a^\n    return b\n"

# 判据件 defer_two_exits 的形状（BUG-76）
DEFER_TWO_EXITS = (
    "def pick(flag: int) -> int:\n"
    '    f = open("t.txt", "w")\n'
    "    defer:\n"
    "        f.close()\n"
    "    if flag:\n"
    "        return 1\n"
    "    return 2\n"
)
# 判据件 single_defer / defer_before_return / two_defers_lifo（今天已对，须一直对）
DEFER_SINGLE_EXIT = (
    "def make() -> int:\n"
    '    print("make")\n'
    "    return 1\n\n"
    "def three() -> int:\n"
    "    f = make()\n"
    "    defer:\n"
    '        print("DONE")\n'
    "    return 7\n"
)
DEFER_LIFO = (
    "def two() -> int:\n"
    '    print("bodyA")\n'
    "    defer:\n"
    '        print("Z1")\n'
    "    defer:\n"
    '        print("Z2")\n'
    '    print("bodyB")\n'
    "    return 0\n"
)
# 判据件 c03 / c03_ctl（BUG-80）
NESTED_DEFER_IN_IF = (
    "def f(n: int) -> int:\n"
    "    if n > 0:\n"
    "        defer:\n"
    '            print("CLEAN")\n'
    '    print("BODY")\n'
    "    return n\n"
)
NESTED_DEFER_IN_FOR = (
    "def f(n: int) -> int:\n"
    "    for i in range(n):\n"
    "        defer:\n"
    '            print("CLEAN")\n'
    '    print("BODY")\n'
    "    return n\n"
)
TOP_LEVEL_DEFER = (
    "def f(n: int) -> int:\n"
    "    defer:\n"
    '        print("CLEAN")\n'
    '    print("BODY")\n'
    "    return n\n"
)

COMPTIME_LIST = "def f() -> int:\n    comptime: [1, 2]\n    return 1\n"
COMPTIME_STR = 'def f() -> int:\n    comptime: "a" + "\\"" + "b"\n    return 1\n'
COMPTIME_STR_PLAIN = 'def f() -> int:\n    comptime: "abc"\n    return 1\n'
COMPTIME_STR_BACKSLASH = 'def f() -> int:\n    comptime: "a" + "\\\\" + "b"\n    return 1\n'
COMPTIME_INT = "def f() -> int:\n    comptime: 1 + 2\n    return 1\n"
GREETING = 'def greet() -> str:\n    return "hi"\n'

# 判据件 c01 / c01_ctl 的六族（BUG-78）：源表达式 -> 产物里必须出现的那一行
BINOP_PARENS = [
    ("a - (b - c)", "a - (b - c)"),
    ("a % (b % c)", "a % (b % c)"),
    ("a >> (b >> c)", "a >> (b >> c)"),
    ("(a | b) & c", "(a | b) & c"),
    ("(a ^ b) & c", "(a ^ b) & c"),
    ("a * (b + c)", "a * (b + c)"),
]
BINOP_NO_PARENS = [
    ("a - b - c", "a - b - c"),
    ("a + b + c", "a + b + c"),
    ("(a + b) - c", "a + b - c"),
    ("a & b | c", "a & b | c"),
    ("a - b + c", "a - b + c"),
]


# --------------------------------------------------------------------------- 工具
def _lower(source: str, source_file: str = None) -> str:
    """Lexer -> Parser -> CythonGenerator：与 CLI 同一张产物脸。"""
    tree = Parser(list(Lexer(source).tokenize())).parse()
    return CythonGenerator(source_file=source_file).generate(tree)


def _fn_slice(code: str, func: str) -> str:
    """被测函数那一段**原文**（保留缩进）：模块头与别的函数都不算进来。"""
    out = []
    inside = False
    for raw in code.splitlines():
        if not inside and raw.startswith(f"def {func}("):
            inside = True
        elif inside and raw.strip() and not raw.startswith((" ", "\t")):
            break
        if inside:
            out.append(raw.rstrip())
    assert out, f"产物里没有函数 {func}"
    return "\n".join(out)


def _fn_lines(code: str, func: str) -> list:
    """被测函数那一段的非空、非注释行（缩进剥掉，只用于逐行比对）。"""
    lines = []
    for raw in _fn_slice(code, func).splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    assert lines, f"函数 {func} 的产物体是空的"
    return lines


def _assert_compilable(code: str, func: str) -> None:
    """产物片段必须能被 Python/Cython 解析：判「产物不可编译」这一条。"""
    text = _fn_slice(code, func)
    try:
        ast.parse(text)
    except SyntaxError as exc:
        pytest.fail(f"产物不可编译 -> {exc}\n{text}")


# --------------------------------------------------------------------------- BUG-74
def test_bug74_augmented_xor_lowers_to_declared_equivalent():
    """SYNTAX/12-operators.md:90 声明 `x ^= 3` ≡ `x = x ^ 3`，左操作数不能丢。"""
    lines = _fn_lines(_lower(XOR_AUG), "f")
    assert "x = x ^ 5" in lines, lines
    assert "x = 5" not in lines, f"左操作数与运算符一起被丢了：{lines}"


def test_bug74_augmented_xor_with_variable_rhs_keeps_both_operands():
    lines = _fn_lines(_lower(XOR_AUG_VAR), "f")
    assert "x = x ^ y" in lines, lines


def test_bug74_plain_assignment_not_touched():
    """对照：不带 `^` 的赋值必须照旧是 `x = 5`（否则上一条判据恒绿）。"""
    lines = _fn_lines(_lower(PLAIN_ASSIGN), "f")
    assert "x = 5" in lines, lines
    assert not any("^" in line for line in lines), lines


def test_bug74_build_value_in_value_position_unchanged():
    """对照：`a^` 出现在值位仍是既有的取值降级，不被本单顺手改语义。"""
    lines = _fn_lines(_lower(BUILD_VALUE_RHS), "f")
    assert "b: int = a" in lines, lines


# --------------------------------------------------------------------------- BUG-76
def test_bug76_nested_return_exit_runs_defer_cleanup():
    """`if` 里的 return 也是函数出口：2 个出口 ⇒ 清理必须发 2 次。"""
    code = _lower(DEFER_TWO_EXITS)
    _assert_compilable(code, "pick")
    lines = _fn_lines(code, "pick")
    returns = [ln for ln in lines if ln.startswith("return")]
    cleanups = [ln for ln in lines if ln == "f.close()"]
    assert len(returns) == 2, lines
    assert len(cleanups) == 2, f"2 个出口只发了 {len(cleanups)} 次清理：{lines}"
    assert lines == [
        "def pick(flag):",
        "f = open('t.txt', 'w')",
        "if flag:",
        "f.close()",
        "return 1",
        "f.close()",
        "return 2",
    ], lines


def test_bug76_defer_in_loop_return_emitted_once_per_exit():
    """for 里的 return 同理：清理跟着出口走，不留在循环体内。"""
    src = (
        "def scan(n: int) -> int:\n"
        '    r = open("t.txt", "w")\n'
        "    defer:\n"
        "        r.close()\n"
        "    for i in range(n):\n"
        "        if i > 0:\n"
        "            return i\n"
        "    return 0\n"
    )
    lines = _fn_lines(_lower(src), "scan")
    assert sum(1 for ln in lines if ln == "r.close()") == 2, lines
    assert lines.index("r.close()") > lines.index("if i > 0:"), lines


def test_bug76_single_exit_still_emits_cleanup_once():
    """对照（defer_before_return）：单出口的清理不能被搬成两次。"""
    lines = _fn_lines(_lower(DEFER_SINGLE_EXIT), "three")
    assert lines.count("print('DONE')") == 1, lines
    assert lines[-2:] == ["print('DONE')", "return 7"], lines


def test_bug76_multiple_defers_keep_reverse_order_at_every_exit():
    """对照（two_defers_lifo）：多 defer 逆序在搬移后仍然成立。"""
    lines = _fn_lines(_lower(DEFER_LIFO), "two")
    assert lines.index("print('Z2')") < lines.index("print('Z1')"), lines
    assert lines[:4] == [
        "def two():",
        "print('bodyA')",
        "print('bodyB')",
        "print('Z2')",
    ], lines


# --------------------------------------------------------------------------- BUG-78
@pytest.mark.parametrize("expr,expected", BINOP_PARENS)
def test_bug78_equal_precedence_right_operand_keeps_parens(expr, expected):
    """等优先级的左结合右操作数、以及 `|`/`^`/`&` 的分级：括号丢了就改了次序。"""
    src = f"def f(a: int, b: int, c: int) -> int:\n    return {expr}\n"
    line = [ln for ln in _fn_lines(_lower(src), "f") if ln.startswith("return")][0]
    assert line == f"return {expected}", f"{expr} -> {line}"


@pytest.mark.parametrize("expr,expected", BINOP_NO_PARENS)
def test_bug78_left_associative_chain_not_over_parenthesized(expr, expected):
    """对照：源里没写括号、次序本来就没变的链，不能被补上一堆括号。"""
    src = f"def f(a: int, b: int, c: int) -> int:\n    return {expr}\n"
    line = [ln for ln in _fn_lines(_lower(src), "f") if ln.startswith("return")][0]
    assert line == f"return {expected}", f"{expr} -> {line}"


def test_bug78_power_stays_right_associative():
    """对照：`**` 的右结合形态今天就有括号，改动后不得倒退。"""
    src = "def f(a: int, b: int, c: int) -> int:\n    return a ** (b ** c)\n"
    line = [ln for ln in _fn_lines(_lower(src), "f") if ln.startswith("return")][0]
    assert line == "return a ** (b ** c)", line


# --------------------------------------------------------------------------- BUG-80
def test_bug80_nested_defer_in_if_runs_at_function_exit():
    """SYNTAX/14-syntax-sugar.md:176「函数退出时自动执行」：if 里的 defer 不得就地跑。"""
    lines = _fn_lines(_lower(NESTED_DEFER_IN_IF), "f")
    prints = [ln for ln in lines if "print(" in ln]
    assert prints == ["print('BODY')", "print('CLEAN')"], lines


def test_bug80_nested_defer_in_for_runs_once_at_exit():
    """for 里的 defer 不是每轮清一次，而是函数退出时清一次。"""
    lines = _fn_lines(_lower(NESTED_DEFER_IN_FOR), "f")
    prints = [ln for ln in lines if "print(" in ln]
    assert prints == ["print('BODY')", "print('CLEAN')"], lines
    loop_body = lines[lines.index("for i in range(n):") + 1: lines.index("print('BODY')")]
    assert "print('CLEAN')" not in loop_body, f"清理留在循环体内：{lines}"


def test_bug80_defer_only_block_stays_compilable():
    """`if` 体里只有 defer 时，搬空之后那一格必须有语句可站。"""
    _assert_compilable(_lower(NESTED_DEFER_IN_IF), "f")


def test_bug80_nested_defer_in_loop_block_stays_compilable():
    src = (
        "def f(n: int) -> int:\n"
        "    while n > 0:\n"
        "        defer:\n"
        '            print("CLEAN")\n'
        '    print("BODY")\n'
        "    return n\n"
    )
    code = _lower(src)
    _assert_compilable(code, "f")
    prints = [ln for ln in _fn_lines(code, "f") if "print(" in ln]
    assert prints == ["print('BODY')", "print('CLEAN')"], prints


def test_bug80_top_level_defer_still_moved_to_exit():
    """对照（c03_ctl）：顶层 defer 的既有搬移不能因为本单倒退。"""
    lines = _fn_lines(_lower(TOP_LEVEL_DEFER), "f")
    prints = [ln for ln in lines if "print(" in ln]
    assert prints == ["print('BODY')", "print('CLEAN')"], lines


def test_bug80_defer_in_nested_function_belongs_to_that_function():
    """defer 的搬移不跨函数作用域：内层函数的 defer 在内层出口跑。"""
    src = (
        "def outer() -> int:\n"
        '    print("outer-body")\n'
        "    defer:\n"
        '        print("outer-clean")\n'
        "    inner()\n"
        "    return 0\n\n"
        "def inner() -> int:\n"
        '    print("inner-body")\n'
        "    defer:\n"
        '        print("inner-clean")\n'
        "    return 0\n"
    )
    code = _lower(src)
    outer = _fn_lines(code, "outer")
    inner = _fn_lines(code, "inner")
    assert [ln for ln in outer if "print(" in ln] == [
        "print('outer-body')",
        "print('outer-clean')",
    ], outer
    assert [ln for ln in inner if "print(" in ln] == [
        "print('inner-body')",
        "print('inner-clean')",
    ], inner


# --------------------------------------------------------------------------- BUG-81
def test_bug81_comptime_collection_product_is_a_compilable_literal():
    """产物里不得出现 AST 节点 repr（`Constant(line=…)`），必须是字面量。"""
    code = _lower(COMPTIME_LIST)
    assert "Constant(line=" not in code, code
    body = _fn_lines(code, "f")
    assert body[1] == "[1, 2]", body
    _assert_compilable(code, "f")


def test_bug81_codegen_renders_container_results_structurally(monkeypatch):
    """生成侧的边界契约：即使求值侧交回挂着节点的元素，也不许 repr 进产物。

    机制栏的生成侧那一半就是 `self._write(repr(result))`。这里把上游返回值钉成
    「半 AST 的列表」，直接驱动这一半：必须渲染成字面量 `[1, 2]`，不是
    `[Constant(line=2, col=16), …]`。
    """
    import cypyc.analyzer.comptime_evaluator as evaluator_mod

    leaked = [Constant(1, line=2, col=16), Constant(2, line=2, col=19)]
    monkeypatch.setattr(evaluator_mod, "evaluate_comptime", lambda node, evaluator=None: leaked)
    code = _lower(COMPTIME_LIST)
    assert "Constant(line=" not in code, code
    body = _fn_lines(code, "f")
    assert body[1] == "[1, 2]", body
    _assert_compilable(code, "f")


def test_bug81_scalar_folding_unchanged():
    """对照：整数 comptime 的折叠形状（3）不受本单影响。"""
    lines = _fn_lines(_lower(COMPTIME_INT), "f")
    assert lines[1] == "3", lines


# --------------------------------------------------------------------------- BUG-82
def test_bug82_comptime_string_result_is_not_interpolated_raw():
    """`comptime: "a" + "\\"" + "b"` 不得产出 `"a"b"` 这种断掉的活表达式。"""
    code = _lower(COMPTIME_STR)
    assert '"a"b"' not in code, code
    body = _fn_slice(code, "f")
    broken = [
        ln.strip()
        for ln in body.splitlines()
        if ln.strip().startswith('"') and ln.strip().count('"') % 2
    ]
    assert not broken, f"未转义的字符串直插产物：{broken}"
    _assert_compilable(code, "f")


def test_bug82_comptime_string_cannot_hijack_docstring():
    """字符串结果落到函数体首行会被 Cython 认成 docstring（可劫持）——不许发生。"""
    code = _lower(COMPTIME_STR_PLAIN)
    _assert_compilable(code, "f")
    func = ast.parse(_fn_slice(code, "f")).body[0]
    first = func.body[0]
    assert not (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(first.value.value, str)
    ), f"comptime 字符串占了 docstring 位：{ast.dump(first)}"


def test_bug82_comptime_string_with_backslash_not_emitted_as_broken_literal():
    """含反斜杠/引号的字符串结果：要么合法转义，要么不落在活字面量位。"""
    code = _lower(COMPTIME_STR_BACKSLASH)
    _assert_compilable(code, "f")
    literals = [ln for ln in _fn_lines(code, "f") if ln[:1] in ("'", '"')]
    assert not literals, f"字符串结果以活字面量落在产物里：{literals}"


# --------------------------------------------------------------------------- BUG-90
def test_bug90_placeholder_identity_not_emitted():
    """调用方没给源路径时，不得伪造 `__name__ = "unknown"` / `__file__ = ""`。"""
    code = _lower(GREETING)
    assert '__name__ = "unknown"' not in code, code
    assert '__file__ = ""' not in code, code
    assert "Source file: unknown" not in code, code
    fabricated = [ln for ln in code.splitlines() if ln.startswith(("__name__ =", "__file__ ="))]
    assert not fabricated, f"身份常量被写死：{fabricated}"


def test_bug90_real_identity_when_source_path_known():
    """拿到源路径时身份常量就是真值（模块认得出自己）。"""
    code = _lower(GREETING, source_file="proj/hello.cypy")
    assert "__name__" in code and "hello" in code, code
    assert "proj/hello.cypy" in code, code
    assert "Source file: unknown" not in code, code


def test_bug90_identity_literals_round_trip_for_nasty_paths():
    """身份常量必须落在合法的字符串字面量里：反斜杠/引号都不能吃掉字符。"""
    nasty = 'proj\\we\'ird"q.cypy'
    code = _lower(GREETING, source_file=nasty)
    lines = {}
    for raw in code.splitlines():
        if raw.startswith("__name__ = ") or raw.startswith("__file__ = "):
            key, _, value = raw.partition(" = ")
            lines[key] = value
    assert "__file__" in lines, code
    try:
        got = ast.literal_eval(lines["__file__"])
    except (SyntaxError, ValueError) as exc:
        pytest.fail(f"__file__ 不是合法字面量：{lines['__file__']!r} -> {exc}")
    assert got == nasty, f"{got!r} != {nasty!r}"


def test_bug90_other_module_metadata_still_emitted():
    """对照（判据件 k07_ctl）：同段其它元数据仍是真值，别把面缩成「什么都不发」。"""
    code = _lower(GREETING, source_file="proj/hello.cypy")
    assert "__all__ = [" in code, code
    assert "__profile__ = " in code, code
    assert "__compile_time__ = " in code, code
    assert "__target__ = " in code, code


def _identity_lines(code: str) -> dict:
    """产物里的模块级身份常量 {名字: 字面量原文}；只认赋值行，注释与 docstring 不算。"""
    out = {}
    for raw in code.splitlines():
        if raw.startswith(("__name__ = ", "__file__ = ")):
            key, _, value = raw.partition(" = ")
            out[key] = value
    return out


def test_bug90_hook_transpile_file_carries_real_identity(tmp_path):
    """调用面锁：`CypyHook.transpile_file` 知道源路径，必须把路径交给生成器。

    BUG-90 的机制栏写的是「`CythonGenerator(source_file=None)` 的默认值从未被任何调用方
    覆盖」——只在生成器上打转的锁打不到这一半：不传路径时，删掉伪造之后产物直接没有身份
    常量（自研套件 `codegen_module_magic_attrs` 就是靠这条打红的）。
    """
    from cypy_hook.hook import CypyHook

    src = tmp_path / "hello_mod.cypy"
    src.write_text(GREETING, encoding="utf-8")
    hook = CypyHook()
    hook.set_output_dir(str(tmp_path / "out"))
    hook.set_verbose(False)
    result = hook.transpile_file(str(src), incremental=False)
    assert result.success, result.errors
    lines = _identity_lines(result.cython_code)
    assert sorted(lines) == ["__file__", "__name__"], lines
    assert ast.literal_eval(lines["__name__"]) == "hello_mod", lines
    assert ast.literal_eval(lines["__file__"]) == str(src), lines


def test_bug90_hook_transpile_without_path_fabricates_nothing():
    """对照：无路径入口 `transpile(source)` 仍不得伪造身份——缺就是缺，不是造一个假的。"""
    from cypy_hook.hook import CypyHook

    hook = CypyHook()
    hook.set_verbose(False)
    result = hook.transpile(GREETING)
    assert result.success, result.errors
    assert _identity_lines(result.cython_code) == {}, result.cython_code


# --------------------------------------------------------------------------- BUG-91
def test_bug91_windows_path_in_header_docstring_is_a_valid_literal():
    """调用方传真路径后，头注 docstring 里的反斜杠必须成对（BUG-91）。

    单反斜杠的 Windows 路径落在模块开头的三引号串里会被读成 unicode 转义，产物在 Cython
    侧就地语法错误；这里把那段三引号串按字面量读回来，读不回就是回归。
    """
    win = "C:\\Users\\who\\proj\\main.cypy"
    code = _lower(GREETING, source_file=win)
    head = code.split('"""')[1]
    assert "\\\\Users" in head, head
    try:
        doc = ast.literal_eval('"""' + head + '"""')
    except (SyntaxError, ValueError) as exc:
        pytest.fail(f"头注 docstring 读不回字符串：{head!r} -> {exc}")
    assert win in doc, doc
