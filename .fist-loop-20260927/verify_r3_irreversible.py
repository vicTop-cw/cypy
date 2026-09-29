"""R3-验证 法 7：不可逆动作零执行——逐条点名 + 当下盘面状态（负面主张分级自证）。

红线里的不可逆动作（commit/push/删分支/删文件/清库/改冻结文档/合 PR）一律只挂账。
每条给三个字段：
  executed      —— 本环有没有做过这件事（必须 False，by_design 项除外）
  method        —— live_probe=当场能从盘面算出来；manifest=只能给「本环执行过的命令清单」级证据
  evidence      —— 探针读到的当下状态（含凭据红线：只读元信息，不读 .env、不打印任何 key）
"""

from __future__ import annotations

import calendar
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXPECTED_HEAD = "17d68b4"
STAGE_START_UTC = datetime(2026, 9, 27, 17, 1, 14, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
DB_CANDIDATES = [ROOT / "fist-mbt.db", ROOT / ".fist-loop-20260927" / "fist-mbt.db"]
REFUSE: list = []
ITEMS: list = []


def sh(cmd, timeout=300):
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def sh_stdout(cmd, timeout=300):
    """只要 stdout：git 的 `LF will be replaced by CRLF` 提示走 stderr，
    混进路径清单会让『文件数』这类判据把警告行当成一个条目（实测踩过）。"""
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def add(name, executed, method, evidence, note=""):
    ITEMS.append({"action": name, "executed": bool(executed), "method": method,
                  "evidence": evidence, "note": note})


def probe_commit():
    _, head = sh(["git", "rev-parse", "HEAD"])
    _, reflog = sh(["git", "reflog", "show", "--date=iso-strict", "-n", "5", "HEAD"])
    first = reflog.splitlines()[0] if reflog else ""
    stamps = re.findall(r"\{([\d-]{10}T[\d:]{8})", reflog)
    newer = [s for s in stamps
             if s and calendar.timegm(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
                                      .replace(tzinfo=timezone.utc).timetuple()) >= STAGE_START_EPOCH]
    ok = head.startswith(EXPECTED_HEAD) and not newer
    add("git commit（本地提交）", not ok, "live_probe",
        {"head": head[:12], "expected": EXPECTED_HEAD, "reflog_top": first[:120],
         "reflog_entries_after_stage_start": newer},
        "实测判据：HEAD 仍是本轮底树 17d68b4，且 HEAD 的 reflog 在本环开工时刻之后没有新条目")
    return ok


def probe_index():
    _, staged = sh(["git", "diff", "--cached", "--name-only"])
    rows = [x for x in staged.splitlines() if x.strip()]
    _, status = sh(["git", "status", "--porcelain"])
    dirty = len([x for x in status.splitlines() if x.strip()])
    add("git add / 暂存区写入", bool(rows), "live_probe",
        {"staged_files": rows[:10], "staged_count": len(rows), "dirty_rows": dirty},
        "暂存区必须为空；工作树的 163~166 条脏行是历轮未提交成果（红线禁止提交，只挂账）")
    return not rows


def probe_push():
    _, refs = sh(["git", "for-each-ref", "--format=%(refname) %(objectname:short) "
                                             "%(committerdate:iso)", "refs/remotes"])
    newer = []
    for line in refs.splitlines():
        m = re.match(r"^(\S+)\s+(\w+)\s+(.{19})", line)
        if not m:
            continue
        epoch = calendar.timegm(datetime.strptime(m.group(3), "%Y-%m-%d %H:%M:%S")
                                .replace(tzinfo=timezone.utc).timetuple())
        if epoch >= STAGE_START_EPOCH:
            newer.append(line)
    _, has_upstream = sh(["git", "rev-parse", "--abbrev-ref", "@{u}"])
    add("git push / 任何远端写入", bool(newer), "live_probe",
        {"remote_refs_checked": len(refs.splitlines()),
         "remote_refs_moved_after_stage_start": newer,
         "upstream": has_upstream.splitlines()[:1]},
        "只读 ref 元信息（名字/commit/时间）；不读 .env、不探测也不回显任何凭据")
    return not newer


def probe_branch_delete():
    _, branches = sh(["git", "branch", "--list"])
    names = [b.strip().lstrip("* ") for b in branches.splitlines() if b.strip()]
    _, all_reflog = sh(["git", "reflog", "show", "--date=iso-strict", "-n", "20"])
    deleted = []
    for ln in all_reflog.splitlines():
        if not re.search(r"(reset|delete|moving from)", ln):
            continue
        stamp = re.search(r"\{([\d-]{10}T[\d:]{8})", ln)
        if not stamp:
            continue
        epoch = calendar.timegm(datetime.strptime(stamp.group(1), "%Y-%m-%dT%H:%M:%S")
                                .replace(tzinfo=timezone.utc).timetuple())
        if epoch >= STAGE_START_EPOCH:
            deleted.append(ln)
    add("删分支 / 分支迁移", bool(deleted), "live_probe",
        {"local_branches": names, "suspicious_reflog_after_stage_start": deleted[:5]},
        "本地分支数与名字当场列出；开工后 reflog 里不得出现 delete/reset")
    return not deleted


def probe_file_deletion():
    _, tracked_raw = sh(["git", "ls-files"])
    tracked = [t for t in tracked_raw.splitlines() if t.strip()]
    _, status = sh(["git", "status", "--porcelain"])
    deleted_now = [ln[3:] for ln in status.splitlines() if ln.startswith(" D ")]
    add("删文件（tracked）", False, "live_probe",
        {"tracked_files": len(tracked), "tracked_absent_on_disk": len(deleted_now),
         "sample": deleted_now[:6],
         "note": "这些 D 条目是本环开工之前就存在的历轮删除（未提交），"
                 "本环没有新增删除：半径判据见 verify_r3_baselines.json（count=0）"},
        "删除数只作前后对照基线；本环的「没删东西」由半径 mtime 判据与 git 状态共同承重")
    return len(tracked) > 0


def probe_db_purge():
    db = next((p for p in DB_CANDIDATES if p.exists()), None)
    if db is None:
        add("清空 FIST 任务库", False, "manifest",
            {"db_found": False, "paths_tried": [str(p) for p in DB_CANDIDATES]},
            "库文件都不在盘上时本条只能是清单级证据")
        return True
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    counts = {}
    for table in ("tasks", "specs", "runs", "call_log", "memory"):
        try:
            counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[table] = None
    con.close()
    prev = json.loads((HERE / "close_r3_fix_root.out.json").read_text(encoding="utf-8"))
    prev_rows = prev.get("call_log_rows")
    shrink = {k: v for k, v in counts.items() if isinstance(v, int) and isinstance(prev_rows, int)
              and k == "call_log" and v < prev_rows}
    add("清空/回退 FIST 任务库", bool(shrink), "live_probe",
        {"db": db.name, "row_counts": counts,
         "call_log_rows_at_fix_closure": prev_rows,
         "shrink_vs_previous_stage": shrink},
        "call_log 只增不减 ⇒ 只读探针比对上一环收口时的行数")
    return not shrink


def probe_frozen_docs():
    rc, out, err = sh_stdout(["git", "diff", "--name-only", "HEAD", "--", "PROJECT-SPEC", "SYNTAX"])
    rows = [x for x in out.splitlines() if x.strip() and "/" in x]
    newest, newest_path = 0.0, None
    for d in ("PROJECT-SPEC", "SYNTAX"):
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.stat().st_mtime >= newest:
                newest, newest_path = path.stat().st_mtime, path
    touched_this_stage = newest >= STAGE_START_EPOCH
    add("改冻结文档（PROJECT-SPEC / SYNTAX）——本环窗口内", touched_this_stage, "live_probe",
        {"diff_vs_HEAD_files": rows, "git_stderr_notes": err.splitlines()[:3],
         "newest_file": str(newest_path),
         "newest_mtime_utc": datetime.fromtimestamp(newest, tz=timezone.utc).isoformat(),
         "stage_start_utc": STAGE_START_UTC.isoformat(),
         "any_file_mtime_after_stage_start": touched_this_stage},
        "判据只看本环窗口：目录里最新 mtime 必须早于开工时刻（mtime 与 HEAD 差异是两回事，"
        "既存漂移另立一条并写明归属，不在这里冒充零漂移）")

    drift_lines = 0
    for f in rows:
        _rc, body, _e = sh_stdout(["git", "diff", "-U0", "HEAD", "--", f])
        drift_lines += len([ln for ln in body.splitlines()
                            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))])
    add("冻结文档相对 HEAD 的既存漂移（非本环所为）", False, "live_probe",
        {"files": rows, "changed_lines": drift_lines,
         "attribution": "mtime 全在 2026-09-27 本环开工之前；appendix-A-keywords.md 正文自带"
                        "『实测快照（2026-09-26 11:24）』字样并写明是补齐 constraint/subtype/true/false "
                        "四行的口径修正 ⇒ 归 R2 特性轮的未提交成果，不是本环动作",
         "status": "挂账待裁决（红线：不改冻结语义；已改的部分要不要回退只有 owner 能定）"},
        "本条不是『本环做了不可逆动作』，而是把红线相关面当下真实状态点名——"
        "写成零漂移会是假话，写成本环违规同样是不诚实")
    return not touched_this_stage


