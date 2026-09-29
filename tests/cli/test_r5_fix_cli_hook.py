"""R5-修复 的回归锁（CLI/HOOK 车道）：BUG-85..BUG-89 五张单。

纪律是「锁先行」：每条锁先跑成**断言级红**，再改实现到绿；每张单都配「正例必须成立 /
同族对照必须仍成立」。机制栏现读 `memory/bugs.md` 的 `## BUG-85` … `## BUG-89`。

- BUG-85 全局 `-o`/`-v` 被子解析器同名 `default` 重新播种。
  正例：写在子命令**前面**的 `-o`/`-v` 生效。对照：写在后面照常生效、两边都写时子命令侧胜出。
- BUG-86 BOM 让 `is_cypy_file`/`find_spec` 判定「不是 Cypy 模块」并静默放行。
  正例：BOM 版仍被识别、loader 是 `CypyLoader`。对照：无 BOM 版仍被识别、普通 `.py` 不被劫持。
- BUG-87 `hook clear-cache` 只删 `__pycache__/cypy` 根层，回执仍报「已清除」。
  正例：哈希子目录里的 `.pyd/.c/setup.py/build` 全清 + 如实报数。
  对照：删不动的文件把原因打出来、回执不再报成功且退出码非零。
- BUG-88 入口点诊断挂在非标准键（`_entry_point`/`_cycles`/`_`），cli 只遍历 `failed_modules`。
  正例：rc=1 的诊断里带被拒的 entry 名。对照：空项目、成环项目同样给出原因。
- BUG-89 `build --check-only` 分支自成一段，从不读 `args.entry`。
  正例：`--check-only --entry geometry` 只检查 geometry+types。
  对照：不带 `--entry` 时仍检查全部三个模块；entry 解析不出模块时必须失败而非退回全项目。

CLI 面一律走子进程 `python -X utf8 -m cypyc …`，工作目录是 tmp_path（不在仓库工作区留残渣）；
不触发真 Cython/C 编译——只走 transpile / `--check-only` / 参数解析面。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

HELLO = "def main() -> int:\n    return 0\n"


def _cli(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    """在临时目录里跑 `python -X utf8 -m cypyc …`，PYTHONPATH 指向本仓库。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "cypyc", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )


def _source(cwd: Path, name: str = "hello.cypy") -> Path:
    path = cwd / name
    path.write_text(HELLO, encoding="utf-8", newline="\n")
    return path


# ========================================================================= BUG-85
# 全局 -o/-v 被子解析器的同名 default 覆盖：写在子命令前面的值静默失效。


def test_r5_85_parse_args_global_before_subcommand():
    """解析面：`cypyc -o DIR transpile x.cypy` 的 DIR 必须留在命名空间里。"""
    from cypyc.cli import parse_args

    assert parse_args(["-o", "DIR", "transpile", "x.cypy"]).output == "DIR"
    assert parse_args(["-v", "compile", "x.cypy"]).verbose is True


def test_r5_85_parse_args_global_after_subcommand_still_works():
    """对照面：写在子命令后面的 -o/-v 今天就是对的，修法不得把它弄坏。"""
    from cypyc.cli import parse_args

    assert parse_args(["transpile", "x.cypy", "-o", "DIR"]).output == "DIR"
    assert parse_args(["compile", "x.cypy", "-v"]).verbose is True


def test_r5_85_parse_args_global_default_unchanged():
    """对照面：两边都不写时仍按文档默认值（`-o` 默认 output，`-v` 默认关）。"""
    from cypyc.cli import parse_args

    assert parse_args(["transpile", "x.cypy"]).output == "output"
    assert parse_args(["transpile", "x.cypy"]).verbose is False


def test_r5_85_output_dir_before_subcommand_is_used(tmp_path):
    """调用面：`cypyc -o outdir transpile hello.cypy` 必须写进 outdir，而不是 output/。"""
    src = _source(tmp_path)
    r = _cli("-o", "outdir", "transpile", str(src), cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-500:]
    assert (
        tmp_path / "outdir" / "hello.pyx"
    ).exists(), f"写在子命令前的 -o 没生效（仍写 output/）：{out[-400:]}"
    assert not (tmp_path / "output").exists(), "-o outdir 同时又在 output/ 拉了一份产物"


def test_r5_85_output_dir_after_subcommand_still_used(tmp_path):
    """同族对照：写在子命令后面的 -o 一直是生效的，改完全样生效。"""
    src = _source(tmp_path)
    r = _cli("transpile", str(src), "-o", "outdir", cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-500:]
    assert (tmp_path / "outdir" / "hello.pyx").exists(), f"写在子命令后的 -o 反而坏了：{out[-400:]}"
    assert not (tmp_path / "output").exists()


