"""R5-修复 的回归锁：BUG-81..BUG-84 四张 comptime / 类型面的分析器侧缺陷。

纪律是「锁先行」：每条锁先跑成**断言级红**，再改实现到绿。四张单的机制栏现读
`memory/bugs.md` 的 `## BUG-81` … `## BUG-84`。语义以 `SYNTAX/*.md` 的声明为准。

- BUG-81 `evaluate()` 对集合字面量返回未求值的 AST 节点列表 ⇒ 生成侧 repr 出不可编译
  文本。正例锁：列表/元组/嵌套/拼接都求值成纯 Python 值，任一元素求不出来 ⇒ 整体判
  求值失败；对照锁：已正确的标量 comptime 不变。
- BUG-82 同一条 comptime 路径上的字符串结果（根因在生成侧直插落码，不在本车道）。
  求值侧确认锁：`comptime: "a" + "\\"" + "b"` ⇒ `'a"b'`。
- BUG-83 `comptime:` **块形式**（SYNTAX/19-comptime.md:42 写明「未实现」）在求值路径
  上没有诊断。正例锁：抛/返回带行列号、措辞含「未实现」的结构化诊断，分析面也不漏
  内部异常文本；对照锁：行内形式仍零诊断。
- BUG-84 文档工作例的 `-> *char` 被判 Undefined name，同名的 `let p: *char` 却能降码。
  正例锁：`*char`/`*void` 返回位零诊断；对照锁：`*int`/`*double`/`let` 位不变，且
  SYNTAX/*.md 查无此名的 `long`/`short`/`unsigned` 仍然被拒（不顺手放开 C 类型面）。

BUG-82 与 BUG-83 的**落码/打印**面（`cypyc/codegen/*`、`cypyc/cli.py`、
`cypyc/parser/macro_expander.py`）不在本车道，锁只钉到分析器这张脸为止。

夹具沿用仓库既有风格（`tests/test_comptime_func.py`、`tests/test_loop_20260927_fix_r4.py`）：
直接从 `Lexer`/`Parser` 造 AST，不新建第二套夹具机制（仓库无 conftest.py）。
"""

from __future__ import annotations

import re

import pytest

from cypyc.analyzer.comptime_evaluator import ComptimeEvaluator, evaluate_comptime
from cypyc.analyzer.scope_analyzer import ScopeAnalyzer
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ASTNode, Parser

# ------------------------------------------------------------------ 共用助手


def _parse(source: str):
    return Parser(Lexer(source).tokenize()).parse()


def _comptime_expr(expr: str):
    """取 `comptime: <expr>` 行内形式里的表达式节点（与 codegen 调 evaluate 的同一形状）。"""
    module = _parse(f"def f() -> int:\n    comptime: {expr}\n    return 1\n")
    stmt = module.body[0].body[0]
    assert stmt.kind == "ComptimeStmt", f"夹具本身没造出 ComptimeStmt：{stmt.kind}"
    return stmt.expr


def _comptime_block(body: str):
    """取 `comptime:` **块形式**的 ComptimeStmt 节点（夹具形状同账本里 G07 的复跑样本）。"""
    body_lines = "".join(f"        {line}\n" for line in body.splitlines())
    module = _parse(f"def f() -> int:\n    comptime:\n{body_lines}    return 1\n")
    stmt = module.body[0].body[0]
    assert stmt.kind == "ComptimeStmt", f"夹具本身没造出 ComptimeStmt：{stmt.kind}"
    return stmt


def _ast_nodes(value, trail: str = "value"):
    """返回值树里所有仍是 AST 节点的对象（BUG-81 契约的判定器）。"""
    found = []
    if isinstance(value, ASTNode):
        found.append((trail, value))
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_ast_nodes(key, f"{trail}.key"))
            found.extend(_ast_nodes(item, f"{trail}[{key!r}]"))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            found.extend(_ast_nodes(item, f"{trail}[{index}]"))
    return found


def _analyze_errors(source: str):
    """走 `cypy_hook.hook.CypyHook._parse_and_analyze` 的同一张脸（scope + type 两通道）。"""
    ast = _parse(source)
    scope = ScopeAnalyzer()
    scope.analyze(ast)
    checker = TypeChecker()
    checker.check(ast)
    return list(scope.errors) + list(checker.errors)


# ============================================================ BUG-81 集合字面量
# 契约（本车道与生成侧的接口）：`evaluate()` 的返回值必须是**纯 Python 值**，
# 否则整体判「求值失败」——半 AST 的值不允许返回。


def test_bug81_list_literal_evaluates_to_pure_python_values():
    value = evaluate_comptime(_comptime_expr("[1, 2]"))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert value == [1, 2], value


