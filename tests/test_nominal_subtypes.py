"""名义子类型 `subtype Name <: Base`（SYNTAX/33 §3）的永久回归测试。

与 `Find_BUG/audit_2026q3/feat_subtype_0{1..5}.py` 同源；那些探针是本轮的一次性裁判
（只读、判 exit 码），本文件是长期护栏：S-1..S-7 的任何一层在未来被改坏，这里立刻红。

写判据的纪律（沿用 `tests/test_named_constraints.py`）：**能写等价性就不写自证**。
「subtype 已实现」这种断言只会重复实现者的假设，而

* 「subtype 版与直接写基类型的版本产物**逐字节相同**」（S-4.1）
* 「subtype 版与 `type` 别名版在**上转**上同判定、在**下转**上必须不同判定」（S-3.4）
* 「命名界与把成员摊平写成内联界同判定」（S-2.3 联动 C-4.1）

三条都是**可证伪**的：任何一半实现退化（parser 能吃、analyzer 无视、codegen 少发一行）
都会立刻打破其中一条。

钉住的条款：S-1.1/S-1.2/S-1.3/S-1.4、S-2.1/S-2.2/S-2.3、S-3.1/S-3.2/S-3.2.1/S-3.3/S-3.4、
S-4.1..S-4.4、S-5.1/S-5.2/S-5.3、S-6、S-7.1/S-7.2/S-7.3/S-7.4、C-3.1、C-7.1、INV-1/INV-2。

所有输入都是内存里的字符串（`CypyHook().transpile` 不落盘），不写 `examples/`、不碰 `output/`。
"""

import os
import re

import pytest

from cypyc.analyzer.type_checker import TypeChecker, Type
from cypyc.codegen.cython_generator import CythonGenerator
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser
from cypy_hook.hook import CypyHook

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECL = "subtype Meter <: float\n"
PAIR = ("subtype Meter <: float\n"
        "subtype Kilometer <: float\n")


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


def _code(source):
    res = _transpile(source)
    assert res.success, res.errors
    return res.cython_code


def _strip_timestamps(code):
    """产物里的 `__generated_at__` / `__compile_time__` 每次运行都不同，比对前先剔除。"""
    return [ln for ln in code.splitlines()
            if not ln.startswith(('__generated_at__', '__compile_time__'))]


# --------------------------------------------------------------------------- #
# S-1 / C-7.1：词法与语法层
# --------------------------------------------------------------------------- #

class TestSubtypeDeclarationLayer:

    def test_subtype_is_a_hard_keyword_and_dispatch_still_is_not(self):
        """裁决 D-4：本轮只有 `constraint`/`subtype` 进 KEYWORDS。"""
        assert 'subtype' in Lexer.KEYWORDS
        assert 'constraint' in Lexer.KEYWORDS
        assert 'dispatch' not in Lexer.KEYWORDS, (
            "dispatch 进 KEYWORDS 会得到一个可词法、无人解析的悬空关键字（§7.1 D-4）")

    def test_declaration_parses_to_a_single_subtypedef(self):
        module = _parse(DECL + "print(1)\n")
        assert [s.kind for s in module.body] == ['SubtypeDef', 'ExprStmt']
        node = module.body[0]
        assert node.name == 'Meter'
        assert (node.base.kind, node.base.id) == ('Name', 'float')

    def test_missing_colon_arrow_is_a_syntax_error_not_a_swallow(self):
        """S-1.4：`subtype Meter` 过去被整段吞成两个裸 ExprStmt，现在必须硬失败。"""
        with pytest.raises(ValueError, match="subtype"):
            _parse("subtype Meter\ndef f() -> int:\n    return 1\n")

    @pytest.mark.parametrize("source, needle", [
        ("subtype Box<T> <: T\n", "deferred"),          # S-1.1 无泛型参数
        ("subtype N <: int | float\n", "union"),        # S-1.2 基类型必须单个
    ])
    def test_banned_declaration_forms_are_refused_by_name(self, source, needle):
        errors = _transpile(source).errors
        assert errors, source
        assert any(needle in e for e in errors), errors

    def test_type_alias_still_parses_as_typealias(self):
        """控制组：`type` 别名没被 subtype 改动（S-3.4 的对照物必须还活着）。"""
        assert _parse("type Meter = float\nprint(1)\n").body[0].kind == 'TypeAlias'


