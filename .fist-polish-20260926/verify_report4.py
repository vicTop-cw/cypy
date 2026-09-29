#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit the freshly generated terminal report against the artifacts it cites.

Run AFTER gen_report.py. This does not restate any number from memory: every value is
re-read from the report text or from a driver artifact, and any disagreement exits non-zero
with the offending text, so a report that drifted from its evidence cannot be handed over.
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, ".fist-polish-20260926")
REVIEWS = os.path.join(ROOT, "memory", "reviews")

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


reports = sorted(glob.glob(os.path.join(REVIEWS, "*.md")))
check(len(reports) == 1, f"memory/reviews/ 只应有一份终态报告，实得 {len(reports)}: "
      f"{[os.path.basename(p) for p in reports]}")
if not reports:
    sys.exit(1)
text = open(reports[0], encoding="utf-8").read()
print(f"report = memory/reviews/{os.path.basename(reports[0])} ({len(text)} chars)")

stray = re.findall(r"\{[a-z_]+(?:\[[^\]]*\])?(?:\.\w+)*\}", text)
check(not stray, f"报告里不许有未渲染的模板占位符，实得 {sorted(set(stray))[:6]}")

m = re.search(r"collected (\d+) items", text)
check(bool(m), "报告里要能读到终态收集数")
sweep5 = open(os.path.join(HERE, "pytest_final_sweep5.log"), encoding="utf-8",
              errors="replace").read()
final_line = [ln for ln in sweep5.splitlines() if re.search(r"\d+ (failed|passed)", ln)][-1].strip("=")
check(final_line in text, f"终态 pytest 末行要逐字出现在报告里：{final_line!r}")
for tok in ("intake4", "close_fixes4", "nogil.py", "BUG-12", "T0r17", "pytest_fourth_sweep_red",
            "pytest_switchoff_bug12", "markers_after_sweep4", "test_suite_after_sweep4"):
    check(tok in text, f"报告缺少第四遍要素 {tok!r}")
for stale in ("markers_after_sweep3.json`（同脚本", "误报 2 条", "共跑过 5 次",
              "pytest_final_sweep4.log` 末行原文"):
    check(stale not in text, f"报告仍留着第三遍口径 {stale!r}")

map_files = sorted(glob.glob(os.path.join(HERE, "intake_map*.json")))
check(len(map_files) >= 1, "驱动目录里要有 intake_map*.json，实得 0 份")
mapping = []
for f in map_files:
    mapping += json.load(open(f, encoding="utf-8"))["mapping"]
bugs_in = [r["bug_id"] for r in mapping]
check(len(bugs_in) == len(set(bugs_in)),
      f"入账映射不许把同一个 bug 登记两次：{sorted(bugs_in)}")
tids = [r["task_id"] for r in mapping]
check(all(tids), f"每单都要有自动发布的任务 id，实得 {tids}")
for r in mapping:
    check(f"{r['bug_id']}" in text and str(r["task_id"]) in text,
          f"闭环表要同时含 {r['bug_id']} 与 {r['task_id']}")
trows = re.findall(r"(?m)^(\| BUG-\d+ \| [^\n]*T0r\d+[^\n]*$)", text)
bug_of = lambda ln: ln.split("|")[1].strip()
check(sorted(map(bug_of, trows)) == sorted(bugs_in),
      f"闭环表逐单一行且仅一行：表内 {sorted(map(bug_of, trows))} vs 入账 {sorted(bugs_in)}")

ledger = json.load(open(os.path.join(HERE, "probe_ledger_final.json"), encoding="utf-8"))
tk = {t["bug"]: t for t in ledger["tickets"]}
check(len(tk) == ledger["tickets_total"] == len(bugs_in),
      f"只读查库要与入账映射一一对应：逐行 {len(tk)}/声明 {ledger['tickets_total']} "
      f"vs 映射 {len(bugs_in)}，差异 {sorted(set(tk) ^ set(bugs_in))}")
pair_bad = sorted(b for b in set(tk) & set(bugs_in)
                  if tk[b]["task_id"] != next(r["task_id"] for r in mapping if r["bug_id"] == b))
