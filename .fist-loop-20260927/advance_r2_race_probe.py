#!/usr/bin/env python3
"""BUG-48 家族的第二半：并发编译批次会互相踩 `build/` —— 开关两态跑在同一夹具上。

形状：`HotReloadEngine._compile_and_reload_module` 用临时目录编译，但 setuptools 的**中间产物**
落在进程 CWD 下共享的 `build/`（报错原文里是 `build\\lib.win-amd64-cpython-313\\<mod>.pyd`）⇒
同一模块的两个批次并发编译时互相覆盖。watchdog 对一次保存会发多个事件，所以这不是罕见路径。

判据形状（成对，缺一半就是摆设）：
- **锁开（当前码）**：N 轮并发必须全绿，且每轮产物都发布到 out 目录；
- **锁关（把 `_compile_lock` 换成空上下文，其余逐字相同）**：N 轮里**至少一轮出红**，
  红的成因必须是编译类错误（不是我的夹具坏了）。
锁关只改测试进程里的实例属性，不落盘、不动产品码。
"""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(ROOT))

from cypy_hook.hook import CypyHook  # noqa: E402
from cypyc.incremental import HotReloadEngine  # noqa: E402

OUT = ROOT / ".fist-loop-20260927" / "advance_r2_race_probe.json"
ATTEMPTS = 3
THREADS = 2


def attempt(idx: int, use_lock: bool) -> dict:
    src = Path(tempfile.mkdtemp())
    out = Path(tempfile.mkdtemp())
    f = src / f"racem_{idx}_{int(use_lock)}.cypy"
    f.write_text("def get_value() -> int:\n    return 1\n", encoding="utf-8")

    hook = CypyHook()
    hook.set_output_dir(str(out))
    eng = HotReloadEngine(hook, artifact_dir=str(out))
    if not use_lock:
        eng._compile_lock = contextlib.nullcontext()

    res = []
    threads = [threading.Thread(target=lambda: res.append(eng._compile_and_reload_module(str(f))))
               for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    errors = [str(e) for r in res for e in r.errors]
    return {
        "successes": sorted(bool(r.success) for r in res),
        "published": [len(r.published_artifacts) for r in res],
        "errors": errors[:2],
        "compileish_failure": any(
            ("编译错误" in e) or ("cl.exe" in e) or ("can't copy" in e) or ("未找到生成的.pyd" in e)
            for e in errors
        ),
    }


def main() -> int:
    refuse: list = []
    on = [attempt(i, True) for i in range(ATTEMPTS)]
    off = [attempt(i, False) for i in range(ATTEMPTS)]

    for i, row in enumerate(on, 1):
        if not all(row["successes"]) or max(row["published"]) < 1:
            refuse.append(f"锁开第{i}轮不绿/无产物：{row['errors'][:1]}")
    off_red = [i for i, row in enumerate(off, 1) if not all(row["successes"])]
    if not off_red:
        refuse.append("锁关的 N 轮全绿 ⇒ 要么并发互踩的成因判断错了，要么这条对照根本没去掉串行（恒绿判据）")
    for i in off_red:
        if not off[i - 1]["compileish_failure"]:
            refuse.append(f"锁关第{i}轮红了但成因不是编译类：{off[i-1]['errors'][:1]}")

    doc = {
        "attempts": ATTEMPTS,
        "threads": THREADS,
        "lock_on": on,
        "lock_off": off,
        "lock_off_red_rounds": off_red,
        "refuse": refuse,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "lock_on_all_green": all(all(r["successes"]) for r in on),
                      "lock_off_red_rounds": off_red}, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
