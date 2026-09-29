"""T0r258.4.2 —— 判据「真咬合」的回归桩（只钉结构事实，不钉「全绿」）。

`Find_BUG/audit_2026q3/feat_anchor_01.py` 负责审计每条 golden 的约束厚度，
`tests/test_golden_anchor_probes.py` 负责钉配对完整性与探针决定性。本文件补的是
上一轮实测出的四条**判据自身**的结构缺陷（LINK-1~LINK-4）已经封死：

  LINK-1  `python -m cypyc ...` 必须把 cli.main() 的返回码传播成进程退出码，
          否则 scripts/e2e_golden.sh 的 RUNFAIL 分支只对「进程自己死了」有反应。
  LINK-2  CLI 失败横幅（`[FAIL] Execution failed:` 等）不得被当成程序 stdout
          比对/注册 —— 用假 python 端到端验证判据本身。
  LINK-3  空 / 纯空白 golden 不得再算绿；`--update` 也不得把它写盘。
  LINK-4  UNREG/RUNFAIL/WARN 任一非零都必须让判据非 0 退出。
  外加    编译子进程必须与「产物目录里有与 stdlib 撞名的 .pyd」隔离
          （那曾让 setup.py 崩成 7 份相同的 traceback 基准），
          以及示例名不得再撞 stdlib 模块名。

这里没有 skip：判据脚本本身是 bash 写的，跑不了 bash 就等于跑不了判据，
那种环境该报错而不是静默通过。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JUDGE = REPO / "scripts" / "e2e_golden.sh"
EXAMPLES = REPO / "examples"

# 与 stdlib 撞名的示例名会把 output/ 变成地雷场（见 hook.py build_isolated_command）。
# sys.stdlib_module_names 是 3.10+；更老的解释器退回这份手抄清单（都是本仓示例用过的词）。
_FALLBACK_STDLIB_NAMES = {
    "struct", "types", "copy", "math", "queue", "random", "signal", "string",
    "typing", "typing_extensions", "enum", "abc", "ast", "csv", "datetime",
    "decimal", "difflib", "fractions", "functools", "gzip", "heapq", "html",
    "inspect", "io", "ipaddress", "json", "logging", "os", "pdb", "pickle",
    "socket", "sqlite3", "ssl", "statistics", "sys", "tempfile", "textwrap",
    "threading", "time", "token", "tokenize", "traceback", "unittest", "uuid",
    "warnings", "weakref", "zipfile", "zlib",
}


def stdlib_module_names():
    names = getattr(sys, "stdlib_module_names", None)
    return set(names) if names else set(_FALLBACK_STDLIB_NAMES)


def example_sources():
    return sorted(p for p in EXAMPLES.glob("*.cypy") if not p.name.startswith("_"))


class TestExitCodePropagation:
    """LINK-1：失败必须让进程退出码变红，而不只是打印一行 [FAIL]。"""

    def test_module_entry_propagates_failure(self):
        missing = REPO / "examples" / "__no_such_cypy_file__.cypy"
        proc = subprocess.run(
            [sys.executable, "-m", "cypyc", "run", str(missing)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(REPO), timeout=300)
        assert proc.returncode != 0, (
            "`python -m cypyc run <坏例子>` 退出码为 0 —— 判据的 RUNFAIL 分支"
            "将只对进程自身死亡有反应\n%s" % proc.stdout[-800:])
        assert "Execution failed" in (proc.stdout + proc.stderr)

    def test_module_entry_keeps_success_zero(self):
        # 同一入口在成功路径上必须仍然是 0（否则上一条断言可以靠「永远红」蒙过）
        proc = subprocess.run(
            [sys.executable, "-m", "cypyc", "--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(REPO), timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestStdlibNameCollision:
    """LINK 清污：示例名不得撞 stdlib —— output/ 会在运行期被挂到 sys.path 上。"""

    def test_no_example_shadows_a_stdlib_module(self):
        names = stdlib_module_names()
        collided = sorted(p.name for p in EXAMPLES.glob("*.cypy")
                          if p.stem.lower() in names)
        assert not collided, (
            "以下示例名与 stdlib 模块同名，其编译产物会遮蔽 stdlib："
            "%s（曾使 output/setup.py 在 import zipfile -> import struct 处崩溃，"
            "并把同一份 traceback 冻结成 7 份 golden）" % ", ".join(collided))

    def test_pending_suspensions_are_marked_by_underscore(self):
        # 挂起约定：下划线前缀 = 判据不跑；这类文件必须写清被哪个 BUG 挡住
        pend = sorted(EXAMPLES.glob("_pending_*.cypy"))
        assert pend, "examples/ 里应有被显式挂起的缺陷用例（_pending_*.cypy）"
        for p in pend:
            text = p.read_text(encoding="utf-8", errors="replace")
            assert "BUGS.md" in text or "BUG-0" in text, \
                "%s 没有说明挂起理由与缺陷编号" % p.name


class TestBuildPathIsolation:
    """清污的通用防线：构建子进程不得把产物目录塞进 sys.path[0]。"""

    def test_build_command_isolates_script_dir(self):
        from cypy_hook.hook import build_isolated_command, build_isolated_env
        cmd = build_isolated_command("setup.py", "build_ext", "--inplace")
        assert cmd[0] == sys.executable
        assert cmd[-3:] == ["setup.py", "build_ext", "--inplace"]
        if sys.version_info >= (3, 11):
            assert "-P" in cmd, "3.11+ 必须用 -P 取消脚本目录的隐式 sys.path 注入"
        env = build_isolated_env({"PATH": "/keep/me"})
        assert env["PYTHONSAFEPATH"] == "1"
        assert env["PATH"] == "/keep/me"

    def test_safe_path_flag_actually_protects_stdlib(self, tmp_path):
        """端到端验证机制本身：产物目录里放一份遮蔽 stdlib 的模块，
        只有加了 -P 的子进程才会重新拿到真 stdlib。"""
        shadow = tmp_path / "struct.py"
        shadow.write_text('raise RuntimeError("shadowed stdlib struct")\n',
                          encoding="utf-8")
        probe = tmp_path / "probe.py"
        probe.write_text("import struct\nprint(struct.__file__)\n", encoding="utf-8")

        plain = subprocess.run([sys.executable, str(probe)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               cwd=str(tmp_path), timeout=120)
        assert plain.returncode != 0, (
            "不带 -P 时子进程居然没被同目录的 struct.py 遮蔽 —— "
            "这条测试的判据依据本身失效了")

        isolated = subprocess.run(
            ([sys.executable, "-P"] if sys.version_info >= (3, 11) else [sys.executable])
            + [str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(tmp_path), timeout=120,
            env={**os.environ, "PYTHONSAFEPATH": "1"})
        assert isolated.returncode == 0, isolated.stdout + isolated.stderr
        assert "shadowed stdlib" not in isolated.stdout
        assert "struct" in isolated.stdout


# --------------------------------------------------------------------------- #
# LINK-2 / LINK-3 / LINK-4：拿假 python 端到端考判据本身
# --------------------------------------------------------------------------- #

_SHIM = r"""#!/usr/bin/env bash
# 假 python：只服务 `-m cypyc run`，按 SHIM_MODE 吐出预先准备好的 CLI 输出。
case "$1 $2" in
  "-m cypyc")
    case "$SHIM_MODE" in
      clean)
        echo "Running $4..."
        echo "Output directory: output"
        echo "hello from shim"
        echo "[OK] Execution successful"
        echo "  Output: 0"
        exit 0
        ;;
      cli_fail_zero)   # LINK-1 修好之前的样子：打印失败横幅却 exit 0
        echo "Running $4..."
        echo "Output directory: output"
        echo "[FAIL] Execution failed:"
        echo "  - 编译错误: Traceback (most recent call last):"
        echo '  File "X:\repo\output\setup.py", line 1, in <module>'
        echo "AttributeError: 'dict' object has no attribute 'width'"
        exit 0
        ;;
      empty)
        echo "Running $4..."
        echo "Output directory: output"
        echo "[OK] Execution successful"
        echo "  Output: None"
        exit 0
        ;;
      nonzero)
        echo "Running $4..."
        echo "[FAIL] Execution failed:"
        echo "  - 运行错误: boom"
        exit 3
        ;;
    esac
    ;;
