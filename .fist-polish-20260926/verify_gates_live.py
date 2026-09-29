#!/usr/bin/env python3
"""门禁③④ 的**现场**复算：不复用任何历史快照的结论，重新扫一遍盘、重新收集一遍用例，
再与基线、与报告成品逐项对账。

为什么单独要这一份：§五 Step 3.1 要求「全单 verify 后复扫三路」，而报告里的收敛表与三向对照
都是**当时那次**扫描/那次成品的快照。快照会被后来的编辑悄悄作废（产品码又被人动过、报告表格
改了字、回归用例改了名），只有现场重跑才能证明「现在这棵树仍然满足门禁③④」。

自查（防判据自己饿死）：解析到的 bug 条目数、报告表行数、收集到的用例数、扫描类别数都必须在
预期下界之上，否则直接 RED —— 空集合让 `all()` 恒真。
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.stdout.reconfigure(encoding="utf-8")
BUGS = os.path.join(ROOT, "memory", "bugs.md")
TESTS = os.path.join(ROOT, "tests", "test_polish_20260926.py")
REV = os.path.join(ROOT, "memory", "reviews")
UNFIXED = {13}          # 入账未修的单：不占用门禁②，也不许有回归条目
CATS = 11               # marker_scan.py 的类别数


def load(name):
    return json.load(open(os.path.join(HERE, name), encoding="utf-8"))


ROWS = []
reds = []


def chk(cond, what):
    ROWS.append((bool(cond), what))
    if not cond:
        reds.append(what)


mds = sorted(f for f in os.listdir(REV) if f.endswith(".md"))
chk(len(mds) == 1, f"memory/reviews 只有 1 份报告（实得 {mds}）")
report = open(os.path.join(REV, mds[0]), encoding="utf-8").read() if len(mds) == 1 else ""

# ---------- 1) 现场重跑标记盘点（与基线同一份脚本，口径不另立） ----------
live_name = "markers_rescan_live.json"
p = subprocess.run([sys.executable, os.path.join(HERE, "marker_scan.py"),
                    ".fist-polish-20260926/" + live_name],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
chk(p.returncode == 0, f"现场复扫退出码 0（原样报错：{(p.stderr or '')[-200:]}）")
live = load(live_name)
base = load("markers_baseline.json")
snap = load("markers_after_sweep4.json")
chk(len(live["counts"]) == CATS, f"复扫类别数 {len(live['counts'])} == 脚本定义的 {CATS} 类")
chk(live["git_head"] == base["git_head"] == snap["git_head"],
    f"三次扫描同一基准 commit：live {live['git_head']} / base {base['git_head']} / snap {snap['git_head']}")
chk(live["files_scanned"] == base["files_scanned"] == 56,
    f"扫描覆盖面仍是三包 56 文件（live {live['files_scanned']} base {base['files_scanned']}）")
grew = {k: (base["counts"][k], live["counts"][k]) for k in live["counts"]
        if live["counts"][k] > base["counts"][k]}
chk(not grew, f"门禁③「新增为零」：无任何类别计数超过基线（违例 {grew}）")
zeroed = [k for k in ("TODO", "FIXME", "HACK", "XXX", "type_ignore") if live["counts"][k] != 0]
chk(not zeroed, f"标记类在现扫仍为 0（违例 {zeroed}）")
chk(live["counts"] == snap["counts"],
    f"现扫逐项等于报告登记的终态（差异 "
    f"{ {k: (snap['counts'][k], live['counts'][k]) for k in live['counts'] if snap['counts'][k] != live['counts'][k]} }）")
chk(live["taken_at_utc"] > snap["taken_at_utc"],
    f"现扫时间戳晚于终态快照（{snap['taken_at_utc']} → {live['taken_at_utc']}）")
for cat, old, new in (("bare_except", 2, 0), ("except_swallowed", 20, 3), ("broad_except", 46, 45)):
    chk(base["counts"][cat] == old and live["counts"][cat] == new,
        f"报告正文的 {cat} {old}→{new} 与基线/现扫一致（实测 {base['counts'][cat]}→{live['counts'][cat]}）")

# ---------- 2) 门禁④ 三向对照：bugs.md ↔ 报告表 ↔ 真实收集项 ----------
booked = {int(m) for m in re.findall(r"^## BUG-(\d+) ", open(BUGS, encoding="utf-8").read(), re.M)}
chk(len(booked) == 13, f"bugs.md 解析到 13 条确诊条目（实得 {sorted(booked)}）")
txt = open(BUGS, encoding="utf-8").read()
fixed = {int(n) for n in re.findall(r"(?m)^## BUG-(\d+) [^\n]*\n(?:(?!^## BUG-).)*?^### FIXED\(verify=已完成\)",
                                    txt, re.S | re.M)}
chk(len(fixed) == 13 - len(UNFIXED),
    f"账本里带 FIXED(verify=已完成) 追加段的恰为 12 条（实得 {len(fixed)}）")
chk(fixed == booked - UNFIXED, f"已闭环集合 == 入账集合去掉入账未修单（差 {fixed ^ (booked - UNFIXED)}）")

rows = re.findall(r"(?m)^\| (BUG-(\d+)) \| [^\n]*T0r[^\n]*$", report)
chk(len(rows) == 13, f"报告 §二 闭环表 13 行（实得 {len(rows)}）")
chk({int(r[1]) for r in rows} == booked, "报告表的 bug id 与 bugs.md 集合相等（双向）")

col = subprocess.run([sys.executable, "-m", "pytest", TESTS, "--collect-only", "-q",
                      "-p", "no:cacheprovider"],
                     cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
out = (col.stdout or "") + (col.stderr or "")
# 本仓 pyproject 的 addopts 强制树形输出，`--collect-only -q` 不给 node id，只给
# `<Function test_bugN_...>` ⇒ 按树形解析，并与它自己的汇总行交叉核对（两个来源不一致即判据坏）。
ids = re.findall(r"<Function (test_bug\d+_[A-Za-z0-9_\[\].-]+)>", out)
summ = re.findall(r"(\d+) tests? collected", out)
chk(len(ids) == 24 and len(summ) == 1 and int(summ[0]) == len(ids),
    f"pytest 现场收集：树形解析 {len(ids)} 条 == 汇总行 {summ} 条（rc={col.returncode}）")
by_bug = {}
for i in ids:
    m = re.match(r"test_bug(\d+)_", i)
    if m:
        by_bug.setdefault(int(m.group(1)), []).append(i)
chk(sum(len(v) for v in by_bug.values()) == 24, f"24 条全部按 test_bugN_ 归单（否则有游离用例）")
lp = load("lockproof_head.json")
per_lp = {int(r["bug"].split("-")[1]): r["cases"] for r in lp["rows"]}
chk({k: len(v) for k, v in by_bug.items()} == per_lp,
    f"现场收集逐单用例数 == 门禁② 锁死对照登记的用例数（{ {k: len(v) for k, v in by_bug.items()} } vs {per_lp}）")
for bid_s, bid in rows:
    n = int(bid)
    row = next(ln for ln in report.splitlines() if ln.startswith(f"| {bid_s} |") and "T0r" in ln)
    names = set(re.findall(r"test_bug\d+_[A-Za-z0-9_]+", row))
    bases = {i.split("[")[0] for i in ids}
    mults = [int(x) for x in re.findall(r"×(\d+)", row)]
    chk(all(re.match(r"test_bug%d_" % n, nm) for nm in names),
        f"{bid_s} 表里点名的用例确属该单（点名 {sorted(names)}）")
    chk(all(nm in bases for nm in names),
        f"{bid_s} 点名的用例真实存在于收集结果：{sorted(names - bases)} 不在")
    covered = sum(mults) if mults else len(names)
    if n in UNFIXED:
        chk("入账未修" in row and not names,
            f"{bid_s} 标记为入账未修且无回归条目（原样：{row[-70:]}）")
    else:
        chk(covered == len(by_bug.get(n, [])) and len(by_bug.get(n, [])) >= 1,
            f"{bid_s} 回归条目覆盖该单全部 {len(by_bug.get(n, []))} 条收集项（表内计 {covered}）")
    if n not in UNFIXED:
        chk("verify=已完成" in row, f"{bid_s} 表内状态为 verify=已完成")

# ---------- 3) 账本引用的路径必须仍然在树上（活证据） ----------
paths = set(re.findall(r"`((?:cypyc|cypy_bridge|cypy_hook)/[A-Za-z0-9_/]+\.py)", txt))
pkgs = {p.split("/")[0] for p in paths}
missing = {p_ for p_ in paths if not os.path.isfile(os.path.join(ROOT, p_.replace("/", os.sep)))}
chk(pkgs == {"cypyc", "cypy_bridge", "cypy_hook"},
    f"账本引用的产品码路径覆盖全部三包（实得 {sorted(pkgs)}，共 {len(paths)} 个文件）")
chk(not missing, f"账本引用的产品码路径全部仍在树上（缺失 {sorted(missing)}）")

print()
for ok, what in ROWS:
    print(f"  {'OK ' if ok else 'RED'} {what}")
print(f"\nverify_gates_live: {'全项通过' if not reds else 'RED ' + str(len(reds)) + ' 项: ' + str(reds)}")
sys.exit(0 if not reds else 1)
