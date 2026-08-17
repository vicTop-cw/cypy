"""Duck 约束语法完整测试套件

测试覆盖:
1. Lexer: DUCK 关键字识别
2. Parser: 各种约束类型的解析
3. Type checker: 编译期检查（循环依赖、重复定义、Self 验证）
4. Codegen: 代码生成正确性
5. Edge cases: 边界场景
6. Integration: 端到端编译
"""
import pytest
from cypyc.parser.lexer import Lexer, TokenType
from cypyc.parser.parser import Parser, DuckDef, DuckRequirement, MetaBlock
from cypyc.analyzer.type_checker import TypeChecker
from cypyc.codegen.cython_generator import CythonGenerator


# ========== Lexer 测试 ==========

class TestDuckLexer:
    """测试 lexer 中的 duck 关键字识别"""

    def test_duck_keyword(self):
        """duck 关键字被正确识别为 DUCK token"""
        lexer = Lexer("duck Comparable:")
        tokens = list(lexer.tokenize())
        assert tokens[0].type == TokenType.DUCK
        assert tokens[0].value == "duck"

    def test_duck_in_meta_block(self):
        """duck 关键字在 meta 块中被识别"""
        code = "meta:\n    duck Comparable:\n        a < b -> bool\n"
        tokens = list(Lexer(code).tokenize())
        duck_tokens = [t for t in tokens if t.type == TokenType.DUCK]
        assert len(duck_tokens) == 1


# ========== Parser 测试 ==========

class TestDuckParser:
    """测试 parser 中的 duck 约束解析"""

    def _parse(self, code: str):
        tokens = list(Lexer(code).tokenize())
        return Parser(tokens).parse()

    def _get_duck(self, code: str) -> DuckDef:
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        return [n for n in meta.body if isinstance(n, DuckDef)][0]

    def test_simple_duck_def(self):
        """简单 duck 定义"""
        duck = self._get_duck("""
meta:
    duck Comparable:
        a < b -> bool
        a > b -> bool
""")
        assert duck.name == "Comparable"
        assert duck.type_params == []
        assert len(duck.requirements) == 2

    def test_operator_requirement(self):
        """操作符约束解析"""
        duck = self._get_duck("""
meta:
    duck C:
        a < b -> bool
""")
        req = duck.requirements[0]
        assert req.kind == "operator"
        assert req.name == "<"
        assert req.params == ["a", "b"]
        assert req.return_type == "bool"
        assert req.is_unary is False

    def test_unary_operator_requirement(self):
        """一元操作符约束: -a -> Self"""
        duck = self._get_duck("""
meta:
    duck N:
        -a -> Self
""")
        req = duck.requirements[0]
        assert req.kind == "operator"
        assert req.name == "-"
        assert req.is_unary is True
        assert req.return_type == "Self"

    def test_attribute_requirement(self):
        """属性约束解析"""
        duck = self._get_duck("""
meta:
    duck Named:
        name: str
""")
        req = duck.requirements[0]
        assert req.kind == "attribute"
        assert req.name == "name"
        assert req.return_type == "str"

    def test_method_requirement(self):
        """方法约束解析"""
        duck = self._get_duck("""
meta:
    duck Iter:
        __iter__(self) -> Iterator
""")
        req = duck.requirements[0]
        assert req.kind == "method"
        assert req.name == "__iter__"
        assert "self" in req.params
        assert req.return_type == "Iterator"

    def test_method_with_params(self):
        """带参数的方法约束"""
        duck = self._get_duck("""
meta:
    duck C<T>:
        add(self, item: T) -> None
""")
        req = duck.requirements[0]
        assert req.kind == "method"
        assert req.name == "add"
        assert "self" in req.params
        assert "item" in req.params
        assert req.return_type == "None"

    def test_generic_duck(self):
        """泛型 duck 约束"""
        duck = self._get_duck("""
meta:
    duck Container<T>:
        add(self, item: T) -> None
""")
        assert duck.name == "Container"
        assert duck.type_params == ["T"]

    def test_multi_type_params(self):
        """多类型参数"""
        duck = self._get_duck("""
meta:
    duck Map<K, V>:
        get(self, key: K) -> V
""")
        assert duck.type_params == ["K", "V"]

    def test_reference_requirement(self):
        """引用约束（无泛型）"""
        duck = self._get_duck("""
meta:
    duck Base:
        a < b -> bool

    duck Derived:
        Base
        a > b -> bool
""")
        # Derived is the second duck
        module = self._parse("""
meta:
    duck Base:
        a < b -> bool

    duck Derived:
        Base
        a > b -> bool
""")
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        derived = [d for d in ducks if d.name == "Derived"][0]
        ref_reqs = [r for r in derived.requirements if r.kind == "reference"]
        assert len(ref_reqs) == 1
        assert ref_reqs[0].name == "Base"
        assert ref_reqs[0].generic_args == []

    def test_reference_with_generic_args(self):
        """引用约束带泛型参数: Container<T>"""
        code = """
meta:
    duck Container<T>:
        add(self, item: T) -> None

    duck Sortable<T>:
        Comparable
        Container<T>
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        sortable = [d for d in ducks if d.name == "Sortable"][0]
        ref_reqs = [r for r in sortable.requirements if r.kind == "reference"]
        # Should have Comparable (no generic args) and Container<T> (with generic args)
        container_ref = [r for r in ref_reqs if r.name == "Container"][0]
        assert container_ref.generic_args == ["T"]

    def test_self_return_type(self):
        """Self 返回类型"""
        duck = self._get_duck("""
