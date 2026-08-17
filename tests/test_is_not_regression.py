"""回归测试：身份/成员检测操作符（is / is not / in / not in / not is）。

锁定以下修复：
1. 类型检查器对比较操作符（含否定形式）应返回 bool，而非 object。
2. 生成器对否定形式应正确输出 ``is not`` / ``not in`` / ``is not``。
"""

import unittest

from cypy_hook import CypyHook


class IsNotRegressionTest(unittest.TestCase):

    SOURCE = """
#!bin cypy
def main() -> int:
    a = None
    b = 1
    let c: bool = a is not None
    let d: bool = b is None
    let e: bool = a not in [1, 2]
    let f: bool = 1 in [1, 2]
    let g: bool = 2 not is 3
    return 0

if __name__ == "__main__":
    main()
"""

    def setUp(self):
        self.hook = CypyHook()

    def test_transpile_no_type_errors(self):
        """is not / not in / not is 不应触发类型错误。"""
        result = self.hook.transpile(self.SOURCE)
        self.assertTrue(result.success, msg="\n".join(result.errors))
        self.assertFalse(result.errors, msg="\n".join(result.errors))

    def test_generated_cython_operators(self):
        """生成代码应正确包含 is not / not in / is not。"""
        result = self.hook.transpile(self.SOURCE)
        self.assertTrue(result.success, msg="\n".join(result.errors))
        code = result.cython_code
        self.assertIn("is not None", code)
        self.assertIn("not in [1, 2]", code)
        # 'not is' 在生成阶段被规范化为 'is not'
        self.assertIn("is not 3", code)

    def test_end_to_end_run(self):
        """端到端编译运行 main 应成功返回 0。"""
        result, module = self.hook.compile_and_import(self.SOURCE, module_name="isnot_reg")
        self.assertTrue(result.success, msg="\n".join(result.errors))
        self.assertIsNotNone(module)
        self.assertEqual(module.main(), 0)


if __name__ == "__main__":
    unittest.main()
