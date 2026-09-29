#!/usr/bin/env python3
"""R3-修复：回归锁的三向对账（声明 / 收集 / 通过）。

`fix_r3_plan.json` 声明了 17 条锁的名字与角色（pos=打缺陷主张、ctl=成对对照），
这里两份实测反解：

- `pytest --collect-only` 的名字集合必须与声明**双向相等**（多一条=声明漏了，少一条=名字拼错
  或文件根本没进收集，后者正是"删掉一条测试"的隐身形状）；
- `pytest -v` 的通过集合必须覆盖全部 17 条，且每条 BUG 至少一条 pos 与一条配对证据
  （配对可以是同一条锁里的双向断言，此时 `paired_inside` 必须写明）。

任何一条不成立都进 refuse，不给"看起来绿"的清单签字。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLAN = json.loads((HERE / "fix_r3_plan.json").read_text(encoding="utf-8"))
TEST_FILE = "tests/test_loop_20260927_fix_r3.py"

REFUSE: list = []


def sh(args, timeout=900):
    r = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    declared, pos, ctl = [], [], []
    for row in PLAN["per_bug"]:
        declared += row["locks"]
        pos += row["pos_locks"]
        ctl += row["ctl_locks"]
    dupes = sorted({n for n in declared if declared.count(n) > 1})
    if dupes:
        REFUSE.append(f"声明里有重名锁：{dupes}")

    rc_c, out_c = sh(["-m", "pytest", TEST_FILE, "--collect-only", "-q",
                      "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], timeout=600)
    collected = sorted(re.findall(r"::(\w+)$", out_c, flags=re.M))
    missing = sorted(set(declared) - set(collected))
    extra = sorted(set(collected) - set(declared))
    if rc_c != 0:
        REFUSE.append(f"收集失败 rc={rc_c}：{out_c[-200:]}")
    if missing:
        REFUSE.append(f"声明的锁没进收集（名字拼错或文件不在盘上）：{missing}")
    if extra:
        REFUSE.append(f"收集里有未声明的锁：{extra}")

    rc_r, out_r = sh(["-m", "pytest", TEST_FILE, "-v", "-p", "no:cacheprovider",
                      "--no-header", "-o", "addopts="], timeout=900)
    passed = sorted(set(re.findall(r"::(\w+) PASSED", out_r)))
    failed = sorted(set(re.findall(r"::(\w+) FAILED", out_r)))
    if rc_r != 0 or failed:
        REFUSE.append(f"锁不绿：rc={rc_r} failed={failed}")
    not_run = sorted(set(declared) - set(passed))
    if not_run:
        REFUSE.append(f"这些锁没以 PASSED 出现（跑了但没通过不算通过）：{not_run}")

    per_bug = {}
    for row in PLAN["per_bug"]:
        ok_pos = len(row["pos_locks"]) >= 1
        paired = len(row["ctl_locks"]) >= 1 or bool(row.get("paired_inside"))
        all_passed = all(n in passed for n in row["locks"])
        per_bug[row["bug"]] = {
            "locks": len(row["locks"]), "pos": len(row["pos_locks"]),
            "ctl": len(row["ctl_locks"]), "paired": paired,
            "all_passed": all_passed, "task_id": row["task_id"],
        }
        if not ok_pos:
            REFUSE.append(f"{row['bug']} 没有 pos 锁（只有对照等于没锁住主张）")
        if not paired:
            REFUSE.append(f"{row['bug']} 缺成对对照：pos 型锁单独存在时判据可能恒绿")
        if not all_passed:
            REFUSE.append(f"{row['bug']} 的锁未全绿")

    out = {
        "declared": len(declared), "collected": len(collected), "passed": len(passed),
        "pos_total": len(pos), "ctl_total": len(ctl),
        "per_bug": per_bug,
        "test_file": TEST_FILE,
        "run_line": next((ln for ln in reversed(out_r.splitlines())
                          if " passed" in ln or "failed" in ln), "")[:160],
        "refuse": REFUSE,
    }
    (HERE / "fix_r3_locks_inventory.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
