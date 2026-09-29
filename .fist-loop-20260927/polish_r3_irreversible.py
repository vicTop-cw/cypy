"""R3-打磨 的不可逆动作面点名：本环确实动了产品码，所以"没越界"不能靠自述，要逐条 live 探针。

每条给 `method`（live_probe / derived / manifest）与当下实测值；
只有清单级的条目会写明**为什么只能清单级**（既有漂移是历轮未提交造成的，本环既没制造也没消除）。
件形状刻意与 `verify_r3_irreversible.json` 一致（items 为整数、detail 为逐条 dict），
否则下一环拿同一把尺子读不到键。
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
PY = sys.executable
EXPECTED_HEAD = "17d68b4"
STAGE_START_UTC = datetime(2026, 9, 27, 17, 37, 27, tzinfo=timezone.utc)
STAGE_START_EPOCH = calendar.timegm(STAGE_START_UTC.timetuple())
RADIUS_DIRS = ["cypyc", "cypy_hook", "cypy_bridge", "tests", "docs", "scripts", "examples"]
LANE = {"cypyc/cli.py", "cypy_hook/hook.py", "docs/USAGE.md",
        "tests/test_loop_20260927_fix_r3.py", "tests/test_loop_20260927_polish_r3.py"}
FROZEN = ["PROJECT-SPEC", "SYNTAX"]
BEFORE_DIR = HERE / "tmp_polish" / "before"
PREV = {"baselines": "verify_r3_baselines.json", "irreversible": "verify_r3_irreversible.json"}
REFUSE: list = []
DETAIL: list = []


def now_s() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, timeout=600):
    """只取 stdout：stderr 的告警会污染路径清单（上一环踩过）。"""
    proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def probe(action, method, executed, evidence, note=""):
    DETAIL.append({"action": action, "executed": bool(executed), "method": method,
                   "evidence": evidence, "note": note, "at_utc": now_s()})
    if executed:
        REFUSE.append(f"[不可逆面] {action} 被执行了（{method}）：{json.dumps(evidence, ensure_ascii=False)[:200]}")


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
            if p.suffix not in (".py", ".md", ".cypy", ".sh", ".toml"):
                continue
            if p.stat().st_mtime >= STAGE_START_EPOCH:
                out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(out)


def self_test() -> dict:
    """判据必须能红：先注入一条"被执行了"的假探针，确认 probe() 真的会记拒，再清空。"""
    before = len(REFUSE)
    probe("SELF-TEST 故意注入的违例", "live_probe", True, {"injected": "commit happened"}, "自测")
    caught = len(REFUSE) > before
    REFUSE[:] = [r for r in REFUSE if not r.startswith("[不可逆面] SELF-TEST")]
    DETAIL[:] = [d for d in DETAIL if d["action"] != "SELF-TEST 故意注入的违例"]
    return {"injected": 1, "caught": 1 if caught else 0,
            "refuse_after_cleanup": len(REFUSE)}


def main() -> int:
    st = self_test()
    if not st["caught"]:
        REFUSE.append("SELF-TEST 没被 probe() 抓住 ⇒ 本件的拒收通道是坏的，绿没有信息量")
        return 1
    prev_base = json.loads((HERE / PREV["baselines"]).read_text(encoding="utf-8"))
    prev_irr = json.loads((HERE / PREV["irreversible"]).read_text(encoding="utf-8"))
    # 跨环对照只用两边都有的键：先证明上一环件里确实有这个键，再拿它当基准（拿错键=恒假/恒真）
    prev_call_log = next((d["evidence"]["row_counts"]["call_log"] for d in prev_irr["detail"]
                          if "call_log" in (d["evidence"].get("row_counts") or {})), None)
    prev_deleted = prev_base["git"]["deleted_tracked"]
    if prev_call_log is None:
        REFUSE.append("上一环件里没有 row_counts.call_log ⇒ 没有可比基准，本条不许按 0 处理")

    rc, head = sh(["git", "rev-parse", "HEAD"])
    head = head.strip()
    rc2, reflog = sh(["git", "reflog", "-1", "--format=%H %gd %gs"])
    probe("git commit（本地提交）", "live_probe",
          not (rc == 0 and head.startswith(EXPECTED_HEAD)),
          {"head": head[:12], "expected": EXPECTED_HEAD, "reflog_top": reflog.strip()[:160]},
          "实测判据：HEAD 仍是本轮底树 ⇒ 本环零 commit")

    rc, ahead = sh(["git", "rev-list", "--count", "@{u}..HEAD"])
    rc_rl, rl = sh(["git", "reflog", "show", "@{u}", "-1", "--date=iso"])
    ahead_now = ahead.strip()
    ahead_prev = str(prev_base["git"]["ahead_of_upstream"])
    rl_line = rl.strip()
    rl_when = None
    m = re.search(r"@\{(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\}", rl_line)
    if m:
        rl_when = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z")
    probe("git push（推送到远端）", "live_probe",
          ahead_now != ahead_prev or (rl_when is not None
                                      and calendar.timegm(rl_when.timetuple()) >= STAGE_START_EPOCH),
          {"ahead_of_upstream_now": ahead_now, "ahead_at_prev_stage": ahead_prev,
           "upstream": sh(["git", "rev-parse", "--abbrev-ref", "@{u}"])[1].strip(),
           "remote_reflog_top": rl_line[:160],
           "remote_reflog_parsed": bool(m)},
          "判据两半：本地领先数与上一环实测相等（推过就会变 0）＋ 远端跟踪 ref 的 reflog 顶条时间早于开工")

    rc, staged = sh(["git", "diff", "--cached", "--name-only"])
    rc_d, dirty = sh(["git", "status", "--porcelain"])
    staged_rows = [x for x in staged.splitlines() if x.strip()]
    dirty_rows = [x for x in dirty.splitlines() if x.strip()]
    deleted = [ln for ln in dirty_rows if ln.startswith((" D", "AD"))]
    probe("git add / 暂存区写入", "live_probe", bool(staged_rows),
          {"staged_files": staged_rows[:5], "staged_count": len(staged_rows),
           "dirty_rows": len(dirty_rows)},
          f"暂存区必须为空；{len(dirty_rows)} 条脏行是历轮未提交成果（红线禁止提交，只挂账）")

    rc, tags = sh(["git", "for-each-ref",
                   "--format=%(refname:short)|%(creatordate=iso8601)", "refs/tags"])
    tag_lines = [ln for ln in tags.splitlines() if ln.strip()]
    fresh = []
    for ln in tag_lines:
        name, _, date = ln.partition("|")
        try:
            when = datetime.strptime(date.strip(), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            fresh.append(f"{ln}（日期解析不出来 ⇒ 不敢当作旧 tag）")
            continue
        if calendar.timegm(when.timetuple()) >= STAGE_START_EPOCH:
            fresh.append(name)
    probe("git tag（新标签）", "live_probe", bool(fresh),
          {"tag_total": len(tag_lines), "created_after_stage_start": fresh},
          f"开工口径 {STAGE_START_UTC.isoformat()} 之后新建的 tag 必须为 0")

    rc, branches = sh(["git", "branch", "-a", "--format=%(refname:short)"])
    rc_b, cur_branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch_rows = [x for x in branches.splitlines() if x.strip()]
    probe("删分支 / 合并 PR", "manifest", False,
          {"branch_count": len(branch_rows), "branches": branch_rows[:12],
           "current_branch": cur_branch.strip(), "has_upstream":
               sh(["git", "rev-parse", "--abbrev-ref", "@{u}"])[1].strip()[:60]},
          "清单级：开工前没留 branch 清单快照，删除会连 reflog 一起消失 ⇒ 事后探针证不了'没删过'，"
          "只能证当下计数与所在分支；本环确实未跑 git branch -d / merge（push 面另有 live 探针，"
          "仓库有 origin/master 上游，所以'不可能推'这句不成立，改为实测领先数与远端 reflog）")

    frozen_touched = touched_in_window(FROZEN)
    probe("改 PROJECT-SPEC / SYNTAX 冻结语义", "live_probe", bool(frozen_touched),
          {"files_touched_in_stage_window": frozen_touched,
           "stage_start_utc": STAGE_START_UTC.isoformat()},
          "mtime 反解，不是自述")

    rc, drift = sh(["git", "diff", "--numstat", "HEAD", "--", "PROJECT-SPEC", "SYNTAX"])
    drows = [ln.split("\t") for ln in drift.splitlines() if ln.strip()]
    add = sum(int(r[0]) for r in drows if r[0] != "-")
    dele = sum(int(r[1]) for r in drows if r[1] != "-")
    probe("既有冻结文档漂移被本环吞掉或冒充已修", "manifest", False,
          {"files": len(drows), "added": add, "removed": dele,
           "files_list": [r[2] for r in drows][:6]},
          "清单级：这是历轮未提交造成的，diff-vs-HEAD 分不出是谁改的 ⇒ 只作上界记录并交裁决，不取交集")

    probe("删除被跟踪文件", "live_probe", len(deleted) != prev_deleted,
          {"deleted_rows_now": len(deleted), "deleted_rows_at_prev_stage": prev_deleted,
           "rows": [x.strip() for x in deleted][:6]},
          "与上一环同键（deleted_tracked）对照：数目一变就说明有人删了档")

    window = touched_in_window(RADIUS_DIRS)
    probe("对非本环文件整档 formatter 重排", "derived", not set(window) <= LANE,
          {"files_touched_in_stage_window": window, "lane_files": sorted(LANE)},
          "由半径反解：black/ruff --fix 整档跑必然在其他文件上留下 mtime")

    cur = (ROOT / "tests" / "test_loop_20260927_fix_r3.py").read_text(encoding="utf-8", newline="")
    old = (BEFORE_DIR / "test_loop_20260927_fix_r3.py").read_text(encoding="utf-8", newline="")
    cur_names = set(re.findall(r"^def (test_\w+)", cur, flags=re.M))
    old_names = set(re.findall(r"^def (test_\w+)", old, flags=re.M))
    gone = sorted(old_names - cur_names)
    probe("弱化/删除既有测试", "live_probe", bool(gone),
          {"names_before": len(old_names), "names_after": len(cur_names), "disappeared": gone},
          "改前快照（tmp_polish/before）与盘面逐名对照；名字没少才谈得上没删")

    rc, wt = sh(["git", "worktree", "list"])
    paths = [ln.split()[0] for ln in wt.splitlines() if ln.strip()]
    foreign = any("_cypy_head_baseline" in p for p in paths)
    probe("删别人的 worktree", "live_probe", not foreign,
          {"worktrees": paths}, "foreign 树必须原样在")

    rc, out = sh([PY, "-X", "utf8", "-c",
                  "import sqlite3;"
                  "db=sqlite3.connect('file:fist-mbt.db?mode=ro',uri=True);"
                  "print(db.execute('select count(*) from call_log').fetchone()[0]);"
                  "print(db.execute(\"select count(*) from call_log where tool like '%issue_up%'\").fetchone()[0])"])
    nums = [x.strip() for x in out.splitlines() if x.strip().isdigit()]
    cur_rows = int(nums[0]) if nums else -1
    issue_up_hits = int(nums[1]) if len(nums) > 1 else -1
    probe("清空/回退 FIST 任务库", "live_probe" if prev_call_log is not None else "manifest",
          prev_call_log is not None and cur_rows < prev_call_log,
          {"call_log_rows_now": cur_rows, "call_log_rows_at_prev_closure": prev_call_log,
           "issue_up_tool_rows": issue_up_hits},
          "只增不减才算没动库；issue_up 在本 FIST 构建里不是工具名（实测 30 个工具无此项）⇒ 如实上报")

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
           "detail": DETAIL,
           "stage_start_utc": STAGE_START_UTC.isoformat(),
           "lane_files": sorted(LANE), "radius_window": window,
           "started_at_utc": now_s(), "finished_at_utc": now_s()}
    (HERE / "polish_r3_irreversible.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": REFUSE, "items": doc["items"], "kinds": kinds,
                      "executed_none": doc["executed_none"], "radius_window": window},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
