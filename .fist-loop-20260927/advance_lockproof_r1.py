"""R1-推进 的「逐单回退树证红」：两条补口各自回退，证明新增的 6 条锁真的承重。

三条判据（沿用 R1-修复 的形状）：
 1. 每条补口在自己的回退树上**至少 1 条锁转红**（否则锁不承重）；
 2. 回退 A 时 B 的锁必须全绿（混因会让红证据归错单）；
 3. 完整树 6 条全绿（证红用的树与验收用的树只差这一处的改动）。

回退是**按文本针**做的：每条都先断言"命中且只命中 1 处"，否则拒绝出结论——
上一轮的教训是同一串在文件里出现 4 次时，补丁会静默针到别处（假绿冒充证明）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"E:\IDEProjects\AI\Cypy")
HERE = Path(__file__).resolve().parent
PKGS = ["cypyc", "cypy_bridge", "cypy_hook"]
TESTS = "tests/test_loop_20260927_advance.py"

ADV1_AFTER = '''    def _visit_RaiseStmt(self, node: Any) -> None:
        """生成 raise 语句的 Cython 代码"""
        if node.exc:
            cause = getattr(node, "cause", None)
            cause_str = f" from {self._expr_to_str(cause)}" if cause is not None else ""
            self._write(f"raise {self._expr_to_str(node.exc)}{cause_str}")
        else:
            self._write("raise")
'''
ADV1_BEFORE = '''    def _visit_RaiseStmt(self, node: Any) -> None:
        """生成 raise 语句的 Cython 代码"""
        if node.exc:
            self._write(f"raise {self._expr_to_str(node.exc)}")
        else:
            self._write("raise")
'''

ADV2_AFTER = """        if self._current().type == TokenType.BUILD_ASSIGN:
            self._consume()
            block = self._parse_build_block(BuildBlockExpr.BUILD_ASSIGN)
            if not isinstance(target, str):
                raise ValueError(
                    f"Left side of =: must be a variable name at "
                    f"{self._current().line}:{self._current().col}"
                )
            return Assign(Name(target, line, col), block, line, col)
        if self._current().type == TokenType.ASSIGN:
"""
ADV2_BEFORE = """        if self._current().type == TokenType.ASSIGN:
"""

LOCKS = {
    "ADV-1": [
        "test_bug_adv1_raise_from_keeps_cause_in_emit",
        "test_bug_adv1_runtime_chain_visible_at_cli",
    ],
    "ADV-2": [
        "test_bug_adv2_let_build_block_form_parses",
        "test_bug_adv2_let_and_bare_forms_emit_identically",
    ],
}
CONTROLS = {
    "ADV-1": ["test_bug_adv1_control_no_cause_raise_unchanged"],
    "ADV-2": ["test_bug_adv2_control_plain_let_still_works"],
}
FILES = {"ADV-1": "cypyc/codegen/cython_generator.py", "ADV-2": "cypyc/parser/parser.py"}
PAIRS = {"ADV-1": (ADV1_AFTER, ADV1_BEFORE), "ADV-2": (ADV2_AFTER, ADV2_BEFORE)}
REFUSE = []


def build_tree(tmp: Path, revert: str | None) -> Path:
    tree = tmp / ("reverted_" + (revert or "none"))
    tree.mkdir(parents=True, exist_ok=True)
    for d in PKGS + ["tests", "scripts", "examples", "PROJECT-SPEC", "SYNTAX"]:
        src = REPO / d
        if src.exists():
            shutil.copytree(src, tree / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pyproject.toml", "conftest.py", "pytest.ini", "setup.py"):
        if (REPO / f).exists():
            shutil.copy2(REPO / f, tree / f)
    if revert:
        rel = FILES[revert]
        p = tree / rel
        text = p.read_text(encoding="utf-8")
        after, before = PAIRS[revert]
        n = text.count(after)
        if n != 1:
            raise RuntimeError(f"回退针 {revert} 在 {rel} 里命中 {n} 处（要求恰好 1）")
        p.write_text(text.replace(after, before), encoding="utf-8", newline="\n")
        if PAIRS[revert][1] not in p.read_text(encoding="utf-8"):
            raise RuntimeError(f"回退后 {rel} 里找不到修复前文本")
    return tree


def run_tests(tree: Path) -> dict:
    """一次 `-v` 跑完：逐条 PASSED/FAILED 行可解析，不靠从摘要行猜。"""
    r = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            TESTS,
            "-v",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-o",
            "addopts=",
        ],
        cwd=str(tree),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    out = (r.stdout or "") + (r.stderr or "")
    (HERE / f"advance_lockproof_{tree.name}.log").write_text(out, encoding="utf-8", newline=chr(10))
    # pytest -v 的行形状是 `tests/x.py::name PASSED [ 16%]`（状态在节点 id **之后**），
    # 而短摘要才是 `FAILED tests/x.py::name`。上一版按 `^PASSED id::` 找 ⇒ passed 恒空，
    # 把 6 条全绿的完整树判成"未收集"。两种形状都收，且只认逐条行不认摘要里的大字。
    per_line = re.findall(r"^\S+::(\w+)\s+(PASSED|FAILED)", out, flags=re.M)
    failed = sorted(
        {n for n, s in per_line if s == "FAILED"}
        | set(re.findall(r"^FAILED \S+::(\w+)", out, flags=re.M))
    )
    passed = sorted({n for n, s in per_line if s == "PASSED"})
    summary = [
        ln for ln in out.splitlines() if " passed" in ln or " failed" in ln or " error" in ln
    ]
    return {
        "rc": r.returncode,
        "failed": failed,
        "passed": passed,
        "collected": len(failed) + len(passed),
        "line": summary[-1][:160] if summary else out[-200:],
    }


def main() -> int:
    reverts = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        full = run_tests(build_tree(tmp, None))
        if full["rc"] != 0 or len(full["passed"]) < 6:
            REFUSE.append(f"判据3 完整树不绿：{full}")
        for who in ("ADV-1", "ADV-2"):
            res = run_tests(build_tree(tmp, who))
            red = [t for t in LOCKS[who] if t in res["failed"]]
            if not red:
                REFUSE.append(f"判据1 回退 {who} 后其锁没转红（锁不承重）：{res}")
            other = "ADV-2" if who == "ADV-1" else "ADV-1"
            mixed = [t for t in LOCKS[other] + CONTROLS[other] if t in res["failed"]]
            if mixed:
                REFUSE.append(f"判据2 回退 {who} 时 {other} 的锁也红了（混因）：{mixed}")
            if CONTROLS[who] and all(t not in res["failed"] + res["passed"] for t in CONTROLS[who]):
                REFUSE.append(f"判据4 {who} 回退树上对照用例未被收集：{res}")
            json_doc = {
                "who": who,
                "red_locks": red,
                "mixed_cause_with_other": mixed,
                "tree_result": res,
            }
            reverts.append(json_doc)
            print(json.dumps(json_doc, ensure_ascii=False))
    out = {"refuse": REFUSE, "full_tree": full, "reverts": reverts}
    (HERE / "advance_lockproof_r1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
