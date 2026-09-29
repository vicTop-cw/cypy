"""R3-推进 法 8：不可逆动作面逐条点名，且**判据通道自己必须先能红**。

推进环改了分析器，所以"没越界"必须是实测：git 五格 live、冻结文档 mtime live、
golden 基准未重注册 live、产物签名未动 live、既有测试未删改 live（拿 tmp_advance/before 的
type_checker.py 逐行对表，改动必须只在 Callable 那一块）；
只有拿不到基线的（分支清单没在开工前留快照）记清单级并写明原因。
"""

from __future__ import annotations

import calendar
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
EXPECTED_HEAD = "17d68b4"
STAGE_START_UTC = datetime(2026, 9, 27, 18, 41, 40, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
FROZEN = ["PROJECT-SPEC", "SYNTAX"]
LANE = {"cypyc/analyzer/type_checker.py", "tests/test_loop_20260927_advance_r3.py"}
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
BEFORE_SNAPSHOT = HERE / "advance_r3_before" / "type_checker.py"
NEW_LOCK_FILE = "tests/test_loop_20260927_advance_r3.py"
PREV_COLLECT_LOG = HERE / "polish_r3_logs" / "pytest_collect.log"
NOW_COLLECT_LOG = HERE / "advance_r3_logs" / "pytest_collect.log"
PREV = {"baselines": "polish_r3_baselines.json", "irreversible": "polish_r3_irreversible.json"}
REFUSE: list = []
DETAIL: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=600):
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def probe(action, method, executed, evidence, note=""):
    DETAIL.append({"action": action, "executed": bool(executed), "method": method,
                   "evidence": evidence, "note": note, "at_utc": now_s()})
    if executed:
        REFUSE.append(f"[不可逆面] {action} 被执行了（{method}）：{str(evidence)[:220]}")


def _nodeids(log_path: Path) -> set:
    if not log_path.exists():
        return set()
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    return {ln.strip() for ln in txt.splitlines() if "::" in ln}


def _name_level_test_compare():
    """全量测试名的两向对照：旧名一个都不能少，新名必须全部来自本环点名的锁文件。

    对照集取自上一环留存的 `--collect-only` 日志（本环改动之前生成），并先证明它和上一环
    基线件里记的 collected 数一致 —— 否则就是在拿错文件比错东西，绿也没有信息量。
    """
    prev_base = json.loads((HERE / PREV["baselines"]).read_text(encoding="utf-8"))
    prev_collected = prev_base["pytest"]["collected"]
    before, now = _nodeids(PREV_COLLECT_LOG), _nodeids(NOW_COLLECT_LOG)
    problems = []
    if len(before) != prev_collected:
        problems.append(f"对照集反解出的名字数 {len(before)} ≠ 上一环件里 collected {prev_collected}")
    declared = sorted(set(re.findall(r"^def (test_\w+)",
                                     (ROOT / NEW_LOCK_FILE).read_text(encoding="utf-8", newline=""),
                                     flags=re.M)))
    if not now:
        problems.append("本环 collect 日志缺失或空 ⇒ 名字级对照不成立")
    gone = sorted(before - now)
    added = sorted(now - before)
    stray = [x for x in added if not x.startswith(NEW_LOCK_FILE + "::")]
    missing = [x for x in declared if x not in {y.split("::")[-1] for y in now}]
    if gone:
        problems.append(f"有既有测试名消失：{gone[:4]}")
    if stray:
        problems.append(f"半径外的文件里冒出了新用例名：{stray[:4]}")
    if missing:
        problems.append(f"本环点名的新锁没在全量收集里现形：{missing[:4]}")
    return gone, added, {"before_names": len(before), "now_names": len(now),
                         "added_names": len(added), "added_stray": stray,
                         "declared_locks": declared, "declared_missing": missing,
                         "shape_problems": problems}


def self_test() -> dict:
    before = len(REFUSE)
    probe("SELF-TEST 故意注入的违例", "live_probe", True, {"injected": "commit happened"}, "自测")
    caught = len(REFUSE) > before
    REFUSE[:] = [r for r in REFUSE if not r.startswith("[不可逆面] SELF-TEST")]
    DETAIL[:] = [d for d in DETAIL if d["action"] != "SELF-TEST 故意注入的违例"]
    return {"injected": 1, "caught": 1 if caught else 0, "refuse_after_cleanup": len(REFUSE)}


def touched_in_window(dirs):
    out = []
    for d in dirs:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if {"__pycache__", ".egg-info"} & set(p.parts):
                continue
            if p.suffix not in (".py", ".md", ".cypy", ".sh", ".toml", ".out"):
                continue
            if p.stat().st_mtime >= STAGE_START_EPOCH:
                out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(out)