def test_r5_85_output_dir_both_sides_subcommand_wins(tmp_path):
    """两边都写：更具体的子命令侧胜出（argparse 的 last-wins 口径），且不产生 fallback 目录。"""
    src = _source(tmp_path)
    r = _cli("-o", "first", "transpile", str(src), "-o", "second", cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-500:]
    assert (tmp_path / "second" / "hello.pyx").exists(), f"子命令侧的 -o 没赢：{out[-400:]}"
    assert not (tmp_path / "first").exists()
    assert not (tmp_path / "output").exists()


def test_r5_85_verbose_before_subcommand_prints_steps(tmp_path):
    """调用面：`cypyc -v transpile … --check-only` 必须打详细步骤（走 CypyHook 的日志通道）。"""
    src = _source(tmp_path)
    r = _cli("-v", "transpile", str(src), "--check-only", cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-500:]
    assert "[CypyHook]" in out, f"写在子命令前的 -v 没打开详细输出：{out[-400:]}"


def test_r5_85_verbose_control_without_flag_stays_quiet(tmp_path):
    """同族对照：不给 -v 时不该有详细步骤（否则上一条「看到 -v」没有信息量）。"""
    src = _source(tmp_path)
    r = _cli("transpile", str(src), "--check-only", cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-500:]
    assert "[CypyHook]" not in out, "没给 -v 也打详细步骤"


# ========================================================================= BUG-86
# 带 BOM 的 `#!bin cypy` 首行让 import hook 判定「不是 Cypy 模块」：
# find_spec 静默放行 ⇒ 文件按普通 .py 执行，且没有任何诊断（docs/USAGE.md 4.2 承诺首行标记即生效）。

MARKER = "#!bin cypy\n"
BODY = 'def greet() -> str:\n    return "hi"\n'


def _marker_file(path: Path, *, bom: bool) -> Path:
    raw = (MARKER + BODY).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + raw) if bom else raw)
    return path


def test_r5_86_bom_marker_still_recognised_as_cypy(tmp_path):
    """检测面：BOM 版与无 BOM 版都必须被 `is_cypy_file` 认出来。"""
    from cypy_hook.hook import CypyCacheManager

    manager = CypyCacheManager()
    plain = _marker_file(tmp_path / "marker_ok.py", bom=False)
    bom = _marker_file(tmp_path / "marker_bom.py", bom=True)
    assert manager.is_cypy_file(str(plain)) is True, "同族对照（无 BOM）被打断"
    assert manager.is_cypy_file(str(bom)) is True, "带 BOM 的 #!bin cypy 首行没被认出来"


def test_r5_86_finder_does_not_silently_pass_bom_file_through(tmp_path):
    """调用面：find_spec 必须接管 BOM 版；返回 None 就等于「按普通 .py 跑 + 零诊断」。"""
    from cypy_hook.hook import CypyLoader, CypyMetaPathFinder

    _marker_file(tmp_path / "marker_bom.py", bom=True)
    spec = CypyMetaPathFinder().find_spec("marker_bom", [str(tmp_path)])
    assert spec is not None, "BOM 版被 import hook 静默放行（既不编译也不给诊断）"
    assert isinstance(spec.loader, CypyLoader), f"接管者不是 CypyLoader：{spec.loader}"


def test_r5_86_plain_python_file_is_not_hijacked(tmp_path):
    """同族对照：没有标记的普通 .py 仍必须走默认 loader，修法不得把 hook 变成全量拦截。"""
    from cypy_hook.hook import CypyMetaPathFinder

    (tmp_path / "plain_mod.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    assert CypyMetaPathFinder().find_spec("plain_mod", [str(tmp_path)]) is None


def test_r5_86_bom_source_still_transpiles(tmp_path):
    """接管之后这条路要走得通：BOM 版转译出 .pyx（不触发 C 工具链）。"""
    from cypy_hook.hook import CypyHook

    bom = _marker_file(tmp_path / "marker_bom.py", bom=True)
    out_dir = tmp_path / "out"
    hook = CypyHook()
    hook.set_output_dir(str(out_dir))
    result = hook.transpile_file(str(bom))
    assert result.success, f"BOM 版转译失败：{result.errors}"
    assert result.pyx_path and Path(result.pyx_path).exists()


# ========================================================================= BUG-87
# `hook clear-cache` 只删 __pycache__/cypy 根层的 .pyd/.so/manifest.json，
# 而产物实际写在哈希子目录里（.pyd/.c/setup.py/build/…），回执却无条件写 [OK]。

CACHE_FILES = [
    "__pycache__/cypy/manifest.json",
    "__pycache__/cypy/0123456789abcdef/marker_ok.cp313-win_amd64.pyd",
    "__pycache__/cypy/0123456789abcdef/marker_ok.c",
    "__pycache__/cypy/0123456789abcdef/setup.py",
    "__pycache__/cypy/0123456789abcdef/build/marker_ok.obj",
    "__pycache__/cypy/fedcba9876543210/other.cp313-win_amd64.pyd",
]


def _plant_cache_tree(root: Path) -> list:
    planted = []
    for rel in CACHE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "placeholder", encoding="utf-8")
        planted.append(path)
    return planted


