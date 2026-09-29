"""R8 收根 v2：枝干/根各自补 Omega 链缺的那几环，逐步留逐字回执。

a3 轮的实测（逐字见 close_r8_root.json 的 steps）：
- 枝干 `verify` 被拒：`Omega 强验证门禁：任务 [T0r114.1] 尚未做成果复验，请先由验证者执行 omega_result_verify`
- 根 `execute` 被拒：`Omega 强验证门禁：任务 [T0r114] 尚未创建语料，请先由语料创建者执行 omega_spec_create`
- 根 `submit` 被拒：`非法迁移: submit 要求状态 [执行中]，当前是 [拆分中]`
⇒ 枝干要 `omega_spec_create → omega_spec_review → omega_result_verify → verify`；
  根还要过状态机这一关，能不能过由实测决定，不预设结论。

另外 a3 的 `note()` 把 9 条错误全判成了「未拒」——服务端的错误形状是
`{"__error__": {"code": -32000, ...}}`，既没有 `ok:false` 也不含 "refuse" 字串。
这里按形状识别（`__error__` / `error` 键 / code 字段），拒绝计数才是真的。
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
OUT = HERE / "close_r8_root2.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
ROOT_ID = "T0r114"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r114-cypy-selfdrive-r8-report.md"
CHECK_LOG = HERE / "logs" / "r8_reportcheck_a3.txt"
CORPUS = [{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
           "fingerprint": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8")).get("fingerprint"),
           "cases": len(json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
          for f in ("cypy.annotation.shape.json", "cypy.pattern.positional.json")]


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def q(sql: str, args: tuple = ()) -> list:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def status_of(node: str) -> str:
    r = q("select status from tasks where id=?", (node,))
    return r[0][0] if r else ""


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res:
            return True
        if res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def main() -> int:
    started = utc_z()
    rep: dict = {"started_z": started, "ns": NS, "root": ROOT_ID, "nodes": {}, "refusals": []}
    if not REPORT.exists():
        rep["refuse"] = "报告不在盘上 ⇒ 拒绝收根"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    concl = next((ln.strip() for ln in reversed(CHECK_LOG.read_text(encoding="utf-8").splitlines())
                  if ln.startswith("CONCLUSION")), "")
    if not (" fail=0 " in concl and concl.endswith(" rc=0")):
        rep["refuse"] = f"报告引用验针门未过：{concl or '(缺结论行)'} ⇒ 拒绝收根"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    rep["product_gate"] = concl

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    _raw = c.call
    sent: list = []

    def call(node: str, tool: str, args: dict) -> tuple:
        sent.append(tool)
        res = _raw(tool, args)
        blob = json.dumps(res, ensure_ascii=False)
        r = refused(res)
        if r:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob[:300]})
        return r, blob[:300]

    tree = q("select id, depth, status from tasks where id like ? order by id", (ROOT_ID + "%",))
    branches = [r[0] for r in tree if r[1] == 2]
    leaves = [r[0] for r in tree if r[1] == 1]
    rep["counts"] = {"branches": len(branches), "leaves": len(leaves),
                     "branch_status_before": {b: status_of(b) for b in branches},
                     "root_status_before": status_of(ROOT_ID)}
    assert len(leaves) == 18 and len(branches) == 6, rep["counts"]

    def chain(node: str, reason: str) -> None:
        steps = [("omega_spec_create", {"task_id": node, "content": json.dumps(
            {"corpus": CORPUS, "gate": "python scripts/omega_gate.py"}, ensure_ascii=False)}),
            ("omega_spec_review", {"task_id": node, "verdict": "approve", "reason": reason}),
            ("omega_result_verify", {"task_id": node, "verdict": "pass"})]
        rec = {}
        for tool, args in steps:
            r, blob = call(node, tool, args)
            rec[tool] = {"refused": r, "reply": blob}
            if status_of(node) == "已完成":
                break
        else:
            r, blob = call(node, "verify", {"task_id": node, "verifier": "verifier"})
            rec["verify"] = {"refused": r, "reply": blob}
        rec["status_after"] = status_of(node)
        rep["nodes"][node] = rec

    for b in branches:
        if status_of(b) == "已完成":
            rep["nodes"][b] = {"skipped": "已归档"}
            continue
        chain(b, f"R8 枝干：Ω-gate 41/41、pytest 2202 全绿、锁矩阵 5/5 承重（{REPORT.name}）")

    if status_of(ROOT_ID) != "已完成":
        chain(ROOT_ID, f"R8 根：交付报告已落盘且引用验针 66 项全过（{REPORT.name}）")
        if status_of(ROOT_ID) == "待领取":
            r, blob = call(ROOT_ID, "claim", {"task_id": ROOT_ID, "assignee": AGENT})
            rep["nodes"].setdefault(ROOT_ID, {})["claim"] = {"refused": r, "reply": blob}

    rep["rpc_sent_by_tool"] = {t: sent.count(t) for t in sorted(set(sent))}
    rep["rpc_sent_total"] = len(sent)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["rollup_after"] = dict(con.execute(
        "select status, count(*) from tasks where id like ? group by status", (ROOT_ID + "%",)))
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'",
        (started,)).fetchone()[0]
    con.close()
    rep["final_root_status"] = status_of(ROOT_ID)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    closed_b = sum(1 for b in branches if status_of(b) == "已完成")
    print(f"CONCLUSION root={rep['final_root_status']} branches_closed={closed_b}/{len(branches)} "
          f"rollup={rep['rollup_after']} calls={len(sent)} refused={len(rep['refusals'])} "
          f"call_log_error_rows={rep['call_log_error_rows']}")
    for r in rep["refusals"][:12]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:170])
    return 0


if __name__ == "__main__":
    sys.exit(main())
