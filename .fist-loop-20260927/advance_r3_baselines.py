"""R3-推进 法 6/7：三套判据体系复算（地板随新锁上调）+ 改动半径逐档归属 + git 红线。

地板不是抄上一环：`PYTEST_FLOOR = 1929 + 新锁条数`，新锁条数从**盘上 def test_ 现数**，
数不出 9 条就当场拒（用例静默消失时全套照样绿，只有收集数下限会叫）。
半径判据与打磨环同向：本环**确实**改了分析器，所以主张是"恰好这 2 档"，
mtime 反解与清单双向对表 —— 多一档越界、少一档未落地都算红。
"""

from __future__ import annotations

import calendar
import difflib
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
LOGDIR = HERE / "advance_r3_logs"
NEW_LOCK_FILE = "tests/test_loop_20260927_advance_r3.py"
PREV_FLOOR = 1929
SUITE_TOTAL = "47"
E2E_PASS = "25"
EXPECTED_HEAD = "17d68b4"
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
STAGE_START_UTC = datetime(2026, 9, 27, 18, 41, 40, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
LANE_FILES = {
    "cypyc/analyzer/type_checker.py": "法 1：Callable 入参元数判定落地（含两个私有辅助方法）",
    NEW_LOCK_FILE: "法 2：本轮新增回归锁（新文件）",
}
TEMP_GLOBS = ["tmp_advance", "tmp_polish", "tmp_verify"]
BEFORE_DIR = HERE / "advance_r3_before"
EXPECTED_SNAPSHOT_SHA = {"cypyc/analyzer/type_checker.py": "4db6e1f3bfc2c7d3"}
WORKTREE_RE = re.compile(r"^(\S+)\s+[0-9a-f]{7,}\s+(.*)$")
REFUSE: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=1800):
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def new_lock_count() -> int:
    return len(re.findall(r"^def (test_\w+)",
                          (ROOT / NEW_LOCK_FILE).read_text(encoding="utf-8", newline=""), flags=re.M))


