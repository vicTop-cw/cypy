#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Violation control for verify_report4.py's new ledger/refusal checks.

A green auditor proves nothing on its own: this script copies the whole evidence set into a
scratch tree, corrupts exactly one claim per variant, and requires the auditor to go RED *naming
that criterion*. Baseline (unmodified copy) must be GREEN, otherwise the harness is broken.

Note on scope: gen_report.py's pre-write guard (`_undisclosed`) is the same predicate as the
auditor's `每一条被服务端拒绝…` check, so variant `hide_refusal` covers both -- it proves the
comparison really detects a missing refusal text, not that it merely re-reads the report.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CTL = os.path.join(HERE, "_ctl_r4")
AUD = "verify_report4.py"
sys.stdout.reconfigure(encoding="utf-8")

REPORT = sorted(glob.glob(os.path.join(ROOT, "memory", "reviews", "*.md")))
BUGS = os.path.join(ROOT, "memory", "bugs.md")
if len(REPORT) != 1:
    sys.exit(f"需要恰 1 份终态报告才能做对照，实得 {REPORT}")

COPY_DRIVER = sorted(os.path.basename(p) for p in
                     (glob.glob(os.path.join(HERE, "intake_map*.json"))
                      + glob.glob(os.path.join(HERE, "close_fixes*.out.json")))) \
    + ["probe_ledger_final.json", "pytest_final_sweep5.log", AUD]
COPY_ROOT = {"memory/bugs.md": BUGS,
             "memory/reviews/report.md": REPORT[0],
             "tests/test_polish_20260926.py": os.path.join(ROOT, "tests",
                                                           "test_polish_20260926.py")}


def stage():
    if os.path.isdir(CTL):
        shutil.rmtree(CTL)
    os.makedirs(os.path.join(CTL, ".fist-polish-20260926"))
    os.makedirs(os.path.join(CTL, "memory", "reviews"))
    os.makedirs(os.path.join(CTL, "tests"))
    for name in COPY_DRIVER:
        shutil.copy2(os.path.join(HERE, name), os.path.join(CTL, ".fist-polish-20260926", name))
    for rel, src in COPY_ROOT.items():
        shutil.copy2(src, os.path.join(CTL, *rel.split("/")))


def rp(*parts):
    return os.path.join(CTL, ".fist-polish-20260926", *parts)


def rd(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def wr(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def edit_report(fn):
    p = os.path.join(CTL, "memory", "reviews", "report.md")
    wr(p, fn(rd(p)))


def edit_json(name, fn):
    p = rp(name)
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    wr(p, json.dumps(fn(data), ensure_ascii=False))


def hide_refusal(text):
    out = [ln for ln in text.splitlines(True) if "对根任务的拒绝" not in ln]
    if len(out) == len(text.splitlines(True)):
        raise AssertionError("报告里没有那条拒绝披露行，对照无从做起")
    return "".join(out)


def fake_closed(d):
    for t in d["tickets"]:
        if t["bug"] == "BUG-13":
            t["status"] = "已完成"
    d["tickets_done"] = len([t for t in d["tickets"] if t["status"] == "已完成"])
    return d


def swap_marker(text):
    def tr(ln):
        if ln.startswith("| BUG-13 |"):
            return ln.replace("入账未修", "已 verify")
        if ln.startswith("| BUG-1 |"):
            return ln.rstrip("\n") + "（入账未修）\n"
        return ln
    return "".join(tr(ln) for ln in text.splitlines(True))


def poison_verify(d):
    for e in d:
        if e["tag"] == "BUG-1:verify":
            e["result"] = dict(e["result"], __error__={"code": -32000,
                                                       "message": "对照注入的拒绝"})
            return d
    raise AssertionError("close_fixes.out.json 里没有 BUG-1:verify")


VARIANTS = [
    ("baseline_unchanged", lambda: None, None, "基线副本必须 rc=0"),
    ("hide_refusal", lambda: edit_report(hide_refusal), ("每一条被服务端拒绝的原始文案",),
     "删掉披露行 → 必须判「拒绝文案没逐字进正文」"),
    ("fake_closed", lambda: edit_json("probe_ledger_final.json", fake_closed),
    ("### FIXED",), "把未修的单改成已完成 → 必须与 bugs.md 的 FIXED 段对不上"),
    ("drop_map5", lambda: os.remove(rp("intake_map5.json")),
     ("bugs.md 条目集合", "一一对应"), "少读一份入账映射 → 集合必须不齐"),
    ("swap_marker", lambda: edit_report(swap_marker), ("闭环表标「入账未修」",),
     "把「入账未修」挪到已闭环的单上 → 集合必须不一致"),
    ("poison_verify", lambda: edit_json("close_fixes.out.json", poison_verify),
     ("四步生命周期",), "生命周期回复里注入拒绝 → 必须被点名"),
]

rows, broke = [], []
try:
  for name, mutate, needles, why in VARIANTS:
    stage()
    if mutate:
        mutate()
    p = subprocess.run([sys.executable, rp(AUD)], cwd=CTL, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    blob = (p.stdout or "") + (p.stderr or "")
    reds = [ln.strip()[5:].strip() for ln in blob.splitlines()
            if ln.strip().startswith("FAIL ")]
    if name == "baseline_unchanged":
        hit = p.returncode == 0
        rows.append({"variant": name, "rc": p.returncode, "caught": hit,
                     "reds": reds[:6], "expect": why})
        if not hit:
            broke.append(f"{name}: 基线副本 rc={p.returncode}，对照树本身不成立（{reds[:3]}）")
        continue
    if p.returncode == 0:
        rows.append({"variant": name, "rc": 0, "caught": False, "reds": [], "expect": why})
        broke.append(name)
        continue
    matched = [n for n in needles if any(n in r for r in reds)]
    rows.append({"variant": name, "rc": p.returncode, "caught": bool(matched),
                 "matched": matched, "reds": reds[:8], "expect": why})
    if not matched:
        broke.append(f"{name}: 红了但没有命中指名判据，实际 RED={reds[:4]}")
finally:
    shutil.rmtree(CTL, ignore_errors=True)

out = {"report": os.path.basename(REPORT[0]), "variants": len(VARIANTS),
       "baseline_ok": rows[0]["caught"], "caught": sum(1 for r in rows if r["caught"]),
       "missed": broke, "rows": rows}
with open(os.path.join(HERE, "control_report4.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
for r in rows:
    print(f"{r['variant']:<20} rc={r['rc']} {'CAUGHT' if r['caught'] else 'MISSED'} "
          f"{r.get('matched', r.get('reds', [])[:1])}")
print(f"\n违例对照 {len(VARIANTS) - 1} 种（另加基线）；未抓住：{broke or '无'}")
sys.exit(1 if broke else 0)