check(not pair_bad, f"bug↔task_id 在库行与入账映射之间不一致：{pair_bad}")
done = sorted(b for b, t in tk.items() if t["status"] == "已完成")
open_t = sorted(b for b, t in tk.items() if t["status"] != "已完成")
check(ledger["tickets_done"] == len(done),
      f"tickets_done={ledger['tickets_done']} 要等于逐行数出的 已完成 {len(done)} 张")
check(len(open_t) <= 3,
      f"转结未修的单最多 3 张（再多就不是「刻意留开」而是没收口）：{open_t}")
bugs_md = open(os.path.join(ROOT, "memory", "bugs.md"), encoding="utf-8").read()
parts = re.split(r"(?m)^## (BUG-\d+)\b", bugs_md)
entries = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
check(sorted(entries) == sorted(bugs_in),
      f"bugs.md 条目集合要与入账映射同集合：{sorted(entries)} vs {sorted(bugs_in)}")
fixed = sorted(b for b, bd in entries.items() if "### FIXED(" in bd)
check(fixed == done,
      f"bugs.md 里带 ### FIXED 段的条目要等于库里 已完成 的单，差异 "
      f"{sorted(set(fixed) ^ set(done))}")
undone = sorted(bug_of(ln) for ln in trows if "入账未修" in ln)
check(undone == open_t,
      f"闭环表标「入账未修」的单要等于库里非 已完成 的单（{undone} vs {open_t}）")
close = []
for f in sorted(glob.glob(os.path.join(HERE, "close_fixes*.out.json"))):
    close += json.load(open(f, encoding="utf-8"))
verified = {e["tag"].split(":")[0] for e in close
            if e["tag"].endswith(":verify") and isinstance(e["result"], dict)
            and e["result"].get("status") == "已完成"}
check(set(done) <= verified,
      f"每张 已完成 的单都要有 verify→已完成 的原始回复，缺 {sorted(set(done) - verified)}")
check(not (set(open_t) & verified),
      f"库里未完成的单不许有 verify→已完成 回复（那是伪造闭环）：{sorted(set(open_t) & verified)}")

test_src = open(os.path.join(ROOT, "tests", "test_polish_20260926.py"), encoding="utf-8").read()
cases = len(re.findall(r"^def test_", test_src, re.M))
check(re.search(rf"{cases} 条|{cases} passed", text) is not None,
      f"回归用例数要与测试文件一致（实得 {cases} 条）")
for r in mapping:
    bug = r["bug_id"]
    pat = rf"test_{bug.lower().replace('-', '')}_"
    if re.search(pat, test_src):
        check(re.search(pat, text) is not None,
              f"{bug} 的闭环表行里要写出 {bug} 的回归测试名（测试文件里有该前缀的用例）")

errs = [(e["tag"], e["result"]["__error__"]) for e in close
        if isinstance(e["result"], dict) and e["result"].get("__error__")]
bad_bug = [t for t, _ in errs if re.match(r"BUG-\d+:(claim|execute|submit|verify)$", t)]
check(not bad_bug, f"修复单的四步生命周期不许带 __error__：{bad_bug}")
hid = [f"{t}：{e.get('message') or 'code=' + str(e.get('code'))}" for t, e in errs
       if not (e.get("message") and e["message"] in text)]
check(not hid, f"每一条被服务端拒绝的原始文案都要逐字出现在报告里（红线「失败原样上报」），"
      f"缺 {hid}")
rc = ledger["root"].get("status")
check(rc == "已归档", f"根任务终态应为 已归档，实得 {rc!r}")
n_failed = int(re.search(r"(\d+) failed", final_line).group(1)) if re.search(r"(\d+) failed",
                                                                            final_line) else 0
check(("不绿" in text) == (n_failed > 0),
      f"门禁①的绿/不绿结论要与终态日志同向（日志红条数 {n_failed}，报告写「不绿」={'不绿' in text}）")

print("\n".join(["", f"checks failed: {len(fails)}"]))
sys.exit(1 if fails else 0)