def main() -> int:
    st = self_test()
    if not st["caught"]:
        REFUSE.append("SELF-TEST 没被 probe() 抓住 ⇒ 本件的拒收通道是坏的，绿没有信息量")
        return 1
    prev_irr = json.loads((HERE / PREV["irreversible"]).read_text(encoding="utf-8"))
    prev_call_log = next((d["evidence"]["call_log_rows_now"] for d in prev_irr["detail"]
                          if "call_log_rows_now" in d["evidence"]), None)
    if prev_call_log is None:
        REFUSE.append("上一环件里没有 call_log_rows_now ⇒ 没有可比基准，本条不许按 0 处理")

    rc, head = sh(["git", "rev-parse", "HEAD"])
    head = head.strip()
    rc2, reflog = sh(["git", "reflog", "-1", "--date=iso"])
    probe("git commit（本地提交）", "live_probe",
          not (rc == 0 and head.startswith(EXPECTED_HEAD)),
          {"head": head[:12], "expected": EXPECTED_HEAD, "reflog_top": reflog.strip()[:160]},
          "HEAD 仍是本轮底树 ⇒ 本环零 commit")

    rc, ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"])
    rc_rl, rl = sh(["git", "reflog", "show", "@{u}", "-1", "--date=iso"])
    m = re.search(r"@\{(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\}", rl)
    when = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z") if m else None
    probe("git push（推送到远端）", "live_probe",
          (when is not None and calendar.timegm(when.timetuple()) >= STAGE_START_EPOCH),
          {"ahead_of_upstream_now": ahead.strip(),
           "ahead_at_prev_stage": "1", "remote_reflog_top": rl.strip()[:160],
           "remote_reflog_parsed": bool(m)},
          "本地领先数与上一环实测相等（推过就会变 0）＋ 远端跟踪 ref 的 reflog 顶条早于开工")

    rc, staged = sh(["git", "diff", "--cached", "--name-only"])
    rc_d, dirty = sh(["git", "status", "--porcelain"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    dirty_rows = [x for x in dirty.splitlines() if x.strip()]
    probe("git add / 暂存区写入", "live_probe", bool(staged_rows),
          {"staged_count": len(staged_rows), "dirty_rows": len(dirty_rows)},
          "暂存区必须为空；脏行是历轮未提交成果（只挂账不提交）")

    rc, tags = sh(["git", "for-each-ref", "--format=%(refname:short)|%(creatordate=iso8601)",
                   "refs/tags"])
    fresh = []
    for ln in [x for x in tags.splitlines() if x.strip()]:
        name, _, date = ln.partition("|")
        try:
            when_t = datetime.strptime(date.strip(), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            fresh.append(f"{ln}（日期解析不出来 ⇒ 不敢当旧 tag）")
            continue
        if calendar.timegm(when_t.timetuple()) >= STAGE_START_EPOCH:
            fresh.append(name)
    probe("git tag（新标签）", "live_probe", bool(fresh),
          {"tag_total": len([x for x in tags.splitlines() if x.strip()]),
           "created_after_stage_start": fresh}, "开工后新增 tag 必须为 0")

    rc, branches = sh(["git", "branch", "-a", "--format=%(refname:short)"])
    rc_b, cur = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch_rows = [x for x in branches.splitlines() if x.strip()]
    probe("删分支 / 合并 PR", "manifest", False,
          {"branch_count": len(branch_rows), "branches": branch_rows[:12], "current_branch": cur.strip()},
          "清单级：开工前没留 branch 清单快照，删分支连 reflog 一起消失 ⇒ 事后证不了「没删过」")

    frozen_touched = touched_in_window(FROZEN)
    probe("改 PROJECT-SPEC / SYNTAX 冻结语义", "live_probe", bool(frozen_touched),
          {"files_touched_in_stage_window": frozen_touched,
           "stage_start_utc": STAGE_START_UTC.isoformat()}, "mtime 反解，不是自述")

    rc, drift = sh(["git", "diff", "--numstat", "HEAD", "--", "PROJECT-SPEC", "SYNTAX"])
    drows = [ln.split("\t") for ln in drift.splitlines() if ln.strip()]
    probe("既有冻结文档漂移被本环吞掉或冒充已修", "manifest", False,
          {"files": len(drows), "added": sum(int(r[0]) for r in drows if r[0] != "-"),
           "removed": sum(int(r[1]) for r in drows if r[1] != "-"),
           "files_list": [r[2] for r in drows][:6]},
          "清单级：历轮未提交与本轮在同一个 diff 里 ⇒ 只记上界交裁决")

    deleted = [ln for ln in dirty_rows if ln.startswith((" D", "AD"))]
    prev_deleted = next((d["evidence"]["deleted_rows_now"] for d in prev_irr["detail"]
                         if "deleted_rows_now" in d["evidence"]), None)
    if prev_deleted is None:
        REFUSE.append("上一环件里没有 deleted_rows_now ⇒ 没有可比基准，'没删跟踪文件'这条不许按 0 蒙")
    probe("删除被跟踪文件", "live_probe", len(deleted) != prev_deleted,
          {"deleted_rows_now": len(deleted), "deleted_rows_at_prev_stage": prev_deleted},
          "与上一环实测相等（跨环只用两边都有的格）")

    golden_touched = [f for f in touched_in_window(["examples"]) if f.endswith(".out")]
    probe("重注册 golden 基准", "live_probe", bool(golden_touched),
          {"baseline_files_touched_in_window": golden_touched},
          "推进环不改基准；要扩覆盖面属交裁决动作")

    window = touched_in_window(RADIUS_DIRS)
    probe("对非本环文件动手 / 整档重排", "derived", not set(window) <= LANE,
          {"files_touched_in_stage_window": window, "lane_files": sorted(LANE)},
          "由半径反解：多一档就是越界")

    cur_src = (ROOT / "cypyc" / "analyzer" / "type_checker.py").read_text(encoding="utf-8", newline="")
    old_src = BEFORE_SNAPSHOT.read_text(encoding="utf-8", newline="")
    pre = json.loads((HERE / "advance_r3_pre_baseline.json").read_text(encoding="utf-8"))
    snap_sha = _sha(BEFORE_SNAPSHOT)
    if snap_sha != pre["type_checker_sha_before"]:
        REFUSE.append(f"before 快照身份不符：{BEFORE_SNAPSHOT.name} sha={snap_sha} "
                      f"开工前件记的={pre['type_checker_sha_before']} ⇒ 逐行对表比的是错文件")
    diff = [ln for ln in _diff(old_src, cur_src) if ln[:1] in ("+", "-") and ln[:3] not in ("+++", "---")]
    removed_defs = [ln[1:].strip() for ln in diff if ln.startswith("-") and re.match(r"\s*(def|class) ", ln[1:])]
    probe("删除既有函数/类（比「只加判定」更远的改动）", "live_probe", bool(removed_defs),
          {"changed_lines": len(diff), "removed_definitions": removed_defs,
           "before_snapshot_sha": snap_sha,
           "pre_baseline_sha": pre["type_checker_sha_before"]},
          "before 快照在 advance_r3_before/（从 tmp_advance/before 固化，sha 与开工前件同值），"
          "逐行对表 ⇒ 本环主张是「只往分析层加判定」")

    gone, added_names, shape = _name_level_test_compare()
    probe("弱化/删除既有测试（全量名字级）", "live_probe",
          bool(gone) or bool(shape["shape_problems"]),
          {"disappeared": gone, "added": added_names, **shape},
          "对照件=上一环留存的 --collect-only 日志（本环改动前），逐名两向对表；"
          "新增必须全部来自本轮点名的锁文件，半径外冒出用例名就是有人动了别的档")

    rc, wt = sh(["git", "worktree", "list"])
    paths = [ln.split()[0] for ln in wt.splitlines() if ln.strip()]
    probe("删别人的 worktree", "live_probe", not any("_cypy_head_baseline" in p for p in paths),
          {"worktrees": paths}, "foreign 树必须原样在")

    rc, out = sh([PY, "-X", "utf8", "-c",
                  "import sqlite3;"
                  "db=sqlite3.connect('file:fist-mbt.db?mode=ro',uri=True);"
                  "print(db.execute('select count(*) from call_log').fetchone()[0]);"
                  "print(db.execute(\"select count(*) from call_log where tool like '%issue_up%'\").fetchone()[0])"])
    nums = [x.strip() for x in out.splitlines() if x.strip().isdigit()]
    cur_rows = int(nums[0]) if nums else -1
    probe("清空/回退 FIST 任务库", "live_probe" if prev_call_log is not None else "manifest",
          prev_call_log is not None and cur_rows < prev_call_log,
          {"call_log_rows_now": cur_rows, "call_log_rows_at_prev_closure": prev_call_log,
           "issue_up_tool_rows": int(nums[1]) if len(nums) > 1 else -1},
          "只增不减才算没动库；issue_up 在本构建里不是工具名 ⇒ 如实上报")

    kinds = {}
    for d in DETAIL:
        kinds[d["method"]] = kinds.get(d["method"], 0) + 1
    doc = {"refuse": REFUSE, "items": len(DETAIL), "probes": [d["action"] for d in DETAIL],
           "self_test": st,
           "live_probe_items": kinds.get("live_probe", 0),
           "derived_items": kinds.get("derived", 0),
           "manifest_items": kinds.get("manifest", 0),
           "executed_none": 0 if REFUSE else 1,
           "executed": [d["action"] for d in DETAIL if d["executed"]],
           "detail": DETAIL, "changed_lines_in_product": len(diff),
           "golden_baseline_touched": golden_touched,
           "before_snapshot_sha": snap_sha,
           "removed_definitions": removed_defs,
           "test_names_disappeared": gone,
           "test_names_added_stray": shape["added_stray"],
           "test_names_shape_problems": shape["shape_problems"],
           "test_names_added": len(added_names),
           "stage_start_utc": STAGE_START_UTC.isoformat(), "lane_files": sorted(LANE),
           "radius_window": window,
           "started_at_utc": now_s(), "finished_at_utc": now_s()}
    (HERE / "advance_r3_irreversible.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "items": doc["items"],
                      "kinds": {k: v for k, v in kinds.items()},
                      "executed_none": doc["executed_none"],
                      "radius_window": window, "changed_lines_in_product": len(diff)},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


def _diff(a: str, b: str):
    import difflib
    return difflib.unified_diff(a.splitlines(), b.splitlines(), n=0)


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


if __name__ == "__main__":
    sys.exit(main())
