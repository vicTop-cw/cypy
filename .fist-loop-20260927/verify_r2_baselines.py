#!/usr/bin/env python3
"""R2-修复：三套基线 + 改动半径 + git 红线的**同一时刻**复算（L7 证据件）。

口径与 R1 一致：
- 数字各自实测，不引用别人正文里的观测值；
- 判定只看逐条行与末行摘要，`-q` 下失败用例名从 `FAILED/ERROR` 摘要行反解；
- 下限写死在代码里（pytest 1883 = R1-推进的 1868 + 本轮新增 15 条锁），**只升不降**；
- 半径按 mtime 反解「本轮之后被改过的产品/测试/文档文件」，逐条点名归属；
  归不到本单的（并发 lane 在飞）照列不隐藏，也不据此宣告"只有我在动"。
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
STAGE_START_LOCAL = time.mktime(time.strptime("2026-09-27 16:41:00", "%Y-%m-%d %H:%M:%S"))
EXPECTED_HEAD = "17d68b4"
PYTEST_FLOOR = 1886
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
MINE = {
    "cypyc/codegen/cython_generator.py": "BUG-44/45 生成器",
    "cypyc/parser/parser.py": "BUG-45 诊断/BUG-39 越域守卫",
    "cypyc/parser/macro_expander.py": "BUG-39 宏展开片段的 body_scope",
    "cypy_hook/hook.py": "BUG-35 分桶",
    "cypyc/cli.py": "BUG-46 口径",
    "cypy_hook/__init__.py": "BUG-47 再导出",
    "docs/USAGE.md": "BUG-46 手册同步",
    "tests/test_loop_20260927_fix_r2.py": "本轮 15 条锁",
}

REFUSE = []


def sh(cmd, timeout=1200, env=None):
    r = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def pytest_run():
    env = dict(os.environ)
    rc, out = sh(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "tests/",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "-o",
            "addopts=",
        ],
        timeout=2400,
        env=env,
    )
    (HERE / "r2verify" / "pytest_gate.txt").write_text(out, encoding="utf-8", newline="\n")
    # 同一时刻先量收集数：`passed < floor` 有两种成因（用例会红 / 用例根本不在收集里），
    # 只报 passed 分不开这两类，而第二类正是"删掉一条测试"的隐身形状。
    rc_c, out_c = sh(
        [
            sys.executable, "-X", "utf8", "-m", "pytest", "tests/",
            "--collect-only", "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts=",
        ],
        timeout=600,
        env=env,
    )
    (HERE / "r2verify" / "pytest_collected.txt").write_text(out_c, encoding="utf-8", newline="\n")
    m_c = re.search(r"(\d+) tests? collected", out_c)
    collected = int(m_c.group(1)) if m_c else 0
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S+?::(\w+)", out, flags=re.M)))
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (failed|error|errors|skipped|xfailed)", out)}
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc_c != 0 or collected < PYTEST_FLOOR:
        REFUSE.append(
            f"收集数不达标：rc_collect={rc_c} collected={collected} 下限={PYTEST_FLOOR}"
        )
    if rc != 0 or passed < PYTEST_FLOOR or failed or counts.get("failed") or counts.get("error"):
        REFUSE.append(f"pytest 不达标：rc={rc} passed={passed} 下限={PYTEST_FLOOR} failed={failed}")
    return {
        "rc": rc,
        "passed": passed,
        "floor": PYTEST_FLOOR,
        "failed": failed,
        "collected": collected,
        "collect_rc": rc_c,
        "other_counts": counts,
        "line": line[:180],
    }


def suite_run():
    rc, out = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], timeout=1200)
    (HERE / "r2verify" / "suite_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "Total:" in ln), out[-200:])
    fields = dict(re.findall(r"(\w+):\s*(\d+)", line))
    green = (
        rc == 0
        and fields.get("Total") == "47"
        and fields.get("Passed") == "47"
        and fields.get("Failed") == "0"
    )
    if not green:
        REFUSE.append(f"自研套件不绿：rc={rc} line={line[:160]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green}


def e2e_run():
    rc, out = sh(["bash", "scripts/e2e_golden.sh"], timeout=1800)
    (HERE / "r2verify" / "e2e_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "summary:" in ln), out[-200:])
    fields = {}
    for k, v in re.findall(r"(PASS|FAIL|WARN)=(\d+)", line):
        fields.setdefault(k, v)
    for k, v in re.findall(r"(UNREG/RUNFAIL)=(\d+)", line):
        fields.setdefault(k, v)
    green = (
        rc == 0
        and fields.get("PASS") == "25"
        and fields.get("FAIL") == "0"
        and fields.get("UNREG/RUNFAIL") == "0"
        and fields.get("WARN") == "0"
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
        "head": head,
        "head_rc": rc,
        "staged": len(staged_rows),
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
    return {
        "count": len(rows),
        "rows": sorted(rows, key=lambda x: x["file"]),
        "unclaimed_by_this_lane": unclaimed,
    }


def main() -> int:
    (HERE / "r2verify").mkdir(exist_ok=True)
    doc = {
        "refuse": REFUSE,
        "pytest": pytest_run(),
        "suite": suite_run(),
        "e2e": e2e_run(),
        "git": git_face(),
        "radius": radius(),
    }
    doc["refuse"] = REFUSE
    (HERE / "verify_r2_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
