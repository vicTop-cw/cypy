"""R3-打磨 的回归锁：把「测试/文档/API 与调用面一致」这件事钉住，而不是靠人读。

| 锁 | 钉住的主张 | 若被回退会怎样 |
|---|---|---|
| 冻结形夹具 | BUG-55 的锁用 SYNTAX/11 的 `struct Box<T>`（不是 `generic struct`） | 改回非冻结形 ⇒ 第 1 条红 |
| 非冻结形现状 | parser 今天**仍然**容忍 `generic struct`（定性留给 R4-寻虫） | 一旦拒绝 ⇒ 第 2 条红并提醒改口径 |
| bridge 生成 setup | `--bridge --generate-setup` 出**可解析**的 setup.py | 少接线 ⇒ 第 3 条红 |
| bridge 拒绝 emit-cython | `--bridge --emit-cython` 明确 decline，不静默改语言 | 措辞被删 ⇒ 第 4 条红 |
| 子模块可达 | `cypy_bridge.union` 是**模块**（旧包 `__init__` 会被同名函数遮蔽） | 遮蔽复发 ⇒ 第 5 条红 |
| 公开 API | `CypyHook.analyze_only()` 存在且与私有实现同结果；CLI 不再直调私有 | 改名/回私有 ⇒ 第 6/7 条红 |
| 三向一致 | `docs/USAGE.md` 的 cypyc 命令行旗标 ↔ argparse ↔ `--help` | 文档漂移/旗标失踪 ⇒ 第 8/9 条红 |

第 9 条只扫 `cypyc …` 行：文档里 `twine upload --repository testpypi` 这类第三方命令不是 Cypy 的旗标，
第一版按整篇文本扫就把它误报成"幽灵旗标"（测量在先，才发现口径要收窄）。
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "cypyc" / "cli.py"
USAGE = ROOT / "docs" / "USAGE.md"
FIX_R3_TEST = ROOT / "tests" / "test_loop_20260927_fix_r3.py"
FLAGS_RE = re.compile(r"--[a-z][a-z0-9-]*")


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "cypyc.cli", *argv],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def _subcommand_flags(sub: str) -> set:
    """从 parse_args 的 AST 里取某个子命令自己声明的长旗标（按 add_parser 分段）。"""
    fn = next(n for n in ast.walk(ast.parse(CLI.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
    cur, table = "GLOBAL", {}
    calls = [x for x in ast.walk(fn) if isinstance(x, ast.Call)]
    for call in sorted(calls, key=lambda x: x.lineno):
        attr = getattr(call.func, "attr", None)
        if attr == "add_parser" and call.args and isinstance(call.args[0], ast.Constant):
            cur = call.args[0].value
            table.setdefault(cur, set())
        elif attr == "add_argument":
            for arg in call.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and arg.value.startswith("--"):
                    table.setdefault(cur, set()).add(arg.value.split()[0])
    return set(table.get(sub, set()))


def _help_flags(sub: str) -> set:
    proc = _cli(sub, "--help")
    assert proc.returncode == 0, proc.stdout[-200:] + proc.stderr[-200:]
    return set(FLAGS_RE.findall(proc.stdout)) - {"--help"}


def _documented_flags(sub: str) -> set:
    """只认 USAGE.md 里 `cypyc <sub> …` 这种命令行（第三方命令与散文都不算）。"""
    out = set()
    for line in USAGE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"cypyc {sub}") or stripped.startswith(f"$ cypyc {sub}"):
            out |= set(FLAGS_RE.findall(stripped))
    return out


# ---------------------------------------------------------- 锁 1/2：夹具形状
def test_polish_generic_fixture_in_fix_r3_uses_frozen_form():
    """BUG-55 的锁必须用 SYNTAX/11 的冻结形 `struct Box<T>`，不是 `generic struct`。"""
    src = FIX_R3_TEST.read_text(encoding="utf-8")
    assert 'struct Box<T>' in src, "冻结形夹具不见了"
    assert "generic struct Box<T>" not in src, "又用回了 SYNTAX/11 里不存在的 generic 关键字"


def test_polish_parser_currently_tolerates_non_frozen_keyword():
    """特征化测试（不是背书）：今天 parser 仍容忍 `generic struct`，R4 若改成拒绝本锁会红并提醒。"""
    from cypyc.parser.lexer import Lexer
    from cypyc.parser.parser import Parser

    def holders(src):
        tree = Parser(Lexer(src).tokenize()).parse()
        stack, seen, found = [tree], set(), 0
        while stack:
            cur = stack.pop()
            if cur is None or id(cur) in seen or not hasattr(cur, "__dict__"):
                continue
            seen.add(id(cur))
            if getattr(cur, "generic_params", None):
                found += 1
            for value in vars(cur).values():
                if isinstance(value, list):
                    stack.extend(x for x in value if hasattr(x, "__dict__"))
                elif hasattr(value, "__dict__") and not isinstance(value, type):
                    stack.append(value)
        return found

    assert holders("generic struct Box<T>:\n    value: T\n") == 1, \
        "parser 不再容忍非冻结形 ⇒ 本锁的定性要更新（这是好事，但记得同步文档与 R4 的账）"


# ------------------------------------------------------ 锁 3/4：bridge 两条路
def test_polish_bridge_generate_setup_writes_parseable_setup(tmp_path):
    src = tmp_path / "br_setup.cypy"
    src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    out = tmp_path / "out"
    proc = _cli("transpile", str(src), "-o", str(out), "--bridge", "--generate-setup")
    setup = out / "setup.py"
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-300:]
    assert setup.exists(), f"--bridge --generate-setup 没写 {setup}"
    body = setup.read_text(encoding="utf-8")
    tree = ast.parse(body)
    sources = [e.value for n in ast.walk(tree)
               if isinstance(n, ast.keyword) and n.arg == "sources"
               for e in getattr(n.value, "elts", [])]
    assert sources, body[:200]


def test_polish_bridge_emit_cython_declines_explicitly(tmp_path):
    src = tmp_path / "br_decline.cypy"
    src.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    out = tmp_path / "out"
    proc = _cli("transpile", str(src), "-o", str(out), "--bridge", "--emit-cython")
    text = proc.stdout + proc.stderr
    assert proc.returncode == 0, text[-300:]
    assert "does not apply in --bridge mode" in text, text[-300:]
    assert "Generated Cython code:" not in text, "bridge 模式不该打印 Cython 代码"


# ------------------------------------------------------ 锁 5：子模块可达性
def test_polish_union_submodule_reachable_via_importlib():
    """旧包 `__init__` 会把同名函数导在子模块之前 ⇒ 取模块一律走 importlib，本锁钉住现状。"""
    import cypy_bridge

    mod = importlib.import_module("cypy_bridge.union")
    assert hasattr(mod, "CUnion") and hasattr(mod, "union"), mod.__file__
    assert isinstance(cypy_bridge.union, type(mod)), \
        "cypy_bridge.union 又不是模块了（被同名函数遮蔽）"


# ------------------------------------------------------ 锁 6/7：公开 API
def test_polish_cypy_hook_exposes_public_analyze_only():
    from cypy_hook.hook import CypyHook

    hook = CypyHook()
    good_ast, good_errors = hook.analyze_only("def add(a: int, b: int) -> int:\n    return a + b\n")
    bad_ast, bad_errors = hook.analyze_only("def bad(a: int) -> int:\n    return\n")
    assert good_ast is not None and good_errors == [], good_errors
    assert bad_errors, "公开门面没能报出坏源码的问题"
    priv_ast, priv_errors = hook._parse_and_analyze("def bad(a: int) -> int:\n    return\n")
    assert priv_errors == bad_errors, "公开面与私有面结果不一致（门面不是纯委托）"


def test_polish_cli_no_longer_calls_private_analyzer():
    src = CLI.read_text(encoding="utf-8")
    assert "_parse_and_analyze" not in src, "CLI 又去直调私有方法了"
    assert "hook.analyze_only(" in src, "CLI 没走公开门面"


# -------------------------------------------------- 锁 8/9：文档三向一致
# 通用旗标写在 USAGE.md 的「选项表」里（`-o, --output DIR` / `-v, --verbose`），
# 不要求出现在每一条 `cypyc <子命令>` 示例行上——第一版按逐行完整性判，9 处全被判成缺文档（假红）。
UNIVERSAL_FLAGS = {"--output", "--verbose"}


def test_polish_transpile_and_build_flags_three_way_sync():
    table = USAGE.read_text(encoding="utf-8")
    for flag, row in (("--output", "-o, --output"), ("--verbose", "-v, --verbose")):
        assert row in table, f"选项表里缺 {flag} 的行（通用旗标的文档落点）"
    for sub in ("transpile", "compile", "build", "run", "watch"):
        declared = _subcommand_flags(sub)
        advertised = _help_flags(sub)
        documented = _documented_flags(sub)
        assert declared, f"{sub}: 从 parse_args 里取不到旗标 ⇒ 判据口径坏了"
        assert advertised == declared, f"{sub}: --help 与 argparse 不一致 {advertised ^ declared}"
        phantom = documented - declared
        assert not phantom, f"{sub}: 文档写了 argparse 里不存在的旗标 {sorted(phantom)}"
        undocumented = declared - documented - UNIVERSAL_FLAGS
        assert not undocumented, f"{sub}: argparse 有旗标没进文档 {sorted(undocumented)}"


def test_polish_every_documented_cypyc_flag_is_real():
    """USAGE.md 里所有 `cypyc <子命令> --旗标` 都必须真的存在（防文档漂到实现前面）。

    R4-修复改判：旗标真值取调用面 `cypyc <sub> --help`。原先只信 `cypyc/cli.py` 里 `parse_args`
    的 AST 切片，而 `hook` 的旗标是在 `cypy_hook/hook.py` 的 parser 上声明的（实测
    `cypyc hook --help` 列出 --transpile-only / --compile / --run / --eval），切片取不到 ⇒
    把真实存在的旗标判成"文档跑到实现前面"。静态切片不废弃，方向改成
    「AST 声明过的，--help 里必须有」——切片漏项会被单独抓到，而不是靠放宽断言糊过去。
    """
    text = USAGE.read_text(encoding="utf-8")
    subs = ("transpile", "compile", "build", "run", "watch", "hook")
    help_flags = {sub: _help_flags(sub) for sub in subs}
    for sub in subs:
        lost = _subcommand_flags(sub) - help_flags[sub]
        assert not lost, f"{sub}: argparse 声明的旗标没进 --help {sorted(lost)}"
    checked = 0
    for line in text.splitlines():
        stripped = line.strip().lstrip("$ ")
        m = re.match(r"^cypyc\s+(\w+)\b(.*)$", stripped)
        if not m or m.group(1) not in help_flags:
            continue
        for flag in FLAGS_RE.findall(m.group(2)):
            assert flag in help_flags[m.group(1)], (
                f"文档 {stripped!r} 里的 {flag} 不在 `cypyc {m.group(1)} --help`")
            checked += 1
    assert checked >= 8, f"扫到的文档旗标只有 {checked} 条，判据口径可疑"
