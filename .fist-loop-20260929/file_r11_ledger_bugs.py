"""R11 收口腿自己踩到的四件缺陷入账（issue_up 面）：先取号，再让 `report_bug` 写台账。

与 `file_r11_bugs.py` 的三处差别都来自本轮实测（不是风格偏好）：
 · 错误行改按 `call_log.ok=0` 取数 —— 旧口径 `result_json like '%__error__%'` 恒 0，正是本次第 2 张单的内容；
 · 幂等守卫按 `reported_key` 查账本原文，已存在就只指认不重发（服务端无自清出路）；
 · 四张都是 [判据面] 前缀 ⇒ 会被引用核验计入"判据/文档面"栏，不混进产品面开口数。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "file_r11_ledger_bugs.json"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"

CARDS = [
    {
        "key": "R11-SPEC-KIND-NEEDLE-ZERO",
        "severity": "medium",
        "summary": ("[判据面·Ω-gate] 环驱动把 specs 表的 spec_type 针写成 \"omega\"/\"omega_result\"，"
                    "而库里实际只有 spec/check/result ⇒ 「已有判据就不重发」的守卫恒 0，"
                    "收口时把 12 叶已 approved 的语料重发一遍，24 条幂等拒绝被记成 refusals 使 rc=1"),
        "detail": (
            "实测（`.fist-loop-20260929/logs/r11_ring_close_a3.out` 逐字）：\n"
            " `CONCLUSION stage=close root=T0r117 root_status=已完成 rollup={'已完成': 17} non_closed=[] "
            "pending_leaves=0 calls=105 refused=24 benign=0 call_log_error_rows=0`\n"
            " —— 账其实收完了（17/17 已完成、0 支待领取），rc 却被 24 条"
            "「已通过审核，无需重复创建」/「当前状态为 [approved]，不是待审核状态」判成失败。\n"
            "机制：`run_r11_ring.py` 用 `spec_rows(node, \"omega\")==0` 当守卫，"
            "而服务端 `omega_spec_create`→'spec'、`run_check`→'check'、`omega_result_verify`→'result'"
            "（`select distinct spec_type from specs` 只有这三值；T0r117% 上分别 17/12/17 行）"
            "⇒ 守卫恒真，R10 已经观测到同型 70 条噪声却只记了现象没修针。\n"
            "修复（本轮，三件一起）：常量 `SPEC_KIND/CHECK_KIND/RESULT_KIND` 收敛口径 + 开批门新增 "
            "`spec_kind_guard()` 对着活库自证（库里有一行 specs 却缺这三个值 ⇒ 直接 refuse 收口）+ "
            "`note()` 拆成 幂等/真拒绝/良性重复 三桶，幂等单列计数并印进结论行。\n"
            "复验：同树复跑 `--stage close`（`logs/r11_ring_close_a4.out`）⇒ "
            "`calls=21 refused=0 idempotent=0 benign=0 loop_ticks_ok=6 rc=0`（幂等门从 24 掉到 0，"
            "而账的终态没变）。证据件：`logs/r11_ring_close_a3.out`、`logs/r11_ring_close_a4.out`、"
            "`ring_r11_close.json`（a4 覆写，a3 的读数只活在 .out 里 ⇒ 同名覆写已在本轮报告 §6.4 记为限制）。"),
    },
    {
        "key": "R11-CALLLOG-ERROR-NEEDLE-ZERO",
        "severity": "medium",
        "summary": ("[判据面·账面尺] 收口自证把 `call_log` 失败行按 `result_json like '%__error__%'` 计数，"
                    "而服务端失败是 `ok=0` + 纯文本回执 ⇒ 恒 0；R9/R10/R11 三份报告里"
                    "「call_log 0 错误行」这句都是坏尺读数（a3 窗口真实红行 25）"),
        "detail": (
            "实测（同一份库两个口径）：\n"
            " `select count(*) from call_log where ts>='2026-09-29T07:59:00Z' and ok=0` ⇒ 25（其中 24 条"
            "Ω-spec 幂等拒绝 + 1 条 loop_tick 参数名被拒），\n"
            " 同窗口 `result_json like '%__error__%'` ⇒ 0。\n"
            "机制：`FistClient.call` 把服务端的 JSON-RPC error 折成 `{\"__error__\": ...}` 返回给调用方，"
            "但**入库的 result_json 是纯文本回执**（`_omit_defaults` 白名单拒绝时尤其明显），"
            "所以 `%__error__%` 只能匹配到少数结构化回执，读数为 0 不代表没红。\n"
            "定性：尺子坏了而不是账面干净 —— 这一条把 R9 起「0 拒/0 错误行」的自证句整体作废，"
            "既往两轮据此写过的「benign=0 即无幂等噪声」也不再成立。\n"
            "修复：`run_r11_ring.py` 结论行改口径 `call_log_error_rows`（ok=0）并**同时**保留"
            "`call_log_error_rows_old_needle` 作对照，两数并印 ⇒ 以后任一口径漂了都能看出来。\n"
            "证据件：`logs/r11_ring_close_a3.out`、`logs/r11_loopfix_a2.out` 的 `ERROR_NEEDLES` 行、"
            "`r11_loop_tick_fix.json`。"),
    },
    {
        "key": "R11-LOOP-NEVER-TICKED",
        "severity": "medium",
        "summary": ("[判据面·组合环] 自 R9 起 `loop_tick` 在服务端一次都没成功过（57 行里 33 红，"
                    "R9-R11 的 13 条全红）⇒「本轮把组合环推进了一格」这句在账上无凭据；"
                    "两条独立成因：客户端注入 namespace/project_dir 撞白名单，以及 LoopRegistry 只在进程内"),
        "detail": (
            "实测分栏（`logs/r11_loopfix_a2.out` 的 SHAPE_CONTROL 行，逐字）：\n"
            " `{\"只传声明键\": {\"环查无\": 24, \"成功\": 24, \"键名被拒\": 0, \"其它\": 0}, "
            "\"含未声明键\": {\"键名被拒\": 10, \"成功\": 0, \"环查无\": 0, \"其它\": 0}}`\n"
            " ⇒ 注入未声明键的那一栏 10/10 全被拒（服务端 BUG-23 的白名单是真的，不是形同虚设），"
            "声明键栏 0 次键名拒绝；两栏各自解释一部分红，不能并成一个原因写。\n"
            "第二条成因：`loop_create` 自述「创建并注册到**进程内** LoopRegistry」，而 `scripts/fist.py` 每个 "
            "FistClient 都 spawn 新的 `node serve` ⇒ start 会话 create、close 会话 tick 必然 "
            "`loop not found: cypy-selfdrive-ring-r11`（本轮跨会话负控制逐字取到）。\n"
            "影响：本系列报告里凡写过「环已推进/loop_tick 已打」的句子，在服务端都没有对应状态；"
            "环的 round/max_rounds 一直是 0/6。\n"
            "修复：新增 `.fist-loop-20260929/r11_loop_drive.py`（同一会话内 create + 6×tick + status，"
            "门表 8 格逐条对表：create_ok/status_pre_ok/all_ticks_ok/status_post_ok/"
            "cross_process_negative_confirmed/round_advanced/"
            "mode_sequence_matches_declared_steps/current_idx_progression/no_early_stop），"
            "并把它接进 `run_r11_ring.py --stage close` 的收口腿。"
            "复验：`logs/r11_loopdrive_a2.out` ⇒ `ticks_ok=6/6 gates={...全 true...}`，"
            "round 0→1、next_mode 序列与登记的 steps 逐位相同、current_idx 1..5→0；"
            "换新会话查同名环 ⇒ 仍 `loop not found`（负控制成立）。"
            "自检：`--selftest` 用 8 组坏数据逐条把对应门翻红（`logs/r11_loopdrive_selftest_a1.out` "
            "`cases=8 bad=[]`）。"),
    },
    {
        "key": "R11-CLOSE-ROOT-UNBOUND",
        "severity": "low",
        "summary": ("[判据面·驱动] `run_r11_ring.py --stage close` 起手即崩："
                    "根单 id 只在 start 分支里赋值，close 分支查了 `root_row` 却不绑定 ⇒ "
                    "UnboundLocalError 且 rc=1，一条账都没写（失败形态是崩溃，不是拒绝）"),
        "detail": (
            "实测（`logs/r11_ring_close_a2.err` 逐字尾两行）：\n"
            " `File \".fist-loop-20260929/run_r11_ring.py\", line 271, in main` / "
            "`UnboundLocalError: cannot access local variable 'root_id' where it is not associated with a value`\n"
            "机制：开批门（报告在盘、引用核验 failed=0、三套终值、Ω-gate）当时已经全过，"
            "崩点在门之后的树回读；`root_row` 查询写在分支外，赋值却写在 `if args.stage == \"start\"` 里。\n"
            "定性：低危但形态难看 —— 崩溃不写回执，只看 rc 会误判成「门禁拦下了」。\n"
            "修复：close 分支改为显式绑定 `root_id`，查无根单时**拒绝并落 refused 回执**"
            "（原因逐字含 ns/前缀/parent_id 口径），绝不静默新建一棵树去凑数。"
            "复验：a3/a4 两次收口都在同一棵根上跑完（`root=T0r117 rollup={'已完成': 17} pending_leaves=0`）。"),
    },
]


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def main() -> int:
    started = utc_z()
    before = LEDGER.read_text(encoding="utf-8")
    before_ids = re.findall(r"(?m)^## (BUG-\d+)", before)
    rep = {"started_z": started, "ns": NS,
           "ledger_ids_before": [before_ids[0], before_ids[-1], len(before_ids)],
           "filed": [], "skipped_existing": [], "refusals": []}
    todo = [c for c in CARDS if c["key"] not in before]
    for c in CARDS:
        if c["key"] in before:
            rep["skipped_existing"].append({"key": c["key"], "why": "账本已含该 reported_key ⇒ 不重发"})
    if not todo:
        rep["three_way"] = "四张已全部在账，未发起任何 RPC"
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"CONCLUSION filed=0 refused=0 skipped={len(CARDS)} （幂等守卫命中）")
        return 0

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    for card in todo:
        res = c.call("report_bug", {"project_dir": ".", "summary": card["summary"],
                                    "severity": card["severity"],
                                    "detail": card["detail"] + f"\n- reported_key: {card['key']}",
                                    "reported_by": AGENT, "publish_task": False})
        rec = {"key": card["key"], "reply_verbatim": json.dumps(res, ensure_ascii=False)[:400]}
        (rep["refusals"] if refused(res) else rep["filed"]).append(rec)
    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    rep["bug_list_rows"] = len(lst) if isinstance(lst, list) else json.dumps(lst, ensure_ascii=False)[:200]
    rep["bug_list_has_new_keys"] = ({cc["summary"][:28]: any(cc["summary"][:28] in json.dumps(x, ensure_ascii=False))
                                     for cc in CARDS} if isinstance(lst, list) else "bug_list 非列表")
    c.close()

    after = LEDGER.read_text(encoding="utf-8")
    after_ids = re.findall(r"(?m)^## (BUG-\d+)", after)
    rep["ledger_ids_after"] = [after_ids[0], after_ids[-1], len(after_ids)]
    rep["new_ids"] = [i for i in after_ids if i not in before_ids]
    rep["keys_present_after"] = {card["key"]: card["key"] in after for card in CARDS}
    con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rep["call_log"] = {
        "rows": con.execute("select count(*) from call_log where ts>=?", (started,)).fetchone()[0],
        "error_rows_ok_needle": con.execute(
            "select count(*) from call_log where ts>=? and ok=0", (started,)).fetchone()[0],
        "error_rows_old_needle": con.execute(
            "select count(*) from call_log where ts>=? and result_json like '%__error__%'",
            (started,)).fetchone()[0],
        "report_bug_rows": con.execute(
            "select count(*) from call_log where ts>=? and tool='report_bug'", (started,)).fetchone()[0]}
    rep["tasks_ns_bugs_rows"] = con.execute(
        "select count(*) from tasks where ns='bugs' and created_at>=?", (started,)).fetchone()[0]
    con.close()
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rep["filed"]:
        print("FILED", r["key"], "|", r["reply_verbatim"][:220])
    for r in rep["refusals"]:
        print("REFUSED", r["key"], "|", r["reply_verbatim"][:220])
    print("NEW_IDS", json.dumps(rep["new_ids"], ensure_ascii=False))
    print("KEYS_PRESENT_AFTER", json.dumps(rep["keys_present_after"], ensure_ascii=False))
    print(f"CONCLUSION filed={len(rep['filed'])} refused={len(rep['refusals'])} skipped={len(rep['skipped_existing'])} "
          f"new_ids={len(rep['new_ids'])} headers={len(after_ids)} "
          f"call_log={json.dumps(rep['call_log'], ensure_ascii=False)}")
    return 0 if not rep["refusals"] and len(rep["filed"]) == len(rep["new_ids"]) == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
