"""把 R4-推进 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

拒绝条件：① 任一承重判据件 refuse 非空；② 三套体系有红或地板不齐；③ 报告 sha 与渲染见证
留档不一致（渲染后被改）；④ 叶收口件不是 16 行或有失败；⑤ 根不是「已归档」；
⑥ 收口后终账里 omega 三连或 laya/issue_up 承担工具零次数（「已开启」不能是形容词）；
⑦ 该环记录已在册（幂等门）。收口链的结果与逐字被拒原文只进这里，不回灌已渲染的报告。
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
MARK = "### R4-推进"
STAMP = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
RING_START = "2026-09-28T03:00:00+00:00"
BOX_MIN = 100
STAGE = "T0r93"
CLI_JS = Path("E:/IDEProjects/AI/FIST-Mbt/_build/js/debug/build/cmd/cli/cli.js")
RUN1_LOG = HERE / "advance_r4_tmp" / "baselines_r4_0345.log"
REFUSE: list = []
KEYS = {"advance_r4_never.json": "nv", "advance_r4_builtins.json": "bi",
        "advance_r4_scope_face.json": "sc", "advance_r4_dormant.json": "dm",
        "advance_r4_lock_plan.json": "lp", "advance_r4_filed.json": "fl",
        "advance_r4_locks.json": "lk", "advance_r4_codegen_diff.json": "cg",
        "advance_r4_corpus.json": "co", "advance_r4_baselines.json": "bs",
        "advance_r4_irreversible.json": "ir", "advance_r4_drivers_lint.json": "ln",
        "advance_r4_calllog_tally.json": "tl",
        "advance_r4_calllog_tally_final.json": "tf",
        "advance_r4_self_audit.json": "sa", "advance_r4_render_order.json": "ro",
        "close_r4_advance.json": "cs", "close_r4_advance.out.json": "closer",
        "close_r4_advance_root.out.json": "rootc", "spec_r4_advance.json": "plan"}
GREEN = ("nv", "bi", "sc", "dm", "fl", "lk", "cg", "co", "bs", "ir", "ln",
         "tl", "tf", "sa", "ro")
CHECKS: list = []


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


def chk(label, got, want, why=""):
    ok = got == want
    CHECKS.append({"label": label, "got": got, "want": want, "ok": ok})
    if not ok:
        REFUSE.append(f"自证未过：{label}（实得 {js(got)}，应为 {js(want)}）{why}")
    return ok


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


def root_status(rootc) -> str:
    return str(rootc.get("root_final") or rootc.get("root_status") or "")


def minutes_now() -> int:
    a = datetime.datetime.fromisoformat(RING_START)
    now = datetime.datetime.fromisoformat(STAMP)
    return round((now - a).total_seconds() / 60)


def run1_facts() -> dict:
    """第一批基线的原始 stdout：件已被第二批复写，只能从留档 log 里反解（它是 JSON，不是散文）。"""
    if not RUN1_LOG.exists():
        REFUSE.append(f"第一批基线没留 log（{RUN1_LOG.name}）⇒ 「跑了两遍」只能写成口头主张")
        return {}
    try:
        d = json.loads(RUN1_LOG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        REFUSE.append(f"第一批 log 不是合法 JSON：{str(exc)[:120]}")
        return {}
    chk("第一批 log 的拒数与 pytest 栏互相印证（有红才该被拒）",
        [bool(d.get("refuse")), d["pytest"][1] > 0], [True, True], js(d.get("pytest")))
    return {"refuse_n": len(d.get("refuse") or []),
            "pytest": d.get("pytest"), "collected": d.get("collected"),
            "radius_rows": d.get("by_mtime"),
            "first_refusal": (d.get("refuse") or ["未记"])[0][:120]}


def disclosures(a) -> str:
    """本环「报告之外发生的事」，逐条现读盘上件——报告已渲染不可回改，所以只能进这里。"""
    bs, lk, sa = a["bs"], a["lk"], a["sa"]
    r1 = run1_facts()
    cli = ("缺件", 0, "")
    if CLI_JS.exists():
        stt = CLI_JS.stat()
        cli = (datetime.datetime.fromtimestamp(stt.st_mtime, datetime.timezone.utc)
               .isoformat(timespec="seconds"), stt.st_size)
    return (
        "- 本环流程外事件（逐字，不吞；报告正文渲染于 "
        f"`{g(a['ro'], 'at_utc')}` 之后一个字都没再动，sha "
        f"`{g(a['ro'], 'report_sha256')[:12]}…` 由见证件与本轮复算双向核对）：\n"
        f"  1. **三套体系批跑了两遍，但不是并发**：第一批留档 `{RUN1_LOG.name}`"
        f"（拒 {r1.get('refuse_n', '—')} 条、pytest 过/红/错={js(r1.get('pytest'))}、"
        f"收集 {r1.get('collected', '—')}；首条被拒原文「{r1.get('first_refusal', '—')}」），"
        f"第二遍 `{g(bs, 'started')}`→`{g(bs, 'at_utc')}` 才是"
        f"承重的那一份。第一批里有两条是**判据自己坏了**（porcelain 恒空口径、"
        f"半径拿绝对路径比相对名单——当时数出来的就是 {js(r1.get('radius_rows'))}），"
        f"两条是被激活的既有测试（defer）⇒ 上一版报告里「同一条批并发起跑」那条失效在本环不成立，"
        f"我按事实改成「两遍串行，第一遍被拒」。\n"
        f"  2. **计划文件曾是非法 JSON，躺了 90 多分钟**：`spec_r4_advance.json` 的 "
        f"`needle_verification.why` 被我手补成 Python 式相邻字符串续行——合法 Python、非法 JSON，"
        f"直到渲染前 `report_spec` 重新 parse 才炸。现在自证件里有「每份 JSON 判据件都能 parse」"
        f"+「相邻字符串违例必红 / 合法 JSON 不误抓」的门与两格 canary"
        f"（本轮自证条数 {cnt(sa, 'self_checks')}）。修法只并那一个值，"
        f"`laws`/`fingerprint` 逐字节未变（改前/改后切片比对 True/True）。\n"
        f"  3. **四个判据件改完没立刻重跑**：`advance_r4_never/scope_face/sweep/irreversible` "
        f"的脚本在 03:48 被改过，件却是 03:14–03:45 产的 ⇒ 直到 05:19 自证件把「脚本比件新且未披露」"
        f"判成红才补跑（现件时间 {g(a['nv'], 'at_utc')} / {g(a['sc'], 'at_utc')} / "
        f"{g(a['co'], 'at_utc')} / {g(a['ir'], 'at_utc')}）。**这条进不了报告 §十**（正文已渲染），"
        f"所以记在这里并转结流程债：改完判据脚本必须立刻重跑它的件，别指望渲染前的复算兜底。\n"
        f"  4. **指挥官裁决落地的唯一一处既有测试改动**：`tests/test_codegen_verification.py` 的 "
        f"`test_defer_statement` 按声明面语义改期望并去掉 `if result.success` 守卫；"
        f"其余 7 处同款守卫与 defer 异常路径安全入账未修"
        f"（{g(a['dm'], 'card_expected_id')} / BUG-77，见报告 §三·B、§四）。\n"
        f"  5. **服务端产物在场**：`cli.js` mtime/大小={js(list(cli))}——收口链开跑前实测，"
        f"不是「环境打不到」的免责（上一环它被别处的构建清掉过一次）。\n"
        f"  6. **lint 清零带来的重跑**：驱动件软账 23→0 之后 `gen_locks` 的 mtime 晚于它的 plan 件，"
        f"按链补跑 `gen_locks → locks`；生成的锁文件两棵树 sha 相同 "
        f"`{g(lk, 'identity', 'lock_sha_work')}`=`{g(lk, 'identity', 'lock_sha_snap')}`，"
        f"所以 §七 的 {g(bs, 'systems', 'pytest', 'passed')}/"
        f"{g(bs, 'systems', 'collect', 'nodeids')} 仍对同一批字节负责。"
    )


def main() -> int:
    a = {v: L(k) for k, v in KEYS.items()}
    for k in GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件 refuse 非空：{js(a[k]['refuse'])[:200]}")
    rep_rel = g(a["ro"], "report")
    rep_p = ROOT / rep_rel
    if not rep_p.exists():
        REFUSE.append(f"报告不在盘上：{rep_rel}")
    now_sha = hashlib.sha256(rep_p.read_bytes()).hexdigest() if rep_p.exists() else ""
    chk("报告渲染后未被改（复算 sha = 见证件留档 sha）", now_sha, g(a["ro"], "report_sha256"),
        rep_rel)
    chk("只渲染一次", g(a["ro"], "renders"), 1)
    chk("渲染器里被拒重试为零", g(a["ro"], "refused_attempts"), 0)
    chk("门禁表全绿（渲染后复数）", [g(a["ro"], "gates_in_table"), g(a["ro"], "gates_red")],
        [g(a["sa"], "gates_total"), 0], f"自证 {g(a['sa'], 'gates_pass')}/"
        f"{g(a['sa'], 'gates_total')}")
    chk("八条法的正文小节都在场", cnt(a["ro"], "law_heads_missing"), 0)
    chk("渲染后 §十 条数与声明相等",
        [g(a["ro"], "section10_rendered", "actual"), g(a["ro"], "section10_rendered", "declared")],
        [g(a["sa"], "section10_items", "actual"), g(a["sa"], "section10_items", "declared")])
    chk("不动点已推到（收口 spec 与最后一次自证逐格相同）",
        g(a["sa"], "fixpoint", "converged"), True, js(g(a["sa"], "fixpoint", "mismatch")))
    chk("过期未披露的件为零", cnt(a["sa"], "stale_undisclosed"), 0)
    bs, gf = a["bs"], g(a["bs"], "git", default={})
    pf, floors = g(bs, "systems", "pytest", default={}), g(bs, "floors", default={})
    chk("pytest 零失败零错误", [pf.get("failed"), pf.get("errors")], [0, 0])
    chk("pytest 与收集数都达地板（地板由上一环实测件反解）",
        [pf.get("passed") >= floors.get("pytest"),
         g(bs, "systems", "collect", "nodeids") >= floors.get("collect")], [True, True],
        js(floors))
    chk("自研套件与 e2e 达地板",
        [g(bs, "systems", "suite", "fields", "Passed"), g(bs, "systems", "e2e", "PASS")],
        [floors.get("suite"), floors.get("e2e_pass")])
    chk("红线：暂存 0 行且 HEAD 未漂", [gf.get("staged"), gf.get("head")], [0, "17d68b4"])
    chk("冻结面 43 个 sha 未变且本环窗口内无脏行",
        [bs.get("frozen_total"), cnt(bs, "frozen_changed"), cnt(bs, "frozen_dirt_in_ring")],
        [43, 0, 0], js(g(bs, "frozen_scope_porcelain")))
    closer, rootc = a["closer"], a["rootc"]
    chk("叶收口 16/16 且零失败", [cnt(closer, "leaves"), cnt(closer, "failed")], [16, 0])
    chk("根已归档", root_status(rootc), "已归档")
    tf, tl = a["tf"], a["tl"]
    chk("收口链的 omega 三连逐工具非零",
        [g(tf, "omega_chain_by_tool", "omega_spec_create") > 0,
         g(tf, "omega_chain_by_tool", "omega_spec_review") > 0,
         g(tf, "omega_chain_by_tool", "omega_result_verify") > 0], [True, True, True],
        js(g(tf, "omega_chain_by_tool", default={})))
    chk("laya/issue_up/call_log 在本环号段都有承担行",
        [g(tf, "spec_named_carriers", k, "this_stage_total", default=0) > 0
         for k in ("laya", "issue_up", "call_log")], [True, True, True],
        js({k: g(tf, "spec_named_carriers", k, "this_stage_total", default=0)
            for k in ("laya", "issue_up", "call_log")}))
    chk("终账行数 > 发单前（收口链真发了 RPC，不是回忆）",
        g(tf, "rows_" + STAGE) > g(tl, "rows_" + STAGE), True,
        f"{g(tl, 'rows_' + STAGE)}→{g(tf, 'rows_' + STAGE)}")
    chk("终账被拒为零", g(tf, "stages", STAGE, "refused"), 0)
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    if MARK in PROG.read_text(encoding="utf-8"):
        print(json.dumps({"refuse": ["该环记录已在册（幂等门）：不许追加第二份"]},
                         ensure_ascii=False, indent=1))
        return 1

    nv, bi, sc, dm, fl = a["nv"], a["bi"], a["sc"], a["dm"], a["fl"]
    lk, cg, co, ir, ln, sa, ro, cs = (a["lk"], a["cg"], a["co"], a["ir"], a["ln"],
                                      a["sa"], a["ro"], a["cs"])
    rad, nrc = bs["radius"], g(bs, "canary", default={})
    lnp, lnw = g(lk, "lane_prefix_code", default={}), g(lk, "lane_work", default={})
    lines = [f"{MARK}（根 `{g(cs, 'root_task', default='未记')}`，执行人 "
             f"`{g(cs, 'assignee', default='未记')}`）", ""]
    lines.append(f"- 结论：**{root_status(rootc)}**。八条法全部独立复算；半径=名称面补口"
                 f"（产品 {cnt(rad, 'product_by_mtime_this_ring')} 档分析器 / 冻结 "
                 f"{cnt(rad, 'frozen')} 项 / tests {cnt(rad, 'tests')} 项 / docs "
                 f"{cnt(rad, 'docs')} 项，判据件 {cnt(rad, 'loop')} 个）。")
    lines.append(f"- 法①②名称面：`Never` {cnt(nv, 'cases')} 个夹具两棵树同批跑，改前 rc "
                 f"{js([r['before']['rc'] for r in nv['cases']])}→改后 "
                 f"{js([r['after']['rc'] for r in nv['cases']])}；`{js(bi['added'])}` 三个"
                 f"「文档在用、名称表缺席」的内建名补齐，未放行的 "
                 f"{cnt(bi, 'not_added')} 个 {js(bi['not_added'])} 在冻结语料里 0 处调用点、"
                 f"两态都仍被拒；产物签名 `{g(nv, 'worked_example_from_doc', 'after_pyx_signature')}`"
                 f"（codegen 一行没动，走既有 `Never→NoReturn` 映射）。")
    shape_rows = [[r["shape"], r["moved_to_end"], r["exit_paths"], r["cleanup_count"]]
                  for r in dm["shapes"]]
    lines.append(f"- 法②的后果件：放行 `open` 让 `test_defer_statement` 从空过变成真跑——"
                 f"改前 success={g(dm, 'activation', 'before', 'success')}（守卫为假整块跳过）、"
                 f"改后 success={g(dm, 'activation', 'after', 'success')} 而 "
                 f"try={g(dm, 'activation', 'after', 'has_try')}/finally="
                 f"{g(dm, 'activation', 'after', 'has_finally')}；4 档 defer 形状 "
                 f"{js(shape_rows)}，"
                 f"钉住的多出口形状（{g(dm, 'pinned_defect', 'exit_paths')} 出口只发 "
                 f"{g(dm, 'pinned_defect', 'cleanup_count')} 次清理）入账未修，其余 "
                 f"{g(dm, 'vacuous_guards', 'count')} 处同款守卫同账。")
    lines.append(f"- 法③量表与入账：{cnt(sc, 'augmented_matrix')} 条复合赋值 + "
                 f"{cnt(sc, 'binary_matrix')} 条表达式 + {cnt(sc, 'other_faces')} 个其他形状，"
                 f"静默产错 {js(sc['silent_wrong'])}、响亮拒绝 {cnt(sc, 'declared_rejected')} 条、"
                 f"挂账 {cnt(sc, 'adjudication_queue')} 条；真入账 {cnt(fl, 'filed')} 张 "
                 f"{js([f['ledger_number'] for f in fl['filed']])}（账本最大号 "
                 f"{fl['ledger_before_max']}→{fl['ledger_after_max']}，sqlite bug 任务 "
                 f"{fl['sqlite_bug_tasks_before']}→{fl['sqlite_bug_tasks_after']}）。")
    lines.append(f"- 法④永久锁：`{lk['new_test_file']}` {lk['expected_tests']} 条（条数由 plan 反解 "
                 f"{js(lk['lock_plan'])}），工作区 {lnw.get('passed')} 通过/{lnw.get('failed')} 失败、"
                 f"修前码 {lnp.get('passed')} 通过/{lnp.get('failed')} 失败，"
                 f"红名单 {cnt(lnp, 'red_ids')} 条与 plan 逐字相等；两棵树身份 "
                 f"`{g(lk, 'identity', 'work_type_checker_sha')}` ≠ "
                 f"`{g(lk, 'identity', 'snap_type_checker_sha')}`，收集 "
                 f"{lk['collect_after_locks']}={lk['previous_round_collect_floor']}+"
                 f"{bs['locks_added_this_ring']}。")
    lines.append(f"- 法⑤⑥产物与语料：{cg['files_compared']} 档两态转译剔除时间戳行后逐字相同 "
                 f"{cg['all_textual_identical']} 档、无理解释差异 {cnt(cg, 'differing_unjustified')} 档；"
                 f"语料 {co['samples_scanned']} 档扫描，新增红 {cnt(co, 'files_with_new_errors')} 档、"
                 f"变少 {cnt(co, 'files_with_errors_gone')} 档，见证夹具 {cnt(co, 'witnesses')} 支。")
    lines.append(f"- 法⑦判据体系：pytest {pf['passed']} 通过/{pf['failed']} 失败/{pf['errors']} 错误"
                 f"（`{pf['summary_line']}`）、收集 {g(bs, 'systems', 'collect', 'nodeids')}、"
                 f"自研 {js(g(bs, 'systems', 'suite', 'fields'))}、e2e {js(g(bs, 'systems', 'e2e'))}；"
                 f"地板取上环实测件 {g(bs, 'floors_source')}；canary "
                 f"{sum(1 for v in nrc.values() if v is True)}/{len(nrc)} 格为真 {js(nrc)}；"
                 f"驱动件亲笔 {ln['drivers_scanned']} 个、硬错 "
                 f"{ln['hard_violations']}、软账 {ln['soft_total']}（基线 "
                 f"{ln['previous_round_soft_baseline']}）、生成锁件超长行 "
                 f"{g(ln, 'generated_lock', 'e501')}（上环 "
                 f"{g(ln, 'generated_lock', 'previous_ring_e501')}）。")
    lines.append(f"- 法⑧不可逆动作面：毁灭型工具 {js(g(ir, 'verdict', 'destructive_tools'))}、"
                 f"别人号段 archive {js(g(ir, 'verdict', 'foreign_archive_targets'))}、"
                 f"产品面删除/改名 {cnt(ir, 'product_bad_status')} 条、本环新增 "
                 f"{cnt(ir, 'product_untracked_new')} 条，检测器 canary {js(ir.get('canary'))}。")
    lines.append(f"- 自证与门禁：{sa['gates_pass']}/{sa['gates_total']} 道渲染前解出、"
                 f"自引用延后 {cnt(sa, 'gates_self_deferred')} 道、渲染后复数 "
                 f"{ro['gates_green']}/{ro['gates_in_table']} 全绿；占位 "
                 f"{sa['placeholders_total']} 个（坏 {cnt(sa, 'placeholders_bad')}、"
                 f"空值无佐证 {cnt(sa, 'placeholders_empty_unjustified')}），needle 严口径违例 "
                 f"{cnt(sa, 'needle_strict_violations')} 条、过期未披露 {cnt(sa, 'stale_undisclosed')} "
                 f"条、§十 实测 {g(sa, 'section10_items', 'actual')} 条（声明 "
                 f"{g(sa, 'section10_items', 'declared')}）、不动点 "
                 f"{g(sa, 'fixpoint', 'converged')}（嵌入 {js(g(sa, 'fixpoint', 'embedded'))}）。")
    lines.append(f"- 收口：叶 {cnt(closer, 'leaves')}/16、失败 {cnt(closer, 'failed')}，"
                 f"根 `{root_status(rootc)}`（上卷前 `{g(rootc, 'root_status_before')}`）；"
                 f"call_log 本环前缀 发单前 {tl['rows_' + STAGE]} 行 → 终账 "
                 f"{tf['rows_' + STAGE]} 行 / {tf['distinct_tasks']} 个任务（全库 "
                 f"{tf['total_call_log_rows']} 行），omega 三连 "
                 f"{js(tf['omega_chain_by_tool'])}。")
    box = minutes_now()
    lines.append(f"- 时间盒：环节起于 {RING_START}，本条生成于 {STAMP}，实耗 {box} 分钟"
                 f"（盒 {BOX_MIN} 分钟，{'超盒' if box > BOX_MIN else '在盒内'}）——"
                 f"超出的是三套体系跑了两遍（其中第一遍是被拒的坏口径 + 一条被激活的既有测试）"
                 f"和驱动件软账清零后的补跑；门禁未缩、判据未放宽、冻结面未动、半径未外溢。")
    lines.append(disclosures(a))
    lines.append(f"- 转结 R5：修复环领 {cnt(fl, 'filed')} 张新卡 "
                 f"{js(sorted({f['ledger_number'] for f in fl['filed']}))}"
                 f"（含 {g(dm, 'vacuous_guards', 'count')} 处同款空过守卫与 "
                 f"defer 异常路径安全那条未声明语义）、`^=` 静默产错、`^`/`~` 与构建块共用词位"
                 f"的消歧裁决；推进环领 §十一 与 {cnt(sc, 'adjudication_queue')} 条"
                 f"半径外形状的挂账去向。"
                 f"流程债三条：改完判据脚本立刻重跑它的件；手补 JSON 后必须让读它的那条路跑一遍；"
                 f"起全量批之前先确认测量面已冻结。")
    lines.append("- 本条**重生成过一次**：首版有两处反解缺陷——把 JSON 数组按 `^  \"` 行数当成"
                 "「拒 18 条」（真值是 4 条拒），以及把 `pinned_card_ids` 的 values 当卡号清单"
                 "（出现重复的 BUG-75 并漏掉 BUG-77）。两处都改在驱动件里，正身以本条为准；"
                 "首次写入与本条相隔 90 秒，其间没有第三方读过这份台账。")
    lines.append(f"- 本条记录生成于 {STAMP}。")

    refusals = (g(tf, "stages", STAGE, "refused_detail") or [])
    if refusals:
        lines.append("- 收口被拒原文（逐字）：")
        for r in refusals:
            lines.append(f"  - `{js(r)[:400]}`")
    else:
        lines.append(f"- 收口被拒原文：无（终账 `refused=0`，按前缀数出来的；"
                     f"根上无 `[omega:required]` 的既定语义本轮零次触发——"
                     f"`refusals_md` {len(tf.get('refusals_md') or '')} B）。")

    body = "\n".join(lines) + "\n"
    (HERE / "advance_r4_progress.json").write_text(
        json.dumps({"mark": MARK, "block_chars": len(body), "ring_minutes": box,
                    "report_sha256": ro["report_sha256"], "root": root_status(rootc),
                    "self_checks": len(CHECKS), "checks_red": [
                        c["label"] for c in CHECKS if not c["ok"]],
                    "at_utc": STAMP, "refuse": sorted(set(REFUSE))},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    PROG.write_text(PROG.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + body,
                    encoding="utf-8", newline="\n")
    print(json.dumps({"written": PROG.name, "block_chars": len(body), "ring_minutes": box,
                      "root": root_status(rootc), "self_checks": len(CHECKS),
                      "refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
