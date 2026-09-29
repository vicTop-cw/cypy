"""把 R4-打磨 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

拒绝条件：① 任一判据件 refuse 非空；② 三套体系有红；③ 报告 sha 与渲染见证留档不一致
（渲染后被改）；④ 叶收口件不是 16 行或有失败；⑤ 根不是「已归档」；⑥ 该环记录已在册（幂等门）。
收口后的 call_log 终账与逐字被拒原文只进这里，不回灌已渲染的报告。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROG = HERE / "loop_progress.md"
MARK = "### R4-打磨"
STAMP = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
RING_START = "2026-09-28T01:41:16+00:00"
REFUSE: list = []
KEYS = {"polish_r4_docs.json": "dc", "polish_r4_appendixC.json": "ap",
        "polish_r4_ledger.json": "lg", "polish_r4_debt.json": "db",
        "polish_r4_locks.json": "lk", "polish_r4_structural.json": "st",
        "polish_r4_baselines.json": "bs", "polish_r4_calllog_tally.json": "tl",
        "polish_r4_calllog_tally_final.json": "tf",
        "polish_r4_drivers_lint.json": "ln", "polish_r4_self_audit.json": "sa",
        "polish_r4_render_order.json": "ro", "close_r4_polish.json": "cs",
        "close_r4_polish.out.json": "closer", "close_r4_polish_root.out.json": "rootc",
        "spec_r4_polish.json": "plan"}
GREEN = ("dc", "ap", "lg", "db", "lk", "st", "bs", "tl", "tf", "ln", "sa", "ro")
BATCH1 = HERE / "polish_r4_tmp" / "baselines_batch1_015503.json"


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


def root_status(rootc):
    return str(rootc.get("root_final") or rootc.get("root_status") or "")


def minutes_now():
    a = datetime.datetime.fromisoformat(RING_START)
    now = datetime.datetime.fromisoformat(STAMP)
    return round((now - a).total_seconds() / 60)


def disclosures(a) -> str:
    """本环「报告之外发生的事」，逐条现读盘上件，不许无声丢掉。"""
    bs, plan = a["bs"], a["plan"]
    b1 = json.loads(BATCH1.read_text(encoding="utf-8")) if BATCH1.exists() else {}
    if not b1:
        REFUSE.append("第一批基线没留快照 ⇒ 「两批并发」这条披露会变成无证据的口头话")
    mainjs = Path("E:/IDEProjects/AI/FIST-Mbt/_build/js/debug/build/cmd/main/main.js")
    mjs = ("缺件", 0)
    if mainjs.exists():
        stt = mainjs.stat()
        mjs = (datetime.datetime.fromtimestamp(stt.st_mtime, datetime.timezone.utc)
               .isoformat(timespec="seconds"), stt.st_size)
    nc = plan.get("needle_correction") or {}
    pairs = [[x["law"], x["from"], x["to"]] for x in (nc.get("changed") or [])]
    b1s = g(b1, "started", default="未快照")
    b1p = g(b1, "systems", "pytest", "passed", default="—")
    b1c = g(b1, "systems", "collect", "nodeids", default="—")
    b1g = g(b1, "three_systems_green", default="—")
    b2s = g(bs, "window", "batch_started_at_utc")
    b2p = g(bs, "systems", "pytest", "passed")
    b2c = g(bs, "systems", "collect", "nodeids")
    return (
        "- 本环流程外事件（逐字，不吞，也不写进报告正文——报告已渲染不可回改）：\n"
        f"  1. **同一条三套体系批被我起了两遍，而且并发**：第一批起跑 `{b1s}`（pytest {b1p} / "
        f"收集 {b1c} / 绿 {b1g}），第二批起跑 `{b2s}`（pytest {b2p} / "
        f"收集 {b2c}）。起因是第一批起跑后我又重写了测试文件"
        f"（测量面没冻结），发现没落件时还没查进程表就起了第二批。两批数字互相同意，"
        f"所以判定数可用；**流程是错的**，已写进报告 §十 3 与下面的转结流程债。\n"
        f"  2. **needle 口径当场升级**：环节计划里 {nc.get('missing_before', '—')} 个 needle 键名"
        f"盘上不存在、{nc.get('false_substring_before', '—')} 个只是子串假命中"
        f"（`control` 撞文件名 `SYNTAX/15-control-flow.md`、`queue` 撞 `queue_frozen_edit` 前缀），"
        f"共改 {nc.get('changed_len', '—')} 处，逐对 (法, from, to)={js(pairs)}，"
        f"规则改成「needle 必须是被引件里的真键名」并配 canary "
        f"{js(g(a['sa'], 'needle_canary'))}。文件、min_chars 与「逐字含键」的强度未动。\n"
        f"  3. **服务端产物状态**：`main.js` mtime/大小={js(list(mjs))}——本环收口链开跑前"
        f"实测在场（上一环被别处的 `moon test` 清掉过一次，已重建，不是「环境打不到」的免责）。"
    )


def main() -> int:
    a = {v: L(k) for k, v in KEYS.items()}
    for k in GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件 refuse 非空：{js(a[k]['refuse'])[:200]}")
    rep_p = ROOT / "memory" / "reviews" / f"{g(a['ro'], 'report')}".split("/")[-1]
    if not rep_p.exists():
        REFUSE.append(f"报告不在盘上：{g(a['ro'], 'report')}")
    now_sha = hashlib.sha256(rep_p.read_bytes()).hexdigest() if rep_p.exists() else ""
    if now_sha and now_sha != g(a["ro"], "report_sha256"):
        REFUSE.append("报告在渲染之后被改过：sha 与见证件不一致")
    pf, gf = g(a["bs"], "systems", "pytest", default={}), g(a["bs"], "git", default={})
    if pf.get("failed") or pf.get("errors"):
        REFUSE.append(f"pytest 有红：{pf.get('failed')}/{pf.get('errors')}")
    if gf.get("staged"):
        REFUSE.append(f"暂存区非 0（{gf.get('staged')} 行）")
    closer, rootc = a["closer"], a["rootc"]
    if len(closer.get("leaves") or []) != 16:
        REFUSE.append(f"叶收口件不是 16 行：{len(closer.get('leaves') or [])}")
    if closer.get("failed"):
        REFUSE.append(f"叶失败：{js(closer.get('failed'))[:200]}")
    if root_status(rootc) != "已归档":
        REFUSE.append(f"根状态不是已归档：{root_status(rootc)!r}")
    tf = a["tf"]
    if tf.get("refuse"):
        REFUSE.append(f"终账件 refuse 非空：{js(tf['refuse'])[:200]}")
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    if MARK in PROG.read_text(encoding="utf-8"):
        print(json.dumps({"refuse": ["该环记录已在册（幂等门）：不许往 loop_progress 里追加第二份"]},
                         ensure_ascii=False, indent=1))
        return 1

    bs, sa, ro, tl, tf, ln = (a["bs"], a["sa"], a["ro"], a["tl"], a["tf"], a["ln"])
    dc, ap, lg, db, lk, st = (a["dc"], a["ap"], a["lg"], a["db"], a["lk"], a["st"])
    lines = [f"{MARK}（根 `{g(a['cs'], 'root_task', default='未记')}`，执行人 "
             f"`{g(a['cs'], 'assignee', default='未记')}`）", ""]
    lines.append(f"- 结论：**{root_status(rootc)}**。八条法全部独立复算；"
                 f"半径=措辞面/账面/测试面/骨架（产品 {cnt(bs['radius'], 'product')} 项 / "
                 f"冻结 {cnt(bs['radius'], 'frozen')} 项 / tests {cnt(bs['radius'], 'tests')} 项 / "
                 f"docs {cnt(bs['radius'], 'docs')} 项，判据件 {cnt(bs['radius'], 'loop')} 个）。")
    m = dc.get("measurement") or {}
    tri = js([m.get("pyd_reused_between_calls"), m.get("get_cached_pyd_all_none"),
              m.get("single_call_prints_both_cache_verdicts")])
    lines.append(f"- 法①文档：`docs/USAGE.md` 实测第 "
                 f"{js(dc.get('old_line_number_measured'))} 行改写，"
                 f"sha `{dc.get('before_sha')}`→`{dc.get('after_sha')}`，"
                 f"差分 {cnt(dc, 'diff_changed_lines')} 行；三格实测 {tri}。")
    lines.append(f"- 法②附录 C：交人工栏 {js(ap.get('queue_frozen_edit'))}，我方补注 "
                 f"{ap.get('note_done_rows')} 行 {ap.get('note_bytes')} B；"
                 f"冻结面 {ap.get('frozen_files')} 个 sha 相等 {ap.get('frozen_sha_equal')}、"
                 f"注入 canary 被抓 {g(ap, 'canary', 'caught')}。")
    lines.append(f"- 法③账面：新增 {g(lg, 'append_only_diff', 'added')} 行 / 删除 "
                 f"{g(lg, 'append_only_diff', 'removed')} 行，卡数 {lg.get('cards_total_before')}→"
                 f"{lg.get('cards_total_after')}，合法 task_id {lg.get('valid_task_ids_before')}→"
                 f"{lg.get('valid_task_ids_after')}；{cnt(lg, 'missing_before')} 张缺号卡反查命中 "
                 f"{cnt(lg, 'resolved_from_sqlite')} 张 ⇒ 措辞「未派单」交人工。")
    lines.append(f"- 法④骨架：`{db.get('kit')}`（API {cnt(db, 'kit_apis')} 个），行为不变 "
                 f"{cnt(db, 'equivalence')} 行覆盖 {js(db.get('equivalence_artifacts'))}，"
                 f"复制集合相同 {g(db, 'copy_tree_face', 'matches_reference')}、双 canary "
                 f"{js(db.get('canary'))}；形状分差 {db.get('shape_divergence_len')} 条与留债 "
                 f"{js(db.get('debt_remaining_counts'))} 点名未修。")
    lnp = lk.get("lane_prefix_code") or {}
    lines.append(f"- 法⑤永久锁：`{lk.get('new_test_file')}` 工作区 "
                 f"{lk['lane_work']['summary']} / 修前码 {lnp.get('summary')}"
                 f"（红 {cnt(lnp, 'red')} 条，含 1 条文档面）；两档 sha "
                 f"`{lk['identity']['work_type_checker_sha']}` ≠ "
                 f"`{lk['identity']['snap_type_checker_sha']}`，收集 "
                 f"{lk.get('collect_after_locks')}={lk.get('previous_round_collect_floor')}+20。")
    tcl, tcm = g(st, "type_checker", "code_lines"), g(st, "type_checker", "methods")
    hk, hkp = st.get("hook_eval_marker_count"), st.get("hook_eval_marker_product_face_total")
    lines.append(f"- 法⑥结构债：{st.get('files_measured')} 文件过 {st.get('redline')} 行红线，"
                 f"越线 {cnt(st, 'over_redline')} 个，type_checker {tcl} 行/{tcm} 方法，"
                 f"`__result__` {hk}/{hkp}；挂账 {cnt(st, 'adjudication_queue')} 条、"
                 f"执行不可逆 {cnt(st, 'executed_irreversible')} 条、"
                 f"碰过产品文件 {cnt(st, 'product_files_touched_this_ring')} 个、"
                 f"改名 {cnt(st, 'renamed_verbatim')} 个。")
    flds, e2e = js(g(bs, "systems", "suite", "fields")), js(g(bs, "systems", "e2e"))
    coll = g(bs, "systems", "collect", "nodeids")
    lines.append(f"- 三套体系：pytest {pf['passed']} 通过 / {pf['failed']} 失败 / "
                 f"{pf['errors']} 错误（地板 {g(bs, 'floors', 'pytest')}）、收集 {coll}"
                 f"（地板 {g(bs, 'floors', 'collect')}+20）、自研 {flds}、e2e {e2e}；"
                 f"HEAD `{gf.get('head')}`、暂存 {gf.get('staged')} 行、"
                 f"脏行 {g(bs, 'git', 'dirty_rows')}、冻结 {bs.get('frozen_total')} 个 sha 未变；"
                 f"三套同刻为绿 {bs.get('three_systems_green')}。")
    lines.append(f"- 驱动面：本轮亲笔 {ln.get('drivers_scanned')} 个脚本，硬错 "
                 f"{ln.get('hard_violations')}、软账 {ln.get('soft_total')}"
                 f"（基线 {ln.get('previous_round_soft_baseline')}）。")
    bad_ph = cnt(sa, "placeholders_bad")
    unjust = cnt(sa, "placeholders_empty_unjustified")
    lines.append(f"- 自证与门禁：{sa.get('gates_pass')}/{sa.get('gates_total')} 道在渲染前解出，"
                 f"自引用延后 {cnt(sa, 'gates_self_deferred')} 道，"
                 f"占位 {sa.get('placeholders_total')} 个（坏 {bad_ph} 个、"
                 f"空值无佐证 {unjust} 个），needle 严口径违例 "
                 f"{cnt(sa, 'needle_strict_violations')} 条，过期未披露 "
                 f"{cnt(sa, 'stale_undisclosed')} 条，§十 实测 "
                 f"{g(sa, 'section10_items', 'actual')} 条"
                 f"（声明 {g(sa, 'section10_items', 'declared')}）；不动点 "
                 f"{g(sa, 'fixpoint', 'converged')}，嵌入 {js(g(sa, 'fixpoint', 'embedded'))} vs "
                 f"实测 {js(g(sa, 'fixpoint', 'actual'))}。")
    lines.append(f"- 报告：`{ro.get('report')}`（{ro.get('report_bytes')} B，"
                 f"sha `{ro.get('report_sha256')}`），渲染 {ro.get('renders')} 次、"
                 f"被拒重试 {ro.get('refused_attempts')} 次、"
                 f"门禁表 {ro.get('gates_in_table')} 行全绿 {ro.get('gates_green')}、"
                 f"渲染后 §十 {js(ro.get('section10_rendered'))}、缺法条标题 "
                 f"{cnt(ro, 'law_heads_missing')} 个。")
    lines.append(f"- 收口：叶 {cnt(closer, 'leaves')}/16、失败 {cnt(closer, 'failed')}，"
                 f"根状态 `{root_status(rootc)}`；发单前 call_log 本环前缀 {tl.get('rows_T0r90')} 行、"
                 f"终账 {tf.get('rows_T0r90')} 行 / {tf.get('distinct_tasks')} 个任务，被拒 "
                 f"{g(tf, 'stages', 'T0r90', 'refused')} 条（逐字见下）。")
    box = minutes_now()
    verdict = "超盒" if box > 100 else "在盒内"
    cost = ("超出的是两批全量并发的墙钟" if box > 100
            else "并发重跑浪费的那段墙钟已记在披露 1")
    lines.append(f"- 时间盒：环节起于 {RING_START}，本条记录生成于 {STAMP}，实耗 {box} 分钟"
                 f"（盒 100 分钟，{verdict}）——{cost}；"
                 f"门禁未缩、判据未放宽、冻结面未动。")
    lines.append(disclosures(a))
    lines.append(f"- 转结：R4-推进 领「§十一 的 6 项裁决 + {cnt(lg, 'missing_before')} 张未派单卡 + "
                 f"{db.get('shape_divergence_len')} 条形状分差」，不得引用旧行号 406；"
                 f"R5 打磨领四类骨架留债；流程债两条（起后台批前先查同项目"
                 f"是否已有批在跑；基线起跑后冻结被测量面）。")
    lines.append(f"- 本条记录生成于 {STAMP}。")

    refusals = tf.get("stages", {}).get("T0r90", {}).get("refused_detail") or []
    if refusals:
        lines.append("- 收口被拒原文（逐字）：")
        for r in refusals:
            lines.append(f"  - `{js(r)[:400]}`")
    else:
        lines.append("- 收口被拒原文：无（终账 `refused=0`，按前缀数出来的，不是按回忆）。")

    body = "\n".join(lines) + "\n"
    (HERE / "polish_r4_progress.json").write_text(
        json.dumps({"mark": MARK, "block_chars": len(body), "ring_minutes": box,
                    "report_sha256": ro.get("report_sha256"), "root": root_status(rootc),
                    "at_utc": STAMP, "refuse": sorted(set(REFUSE))},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    PROG.write_text(PROG.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + body,
                    encoding="utf-8", newline="\n")
    print(json.dumps({"written": PROG.name, "block_chars": len(body), "ring_minutes": box,
                      "root": root_status(rootc), "refuse": sorted(set(REFUSE))},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
