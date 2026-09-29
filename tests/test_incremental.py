"""OMEGA 回归测试 T0r61.1.2 - cypyc/incremental 依赖图与 AST 差异器

钉住四个缺陷的修复：
  1. dependency_graph 只匹配 kind == 'Identifier'，而 parser 产出的是 kind == 'Name'
     (载荷在 .id) -> 依赖图有节点无边（repro_incremental_01）。
  2. StructDef / TypeAlias / TraitDef 的泛型形参被当成 phantom 依赖边
     (`dependencies -= {name} - set(generic_params)` 优先级错误，repro 同文件附带发现)。
  3. ast_differ 的节点哈希来自 `kind : hash(str(node))`，而 ASTNode.__repr__ 只有
     kind/line/col -> 行号不变的原地函数体改写不可见（repro_incremental_02）。
  4. ASTDiffer.compare() 不在入口清空 changed_definitions，而 IncrementalCompiler
     长期复用同一实例 -> 上一轮变更被重放，need_recompile 恒真、reused 恒空
     (repro_incremental_03)。

测试输入只用 struct / func / type-alias / enum / trait：`exception` 构造可词法但当前
不可解析，故不作 fixture；文件一律写在 tmp_path 下，不写入 examples/。

（原文提到的「examples/struct.cypy 尾部已损坏（二进制垃圾）」指的是**工作区里那份被
UTF-16 式 NUL 污染的未提交副本**；T0r258.4.2 已用 `git show HEAD:` 恢复干净版并按
「示例名不得撞 stdlib」的规则改名为 examples/struct_records.cypy，污染副本留档在
Find_BUG/audit_2026q3/corrupt_backup/，当时的 golden 留档在
Find_BUG/audit_2026q3/golden_before/。该文件与 examples/minimal_test.cypy 现在
**必须**真正进入 reformat 不变式检查，见
TestStructuralDigest.test_corpus_reformat_invariance 的 must_check 断言。）
"""

import ast as pyast
import inspect
import os
import subprocess
import sys
import time

import pytest

from cypyc.incremental import ast_differ as ast_differ_module
from cypyc.incremental.ast_differ import ASTDiffer
from cypyc.incremental.dependency_graph import DependencyGraph
from cypyc.incremental.incremental_manager import IncrementalCompiler
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import ASTNode, EnumDef, FuncDef, Parser, StructDef, TraitDef, TypeAlias

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 ASTDiffer._extract_definitions 一致的顶层定义视图
# （不含 ExceptionDef：该构造可词法但当前不可解析）
DEFINITION_KINDS = (FuncDef, StructDef, TypeAlias, EnumDef, TraitDef)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def parse_source(source):
    return Parser(Lexer(source).tokenize()).parse()


def build_graph(source):
    graph = DependencyGraph()
    graph.build_from_ast(parse_source(source))
    return graph


def top_level_defs(ast):
    return {stmt.name: stmt for stmt in ast.body if isinstance(stmt, DEFINITION_KINDS)}


def digest(differ, ast, name):
    return differ._compute_definition_hash(top_level_defs(ast)[name])


MODULE_CALLS = """def helper(x: int) -> int:
    return x + 1

def other(x: int) -> int:
    return helper(x)

def main() -> int:
    let a: int = helper(1)
    let b: int = other(2)
    return a + b
"""

MODULE_ANNOTATIONS = """struct Point:
    x: int
    y: int

struct Segment:
    start: Point
    end: Point

type Origin = Point

def distance(s: Segment) -> Point:
    return s.start
"""

# 泛型形参名 T / X / E 同时是真实存在的顶层定义：修复前它们会成为 phantom 依赖边
MODULE_GENERICS = """struct Point:
    x: int

struct T:
    v: int

def X(a: int) -> int:
    return a

struct Box<T>:
    value: T
    origin: Point
    label: T

    def get() -> T:
        return self.value

type Wrapper<T, X> = T | X | Point
"""

MODULE_TRAIT_GENERICS = """struct E:
    v: int

struct Base:
    w: int

trait Reader<E>:
    def make() -> E:
        return Base(w=1)
"""

