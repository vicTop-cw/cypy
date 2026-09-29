"""R4-修复 的顺序与"渲染后不再改"正面取证。

本环纪律（写进 spec 法 ⑥）是 **判据件 → 报告终版 → 叶收口 → 根收口**。这一格不能用"我记得
只渲染过一次"来交账，所以全部从盘上反解：

1. 本轮 tag 在 `memory/reviews/` 里只能命中 **一个** 报告文件（多一个就是旧时间戳副本没清）；
2. 报告 mtime 必须**晚于**全部判据件与产品码的 mtime（否则报告不是终版）；
3. 报告正文里 `‹未解析›` / `❌` 必须为零，门禁行数 = spec 声明的 gates 数；
4. 留一份 sha256，`--check` 只读比对：渲染之后再跑一次就能证明"交付物没被回改"。

`--check` 模式不写任何文件（收口之后再动证据件就是上一环记过的债）。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r4_render_order.json"
TAG = "[loop:20260927-loop:R4-修复]"
SPEC = HERE / "report_spec_r4_fix.json"
JUDGE_GLOB = "fix_r4_*.json"
PRODUCT = ["cypyc/analyzer/type_checker.py", "tests/test_loop_20260927_fix_r4.py",
           "docs/USAGE.md"]
REFUSE: list = []


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(
        timespec="seconds")


def main() -> int:
    if "--check" in sys.argv:
        if not OUT.exists():
            print(json.dumps({"refuse": ["没有 record 件，无从比对"]}, ensure_ascii=False))
            return 1
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        p = ROOT / prev["report"]
        now = sha256(p) if p.exists() else ""
        same = bool(now) and now == prev["report_sha256"]
        print(json.dumps({"report": prev["report"], "sha_recorded": prev["report_sha256"],
                          "sha_now": now, "unchanged_after_render": same,
                          "checked_at_utc": utc(datetime.datetime.now().timestamp())},
                         ensure_ascii=False, indent=1))
        return 0 if same else 1

    started = utc(datetime.datetime.now().timestamp())
    if not SPEC.exists():
        REFUSE.append(f"报告 spec 不在盘上：{SPEC.name}")
        spec = {}
    else:
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
    # 本轮报告的身份 = 装配器页脚里的 `root=<根任务>` 与本页 marker 同时出现。
    # （原先找 `[loop:…]` 任务标签：那是**任务库 description** 的形状，报告正文里根本没有 ⇒
    #  命中 0 个文件，"渲染次数"这一格就读成 0，是恒假而不是恒真——两种都会骗人。）
    root = spec.get("root_task", "")
    marker = spec.get("marker", "")
    sig_hits = []
    for p in sorted((ROOT / "memory" / "reviews").glob("*.md")):
        t = p.read_text(encoding="utf-8", errors="replace")
        if root and marker and f"root={root}" in t and marker in t:
            sig_hits.append(p)
    reports = sig_hits
    if len(reports) != 1:
        REFUSE.append(f"本轮 tag 命中 {len(reports)} 个报告文件（应为 1）："
                      f"{[p.name for p in reports]}")
        doc = {"started": started, "renders": len(reports), "refuse": REFUSE}
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 1
    rep = reports[0]
    text = rep.read_text(encoding="utf-8")
    rel = rep.relative_to(ROOT).as_posix()
    rep_mt = rep.stat().st_mtime

    judges = sorted(HERE.glob(JUDGE_GLOB))
    own = [j for j in judges if j.name != OUT.name]
    if not own:
        REFUSE.append("判据件集合为空 ⇒ 「渲染晚于判据」这一格是空话")
    late_j = [j.name for j in own if j.stat().st_mtime > rep_mt]
    late_p = [n for n in PRODUCT
              if (ROOT / n).exists() and (ROOT / n).stat().st_mtime > rep_mt]
    if late_j:
        REFUSE.append(f"报告渲染后还有判据件被改写：{late_j}")
    if late_p:
        REFUSE.append(f"报告渲染后产品码/测试/文档还在动：{late_p}")

    unresolved = text.count("‹未解析›") + text.count("‹收口后生成›")
    cross = len(re.findall(r"^\|\s*[❌]", text, re.M))
    declared = len(spec.get("gates", []))
    rows = len(re.findall(r"^\|\s*[①-⑳]|^\|\s*\d+\s*\|", text, re.M))
    if unresolved:
        REFUSE.append(f"报告里有 {unresolved} 处未解析占位")
    if cross:
        REFUSE.append(f"报告里有 {cross} 行门禁判红")
    if not rows:
        REFUSE.append("门禁表一行都没解析到 ⇒ 行数对照恒真")
    if spec and declared != rows:
        REFUSE.append(f"spec 声明 {declared} 道门禁，报告表里 {rows} 行 ⇒ 对不上")

    doc = {
        "started": started, "stage_order": "判据件 → 报告终版 → 叶收口 → 根收口",
        "renders": len(reports), "report": rel, "report_bytes": rep.stat().st_size,
        "report_sha256": sha256(rep), "report_mtime_utc": utc(rep_mt),
        "spec_name": spec.get("name", ""), "root_task": spec.get("root_task", ""),
        "marker": marker, "signature": f"root={root} + {marker}",
        "product_mtime_utc": {n: utc((ROOT / n).stat().st_mtime) for n in PRODUCT
                              if (ROOT / n).exists()},
        "tag": TAG, "judges_total": len(own),
        "judges_later_than_report": late_j, "product_later_than_report": late_p,
        "earliest_judge_utc": utc(min(j.stat().st_mtime for j in own)) if own else "",
        "latest_judge_utc": utc(max(j.stat().st_mtime for j in own)) if own else "",
        "gates_declared_in_spec": declared, "gate_rows_in_report": rows,
        "unresolved_placeholders": unresolved, "red_gate_rows": cross,
        "refuse": REFUSE, "at_utc": utc(datetime.datetime.now().timestamp()),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "renders", "report", "report_sha256",
                                          "gates_declared_in_spec", "gate_rows_in_report",
                                          "judges_total", "latest_judge_utc",
                                          "report_mtime_utc")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
