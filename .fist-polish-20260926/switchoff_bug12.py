#!/usr/bin/env python3
"""Switch-off control for BUG-12: does the new test fail when only the fix is removed?

The guard is stripped in-memory (a rewritten copy of cypy_bridge/nogil.py is exec'd under the
same module name); the real source is never touched. If the two tests come out 1 failed / 1
passed — the same shape as the pre-fix RED log — the lock really sits on this fix.
"""
import sys
import types

sys.path.insert(0, r"E:\IDEProjects\AI\Cypy")
sys.stdout.reconfigure(encoding="utf-8")

FIXED = "        if self._released:\n            self.acquire()\n        return False\n"
UNFIXED = "        self.acquire()\n        return False\n"

src = open(r"E:\IDEProjects\AI\Cypy\cypy_bridge\nogil.py", encoding="utf-8").read()
assert src.count(FIXED) == 1, f"当前源码里找不到这一处修复，对照实验的前提已变: {src.count(FIXED)}"
reverted = src.replace(FIXED, UNFIXED)

import cypy_bridge  # noqa: E402  — import the real package first; swapping the submodule
import cypy_bridge.nogil  # noqa: E402    in mid-import would break its own `from .core import`

mod = types.ModuleType("cypy_bridge.nogil")
mod.__file__ = r"E:\IDEProjects\AI\Cypy\cypy_bridge\nogil.py"
sys.modules["cypy_bridge.nogil"] = mod
exec(compile(reverted, mod.__file__, "exec"), mod.__dict__)
cypy_bridge.nogil = mod

import tests.test_polish_20260926 as t  # noqa: E402

results = {}
for name in ("test_bug12_gilstate_exit_does_not_replace_user_exception",
             "test_bug12_gilstate_exit_still_restores_state"):
    try:
        getattr(t, name)()
        results[name] = "passed"
    except AssertionError as exc:
        results[name] = f"FAILED: {str(exc).splitlines()[0][:90]}"

print(f"module identity: {sys.modules['cypy_bridge.nogil'].__name__} "
      f"(in-memory copy, {len(reverted)} chars vs on-disk {len(src)} chars)")
for name, outcome in results.items():
    print(f"  {name} -> {outcome}")

n_fail = sum(1 for v in results.values() if v.startswith("FAILED"))
print(f"switch-off result: {n_fail} failed, {len(results) - n_fail} passed")
if n_fail != 1:
    sys.exit(f"[switchoff] 期望恰好 1 条红（锁死用例），实际 {n_fail} —— 对照不成立，不能交付")
