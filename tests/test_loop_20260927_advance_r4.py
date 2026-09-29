"""R4-推进 的永久回归锁：把名称面（`Never` 与三个文档内建名）的实测形状钉进仓库。

来源三份：`Never 类型名在分析器名称面落地（含文档工作例与负对照）`、`文档已用、名称表缺席的三个内建名（repr/open/iter）在分析器名称面补齐` 与 `法②后果：放行 open 激活休眠测试 test_defer_statement，声明面实测 try/finally 未被承诺`；
本文件由 `.fist-loop-20260927/advance_r4_gen_locks.py` 从
`.fist-loop-20260927/advance_r4_never.json` / `advance_r4_builtins.json` 反解生成，
探针源码逐字取自 `.fist-loop-20260927/advance_r4_probe/`。

| 锁 | 角色 | 期望 | 实测依据 | 若被回退 |
|---|---|---|---|---|
| A4-doc_worked_example | expect_green | clean | 改前 rc=1 改后 rc=0；红因 ["- Undefined name 'Never' at 1:34"] | |
| A4-never_min_return | expect_green | clean | 改前 rc=1 改后 rc=0；红因 ["- Undefined name 'Never' at 1:28"] | |
| A4-never_in_param_position | expect_green_no_claim | clean | 改前 rc=1 改后 rc=0；红因 ["- Undefined name 'Never' at 1:20"] | |
| A4-bogus_type_name_control | expect_red_undefined | error | 改前 rc=1 改后 rc=1；红因 ["- Undefined name 'NeverX' at 1:12"] | |
| A4-bogus_function_control | expect_red_undefined | error | 改前 rc=1 改后 rc=1；红因 ["- Undefined name 'repx' at 2:11"] | |
| A4B-repr | 已放行 | clean | 改前 rc=1 改后 rc=0；（诊断干净） | |
| A4B-open | 已放行 | clean | 改前 rc=1 改后 rc=0；（诊断干净） | |
| A4B-iter | 已放行 | clean | 改前 rc=1 改后 rc=0；（诊断干净） | |
| A4B-chr | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'chr' at 2:11"] | |
| A4B-hex | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'hex' at 2:11"] | |
| A4B-pow | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'pow' at 2:11"] | |
| A4B-round | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'round' at 2:11"] | |
| A4B-divmod | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'divmod' at 2:11"] | |
| A4B-bytes | 半径外仍拒 | error | 改前 rc=1 改后 rc=1；["- Undefined name 'bytes' at 2:11"] | |
| 产物签名 | codegen 未动 | `-> NoReturn` | 见 test_doc_worked_example_maps_to_noreturn | 回退即该行消失 |
| 账实一致 | 挂账 | 在档 | BUG-74 / BUG-75 / BUG-76 / BUG-77 有卡 | 卡被删 ⇒ 红 |
| defer 形状 | 声明面语义 | 在档 | 4 档实测（含钉住的 BUG-76 形状） | 搬迁规则或出口注入被改 ⇒ 红 |
| 文档声明面 | 引用行 | 在档 | 三处 `name(` 引用行仍含该调用 | 文档改写 ⇒ 红，逼人重量 |

"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")
BUGS = ROOT / "memory" / "bugs.md"
LEAKS = ("Traceback", "NoneType object", "cypyc.analyzer", "object at 0x")

# (id, law, role, src, want, [诊断子串…], 出题理由)
PROBES = [
    [
        "A4-doc_worked_example",
        "\u6cd5\u2460Never",
        "expect_green",
        "def fatal_error(message: str) -> Never:\n    raise RuntimeError(message)\n\ndef safe_divide(a: float, b: float) -> float:\n    if b == 0:\n        fatal_error(\"Division by zero\")\n    return a / b\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\u7ea2\u56e0 [\"- Undefined name 'Never' at 1:34\"]"
    ],
    [
        "A4-never_min_return",
        "\u6cd5\u2460Never",
        "expect_green",
        "def fatal(message: str) -> Never:\n    raise ValueError(message)\n\ndef main() -> int:\n    print(\"start\")\n    return 0\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\u7ea2\u56e0 [\"- Undefined name 'Never' at 1:28\"]"
    ],
    [
        "A4-never_in_param_position",
        "\u6cd5\u2460Never",
        "expect_green_no_claim",
        "def needs_never(x: Never) -> int:\n    return 1\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\u7ea2\u56e0 [\"- Undefined name 'Never' at 1:20\"]"
    ],
    [
        "A4-bogus_type_name_control",
        "\u6cd5\u2460Never",
        "expect_red_undefined",
        "def f() -> NeverX:\n    return 1\n",
        "error",
        [
            "NeverX"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b\u7ea2\u56e0 [\"- Undefined name 'NeverX' at 1:12\"]"
    ],
    [
        "A4-bogus_function_control",
        "\u6cd5\u2460Never",
        "expect_red_undefined",
        "def main() -> int:\n    print(repx(1))\n    return 0\n",
        "error",
        [
            "repx"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b\u7ea2\u56e0 [\"- Undefined name 'repx' at 2:11\"]"
    ],
    [
        "A4B-repr",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u5df2\u653e\u884c",
        "def main() -> int:\n    print(repr(1))\n    return 0\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\uff08\u8bca\u65ad\u5e72\u51c0\uff09"
    ],
    [
        "A4B-open",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u5df2\u653e\u884c",
        "def main() -> int:\n    f = open(\"data.txt\", \"r\")\n    return 0\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\uff08\u8bca\u65ad\u5e72\u51c0\uff09"
    ],
    [
        "A4B-iter",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u5df2\u653e\u884c",
        "def main() -> int:\n    xs = [1, 2]\n    it = iter(xs)\n    return 0\n",
        "clean",
        [],
        "\u6539\u524d rc=1 \u6539\u540e rc=0\uff1b\uff08\u8bca\u65ad\u5e72\u51c0\uff09"
    ],
    [
        "A4B-chr",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(chr(65))\n    return 0\n",
        "error",
        [
            "chr"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'chr' at 2:11\"]"
    ],
    [
        "A4B-hex",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(hex(255))\n    return 0\n",
        "error",
        [
            "hex"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'hex' at 2:11\"]"
    ],
    [
        "A4B-pow",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(pow(2, 10))\n    return 0\n",
        "error",
        [
            "pow"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'pow' at 2:11\"]"
    ],
    [
        "A4B-round",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(round(3.6))\n    return 0\n",
        "error",
        [
            "round"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'round' at 2:11\"]"
    ],
    [
        "A4B-divmod",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(divmod(7, 2))\n    return 0\n",
        "error",
        [
            "divmod"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'divmod' at 2:11\"]"
    ],
    [
        "A4B-bytes",
        "\u6cd5\u2461\u5185\u5efa\u540d",
        "\u534a\u5f84\u5916\u4ecd\u62d2",
        "def main() -> int:\n    print(bytes(4))\n    return 0\n",
        "error",
        [
            "bytes"
        ],
        "\u6539\u524d rc=1 \u6539\u540e rc=1\uff1b[\"- Undefined name 'bytes' at 2:11\"]"
    ]
]


def _run_cli(tmp_path: Path, src: str, extra: list) -> subprocess.CompletedProcess:
    f = tmp_path / "probe.cypy"
    f.write_text(src, encoding="utf-8", newline="\n")
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", "transpile", str(f),
         "-o", str(tmp_path)] + extra,
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300)


def _plain(p: subprocess.CompletedProcess) -> str:
    return ANSI.sub("", (p.stdout or "") + (p.stderr or ""))


@pytest.mark.parametrize("probe", PROBES, ids=[p[0] for p in PROBES])
def test_name_face_at_cli_entry(tmp_path, probe):
    """每条探针钉三件事：退出码、诊断里的名字、不把内部实现吐给用户。"""
    pid, law, role, src, want, needles, _why = probe
    p = _run_cli(tmp_path, src, [])
    text = _plain(p)
    expected_rc = 1 if want == "error" else 0
    assert p.returncode == expected_rc, f"{pid}/{law}/{role} rc={p.returncode}"
    if want == "error":
        low = text.lower()
        assert [n for n in needles if n.lower() in low or n in text], \
            f"{pid}: 诊断里找不到预期名字 {needles}"
    for leak in LEAKS:
        assert leak not in text, f"{pid}: 内部实现外泄 {leak}"


def test_doc_worked_example_maps_to_noreturn(tmp_path):
    """文档工作例真编译到产物：`Never` 走既有 codegen 的 NoReturn 映射（本环未动 codegen）。"""
    src = next(r[3] for r in PROBES if r[0] == "A4-doc_worked_example")
    p = _run_cli(tmp_path, src, [])
    assert p.returncode == 0, _plain(p)[-300:]
    pyx = sorted(tmp_path.rglob("*.pyx"))
    assert pyx, "没产出 .pyx"
    text = pyx[0].read_text(encoding="utf-8")
    assert "-> NoReturn:" in text, "产物里没有 NoReturn 签名 ⇒ 名称面或映射被回退"


@pytest.mark.parametrize("bug", ["BUG-74", "BUG-75", "BUG-76", "BUG-77"])
def test_pinned_defects_still_have_a_card(bug):
    """账实一致锁：本环挂账的两条（复合异或静默产错码 / 位运算符词位不可达）必须可查。"""
    assert bug in BUGS.read_text(encoding="utf-8"), f"{bug} 卡片不在账本里"


DOC_CITATIONS = [["repr", "SYNTAX/05-struct.md:53", "print(repr(p1))      # Point(x=1, y=2) (__repr__)"], ["open", "SYNTAX/14-syntax-sugar.md:174", "let file = open(path, \"r\")"], ["iter", "SYNTAX/06d-builtin-magic-traits.md:264", "return iter(range(self.start, self.end))"]]


@pytest.mark.parametrize("name,wanted,text", DOC_CITATIONS,
                         ids=[c[0] for c in DOC_CITATIONS])
def test_declared_builtins_still_cited_in_syntax_docs(name, wanted, text):
    """放行三个内建名的依据是文档自己在用；文档改写就要重量，不能靠这行绿着。"""
    path, _, line = wanted.partition(":")
    doc = (ROOT / path).read_text(encoding="utf-8", errors="replace").splitlines()
    got = doc[int(line) - 1].strip()
    assert name + "(" in got, f"{wanted} 这一行已不含 {name}( ⇒ 声明面变了"
    assert got == text, f"{wanted} 原文漂了：{got!r} != {text!r}"


# (形状, 源, [deferred 调用…], 体末最后语句, 判定档, 被测函数, 出口数, 清理次数)
DEFER_SHAPES = [
    [
        "single_defer",
        "def say(msg):\n    print(msg)\n\ndef one():\n    say(\"bodyA\")\n    defer:\n        say(\"Z1\")\n    say(\"bodyB\")\n",
        [
            "say('Z1')"
        ],
        "say('bodyB')",
        "moved",
        "one",
        0,
        1
    ],
    [
        "two_defers_lifo",
        "def say(msg):\n    print(msg)\n\ndef two():\n    say(\"bodyA\")\n    defer:\n        say(\"Z1\")\n    defer:\n        say(\"Z2\")\n    say(\"bodyB\")\n",
        [
            "say('Z2')",
            "say('Z1')"
        ],
        "say('bodyB')",
        "lifo",
        "two",
        0,
        2
    ],
    [
        "defer_before_return",
        "def make():\n    print(\"make\")\n    return 1\n\ndef three():\n    f = make()\n    defer:\n        print(\"DONE\")\n    return 7\n",
        [
            "print('DONE')"
        ],
        "return 7",
        "before_return",
        "three",
        1,
        1
    ],
    [
        "defer_two_exits",
        "def pick(flag):\n    f = open(\"t.txt\", \"w\")\n    defer:\n        f.close()\n    if flag:\n        return 1\n    return 2\n",
        [
            "f.close()"
        ],
        "return 2",
        "all_exits_cleaned",
        "pick",
        2,
        2
    ]
]


def _func_slice(code: str, func: str) -> str:
    """只取被测函数那一段：隔壁函数的 return 不能算进它的出口数。"""
    head = f"def {func}("
    i = code.find(head)
    assert i >= 0, f"产物里没有 {head}：{code[-200:]!r}"
    nxt = code.find("\ndef ", i + 1)
    return code[i:nxt if nxt > 0 else len(code)]


@pytest.mark.parametrize("shape,src,deferred,body_last,mode,func,exits,cleanups",
                         DEFER_SHAPES, ids=[r[0] for r in DEFER_SHAPES])
def test_defer_declared_shape(tmp_path, shape, src, deferred, body_last, mode, func,
                             exits, cleanups):
    """钉声明面语义（2026-09-28 裁决：`defer` = 函数退出时执行 + 多 defer 逆序，不含 try/finally）。"""
    p = _run_cli(tmp_path, src, [])
    assert p.returncode == 0, _plain(p)[-300:]
    pyx = sorted(tmp_path.rglob("*.pyx"))
    assert pyx, "没产出 .pyx"
    seg = _func_slice(pyx[0].read_text(encoding="utf-8"), func)
    if mode == "pinned_defect":
        # BUG-76 今天的行为：只遍历顶层出口，嵌套 return 那条不注入清理。
        # 修好后这两格会红 ⇒ 与关账同批走，不许悄悄把钉住的形状改掉。
        emitted = sum(seg.count(c) for c in deferred)
        assert [seg.count("return "), emitted] == [exits, cleanups], seg
        return
    if mode == "all_exits_cleaned":
        # 2026-09-28 R5-修复 关账同批的翻档：BUG-76 修好前这格钉的是
        # `"pinned_defect", exits=2, cleanups=1`（嵌套 return 拿不到清理），
        # 修好后每个出口前都必须注入清理 ⇒ 判定档换成逐出口校验，只升不降。
        lines = seg.splitlines()
        returns = [i for i, ln in enumerate(lines) if "return " in ln]
        assert len(returns) == exits, f"{shape}: 出口 {len(returns)} != {exits}：{seg!r}"
        emitted = sum(seg.count(c) for c in deferred)
        assert emitted == cleanups, f"{shape}: 清理注入 {emitted} 次 != {cleanups}：{seg!r}"
        for i in returns:
            prev = next((ln.strip() for ln in reversed(lines[:i]) if ln.strip()), "")
            assert any(c in prev for c in deferred), \
                f"{shape}: 第 {i} 行的 return 前没有清理，实得 {prev!r}"
        return
    for call in deferred:
        assert call in seg, f"{shape}: 产物函数段里没有 {call}：{seg!r}"
        if mode in ("moved", "lifo"):
            assert seg.rfind(call) > seg.rfind(body_last) >= 0, f"{shape}: 没搬到体末"
        if mode == "before_return":
            assert seg.rfind(call) < seg.rfind(body_last), f"{shape}: 清理在 return 之后"
    if mode == "lifo":
        assert seg.find(deferred[0]) < seg.find(deferred[1]), f"{shape}: 不按逆序"

