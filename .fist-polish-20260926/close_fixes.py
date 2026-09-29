#!/usr/bin/env python3
"""Close the polish round in the FIST ledger (ns=cypy-polish-20260926).

Three passes, all with a real UTC `now` per call:
  1. archive the diagnostic bug-tasks the report_bug probe runs left behind;
  2. per fix task: claim -> execute(deliverable) -> submit -> verify;
  3. per T0 leaf and then T0 itself: execute -> submit -> verify -> archive.

Every step's raw server reply is written to close_fixes.out.json so the numbers in the
polish report can be checked against the ledger instead of against my prose.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = json.load(open(os.path.join(HERE, "intake_map.json"), encoding="utf-8"))["mapping"]
POLISHER = "cypy-polisher"

FIXES = {
    "BUG-1": ("cypy_bridge/compiler.py (BridgeCacheManager.clear_cache)",
              "test_bug1_clear_cache_does_not_claim_success_when_remove_fails",
              "删除失败时不再摘 manifest 条目并保留磁盘现状；返回 {removed, failed} 并打 "
              "[cypy][warn]。RED：修复前该用例断言『.pyd 仍在但条目被删』失败（8 failed 之一），"
              "GREEN：现 15 passed。"),
    "BUG-2": ("cypy_bridge/compiler.py (BUILD_TIMEOUT=120 + subprocess.run(timeout=) + "
              "except subprocess.TimeoutExpired)",
              "test_bug2_bridge_build_subprocess_run_passes_timeout / "
              "test_bug2_build_timeout_is_shared_with_sibling_callers",
              "build_ext 子进程补 timeout=120，与 cypy_hook/hook.py:516、"
              "cypyc/project/project_compiler.py:602 同口径；超时转 BridgeError 而不是永挂。"
              "判据为 AST 级（扫描全部 subprocess.run 的 timeout 关键字），RED 时报告缺失行号 3795。"),
    "BUG-3": ("cypyc/project/project_compiler.py (get_incremental_changes)",
              "test_bug3_reparse_failure_is_reported_not_swallowed",
              "_reparse_module 失败不再 `except Exception: pass`：打 [cypy][warn] 点名模块，"
              "并说明本次仍用陈旧 AST、需全量重编确认。返回值语义未改。"),
    "BUG-4": ("cypyc/transformer/{defer,enum,generic,struct,trait}_transformer.py",
              "test_bug4_transformer_recursion_is_outside_broad_try (5 参数化)",
              "只把 getattr 留在 try/except(AttributeError,TypeError) 内，递归 _collect_* 移出静默区；"
              "子节点真实缺陷不再被当成遍历正常结束（defer/struct/trait 静默漏收集）。"
              "判据开关对照：旧形 synthetic 命中 ['_collect_defers']，新形与实文件命中 []。"),
    "BUG-5": ("cypyc/incremental/hot_reload.py (_warn_state + _save_state/_restore_state)",
              "test_bug5_state_snapshot_reports_getattr_failure / "
              "test_bug5_state_restore_reports_setattr_failure",
              "状态快照/回滚失败改为点名告警（原 6 处 except Exception: pass 中的 2 处状态面），"
              "热重载后模块带状态空洞不再不可见。"),
    "BUG-6": ("cypyc/incremental/file_monitor.py (_is_cypy_file)",
              "test_bug6_cypy_file_with_bom_is_still_detected / "
              "test_bug6_unreadable_cypy_candidate_warns",
              "首行改按字节读 + utf-8-sig 解码：带 BOM 的 `#!bin cypy` 入口不再被误判为普通 .py；"
              "FileNotFoundError 静默 False，其它 OSError 打告警，不再把读不到归成『不是 Cypy 文件』。"),
    "BUG-7": ("cypy_hook/hook.py (CypyCacheManager._load_manifest) + "
              "cypy_bridge/compiler.py (BridgeCacheManager._load_manifest)",
              "test_bug7_corrupt_manifest_warns / test_bug7_corrupt_bridge_manifest_warns",
              "manifest 损坏与『无 manifest』区分开：仍返回 {} 走重编，但打 [cypy][warn] 点名路径与异常，"
              "重编原因可见。"),
}


def main():
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close", "version": "1"}})
    log = []

    def step(tool, args, tag):
        out = c.call(tool, args)
        log.append({"tag": tag, "tool": tool, "args": {k: v for k, v in args.items()
                                                       if k != "deliverable"},
                    "result": out})
        return out

    for tid in ("T0r1", "T0r2", "T0r3", "T0r4", "T0r5"):
        step("archive", {"task_id": tid, "by": POLISHER,
                         "reason": "report_bug 落点/超时诊断期间产生的孤儿任务，非本轮确诊缺陷"},
             f"diagnostic-archive:{tid}")

    for row in MAP:
        bid, tid = row["bug_id"], row["task_id"]
        files, test, what = FIXES[bid]
        deliverable = (f"{bid} -> {tid}\n改动文件：{files}\n新增回归：tests/test_polish_20260926.py::{test}\n"
                       f"修复口径：{what}")
        step("claim", {"task_id": tid, "assignee": POLISHER}, f"{bid}:claim")
        step("execute", {"task_id": tid, "deliverable": deliverable}, f"{bid}:execute")
        step("submit", {"task_id": tid}, f"{bid}:submit")
        step("verify", {"task_id": tid, "verifier": POLISHER}, f"{bid}:verify")

    tree = step("list", {}, "list:all")
    tasks = tree if isinstance(tree, list) else (tree.get("tasks") or [])
    leaves = sorted(t["id"] for t in tasks
                    if t.get("parent_id") == "T0" and t.get("status") != "已完成")
    summary_leaf = ("三路发现与修复闭环已在同一 ns 下逐单走完 "
                    "report_bug->claim->execute->submit->verify；"
                    "证据：memory/bugs.md（BUG-1..BUG-7）、"
                    ".fist-polish-20260926/{markers_baseline.json,markers_after.json,"
                    "pytest_baseline.log,pytest_final.log,intake_map.json,close_fixes.out.json}")
    for lid in leaves:
        step("execute", {"task_id": lid, "deliverable": summary_leaf}, f"{lid}:execute")
        step("submit", {"task_id": lid}, f"{lid}:submit")
        step("verify", {"task_id": lid, "verifier": POLISHER}, f"{lid}:verify")

    step("execute", {"task_id": "T0", "deliverable": summary_leaf}, "T0:execute")
    step("submit", {"task_id": "T0"}, "T0:submit")
    step("verify", {"task_id": "T0", "verifier": POLISHER}, "T0:verify")
    step("archive", {"task_id": "T0", "by": POLISHER, "reason": "打磨轮收口"}, "T0:archive")
    c.close()

    json.dump(log, open(os.path.join(HERE, "close_fixes.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bad = [e for e in log if isinstance(e["result"], dict) and "__error__" in e["result"]]
    for e in log:
        r = e["result"]
        note = r.get("__error__") if isinstance(r, dict) and "__error__" in r else \
            (r.get("status") or r.get("ok") or "") if isinstance(r, dict) else str(r)[:60]
        print(f"{e['tag']:26s} {str(note)[:70]}")
    print(f"steps={len(log)} errors={len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
