#!/usr/bin/env python3
"""Try to amend T0r15 (BUG-10) with the post-verify regression-strengthening record.

The judgment criterion of that ticket was rewritten AFTER the ticket reached 已完成, so the
ledger has to say so. Whether FIST-Mbt allows any post-verify write is itself measured here
and the raw replies are dumped for the report — no paraphrasing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TID = "T0r15"
POLISHER = "cypy-polisher"
NOTE = (
    "【验收后加固，非新一轮修复】tests/test_polish_20260926.py 的两条 BUG-10 用例原判据靠 "
    "monkeypatch 换掉 cypyc.parser.parser.Parser，单跑 20 passed 但全量跑时该桩未被触发"
    "（test_bug10_cache_update_parse_failure_warns 红、capsys.err 为空串）。\n"
    "已改：用『源文件真的读不到』触发同一 except 站点，并加自证断言 compiler.calls == []"
    "（判据没绑进该站点就直接判红，不吃 ambient import 身份）。\n"
    "开关对照：两处 _warn_parse 退回 pass → `pytest -k bug10` → 2 failed"
    "（.fist-polish-20260926/pytest_switchoff_bug10.log）；恢复后 → 该文件 20 passed，"
    "cypyc/incremental/hot_reload.py 未改一行（产品代码零改动，本轮只动 tests/）。\n"
    "终态全量见报告 §三（pytest_final_sweep3.log）。"
)

c = Client(timeout=180)
c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                       "clientInfo": {"name": "cypy-polish-amend", "version": "1"}})
log = []


def step(tool, args, tag):
    out = c.call(tool, args)
    log.append({"tag": tag, "result": out})
    print(f"{tag:26s} {str(out)[:200]}")
    return out


step("get", {"task_id": TID}, "before:get")
step("execute", {"task_id": TID, "deliverable": NOTE, "now": utc_now()}, "try:execute")
step("heartbeat", {"task_id": TID, "signal": NOTE[:120], "now": utc_now()}, "try:heartbeat")
step("get", {"task_id": TID}, "after:get")
c.close()
json.dump(log, open(os.path.join(HERE, "post_verify_amend.out.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("wrote post_verify_amend.out.json")
