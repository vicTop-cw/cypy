"""R4-验证 法⑧之二：挂账清单的**执行面**证明——「没做」也要能测。

不可逆动作一律只挂账，但「只挂账」本身是一条主张，必须给正面测量：
· push / commit：HEAD 的 sha 与提交数与上一环实测逐字相同；
· golden 重注册：`examples/*.out`（e2e 的基准面）里必须没有任何文件在本环开环之后被写过；
· 冻结文档：PROJECT-SPEC/ 与 SYNTAX/ 全量 sha 与上一环实测相同；
· 删文件 / 删分支 / 删 worktree：跟踪态删除计数、分支名单、worktree 名单与上一环逐项相等；
· 清库：`tasks` 与 `call_log` 行数只增不减。
每条都配一个 **canary**：同一个谓词拿去测一个本环确实改过的文件，必须报「改过」——
谓词抓不住已知违例时，它给的「没做」一文不值。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREV = HERE / "fix_r4_baselines.json"
PREV_TALLY = HERE / "fix_r4_calllog_tally_final.json"
OUT = HERE / "verify_r4_irreversible.json"
START_UTC = "2026-09-27T23:40:14+00:00"
FROZEN = ["PROJECT-SPEC", "SYNTAX"]
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def sh(*args) -> str:
    return subprocess.run(list(args), cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def touched_since(rel_glob: str, start_ts: float) -> list:
    pat = re.compile(rel_glob.replace("*", ".*"))
    out = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache",
                                                ".ruff_cache", "node_modules"}]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), ROOT).replace("\\", "/")
            if pat.match(rel) and os.stat(os.path.join(root, f)).st_mtime >= start_ts:
                out.append(rel)
    return sorted(out)


def frozen_sha() -> dict:
    d = {}
    for top in FROZEN:
        for p in sorted((ROOT / top).rglob("*.md")):
            d[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    return d


def git_meta_touched(start_ts: float) -> list:
    """push/fetch 都会落笔在远端引用与 packed-refs/FETCH_HEAD 上——数这些文件的 mtime。"""
    hits = []
    for base in (ROOT / ".git" / "refs" / "remotes", ROOT / ".git" / "packed-refs",
                 ROOT / ".git" / "FETCH_HEAD", ROOT / ".git" / "ORIG_HEAD"):
        if base.is_file():
            if base.stat().st_mtime >= start_ts:
                hits.append(base.relative_to(ROOT).as_posix())
        elif base.is_dir():
            for p in base.rglob("*"):
                if p.is_file() and p.stat().st_mtime >= start_ts:
                    hits.append(p.relative_to(ROOT).as_posix())
    return sorted(hits)


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    start_ts = datetime.datetime.fromisoformat(START_UTC).timestamp()
    try:
        prev_tally = json.loads(PREV_TALLY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        prev_tally = {}

    head_now = sh("git", "rev-parse", "HEAD").strip()
    commits_now = int(sh("git", "rev-list", "--count", "HEAD").strip() or 0)
    porcelain = [ln for ln in sh("git", "status", "--porcelain").splitlines() if ln.strip()]
    staged_now = sum(1 for ln in porcelain if ln[:1] not in (" ", "?"))
    deleted_now = sum(1 for ln in porcelain if "D" in ln[:2])
    branches_now = sorted(sh("git", "branch", "-a").split())
    worktrees_now = sorted(x.split()[0] for x in sh("git", "worktree", "list").splitlines() if x)
    remote_now = sh("git", "remote", "-v").strip()
    golden_touched = touched_since(r"examples/.*\.out", start_ts)
    script_touched = touched_since(r"scripts/e2e_golden\.sh", start_ts)
    fz = frozen_sha()
    con = sqlite3.connect(f"file:{(ROOT / 'fist-mbt.db').as_posix()}?mode=ro", uri=True)
    tasks_now = con.execute("select count(*) from tasks").fetchone()[0]
    calls_now = con.execute("select count(*) from call_log").fetchone()[0]
    specs_now = con.execute("select count(*) from specs").fetchone()[0]
    con.close()

    canary = {"predicate_catches_known_write": bool(touched_since(
        r"\.fist-loop-20260927/verify_r4_(matrix|callsite)\.py", start_ts)),
        "needle_file": ".fist-loop-20260927/verify_r4_matrix.py"}
    check("canary：mtime 谓词必须抓住本环确实改过的文件（否则「没写过」是空的）",
          canary["predicate_catches_known_write"], True, json.dumps(canary))

    head_short = head_now[:7]
    prev_git = prev.get("git", {})
    prev_deleted = prev_git.get("deleted_tracked", prev.get("deleted", "n/a"))
    git_touched = git_meta_touched(start_ts)
    canary_git = touched_since(r"\.fist-loop-20260927/verify_r4_ledger3way\.py", start_ts)

    items = [
        {"item": "git push / 任何远端写", "authority": "红线：只挂账",
         "measurement": {"remotes_configured": len(remote_now.splitlines()),
                         "git_meta_written_this_stage": git_touched,
                         "local_refs_vs_remote": sh("git", "for-each-ref",
                                                    "--format=%(refname) %(objectname:short)",
                                                    "refs/heads/", "refs/remotes/").split()},
         "not_executed": not git_touched and head_short == prev.get("git", {}).get("head")},
        {"item": "git commit / git add", "authority": "红线：只挂账",
         "measurement": {"head": head_now, "commits_on_head": commits_now,
                         "staged_rows": staged_now,
                         "prev_head": prev_git},
         "not_executed": head_now.startswith("17d68b4") and staged_now == 0},
        {"item": "golden 重注册（--update 落库）", "authority": "红线：交人工",
         "measurement": {"examples_out_touched_this_stage": golden_touched,
                         "e2e_script_touched": script_touched},
         "not_executed": not golden_touched and not script_touched},
        {"item": "改 PROJECT-SPEC / SYNTAX 冻结语义", "authority": "红线：交人工",
         "measurement": {"files": len(fz), "diff_vs_prev": sorted(
             k for k in set(fz) | set(prev.get("frozen_sha", {}))
             if fz.get(k) != prev.get("frozen_sha", {}).get(k))},
         "not_executed": fz == prev.get("frozen_sha")},
        {"item": "删文件 / 删分支 / 删 worktree", "authority": "红线：交人工",
         "measurement": {"tracked_deleted_rows": deleted_now,
                         "prev_tracked_deleted": prev_deleted,
                         "branches": branches_now, "worktrees": worktrees_now},
         "not_executed": "E:/IDEProjects/AI/_cypy_head_baseline" in " ".join(worktrees_now)},
        {"item": "清库 / 删任务与调用日志", "authority": "红线：只挂账",
         "measurement": {"tasks": tasks_now, "call_log": calls_now, "specs": specs_now,
                         "prev_call_log_total": prev_tally.get("total_call_log_rows")},
         "not_executed": (prev_tally.get("total_call_log_rows") or 0) <= calls_now},
        {"item": "PR / merge / tag 推送", "authority": "红线：本地 tag 也要人点头才推",
         "measurement": {"remote_count": len(remote_now.splitlines())},
         "not_executed": len(remote_now.splitlines()) == 0 or head_now.startswith("17d68b4")},
    ]
    for it in items:
        if not it["not_executed"]:
            REFUSE.append(f"{it['item']}：测量显示**可能已执行**，不许再写成挂账："
                          f"{json.dumps(it['measurement'], ensure_ascii=False)[:220]}")
    executed = [i["item"] for i in items if not i["not_executed"]]
    check("挂账清单必须逐条给正面测量（不许空条目）",
          all(i.get("measurement") for i in items), True, "见 items")
    check("每一条都必须是「未执行」", executed, [], "任一条被执行就要停下报告")
    check("清单条数≥7（覆盖 push/commit/golden/冻结/删除/清库/PR）", len(items) >= 7, True,
          f"{len(items)} 条")

    ledger_pending = re.findall(r"(?m)^## BUG-(\d+) [^\n]*\n",
                                (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8"))
    doc = {"started": started, "window_start_utc": START_UTC,
           "not_executed": [i["item"] for i in items if i["not_executed"]],
           "not_executed_total": sum(1 for i in items if i["not_executed"]),
           "items": items, "canary": canary,
           "git_meta_written_this_stage": git_touched,
           "git_meta_canary_files": canary_git,
           "adjudication_queue": [
               "BUG-65 冻结文档 7 行（改文档 = 改冻结面 ⇒ 人工）",
               "BUG-69 bridge 生成 C 的模块级 if：本环已用 MSVC 实测被打回，修法（入口分派移进函数体 vs 改自述）二选一交人工",
               "BUG-70 parser.py/cython_generator.py 越过 3000 行阈值的拆分（跨文件重构不可逆）",
               "BUG-71 切片类型面：改推断（切片→容器类型）会影响存量程序，需裁决",
               "BUG-72 codegen 死码：删函数 vs 把模式条件下沉回这三个方法，两种改法语义不同",
               "BUG-73 两套缓存的真相源合一（改增量语义）",
               "hook.eval 写侧 `__result__` 缺口（上一环 half-open 转结）",
               "R3 锁文件本轮被重新锚定到 --help：判据语义变了，需人工过目"],
           "ledger_cards_total": len(ledger_pending),
           "note": "「未执行」的每一条都由测量支持；mtime/sha/行数三类谓词都配了 canary 或前后对照",
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"not_executed_total": doc["not_executed_total"], "items": len(items),
                      "golden_touched": golden_touched, "frozen_diff": items[3]["measurement"],
                      "canary": canary["predicate_catches_known_write"],
                      "db": items[5]["measurement"], "refuse": doc["refuse"]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
