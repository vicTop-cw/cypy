"""从 R4-验证 的调用面件反解出永久锁测试文件（不手打源样本，避免「重打 needle 造出假 0」）。

产出 `tests/test_loop_20260927_polish_r4.py`：18 条 CLI 探针逐条钉住退出码与诊断子串，
外加两条「文档↔实测」「账↔卡」一致锁。测试里的 src 全部逐字取自 `verify_r4_callsite.json`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC_ART = HERE / "verify_r4_callsite.json"
OUT = ROOT / "tests" / "test_loop_20260927_polish_r4.py"

HEADER = '"""R4-打磨 的永久回归锁：把 R4-验证 的调用面探针从 .fist-loop 搬进仓库。\n' \
    r'''\
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
'''


TAIL = r'''

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
'''


def main() -> int:
    art = json.loads(SRC_ART.read_text(encoding="utf-8"))
    rows = art["cli_rows"]
    body = [f"    ({json.dumps(r['id'])}, {json.dumps(r['bug'])}, "
            f"{json.dumps(r['role'])}, {json.dumps(r['src'])}, "
            f"{json.dumps(r['want'])}, {json.dumps(r.get('contains') or [])}, "
            f"{json.dumps(r.get('why') or '')}),"
            for r in rows]
    table = "PROBES = [\n" + "\n".join(body) + "\n]\n"
    OUT.write_text(HEADER + table + TAIL, encoding="utf-8", newline="\n")
    print(json.dumps({"written": OUT.relative_to(ROOT).as_posix(), "probes": len(rows)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