FUNC_V1 = "def add(x: int, y: int) -> int:\n    return x + y\n\ndef keep(z: int) -> int:\n    return z\n"
# 只有 add 的表达式变了，全部 token 的行号/列号与 v1 完全一致
FUNC_V2 = "def add(x: int, y: int) -> int:\n    return x - y\n\ndef keep(z: int) -> int:\n    return z\n"
# 纯格式化：整体下移 4 行，函数之间插入空行，没有任何语义变化
FUNC_REFORMAT = "# moved by a comment\n\n\ndef add(x: int, y: int) -> int:\n    return x + y\n\n\n\ndef keep(z: int) -> int:\n    return z\n"
# 纯格式化：仅列偏移
FUNC_COLSHIFT = "def add(x:int,y:int)->int:\n    return x+y\n"
FUNC_COLSHIFT_PRETTY = "def add( x : int , y : int ) -> int:\n    return x + y\n"


# --------------------------------------------------------------------------- #
# 1 + 2. 依赖图：边必须真的被收集，且泛型形参不是边
# --------------------------------------------------------------------------- #

class TestDependencyGraphEdgeCollection:

    def test_function_calls_produce_edges(self):
        """defect 1：kind 词表修正后，真实模块不再是一张零边的空图"""
        graph = build_graph(MODULE_CALLS)
        assert graph.get_dependencies("other") == {"helper"}
        assert graph.get_dependencies("main") == {"helper", "other"}
        assert graph.get_dependencies("helper") == set()
        assert sum(len(graph.get_dependencies(n)) for n in graph.get_all_definitions()) > 0

    def test_type_annotations_of_fields_and_aliases_produce_edges(self):
        """类型注解本身就是 Name 节点：直接作为参数传入也必须被采集"""
        graph = build_graph(MODULE_ANNOTATIONS)
        assert graph.get_dependencies("Segment") == {"Point"}
        assert graph.get_dependencies("Origin") == {"Point"}
        assert graph.get_dependencies("distance") == {"Segment", "Point"}

    def test_only_defined_names_become_edges(self):
        """内置类型/局部变量/形参名都不算依赖（未定义名被过滤）"""
        graph = build_graph(MODULE_CALLS)
        deps = graph.get_dependencies("main")
        assert deps == {"helper", "other"}  # 前提：边确实被收集了
        assert "int" not in deps and "print" not in deps
        assert "a" not in deps and "b" not in deps
        assert "main" not in graph.get_dependencies("main")  # 自引用被排除

    def test_struct_generic_param_is_not_a_dependency(self):
        """defect 2（同文件附带）：泛型形参即便与某个顶层定义同名也不成为边"""
        graph = build_graph(MODULE_GENERICS)
        assert "T" in top_level_defs(parse_source(MODULE_GENERICS))  # 前提：T 确实是定义
        # 精确集合：既不能把 T 收进来（phantom），也不能连真实的 Point 一起丢掉
        assert graph.get_dependencies("Box") == {"Point"}

    def test_type_alias_generic_param_is_not_a_dependency(self):
        graph = build_graph(MODULE_GENERICS)
        assert graph.get_dependencies("Wrapper") == {"Point"}

    def test_trait_generic_param_is_not_a_dependency(self):
        ast = parse_source(MODULE_TRAIT_GENERICS)
        graph = DependencyGraph()
        graph.build_from_ast(ast)
        assert "E" in top_level_defs(ast)  # 前提：E 是真实定义，否则本测试无意义
        assert graph.get_dependencies("Reader") == {"Base"}

    def test_analyze_definition_dependencies_excludes_self_and_generics(self):
        """单元级：减去泛型形参的语义与 FuncDef 分支一致"""
        graph = DependencyGraph()
        ast = parse_source(MODULE_GENERICS)
        box = next(s for s in ast.body if getattr(s, "name", None) == "Box")
        assert box.generic_params == ["T"]
        raw = graph._analyze_definition_dependencies(box)
        assert "T" not in raw
        assert "Box" not in raw
        assert "Point" in raw
        alias = next(s for s in ast.body if getattr(s, "name", None) == "Wrapper")
        assert graph._analyze_definition_dependencies(alias) == {"Point"}

    def test_reverse_and_transitive_dependents_use_the_edges(self):
        graph = build_graph(MODULE_CALLS)
        assert graph.get_dependents("helper") == {"other", "main"}
        assert graph.get_transitive_dependents("helper") == {"other", "main"}
        assert graph.get_affected_definitions({"helper"}) == {"helper", "other", "main"}
        assert graph.get_definition_type("helper") == "FuncDef"
        assert not graph.is_empty()

    def test_identifier_kind_is_still_tolerated(self):
        """'Identifier' 作为别名保留（手工构造/历史节点），'Name' 是 parser 真实词表"""
        probe = ASTNode("Probe")
        probe.expr = ASTNode("Name")
        probe.expr.id = "from_name_node"
        probe.legacy = ASTNode("Identifier")
        probe.legacy.id = "from_identifier_alias"
        assert DependencyGraph()._extract_identifier_usage(probe) == {
            "from_name_node", "from_identifier_alias"}

    def test_bare_name_node_is_harvested(self):
        node = ASTNode("Name")
        node.id = "Point"
        assert DependencyGraph()._extract_identifier_usage(node) == {"Point"}


