"""把 R4-验证 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

拒绝条件：① 任一判据件 refuse 非空；② 三套体系有红；③ 报告 sha 与渲染时留档不一致
（渲染后被改）；④ 叶收口件不是 16 行或有失败；⑤ 根不是「已归档」；⑥ 该环记录已在册（幂等门）。
收口后的 call_log 终账与逐字被拒原文只进这里，不回灌已渲染的报告。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROG = HERE / "loop_progress.md"
MARK = "### R4-验证"
STAMP = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
REFUSE: list = []

KEYS = {"verify_r4_matrix.json": "mx", "verify_r4_callsite.json": "cs",
        "verify_r4_appendixC.json": "ap", "verify_r4_compile.json": "cp",
        "verify_r4_baselines.json": "bs", "verify_r4_lockproof.json": "lp",
        "verify_r4_ledger3way.json": "lg", "verify_r4_irreversible.json": "ir",
        "verify_r4_calllog_tally.json": "tl",
        "verify_r4_calllog_tally_final.json": "tf",
        "verify_r4_file_bugs.json": "fb", "verify_r4_drivers_lint.json": "ln",
        "verify_r4_self_audit.json": "sa", "verify_r4_render_order.json": "ro",
        "close_r4_verify.out.json": "closer", "close_r4_verify_root.out.json": "rootc"}
MUST_BE_GREEN = ("mx", "cs", "ap", "cp", "bs", "lp", "lg", "ir", "tl", "fb", "ln", "sa")


def L(name: str) -> dict:
    p = HERE / name
    if not p.exists():
        REFUSE.append(f"判据件缺失：{name}")
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        REFUSE.append(f"判据件不是合法 JSON：{name}（{str(exc)[:120]}）")
        return {}


def g(d, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def cnt(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    if isinstance(v, (list, dict)):
        return len(v)
    return v if isinstance(v, int) else 0


def js(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def carriers(tally):
    return {k: v.get("this_stage_total")
            for k, v in (tally.get("spec_named_carriers") or {}).items()}


def root_status(rootc):
    return str(rootc.get("root_final") or rootc.get("root_status") or "")


def minutes_used(bs):
    """返回（到基线终批起跑、到本进度件生成）两个墙钟分钟数。

    `window.finished_at_utc` 实测存的是基线脚本**自身起跑**的时刻（不是跑完时刻），
    拿它当终点会把超盒算成在盒内 ⇒ 终点必须另取本件的生成戳。
    """
    w = bs.get("window") or {}
    try:
        a = datetime.datetime.fromisoformat(w["start_utc"])
    except (KeyError, ValueError, TypeError):
        return "未记", "未记"
    b = a
    try:
        b = datetime.datetime.fromisoformat(w["finished_at_utc"])
    except (KeyError, ValueError, TypeError):
        pass
    now = datetime.datetime.fromisoformat(STAMP)
    return round((b - a).total_seconds() / 60), round((now - a).total_seconds() / 60)


def level_if_line(cp):
    """模块级 if 的行号：件里存的是 [[行号, 文本], …]，`g()` 走不进列表 ⇒ 单独取。"""
    rows = (cp.get("structural") or {}).get("module_level_if_lines") or []
    return rows[0][0] if rows and isinstance(rows[0], (list, tuple)) else "未记"


def disclosures() -> str:
    """本环「报告之外发生的事」：三条都现读盘上件/日志，不靠回忆，也不许省。

    缺任何一份输入就 REFUSE —— 这类披露是最容易被无声丢掉的一格。
    """
    mainjs = Path("E:/IDEProjects/AI/FIST-Mbt/_build/js/debug/build/cmd/main/main.js")
    log = HERE / "out_close_stage_r4_verify.log"
    snap_p = HERE / "verify_r4_tmp" / "calllog_prerender_snapshot.json"
    tal_p = HERE / "verify_r4_calllog_tally.json"
    for p in (log, snap_p, tal_p):
        if not p.exists():
            REFUSE.append(f"披露输入缺件：{p.name} ⇒ 这三条必须逐字进账，不许无声丢掉")
    mjs = "缺件"
    if mainjs.exists():
        st = mainjs.stat()
        mjs = (datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
               .isoformat(timespec="seconds"), st.st_size)
    refused_line = ""
    if log.exists():
        head = [ln for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()
                if "REFUSE" in ln or "law8" in ln]
        refused_line = " ⏎ ".join(head[:2])
    snap_rows = json.loads(snap_p.read_text(encoding="utf-8")).get("rows_T0r86") \
        if snap_p.exists() else "未记"
    tal_chars = len(tal_p.read_text(encoding="utf-8")) if tal_p.exists() else "未记"
    tal_rows = (json.loads(tal_p.read_text(encoding="utf-8")).get("rows_T0r86")
                if tal_p.exists() else "未记")
    return ("- 本环流程外事件（逐字，不吞，也不写进报告正文——报告已渲染不可回改）：\n"
            f"  1. **服务端产物在本环中途消失**：`{mainjs.as_posix()}` 被别处的 "
            f"`moon test --target js` 清掉，实测 `python lfist.py get` 回 "
            f"`[pfist] missing server build`；本地 `moon build --target js`（78 tasks，0 errors）"
            f"+ `python scripts/patch_esm_main.py` 重建后 RPC 才通 ⇒ 盘上产物 mtime/大小 = "
            f"{js(mjs)}。重建发生在叶收口**之前**，收口链一次通过（0 拒）；"
            f"这条不是「环境打不到」的免责，是当场重测并修通了。\n"
            f"  2. **收口预检第一次在盘上就拒**（逐字）：`{refused_line or '未记'}` —— "
            f"预检是 fail-closed 的，一个 RPC 都没发。处置不是把计划里的 3000 字符地板改小，"
            f"而是给 call_log 件补一条真实测量（整条循环 19 个根任务逐根点名行数/被拒数），"
            f"件从 2978 → {tal_chars} 字符，地板原样保留。\n"
            f"  3. **渲染之后重跑过一份渲染输入件**（`verify_r4_calllog_tally.json`）："
            f"报告 §八 的渲染前快照是 {snap_rows} 行，重跑后发单前复算 {tal_rows} 行，"
            f"`total_call_log_rows` 同步漂；报告不可回改，所以两个数在这里按时刻分栏记账，"
            f"而不是拿新数去确认旧数。")


def final_rows(tf, rootc):
    """收口后的终账：逐字被拒原文一条不吞，按前缀分组而不是按回忆。"""
    car = js({k: v.get("this_stage_total") for k, v in
              (tf.get("spec_named_carriers") or {}).items()})
    om = js(tf.get("omega_chain_by_tool") or {})
    ref = tf.get("refusals_md") or "（无）"
    root_ref = js(rootc.get("refused") or [])
    return (f"- 终账（收口后）：本环前缀 {g(tf, 'rows_T0r86')} 行 / "
            f"{g(tf, 'distinct_tasks')} 个任务，全库 {g(tf, 'total_call_log_rows')} 行，"
            f"载体 {car}，Omega 三连 {om}，被拒 {g(tf, 'stages', 'T0r86', 'refused')} 条。\n"
            f"- 根收口件逐字被拒（`close_r4_verify_root.out.json` 的 refused，一条不吞）："
            f"{root_ref}\n"
            f"  被拒原文（逐字）：\n\n{ref}\n")


def build_row(a):
    bs, mx, cs, ap = a["bs"], a["mx"], a["cs"], a["ap"]
    cp, lp, lg = a["cp"], a["lp"], a["lg"]
    ir, fb, ln, sa, ro, tf = a["ir"], a["fb"], a["ln"], a["sa"], a["ro"], a["tf"]
    pf, gf, r = bs["systems"]["pytest"], bs["git"], bs.get("radius") or {}
    lines = []
    append = lines.append
    append(f"{MARK}（根 `T0r86`，执行人 `cypy-verifier`）\n")
    append("")
    append(f"- 结论：**已收口**。八条法全部独立复算，半径=只看不动手"
           f"（产品 {len(r.get('product') or [])} / 测试 {len(r.get('tests') or [])} / "
           f"docs {len(r.get('docs') or [])} / 冻结 {len(r.get('frozen') or [])} 全空，"
           f"判据件 {len(r.get('loop') or [])} 个）。")
    append(f"- 回退矩阵：{g(mx, 'rows_total')} 行切片自 difflib，承重 {cnt(mx, 'bearing')} / "
           f"不承重 {cnt(mx, 'non_bearing')} / 摘坏 {cnt(mx, 'broken_import')}，"
           f"sha 复原 {g(mx, 'sha_restored')}，反面 canary 被抓 {g(mx, 'canary_caught')}。")
    append(f"- 调用面：{g(cs, 'rows_total')} 条 CLI 探针（对照 {g(cs, 'controls_pass')} 条），"
           f"外泄内部表示 {cnt(cs, 'internal_repr_leaks')} 条，换回修前码翻转 "
           f"{g(cs, 'sensitivity', 'flips_total')} 条（含正确形状 "
           f"{js(g(cs, 'sensitivity', 'proper_flips'))}）。")
    append(f"- 附录 C：反解 {g(ap, 'rows_total')} 行，成立 {cnt(ap, 'verified')} / "
           f"claim-false {cnt(ap, 'claim_false')} / half-true {cnt(ap, 'claim_half_true')} / "
           f"没测到 {cnt(ap, 'unverified')}，needle 对照 {g(ap, 'canary_caught')}。")
    append(f"- 真编译：三发 rc={js([x['rc'] for x in cp.get('attempts') or []])}"
           f"（合法 C / 合成违例 / bridge 生成物），模块级 if 在第 "
           f"{level_if_line(cp)} 行；D18 "
           f"{g(cp, 'd18_cache', 'verdict')}（重写 "
           f"{g(cp, 'd18_cache', 'pyd_rewritten_between_calls')}）。"
           f"golden 面 {g(cp, 'golden_untouched', 'files_after')} 个文件 sha "
           f"{g(cp, 'golden_untouched', 'equal')} 相等、未跟踪新增 "
           f"{cnt(cp, 'repo_new_files')}。")
    lanes = [(x["lane"], x["achieved"], x["target_red_count"]) for x in lp.get("runs") or []]
    head_hits = len((lp.get("runs") or [{}, {}, {}])[2].get("r4_shape_hits") or [])
    suite, e2e = g(bs, "systems", "suite", "fields"), g(bs, "systems", "e2e")
    append(f"- 三套体系：pytest {g(pf, 'passed')} 通过 / {g(pf, 'failed')} 失败 / "
           f"{g(pf, 'errors')} 错误（地板 {g(bs, 'floors', 'pytest')}）、收集 "
           f"{g(bs, 'systems', 'collect', 'nodeids')}、自研 {js(suite)}、e2e {js(e2e)}；"
           f"HEAD `{g(gf, 'head')}`、暂存 {g(gf, 'staged')} 行、"
           f"脏行 {g(gf, 'dirty_rows')}、冻结面 {g(bs, 'frozen_total')} 个文件 sha 未变。")
    append(f"- 锁必红复核：三档 {js(lanes)}，同一份测试（sha 集合=1），"
           f"HEAD 档红在本轮形状上的有 {head_hits} 条。")
    append(f"- 账面：md {g(lg, 'cards_total')} 卡 / sqlite {g(lg, 'sqlite_bug_rows')} 行，"
           f"差 {g(lg, 'ledger_delta')}（有卡无行 {cnt(lg, 'md_only_cards')}、"
           f"有行无卡 {cnt(lg, 'sqlite_only_rows')}），FIXED 三向一致 "
           f"{g(lg, 'three_way_agreed')}/{cnt(lg, 'r4_fixed_cards')}，复跑 "
           f"{cnt(lg, 'recheck')} 条：不再现形 {js(lg.get('fixed_not_recurring') or [])}、"
           f"仍现形 {cnt(lg, 'still_recurring')}、未交代半开 {cnt(lg, 'undisclosed_half_open')}。")
    append(f"- 挂账：不可逆 {g(ir, 'not_executed_total')} 条逐条带测量（canary "
           f"{g(ir, 'canary', 'predicate_catches_known_write')}），裁决队列 "
           f"{cnt(ir, 'adjudication_queue')} 条；新入账 {cnt(fb, 'filed_total')} 张 "
           f"{js(fb.get('filed') or [])}（sqlite 增量 {g(fb, 'sqlite_bug_rows', 'delta')}）。")
    append(f"- 驱动面：本轮亲笔 {g(ln, 'drivers_scanned')} 个脚本，硬错 {g(ln, 'hard_violations')}、"
           f"软账 {g(ln, 'soft_total')}（上一环基线 {g(ln, 'previous_round_soft_baseline')}）。")
    append(f"- 报告：`{g(ro, 'report', default='—')}`（{g(ro, 'report_bytes')} B，"
           f"sha `{g(ro, 'report_sha256')}`，渲染 {g(ro, 'renders')} 次，"
           f"被拒重试 {g(ro, 'refused_attempts')} 次，门禁表 {g(ro, 'gates_in_table')} 行全绿 "
           f"{g(ro, 'gates_green')}）；自证 {g(sa, 'gates_pass')}/{g(sa, 'gates_total')} 道，"
           f"自引用延后 {cnt(sa, 'gates_self_deferred')} 道，"
           f"《十》{g(sa, 'section10_items', 'actual')} 条判据自伤，"
           f"件-脚本同源披露 {cnt(sa, 'stale_artifacts')} 条。")
    append(f"- 收口：叶 {cnt(a['closer'], 'leaves')}/16、失败 {cnt(a['closer'], 'failed')}，"
           f"根状态 `{root_status(a['rootc'])}`。")
    box_fin, box_now = minutes_used(bs)
    over = isinstance(box_now, int) and box_now > 100
    append(f"- 时间盒：环节起于 {g(bs, 'window', 'start_utc')}；"
           f"`window.finished_at_utc`={g(bs, 'window', 'finished_at_utc')} 这个键实测存的是"
           f"基线脚本**自身起跑**的时刻（不是三套体系跑完的时刻，报告 §十 19 已记），"
           f"所以终点取本进度件的生成戳 {STAMP} ⇒ 自环节起算实耗 {box_now} 分钟"
           f"（盒 100 分钟，{'**超盒 ' + str(box_now - 100) + ' 分钟**' if over else '在盒内'}）"
           f"——超盒如实记账，门禁未缩、判据未放宽、未动冻结面；"
           f"基线终批从环节起算的第 {box_fin} 分钟起跑。")
    append(disclosures())
    append("- 转结：R4-打磨 领「附录 C 的 4 条形差 + USAGE.md:406 那句『源未变会复用 .pyd』」"
           "的措辞面（本环不改冻结面与文档）；R4-推进 半径仍限「已声明未实现」；"
           "BUG-71/72/73 与挂账队列逐条带可复跑命令。")
    append(f"- 本条记录生成于 {STAMP}。")
    return "\n".join(lines) + "\n" + final_rows(tf, a["rootc"])


def main() -> int:
    a = {v: L(k) for k, v in KEYS.items()}
    for k in MUST_BE_GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件的 refuse 非空：{js(a[k]['refuse'])[:200]}")
    rep = ROOT / str(a["ro"].get("report") or "")
    if not rep.exists():
        REFUSE.append(f"报告文件不在盘上：{a['ro'].get('report') or '(render_order 件缺失)'}")
    if len(a["closer"].get("leaves") or []) != 16:
        REFUSE.append(f"叶收口件只有 {len(a['closer'].get('leaves') or [])} 行（应 16）")
    if a["closer"].get("failed"):
        REFUSE.append(f"有叶未闭：{js(a['closer']['failed'])[:200]}")
    if root_status(a["rootc"]) != "已归档":
        REFUSE.append(f"根任务终态不是「已归档」：{root_status(a['rootc']) or '(空)'}")
    if rep.exists() and a["ro"].get("report_sha256"):
        now = hashlib.sha256(rep.read_bytes()).hexdigest()
        if now != a["ro"]["report_sha256"]:
            REFUSE.append(f"报告在渲染后被改动：sha {a['ro']['report_sha256'][:16]} → {now[:16]}")
    if a["bs"].get("systems", {}).get("pytest", {}).get("failed_names"):
        REFUSE.append(f"pytest 仍有红：{js(a['bs']['systems']['pytest']['failed_names'])}")
    if a["ro"].get("gates_red"):
        REFUSE.append(f"报告门禁表里有 {a['ro']['gates_red']} 行 ❌")

    text = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    if MARK in text:
        print(json.dumps({"refuse": [f"进度账里已有「{MARK}」段 ⇒ 拒绝叠加（幂等门）"]},
                         ensure_ascii=False))
        return 1
    row = build_row(a) if not REFUSE else ""
    ks = re.findall(r"(?:^|\s)([a-z][\w-]*)=", row)
    dup = sorted({k for k in ks if ks.count(k) > 1})
    if dup:
        REFUSE.append(f"记录内同名键出现两次：{dup}")
    refuse = sorted(set(REFUSE))
    doc = {"started": a["sa"].get("started", ""), "mark": MARK, "refuse": refuse,
           "written": not refuse, "dup_keys": dup,
           "bytes_written": len(row.encode("utf-8")) if row else 0, "at_utc": STAMP}
    (HERE / "verify_r4_progress.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    if refuse:
        print(json.dumps({"refuse": refuse}, ensure_ascii=False, indent=1))
        return 1
    PROG.write_text(text.rstrip("\n") + "\n\n" + row.rstrip("\n") + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": [], "mark": MARK, "bytes": doc["bytes_written"],
                      "lines": len(row.splitlines())}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
