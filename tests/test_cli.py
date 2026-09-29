import unittest
from unittest.mock import patch, MagicMock
from cypyc.cli import parse_args, main


class TestCLI(unittest.TestCase):
    def test_parse_args_source(self):
        args = parse_args(["test.cypy"])
        self.assertEqual(args.source, "test.cypy")

    def test_parse_args_output(self):
        args = parse_args(["test.cypy", "-o", "build"])
        self.assertEqual(args.output, "build")

    def test_parse_args_verbose(self):
        args = parse_args(["test.cypy", "-v"])
        self.assertTrue(args.verbose)

    def test_parse_args_check_only(self):
        args = parse_args(["test.cypy", "--check-only"])
        self.assertTrue(args.check_only)

    def test_parse_args_emit_ast(self):
        args = parse_args(["test.cypy", "--emit-ast"])
        self.assertTrue(args.emit_ast)

    def test_parse_args_emit_cython(self):
        args = parse_args(["test.cypy", "--emit-cython"])
        self.assertTrue(args.emit_cython)

    @patch("sys.argv", ["cypyc", "test.cypy"])
    def test_main_with_source(self):
        # 创建临时测试文件
        import tempfile
        import os
        
        # 创建临时目录并写入测试文件
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.cypy")
            with open(test_file, "w") as f:
                f.write("def foo() -> int:\n    return 42\n")
            
            # 切换到临时目录，使相对路径生效
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("builtins.print") as mock_print:
                    result = main()
                    # 转译成功应该返回0
                    self.assertEqual(result, 0)
            finally:
                os.chdir(original_dir)

    @patch("sys.argv", ["cypyc"])
    def test_main_without_source(self):
        with patch("builtins.print") as mock_print:
            result = main()
            self.assertEqual(result, 1)


class TestRunRunReportsErrors(unittest.TestCase):
    """`cypyc run` must not call a failed execution successful.

    hook.run() folds run_module exceptions into result.errors while leaving
    success=True; the CLI used to report "[OK] Execution successful" anyway,
    which is how 13 golden examples rotted behind a green pytest run.
    """

    class Args:
        source = "x.cypy"
        output = "output"
        verbose = False
        func = "main"

    def _hook(self, errors):
        from cypy_hook.hook import CompileResult
        res = CompileResult(success=True)
        res.pyd_path = "x.pyd"
        res.errors = errors
        hook = MagicMock()
        hook.run.return_value = (res, None if errors else 0)
        return hook

    def test_run_run_fails_when_hook_reports_errors(self):
        from cypyc.cli import run_run
        with patch("cypy_hook.hook.CypyHook", return_value=self._hook(["运行错误: DLL load failed"])):
            self.assertEqual(run_run(self.Args()), 1)

    def test_run_run_succeeds_without_errors(self):
        from cypyc.cli import run_run
        with patch("cypy_hook.hook.CypyHook", return_value=self._hook([])):
            self.assertEqual(run_run(self.Args()), 0)


if __name__ == "__main__":
    unittest.main()
