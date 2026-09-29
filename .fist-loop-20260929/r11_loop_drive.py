"""R11 组合环的服务端推进腿：在**同一个** RPC 会话里 create + tick×6 + status，并留跨会话失效的对照。

为什么要单独写这一件（不是补仪式感，是上一轮的账面主张站不住）：
 · `loop_create` 的自述是"创建并注册到**进程内** LoopRegistry"，而 `scripts/fist.py` 每个 FistClient
   都 spawn 一个新的 `node serve` ⇒ 上一轮 create 与本轮 tick 落在两个进程里，tick 必然 `loop not found`；
   R9-R11 的报告据此写的"环已推进"在服务端其实一格都没落，而驱动里的错误计数器（`%__error__%`）恒 0，
   把这个洞盖住了（真实口径是 `call_log.ok=0`）。
 · 另一半原因是键名：客户端会给每次调用注入 `namespace`/`project_dir`，而 loop_* 只声明了自己的参数集，
   服务端按 BUG-23 口径硬拒 ⇒ 必须带 `_omit_defaults` 退出键。两者各自能独立解释一部分红，故分开取证。
本件的负控制：会话内 tick 必成功；换新会话后同一环名必 `loop not found` —— 两条一起才说明"这是进程内状态"，
而不是"我的针又写歪了"。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-ring-r11"
STEPS = ["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"]
sys.path.insert(0, str(HERE))
import verify_r11_report as vr  # noqa: E402

CURRENT_LOG = HERE / "logs" / "r11_pytest_a2.log"


def recorded_create() -> dict:
    """回放依据从账上取：用上一笔成功的 loop_create 参数，不手敲基线数。"""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("select params_json from call_log where tool='loop_create' and ok=1 and params_json like ? "
                      "order by rowid desc limit 1", (f'%{LOOP_NAME}%',)).fetchone()
    con.close()
    if not row:
        raise SystemExit("账上查无本环成功的 loop_create 参数 ⇒ 基线数无来源，拒绝手填")
    return json.loads(row[0])


def measure() -> dict:
    led = vr.ledger_state()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    roll = dict(con.execute("select status, count(*) from tasks where ns=? group by status", (NS,)).fetchall())
    con.close()
    hits = re.findall(r"(\d+) passed", CURRENT_LOG.read_text(encoding="utf-8", errors="replace"))
    if not hits:
        raise SystemExit("r11_pytest_a2.log 解析不到 passed 计数 ⇒ current_test_count 无来源")
    return {"project_health_grade": "attention", "blocked_tasks": roll.get("已打回", 0) + roll.get("被阻塞", 0),
            "current_test_count": int(hits[-1]), "current_open_bug_count": led["open"]}


def is_err(res) -> tuple[bool, str]:
    blob = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
    return (blob.startswith("RPC-ERROR") or '"__error__"' in blob or "不被接受" in blob
            or "loop not found" in blob), blob


def pick(blob: str) -> dict:
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    keys = ("round", "rounds", "step", "mode", "next_mode", "should_stop", "stop_reason",
            "loop_after", "max_rounds", "completed_rounds", "ticks", "history")
    out = {k: data[k] for k in keys if k in data}
    return out or {"unparsed_keys": sorted(data)[:12]}


def gate_table(create_refused, pre_refused, post_refused, ticks, pre_round, post_round,
               cross_refused, steps) -> dict:
    seq = [s["picked"].get("next_mode") for s in ticks]
    idx_seq = [(s["picked"].get("loop_after") or {}).get("current_idx") for s in ticks]
    return {
        "create_ok": not create_refused,
        "status_pre_ok": not pre_refused,
        "all_ticks_ok": len([t for t in ticks if not t["refused"]]) == len(steps),
        "status_post_ok": not post_refused,
        "cross_process_negative_confirmed": cross_refused,
        # 逐条比语义格（不比整份 raw：raw 里有 created_at，"变了"会恒真）
        "round_advanced": pre_round is not None and post_round == pre_round + 1,
        "mode_sequence_matches_declared_steps": seq == list(steps),
        "current_idx_progression": idx_seq == list(range(1, len(steps))) + [0],
        "no_early_stop": all(t["picked"].get("should_stop") is False and t["picked"].get("stop_reason") == ""
                             for t in ticks),
    }


def _tick(mode, idx, refused=False, should_stop=False, reason=""):
    return {"refused": refused,
            "picked": {"next_mode": mode, "should_stop": should_stop, "stop_reason": reason,
                       "loop_after": {"current_idx": idx}}}


def selftest() -> int:
    """每道语义门都要被坏数据翻红一次，否则它只是在给自己念好话。"""
    good_ticks = [_tick(m, i + 1) for i, m in enumerate(STEPS)]
    good_ticks[-1]["picked"]["loop_after"]["current_idx"] = 0
    base = gate_table(False, False, False, good_ticks, 0, 1, True, STEPS)
    mutations = [
        ("round 不前进", dict(post_round=0), "round_advanced"),
        ("少 tick 一次", dict(ticks=good_ticks[:-1]), "all_ticks_ok"),
        ("mode 序列打乱", dict(ticks=[_tick(m, i + 1) for i, m in enumerate(reversed(STEPS))]),
         "mode_sequence_matches_declared_steps"),
        ("服务端叫停", dict(ticks=[_tick(m, i + 1, should_stop=True, reason="goal")
                                for i, m in enumerate(STEPS)]), "no_early_stop"),
        ("单次 tick 被拒", dict(ticks=[good_ticks[0], _tick("bugfind", 2, refused=True), *good_ticks[2:]]),
         "all_ticks_ok"),
        ("跨会话竟查得到", dict(cross=False), "cross_process_negative_confirmed"),
        ("create 被拒", dict(create=True), "create_ok"),
        ("status 前后任一回执被拒", dict(pre=True), "status_pre_ok"),
    ]
    bad = []
    for name, over, gate in mutations:
        t = dict(ticks=good_ticks, post_round=1, cross=True, create=False, pre=False)
        t.update(over)
        got = gate_table(t["create"], t["pre"], False, t["ticks"], 0, t["post_round"], t["cross"], STEPS)
        if got[gate]:
            bad.append(f"{name} 未翻红")
    if not all(base.values()):
        bad.append("基线（应有的好数据）本身没过门")
    print("GATES_GOOD", json.dumps(base, ensure_ascii=False))
    print(f"CONCLUSION stage=selftest cases={len(mutations)} bad={json.dumps(bad, ensure_ascii=False)}")
    return 0 if not bad else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    base = recorded_create()
    if list(base.get("steps") or []) != STEPS:
        # 步进序列要和账上登记的一致，否则"6 步走完一轮"这句是我编的
        raise SystemExit(f"账上 steps 与本件 STEPS 不一致：{base.get('steps')} != {STEPS}")
    meas = measure()
    rep = {"loop": LOOP_NAME, "replayed_create_params": base, "tick_args": meas, "steps": []}

    c = fist.FistClient(timeout=240)
    err, blob = is_err(c.call("loop_create", {**{k: base[k] for k in
                                                 ("name", "steps", "max_rounds", "baseline_test_count",
                                                  "baseline_open_bug_count", "stop_on_goal", "stop_on_exceeded")
                                                 if k in base}, "_omit_defaults": True}))
    rep["create"] = {"refused": err, "raw": blob[:300]}
    pre = is_err(c.call("loop_status", {"name": LOOP_NAME, "_omit_defaults": True}))
    rep["status_pre"] = {"refused": pre[0], "picked": pick(pre[1])}
    for i, step in enumerate(STEPS, 1):
        err, blob = is_err(c.call("loop_tick", {**meas, "name": LOOP_NAME, "_omit_defaults": True}))
        rep["steps"].append({"i": i, "expect_mode": step, "refused": err, "picked": pick(blob),
                             "raw": blob[:400] if err else ""})
    err, blob = is_err(c.call("loop_status", {"name": LOOP_NAME, "_omit_defaults": True}))
    rep["status_post"] = {"refused": err, "picked": pick(blob), "raw": blob[:1200] if err else ""}
    c.close()

    # 负控制：换新进程（新 FistClient 会再 spawn 一个 serve）后同一环名必须查无 ⇒ 证实"进程内"
    c2 = fist.FistClient(timeout=120)
    err2, blob2 = is_err(c2.call("loop_status", {"name": LOOP_NAME, "_omit_defaults": True}))
    c2.close()
    rep["cross_process_negative"] = {"refused_as_expected": err2, "raw": blob2[:220]}

    ticks_ok = [s for s in rep["steps"] if not s["refused"]]
    seq = [s["picked"].get("next_mode") for s in rep["steps"]]
    idx_seq = [(s["picked"].get("loop_after") or {}).get("current_idx") for s in rep["steps"]]
    pre_round, post_round = rep["status_pre"]["picked"].get("round"), rep["status_post"]["picked"].get("round")
    # 门只有一处实现：自检件的坏数据走的就是这张表
    gates = gate_table(rep["create"]["refused"], rep["status_pre"]["refused"],
                       rep["status_post"]["refused"], rep["steps"], pre_round, post_round,
                       rep["cross_process_negative"]["refused_as_expected"], STEPS)
    rep["gates"] = gates
    rep["observed"] = {"pre_round": pre_round, "post_round": post_round, "next_mode_seq": seq,
                       "current_idx_seq": idx_seq,
                       "tick_args": meas, "create_params_replayed": {k: base[k] for k in base if k != "steps"}}
    (HERE / "r11_loop_drive.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CREATE", json.dumps(rep["create"], ensure_ascii=False)[:300])
    print("STATUS_PRE", json.dumps(rep["status_pre"], ensure_ascii=False)[:400])
    for s in rep["steps"]:
        print(f"TICK {s['i']}/{s['expect_mode']}", "refused=" + str(s["refused"]),
              json.dumps(s["picked"], ensure_ascii=False)[:300], s["raw"][:160])
    print("STATUS_POST", json.dumps(rep["status_post"], ensure_ascii=False)[:900])
    print("CROSS_PROC", json.dumps(rep["cross_process_negative"], ensure_ascii=False)[:260])
    print(f"CONCLUSION stage=loop_drive ticks_ok={len(ticks_ok)}/{len(STEPS)} "
          f"gates={json.dumps(gates, ensure_ascii=False)} evidence=r11_loop_drive.json")
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