def test_r5_87_clear_cache_removes_every_artifact_and_reports_count(tmp_path):
    """正例：哈希子目录里的 .pyd/.c/setup.py/build 全部真删掉，回执如实报数。"""
    planted = _plant_cache_tree(tmp_path)
    r = _cli("hook", "clear-cache", cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    left = [str(p) for p in planted if p.exists()]
    assert not left, f"回执报「已清除」，产物却原地留着：{left}"
    assert not (tmp_path / "__pycache__" / "cypy").exists(), "缓存根目录本身没被清掉"
    counts = re.findall(r"removed (\d+) file", out)
    assert counts == [str(len(planted))], f"回执没有如实报告删除了几个文件：{out[-300:]}"


def test_r5_87_clear_cache_reports_undeletable_file_in_report(tmp_path, monkeypatch):
    """清不动的文件要进报告（路径 + 原因），且不能从账面上消失。"""
    from cypy_hook import hook as hook_mod

    planted = _plant_cache_tree(tmp_path)
    victim = planted[1]
    real_remove = os.remove

    def refusing(path, *args, **kwargs):
        if os.path.abspath(str(path)) == os.path.abspath(str(victim)):
            raise PermissionError(13, "another process is using the file (simulated lock)")
        return real_remove(str(path), *args, **kwargs)

    monkeypatch.setattr(hook_mod.os, "remove", refusing)
    monkeypatch.chdir(tmp_path)
    report = hook_mod.CypyCacheManager().clear_cache()

    assert report is not None, "clear_cache() 不回报任何结果，调用方无从知道删了几个、几个没删掉"
    assert victim.exists(), "删不动的文件被报告成已删除"
    failed_paths = [os.path.abspath(p) for p, _reason in report.failed]
    assert failed_paths == [os.path.abspath(str(victim))], f"失败清单不对：{report.failed}"
    assert "PermissionError" in report.failed[0][1], f"失败原因没带上异常类型：{report.failed}"
    assert len(report.removed) == len(planted) - 1, f"成功计数虚报：{report.removed} vs {planted}"


def test_r5_87_cli_clear_cache_does_not_claim_success_on_leftovers(tmp_path, monkeypatch, capsys):
    """调用面：还有文件没删掉时，回执必须打原因并且不再写「cleared successfully」。"""
    from cypy_hook import hook as hook_mod
    from cypyc.cli import main as cli_main

    planted = _plant_cache_tree(tmp_path)
    victims = {os.path.abspath(str(p)) for p in planted}

    def refuse_all(path, *args, **kwargs):
        raise PermissionError(13, "another process is using the file (simulated lock)")

    monkeypatch.setattr(hook_mod.os, "remove", refuse_all)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["cypyc", "hook", "clear-cache"])
    try:
        rc = cli_main()
    except OSError as exc:
        pytest.fail(f"clear-cache 碰到删不动的文件直接抛裸异常，用户拿不到原因：{exc!r}")
    out = capsys.readouterr().out

    assert rc != 0, f"一个文件都没删掉，命令仍然回报成功（rc={rc}）"
    assert "cleared successfully" not in out, f"删不动却仍报成功：{out}"
    assert "PermissionError" in out, f"诊断里没有用户看得懂的原因：{out}"
    assert any(str(Path(p).name) in out for p in victims), f"诊断里没写出删不动的文件名：{out}"


# ========================================================================= BUG-88
# ProjectCompileResult.errors 里除 `模块名 -> 错误` 外还挂着非模块键的诊断
# （_entry_point / _cycles / _discovery / _），cli 失败分支只遍历 failed_modules，
# 于是 `build --entry nosuch` 给出 rc=1 + 「Failed modules (0)」，那句原因永远打不出来。

SAMPLE_PROJECT = ROOT / "examples" / "test_project"


