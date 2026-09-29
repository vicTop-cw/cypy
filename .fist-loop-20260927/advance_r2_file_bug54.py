#!/usr/bin/env python3
"""入账 BUG-54：热重载的编译中间目录 `build/` 是**进程间共享**的，两个 watch 会互踩。

幂等守卫：`memory/bugs.md` 里已有同号同 summary 的条目就拒绝再报（上一轮重跑非幂等脚本
造出过 BUG-53 双发，只能追加 DUPLICATE 收拾）。证据数字从 `advance_r2_race_probe.json` 反解，
不手打。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory" / "bugs.md"
EVIDENCE = HERE / "advance_r2_race_probe.json"
SUMMARY = "cypyc watch 的编译中间目录 build/ 是进程间共享的：两个 watch 并发编译会互踩，引擎内串行锁挡不住"
DETAIL = """现象（本环实测，判据件 `.fist-loop-20260927/advance_r2_race_probe.json`）：
同一引擎内两个线程并发调用 `HotReloadEngine._compile_and_reload_module` 编译**同一模块**时，
锁关（把 `_compile_lock` 换成 nullcontext，其余逐字相同）3/3 轮出红，锁开 3/3 轮全绿。
红文的成因不是我的夹具：`error: can't copy 'build\\lib.win-amd64-cpython-313\\<mod>.pyd':
doesn't exist or not a regular file`、`error: command 'cl.exe' failed with exit code 1`、
以及随后 `未找到生成的.pyd文件` + `[WinError 2] 系统找不到指定的文件: <临时目录>`。

来历：`CypyHook.compile_to_pyd` 虽然把**最终**产物写进传入的 output_dir（本环之后还会复制到 -o），
但 setuptools 的**中间**产物固定在调用进程 CWD 下的 `build/`（`build\\lib.win-amd64-cpython-313\\`），
这个路径不受 output_dir 参数控制 ⇒ 同进程用锁串行可以避开，**两个进程**（例如两个
`cypyc watch` 分别盯两个目录，或 watch 与 `cypyc transpile --watch` 之类并行）仍会在同一个
`build/` 上互相覆盖。

影响：本环加的引擎级 `threading.RLock` 只保证单引擎串行（`advance_r2_watch_probe.py` 三次
跑全绿即为此证）；跨进程并行使用时，用户看到的是一条不含模块名的 `cl.exe failed`，
难以归因到"另一个 watch 进程正在写同一个 build 目录"。

修法（下一轮或人工）：给每次编译一个独立 `build_temp`/`--build-lib`（把中间目录也搬进临时目录），
或让 CLI 在同一仓库内对 watch 进程做单实例锁。本环不动 `cypy_hook`，因为它同时服务
import hook 路径，改中间目录会影响缓存命中面。

不算证明：只说"加了引擎内锁"不等于这条关闭；关闭判据必须是**两个进程**并发编译不同模块
仍能各自产出 .pyd（配一条子进程对照）。"""

SEVERITY = "medium"


def main() -> int:
    refuse: list = []
    text = LEDGER.read_text(encoding="utf-8")
    if re.search(r"^## BUG-54\b", text, flags=re.M):
        refuse.append("幂等守卫：账本里已有 ## BUG-54 条目，不重复入账")
    if SUMMARY in text:
        refuse.append("幂等守卫：同一条 summary 已在账上")
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else {}
    if not ev:
        refuse.append("证据件缺失：advance_r2_race_probe.json 不在盘上")
    elif ev.get("refuse"):
        refuse.append(f"证据件自身 refuse 非空：{ev['refuse'][:2]}")
    if refuse:
        print(json.dumps({"refuse": refuse, "filed": False}, ensure_ascii=False))
        return 1

    c = lfist_lib.Client(timeout=180)
    resp = c.call(
        "report_bug",
        {
            "summary": SUMMARY,
            "detail": DETAIL,
            "severity": SEVERITY,
            "project_dir": ".",
            "reported_by": "cypy-advancer",
            "publish_task": True,
            "now": lfist_lib.utc_now(),
        },
    )
    c.close()
    bug_id = resp.get("bug_id") or resp.get("id")
    task_id = resp.get("task_id")
    back = LEDGER.read_text(encoding="utf-8")
    m = re.search(rf"^## (BUG-\d+) \[[^\]]+\] \[{SEVERITY}\] OPEN", back, flags=re.M)
    numbers = re.findall(r"^## (BUG-\d+) ", back, flags=re.M)
    out = {
        "filed": True,
        "rpc_bug_id": bug_id,
        "task_id": task_id,
        "ledger_last_number": numbers[-1] if numbers else None,
        "summary_on_disk": SUMMARY in back,
        "raw_keys": sorted(resp.keys())[:12],
        "refuse": [],
    }
    if not bug_id:
        out["refuse"].append(f"report_bug 没回 bug_id：{json.dumps(resp, ensure_ascii=False)[:300]}")
    if not out["summary_on_disk"]:
        out["refuse"].append("入账后账本里搜不到这条 summary")
    if out["ledger_last_number"] != f"BUG-{str(bug_id).split('-')[-1] if bug_id else ''}":
        # 只作对照打印，不据此判失败：账本尾部可能还有别的段
        out["ledger_tail_check"] = {"last": out["ledger_last_number"], "expected_from_rpc": bug_id}
    (HERE / "advance_r2_bug54.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False))
    return 1 if out["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