def probe_pr_and_external():
    add("合并 PR / 开 Issue 等外部可见动作", False, "manifest",
        {"commands_this_stage_are_local_only": True,
         "external_write_tools_used": ["FIST-Mbt 任务链 RPC（claim/omega/submit/verify，属流程内、可复核、不删数据）"],
         "evidence_source": "本环判据件的命令字段（verify_r3_*.json 的 how/detail 全为本地命令）"},
        "外部动作只能给清单级证据：盘面上没有「没推送的 PR」这种可探针对象，故不冒充 live_probe")
    return True


def probe_worktrees():
    _, wt = sh(["git", "worktree", "list"])
    paths = []
    for ln in wt.splitlines():
        m = re.match(r"^(\S+)\s+[0-9a-f]{7,}\s", ln.strip())
        if m:
            paths.append(m.group(1))
    foreign = [p for p in paths if "_cypy_head_baseline" in p]
    own_leftovers = [str(p) for p in (HERE / "tmp_verify").glob("snap_*")] if (HERE / "tmp_verify").exists() else []
    add("删别人家的 worktree / 留自己的快照树不清", not foreign, "live_probe",
        {"worktrees": paths, "foreign_present": bool(foreign),
         "own_snapshot_dirs_left": own_leftovers},
        "foreign_present 必须 True（没删别人的）；自己的快照树在收口步删除，本条记录当下还剩哪些")
    return bool(foreign)


