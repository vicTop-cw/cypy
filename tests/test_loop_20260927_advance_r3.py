"""R3-推进 的回归锁：把 `Callable[[T...], R]` 的**入参元数**这一层钉住。

SYNTAX/12-type-alias.md:11 把 `type Callback = Callable[[int], str]` 写成受支持语法，
SYNTAX/appendix-C-features.md:594 又把它列在「已知限制（尚未实现）」。本环补的是**元数判定**，
不是全量函数类型系统，所以这些锁同时钉住"做了什么"和"没做什么"：

| 锁 | 钉住的主张 | 若被回退会怎样 |
|---|---|---|
| 违例必报 | 实参数 ≠ 声明参数数 ⇒ `Callable arity mismatch` | 摘掉调用点 ⇒ 第 1/2 条红 |
| 形状不认识就不判 | 裸 `Callable`、`Callable[int]` 这类畸形/未声明形状 ⇒ 不报错 | 判定放宽成"拿最后一项当返回" ⇒ 第 3 条红 |
| 正确调用必不红 | 1 元、2 元、0 元三种声明在匹配实参时全清 | 判定写反/过严 ⇒ 第 4/5 条红 |
| 别名也走同一条判定 | `type Callback = Callable[[int], str]` 的形参调用同样受检 | 别名在分析层退化 ⇒ 第 6 条红 |
| 关键字实参不判 | `f(x=1)` 这种形状对不上位置参数表 ⇒ 跳过，不误报 | 只按元组长度剔 ⇒ 第 7 条红 |
| 与返回类型判定共存 | 元数错 + 返回类型错 同时成立时两条都在 | 早退 return 吞掉一条 ⇒ 第 8 条红 |
| 产物面不动 | `Callable` 参数在 Cython 里仍回退成无标注（`def a(f):`） | codegen 被顺手改 ⇒ 第 9 条红 |

第 7 条的判据形状是被实测逼出来的：`(1, 2)` 作为实参在 parser 里是**单个表达式节点**，
而 `x=1` 才是"首元素为 str 的元组" ⇒ 只按 `isinstance(tuple)` 剔会把元组字面量误计成关键字。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARITY_RE = re.compile(r"Callable arity mismatch: expected (\d+), got (\d+) at \d+:\d+")


def _analyze(src: str) -> list:
    from cypy_hook.hook import CypyHook

    _, errors = CypyHook().analyze_only(src)
    return list(errors)


def test_advance_callable_arity_violation_reported():
    errors = _analyze("def apply(f: Callable[[int], str]) -> str:\n    return f(1, 2)\n")
    assert ARITY_RE.search("; ".join(errors)), errors
    assert "expected 1, got 2" in "; ".join(errors)


def test_advance_callable_arity_zero_args_passed_reported():
    errors = _analyze("def apply(f: Callable[[int], str]) -> str:\n    return f()\n")
    joined = "; ".join(errors)
    assert ARITY_RE.search(joined) and "expected 1, got 0" in joined, errors


def test_advance_unrecognized_callable_shape_is_not_judged():
    # 裸 Callable 与 `Callable[int]` 都不是 SYNTAX 声明的形状 ⇒ 不许拿它们报元数错
    for src in ("def a(f: Callable) -> int:\n    return f(1, 2)\n",
                "def a(f: Callable[int]) -> int:\n    return f(1, 2)\n"):
        joined = "; ".join(_analyze(src))
        assert "arity mismatch" not in joined, (src, joined)


def test_advance_correct_single_arg_call_stays_clean():
    assert _analyze("def apply(f: Callable[[int], str]) -> str:\n    return f(1)\n") == []


def test_advance_two_arg_and_zero_arg_forms_match():
    assert _analyze("def run(f: Callable[[int, str], bool], a: int, b: str) -> bool:\n"
                    "    return f(a, b)\n") == []
    assert _analyze("def run(f: Callable[[], int]) -> int:\n    return f()\n") == []


def test_advance_alias_form_is_also_checked():
    src = ("type Callback = Callable[[int], str]\n"
           "def process(cb: Callback):\n    return cb(1, 2)\n")
    joined = "; ".join(_analyze(src))
    assert "Callable arity mismatch: expected 1, got 2 at 3:12" in joined, joined


def test_advance_keyword_arg_call_is_skipped():
    # 声明是位置参数表；`f(x=1)` 的形状对不上 ⇒ 不判（曾经被误计成 0 个实参）
    assert _analyze("def apply(f: Callable[[int], str]) -> str:\n    return f(x=1)\n") == []
    # 元组字面量实参不是关键字：声明 1 元、给 1 个元组 ⇒ 仍不许报
    assert _analyze("def apply(f: Callable[[int], str]) -> str:\n    return f((1, 2))\n") == []


def test_advance_arity_and_return_errors_coexist():
    errors = _analyze("def apply(f: Callable[[int], str]) -> int:\n    return f(1, 2)\n")
    joined = "; ".join(errors)
    assert "Callable arity mismatch" in joined, errors
    assert "Return type mismatch" in joined, errors


def test_advance_codegen_object_fallback_unchanged():
    out = ROOT / ".fist-loop-20260927" / "tmp_advance" / "lock_out"
    src = ROOT / ".fist-loop-20260927" / "tmp_advance" / "direct_annot.cypy"
    # 夹具目录自己建：这条锁要在**内容快照树**里也能跑（禁 commit 的仓里 HEAD 不含本轮改动，
    # 回退证明只能在快照树上做），而快照只按 KEEP_ROOTS 复制产品与测试目录。
    out.mkdir(parents=True, exist_ok=True)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def apply(f: Callable[[int], str]) -> str:\n    return f(1)\n",
                   encoding="utf-8", newline="\n")
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile",
                           str(src), "-o", str(out)],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    assert proc.returncode == 0, proc.stdout[-400:] + proc.stderr[-200:]
    pyx = (out / "direct_annot.pyx").read_text(encoding="utf-8")
    assert "def apply(f):" in pyx, pyx[-400:]
    assert "Callable" not in pyx.split("def apply")[1][:200], pyx[-400:]
