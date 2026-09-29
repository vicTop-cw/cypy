#!/usr/bin/env python3
"""R2-寻虫 两组确诊控制（避免上一版的 -c 引号把探针本身跑挂了）。

控制 1（hook 是否 durable）：文档 docs/USAGE.md:121 声明 `cypyc hook install` 会"安装 import hook
（写入用户 sitecustomize / 注册）"。判据 = 换一个**新进程**问 `is_hook_installed()`，
而不是问刚刚那个装完就退出的进程。
控制 2（watch 是否真的热重载）：分别**改动已有文件**与**新增文件**，看 output/ 里是否出现产物。
两种形状都试，才能把"产品不做"和"我只试了一种触发方式"分开。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
HERE = Path(__file__).resolve().parent
PY = sys.executable
PROBE = ROOT / ".fist-loop-20260927" / "probes" / "r2_hook_state.py"

CHECK_SNIPPET = (
    "import cypy_hook\n" "print('FRESH_PROC_INSTALLED=' + str(cypy_hook.is_hook_installed()))\n"
)
SAME_PROC = (
    "import sys, cypy_hook\n"
    "cypy_hook.install_hook()\n"
    "print('SAME_PROC_INSTALLED=' + str(cypy_hook.is_hook_installed()))\n"
    "print('META0=' + type(sys.meta_path[0]).__name__)\n"
)


def run(args: list, cwd: Path, timeout: int = 90) -> dict:
    p = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "rc": p.returncode,
        "out": (p.stdout or "").strip(),
        "err": (p.stderr or "").strip(),
    }


def hook_durability() -> dict:
    before = run([PY, "-X", "utf8", "-c", CHECK_SNIPPET], ROOT)
    inst = run([PY, "-X", "utf8", "-m", "cypyc", "hook", "install"], ROOT)
    after = run([PY, "-X", "utf8", "-c", CHECK_SNIPPET], ROOT)
    same = run([PY, "-X", "utf8", "-c", SAME_PROC], ROOT)
    un = run([PY, "-X", "utf8", "-m", "cypyc", "hook", "uninstall"], ROOT)
    site = run([PY, "-X", "utf8", "-c", "import site; print(site.getusersitepackages())"], ROOT)
    return {
        "before_install": before,
        "install_cli": inst,
        "fresh_process_after_install": after,
        "same_process_api": same,
        "uninstall_cli": un,
        "user_site": site,
        "verdict": (
            "durable"
            if "FRESH_PROC_INSTALLED=True" in after["out"]
            else "install 只在退出即销毁的进程里改了 sys.meta_path，新进程仍判未装"
        ),
    }


def watch_triggers() -> dict:
    work = Path(tempfile.mkdtemp(prefix="r2watch3_"))
    try:
        (work / "lib.cypy").write_text(
            'def greet(who: str) -> str:\n    return "hi " + who\n', encoding="utf-8"
        )
        (work / "a.cypy").write_text("let n: int = 1\nprint(n)\n", encoding="utf-8")
        proc = subprocess.Popen(
            [PY, "-X", "utf8", "-u", "-m", "cypyc", "watch", str(work), "--debounce", "0.2"],
            cwd=str(work),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        time.sleep(6)
        at_start = sorted(p.name for p in work.rglob("*") if p.is_file())
        (work / "a.cypy").write_text("let n: int = 99\nprint(n)\n", encoding="utf-8")
        time.sleep(8)
        after_modify = sorted(p.name for p in work.rglob("*") if p.is_file())
        (work / "b.cypy").write_text("let m: int = 2\nprint(m)\n", encoding="utf-8")
        time.sleep(8)
        after_add = sorted(p.name for p in work.rglob("*") if p.is_file())
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        tail = []
        if proc.stdout:
            tail = proc.stdout.read().splitlines()
            proc.stdout.close()
        events = [ln.strip()[:150] for ln in tail if ln.strip()][:14]
        return {
            "files_at_start": at_start,
            "files_after_modify": after_modify,
            "files_after_add": after_add,
            "modify_recompiled": any(f.endswith((".pyx", ".pyd")) for f in after_modify),
            "add_recompiled": any(f.endswith((".pyx", ".pyd")) for f in after_add),
            "stdout_lines": events,
        }
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    doc = {"hook_durability": hook_durability(), "watch_triggers": watch_triggers()}
    (HERE / "hunt_r2_controls.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "hook_verdict": doc["hook_durability"]["verdict"],
                "fresh_proc_out": doc["hook_durability"]["fresh_process_after_install"]["out"][:80],
                "same_proc_out": doc["hook_durability"]["same_process_api"]["out"][:80],
                "watch_modify": doc["watch_triggers"]["modify_recompiled"],
                "watch_add": doc["watch_triggers"]["add_recompiled"],
                "watch_lines": doc["watch_triggers"]["stdout_lines"][:4],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
