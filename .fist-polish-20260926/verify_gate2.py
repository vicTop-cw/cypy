#!/usr/bin/env python3
"""门禁② 的独立复算：报告 §五.12 的数字必须能从 **原始 pytest 日志** 重算出来。

verify_l4_report.py 校的是 L4 段落与本仓 §三 新鲜度表；这个脚本只管锁死对照那一节，且刻意不读
prove_lockins.py 的解析结果之外的任何东西：所有计数从 `lockproof_head.log` 的 `-rA` 状态行重新解析，
再与 `lockproof_head.json` 的行、与报告正文表格逐一对照。任何一处对不上就 RED。

自查（防「判据自己坏了」）：解析结果必须同时含 PASSED 与 FAILED 两种状态、且用例数 = 24；
只出现一种状态说明解析器没吃到东西，此时不许输出「全项通过」。
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.stdout.reconfigure(encoding="utf-8")

LOG = os.path.join(HERE, "lockproof_head.log")
# GATE2_JSON 只给违例对照用（control_gate2.py 拿被改坏的副本跑本脚本，证明这里真在比对而不是复述）
JS = os.environ.get("GATE2_JSON") or os.path.join(HERE, "lockproof_head.json")
RED_RE = re.compile(r"^-(\d+)")
STAT_RE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+)")
ROWS = []
reds = []


def chk(cond, what):
    ROWS.append((bool(cond), what))
    if not cond:
        reds.append(what)


log = open(LOG, encoding="utf-8", errors="replace").read()
js = json.load(open(JS, encoding="utf-8"))
REV = os.path.join(ROOT, "memory", "reviews")
mds = sorted(f for f in os.listdir(REV) if f.endswith(".md"))
chk(len(mds) == 1, f"memory/reviews 应只有 1 份报告，实得 {mds}")
text = open(os.path.join(REV, mds[0]), encoding="utf-8").read() if len(mds) == 1 else ""

# ---- 1) 从日志重算逐用例状态（不看 JSON 的 rows）
from_log = {}
for ln in log.splitlines():
    s = ln.strip()
    m = STAT_RE.match(s)
    if m and "::" in m.group(2):
        from_log[m.group(2).split("::")[-1]] = m.group(1)
chk(len(from_log) == js["collected"],
    f"日志解析出的用例数 {len(from_log)} == JSON 声明的 collected {js['collected']}")
sts = set(from_log.values())
chk("PASSED" in sts and "FAILED" in sts,
    f"日志里同时出现红与绿两种状态（实得 {sorted(sts)}）——只有一种说明解析器空转")
chk(sum(1 for v in from_log.values() if v == "FAILED") == 23
    and sum(1 for v in from_log.values() if v == "PASSED") == 1,
    "日志重算：23 FAILED / 1 PASSED")
chk(js["summary_line"] and "23 failed, 1 passed" in js["summary_line"],
    f"JSON 汇总行与日志一致（{js['summary_line']}）")

# ---- 2) 逐单聚合，与 JSON rows 对表
CTL, CONF = set(js["controls"]), set(js["confounds"])
agg = {}
for case, st in from_log.items():
    m = re.match(r"test_bug(\d+)_", case)
    if not m:
        continue
    bid = f"BUG-{int(m.group(1))}"
    role = "control" if case in CTL else "confound" if case in CONF else "lock"
    d = agg.setdefault(bid, {"cases": 0, "lock": 0, "lock_red": 0, "ctl_red": 0, "conf_red": 0})
    d["cases"] += 1
    red = st in ("FAILED", "ERROR")
    if role == "lock":
        d["lock"] += 1
        d["lock_red"] += int(red)
    elif role == "control":
        d["ctl_red"] += int(red)
    else:
        d["conf_red"] += int(red)
chk(len(agg) == 12, f"日志里覆盖 12 张单（实得 {len(agg)}）")
jr = {r["bug"]: r for r in js["rows"]}
chk(sorted(jr) == sorted(agg), "JSON rows 的单号集合与日志重算一致")
for bid in sorted(agg, key=lambda x: int(x.split("-")[1])):
    a, r = agg[bid], jr[bid]
    chk(a["cases"] == r["cases"] and a["lock"] == r["lock_cases"]
        and a["lock_red"] == r["red_on_head"] and a["ctl_red"] == len(r["controls_red"])
        and a["conf_red"] == len(r["confounded_red"]),
        f"{bid} 日志重算 {a} 与 JSON {r['cases']}/{r['lock_cases']}/{r['red_on_head']}"
        f"/{len(r['controls_red'])}/{len(r['confounded_red'])} 一致")
    chk(a["lock_red"] >= 1, f"{bid} 至少 1 条非对照非混因用例在 HEAD 上变红（门禁②）")
    chk(r["lock_case"] in from_log and from_log[r["lock_case"]] == "FAILED",
        f"{bid} 报告点名的锁死用例 {r['lock_case']} 在日志里确为 FAILED")

# ---- 3) 报告 §五.12 表格逐格对数
tbl = re.findall(r"^\| (BUG-\d+) \| (\d+) \| (\d+) \| (\d+) \| `([^`]+)` \|$", text, re.M)
chk(len(tbl) == 12, f"§五.12 表格 12 行（实得 {len(tbl)}）")
_key = lambda x: int(x.split("-")[1])
chk([t[0] for t in tbl] == sorted(agg, key=_key),
    "§五.12 覆盖的单号与日志一致（且按单号升序）")
for bid, cs, lk, rd, case in tbl:
    a = agg[bid]
    chk((cs, lk, rd) == (str(a["cases"]), str(a["lock"]), str(a["lock_red"])),
        f"§五.12 {bid} 三个数字（{cs}/{lk}/{rd}）等于日志重算")
    chk(from_log.get(case) == "FAILED",
        f"§五.12 {bid} 点名的 {case} 在日志里是红的")
    chk(case not in CTL and case not in CONF, f"§五.12 {bid} 没拿对照/混因用例冒充锁")

# ---- 4) 正文里的对照/混因/护栏叙述与实测吻合
chk(all(f"`{c}`" in text for c in CTL | CONF),
    "对照与混因用例名逐个出现在正文里（不许只写「有一项对照」）")
chk(f"`{js['head']}`" in text, f"正文写明对照基准 commit {js['head']}")
# control_gate2.py 实测出的坑：「正文里有这个数字」不是比对——把 56 改成 0 照样过，因为报告别处
# 本来就有「0 个」。改成从锚定句里抠出数字做等值比较，并回到 git/工作区把混因依据自己重算一遍。
m = re.search(r"不同的 `\.py` 必须 > 0（本轮实测 (\d+) 个）", text)
chk(m is not None and js["product_py_differing"] > 0
    and int(m.group(1)) == js["product_py_differing"],
    f"正文锚定句的不同 .py 数 == JSON 声明且 > 0"
    f"（正文={m.group(1) if m else '(抠不到)'} json={js['product_py_differing']}）")
sub = js["subtype_confound_evidence"]
HP, HS = ("cypyc/parser/parser.py", "cypyc/analyzer/scope_analyzer.py")
declared = [sub["head"][HP], sub["head"][HS], sub["worktree"][HP], sub["worktree"][HS]]


def _git_count(rev, path):
    p = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout.decode("utf-8", "replace").count("subtype")


recomputed = [(_git_count(js["head"], p),
               open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read().count("subtype"))
              for p in (HP, HS)]
flat = [recomputed[0][0], recomputed[1][0], recomputed[0][1], recomputed[1][1]]
chk(all(v is not None for v in flat) and flat == declared,
    f"混因依据独立重算（git show {js['head']} + 工作区实读）= {flat} == JSON 声明 {declared}")
m2 = re.search(r"`subtype` 出现\s*(\d+) 次、`cypyc/analyzer/scope_analyzer\.py` (\d+) 次，"
               r"工作区分别是\s*(\d+)/(\d+) 次", text)
chk(m2 is not None and [int(x) for x in m2.groups()] == declared,
    f"正文四个 subtype 计数 == JSON（正文={m2.groups() if m2 else '(抠不到)'} json={declared}）")
for lab, name in (("cypyc", js["module_paths"]["cypyc"]),
                  ("nogil", js["module_paths"]["nogil"])):
    chk("_lockproof_head" in name, f"身份探针：{lab} 确实从临时树加载（{name}）")
chk(os.path.isdir(os.path.join(HERE, "_lockproof_head")) is False,
    "临时树已删除，报告里没有指向一个已不存在的路径当证据（留的是 log/json）")

print()
for ok, what in ROWS:
    print(f"  {'OK ' if ok else 'RED'} {what}")
print(f"\nverify_gate2: {'全项通过' if not reds else 'RED ' + str(len(reds)) + ' 项: ' + str(reds)}")
sys.exit(0 if not reds else 1)
