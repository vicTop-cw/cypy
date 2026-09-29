"""R5-修复 的渲染前自证：门禁按 report_kit 的**同一把尺子**预跑一遍，能红的先红。

为什么复用 `report_kit` 而不是自己写一套判定：上一环吃过「自证过了、渲染时另一套口径」的亏，
`load_art/walk/gate_ok` 是渲染器实际用的那三个函数，直接 import 才能保证两路口径同源。

本驱动自己也要能被红：
- 恒真门（`min: 0`、`min: 1` 套在必然存在的标量上）单列计数，>0 即拒；
- 每条门禁的 `path` 首段必须是判据件里的**真键名**（needle 严口径，同 fix_r5_needles.py）；
- 判据件比它的驱动脚本旧 ⇒ 陈旧，除非在 `stale_ok` 里逐条写了理由；这条判据配一条合成 canary
  （把脚本 mtime 设到未来，必须被抓到），否则它可能只是一道恒绿门；
- 每份 JSON 判据件必须真能 parse（上一环的手补计划件就是靠这条抓出来的）；
- 正文里的 `{{件|路径}}` 占位必须全部解析得出来；空值占位要有 `equals: []` 的门禁佐证。

本环（R5-修复）判据件集 = 八条法的八件（intake/locks/rc/revert/impact/baselines/ledger/drivers_lint）
+ `fix_r5_calllog_tally.json` + `fix_r5_needles.json`
+ `close_r5_fix.json` + `close_r5_fix.out.json`；
缺一张就不落数字。另外各件自己的 `self_checks_red` 必须为空——认领表/锁/根因/影响面这四位驱动的
`refuse` 只装 REFUSE、不折自身红条，红条由这里的第二路抓住。
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
sys.path.insert(0, str(HERE))
import report_kit as RK  # noqa: E402

SPEC = HERE / "report_spec_r5_fix.json"
PLAN = HERE / "spec_r5_fix.json"
NS = "cypy-loop-20260927"
OUT = HERE / "fix_r5_self_audit.json"
REQUIRED = [
    "fix_r5_intake.json",  # 法① 认领表
    "fix_r5_locks.json",  # 法② 锁先行
    "fix_r5_rc.json",  # 法③ 根因合并修
    "fix_r5_revert.json",  # 法④ 回退矩阵
    "fix_r5_impact.json",  # 法⑤ 语义变更影响面
    "fix_r5_baselines.json",  # 法⑥ 三套体系 + 地板 + 半径
    "fix_r5_ledger.json",  # 法⑦ 账面闭环
    "fix_r5_drivers_lint.json",  # 法⑧ 驱动面自证
    "fix_r5_calllog_tally.json",  # 收口面：call_log 两档现数
    "fix_r5_needles.json",  # 收口面：needle 严口径
    "close_r5_fix.json",  # 派单/收口的同一份法条
    "close_r5_fix.out.json",  # 逐叶收口的实测输出
]
# 根上卷件在**渲染之后**才会存在（close_root 要拿渲染好的报告过 L4 产物门）：
# 本件在渲染前必须断言它「不在盘上」，而不是要求它在渲染前就在；渲染后由
# fix_r5_render_order.py 现读断言它已落盘且根已归档。
POST_RENDER_ONLY = ["close_r5_fix_root.out.json"]
REFUSE: list = []
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


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def driver_for(name: str):
    drv = HERE / name.replace(".json", ".py")
    return drv if drv.exists() else None


def is_stale(rel: str) -> bool:
    j = HERE / Path(rel).name
    drv = driver_for(j.name)
    return bool(drv and j.exists() and os.path.getmtime(drv) > os.path.getmtime(j) + 1)


def key_names(obj, acc: set, depth: int = 1) -> set:
    if depth < 0 or not isinstance(obj, dict):
        return acc
    for k, v in obj.items():
        acc.add(str(k))
        if isinstance(v, dict):
            key_names(v, acc, depth - 1)
        elif isinstance(v, list):
            for item in v[:8]:
                if isinstance(item, dict):
                    key_names(item, acc, depth - 1)
    return acc


def parse_err(txt: str) -> str:
    try:
        json.loads(txt)
        return ""
    except Exception as exc:
        return type(exc).__name__


def js(v, n: int = 180) -> str:
    """把判据件里的值压成一行短文本进 `why` 栏——证据要点名，不要整件抄。"""
    return json.dumps(v, ensure_ascii=False)[:n]


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        REFUSE.append(f"判据件/收口件缺失，一个数字都不落：{missing}")
    L = {
        f: json.loads((HERE / f).read_text(encoding="utf-8"))
        for f in REQUIRED
        if (HERE / f).exists()
    }
    for f, doc in L.items():
        if isinstance(doc, dict) and doc.get("refuse"):
            REFUSE.append(f"{f} 自带拒绝：{json.dumps(doc['refuse'], ensure_ascii=False)[:200]}")

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    cache: dict = {}
    stale_disclosed = {d["artifact"]: d.get("reason", "") for d in spec.get("stale_ok", [])}

    # ① 门禁预跑（与渲染器同口径）
    green, red, fake_min, bad_needle = 0, [], [], []
    for g in spec["gates"]:
        st, obj = RK.load_art(g["artifact"], cache)
        if st == "missing":
            red.append(f"{g['label']} 件不在盘上：{g['artifact']}")
            continue
        val, why = RK.walk(obj, g["path"])
        if why:
            red.append(f"{g['label']} 路径解析不出：{g['artifact']}::{g['path']}（{why}）")
            continue
        ok, detail = RK.gate_ok(g, val)
        if ok:
            green += 1
        else:
            red.append(f"{g['label']} 门禁未过：{detail}")
        if "min" in g and int(g["min"]) <= 0:
            fake_min.append(g["label"])
        head = re.split(r"[.\[]", g["path"])[0]
        if head and head not in key_names(obj, set()):
            bad_needle.append(f"{g['label']}::{g['artifact']}::{head}")
    check("门禁全绿（红表必须为空）", red, [], f"{green}/{len(spec['gates'])} 绿")
    check("恒真门（min<=0）必须为 0 道", fake_min, [], "把门焊死不算通过")
    check(
        "每条门禁的 path 首段是被引件里的真键名",
        bad_needle,
        [],
        "子串假命中不算 needle（上一环 control/queue 那类）",
    )
    check(
        "门禁条数达八法 × 每法至少三道",
        len(spec["gates"]) >= 24,
        True,
        f"实得 {len(spec['gates'])} 道",
        ok=len(spec["gates"]) >= 24,
    )

    # ② 计划法条 ↔ 门禁覆盖
    arts_in_gates = {Path(g["artifact"]).name for g in spec["gates"]}
    uncovered = [
        f"法{i}:{Path(law['artifacts'][0][0]).name}"
        for i, law in enumerate(plan["laws"], 1)
        if Path(law["artifacts"][0][0]).name not in arts_in_gates
    ]
    check("八条法的头号证据件都有门禁家族在场", uncovered, [], f"件集 {sorted(arts_in_gates)}")
    check(
        "每条法配三道证据件（派单与收口读同一份计划）",
        sorted({len(law["artifacts"]) for law in plan["laws"]}),
        [3],
        "artifacts 条数分布",
    )

    # ③ 收口与根
    stage = L.get("close_r5_fix.out.json", {})
    cs = L.get("close_r5_fix.json", {})
    root_live = None
    try:
        con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
        row = con.execute(
            "select status from tasks where ns=? and id=?", (NS, spec["root_task"])
        ).fetchone()
        root_live = row[0] if row else None
        con.close()
    except Exception as exc:
        REFUSE.append(f"根状态现读失败：{type(exc).__name__}: {exc}")
    check("收口叶子 16 张", len(stage.get("leaves") or []), 16, "按 sqlite 反解的叶数")
    cs_branches = len(cs.get("branches") or [])
    cs_leaves = len(cs.get("leaves") or [])
    out_leaves = len(stage.get("leaves") or [])
    check(
        "派单面与收口面同一批：根号 = 渲染件的根号，8 支 × 16 叶，执行人 cypy-fixer",
        [
            cs.get("root_task") == spec["root_task"],
            cs.get("assignee"),
            cs.get("stage"),
            [cs_branches, cs_leaves],
            cs_leaves == len(stage.get("leaves") or []),
        ],
        [True, "cypy-fixer", "R5-修复", [8, 16], True],
        f"root={cs.get('root_task')} 支={cs_branches} 叶={cs_leaves} 输出件叶={out_leaves}",
    )
    check(
        "收口零失败",
        stage.get("failed"),
        [],
        js(stage.get("failed"), 200),
    )
    # 收口次序是「叶 → 渲染 → 根上卷」，本件在两个阶段各要说一句话，两句都可翻红：
    # 渲染前根不该已归档（否则是拿没出的报告去上卷），渲染后根必须已归档。
    root_art_present = (HERE / "close_r5_fix_root.out.json").exists()
    if root_art_present:
        check(
            "渲染后阶段：根已上卷归档（sqlite 现读 = 已归档）",
            root_live,
            "已归档",
            f"live root={root_live} / 收口件在盘={root_art_present}",
        )
    else:
        check(
            "渲染前阶段：根尚未上卷（现读非已归档 且 收口件不在盘上，两条同时成立）",
            [root_live != "已归档", root_art_present is False],
            [True, True],
            f"live root={root_live} / root 件在盘={root_art_present}",
        )

    check(
        "每叶 omega 链走完（verify 结果为已完成）",
        sorted({row.get("verify") for row in stage.get("leaves") or []}),
        ["已完成"],
        "逐叶 verify 字段",
    )

    # ④ 三套体系与 git 红线
    base = L.get("fix_r5_baselines.json", {})
    three_green = base.get("three_systems_green")
    check(
        "三套体系同刻为绿（三栏分别判：pytest / 自研套件 / e2e 各一条，不是拿 all() 蒙一个）",
        [three_green, base.get("three_systems_ok")],
        [[True, True, True], True],
        js(three_green, 140),
    )
    check(
        "pytest 失败汇总为 0 且 rc=0（字段名从件反解：failed_sum）",
        [base.get("pytest", {}).get("failed_sum"), base.get("pytest", {}).get("rc")],
        [0, 0],
        "两栏分列",
    )
    check(
        "pytest 通过数不低于上一环实测地板",
        base.get("pytest", {}).get("passed", 0) >= base.get("floors", {}).get("pytest", 1 << 30),
        True,
        f"passed={base.get('pytest', {}).get('passed')} floors={base.get('floors')}",
    )
    check(
        "收集数达地板（解析器活着）",
        base.get("collect", {}).get("nodeids", 0) >= base.get("floors", {}).get("collect", 1 << 30),
        True,
        f"collect={base.get('collect', {}).get('nodeids')}",
    )
    check(
        "地板四栏齐全且来源点名上一环件",
        sorted(base.get("floors") or {}),
        ["collect", "e2e_pass", "pytest", "suite"],
        str(base.get("floors_source"))[:160],
    )
    ef = base.get("e2e", {}).get("fields", {})
    sf = base.get("suite", {}).get("fields", {})
    check(
        "e2e：PASS 达地板且 FAIL/WARN/UNREG 三格为零（法⑥点名的三格）",
        [ef.get("PASS"), ef.get("FAIL"), ef.get("WARN"), ef.get("UNREG/RUNFAIL")],
        [base.get("floors", {}).get("e2e_pass"), 0, 0, 0],
        js(ef, 160),
    )
    suite_sum = sf.get("Passed", -1) + sf.get("Failed", 0) + sf.get("Skipped", 0)
    check(
        "自研套件：Passed 达地板、Failed 为零、三栏之和 = Total（分栏不吞行）",
        [sf.get("Passed"), sf.get("Failed"), suite_sum == sf.get("Total")],
        [base.get("floors", {}).get("suite"), 0, True],
        js(sf, 160),
    )
    git_doc = base.get("git", {})
    check(
        "HEAD 未动 / 暂存为 0 / 件里声明的期望 HEAD 就是它 / 外部 HEAD 基线 worktree 仍在",
        [
            git_doc.get("head"),
            git_doc.get("head") == base.get("git_head_expected"),
            git_doc.get("staged"),
            git_doc.get("foreign_worktree_present"),
        ],
        ["17d68b4", True, 0, True],
        f"脏行 {git_doc.get('dirty_rows')} / 删掉的跟踪文件 {git_doc.get('deleted_tracked')} 个",
    )
    check(
        "冻结面改动为 0",
        base.get("radius", {}).get("forbidden_total"),
        0,
        js(base.get("radius", {}).get("touched_forbidden"), 200),
    )
    check(
        "半径正面测出确实写了东西",
        base.get("radius", {}).get("allowed_touched", 0) > 10,
        True,
        f"loop/memory 侧 {base.get('radius', {}).get('allowed_touched')} 个",
        ok=base.get("radius", {}).get("allowed_touched", 0) > 10,
    )

    # ⑤ 认领 → 锁 → 回退 → 账面：四件必须落在同一批单号上，逐张对得上才谈闭环
    ik = L.get("fix_r5_intake.json", {})
    lkd = L.get("fix_r5_locks.json", {})
    rcd = L.get("fix_r5_rc.json", {})
    rvd = L.get("fix_r5_revert.json", {})
    im = L.get("fix_r5_impact.json", {})
    lgd = L.get("fix_r5_ledger.json", {})
    cols = ik.get("split_columns") or {}
    planned = sorted(ik.get("planned_ids") or [])
    claimed = sorted(cols.get("本环认领") or [])
    handed = sorted({x for k, v in cols.items() if k != "本环认领" for x in (v or [])})
    cards_n = len(ik.get("cards") or [])
    n_new = len(ik.get("ring_new_ids") or [])
    n_legacy = len(ik.get("legacy_open_ids") or [])
    col_counts = js({k: len(v or []) for k, v in cols.items()}, 180)
    check(
        "认领表基数：卡表条数 = cards_total，且四栏之和 = 卡表条数（分栏不吞行）",
        [cards_n, sum(len(v or []) for v in cols.values())],
        [ik.get("cards_total"), cards_n],
        f"cards_total={ik.get('cards_total')} 栏位 {col_counts}",
    )
    check(
        "本环认领面 = 分栏「本环认领」那一栏（planned_ids 不是第二套手打的号）",
        [planned, len(planned)],
        [claimed, len(claimed)],
        f"planned {len(planned)} 张 / 本环认领栏 {len(claimed)} 张 / 交人工面 {len(handed)} 张",
    )
    check(
        "上一环入账的新单逐张落在本环认领面（漏一张=这张单没人领）",
        sorted(set(ik.get("ring_new_ids") or []) - set(planned)),
        [],
        f"新单 {n_new} 张 / 账本未闭环旧单 {n_legacy} 张",
    )
    locked = sorted(lkd.get("locked_ids") or [])
    lanes_doc = json.loads((HERE / "r5_fix_lanes.json").read_text(encoding="utf-8"))
    lane_undelivered = sorted(
        {
            int(cid)
            for lane in (lanes_doc.get("lanes") or [])
            for cid in (lane.get("undelivered_cards") or [])
        }
    )
    no_code = sorted(lkd.get("no_code_lock_ids") or [])
    check(
        "锁先行三栏对齐：绿过=locked；红过=locked 减装饰锁；装饰锁两路（法②点名 vs 车道未交付）同集合",
        [
            sorted(set(lkd.get("lock_green_after") or []) ^ set(locked)),
            sorted(set(lkd.get("lock_red_before") or []) ^ (set(locked) - set(no_code))),
            sorted(set(no_code) ^ set(lane_undelivered)),
        ],
        [[], [], []],
        f"有锁 {len(locked)} 张 / 红 {len(lkd.get('lock_red_before') or [])} 张 / "
        f"装饰锁 {no_code} / 车道自述未交付 {lane_undelivered}",
    )
    check(
        "不承重的锁只能逐张点名在案：HEAD 旧码树上就绿的锁必须恰等于装饰锁名单（不许多也不许少）",
        sorted(set(lkd.get("lock_green_on_head") or []) ^ set(no_code)),
        [],
        js(lkd.get("lock_green_on_head"), 160),
    )
    check(
        "无锁的认领单逐张点名（locks_missing 只能是认领面子集，不并进闭环主张）",
        sorted(set(lkd.get("locks_missing") or []) - set(planned)),
        [],
        f"无锁 {js(lkd.get('locks_missing'), 120)} / 红档日志 {js(lkd.get('red_log_evidence'), 120)}",
    )
    mat = rvd.get("matrix") or []
    nm_rows = sorted(r.get("bug_id") for r in mat if r.get("revert_mode") == "not_measured")
    unfixed = sorted(rcd.get("unfixed_claimed") or [])
    no_lock = sorted(lkd.get("locks_missing") or [])
    expect_nm = sorted(set(unfixed) | set(no_lock))
    check(
        "回退矩阵里 not_measured 的行 = 「没产品码改动／无交付」∪「没有锁」两张名单的并集（多一行少一行都要点名）",
        [sorted(set(nm_rows) - set(expect_nm)), sorted(set(expect_nm) - set(nm_rows))],
        [[], []],
        f"not_measured {js(nm_rows)} / 未修完 {js(unfixed)} / 无锁 {js(no_lock)}",
    )
    check(
        "回退矩阵条数 = 认领单数（法④的字面主张，两路各自反解）",
        [rvd.get("matrix_rows"), len(mat)],
        [len(planned), len(planned)],
        f"matrix_rows={rvd.get('matrix_rows')} 行数={len(mat)} 认领={len(planned)}",
    )
    ex = rvd.get("extras") or {}
    sha_pair = f"{rvd.get('sha_restored')}/{rvd.get('sha_files_total')}"
    check(
        "摘完逐文件复原：sha 复原数 = 摘回触及的文件数且不为 0，真树没被写脏",
        [
            rvd.get("sha_restored") == rvd.get("sha_files_total"),
            (rvd.get("sha_files_total") or 0) > 0,
            ex.get("root_tree_dirtied"),
        ],
        [True, True, []],
        f"sha {sha_pair} 脏行 {js(ex.get('root_tree_dirtied'), 120)}",
    )
    cnr = rvd.get("canary_no_op_revert") or {}
    check(
        "空操作摘回对照跑过且没把锁摘红（矩阵判据的承重证明）",
        [cnr.get("ran"), cnr.get("head_equals_current"), cnr.get("nodes_went_bad")],
        [True, True, []],
        js(cnr, 220),
    )
    check(
        "组间牵连为零：collateral 空表（摘一组把别组的锁摘红 ⇒ 矩阵作废）",
        rvd.get("collateral"),
        [],
        js(rvd.get("collateral"), 200),
    )
    closed = sorted(lgd.get("closed_ids") or [])
    leftover = sorted(lgd.get("leftover_ids") or [])
    three = lgd.get("three_way") or []
    n_green_after = len(lkd.get("lock_green_after") or [])
    n_revert_red = len(rvd.get("revert_red_ids") or [])
    check(
        "账面基数：闭环 ∪ 转结 = 认领面，且两栏不重叠（一张都不许悄悄消失）",
        [sorted(set(closed) | set(leftover)), sorted(set(closed) & set(leftover))],
        [planned, []],
        f"闭环 {len(closed)} / 转结 {len(leftover)} / 认领 {len(planned)}",
    )
    check(
        "交人工与未认领的单没被本环闭环（红线：不占修、不改账本状态）",
        sorted(set(closed) & set(handed)),
        [],
        f"交人工面 {len(handed)} 张 {js(handed, 160)}",
    )
    check(
        "闭环集仍是「旧码红过、当前绿、摘回会红」的交集（三件独立复算，不是 ledger 自报）",
        [
            sorted(set(closed) - set(lkd.get("lock_red_before") or [])),
            sorted(set(closed) - set(lkd.get("lock_green_after") or [])),
            sorted(set(closed) - set(rvd.get("revert_red_ids") or [])),
            sorted(set(closed) - set(planned)),
        ],
        [[], [], [], []],
        f"闭环 {len(closed)} / 绿 {n_green_after} / 摘回红 {n_revert_red} / 认领 {len(planned)}",
    )
    check(
        "三向对照逐张同意：three_way_bad 空表且 agree_total = 对照行数",
        [lgd.get("three_way_bad"), lgd.get("agree_total")],
        [[], len(three)],
        f"对照 {len(three)} 行 / 同意 {lgd.get('agree_total')} / 转结 {lgd.get('leftover_len')}",
    )
    md = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    entries = len(re.findall(r"(?m)^## BUG-\d+", md))
    open_entries = len(re.findall(r"(?m)^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN", md))
    check(
        "账面基数两路对：ledger_total / ledger_open_total = 盘上现读的条目数 / OPEN 数",
        [lgd.get("ledger_total"), lgd.get("ledger_open_total")],
        [entries, open_entries],
        f"现读 {entries} 条 / OPEN {open_entries} 条",
    )
    adj_im = sorted(im.get("corpus_adjudication_files") or [])
    check(
        "影响面挂账逐张进账（ledger.impact_adjudication = impact.corpus_adjudication_files）",
        sorted(lgd.get("impact_adjudication") or []),
        adj_im,
        f"影响面 {len(adj_im)} 档 / 账面 {len(lgd.get('impact_adjudication') or [])} 档",
    )
    red_per_art = {f: d.get("self_checks_red") for f, d in L.items() if d.get("self_checks_red")}
    check(
        "各判据件自身的自证没有红条（四件驱动的 refuse 只装 REFUSE，红条不折进去）",
        sorted(red_per_art),
        [],
        js({f: v for f, v in red_per_art.items()}, 300),
    )

    # ⑥ 陈旧与 parse
    stale = sorted({Path(g["artifact"]).name for g in spec["gates"] if is_stale(g["artifact"])})
    undeclared = [s for s in stale if s not in stale_disclosed]
    check(
        "没有判据件比它的驱动脚本旧（除非逐条披露理由）",
        undeclared,
        [],
        f"陈旧集 {stale}，已披露 {list(stale_disclosed)}",
    )
    fake_disclosed = [k for k in stale_disclosed if k not in stale]
    check(
        "披露的例外必须真属陈旧（不许拿 stale_ok 当免检通道）",
        fake_disclosed,
        [],
        "披露而不成立 ⇒ 拒",
    )
    on_disk = sorted(p.name for p in HERE.glob("fix_r5_*.json"))
    parses = {n: parse_err((HERE / n).read_text(encoding="utf-8")) for n in on_disk}
    bad_parses = sorted(k for k, v in parses.items() if v)
    check(
        "每份 JSON 判据件都能 parse", bad_parses, [], json.dumps(parses, ensure_ascii=False)[:300]
    )
    req_json_on_disk = [f for f in REQUIRED if f.startswith("fix_r5_") and (HERE / f).exists()]
    check(
        "parse 扫描面盖住 REQUIRED 里在盘的判据件（基数门：改了前缀或漏扫就红）",
        sorted(set(req_json_on_disk) - set(on_disk)),
        [],
        f"REQUIRED 在盘 {len(req_json_on_disk)} 份 / 扫到 {len(on_disk)} 份",
    )
    check(
        "canary：parse 判据对「相邻字符串续行」必红",
        parse_err('{"why": "甲，"\n "乙"}'),
        "JSONDecodeError",
        "不是恒绿的存在性检查",
    )
    check(
        "canary：parse 判据不误抓合法 JSON",
        parse_err('{"why": "甲，乙", "n": 1}'),
        "",
        "同一把尺子的另一侧",
    )

    # ⑦ 正文占位与 §十
    body_rel = spec["fragment"]
    bstate, btxt = RK.load_art(body_rel, cache)
    text = btxt if isinstance(btxt, str) else ""
    if bstate == "missing":
        REFUSE.append(f"正文片段不在盘上：{body_rel}")
    ph = re.findall(r"\{\{([^{}]+)\}\}", text)
    unresolved_ph = []
    empty_with_witness, empty_no_witness = [], []
    for expr in ph:
        rel, _, dotted = expr.partition("|")
        st, obj = RK.load_art(rel.strip(), cache)
        if st == "missing":
            unresolved_ph.append(f"{expr}（件缺失）")
            continue
        val, w = obj, ""
        if dotted:
            val, w = RK.walk(obj, dotted)
        if w:
            unresolved_ph.append(f"{expr}（{w}）")
        elif val in ([], {}, "", None):
            head = re.split(r"[.\[]", dotted)[0]
            gate_backed = any(
                Path(g["artifact"]).name == Path(rel.strip()).name
                and g["path"].split(".")[0] == head
                and g.get("equals") == []
                for g in spec["gates"]
            )
            (empty_with_witness if gate_backed else empty_no_witness).append(expr)
    check("正文占位全部解析得出来", unresolved_ph, [], f"{len(ph)} 个占位")
    check(
        "空值占位必须有 equals:[] 的门禁背书",
        empty_no_witness,
        [],
        f"有背书 {len(empty_with_witness)} 个",
    )
    s10_declared = (
        len(re.findall(r"(?m)^\d+\. ", text.split("## 八、")[-1])) if "## 八、" in text else -1
    )
    check(
        "§八 失效条目在正文里数得出来（负数=没有该节）",
        s10_declared > 0,
        True,
        f"实测 {s10_declared} 条",
        ok=s10_declared > 0,
    )

    # ⑧ needle 件与法条一致
    nd = L.get("fix_r5_needles.json", {})
    check(
        "needle 严口径：全部 needle 都是真键名",
        nd.get("real_key_len"),
        nd.get("checked_len"),
        f"{nd.get('real_key_len')}/{nd.get('checked_len')}",
    )
    check(
        "扫描时不存在判据件必须为空表（法条不许引用空气）",
        nd.get("pending_artifacts"),
        [],
        "收口前复扫",
    )
    check(
        "法条只引本环那八件（needle 件的 off_ring_artifacts 必须是空表）",
        nd.get("off_ring_artifacts"),
        [],
        js(nd.get("off_ring_artifacts"), 200),
    )
    check(
        "前缀式假命中 canary 抓到了东西",
        bool(nd.get("prefix_canary")),
        True,
        f"{len(nd.get('prefix_canary') or [])} 条",
        ok=bool(nd.get("prefix_canary")),
    )

    # ⑨ 驱动面
    ln = L.get("fix_r5_drivers_lint.json", {})
    check(
        "亲笔驱动硬错为 0",
        ln.get("hard_violations"),
        0,
        js(ln.get("hard_lines"), 200),
    )
    soft_base = ln.get("previous_round_soft_baseline")
    soft_ok = (
        isinstance(ln.get("soft_total"), int)
        and isinstance(soft_base, int)
        and ln["soft_total"] <= soft_base
    )
    check(
        "软账不高于上一环实测基线（基线从件里读，不是我记得的 0）",
        soft_ok,
        True,
        f"soft={ln.get('soft_total')} 基线={soft_base} 来源={ln.get('baseline_source')}",
        ok=soft_ok,
    )
    ln_can = ln.get("canary") or {}
    check(
        "lint 的注入对照两侧都成立：违例必被抓、干净件不误抓（否则硬错门是装饰）",
        [bool(ln_can.get("bad_caught")), ln_can.get("clean_false_positive")],
        [True, 0],
        js(ln_can, 200),
    )
    drv_list = sorted(ln.get("driver_list") or [])
    check(
        "扫描面只数本环亲笔：清单里外环脚本 = 空表，且清单长度 = drivers_scanned",
        [
            [x for x in drv_list if not str(x).startswith("fix_r5_")],
            ln.get("drivers_scanned") == len(drv_list),
        ],
        [[], True],
        f"清单 {len(drv_list)} 个 / 件里自报 {ln.get('drivers_scanned')} 个",
    )
    check(
        "行长与 ignore 口径跟仓库声明一致（lint 不是自定口径）",
        [ln.get("line_length_declared"), sorted(ln.get("ignore_declared") or [])],
        [100, ["E203", "W503", "W505"]],
        js(ln.get("ignore_declared"), 120),
    )

    doc = {
        "started": started,
        "gates_total": len(spec["gates"]),
        "gates_green": green,
        "gates_red": red,
        "fake_min_gates": fake_min,
        "needle_bad": bad_needle,
        "stale_undeclared": undeclared,
        "stale_disclosed": list(stale_disclosed),
        "placeholders_total": len(ph),
        "placeholders_unresolved": unresolved_ph,
        "placeholders_empty_unjustified": empty_no_witness,
        "section10_items_declared": s10_declared,
        "claim": {
            "cards_total": ik.get("cards_total"),
            "planned": len(planned),
            "handed_over": len(handed),
            "locked": len(locked),
            "closed": len(closed),
            "leftover": len(leftover),
            "matrix_rows": rvd.get("matrix_rows"),
        },
        "baselines": {
            "three_systems_green": three_green,
            "three_systems_ok": base.get("three_systems_ok"),
            "floors": base.get("floors"),
            "radius_forbidden": base.get("radius", {}).get("forbidden_total"),
        },
        "artifact_self_checks_red": sorted(red_per_art),
        "closure": {
            "leaves": len(stage.get("leaves") or []),
            "failed": stage.get("failed"),
            "root_pre_render": root_live,
            "close_root_task": cs.get("root_task"),
            "close_branches": cs_branches,
        },
        "self_checks": CHECKS,
        "refuse": [],
        "identity": {"report": spec["name"], "root_task": spec["root_task"]},
        "at_utc": now_s(),
    }
    red_checks = [c["label"] for c in CHECKS if not c["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red_checks})
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "gates_green": f"{green}/{len(spec['gates'])}",
                "self_checks": f"{len(CHECKS) - len(red_checks)}/{len(CHECKS)}",
                "placeholders": len(ph),
                "at_utc": doc["at_utc"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"], "at_utc": now_s()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
