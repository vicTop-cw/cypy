#!/usr/bin/env python3
"""Fifth-pass intake: the TestDigestCost wall-clock gate is not a function of the code it measures.

Found by lane ② (the terminal `pytest tests/ -q` sweep went from 1 red to 2 reds without any
change on the measured path).  Filed because the *criterion* is confirmed defective, with a
deterministic mechanism proof; the product code is exonerated, so nothing in cypyc/ is touched
and the ticket is deliberately left open for the commander (loosening or re-instrumenting an
existing test's assertion is a judge change, out of this round's "tests/ 只补回归不改语义" scope).

Evidence, all re-runnable:
  .fist-polish-20260926/pytest_final_sweep5.log            whole suite -> 2 failed (digest 3.223s)
  .fist-polish-20260926/pytest_isolated_incremental_sweep5.log  whole file -> 1 failed (3.385s)
  .fist-polish-20260926/pytest_digestcost_ordering.log     same case alone -> passed (6.12s run)
  .fist-polish-20260926/meas_digest_cost.out.txt           CPU time stable 0.39-0.42s standalone
  .fist-polish-20260926/meas_digest_gc.out.txt              CPU 0.42-0.47s under 1.5M cyclic noise;
                                                          gc.freeze() brings wall DOWN to 0.544s
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client, utc_now  # noqa: E402

FINDINGS = [
    {
        "summary": "[judge-brittleness] tests/test_incremental.py:547 TestDigestCost 用墙钟阈值 "
                   "`digest_elapsed < 2.0` 判性能，代价取决于同进程里先跑过多少用例（CPython 循环 "
                   "GC 要扫既有堆）——同一份产品代码在单跑时 0.5s、整文件跑后 3.385s，判据跨收集"
                   "顺序不可复现，把门禁 ① 变成抛硬币",
        "severity": "medium",
        "detail": (
            "现象: 终态全量 `python -m pytest tests/ -q` 从 1 红变 2 红，新增的红条是 "
            "tests/test_incremental.py::TestDigestCost::"
            "test_digest_cost_on_ten_thousand_line_module，原文 "
            "`AssertionError: digest cost too high: 3.223s`（sweep5）与 `3.385s`"
            "（只跑 tests/test_incremental.py 单文件，1 failed, 37 passed）。"
            "同一条用例单独跑（1 passed in 6.12s）与只跑 TestStructuralDigest+本用例（21 passed）"
            "都是绿的——判据结论随收集顺序翻面。\n"
            "被测量本身没有变慢：`meas_digest_cost.out.txt` 用同一份 tests/test_incremental.py "
            "里的 _large_module/parse_source/ASTDiffer 复测，1100 个顶层定义的摘要 CPU 时间 "
            "0.391/0.406/0.422s（三次），墙钟 0.510/0.530/0.708s。"
            "`meas_digest_gc.out.txt` 再把机制钉住：往同一进程灌 1.5M 个循环对象（"
            "alloc_blocks 135568→3135582）后 CPU 时间仍 0.42→0.47s 不变，墙钟 0.793→0.945s；"
            "对这些对象执行 gc.freeze()（活对象数不变）墙钟又回落到 0.544s。"
            "⇒ 超时的那 2~3s 花在 GC 扫描进程既有堆 + 被抢占（同脚本纯 CPU 校准循环 "
            "wall/cpu 比 1.28~1.40，即约三成墙钟根本不在 CPU 上），不花在 cypyc 的摘要计算上。\n"
            "定性: 产品侧 [误报]（cypyc/incremental/ast_differ.py 自 2026-09-25 16:39 未改，"
            "本轮 sweep4→sweep5 之间唯一产品改动是 cypy_bridge/nogil.py 的异常传播守卫，"
            "不在被测路径上）；判据侧 [真缺陷] → 入账本单。"
            "门禁 ① 的「全绿」因此不可复现：任何一次全量都可能因为无关用例先跑而红。\n"
            "建议（择一，都属改既有判据，交指挥官裁决，本轮不自行落地）: "
            "① 计时改用 `time.process_time()`（或取 wall 与 cpu 的较大者）并保留同量级阈值；"
            "② 计时前 `gc.collect()` 后 `gc.disable()`、并对堆做 `gc.freeze()`，"
            "使代价只随被测 AST 规模增长；③ 把该用例标 `@pytest.mark.perf` 并默认不收集，"
            "只在专用 `-m perf` 单进程运行里判；④ 把绝对阈值改成同进程内的相对比值"
            "（例如 digest 成本 / 一次 parse 成本），堆噪声自然抵消。\n"
            "本轮处置: 不修、不降阈值（红线：tests/ 只补回归不改语义；门禁只能破红线转正时交回"
            "指挥官）。终态报告按收集顺序披露，并给出上面三条可复跑证据日志。"
        ),
    },
]


def bug_id_of(row):
    return row.get("bug_id") or row.get("id")


def main() -> int:
    c = Client(timeout=120)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-intake5", "version": "1"}})

    def rows():
        return (c.call("bug_list", {"project_dir": "."}) or {}).get("bugs") or []

    before = rows()
    known = {(r.get("summary") or "").strip(): bug_id_of(r) for r in before}
    mapping, failures = [], []
    for spec in FINDINGS:
        summary = spec["summary"]
        if summary in known:
            mapping.append({"bug_id": known[summary], "task_id": None,
                            "summary": summary, "fired": False, "note": "already in ledger"})
            continue
        out = c.call("report_bug", {
            "project_dir": ".", "summary": summary, "detail": spec["detail"],
            "severity": spec["severity"], "publish_task": True,
            "reported_by": "cypy-polisher", "now": utc_now()})
        if not isinstance(out, dict) or not (out.get("bug_id") or out.get("id")):
            failures.append({"summary": summary, "reply": out})
            continue
        mapping.append({"bug_id": bug_id_of(out), "task_id": out.get("task_id"),
                        "summary": summary, "fired": True})

    after = rows()
    c.close()
    got = {(r.get("summary") or "").strip(): bug_id_of(r) for r in after}
    missing = [s["summary"] for s in FINDINGS if s["summary"] not in got]
    json.dump({"mapping": mapping, "failures": failures, "missing": missing,
               "ledger_before": len(before), "ledger_after": len(after)},
              open(os.path.join(HERE, "intake_map5.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for m in mapping:
        print(f"{m['bug_id']:8s} {str(m['task_id']):8s} fired={m['fired']} "
              f"{m['summary'][:60]}")
    print(f"ledger_before={len(before)} ledger_after={len(after)} "
          f"failures={len(failures)} missing={len(missing)}")
    return 0 if not missing and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