def test_bug81_tuple_literal_evaluates_to_pure_python_values():
    value = evaluate_comptime(_comptime_expr("(1, 2)"))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert list(value) == [1, 2], value
    assert isinstance(value, tuple), f"元组字面量应保型：{type(value).__name__}"


def test_bug81_collection_elements_are_evaluated_not_copied():
    """元素里的表达式必须真的算：`["x" + "y", 2]` ⇒ `['xy', 2]`，不是 BinOp 节点。"""
    value = evaluate_comptime(_comptime_expr('["x" + "y", 2]'))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert value == ["xy", 2], value


def test_bug81_nested_collection_literal_is_pure():
    value = evaluate_comptime(_comptime_expr("[[1, 2], 3]"))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert value == [[1, 2], 3], value


def test_bug81_list_concatenation_is_pure():
    value = evaluate_comptime(_comptime_expr("[1, 2] + [3]"))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert value == [1, 2, 3], value


def test_bug81_mixed_scalar_collection_is_pure():
    value = evaluate_comptime(_comptime_expr('[1, "a", True, 2.5]'))
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"
    assert value == [1, "a", True, 2.5], value


def test_bug81_unresolvable_element_is_whole_evaluation_failure():
    """任一元素求不出来 ⇒ 整体求值失败（`evaluate_comptime` 返回 None），不得返回半 AST 值。"""
    expr = _comptime_expr("[nosuch_var, 1]")
    value = evaluate_comptime(expr)
    assert value is None, f"求不出来的元素被当成值返回了：{value!r}"
    with pytest.raises(ValueError):
        ComptimeEvaluator().evaluate(_comptime_expr("[nosuch_var, 1]"))


def test_bug81_nested_unresolvable_element_is_whole_evaluation_failure():
    expr = _comptime_expr("[[1, nosuch_var], 2]")
    assert evaluate_comptime(expr) is None
    with pytest.raises(ValueError):
        ComptimeEvaluator().evaluate(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "6 * 7",
        "1 + 2 * 3",
        '"a" + "b"',
        "True",
        "[1, 2]",
        "(1, 2)",
        "[1, 2] + [3]",
        "[[1, 2], 3]",
        "len([1, 2, 3])",
        "range(3)",
        "[abs(-1), len([1])]",
    ],
)
def test_bug81_evaluate_contract_returns_no_ast_node(expr):
    """契约总锁：这一批形状的求值结果里，任何深度都不许出现 AST 节点对象。"""
    value = evaluate_comptime(_comptime_expr(expr))
    leaked = _ast_nodes(value)
    assert leaked == [], f"{expr!r} 的求值结果外泄 AST 节点：{leaked}"


def test_bug81_control_scalar_comptime_unchanged():
    """对照：今天已经正确的标量 comptime 不得被改坏。"""
    assert evaluate_comptime(_comptime_expr("6 * 7")) == 42
    assert evaluate_comptime(_comptime_expr("1 + 2")) == 3


# ==================================================================== BUG-82
def test_bug82_string_comptime_value_is_correct_on_evaluator_side():
    """BUG-82 的求值侧确认锁：值本身是 `a"b`（一个引号），不带转义残骸。

    产物里出现 `"a"b"` 是生成侧 `f'"{result}"'` 直插所致（不在本车道文件里）。
    """
    value = evaluate_comptime(_comptime_expr('"a" + "\\"" + "b"'))
    assert value == 'a"b', repr(value)
    assert isinstance(value, str), type(value)
    leaked = _ast_nodes(value)
    assert leaked == [], f"返回值里仍有 AST 节点：{leaked}"


def test_bug82_control_int_comptime_on_same_path():
    """对照：同一条 comptime 路径上的整数结果值侧无泄漏。"""
    assert evaluate_comptime(_comptime_expr("1 + 2")) == 3


# ==================================================================== BUG-83
def _not_implemented_error():
    module = __import__("cypyc.analyzer.comptime_evaluator", fromlist=["*"])
    cls = getattr(module, "ComptimeNotImplementedError", None)
    assert cls is not None, (
        "求值侧没有结构化的未实现诊断类型 "
        "cypyc.analyzer.comptime_evaluator.ComptimeNotImplementedError"
    )
    return cls


def test_bug83_block_form_raises_structured_not_implemented_diagnostic():
    """块形式的求值必须给「带行列号 + 未实现」的结构化诊断，而不是内部异常或半求值值。"""
    cls = _not_implemented_error()
    evaluator = ComptimeEvaluator()
    stmt = _comptime_block("[1, 2]")
    with pytest.raises(ValueError) as info:
        evaluator.evaluate(stmt)
    exc = info.value
    assert isinstance(exc, cls), f"抛的不是结构化未实现诊断，而是 {type(exc).__name__}: {exc}"
    text = str(exc)
    assert "未实现" in text, f"诊断文案没有「未实现」措辞：{text}"
    assert re.search(r"at \d+:\d+", text), f"诊断文案没有行列号：{text}"
    assert "__dict__" not in text, f"诊断漏出内部异常文本：{text}"
    assert getattr(exc, "line", 0) > 0, f"诊断没带结构化行号：{text}"


