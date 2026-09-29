#!/usr/bin/env python3
"""R2-推进 的接线证据：在**调用面**核对 run_watch 到底把哪三样东西交给了引擎。

不用"源码里出现了某字样"当证据：这里用哨兵对象替换 `CypyHook` 与 `HotReloadEngine`，
真调一次 `cli.run_watch(args)`，把构造函数与 `start()` 收到的实参取出来判。
再加一条引擎面的实测：`start(debounce_delay=…)` 之后监控器里存的到底是几。

输出 `.fist-loop-20260927/advance_r2_wiring.json`，`refuse==[]` 才算三件接线成立。
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
sys.path.insert(0, str(ROOT))
OUT = ROOT / ".fist-loop-20260927" / "advance_r2_wiring.json"

from cypyc.incremental import HotReloadEngine  # noqa: E402
from cypyc.incremental.hot_reload import HotReloadResult  # noqa: E402


class SpyEngine:
    last: dict = {}

    def __init__(self, hook, incremental_compiler=None, artifact_dir=None):
        SpyEngine.last["artifact_dir"] = artifact_dir
        SpyEngine.last["hook_marker"] = getattr(hook, "marker", None)

    def start(self, watch_dirs, on_reload=None, debounce_delay=None):
        SpyEngine.last["watch_dirs"] = list(watch_dirs)
        SpyEngine.last["on_reload_callable"] = callable(on_reload)
        SpyEngine.last["debounce_delay"] = debounce_delay
        # 真调一次回调：回调体里引用了不存在的名字，这一步就会炸出来
        printed = []

        class Sink:
            def write(self, s):
                printed.append(s)

            def flush(self):
                pass

        old = sys.stdout
        sys.stdout = Sink()
        try:
            on_reload(
                HotReloadResult(
                    success=True,
                    recompiled_modules=["m"],
                    updated_modules=["m"],
                    published_artifacts=["C:\\x\\out\\m.pyx", "C:\\x\\out\\m.cp313.pyd"],
                )
            )
        finally:
            sys.stdout = old
        SpyEngine.last["callback_output"] = "".join(printed).strip()

    def stop(self):
        SpyEngine.last["stopped"] = True


class SpyHook:
    def __init__(self, *a, **k):
        self.marker = "spy-hook"
        self.output_dir = None
        self.verbose = None

    def set_output_dir(self, d):
        self.output_dir = d

    def set_verbose(self, v):
        self.verbose = v


def main() -> int:
    refuse: list = []
    import cypyc.cli as cli
    import cypyc.incremental as inc
    import cypy_hook.hook as hook_mod

    tmp = ROOT / ".fist-loop-20260927" / "r2advance" / "wiring"
    tmp.mkdir(parents=True, exist_ok=True)

    real_engine, real_hook_cls, real_sleep = inc.HotReloadEngine, hook_mod.CypyHook, cli.time.sleep
    inc.HotReloadEngine = SpyEngine
    hook_mod.CypyHook = SpyHook
    cli.time.sleep = lambda _s: (_ for _ in ()).throw(KeyboardInterrupt())
    try:
        args = types.SimpleNamespace(
            source=str(tmp), output=str(tmp / "out"), debounce=0.7, verbose=False
        )
        rc = cli.run_watch(args)
    finally:
        inc.HotReloadEngine = real_engine
        hook_mod.CypyHook = real_hook_cls
        cli.time.sleep = real_sleep

    captured = dict(SpyEngine.last)
    if rc != 0:
        refuse.append(f"run_watch Ctrl+C 退出码 {rc}（要 0）")
    if captured.get("artifact_dir") != str(tmp / "out"):
        refuse.append(f"-o 没当成产物目录：{captured.get('artifact_dir')!r}")
    if captured.get("on_reload_callable") is not True:
        refuse.append("CLI 没挂 on_reload 回调（BUG-48 那半才是真的缺）")
    if captured.get("debounce_delay") != 0.7:
        refuse.append(f"--debounce 没传下去：{captured.get('debounce_delay')!r}")
    if "Published 2 artifact(s)" not in captured.get("callback_output", ""):
        refuse.append(f"回调输出不含批次结论：{captured.get('callback_output')!r}")

    # 引擎面实测：监控器真正拿到的 debounce
    monitored = {}
    for label, value in (("explicit", 1.23), ("default", None)):
        eng = HotReloadEngine(SpyHook())
        kwargs = {} if value is None else {"debounce_delay": value}
        eng.start([str(tmp)], **kwargs)
        try:
            monitored[label] = eng._monitor._debounce_delay
        finally:
            eng.stop()
        time.sleep(0.1)
    if monitored.get("explicit") != 1.23:
        refuse.append(f"显式 debounce 没生效：{monitored}")
    if monitored.get("default") != 0.5:
        refuse.append(f"不传时默认被改了：{monitored}")

    doc = {
        "cli_wiring": captured,
        "monitor_debounce_measured": monitored,
        "refuse": refuse,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": refuse, "cli_wiring_keys": sorted(captured), "monitor": monitored}, ensure_ascii=False))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
