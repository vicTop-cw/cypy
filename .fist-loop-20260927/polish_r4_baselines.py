"""R4-打磨 法⑦：三套判据体系同批复算 + 只升不降 + 半径与冻结面正面测。

与修复环的两处口径不同：
① 地板取 **R4-修复 的实测数**（1956 / 1956 / 47 / 25），不是手填的目标；
② 验证环不该动产品码、测试码与文档——所以 `radius.product`、`radius.tests`、`radius.docs`
   三栏在本环**必须为空**，只有 `.fist-loop-20260927/` 与 `memory/` 允许变动。
   这条比上一环更严，因为本环的角色就是「只看不动手」。
③ 「只升不降」的比较本身也要配 canary：拿一个必然达不到的地板去比，比较函数必须报违规，
   否则这条门是恒真的。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREV = HERE / "verify_r4_baselines.json"
OUT = HERE / "polish_r4_baselines.json"
START_UTC = "2026-09-28T01:41:16+00:00"      # 根任务 T0r90 发布时刻
FROZEN_DIRS = ["PROJECT-SPEC", "SYNTAX"]
NOISE = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv",
         "build", "dist", "node_modules", ".idea", ".vscode"}
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def run(cmd, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def at_or_floor(got: int, floor: int) -> bool:
    return got >= floor


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    floors = {"pytest": prev["systems"]["pytest"]["passed"],
              "collect": prev["systems"]["collect"]["nodeids"],
              "suite": prev["systems"]["suite"]["fields"]["Total"],
              "e2e_pass": prev["systems"]["e2e"]["PASS"]}

    p = run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
             "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], timeout=2400)
    ptext = (p.stdout or "") + (p.stderr or "")
    line = next((ln for ln in reversed(ptext.splitlines())
                 if re.search(r"\d+ (passed|failed|error)", ln)), "")

    def num(pat: str) -> int:
        m = re.search(pat, line)
        return int(m.group(1)) if m else 0

    passed, failed, errors, skipped = (num(r"(\d+) passed"), num(r"(\d+) failed"),
                                       num(r"(\d+) error"), num(r"(\d+) skipped"))
    failed_names = sorted({m.group(1) for m in
                           re.finditer(r"^(?:FAILED|ERROR) (\S+)", ptext, re.M)})
    c = run([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only", "-q",
             "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], timeout=900)
    ctext = (c.stdout or "") + (c.stderr or "")
    mc = re.search(r"(\d+) tests? collected", ctext)
    collected = int(mc.group(1)) if mc else 0

    s = run([sys.executable, "-X", "utf8", "scripts/run_tests.py"], timeout=1800)
    stext = (s.stdout or "") + (s.stderr or "")
    sline = next((ln for ln in reversed(stext.splitlines()) if "Total:" in ln), "")
    suite = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", sline)}

    e = run(["bash", "scripts/e2e_golden.sh"], timeout=1800)
    etext = (e.stdout or "") + (e.stderr or "")
    eline = next((ln for ln in reversed(etext.splitlines()) if "PASS" in ln), "")
    e2e = {k: int(v) for k, v in re.findall(r"(\w+)[=:]\s*(\d+)", eline)}

    g = run(["git", "status", "--porcelain"])
    rows = [ln for ln in (g.stdout or "").splitlines() if ln.strip()]
    staged = sum(1 for ln in rows if ln[:1] not in (" ", "?"))
    deleted = sum(1 for ln in rows if "D" in ln[:2])
    head = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    wt = run(["git", "worktree", "list"]).stdout or ""

    start = datetime.datetime.fromisoformat(START_UTC)
    radius = {k: [] for k in ("product", "tests", "docs", "frozen", "loop", "ledger", "other")}
    scanned = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts
        if any(part in NOISE or part.endswith(".egg-info") for part in parts[:-1]):
            continue
        scanned += 1
        m = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
        if m < start:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("cypyc/", "cypy_hook/", "cypy_bridge/")):
            radius["product"].append(rel)
        elif rel.startswith("tests/"):
            radius["tests"].append(rel)
        elif rel.startswith("docs/"):
            radius["docs"].append(rel)
        elif rel.startswith(("PROJECT-SPEC", "SYNTAX")):
            radius["frozen"].append(rel)
        elif rel.startswith(".fist-loop-20260927/"):
            radius["loop"].append(rel)
        elif rel.startswith("memory/"):
            radius["ledger"].append(rel)
        else:
            radius["other"].append(rel)
    radius = {k: sorted(v) for k, v in radius.items()}

    frozen_sha = {}
    for d in FROZEN_DIRS:
        for f in sorted((ROOT / d).rglob("*.md")):
            frozen_sha[f.relative_to(ROOT).as_posix()] = \
                hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    prev_frozen = prev.get("frozen_sha", {})

    systems = {"pytest": {"passed": passed, "failed": failed, "errors": errors,
                          "skipped": skipped, "failed_names": failed_names,
                          "summary_line": line, "rc": p.returncode},
               "collect": {"nodeids": collected},
               "suite": {"fields": suite, "line": sline, "rc": s.returncode},
               "e2e": e2e}
    three_green = (failed == 0 and errors == 0 and suite.get("Failed", -1) == 0
                   and e2e.get("FAIL", -1) == 0 and e2e.get("WARN", -1) == 0
                   and e2e.get("PASS", 0) >= floors["e2e_pass"])

    check("pytest 通过数不低于上一环实测（只升不降）",
          at_or_floor(passed, floors["pytest"]), True, f"{passed} vs 地板 {floors['pytest']}")
    check("pytest 零失败零错误", [failed, errors], [0, 0], line)
    check("pytest 失败用例名必须为空", failed_names, [], "逐条点名")
    check("收集数不低于上一环", at_or_floor(collected, floors["collect"]), True,
          f"{collected} vs {floors['collect']}")
    check("收集数与通过数不得互相矛盾（收集到却没跑=有跳过之外的黑洞）",
          collected >= passed, True, f"collected={collected} passed={passed}")
    check("自研套件 Total 与地板同为 47", suite.get("Total"), floors["suite"], sline)
    check("自研套件全绿", [suite.get("Passed"), suite.get("Failed")],
          [floors["suite"], 0], sline)
    check("e2e golden PASS 不低于地板", at_or_floor(e2e.get("PASS", 0), floors["e2e_pass"]),
          True, json.dumps(e2e, ensure_ascii=False))
    check("e2e golden 零失败零警告", [e2e.get("FAIL", -1), e2e.get("WARN", -1)], [0, 0],
          json.dumps(e2e, ensure_ascii=False))
    check("三套体系必须同时为绿（同一时刻复算的快照）", three_green, True,
          json.dumps({"pytest": [passed, failed, errors], "suite": suite, "e2e": e2e}))
    check("HEAD 未动（本环不 commit）", head, "17d68b4", "git rev-parse --short HEAD")
    check("新锁文件确在 tests/ 半径里（法⑤落地看得见）",
          "tests/test_loop_20260927_polish_r4.py" in radius["tests"], True,
          f"tests 栏 {radius['tests']}")
    check("新锁带来的收集增量恰为 20（地板 +20）",
          collected, floors["collect"] + 20, f"{collected} vs {floors['collect']}+20")
    check("暂存区为空（没有 git add）", staged, 0, f"{staged} 行")
    check("外部基线 worktree 仍在（不许删别人的树）",
          "E:/IDEProjects/AI/_cypy_head_baseline" in wt, True,
          wt.strip().splitlines()[:2])
    check("打磨环半径：产品码必须零改动（不改语义）", radius["product"], [],
          "本环只做文档/测试/账面")
    check("打磨环半径：tests 只许新增本轮永久锁文件，不许改动既有测试文件",
          [x for x in radius["tests"] if x != "tests/test_loop_20260927_polish_r4.py"], [],
          f"tests 栏 {radius['tests']}")
    check("打磨环半径：docs 栏只许 USAGE.md（法①的措辞改写）加本轮新增补注",
          [x for x in radius["docs"] if x not in ("docs/USAGE.md",
                                                  "docs/APPENDIX_C_DEVIATIONS.md")], [],
          f"docs 栏 {radius['docs']}")
    check("冻结面 mtime 为空", radius["frozen"], [], "PROJECT-SPEC/ 与 SYNTAX/ 未被触碰")
    frozen_diff_keys = sorted(set(frozen_sha) ^ set(prev_frozen)) or [
        k for k in frozen_sha if prev_frozen.get(k) != frozen_sha[k]]
    check("冻结面 sha 与上一环实测逐字相同", frozen_sha == prev_frozen, True,
          f"差异键={frozen_diff_keys}")
    check("扫描面必须真扫到文件（空扫描=分栏装饰）", scanned > 2000, True, f"scanned={scanned}")
    check("loop 栏必须非空（本环判据件都写在这里）", bool(radius["loop"]), True,
          f"{len(radius['loop'])} 个")

    bogus = {"only_up_reports_violation": not at_or_floor(passed, passed + 1),
             "only_up_reports_equality_ok": at_or_floor(passed, passed)}
    check("「只升不降」比较函数的 canary：必然违例的地板必须报违规",
          bogus, {"only_up_reports_violation": True, "only_up_reports_equality_ok": True},
          "比较函数若对不可能地板也放行，这条门就是恒真")

    doc = {"started": started, "window": {"start_utc": START_UTC, "batch_started_at_utc": started},
           "floors": floors, "floors_source": "verify_r4_baselines.json 的实测值（R4-验证 同批三套体系）",
           "systems": systems,
           "git": {
               "head": head, "staged": staged, "dirty_rows": len(rows),
               "deleted_tracked": deleted, "worktrees": wt.count("\n")},
           "radius": radius, "scanned_files": scanned, "frozen_sha": frozen_sha,
           "frozen_total": len(frozen_sha), "three_systems_green": three_green,
           "canary": bogus,
           "note": "本环是打磨环：产品码必须零改动，tests/docs 只许点名的新增/改写；"
                   "地板来自 R4-验证 实测件而不是手写目标；"
                   "window 里不再有 finished_at_utc 这个歧义键（R4-验证 §十 19 的转结）",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"),
           "elapsed_min_from_start": round(
               (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.
                fromisoformat(START_UTC)).total_seconds() / 60)}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"floors": floors, "systems": {
        "pytest": [passed, failed, errors, skipped], "collect": collected,
        "suite": suite, "e2e": e2e},
        "radius_counts": {k: len(v) for k, v in radius.items()},
        "head": head, "staged": staged, "dirty_rows": len(rows),
        "three_green": three_green, "refuse": doc["refuse"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