meta:
    duck Numeric:
        a + b -> Self
""")
        req = duck.requirements[0]
        assert req.return_type == "Self"

    def test_empty_duck(self):
        """空 duck 定义（仅有引用）"""
        duck = self._get_duck("""
meta:
    duck Empty:
        Comparable
""")
        assert len(duck.requirements) == 1
        assert duck.requirements[0].kind == "reference"

    def test_multiple_duck_defs(self):
        """多个 duck 定义在同一 meta 块"""
        code = """
meta:
    duck A:
        a < b -> bool

    duck B:
        a + b -> Self

    duck C<T>:
        add(self, item: T) -> None
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        assert len(ducks) == 3
        names = [d.name for d in ducks]
        assert "A" in names and "B" in names and "C" in names


# ========== Type Checker 测试 ==========

class TestDuckTypeChecker:
    """测试 type checker 的 duck 约束检查"""

    def _check(self, code: str):
        tokens = list(Lexer(code).tokenize())
        module = Parser(tokens).parse()
        checker = TypeChecker()
        checker.check(module)
        return checker.errors

    def test_valid_duck(self):
        """有效的 duck 定义不产生错误"""
        errors = self._check("""
meta:
    duck Comparable:
        a < b -> bool
        a > b -> bool
""")
        assert len(errors) == 0

    def test_undefined_reference(self):
        """引用未定义的 duck 约束"""
        errors = self._check("""
meta:
    duck Derived:
        Undefined
""")
        assert any("undefined constraint" in e for e in errors)

    def test_duplicate_definition(self):
        """重复定义 duck 约束"""
        errors = self._check("""
meta:
    duck Foo:
        a < b -> bool

    duck Foo:
        a > b -> bool
""")
        assert any("Duplicate" in e for e in errors)

    def test_circular_dependency(self):
        """循环依赖检测"""
        errors = self._check("""
meta:
    duck A:
        B

    duck B:
        A
""")
        assert any("Circular" in e for e in errors)

    def test_self_in_attribute_error(self):
        """Self 返回类型不能用于属性约束"""
        errors = self._check("""
meta:
    duck Bad:
        name: Self
""")
        assert any("Self" in e for e in errors)

    def test_self_in_method_ok(self):
        """Self 返回类型可用于方法约束"""
        errors = self._check("""
meta:
    duck Good:
        clone(self) -> Self
""")
        assert len(errors) == 0

    def test_duplicate_type_param(self):
        """重复的类型参数"""
        errors = self._check("""
meta:
    duck Bad<T, T>:
        add(self, item: T) -> None
""")
        assert any("Duplicate type parameter" in e for e in errors)

    def test_valid_reference_chain(self):
        """有效的引用链"""
        errors = self._check("""
meta:
    duck Base:
        a < b -> bool

    duck Mid:
        Base
        a > b -> bool

    duck Top:
        Mid
        a == b -> bool
""")
        assert len(errors) == 0