# --------------------------------------------------------------------------- #
# INV-1 / S-2.2：`Type` 表示与 `_is_subtype` 唯一入口
# --------------------------------------------------------------------------- #

class TestTypeRepresentationInvariants:

    def test_subtype_type_carries_only_a_name(self):
        """INV-1：名字进 `Type` 时只能是 `Type.name`，其余字段不得被塞进成员。"""
        tc = _check(DECL)
        ty = tc.type_map['Meter']
        assert ty.name == 'Meter'
        assert ty.union_members == [] and ty.generic_params == []
        assert not ty.is_pointer and not ty.is_ref

    def test_edge_lives_in_inheritance_map_not_in_a_second_table(self):
        """S-2.2：边并入 `inheritance_map`（复用现成的那条判定分支）。"""
        tc = _check(PAIR + "subtype CentiMeter <: Meter\n")
        assert 'Meter' in tc.inheritance_map['CentiMeter']
        assert 'float' in tc.inheritance_map['CentiMeter']   # S-7.1 传递闭包
        # R1 不变式：`Type.__eq__` 仍然比较 union_members，subtype 没把它冲淡
        assert Type('object', union_members=[Type('int')]) != Type(
            'object', union_members=[Type('str')])

    def test_assignability_is_decided_by_is_subtype_only(self):
        """INV-2：断言方向表就是 `_is_subtype` 的取值，而不是另一套字符串比较。"""
        tc = _check(DECL)
        assert tc._is_subtype(Type('Meter'), Type('float'))
        assert not tc._is_subtype(Type('float'), Type('Meter'))
        assert tc._is_subtype(Type('Meter'), Type('object'))


# --------------------------------------------------------------------------- #
# S-3.1..S-3.4：可赋值方向 —— 与 `type` 别名的**等价/差异**矩阵
# --------------------------------------------------------------------------- #

UPCAST = "%slet m: %s = 2.5\nlet v: float = m\nprint(v)\n"


class TestAssignabilityDirectionVersusAlias:

    @pytest.mark.parametrize("label, decl, name", [
        ("subtype", DECL, 'Meter'),
        ("alias", "type Meter = float\n", 'Meter'),
    ])
    def test_upcast_agrees_between_subtype_and_alias(self, label, decl, name):
        """S-3.1：上转这一格二者必须**同样**放行 —— 否则 subtype 是凭空变严。"""
        res = _transpile(UPCAST % (decl, name))
        assert res.success, (label, res.errors)

    def test_downcast_differs_between_subtype_and_alias(self):
        """S-3.4 的核心证据：别名双向静默通过，subtype 必须拒绝下转。

        两条语料只差声明那一行（`type` ↔ `subtype`），其余完全相同 ——
        于是「判定不同」只能来自名义身份本身，不来自语料差异。
        """
        body = "let f: float = 2.5\nlet m: Meter = f\nprint(m)\n"
        alias = _transpile("type Meter = float\n" + body)
        assert alias.success, (alias.errors, "别名若也拒绝，就不是「透明」了")
        sub = _transpile(DECL + body)
        assert not sub.success, sub.errors
        assert any("nominal" in e for e in sub.errors), sub.errors      # S-3.2.1 文案
        assert any("as Meter" in e for e in sub.errors), sub.errors     # 指名替代写法

    def test_explicit_as_is_accepted_and_is_a_codegen_noop(self):
        """S-3.2 + S-4.4：`as` 只消耗一次编译期显式转换，产物里没有运行时校验。"""
        res = _transpile(DECL + "let f: float = 1.5\nlet m: Meter = f as Meter\n"
                                "print(m)\n")
        assert res.success, res.errors
        assert not [ln for ln in res.cython_code.splitlines() if 'Meter' in ln]

    def test_sibling_subtypes_are_not_interchangeable(self):
        """S-3.3：兄弟直转拒绝，两步经基类型放行 —— 二者在同一条语料里对照。"""
        direct = _transpile(PAIR + "let m: Meter = 1.0\n"
                                   "let k: Kilometer = m as Kilometer\nprint(k)\n")
        assert not direct.success, direct.errors
        assert any("mutually" in e for e in direct.errors), direct.errors
        two_step = _transpile(PAIR + "let m: Meter = 1.0\nlet k: Kilometer = "
                                     "(m as float) as Kilometer\nprint(k)\n")
        assert two_step.success, two_step.errors

    def test_chain_direction_matrix(self):
        """S-7.1：`A <: B <: float` 上转一路隐式，回到 A 仍需 `as`。"""
        chain = "subtype A <: B\nsubtype B <: float\n"
        up = _transpile(chain + "let a: A = 1.0\nlet b: B = a\nlet f: float = b\n"
                                "print(f)\n")
        assert up.success, up.errors
        down = _transpile(chain + "let f: float = 1.0\nlet a: A = f\nprint(a)\n")
        assert not down.success, down.errors
        assert any("as A" in e for e in down.errors), down.errors

    def test_return_position_uses_the_same_direction_table(self):
        """方向表在 `let` 与 `return` 两处必须一致（同一入口，INV-2）。"""
        up = _transpile(DECL + "def use(m: Meter) -> float:\n    return m\n\n"
                              "let m: Meter = 1.5\nprint(use(m))\n")
        assert up.success, up.errors
        down = _transpile(DECL + "def make() -> Meter:\n    let f: float = 1.5\n"
                                 "    return f\n\nprint(make())\n")
        assert not down.success, down.errors
        assert any("nominal" in e for e in down.errors), down.errors


