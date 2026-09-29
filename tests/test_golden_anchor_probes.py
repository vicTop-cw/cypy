"""把「golden 判据厚度审计」长期钉进测试套件（T0r258.4.1 的配套回归桩）。

这里刻意**不**断言「所有 golden 都达到厚度阈值」——那是
`Find_BUG/audit_2026q3/feat_anchor_01.py` 的自门控职责（缺陷仍在时 exit 1），
把它复制成一条会长期红灯的 pytest 用例只会淹掉别的信号。

本文件钉住的是两条不会因为修 bug 而改变结论的结构事实：
  1. examples/ 里每个 .cypy 都必须有配对的 .out（缺了就退化成 UNREG，判据少一条锚点）；
  2. 两个审计探针都必须跑到「决定性结论」（exit 0 = 已修 / exit 1 = 缺陷仍在）；
     探针自身崩溃、超时或返回 2/3（判据自身出错）都算这条测试失败——
     这样锚点不会因为探针烂掉而悄悄变成「没有证据」。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
AUDIT = REPO / "Find_BUG" / "audit_2026q3"
PROBES = ["feat_anchor_01.py", "feat_docs_01.py"]


def example_sources():
    return sorted(p for p in EXAMPLES.glob("*.cypy") if not p.name.startswith("_"))


class TestGoldenPairing:
    """每条外部锚点都必须有基准文件，否则 e2e_golden.sh 只会记 UNREG。"""

    def test_examples_dir_exists(self):
        assert EXAMPLES.is_dir(), "examples/ 不存在，e2e golden 判据无输入"

    def test_every_example_has_golden(self):
        srcs = example_sources()
        assert srcs, "examples/ 里没有任何 .cypy —— 判据空转"
        missing = [p.name for p in srcs if not p.with_suffix(".out").exists()]
        assert not missing, "以下示例缺 golden（判据会记 UNREG）: %s" % ", ".join(missing)

    def test_goldens_are_not_deadbeef_placeholders(self):
        for p in sorted(EXAMPLES.glob("*.out")):
            body = p.read_bytes().strip()
            assert body != b"\xde\xad\xbe\xef", "%s 是占位死码，不是基准" % p.name

    def test_no_example_name_collides_with_stdlib(self):
        """示例名不得撞 stdlib：`examples/struct.cypy` 编出的 `output/struct.*.pyd` 会在
        `python setup.py` 里抢占 sys.path[0]，让 setuptools 崩在 `zipfile -> struct`，
        而崩溃回溯又被判据当成「程序 stdout」冻结进 7 份 golden（BUG-031/032）。"""
        import sys

        colliding = sorted(p.stem for p in example_sources()
                           if p.stem in getattr(sys, "stdlib_module_names", set()))
        assert not colliding, "以下示例名与 stdlib 模块同名: %s" % ", ".join(colliding)


class TestAuditProbesDecisive:
    """审计探针必须永远给出方向明确的结论（0 或 1），不许烂成 2/3/超时。"""

    def test_probe_scripts_present(self):
        for name in PROBES:
            assert (AUDIT / name).exists(), "缺少审计探针 %s" % name

    def test_each_probe_reaches_verdict(self):
        for name in PROBES:
            script = AUDIT / name
            if not script.exists():
                continue
            proc = subprocess.run(
                [sys.executable, str(script)], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600, cwd=str(REPO))
            tail = (proc.stdout or "").strip().splitlines()[-1:] or ["<无输出>"]
            assert proc.returncode in (0, 1), (
                "%s 没有给出决定性结论：exit=%s（2=判据自身出错, 3=探针异常）\n%s\n%s"
                % (name, proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))
            assert "VERDICT" in (proc.stdout or ""), \
                "%s 未打印 VERDICT 段：exit=%s %s" % (name, proc.returncode, tail[0])


class TestCriteriaHealthHonesty:
    """`criteria_health()` 自检段必须双向诚实：拿加固前的判据要报警，拿现在的要放行。

    这一节是「判据的判据」，说它 OK 而实际没加固 = 一条会说谎的诊断（本仓库踩过
    两次：needle 命中自己的注释、以及把已修项继续登记为缺陷）。
    `golden_before/e2e_golden.sh.orig` 是加固前的原件留档，正好当反向对照。
    """

    CODES = ("LINK-2 剥离", "LINK-3 空基准", "LINK-4 末行门控")

    @staticmethod
    def _probe():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "feat_anchor_01", AUDIT / "feat_anchor_01.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @classmethod
    def _notes(cls, judge_text, tmp_path):
        module = cls._probe()
        root = tmp_path / "root"
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "e2e_golden.sh").write_text(judge_text, encoding="utf-8")
        module.ROOT = root
        return dict(module.criteria_health())

    def test_pre_hardening_judge_is_reported_as_broken(self, tmp_path):
        orig = (AUDIT / "golden_before" / "e2e_golden.sh.orig").read_text(encoding="utf-8")
        notes = self._notes(orig, tmp_path)
        for code in self.CODES:
            assert code in notes, "%s 自检项缺失" % code
            assert not notes[code].startswith("OK"), \
                "加固前的判据被判成 OK（假绿自检）: %s -> %s" % (code, notes[code])

    def test_current_judge_is_reported_as_hardened(self, tmp_path):
        current = (REPO / "scripts" / "e2e_golden.sh").read_text(encoding="utf-8")
        notes = self._notes(current, tmp_path)
        for code in self.CODES:
            assert notes[code].startswith("OK"), \
                "判据 %s 的加固回归了: %s" % (code, notes[code])
