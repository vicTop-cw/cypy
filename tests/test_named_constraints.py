"""命名联合类型约束 `constraint Name = A | B`（SYNTAX/33 §2）的永久回归测试。

与 `Find_BUG/audit_2026q3/feat_constraint_*.py` 同源，但那些探针是**本轮的一次性裁判**
（只读、判 exit 码），本文件是长期护栏：条款一旦在未来某轮被改坏，这里立刻红。

钉住的条款：

* C-1.2/C-1.3 成员必须是类型名；去重后按声明顺序保留（`tests` 里是 `_expand_constraint_members`
  的返回值顺序）
* C-2.1 约束**不是类型**：值位置（`let x: Numeric` / 形参 / `as` / `list<Numeric>`）硬报错
* C-2.2 满足关系走唯一入口 `_is_subtype`（INV-2）
* C-2.3 传递展开：成员是另一个已声明 constraint 时并上它的成员
* C-2.4 环检测必须指名路径 `A -> B -> A`
* C-2.5 未定义成员仍报错（展开只吃「本模块已声明的 constraint」，不是把未知名字悄悄丢掉）
* C-4.1 命名界 ⟺ 内联联合界（判定分区 + 产物只差一行注释）
* C-5.1..C-5.5 诊断模板：真实 `line:col`（禁止 `at 0:0`）、摊开成员、指名推断后的实参类型、
  保留 `does not satisfy constraint '<name>'` 子串、同一调用点只报第一条
* C-7.1 / 裁决 D-4 `constraint`/`subtype` 进 `KEYWORDS`，`dispatch` **不进**
* §5 的 codegen 行：只发注释 `# constraint Numeric = int | float`，**不发** `ctypedef`

所有输入都是内存里的字符串（`CypyHook().transpile` 不落盘），不写 `examples/`、不碰 `output/`。
"""

import os
import re

import pytest

from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_hook.hook import CypyHook

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECL = "constraint Numeric = int | float\n"
CALL = "def clamp<T: Numeric>(v: T) -> T:\n    return v\n\nprint(clamp(%s))\n"


def _parse(source):
    return Parser(Lexer(source).tokenize()).parse()


def _check(source):
    """解析 + 类型检查（诊断读 `tc.errors`）。"""
    tc = TypeChecker()
    tc.check(_parse(source))
    return tc


def _gen(source):
    return CythonGenerator().generate(_parse(source))


def _transpile(source):
    """全管线（preprocessor→lexer→parser→scope→type→pointer→codegen），纯内存。"""
    return CypyHook().transpile(source)


# --------------------------------------------------------------------------- #
# C-1 / C-7.1：语法与关键字化
# --------------------------------------------------------------------------- #

class TestConstraintDeclarationLayer:

    def test_declaration_parses_to_constraintdef_with_members(self):
        module = _parse(DECL + "print(1)\n")
        assert [s.kind for s in module.body] == ['ConstraintDef', 'ExprStmt']
        node = module.body[0]
        assert node.name == 'Numeric'
        assert [m.id for m in node.members] == ['int', 'float']

    def test_constraint_and_subtype_are_keywords_dispatch_is_not(self):
        """裁决 D-4：`constraint`/`subtype` 硬保留；`dispatch` 本轮不进（deferred）。"""
        assert 'constraint' in Lexer.KEYWORDS
        assert 'subtype' in Lexer.KEYWORDS
        assert 'dispatch' not in Lexer.KEYWORDS, (
            "dispatch 进 KEYWORDS 会留下一个可词法却无人解析的悬空关键字（§7.1 D-4）")

    def test_constraint_as_plain_identifier_is_now_a_syntax_error(self):
        """C-7.2 接受破坏性：关键字化后 `constraint = 5` 必须报错而不是静默吞（B1/D3）。"""
        with pytest.raises(ValueError, match="constraint"):
            _parse("constraint = 5\nprint(constraint)\n")

    def test_type_alias_still_parses_as_typealias(self):
        """控制组：`type` 别名没被关键字化改动（C-3.2 两套并存的前提）。"""
        module = _parse("type N = int | float\nprint(1)\n")
        assert module.body[0].kind == 'TypeAlias'


