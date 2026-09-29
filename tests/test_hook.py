import unittest
import tempfile
import os
from unittest.mock import patch


class TestHook(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_hook_compile_file(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def foo():\n    return 42\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_file(source_path)

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))
        self.assertTrue(result.endswith(".pyx"))

    def test_hook_compile_directory(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def foo():\n    return 42\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        results = hook.compile_directory(self.temp_dir)

        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0])


class TestExtensionNaming(unittest.TestCase):
    """审计 T0r61.4.2 / 缺陷 04：构建产物文件名必须由解释器的 EXT_SUFFIX 推导

    旧实现 `f"{module_name}.cp{major}{minor}-win_amd64.pyd"` 把平台标签和后缀写成
    字面量，在 Linux/macOS/win32/free-threaded/abi3 上产出的名字都不是 CPython 愿意
    加载的名字（hook 自己回报的也是这个错名字）。
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_filename_tracks_ext_suffix(self):
        import sysconfig
        from cypy_hook.hook import extension_filename, extension_suffix

        ext = sysconfig.get_config_var("EXT_SUFFIX")
        self.assertEqual(extension_suffix(), ext)
        self.assertEqual(extension_filename("hello"), "hello" + ext)

    def test_no_hardcoded_platform_tag_in_hook_source(self):
        import re
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cypy_hook", "hook.py")
        src = open(path, encoding="utf-8").read()
        self.assertIsNone(re.search(r"target_pyd_name\s*=\s*f\"[^\"]*win_amd64", src))
        self.assertIn("sysconfig", src)
        self.assertIn("EXT_SUFFIX", src)

    def test_module_name_stripped_from_real_world_filenames(self):
        from cypy_hook.hook import module_name_from_filename

        cases = {
            "hello.cp313-win_amd64.pyd": "hello",
            "hello.cpython-313-x86_64-linux-gnu.so": "hello",
            "hello.cpython-313-aarch64-linux-gnu.so": "hello",
            "hello.cpython-312-x86_64-linux-musl.so": "hello",
            "hello.cpython-312-darwin.so": "hello",
            "hello.cp313t-win_amd64.pyd": "hello",
            "hello.cp313t-x86_64-linux-gnu.so": "hello",
            "hello.cp311-win32.pyd": "hello",
            "hello.abi3.pyd": "hello",
            "main.pyd": "main",
            "hello.so": "hello",
            "hello": "hello",
            "pkg.hello.cp313-win_amd64.pyd": "pkg.hello",
        }
        for name, expected in cases.items():
            self.assertEqual(module_name_from_filename(name), expected, name)

    def test_run_module_regex_is_anchored_in_source(self):
        """module_name_from_filename 里的那条正则必须能独立解析 ABI 标签"""
        import re
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "cypy_hook", "hook.py")
        src = open(path, encoding="utf-8").read()
        found = re.search(r"match\s*=\s*re\.match\(r'(\^\S+?)',", src)
        self.assertIsNotNone(found, "找不到用于剥 ABI 标签的行内正则")
        rx = re.compile(found.group(1))
        for stem in ("hello.cpython-313-x86_64-linux-gnu", "hello.cp313t-win_amd64",
                     "hello.abi3", "hello.cp311-win32", "hello.cp313-win_amd64"):
            m = rx.match(stem)
            self.assertIsNotNone(m, stem)
            self.assertEqual(m.group(1), "hello", stem)

    def test_pick_built_extension_prefers_inplace_and_real_name(self):
        import sysconfig
        from cypy_hook.hook import pick_built_extension

        ext = sysconfig.get_config_var("EXT_SUFFIX")
        out = os.path.abspath(os.path.join(self.temp_dir, "out"))
        stale = os.path.join(out, "lib", "x", "other" + ext)
        in_build = os.path.join(out, "build", "lib.win", "hello" + ext)
        inplace = os.path.join(out, "hello" + ext)
        # 旧实现取 pyd_files[0]：顺序决定结果，历史残留也会被当成产物
        self.assertEqual(pick_built_extension([stale, in_build, inplace], "hello", out),
                         inplace)
        self.assertEqual(pick_built_extension([in_build, stale], "hello", out), in_build)
        self.assertIsNone(pick_built_extension([os.path.join(out, "vendor" + ext)],
                                               "hello", out))

    @unittest.skipUnless(
        __import__("shutil").which("cl") and os.path.isdir(
            __import__("sysconfig").get_paths()["include"]),
        "需要 MSVC cl.exe 与 CPython 开发头文件")
    def test_real_build_reports_ext_suffix_name(self):
        """端到端：真实工具链产物的名字就是解释器接受的名字"""
        import shutil
        import sysconfig
        from cypy_hook.hook import CypyHook

        outdir = os.path.join(self.temp_dir, "out")
        os.makedirs(outdir, exist_ok=True)
        hook = CypyHook()
        result = hook.compile_to_pyd(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "examples", "hello.cypy"),
            output_dir=outdir)
        self.assertTrue(result.success, result.errors)
        self.assertIsNotNone(result.pyd_path)
        ext = sysconfig.get_config_var("EXT_SUFFIX")
        self.assertEqual(os.path.basename(result.pyd_path), "hello" + ext)
        self.assertTrue(os.path.exists(result.pyd_path))
        shutil.rmtree(outdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
