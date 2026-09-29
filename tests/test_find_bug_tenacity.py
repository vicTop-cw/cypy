"""复刻库压测：tenacity 子集移植 + 相关编译器 bug 回归测试。

这些测试来自 Find_BUG 的"用 Cypy 复刻流行库以压测编译器"工程。
tenacity 复刻覆盖了：带参装饰器工厂 / 嵌套函数 / 闭包捕获 / 异常层级 /
try-except / while 循环 / 可变变量 / `and not` 逻辑条件 —— 由此暴露并
修复了若干真实编译器缺陷（见 Find_BUG/BUGS.md：BUG-010/012/013/014）。
"""
import os
import sys
import tempfile
import importlib.util

import pytest

from cypy_hook.hook import CypyHook
from cypyc.parser.lexer import Lexer
from cypyc.parser.parser import Parser

TENACITY_SRC = os.path.join(
    os.path.dirname(__file__), "..", "Find_BUG", "tenacity", "tenacity.cypy"
)


def _compile_and_import(src: str, module_name: str = None):
    """把一段 Cypy 源码编译为 .pyd 并动态导入，返回模块对象。"""
    with tempfile.NamedTemporaryFile("w", suffix=".cypy", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    # 编译出的扩展模块导出名由源文件名（不含后缀）决定，必须与之匹配才能导入
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


def _parse(src: str):
    return Parser(Lexer(src).tokenize()).parse()


def _transpile(src: str) -> str:
    """把一段 Cypy 源码转译为 Cython 并返回生成的代码。"""
    result = CypyHook().transpile(src)
    assert result.success, f"转译失败: {result.errors}"
    return result.cython_code or ""


def test_tenacity_replication_transpiles():
    """复刻库本身必须能编译通过（压测装饰器/泛型/异常/闭包等路径）。"""
    assert os.path.exists(TENACITY_SRC), f"缺少复刻源文件: {TENACITY_SRC}"
    result = CypyHook().transpile_file(TENACITY_SRC)
    assert result.success, f"tenacity 复刻编译失败: {result.errors}"


def test_attribute_assignment_not_lost():
    """BUG-012：obj.attr = value 不能被当成表达式语句（丢失右侧）。"""
    mod = _parse("def f(o: object) -> int:\n    o.y = 5\n    return 1\n")
    for stmt in mod.body:
        if getattr(stmt, "name", "") == "f":
            first = stmt.body[0]
            assert first.kind == "Assign", f"期望 Assign，实际 {first.kind}"
            assert first.value is not None, "属性赋值右侧丢失"
            return
    pytest.fail("未找到函数体")


def test_struct_method_assignment_not_lost():
    """BUG-012：结构体方法内 self.x = v 必须保留右侧赋值。"""
    mod = _parse(
        "struct Foo:\n    x: int\n    def set_x(self, v: int):\n        self.x = v\n"
    )
    for stmt in mod.body:
        if getattr(stmt, "kind", "") == "StructDef":
            for m in stmt.methods:
                if getattr(m, "name", "") == "set_x":
                    first = m.body[0]
                    assert first.kind == "Assign", f"期望 Assign，实际 {first.kind}"
                    assert first.value is not None
                    return
    pytest.fail("未找到结构体方法")


def test_logical_and_with_not():
    """BUG-010：a and not b 必须解析为逻辑与，而非把 not 当成按位 & 的操作数。"""
    mod = _parse("def f():\n    if a and not b:\n        return 1\n    return 0\n")
    for stmt in mod.body:
        if getattr(stmt, "name", "") == "f":
            cond = stmt.body[0].test
            assert cond.kind == "BinOp", f"期望 BinOp，实际 {cond.kind}"
            assert cond.op in ("and", "&&"), f"期望逻辑 and，实际 {cond.op!r}"
            assert cond.right.kind == "UnaryOp" and cond.right.op == "not"
            return
    pytest.fail("未找到 if 条件")


def test_logical_amp_amp_codegen():
    """BUG-014：&& / || 必须生成 and / or（Cython 无 && / ||）。"""
    code = _transpile(
        "def f(a: bool, b: bool) -> bool:\n"
        "    let x: bool = a && b\n"
        "    let y: bool = a || b\n"
        "    return x\n"
    )
    assert "&&" not in code, "生成了非法的 Cython && 运算符"
    assert "||" not in code, "生成了非法的 Cython || 运算符"
    assert "a and b" in code
    assert "a or b" in code


def test_bitwise_and_still_works():
    """修复 BUG-010 后，单个 &（解引用/按位）应保留为 &，不与逻辑 and 混淆。"""
    code = _transpile(
        "def f(x: int, y: int) -> int:\n    return x & y\n"
    )
    assert "x & y" in code


def test_single_struct_init_not_duplicated():
    """BUG-013：用户显式定义 __init__ 时不应再生成重复的全参构造器。"""
    code = _transpile(
        "struct Attempt:\n"
        "    number: int\n"
        "    has_exception: bool\n"
        "    def __init__(self, number: int):\n"
        "        self.number = number\n"
        "        self.has_exception = False\n"
    )
    # 只应有一个 def __init__
    assert code.count("def __init__") == 1, f"出现重复 __init__:\n{code}"
    # 且用户版赋值必须保留
    assert "self.number = number" in code


def test_runtime_struct_attribute_assignment():
    """运行时验证：结构体方法内的 self.x = v 赋值确实生效（BUG-012 修复）。"""
    mod = _compile_and_import(
        "struct Counter:\n"
        "    n: int\n"
        "    def inc(self):\n"
        "        self.n = self.n + 1\n"
    )
    c = mod.Counter(n=0)
    c.inc()
    c.inc()
    assert c.n == 2


def test_runtime_tenacity_retry():
    """复刻库真正运行：tenacity 的 Retrying 引擎按策略重试并在成功后返回。"""
    mod = _compile_and_import(open(TENACITY_SRC, encoding="utf-8").read())
    engine = mod.Retrying(
        stop=mod.StopAfterAttempt(3), wait=None, retry=mod.RetryIfExceptionType()
    )
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("boom")
        return "ok"

    assert engine.call(flaky) == "ok"
    assert calls["n"] == 2
