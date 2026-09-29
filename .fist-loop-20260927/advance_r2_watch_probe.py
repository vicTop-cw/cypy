#!/usr/bin/env python3
"""BUG-48 的调用面探针：起一个**真子进程**跑 `cypyc watch`，改文件、加文件，看产物与事件行。

为什么不能只读代码下结论：`HotReloadEngine.start()` 里其实**已经**把 `self._handle_file_changes`
挂给了 watchdog 监控器，而 CLI 少传的 `on_reload` 只是"完成后回调"——所以"没传回调"这句话
推不出"完全不重编译"。谁生效要看盘面：`output/` 里有没有 .pyx、stdout 有没有 `[HotReload] File changed`。

输出 `.fist-loop-20260927/advance_r2_watch_probe.json`：本脚本是**观察件**不是门禁件，
`refuse` 只在"探针自己没跑成"时非空（进程没起来 / 横幅都没打出来），产品行为照实测记录。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
WORK = ROOT / ".fist-loop-20260927" / "r2advance"
SRC = WORK / "src"
OUT = WORK / "out"
LOG = WORK / "watch.log"
RESULT = ROOT / ".fist-loop-20260927" / "advance_r2_watch_probe.json"
BUDGET_S = 30

A_SRC = "def add(a: int, b: int) -> int:\n    return a + b\n"
A_MODIFIED = "def add(a: int, b: int) -> int:\n    return a + b\n\n# touched by probe\n"
B_SRC = "def mul(a: int, b: int) -> int:\n    return a * b\n"


def wait_until(predicate, timeout, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = predicate()
        if got:
            return got
        time.sleep(interval)
    return None


def main() -> int:
    refuse: list = []
    for d in (SRC, OUT):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    (SRC / "a.cypy").write_text(A_SRC, encoding="utf-8")
    if LOG.exists():
        LOG.unlink()

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    logf = LOG.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "cypyc", "watch", str(SRC), "-o", str(OUT), "--debounce", "0.2"],
        cwd=str(ROOT),
        stdout=logf,
        stderr=subprocess.STDOUT,
        env=env,
    )

    def banner_up():
        text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
        return "Engine started" in text or "[CypyFileMonitor]" in text

    started = wait_until(banner_up, 20)
    doc: dict = {"rc_at_check": proc.poll(), "banner_seen": bool(started), "budget_s": BUDGET_S}
    if not started:
        refuse.append(f"watch 进程横幅 20s 内没出现：rc={proc.poll()} log={LOG.read_text(errors='replace')[-400:] if LOG.exists() else '无 log'}")

    events: dict = {}
    if started:
        # 形状 1：改动已存在的文件
        t0 = time.time()
        (SRC / "a.cypy").write_text(A_MODIFIED, encoding="utf-8")
        os.utime(SRC / "a.cypy", (time.time() + 2, time.time() + 2))
        ev1 = wait_until(
            lambda: "[HotReload] File changed" in LOG.read_text(encoding="utf-8", errors="replace") or None,
            12,
        )
        events["modify_event_line"] = bool(ev1)
        events["modify_elapsed_s"] = round(time.time() - t0, 2)

        # 形状 2：新增文件（等到 a 与 b 两份产物都落地，或超时）
        t1 = time.time()
        (SRC / "b.cypy").write_text(B_SRC, encoding="utf-8")

        def both_published():
            names = set(p.name for p in OUT.rglob("*") if p.is_file())
            has_a = any(n.startswith("a.") for n in names)
            has_b = any(n.startswith("b.") for n in names)
            return (sorted(names) if has_a and has_b else None)

        ev2 = wait_until(both_published, 25)
        events["add_produced_or_reloaded"] = bool(ev2)
        events["both_a_and_b_published"] = bool(ev2)
        events["add_elapsed_s"] = round(time.time() - t1, 2)

    time.sleep(1.0)
    text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    doc["events"] = events
    doc["outputs_in_out_dir"] = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    doc["log_lines_total"] = len([ln for ln in text.splitlines() if ln.strip()])
    doc["grep"] = {
        "file_changed": text.count("[HotReload] File changed"),
        "successfully_reloaded": text.count("[HotReload] Successfully reloaded"),
        "failed_to_reload": text.count("[HotReload] Failed to reload"),
        "monitor_found": text.count("Found") and "Cypy files to monitor" in text,
        "callback_error": text.count("[HotReload] Callback error"),
        "watch_published": text.count("[Watch] Published"),
        "watch_no_artifacts": text.count("[Watch] No artifacts published"),
        "traceback": text.count("Traceback"),
    }
    doc["monitor_found_line"] = next((ln for ln in text.splitlines() if "files to monitor" in ln), "")
    doc["tail"] = text[-1200:]
    doc["rc_final_before_terminate"] = proc.poll()

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        doc["terminate_needed_kill"] = True
    logf.close()
    doc["rc_after_terminate"] = proc.poll()

    doc["refuse"] = refuse
    RESULT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("banner_seen", "events", "grep", "outputs_in_out_dir", "monitor_found_line", "rc_after_terminate")}, ensure_ascii=False))
    print(json.dumps({"refuse": refuse}, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
