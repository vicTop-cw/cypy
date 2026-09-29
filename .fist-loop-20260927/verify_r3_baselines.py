"""R3-验证 法 5/6：三套判据体系同一时刻复算 + 本轮改动半径的负面主张正面测。

基线只升不降：pytest 下限 1920（上一环实测）、自研套件 47/47、e2e golden 25/25。
半径判据：验证环不修产品码 ⇒ RADIUS_DIRS 里 mtime 晚于本环开工时刻的
可维护文件必须为 0 条；这不是「我没改」的自述，而是从文件系统反解。
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
LOGDIR = HERE / "r3verify_logs"
PYTEST_FLOOR = 1920
SUITE_TOTAL = "47"
E2E_PASS = "25"
EXPECTED_HEAD = "17d68b4"
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
STAGE_START_UTC = datetime(2026, 9, 27, 17, 1, 14, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
REFUSE: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=1800):
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def pytest_run():
    cmd_collect = [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only",
                   "-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts="]
    rc_c, out_c = sh(cmd_collect, 1800)
    collected = len([ln for ln in out_c.splitlines() if "::" in ln])
    rc, out = sh([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
                  "-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "--tb=line"], 3600)
    (LOGDIR / "pytest_final.log").write_text(out, encoding="utf-8", newline="\n")
    (LOGDIR / "pytest_collect.log").write_text(out_c, encoding="utf-8", newline="\n")
    passed = int(re.search(r"(\d+) passed", out).group(1)) if re.search(r"(\d+) passed", out) else 0
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S+?::(\w+)", out, flags=re.M)))
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (failed|error|errors|skipped|xfailed)", out)}
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc_c != 0 or collected < PYTEST_FLOOR:
        REFUSE.append(f"收集数不达标：rc_collect={rc_c} collected={collected} 下限={PYTEST_FLOOR}")
    if rc != 0 or passed < PYTEST_FLOOR or failed or counts.get("failed") or counts.get("error"):
        REFUSE.append(f"pytest 不达标：rc={rc} passed={passed} 下限={PYTEST_FLOOR} failed={failed}")
    return {"rc": rc, "passed": passed, "floor": PYTEST_FLOOR, "failed": failed,
            "collected": collected, "collect_rc": rc_c, "other_counts": counts,
            "line": line[:180], "at_utc": now_s()}


def suite_run():
    rc, out = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], 1800)
    (LOGDIR / "suite_final.log").write_text(out, encoding="utf-8", newline="\n")
    line = next((ln for ln in reversed(out.splitlines()) if "Total:" in ln), out[-200:])
    fields = dict(re.findall(r"(\w+):\s*(\d+)", line))
    green = (rc == 0 and fields.get("Total") == SUITE_TOTAL and fields.get("Passed") == SUITE_TOTAL
             and fields.get("Failed") == "0")
    if not green:
        REFUSE.append(f"自研套件不绿：rc={rc} line={line[:160]}")
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green,
            "at_utc": now_s()}


def e2e_run():
    rc, out = sh(["bash", "scripts/e2e_golden.sh"], 2400)
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
    return {"rc": rc, "line": line[:180], "fields": fields, "green": green,
            "at_utc": now_s()}


WORKTREE_RE = re.compile(r"^(\S+)\s+[0-9a-f]{7,}\s+(.*)$")


def git_face():
    checks = {}
    rc, head = sh(["git", "rev-parse", "--short", "HEAD"])
    head = head.strip()
    checks["head_ok"] = head == EXPECTED_HEAD
    if not checks["head_ok"]:
        REFUSE.append(f"HEAD 变了：{head} != {EXPECTED_HEAD}（红线：不提交）")
    _, staged = sh(["git", "diff", "--cached", "--name-only"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    checks["staged_zero"] = not staged_rows
    if staged_rows:
        REFUSE.append(f"暂存区非空（不得 git add）：{staged_rows[:8]}")
    _, dirty = sh(["git", "status", "--porcelain"])
    dirty_rows = [x for x in dirty.splitlines() if x.strip()]
    checks["dirty_rows"] = len(dirty_rows)
    checks["deleted_tracked"] = sum(1 for x in dirty_rows if x.startswith(" D") or x.startswith("AD"))
    _, wt = sh(["git", "worktree", "list"])
    parsed = [WORKTREE_RE.match(ln.strip()) for ln in wt.splitlines() if ln.strip()]
    paths = [m.group(1) for m in parsed if m]
    if len(paths) != len([ln for ln in wt.splitlines() if ln.strip()]):
        REFUSE.append(f"worktree list 解析行数不符：输出 {len([ln for ln in wt.splitlines() if ln.strip()])} 行、解析到 {len(paths)} 条")
    checks["worktrees"] = paths
    checks["foreign_worktree_present"] = any("_cypy_head_baseline" in p for p in paths)
    if not checks["foreign_worktree_present"]:
        REFUSE.append(f"别人家的 worktree 不见了（不得删）：{paths}")
    # 自证：本环自己的快照临时树必须清零。旧写法拿 worktree 路径列表找 "tmp_verify"
    # ⇒ 快照树从来不是 worktree，那格恒真（恒真格不配当门禁）。改成数盘上的目录。
    snap_left = sorted(x.name for x in (HERE / "tmp_verify").glob("snap_*")) if (HERE / "tmp_verify").exists() else []
    checks["own_snapshot_dirs_left"] = snap_left
    checks["own_snapshot_gone"] = not snap_left
    if snap_left:
        REFUSE.append(f"本环自己的快照临时树仍在（临时树必删）：{snap_left}")
    rc_a, ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"])
    checks["ahead_of_upstream"] = ahead.strip() or "no-upstream"
    checks["all_ok"] = (checks["head_ok"] and checks["staged_zero"] and len(paths) >= 1
                        and checks["foreign_worktree_present"] and checks["own_snapshot_gone"])
    if not checks["all_ok"]:
        REFUSE.append(f"git 红线格未过：{ {k: v for k, v in checks.items() if k.endswith('_ok') or k in ('foreign_worktree_present', 'own_snapshot_gone')} }")
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
            parts = set(path.parts)
            if "__pycache__" in parts or ".egg-info" in parts:
                continue
            if path.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            if path.stat().st_mtime >= STAGE_START_EPOCH:
                rows.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    if rows:
        REFUSE.append(f"验证环声称不修产品码，但半径里有 {len(rows)} 个文件 mtime 晚于开工时刻：{sorted(rows)[:10]}")
    return {"count": len(rows), "files": sorted(rows),
            "stage_start_utc": STAGE_START_UTC.isoformat(),
            "scanned_dirs": RADIUS_DIRS, "at_utc": now_s()}


def lint_own_files():
    targets = [str(p.relative_to(ROOT)).replace("\\", "/") for p in HERE.glob("verify_r3_*.py")]
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
    return {"rc": rc, "files": len(targets), "hard_violations": len([m for m in parsed if m]),
            "detail": lines[:12], "targets": targets, "at_utc": now_s()}


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    doc = {"refuse": [], "started_at_utc": now_s(),
           "note": "三套体系是**一批连续复算**（各格自带 at_utc），不是同一秒；"
                   "报告里凡说『同一时刻』都按本件的 start→finish 窗口口径读",
           "measured_at_utc": now_s(),
           "stage_start_utc": STAGE_START_UTC.isoformat(),
           "pytest": pytest_run(), "suite": suite_run(), "e2e": e2e_run(),
           "git": git_face(), "radius": radius(), "lint": lint_own_files()}
    doc["radius_claim_ok"] = 1 if doc["radius"]["count"] == 0 else 0
    doc["pytest_ge_floor"] = 1 if doc["pytest"]["passed"] >= PYTEST_FLOOR else 0
    doc["git"] = {k: v for k, v in doc["git"].items()}
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    (HERE / "verify_r3_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "measured_at_utc": doc["measured_at_utc"],
                      "pytest": {k: v for k, v in doc["pytest"].items() if k != "out"},
                      "suite": doc["suite"], "e2e": doc["e2e"], "git": doc["git"],
                      "radius": doc["radius"], "radius_claim_ok": doc["radius_claim_ok"],
                      "lint": {k: v for k, v in doc["lint"].items() if k != "detail"}},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