# ========== Codegen 测试 ==========

class TestDuckCodegen:
    """测试 duck 约束的代码生成"""

    def _generate(self, code: str) -> str:
        tokens = list(Lexer(code).tokenize())
        module = Parser(tokens).parse()
        return CythonGenerator().generate(module)

    def test_duck_registry_init(self):
        """_duck_registry 初始化"""
        output = self._generate("""
meta:
    duck C:
        a < b -> bool
""")
        assert "_duck_registry = {}" in output

    def test_duck_name_in_output(self):
        """duck 名称出现在注释中"""
        output = self._generate("""
meta:
    duck Comparable:
        a < b -> bool
""")
        assert "# Duck constraint: Comparable" in output

    def test_operator_in_output(self):
        """操作符约束出现在注释中"""
        output = self._generate("""
meta:
    duck C:
        a < b -> bool
""")
        assert "#   Operator: <(a, b) -> bool" in output

    def test_attribute_in_output(self):
        """属性约束出现在注释中"""
        output = self._generate("""
meta:
    duck N:
        name: str
""")
        assert "#   Attribute: name: str" in output

    def test_method_in_output(self):
        """方法约束出现在注释中"""
        output = self._generate("""
meta:
    duck I:
        iter(self) -> Iterator
""")
        assert "#   Method: iter(self) -> Iterator" in output

    def test_reference_in_output(self):
        """引用约束出现在注释中"""
        output = self._generate("""
meta:
    duck Base:
        a < b -> bool

    duck Derived:
        Base
""")
        assert "#   Reference: Base" in output

    def test_generic_ref_in_output(self):
        """带泛型的引用约束出现在注释中"""
        output = self._generate("""
meta:
    duck C<T>:
        add(self, item: T) -> None

    duck S<T>:
        C<T>
""")
        assert "#   Reference: C<T>" in output

    def test_generic_params_in_output(self):
        """泛型参数出现在注释中"""
        output = self._generate("""
meta:
    duck C<T>:
        add(self, item: T) -> None
""")
        assert "#   Generic: <T>" in output

    def test_registry_has_complete_data(self):
        """注册表包含完整的约束数据（不是 [...]）"""
        output = self._generate("""
meta:
    duck C:
        a < b -> bool
""")
        assert "_duck_registry['C']" in output
        assert "[...]" not in output
        assert "'kind': 'operator'" in output
        assert "'name': '<'" in output
        assert "'is_unary': False" in output

    def test_unary_operator_in_output(self):
        """一元操作符在注释和注册表中"""
        output = self._generate("""
meta:
    duck N:
        -a -> Self
""")
        assert "#   Operator: -a -> Self" in output
        assert "'is_unary': True" in output


# ========== Edge Cases 测试 ==========

class TestDuckEdgeCases:
    """边界场景测试"""

    def _parse(self, code: str):
        tokens = list(Lexer(code).tokenize())
        return Parser(tokens).parse()

    def test_duck_outside_meta_error(self):
        """duck 在 meta 块外使用应报错"""
        with pytest.raises((ValueError, Exception)):
            self._parse("duck C:\n    a < b -> bool\n")

    def test_empty_meta_block(self):
        """空 meta 块"""
        module = self._parse("meta:\n    pass\n")
        # Should not crash
        assert module is not None

    def test_nested_generic_reference(self):
        """嵌套泛型引用: Container<T> 在 Sortable<T> 中"""
        code = """
meta:
    duck Container<T>:
        add(self, item: T) -> None

    duck Sortable<T>:
        Container<T>
        a < b -> bool
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        sortable = [d for d in ducks if d.name == "Sortable"][0]
        refs = [r for r in sortable.requirements if r.kind == "reference"]
        assert len(refs) == 1
        assert refs[0].name == "Container"
        assert refs[0].generic_args == ["T"]

    def test_all_operator_types(self):
        """所有操作符类型"""
        code = """