# --------------------------------------------------------------------------- #
# S-2.3：与 `constraint` 的联动
# --------------------------------------------------------------------------- #

class TestConstraintInterplay:

    def test_subtype_satisfies_a_bound_on_its_base(self):
        res = _transpile("constraint F = float\n" + DECL
                         + "def keep<T: F>(v: T) -> T:\n    return v\n\n"
                           "let m: Meter = 1.0\nprint(keep(m))\n")
        assert res.success, res.errors

    def test_base_does_not_satisfy_a_bound_on_the_subtype(self):
        """名义**不放宽**：`constraint M = Meter` 的成员是身份，不是 float。"""
        res = _transpile("constraint M = Meter\n" + DECL
                         + "def keep<T: M>(v: T) -> T:\n    return v\n\n"
                           "let f: float = 1.0\nprint(keep(f))\n")
        assert not res.success, res.errors
        assert any("(allowed: Meter)" in e for e in res.errors), res.errors

    def test_named_and_flattened_bounds_agree_on_a_subtype_argument(self):
        """C-4.1 × S-2.3：命名界与内联界对同一个 subtype 实参必须同判定。"""
        named = _transpile("constraint F = float\n" + DECL
                           + "def keep<T: F>(v: T) -> T:\n    return v\n\n"
                             "let m: Meter = 1.0\nprint(keep(m))\n")
        inline = _transpile(DECL + "def keep<T: float>(v: T) -> T:\n    return v\n\n"
                                   "let m: Meter = 1.0\nprint(keep(m))\n")
        assert named.success == inline.success, (named.errors, inline.errors)


# --------------------------------------------------------------------------- #
# S-4：运行时表示零变化
# --------------------------------------------------------------------------- #

