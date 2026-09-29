#!/usr/bin/env python3
"""R2-打磨：三套基线 + 改动半径 + git 红线的同一时刻复算。

与 `fix_r2_baselines.py` 同口径，差异只在两处：
- **下限只升不降**：pytest 1894 = R2-修复收口时的 1886 + 本环新增 8 条锁；
- 半径归属只列本环亲笔的 3 档；归不到本单的照列不认领，也不据此宣告"只有我在动"。

收集数与 passed 数**同一时刻各自实测**：只看 passed 分不开"用例红"与"用例根本不在收集里"，
后者正是"删掉一条测试"的隐身形状（本环红线是不弱化既有测试，必须能被机器否证）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
STAGE_START_LOCAL = time.mktime(time.strptime("2026-09-27 18:20:00", "%Y-%m-%d %H:%M:%S"))
EXPECTED_HEAD = "17d68b4"
PYTEST_FLOOR = 1894
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
MINE = {
    "cypyc/codegen/cython_generator.py": "BUG-42 删除被遮蔽的 _visit_ExprStmt",
    "cypyc/analyzer/scope_analyzer.py": "BUG-42 删除被遮蔽的 _visit_MetaBlock",
    "tests/test_polish_20260927_r2.py": "本环 8 条锁（结构门 + class 侧空白面 + 生效性/守卫存活）",
}

REFUSE = []
LOGDIR = HERE / "r2polish"


def sh(cmd, timeout=1200, env=None):
    r = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=env,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def pytest_run():
    env = dict(os.environ)
    rc, out = sh(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
        timeout=2400, env=env,
    )
    (LOGDIR / "pytest_gate.txt").write_text(out, encoding="utf-8", newline="\n")
    rc_c, out_c = sh(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
        timeout=600, env=env,
    )
    (LOGDIR / "pytest_collected.txt").write_text(out_c, encoding="utf-8", newline="\n")
    m_c = re.search(r"(\d+) tests? collected", out_c)
    collected = int(m_c.group(1)) if m_c else 0
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S+?::(\w+)", out, flags=re.M)))
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (failed|error|errors|skipped|xfailed)", out)}
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc_c != 0 or collected < PYTEST_FLOOR:
        REFUSE.append(f"收集数不达标：rc_collect={rc_c} collected={collected} 下限={PYTEST_FLOOR}")
    if rc != 0 or passed < PYTEST_FLOOR or failed or counts.get("failed") or counts.get("error"):
        REFUSE.append(f"pytest 不达标：rc={rc} passed={passed} 下限={PYTEST_FLOOR} failed={failed}")
    return {
        "rc": rc, "passed": passed, "floor": PYTEST_FLOOR, "failed": failed,
        "collected": collected, "collect_rc": rc_c, "other_counts": counts, "line": line[:180],
    }


def suite_run():
    rc, out = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], timeout=1200)
    (LOGDIR / "suite_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "Total:" in ln), out[-200:])
    fields = dict(re.findall(r"(\w+):\s*(\d+)", line))
    green = rc == 0 and fields.get("Total") == "47" and fields.get("Passed") == "47" and fields.get("Failed") == "0"
    if not green:
        REFUSE.append(f"自研套件不绿：rc={rc} line={line[:160]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green}


def e2e_run():
    rc, out = sh(["bash", "scripts/e2e_golden.sh"], timeout=1800)
    (LOGDIR / "e2e_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "summary:" in ln), out[-200:])
    fields = {}
    for k, v in re.findall(r"(PASS|FAIL|WARN)=(\d+)", line):
        fields.setdefault(k, v)
    for k, v in re.findall(r"(UNREG/RUNFAIL)=(\d+)", line):
        fields.setdefault(k, v)
    green = (
        rc == 0 and fields.get("PASS") == "25" and fields.get("FAIL") == "0"
        and fields.get("UNREG/RUNFAIL") == "0" and fields.get("WARN") == "0"
    )
    if not green:
        REFUSE.append(f"e2e golden 不绿：rc={rc} line={line[:180]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green}


def git_face():
    rc, head = sh(["git", "rev-parse", "--short", "HEAD"])
    head = head.strip()
    if head != EXPECTED_HEAD:
        REFUSE.append(f"HEAD 变了：{head} != {EXPECTED_HEAD}（红线：不提交不推送）")
    _, staged = sh(["git", "diff", "--cached", "--name-only"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    if staged_rows:
        REFUSE.append(f"暂存区非空（不得 git add）：{staged_rows[:8]}")
    _, dirty = sh(["git", "status", "--porcelain"])
    return {
        "head": head, "head_rc": rc, "staged": len(staged_rows),
        "dirty_rows": len([x for x in dirty.splitlines() if x.strip()]),
    }


def radius():
    rows = []
    for d in RADIUS_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            parts = set(path.parts)
            if "__pycache__" in parts or ".egg-info" in parts:
                continue
            if path.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            if path.stat().st_mtime >= STAGE_START_LOCAL:
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                rows.append({"file": rel, "attributed_to_this_lane": rel in MINE})
    unclaimed = sorted(r["file"] for r in rows if not r["attributed_to_this_lane"])
    missing = sorted(set(MINE) - {r["file"] for r in rows})
    if missing:
        REFUSE.append(f"本单声明改过的文件没出现在半径里（mtime 反解不成立）：{missing}")
    return {"count": len(rows), "rows": sorted(rows, key=lambda x: x["file"]), "unclaimed_by_this_lane": unclaimed}


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    doc = {
        "refuse": REFUSE, "pytest": pytest_run(), "suite": suite_run(),
        "e2e": e2e_run(), "git": git_face(), "radius": radius(),
    }
    doc["refuse"] = REFUSE
    (HERE / "polish_r2_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in doc.items() if k != "radius"}, ensure_ascii=False, indent=1))
    print("RADIUS count=%s unclaimed=%s" % (doc["radius"]["count"], doc["radius"]["unclaimed_by_this_lane"]))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
