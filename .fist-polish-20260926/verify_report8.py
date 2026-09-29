#!/usr/bin/env python3
"""Independent audit of the final pass-7/8 report -- recomputes claims from raw evidence.

The generator that writes the report is not the authority on whether the report is true: this
script re-derives every headline number from the evidence files themselves (pytest log, sqlite,
bugs.md, lockproof/golden JSONs) and compares against what the report actually says. It also
checks the two things a green generator cannot see: whether the report points at files that exist,
and whether the ledger's own text obeys the path-safety rule (relative to the Cypy root).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.stdout.reconfigure(encoding="utf-8")
REVIEWS = ROOT / "memory" / "reviews"

problems, checked = [], 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checked
    checked += 1
    print(f"{'ok  ' if ok else 'RED '} {label}{'' if ok else '  <- ' + detail}")
    if not ok:
        problems.append(label)


def main() -> int:
    reports = sorted(REVIEWS.glob("*.md"))
    if not reports:
        print("REFUSE: memory/reviews/ 下没有报告")
        return 2
    rep = reports[-1]
    text = rep.read_text(encoding="utf-8")
    print(f"auditing {rep.relative_to(ROOT)}  ({len(text)} chars, newest of {len(reports)})")

    sweep = (HERE / "pytest_final_sweep11.log").read_text(encoding="utf-8", errors="replace")
    tail = sweep.strip().splitlines()[-1]
    passed = int(re.search(r"(\d+) passed", tail).group(1))
    failed = int((re.search(r"(\d+) failed", tail) or [None, "0"])[1]) if "failed" in tail else 0
    errors = int((re.search(r"(\d+) error", tail) or [None, "0"])[1]) if "error" in tail else 0
    check("终态全量 0 failed / 0 error", failed == 0 and errors == 0, tail)
    check(f"报告写了这次全量的通过数 {passed}", f"{passed} passed" in text, tail)
    col = re.search(r"collected (\d+) items", sweep)
    if col:
        check("报告里的收集数与 pytest 头部一致", f"收集 {col.group(1)}" in text, col.group(0))

    bugs = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8").splitlines()
    titles = [ln for ln in bugs if re.match(r"^## BUG-\d+ ", ln)]
    fixed = sum(1 for ln in bugs if ln.startswith("### FIXED(verify=已完成)"))
    check(f"账本条目数 {len(titles)} 出现在报告里", f"{len(titles)} 条" in text)
    check(f"账本 FIXED 段数 {fixed} 出现在报告里", f"{fixed} 段" in text)

    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    st = dict(db.execute("select id, status from tasks where ns='bugs'"))
    db.close()
    for bug, tid in (("BUG-13", "T0r18"), ("BUG-14", "T0r19"), ("BUG-32", "T0r37"),
                     ("BUG-30", "T0r35"), ("BUG-31", "T0r36")):
        want = "已完成" if bug in ("BUG-13", "BUG-14", "BUG-32") else "待领取"
        check(f"{bug}/{tid} 库内状态是 {want}", st.get(tid) == want, str(st.get(tid)))
        check(f"报告里点名了 {tid}", tid in text)

    lock = json.loads((HERE / "lockproof_pass7.json").read_text(encoding="utf-8"))
    reds = {r["bug"]: r["red_on_prefix_code"] for r in lock["rows"]}
    check("回退树：没有任何单零红", not lock["tickets_without_a_red"],
          str(lock["tickets_without_a_red"]))
    for bug in ("BUG-13", "BUG-14"):
        check(f"{bug} 的锁在回退树上转过红", bool(reds.get(bug)), str(reds.get(bug)))
    check(f"报告里的红条总数 {sum(len(v) for v in reds.values())}",
          f"共 {sum(len(v) for v in reds.values())} 条红" in text)
    check("临时回退树已不在盘上（报告声称跑完即删）", not (HERE / "_prefix_tree").exists())

    gold = json.loads((HERE / "golden_float_diff.json").read_text(encoding="utf-8"))
    num = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
    bad = [(r["file"], ln) for r in gold["rows"] for ln, b, a in r.get("lines", [])
           if num.sub("#", b) != num.sub("#", a) or len(num.findall(b)) != len(num.findall(a))]
    check("golden 逐行差只动了数字", not bad, str(bad[:3]))
    check(f"报告里的 golden 变更份数 {len(gold['changed'])}",
          f"{len(gold['changed'])} 份内容变化" in text or f"{len(gold['changed'])} 行" in text)

    # 报告引用的具名件必须存在。参数卡（打磨_20260926.md）在仓库外的 _fist_meta_prompts 下，
    # 单列一个可解析位置，别让「审计器不知道的地方」变成一条假 RED。
    external = {
        "打磨_20260926.md": Path(r"E:\IDEProjects\AI\_fist_meta_prompts\实例\Cypy\打磨_20260926.md"),
    }
    # 报告引用的**带目录**具名件必须存在（只写裸文件名的多是行文提及，不构成路径主张）。
    ref_re = re.compile(r"`((?:[\w.\-\u4e00-\u9fff]+/)+[\w.\-\u4e00-\u9fff]+\.(?:json|log|py|txt|md))`")
    refs = sorted({m.group(1) for m in ref_re.finditer(text)})
    missing_refs = [r for r in refs
                    if not (ROOT / r).exists()
                    and not (r.split("/")[-1] in external and external[r.split("/")[-1]].exists())]
    check("报告引用的每个带目录证据件都在盘上", not missing_refs,
          f"{len(refs)} 条里缺 {missing_refs}")

    new_entries = re.split(r"(?m)^(?=## BUG-\d+ )", "\n".join(bugs))
    for block in new_entries:
        head = re.match(r"## (BUG-\d+) ", block)
        if not head or head.group(1) not in ("BUG-30", "BUG-31"):
            continue
        first = block.splitlines()[0]
        check(f"{head.group(1)} 标题行是 OPEN 未被改写", "OPEN" in first, first)
        check(f"{head.group(1)} 文案不含本机绝对路径（路径安全红线）",
              not re.search(r"[A-Za-z]:\\|/home/", block), "有绝对路径")

    for key in ("theme:", "found:", "bugs:", "regress:", "rescan:", "root:", "report:", "note:"):
        check(f"§七 汇报块含 {key}", key in text)
    print(f"\nchecked={checked} problems={len(problems)}")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
