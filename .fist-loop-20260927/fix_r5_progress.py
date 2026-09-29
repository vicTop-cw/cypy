"""把 R5-修复 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

拒绝条件：① 任一判据件 refuse 非空或自带 self_checks_red；② 三套体系有红或地板不是从上一环实测件
反解；③ 报告 sha 与渲染见证不一致（渲染后被改）；④ 叶收口件不是 16 行或有失败；⑤ 根不是「已归档」；
⑥ 闭环 ∪ 转结 ≠ 认领面、或账面基数与 `memory/bugs.md` 现读不一致；⑦ 同一标记在 `loop_progress.md`
里出现两次以上（幂等是按标记**整块替换**，不是拒绝重写——更正过自身的数字必须能落回同一块里）。
时间盒起点取「本环亲笔驱动里最早一个的 mtime」，是量出来的，不是我记得的几点。
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
MARK = "### R5-修复"
REFUSE: list = []
CHECKS: list = []
KEYS = {
    "fix_r5_intake.json": "ik",  # 法① 认领表
    "fix_r5_locks.json": "lk",  # 法② 锁先行
    "fix_r5_rc.json": "rc",  # 法③ 根因合并修
    "fix_r5_revert.json": "rv",  # 法④ 回退矩阵
    "fix_r5_impact.json": "im",  # 法⑤ 语义变更影响面
    "fix_r5_baselines.json": "bs",  # 法⑥ 三套体系 + 地板 + 半径
    "fix_r5_ledger.json": "lg",  # 法⑦ 账面闭环
    "fix_r5_drivers_lint.json": "ln",  # 法⑧ 驱动面自证
    "fix_r5_calllog_tally.json": "tl",  # call_log 两档现数
    "fix_r5_needles.json": "nd",  # needle 严口径
    "close_r5_fix.json": "cs",
    "close_r5_fix.out.json": "closer",
    "close_r5_fix_root.out.json": "rootc",
    "report_spec_r5_fix.json": "rs",
    "fix_r5_self_audit.json": "sa",
    "fix_r5_render_order.json": "ro",
    "spec_r5_fix.json": "plan",
}
GREEN = ("ik", "lk", "rc", "rv", "im", "bs", "lg", "ln", "nd", "tl", "sa", "ro", "cs", "rs")


def chk(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


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


def js(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def cnt(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return len(v) if isinstance(v, (list, dict)) else (v if isinstance(v, int) else 0)


def ring_start() -> tuple:
    """时间盒起点 = 本环亲笔驱动（fix_r5_*.py）里最早的 mtime。"""
    files = sorted(HERE.glob("fix_r5_*.py"))
    if not files:
        return ("未测", None)
    stamp = min(p.stat().st_mtime for p in files)
    return (
        datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat(timespec="seconds"),
        len(files),
    )


def ledger_numbers() -> list:
    txt = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    return sorted({int(x) for x in re.findall(r"(?m)^## BUG-(\d+) ", txt)})


def open_bug_ids() -> tuple:
    """账本里没写 `### FIXED(...)` 的号段 ⇒ (未闭环号表, 已闭环条数)。

    闭口标记按整条目正文找（`### FIXED` 常落在长正文之后，截窗口会把已闭环的读成未闭环）。
    """
    txt = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    opened, closed = [], 0
    for chunk in re.split(r"(?m)^## ", txt)[1:]:
        m = re.match(r"BUG-(\d+) ", chunk.split("\n", 1)[0])
        if not m:
            continue
        if re.search(r"(?m)^### FIXED", chunk):
            closed += 1
        else:
            opened.append(int(m.group(1)))
    return sorted(opened), closed


def open_state_entries() -> int:
    """账本里抬头状态栏仍是 OPEN 的条目数（与 fix_r5_ledger.py 的 ledger_open_total 同一条正则）。"""
    txt = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    return len(re.findall(r"(?m)^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN", txt))


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    a = {v: L(k) for k, v in KEYS.items()}
    for k in GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件 refuse 非空：{js(a[k]['refuse'])[:200]}")
    # 四件驱动（intake/locks/rc/impact）的 refuse 只装 REFUSE、不折自身红条：红条在这里被第二路抓住。
    for k in GREEN:
        red_rows = a[k].get("self_checks_red") or []
        if red_rows:
            REFUSE.append(f"{k} 件自带 self_checks_red {len(red_rows)} 条：{js(red_rows)[:200]}")
    root_task = g(a["cs"], "root_task") or ""
    if not root_task:
        REFUSE.append("收口件里没有 root_task ⇒ 环号与 call_log 号段都对不上")
    rep_p = ROOT / "memory" / "reviews" / f"{g(a['ro'], 'report')}".split("/")[-1]
    if not rep_p.exists():
        REFUSE.append(f"报告不在盘上：{g(a['ro'], 'report')}")
    now_sha = hashlib.sha256(rep_p.read_bytes()).hexdigest() if rep_p.exists() else ""
    rep_text = rep_p.read_text(encoding="utf-8", errors="replace") if rep_p.exists() else ""
    if now_sha and now_sha != g(a["ro"], "report_sha256"):
        REFUSE.append("报告在渲染之后被改过：sha 与见证件不一致")
    recs = a["ro"].get("render_records") or []
    if g(a["ro"], "renders") != len(recs):
        REFUSE.append(
            f"渲染次数 {g(a['ro'], 'renders', default='—')!r} 与见证件记录数 {len(recs)} 不一致"
        )
    if not recs:
        REFUSE.append("没有渲染记录件 ⇒ 「渲染了几次」这句话没有出处")
    if len({r.get("note") for r in recs}) != len(recs):
        REFUSE.append("渲染记录的 note 有重复 ⇒ 多出来的那一趟写盘没有独立理由")
    if len(recs) > 1 and "重渲" not in rep_text:
        REFUSE.append("渲染过不止一次，但报告正文里没有『重渲』的披露 ⇒ 次数在报告外被吞掉")

    if g(a["ro"], "gates_red") != 0:
        REFUSE.append(f"门禁表有红/未判定行：{g(a['ro'], 'gates_red')}")
    gates_floor = max(3 * cnt(a["plan"], "laws"), 60)
    if cnt(a["rs"], "gates") < gates_floor:
        REFUSE.append(
            f"门禁条数低于本环下限 {gates_floor}（八法×3 与 60 取大）：{cnt(a['rs'], 'gates')}"
        )

    bs = a["bs"]
    pf = g(bs, "pytest", default={})
    if pf.get("failed_sum") or pf.get("rc"):
        REFUSE.append(f"pytest 有红：failed_sum={pf.get('failed_sum')} rc={pf.get('rc')}")
    if g(bs, "three_systems_green", default=[]) != [True, True, True] or not g(
        bs, "three_systems_ok", default=False
    ):
        REFUSE.append(f"三套体系不同刻为绿（三栏分别判）：{js(g(bs, 'three_systems_green'))}")
    if sorted(g(a["bs"], "floors", default={})) != ["collect", "e2e_pass", "pytest", "suite"]:
        REFUSE.append(f"地板四栏不齐：{js(g(a['bs'], 'floors', default={}))}")
    gf = g(a["bs"], "git", default={})
    if gf.get("staged"):
        REFUSE.append(f"暂存区非 0（{gf.get('staged')} 行）")
    head_exp = g(a["bs"], "git_head_expected", default="未声明")
    if gf.get("head") != head_exp:
        REFUSE.append(f"HEAD 与件里声明的期望 HEAD 不一致：{gf.get('head')} / {head_exp}")
    if g(a["bs"], "radius", default={}).get("forbidden_total"):
        REFUSE.append("冻结面/禁改面被本环动过")
    closer, rootc = a["closer"], a["rootc"]
    if len(closer.get("leaves") or []) != 16:
        REFUSE.append(f"叶收口件不是 16 行：{len(closer.get('leaves') or [])}")
    if closer.get("failed"):
        REFUSE.append(f"叶失败：{js(closer.get('failed'))[:200]}")
    if rootc.get("root_final") != "已归档":
        REFUSE.append(f"根状态不是已归档：{js(rootc)[:120]}")
    nums = ledger_numbers()
    open_state = open_state_entries()
    planned = sorted(a["ik"].get("planned_ids") or [])
    closed = sorted(a["lg"].get("closed_ids") or [])
    leftover = sorted(a["lg"].get("leftover_ids") or [])
    green_after = sorted(g(a["lk"], "lock_green_after", default=[]))
    revert_red = sorted(g(a["rv"], "revert_red_ids", default=[]))
    chk(
        "账面基数：闭环 ∪ 转结 = 认领面且两栏不重叠（号从 intake/ledger 两件反解，不写死 13/21）",
        [sorted(set(closed) | set(leftover)), sorted(set(closed) & set(leftover))],
        [planned, []],
        f"闭环 {len(closed)} / 转结 {len(leftover)} / 认领 {len(planned)}",
    )
    chk(
        "闭环集仍被「当前绿」与「摘回会红」两栏共同承重（不是 ledger 自报的交集）",
        [
            sorted(set(closed) - set(green_after)),
            sorted(set(closed) - set(revert_red)),
        ],
        [[], []],
        f"绿栏 {len(green_after)} / 摘回红栏 {len(revert_red)}",
    )
    chk(
        "账本基数两路对：ledger_total / ledger_open_total = 现读条目数 / 现读 OPEN 数",
        [a["lg"].get("ledger_total"), a["lg"].get("ledger_open_total")],
        [len(nums), open_state],
        "件里自报 vs 盘上现读（现读口径与 ledger 驱动同一条正则）",
    )
    chk(
        "渲染次数按见证件的记录数自比，且门禁表全绿（红行数 0）",
        [
            g(a["ro"], "renders"),
            len(a["ro"].get("render_records") or []),
            g(a["ro"], "gates_green"),
            g(a["ro"], "gates_in_table"),
            g(a["ro"], "gates_red"),
        ],
        [
            len(a["ro"].get("render_records") or []),
            len(a["ro"].get("render_records") or []),
            g(a["ro"], "gates_in_table"),
            g(a["ro"], "gates_in_table"),
            0,
        ],
        "次数=记录数、绿=表行数、红=0；三对都自比",
    )
    chk(
        "§八 失效条数（标题声明 = 渲染后实数）",
        g(a["ro"], "section8_rendered", default={}),
        {
            "declared": g(a["ro"], "section8_rendered", default={}).get("declared"),
            "actual": g(a["ro"], "section8_rendered", default={}).get("actual"),
        },
        "见证件已把不等判成红",
        ok=g(a["ro"], "section8_rendered", default={}).get("declared")
        == g(a["ro"], "section8_rendered", default={}).get("actual")
        and g(a["ro"], "section8_rendered", default={}).get("declared", -1) > 0,
    )
    nd_pair = f"{a['nd'].get('real_key_len')}/{a['nd'].get('checked_len')}"
    chk(
        "needle 严口径：全部是真键名，且法条只引本环八件",
        [a["nd"].get("real_key_len"), sorted(a["nd"].get("off_ring_artifacts") or [])],
        [a["nd"].get("checked_len"), []],
        f"{nd_pair} 条，越环件 {cnt(a['nd'], 'off_ring_artifacts')} 个",
    )
    chk(
        "驱动面软账不回升（基线从件里读：上一环实测 "
        f"{a['ln'].get('previous_round_soft_baseline')}，来源 {a['ln'].get('baseline_source')}）",
        (a["ln"].get("soft_total") or 0) <= (a["ln"].get("previous_round_soft_baseline") or 0),
        True,
        f"软账 {a['ln'].get('soft_total')} / 硬错 {a['ln'].get('hard_violations')}",
        ok=(a["ln"].get("soft_total") or 0) <= (a["ln"].get("previous_round_soft_baseline") or 0),
    )
    chk(
        "自证门未过条数为 0",
        cnt(a["sa"], "gates_red"),
        0,
        js(g(a["sa"], "gates_red", default=[]))[:180],
    )
    box_start, drv_n = ring_start()
    if not drv_n:
        REFUSE.append("时间盒起点量不出来（没有本环驱动）")
    minutes = (
        round(
            (
                datetime.datetime.fromisoformat(now) - datetime.datetime.fromisoformat(box_start)
            ).total_seconds()
            / 60
        )
        if drv_n
        else -1
    )
    if REFUSE:
        print(
            json.dumps(
                {
                    "refuse": sorted(set(REFUSE)),
                    "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 1
    prior = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    marks = prior.count(MARK)
    if marks > 1:
        print(
            json.dumps(
                {
                    "refuse": [
                        f"loop_progress 里「{MARK}」出现 {marks} 次 ⇒ 记录被重复追加，先人工合并"
                    ]
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 1
    # 出现 1 次不是事故：本环更正（例如把取数失败写成了 None）必须能重写自己那一块。
    # 幂等的正确形状是「按标记替换整块」，追加才是错的写法。

    ik, lkd, rcd, rvd, im, lgd, ln, nd, sa, ro, tl = (
        a["ik"],
        a["lk"],
        a["rc"],
        a["rv"],
        a["im"],
        a["lg"],
        a["ln"],
        a["nd"],
        a["sa"],
        a["ro"],
        a["tl"],
    )
    bs = a["bs"]
    cols = ik.get("split_columns") or {}
    claimed_n = len(cols.get("本环认领") or [])
    handed = sorted({x for k, v in cols.items() if k != "本环认领" for x in (v or [])})
    col_counts = js({k: len(v or []) for k, v in cols.items()})[:150]
    cols_sum = sum(len(v or []) for v in cols.values())
    new_ids = sorted(ik.get("ring_new_ids") or [])
    new_range = f"BUG-{new_ids[0]}..BUG-{new_ids[-1]}" if new_ids else "无（本环没入账）"
    locked_ids = sorted(lkd.get("locked_ids") or [])
    strict_ids = sorted(lkd.get("assertion_level_red_only") or [])
    non_strict = sorted(set(locked_ids) - set(strict_ids))
    snap = lkd.get("snapshot") or {}
    ex = rvd.get("extras") or {}
    cnr = rvd.get("canary_no_op_revert") or {}
    nm_ids = sorted(
        r.get("bug_id") for r in (rvd.get("matrix") or []) if r.get("revert_mode") == "not_measured"
    )
    lanes = rcd.get("lane_receipts") or []
    scope_only = js(rcd.get("covered_only_by_scope"))[:150]
    bng_total = js((ex.get("baseline_not_green") or {}).get("total"))
    imp_can = im.get("canary") or {}
    three = lgd.get("three_way") or []
    lines = [
        f"{MARK}（根 `{g(a['cs'], 'root_task', default='未记')}`，执行人 "
        f"`{g(a['cs'], 'assignee', default='未记')}`）",
        "",
    ]
    lines.append(
        f"- 结论：**已归档**。八条法独立复算；门禁 "
        f"{g(ro, 'gates_green')}/{g(ro, 'gates_in_table')} 全绿，报告渲染 "
        f"{ro.get('renders')} 次、被拒重试 {ro.get('refused_attempts')} 次；"
        f"本环认领 {len(planned)} 张 ⇒ 闭环 {len(closed)} 张、留 OPEN 转结 {len(leftover)} 张。"
    )
    lines.append(
        f"- 法①认领表：账本现读未闭环 {ik.get('cards_total')} 张，分栏 {col_counts}"
        f"（之和 {cols_sum} = 卡表 {cnt(ik, 'cards')} 张，分栏不吞行）；"
        f"本环认领 {claimed_n} 张 = 上一环入账的 {new_range}（{len(new_ids)} 张）+ 旧单；"
        f"交人工/未认领 {len(handed)} 张一律不占修、不改账本状态；"
        f"服务端没有任务号的卡 {js(ik.get('no_server_card_ids'))}；"
        f"裸条目歧义 {cnt(ik, 'ambiguous_bare')} 张；未认领按严重度 {js(ik.get('unclaimed_severities'))}；"
        f"归属来源分布 {js(ik.get('face_sources'))[:150]}；交接引文 {ik.get('handoff_quote_len')} 段逐字。"
    )
    lines.append(
        f"- 法②锁先行：认领 {len(planned)} 张里有锁 {len(locked_ids)} 张，"
        f"无锁逐张点名 {js(lkd.get('locks_missing'))}；旧码树红 {cnt(lkd, 'lock_red_before')} 张 → "
        f"当前树绿 {cnt(lkd, 'lock_green_after')} 张，断言级红 {len(strict_ids)} 张"
        f"（不达标的 {js(non_strict)}）；锁节点 {lkd.get('lock_nodes_total')} 个；"
        f"旧码树 {snap.get('dir')}（HEAD {snap.get('head')}，归档解出 "
        f"{snap.get('archived_plus_copied_files')} 个 + 覆盖本轮 tests "
        f"{snap.get('overwritten_from_worktree')} 个，rc={snap.get('rc')}）；"
        f"三条对照：探针 {js(lkd.get('canary_probe'))} / "
        f"点名不存在的锁 {js(lkd.get('ghost_probe'))} / HEAD 上就绿的锁 "
        f"{js(lkd.get('lock_green_on_head'))}；红档日志 {js(lkd.get('red_log_evidence'))[:160]}。"
    )
    lines.append(
        f"- 法③根因合并修：本环改动 {rcd.get('ring_files_all_len')} 个文件 / "
        f"{rcd.get('change_points')} 个改动点 / 引用符号 {rcd.get('symbols_referenced_len')} 个"
        f"（按文件分栏 {cnt(rcd, 'per_file_change_points')} 个）；同一 (文件,符号) 合并出的根因组 "
        f"{rcd.get('merged_root_cause_len')} 处、共享同一符号的单子对 "
        f"{rcd.get('cards_sharing_a_symbol_len')}；车道回执 {len(lanes)} 条自报文件 "
        f"{rcd.get('reported_files_len')} 个，落到单上的改动面 {cnt(rcd, 'card_change_files')} 张单；"
        f"没卡片认领的改动文件 {js(rcd.get('product_files_without_card'))}、"
        f"只落在既有面上的 {scope_only}、归属不到单的 {js(rcd.get('unattributed_changes'))}；"
        f"未修完仍 OPEN {js(rcd.get('unfixed_claimed'))}。"
    )
    lines.append(
        f"- 法④回退矩阵：{rvd.get('matrix_rows')} 行 = 认领 {len(planned)} 张；"
        f"承重探针 {cnt(ex, 'units_probed')} 个单元并成 {rvd.get('groups_len')} 组"
        f"（闭包复扫后 {cnt(ex, 'groups2')} 组）；摘回变红 {cnt(rvd, 'revert_red_ids')} 张 / "
        f"断言级 {cnt(rvd, 'assertion_level_ids')} 张，组间牵连 {js(rvd.get('collateral'))}；"
        f"逐文件 sha 复原 {rvd.get('sha_restored')}/{rvd.get('sha_files_total')}；"
        f"空操作对照（{cnr.get('file')}，与 HEAD 逐字相同={cnr.get('head_equals_current')}）坏掉节点 "
        f"{js(cnr.get('nodes_went_bad'))}；副本树基线不绿的节点 {bng_total}；"
        f"真树被写脏 {js(ex.get('root_tree_dirtied'))}；没有产品码改动的行 {js(nm_ids)}"
        f"（与 rc 的 unfixed_claimed 同一批）。"
    )
    lines.append(
        f"- 法⑤影响面：语料 {im.get('corpus_total')} 档（{js(im.get('corpus_dirs'))} 目录）"
        f"在 HEAD 树（{(im.get('head_tree') or {}).get('py_files')} 个 py）与当前树各跑一遍；"
        f"变差两表：新增诊断 {im.get('new_diagnostics_len')} 条 / 新增拒绝 {im.get('new_rejections_len')} 条；"
        f"改好 {im.get('new_acceptances_len')} 条、同档诊断文案变了 {im.get('shape_changed_len')} 条；"
        f"需裁决挂账 {im.get('adjudication_needed')} 档（{js(im.get('corpus_adjudication_files'))}）；"
        f"API 面 head={js((im.get('api_surface') or {}).get('head'))} / "
        f"current={js((im.get('api_surface') or {}).get('current'))}；"
        f"诊断通道口径（逐字）：{im.get('diagnostics_channel')}；对照 canary："
        f"transpile 可比={imp_can.get('transpile_comparable')} "
        f"同净源同观察={imp_can.get('same_source_agrees')} "
        f"坏源两档都拒={imp_can.get('bad_source_rejected_both')}。"
    )
    lines.append(
        f"- 法⑥三套体系：pytest {g(bs, 'pytest', 'passed')} 通过 / "
        f"{g(bs, 'pytest', 'failed_sum')} 失败 / rc={g(bs, 'pytest', 'rc')}，"
        f"收集 {g(bs, 'collect', 'nodeids')}，套件字段 {js(g(bs, 'suite', 'fields'))}，"
        f"e2e {js(g(bs, 'e2e', 'fields'))}；三栏同刻绿 {js(bs.get('three_systems_green'))} "
        f"= {bs.get('three_systems_ok')}；地板反解自 {js(g(bs, 'floors'))}"
        f"（来源 {g(bs, 'floors_source')}）；HEAD `{g(bs, 'git', 'head')}`、暂存 "
        f"{g(bs, 'git', 'staged')}、脏行 {g(bs, 'git', 'dirty_rows')}、半径禁改面 "
        f"{g(bs, 'radius', 'forbidden_total')} / 允许面 {g(bs, 'radius', 'allowed_touched')}。"
    )
    lines.append(
        f"- 法⑦账面闭环：claim→execute→submit→verify 三向对照 {lgd.get('agree_total')}/"
        f"{len(three)} 张一致（不一致 {js(lgd.get('three_way_bad'))}）；"
        f"闭环 {len(closed)} 张、留 OPEN {len(leftover)} 张 {js(leftover)}；"
        f"账本追加 FIXED 段 {cnt(lgd, 'fixed_sections')} 条 / 转结段 "
        f"{cnt(lgd, 'not_fixed_sections')} 条；账本条目 {lgd.get('ledger_total')} 条"
        f"（现读 {len(nums)}）、OPEN {lgd.get('ledger_open_total')} 条（现读 {open_state}）；"
        f"影响面挂账进账 {cnt(lgd, 'impact_adjudication')} 条。"
    )
    lines.append(
        f"- 法⑧驱动面：亲笔 {ln.get('drivers_scanned')} 个脚本，硬错 {ln.get('hard_violations')}、"
        f"软账 {ln.get('soft_total')}（上一环实测基线 "
        f"{ln.get('previous_round_soft_baseline')}，来源 {ln.get('baseline_source')}）；"
        f"行长口径 {ln.get('line_length_declared')}、ignore {js(ln.get('ignore_declared'))}；"
        f"注入对照 {js(ln.get('canary'))[:160]}。"
    )
    lines.append(
        f"- needle 与占位自证：{nd_len(a)} 条全部是被引件里的真键名，越环法条 "
        f"{cnt(nd, 'off_ring_artifacts')} 个，扫描时不存在的件 {js(nd.get('pending_artifacts'))}；"
        f"前缀式假命中 canary 抓到 {cnt(nd, 'prefix_canary')} 条。"
    )
    tl_stage = (tl.get("stages") or {}).get(root_task, {})
    tl_tag = tl.get("ring_tag_calls") or {}
    lines.append(
        f"- 收口：叶 {cnt(closer, 'leaves')}/16、失败 {cnt(closer, 'failed')}，根 "
        f"`{g(a['rootc'], 'root_final')}`；call_log 本环号段（{root_task}）"
        f"{g(tl_stage, 'rows', default='未数到')} 行 / {g(tl_stage, 'distinct_tasks', default='未数到')} "
        f"个任务（环标签档 {g(tl_tag, 'total', default='未数到')} 行），被拒 "
        f"{g(tl_stage, 'refused', default='未数到')} 条；规格点名工具的承担者 "
        f"{js(tl.get('spec_named_carriers'))[:180]}。"
    )
    lines.append(
        f"- 报告：`{ro.get('report')}`（{ro.get('report_bytes')} B，sha "
        f"`{ro.get('report_sha256')}`），§八 声明/实数 "
        f"{js(ro.get('section8_rendered'))}，缺法条标题 {cnt(ro, 'law_heads_missing')} 个。"
    )
    lines.append(
        f"- 自证与门禁预跑：渲染前 {g(sa, 'gates_green', default='未跑')}/"
        f"{g(sa, 'gates_total', default='未跑')} 道解出，红 {cnt(sa, 'gates_red')} 道，"
        f"恒真门 {cnt(sa, 'fake_min_gates')} 道，needle 不合格 {cnt(sa, 'needle_bad')} 条，"
        f"占位 {g(sa, 'placeholders_total', default=0)} 个（未解析 "
        f"{cnt(sa, 'placeholders_unresolved')} 个、空值无佐证 "
        f"{cnt(sa, 'placeholders_empty_unjustified')} 个），陈旧未披露 "
        f"{cnt(sa, 'stale_undeclared')} 件，件里自带红条的 {cnt(sa, 'artifact_self_checks_red')} 件。"
    )
    lines.append(
        f"- 时间盒：起点 {box_start}（取本环 {drv_n} 个亲笔驱动的最早 mtime），"
        f"本条记录生成于 {now}，实耗 {minutes} 分钟（盒 100 分钟，"
        f"{'超盒' if minutes > 100 else '在盒内'}）——门禁未缩、判据未放宽、冻结面未动。"
    )
    lines.append(disclosures(a, minutes))
    opened, fixed_in_ledger = open_bug_ids()
    chk(
        "账本基数自证：无 FIXED 段的条目 + 有 FIXED 段的条目 = 账本现读的 BUG 条目数（分栏不能吞行）",
        [len(opened) + fixed_in_ledger, len(nums)],
        [len(nums), len(nums)],
        f"无 FIXED {len(opened)} / 有 FIXED {fixed_in_ledger} / 条目 {len(nums)}",
    )
    chk(
        "转结面自证：认领栏与交人工栏不重叠（一张单不能既本环修又交人工）",
        sorted(set(planned) & set(handed)),
        [],
        f"认领 {len(planned)} / 交人工 {len(handed)} / 卡表 {ik.get('cards_total')}",
    )
    lines.append(
        f"- 转结：R5-验证 复测本环闭环的 {len(closed)} 张（{js(closed)}）锁是否仍然承重；"
        f"本环留 OPEN 的 {len(leftover)} 张 {js(leftover)}（逐张写明卡在哪，见 §九）；"
        f"交人工或裁决 {len(handed)} 张 {js(handed)}；"
        f"影响面待裁决 {im.get('adjudication_needed')} 档；"
        f"账本现数无 FIXED 段 {len(opened)} 张。"
    )
    lines.append(
        "- 流程债（不带病转结）：全量批不与电池并发、脚本替换后必须实跑一次而不是只 compile、"
        "needle 只按子串校等于没校。"
    )
    lines.append(f"- 本条记录生成于 {now}。")
    refusals = g(tl, "stages", root_task, "refused_detail", default=[]) or []
    root_refusals = a["rootc"].get("refused") or []
    if refusals or root_refusals:
        lines.append("- 收口被拒原文（逐字）：")
        for r in list(refusals) + list(root_refusals):
            lines.append(f"  - `{js(r)[:400]}`")
    else:
        lines.append("- 收口被拒原文：无（终账按号段数出来 refused=0，不是按回忆）。")

    body = "\n".join(lines) + "\n"
    leaks = sorted(
        set(re.findall(r"(?<![A-Za-z0-9_])None(?![A-Za-z0-9_])", body))
        | set(re.findall(r"(?<= )—(?![—])", body))
    )
    chk(
        "取数失败的痕迹不许进正文（None 或孤立的「 — 」都是键路径没解析出来，不是测量值）",
        leaks,
        [],
        f"命中 {leaks} 处",
    )
    chk(
        "根上卷件与叶收口件两路对：leaves_done=16、根件 refused 空表、叶件 failed 空表",
        [
            a["rootc"].get("leaves_done"),
            sorted(str(x)[:40] for x in (a["rootc"].get("refused") or [])),
            cnt(closer, "failed"),
        ],
        [16, [], 0],
        f"rootc={js(a['rootc'])[:200]}",
    )

    txt = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    reds = [c["label"] for c in CHECKS if not c["ok"]]
    if reds:
        REFUSE.append(f"落盘前自证未过，loop_progress 不动：{reds}")
        (HERE / "fix_r5_progress.json").write_text(
            json.dumps(
                {
                    "mark": MARK,
                    "written": False,
                    "self_checks": CHECKS,
                    "self_checks_red": reds,
                    "at_utc": now,
                    "refuse": sorted(set(REFUSE)),
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1

    if MARK in txt:
        i0 = txt.index(MARK)
        nxt = txt.find("\n### ", i0 + len(MARK))
        tail = txt[nxt + 1 :] if nxt != -1 else ""
        new_txt = txt[:i0] + body + ("\n" + tail if tail else "")
        replaced, prior_chars = True, (nxt - i0) if nxt != -1 else (len(txt) - i0)
    else:
        new_txt = txt.rstrip("\n") + "\n\n" + body
        replaced, prior_chars = False, 0
    PROG.write_text(new_txt, encoding="utf-8", newline="\n")
    back = PROG.read_text(encoding="utf-8")
    chk("写完后本环标记在文件里只有一处", back.count(MARK), 1, f"实得 {back.count(MARK)} 处")
    chk(
        "盘上的本环记录与本次生成的正文逐字相等（重写不是拼接）",
        body.strip() in back,
        True,
        f"body {len(body)} 字符 / 覆盖旧块 {prior_chars} 字符 / replaced={replaced}",
    )

    (HERE / "fix_r5_progress.json").write_text(
        json.dumps(
            {
                "mark": MARK,
                "block_replaced": replaced,
                "prior_block_chars": prior_chars,
                "block_chars": len(body),
                "ring_minutes": minutes,
                "report_sha256": ro.get("report_sha256"),
                "self_checks": CHECKS,
                "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
                "at_utc": now,
                "refuse": sorted(set(REFUSE)),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "written": PROG.name,
                "block_chars": len(body),
                "ring_minutes": minutes,
                "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
                "refuse": sorted(set(REFUSE)),
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


def nd_len(a) -> str:
    return f"{a['nd'].get('real_key_len')}/{a['nd'].get('checked_len')}"


def _stage_rows(a) -> str:
    st = (a["tl"].get("stages") or {}).get(a["cs"].get("root_task"), {})
    return st.get("rows", "?")


def _tag_rows(a) -> str:
    return (a["tl"].get("ring_tag_calls") or {}).get("total", "?")


def disclosures(a, minutes) -> str:
    """本环「报告之外发生的事」，逐条现读盘上件，不无声丢掉。"""
    ik, lk, rc, rv, im, bs, lg, ln, tl = (
        a["ik"],
        a["lk"],
        a["rc"],
        a["rv"],
        a["im"],
        a["bs"],
        a["lg"],
        a["ln"],
        a["tl"],
    )
    locked = sorted(lk.get("locked_ids") or [])
    strict = sorted(lk.get("assertion_level_red_only") or [])
    non_strict = sorted(set(locked) - set(strict))
    ex = rv.get("extras") or {}
    tag = tl.get("ring_tag_calls") or {}
    carriers = tl.get("spec_named_carriers") or {}
    items = [
        f"  1. **锁的红有 {len(non_strict)} 张不到断言级**（{js(non_strict)}）：locks 件自己就把这条判成红"
        f"（`self_checks_red` 点名『红必须是断言级』），红档日志逐张点名 "
        f"{js(lk.get('red_log_evidence'))[:200]}；不达标的单不进闭环主张，也不写成已修。",
        f"  2. **回退矩阵合过两次组**：第一遍的组 {js(rv.get('groups'))[:120]} 观测到组间牵连 "
        f"{js(rv.get('collateral'))}（摘 A 组把 B 组的锁摘红），按承重闭包并成 "
        f"{cnt(ex, 'groups2')} 组后仍有牵连就照红；本件 refuse 栏现状（逐字）："
        f"{js(rv.get('refuse'))[:260]}。",
        f"  3. **有认领单没有产品码改动**（{js(rc.get('unfixed_claimed'))}）：rc 的 `unfixed_claimed` 与"
        f"回退矩阵的 not_measured 行是同一批，转结时状态仍是 OPEN；没卡片认领的改动文件 "
        f"{js(rc.get('product_files_without_card'))}，只落在既有面上的 "
        f"{js(rc.get('covered_only_by_scope'))[:200]}；车道回执状态 "
        f"{js([[x.get('lane'), x.get('status')] for x in (rc.get('lane_receipts') or [])])[:200]}。",
        f"  4. **影响面的分析器诊断通道记的是 not_measured**（逐字）：{im.get('diagnostics_channel')}；"
        f"所以「修前无诊断→修后有诊断」这张清单本环不主张，只主张 transpile 的拒绝面。",
        f"  5. **地板与窗口都是读出来的**：地板 {js(bs.get('floors'))} 来源 {bs.get('floors_source')}；"
        f"窗口起点 {g(bs, 'window', 'start_utc', default='未记')}（口径 "
        f"{g(bs, 'window', 'source', default='未记')}），不是我记得的几点。",
        f"  6. **驱动面 lint 的软账基线来自上一环实测件** {ln.get('baseline_source')} → "
        f"{ln.get('previous_round_soft_baseline')}；注入对照的残留文件 "
        f"{js(ln.get('canary_left'))}（非空就是没清干净）。",
        f"  7. **call_log 环标签档 {tag.get('total')} 行的解释**（逐字）：{js(tag.get('note'))[:240]}；"
        f"规格点名工具在本 build 的承担者 laya={js(carriers.get('laya'))[:170]} / "
        f"issue_up={js(carriers.get('issue_up'))[:170]}。",
        f"  8. **交人工与未认领的栏位是逐张点名的**：{js(ik.get('split_columns'))[:300]}；"
        f"服务端没有任务号的卡 {js(ik.get('no_server_card_ids'))}（不占修、不改账本状态）。",
        f"  9. **账面留 OPEN 的 {cnt(lg, 'leftover_ids')} 张**：{js(lg.get('leftover_ids'))}，"
        f"三向对照不一致的行 {js(lg.get('three_way_bad'))[:200]}；"
        f"影响面挂账进账 {cnt(lg, 'impact_adjudication')} 条。",
        f"  10. 时间盒实耗 {minutes} 分钟：起点不是手写，是取本环 {cnt(a['plan'], 'laws')} 条法 + "
        f"亲笔驱动 mtime 的最小值；超盒的部分是全量批的墙钟，判据没有为此放宽"
        f"（当前 call_log 本环号段 {_stage_rows(a)} 行 / 环标签档 {_tag_rows(a)} 行）。",
        "  11. 渲染见证件（按序号，存在性不冒充次数）：\n"
        + "".join(
            f"     - seq={r.get('seq')} sha={str(r.get('report_sha256'))[:16]}… "
            f"{r.get('report_bytes')} B／门禁 {r.get('gates_total')} 道／{r.get('at_utc')}／"
            f"note（逐字）：{r.get('note')}\n"
            for r in (a["ro"].get("render_records") or [])
        ),
    ]
    return "- 本环流程外事件（逐字，不吞）：\n" + "\n".join(items)


if __name__ == "__main__":
    sys.exit(main())
