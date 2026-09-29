#!/usr/bin/env python3
"""Post-generation auditor for the fifth-pass report.  Reads only artifacts, never the chat.

Exits non-zero with a reason if the generated markdown disagrees with any source of truth.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.stdout.reconfigure(encoding="utf-8")
FAILS = []


def art(name):
    with open(os.path.join(HERE, name), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


revs = sorted(glob.glob(os.path.join(ROOT, "memory", "reviews", "*.md")))
check(len(revs) == 1, f"memory/reviews 下应有且只有 1 份报告，实测 {[os.path.basename(p) for p in revs]}")
if not revs:
    print("FAIL:", *FAILS, sep="\n  ")
    sys.exit(1)
text = open(revs[0], encoding="utf-8").read()
rel = os.path.relpath(revs[0], ROOT).replace("\\", "/")

# 1. no unrendered placeholder left behind
leftovers = re.findall(r"\{[A-Za-z_][A-Za-z_0-9]*(?:\[|\.get\(|\})", text)
check(not leftovers, f"报告里还有未渲染的占位符：{leftovers[:5]}")

# 2. the terminal pytest line, verbatim, and the sweep5 line as the previous snapshot
def tally(name):
    for ln in reversed([l.strip() for l in art(name).splitlines() if l.strip()]):
        if re.search(r"\b\d+ (failed|passed|error)", ln):
            return ln
    return ""


t6, t5 = tally("pytest_final_sweep6.log"), tally("pytest_final_sweep5.log")
check(bool(t6), "sweep6 日志没有汇总行（还没跑完？）")
check(t6 in text, f"报告里没有终态末行原文：{t6!r}")
check(t5 in text, f"报告里没有把 sweep5 作为上一快照列出：{t5!r}")

# 3. the fifth pass must be visible in the report, with its evidence names
for tok in ("BUG-13", "六.8", "TestDigestCost", "intake_map5.json", "meas_digest_gc.out.txt",
            "pytest_final_sweep6.log", "patch_gen_report5"):
    check(tok in text, f"报告缺第五遍的关键落点 {tok}")

# 4. gate ① conclusion must track the real red count
n_fail = int(re.search(r"(\d+) failed", t6 or "0 failed").group(1))
check(("不绿" in text) == (n_fail > 0),
      f"门禁① 的结论与实测红条数不符：red={n_fail}，文里有「不绿」= {'不绿' in text}")

# 5. ledger <-> report pairing (bug id, task id) over all five intakes
rows = []
for name in ("intake_map.json", "intake_map2.json", "intake_map3.json", "intake_map4.json",
             "intake_map5.json"):
    rows += load(name)["mapping"]
for r in rows:
    bid, tid = r["bug_id"], r["task_id"]
    check(bool(bid) and bool(tid), f"intake 行缺 id：{r}")
    if bid and tid:
        hit = [ln for ln in text.splitlines() if ln.startswith(f"| {bid} ") and tid in ln]
        check(len(hit) == 1, f"{bid}↔{tid} 在 §二 表里应当恰好一行，实测 {len(hit)}")

# 6. read-only DB audit agrees: 12 done + exactly BUG-13 open, root archived
db = load("probe_ledger_final.json")
check(db["tickets_total"] == len(rows),
      f"库里修复单 {db['tickets_total']} != 入账 mapping {len(rows)}")
opens = [t for t in db["tickets"] if t["status"] != "已完成"]
check(db["tickets_done"] == len(rows) - 1 and len(opens) == 1 and opens[0]["bug"] == "BUG-13",
      f"库内终态应为 {len(rows)-1} 已完成 + 唯一在途 BUG-13，实测 done={db['tickets_done']} 在途={opens}")
check(db["root"].get("status") == "已归档", f"根任务 T0 状态 {db['root'].get('status')}")
check(f"BUG-13→`{opens[0]['id']}`" in text or (opens and opens[0]["id"] in text),
      "报告没点出在途单的 task id")

# 7. every fixed ticket really reached 已完成 in the call logs, and no step errored
log = []
for name in ("close_fixes.out.json", "close_fixes2.out.json", "close_fixes3.out.json",
             "close_fixes4.out.json"):
    log += load(name)
# the root T0 is archived and the diagnostic-archive probes were meant to fail -> their
# __error__ replies are recorded evidence, not a swallowed failure
NEG_PREFIX = ("T0:", "diagnostic-archive:")
errs = [e["tag"] for e in log
        if not e["tag"].startswith(NEG_PREFIX) and isinstance(e["result"], dict)
        and e["result"].get("__error__")]
check(not errs, f"修复单收尾调用有报错却被当成完成：{errs}")
verified = {e["tag"].split(":")[0] for e in log
            if re.fullmatch(r"BUG-\d+:verify", e["tag"]) and isinstance(e["result"], dict)
            and e["result"].get("status") == "已完成"}
fixed = {r["bug_id"] for r in rows if r["bug_id"] != "BUG-13"}
check(fixed == verified, f"逐单终态 已完成 的集合与已修集合不一致：缺 {sorted(fixed - verified)}，"
                        f"多 {sorted(verified - fixed)}")

# 8. the cited regression-case count equals the real number of test functions
src = open(os.path.join(ROOT, "tests", "test_polish_20260926.py"), encoding="utf-8").read()
n_def = len(re.findall(r"^\s*def test_", src, re.M))
m = re.search(r"本轮收集 (\d+) 条用例", text)
n_rep = int(m.group(1)) if m else -1
import subprocess
col = subprocess.run([sys.executable, "-m", "pytest", "tests/test_polish_20260926.py",
                      "--collect-only", "-q", "-p", "no:cacheprovider"],
                     cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                     errors="replace")
n_col = len([l for l in (col.stdout or "").splitlines() if ".py::" in l])
m_col = re.search(r"(\d+) tests? collected", col.stdout or "")
n_col = int(m_col.group(1)) if m_col else n_col
check(n_rep == n_col and n_col >= n_def,
      f"报告写的回归用例数 {n_rep} != collect-only 实测 {n_col}"
      f"（def test_ 数 {n_def}；pytest 原文末 200 字：{(col.stdout or '')[-200:]!r}）")

# 9. do not claim a single red when the terminal log has two, and vice versa
reds = [l.strip() for l in art("pytest_final_sweep6.log").splitlines() if l.startswith("FAILED")]
check(("唯一红" not in text) or len(reds) == 1,
      f"终态红条 {len(reds)} 条，报告仍写「唯一红」")
for r in reds:
    check(r in text, f"红条 {r[:60]}… 没在报告里点名")

# 10. bugs.md 增量留档：已闭环条目各带一段 FIXED 段，BUG-13 不带；报告点名的 test_bug* 必须真实存在
led = open(os.path.join(ROOT, "memory", "bugs.md"), encoding="utf-8").read()
pat = re.compile(r"(?m)^(## BUG-\d+ \[[^\]]*\] \[[a-z]+\] OPEN)\n"
                 r"(.*?)(?=^## BUG-\d+ |\Z)", re.S)
entries = [(h.split()[1], h, b) for h, b in pat.findall(led)]
check(len(entries) == 13, f"账本条目数 {len(entries)} != 13（或标题行 OPEN 形态被改写）")
tid_of = {t["bug"]: t["id"] for t in db["tickets"]}
for bid, head, body in entries:
    want = bid in fixed
    check(("### FIXED(" in body) == want,
          f"{bid} 的 FIXED 段应为 {want}，实测 {not want}")
    if want:
        check(f"`{tid_of[bid]}`" in body and "已完成" in body,
              f"{bid} 的 FIXED 段没点名 {tid_of[bid]}/已完成")
check("### FIXED(verify=已完成)" in text, "报告没提账本侧的 FIXED 追加段")
phantom = sorted({t for t in re.findall(r"\btest_bug\w+", text)
                  if t not in set(re.findall(r"(?m)^\s*def (test_\w+)", src))})
check(not phantom, f"报告点名的 test_bug* 用例在回归文件里不存在（截断/臆造）：{phantom}")

print(f"report: {rel}")
print(f"terminal: {t6}")
print(f"reds: {len(reds)}  tickets: {db['tickets_done']}/{db['tickets_total']}  root: {db['root'].get('status')}")
if FAILS:
    print("FAIL:", *("  - " + f for f in FAILS), sep="\n")
    sys.exit(1)
print("verify_report5: 全项通过")
