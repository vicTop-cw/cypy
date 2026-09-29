"""R5-修复 的 call_log 对账：按 `params_json.task_id` 前缀分组数，不按标签、不按回忆。

三条自证（缺一条这栏就是装饰）：
① 每个前缀的逐工具计数之和 == 该前缀总行数（分组不许吞行）；
② `refused` 计数 == `refused_detail` 条数（拒收清单不是手数出来的）；
③ 拿一个**必然不存在**的前缀当对照，必须数出 0 行——否则这个过滤是恒真的。
另开一栏如实回答"规格点名的工具在这个 build 里到底存不存在"：`laya`/`issue_up` 若在 call_log
里 0 命中，就不许假装开过，要写明等价能力由哪一步承担。
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = (ROOT / "fist-mbt.db").as_posix()
PREFIXES = {"T0r110": "R5-修复（16 叶 × omega 全链 + 8 支 + 根上卷）"}
NEEDLE_ABSENT = "T0r9ZZZ-not-a-task"
NAMED_TOOLS = [
    "laya",
    "issue_up",
    "omega_spec_create",
    "omega_result_verify",
    "report_bug",
    "output_validate",
    "submit",
    "claim",
    "verify",
]
# 规格点名的工具名在本 build 里不一定存在——承担同一能力的是这些实际工具名
CARRIERS = {
    "laya": ["laya_decide"],
    "issue_up": ["publish", "report_bug"],
    "call_log": ["call_log"],
}
STAGE_SEED = "%[loop:20260927-loop:R4-%"
OUT = HERE / "fix_r5_calllog_tally.json"
PLAN = HERE / "spec_r5_fix.json"
ROOT_ID = "T0r110"
NS = "cypy-loop-20260927"
HUNT_ROOT = "T0r96"
# `laya_decide`/`publish`/`report_bug` 的 params 里没有 task_id，只有环标签 ⇒
# 按前缀数它们必然数到 0。0 不是"没开过"，是过滤器看不见；这一栏按标签现数，
# 并配一个必然不存在的标签当对照。
TAG_ABSENT = "%[loop:20260927-loop:R9-不存在的环]%"
# 本环根描述里没有环标签（发布时未拼进去，已作为失效条目入账），所以标签档对本环恒 0 行。
# 换一条同样「来自盘上、不是我记得」的指纹：根任务 description 的首行。
FINGERPRINT_ABSENT = "修复（fix）R5-不存在的环首行"


def esc_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def main() -> int:
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    refuse = []
    total_all = con.execute("select count(*) from call_log").fetchone()[0]
    stages = {}
    for prefix, label in PREFIXES.items():
        rows = list(
            con.execute(
                "select tool, ok, ts, params_json, result_json from call_log "
                "where json_extract(params_json,'$.task_id') like ? order by id",
                (f"{prefix}%",),
            )
        )
        by_tool, refused_detail, leaf_ids = {}, [], set()
        for tool, ok, ts, params, result in rows:
            try:
                pj = json.loads(params)
            except (TypeError, json.JSONDecodeError):
                pj = {}
                refused_detail.append(f"{prefix}: params_json 不是合法 JSON（{ts}）")
            tid = pj.get("task_id") or "?"
            leaf_ids.add(tid)
            slot = by_tool.setdefault(tool, {"ok": 0, "refused": 0})
            slot["ok" if ok else "refused"] += 1
            if not ok:
                refused_detail.append(
                    {"task": tid, "tool": tool, "ts": ts, "err": (result or "")[:500]}
                )
        summed = sum(v["ok"] + v["refused"] for v in by_tool.values())
        if summed != len(rows):
            refuse.append(f"{prefix}：逐工具合计 {summed} ≠ 该前缀行数 {len(rows)} ⇒ 分组吞了行")
        # 号段在 ns `bugs` 里可能撞车（bug 卡也占 T0rNN 空间），按 ns 收窄后必须同数
        ns_rows = con.execute(
            "select count(*) from call_log where json_extract(params_json,'$.task_id') like ? "
            "and json_extract(params_json,'$.task_id') in (select id from tasks where ns=?)",
            (f"{prefix}%", NS),
        ).fetchone()[0]
        if ns_rows != len(rows):
            refuse.append(
                f"{prefix}：号段前缀 {len(rows)} 行里有 {len(rows) - ns_rows} 行不属于 ns {NS}"
                "⇒ 号段撞车，前缀档不可信"
            )
        n_refused = sum(v["refused"] for v in by_tool.values())
        structured = [d for d in refused_detail if isinstance(d, dict)]
        if n_refused != len(structured):
            refuse.append(f"{prefix}：refused 计数 {n_refused} ≠ 明细条数 {len(structured)}")
        stages[prefix] = {
            "label": label,
            "rows": len(rows),
            "rows_ns_scoped": ns_rows,
            "ns": NS,
            "distinct_tasks": len(leaf_ids),
            "by_tool": by_tool,
            "refused": n_refused,
            "refused_total": n_refused,
            "refused_detail": refused_detail,
        }
    # 环种子那一档：laya/publish/report_bug 的 params 里没有 task_id，只按前缀数必然数到 0
    seed_rows = list(
        con.execute(
            "select tool, ok, ts, substr(result_json,1,300) from call_log "
            "where params_json like ? order by id",
            (STAGE_SEED,),
        )
    )
    seed_by_tool = {}
    for tool, ok, ts, result in seed_rows:
        slot = seed_by_tool.setdefault(tool, {"ok": 0, "refused": 0, "examples": []})
        slot["ok" if ok else "refused"] += 1
        if not ok and len(slot["examples"]) < 3:
            slot["examples"].append({"ts": ts, "err": result})
    ring_tag = (json.loads(PLAN.read_text(encoding="utf-8")) or {}).get("tag") or ""
    if not ring_tag:
        refuse.append("spec_r5_fix.json 没有 tag 字段 ⇒ 按标签数出来的东西没有出处")
    tag_rows = list(
        con.execute(
            "select tool, ok, ts, "
            "case when json_valid(params_json) then json_extract(params_json,'$.summary') "
            "else null end, "
            "substr(result_json,1,600) from call_log where params_json like ? order by id",
            (f"%{ring_tag}%",),
        )
    )
    tag_ok = sum(1 for r in tag_rows if r[1])
    tag_refused = sum(1 for r in tag_rows if not r[1])
    tag_by_tool, tag_refused_detail = {}, []
    for tool, ok, ts, summary, result in tag_rows:
        slot = tag_by_tool.setdefault(tool, {"ok": 0, "refused": 0})
        slot["ok" if ok else "refused"] += 1
        if not ok:
            tag_refused_detail.append(
                {"tool": tool, "ts": ts, "who": summary or "(params 无 summary)", "err": result}
            )
    tag_absent_rows = con.execute(
        "select count(*) from call_log where params_json like ?", (TAG_ABSENT,)
    ).fetchone()[0]
    # ── 指纹档：本环根任务 description 的首行，从 tasks 表现读（不是手打的needle）
    root_row = con.execute(
        "select description, created_at from tasks where ns=? and id=?", (NS, ROOT_ID)
    ).fetchone()
    hunt_row = con.execute(
        "select created_at from tasks where ns=? and id=?", (NS, HUNT_ROOT)
    ).fetchone()
    if not root_row:
        refuse.append(f"tasks 表里没有 {NS}/{ROOT_ID} ⇒ 指纹档没有出处，只能记 not_measured")
        finger = ""
    else:
        finger = (root_row[0] or "").splitlines()[0].strip()[:60]
    fix_start = root_row[1] if root_row else ""
    hunt_start = hunt_row[0] if hunt_row else ""
    fp_rows = (
        list(
            con.execute(
                "select id, tool, ok, ts, substr(result_json,1,400) from call_log "
                "where instr(params_json, ?) > 0 order by id",
                (finger,),
            )
        )
        if finger
        else []
    )
    fp_by_tool: dict = {}
    for rid, tool, ok, ts, result in fp_rows:
        slot = fp_by_tool.setdefault(tool, {"ok": 0, "refused": 0, "row_ids": [], "errs": []})
        slot["ok" if ok else "refused"] += 1
        slot["row_ids"].append(rid)
        if not ok and len(slot["errs"]) < 3:
            slot["errs"].append({"id": rid, "ts": ts, "err": result})
    dead_needle_rows = con.execute(
        "select count(*) from call_log where instr(params_json, ?) > 0", (FINGERPRINT_ABSENT,)
    ).fetchone()[0]

    def win(tool: str, since: str, until: str = "") -> int:
        if not since:
            return -1
        q = "select count(*) from call_log where tool=? and ts>=?"
        a: list = [tool, since]
        if until:
            q += " and ts<?"
            a.append(until)
        return con.execute(q, a).fetchone()[0]

    def chan_total(tool: str) -> int:
        slot = fp_by_tool.get(tool, {})
        return int(slot.get("ok", 0)) + int(slot.get("refused", 0))

    laya_fp, pub_fp, rb_fp = (
        chan_total("laya_decide"),
        chan_total("publish"),
        chan_total("report_bug"),
    )
    laya_win = win("laya_decide", fix_start)
    laya_ok = fp_by_tool.get("laya_decide", {}).get("ok", 0)
    pub_win = win("publish", fix_start)
    rb_win = win("report_bug", fix_start)
    rb_hunt = win("report_bug", hunt_start, fix_start)
    # 立单调用不带根描述首行 ⇒ 指纹档对它天生 0 行；改用「卡片 detail 来历行里的环标签」当第二路，
    # 再拿入账件自己记的 call_log 增量当第三路（三路同源才算数）。
    rb_tag_slot = tag_by_tool.get("report_bug", {"ok": 0, "refused": 0})
    rb_tag = rb_tag_slot["ok"] + rb_tag_slot["refused"]
    book_p = HERE / "fix_r5_book91.json"
    book_delta = -1
    if book_p.exists():
        pair = json.loads(book_p.read_text(encoding="utf-8")).get("calllog_report_bug") or []
        book_delta = int(pair[1]) - int(pair[0]) if len(pair) == 2 else -1
    fingerprint_channel = {
        "needle_source": f"tasks(ns={NS}, id={ROOT_ID}).description 首行（现读）",
        "needle": finger,
        "rows": len(fp_rows),
        "row_ids": [r[0] for r in fp_rows],
        "by_tool": fp_by_tool,
        "absent_control_rows": dead_needle_rows,
        "windows": {
            "fix_start_utc": fix_start,
            "hunt_start_utc": hunt_start,
            "laya_decide": laya_win,
            "publish": pub_win,
            "report_bug_this_ring": rb_win,
            "report_bug_hunt_ring": rb_hunt,
            "report_bug_tag_channel": rb_tag,
            "report_bug_book_delta": book_delta,
        },
        "note": "本环根描述里既没有环标签也没有 [omega:required]（发布时未拼进去），"
        "所以标签档对本环恒 0 行是**过滤器看不见**而不是没开过；指纹档用根描述首行把 "
        "laya_decide / publish 数出来，并按 ts 窗口独立复算第二路。"
        "report_bug 的 params 里没有根描述首行（立单只带 summary/detail），指纹档对它天生数不到，"
        "这一路改按「环标签写在卡片 detail 的来历行里」来对：标签档与 ts 窗口档必须同数。"
        "本环修复途中新立了一张单（BUG-91），所以『修复环 0 次』那句旧口径已作废。",
    }
    carriers = {}
    # 真打一次客户端的 call_log 工具：自读 sqlite 不等于『开过 call_log』
    call = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(HERE / "lfist.py"),
            "call_log",
            json.dumps(
                {"limit": 2500, "namespace": "cypy-loop-20260927", "project_dir": "."},
                ensure_ascii=False,
            ),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    client_rows, client_err = None, ""
    if call.returncode == 0:
        try:
            client_rows = json.loads(call.stdout)["calls"]
        except Exception as exc:
            client_err = f"回包解析失败：{type(exc).__name__}: {exc}"
    else:
        client_err = f"rc={call.returncode} {(call.stderr or call.stdout)[:240]}"
    client_prefix = (
        sum(1 for c in client_rows if "T0r110" in (c.get("params") or ""))
        if client_rows is not None
        else 0
    )
    if client_rows is None:
        refuse.append(f"call_log 工具没调通：{client_err}")
    elif client_prefix < stages["T0r110"]["rows"]:
        refuse.append(
            f"call_log 工具只回 {client_prefix} 行含 T0r110（sqlite 同口径 "
            f"{stages['T0r110']['rows']} 行）⇒ 工具面看不到这些调用"
        )
    client_ok = 1 if (client_rows is not None and client_prefix >= stages["T0r110"]["rows"]) else 0
    fp_channel_of = {
        "laya_decide": laya_fp,
        "publish": pub_fp,
        "report_bug": rb_fp,
        "call_log": client_ok,
    }
    for spec_name, real_tools in CARRIERS.items():
        per = {}
        for t in real_tools:
            per[t] = {
                "whole_db": con.execute(
                    "select count(*) from call_log where tool=?", (t,)
                ).fetchone()[0],
                "this_stage_seed": sum(
                    v["ok"] + v["refused"] for k, v in seed_by_tool.items() if k == t
                ),
                "this_stage_prefix": sum(
                    v["ok"] + v["refused"] for k, v in stages["T0r110"]["by_tool"].items() if k == t
                ),
                "this_ring_fingerprint": fp_channel_of.get(t, 0),
            }
        if spec_name == "call_log":
            per["call_log"]["this_stage_prefix"] = client_ok
            per["call_log"]["client_visible_T0r110_rows"] = client_prefix
            per["call_log"]["client_rows_returned"] = (
                len(client_rows) if client_rows is not None else 0
            )
            if client_err:
                per["call_log"]["error"] = client_err
        hit = sum(v["whole_db"] for v in per.values())
        in_stage = sum(v["this_stage_seed"] + v["this_stage_prefix"] for v in per.values())
        in_ring = sum(v["this_ring_fingerprint"] for v in per.values())
        carriers[spec_name] = {
            "carriers": per,
            "whole_db_total": hit,
            "this_stage_total": in_stage,
            "this_ring_fingerprint_total": in_ring,
        }
        if hit == 0:
            refuse.append(
                f"规格点名的 {spec_name} 在本 build 的 call_log 里一次都没有（工具名不存在或从未调用）"
                "⇒ 不许写『已开启』"
            )
    absent = con.execute(
        "select count(*) from call_log where " "json_extract(params_json,'$.task_id') like ?",
        (f"{NEEDLE_ABSENT}%",),
    ).fetchone()[0]
    if absent != 0:
        refuse.append(f"对照前缀 {NEEDLE_ABSENT} 数出 {absent} 行（应为 0）⇒ 过滤器恒真")
    named = {}
    for t in NAMED_TOOLS:
        n = con.execute("select count(*) from call_log where tool=?", (t,)).fetchone()[0]
        like = con.execute(
            "select count(*) from call_log where tool like ?", (f"%{t}%",)
        ).fetchone()[0]
        named[t] = {"exact": n, "substring": like}
    con.close()

    def group_verbatim(items, witness):
        """按错误原文去重分组，返回 (markdown 表, 组数, 次数合计)——两路都用于回加自证。"""
        gp, ordr = {}, []
        for d in items:
            if not isinstance(d, dict):
                continue
            key = d["err"] or "(空 result_json)"
            if key not in gp:
                gp[key] = {"count": 0, "first": witness(d), "tool": d["tool"]}
                ordr.append(key)
            gp[key]["count"] += 1
        ls = ["| 被拒原文（逐字） | 工具 | 次数 | 首个见证 |", "| --- | --- | --- | --- |"]
        for key in ordr:
            g = gp[key]
            quoted = key.replace("|", "\\|").replace("\n", "⏎")
            ls.append(f'| `{quoted}` | {g["tool"]} | {g["count"]} | {g["first"][:150]} |')
        return "\n".join(ls), len(ordr), sum(g["count"] for g in gp.values())

    # 被拒原文逐字：按错误文本去重分组，每组给次数 + 一个 task/ts 见证（不进表格单元，纯文本行）
    refusals_md, distinct_refusals, grouped_sum = group_verbatim(
        stages["T0r110"]["refused_detail"], lambda d: f'{d["task"]} @ {d["ts"]}'
    )
    if grouped_sum != stages["T0r110"]["refused"]:
        refuse.append(
            f"逐字分组次数合计 {grouped_sum} ≠ refused 计数 {stages['T0r110']['refused']} ⇒ 分组漏行"
        )
    tag_refusals_md, tag_distinct_refusals, tag_grouped_sum = group_verbatim(
        tag_refused_detail, lambda d: f'{d["who"]} @ {d["ts"]}'
    )
    if tag_grouped_sum != tag_refused:
        refuse.append(
            f"标签档逐字分组次数合计 {tag_grouped_sum} ≠ 标签 refused {tag_refused} ⇒ 分组漏行"
        )
    if tag_distinct_refusals == 0 and tag_refused > 0:
        refuse.append(f"标签档有 {tag_refused} 条被拒却没有一条原文 ⇒ 逐字清单是空的")
    sum_by_tool = sum(v["ok"] + v["refused"] for v in stages["T0r110"]["by_tool"].values())
    check(
        "逐工具计数之和 = 前缀总行数（分组不吞行）",
        sum_by_tool,
        stages["T0r110"]["rows"],
        "两路回加",
    )
    check(
        "refused 计数 = 逐字清单条数（拒收清单不是手数）",
        stages["T0r110"]["refused"],
        len(stages["T0r110"]["refused_detail"]),
        "两栏同数",
    )
    check("不存在前缀必须数出 0 行（过滤器不恒真）", absent, 0, "对照前缀")
    check(
        "按标签这一路的逐工具合计 = 标签行数（换了过滤器也不吞行）",
        sum(v["ok"] + v["refused"] for v in tag_by_tool.values()),
        len(tag_rows),
        "两路回加",
    )
    ring_tag_calls = {
        "tag": ring_tag,
        "by_tool": tag_by_tool,
        "total": len(tag_rows),
        "ok": tag_ok,
        "refused": tag_refused,
        "absent_control_rows": tag_absent_rows,
        "refused_detail": tag_refused_detail,
        "refusals_md": tag_refusals_md,
        "distinct_refusal_texts": tag_distinct_refusals,
        "note": "laya / issue_up 的 params 里没有 task_id，只有环标签 ⇒ 按前缀数它们恒为 0，"
        "这一栏才是本环真开过的次数；report_bug 的 refused 是服务端拒收那一批（不是没调）。"
        "call_log 工具的回包行数见 call_log_tool_probe（它的 params 不带环标签，不能按标签数）。",
    }
    check(
        "标签档对本环 0 行必须能换成指纹档：laya 的承担者 laya_decide 在本环确有成功调用，"
        "且指纹档与 ts 窗口档同数",
        [laya_fp, laya_win, laya_ok],
        [laya_win, laya_win, 1],
        f"指纹 {laya_fp} / 窗口 {laya_win} / 其中成功 {laya_ok}（窗口起 {fix_start}）",
        ok=bool(finger) and laya_fp == laya_win >= 1 and laya_ok >= 1,
    )
    check(
        "publish（issue_up 的账面上报动作）指纹档与窗口档同数且 ≥1",
        [pub_fp, pub_win],
        [pub_win, pub_win],
        f"指纹 {pub_fp} / 窗口 {pub_win}",
        ok=pub_fp == pub_win >= 1,
    )
    check(
        "report_bug（issue_up 的字面工具）三路同源：ts 窗口 = 环标签档 = 入账件自记的 call_log 增量，"
        "且本环 ≥1（修复途中立了 BUG-91）；同一按-工具过滤器在寻虫环窗口也必须数到 >0"
        "⇒ 指纹档对它 0 行是通道形状所致，不是没调用",
        f"窗口{rb_win} / 标签{rb_tag} / 入账件增量{book_delta} / 寻虫环 {rb_hunt} 行",
        "三路相等 且 本环>=1 且 对照>0",
        f"fp 档 {rb_fp} 行（params 里没有根描述首行，预期 0）",
        ok=rb_win == rb_tag == book_delta >= 1 and rb_hunt > 0 and rb_fp == 0,
    )
    check(
        "指纹档的反例必须数出 0 行（这个过滤器不恒真）", dead_needle_rows, 0, "必然不存在的 needle"
    )
    check(
        "标签档与指纹档不许同时为空：两档都看不见本环 ⇒ 对账失明（本环标签 0 行必须由指纹档补上）",
        f"标签档 {len(tag_rows)} 行 / 指纹档 {laya_fp + pub_fp} 行",
        "至少一档 >0",
        f"环标签 {ring_tag} 在本环 params 里不出现 ⇒ 已列为失效条目",
        ok=len(tag_rows) > 0 or (laya_fp + pub_fp) > 0,
    )
    check(
        "call_log 工具本轮真打了一次且回包看得到本环号段",
        client_ok,
        1,
        f"sqlite 同口径 {stages['T0r110']['rows']} 行 / 回包含 T0r110 {client_prefix} 行",
    )
    doc = {
        "started": started_at,
        "self_checks": CHECKS,
        "grouped_by": "params_json.task_id 前缀（不按标签、不按回忆）",
        "stages": stages,
        "control_absent_prefix_rows": absent,
        "total_call_log_rows": total_all,
        "stage_seed_rows": {
            "needle": STAGE_SEED,
            "total": len(seed_rows),
            "by_tool": seed_by_tool,
            "scope": "上一环（R4）号段：跨环正例对照，证明按标签过滤器找得到行；不是本环计数",
        },
        "ring_tag_calls": ring_tag_calls,
        "fingerprint_channel": fingerprint_channel,
        "call_log_tool_probe": {
            "rows_returned": len(client_rows) if client_rows is not None else None,
            "rows_containing_stage": client_prefix,
            "sqlite_rows": stages["T0r110"]["rows"],
            "error": client_err,
        },
        "named_tools_in_this_build": named,
        "spec_named_carriers": carriers,
        "distinct_refusal_texts": distinct_refusals,
        "refusals_md": refusals_md,
        "note": "规格点名的 laya / issue_up 若在 call_log 里 0 命中，说明本 build 没有这两个工具名；"
        "等价能力由谁承担要写在报告里，不许写『已开启』。本环根描述里没有环标签也没有 "
        "[omega:required]（发布时未拼进去），所以按标签那一档对本环恒 0 行，改由「根描述首行指纹档 + "
        "ts 窗口档」两路对账；report_bug 的 params 里没有根描述首行，那一档改按「卡片 detail 来历行的环标签」"
        "与 ts 窗口两路对，第三路取入账件自记的 call_log 增量；本环修复途中立了 BUG-91，"
        "旧口径「修复环 0 次是设计后果」已作废，对照仍给寻虫环计数。",
        "refuse": sorted(
            set(refuse)
            | {f"判据自证未过：{c['label']}（实得 {c['got']}）" for c in CHECKS if not c["ok"]}
        ),
        "queried_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "rows_T0r110": stages["T0r110"]["rows"],
                "distinct_tasks": stages["T0r110"]["distinct_tasks"],
                "refused_T0r110": stages["T0r110"]["refused"],
                "stage_seed_total": len(seed_rows),
                "carriers": {k: v["this_stage_total"] for k, v in carriers.items()},
                "by_tool": stages["T0r110"]["by_tool"],
                "named": {k: v["exact"] for k, v in named.items()},
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
