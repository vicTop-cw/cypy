#!/usr/bin/env python3
"""R3-修复：三套基线 + 改动半径 + git 红线的同一时刻复算。

与 `hunt_r3_baselines.py` 同口径，差异在三处：

- **下限只升**：pytest 1920 = 上一环实测 1903 + 本环新增 17 条锁（`test_loop_20260927_fix_r3.py`
  实测条数），不是估的；收集数与 passed 数各自实测，分不开"用例红"与"用例不在收集里"。
- **半径必须全部归本单**：修复环动被测量面，所以逐个文件声明归属；半径里出现未声明的文件
  就打印出来（并发 lane 的改动不能被我这一单认领）。
- **两套体系都要绿**：自研套件与 e2e golden 各自独立跑，pytest 绿不能抵扣它们。
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
STAGE_START_LOCAL = time.mktime(time.strptime("2026-09-28 00:00:00", "%Y-%m-%d %H:%M:%S"))
EXPECTED_HEAD = "17d68b4"
PYTEST_FLOOR = 1920
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
MINE = {
    "cypyc/cli.py": "BUG-56：transpile 四个旗标落地",
    "cypyc/transformer/generic_transformer.py": "BUG-55：收集 generic_params",
    "cypy_bridge/union.py": "BUG-57：示例改成可用形状 + 内建类型给专属错误",
    "cypy_bridge/memory.py": "BUG-58：realloc 注解/文档与返回值一致",
    "cypyc/project/module_dependency_graph.py": "BUG-59：环内模块排序确定化",
    "cypyc/analyzer/build_block_checker.py": "BUG-60：docstring 规则 2 对齐 SYNTAX/04",
    "tests/test_loop_20260927_fix_r3.py": "本环 17 条回归锁",
}

REFUSE = []
LOGDIR = HERE / "r3fix_logs"


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


def locks_run():
    """单独跑本环 17 条锁，并数出条数（下限里的 +17 必须能被这份实测反解）。"""
    rc, out = sh(
        [sys.executable, "-X", "utf8", "-m", "pytest", "tests/test_loop_20260927_fix_r3.py",
         "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts="],
        timeout=900,
    )
    (LOGDIR / "locks.txt").write_text(out, encoding="utf-8", newline="\n")
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    declared = sum(1 for ln in (ROOT / "tests" / "test_loop_20260927_fix_r3.py")
                   .read_text(encoding="utf-8").splitlines() if ln.startswith("def test_"))
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc != 0 or passed != declared:
        REFUSE.append(f"本环锁不绿或条数对不上：rc={rc} passed={passed} 文件内 test_ 数={declared}")
    return {"rc": rc, "passed": passed, "test_defs_in_file": declared, "line": line[:160]}


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
    _, others = sh(["git", "worktree", "list"])
    worktrees = []
    for ln in others.splitlines():
        m = re.match(r"^(.*?)\s+([0-9a-f]{7,40})\s", ln.strip() + " ")
        if m:
            worktrees.append(m.group(1))
    return {
        "head": head, "head_rc": rc, "staged": len(staged_rows),
        "dirty_rows": len([x for x in dirty.splitlines() if x.strip()]),
        "worktrees": worktrees,
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
                rows.append({"file": rel, "attributed_to_this_lane": rel in MINE,
                             "why": MINE.get(rel, "")})
    unclaimed = sorted(r["file"] for r in rows if not r["attributed_to_this_lane"])
    missing = sorted(set(MINE) - {r["file"] for r in rows})
    if missing:
        REFUSE.append(f"本单声明改过的文件没出现在半径里（mtime 反解不成立）：{missing}")
    if unclaimed:
        REFUSE.append(f"半径里出现未归属本单的文件（不得认领别人的改动）：{unclaimed}")
    return {"count": len(rows), "rows": sorted(rows, key=lambda x: x["file"]),
            "unclaimed_by_this_lane": unclaimed}


LEGACY_E501 = {  # 修前就存在的超长行（本轮只准减不准增）
    "cypyc/cli.py": 1,                          # :79
    "cypyc/analyzer/build_block_checker.py": 3,  # :133/:142/:180
}


def lint_face():
    """可机器否证的 lint 面：

    - 7 个文件必须无 E9（语法）与 W605（非法转义）——只可能由本轮改动引入；
    - 新建的测试文件整份都是亲笔行 ⇒ E501/W291/W293 必须为 0；
    - 6 个产品文件的 E501 逐文件与 `LEGACY_E501` 对照（只降不升），W293 是存量、只记计数。
    """
    targets = sorted(MINE)
    rc, out = sh([sys.executable, "-X", "utf8", "-m", "flake8", "--max-line-length=100",
                  "--select=E501,E9,W291,W293,W605"] + targets, timeout=300)
    rows = [ln for ln in out.splitlines() if ln.strip()]
    (LOGDIR / "lint.txt").write_text("\n".join(rows), encoding="utf-8", newline="\n")
    parsed = []
    for ln in rows:
        m = re.match(r"^(.+?):(\d+):\d+: ([AWEXFC]\d+) ", ln)
        if m:
            parsed.append((m.group(1).replace("\\", "/"), int(m.group(2)), m.group(3)))
    missed = len(rows) - len(parsed)
    hard = [c for c in parsed if c[2].startswith("E9") or c[2] == "W605"]
    new_file = [c for c in parsed if c[0].endswith("test_loop_20260927_fix_r3.py")]
    e501_by_file: dict = {}
    legacy_w293: dict = {}
    for fname, _line, code in parsed:
        if code == "E501":
            e501_by_file[fname] = e501_by_file.get(fname, 0) + 1
        if code == "W293":
            legacy_w293[fname] = legacy_w293.get(fname, 0) + 1
    if missed:
        REFUSE.append(f"lint 输出有 {missed} 行解析不出违规码（判据读不到=空转，先看格式）")
    if hard:
        REFUSE.append(f"lint 硬违例 {len(hard)} 条：{hard[:4]}")
    if new_file:
        REFUSE.append(f"亲笔新文件有违例 {len(new_file)} 条：{new_file[:4]}")
    grew = {f: n for f, n in e501_by_file.items() if n > LEGACY_E501.get(f, 0)}
    if grew:
        REFUSE.append(f"E501 比修前变多（只准减不准增）：{grew} 存量上限={LEGACY_E501}")
    if not parsed:
        REFUSE.append("一条违规都没解析出来：先确认 flake8 真跑到了（rc/输出非空）")
    return {"rc": rc, "rows_total": len(rows), "parsed": len(parsed),
            "hard_violations": len(hard),
            "new_file_violations": len(new_file), "e501_by_file": e501_by_file,
            "legacy_e501_cap": LEGACY_E501, "legacy_w293_by_file": legacy_w293}


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    doc = {
        "refuse": REFUSE, "pytest": pytest_run(), "locks": locks_run(), "suite": suite_run(),
        "e2e": e2e_run(), "git": git_face(), "radius": radius(), "lint": lint_face(),
    }
    doc["refuse"] = REFUSE
    (HERE / "fix_r3_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in doc.items() if k != "radius"}, ensure_ascii=False, indent=1))
    print("RADIUS count=%s unclaimed=%s" % (doc["radius"]["count"],
                                            doc["radius"]["unclaimed_by_this_lane"]))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