# --------------------------------------------------------------------------- #
# C-2.3 传递展开（含 C-1.3 去重保序）与 C-2.4 环检测
# --------------------------------------------------------------------------- #

class TestTransitiveFlattening:

    def test_nested_constraint_members_are_flattened(self):
        """C-2.3：`constraint Small = Numeric | str` 的成员是 int, float, str。"""
        tc = _check(DECL + "constraint Small = Numeric | str\n")
        members, cycle = tc._expand_constraint_members('Small')
        assert cycle is None
        assert members == ['int', 'float', 'str'], members

    def test_flattening_dedupes_and_keeps_declaration_order(self):
        """C-1.3：去重后按**声明顺序**保留 —— 嵌套成员的顺序也不得反转。"""
        tc = _check("constraint A = float | int\nconstraint B = A | float | str\n")
        assert tc._expand_constraint_members('B') == (['float', 'int', 'str'], None)

    def test_flattened_constraint_accepts_every_member_at_call_site(self):
        """展开后的名单是真的界：int / float / str 三个实参都得放行。

        这正是 `feat_constraint_02` 的 C-2.3 用例**按规范该有的样子**——那条探针忘了把
        `DECL` 拼进语料，于是 `Numeric` 在本模块里根本没声明（见本轮交付报告）。
        """
        src = (DECL + "constraint Small = Numeric | str\n"
               + CALL.replace("Numeric", "Small"))
        for arg in ("1", "1.5", "'a'"):
            res = _transpile(src % arg)
            assert res.success, (arg, res.errors)

    def test_violation_diagnostic_prints_flattened_members(self):
        """C-2.3 × C-5.2：`(allowed: ...)` 必须是摊平后的成员表，而不是嵌套约束名。"""
        tc = _check("constraint Numeric = int | float\n"
                    "constraint Small = Numeric | bool\n"
                    "def clamp<T: Small>(v: T) -> T:\n    return v\n\n"
                    "print(clamp('a'))\n")
        assert len(tc.errors) == 1, tc.errors
        assert "(allowed: int | float | bool)" in tc.errors[0], tc.errors[0]
        assert "Numeric" not in tc.errors[0].split("(allowed:")[1], tc.errors[0]

    def test_cycle_names_the_path(self):
        """C-2.4：`A = B | int` / `B = A | str` 必须指名环路径（且展开不得死循环）。"""
        tc = _check("constraint A = B | int\nconstraint B = A | str\n")
        assert any("circular constraint definition: A -> B -> A" in e for e in tc.errors), tc.errors
        assert not any("references undefined type" in e for e in tc.errors), tc.errors

    def test_self_reference_is_a_cycle_too(self):
        tc = _check("constraint Bad = int | Bad\n")
        assert any(e.startswith("circular constraint definition: Bad -> Bad")
                   for e in tc.errors), tc.errors

    def test_flattening_survives_bound_check_after_cycle(self):
        """有环时**不得**退化成「静默按未展开的名字比」——那是 B2 的假报错形态。"""
        tc = _check("constraint A = B | int\nconstraint B = A | str\n"
                    "def f<T: A>(v: T) -> T:\n    return v\n\nprint(f(1))\n")
        assert any("circular constraint definition" in e for e in tc.errors), tc.errors


# --------------------------------------------------------------------------- #
# C-1.2 / C-2.5：成员合法性
# --------------------------------------------------------------------------- #

class TestConstraintMemberValidity:

    def test_undefined_member_is_rejected(self):
        """C-2.5：未知名字**不能**被展开逻辑悄悄吞掉。"""
        tc = _check("constraint Q = Intg | str\n")
        assert any("references undefined type 'Intg'" in e for e in tc.errors), tc.errors
        assert any("not a builtin, class, struct, enum, subtype or constraint" in e
                   for e in tc.errors), tc.errors

    def test_pointer_member_is_not_a_type_name(self):
        """C-1.2：成员只允许「类型名 [+ 实参]」。"""
        tc = _check("constraint P = *int | str\n")
        assert any("is not a type name" in e and "'*int'" in e for e in tc.errors), tc.errors

    def test_user_declared_class_member_is_accepted(self):
        tc = _check("class Pet:\n    pass\n\nconstraint Animals = Pet | str\n")
        assert tc.errors == [], tc.errors


