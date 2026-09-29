"""R3-打磨 法 7/8：三套判据体系同一时刻复算 + 本轮改动半径归因 + 红线面复验。

与 R3-验证 的差别是**方向**：验证环主张"没改产品码"（半径必须为 0 条），
打磨环改了 5 档，于是半径判据换成"逐档点名归属"——
mtime 晚于本环开工时刻的可维护文件必须**恰好等于**清单，多一条就是越界，少一条就是清单口径漏了。
基线只升不降：pytest 下限从上一环实测 1920 上调到 1929（本轮新增 9 条锁），
且这 9 条的 nodeid 必须在**全量收集**里现形——只在两个锁文件里跑绿不算绿。
"""

from __future__ import annotations

import calendar
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOGDIR = HERE / "polish_r3_logs"
PYTEST_FLOOR = 1929
POLISH_LOCK_NODEIDS_MIN = 9
SUITE_TOTAL = "47"
E2E_PASS = "25"
EXPECTED_HEAD = "17d68b4"
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
# 本环开工口径：pre-baseline 的实测时刻（"打磨环尚未改任何文件"那一秒）
STAGE_START_UTC = datetime(2026, 9, 27, 17, 37, 27, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
LANE_FILES = {
    "cypyc/cli.py": "法 4：CLI 改走公开门面 analyze_only()",
    "cypy_hook/hook.py": "法 4：新增公开 analyze_only() 委托",
    "docs/USAGE.md": "法 3：补 --emit-code 文档行",
    "tests/test_loop_20260927_fix_r3.py": "法 1：BUG-55 夹具换冻结形",
    "tests/test_loop_20260927_polish_r3.py": "法 2：本轮新增 9 条锁（新文件）",
}
TEMP_GLOBS = ["tmp_polish", "tmp_verify"]
WORKTREE_RE = re.compile(r"^(\S+)\s+[0-9a-f]{7,}\s+(.*)$")
REFUSE: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=1800):
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def pytest_run():
    rc_c, out_c = sh([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only",
                      "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], 1800)
    collected_lines = [ln for ln in out_c.splitlines() if "::" in ln]
    collected = len(collected_lines)
    polish_collected = sorted(ln.split("::")[-1] for ln in collected_lines
                              if "test_loop_20260927_polish_r3.py" in ln.replace("\\", "/"))
    rc, out = sh([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
                  "-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "--tb=line"], 3600)
    LOGDIR.mkdir(exist_ok=True)
    (LOGDIR / "pytest_final.log").write_text(out, encoding="utf-8", newline="\n")
    (LOGDIR / "pytest_collect.log").write_text(out_c, encoding="utf-8", newline="\n")
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S+?::(\w+)", out, flags=re.M)))
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (failed|error|errors|skipped|xfailed)", out)}
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc_c != 0 or collected < PYTEST_FLOOR:
        REFUSE.append(f"全量收集数不达标：rc_collect={rc_c} collected={collected} 下限={PYTEST_FLOOR}")
    if len(polish_collected) < POLISH_LOCK_NODEIDS_MIN:
        REFUSE.append(f"本轮新锁在全量收集里只现形 {len(polish_collected)} 条"
                      f"（下限 {POLISH_LOCK_NODEIDS_MIN}）⇒ 新测试没进全套，收集下限才是唯一防线")
    if rc != 0 or passed < PYTEST_FLOOR or failed or counts.get("failed") or counts.get("error"):
        REFUSE.append(f"pytest 不达标：rc={rc} passed={passed} 下限={PYTEST_FLOOR} failed={failed}")
    if passed > collected:
        REFUSE.append(f"passed {passed} > collected {collected} ⇒ 计数口径坏了")
    return {"rc": rc, "passed": passed, "floor": PYTEST_FLOOR, "failed": failed,
            "collected": collected, "collect_rc": rc_c,
            "polish_locks_collected": len(polish_collected),
            "polish_lock_nodeids": polish_collected,
            "other_counts": counts, "line": line[:180], "at_utc": now_s()}


def suite_run():
    rc, out = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], 1800)
    LOGDIR.mkdir(exist_ok=True)
    (LOGDIR / "suite_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "Total:" in ln), out[-200:])
    fields = dict(re.findall(r"(\w+):\s*(\d+)", line))
    green = (rc == 0 and fields.get("Total") == SUITE_TOTAL and fields.get("Passed") == SUITE_TOTAL
             and fields.get("Failed") == "0")
    if not green:
        REFUSE.append(f"自研套件不绿：rc={rc} line={line[:160]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green, "at_utc": now_s()}


def e2e_run():
    rc, out = sh(["bash", "scripts/e2e_golden.sh"], 2400)
    LOGDIR.mkdir(exist_ok=True)
    (LOGDIR / "e2e_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "summary:" in ln), out[-200:])
    fields = {}
    for k, v in re.findall(r"(PASS|FAIL|WARN)=(\d+)", line):
        fields.setdefault(k, v)
    for k, v in re.findall(r"(UNREG/RUNFAIL)=(\d+)", line):
        fields.setdefault(k, v)
    green = (rc == 0 and fields.get("PASS") == E2E_PASS and fields.get("FAIL") == "0"
             and fields.get("UNREG/RUNFAIL") == "0" and fields.get("WARN") == "0")
    if not green:
        REFUSE.append(f"e2e golden 不绿：rc={rc} line={line[:180]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green, "at_utc": now_s()}


def git_face():
    checks = {}
    rc, head = sh(["git", "rev-parse", "--short", "HEAD"])
    head = head.strip()
    checks["head"] = head
    checks["head_ok"] = head == EXPECTED_HEAD
    if not checks["head_ok"]:
        REFUSE.append(f"HEAD 变了：{head} != {EXPECTED_HEAD}（红线：不提交）")
    _, staged = sh(["git", "diff", "--cached", "--name-only"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    checks["staged_rows"] = len(staged_rows)
    checks["staged_zero"] = not staged_rows
    if staged_rows:
        REFUSE.append(f"暂存区非空（不得 git add）：{staged_rows[:8]}")
    _, dirty = sh(["git", "status", "--porcelain"])
    dirty_rows = [x for x in dirty.splitlines() if x.strip()]
    checks["dirty_rows"] = len(dirty_rows)
    checks["deleted_tracked"] = sum(1 for x in dirty_rows if x.startswith(" D") or x.startswith("AD"))
    _, wt = sh(["git", "worktree", "list"])
    wt_lines = [ln for ln in wt.splitlines() if ln.strip()]
    parsed = [WORKTREE_RE.match(ln.strip()) for ln in wt_lines]
    paths = [m.group(1) for m in parsed if m]
    if len(paths) != len(wt_lines):
        REFUSE.append(f"worktree list 解析行数不符：输出 {len(wt_lines)} 行、解析到 {len(paths)} 条")
    checks["worktrees"] = paths
    checks["foreign_worktree_present"] = any("_cypy_head_baseline" in p for p in paths)
    if not checks["foreign_worktree_present"]:
        REFUSE.append(f"别人家的 worktree 不见了（不得删）：{paths}")
    temp_left = {}
    for g in TEMP_GLOBS:
        base = HERE / g
        temp_left[g] = sorted(p.name for p in base.glob("snap_*")) if base.exists() else []
    checks["temp_snapshots_left"] = temp_left
    checks["temp_snapshots_gone"] = all(not v for v in temp_left.values())
    if not checks["temp_snapshots_gone"]:
        REFUSE.append(f"本环/上一环的临时快照树没清：{temp_left}")
    checks["all_ok"] = (checks["head_ok"] and checks["staged_zero"] and paths
                        and checks["foreign_worktree_present"] and checks["temp_snapshots_gone"])
    if not checks["all_ok"]:
        REFUSE.append(f"git 红线格未过：{ {k: v for k, v in checks.items() if k.endswith('_ok')} }")
    checks["at_utc"] = now_s()
    return checks


def radius():
    rows = []
    for d in RADIUS_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in set(path.parts) or ".egg-info" in set(path.parts):
                continue
            if path.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            st = path.stat()
            if st.st_mtime >= STAGE_START_EPOCH:
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                rows.append({"file": rel,
                             "mtime_utc": datetime.fromtimestamp(
                                 st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                             "attributed": rel in LANE_FILES})
    touched = sorted(r["file"] for r in rows)
    unexpected = sorted(set(touched) - set(LANE_FILES))
    missing = sorted(set(LANE_FILES) - set(touched))
    if unexpected:
        REFUSE.append(f"半径越界：mtime 晚于开工但不属本环清单的文件 {unexpected}")
    if missing:
        REFUSE.append(f"清单里的文件没在半径里现形（清单口径宽了或改动没落地）：{missing}")
    return {"count": len(rows), "files": rows, "lane_files": sorted(LANE_FILES),
            "lane_attributions": LANE_FILES, "unexpected": unexpected, "missing": missing,
            "stage_start_utc": STAGE_START_UTC.isoformat(), "scanned_dirs": RADIUS_DIRS,
            "at_utc": now_s()}


def lint_own_drivers():
    targets = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in HERE.glob("polish_r3_*.py"))
    rc, out = sh([sys.executable, "-X", "utf8", "-m", "flake8", "--select=E9,W605,F821",
                  "--max-line-length=200", *targets], 600)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    pat = re.compile(r"^(.+?):(\d+):(\d+): (\w+) ")
    parsed = [pat.match(ln) for ln in lines]
    bad = [ln for ln, m in zip(lines, parsed) if m is None]
    if bad:
        REFUSE.append(f"flake8 输出有 {len(bad)} 行解析不出来（判据自己坏了）：{bad[:4]}")
    if lines and len(parsed) != len(lines):
        REFUSE.append("flake8 行数与解析行数不等")
    return {"rc": rc, "files": len(targets), "targets": targets,
            "hard_violations": sum(1 for m in parsed if m), "detail": lines[:12],
            "at_utc": now_s()}


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    doc = {"refuse": [], "started_at_utc": now_s(),
           "note": "三套体系是**一批连续复算**（各格自带 at_utc），不是同一秒；"
                   "报告里凡说『同一时刻』都按本件的 start→finish 窗口口径读",
           "stage_start_utc": STAGE_START_UTC.isoformat(),
           "stage_start_basis": "r3_polish_pre_baseline.json 的 measured_at_utc（打磨环开工前实测）"}
    doc["pytest"] = pytest_run()
    doc["suite"] = suite_run()
    doc["e2e"] = e2e_run()
    doc["git"] = git_face()
    doc["radius"] = radius()
    doc["lint"] = lint_own_drivers()
    doc["pytest_ge_floor"] = 1 if doc["pytest"]["passed"] >= PYTEST_FLOOR else 0
    doc["three_systems_green"] = 1 if (doc["pytest"]["rc"] == 0 and doc["suite"]["green"]
                                       and doc["e2e"]["green"]) else 0
    doc["radius_exact"] = 1 if (not doc["radius"]["unexpected"]
                                and not doc["radius"]["missing"]) else 0
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    (HERE / "polish_r3_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "pytest": doc["pytest"], "suite": doc["suite"],
                      "e2e": doc["e2e"], "git": doc["git"],
                      "radius": {k: v for k, v in doc["radius"].items() if k != "lane_attributions"},
                      "lint": {k: v for k, v in doc["lint"].items() if k != "detail"},
                      "ge_floor": doc["pytest_ge_floor"],
                      "three_systems_green": doc["three_systems_green"],
                      "radius_exact": doc["radius_exact"],
                      "window": [doc["started_at_utc"], doc["finished_at_utc"]]},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
