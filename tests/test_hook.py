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


if __name__ == "__main__":
    unittest.main()