def test_r5_88_rejected_entry_name_reaches_user(tmp_path):
    """rc=1 的诊断里必须写出被拒的 entry 名，而不是只报一个空的失败清单。"""
    r = _cli(
        "build", str(SAMPLE_PROJECT), "--entry", "nosuch", "-o", str(tmp_path / "out"), cwd=tmp_path
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 1, f"入口点不存在时应当失败：{out[-400:]}"
    assert "nosuch" in out, f"只打了失败清单，没写被拒的 entry：{out[-500:]}"
    assert "entry" in out.lower(), f"诊断里看不出是入口点被拒：{out[-500:]}"


def test_r5_88_no_cypy_files_reason_reaches_user(tmp_path):
    """同族：空项目的 `_` 键诊断（No .cypy files found）也不能再被丢掉。"""
    (tmp_path / "empty_project").mkdir()
    r = _cli("build", str(tmp_path / "empty_project"), "-o", str(tmp_path / "out"), cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 1, out[-300:]
    assert "reason" in out.lower(), f"rc=1 却没给出原因：{out[-400:]}"
    assert "Failed modules (0)" not in out, f"仍然只用空清单交代失败：{out[-400:]}"


def test_r5_88_cycle_reason_reaches_user(tmp_path):
    """同族 `_cycles` 键：模块因成环被丢弃时，rc=1 的诊断要写清是哪几个、为什么。"""
    proj = tmp_path / "cyclic"
    proj.mkdir()
    (proj / "a.cypy").write_text(
        "from b import fb\n\ndef fa() -> int:\n    return 1\n", encoding="utf-8", newline="\n"
    )
    (proj / "b.cypy").write_text(
        "from a import fa\n\ndef fb() -> int:\n    return 2\n", encoding="utf-8", newline="\n"
    )
    r = _cli("build", str(proj), "-o", str(tmp_path / "out"), cwd=tmp_path)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 1, out[-400:]
    assert "cycle" in out.lower(), f"成环被丢弃这件事没进诊断：{out[-500:]}"
    assert "Failed modules (0)" not in out, f"仍然只用空清单交代失败：{out[-400:]}"


# ========================================================================= BUG-89
# `build --check-only` 分支自成一段，从不读 args.entry：docs/USAGE.md:102 承诺
# 「--entry main 仅编译 main 模块及其依赖」，检查模式下范围却始终是整项目。
# examples/test_project 的依赖形状：main -> {geometry, types}，geometry -> {types}，types -> {}。

SAMPLE_MODULES = ("main", "geometry", "types")


def test_r5_89_check_only_honours_entry_scope(tmp_path):
    """正例：`--check-only --entry geometry` 只检查 geometry 与它的依赖 types，不碰 main。"""
    r = _cli(
        "build",
        str(SAMPLE_PROJECT),
        "--entry",
        "geometry",
        "--check-only",
        "-o",
        str(tmp_path / "out"),
        cwd=tmp_path,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    assert "geometry: type check passed" in out, f"入口模块没被检查：{out[-400:]}"
    assert "types: type check passed" in out, f"入口的依赖没被检查：{out[-400:]}"
    assert (
        "main: type check passed" not in out
    ), f"--check-only 仍然无视 --entry 扫了全部模块：{out[-500:]}"
    assert re.search(r"(?i)scope|entry", out), f"检查范围没交代给用户：{out[-300:]}"


def test_r5_89_check_only_without_entry_still_checks_everything(tmp_path):
    """同族对照：不带 --entry 时仍是全项目检查（docs/USAGE.md:103 的「全项目」口径）。"""
    r = _cli(
        "build", str(SAMPLE_PROJECT), "--check-only", "-o", str(tmp_path / "out"), cwd=tmp_path
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out[-400:]
    for mod in SAMPLE_MODULES:
        assert f"{mod}: type check passed" in out, f"全项目检查漏了 {mod}：{out[-400:]}"


def test_r5_89_check_only_with_unknown_entry_fails_loudly(tmp_path):
    """入口点不存在时不得退回成全项目检查：必须非零退出并写出被拒的 entry。"""
    r = _cli(
        "build",
        str(SAMPLE_PROJECT),
        "--entry",
        "nosuch",
        "--check-only",
        "-o",
        str(tmp_path / "out"),
        cwd=tmp_path,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode != 0, f"entry 被拒却回报成功：{out[-400:]}"
    assert "nosuch" in out, f"诊断里没有被拒的 entry 名：{out[-400:]}"
    assert "main: type check passed" not in out, f"entry 解析失败却退回整项目检查：{out[-500:]}"
