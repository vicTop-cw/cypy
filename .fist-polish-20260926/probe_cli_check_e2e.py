#!/usr/bin/env python3
"""End-to-end proof for BUG-11 at the real CLI entry: `cypyc build --check-only`.

Runs the CLI against a throwaway project outside the repo (so nothing is written under
output/ or dist/), and checks the exit code + the diagnostic reaching stdout.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

SOURCE = "def f() -> int:\n    return 1\n\n\ndef f() -> int:\n    return 2\n"


def main():
    with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as out:
        with open(os.path.join(proj, "dup.cypy"), "w", encoding="utf-8") as f:
            f.write(SOURCE)
        proc = subprocess.run(
            [sys.executable, "-m", "cypyc", "build", proj, "--check-only", "-o", out],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
        printed = (proc.stdout or "") + (proc.stderr or "")
        hit = [l.strip() for l in printed.splitlines() if "already declared" in l]
        print("exit:", proc.returncode)
        print("diagnostic lines on stdout:", hit or "（无）")
        print("verdict:", "PASSED-THROUGH" if proc.returncode == 1 and hit else "STILL DROPPED")
        return 0 if (proc.returncode == 1 and hit) else 1


if __name__ == "__main__":
    sys.exit(main())
