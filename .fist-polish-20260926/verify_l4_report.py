#!/usr/bin/env python3
"""Independent audit of the L4 paragraph: report text vs ov_audit_and_fist_report.json vs raw logs.

Deliberately does not import gen_report.py — it re-measures from the artifacts the way
verify_report5.py re-measures the ledger, so the generator cannot vouch for itself.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.stdout.reconfigure(encoding="utf-8")

REV = os.path.join(ROOT, "memory", "reviews")
files = sorted(f for f in os.listdir(REV) if f.endswith(".md"))
l4 = json.load(open(os.path.join(HERE, "ov_audit_and_fist_report.json"), encoding="utf-8"))
a, r = l4["part1_audit"], l4["part2_fist_report"]

skip_base = open(os.path.join(HERE, "pytest_baseline.log"), encoding="utf-8",
                 errors="replace").read()
skip_final = open(os.path.join(HERE, "pytest_final_sweep6.log"), encoding="utf-8",
                  errors="replace").read()
SB = skip_base.count("skipped") + skip_base.count("xfail")
SF = skip_final.count("skipped") + skip_final.count("xfail")

reds = []


def chk(cond, msg):
    print(("  OK  " if cond else "  RED ") + msg)
    if not cond:
        reds.append(msg)


if len(files) != 1:
    print(f"[verify_l4] memory/reviews 应有且仅有 1 份报告，实得 {len(files)}: {files}")
    sys.exit(2)
text = open(os.path.join(REV, files[0]), encoding="utf-8").read()
print(f"report: memory/reviews/{files[0]}")

chk(a["tickets_total"] == 13, f"审计覆盖 13 张单（实得 {a['tickets_total']}）")
chk(a["audited"] == 12 and a["pass"] == 12, f"L4 审计 12/12 pass（实得 {a['pass']}/{a['audited']}）")
chk(a["control_negative"]["got"] == "fail", "负向对照必须 fail（硬门真能拦）")
chk(r["ledger_after"] == r["ledger_before"] + 1,
    f"FIST-Mbt 账本 +1（{r['ledger_before']}→{r['ledger_after']}）")
chk(r["publish_task"] is False, "FIST-Mbt 上报未发布任务（publish_task=False）")

for needle in [f"{a['pass']}/{a['audited']} 全部", str(sum(x["n_artifacts"] for x in a["rows"])),
               r["reply"]["bug_id"], str(r["ledger_before"]), str(r["ledger_after"])]:
    chk(needle in text, f"报告正文含实测值 {needle!r}")
chk(f"{SB} → {SF}" in text, f"报告正文的 skip/xfail 命中数等于日志实跑值（{SB} → {SF}）")
chk("l4-pass" in text, "报告正文引用了证据层 l4-pass")
chk("l4-hard-failed" in text, "报告正文引用了对照的 l4-hard-failed")
chk("invariant" in text, "报告正文点明了未知键仍被断言 invariant 这一危害")
chk("probe_output_validate3" in text, "报告正文留了推翻两条误报的探针指针")

# 附：③ 读码类别扫描的留痕（表格数字必须逐个等于产物里的实测命中数）
cat = json.load(open(os.path.join(HERE, "sweep4_classes.json"), encoding="utf-8"))
catb = json.load(open(os.path.join(HERE, "sweep4_classes_before_reclosure.json"), encoding="utf-8"))
CLASSES = ("A_mutable_default", "B_open_no_ctx", "C_subprocess_no_timeout",
           "D_lock_no_finally", "E_index_after_filter")
for c in CLASSES:
    la = [x["loc"] for x in cat[c]]
    lb = [x["loc"] for x in catb[c]]
    chk(la == lb, f"复跑与快照一致：{c}（{len(la)} vs {len(lb)} 处）")
    chk(f"| `{c}` |" in text and f"| {len(cat[c])} 处 |" in text, f"报告含 {c} 行且命中数={len(cat[c])}")
chk(f"{cat['files_scanned']} 文件" in text and f"{cat['lines_scanned']} 行" in text,
    f"报告正文扫描规模等于产物实测（{cat['files_scanned']} 文件 / {cat['lines_scanned']} 行）")
_pipes = [ln.count("|") for ln in text.splitlines() if ln.startswith("| `A_mutable")
          or ln.startswith("| `B_open") or ln.startswith("| `C_sub") or ln.startswith("| `D_lock")
          or ln.startswith("| `E_index")]
chk(len(_pipes) == 5 and set(_pipes) == {5}, f"类别表 5 行且每行 5 根竖线（实得 {len(_pipes)} 行 {set(_pipes)}）")

# 附：终态数字的新鲜度归因（报告说的"最新文件晚了多少秒"要与独立重算一致）
_log_ts = os.path.getmtime(os.path.join(HERE, "pytest_final_sweep6.log"))
_trees = ("cypyc", "cypy_bridge", "cypy_hook", "tests")
_newest = max((os.path.getmtime(os.path.join(dp, fn)), os.path.join(dp, fn))
              for t in _trees for dp, dn, fns in os.walk(os.path.join(ROOT, t))
              for fn in fns if fn.endswith(".py") and "__pycache__" not in dp)
_rel = os.path.relpath(_newest[1], ROOT).replace("\\", "/")
_lag = int(_log_ts - _newest[0])
chk(_newest[0] <= _log_ts, f"四棵树最新 .py 不晚于终态日志（最新={_rel}）")
chk(f"`{_rel}`" in text and f"早 {_lag} 秒" in text,
    f"报告正文的最新文件与滞后秒数等于独立重算（{_rel} / 早 {_lag} 秒）")
chk("## 三、基线前后对照" in text and text.index("新鲜度守卫扫了四棵树的") > text.index("## 三、基线前后对照"),
    "新鲜度段落落在 §三 之后（不是塞在别处）")

# 附：终态/基线证据 mtime 表——分钟数由本脚本独立重算，不接受生成器自报
_new_ts = max(os.path.getmtime(os.path.join(dp, fn))
              for t in ("cypyc", "cypy_bridge", "cypy_hook", "tests")
              for dp, dn, fns in os.walk(os.path.join(ROOT, t))
              for fn in fns if fn.endswith(".py") and "__pycache__" not in dp)
_gr = open(os.path.join(HERE, "gen_report.py"), encoding="utf-8").read()


def _declared(var):
    """从生成器源码里读出它**声明**要钉的证据集——审计器原本把 3+2 写死，生成器加了两行它就静默少审。"""
    m = re.search(var + r" = \[(.*?)\]\n", _gr, re.S)
    if not m:
        sys.exit(f"[verify_l4] gen_report.py 里找不到 {var} 声明")
    pairs = re.findall(r'\("([^"]+)", "([^"]+)"\)', m.group(1))
    return dict(pairs)


_TERM = _declared("TERMINAL_EVIDENCE")
_BASE = _declared("BASELINE_EVIDENCE")
if len(_TERM) < 3 or len(_BASE) < 2:
    sys.exit(f"[verify_l4] 生成器声明的证据集比预期小（终态 {len(_TERM)} / 基线 {len(_BASE)}）——"
             "先确认是真的删了还是正则没吃全")
for _lab, _name in _TERM.items():
    _ts = os.path.getmtime(os.path.join(HERE, _name))
    chk(_ts >= _new_ts and f"| {_lab} | `{_name}` | 晚 {int((_ts - _new_ts) / 60)} 分钟 | 有效 |" in text,
        f"终态证据行 {_name} 的分钟数等于独立重算")
for _lab, _name in _BASE.items():
    _ts = os.path.getmtime(os.path.join(HERE, _name))
    chk(_ts < _log_ts and f"| {_lab} | `{_name}` | 早 {int((_log_ts - _ts) / 60)} 分钟 | 作对照锚 |" in text,
        f"基线证据行 {_name} 早于终态且分钟数等于独立重算")
_ROWRE = re.compile(r"^\| (.+?) \| `([^`]+)` \| (晚|早) (\d+) 分钟 \| (.+?) \|$")
_frows = [(_ROWRE.match(ln).groups(), ln) for ln in text.splitlines() if _ROWRE.match(ln)]
chk(len(_frows) == len(_TERM) + len(_BASE),
    f"新鲜度表行数 == 生成器声明的终态 {len(_TERM)} + 基线 {len(_BASE)}（实得 {len(_frows)} 行）")
chk({ln.count("|") for _, ln in _frows} == {5}, f"新鲜度表每行 4 个单元格 = 5 根竖线（实得 {sorted({ln.count('|') for _, ln in _frows})}）")
chk(sorted(f"{lab}|{name}" for lab, name, *_x in [g for g, _ in _frows])
    == sorted(f"{lab}|{name}" for lab, name in list(_TERM.items()) + list(_BASE.items())),
    "新鲜度表的 (标签, 文件) 集合与生成器声明逐一对应，无多无少")
chk(len({name for _lab, name, *_x in [g for g, _ in _frows]}) == len(_frows),
    "新鲜度表里没有同一文件被钉两次凑数")

print(f"\nverify_l4: {'全项通过' if not reds else 'RED ' + str(len(reds)) + ' 项: ' + str(reds)}")
sys.exit(0 if not reds else 1)
