"""R3-验证 法 4：报告与账本自洽审计（正文计数反解 + 被拒逐字对表 + FIXED 段复跑）。

三块都是「拿上一环说过的话当被测对象」：
A. 页脚每条数字/清单从**判据件**反解（不是从正文另一处取），逐条对表；
B. 《被拒原文》表与 `close_r3_fix_root.out.json` 的 refused 做**双向**集合对表
   （少引=吞条，多引=伪造，逐字不等=改写）；
C. `memory/bugs.md` 里本轮 6 个 `### FIXED` 段各自的「复跑」命令当场再跑，
   退出码必须等于该段自己声明的 after rc。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "memory" / "reviews" / "20260928.00.20.00.md"
LEDGER = ROOT / "memory" / "bugs.md"
ROUND_TAG = "2026-09-28 R3-修复"
PY = sys.executable
COUNTS: list = []
REFUSE: list = []


def art(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def claim(name, reported, recomputed, source, ok=None):
    equal = (str(reported) == str(recomputed)) if ok is None else bool(ok)
    COUNTS.append({"claim": name, "reported": reported, "recomputed": recomputed,
                   "source": source, "equal": equal})
    if not equal:
        REFUSE.append(f"[计数对表] {name}：报告说 {reported!r}，判据件算得 {recomputed!r}（依据 {source}）")
    return equal


def parse_footer(text: str) -> str:
    m = re.search(r"\[selfdrive-fix\][^\n]*", text)
    if not m:
        REFUSE.append("报告里找不到 `[selfdrive-fix]` 页脚 ⇒ 审计对象缺失")
        return ""
    return m.group(0)


def part_a():
    text = REPORT.read_text(encoding="utf-8")
    footer = parse_footer(text)
    if not footer:
        return
    foot = dict(re.findall(r"(\w+)=([^\s]+)", footer))
    root_out = art("root_r3_fix.out.json")
    root_close = art("close_r3_fix_root.out.json")
    spec = art("report_spec_r3_fix.json")
    locks_inv = art("fix_r3_locks_inventory.json")
    baselines = art("fix_r3_baselines.json")
    evidence = art("fix_r3_evidence.json")
    plan = art("fix_r3_plan.json")

    claim("root", foot.get("root"), root_out.get("root"), "root_r3_fix.out.json:root")
    claim("gates", foot.get("gates"), len(spec["gates"]), "report_spec_r3_fix.json:gates")
    claim("refused", foot.get("refused"), len(root_close["refused"]),
          "close_r3_fix_root.out.json:refused")

    test_src = (ROOT / "tests" / "test_loop_20260927_fix_r3.py").read_text(encoding="utf-8")
    defs = re.findall(r"^def (test_\w+)", test_src, flags=re.M)
    plan_locks = sum(len(b["locks"]) for b in plan["per_bug"])
    plan_pos = sum(len(b["pos_locks"]) for b in plan["per_bug"])
    plan_ctl = sum(len(b["ctl_locks"]) for b in plan["per_bug"])
    m = re.search(r"locks=(\d+)\(pos=(\d+),ctl=(\d+)\)", footer)
    reported_locks = m.groups() if m else ("?", "?", "?")
    claim("locks 条数（页脚 vs 测试文件 def test_ 计数）", reported_locks[0], len(defs),
          "tests/test_loop_20260927_fix_r3.py")
    claim("pos 条数", reported_locks[1], plan_pos, "fix_r3_plan.json:pos_locks 求和")
    claim("ctl 条数", reported_locks[2], plan_ctl, "fix_r3_plan.json:ctl_locks 求和")
    claim("locks 汇总与台账一致", len(defs), plan_locks,
          "测试文件 def test_ 计数 vs plan.per_bug.locks 求和")
    claim("锁清点件的 collected", locks_inv.get("collected"), len(defs),
          "fix_r3_locks_inventory.json:collected")

    claim("pytest", foot.get("pytest"), baselines["pytest"]["passed"],
          "fix_r3_baselines.json:pytest.passed")
    claim("suite", foot.get("suite"),
          f"{baselines['suite']['fields'].get('Passed')}/{baselines['suite']['fields'].get('Total')}",
          "fix_r3_baselines.json:suite")
    e2e = baselines["e2e"]["fields"]
    claim("e2e", foot.get("e2e"), f"{e2e.get('PASS')}/{e2e.get('PASS')}",
          "fix_r3_baselines.json:e2e.PASS（FAIL 见下）")
    claim("e2e FAIL/WARN/UNREG 全零", "0",
          f"{e2e.get('FAIL')}{e2e.get('WARN')}{e2e.get('UNREG/RUNFAIL')}".strip("0") or "0",
          "fix_r3_baselines.json:e2e.fields")
    claim("radius", foot.get("radius"), baselines["radius"]["count"],
          "fix_r3_baselines.json:radius.count")
    claim("radius 全部归属本单", 0, len(baselines["radius"]["unclaimed_by_this_lane"]),
          "fix_r3_baselines.json:radius.unclaimed_by_this_lane")

    bugs_in_footer = re.search(r"fixed=([^\s]+)", footer)
    listed = [x.split("(")[0] for x in (bugs_in_footer.group(1).split(",") if bugs_in_footer else [])]
    ledger_text = LEDGER.read_text(encoding="utf-8")
    fixed_sections = ledger_text.count(f"### FIXED(修复=已完成)")
    this_round_sections = len(re.findall(rf"### FIXED\(修复=已完成\)[^\n]*{re.escape(ROUND_TAG)}",
                                         ledger_text))
    claim("fixed= 清单条数 vs 页脚", len(listed), len(plan["per_bug"]),
          "页脚 fixed= vs fix_r3_plan.json:per_bug")
    claim("账本本轮 FIXED 段数", len(listed), this_round_sections,
          f"memory/bugs.md 含 {ROUND_TAG} 的 FIXED 段")
    claim("账本 FIXED 段与全部(修复=已完成)段不串轮", this_round_sections, fixed_sections,
          "上一轮（R2）没有『修复=已完成』段 ⇒ 两个数应相等")

    flips = re.search(r"flips=([^\s]+)", footer).group(1) if re.search(r"flips=([^\s]+)", footer) else ""
    flip_ids = sorted(x.split(":")[0] for x in flips.split(","))
    kept = re.search(r"kept_red=([^\s]+)", footer).group(1).split(",") if re.search(r"kept_red=([^\s]+)", footer) else []
    ev_flips = evidence.get("flips") or {}
    if not ev_flips:
        REFUSE.append("fix_r3_evidence.json:flips 是空的 ⇒ 反解不出任何翻转，检查作废")
    bad_shape = [cid for cid, rec in ev_flips.items() if "after_rc" not in rec]
    if bad_shape:
        REFUSE.append(f"flips 条目缺 after_rc（形状与预期不符）：{bad_shape}")
    recomputed_flip = sorted(cid for cid, rec in ev_flips.items() if rec.get("after_rc") == 1)
    recomputed_kept = sorted(cid for cid, rec in ev_flips.items() if rec.get("after_rc") == 0)
    claim("flips 清单", ",".join(flip_ids), ",".join(recomputed_flip),
          "fix_r3_evidence.json:flips[*].after_rc==1")
    claim("kept_red 清单", ",".join(sorted(kept)), ",".join(recomputed_kept),
          "fix_r3_evidence.json:flips[*].after_rc==0")

    runs = re.search(r"baselines_run=(\d+)", footer)
    present = sum(1 for f in ("fix_r3_baselines.json", "fix_r3_baselines_run1.json")
                  if (HERE / f).exists())
    claim("baselines_run", runs.group(1) if runs else "?", present,
          "fix_r3_baselines.json + fix_r3_baselines_run1.json 存在数")

    sec = text.split("## 六、本环自身缺陷", 1)
    if len(sec) != 2:
        REFUSE.append("报告缺《六、本环自身缺陷》段 ⇒ 无法反解缺陷计数")
    else:
        body = sec[1].split("## ", 1)[0]
        parts = re.split(r"操作[与和类]*[：:]", body)
        judge_items = len(re.findall(r"^\d+\. ", parts[0], flags=re.M))
        op_items = len(re.findall(r"^\d+\. ", parts[1], flags=re.M)) if len(parts) > 1 else -1
        jd = re.search(r"judge-defects=(\d+)", footer)
        od = re.search(r"op-defects=(\d+)", footer)
        claim("judge-defects", jd.group(1) if jd else "?", judge_items,
              "报告《六》段『判据与工具类』小节下的编号条数")
        claim("op-defects", od.group(1) if od else "?", op_items,
              "报告《六》段『操作』小节下的编号条数")


def part_b():
    root_close = art("close_r3_fix_root.out.json")
    text = REPORT.read_text(encoding="utf-8")
    section = text.split("## 被拒原文（逐字，一条不吞）", 1)
    if len(section) != 2:
        REFUSE.append("报告缺《被拒原文》段 ⇒ 无法逐字对表")
        return
    body = section[1].split("## ", 1)[0]
    rows = re.findall(r"^\|\s*`(\w+)`\s*\|\s*`(T[\w.]+)`\s*\|\s*(.+?)\s*\|\s*$",
                      body, flags=re.M)
    artifact = [(r["call"], r["task_id"], r["error"]) for r in root_close["refused"]]
    report_set = {(c, t, m.strip()) for c, t, m in rows}
    art_set = {(c, t, m.strip()) for c, t, m in artifact}
    missing = sorted(art_set - report_set)
    extra = sorted(report_set - art_set)
    if missing:
        REFUSE.append(f"[被拒对表] 判据件有而报告没引（吞条）：{missing}")
    if extra:
        REFUSE.append(f"[被拒对表] 报告有而判据件没有（伪造或改写）：{extra}")
    claim("被拒逐字对表（双向集合）", len(report_set), len(art_set),
          "close_r3_fix_root.out.json:refused vs 报告《被拒原文》表",
          ok=not missing and not extra and len(report_set) == len(art_set))
    return {"rows_in_report": len(rows), "rows_in_artifact": len(artifact),
            "missing": missing, "extra": extra}


def part_c():
    ledger_text = LEDGER.read_text(encoding="utf-8")
    entries = re.split(r"^(## BUG-\d+ .*)$", ledger_text, flags=re.M)
    reruns = []
    bug = None
    for chunk in entries:
        if chunk.startswith("## BUG-"):
            bug = chunk.split()[1]
            continue
        if bug is None or ROUND_TAG not in chunk:
            continue
        sec = chunk.split(f"### FIXED(修复=已完成)", 1)
        if len(sec) != 2:
            continue
        body = sec[1]
        cmd = re.search(r"复跑：`([^`]+)`", body)
        rcs = re.search(r"before rc=(\d+) → after rc=(\d+)", body)
        if not cmd or not rcs:
            REFUSE.append(f"[FIXED 复跑] {bug} 段缺『复跑』命令或缺 before/after rc ⇒ 段落不合规")
            continue
        proc = subprocess.run(cmd.group(1).split(), cwd=str(ROOT), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=600)
        expected = int(rcs.group(2))
        reruns.append({"bug": bug, "cmd": cmd.group(1), "before_rc": int(rcs.group(1)),
                       "after_rc_claimed": expected, "rc_now": proc.returncode,
                       "matches_claim": proc.returncode == expected,
                       "output_tail": ((proc.stdout or "") + (proc.stderr or ""))[-120:]})
    for rec in reruns:
        if not rec["matches_claim"]:
            REFUSE.append(f"[FIXED 复跑] {rec['bug']} 段声明 after rc={rec['after_rc_claimed']}，"
                          f"当场跑 {rec['cmd']} 得 rc={rec['rc_now']}")
    if len(reruns) != 6:
        REFUSE.append(f"[FIXED 复跑] 只复跑到 {len(reruns)} 段（应为 6 段）")
    return reruns


def main() -> int:
    part_a()
    refusal_table = part_b()
    reruns = part_c()
    doc = {
        "refuse": REFUSE,
        "counts": sum(1 for c in COUNTS if c["equal"]),
        "counts_total": len(COUNTS),
        "counts_all_equal": 1 if all(c["equal"] for c in COUNTS) and COUNTS else 0,
        "refusal_table": refusal_table,
        "repro_reruns": len(reruns),
        "repro_reruns_match_claim": sum(1 for r in reruns if r["matches_claim"]),
        "detail": COUNTS,
        "reruns_detail": reruns,
    }
    (HERE / "verify_r3_report_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "counts", "counts_total", "counts_all_equal",
                                          "repro_reruns", "repro_reruns_match_claim")},
                     ensure_ascii=False, indent=1))
    return 0 if not REFUSE else 1


if __name__ == "__main__":
    sys.exit(main())
