"""Read-only snapshot of the lifecycle surface I asserted about in the report.

Why: 报告 §六.4 写「已完成的单不允许追加/更正交付物 → 账面无处可写」，§六.1 把
「停在 [待领取] 的孤儿单无合法废弃路径」报成了 FIST-Mbt 的 BUG-10。两条都只试了
`archive`/`execute` 一条路径就下了结论。tools/list 显示还有 reopen_task / pause /
resume / reject / retry / delete / task_cleanup。这里先把现状原样存盘（只读，不改状态）。
"""
import json
import sys

import pfist

NOW = "2026-09-26T07:53:00Z"
STATUSES = ("待领取", "已领取", "执行中", "待验收", "已完成", "已归档", "已暂停", "已打回")
IDS = ("T0", "T0r15", "T0r16", "T0r2", "T0r3", "T0r4", "T0r5")


def rows(result):
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("tasks", "items", "rows", "result"):
            v = result.get(key)
            if isinstance(v, list):
                return v
        if "text" in result:
            try:
                return rows(json.loads(result["text"]))
            except Exception:  # noqa: BLE001 - probe helper, keep raw shape on disk
                return []
    return []


def main() -> int:
    c = pfist.Client()
    c._send("initialize", {"protocolVersion": pfist.PROTOCOL_VERSION,
                           "capabilities": {}, "clientInfo": pfist.CLIENT_INFO})
    out = {"now": NOW, "get": {}, "by_status": {}, "ns_rows": {}}
    for tid in IDS:
        out["get"][tid] = c.call("get", {"task_id": tid})
    for st in STATUSES:
        r = c.call("list", {"status": st})
        got = rows(r)
        out["by_status"][st] = [x.get("id") or x.get("task_id") for x in got if isinstance(x, dict)]
    nsr = c.call("list", {"namespace": "cypy-polish-20260926"})
    out["ns_rows"] = {x.get("id") or x.get("task_id"): x.get("status")
                      for x in rows(nsr) if isinstance(x, dict)}
    c.close()
    with open("probe_lifecycle_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for tid in IDS:
        g = out["get"][tid]
        t = g.get("task") if isinstance(g, dict) and "task" in g else g
        if isinstance(t, dict):
            print(f"get {tid}: status={t.get('status')!r} assignee={t.get('assignee')!r} "
                  f"ns={t.get('namespace')!r} parent={t.get('parent_id')!r} "
                  f"deliv_len={len(t.get('deliverable') or '')}")
        else:
            print(f"get {tid}: RAW {json.dumps(g, ensure_ascii=False)[:200]}")
    print("by_status:", json.dumps({k: len(v) for k, v in out["by_status"].items()},
                                   ensure_ascii=False))
    print("ns_rows:", json.dumps(out["ns_rows"], ensure_ascii=False)[:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