meta:
    duck AllOps:
        a < b -> bool
        a > b -> bool
        a <= b -> bool
        a >= b -> bool
        a == b -> bool
        a != b -> bool
        a + b -> Self
        a - b -> Self
        a * b -> Self
        a / b -> Self
        -a -> Self
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        duck = [n for n in meta.body if isinstance(n, DuckDef)][0]
        assert len(duck.requirements) == 11
        unary = [r for r in duck.requirements if r.is_unary]
        assert len(unary) == 1
        assert unary[0].name == "-"

    def test_self_return_in_all_contexts(self):
        """Self 返回类型在各种约束中"""
        code = """
meta:
    duck S:
        a + b -> Self
        clone(self) -> Self
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        duck = [n for n in meta.body if isinstance(n, DuckDef)][0]
        self_reqs = [r for r in duck.requirements if r.return_type == "Self"]
        assert len(self_reqs) == 2

    def test_three_level_reference_chain(self):
        """三级引用链"""
        code = """
meta:
    duck L1:
        a < b -> bool

    duck L2:
        L1
        a > b -> bool

    duck L3:
        L2
        a == b -> bool
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        assert len(ducks) == 3
        l3 = [d for d in ducks if d.name == "L3"][0]
        refs = [r for r in l3.requirements if r.kind == "reference"]
        assert refs[0].name == "L2"

    def test_multiple_references(self):
        """多个引用约束"""
        code = """
meta:
    duck A:
        a < b -> bool

    duck B:
        a + b -> Self

    duck C:
        A
        B
"""
        module = self._parse(code)
        meta = [n for n in module.body if isinstance(n, MetaBlock)][0]
        ducks = [n for n in meta.body if isinstance(n, DuckDef)]
        c_duck = [d for d in ducks if d.name == "C"][0]
        refs = [r for r in c_duck.requirements if r.kind == "reference"]
        assert len(refs) == 2


# ========== Integration 测试 ==========

class TestDuckIntegration:
    """端到端集成测试"""

    def test_full_example_compilation(self):
        """完整示例编译"""
        code = """
meta:
    duck Comparable:
        a < b -> bool
        a > b -> bool
        a == b -> bool

    duck Container<T>:
        add(self, item: T) -> None
        remove(self, item: T) -> bool
        __len__(self) -> int

    duck SortableContainer<T>:
        Comparable
        Container<T>

def sort<T: Comparable>(items: list<T>) -> list<T>:
    return items

def process<T: Container<int>>(container: T) -> None:
    container.add(42)
"""
        tokens = list(Lexer(code).tokenize())
        module = Parser(tokens).parse()
        assert module is not None
        assert len(module.body) > 0

        # Type check
        checker = TypeChecker()
        checker.check(module)
        assert len(checker.errors) == 0

        # Codegen
        output = CythonGenerator().generate(module)
        assert "_duck_registry" in output
        assert "Comparable" in output
        assert "Container" in output
        assert "SortableContainer" in output

    def test_duck_with_trait_coexistence(self):
        """duck 与 trait 共存"""
        code = """
meta:
    duck Comparable:
        a < b -> bool

trait Printable:
    def print(self) -> None
"""
        tokens = list(Lexer(code).tokenize())
        module = Parser(tokens).parse()
        assert module is not None

        # duck 和 trait 都应正确解析
        meta_blocks = [n for n in module.body if isinstance(n, MetaBlock)]
        assert len(meta_blocks) == 1
        duck_defs = [n for n in meta_blocks[0].body if isinstance(n, DuckDef)]
        assert len(duck_defs) == 1
        assert duck_defs[0].name == "Comparable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