# --------------------------------------------------------------------------- #
# 3. 结构摘要：内容可见、格式化不可见
# --------------------------------------------------------------------------- #

class TestStructuralDigest:

    def test_in_place_body_edit_on_unchanged_lines_is_detected(self):
        """defect 3（repro_incremental_02）：行号/列号完全相同的表达式改写必须被发现"""
        a1, a2 = parse_source(FUNC_V1), parse_source(FUNC_V2)

        def positions(ast):
            stmt = ast.body[0].body[0]
            return (stmt.line, stmt.col, stmt.value.line, stmt.value.col)

        assert positions(a1) == positions(a2)  # 位置没有任何变化
        differ = ASTDiffer()
        assert digest(differ, a1, "add") != digest(differ, a2, "add")
        assert differ.compare(a1, a2) is True
        assert differ.changed_definitions == {"add"}
        assert digest(differ, a1, "keep") == digest(differ, a2, "keep")

    def test_pure_line_shift_is_not_a_semantic_change(self):
        """约束 2：整体下移若干行（加注释/空行）不得判为变更"""
        a1, a2 = parse_source(FUNC_V1), parse_source(FUNC_REFORMAT)
        assert a1.body[0].line != a2.body[0].line  # 位置确实变了
        differ = ASTDiffer()
        assert digest(differ, a1, "add") == digest(differ, a2, "add")
        assert differ.compare(a1, a2) is False
        assert differ.changed_definitions == set()

    def test_pure_column_shift_is_not_a_semantic_change(self):
        a1, a2 = parse_source(FUNC_COLSHIFT), parse_source(FUNC_COLSHIFT_PRETTY)
        differ = ASTDiffer()
        assert digest(differ, a1, "add") == digest(differ, a2, "add")
        assert differ.compare(a1, a2) is False

    @pytest.mark.parametrize("old, new, expected", [
        pytest.param("def f(x: int) -> int:\n    return x + 1\n",
                     "def f(x: int) -> int:\n    return x + 2\n", "f", id="literal"),
        pytest.param("def f(x: int, y: int) -> int:\n    return x + y\n",
                     "def f(x: int, y: int) -> int:\n    return x + z\n", "f", id="identifier"),
        pytest.param("def f(x: int, y: int) -> int:\n    return g(x, y)\n",
                     "def f(x: int, y: int) -> int:\n    return g(y, x)\n", "f", id="arg-order"),
        pytest.param("def f(x: int) -> int:\n    return x\n",
                     "def f(x: float) -> float:\n    return x\n", "f", id="param-type"),
        pytest.param("def f(x: int) -> int:\n    return x\n",
                     "async def f(x: int) -> int:\n    return x\n", "f", id="async-flag"),
        pytest.param("def f(x: int) -> int:\n    if x > 0:\n        return x\n    return 0\n",
                     "def f(x: int) -> int:\n    if x >= 0:\n        return x\n    return 0\n",
                     "f", id="comparison-op"),
        pytest.param("def f(x: int) -> int:\n    let a: int = x\n    return a\n",
                     "def f(x: int) -> int:\n    let a: int = x\n    a = a + 1\n    return a\n",
                     "f", id="extra-statement"),
        pytest.param("struct P:\n    x: int\n",
                     "struct P:\n    x: float\n", "P", id="struct-field-type"),
        pytest.param("struct P:\n    x: int\n\n    def get() -> int:\n        return x\n",
                     "struct P:\n    x: int\n\n    def get() -> int:\n        return y\n",
                     "P", id="struct-method-body-same-lines"),
        pytest.param("@value\nstruct P:\n    x: int\n",
                     "struct P:\n    x: int\n", "P", id="decorator"),
        pytest.param("type N = int\n", "type N = float\n", "N", id="alias-target"),
        # 旧实现只把 variant.name 拼进摘要，变体取值改动完全不可见
        pytest.param("enum Color:\n    Red = 1\n    Blue = 2\n",
                     "enum Color:\n    Red = 3\n    Blue = 2\n", "Color", id="enum-variant-value"),
    ])
    def test_payload_changes_are_detected(self, old, new, expected):
        differ = ASTDiffer()
        assert differ.compare(parse_source(old), parse_source(new)) is True
        assert differ.changed_definitions == {expected}

    def test_digest_is_hashlib_based_not_builtin_hash(self):
        """约束 1：这些摘要会随增量缓存持久化，禁止使用 PYTHONHASHSEED 随机化的内置 hash()"""
        tree = pyast.parse(inspect.getsource(ast_differ_module))
        plain_calls = {node.func.id for node in pyast.walk(tree)
                       if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name)}
        module_calls = {node.func.attr for node in pyast.walk(tree)
                        if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Attribute)}
        assert "hash" not in plain_calls, "ast_differ must not call builtin hash()"
        assert {"blake2b", "sha1"} & module_calls, "digest must come from hashlib"

        differ = ASTDiffer()
        value = differ._node_to_hash(parse_source(FUNC_V1).body[0])
        assert len(value) == 32 and set(value) <= set("0123456789abcdef")

    def test_digest_is_stable_across_pythonhashseed(self):
        """跨进程（不同 PYTHONHASHSEED）摘要必须一致，否则缓存无法复用

        覆盖两级：定义级哈希 + 语句级摘要。旧实现 `_node_to_hash` 用的正是内置
        hash()，语句级摘要在种子不同的子进程里必然漂移。
        """
        script = (
            "import sys; sys.path.insert(0, %r)\n"
            "from cypyc.parser.lexer import Lexer\n"
            "from cypyc.parser.parser import Parser\n"
            "from cypyc.incremental.ast_differ import ASTDiffer\n"
            "ast = Parser(Lexer(%r).tokenize()).parse()\n"
            "differ = ASTDiffer()\n"
            "print(differ._compute_definition_hash(ast.body[0]))\n"
            "print(differ._node_to_hash(ast.body[0].body[0]))\n"
            % (REPO_ROOT, FUNC_V1)
        )
        differ = ASTDiffer()
        ast = parse_source(FUNC_V1)
        expected = [differ._compute_definition_hash(ast.body[0]),
                    differ._node_to_hash(ast.body[0].body[0])]
        assert len(set(expected)) == 2  # 两个粒度都要参与比较
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                 text=True, env=env, cwd=REPO_ROOT, timeout=120)
            assert out.returncode == 0, out.stderr
            assert out.stdout.split() == expected, "digest drifted with PYTHONHASHSEED=%s" % seed

    def test_canonical_form_excludes_positions(self):
        from cypyc.incremental.ast_differ import _canonical_fragments

        node = parse_source(FUNC_V1).body[0]
        with_pos = b"".join(_canonical_fragments(node))
        node.line = 999
        node.col = 4242
        node.body[0].line = 77
        assert b"".join(_canonical_fragments(node)) == with_pos

    def test_deep_tree_digest_does_not_recurse(self):
        """约束 3：显式栈实现，节点数线性；深树不得触发 RecursionError"""
        depth = 20000
        node = ASTNode("Constant")
        node.value = 1
        for _ in range(depth):
            parent = ASTNode("BinOp")
            parent.left = node
            parent.op = "+"
            parent.right = ASTNode("Constant")
            parent.right.value = 1
            node = parent

        differ = ASTDiffer()
        previous_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(400)  # 任何按节点递归的实现都会在这里爆栈
        try:
            started = time.perf_counter()
            value = differ._node_to_hash(node)
            elapsed = time.perf_counter() - started
        finally:
            sys.setrecursionlimit(previous_limit)
        assert len(value) == 32
        assert elapsed < 10.0, "digest cost too high on %d nodes: %.3fs" % (depth, elapsed)

    def test_corpus_reformat_invariance(self):
        """真实语料回归：给每个可解析模块加注释/空行后，全部定义摘要不变

        跳过不是免费的：过去这里用裸 `except Exception: continue` 掩盖了一份
        「工作区里被 NUL 污染、git 当二进制」的语料（examples/struct.cypy），
        损坏因此对这条检查完全不可见。现在把跳过集合显式记下来，并强制要求
        T0r258.4.2 恢复/改名的三份语料**必须**出现在被检查集合里 —— 它们再次
        变得不可解析（或被改名挪走）时这条用例会红，而不是静默少一条锚点。
        """
        root = os.path.join(REPO_ROOT, "examples")
        checked = 0
        checked_paths = set()
        skipped_paths = []
        differ = ASTDiffer()
        for dirpath, _dirs, files in os.walk(root):
            for filename in sorted(files):
                if not filename.endswith(".cypy"):
                    continue
                path = os.path.join(dirpath, filename)
                with open(path, "r", encoding="utf-8") as handle:
                    source = handle.read()
                try:
                    original = parse_source(source)
                    shifted = parse_source("# format only\n\n" + source + "\n\n")
                except Exception as exc:                    # noqa: BLE001
                    skipped_paths.append((os.path.relpath(path, root), str(exc)))
                    continue  # 显式挂起的语料（examples/_pending_*.cypy）与暂不可解析的 demo
                before = {name: differ._compute_definition_hash(node)
                          for name, node in top_level_defs(original).items()}
                after = {name: differ._compute_definition_hash(node)
                         for name, node in top_level_defs(shifted).items()}
                assert before == after, "line/col shift changed the digest of %s" % path
                checked += 1
                checked_paths.add(os.path.relpath(path, root).replace(os.sep, "/"))
        assert checked >= 40, "corpus too small to be a meaningful check: %d" % checked

        must_check = {
            "struct_records.cypy",       # 恢复干净版 + 改名（原 struct.cypy）
            "minimal_test.cypy",         # 恢复干净版（曾被 NUL 污染）
            "new_syntax_features.cypy",  # 重写驱动体
            "struct_enum.cypy",          # 摘掉字符串枚举
        }
        missing = sorted(must_check - checked_paths)
        assert not missing, (
            "以下语料没有进入 reformat 不变式检查（不可解析或被挪走）: %s；"
            "跳过清单=%s" % (", ".join(missing), skipped_paths))


