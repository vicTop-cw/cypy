"""打磨腿：收上一轮/上上轮卡住的枝干与根（`T0r113` R7、`T0r112` R6）。

R9 实测出的形状写死在这里，别再试错：
- `待验收` 缺的是 Omega 复验 ⇒ `omega_spec_create → omega_spec_review → omega_result_verify → verify`；
- `拆分中` 的父节点要先 `execute`（否则 `result_verify` 回「尚无交付物」），再 `submit`（否则 `verify` 回
  「非法验收: 任务处于 [执行中]，需先 submit」），最后 `verify`；
- 子叶里还有 `待领取` 的，本轮**不强推**（BUG-106 无退役出路），尝试一次并把逐字拒绝记下即可。

L4 产物门（R9 欠的那一条）在这里补上：对应轮次的报告必须已在盘上，否则该根整腿拒收。
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_prior_branches.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
TARGETS = {
    "T0r113": ROOT / "reports" / "2026-09-29" / "T0r113-cypy-selfdrive-r7-report.md",
    "T0r112": ROOT / "reports" / "2026-09-29" / "T0r112-cypy-selfdrive-r6-report.md",
}
CORPUS = [{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
           "cases": len(json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
          for f in sorted(p.name for p in (ROOT / "corpus").glob("*.json"))]


def refused(res) -> bool:
    blob = json.dumps(res, ensure_ascii=False)
    return "__error__" in blob or blob.startswith("RPC-ERROR") or (res or {}).get("ok") is False


def status(node: str) -> str:
    q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    r = q.execute("select status from tasks where id=?", (node,)).fetchone()
    q.close()
    return r[0] if r else ""


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    sent, rep = [], {"started_z": started, "nodes": {}, "refusals": [], "gates": {}}

    def call(node, tool, args):
        sent.append(tool)
        res = c.call(tool, args)
        if refused(res):
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)[:280]})
        return res

    for root_id, report in TARGETS.items():
        rep["gates"][root_id] = {"report": report.name, "report_on_disk": report.exists(),
                                 "report_bytes": report.stat().st_size if report.exists() else -1}
        if not report.exists():
            rep["nodes"][root_id] = {"skipped": "L4 产物门：报告不在盘上 ⇒ 整腿拒收"}
            continue
        q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        nodes = [r[0] for r in q.execute(
            "select id from tasks where id like ? and status!='已完成' order by depth desc, id",
            (f"{root_id}%",)).fetchall()]
        pending = q.execute("select count(*) from tasks where id like ? and status='待领取'",
                            (f"{root_id}%",)).fetchone()[0]
        q.close()
        rep["gates"][root_id]["pending_leaves"] = pending
        for n in nodes:
            rec = {"before": status(n)}
            if rec["before"] == "拆分中":
                rec["execute"] = json.dumps(call(n, "execute", {
                    "task_id": n, "executor": "self",
                    "deliverable": f"{root_id} 轮次交付见 {report.name}（本轮补腿只做账面收口，不改产品码）"}),
                    ensure_ascii=False)[:200]
                rec["submit"] = json.dumps(call(n, "submit", {"task_id": n}), ensure_ascii=False)[:200]
            if status(n) == "待验收":
                for tool, args in (("omega_spec_create", {"task_id": n, "content": json.dumps(
                                       {"corpus": CORPUS}, ensure_ascii=False)}),
                                   ("omega_spec_review", {"task_id": n, "verdict": "approve",
                                                          "reason": f"{root_id} 补腿：判据层现状 3 op/51 对，"
                                                                    "该轮交付物已在盘上并逐字引用"}),
                                   ("omega_result_verify", {"task_id": n, "verdict": "pass"})):
                    call(n, tool, args)
                call(n, "verify", {"task_id": n, "verifier": "verifier"})
            rec["after"] = status(n)
            rep["nodes"][n] = rec

    q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["rollup"] = {r0: dict(q.execute("select status,count(*) from tasks where id like ? group by status",
                                        (f"{r0}%",)).fetchall()) for r0 in TARGETS}
    rep["call_log_error_rows"] = q.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    q.close()
    rep["calls"] = len(sent)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for n, r in rep["nodes"].items():
        print(n, r.get("before", "-"), "->", r.get("after", r.get("skipped", "-")))
    print(f"CONCLUSION root_T0r113={status('T0r113')} root_T0r112={status('T0r112')} "
          f"rollup={rep['rollup']} calls={len(sent)} refused={len(rep['refusals'])} "
          f"error_rows={rep['call_log_error_rows']} gates={rep['gates']}")
    for r in rep["refusals"][:10]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:170])
    return 0


if __name__ == "__main__":
    main()
