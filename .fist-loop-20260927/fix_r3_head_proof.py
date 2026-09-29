#!/usr/bin/env python3
"""R3-修复：把 17 条锁拿到**上一提交的产品码树**上重跑一遍。

目的：证明这些锁不是"跟着实现一起写出来的恒绿断言"。做法是 `git worktree add` 出一份
`17d68b4` 的干净树，只把本轮新建的测试文件复制进去跑（产品码是旧的、测试是新的）。

必须如实标注的口径差：`HEAD` **不等于**本环开工时的盘面。仓库有 160+ 行未提交改动
（前几轮的产品码都没提交，红线禁止 commit），所以旧树里缺的不只是本轮六件修复，
还有前几轮的改动 ⇒ 个别红是"陈旧面"造成的（例：`cypy_bridge.memory` 在旧树里没有
`_as_address`）。因此本件只作为**次级**证据，主证据是 `fix_r3_evidence.json` 那份
"同一夹具、修前修后"的翻转对照。

判定：六个 BUG 组每组至少一条红；五条对照锁（control/形状保持）必须**不**红——
对照若在旧树上也红，说明它根本没在测"别动"这件事。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WT = HERE / "tmp_r3" / "head_tree"
TEST_FILE = Path("tests") / "test_loop_20260927_fix_r3.py"
PLAN = json.loads((HERE / "fix_r3_plan.json").read_text(encoding="utf-8"))

CAVEAT = (
    "HEAD(17d68b4) 不是本环开工快照：工作树有 160+ 行未提交改动（红线禁止 commit），"
    "旧树里同时缺本轮六件修复与前几轮改动，故个别红是陈旧面（如 cypy_bridge.memory "
    "在旧树没有 _as_address）。本件是次级证据；主证据是 fix_r3_evidence.json 的同夹具翻转对照。"
)


def failure_reasons(text: str) -> dict:
    """从 pytest -v 输出里按用例抓第一条 `E ` 行（红因归类用，不猜）。"""
    reasons: dict = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"_{5,} (?:tests/[\w/\.]+::)?(\w+) _{5,}", line)
        if m:
            current = m.group(1)
            continue
        if current and line.startswith("E "):
            reasons.setdefault(current, line.strip()[:200])
            current = None
    return reasons


def sh(args, cwd=ROOT, timeout=900):
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    refuse: list = []
    if WT.exists():
        shutil.rmtree(WT, ignore_errors=True)
        time.sleep(1.0)
    rc, out = sh(["git", "worktree", "add", str(WT), "HEAD"], timeout=300)
    if rc != 0:
        print(json.dumps({"refuse": [f"worktree add 失败 rc={rc}: {out[-300:]}"]},
                         ensure_ascii=False))
        return 1
    try:
        shutil.copyfile(ROOT / TEST_FILE, WT / TEST_FILE)
        rc_r, out_r = sh([sys.executable, "-X", "utf8", "-m", "pytest", str(TEST_FILE),
                          "-v", "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
                         cwd=WT, timeout=900)
    finally:
        # 不在 worktree 里当 cwd 时才能删；删不掉就 prune 登记（不留别人的目录）
        sh(["git", "worktree", "remove", "--force", str(WT)], timeout=300)
        sh(["git", "worktree", "prune"], timeout=120)
        if WT.exists():
            shutil.rmtree(WT, ignore_errors=True)

    passed = sorted(set(re.findall(r"::(\w+) PASSED", out_r)))
    failed = sorted(set(re.findall(r"::(\w+) FAILED", out_r)))
    if len(passed) + len(failed) != PLAN["locks_total"]:
        refuse.append(f"旧树上的结果数不等于声明的 {PLAN['locks_total']} 条："
                      f"passed={len(passed)} failed={len(failed)}")

    reasons = failure_reasons(out_r)
    groups = {}
    stale_control_reds = []
    for row in PLAN["per_bug"]:
        bug = row["bug"]
        reds = [n for n in row["locks"] if n in failed]
        green = [n for n in row["locks"] if n in passed]
        ctl_red = [n for n in row["ctl_locks"] if n in failed]
        behavioral_ctl_red = []
        for name in ctl_red:
            why = reasons.get(name, "")
            stale = ("no attribute" in why) or ("ImportError" in why) \
                or ("ModuleNotFoundError" in why)
            if stale:
                stale_control_reds.append({"lock": name, "reason": why})
            else:
                behavioral_ctl_red.append(name)
        groups[bug] = {"red": reds, "green": green,
                       "red_reasons": {n: reasons.get(n, "") for n in reds},
                       "control_red_on_old_tree": behavioral_ctl_red,
                       "task_id": row["task_id"]}
        if not reds:
            refuse.append(f"{bug} 在旧产品码上零红 ⇒ 该组锁不承重（可能只是跟着实现写的断言）")
        if behavioral_ctl_red:
            refuse.append(f"{bug} 的对照锁在旧树上因行为差异而红 ⇒ 它没在测『别动』："
                          f"{behavioral_ctl_red}")

    red_groups = sum(1 for g in groups.values() if g["red"])
    out_doc = {
        "head": "17d68b4",
        "run_rc": rc_r,
        "red_groups": red_groups,
        "failed_total": len(failed),
        "passed_total": len(passed),
        "stale_control_reds": stale_control_reds,
        "groups": groups,
        "caveat": CAVEAT,
        "primary_evidence": ".fist-loop-20260927/fix_r3_evidence.json",
        "refuse": refuse,
    }
    (HERE / "fix_r3_head_proof.json").write_text(
        json.dumps(out_doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out_doc, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