class TestZeroRuntimeRepresentation:

    def test_artifact_is_identical_to_writing_the_base_type(self):
        """S-4.1 的最强形式：把 `Meter` 全换成 `float` 后产物**逐字节**相同。"""
        with_subtype = _code(DECL + "let m: Meter = 1.5\nprint(m)\n")
        with_base = _code("let m: float = 1.5\nprint(m)\n")
        assert _strip_timestamps(with_subtype) == _strip_timestamps(with_base)

    def test_no_type_object_or_registry_is_emitted(self):
        code = _code(PAIR + "subtype CentiMeter <: Meter\nlet m: Meter = 1.5\nprint(m)\n")
        assert not re.search(r"ctypedef.*Meter|cdef class Meter|Meter\s*=\s*type\(", code)
        assert not [ln for ln in code.splitlines() if 'Meter' in ln]

    def test_runtime_identity_is_the_base_name(self):
        """S-4.2：`type(m).__name__` 就是基类型 —— 这是 subtype 与 struct 的分界线。"""
        assert "type(m).__name__" not in _code(DECL + "let m: Meter = 1.5\nprint(m)\n")

    @pytest.mark.parametrize("expr", ["isinstance(m, Meter)", "isinstance(m, Kilometer)"])
    def test_isinstance_on_a_subtype_is_a_compile_time_error(self, expr):
        res = _transpile(PAIR + "let m: Meter = 1.5\nif %s:\n    print('yes')\n" % expr)
        assert not res.success, res.errors
        assert any("no runtime type object" in e for e in res.errors), res.errors
        # S-4.3 要求指名替代方案（用基类型），而不是只说「不行」
        assert any("'float'" in e and "struct" in e for e in res.errors), res.errors

    def test_match_type_pattern_is_refused_by_the_same_rule(self):
        """S-4.3 末条：`case Meter x:` 与 isinstance 同源，同一条编译期拒绝。"""
        res = _transpile(DECL + "let m: Meter = 1.5\nmatch m:\n"
                                "    case Meter x:\n        print(1)\n")
        assert not res.success, res.errors
        assert any("type pattern" in e and "no runtime type object" in e
                   for e in res.errors), res.errors

    def test_isinstance_on_the_base_still_works(self):
        res = _transpile(DECL + "let m: Meter = 1.5\nprint(isinstance(m, float))\n")
        assert res.success, res.errors


# --------------------------------------------------------------------------- #
# S-5：trait / impl / duck 边界
# --------------------------------------------------------------------------- #

TRAIT = ("trait Show:\n    def show(self) -> str\n\n"
         "struct Dollar:\n    amount: int\n\n"
         "impl Show for Dollar:\n    pass\n\n")
DUCK = "meta:\n    duck Numeric:\n        a + b -> Self\n\n"


class TestTraitDuckBoundary:

    def test_impl_on_a_subtype_is_refused_naming_the_runtime_reason(self):
        """S-5.1 / 裁决 D-6：拒绝理由是 `type(x).__name__` 那张表挂不住 subtype。"""
        res = _transpile(TRAIT + "subtype Cent <: Dollar\n"
                                 "impl Show for Cent:\n    pass\n\nprint(1)\n")
        assert not res.success, res.errors
        assert any("runtime" in e and "Dollar" in e for e in res.errors), res.errors

    def test_trait_bound_does_not_pick_a_subtype_up_for_free(self):
        """S-5.2：没有 `impl` 记录就不满足 trait 界，即使它 <: int。"""
        res = _transpile(TRAIT + "subtype Cent <: int\n"
                                 "def render<T: Show>(v: T) -> str:\n    return 'x'\n\n"
                                 "let c: Cent = 5\nprint(render(c))\n")
        assert not res.success, res.errors
        assert any("Show" in e for e in res.errors), res.errors

    def test_duck_bound_agrees_between_subtype_and_base(self):
        """S-5.3 × S-2.1 结构同构：duck 界对 `Cents <: int` 的判定 == 对 `int` 的判定。

        对照组（str）同一条目必须仍然拒绝，否则「相等」只是因为什么都放行。
        """
        def duck_program(decl, ty, literal):
            return (DUCK + decl
                    + "def add<T: Numeric>(a: T, b: T) -> T:\n    return a\n\n"
                      "let x: %s = %s\nprint(add(x, x))\n" % (ty, literal))
        as_subtype = _transpile(duck_program("subtype Cents <: int\n", 'Cents', '1'))
        as_base = _transpile(duck_program("", 'int', '1'))
        as_str = _transpile(duck_program("", 'str', "'a'"))
        assert as_subtype.success and as_base.success, (as_subtype.errors,
                                                        as_base.errors)
        assert not as_str.success, as_str.errors      # 对照：同一条目对 str 仍拒绝