# --------------------------------------------------------------------------- #
# C-2.1：约束是界，不是类型
# --------------------------------------------------------------------------- #

VALUE_POSITION = [
    pytest.param("let x: Numeric = 1", DECL + "\nlet x: Numeric = 1\nprint(x)\n", id="let"),
    pytest.param("def f(v: Numeric)", DECL + "\ndef f(v: Numeric) -> int:\n    return 1\n", id="param"),
    pytest.param("as Numeric", DECL + "\nlet y = 1 as Numeric\nprint(y)\n", id="as"),
    pytest.param("list<Numeric>", DECL + "\nlet z: list<Numeric> = [1]\nprint(z)\n", id="container"),
]


class TestConstraintIsNotAType:

    @pytest.mark.parametrize("label, source", VALUE_POSITION)
    def test_value_position_is_rejected_naming_it_a_constraint(self, label, source):
        errors = _check(source).errors
        assert any("Numeric" in e and "is a constraint, not a type" in e for e in errors), \
            "%s -> %r" % (label, errors)
        # 不得同时伪造出「int 不满足 Numeric」那种假报错（实测基线 B2）
        assert not any("does not satisfy" in e for e in errors), errors

    def test_alias_and_constraint_coexist_under_different_names(self):
        """C-3.2：`type` 走值位置、`constraint` 走界位置，两张表互不干扰。"""
        res = _transpile("type Numeric = int | float\n"
                         "constraint Small = int | float\n"
                         "def pick<T: Small>(a: T, b: T) -> T:\n    return a\n\n"
                         "let v: Numeric = 2\nprint(v)\nprint(pick(1, 2))\n")
        assert res.success, res.errors

    def test_same_name_for_alias_and_constraint_is_rejected(self):
        """C-3.1：`constraint`/`type` 共用一个模块级名字空间，后声明者被拒。

        重名护栏在 `ScopeAnalyzer`（`_user_def_kinds`）里，所以这条走全管线，
        与探针 feat_constraint_03 同源。
        """
        for label, source in (
                ("constraint-then-alias", DECL + "type Numeric = int | float\nprint(1)\n"),
                ("alias-then-constraint",
                 "type Numeric = int | float\n" + DECL + "print(1)\n"),
                ("constraint-then-constraint", DECL + DECL + "print(1)\n")):
            errors = _transpile(source).errors
            assert any("redefinition" in e or "already declared" in e for e in errors), \
                "%s -> %r" % (label, errors)


# --------------------------------------------------------------------------- #
# C-5：诊断模板
# --------------------------------------------------------------------------- #

PROGRAM = (DECL + "\n"
           "def clamp<T: Numeric>(v: T) -> T:\n"
           "    return v\n"
           "\n"
           "let bad_value = 'oops'\n"
           "print(clamp(bad_value))\n")       # 调用点在第 7 行


