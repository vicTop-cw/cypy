"""R1-修复 的双套基线复跑：自研套件 scripts/run_tests.py + 定向 pytest（从改动面反解文件清单）。

反解口径（不手写清单）：本轮动了 cypyc/parser/lexer.py、cypyc/codegen/cython_generator.py、
cypy_bridge/types.py 与 examples/*.out，故定向集合 = tests/ 下**源码里点名**了这些消费面的文件
（Lexer/tokenize、CythonGenerator/cython_code、cypy_bridge/TypeMapper、examples/.out）。
任何一条红 ⇒ 非零退出，且不开账本 FIXED 段。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
TS_RE = re.compile(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)")
NEEDLES = {
    "lexer": r"\bLexer\(|tokenize\(|_skip_whitespace",
    "codegen": r"CythonGenerator|cython_code|_type_to_str",
    "bridge": r"cypy_bridge|TypeMapper\b",
    "examples": r"examples/|\.out\b",
}


def targeted_files() -> dict:
    picked = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [k for k, pat in NEEDLES.items() if re.search(pat, text)]
        if hits:
            picked[str(path.relative_to(ROOT)).replace("\\", "/")] = hits
    return picked


def run(cmd: list, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
    )


def main() -> int:
    refuse = []
    doc = {}

    ts = run([sys.executable, "-X", "utf8", "scripts/run_tests.py"])
    ts_out = (ts.stdout or "") + (ts.stderr or "")
    (HERE / "run_tests_after_r1.log").write_text(ts_out, encoding="utf-8", newline="\n")
    m = TS_RE.search(ts_out)
    if not m:
        refuse.append(
            f"自研套件输出里解析不到 `Total|Passed|Failed` 汇总行（rc={ts.returncode}），"
            f"末 15 行：{ts_out.strip().splitlines()[-15:]}"
        )
        doc["test_suite"] = {"parsed": None}
    else:
        total, passed, failed = (int(x) for x in m.groups())
        doc["test_suite"] = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "rc": ts.returncode,
        }
        if failed or passed != total or ts.returncode != 0:
            refuse.append(f"自研套件未全绿：{m.group(0)} rc={ts.returncode}")

    files = targeted_files()
    if not files:
        refuse.append("定向集合反解为空 —— 判据自己坏了，不能当绿")
        doc["targeted"] = {"files": {}}
    else:
        for grp in NEEDLES:
            if not any(grp in v for v in files.values()):
                refuse.append(f"改动面 {grp} 在定向集合里无人认领（反解口径漏了）")
        proc = run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "pytest",
                *sorted(files),
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ]
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        (HERE / "pytest_targeted_r1.log").write_text(out, encoding="utf-8", newline="\n")
        tail = out.strip().splitlines()[-1:] or [""]
        pm = re.search(r"(\d+) passed", tail[0])
        fm = re.search(r"(\d+) failed", tail[0])
        em = re.search(r"(\d+) error", tail[0])
        doc["targeted"] = {
            "files": files,
            "file_count": len(files),
            "rc": proc.returncode,
            "summary_line": tail[0],
            "passed": int(pm.group(1)) if pm else 0,
            "failed": int(fm.group(1)) if fm else 0,
            "errors": int(em.group(1)) if em else 0,
        }
        if proc.returncode != 0 or not pm or fm or em:
            refuse.append(f"定向 pytest 非全绿：{tail[0]!r} rc={proc.returncode}")

    (HERE / "run_baselines_r1.json").write_text(
        json.dumps({"refuse": refuse, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "test_suite": doc.get("test_suite"),
                "targeted": {k: v for k, v in doc.get("targeted", {}).items() if k != "files"},
            },
            ensure_ascii=False,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