# --------------------------------------------------------------------------- #
# 4. compare() 状态复位 + 端到端增量决策
# --------------------------------------------------------------------------- #

class TestCompareState:

    def test_compare_resets_changed_definitions(self):
        """defect 4（repro_incremental_03）：第二轮比较不得重放上一轮"""
        a1, a2 = parse_source(FUNC_V1), parse_source(FUNC_V2)
        differ = ASTDiffer()
        assert differ.compare(a1, a2) is True
        assert differ.changed_definitions == {"add"}

        assert differ.compare(a1, a1) is False
        assert differ.changed_definitions == set()
        assert differ.added_definitions == set()
        assert differ.removed_definitions == set()
        assert differ.get_changed_definitions() == set()
        assert differ.is_changed("add") is False

        assert differ.compare(a1, a1) is False  # 第三轮依旧干净

    def test_compare_resets_added_and_removed(self):
        a1 = parse_source(FUNC_V1)
        a3 = parse_source(FUNC_V1 + "\ndef sub(x: int) -> int:\n    return x\n")
        differ = ASTDiffer()
        assert differ.compare(a1, a3) is True
        assert differ.added_definitions == {"sub"}
        assert differ.compare(a1, a1) is False
        assert differ.added_definitions == set()
        assert differ.removed_definitions == set()
        assert differ.compare(a3, a1) is True
        assert differ.removed_definitions == {"sub"} and differ.added_definitions == set()

    def test_reformat_then_edit_round_trip(self):
        """格式化轮不产生变更，紧随其后的语义轮仍能定位到具体定义"""
        differ = ASTDiffer()
        assert differ.compare(parse_source(FUNC_V1), parse_source(FUNC_REFORMAT)) is False
        assert differ.compare(parse_source(FUNC_REFORMAT), parse_source(FUNC_V2)) is True
        assert differ.changed_definitions == {"add"}


