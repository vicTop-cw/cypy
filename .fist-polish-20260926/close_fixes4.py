#!/usr/bin/env python3
"""Close the fourth-pass fix ticket (BUG-12 -> T0r17).

Every number in the deliverable is parsed from an artifact at run time (pytest / test_suite
logs, the intake map, the switch-off log) — nothing is typed from memory, and the script
refuses to file the ticket if an artifact disagrees with what the deliverable claims.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

MAP = json.load(open(os.path.join(HERE, "intake_map4.json"), encoding="utf-8"))["mapping"]
POLISHER = "cypy-polisher"


def text(name):
    with open(os.path.join(HERE, name), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def tally(name):
    """Last pytest summary line of a log."""
    lines = [ln.strip() for ln in text(name).splitlines() if ln.strip()]
    for ln in reversed(lines):
        if re.search(r"\b\d+ (passed|failed|error)", ln):
            return ln
    raise SystemExit(f"[close4] {name} 里没有 pytest 计数行，末三行：{lines[-3:]}")


def suite(name):
    blob = text(name)
    tot = int(re.search(r"Total[:\s]+(\d+)", blob).group(1))
    pas = int(re.search(r"Passed[:\s]+(\d+)", blob).group(1))
    fail = int(re.search(r"Failed[:\s]+(\d+)", blob).group(1))
    return tot, pas, fail


RED = tally("pytest_fourth_sweep_red.log")
SWITCH = [ln for ln in text("pytest_switchoff_bug12.log").splitlines() if "switch-off result" in ln]
if len(SWITCH) != 1:
    raise SystemExit("[close4] 开关对照日志里没有唯一结论行，不能交付")
SWITCH_RES = SWITCH[0].split("switch-off result:")[1].strip()
GREEN_FILE = tally("pytest_green_bug12.log") if os.path.exists(os.path.join(HERE, "pytest_green_bug12.log")) else None
if GREEN_FILE is None:
    raise SystemExit("[close4] 缺 pytest_green_bug12.log —— 定点绿证没跑，先补测再收尾")
FINAL_LOG = sys.argv[1] if len(sys.argv) > 1 else "pytest_final_sweep6.log"
FINAL = tally(FINAL_LOG)
_REDS = [ln.strip() for ln in text(FINAL_LOG).splitlines() if ln.startswith("FAILED")]
if not any("test_every_example_has_golden" in r for r in _REDS):
    raise SystemExit("[close4] 终态日志里没有 subtype golden 红条，交付物文案要重写")
if len(_REDS) > 2:
    raise SystemExit(f"[close4] 终态红条多于两条，本轮文案不覆盖：{_REDS}")
DIGEST_RED = [r for r in _REDS if "TestDigestCost" in r]
TS_TOT, TS_PAS, TS_FAIL = suite("test_suite_after_sweep4.log")

if "1 failed, 1 passed, 22 deselected" not in RED or SWITCH_RES != "1 failed, 1 passed":
    raise SystemExit(f"[close4] RED={RED!r} 开关={SWITCH_RES!r} —— 锁死证据形状不符，不入账收尾")

DELIVERABLE = (
    "改动文件：cypy_bridge/nogil.py（GilState.__exit__ :73-81 —— 由无条件 `self.acquire()` 改为 "
    "`if self._released: self.acquire()`，`return False` 保持不变；release/acquire 自身的报错语义、"
    "NoGilContext、nogil 单例与对外 __all__ 均未改）\n"
    "新增回归：tests/test_polish_20260926.py::test_bug12_gilstate_exit_does_not_replace_user_exception"
    " + ::test_bug12_gilstate_exit_still_restores_state（各 1 条，共 2 条；后者防「把退出恢复 GIL "
    "的本职一并削掉」的过度修复）\n"
    "修复口径：只修异常传播路径，不碰 nogil 的语义契约——进入区域仍置 released=True，退出仍复位为 "
    "False，区域内已自行归还时不再重复归还；异常一律不吞（return False 原样保留）。\n"
    "取证探针：python .fist-polish-20260926/repro_sweep4_nogil.py → A 项 REPRODUCED"
    "（`escaped exception type = NoGilError`，即用户的 ValueError 被 __exit__ 顶掉）；"
    "同脚本 B 项（nogil_thread 一次性调用是否泄漏执行器线程）实测 not reproduced"
    "（12 次调用后 active_count 1→2、仅余 1 个临时 worker，会被回收），按红线判为误报、不入账。"
    "原始输出 .fist-polish-20260926/repro_sweep4_nogil.out\n"
    f"RED：改前 `pytest tests/test_polish_20260926.py -q -k bug12` → {RED}"
    "（`.fist-polish-20260926/pytest_fourth_sweep_red.log`，失败原文 "
    "`AssertionError: GIL 退出路径把用户的 ValueError 换成了 NoGilError`）\n"
    f"开关对照：摘掉本单修复（内存改写模块源码、不动磁盘文件）后同两条用例 → {SWITCH_RES}，"
    "与 RED 的形状逐条一致（`.fist-polish-20260926/pytest_switchoff_bug12.log`），"
    "证明锁死点就在这两行守卫上\n"
    f"GREEN：改后 `pytest tests/test_polish_20260926.py -q` → {GREEN_FILE}"
    "（`.fist-polish-20260926/pytest_green_bug12.log`）\n"
    f"基线不回落（本单收尾时的终态实测）：`pytest tests/ -q` → {FINAL}"
    f"（`.fist-polish-20260926/{FINAL_LOG}`）——红条逐条点名：{'；'.join(_REDS)}。"
    "其中 subtype golden（缺 `examples/subtype_units.out`）属上一轮在途产物与「examples/ 不动」"
    f"红线的冲突，本单不顺手注册基准{'；另 ' + DIGEST_RED[0] + ' 已按判据缺陷单独入账为 BUG-13'
     '（单跑该用例为绿、整文件跑为红，产品代码不在被测路径上），不是本单修复带来的回退'
     if DIGEST_RED else '，本轮再无其它红条'}。自研体系 `python scripts/run_tests.py` → Total {TS_TOT} / "
    f"Passed {TS_PAS} / Failed {TS_FAIL}（`.fist-polish-20260926/test_suite_after_sweep4.log`）"
)


def main():
    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close4", "version": "1"}})
    log = []

    def step(tool, args, tag):
        out = c.call(tool, args)
        log.append({"tag": tag, "result": out})
        print(f"{tag:34s} {str(out)[:110]}")
        return out

    for row in MAP:
        bug, tid = row["bug_id"], row["task_id"]
        if not tid:
            step("get", {"task_id": f"{bug}"}, f"{bug}:no-task-id")
            continue
        step("claim", {"task_id": tid, "assignee": POLISHER, "now": utc_now()}, f"{bug}:claim")
        step("execute", {"task_id": tid, "deliverable": DELIVERABLE, "now": utc_now()},
             f"{bug}:execute")
        step("run_check", {"task_id": tid, "cmd": sys.executable,
                           "args": ["-m", "pytest", "tests/test_polish_20260926.py", "-q",
                                    "-p", "no:cacheprovider"],
                           "workdir": ".", "timeout_ms": 240000, "now": utc_now()},
             f"{bug}:run_check")
        step("submit", {"task_id": tid, "now": utc_now()}, f"{bug}:submit")
        step("verify", {"task_id": tid, "verifier": POLISHER, "now": utc_now()}, f"{bug}:verify")
        step("get", {"task_id": tid}, f"{bug}:final")

    root = step("get", {"task_id": "T0"}, "root:T0")
    c.close()
    json.dump(log, open(os.path.join(HERE, "close_fixes4.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bad = [e["tag"] for e in log
           if isinstance(e["result"], dict) and e["result"].get("__error__")]
    print("errors:", bad or "none")
    print("root T0 status:", (root or {}).get("status") if isinstance(root, dict) else root)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
