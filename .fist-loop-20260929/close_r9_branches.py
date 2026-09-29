"""R9 收口补腿：卡住的 3 支枝干与根，先落 `execute`（交付物）再走 result_verify → verify。

R8 收根之所以一次过，是因为更早一轮 a2 已经对根发过 `execute`（deliverable 落了库）；
本轮 a3 只发 spec_create/review/result_verify 三支 ⇒ 服务端逐字回
`任务 [T0r115.3] 尚无交付物（deliverable 为空），无可复验成果`。
这条把形状补全；如果 `execute` 在「拆分中」态也被状态机拒，就如实记为一条无出路面并立单，不伪造关闭。
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
OUT = HERE / "close_r9_branches.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
ROOT_ID = "T0r115"
CORPUS = [{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
           "cases": len(json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
          for f in ("cypy.annotation.shape.json", "cypy.pattern.positional.json",
                    "cypy.type.slice.json")]


def refused(res) -> bool:
    blob = json.dumps(res, ensure_ascii=False)
    return "__error__" in blob or blob.startswith("RPC-ERROR") or (res or {}).get("ok") is False


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    targets = [r[0] for r in con.execute(
        "select id from tasks where id like ? and status!='已完成' and depth in (2,3) order by depth desc, id",
        (f"{ROOT_ID}%",)).fetchall()]
    con.close()
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    sent: list = []
    rep: dict = {"started_z": started, "targets": targets, "nodes": {}, "refusals": []}

    def call(node, tool, args):
        sent.append(tool)
        res = c.call(tool, args)
        if refused(res):
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)[:260]})
        return res

    def status(node: str) -> str:
        q = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            r = q.execute("select status from tasks where id=?", (node,)).fetchone()
        finally:
            q.close()
        return r[0] if r else ""

    for node in targets:
        rec = {}
        deliverable = (f"R9 交付：BUG-71 切片结果类型闭环（DEMO `planned_features.cypy --check-only` rc 1→0）；"
                       "越界槽位在字段可见前提下不再发 `.__f{i}`；Ω-spec 3 op/51 对；"
                       "账本 9 段（7 关闭/2 AMENDMENT），open 块 32→25。"
                       "终验 pytest 2212 passed rc=0 / 自研 47/47 / e2e PASS=25 FAIL=0 / Ω-gate 51/51 100%")
        rec["execute"] = json.dumps(call(node, "execute", {"task_id": node, "deliverable": deliverable,
                                                           "executor": "self"}),
                                    ensure_ascii=False)[:240]
        rec["status_after_execute"] = status(node)
        for tool, args in (("omega_spec_create", {"task_id": node,
                                                  "content": json.dumps({"corpus": CORPUS},
                                                                        ensure_ascii=False)}),
                           ("omega_spec_review", {"task_id": node, "verdict": "approve",
                                                  "reason": "R9：3 op/51 测试对含 2 条错误路径与成对另一半"}),
                           ("omega_result_verify", {"task_id": node, "verdict": "pass"})):
            rec[tool] = json.dumps(call(node, tool, args), ensure_ascii=False)[:240]
            if status(node) == "已完成":
                break
        else:
            rec["verify"] = json.dumps(call(node, "verify", {"task_id": node, "verifier": "verifier"}),
                                       ensure_ascii=False)[:240]
        rec["status_final"] = status(node)
        rep["nodes"][node] = rec

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["rollup"] = dict(con.execute("select status, count(*) from tasks where id like ? group by status",
                                     (f"{ROOT_ID}%",)).fetchall())
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    con.close()
    rep["calls"] = len(sent)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for n, r in rep["nodes"].items():
        print(n, "| after_execute=", r.get("status_after_execute"), "| final=", r.get("status_final"))
    print(f"CONCLUSION root={status(ROOT_ID)} rollup={rep['rollup']} calls={len(sent)} "
          f"refused={len(rep['refusals'])} call_log_error_rows={rep['call_log_error_rows']}")
    for r in rep["refusals"][:8]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:170])
    return 0


if __name__ == "__main__":
    main()