class TestIncrementalCompilerEndToEnd:

    def test_second_round_reports_reuse(self, tmp_path):
        """长生命周期 ASTDiffer：need_recompile 不再粘住，reused 不再恒空"""
        compiler = IncrementalCompiler(cache_dir=str(tmp_path / "cache"))
        v1, v2 = parse_source(FUNC_V1), parse_source(FUNC_V2)

        first = compiler.analyze_changes_with_old_ast(v1, v2)
        assert first.need_recompile is True
        assert first.changed_definitions == {"add"}

        second = compiler.analyze_changes_with_old_ast(v2, v2)
        assert second.need_recompile is False
        assert second.cache_hit is True
        assert second.changed_definitions == set()
        assert second.affected_definitions == set()
        assert second.reused_definitions == {"add", "keep"}

    def test_affected_scope_follows_dependency_edges(self, tmp_path):
        """defect 1 的下游效果：无边则受影响集只有被改的定义，复用集会漏掉真正的使用者"""
        base = ("def base(x: int) -> int:\n    return x\n\n"
                "def uses_base(x: int) -> int:\n    return base(x)\n\n"
                "def unrelated(x: int) -> int:\n    return x\n")
        changed = ("def base(x: int) -> int:\n    return x + 1\n\n"
                   "def uses_base(x: int) -> int:\n    return base(x)\n\n"
                   "def unrelated(x: int) -> int:\n    return x\n")
        compiler = IncrementalCompiler(cache_dir=str(tmp_path / "cache"))
        result = compiler.analyze_changes_with_old_ast(parse_source(base), parse_source(changed))
        assert result.changed_definitions == {"base"}
        assert result.affected_definitions == {"base", "uses_base"}
        assert result.reused_definitions == {"unrelated"}

    def test_file_cache_round_trip(self, tmp_path):
        path = tmp_path / "mod.cypy"
        path.write_text(FUNC_V1, encoding="utf-8")
        compiler = IncrementalCompiler(cache_dir=str(tmp_path / "cache"))
        ast = parse_source(FUNC_V1)

        cold = compiler.analyze_changes(str(path), ast)
        assert cold.need_recompile is True

        compiler.update_cache(str(path), ast)
        warm = compiler.analyze_changes(str(path), parse_source(FUNC_REFORMAT))
        assert warm.cache_hit is True
        assert warm.need_recompile is False
        assert warm.reused_definitions == {"add", "keep"}


