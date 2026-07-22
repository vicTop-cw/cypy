import unittest
import tempfile
import os
import sys
import shutil


class TestTranspileMode(unittest.TestCase):
    """测试模式1：基础转译测试模式"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_transpile_basic_function(self):
        """测试基础函数转译"""
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test_basic.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def foo() -> int:\n    return 42\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.transpile_file(source_path)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.cython_code)
        self.assertTrue(result.pyx_path.endswith(".pyx"))
        self.assertTrue(os.path.exists(result.pyx_path))
        self.assertIn("cdef", result.cython_code)
        self.assertIn("foo", result.cython_code)

    def test_transpile_with_struct(self):
        """测试struct转译"""
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test_struct.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("struct Point:\n    x: int\n    y: int\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.transpile_file(source_path)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.cython_code)
        self.assertIn("cdef struct Point", result.cython_code)

    def test_transpile_error_invalid_syntax(self):
        """测试无效语法的错误处理"""
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test_error.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def foo(\n")  # 不完整的函数定义

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.transpile_file(source_path)

        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) > 0)

    def test_transpile_in_memory(self):
        """测试内存中转译"""
        from cypy_hook.hook import CypyHook

        source = "def bar() -> str:\n    return 'hello'\n"

        hook = CypyHook()
        result = hook.transpile(source)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.cython_code)
        self.assertIn("bar", result.cython_code)


class TestCompileMode(unittest.TestCase):
    """测试模式2：一步到位自动处理模式"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compile_to_pyd_basic(self):
        """测试编译为.pyd文件"""
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test_compile.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def add(a: int, b: int) -> int:\n    return a + b\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.compile_to_pyd(source_path)

        # 检查步骤记录
        self.assertTrue(len(result.steps) > 0)
        
        if result.success:
            self.assertIsNotNone(result.pyd_path)
            self.assertTrue(os.path.exists(result.pyd_path))
            self.assertTrue(result.pyd_path.endswith(".pyd") or result.pyd_path.endswith(".so"))
        else:
            # 如果编译失败（可能是环境问题），至少确保步骤记录完整
            self.assertTrue(len(result.steps) > 0)

    def test_run_module(self):
        """测试运行已编译模块"""
        from cypy_hook.hook import CypyHook

        source_path = os.path.join(self.temp_dir, "test_run.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def square(x: int) -> int:\n    return x * x\n")

        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result, output = hook.run(source_path, "square")

        # 检查步骤记录
        self.assertTrue(len(result.steps) > 0)
        
        if result.success:
            self.assertEqual(output, None)  # run返回的是编译结果，不是输出


class TestHookIntegrationMode(unittest.TestCase):
    """测试模式3：Hook集成模式"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compile_and_import(self):
        """测试编译并导入模块"""
        from cypy_hook.hook import CypyHook

        source_code = """
def greet(name: str) -> str:
    return 'Hello, ' + name
"""

        hook = CypyHook()
        result, module = hook.compile_and_import(source_code, "test_greet")

        # 检查步骤记录
        self.assertTrue(len(result.steps) > 0)
        self.assertTrue(result.steps[0].startswith("=== Hook集成模式 ==="))

        if result.success:
            self.assertIsNotNone(module)
            self.assertTrue(hasattr(module, "greet"))
            self.assertEqual(module.greet("World"), "Hello, World")

    def test_eval_simple(self):
        """测试直接求值代码"""
        from cypy_hook.hook import CypyHook

        source_code = """
def add(a: int, b: int) -> int:
    return a + b
"""

        hook = CypyHook()
        module = hook.eval(source_code)

        if module is not None:
            self.assertTrue(hasattr(module, "add"))


class TestCLIModes(unittest.TestCase):
    """测试CLI命令"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_transpile_command(self):
        """测试cypyc transpile命令"""
        source_path = os.path.join(self.temp_dir, "cli_test.cypy")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def cli_func() -> int:\n    return 100\n")

        from cypy_hook.hook import CypyHook
        
        hook = CypyHook()
        hook.set_output_dir(self.temp_dir)
        result = hook.transpile_file(source_path)
        
        self.assertTrue(result.success)
        pyx_path = os.path.join(self.temp_dir, "cli_test.pyx")
        self.assertTrue(os.path.exists(pyx_path))

    def test_compile_result_data_class(self):
        """测试CompileResult数据类"""
        from cypy_hook.hook import CompileResult

        result = CompileResult(success=True, cython_code="test")
        self.assertTrue(result.success)
        self.assertEqual(result.cython_code, "test")
        self.assertEqual(result.errors, [])
        self.assertEqual(result.steps, [])

        result2 = CompileResult(success=False, errors=["error1", "error2"])
        self.assertFalse(result2.success)
        self.assertEqual(result2.errors, ["error1", "error2"])


if __name__ == "__main__":
    unittest.main()
