#!/usr/bin/env python3
r"""Second pass to FIST-Mbt's own bug ledger: one new contract defect + one correction.

Same launch detail as report_fist_findings.py (cwd=E:\IDEProjects\AI\FIST-Mbt,
project_dir=".", publish_task=False) so nothing lands on their production board and nothing
under E:\IDEProjects\AI\Cypy is written by these calls.

Why a second pass: after filing the first 4 entries I asserted in my own report that a
已完成 ticket cannot be amended and that a 待领取 orphan has no legal exit. Both were
single-path conclusions. Probing the whole 116-tool surface found `reopen_task` / `pause` /
`resume` / `reject` / `retry` / `delete`, and walking them proved the opposite — so the entry
this script previously wrote into *their* ledger (BUG-10) is itself now an over-strong claim
that the next reader would inherit as fact.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import pfist  # noqa: E402
from pfist import Client, utc_now  # noqa: E402

FIST_ROOT = r"E:\IDEProjects\AI\FIST-Mbt"
REPORTED_BY = "cypy-polisher"

FINDINGS = [
    {
        "summary": "[contract] list 描述称「不传 namespace 则列出全库所有命名空间」，实测只回单一 "
                   "ns 的行，ns `bugs`（report_bug 自动发布的修复单所在）一条都不回",
        "severity": "medium",
        "detail_key": "scope",
    },
    {
        "summary": "[更正 BUG-10] 停在 [待领取] 的任务有合法出路 `pause`（任意活跃状态→已暂停），"
                   "「无合法废弃路径 / 只能靠假交付物刷成已完成」不成立",
        "severity": "low",
        "detail": (
            "被更正条目：本账本 BUG-10「archive 走 complete 且要求状态 [待验收]，停在 [待领取] 的任务"
            "没有任何合法废弃路径（孤儿单永久残留）」。\n"
            "仍然成立的部分：`archive` 确实走 `complete`，对 `待领取` 原样报 "
            "`非法迁移: complete 要求状态 [待验收]，当前是 [待领取]`。\n"
            "不成立的部分：BUG-10 断言「没有 cancel/abandon 类工具可废弃」「只能先 claim→execute 假交付物"
            "→submit 再 archive 才能清理」。tools/list（116 个工具）里就有 "
            "`pause`（描述：任意活跃状态 -> 已暂停）、`resume`（已暂停 -> 已领取）、"
            "`reopen_task`（任意非归档任务回滚为已领取）、`reject`（待验收 -> 已打回）、"
            "`retry`（已打回 -> 执行中）、`delete`（删除已归档任务）。"
            "我当初只试了 `archive` 一条路径就下了「无出路」的结论。\n"
            "活证据（2026-09-26 实测）：对 BUG-10 点名的那 4 条孤儿单 T0r2..T0r5 逐条 `pause`，"
            "全部落到 `已暂停`（`get` 逐条复核，另有同轮 12 条未开工深拆叶子 T0.1.1..T0.6.2 一并 park，"
            "16/16 park 成功）；原始回复见 "
            "E:/IDEProjects/AI/Cypy/.fist-polish-20260926/probe_lifecycle_park.out.json 的 `pause` 段。\n"
            "为什么仍值得留一条修订而非直接当误报：BUG-10 的「建议 ①提供 abandon()」现在应改成"
            "「`pause` 已具备该语义，但 `待领取`→`已暂停` 与『作废』之间的差别（是否可 resume、"
            "是否计入未闭环、错误文案是否提示出路）没有在描述里写明」——调用方要靠读 116 个工具的描述"
            "才找得到出路，这本身就是可改进点，但不该记成「无合法路径」。\n"
            "建议：① `archive`/`complete` 的非法迁移错误文案追加一句「可用工具：pause / reopen_task」；"
            "② 在 lifecycle 文档里给出 `待领取` 的两条出路（park 或走完 claim→execute→submit→verify），"
            "别让下一位读者照 BUG-10 的措辞去造假交付物。"),
    },
]


def detail1(s):
    return (
        "现象：`list` 的 inputSchema 描述写「namespace(可选，按命名空间过滤；不传则列出全库所有命名空间)」，"
        "但不带 `namespace` 的查询只回一个命名空间的行。\n"
        f"活证据（2026-09-26 实测，cwd=E:/IDEProjects/AI/Cypy，隔离库 E:/IDEProjects/AI/Cypy/fist-mbt.db）："
        f"不带 namespace 的 `list` 返回 {s['all_rows']} 行，逐行 `namespace` 去重后只有 "
        f"{s['all_namespaces']} 一个值；同库 `list(namespace=\"cypy-polish-20260926\")` 返回 {s['polish_rows']} 行、"
        f"`list(namespace=\"bugs\")` 返回 {s['bugs_rows']} 行，其中 "
        f"{len(s['bugs_ids_missing_from_all'])} 行（如 {', '.join(s['bugs_ids_missing_from_all'][:5])}）"
        "在没有 namespace 的查询里一条都不出现。"
        "原始回复见 E:/IDEProjects/AI/Cypy/.fist-polish-20260926/probe_list_scope.out.json "
        "与 probe_lifecycle_park.out.json。\n"
        "实际后果：调用方按描述写的「全库扫一遍找未闭环单」会静默漏掉 ns `bugs` 里 "
        "`report_bug(publish_task=true)` 自动发布的全部修复单（正是 issue_up 闭环的产物），"
        "表现为「单子明明开着却查不到」→ 收尾自证不完备却看起来完备。与已入账的 BUG-8"
        "（修复单硬落 ns `bugs`、根上卷覆盖不到）叠加：一个把单送进 `bugs`，一个让默认查询看不见 `bugs`。\n"
        "建议：① 让无 namespace 的查询真正跨全库，或在返回体里加 `namespaces_scanned` 让调用方能自证范围；"
        "② 若刻意默认单 ns，就把描述改成「缺省按调用方最近使用的 ns」这类真实语义并给出取全库的入参；"
        "③ `list` 增加 `include_namespaces`，让 `bugs` 能被显式纳入。")


def scope_measurement():
    """Measure the `list` scoping facts before writing them into a bug entry."""
    pfist.SERVER_CWD = r"E:\IDEProjects\AI\Cypy"
    c = Client(timeout=60)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-scope", "version": "1"}})
    all_rows = (c.call("list", {}) or [])
    if isinstance(all_rows, dict):
        all_rows = all_rows.get("tasks") or all_rows.get("items") or []
    pol = (c.call("list", {"namespace": "cypy-polish-20260926"}) or [])
    bugs = (c.call("list", {"namespace": "bugs"}) or [])
    c.close()
    ns_seen = sorted({r.get("namespace") for r in all_rows})
    return {
        "all_rows": len(all_rows),
        "all_namespaces": ns_seen,
        "polish_rows": len(pol),
        "bugs_rows": len(bugs),
        "bugs_ids_missing_from_all": sorted(
            r.get("id") for r in bugs if r.get("id") not in {x.get("id") for x in all_rows}),
    }


def main():
    scope = scope_measurement()
    json.dump(scope, open(os.path.join(HERE, "probe_list_scope.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    if scope["all_namespaces"] != ["cypy-polish-20260926"] or not scope["bugs_ids_missing_from_all"]:
        sys.exit(f"[fist-report2] list-scope premise not reproduced, refuse to file finding 1: {scope}")
    FINDINGS[0]["detail"] = detail1(scope)
    FINDINGS[0].pop("detail_key", None)
    pfist.SERVER_CWD = FIST_ROOT
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-fist-report2", "version": "1"}})
    log = []

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    def summ(r):
        return (r.get("summary") or r.get("title") or "").strip()

    existing = {summ(r) for r in rows()}
    log.append({"tag": "bug_list:before", "count": len(existing)})

    for spec in FINDINGS:
        summary = spec["summary"]
        if summary in existing:
            log.append({"tag": f"skip:{summary[:40]}", "note": "already in ledger"})
            continue
        out = c.call("report_bug", {
            "project_dir": ".", "summary": summary, "detail": spec["detail"],
            "severity": spec["severity"], "publish_task": False,
            "reported_by": REPORTED_BY, "now": utc_now()})
        log.append({"tag": f"report:{summary[:40]}", "result": out})

    after = rows()
    c.close()
    json.dump({"ledger_before": len(existing), "ledger_after": len(after), "log": log},
              open(os.path.join(HERE, "report_fist_findings2.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for e in log:
        r = e.get("result")
        note = (r.get("bug_id") or r.get("__error__") or "") if isinstance(r, dict) else e.get("note", "")
        print(f"{e['tag']:52s} {str(note)[:90]}")
    got = {summ(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    print(f"ledger_before={len(existing)} ledger_after={len(after)} missing={len(missing)}")
    for m in missing:
        print("MISSING:", m[:70])
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
