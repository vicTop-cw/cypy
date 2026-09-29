"""测试项目级编译器功能"""

import os
import tempfile
import time
import pytest
from cypyc.project.project_compiler import ProjectCompiler


class TestProjectCompiler:
    """测试项目级编译器"""

    def test_discover_modules(self):
        """测试模块发现"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "types.cypy"), "w").write(
                "def add(a: int, b: int) -> int:\n    return a + b\n"
            )
            open(os.path.join(tmpdir, "main.cypy"), "w").write(
                "from types import add\n\ndef main() -> int:\n    return add(1, 2)\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            modules = compiler.discover_modules()

            assert "types" in modules
            assert "main" in modules

    def test_parse_all_modules(self):
        """测试解析所有模块"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "types.cypy"), "w").write(
                "def add(a: int, b: int) -> int:\n    return a + b\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            compiler.discover_modules()
            ast_map = compiler.parse_all_modules()

            assert "types" in ast_map
            assert ast_map["types"] is not None

    def test_build_dependency_graph(self):
        """测试构建依赖图"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "types.cypy"), "w").write(
                "def add(a: int, b: int) -> int:\n    return a + b\n"
            )
            open(os.path.join(tmpdir, "geometry.cypy"), "w").write(
                "from types import add\n\ndef double(x: int) -> int:\n    return add(x, x)\n"
            )
            open(os.path.join(tmpdir, "main.cypy"), "w").write(
                "from geometry import double\n\ndef main() -> int:\n    return double(21)\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            compiler.discover_modules()
            compiler.parse_all_modules()
            graph = compiler.build_dependency_graph()

            # 验证依赖关系
            deps = graph.get_dependencies("geometry")
            assert "types" in deps
            deps2 = graph.get_dependencies("main")
            assert "geometry" in deps2

    def test_topological_sort(self):
        """测试拓扑排序"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "types.cypy"), "w").write(
                "def add(a: int, b: int) -> int:\n    return a + b\n"
            )
            open(os.path.join(tmpdir, "geometry.cypy"), "w").write(
                "from types import add\n\ndef double(x: int) -> int:\n    return add(x, x)\n"
            )
            open(os.path.join(tmpdir, "main.cypy"), "w").write(
                "from geometry import double\n\ndef main() -> int:\n    return double(21)\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            compiler.discover_modules()
            compiler.parse_all_modules()
            graph = compiler.build_dependency_graph()

            sorted_modules, cycles = graph.topological_sort()

            # 验证无循环依赖
            assert len(cycles) == 0

            # 验证 types 在 geometry 之前，geometry 在 main 之前
            types_idx = sorted_modules.index("types")
            geometry_idx = sorted_modules.index("geometry")
            main_idx = sorted_modules.index("main")

            assert types_idx < geometry_idx
            assert geometry_idx < main_idx

    def test_cross_module_type_collection(self):
        """测试跨模块类型收集"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "types.cypy"), "w").write(
                "def create_point(x: float, y: float) -> tuple<float, float>:\n"
                "    return (x, y)\n"
            )
            open(os.path.join(tmpdir, "main.cypy"), "w").write(
                "from types import create_point\n\n"
                "def main() -> tuple<float, float>:\n"
                "    return create_point(1.0, 2.0)\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            modules = compiler.discover_modules()
            ast_map = compiler.parse_all_modules()
            graph = compiler.build_dependency_graph()

            # 验证跨模块依赖关系
            deps = graph.get_dependencies("main")
            assert "types" in deps

            # 验证源文件和 AST 缓存
            assert "types" in modules
            assert "types" in ast_map
            assert "main" in ast_map

    def test_single_module_compile(self):
        """测试单模块编译"""
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "main.cypy"), "w").write(
                "def main() -> int:\n    return 42\n"
            )

            compiler = ProjectCompiler(
                project_root=tmpdir,
                output_dir=os.path.join(tmpdir, "output"),
                verbose=False,
            )
            result = compiler.build()

            # 验证编译结果
            assert result is not None
            assert "main" in result.compiled_modules


class TestImportResolution:
    """审计 T0r61.4.2 / 缺陷 05、06：相对导入层级 + 绝对导入的模糊后缀匹配"""

    FILES = {
        "pkg/sub/leaf.cypy": "from .sib import leaf_fn\n\ndef caller() -> int:\n    return leaf_fn()\n",
        "pkg/sub/sib.cypy": "def leaf_fn() -> int:\n    return 1\n",
        "pk2/__init__.cypy": "from .sib2 import leaf2\n\ndef caller2() -> int:\n    return leaf2()\n",
        "pk2/sib2.cypy": "def leaf2() -> int:\n    return 2\n",
        "pk3/a/top.cypy": "def top_fn() -> int:\n    return 3\n",
        "pk3/__init__.cypy": "def z() -> int:\n    return 0\n",
    }

    def _compiler(self, tmpdir, extra=None):
        files = dict(self.FILES)
        files.update(extra or {})
        for rel, body in files.items():
            p = os.path.join(tmpdir, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
        pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
        pc.discover_modules()
        pc.parse_all_modules()
        return pc

    @pytest.mark.parametrize("current,import_path,expected", [
        # 叶子模块里 level=1 的基准是父包（旧公式多留一层 → 解析不到，边被丢弃）
        ("pkg.sub.leaf", ".sib", "pkg.sub.sib"),
        # 包自身（__init__.cypy）里 level=1 的基准是包本身
        ("pk2", ".sib2", "pk2.sib2"),
        # 叶子模块里 level=2：旧公式会解析成 *错误的* pkg.sub.sib
        ("pkg.sub.leaf", "..sib", "pkg.sib"),
        ("pk3.a.b.deep", "..top", "pk3.a.top"),
    ])
    def test_relative_import_base_level(self, current, import_path, expected):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._compiler(tmpdir)
            assert pc._resolve_import_target(import_path, current) == expected

    def test_relative_import_beyond_top_level_is_diagnosed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._compiler(tmpdir)
            assert pc._resolve_import_target("...too_far", "pk2") is None
            assert any("beyond top-level" in d for d in pc._import_diagnostics)

    def test_dependency_edge_for_leaf_relative_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._compiler(tmpdir)
            graph = pc.build_dependency_graph()
            assert "pkg.sub.sib" in graph.get_dependencies("pkg.sub.leaf")
            assert "pk2.sib2" in graph.get_dependencies("pk2")

    def test_absolute_import_does_not_bind_a_deeper_vendor_module(self):
        """`from pkg.mod import ...` 不能因为 endswith('.pkg.mod') 绑到 vendor.pkg.mod"""
        files = {
            "vendor/pkg/mod.cypy": "def vendored() -> int:\n    return 42\n",
            "app/consumer.cypy": "from pkg.mod import vendored\n\ndef use() -> int:\n    return vendored()\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            for rel, body in files.items():
                p = os.path.join(tmpdir, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(body)
            pc = ProjectCompiler(project_root=tmpdir,
                                 output_dir=os.path.join(tmpdir, "_out"))
            pc.discover_modules()
            pc.parse_all_modules()
            assert pc._resolve_import_target("pkg.mod", "app.consumer") is None
            graph = pc.build_dependency_graph()
            assert "vendor.pkg.mod" not in graph.get_dependencies("app.consumer")
            assert any("not found" in d for d in pc._import_diagnostics)

    def test_exact_absolute_import_still_resolves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._compiler(tmpdir)
            assert pc._resolve_import_target("pkg.sub.sib", "app") == "pkg.sub.sib"

    def test_ambiguous_candidates_are_reported_not_first_walk_hit(self):
        """多个候选时返回 None 并给出歧义诊断（旧实现静默返回 os.walk 的第一个命中）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            mod_path = os.path.abspath(os.path.join(tmpdir, "pkg", "mod.cypy"))
            # 同一 import 路径既能精确命中 `pkg.mod`，又能按项目根解析出另一个名字
            pc._source_files = {"pkg.mod": mod_path, "vendor.pkg.mod": mod_path}
            pc._path_to_module = {mod_path: "vendor.pkg.mod"}
            assert pc._resolve_import_target("pkg.mod", "consumer") is None
            assert any("ambiguous" in d for d in pc._import_diagnostics)


class TestBuildSuccessSemantics:
    """审计 T0r61.4.2 / 缺陷 07、08：success 标志的计算时机与模块名冲突"""

    def _make(self, tmpdir, files):
        for rel, body in files.items():
            p = os.path.join(tmpdir, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
        return ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))

    def test_bogus_entry_point_fails_instead_of_empty_success(self):
        files = {
            "lib.cypy": "def helper() -> int:\n    return 1\n",
            "main.cypy": "from lib import helper\n\ndef start() -> int:\n    return helper()\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, files)
            called = []

            def spy(module_name):
                called.append(module_name)
                return True, module_name + ".pyd", []

            pc.compile_module = spy
            result = pc.build(entry_point="does.not.exist")
            assert called == []
            assert result.success is False
            assert result.compiled_modules == []
            assert any("entry_point" in " ".join(v) for v in result.errors.values())

    def test_fully_cyclic_project_fails(self):
        files = {
            "aa.cypy": "from bb import b_fn\n\ndef a_fn() -> int:\n    return b_fn()\n",
            "bb.cypy": "from aa import a_fn\n\ndef b_fn() -> int:\n    return a_fn()\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, files)
            pc.compile_module = lambda m: (True, m + ".pyd", [])
            result = pc.build()
            assert result.success is False
            assert result.compiled_modules == []
            assert result.cycles_detected
            assert any("_cycles" in k for k in result.errors)

    def test_empty_project_still_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            result = pc.build()
            assert result.success is False

    def test_successful_build_still_reports_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, {"main.cypy": "def main() -> int:\n    return 42\n"})
            pc.compile_module = lambda m: (True, os.path.join(tmpdir, m + ".pyd"), [])
            result = pc.build()
            assert result.success is True
            assert result.compiled_modules == ["main"]

    def test_failed_module_compile_fails_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, {"main.cypy": "def main() -> int:\n    return 42\n"})
            pc.compile_module = lambda m: (False, None, ["boom"])
            result = pc.build()
            assert result.success is False
            assert result.failed_modules == ["main"]

    def test_name_collision_is_deterministic_and_visible(self):
        files = {
            "foo.cypy": "def only_in_module_file() -> int:\n    return 1\n",
            "foo/__init__.cypy": "def only_in_package_init() -> int:\n    return 2\n",
            "foo/bar.cypy": "def bar_fn() -> int:\n    return 3\n",
        }
        outcomes = []
        for _ in range(3):
            with tempfile.TemporaryDirectory() as tmpdir:
                pc = self._make(tmpdir, files)
                discovered = pc.discover_modules()
                outcomes.append(str((
                    len(discovered),
                    os.path.basename(discovered.get("foo", "")),
                    sorted(os.path.basename(v) for v in discovered.values()),
                )))
        # 确定性：同样的目录树，重复发现的结果一致（不再依赖 os.walk 顺序）
        assert len(set(outcomes)) == 1
        assert outcomes[0] == str((3, "__init__.cypy",
                                   ["__init__.cypy", "bar.cypy", "foo.cypy"]))

        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, files)
            pc.compile_module = lambda m: (True, m + ".pyd", [])
            result = pc.build()
            assert result.success is False
            assert any("collision" in " ".join(v) for v in result.errors.values())

    def test_parse_failures_are_reported_as_warnings(self):
        files = {
            "good.cypy": "def g() -> int:\n    return 1\n",
            "broken.cypy": "def f( x - > int ???\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = self._make(tmpdir, files)
            pc.compile_module = lambda m: (True, m + ".pyd", [])
            result = pc.build()
            if pc._parse_errors:
                assert any("failed to parse" in w for w in result.warnings)
            else:
                pytest.skip("该源码在当前 parser 下仍能解析，无法验证解析失败诊断")


class TestGetTypeErrorHandling:
    """审计 .1.2 转交：_get_type_str 的死分支，以及修好后暴露的两个错误答案"""

    def _nodes(self, source):
        from cypyc.parser.lexer import Lexer
        from cypyc.parser.parser import Parser
        return Parser(Lexer(source).tokenize()).parse()

    def test_dead_identifier_branch_is_gone(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cypyc", "project", "project_compiler.py")
        src = open(path, encoding="utf-8").read()
        start = src.index("def _get_type_str")
        end = src.index("def type_check_module", start)
        body = src[start:end]
        assert "kind == 'Identifier'" not in body
        assert "kind == 'TypeAnnotation'" not in body
        assert "'Identifier'" not in body
        assert hasattr(ProjectCompiler, "_get_type_str")

    def test_generic_type_and_list_annotation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            ast = self._nodes(
                "def f(a: Vec[int]) -> Vec[int]:\n    return a\n"
                "\ndef g() -> [int]:\n    return [1]\n"
            )
            funcs = [s for s in ast.body if s.kind == "FuncDef"]
            assert pc._get_type_str(funcs[0].params[0].type_annotation) == "Vec[int]"
            assert pc._get_type_str(funcs[0].return_type) == "Vec[int]"
            list_ret = pc._get_type_str(funcs[1].return_type)
            assert list_ret == "[int]", list_ret
            assert "Name(line=" not in list_ret

    def test_pointer_and_union_annotations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            ast = self._nodes(
                "type Number = int | float\n"
                "\ndef f(a: *int) -> *int:\n    return a\n"
            )
            alias = [s for s in ast.body if s.kind == "TypeAlias"][0]
            assert pc._get_type_str(alias.target) == "int | float"
            func = [s for s in ast.body if s.kind == "FuncDef"][0]
            assert pc._get_type_str(func.params[0].type_annotation) == "*int"

    def test_plain_name_and_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            ast = self._nodes("def f(a: int) -> float:\n    return 1.0\n")
            func = ast.body[0]
            assert pc._get_type_str(func.params[0].type_annotation) == "int"
            assert pc._get_type_str(func.return_type) == "float"
            assert pc._get_type_str(None) == "Any"

    def test_cross_module_generic_exports(self):
        """类型导出必须带上真正的泛型/列表类型，而不是 Any 或 repr 垃圾"""
        files = {
            "shapes.cypy": "def scale(v: Vec[int]) -> Vec[int]:\n    return v\n",
            "main.cypy": "def lst() -> [int]:\n    return [1]\n",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            for rel, body in files.items():
                with open(os.path.join(tmpdir, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            pc = ProjectCompiler(project_root=tmpdir, output_dir=os.path.join(tmpdir, "_out"))
            pc.discover_modules()
            pc.parse_all_modules()
            registry = pc.collect_type_exports()
            exports = {}
            for mod in sorted(registry._modules):
                for name, exp in (registry._modules[mod].exports or {}).items():
                    exports["%s.%s" % (mod, name)] = exp
            assert exports["shapes.scale"].param_types == ["Vec[int]"]
            assert exports["shapes.scale"].return_type == "Vec[int]"
            assert exports["main.lst"].return_type == "[int]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
