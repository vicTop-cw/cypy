#!/usr/bin/env python3
"""Switch-off control for BUG-11: revert the fix in place, re-run the final tests, restore.

Adds exactly two lines in cypyc/project/project_compiler.py::type_check_module; the control
removes them, runs `pytest -k bug11` in a subprocess, and restores the bytes. Verifies the
file is byte-identical afterwards (md5 before == md5 after) so a crash can't leave it open.
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "cypyc", "project", "project_compiler.py")
ADDED = [
    "            errors.extend(scope_analyzer.errors)\n",
    "            # 作用域与类型两条通道对同一处会给出逐字相同的诊断（如 Undefined name）\n"
    "            errors = list(dict.fromkeys(errors))\n",
]


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    original = open(TARGET, encoding="utf-8").read()
    digest = md5(TARGET)
    for line in ADDED:
        if line not in original:
            print("[switchoff] 锚点没找到，可能文件形态已变，拒绝继续：\n" + repr(line))
            return 2
    off = original
    for line in ADDED:
        off = off.replace(line, "", 1)

    try:
        with open(TARGET, "w", encoding="utf-8", newline="") as f:
            f.write(off)
        print("[switchoff] OFF-state md5:", md5(TARGET))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_polish_20260926.py", "-q",
             "-k", "bug11", "--no-header", "-rf"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = [l for l in (proc.stdout or "").splitlines() if l.strip()][-6:]
        print("\n".join(tail))
        log = os.path.join(ROOT, ".fist-polish-20260926", "pytest_switchoff_bug11.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write(proc.stdout or "")
    finally:
        with open(TARGET, "w", encoding="utf-8", newline="") as f:
            f.write(original)
        restored = md5(TARGET)
        print("[switchoff] restored md5:", restored, "== before:", restored == digest)
    return 0 if restored == digest else 1


if __name__ == "__main__":
    sys.exit(main())