class TestViolationDiagnostic:

    def test_template_fields(self):
        """C-5.2/C-5.3/C-5.4：模板字段逐个核对（正则形状与探针 feat_constraint_04 一致）。"""
        errors = _check(PROGRAM).errors
        assert len(errors) == 1, errors
        msg = errors[0]
        assert re.search(r"constraint violation:.*type 'str' does not satisfy constraint "
                         r"'Numeric'.*allowed: int \| float", msg, re.S), msg
        assert "does not satisfy constraint 'Numeric'" in msg, msg   # C-5.4 可 grep 子串
        assert "in call to 'clamp'" in msg, msg

    def test_position_is_a_real_line_and_column(self):
        """C-5.1：`at 0:0` 让 IDE 与增量编译无法定位，直接拒绝。"""
        errors = _check(PROGRAM).errors
        assert errors and "at 0:0" not in errors[0], errors
        m = re.search(r"reported at line (\d+), col (\d+)", errors[0])
        assert m, errors[0]
        assert (int(m.group(1)), int(m.group(2))) == (7, 7), errors[0]

    def test_actual_type_is_inferred_not_object(self):
        """C-5.3：`{actual}` 是推断后的类型名。"""
        errors = _check(DECL + "def clamp<T: Numeric>(v: T) -> T:\n    return v\n\n"
                               "print(clamp([1, 2]))\n").errors
        assert any("type 'list'" in e for e in errors), errors

    def test_one_diagnostic_per_call_site(self):
        """C-5.5：两个实参同时违例只报第一条。"""
        errors = _check(DECL + "def two<T: Numeric>(a: T, b: T) -> T:\n    return a\n\n"
                               "print(two('x', 'y'))\n").errors
        assert len([e for e in errors if "onstraint" in e]) == 1, errors


# --------------------------------------------------------------------------- #
# C-4.1 / §6.1：命名界 ⟺ 内联联合界
# --------------------------------------------------------------------------- #

INLINE = "def clamp<T: int | float>(v: T) -> T:\n    return v\n\nprint(clamp(%s))\n"


class TestNamedVersusInlineEquivalence:

    @pytest.mark.parametrize("arg", ["1", "1.5", "'a'", "True", "[1, 2]"])
    def test_same_accept_reject_partition(self, arg):
        named = _transpile(DECL + CALL % arg)
        inline = _transpile(INLINE % arg)
        assert named.success == inline.success, (
            arg, named.errors, inline.errors)
        assert bool(named.errors) == bool(inline.errors), (arg, named.errors, inline.errors)

    def test_diagnostic_template_differs_only_by_the_name_column(self):
        """C-4.1：同一个模板，只差「约束名那一栏」（位置差异来自语料多了一行声明）。"""
        named = _check(DECL + CALL % "'a'").errors[0]
        inline = _check(INLINE % "'a'").errors[0]
        normalise = lambda s: re.sub(
            r"constraint '[^']*'|line \d+, col \d+", lambda m: "<X>", s)
        assert normalise(named) == normalise(inline), (named, inline)

    def test_artifacts_differ_only_by_the_constraint_comment(self):
        """C-4.1 的产物侧：命名界的 .pyx 与内联界的 .pyx 只差那一行注释。"""
        named = _gen(DECL + CALL % "1")
        inline = _gen(INLINE % "1")
        without_comment = [
            line for line in named.splitlines()
            if line.strip() != "# constraint Numeric = int | float"]
        assert without_comment == inline.splitlines()


# --------------------------------------------------------------------------- #
# §5 的 codegen 行：约束只发注释
# --------------------------------------------------------------------------- #

class TestConstraintCodegen:

    def test_only_a_comment_is_emitted(self):
        code = _gen(DECL + CALL % "1")
        assert "# constraint Numeric = int | float" in code
        for line in code.splitlines():
            stripped = line.strip()
            if 'Numeric' not in stripped:
                continue
            assert stripped.startswith("#"), (
                "约束不是类型，codegen 里除了注释出现它的名字就是伪造可用性：%r" % line)

    def test_no_ctypedef_for_constraint(self):
        code = _gen(DECL + "constraint Wide = Numeric | str\n")
        assert not re.search(r"ctypedef.*Numeric|ctypedef.*Wide", code), code
        assert "# constraint Wide = Numeric | str" in code

    def test_shipped_example_transpiles_clean(self):
        """调用面：`examples/constraint_numeric.cypy` 必须全管线无诊断。"""
        path = os.path.join(REPO_ROOT, "examples", "constraint_numeric.cypy")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        res = _transpile(source)
        assert res.success, res.errors
        assert "# constraint Numeric = int | float | double" in res.cython_code
        assert "# constraint Wide = Numeric | str" in res.cython_code