esac
exit 0
"""


def _judge_fixture(tmp_path, golden_text):
    """把真判据脚本连同 examples/ 与假 python 复制进 tmp_path，返回 (脚本, env)。"""
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "examples").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    script = tmp_path / "scripts" / "e2e_golden.sh"
    script.write_text(JUDGE.read_text(encoding="utf-8"), encoding="utf-8",
                      newline="\n")
    (tmp_path / "examples" / "sample.cypy").write_text(
        'def main() -> int:\n    print("hello from shim")\n    return 0\n',
        encoding="utf-8")
    golden = tmp_path / "examples" / "sample.out"
    if golden_text is not None:
        golden.write_text(golden_text, encoding="utf-8", newline="\n")
    shim = tmp_path / "bin" / "python"
    shim.write_text(_SHIM, encoding="utf-8", newline="\n")
    os.chmod(shim, 0o755)
    env = dict(os.environ)
    env["PATH"] = str(tmp_path / "bin") + os.pathsep + env.get("PATH", "")
    return script, env


def _run_judge(tmp_path, mode, golden_text, extra_args=()):
    script, env = _judge_fixture(tmp_path, golden_text)
    env["SHIM_MODE"] = mode
    proc = subprocess.run(["bash", str(script)] + list(extra_args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=str(tmp_path), env=env, timeout=300)
    return proc


class TestJudgeRefusesFakeGreen:
    """判据在「进程绿灯但内容有毒」的样本上必须报红。"""

    def test_clean_sample_is_green(self, tmp_path):
        proc = _run_judge(tmp_path, "clean", "hello from shim\n")
        assert "PASS  sample.cypy" in proc.stdout, proc.stdout + proc.stderr
        assert "summary: PASS=1 FAIL=0 UNREG/RUNFAIL=0 WARN=0" in proc.stdout, proc.stdout
        assert proc.returncode == 0

    def test_cli_failure_banner_is_not_program_output(self, tmp_path):
        """LINK-2：失败诊断混进程序输出 -> 判 FAIL，且不参与比对也不写盘。"""
        poisoned = (
            "[FAIL] Execution failed:\n"
            "  - 编译错误: Traceback (most recent call last):\n")
        proc = _run_judge(tmp_path, "cli_fail_zero", poisoned)
        assert proc.returncode != 0, (
            "CLI 失败诊断被当成程序 stdout 比对通过了（golden 里就留着 traceback）\n"
            + proc.stdout)
        assert "FAIL  sample.cypy" in proc.stdout
        assert "拒绝比对/注册" in proc.stdout
        # 基准内容没有被改写
        assert (tmp_path / "examples" / "sample.out").read_text(
            encoding="utf-8") == poisoned

    def test_update_refuses_to_register_failure_banner(self, tmp_path):
        """LINK-2 + --update：一次注册不得再冻结出 traceback 基准。"""
        before = "[FAIL] Execution failed:\n"
        proc = _run_judge(tmp_path, "cli_fail_zero", before, extra_args=["--update"])
        assert proc.returncode != 0, proc.stdout + proc.stderr
        written = (tmp_path / "examples" / "sample.out").read_text(encoding="utf-8")
        assert written == before, "--update 把失败诊断写进了基准"

    def test_empty_golden_is_not_green(self, tmp_path):
        """LINK-3：空 golden 过去记 WARN 后整体仍 exit 0。"""
        proc = _run_judge(tmp_path, "empty", "\n")
        assert proc.returncode != 0, proc.stdout
        assert "FAIL  sample.cypy" in proc.stdout
        assert "无约束力" in proc.stdout

    def test_update_refuses_empty_golden(self, tmp_path):
        proc = _run_judge(tmp_path, "empty", None, extra_args=["--update"])
        assert proc.returncode != 0, proc.stdout
        assert not (tmp_path / "examples" / "sample.out").exists(), \
            "--update 注册了一条零输出的空基准"

    def test_machine_absolute_path_in_golden_is_not_green(self, tmp_path):
        proc = _run_judge(tmp_path, "clean", 'hello from shim\nX:\\repo\\output\\setup.py\n')
        assert proc.returncode != 0, proc.stdout
        assert "绝对路径" in proc.stdout

    def test_nonzero_run_exit_code_gates_red(self, tmp_path):
        """LINK-4：RUNFAIL 过去只记录不进末行门控。"""
        proc = _run_judge(tmp_path, "nonzero", "hello from shim\n")
        assert proc.returncode != 0, proc.stdout
        assert "RUNFAIL" in proc.stdout

    def test_unregistered_golden_gates_red(self, tmp_path):
        proc = _run_judge(tmp_path, "clean", None)
        assert proc.returncode != 0, proc.stdout
        assert "UNREG" in proc.stdout


class TestJudgeScriptOnlyGotStricter:
    """把「只准变严」写成机检：新判据必须保留旧判据的全部剥离规则。"""

    def test_old_strip_rules_survive(self):
        text = JUDGE.read_text(encoding="utf-8")
        # 旧版 strip_debug 的每一条剥离规则都必须还在（只允许增，不允许删）
        for marker in ("/^Running /", "/^Output directory: /",
                       "/^\\[OK\\] Execution successful/", "/^  Output: /",
                       "/^============/", "/^  Cypy Transpiler/",
                       "/^\\[[0-9]+\\/3\\]/", "/^\\[INFO\\]/", "/^$/"):
            assert marker in text, "旧判据的剥离/防伪规则 %r 不见了（判据被放宽？）" % marker
        assert "is_deadbeef" in text, "防伪死码哨兵被删 —— 判据被放宽"
        # 新增的 LINK-2 规则也必须在位
        assert "/^[[]FAIL] /" in text, "strip_debug 不再从 [FAIL] 横幅处截断"

    def test_every_branch_is_counted(self):
        text = JUDGE.read_text(encoding="utf-8")
        for gate in ('[ "$fail" -eq 0 ]', '[ "$runfail" -eq 0 ]', '[ "$warn" -eq 0 ]'):
            assert gate in text, "末行门控缺少 %s —— 该类不通过项又变成静默绿" % gate

    def test_real_examples_have_no_cli_failure_banner(self):
        """误伤防护的反证：现有示例的真实输出里不该出现 `[FAIL] ` 行首文本。"""
        offenders = []
        for golden in sorted(EXAMPLES.glob("*.out")):
            for line in golden.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("[FAIL] ") or line.startswith("[FAIL] Execution"):
                    offenders.append("%s: %s" % (golden.name, line))
        assert not offenders, "以下基准以 CLI 失败横幅开头：%s" % ", ".join(offenders)


def test_bash_is_available():
    assert shutil.which("bash"), (
        "找不到 bash：scripts/e2e_golden.sh 本身就是 bash 判据，"
        "没有 bash 就无法验证外部锚点，这里按失败处理而不是静默跳过")
