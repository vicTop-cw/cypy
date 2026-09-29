"""R11 组合环的服务端推进腿：把 `loop_tick` 真正打一次，并留"针为什么以前恒失败"的对照。

三条来自盘面的事实（不是猜测）：
 · `loop_tick` 声明的参数只有 name / project_health_grade / blocked_tasks / current_test_count /
   current_open_bug_count，而 R9 起驱动多传了 `namespace` 与 `project_dir` ⇒ 服务端硬拒（BUG-23 那套白名单）；
   本件把这条按**参数形状**分栏统计，作为"改针就翻绿"的负控制，不新造拒绝行；
 · 驱动里的错误计数器用 `result_json like '%__error__%'` 取数，而服务端把失败写成 `ok=0` + 纯文本回执
   ⇒ 恒 0；本件同时报两个口径，并把恒 0 那个显式标成坏尺；
 · `loop_create` 只在服务端注册环名，环的轮次/next_mode 只有 tick 才会动 ⇒ 前三轮报告写的"环已推进"
   在服务端其实没推进，这一腿补上并留前后状态。
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
LOGS = HERE / "logs"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-ring-r11"
sys.path.insert(0, str(HERE))
import verify_r11_report as vr  # noqa: E402  同一份账本读取函数，不另起口径

# 客户端注入键（`scripts/fist.py` 会给每次调用补 namespace/project_dir，除非带退出键）
INJECTED = {"namespace", "project_dir"}


def cause(msg: str) -> str:
    if "参数名不被接受" in msg:
        return "键名被拒"
    if "loop not found" in msg:
        return "环查无"
    return "其它"


def measure() -> dict:
    led = vr.ledger_state()
    pytest_tail = LOGS / "r11_pytest_a2.log"
    txt = pytest_tail.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"(\d+) passed", txt)
    if not m:
        raise SystemExit("r11_pytest_a2.log 里解析不到 passed 计数 ⇒ 测试数栏无来源")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    roll = dict(con.execute("select status, count(*) from tasks where ns=? group by status", (NS,)).fetchall())
    con.close()
    return {"open_bugs": led["open"], "test_count": int(m[-1]), "task_rollup": roll,
            "blocked_tasks": roll.get("已打回", 0) + roll.get("被阻塞", 0)}


def needle_control() -> dict:
    """按（参数形状 × 失败原因）做二维对照：注入未声明键必须 100% 被拒，声明键形状下 0 次键名拒绝。

    两类失败原因分开数，不许混进同一格 —— `loop not found` 是"环名/ns 对不上"，与键名无关。
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("select params_json, result_json, ok from call_log where tool='loop_tick'").fetchall()
    con.close()
    grid = {}
    for params, res, ok in rows:
        try:
            keys = set(json.loads(params))
        except json.JSONDecodeError:
            keys = set()
        shape = "含未声明键" if keys & INJECTED else "只传声明键"
        c = cause(res or "") if not ok else "成功"
        grid.setdefault(shape, {}).setdefault(c, 0)
        grid[shape][c] += 1
    for b in grid.values():
        b.setdefault("成功", 0)
        b.setdefault("键名被拒", 0)
        b.setdefault("环查无", 0)
        b.setdefault("其它", 0)
    return grid


def control_gates(grid: dict) -> tuple[bool, list]:
    bad = []
    inj = grid.get("含未声明键", {})
    if sum(inj.values()) and inj.get("成功"):
        bad.append(f"注入未声明键仍有 {inj['成功']} 次成功 ⇒ 服务端白名单形同虚设")
    dec = grid.get("只传声明键", {})
    if dec.get("键名被拒"):
        bad.append(f"只传声明键却出现 {dec['键名被拒']} 次键名拒绝 ⇒ 归因写错了")
    if not dec.get("成功"):
        bad.append("声明键形状一次都没成功过 ⇒ '改针即翻绿'无从谈起")
    return not bad, bad


