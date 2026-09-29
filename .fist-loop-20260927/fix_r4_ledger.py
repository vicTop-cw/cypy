"""账面闭环：本环修掉的六张单逐张走 claim→execute→submit→verify，并把 FIXED 段追加进 md 账本。

bug 单没有关闭 API，Omega 三连对它们也不可用（`report_bug` 发的单没有 `[omega:required]`），
所以闭环强度落在三件事上：**任务库终态**、**md 追加留档**、**call_log 里真有这些调用**（三向对照）。
幂等：已经有 FIXED 段的条目不再重复驱动（重复跑会多出第二条 FIXED 与第二条调用记录）。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

LEDGER = ROOT / "memory" / "bugs.md"
DB = (ROOT / "fist-mbt.db").as_posix()
OUT = HERE / "fix_r4_ledger.json"
NS = "cypy-loop-20260927"
CARDS = {
    "RC1_func_symbol_typed_as_return": {
        "files": "`cypyc/analyzer/type_checker.py`（新增 `callable_sigs` 签名表与 `_register_callable`）",
        "locks": "`tests/test_loop_20260927_fix_r4.py::test_fixture_matches_declared_expectation`"
                 " 的 C01..C05 五条 + `test_call_face_reports_over_cli`（CLI 调用面）",
        "evidence": ".fist-loop-20260927/fix_r4_locks.json（修前 14 红→修后全绿）、"
                    "fix_r4_revert.json（摘掉 `_register_callable` 后该族锁必红）"},
    "RC2_no_argument_type_check": {
        "files": "`cypyc/analyzer/type_checker.py`（`_callable_arg_mismatch` 与 "
                 "`_check_callable_arg_types`，判定入口只有这一个）",
        "locks": "同上 C06..C08，外加对照 `test_arg_type_control_on_dynamic_value_stays_silent`"
                 "（动态值不得误报）",
        "evidence": "fix_r4_impact.json（203 档语料：新增诊断 0、消失诊断 0）"},
    "RC3_struct_field_type_unresolved": {
        "files": "`cypyc/analyzer/type_checker.py`（`self` 绑定不再被 object 覆盖；"
                 "属性位 Callable 复用同一套判定；成员未知时返回 object 而不是 None）",
        "locks": "同上 C09..C11 + 对照 `test_fixture_matches_declared_expectation[C09_ctl]`",
        "evidence": "fix_r4_revert.json（RC3 摘除 ⇒ C09/C10/C11 红）"},
    "RC4_internal_repr_in_message": {
        "files": "`cypyc/analyzer/type_checker.py`（`_type_display` 显示层 + `_mismatch` 统一出口）",
        "locks": "C12 与横向锁 `test_no_internal_repr_leaks_in_any_fixture_message`",
        "evidence": "fix_r4_revert.json（RC4 摘除 ⇒ C12 红）"},
    "DOC_cli_face_mismatch": {
        "files": "`docs/USAGE.md`（Python 下限、hook 选项清单、入口点三处按实读改写）",
        "locks": ".fist-loop-20260927/fix_r4_docs.json 的 D08/D09/D10 三行 + "
                 "反向对照「实现里没有的 `--incremental` 不得出现在文档」",
        "evidence": "fix_r4_docs.json（verdict 全 agreed）；"
                    "**half-open**：`SYNTAX/appendix-C-features.md` 的 `cypyc --compile` 行属冻结面，"
                    "本轮只读不动（frozen_control 探针证明它仍然 stale）"},
    "DOC_example_fails": {
        "files": "`docs/USAGE.md`（构建示例改引用真实字段 `pyd_paths`；eval 示例不再承诺返回 42）",
        "locks": "fix_r4_docs.json 的 D11/D12 两行",
        "evidence": "fix_r4_docs.json；**half-open**：`hook.eval` 的写侧从不产出 `__result__`"
                    "（生成侧缺口，改它超出本单授权）⇒ 转结"},
}
REFUSE: list = []


def sha_ok() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def block_span(text: str, key: str):
    """按根因键定位账本条目：从 `## BUG-nn` 标题到下一条标题（或文件尾）。

    两处（追加前 / 追加后自证）必须用**同一个**定位函数 —— 否则追加成功而自证用另一个
    更窄的窗口去够 FIXED 段，会把真留档读成没留档（BUG-61 条目 261 行，固定字符窗必输）。
    """
    return re.search(r"^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN\n- summary: \["
                     + re.escape(key) + r"\].*?(?=^## BUG-|\Z)", text, re.M | re.S)


def card_body(key: str, task_id: str, status: str, updated: str) -> str:
    c = CARDS[key]
    return ("\n### FIXED(verify=" + status + ") — 2026-09-28 R4-修复 追加留档"
            "（本条目正文与标题行 `OPEN` 一字未改）\n\n"
            "- 修复任务：`" + task_id + "`（ns `bugs`，库里 `status=" + status + "`、"
            "`updated_at=" + updated + "`、`completed_by=cypy-fixer`）\n"
            "- 改动文件：" + c["files"] + "\n"
            "- 锁死回归：" + c["locks"] + "\n"
            "- 闭环证据：" + c["evidence"] + "\n"
            "- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，"
            "标题行的 `OPEN` 不改写，也不据此判定门禁已绿。\n")


def check_main() -> int:
    """只读复核（不改账本、不调客户端）：驱动件落盘后驱动本身若被再格式化，就靠这一格自证。

    上一环的教训是"绿灯不能跨时间抵扣"：`fix_r4_ledger.json` 是格式化**之前**那版驱动跑出来的，
    所以盘上现状必须独立重读一遍，而不是引用旧件。
    """
    md = LEDGER.read_text(encoding="utf-8")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    for key in sorted(CARDS):
        tids = [tid for tid, desc in con.execute(
            "select id, description from tasks where ns='bugs'")
            if "[" + key + "]" in (desc or "")]
        tid = tids[0] if len(tids) == 1 else ""
        st = con.execute("select status, completed_by from tasks where id=?", (tid,)).fetchone() \
            if tid else None
        calls = con.execute(
            "select count(*) from call_log where tool in ('claim','execute','submit','verify') "
            "and params_json like ?", ('%"' + tid + '"%',)).fetchone()[0] if tid else 0
        blk = block_span(md, key)
        rows.append({
            "key": key, "task_id": tid, "cards_matched": len(tids),
            "status": (st[0] if st else ""), "completed_by": (st[1] if st else ""),
            "md_fixed": bool(blk) and "### FIXED(verify=已完成)" in blk.group(0),
            "call_log_rows": calls})
    con.close()
    bad = [r for r in rows if not (r["cards_matched"] == 1 and r["status"] == "已完成"
                                   and r["completed_by"] == "cypy-fixer"
                                   and r["md_fixed"] and r["call_log_rows"] >= 4)]
    here = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    doc = {"mode": "check", "rows": rows, "total": len(rows), "agree_total": len(rows) - len(bad),
           "driving_artifact_at": here.get("started", ""),
           "driving_artifact_agree": here.get("agree_total"),
           "refuse": sorted(set(REFUSE)) + [f"只读复核不一致：{json.dumps(bad, ensure_ascii=False)}"]
           if bad else sorted(set(REFUSE)),
           "note": "check 态只读 sqlite 与 md、只调 count(*) ⇒ 不产生新调用、不追加留档",
           "at_utc": sha_ok()}
    (HERE / "fix_r4_ledger_check.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "agree_total": doc["agree_total"],
                      "total": doc["total"],
                      "rows": [(r["key"], r["task_id"], r["status"], r["md_fixed"],
                                r["call_log_rows"]) for r in rows]},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check_main()
    started = sha_ok()
    md = LEDGER.read_text(encoding="utf-8")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bug_rows = {r[0]: r[1] for r in con.execute(
        "select id, description from tasks where ns='bugs'")}
    con.close()
    by_key = {}
    for tid, desc in bug_rows.items():
        for key in CARDS:
            if "[" + key + "]" in (desc or ""):
                by_key.setdefault(key, []).append(tid)
    missing = [k for k, v in by_key.items() if len(v) != 1]
    if missing or len(by_key) != len(CARDS):
        REFUSE.append(f"bug 任务与根因键对不上：找到 {len(by_key)}/{len(CARDS)}，多对 {missing}")

    if "R4-修复 追加留档" in md:
        print(json.dumps(
            {"refuse": ["账本里已有 R4-修复 的 FIXED 段 ⇒ 拒绝重复驱动与重复追加"
             "（幂等门）"]},
            ensure_ascii=False))
        return 1

    client = lfist_lib.Client(timeout=180)
    results = []
    for key, tids in sorted(by_key.items()):
        tid = tids[0]
        con = sqlite3.connect(f"file:{DB}", uri=True)
        st = con.execute("select status, updated_at from tasks where id=?", (tid,)).fetchone()
        con.close()
        steps = []
        if st[0] != "已完成":
            calls = [
                ("claim", {"task_id": tid, "assignee": "cypy-fixer", "now": sha_ok()}),
                ("execute", {"task_id": tid, "now": sha_ok(),
                             "deliverable": f"修 {key}：改动 {CARDS[key]['files']}；"
                                            f"锁与回退矩阵 {CARDS[key]['evidence']}"}),
                ("submit", {"task_id": tid, "now": sha_ok()}),
                ("verify", {"task_id": tid, "now": sha_ok(), "verifier": "cypy-fixer"}),
            ]
            for call, args in calls:
                r = client.call(call, args)
                err = r.get("error") if isinstance(r, dict) else None
                steps.append({"call": call, "ok": not err,
                              "echo": (json.dumps(r, ensure_ascii=False)[:180]
                                       if isinstance(r, dict) else str(r)[:180])})
        else:
            steps.append({"call": "skip", "ok": True, "echo": f"库里已是 {st[0]}"})
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        final = con.execute("select status, updated_at, completed_by from tasks where id=?",
                            (tid,)).fetchone()
        con.close()
        if final[0] != "已完成":
            REFUSE.append(f"{tid}（{key}）没驱动到已完成：{json.dumps(steps, ensure_ascii=False)[:300]}")
        results.append({"root_cause_key": key, "task_id": tid, "steps": steps,
                        "final_status": final[0], "completed_by": final[2]})

    appended = []
    for res in results:
        m = block_span(md, res["root_cause_key"])
        if not m:
            REFUSE.append(f"账本里找不到 {res['root_cause_key']} 的条目 ⇒ 不追加")
            continue
        block = m.group(0)
        if "### FIXED" in block:
            appended.append({"key": res["root_cause_key"], "appended": False,
                             "why": "该条目已有 FIXED 段（历史留档），不叠加"})
            continue
        insert_at = m.end(0)
        md = (md[:insert_at].rstrip("\n") + "\n"
              + card_body(res["root_cause_key"], res["task_id"], res["final_status"],
                          datetime.datetime.now(datetime.timezone.utc)
                          .isoformat(timespec="seconds"))
              + "\n" + md[insert_at:].lstrip("\n"))
        appended.append({"key": res["root_cause_key"], "appended": True, "why": ""})
    LEDGER.write_text(md, encoding="utf-8", newline="\n")

    # 三向对照：md 的 FIXED 段 / sqlite 终态 / call_log 里本环真的调过
    md_after = LEDGER.read_text(encoding="utf-8")
    three = []
    logs = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    for res in results:
        blk = block_span(md_after, res["root_cause_key"])
        block_text = blk.group(0) if blk else ""
        has_md = bool(block_text) and ("### FIXED(verify=已完成)" in block_text)
        calls = logs.execute(
            "select count(*) from call_log where tool in "
            "('claim','execute','submit','verify') and params_json like ?",
            ('%"' + res["task_id"] + '"%',)).fetchone()[0]
        three.append({"key": res["root_cause_key"], "md_fixed": has_md,
                      "sqlite_done": res["final_status"] == "已完成", "call_log_rows": calls})
    logs.close()
    bad = [t for t in three if not (t["md_fixed"] and t["sqlite_done"] and t["call_log_rows"] >= 3)]
    if bad:
        REFUSE.append(f"三向对照不一致：{json.dumps(bad, ensure_ascii=False)[:400]}")
    # 每条都必须能被同一个定位函数找到，且新段前有整行空行（隐形标题事故 #55：粘住就不是标题）
    glued = []
    for res in results:
        blk = block_span(md_after, res["root_cause_key"])
        if not blk or not re.search(r"\n\n### FIXED\(verify=已完成\)", blk.group(0)):
            glued.append(res["root_cause_key"])
    if glued:
        REFUSE.append(f"FIXED 段粘连或缺段：{glued}")
    doc = {"started": started, "cards": results, "appended": appended,
           "agree": [t for t in three if t not in bad], "agree_total": len(three) - len(bad),
           "three_way": three, "ledger_total": len(re.findall(r"^## BUG-\d+", md_after, re.M)),
           "note": "bug 单没有 [omega:required] ⇒ Omega 三连对它不可用（既定语义），"
                   "闭环强度在锁 + 回退矩阵 + 影响面三件判据上",
           "refuse": sorted(set(REFUSE)), "at_utc": sha_ok()}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(
        {"refuse": doc["refuse"], "agree": doc["agree_total"],
         "ledger_total": doc["ledger_total"],
         "cards": [(c["root_cause_key"], c["task_id"], c["final_status"])
                   for c in results]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
