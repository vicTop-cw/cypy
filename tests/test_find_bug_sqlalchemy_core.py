"""复刻库压测：SQLAlchemy Core 表达式层子集移植 + 相关编译器 bug 回归测试。

来自 Find_BUG 的"用 Cypy 复刻流行库以压测编译器"工程。SQLAlchemy Core 表达式层
重度使用运算符重载（__eq__/__and__/...）与 trait 多态，由此暴露并修复了：
- BUG-022：函数/方法默认参数值在 codegen 中丢失；
- BUG-023：trait 包装器不转发运算符重载、isinstance(具体实例, Trait) 运行时为假
  （已修复：运算符方法直接返回 trait 类型 ClauseElement，_compile_operand 用
  isinstance(o, ClauseElement)，编译为 pyd 后链式运算与自省均正常工作）。
"""
import os
import sys
import tempfile
import importlib.util

import pytest

from cypy_hook.hook import CypyHook

SQLALCHEMY_SRC = os.path.join(
    os.path.dirname(__file__), "..", "Find_BUG", "sqlalchemy_core", "sqlalchemy_core.cypy"
)


def _compile_and_import(src: str):
    with tempfile.NamedTemporaryFile("w", suffix=".cypy", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    module_name = os.path.splitext(os.path.basename(path))[0]
    out = tempfile.mkdtemp()
    try:
        result = CypyHook().compile_to_pyd(path, output_dir=out, force_recompile=True)
        assert result.success, f"编译为 pyd 失败: {result.errors}"
        spec = importlib.util.spec_from_file_location(module_name, result.pyd_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.remove(path)


def test_sqlalchemy_replication_transpiles():
    """复刻库本身必须能编译通过（运算符重载 / trait / dict / while 路径）。"""
    assert os.path.exists(SQLALCHEMY_SRC), f"缺少复刻源文件: {SQLALCHEMY_SRC}"
    result = CypyHook().transpile_file(SQLALCHEMY_SRC)
    assert result.success, f"sqlalchemy_core 复刻编译失败: {result.errors}"


def test_runtime_build_query():
    """复刻库真正运行：运算符重载 + 链式调用构建出正确 SQL。"""
    mod = _compile_and_import(open(SQLALCHEMY_SRC, encoding="utf-8").read())
    assert mod.build_query() == "SELECT * FROM users WHERE id = 5 AND age > 18"


def test_default_arg_emitted():
    """BUG-022：函数默认参数值必须生成到 Cython 签名中，否则调用时参数变必填。"""
    mod = _compile_and_import(
        "def f(a: int, b: int = 3, c: str = 'x') -> int:\n    return a + b\n"
    )
    # 仅传必填参数 a（依赖默认值 b=3）
    assert mod.f(1) == 4
    # 覆盖默认参数
    assert mod.f(1, 2) == 3


def test_default_arg_in_struct_init():
    """BUG-022：结构体 __init__ 的默认参数同样必须生成（Column('id') 仅传必填）。"""
    mod = _compile_and_import(
        "struct Point:\n"
        "    x: int\n"
        "    y: int\n"
        "    def __init__(self, x: int, y: int = 0):\n"
        "        self.x = x\n"
        "        self.y = y\n"
    )
    p = mod.Point(x=5)
    assert p.x == 5 and p.y == 0
