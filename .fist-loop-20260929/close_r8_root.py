"""R8 收根：枝干（待验收）→ 根（T0r114）逐层 verify，产物门不过就拒绝开批。

三条实测依据写在这里，别下次再猜：
1. 叶闭完不会自动把根推到可验收 —— 枝干停在「待验收」，根停在「拆分中」，需要逐层 verify；
2. 带 `[omega:required]` 的根在「拆分中」态 claim 会被状态机拒（#60），所以这里不 claim，只 verify；
3. 收根前报告必须已在盘上且报告验针门 rc=0（PROJECT-SPEC/05 的 L4 产物门 + 本轮自加的引用重算门），
   归档后无法 reopen，也没有 amend 接口 ⇒ 门不过就只能拒绝，不做「先收再说」。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r8_root.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
ROOT_ID = "T0r114"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r114-cypy-selfdrive-r8-report.md"
CHECK_LOG = HERE / "logs" / "r8_reportcheck_a3.txt"


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows_like(prefix: str) -> list:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute("select id, depth, status from tasks where id like ? order by id",
                           (prefix + "%",)).fetchall()
    finally:
        con.close()


def status_of(node: str) -> str:
    r = rows_like(node)
    return next((x[2] for x in r if x[0] == node), "")


def last_line(path: Path, needle: str) -> str:
    if not path.exists():
        return ""
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return ""


def main() -> int:
    started = utc_z()
    rep: dict = {"started_z": started, "ns": NS, "root": ROOT_ID, "steps": {}, "refusals": []}

    # 产物门（两道，先便宜门后重门）
    if not REPORT.exists():
        rep["refuse"] = f"报告不在盘上（{REPORT.name}）⇒ 拒绝收根"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1
    verdict = last_line(CHECK_LOG, "CONCLUSION")
    # 针按字段取，不按「相邻子串」—— 实测结论行是 `... fail=0 report=<名> rc=0`，
    # 拿 `"fail=0 rc=0"` 当 needle 会因中间夹了 report 名而恒假（本门第一次跑就被自己拒了）。
    if not (verdict.startswith("CONCLUSION") and " fail=0 " in verdict and verdict.endswith(" rc=0")):
        rep["refuse"] = f"报告引用验针门未过：{verdict or '(缺结论行)'} ⇒ 拒绝收根"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1
    rep["product_gate"] = {"report_bytes": REPORT.stat().st_size,
                           "report_conclusion_tail": last_line(REPORT, "**一句话终态**")[:200],
                           "verifier_conclusion": verdict}

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    _raw = c.call
    sent: list = []

    def call(tool, args):
        sent.append(tool)
        return _raw(tool, args)

    def note(node, tool, res):
        blob = json.dumps(res, ensure_ascii=False)
        refused = (res.get("ok") is False) or "refuse" in blob.lower() or blob.startswith("RPC-ERROR")
        if refused:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob})
        return refused

    tree = rows_like(ROOT_ID)
    # depth 是「离叶的距离」不是「离根的距离」：实测根=3、枝干=2、叶=1（R8 a1 拿 depth==1 当枝干，
    # 于是要么没 verify 到任何一支、要么把 18 支叶当成了枝干）。这里按实测层级取，并回读校验层数。
    branches = [r[0] for r in tree if r[1] == 2]
    leaves = [r[0] for r in tree if r[1] == 1]
    assert len(leaves) == 18 and len(branches) == 6, (len(leaves), len(branches))
    rep["tree_counts"] = {"root": 1 if any(r[0] == ROOT_ID for r in tree) else 0,
                          "branches": len(branches), "leaves": len(leaves),
                          "branch_status_before": {b: status_of(b) for b in branches}}

    for b in [x for x in branches if status_of(x) in ("待验收", "待领取")]:
        res = call("verify", {"task_id": b, "verifier": "verifier"})
        rep["steps"][b] = {"reply": json.dumps(res, ensure_ascii=False)[:300],
                           "status_after": status_of(b)}
        note(b, "verify", res)

    rep["root_status_before"] = status_of(ROOT_ID)
    if rep["root_status_before"] == "待验收":
        res = call("verify", {"task_id": ROOT_ID, "verifier": "verifier"})
        rep["steps"]["root:verify"] = {"reply": json.dumps(res, ensure_ascii=False)[:300],
                                      "status_after": status_of(ROOT_ID)}
        note(ROOT_ID, "verify", res)
    elif rep["root_status_before"] == "待领取":
        res = call("claim", {"task_id": ROOT_ID, "assignee": AGENT})
        rep["steps"]["root:claim"] = {"reply": json.dumps(res, ensure_ascii=False)[:300]}
        note(ROOT_ID, "claim", res)
        res = call("verify", {"task_id": ROOT_ID, "verifier": "verifier"})
        rep["steps"]["root:verify"] = {"reply": json.dumps(res, ensure_ascii=False)[:300]}
        note(ROOT_ID, "verify", res)
    else:
        rep["root_chain_attempted"] = False
    rep["steps"][ROOT_ID] = status_of(ROOT_ID)

    # 根若仍「拆分中」：枝干已闭 ⇒ 试着让状态机自己上卷一次（不伪造），只读复算后再报
    if status_of(ROOT_ID) == "拆分中":
        rep["root_chain_attempted"] = rep.get("root_chain_attempted", False)
        for tool, args in (("execute", {"task_id": ROOT_ID,
                                        "output": f"R8 交付见 {REPORT.name}",
                                        "deliverable": f"{last_line(CHECK_LOG, 'CONCLUSION')}"}),
                           ("submit", {"task_id": ROOT_ID})):
            res = call(tool, args)
            rep["steps"][f"root:{tool}"] = {"reply": json.dumps(res, ensure_ascii=False)[:300],
                                            "status_after": status_of(ROOT_ID)}
            note(ROOT_ID, tool, res)
        rep["steps"]["root_after_execute_submit"] = status_of(ROOT_ID)
        if rep["steps"]["root_after_execute_submit"] == "待验收":
            note(ROOT_ID, "verify", call("verify", {"task_id": ROOT_ID, "verifier": "verifier"}))
            rep["steps"][ROOT_ID] = status_of(ROOT_ID)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rollup = dict(con.execute("select status, count(*) from tasks where id like ? group by status",
                              (ROOT_ID + "%",)).fetchall())
    logged = con.execute("select count(*) from call_log where tool in ('verify','execute','submit','claim') "
                         "and ts>=?", (started,)).fetchone()[0]
    con.close()
    rep["rollup_after"] = rollup
    rep["call_log_rows_since_start"] = logged
    rep["rpc_sent_total"] = len(sent)
    rep["rpc_sent_by_tool"] = {t: sent.count(t) for t in sorted(set(sent))}
    rep["final_root_status"] = status_of(ROOT_ID)

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"CONCLUSION root={rep['final_root_status']} rollup={rollup} "
          f"branches_closed={sum(1 for b in branches if status_of(b) == '已完成')}/{len(branches)} "
          f"calls={len(sent)} refused={len(rep['refusals'])} "
          f"gate={rep['product_gate']['verifier_conclusion'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