# --------------------------------------------------------------------------- #
# 约束 3：摘要代价（10k 行级别文件必须可接受）
# --------------------------------------------------------------------------- #

def _large_module(functions=1100):
    """约 11k 行的合成模块：每个函数 10 行，含分支/循环/调用"""
    out = []
    for index in range(functions):
        previous = index - 1
        out.append("def f%d(a: int, b: int) -> int:\n" % index)
        out.append("    let x: int = a + b\n")
        out.append("    if x > a:\n")
        out.append("        x = x - b\n")
        out.append("    for k in range(0, 4):\n")
        out.append("        x = x + k\n")
        out.append("    while x > 0:\n")
        out.append("        x = x - 1\n")
        out.append("    return f%d(x, a)\n" % previous if previous >= 0 else "    return x\n")
        out.append("\n")
    return "".join(out)


class TestDigestCost:

    def test_digest_cost_on_ten_thousand_line_module(self):
        source = _large_module()
        assert len(source.splitlines()) >= 9000
        started = time.perf_counter()
        large_ast = parse_source(source)
        parse_elapsed = time.perf_counter() - started

        differ = ASTDiffer()
        # BUG-13 裁决（2026-09-26）：摘要代价用 CPU 时间判，阈值量级不变。
        # 墙钟测的是「本进程当时有多少堆要扫」——实测同一份产品码 CPU 恒 0.39–0.47s，
        # 而墙钟随收集顺序在 0.51s 与 3.385s 之间翻面，把门禁变成了抛硬币。
        started = time.process_time()
        for stmt in large_ast.body:
            differ._compute_definition_hash(stmt)
        digest_elapsed = time.process_time() - started

        assert digest_elapsed < 2.0, "digest cost too high: %.3fs" % digest_elapsed
        # 纯格式化（整体下移）在全文件规模上仍然是"零变更"，且代价与一次摘要同阶
        shifted = parse_source("# format only\n\n" + source)
        started = time.perf_counter()
        assert differ.compare(large_ast, shifted) is False
        compare_elapsed = time.perf_counter() - started
        assert compare_elapsed < 5.0
        assert parse_elapsed < 60.0

    def test_digest_cost_scales_linearly(self):
        """二次实现在这里会立刻超时：4 倍规模 < 12 倍耗时（宽松上界）"""
        small = _large_module(200)
        large = _large_module(800)
        differ = ASTDiffer()
        small_ast = parse_source(small)

        started = time.process_time()
        for stmt in small_ast.body:
            differ._compute_definition_hash(stmt)
        small_elapsed = max(time.process_time() - started, 1e-4)

        large_ast = parse_source(large)
        started = time.process_time()
        for stmt in large_ast.body:
            differ._compute_definition_hash(stmt)
        large_elapsed = time.process_time() - started

        assert large_elapsed < small_elapsed * 12 + 0.5