def pytest_run(floor: int):
    rc_c, out_c = sh([PY, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only", "-q",
                      "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], 1800)
    collected_lines = [ln for ln in out_c.splitlines() if "::" in ln]
    collected = len(collected_lines)
    adv_collected = sorted(ln.split("::")[-1] for ln in collected_lines
                           if NEW_LOCK_FILE.split("/")[-1] in ln)
    rc, out = sh([PY, "-X", "utf8", "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider",
                  "--no-header", "-o", "addopts=", "--tb=line"], 3600)
    LOGDIR.mkdir(exist_ok=True)
    (LOGDIR / "pytest_final.log").write_text(out, encoding="utf-8", newline="\n")
    (LOGDIR / "pytest_collect.log").write_text(out_c, encoding="utf-8", newline="\n")
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S+?::(\w+)", out, flags=re.M)))
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (failed|error|errors|skipped|xfailed)", out)}
    line = next((ln for ln in reversed(out.splitlines()) if " passed" in ln or "failed" in ln), "")
    if rc_c != 0 or collected < floor:
        REFUSE.append(f"全量收集数不达标：rc_collect={rc_c} collected={collected} 下限={floor}")
    if len(adv_collected) < new_lock_count():
        REFUSE.append(f"本轮新锁在全量收集里只现形 {len(adv_collected)} 条，盘上声明 {new_lock_count()} 条")
    if rc != 0 or passed < floor or failed or counts.get("failed") or counts.get("error"):
        REFUSE.append(f"pytest 不达标：rc={rc} passed={passed} 下限={floor} failed={failed}")
    if passed > collected:
        REFUSE.append(f"passed {passed} > collected {collected} ⇒ 计数口径坏了")
    return {"rc": rc, "passed": passed, "floor": floor, "failed": failed, "collected": collected,
            "collect_rc": rc_c, "advance_locks_collected": len(adv_collected),
            "advance_lock_nodeids": adv_collected, "other_counts": counts,
            "line": line[:180], "at_utc": now_s()}


def suite_run():
    rc, out = sh([PY, "-X", "utf8", "scripts/run_tests.py"], 1800)
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
    _, head = sh(["git", "rev-parse", "--short", "HEAD"])
    head = head.strip()
    checks["head"] = head
    checks["head_ok"] = head == EXPECTED_HEAD
    if not checks["head_ok"]:
        REFUSE.append(f"HEAD 变了：{head} != {EXPECTED_HEAD}（红线：不提交）")
    _, staged = sh(["git", "diff", "--cached", "--name-only"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    checks["staged_zero"] = not staged_rows
    checks["staged_rows"] = len(staged_rows)
    if staged_rows:
        REFUSE.append(f"暂存区非空（不得 git add）：{staged_rows[:8]}")
    _, dirty = sh(["git", "status", "--porcelain"])
    dirty_rows = [x for x in dirty.splitlines() if x.strip()]
    checks["dirty_rows"] = len(dirty_rows)
    checks["deleted_tracked"] = sum(1 for x in dirty_rows if x.startswith((" D", "AD")))
    _, ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"])
    checks["ahead_of_upstream"] = ahead.strip()
    _, wt = sh(["git", "worktree", "list"])
    wt_lines = [ln for ln in wt.splitlines() if ln.strip()]
    parsed = [WORKTREE_RE.match(ln.strip()) for ln in wt_lines]
    paths = [m.group(1) for m in parsed if m]
    if len(paths) != len(wt_lines):
        REFUSE.append(f"worktree list 解析行数不符：{len(wt_lines)} 行 / 解析 {len(paths)} 条")
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
        REFUSE.append(f"临时快照树没清：{temp_left}")
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
            if {"__pycache__", ".egg-info"} & set(path.parts):
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
        REFUSE.append(f"半径越界（mtime 晚于开工但不在本环清单）：{unexpected}")
    if missing:
        REFUSE.append(f"清单里的文件没在半径里现形（清单口径宽了或改动没落地）：{missing}")
    return {"count": len(rows), "files": rows, "lane_files": sorted(LANE_FILES),
            "lane_attributions": LANE_FILES, "unexpected": unexpected, "missing": missing,
            "stage_start_utc": STAGE_START_UTC.isoformat(), "scanned_dirs": RADIUS_DIRS,
            "at_utc": now_s()}


def lint_face():
    targets = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in HERE.glob("advance_r3_*.py"))
    rc, out = sh([PY, "-X", "utf8", "-m", "flake8", "--select=E9,W605,F821",
                  "--max-line-length=200", *targets], 600)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    pat = re.compile(r"^(.+?):(\d+):(\d+): (\w+) ")
    parsed = [pat.match(ln) for ln in lines]
    unparsed = [ln for ln, m in zip(lines, parsed) if m is None]
    if unparsed:
        REFUSE.append(f"flake8 有 {len(unparsed)} 行解析不出来（判据自己坏了）：{unparsed[:3]}")
    hard = sum(1 for m in parsed if m)
    if hard:
        REFUSE.append(f"本环驱动有硬违例：{lines[:4]}")
    # 亲笔面分两种口径：**新写的整档**每一行都要合规；**改到的既有档**只对本窗口新加的行负责，
    # 但整档违例数必须只减不增（对照开工前快照，快照 sha 先自证是同一档）。
    own_new = _flake8(NEW_LOCK_FILE)
    if own_new:
        REFUSE.append(f"亲笔新档有违例（整档都是我写的）：{ {NEW_LOCK_FILE: own_new[:2]} }")
    product = [f for f in LANE_FILES if f.endswith(".py") and f != NEW_LOCK_FILE]
    diffs = {}
    for rel in product:
        snap = BEFORE_DIR / rel.split("/")[-1]
        if not snap.exists():
            REFUSE.append(f"{rel} 没有开工前快照 ⇒ 分不出哪些行是我加的，本件不作数")
            continue
        before_txt = snap.read_text(encoding="utf-8", newline="")
        sha_before = hashlib.sha256(before_txt.encode("utf-8")).hexdigest()[:16]
        if sha_before != EXPECTED_SNAPSHOT_SHA.get(rel):
            REFUSE.append(f"{rel} 快照身份不符：sha={sha_before} 期望={EXPECTED_SNAPSHOT_SHA.get(rel)}")
            continue
        now_txt = (ROOT / rel).read_text(encoding="utf-8", newline="")
        added = _added_lines(before_txt, now_txt)
        viols = _flake8(rel)
        viols_before = _flake8_path(snap)
        mine = [v for v in viols if int(v.split(":")[1]) in added]
        if mine:
            REFUSE.append(f"{rel} 本窗口新加的行上有违例：{mine[:2]}")
        if len(viols) > len(viols_before):
            REFUSE.append(f"{rel} 整档违例数上升：{len(viols_before)} → {len(viols)}")
        if not added:
            REFUSE.append(f"{rel} 与开工前快照逐字相同 ⇒ 半径里的改动没落地，归属无从谈起")
        # 双向对照：抽掉「行号过滤」这一层，同一批违例必须非空 ⇒ 证明过滤器不是靠空集蒙绿
        canary = len(viols)
        diffs[rel] = {"added_lines": len(added), "violations_now": len(viols),
                      "violations_before": len(viols_before),
                      "violations_on_my_lines": len(mine),
                      "unfiltered_control": {"would_be_refused": canary > 0, "count": canary},
                      "snapshot_sha16": sha_before}
    return {"rc": rc, "drivers": len(targets), "hard_violations": hard,
            "own_new_file": {NEW_LOCK_FILE: len(own_new)},
            "own_new_clean": not own_new, "product_face": diffs,
            "canary": lint_canary(),
            "product_clean": all(d["violations_on_my_lines"] == 0 and d["added_lines"] > 0
                                 and d["unfiltered_control"]["would_be_refused"]
                                 for d in diffs.values()) and bool(diffs),
            "detail": lines[:8], "at_utc": now_s()}


def _flake8(rel: str) -> list:
    rc_o, out_o = sh([PY, "-X", "utf8", "-m", "flake8", "--max-line-length", "100", rel], 300)
    return _flake8_lines(out_o)


def _flake8_path(path: Path) -> list:
    rc_o, out_o = sh([PY, "-X", "utf8", "-m", "flake8", "--max-line-length", "100",
                      str(path.relative_to(ROOT))], 300)
    return _flake8_lines(out_o)


def _flake8_lines(out: str) -> list:
    return [ln for ln in out.splitlines() if ln.strip()]


def _added_lines(before_txt: str, now_txt: str) -> set:
    b = before_txt.splitlines()
    n = now_txt.splitlines()
    added = set()
    for tag, _i1, i2, j1, j2 in difflib.SequenceMatcher(None, b, n).get_opcodes():
        if tag in ("insert", "replace"):
            added.update(range(j1 + 1, j2 + 1))
    return added


def lint_canary():
    """行号过滤这一层配一对对照：往开工前快照里插一条 120 字符的行 ⇒ 过滤器必须点出它；
    插一条合规行 ⇒ 必须不误抓。没有这对对照，"新加的行上 0 违例"就可能是空集蒙出来的。"""
    out = {}
    for rel, expect_sha in EXPECTED_SNAPSHOT_SHA.items():
        snap = BEFORE_DIR / rel.split("/")[-1]
        if not snap.exists():
            continue
        base = snap.read_text(encoding="utf-8", newline="")
        if hashlib.sha256(base.encode("utf-8")).hexdigest()[:16] != expect_sha:
            continue
        lines = base.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        for label, inject in (("too_long", "'" + "q" * 130 + "'"), ("clean", "1")):
            fake = "\n".join(lines + ["", "", f"_CANARY_{label} = {inject}"]) + "\n"
            tmp = HERE / "tmp_advance" / f"canary_{label}.py"
            tmp.parent.mkdir(exist_ok=True)
            tmp.write_text(fake, encoding="utf-8", newline="\n")
            added = _added_lines(base, fake)
            viols = _flake8_path(tmp)
            mine = [v for v in viols if int(v.split(":")[1]) in added]
            codes = sorted({v.split(":")[3].split()[0] for v in mine})
            out[f"{rel}:{label}"] = {"added_lines": len(added), "on_my_lines": len(mine),
                                     "codes": codes}
            tmp.unlink(missing_ok=True)
        bad = out.get(f"{rel}:too_long", {})
        good = out.get(f"{rel}:clean", {})
        if "E501" not in bad.get("codes", []):
            REFUSE.append(f"行号过滤器漏抓了必然违例（{rel}:too_long 抓到 {bad}）⇒ 亲笔面判据不承重")
        if good.get("on_my_lines", -1) != 0:
            REFUSE.append(f"行号过滤器误抓了合规行（{rel}:clean 抓到 {good}）⇒ 会假红，判据不承重")
    return out


def main() -> int:
    LOGDIR.mkdir(exist_ok=True)
    locks = new_lock_count()
    if locks == 0:
        REFUSE.append(f"{NEW_LOCK_FILE} 里一条 def test_ 都没数出来 ⇒ 地板无从上调，本件不作数")
    floor = PREV_FLOOR + locks
    doc = {"refuse": [], "started_at_utc": now_s(),
           "note": "三套体系是**一批连续复算**（各格自带 at_utc）；地板=上一环实测 1929 + 本轮新锁条数",
           "new_locks_declared": locks, "pytest_floor": floor,
           "stage_start_utc": STAGE_START_UTC.isoformat(),
           "stage_start_basis": "root_stage.py 发布 T0r73 的时刻（root_r3_advance.out.json 同批）"}
    doc["pytest"] = pytest_run(floor)
    doc["suite"] = suite_run()
    doc["e2e"] = e2e_run()
    doc["git"] = git_face()
    doc["radius"] = radius()
    doc["lint"] = lint_face()
    doc["pytest_ge_floor"] = 1 if doc["pytest"]["passed"] >= floor else 0
    doc["three_systems_green"] = 1 if (doc["pytest"]["rc"] == 0 and doc["suite"]["green"]
                                       and doc["e2e"]["green"]) else 0
    doc["radius_exact"] = 1 if (not doc["radius"]["unexpected"] and not doc["radius"]["missing"]) else 0
    doc["floor_raised"] = floor - PREV_FLOOR
    doc["refuse"] = REFUSE
    doc["finished_at_utc"] = now_s()
    (HERE / "advance_r3_baselines.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "floor": floor, "pytest": doc["pytest"],
                      "suite": doc["suite"], "e2e": doc["e2e"], "git": doc["git"],
                      "radius": {k: v for k, v in doc["radius"].items() if k != "lane_attributions"},
                      "lint": {k: v for k, v in doc["lint"].items() if k != "detail"},
                      "flags": [doc["pytest_ge_floor"], doc["three_systems_green"], doc["radius_exact"]],
                      "window": [doc["started_at_utc"], doc["finished_at_utc"]]},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