def parse_tick(res):
    blob = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
    try:
        data = json.loads(blob) if blob.strip().startswith("{") else {}
    except json.JSONDecodeError:
        data = {}
    keys = {k: data.get(k) for k in ("round", "rounds", "next_mode", "mode", "should_stop",
                                     "stop_reason", "loop_after") if k in data}
    return blob, keys


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    meas, control = measure(), needle_control()
    ok_gates, bad_gates = control_gates(control)
    rep = {"measured": meas, "shape_control": control, "control_gates": {"pass": ok_gates, "bad": bad_gates},
           "nodes": {}}
    c = fist.FistClient(timeout=240)
    for phase in ("before", "after"):
        st = c.call("loop_status", {"name": LOOP_NAME, "_omit_defaults": True})
        blob, keys = parse_tick(st)
        rep[f"loop_status_{phase}"] = {"raw": blob[:900], "picked": keys,
                                       "refused": blob.startswith("RPC-ERROR") or '"__error__"' in blob
                                       or "不被接受" in blob}
        if phase == "before":
            rep["tick"] = parse_tick(c.call("loop_tick", {
                "name": LOOP_NAME, "project_health_grade": "attention",
                "blocked_tasks": meas["blocked_tasks"], "current_test_count": meas["test_count"],
                "current_open_bug_count": meas["open_bugs"], "_omit_defaults": True}))[:2]
    c.close()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    mine = con.execute("select ts,params_json,result_json,ok from call_log where tool in "
                       "('loop_tick','loop_status') order by rowid desc limit 3").fetchall()
    rep["error_rows_two_needles"] = {
        "ok_0_needle_since_0759": con.execute(
            "select count(*) from call_log where ts>='2026-09-29T07:59:00Z' and ok=0").fetchone()[0],
        "percent_error_needle_same_window": con.execute(
            "select count(*) from call_log where ts>='2026-09-29T07:59:00Z' "
            "and result_json like '%__error__%'").fetchone()[0],
        "newest_three_rows": [[r[0], r[3], r[2][:120]] for r in mine]}
    con.close()

    tick_blob, tick_pick = rep["tick"]
    tick_refused = tick_blob.startswith("RPC-ERROR") or "不被接受" in tick_blob or '"__error__"' in tick_blob \
        or "loop not found" in tick_blob
    b_state, a_state = rep["loop_status_before"]["picked"], rep["loop_status_after"]["picked"]
    # 只比语义字段：整份 raw 里若有 ts，"变了"就是恒真判据
    moved = bool(b_state) and bool(a_state) and b_state != a_state
    rep["tick_refused"], rep["state_moved"], rep["state_unmeasurable"] = tick_refused, moved, not (b_state or a_state)
    (HERE / "r11_loop_tick_fix.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print("MEASURED", json.dumps(meas, ensure_ascii=False))
    print("SHAPE_CONTROL", json.dumps(control, ensure_ascii=False))
    print("GATES", json.dumps({"pass": ok_gates, "bad": bad_gates}, ensure_ascii=False))
    print("TICK", tick_blob[:300])
    print("TICK_PICKED", json.dumps(tick_pick, ensure_ascii=False))
    for phase in ("before", "after"):
        print(f"LOOP_STATUS_{phase}", json.dumps(rep[f"loop_status_{phase}"]["picked"], ensure_ascii=False),
              "refused=", rep[f"loop_status_{phase}"]["refused"])
    print("ERROR_NEEDLES", json.dumps(rep["error_rows_two_needles"], ensure_ascii=False)[:400])
    print(f"CONCLUSION stage=loop_tick tick_refused={tick_refused} state_moved={moved} "
          f"shape_control_ok={ok_gates} control_bad={json.dumps(bad_gates, ensure_ascii=False)} "
          f"evidence=r11_loop_tick_fix.json")
    return 0 if (ok_gates and not tick_refused and moved) else 1


if __name__ == "__main__":
    sys.exit(main())
