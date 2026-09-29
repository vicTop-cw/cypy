#!/usr/bin/env python3
"""R2-寻虫 的两套补充基线（自研套件 + 端到端 golden），等 pytest 之后跑，避免并发污染耗时。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
PY = sys.executable
REFUSE: list = []


def run(args: list, timeout: int) -> tuple:
    p = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    rc_s, out_s = run([PY, "-X", "utf8", "scripts/run_tests.py"], 900)
    line = next((ln.strip() for ln in out_s.splitlines() if "Total:" in ln), "")
    fields = dict(re.findall(r"(\w+):\s*(\d+)", line))
    suite = {
        "rc": rc_s,
        "line": line,
        "fields": fields,
        "green": rc_s == 0
        and fields.get("Failed") == "0"
        and fields.get("Skipped") == "0"
        and fields.get("Passed") == fields.get("Total"),
    }
    if not suite["green"]:
        REFUSE.append(f"suite 不绿：{line} rc={rc_s}")

    rc_e, out_e = run(["bash", "scripts/e2e_golden.sh"], 1800)
    eline = next((ln.strip() for ln in out_e.splitlines() if "summary:" in ln), "")
    ef = dict(re.findall(r"(\w+)=(\d+)", eline))
    e2e = {
        "rc": rc_e,
        "line": eline,
        "fields": ef,
        "green": rc_e == 0 and ef.get("PASS") == "25" and ef.get("FAIL") == "0",
    }
    if not e2e["green"]:
        REFUSE.append(f"e2e 不绿：{eline} rc={rc_e}")

    log = ROOT / ".fist-loop-20260927" / "hunt_r2_pytest.log"
    txt = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    m = re.search(r"(\d+) passed", txt)
    failed = re.findall(r"FAILED (\S+)::(\w+)", txt)
    pytest = {
        "passed": int(m.group(1)) if m else 0,
        "failed": [f"{p}::{n}" for p, n in failed],
        "summary_line": next((ln.strip() for ln in txt.splitlines()[::-1] if " passed" in ln), "")[
            :170
        ],
    }
    if pytest["passed"] < 1868 or pytest["failed"]:
        REFUSE.append(f"pytest 不达标：{pytest['summary_line']} 红={pytest['failed'][:4]}")

    doc = {
        "refuse": REFUSE,
        "pytest": pytest,
        "suite": suite,
        "e2e": e2e,
        "floor": 1868,
    }
    (HERE / "hunt_r2_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False)[:500])
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
