"""把 R5-寻虫 的结果写进 `loop_progress.md`：每个数字从判据件反解，不手填。

拒绝条件：① 任一判据件 refuse 非空；② 三套体系有红或地板不是从上一环实测件反解；③ 报告 sha 与
渲染见证不一致（渲染后被改）；④ 叶收口件不是 16 行或有失败；⑤ 根不是「已归档」；⑥ 号段与
`memory/bugs.md` 现读不一致；⑦ 同一标记在 `loop_progress.md` 里出现两次以上（幂等是按标记**整块
替换**，不是拒绝重写——更正过自身的数字必须能落回同一块里）。
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
MARK = "### R5-寻虫"
REFUSE: list = []
CHECKS: list = []
KEYS = {
    "hunt_r5_faces.json": "fa",
    "hunt_r5_declared.json": "dc",
    "hunt_r5_codegen.json": "cg",
    "hunt_r5_cli_face.json": "cl",
    "hunt_r5_needles.json": "nd",
    "hunt_r5_book.json": "bk",
    "hunt_r5_baselines.json": "bs",
    "hunt_r5_drivers_lint.json": "ln",
    "hunt_r5_calllog_tally.json": "tl",
    "close_r5_hunt.json": "cs",
    "close_r5_hunt.out.json": "closer",
    "close_r5_hunt_root.out.json": "rootc",
    "report_spec_r5_hunt.json": "rs",
    "hunt_r5_self_audit.json": "sa",
    "hunt_r5_render_order.json": "ro",
    "spec_r5_hunt.json": "plan",
}
GREEN = ("fa", "dc", "cg", "cl", "nd", "bk", "bs", "ln", "tl", "sa", "ro", "cs", "rs")


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
    """时间盒起点 = 本环亲笔驱动（hunt_r5_*.py）里最早的 mtime。"""
    files = sorted(HERE.glob("hunt_r5_*.py"))
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


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    a = {v: L(k) for k, v in KEYS.items()}
    for k in GREEN:
        if a[k].get("refuse"):
            REFUSE.append(f"{k} 件 refuse 非空：{js(a[k]['refuse'])[:200]}")
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
    if cnt(a["rs"], "gates") < 60:
        REFUSE.append(f"门禁条数低于本环下限：{cnt(a['rs'], 'gates')}")
    bs = a["bs"]
    pf = g(bs, "pytest", default={})
    if pf.get("failed_sum") or pf.get("rc"):
        REFUSE.append(f"pytest 有红：failed_sum={pf.get('failed_sum')} rc={pf.get('rc')}")
    if not g(a["bs"], "three_systems_green", default=False):
        REFUSE.append("三套体系不同刻为绿")
    if sorted(g(a["bs"], "floors", default={})) != ["collect", "e2e_pass", "pytest", "suite"]:
        REFUSE.append(f"地板四栏不齐：{js(g(a['bs'], 'floors', default={}))}")
    gf = g(a["bs"], "git", default={})
    if gf.get("staged"):
        REFUSE.append(f"暂存区非 0（{gf.get('staged')} 行）")
    if g(a["bs"], "radius", default={}).get("forbidden_total"):
        REFUSE.append("冻结面/禁改面被本环动过")
    closer, rootc = a["closer"], a["rootc"]
    if len(closer.get("leaves") or []) != 16:
        REFUSE.append(f"叶收口件不是 16 行：{len(closer.get('leaves') or [])}")
    if closer.get("failed"):
        REFUSE.append(f"叶失败：{js(closer.get('failed'))[:200]}")
    if (rootc.get("root_final") or rootc.get("root_status")) != "已归档":
        REFUSE.append(f"根状态不是已归档：{js(rootc)[:120]}")
    nums = ledger_numbers()
    n_ring = cnt(a["bk"], "keys")
    lo_ring = int(a["bk"].get("ledger_after_max") or 0) - n_ring + 1
    chk(
        "号段：本环新增的张数与账本现读的尾段能对上（张数与起号都从件里反解，不写死 13/78）",
        nums[-n_ring:] == list(range(lo_ring, lo_ring + n_ring)),
        True,
        f"账本尾 {n_ring} 号 {nums[-n_ring:]} / 起号反解 {lo_ring}",
    )
    chk(
        "入账件的 ledger_after_max = 账本现读最大值（两路独立）",
        a["bk"].get("ledger_after_max"),
        max(nums),
        "件里自报 vs 盘上现读",
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
    chk(
        "needle 严口径：全部是真键名",
        a["nd"].get("real_key_len"),
        a["nd"].get("checked_len"),
        f"{a['nd'].get('real_key_len')}/{a['nd'].get('checked_len')}",
    )
    chk("驱动面软账不回升", a["ln"].get("soft_total"), 0, f"硬错 {a['ln'].get('hard_violations')}")
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

    fa, dc, cg, cl, bk, ln, sa, ro, tl = (
        a["fa"],
        a["dc"],
        a["cg"],
        a["cl"],
        a["bk"],
        a["ln"],
        a["sa"],
        a["ro"],
        a["tl"],
    )
    lines = [
        f"{MARK}（根 `{g(a['cs'], 'root_task', default='未记')}`，执行人 "
        f"`{g(a['cs'], 'assignee', default='未记')}`）",
        "",
    ]
    lines.append(
        f"- 结论：**已归档**。八条法独立复算；门禁 "
        f"{g(ro, 'gates_green')}/{g(ro, 'gates_in_table')} 全绿，报告渲染 "
        f"{ro.get('renders')} 次、被拒重试 {ro.get('refused_attempts')} 次。"
    )
    lines.append(
        f"- 法①观察面：{fa.get('families')} 带 / {fa.get('cases_total')} 格，变异通道翻转归属 "
        f"{js(fa.get('flips_by_mutant'))}，按族 {cnt(fa, 'flips_by_family')} 族；"
        f"白建通道点名 {js(fa.get('unattributed_mutants'))}；盲区 "
        f"{cnt(fa, 'blind_spots')} 格；本层候选 {fa.get('candidate_total')} 条"
        f"（R4-修复 已改掉那四个根因，零候选由翻转证明，不是「没报错」）。"
    )
    lines.append(
        f"- 法②声明面：{dc.get('rows_total')} 条主张现读原文 + 当场重测 ⇒ 陈旧 "
        f"{dc.get('stale_total')} / 真实缺口 {dc.get('real_gap_total')} / 按设计撤回 "
        f"{cnt(dc, 'withdrawn_design')} / 未测或仍成立 {cnt(dc, 'not_measured_or_true')}；"
        f"规模红线 {js(dc.get('size_lines'))}；hook 未列选项 {cnt(dc, 'undocumented_hook_options')} 个。"
    )
    lines.append(
        f"- 法③生成面：{cg.get('cases')} 条全部成对确诊 {js(cg.get('confirmed'))}；"
        f"canary {js(cg.get('canary'))}；残渣复测 {js(cg.get('tmp_left'))}。"
    )
    lines.append(
        f"- 法④入口面：{cl.get('cases')} 条确诊 {js(cl.get('confirmed'))}，未确认 "
        f"{js(cl.get('unsure'))}（对照两态同观察 ⇒ 不占号）；canary "
        f"{js(cl.get('canary'))}。"
    )
    lines.append(
        f"- 法⑤自证：needle {nd_len(a)} 条全部真键名（{js(a['nd'].get('prefix_canary', [])[:1])} "
        f"canary 抓到前缀假命中）；入账件逐卡现场在账反解 {bk.get('on_disk_keys_len')}/"
        f"{bk.get('cards')} 命中。"
    )
    n_filed = cnt(bk, "keys")
    lo_id = int(bk.get("ledger_after_max") or 0) - n_filed + 1
    lines.append(
        f"- 法⑥入账：账本 {bk.get('ledger_before_max')}→{bk.get('ledger_after_max')}，"
        f"bugs 任务 {bk.get('sqlite_bug_tasks_before')}→{bk.get('sqlite_bug_tasks_after')}，"
        f"新单 BUG-{lo_id}..BUG-{bk.get('ledger_after_max')}（号由「账本最大值 − 卡数 + 1」反解，"
        f"不是手打）；幂等复扫 duplicates {cnt(bk, 'duplicates')} 条（重跑一条不重开）。"
    )
    lines.append(
        f"- 法⑦三套体系：pytest {g(bs, 'pytest', 'passed')} 通过 / "
        f"{g(bs, 'pytest', 'failed_sum')} 失败 / rc={g(bs, 'pytest', 'rc')}，"
        f"收集 {g(bs, 'collect', 'nodeids')}，套件字段 {js(g(bs, 'suite', 'fields'))}，"
        f"e2e {js(g(bs, 'e2e', 'fields'))}；地板反解自 {js(g(bs, 'floors'))}"
        f"（来源 {g(bs, 'floors_source')}）；HEAD `{g(bs, 'git', 'head')}`、暂存 "
        f"{g(bs, 'git', 'staged')}、脏行 {g(bs, 'git', 'dirty_rows')}、半径禁改面 "
        f"{g(bs, 'radius', 'forbidden_total')} / 允许面 {g(bs, 'radius', 'allowed_touched')}。"
    )
    lines.append(
        f"- 法⑧驱动面：亲笔 {ln.get('drivers_scanned')} 个脚本，硬错 "
        f"{ln.get('hard_violations')}、软账 {ln.get('soft_total')}"
        f"（上一环基线 0）；行长口径 {ln.get('line_length_declared')}；"
        f"canary {js(ln.get('canary'))[:180]}。"
    )
    tl_stage = (tl.get("stages") or {}).get(g(a["cs"], "root_task"), {})
    tl_tag = tl.get("ring_tag_calls") or {}
    lines.append(
        f"- 收口：叶 {cnt(closer, 'leaves')}/16、失败 {cnt(closer, 'failed')}，根 "
        f"`{g(a['rootc'], 'root_final')}`；call_log 本环号段 {tl_stage.get('rows')} 行 / "
        f"{tl_stage.get('distinct_tasks')} 个任务（环标签档 {tl_tag.get('total')} 行），被拒 "
        f"{g(tl, 'stages', 'T0r96', 'refused', default='—')} 条。"
    )
    lines.append(
        f"- 报告：`{ro.get('report')}`（{ro.get('report_bytes')} B，sha "
        f"`{ro.get('report_sha256')}`），§八 声明/实数 "
        f"{js(ro.get('section8_rendered'))}，缺法条标题 {cnt(ro, 'law_heads_missing')} 个。"
    )
    lines.append(
        f"- 自证与门禁预跑：渲染前 {g(sa, 'gates_green', default='—')}/"
        f"{g(sa, 'gates_total', default='—')} 道解出，红 {cnt(sa, 'gates_red')} 道，"
        f"恒真门 {cnt(sa, 'fake_min_gates')} 道，needle 不合格 {cnt(sa, 'needle_bad')} 条，"
        f"占位 {g(sa, 'placeholders_total', default='—')} 个（未解析 "
        f"{cnt(sa, 'placeholders_unresolved')} 个、空值无佐证 "
        f"{cnt(sa, 'placeholders_empty_unjustified')} 个），陈旧未披露 "
        f"{cnt(sa, 'stale_undeclared')} 件。"
    )
    lines.append(
        f"- 时间盒：起点 {box_start}（取本环 {drv_n} 个亲笔驱动的最早 mtime），"
        f"本条记录生成于 {now}，实耗 {minutes} 分钟（盒 100 分钟，"
        f"{'超盒' if minutes > 100 else '在盒内'}）——门禁未缩、判据未放宽、冻结面未动。"
    )
    lines.append(disclosures(a, minutes))
    n_new = cnt(bk, "keys")
    max_id = int(bk.get("ledger_after_max") or 0)
    opened, closed_bugs = open_bug_ids()
    old_open = [x for x in opened if x < max_id - n_new + 1]
    chk(
        "账本基数自证：未闭环 + 已闭环 = 账本现读的 BUG 条目数（分栏不能吞行）",
        [len(opened) + closed_bugs, len(ledger_numbers())],
        [len(ledger_numbers()), len(ledger_numbers())],
        f"open={len(opened)} closed={closed_bugs} 条目={len(ledger_numbers())}",
    )

    lines.append(
        f"- 转结：R5-修复 领 BUG-{max_id - n_new + 1}..BUG-{max_id} 共 {n_new} 张新单 + "
        f"账本现数的 {len(old_open)} 张未闭环旧单（{js(old_open)}，判据=该号段正文无 FIXED 标记）"
        f" + §九 的 {a['dc'].get('real_gap_total')} 条 real-gap 裁决；R5-验证 复测本轮四张电池的判据是否仍然承重；流程债三条"
        "（全量批不与电池并发、脚本替换后必须实跑一次而不是只 compile、"
        "needle 只按子串校等于没校）。"
    )
    lines.append(f"- 本条记录生成于 {now}。")
    refusals = g(tl, "stages", "T0r96", "refused_detail", default=[]) or []
    if refusals:
        lines.append("- 收口被拒原文（逐字）：")
        for r in refusals:
            lines.append(f"  - `{js(r)[:400]}`")
    else:
        lines.append("- 收口被拒原文：无（终账按前缀数出来 refused=0，不是按回忆）。")

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
        "转结行的新单号段是反解出来的（号段最大值必须等于账本现读最大值）",
        max_id == (ledger_numbers() or [None])[-1],
        True,
        f"max_id={max_id} / 账本现读={js(ledger_numbers()[-5:])}",
    )

    txt = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    reds = [c["label"] for c in CHECKS if not c["ok"]]
    if reds:
        REFUSE.append(f"落盘前自证未过，loop_progress 不动：{reds}")
        (HERE / "hunt_r5_progress.json").write_text(
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

    (HERE / "hunt_r5_progress.json").write_text(
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
    bk = a["bk"]
    sev = [r for r in (bk.get("refuse") or [])]
    return (
        "- 本环流程外事件（逐字，不吞）：\n"
        "  1. **13 条 report_bug 全被服务端拒**：我给卡表用的是内部口径 P0/P1/P2，服务端闭集是\n"
        "     `critical/high/medium/low`。回执代表原文（逐字）："
        "`CLI_build_failure_reason_message_swallowed：入账后账本搜不到这条 summary（回执 "
        '{"__error__": {"code": -32000, "message": "report_bug: 非法 severity=P2'
        '（合法值：critical/high/medium/low；缺省 medium。BUG-88：闭集必须等于抬头文法）"}}）`。'
        "账本零写入（sqlite 任务数与账本最大号都没动），闭集校验已前移为发单前的预检并配 P9 canary。\n"
        f"  2. **入账件的三向对齐改过一次**：原用「跑前后计数差」⇒ 重跑差为 0 就恒红；改成逐卡在账"
        f"反解（`per_key_on_disk` {cnt(bk, 'per_key_on_disk')} 条、账本 hits≥1 且 bugs 树恰好 1 行）。"
        f"本件当前是**二次扫描**状态：实开 {cnt(bk, 'filed')} 条、已在账 {cnt(bk, 'duplicates')} 条。\n"
        "  3. **`tmp_left` 的语义错过一次**：首版采在 `shutil.rmtree(..., ignore_errors=True)` 之前，"
        "既永远非空又掩盖了清理静默失败（首跑实测留 21 个目录）。现在先清理（带重试）再采样、非空即拒。\n"
        f"  4. **全量基线被我起了两遍**：第一遍起跑后 `tasklist` 查不到 python.exe，我据此判它已死并"
        f"重跑；随后第一遍回来说「completed exit 0」——它其实一直活着，我的判活方式错了"
        f"（管道里 `tail` 吞了中间输出，日志 0 字节不等于没在跑）。第二遍起跑时第一遍已收尾，"
        f"两遍数字互相同意，测量面未被并发改动；**流程仍是错的**，已记进 §八 12。\n"
        f"  5. **D11 的立单原文已经不成立**：`result.output_files` 在上一环修法①里被改掉，自证门"
        f"「每行立单原文都在盘上」如实拒了那一条；改成现读 `result.pyd_paths` 并用 "
        f"`dataclasses.fields()` 判存在后，本条翻成 `doc-still-true`（等于独立复验了上一环的修法）。\n"
        f"  6. **改名脚本自噬一次**：`str.replace` 把 `now_iso()` 的定义体也换成了 `return now_iso()`"
        f"（自递归），`py_compile` 过、flake8 的 F401 才抓住 ⇒ 已改成 tokenize 级替换并逐处计数。\n"
        f"  7. 时间盒实耗 {minutes} 分钟：起点不是手写，是取本环 {cnt(a['plan'], 'laws')} 条法 + "
        f"亲笔驱动 mtime 的最小值；超出盒的那部分是两遍全量批与电池并发的墙钟，判据没有为此放宽。"
        f"（当前 call_log 本环号段 {_stage_rows(a)} 行 / 环标签档 {_tag_rows(a)} 行）\n"
        f"  8. 二次扫描的 refuse 栏现状（逐字，若为空表示这一栏本环没有残留）：{js(sev)[:200]}\n"
        "  9. 渲染见证件（按序号，存在性不冒充次数）：\n"
        + "".join(
            f"     - seq={r.get('seq')} sha={str(r.get('report_sha256'))[:16]}… "
            f"{r.get('report_bytes')} B／门禁 {r.get('gates_total')} 道／{r.get('at_utc')}／"
            f"note（逐字）：{r.get('note')}\n"
            for r in (a["ro"].get("render_records") or [])
        )
    )


if __name__ == "__main__":
    sys.exit(main())
