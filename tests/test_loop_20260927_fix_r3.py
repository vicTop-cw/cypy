"""R3-修复 的回归锁：BUG-55..BUG-60 六件，每件配成对对照。

| 缺陷 | 正例（必须成立） | 对照（必须仍成立） |
|------|------------------|--------------------|
| BUG-55 收集器读错属性名 | `generic_params` 节点被收进 `generic_defs` | DuckDef 的 `type_params` 仍被收（没改丢另一族） |
| BUG-56 四个旗标无人读 | 每个旗标在 CLI 调用面有可观测效果 | 不传旗标时产物形状与修复前一致 |
| BUG-57 CUnion 示例跑不通 | 文档写的两种形状（ctypes / C 类型名）可构造 | 传 Python 内建类型 ⇒ `UnionTypeError` |
| BUG-58 注解与返回值互斥 | `-> Optional[int]` + 文档写明 size<=0 给 None | `realloc(p, 0)` **仍返回 None**（老测试钉着） |
| BUG-59 环内序随哈希种子变 | 5 个 PYTHONHASHSEED 子进程给出同一序 | 无环图仍给「被依赖者在前」的确定序 |
| BUG-60 docstring 与冻结层冲突 | 规则 2 按 SYNTAX/04 写成函数作用域 | 函数体内 `p: *int` 仍**不报**构建块错误 |

BUG-58 与 BUG-60 只修了「声明与实现互斥」那一半：返回 None、块外不报错这两个行为本身
被既有测试与 SYNTAX/04 钉住，动它们会撞红线 ⇒ 那两半（malloc/realloc 不对称、是否补强制检查）
留在裁决面，本文件不假装它们已修。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc.cli", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def _all_text(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def _parse(src: str):
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser

    return Parser(Lexer(src).tokenize()).parse()


def _walk(node):
    seen, stack = set(), [node]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen or not hasattr(cur, "__dict__"):
            continue
        seen.add(id(cur))
        yield cur
        for val in vars(cur).values():
            if isinstance(val, list):
                stack.extend(v for v in val if hasattr(v, "__dict__"))
            elif hasattr(val, "__dict__") and not isinstance(val, type):
                stack.append(val)


# ------------------------------------------------------------------- BUG-55
def test_bug55_generic_params_nodes_are_collected():
    """parser 带的是 `generic_params` ⇒ 收集器必须认这个名字。"""
    from cypyc.transformer.generic_transformer import GenericTransformer

    tree = _parse("struct Box<T>:\n    value: T\n")
    holders = [n for n in _walk(tree) if getattr(n, "generic_params", None)]
    assert holders, "夹具坏了：这份源码没解析出泛型节点"

    transformer = GenericTransformer()
    transformer.transform(tree)
    assert len(transformer.generic_defs) == len(holders), (
        f"泛型节点 {len(holders)} 个、只收到 {len(transformer.generic_defs)} 个"
    )


def test_bug55_duck_def_type_params_still_collected():
    """对照：`type_params` 那一族（DuckDef）不得因为修 BUG-55 而被丢掉。"""
    from cypyc.transformer.generic_transformer import GenericTransformer

    tree = _parse(
        "meta:\n    duck Container<T>:\n        add(self, item: T) -> None\n"
    )
    ducks = [n for n in _walk(tree) if getattr(n, "type_params", None)]
    assert ducks, "夹具坏了：duck 定义没带 type_params"

    transformer = GenericTransformer()
    transformer.transform(tree)
    assert transformer.generic_defs, "DuckDef 的 type_params 不再被收集"


# ------------------------------------------------------------------- BUG-56
def test_bug56_check_only_reports_and_generates_nothing():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "ok.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        out = tmp / "out"
        r = _cli("transpile", str(src), "-o", str(out), "--check-only")
        text = _all_text(r)
        assert r.returncode == 0, text
        assert "Static analysis passed" in text, text
        assert not out.exists() or list(out.glob("*")) == [], (
            f"--check-only 承诺不生成代码，产物目录里却有 {list(out.glob('*'))}"
        )


def test_bug56_check_only_fails_on_broken_source():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "bad.cypy"
        src.write_text("def bad(a: int) -> int:\n    return\n", encoding="utf-8")
        r = _cli("transpile", str(src), "-o", str(tmp / "out"), "--check-only")
        text = _all_text(r)
        assert r.returncode != 0, f"坏源码被 --check-only 放过了：{text}"
        assert "Static analysis found" in text, text


def test_bug56_emit_ast_prints_parsed_nodes():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "ast.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        r = _cli("transpile", str(src), "-o", str(tmp / "out"), "--emit-ast")
        text = _all_text(r)
        assert r.returncode == 0, text
        assert "FuncDef add" in text, [ln for ln in text.splitlines() if "FuncDef" in ln]


def test_bug56_emit_cython_prints_cython_code():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "cy.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        r = _cli("transpile", str(src), "-o", str(tmp / "out"), "--emit-cython")
        text = _all_text(r)
        assert r.returncode == 0, text
        assert "Generated Cython code:" in text, text
        assert "def add(" in text, text


def test_bug56_generate_setup_writes_buildable_script():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "setup_demo.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        out = tmp / "out"
        r = _cli("transpile", str(src), "-o", str(out), "--generate-setup")
        text = _all_text(r)
        assert r.returncode == 0, text
        setup = out / "setup.py"
        assert setup.exists(), f"--generate-setup 之后 {setup} 不在盘上：{text}"
        body = setup.read_text(encoding="utf-8")
        ast.parse(body)  # 生成的脚本必须自己语法可解析
        assert "setup_demo" in body and "setup_demo.pyx" in in_quotes(body), body


def test_bug56_control_plain_transpile_writes_no_setup():
    """对照：不传旗标时的产物形状不变（只落 .pyx，不写 setup.py）。"""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "plain.cypy"
        src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        out = tmp / "out"
        r = _cli("transpile", str(src), "-o", str(out))
        assert r.returncode == 0, _all_text(r)
        names = sorted(p.name for p in out.glob("*"))
        assert "setup.py" not in names, names
        assert "plain.pyx" in names, names


def in_quotes(body: str) -> list:
    """取 setup.py 里 `sources=[...]` 的字符串项。"""
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "sources":
            return [e.value for e in getattr(node.value, "elts", [])]
    return []


# ------------------------------------------------------------------- BUG-57
def test_bug57_documented_member_shapes_work():
    from ctypes import c_double, c_int

    from cypy_bridge.union import CUnion, union

    a = CUnion(c_int, c_double)
    b = CUnion("int", "double")
    c = union("int", "double")
    for obj in (a, b, c):
        obj.value = 42
        assert obj.value == 42
    assert a.size == b.size == c.size


def test_bug57_builtin_member_type_is_diagnosed():
    from cypy_bridge.union import CUnion, UnionTypeError

    with pytest.raises(UnionTypeError) as exc:
        CUnion(int, float)
    message = str(exc.value)
    assert "Python builtin type" in message, message
    assert "no size" not in message, "仍在漏 ctypes 的内部文案"


def test_bug57_union_docstrings_advertise_only_runnable_shapes():
    from cypy_bridge import union as union_mod
    from cypy_bridge.union import CUnion

    for doc in (CUnion.__doc__, union_mod.union.__doc__, union_mod.cdef_union.__doc__):
        assert doc is not None
        assert "CUnion(int, float)" not in doc and "union(int, float)" not in doc, doc[:200]


# ------------------------------------------------------------------- BUG-58
def test_bug58_realloc_annotation_matches_return_shape():
    import typing

    from cypy_bridge import memory as mem

    ann = typing.get_type_hints(mem.realloc)["return"]
    assert str(ann) == "typing.Optional[int]", ann
    doc = mem.realloc.__doc__ or ""
    assert "size <= 0" in doc and "None" in doc, doc[:300]


def test_bug58_realloc_zero_size_still_returns_none_and_frees():
    """既有形状：`realloc(p, 0)` 释放并返回 None（`test_realloc_zero_size` 钉着）。

    这里刻意**不再** `free(ptr)`：那块地址已经被 realloc 释放过，第二次 free 是
    double-free（堆损坏），锁不能自己制造未定义行为。
    """
    from cypy_bridge import memory as mem

    ptr = mem.malloc(100)
    assert mem.realloc(ptr, 0) is None
    assert mem._as_address(ptr) not in mem._aligned_blocks, "释放后仍被记账为对齐块"


def test_bug58_control_malloc_zero_still_raises():
    """对照：`malloc(0)` 抛 MemoryError 的行为没被顺手改掉（不对称是文档化的）。"""
    from cypy_bridge.memory import MemoryError as BridgeMemoryError
    from cypy_bridge.memory import malloc

    with pytest.raises(BridgeMemoryError):
        malloc(0)


# ------------------------------------------------------------------- BUG-59
_ORDER_SNIPPET = (
    "import sys;sys.path.insert(0,%r)\n"
    "from cypyc.project.module_dependency_graph import ModuleDependencyGraph as G\n"
    "g=G()\n"
    "for a,b in (('x','y'),('a','b'),('b','c'),('c','a')): g.add_dependency(a,b)\n"
    "print(g.get_compilation_order())\n"
    "h=G()\n"
    "for a,b in (('x','y'),('y','z')): h.add_dependency(a,b)\n"
    "print(h.get_compilation_order())\n"
) % str(ROOT)


def test_bug59_compilation_order_stable_across_hash_seeds():
    outputs = []
    for seed in ("0", "1", "7", "42", "99"):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", _ORDER_SNIPPET],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONHASHSEED": seed},
            timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-300:]
        outputs.append(proc.stdout.strip())
    assert len(set(outputs)) == 1, f"同一张图给出 {len(set(outputs))} 种顺序：{outputs}"

    cyclic = ast.literal_eval(outputs[0].splitlines()[0])
    acyclic = ast.literal_eval(outputs[0].splitlines()[1])
    assert cyclic[-3:] == ["a", "b", "c"], f"环内模块没按名字排在最后：{cyclic}"
    assert cyclic[:2] == ["y", "x"], f"无环部分顺序变了：{cyclic}"
    assert acyclic == ["z", "y", "x"], f"纯无环图的确定序坏了：{acyclic}"


# ------------------------------------------------------------------- BUG-60
def test_bug60_docstring_rule2_aligns_with_frozen_syntax():
    import cypyc.analyzer.build_block_checker as bbc

    doc = bbc.__doc__ or ""
    assert "指针语法只能在构建块内部使用" not in doc, doc
    assert "函数作用域" in doc, doc
    assert "04-pointer-types" in doc, doc


def test_bug60_control_other_rules_still_enforced():
    """对照：改文档不是把检查器掏空——规则 5（assign 块里不许 yield）必须仍在报。"""
    from cypyc.analyzer.build_block_checker import BuildBlockChecker

    tree = _parse("def f() -> int:\n    x =:\n        yield 1\n        1\n    return x\n")
    checker = BuildBlockChecker()
    checker.check(tree)
    assert checker.errors, "整块检查器空转了：改文档不该让这个门失效"