def test_bug83_block_form_evaluate_entry_also_reports_not_implemented():
    """codegen 直接把块形式的语句列表递给 `evaluate()`：这条入口同样必须是结构化诊断。"""
    cls = _not_implemented_error()
    stmt = _comptime_block("[1, 2]")
    assert isinstance(stmt.expr, list), f"块形式的 expr 不是语句列表：{type(stmt.expr)}"
    with pytest.raises(cls) as info:
        ComptimeEvaluator().evaluate(stmt.expr)
    assert "未实现" in str(info.value)


BLOCK_FORM_SOURCE = "def f() -> int:\n" "    comptime:\n" "        [1, 2]\n" "    return 1\n"


def test_bug83_block_form_surfaces_diagnostic_through_analyzer_face():
    """分析面（CLI `--check-only` / transpile 用的同一张脸）：给诊断，不给异常文本。"""
    errors = _analyze_errors(BLOCK_FORM_SOURCE)
    joined = " | ".join(errors)
    assert "__dict__" not in joined, f"内部异常文本外泄给用户：{joined}"
    assert "Traceback" not in joined, f"traceback 外泄给用户：{joined}"
    assert any("未实现" in e for e in errors), f"用户拿不到「未实现」措辞：{errors}"
    assert any(re.search(r"at \d+:\d+", e) for e in errors), f"诊断没有行列号：{errors}"


def test_bug83_inline_form_control_still_clean():
    """对照：同一表达式的行内形式不欠诊断（文档只说块形式未实现）。"""
    source = "def f() -> int:\n    comptime: [1, 2]\n    return 1\n"
    errors = _analyze_errors(source)
    assert errors == [], f"行内形式被误判：{errors}"


# ==================================================================== BUG-84
# 最小集合的取证（只补这两张文档列过的名字，不放开整套 C 类型面）：
#   char  -> SYNTAX/04-pointer-types.md:59 `def allocate_buffer(size: int) -> *char:`
#           （返回位工作例）、:60/:116/:118
#   void  -> SYNTAX/04-pointer-types.md:87 `let void_ptr: *void = malloc(100)`
#   long/short/unsigned -> SYNTAX/*.md 里一次都没出现 ⇒ 不进集合


def test_bug84_documented_char_pointer_return_annotation_resolves():
    """本单主张的那一处不一致：文档工作例的 `-> *char` 返回位不得判 Undefined name。"""
    source = "def my_strcpy(dst: *char, src: *char) -> *char:\n    return dst\n"
    errors = _analyze_errors(source)
    assert errors == [], f"文档工作例的 *char 返回位被拒：{errors}"


def test_bug84_documented_void_pointer_name_resolves():
    source = "def f(p: *void) -> *void:\n    return p\n"
    errors = _analyze_errors(source)
    assert errors == [], f"文档 04:87 的 *void 被拒：{errors}"


def test_bug84_control_documented_pointer_names_stay_clean():
    """对照：今天已经通过的 *int / *double 返回位与 let 位。"""
    assert _analyze_errors("def f(p: *int) -> *int:\n    return p\n") == []
    assert _analyze_errors("def f(p: *double) -> *double:\n    return p\n") == []
    assert _analyze_errors("let p: *char = malloc(10)\n") == []


def test_bug84_undocumented_c_integer_names_stay_undefined():
    """边界锁（本单不主张）：`long`/`short`/`unsigned` 在 SYNTAX/*.md 里查无此名，
    所以它们仍应停在 Undefined name——不能顺手把 C 整型面全放开。"""
    for name in ("long", "short", "unsigned"):
        errors = _analyze_errors(f"def f(p: *{name}) -> *{name}:\n    return p\n")
        assert any(
            "Undefined name" in e for e in errors
        ), f"{name} 未见于 SYNTAX/*.md，却被放行了：{errors}"


def test_bug84_both_analyzer_channels_agree_on_pointer_element_name():
    """同一符号两处不一致的正面锁：scope 与 type 两条通道对 `char` 的判定必须同向。"""
    source = "def f(p: *char) -> *char:\n    return p\n"
    ast = _parse(source)
    scope = ScopeAnalyzer()
    scope.analyze(ast)
    checker = TypeChecker()
    checker.check(ast)
    assert scope.errors == [], scope.errors
    assert checker.errors == [], checker.errors
