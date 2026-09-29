"""R4-推进 法⑦：三套判据体系同刻为绿 + 冻结面未动 + 半径按 mtime 归因到本环。

 floors 不手打：上一环的实测值从 `polish_r4_baselines.json` 反解（pytest/collect 1976、
 suite 47、e2e PASS 25），本环的下限取「上环实测 + 本环新增锁数」，写不出来源就拒判。
 归因口径分两层：**mtime ≥ 本环起点**才算本轮亲笔（`git diff HEAD` 分不开未提交的相邻两轮，
 上一环已经为此栽过）；冻结面另用 43 个文件的 sha 与上环记录逐字节比。
 冻结面的 porcelain 栏第一版写成「必须为空」，实测被 3 条 09-26 的历史脏行打回（tracked 的
 `M` 行是相对 HEAD 而言，未提交的相邻轮次全都算脏）⇒ 改成三条：sha 逐字节未变 + 本环窗口内
 无脏行 + 每条脏行都要有解释（早于本 loop 开工或 sha 与上环相等），并配一新一旧两条合成行 canary。
 基数自证：`--collect-only` 的条数必须等于跑完后的「过+红+错」，对不上就是解析器坏了。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from loop_kit import (collect_nodeids, parse_kv_line, parse_pytest_summary,  # noqa: E402
                      record)

OUT = HERE / "advance_r4_baselines.json"
PREV = json.loads((HERE / "polish_r4_baselines.json").read_text(encoding="utf-8"))
LOCKS = json.loads((HERE / "advance_r4_locks.json").read_text(encoding="utf-8"))
PLAN = json.loads((HERE / "advance_r4_lock_plan.json").read_text(encoding="utf-8"))
RING_START = "2026-09-28T03:00:00+00:00"
LOOP_START = "2026-09-27T00:00:00+00:00"
PRODUCT_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "scripts"]
FROZEN_GLOBS = ["PROJECT-SPEC", "SYNTAX"]
NEW_LOCK_FILE = LOCKS["new_test_file"]
CHECKS: list = []
REFUSE: list = []


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sh(args: list, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def sha12(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def row_mtime(row: str) -> str:
    """porcelain 行 → 该文件的 UTC mtime；文件已不在就报 MISSING（删冻结面更要抓）。"""
    p = ROOT / row[3:].strip().strip('"')
    if not p.exists():
        return "MISSING"
    return datetime.datetime.fromtimestamp(
        p.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")


def frozen_dirt(rows: list) -> list:
    """porcelain 里只把 mtime 落在本环窗口内的行算「本环动了冻结面」。

    `git status` 分不开相邻两轮的未提交脏状态：上一环为此栽过一次。脏行本身进
    `frozen_preexisting_dirt` 栏披露，不许悄悄丢掉。
    """
    return sorted(r for r in rows if row_mtime(r) >= RING_START)


def main() -> int:
    started = now_iso()
    prev_pytest = PREV["systems"]["pytest"]["passed"]
    prev_collect = PREV["systems"]["collect"]["nodeids"]
    prev_suite = PREV["systems"]["suite"]["fields"]["Total"]
    prev_e2e = PREV["systems"]["e2e"]["PASS"]
    locks_added = LOCKS["collect_after_locks"] - LOCKS["previous_round_collect_floor"]
    floors = {"pytest": prev_pytest + locks_added, "collect": prev_collect + locks_added,
              "suite": prev_suite, "e2e_pass": prev_e2e}
    # 两份独立来源：plan 说本环该加几条锁，全量收集数的差是实测加了几条 —— 不等就红
    if locks_added != PLAN["expected_tests"]:
        REFUSE.append(f"实测收集数增量 {locks_added} 与生成器 plan 的 "
                      f"{PLAN['expected_tests']} 条不符 ⇒ 有用例静默消失或地板算法要重新说")

    p = sh([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q",
            "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], 3000)
    s = parse_pytest_summary((p.stdout or "") + (p.stderr or ""))
    c = sh([sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "--collect-only", "-q",
            "-p", "no:cacheprovider", "--no-header", "-o", "addopts="], 900)
    collected = collect_nodeids((c.stdout or "") + (c.stderr or ""))
    su = sh([sys.executable, "-X", "utf8", "scripts/run_tests.py"], 1800)
    su_line = next((ln for ln in reversed((su.stdout or "").splitlines())
                    if "Total:" in ln), "")
    suite = parse_kv_line(su_line)
    e2 = sh(["bash", "scripts/e2e_golden.sh"], 2400)
    e2_text = (e2.stdout or "") + (e2.stderr or "")
    e2_line = next((ln for ln in reversed(e2_text.splitlines()) if "PASS=" in ln), "")
    e2e = parse_kv_line(e2_line)

    record(CHECKS, REFUSE, "pytest 全量：零失败零错误且不少于地板",
           [s["failed"], s["errors"], s["passed"] >= floors["pytest"]], [0, 0, True],
           f"{s['summary_line'] or '（没解析到摘要行）'}；地板 {floors}")
    record(CHECKS, REFUSE, "基数自证：收集数 == 跑完的「过+红+错」（对不上是解析器坏了）",
           collected, s["passed"] + s["failed"] + s["errors"] + s["skipped"],
           f"collected={collected} run={s}")
    record(CHECKS, REFUSE, "自研套件：47 条且零失败",
           [suite.get("Total"), suite.get("Failed"), suite.get("Skipped")],
           [floors["suite"], 0, 0], su_line or "（没解析到 Total 行）")
    record(CHECKS, REFUSE, "e2e golden：PASS 不少于地板且 FAIL/RUNFAIL/WARN 全零",
           [e2e.get("PASS", 0) >= floors["e2e_pass"], e2e.get("FAIL"), e2e.get("RUNFAIL"),
            e2e.get("WARN")], [True, 0, 0, 0], e2_line or "（没解析到 PASS= 行）")

    head = sh(["git", "rev-parse", "--short", "HEAD"], 60).stdout.strip()
    staged = [ln for ln in sh(["git", "diff", "--cached", "--name-only"], 120).stdout.splitlines()
              if ln.strip()]
    dirty = [ln for ln in sh(["git", "status", "--porcelain=v1"], 180).stdout.splitlines()
             if ln.strip()]
    touched = sorted({Path(ln[3:].strip()) for ln in dirty} | {Path(NEW_LOCK_FILE)})
    product = [str(t.as_posix()) for t in touched
               if any(t.as_posix().startswith(d + "/") for d in PRODUCT_DIRS)
               and t.suffix in {".py", ".toml", ".sh"}]
    by_mtime = sorted(pth.relative_to(ROOT).as_posix() for base in PRODUCT_DIRS
                      for pth in (ROOT / base).rglob("*.py")
                      if datetime.datetime.fromtimestamp(
                          pth.stat().st_mtime, datetime.timezone.utc
                      ).isoformat(timespec="seconds") >= RING_START)
    frozen_scope = sh(["git", "status", "--porcelain=v1", "--", *FROZEN_GLOBS],
                      180).stdout.splitlines()

    def face_by_mtime(prefix: str) -> list:
        rows = set()
        for rn in dirty:
            rel = rn[3:].strip().strip('"')
            if rel.startswith(prefix) and row_mtime(" M " + rel) >= RING_START:
                rows.add(rel)
        return sorted(rows)
    tests_by_mtime = face_by_mtime("tests/")
    docs_by_mtime = face_by_mtime("docs/")
    prev_frozen = PREV["frozen_sha"]
    frozen_now = {k: (sha12(ROOT / k) if (ROOT / k).exists() else "MISSING")
                  for k in prev_frozen}
    frozen_changed = sorted(k for k in prev_frozen if frozen_now[k] != prev_frozen[k])

    def row_path(row: str) -> str:
        return row[3:].strip().strip('"')

    def explained(row: str) -> bool:
        """脏行的两种清白：早于本 loop 开工，或 sha 与上环记录逐字节相等。"""
        if row_mtime(row) < LOOP_START:
            return True
        rel = row_path(row)
        return rel in prev_frozen and frozen_now.get(rel) == prev_frozen.get(rel)

    # canary 的两条合成行：一条必然算本环脏（刚写的判据件），一条必然算陈旧（loop 之前的文件）
    fresh_rows = [q.relative_to(ROOT).as_posix() for q in HERE.glob("advance_r4_*.py")]
    fresh_row = " M " + max(fresh_rows, key=lambda p: (ROOT / p).stat().st_mtime)
    stale_row = " M " + min((k for k in prev_frozen if (ROOT / k).exists()),
                            key=lambda k: row_mtime(" M " + k))

    record(CHECKS, REFUSE, "底树未漂：HEAD 仍是开工时那一棵", head, PREV["git"]["head"],
           f"git rev-parse --short HEAD = {head}")
    record(CHECKS, REFUSE, "未暂存：本轮不替别人提交东西", len(staged), 0, f"{staged[:3]}")
    record(CHECKS, REFUSE, "冻结面：上环记录的 43 个 sha 逐字节未变",
           [frozen_changed, len(frozen_now)], [[], len(prev_frozen)],
           f"sha 变了 {frozen_changed}，共比 {len(frozen_now)} 个文件")
    dirt_in_ring = frozen_dirt(frozen_scope)
    unexplained_rows = sorted(r for r in frozen_scope if not explained(r))
    record(CHECKS, REFUSE, f"冻结面：mtime 落在本环窗口（≥{RING_START}）内的脏行为空",
           dirt_in_ring, [],
           f"冻结面脏行与 mtime {[(r, row_mtime(r)) for r in frozen_scope]}")
    record(CHECKS, REFUSE,
           "冻结面每条脏行必须有解释（早于本 loop 开工，或 sha 与上环记录逐字节相等）",
           unexplained_rows, [], f"无解释脏行 {unexplained_rows}")
    record(CHECKS, REFUSE, "半径按 mtime 归因到本环：产品面只许两档分析器",
           by_mtime, ["cypyc/analyzer/scope_analyzer.py", "cypyc/analyzer/type_checker.py"],
           f"mtime ≥ {RING_START} 的产品文件 {by_mtime}")
    record(CHECKS, REFUSE,
           "半径按 mtime 归因：测试面只许「新增锁文件 + 裁决改期望的那一条」，文档面必须为空",
           [tests_by_mtime, docs_by_mtime],
           [sorted([NEW_LOCK_FILE, "tests/test_codegen_verification.py"]), []],
           f"tests 面 mtime ≥ {RING_START} 的 {tests_by_mtime}；docs 面 {docs_by_mtime}")
    record(CHECKS, REFUSE, "本环新增的锁文件必须在测试面名单里（不在＝它没被 git 看见）",
           NEW_LOCK_FILE in tests_by_mtime, True, f"{NEW_LOCK_FILE} → {tests_by_mtime}")
    green3 = (s["failed"] == 0 and s["errors"] == 0 and suite.get("Failed") == 0
              and e2e.get("FAIL") == 0)
    canary = {"three_systems_green": green3,
              "floors_came_from_artifact": all(k in floors for k in
                                               ("pytest", "collect", "suite", "e2e_pass")),
              "frozen_face_count_matches_previous": len(frozen_now) == PREV["frozen_total"],
              "radius_is_exactly_two_product_files": len(by_mtime) == 2,
              "frozen_predicate_flags_a_fresh_row": (
                  frozen_dirt([fresh_row]) == [fresh_row] and not explained(fresh_row)),
              "frozen_predicate_explains_a_stale_row": (
                  frozen_dirt([stale_row]) == [] and explained(stale_row)),
              "faces_measured_not_declared": (len(tests_by_mtime) == 2
                                              and docs_by_mtime == [])}
    record(CHECKS, REFUSE, "canary 七格必须同时成立", [len(canary), sorted(canary.values())],
           [7, [True] * 7], json.dumps(canary, ensure_ascii=False))

    doc = {"started": started, "law": "三套判据体系同刻为绿、冻结面未动、半径只到两档分析器",
           "floors": floors, "floors_source": "polish_r4_baselines.json 实测 + 本环新增锁数",
           "locks_added_this_ring": locks_added,
           "systems": {"pytest": {**s, "rc": p.returncode}, "collect": {"nodeids": collected},
                       "suite": {"fields": suite, "line": su_line, "rc": su.returncode},
                       "e2e": e2e},
           "git": {"head": head, "staged": len(staged), "dirty_rows": len(dirty),
                   "worktrees": len(sh(["git", "worktree", "list"], 120).stdout.splitlines())},
           "frozen_scope_porcelain": sorted(frozen_scope), "frozen_now": frozen_now,
           "frozen_changed": frozen_changed, "frozen_total": len(frozen_now),
           "frozen_dirt_in_ring": dirt_in_ring, "frozen_unexplained": unexplained_rows,
           "frozen_dirty_mtime": {r: row_mtime(r) for r in sorted(frozen_scope)},
           "frozen_canary_rows": {"fresh": [fresh_row, row_mtime(fresh_row)],
                                  "stale": [stale_row, row_mtime(stale_row)]},
           "radius": {"product_by_mtime_this_ring": by_mtime, "product_touched_any": product,
                      "tests": tests_by_mtime, "tests_new_lock_file": NEW_LOCK_FILE,
                      "docs": docs_by_mtime, "frozen": frozen_changed,
                      "loop": sorted(q.as_posix() for q in HERE.glob("advance_r4_*"))},
           "three_systems_green": canary["three_systems_green"], "canary": canary,
           "window": {"ring_start": RING_START, "note": "mtime 归因口径见件首注释"},
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)), "at_utc": now_iso()}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "pytest": [s["passed"], s["failed"], s["errors"]],
                      "collected": collected, "suite": suite, "e2e": e2e,
                      "by_mtime": by_mtime, "frozen_changed": frozen_changed,
                      "head": head, "canary": canary}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
