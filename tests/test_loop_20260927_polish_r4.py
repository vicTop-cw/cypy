"""R4-打磨 的永久回归锁：把 R4-验证 的调用面探针从 .fist-loop 搬进仓库。
\
| 锁 | 钉住的主张 | 若被回退会怎样 |
|---|---|---|
| 18 条 CLI 探针 | `python -m cypyc.cli transpile --check-only` 对 BUG-61..64 四类形状的退出码与诊断子串 |
  类型检查回退 ⇒ 对应行红 |
| 文档不宣称复用 .pyd | `docs/USAGE.md` 里没有「源未变会复用」，且有实测措辞 | 措辞改回假口径 ⇒ 第 19 条红 |
| 账实一致 | BUG-73 在 `memory/bugs.md` 有卡 | 卡片被删 ⇒ 第 20 条红 |

源样本逐字来自 `.fist-loop-20260927/verify_r4_callsite.json`（由
`.fist-loop-20260927/polish_r4_gen_locks.py` 反解生成本文件），不是手打的。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LEAKS = ("Traceback", "NoneType object", "cypyc.analyzer", "object at 0x")
USAGE = ROOT / "docs" / "USAGE.md"
BUGS = ROOT / "memory" / "bugs.md"

# (id, bug, role, src, want, [诊断子串…], 出题理由)
PROBES = [
    ("V61a", "BUG-61", "proper", "type F = Callable[[int], int]\ndef wrap(cb: F, n: int) -> F:\n    return cb\n\ndef thrice(a: int) -> int:\n    return a\n\ndef run() -> F:\n    return wrap(thrice, 1)\n", "clean", [], "\u8fd4\u56de\u7c7b\u578b\u662f Callable \u7684\u51fd\u6570\u6309\u81ea\u8eab\u5143\u6570\u88ab\u6b63\u786e\u8c03\u7528\uff0c\u4e0d\u8be5\u88ab\u5224\u9519\uff08\u65e7\u75c7\u72b6 C01\uff1a`mk(one, 1)` \u88ab\u62a5 expected 1, got 2\uff09"),
    ("V61b", "BUG-61", "violation", "def pair(a: int, b: int) -> int:\n    return a\n\ndef run(g: int) -> int:\n    return pair(g)\n", "error", ["arity", "expected 2, got 1"], "\u5c11\u4f20\u4e00\u4e2a\u5b9e\u53c2\u5fc5\u987b\u62a5\u5143\u6570\uff08\u65e7\u75c7\u72b6 C02/C05 \u96f6\u8bca\u65ad\uff09"),
    ("V61c", "BUG-61", "proper", "type F = Callable[[int], int]\ndef twice(a: int) -> int:\n    return a\n\ndef mk() -> F:\n    return twice\n", "clean", [], "\u51fd\u6570\u4f5c\u503c\u8fd4\u56de\u4e0d\u8be5\u88ab\u5f53\u6210\u8fd4\u56de\u7c7b\u578b\u4e0d\u7b26\uff08\u65e7\u75c7\u72b6 C03\uff09"),
    ("V61d", "BUG-61", "control", "type F = Callable[[int], int]\ndef use(f: F) -> int:\n    return f(1, 2)\n", "error", ["arity"], "\u5bf9\u7167\uff1a\u522b\u540d Callable \u53d8\u91cf\u4e0a\u7684\u5143\u6570\u5224\u5b9a\u4e0d\u5f97\u56e0 RC1 \u4fee\u6cd5\u5931\u6548"),
    ("V61e", "BUG-61", "violation", "def pair(a: int, b: int) -> int:\n    return a\n\ndef run(g: int) -> int:\n    return pair(g, 1, 2)\n", "error", ["arity", "expected 2, got 3"], "\u591a\u4f20\u4e00\u4e2a\u5b9e\u53c2\u5fc5\u987b\u62a5\u5143\u6570\uff08\u65e7\u75c7\u72b6 C04 \u96f6\u8bca\u65ad\uff09"),
    ("V62a", "BUG-62", "violation", "def apply(n: int) -> int:\n    return n\n\ndef run() -> int:\n    return apply(\"s\")\n", "error", ["mismatch"], "str \u4f20\u7ed9 int \u5f62\u53c2\u5fc5\u987b\u62a5\uff08\u65e7\u75c7\u72b6 C08 \u96f6\u8bca\u65ad\uff09"),
    ("V62b", "BUG-62", "violation", "def apply(s: str) -> str:\n    return s\n\ndef run() -> str:\n    return apply(42)\n", "error", ["mismatch"], "int \u4f20\u7ed9 str \u5f62\u53c2\u5fc5\u987b\u62a5"),
    ("V62c", "BUG-62", "proper", "def apply(n: int) -> int:\n    return n\n\ndef run() -> int:\n    return apply(7)\n", "clean", [], "\u7c7b\u578b\u76f8\u7b26\u7684\u8c03\u7528\u4e0d\u5f97\u8bef\u62a5"),
    ("V62d", "BUG-62", "control", "def apply(n: int) -> int:\n    return n\n\nlet dyn: object = 1\n\ndef run() -> int:\n    return apply(dyn)\n", "clean", [], "\u5bf9\u7167\uff1a\u52a8\u6001\u503c\u8d70\u5bbd\u677e\u5206\u652f\u662f\u8bbe\u8ba1\uff0c\u4e0d\u5f97\u8bef\u62a5"),
    ("V62e", "BUG-62", "violation", "type F = Callable[[int], int]\ndef applyf(f: F) -> int:\n    return 0\n\ndef thrice(a: int, b: int) -> int:\n    return a\n\ndef run() -> int:\n    return applyf(thrice)\n", "error", ["mismatch"], "\u4e24\u53c2\u51fd\u6570\u4f20\u7ed9\u4e00\u53c2 Callback \u5f62\u53c2\u5fc5\u987b\u62a5\uff08\u65e7\u75c7\u72b6 C06\uff09"),
    ("V63a", "BUG-63", "violation", "struct K:\n    n: int\n\n    def f(self) -> str:\n        return self.n\n", "error", ["Return type mismatch"], "self.n \u662f int \u5374\u58f0\u660e\u8fd4\u56de str\uff08\u65e7\u75c7\u72b6 C09 \u9759\u9ed8\uff09"),
    ("V63b", "BUG-63", "violation", "struct Inner:\n    n: int\n\nstruct Outer:\n    i: Inner\n\n    def f(self) -> str:\n        return self.i.n\n", "error", ["Return type mismatch"], "\u5d4c\u5957\u6210\u5458\u94fe\u540c\u6837\u8981\u89e3\u6790"),
    ("V63c", "BUG-63", "violation", "type F = Callable[[int], int]\nstruct S:\n    cb: F\n\n    def f(self) -> int:\n        return self.cb(1, 2)\n", "error", ["arity"], "\u6210\u5458\u662f Callable \u65f6\u5143\u6570\u8981\u5224\uff08\u65e7\u75c7\u72b6 C11\uff09"),
    ("V63d", "BUG-63", "control", "struct K:\n    n: int\n\n    def f(self) -> int:\n        return self.n\n", "clean", [], "\u5bf9\u7167\uff1a\u7c7b\u578b\u76f8\u7b26\u7684\u6210\u5458\u8fd4\u56de\u4e0d\u5f97\u8bef\u62a5"),
    ("V64a", "BUG-64", "violation", "type F = Callable[[int], int]\ndef run() -> int:\n    let x: F = 1\n    return x\n", "error", ["Callable[[int], int]"], "\u6587\u6848\u5fc5\u987b\u7ed9\u6e90\u8bed\u6cd5\u540d\u800c\u4e0d\u662f\u5185\u90e8\u8868\u793a\uff08\u65e7\u75c7\u72b6 C12\uff09"),
    ("V64b", "BUG-64", "violation", "def run() -> int:\n    let x: int = \"s\"\n    return x\n", "error", ["Type mismatch"], "\u57fa\u672c\u7c7b\u578b\u7684\u6587\u6848\u5f62\u72b6\u4e0d\u5f97\u88ab\u5171\u7528\u4ef6\u5e26\u504f"),
    ("V64c", "BUG-64", "violation", "type F = Callable[[int], int]\ndef run() -> int:\n    let x: F = 1\n    return 0\n", "error", ["Callable[[int], int]"], "\u540c\u4e00\u4efd\u6e90\u91cc\u7b2c\u4e8c\u6761\u8bca\u65ad\u4e5f\u4e0d\u8bb8\u5916\u6cc4"),
    ("V64d", "BUG-64", "control", "struct P:\n    x: int\n\ndef use(p: P) -> int:\n    return p.x\n\ndef run() -> int:\n    return use(1)\n", "error", ["P"], "\u5bf9\u7167\uff1a\u7528\u6237\u7c7b\u578b\u540d\u5fc5\u987b\u539f\u6837\u51fa\u73b0\u5728\u6587\u6848\u91cc\uff08\u5171\u7528\u663e\u793a\u4ef6\u4e0d\u5f97\u628a struct \u4e5f\u7cca\u6389\uff09"),
]


def _run_check(tmp_path: Path, src: str) -> subprocess.CompletedProcess:
    f = tmp_path / "probe.cypy"
    f.write_text(src, encoding="utf-8", newline="\n")
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc.cli", "transpile", str(f),
         "-o", str(tmp_path), "--check-only"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)


def _plain(p: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (p.stdout or "") + (p.stderr or ""))


@pytest.mark.parametrize("probe", PROBES, ids=[p[0] for p in PROBES])
def test_cli_check_only_face(tmp_path, probe):
    """每条探针钉三件事：退出码、诊断子串、不把内部实现吐给用户。"""
    pid, bug, role, src, want, needles, _why = probe
    p = _run_check(tmp_path, src)
    text = _plain(p)
    expected_rc = 1 if want == "error" else 0
    assert p.returncode == expected_rc, f"{pid}/{bug}/{role} rc={p.returncode}"
    if want == "error":
        low = text.lower()
        assert [n for n in needles if n.lower() in low], \
            f"{pid}: 诊断里找不到任何预期子串 {needles}"
    for leak in LEAKS:
        assert leak not in text, f"{pid}: 内部实现外泄 {leak}"


def test_usage_doc_does_not_claim_pyd_reuse():
    """文档口径锁：`源未变会复用` 已被真编译判假，措辞回退即红。"""
    text = USAGE.read_text(encoding="utf-8")
    assert "源未变会复用" not in text, "USAGE.md 又宣称复用 .pyd"
    assert "每次都重编译" in text, "实测措辞被删掉了"


def test_bug73_card_present_in_ledger():
    """账实一致锁：.pyd 缓存两处分道这件事必须有账可查。"""
    assert "BUG-73" in BUGS.read_text(encoding="utf-8"), "BUG-73 卡片不在账本里"