# --------------------------------------------------------------------------- #
# S-1.2 / S-1.3 / S-7.2 / S-7.4：声明层的定向诊断
# --------------------------------------------------------------------------- #

class TestSubtypeDefinitionDiagnostics:

    @pytest.mark.parametrize("source, needles", [
        ("subtype Meter <: Flaot\nprint(1)\n", ["unknown base type 'Flaot'"]),  # S-7.3
        ("trait Show:\n    def show(self) -> str\n\nsubtype M <: Show\nprint(1)\n",
         ["trait"]),                                                            # S-1.2
        ("type Num = float\nsubtype M <: Num\nprint(1)\n", ["alias"]),          # D-5
        ("constraint C = int | float\nsubtype M <: C\nprint(1)\n", ["constraint"]),
        ("subtype M <: object\nprint(1)\n", ["object"]),                        # S-1.2
        ("subtype M <: list<int>\nprint(1)\n", ["generic"]),                    # S-1.2
        ("subtype X <: X\nprint(1)\n", ["circular subtype definition: X -> X"]),  # S-1.3
        ("subtype A <: B\nsubtype B <: A\nprint(1)\n",
         ["circular subtype definition: A -> B -> A"]),                          # S-1.3
        ("".join("subtype S%d <: S%d\n" % (i, i - 1) for i in range(2, 11))
         + "subtype S1 <: float\nprint(1)\n", ["too deep (limit 8)"]),           # S-7.2
    ])
    def test_bad_declaration_is_a_compile_time_error_with_a_named_reason(self,
                                                                        source, needles):
        res = _transpile(source)
        assert not res.success, (source, res.errors)
        for needle in needles:
            assert any(needle in e for e in res.errors), (needle, res.errors)

    @pytest.mark.parametrize("source", [
        "class Meter:\n    pass\n\nsubtype Meter <: float\nprint(1)\n",      # S-7.4
        "type Meter = float\n\nsubtype Meter <: float\nprint(1)\n",          # C-3.1
        "subtype Meter <: float\nsubtype Meter <: int\nprint(1)\n",          # S-7.4
        "constraint Meter = int | float\nsubtype Meter <: float\nprint(1)\n",  # C-3.1
    ])
    def test_one_declaration_namespace(self, source):
        res = _transpile(source)
        assert not res.success, res.errors
        assert any("redefinition" in e or "already declared" in e
                   for e in res.errors), res.errors

    @pytest.mark.parametrize("base, prelude", [
        ('Money', "class Money:\n    pass\n\n"),
        ('Dollar', "struct Dollar:\n    amount: int\n\n"),
        ('Color', "enum Color:\n    RED = 1\n    BLUE = 2\n\n"),
    ])
    def test_allowed_base_kinds(self, base, prelude):
        """S-1.2 白名单：class / struct / enum 都能作基类型（控制组，防过度收紧）。"""
        res = _transpile(prelude + "subtype M <: %s\nprint(1)\n" % base)
        assert res.success, (base, res.errors)


# --------------------------------------------------------------------------- #
# 调用面：examples/ 里的语料必须全管线无诊断
# --------------------------------------------------------------------------- #

class TestShippedExample:

    def test_example_transpiles_clean(self):
        path = os.path.join(REPO_ROOT, "examples", "subtype_units.cypy")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        res = _transpile(source)
        assert res.success, res.errors

    def test_example_artifact_mentions_no_subtype_name(self):
        """产物里连 `Meter` 都不该出现（S-4.1 在真实语料上的同一判据）。"""
        path = os.path.join(REPO_ROOT, "examples", "subtype_units.cypy")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        code = _transpile(source).cython_code
        assert not [ln for ln in code.splitlines()
                    if 'Meter' in ln or 'Kilometer' in ln or 'OrderId' in ln
                    or 'CentiMeter' in ln], \
            [ln for ln in code.splitlines() if 'eter' in ln or 'OrderId' in ln]
