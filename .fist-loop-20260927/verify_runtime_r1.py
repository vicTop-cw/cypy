"""R1-验证 的「修复面真编译复核」：把三处修复打到真 .pyd / 真 CLI 上，不看生成码看运行期。

BUG-30 的原始主张是**运行期身份**（`type(e)` 是 int 还是 float），只查 `.pyx` 文本是半程取证；
BUG-33/38 的原始主张是 CLI 行为（拒绝/接受 + rc），故一律走子进程实测。
判据三条都要「值 + rc」双向：BUG-30 必须报 float，BUG-33 必须 rc≠0 且带行列，BUG-38 必须 rc=0。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")

SRC_B30 = """
def main() -> int:
    let a: int = 42
    let e: float = a
    print(f"probe: {type(e)} value={e}")
    return 0
"""


def run(cmd: list, cwd: Path) -> tuple:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cypy_verify_r1_"))
    out = {}

    s = tmp / "b30.cypy"
    s.write_text(SRC_B30, encoding="utf-8", newline="\n")
    rc, log = run([sys.executable, "-X", "utf8", "-m", "cypyc", "run", str(s)], ROOT)
    out["bug30"] = {"rc": rc, "line": [l for l in log.splitlines() if "probe:" in l]}
    ok30 = rc == 0 and bool(out["bug30"]["line"]) and "<class 'float'>" in out["bug30"]["line"][0]

    s2 = tmp / "b33.cypy"
    s2.write_text(
        'def main() -> int:\n    let s: str = "abc\n    return 0\n', encoding="utf-8", newline="\n"
    )
    rc2, log2 = run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "cypyc",
            "transpile",
            str(s2),
            "-o",
            str(tmp / "out33"),
        ],
        ROOT,
    )
    diag = [l for l in log2.splitlines() if "Unterminated string" in l]
    out["bug33"] = {"rc": rc2, "diag": diag}
    ok33 = rc2 != 0 and bool(diag) and ":" in diag[0]

    s3 = tmp / "b38.cypy"
    s3.write_bytes(b"def main() -> int:\n    return 0   ")
    rc3, log3 = run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "cypyc",
            "transpile",
            str(s3),
            "-o",
            str(tmp / "out38"),
        ],
        ROOT,
    )
    out["bug38"] = {"rc": rc3, "tail": log3.strip().splitlines()[-3:]}
    ok38 = rc3 == 0 and "TypeError" not in log3

    verdict = {
        "ok": ok30 and ok33 and ok38,
        "bug30": ok30,
        "bug33": ok33,
        "bug38": ok38,
        "detail": out,
    }
    (HERE / "verify_runtime_r1.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
