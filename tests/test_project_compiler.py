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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])