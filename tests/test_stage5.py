import unittest
import tempfile
import os
import sys


class TestCLIIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_cli_compile_file(self):
        from cypyc.cli import main
        from unittest.mock import patch

        source_path = os.path.join(self.temp_dir, "test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def foo():\n    return 42\n")

        with patch("sys.argv", ["cypyc", source_path, "-o", self.temp_dir]):
            result = main()
            self.assertEqual(result, 0)

    def test_cli_check_only(self):
        from cypyc.cli import parse_args

        args = parse_args(["test.cypy", "--check-only"])
        self.assertTrue(args.check_only)

    def test_cli_emit_ast(self):
        from cypyc.cli import parse_args

        args = parse_args(["test.cypy", "--emit-ast"])
        self.assertTrue(args.emit_ast)

    def test_cli_emit_cython(self):
        from cypyc.cli import parse_args

        args = parse_args(["test.cypy", "--emit-cython"])
        self.assertTrue(args.emit_cython)


class TestHookIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_hook_compile_with_struct(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "struct_test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("struct Point:\n    x: int\n    y: int\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_file(source_path)

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))

    def test_hook_compile_with_enum(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "enum_test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("enum Color:\n    RED\n    GREEN\n    BLUE\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_file(source_path)

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))

    def test_hook_compile_with_let_val(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "let_val_test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def test():\n    val x: int = 10\n    var y: int = 20\n    return x + y\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_file(source_path)

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))

    def test_hook_compile_with_meta(self):
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "meta_test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("struct Dog:\n    pass\n\nstruct Cat:\n    pass\n\nmeta:\n    constraint Pet = Dog | Cat\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_file(source_path)

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))


if __name__ == "__main__":
    unittest.main()