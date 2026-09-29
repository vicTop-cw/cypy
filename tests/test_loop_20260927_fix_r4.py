"""R4-修复 的回归锁：BUG-61..BUG-64 四个分析器根因，逐单配「正例必须成立 / 对照必须仍成立」。

| 根因 | 缺陷面 | 正例锁 | 对照锁 |
|------|--------|--------|--------|
| RC1 函数符号被登记成它的**返回类型** | 元数判定挂错表：`mk(one, 1)`（正确）被判 `expected 1` | 正确调用零诊断；错误调用必须报 arity | 内置/别名 Callable 的判定不变 |
| RC2 实参类型与形参声明从不做兼容比对 | `apply("s")`、`apply(42)`、`apply(three)` 全静默 | 三者必须报类型不匹配 | `apply(1)` / 动态值（object）不报 |
| RC3 `self.成员` 的类型不解析 | 方法里 `return self.n`（n: int，声明 str）静默 | 必须有 Return type mismatch | 同类型返回仍零诊断 |
| RC4 诊断文案把内部表示当名字用 | `Callable[tuple[int], str]` 外泄给用户 | 文案给 `Callable[[int], str]`，无 `tuple[` | 文案仍含可定位信息（行号列号） |

夹具是 R4-寻虫 的 12 条确诊样本（C01..C12），逐字照抄；本文件**只加锁不改实现**。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CB = "type Callback = Callable[[int], str]\n"
MK2 = "def mk(cb: Callback, n: int) -> Callback:\n    return cb\n\n"

FIXTURES = {
    # --- RC1：函数作值 / 函数作被调用者 ---
    "C01": (CB + "def one(a: int) -> str:\n    return \"\"\n\n" + MK2 +
            "def g() -> None:\n    mk(one, 1)\n", "clean"),
    "C02": (CB + "def one(a: int) -> str:\n    return \"\"\n\n" + MK2 +
            "def g() -> None:\n    mk(one)\n", "arity"),
    "C03": (CB + "def one(a: int) -> str:\n    return \"\"\n\n"
            "def mk() -> Callback:\n    return one\n", "clean"),
    "C04": ("def mk() -> int:\n    return 1\n\ndef g() -> int:\n    return mk(1, 2)\n", "arity"),
    "C05": ("def mk(k: int) -> int:\n    return k\n\ndef g() -> int:\n    return mk()\n", "arity"),
    # --- RC2：实参类型 ---
    "C06": (CB + "def three(a: int, b: int) -> str:\n    return \"\"\n"
            "def apply(f: Callback) -> str:\n    return f(1)\n"
            "def g() -> str:\n    return apply(three)\n", "argtype"),
    "C07": (CB + "def apply(f: Callback) -> str:\n    return f(1)\n"
            "def g() -> str:\n    return apply(42)\n", "argtype"),
    "C08": ("def apply(n: int) -> int:\n    return n\n\ndef g() -> int:\n    return apply(\"s\")\n",
            "argtype"),
    "C08_ctl": ("def apply(n: int) -> int:\n    return n\n\ndef g() -> int:\n    return apply(1)\n",
                "clean"),
    # --- RC3：self.成员 ---
    "C09": ("struct S:\n    n: int\n\n    def f(self) -> str:\n        return self.n\n", "return"),
    "C10": ("struct Inner:\n    n: int\nstruct Outer:\n    i: Inner\n\n"
            "    def f(self) -> str:\n        return self.i.n\n", "return"),
    "C11": (CB + "struct S:\n    cb: Callback\n\n    def f(self) -> str:\n"
            "        return self.cb(1, 2)\n", "arity"),
    "C09_ctl": ("struct S:\n    n: int\n\n    def f(self) -> int:\n        return self.n\n", "clean"),
    # --- RC4：文案形状 ---
    "C12": (CB + "def g() -> int:\n    let x: Callback = 1\n    return x\n", "message"),
}


def _errors(src: str):
    """走 CLI `--check-only` 用的同一张脸：CypyHook.analyze_only。"""
    from cypy_hook.hook import CypyHook

    hook = CypyHook()
    _, errors = hook.analyze_only(src)
    return list(errors or [])


def _kind(errors) -> str:
    text = " | ".join(errors).lower()
    if "arity" in text:
        return "arity"
    if "mismatch" in text:
        return "return" if "return type" in text else "argtype"
    return "clean" if not errors else "other"


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_fixture_matches_declared_expectation(key):
    src, want = FIXTURES[key]
    got = _errors(src)
    if want == "clean":
        assert got == [], f"{key} 是正确程序，不该有诊断：{got}"
    elif want == "message":
        assert got, f"{key} 该报类型不匹配，却零诊断"
        joined = " | ".join(got)
        assert "tuple[" not in joined, f"{key} 文案外泄内部表示：{joined}"
        assert "object at 0x" not in joined, f"{key} 文案外泄对象 repr：{joined}"
        assert "Callable[[int], str]" in joined, f"{key} 文案没给用户看得懂的名字：{joined}"
        assert ":" in joined.split("at ")[-1], f"{key} 文案丢了行列定位：{joined}"
    else:
        assert _kind(got) == want, f"{key} 期望 {want}，实得 {_kind(got)}：{got}"


def test_arity_control_on_alias_callable_still_reports():
    """对照：R3 落在 `Callable` 变量上的元数判定不得因为 RC1 的修法而失效。"""
    src = CB + "def use(cb: Callback) -> str:\n    return cb(1, 2)\n"
    assert _kind(_errors(src)) == "arity", _errors(src)


def test_arg_type_control_on_dynamic_value_stays_silent():
    """对照：值为 object/动态时不得误报（既有宽松分支是设计，不是缺陷）。"""
    src = "def apply(n: int) -> int:\n    return n\n\nlet dyn: object = 1\n\ndef g() -> int:\n    return apply(dyn)\n"
    assert _kind(_errors(src)) == "clean", _errors(src)


def test_call_face_reports_over_cli(tmp_path):
    """调用面：CLI `transpile --check-only` 必须以非零码退出并把 arity 文案打出来。"""
    src = tmp_path / "t.cypy"
    src.write_text(FIXTURES["C05"][0], encoding="utf-8", newline="\n")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(src),
         "-o", str(tmp_path / "out"), "--check-only"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode != 0, out[-400:]
    assert "arity" in out.lower(), out[-400:]


def test_no_internal_repr_leaks_in_any_fixture_message():
    """RC4 的横向锁：12 条夹具里任何一条的文案都不许出现 `tuple[` 或对象 repr。"""
    leaked = {}
    for key, (src, _want) in FIXTURES.items():
        for e in _errors(src):
            if "tuple[<cypyc" in e or "Type object at 0x" in e or "tuple[int]" in e:
                leaked[key] = e
    assert leaked == {}, json.dumps(leaked, ensure_ascii=False)
