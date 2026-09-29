"""Stage B: park the dangling 待领取 rows and measure what `list` actually scopes to.

Two claims of mine need numbers before they go in the report:
1. §六.1 filed FIST-Mbt BUG-10 as「停在 [待领取] 的孤儿单无合法废弃路径」——tools/list shows
   `pause`（任意活跃状态 -> 已暂停）。Measured here on the 4 probe orphans + the 12 unworked
   deep-plan leaves that my report never disclosed.
2. `list` 的描述是「不传 namespace 则列出全库所有命名空间」，但带 status 的无 ns 查询只回了
   cypy-polish-20260926 的行，ns=bugs 的 4 条 待领取 一条没回。
"""
import json
import sys

import pfist

NOW = "2026-09-26T07:56:00Z"
ORPHANS = ("T0r2", "T0r3", "T0r4", "T0r5")
LEAVES = tuple(f"T0.{p}.{c}" for p in range(1, 7) for c in (1, 2))
OUT = "probe_lifecycle_park.out.json"


def rows(result):
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("tasks", "items", "rows"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def brief(result):
    if not isinstance(result, dict):
        return {"raw": str(result)[:200]}
    return {"status": result.get("status"), "__error__": result.get("__error__")}


def main() -> int:
    c = pfist.Client()
    c._send("initialize", {"protocolVersion": pfist.PROTOCOL_VERSION,
                           "capabilities": {}, "clientInfo": pfist.CLIENT_INFO})
    log = {"now": NOW, "before": {}, "pause": {}, "after": {}}

    def snap(tag):
        log[tag] = {
            "list_no_filter": len(rows(c.call("list", {}))),
            "list_pending_no_ns": sorted(
                f"{r.get('id')}@{r.get('namespace')}" for r in rows(c.call("list", {"status": "待领取"}))),
            "list_ns_bugs_pending": sorted(r.get("id") for r in rows(c.call("list", {"namespace": "bugs"}))
                                           if r.get("status") == "待领取"),
            "list_ns_bugs_total": len(rows(c.call("list", {"namespace": "bugs"}))),
            "list_ns_polish_total": len(rows(c.call("list", {"namespace": "cypy-polish-20260926"}))),
            "list_ns_default": [r.get("id") for r in rows(c.call("list", {"namespace": "default"}))],
        }

    snap("before")
    for tid in ORPHANS + LEAVES:
        log["pause"][tid] = brief(c.call("pause", {"task_id": tid, "now": NOW}))
        log["pause"][tid + ":get"] = brief(c.call("get", {"task_id": tid}))
    snap("after")
    c.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    bad = [t for t in ORPHANS + LEAVES
           if log["pause"][t + ":get"].get("status") != "已暂停"]
    print("paused_ok", len(ORPHANS) + len(LEAVES) - len(bad), "of", len(ORPHANS) + len(LEAVES),
          "not_parked", bad)
    print("before:", json.dumps({k: v for k, v in log["before"].items()
                                 if k != "list_pending_no_ns"}, ensure_ascii=False))
    print("before pending_no_ns:", len(log["before"]["list_pending_no_ns"]),
          log["before"]["pending_no_ns" if "pending_no_ns" in log["before"] else "list_pending_no_ns"][:6])
    print("before bugs_pending:", log["before"]["list_ns_bugs_pending"])
    print("before default_ns_rows:", log["before"]["list_ns_default"])
    print("after:", json.dumps({k: v for k, v in log["after"].items()
                                if k != "list_pending_no_ns"}, ensure_ascii=False))
    print("after pending_no_ns:", len(log["after"]["list_pending_no_ns"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