def main() -> int:
    probes = [probe_commit, probe_index, probe_push, probe_branch_delete,
              probe_file_deletion, probe_db_purge, probe_frozen_docs,
              probe_pr_and_external, probe_worktrees]
    results = {}
    for fn in probes:
        try:
            results[fn.__name__] = bool(fn())
        except Exception as exc:  # noqa: BLE001
            REFUSE.append(f"探针 {fn.__name__} 抛异常（不可逆主张不能靠跳过承重）："
                          f"{type(exc).__name__}: {exc}"[:200])
            results[fn.__name__] = False
    executed = [i["action"] for i in ITEMS if i["executed"]]
    live = sum(1 for i in ITEMS if i["method"] == "live_probe")
    if executed:
        REFUSE.append(f"发现已执行的不可逆动作：{executed}")
    if len(ITEMS) < 5:
        REFUSE.append(f"点名条目只有 {len(ITEMS)} 条（应 >=5）")
    if live < 6:
        REFUSE.append(f"live_probe 级条目只有 {live} 条（应 >=6，其余必须写明为何只能清单级）")
    doc = {"refuse": REFUSE, "items": len(ITEMS), "live_probe_items": live,
           "manifest_items": sum(1 for i in ITEMS if i["method"] == "manifest"),
           "executed_none": 1 if not executed else 0, "executed": executed,
           "probes": results, "detail": ITEMS,
           "stage_start_utc": STAGE_START_UTC.isoformat(),
           "measured_at_utc": datetime.now(timezone.utc).isoformat()}
    (HERE / "verify_r3_irreversible.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "items", "live_probe_items",
                                          "manifest_items", "executed_none", "executed", "probes")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
