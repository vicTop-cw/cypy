#!/usr/bin/env python3
"""Report the FIST-Mbt defects this polish round observed, into FIST-Mbt's own ledger.

Standing instruction: 「启用 issue <发现 fist-mbt 缺陷需要上报>」 — a defect found in the
driver project must reach *its* bug ledger, not just my prose.

Launch detail that matters: `report_bug`'s `project_dir` is resolved against the **server
process cwd** (that contract is itself BUG-5 already filed there), so this script starts the
same main.js with cwd=E:\\IDEProjects\\AI\\FIST-Mbt and passes project_dir=".".  Nothing under
`E:\\IDEProjects\\AI\\Cypy` is written by these calls.

`publish_task=False` on purpose: the Cypy polish lane must not seed tasks onto FIST-Mbt's
production board (a watchdog scans it); the finding is filed as a bug entry with live evidence.

Idempotent like intake.py: reconcile by `summary` against `bug_list` before each fire, and
write every raw reply to report_fist_findings.out.json.
"""
import json
import os
import subprocess
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
        "summary": "[ledger-lifecycle] src/server/bugreport.mbt:264 自动发布的修复单硬落 "
                   "namespace \"bugs\"，与发起 ns 断裂，根任务上卷覆盖不到它",
        "severity": "medium",
        "detail": (
            "现象：`report_bug(publish_task=true)` 生成的修复单被写死在 ns `bugs`"
            "（`src/server/bugreport.mbt:264` 的 `ns=\"bugs\"`），`parent_id=null`，"
            "而调用方本轮用的是 ns `cypy-polish-20260926`。\n"
            "活证据（2026-09-26 实测，cwd=E:/IDEProjects/AI/Cypy）：8 张修复单 T0r6..T0r13 的 "
            "`claim`/`verify` 原始回复里都带 `\"namespace\": \"bugs\", \"parent_id\": null`，"
            "见 E:/IDEProjects/AI/Cypy/.fist-polish-20260926/close_fixes.out.json 的 `BUG-1:claim`"
            " 与 `BUG-8:claim` 两条。\n"
            "实际后果：① 「子单全部 verify 后父任务自动上卷」这条生命周期对 issue_up 通道永不触发，"
            "根任务状态与缺陷闭环无关，指挥官若按根状态判断进度必然误判；② `list` 按 ns 作用域，"
            "在本轮 ns 里看不到这些修复单，只能靠 `get(task_id)` 逐单点名；③ 收尾脚本无法用一条"
            "「列出本 ns 未闭环单」的查询自证收口完备，只能自带映射表（本轮 intake_map.json）。\n"
            "建议（按代价升序）：① `report_bug` 增加 `task_namespace` 入参，缺省仍为 `bugs` 但允许"
            "调用方指定；② 返回值与 `bug_list` 行都补 `namespace`/`task_id` 已在做，再加 `root_task_id` "
            "以便按发起树聚合；③ 文档明确写「修复单落在独立 ns `bugs`，不挂到调用方任务树」，"
            "别让「父任务自动上卷」的措辞覆盖它。"),
    },
    {
        "summary": "[ledger-lifecycle] 缺陷账本只写不销：无 bug 关闭/状态位 API，"
                   "修复单全部「已完成」后 bugs.md 条目仍恒为 OPEN",
        "severity": "medium",
        "detail": (
            "现象：bug 工具族只有 `report_bug`（写）与 `bug_list`（读）"
            "（`src/server/server.mbt:4024` 与 `:4096` 是全部注册点），没有任何 "
            "`bug_close`/`bug_resolve`/状态入参。`bugs.md` 条目头写 `## BUG-n [ts] [sev] OPEN`，"
            "此后无论关联修复单走到哪一步，该状态位都没有合法路径可翻转。\n"
            "活证据（2026-09-26 实测）：E:/IDEProjects/AI/Cypy/memory/bugs.md 的 BUG-1..BUG-8 "
            "八条全部标 `OPEN`（grep `^## BUG-` 八行尾列全 OPEN），而同轮 "
            "E:/IDEProjects/AI/Cypy/.fist-polish-20260926/close_fixes.out.json 显示 T0r6..T0r13 "
            "八张修复单 `verify` 回复 status 全部 `已完成`。同一事实两份账，一份说全绿一份说全开。\n"
            "实际后果：issue_up 的「发现→上报→修复→销账」闭环缺最后一环。下一轮（或别的 agent）"
            "读 `bug_list` 会把 8 条已修完的缺陷继续当未决工作，或者靠人工在 markdown 里手改状态位——"
            "手改即污染：`bug_list` 若解析 markdown，手改内容不在服务端事务内，无 `now`、无 caller、"
            "不进 call_log。\n"
            "建议：① 新增 `bug_close(bug_id, resolved_by, task_id, now)`，把状态位写成 "
            "`CLOSED [<task_id>]` 并落 call_log；② 或在修复单 `verify` 成功时自动销账"
            "（需要 bug↔task 反查表，`report_bug` 已经在写 task_id，具备条件）；"
            "③ 过渡期至少让 `bug_list` 返回关联任务的当前 status，别让读方只能看 OPEN。"),
    },
    {
        "summary": "[lifecycle] archive 走 complete 且要求状态 [待验收]，停在 [待领取] 的任务"
                   "没有任何合法废弃路径（孤儿单永久残留）",
        "severity": "low",
        "detail": (
            "现象：`archive` 内部走 `complete` 迁移，前置状态是 `[待验收]`；而诊断/试写期间"
            "产生的、只到 `待领取` 的任务既不能 `archive`（迁移非法）、也没有 `cancel`/`abandon` "
            "类工具可废弃，`verify`/`submit` 又要求先有交付物。结果是任务库里永久留下无法清理的行。\n"
            "活证据（2026-09-26 实测）：本轮隔离库 E:/IDEProjects/AI/Cypy/fist-mbt.db 中入账探针留下的 "
            "T0r2..T0r5 四条停在 `待领取`，`archive` 原样报错 "
            "`非法迁移: complete 要求状态 [待验收]，当前是 [待领取]`（逐条回复见 "
            "E:/IDEProjects/AI/Cypy/.fist-polish-20260926/close_fixes.out.json 的 `diagnostic-archive:*`）。"
            "同一工具对 `待领取` 与 `已完成` 两种状态给出同一个 `complete` 前置，错误文案未提示出路。\n"
            "实际后果：自驱式流水线里「试写/探针/被取代的单」是常态产物，现在只能靠"
            "「先 claim→execute 假交付物→submit 再 archive」把噪声刷成已完成——那等于要求造假账才能清理干净，"
            "与本轮红线「禁止伪造已完成」直接冲突，所以本轮选择留着 4 条孤儿单并写进报告。\n"
            "建议：① 提供 `abandon(task_id, by, reason, now)`：允许从 `待领取`/`执行中` 迁到"
            "`已废弃`，reason 进 call_log；② 或让 `archive` 接受 `待领取` 并把它当「未开工即作废」，"
            "不再要求 complete 前置；③ 错误文案补一句「可用工具：<xxx>」，让调用方不用读源码找出路。"),
    },
    {
        "summary": "[contract] report_bug 返回 `bug_id` 而 bug_list 同一字段叫 `id`，"
                   "按写侧字段名做对账的读侧会静默拿到 null",
        "severity": "low",
        "detail": (
            "现象：写侧 `report_bug` 响应键是 `bug_id`，读侧 `bug_list` 每行的键是 `id`"
            "（值同为 `BUG-n`）——同一实体两个字段名，工具描述未提示这一差异。\n"
            "活证据（2026-09-26 实测，cwd=E:/IDEProjects/AI/Cypy）：`bug_list(project_dir=\".\")` "
            "首行键集合 `['detail','id','reported_by','severity','status','summary','task_id','ts']`，"
            "且 `any('bug_id' in row)` 为 False；而入账响应里是 `\"bug_id\": \"BUG-8\"`。"
            "本轮幂等入账器按 `row.get(\"bug_id\")` 取值，导致重跑时 7 条「已在账」的缺陷在 "
            "E:/IDEProjects/AI/Cypy/.fist-polish-20260926/intake_map.json 中被写成 "
            "`\"bug_id\": null`（`task_id` 仍正确），报告渲染时以 KeyError 暴露。\n"
            "实际后果：任何「按写侧字段名读回」的对账/去重逻辑都会静默丢 id——不报错，只是取不到，"
            "于是「bug↔任务↔回归」三向对照在无人察觉时退化，最坏情形会把已入账缺陷当新缺陷再写一遍。\n"
            "建议：① `bug_list` 行同时输出 `bug_id`（与 `id` 同值，向后兼容）；② 或在工具描述里写明"
            "读侧字段名；③ 长期把 bug 实体 id 收敛成单一字段名，写读两侧共用同一个序列化函数。"),
    },
]


def main():
    pfist.SERVER_CWD = FIST_ROOT
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-fist-report", "version": "1"}})
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
              open(os.path.join(HERE, "report_fist_findings.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for e in log:
        r = e.get("result")
        note = (r.get("bug_id") or r.get("__error__") or "") if isinstance(r, dict) else e.get("note", "")
        print(f"{e['tag']:52s} {str(note)[:80]}")
    got = {summ(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    print(f"ledger_before={len(existing)} ledger_after={len(after)} missing={len(missing)}")
    for m in missing:
        print("MISSING:", m[:70])
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
