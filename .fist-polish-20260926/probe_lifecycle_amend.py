"""Stage A: measure whether a 已完成 ticket can actually be amended, and what `list` scopes to.

Why: 报告 §六.4 断言「已完成的单不允许追加/更正交付物 → 账面无处可写」，依据只是
`execute T0r15` 被拒。tools/list 里有 `reopen_task`（任意非归档任务回滚为已领取）。
本脚本只动本轮隔离库 ns=bugs 的 T0r15 与只读查询，跑完把原始回复全部落盘。
"""
import json
import sys

import pfist

NOW = "2026-09-26T07:54:30Z"
SNAP = "probe_lifecycle_snapshot.json"
OUT = "probe_lifecycle_amend.out.json"
TEST_FILE = "tests/test_polish_20260926.py"

AMEND = (
    "\n\n---\n"
    "【判据加固更正（本单收尾后追加，走 reopen_task 回滚→execute→submit→verify）】\n"
    "1. 上一版交付物写「已完成的单无法追加/更正交付物（execute 报『非法执行: 任务处于 [已完成]』），"
    "只能改用 heartbeat 挂说明」——该结论只对单条路径成立，是误判：\n"
    "   server 侧存在 `reopen_task`（描述：任意非归档任务回滚为已领取）与 `pause`"
    "（任意活跃状态 -> 已暂停），本段文字本身就由 reopen_task -> execute -> submit -> verify 写入，"
    "即『账面无处可写』被本次实测否证。原始回复见 "
    "`.fist-polish-20260926/probe_lifecycle_amend.out.json`。\n"
    "2. 判据加固的实质内容不变：本单锁死的站点在 `tests/test_polish_20260926.py`，"
    "开关对照（破修复→复红、复原→复绿）见 `.fist-polish-20260926/pytest_switchoff_bug10.log`。\n"
)


def rows(result):
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("tasks", "items", "rows"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def main() -> int:
    snap = json.load(open(SNAP, encoding="utf-8"))
    prev = snap["get"]["T0r15"]
    prev_task = prev.get("task") if isinstance(prev, dict) and "task" in prev else prev
    old_deliv = (prev_task or {}).get("deliverable") or ""
    if len(old_deliv) < 400:
        sys.exit(f"[amend] snapshot deliverable looks truncated ({len(old_deliv)} chars), abort")

    c = pfist.Client()
    c._send("initialize", {"protocolVersion": pfist.PROTOCOL_VERSION,
                           "capabilities": {}, "clientInfo": pfist.CLIENT_INFO})
    log = {"now": NOW, "old_deliverable_len": len(old_deliv), "steps": {}, "reads": {}}

    # --- read-only: what does `list` scope to when namespace is omitted? ---
    log["reads"]["list_status_pending_no_ns"] = [
        {"id": r.get("id"), "ns": r.get("namespace")} for r in rows(c.call("list", {"status": "待领取"}))]
    log["reads"]["list_ns_bugs"] = [
        {"id": r.get("id"), "status": r.get("status")} for r in rows(c.call("list", {"namespace": "bugs"}))]
    log["reads"]["list_no_filter"] = len(rows(c.call("list", {})))

    def step(name, tool, args, timeout=None):
        log["steps"][name] = c.call(tool, dict(args, now=NOW), timeout)
        print(name, "->", json.dumps(log["steps"][name], ensure_ascii=False)[:220])
        return log["steps"][name]

    def status(tid):
        r = c.call("get", {"task_id": tid})
        t = r.get("task") if isinstance(r, dict) and "task" in r else r
        return {"status": (t or {}).get("status"),
                "assignee": (t or {}).get("assignee"),
                "deliv_len": len((t or {}).get("deliverable") or "")}

    log["reads"]["T0r15_before"] = status("T0r15")
    step("reopen_task", "reopen_task", {"task_id": "T0r15"})
    log["reads"]["T0r15_after_reopen"] = status("T0r15")
    step("execute", "execute", {"task_id": "T0r15", "executor": "cypy-polisher",
                                "deliverable": old_deliv + AMEND})
    log["reads"]["T0r15_after_execute"] = status("T0r15")
    rc = step("run_check", "run_check", {"task_id": "T0r15", "cmd": sys.executable,
                                         "args": ["-m", "pytest", TEST_FILE, "-q", "-p", "no:cacheprovider"],
                                         "workdir": ".", "timeout_ms": 240000}, timeout=300)
    passed = isinstance(rc, dict) and (rc.get("passed") is True or str(rc.get("status", "")).lower() == "passed")
    print("run_check passed?", passed, json.dumps(rc, ensure_ascii=False)[-260:])
    step("submit", "submit", {"task_id": "T0r15"})
    log["reads"]["T0r15_after_submit"] = status("T0r15")
    step("verify", "verify", {"task_id": "T0r15", "verifier": "cypy-polisher"})
    log["reads"]["T0r15_final"] = status("T0r15")
    log["reads"]["T0_root_final"] = status("T0")
    c.close()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print("reads:", json.dumps(log["reads"], ensure_ascii=False))
    ok = log["reads"]["T0r15_final"]["status"] == "已完成"
    print(f"[amend] terminal status={log['reads']['T0r15_final']['status']} "
          f"deliv_len={log['reads']['T0r15_final']['deliv_len']} walk_ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
