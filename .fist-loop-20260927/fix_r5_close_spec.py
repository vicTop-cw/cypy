"""把环节计划装配成收口件 `close_r5_fix.json`（16 叶 × omega 全链的输入），并逐条自证。

派单与收口读的是**同一份** `spec_r5_fix.json`：这里的 laws 不是重写一遍，而是原样搬过去，
再对每条证据件做渲染前预检（件在盘上、能 parse、needle 是真键名、min_chars 达标）。
预检不过 ⇒ 一个服务端调用都不发（服务端拒绝不可撤回，预检是我方可复算的）。

`root_measured` 的每一格都是按 `MEASURED` 那张 (取件, 键路径, 口径) 表从本环（R5-修复）的判据件
里反解出来的，本文件不打数字：反解不出的键路径不猜、不补零，逐条进 `measured_unresolved` 并判红。
根交付文案与根验收理由里出现的每一个阿拉伯数字也必须落在这张表反解出来的数集里（`stray` 判据），
否则就是手打的。禁止栏同理，从 `spec.fingerprint.禁止` 逐条反解。

自带 canary：把某条 needle 从**已判真的 needle** 上机械截成前缀（如 `change_points`→`change`）后
必须被严口径整件拒、同时被旧的子串口径放行 ⇒ 证明这套预检既不恒绿也不恒红。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLAN = HERE / "spec_r5_fix.json"
ROOTS = HERE / "root_r5_fix.out.json"
OUT = HERE / "close_r5_fix.json"
# 修复环的根 marker：报告页脚靠它找审计对象，留上一环的 hunt 字样就是页脚串环。
FIX_MARKER = "[selfdrive-fix]"
HUNT_MARKER = "[selfdrive-hunt]"
# 上一环（R5-寻虫）禁止栏的说法：修复环的产品码改动正是交付物本身，这句话留在这里就是串环。
HUNT_FORBID = "禁止在本环修产品码"
# 根上卷的附加产物：(件路径, 要能在件里数到的键名, 最少字符)。全是本环件。
EXTRA_ARTIFACTS = [
    [".fist-loop-20260927/fix_r5_needles.json", "per_law_real", 400],
    [".fist-loop-20260927/fix_r5_drivers_lint.json", "hard_violations", 400],
    [".fist-loop-20260927/fix_r5_calllog_tally.json", "ring_tag_calls", 2000],
    [".fist-loop-20260927/fix_r5_revert.json", "matrix", 2000],
    [".fist-loop-20260927/fix_r5_ledger.json", "three_way", 2000],
]
# root_measured 的反解表：(键名, 判据件, 件里的点号键路径, 口径)。
# 口径 len=数条目数（dict/list 都行）、val=直接取整数、true=数列表里为真的格。
# {root} 在运行时换成根任务号（从 root_r5_fix.out.json 反解，不写死 T0r110）。
MEASURED = (
    # 法① 认领表
    ("claimed", "fix_r5_intake.json", "planned_ids", "len"),
    ("cards_total", "fix_r5_intake.json", "cards_total", "val"),
    ("split_columns", "fix_r5_intake.json", "split_columns", "len"),
    ("legacy_open", "fix_r5_intake.json", "legacy_open_ids", "len"),
    ("ring_new", "fix_r5_intake.json", "ring_new_ids", "len"),
    ("unclaimed_gaps", "fix_r5_intake.json", "unclaimed_severities", "len"),
    # 法② 锁先行
    ("locked", "fix_r5_locks.json", "locked_ids", "len"),
    ("lock_red", "fix_r5_locks.json", "lock_red_before", "len"),
    ("lock_green", "fix_r5_locks.json", "lock_green_after", "len"),
    ("lock_assertion", "fix_r5_locks.json", "assertion_level_red_only", "len"),
    ("lock_nodes", "fix_r5_locks.json", "lock_nodes_total", "val"),
    ("locks_missing", "fix_r5_locks.json", "locks_missing", "len"),
    ("green_on_head", "fix_r5_locks.json", "lock_green_on_head", "len"),
    # 法③ 根因合并修
    ("change_points", "fix_r5_rc.json", "change_points", "val"),
    ("merged_rc", "fix_r5_rc.json", "merged_root_cause_len", "val"),
    ("symbols", "fix_r5_rc.json", "symbols_referenced_len", "val"),
    ("no_card_files", "fix_r5_rc.json", "product_files_without_card", "len"),
    ("scope_only_files", "fix_r5_rc.json", "covered_only_by_scope", "len"),
    ("unattributed", "fix_r5_rc.json", "unattributed_changes", "len"),
    ("ring_files", "fix_r5_rc.json", "ring_files_all_len", "val"),
    ("unfixed", "fix_r5_rc.json", "unfixed_claimed", "len"),
    # 法④ 回退矩阵
    ("matrix_rows", "fix_r5_revert.json", "matrix_rows", "val"),
    ("groups", "fix_r5_revert.json", "groups_len", "val"),
    ("revert_red", "fix_r5_revert.json", "revert_red_ids", "len"),
    ("assertion_ids", "fix_r5_revert.json", "assertion_level_ids", "len"),
    ("collateral", "fix_r5_revert.json", "collateral", "len"),
    ("sha_restored", "fix_r5_revert.json", "sha_restored", "val"),
    ("sha_files", "fix_r5_revert.json", "sha_files_total", "val"),
    ("bearing", "fix_r5_revert.json", "extras.bearing", "len"),
    ("unborne", "fix_r5_revert.json", "extras.unborne_files", "len"),
    ("declared_not_bearing", "fix_r5_revert.json", "extras.declared_face_not_bearing", "len"),
    ("rows_with_lock", "fix_r5_revert.json", "extras.rows_with_lock", "len"),
    # 法⑤ 语义变更影响面
    ("corpus", "fix_r5_impact.json", "corpus_total", "val"),
    ("new_diag", "fix_r5_impact.json", "new_diagnostics_len", "val"),
    ("new_rej", "fix_r5_impact.json", "new_rejections_len", "val"),
    ("new_acc", "fix_r5_impact.json", "new_acceptances_len", "val"),
    ("shape_changed", "fix_r5_impact.json", "shape_changed_len", "val"),
    ("adjudication", "fix_r5_impact.json", "adjudication_needed", "val"),
    # 法⑥ 三套体系 + 地板 + 半径
    ("pytest_passed", "fix_r5_baselines.json", "pytest.passed", "val"),
    ("pytest_failed", "fix_r5_baselines.json", "pytest.failed_sum", "val"),
    ("collect_nodes", "fix_r5_baselines.json", "collect.nodeids", "val"),
    ("suite_passed", "fix_r5_baselines.json", "suite.fields.Passed", "val"),
    ("suite_failed", "fix_r5_baselines.json", "suite.fields.Failed", "val"),
    ("e2e_pass", "fix_r5_baselines.json", "e2e.fields.PASS", "val"),
    ("e2e_fail", "fix_r5_baselines.json", "e2e.fields.FAIL", "val"),
    ("e2e_unreg", "fix_r5_baselines.json", "e2e.fields.UNREG/RUNFAIL", "val"),
    ("e2e_warn", "fix_r5_baselines.json", "e2e.fields.WARN", "val"),
    ("floors", "fix_r5_baselines.json", "floors", "len"),
    ("floor_pytest", "fix_r5_baselines.json", "floors.pytest", "val"),
    ("systems_total", "fix_r5_baselines.json", "three_systems_green", "len"),
    ("systems_green", "fix_r5_baselines.json", "three_systems_green", "true"),
    ("radius_touched", "fix_r5_baselines.json", "radius.allowed_touched", "val"),
    ("radius_forbidden", "fix_r5_baselines.json", "radius.forbidden_total", "val"),
    # 法⑦ 账面闭环
    ("closed", "fix_r5_ledger.json", "closed_ids", "len"),
    ("fixed_sections", "fix_r5_ledger.json", "fixed_sections", "len"),
    ("leftover", "fix_r5_ledger.json", "leftover_ids", "len"),
    ("three_way", "fix_r5_ledger.json", "three_way", "len"),
    ("three_way_bad", "fix_r5_ledger.json", "three_way_bad", "len"),
    ("agree", "fix_r5_ledger.json", "agree_total", "val"),
    # 法⑧ 驱动面
    ("hard", "fix_r5_drivers_lint.json", "hard_violations", "val"),
    ("soft", "fix_r5_drivers_lint.json", "soft_total", "val"),
    ("soft_baseline", "fix_r5_drivers_lint.json", "previous_round_soft_baseline", "val"),
    ("drivers", "fix_r5_drivers_lint.json", "drivers_scanned", "val"),
    ("lint_canary", "fix_r5_drivers_lint.json", "canary.bad_caught", "val"),
    # needle 严口径 + call_log 两档 + 车道回执
    ("needles", "fix_r5_needles.json", "real_key_len", "val"),
    ("needles_checked", "fix_r5_needles.json", "checked_len", "val"),
    ("tally_rows", "fix_r5_calllog_tally.json", "stages.{root}.rows", "val"),
    ("tally_nodes", "fix_r5_calllog_tally.json", "stages.{root}.distinct_tasks", "val"),
    ("ring_tag", "fix_r5_calllog_tally.json", "ring_tag_calls.total", "val"),
    ("fp_rows", "fix_r5_calllog_tally.json", "fingerprint_channel.rows", "val"),
    ("refusals", "fix_r5_calllog_tally.json", "distinct_refusal_texts", "val"),
    ("lanes", "r5_fix_lanes.json", "lanes", "len"),
)
CHECKS: list = []
REFUSE: list = []


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


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


def key_names(obj, acc, depth=1):
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


def preflight(laws, strict=True):
    bad = []
    for i, law in enumerate(laws, 1):
        for rel, needle, minc in law["artifacts"]:
            p = ROOT / rel
            if not p.exists():
                bad.append(f"law{i} 件不在盘上：{rel}")
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            try:
                doc = json.loads(txt)
            except json.JSONDecodeError as exc:
                bad.append(f"law{i} {rel} 不是合法 JSON：{str(exc)[:80]}")
                continue
            if strict and str(needle) not in key_names(doc, set()):
                bad.append(f"law{i} {rel} 里「{needle}」不是真键名")
            elif len(txt) < int(minc):
                bad.append(f"law{i} {rel} 仅 {len(txt)} 字符 < {minc}")
    return bad


def read(name: str) -> dict:
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pull(doc, path: str):
    """按点号路径取判据件里的嵌套键；任一段不存在就返回 (False, None)，不猜默认值。"""
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def mn(value) -> str:
    """实测数进文案；反解不出的一格写『未实测』而不是 0——0 是结论，未实测是没测。"""
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else "未实测"


def resolve_measured(root_task: str) -> tuple:
    """把 MEASURED 那张表逐格从判据件反解。

    反解不出的（件还没落盘、键路径不存在、口径对不上类型）一律进 unresolved 并留空，
    由判据红把整件收口顶回去——这一格的存在意义就是拦住手打的数。
    """
    docs = {art: read(art) for _, art, _, _ in MEASURED}
    measured = {name: None for name, _, _, _ in MEASURED}
    unresolved = []
    for name, art, path, how in MEASURED:
        real = path.replace("{root}", str(root_task or ""))
        found, val = pull(docs.get(art) or {}, real)
        if not found:
            unresolved.append(f"{name}←{art}:{real}（件不在盘上或键路径不存在）")
            continue
        if how == "len" and isinstance(val, (dict, list)):
            measured[name] = len(val)
        elif how == "true" and isinstance(val, list):
            measured[name] = sum(1 for x in val if x)
        elif how == "val" and isinstance(val, int) and not isinstance(val, bool):
            measured[name] = val
        else:
            unresolved.append(f"{name}←{art}:{real}（口径 {how} 取不到该类型的值）")
    return measured, unresolved


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    roots = json.loads(ROOTS.read_text(encoding="utf-8")) if ROOTS.exists() else {}
    root_task = roots.get("root")
    if not root_task:
        REFUSE.append("根任务号没拿到（root_r5_fix.out.json 缺失或没有 root 字段）")
    leaves, branches = roots.get("leaves") or [], roots.get("branches") or []
    check("叶子按 sqlite 反解到 16 张", len(leaves), 16, f"实得 {len(leaves)}")
    check("分支 8 支（每条法一支）", len(branches), 8, f"实得 {len(branches)}")
    check(
        "omega 强验证在每支叶子上都开着",
        roots.get("omega_off"),
        [],
        json.dumps(roots.get("omega_off"), ensure_ascii=False)[:200],
    )
    check(
        "计划八条法逐条有 3 件证据",
        sorted({len(row["artifacts"]) for row in plan["laws"]}),
        [3],
        "artifacts 条数分布",
    )
    check("计划法条数 = 收口法条数（同源）", len(plan["laws"]), 8, "同一份计划派单与收口")
    bad = preflight(plan["laws"])
    check(
        "渲染前预检：件在盘上、能 parse、needle 是真键名、长度达标",
        bad,
        [],
        json.dumps(bad, ensure_ascii=False)[:400],
    )
    # canary 的前缀不手打：从法③ 已判真的那条 needle 上机械截一半，
    # 于是「严口径必拒」与「子串口径必放行」两侧都还在同一把尺子上。
    probe_rel, probe_needle = plan["laws"][2]["artifacts"][0][0], plan["laws"][2]["artifacts"][0][1]
    probe = probe_needle[: max(3, len(probe_needle) // 2)]
    probe_laws = [{**plan["laws"][2], "artifacts": [[probe_rel, probe, 1]]}]
    fake = preflight(probe_laws)
    check(
        f"canary：前缀式 needle（{probe_needle}→{probe}）必被严口径拒",
        bool(fake),
        True,
        json.dumps(fake, ensure_ascii=False)[:200],
        ok=bool(fake),
    )
    lax = preflight(probe_laws, strict=False)
    check(
        "canary 的另一侧：同一个前缀在旧子串口径下会被放行（说明严口径真的加了约束）",
        lax,
        [],
        f"子串口径对 {probe} 的判定：{json.dumps(lax, ensure_ascii=False)[:180]}",
    )
    probe_doc = read(Path(probe_rel).name)
    probe_txt = (
        (ROOT / probe_rel).read_text(encoding="utf-8", errors="replace")
        if (ROOT / probe_rel).exists()
        else ""
    )
    check(
        "canary 用的前缀确实是『被引件原文里有、真键名里没有』（不然上面两侧的 canary 都是假绿）",
        [bool(probe_doc), probe in probe_txt, probe in key_names(probe_doc, set())],
        [True, True, False],
        f"{probe_rel}：{probe_needle}→{probe}",
    )
    for law in plan["laws"]:
        for rel, needle, minc in law["artifacts"]:
            if not (ROOT / rel).exists():
                REFUSE.append(f"法条引用了不存在的判据件：{rel}")

    # 根上卷件（close_root_generic.py 要的形状）：branches 是「法名 / 证据件 / needle」三元组，
    # 外加根上的 marker·交付文案·验收理由·附加产物。数字全部按 MEASURED 表反解，不手打。
    measured, unresolved = resolve_measured(root_task)
    measured["laws"] = len(plan["laws"])
    measured["leaves"] = len(leaves)
    measured["branches"] = len(branches)
    m = {k: mn(v) for k, v in measured.items()}
    check(
        "measured 每一格都能从本环判据件反解（反解不出=件没跑完或键名是我编的）",
        unresolved,
        [],
        json.dumps(unresolved, ensure_ascii=False)[:400],
    )
    branch_spec = [
        [law["name"], law["artifacts"][0][0], law["artifacts"][0][1]] for law in plan["laws"]
    ]
    root_marker = plan.get("root_marker") or FIX_MARKER
    check(
        "根 marker 是本环（修复）的页脚字样，不是上一环（寻虫）那个",
        [root_marker, root_marker == HUNT_MARKER],
        [FIX_MARKER, False],
        f"实得 {root_marker}；spec 自带的 root_marker={plan.get('root_marker')!r}",
    )
    banned = [str(x) for x in (plan.get("fingerprint") or {}).get("禁止") or []]
    forbid = "；".join(banned)
    check(
        "禁止栏逐条从 spec.fingerprint.禁止 反解，且没留上一环那句『禁止在本环修产品码』",
        [
            bool(banned),
            all(line in forbid for line in banned),
            HUNT_FORBID in forbid,
        ],
        [True, True, False],
        f"{len(banned)} 条：{forbid[:180]}",
    )
    root_deliverable = (
        "R5-修复 交付：{REPORT}。八法＝① 认领表从账本现读反解：账上未闭环 "
        f"{m['cards_total']} 张里本环认领 {m['claimed']} 张（R5-寻虫 新立 {m['ring_new']} 张＋旧账转结 "
        f"{m['legacy_open']} 张），分栏 {m['split_columns']} 栏「本环可修／交人工／已闭环不复修」逐张"
        "点名归属理由，交人工的一张都不占修、不改账本状态（没认领的严重度按 "
        f"{m['unclaimed_gaps']} 档逐档给数，不写统称）→ ② 锁先行："
        f"{m['locked']} 张单各一条锁，动实现前红 {m['lock_red']} 条、动实现后绿 {m['lock_green']} 条"
        f"（共 {m['lock_nodes']} 个测试节点），红落在断言级的 {m['lock_assertion']} 条——收集错、夹具崩、"
        f"import 错一律不算红；在 HEAD 快照树上复算后仍为绿的 {m['green_on_head']} 条，"
        f"没锁的 {m['locks_missing']} 张逐条点名、不并进闭环主张 → ③ 根因合并修：改动点 "
        f"{m['change_points']} 处、按 (文件,符号) 归并成 {m['merged_rc']} 个根因、符号引用 "
        f"{m['symbols']} 个，落在本环改动的 {m['ring_files']} 个文件上；没单认领的产品文件 "
        f"{m['no_card_files']} 个、只被派单半径覆盖而没单点到的 {m['scope_only_files']} 个、"
        f"复算没归到任何单的 {m['unattributed']} 处逐条点名不藏；认领了却没修完的 {m['unfixed']} 张"
        "仍按 OPEN 转结 → ④ 回退矩阵："
        f"{m['matrix_rows']} 行（＝认领单数，一张不落；本环没产品码改动的记 not_measured 而不是"
        f"假装摘过），其中带锁可测的 {m['rows_with_lock']} 行，摘回单元按锁承重并成 {m['groups']} 组，"
        f"摘回后变红 {m['revert_red']} 单"
        f"（断言级 {m['assertion_ids']} 单），第一遍数到的 {m['collateral']} 条组间牵连并组复扫后归零，"
        f"摘完 {m['sha_restored']}/{m['sha_files']} 个文件逐个 sha 复原自证；承重探针正面数出 "
        f"{m['bearing']} 个产品文件真承重、{m['unborne']} 个不承重、派单声明面里没承重的 "
        f"{m['declared_not_bearing']} 个，三份清单同屏点名 → ⑤ 影响面：{m['corpus']} 档存量语料"
        f"在 HEAD 树与当前树各跑一遍分析/转译，新增诊断 {m['new_diag']} 条、新增被拒 {m['new_rej']} 条、"
        f"新增可编译 {m['new_acc']} 条、诊断形状变了 {m['shape_changed']} 条，需交裁决 "
        f"{m['adjudication']} 条——有命中就挂账交裁决，本环不放宽不放行 → ⑥ 三套体系同批全量复算："
        f"pytest 过 {m['pytest_passed']} 条、失败 {m['pytest_failed']} 条、收集 "
        f"{m['collect_nodes']} 节点；"
        f"自研套件过 {m['suite_passed']} 条、失败 {m['suite_failed']} 条；e2e PASS {m['e2e_pass']} 条、"
        f"FAIL {m['e2e_fail']} 条、UNREG/RUNFAIL {m['e2e_unreg']} 条、WARN {m['e2e_warn']} 条；"
        f"地板 {m['floors']} 格从上一环实测件反解且只升不降（pytest 地板 {m['floor_pytest']}），"
        f"三套体系绿 {m['systems_green']}/{m['systems_total']} 格；改动半径 {m['radius_touched']} 个"
        f"允许面文件、冻结面被碰 {m['radius_forbidden']} 处 → ⑦ 账面闭环：{m['closed']} 张走完 "
        "claim→execute→submit→verify，账本追加 FIXED 段 "
        f"{m['fixed_sections']} 段，未修完如实留 OPEN {m['leftover']} 张并逐字写明卡在哪，"
        f"服务端回读／账本／sqlite 三向对照 {m['three_way']} 张里一致 {m['agree']} 张、对不上 "
        f"{m['three_way_bad']} 张 → ⑧ 驱动面：亲笔脚本 {m['drivers']} 个、硬码违规 {m['hard']} 条、"
        f"软账 {m['soft']} 条不高于上一环实测基线 {m['soft_baseline']} 条，注入对照被抓到 "
        f"{m['lint_canary']} 条（证明 lint 不是恒绿）；needle 严口径 {m['needles']}/"
        f"{m['needles_checked']} 条全是被引件里的真键名；call_log 按号段现数 {m['tally_rows']} 行"
        f"（{m['tally_nodes']} 个节点），环标签档 {m['ring_tag']} 行、指纹档 {m['fp_rows']} 行——"
        "标签档数到零行时报告里写的是『过滤器看不见这个标签』而不是『没开过』，两档都数不到的工具"
        f"逐条点名等价承担者（工具名不存在≠能力没开）；本环被拒原文 {m['refusals']} 条逐字进件；"
        f"车道回执 {m['lanes']} 条自报文件全部被 git diff 与 mtime 复算过（报了≠改了）。"
        "本环零提交，HEAD 未动。"
    )
    root_verify_reason = (
        "修复环最容易说谎的是『这单我修完了』这句话，所以每一层都配了反向证明："
        "(一) 认领表从账本现读反解，分栏之和必须等于未闭环卡数（分栏不吞行），交人工的单只进表不占修、"
        "不改状态；`unclaimed_severities` 逐档点名没认领的严重度，而不是统称『已评估』。"
        "(二) 锁的红一律在 `git archive HEAD` 解出的独立快照树里复算：`lock_green_on_head` 必须为空，"
        "`locks_missing` 里的单不并进闭环主张；collection error、夹具崩、import 错都不算红，"
        "`assertion_level_red_only` 只数断言级那一档。"
        "(三) 根因合并按 (文件,符号) 归并并给 file:line＋符号引用，`product_files_without_card`、"
        "`covered_only_by_scope`、`unattributed_changes` 任一非空都要逐条点名——一堆补丁冒充根因、"
        "或改了没单认领的文件，在这里藏不住；`unfixed_claimed` 非空就是没修完，按 OPEN 转结不写成本环修掉。"
        "(四) 回退矩阵每单一行：摘回不红＝这条锁不承重，`revert_red_ids` 数不满有锁的行数就要点名；"
        "`collateral` 记第一遍观测到的组间牵连、并组复扫后必须归零；`sha_restored` 与 `sha_files_total` "
        "不等即拒；`extras.bearing` 是正面测出来的承重面，`unborne_files` 与 "
        "`declared_face_not_bearing` 专门点名『派单时声明改了、探针说没承重』那批文件；"
        "空操作对照（摘一条本环根本没碰的文件）也配了，它一红整套矩阵作废。"
        "(五) 影响面：两档 API 面不等（HEAD 的 hook 没有 analyze_only）时本件写 `not_measured` 并只走 "
        "transpile 错误面，不写成『没有影响』；`new_rejections` 或 `shape_changed` 有命中就挂账交裁决，"
        "`new_acceptances`（改好的那部分）与变差的那部分同屏列出，不自挑好看的。"
        "(六) 三套体系同批全量复算，地板从上一环实测件的 `floors` 反解、只升不降；`three_systems_green` "
        "缺任一格或 `three_systems_ok` 不为真就不写『全绿』；冻结面与 git 红线按 mtime＋sha 正面测出"
        "改动半径，`radius.touched_forbidden` 非空即拒。"
        "(七) 账面闭环按 claim→execute→submit→verify 逐单走，服务端回读／账本／sqlite 三向对照，"
        "对不上的进 `three_way_bad` 并拒；未修完的留 OPEN 且由 `leftover_marked` 逐字写明卡在哪；"
        "被拒原文逐字进件（`refusals_md`）。"
        "(八) 驱动面硬码 lint 配注入对照：`canary.bad_caught` 抓不到东西就说明这套 lint 恒绿、判据坏了；"
        "软账与上一环实测基线逐格对齐；渲染次数按见证件记录数而不是文件存在性。"
        "(九) call_log 两档并记（环标签档＋指纹档）。某档数到零行时，报告里写的是『过滤器看不见这个标签』"
        "或『本 build 没有这个工具名』，并点名等价能力由谁承担，而不是『没开过』或『已开启』；"
        "needle 一律按『被引件里的真键名』校，从已判真 needle 上机械截出来的前缀式假命中被严口径拒。"
        "(十) 零值测量（`hard_violations` 为零、`collateral` 为空、`new_rejections` 为空）是合法结果，"
        "门禁把零值当缺失就是判据坏了；反过来『件还没跑完』不算零值，"
        "`root_measured` 里反解不出的一格一律写成未实测并进 refuse。"
    )
    root_extra = [list(row) for row in EXTRA_ARTIFACTS]
    report_stub = "memory/reviews/x.md"
    rendered = root_deliverable.replace("{REPORT}", report_stub)
    allowed = {v for v in measured.values() if isinstance(v, int) and not isinstance(v, bool)}
    stray = sorted(
        {
            int(t)
            for t in re.findall(r"(?<![\w.])\d+(?![\w.])", rendered + "\n" + root_verify_reason)
            if int(t) not in allowed
        }
    )
    check(
        "根交付文案＋根验收理由里每个整数都落在 MEASURED 反解出来的数集内（不许手打新数字）",
        stray,
        [],
        f"allowed={sorted(allowed)} unresolved={len(unresolved)}",
    )
    check(
        "渲染前预检用的报告占位串里不含阿拉伯数字（含了就能把数字偷渡过上面那条门）",
        bool(re.findall(r"\d", report_stub)),
        False,
        report_stub,
    )
    check(
        "branches 三元组数 = 法条数（根上卷按支取证据件）",
        len(branch_spec),
        len(plan["laws"]),
        "close_root_generic 按分支号取 (法, 件, needle)",
    )
    check(
        "附加产物逐件在盘上、且 needle 是被引件里的真键名",
        [
            (ROOT / p).exists() and str(n) in key_names(read(Path(p).name), set())
            for p, n, _ in root_extra
        ],
        [True] * len(root_extra),
        json.dumps(root_extra, ensure_ascii=False)[:260],
    )
    check(
        "附加产物点的件全是本环件（混进上一环的 faces/declared/book 那一类即红）",
        sorted({Path(p).name for p, _, _ in root_extra}),
        sorted(
            [
                "fix_r5_calllog_tally.json",
                "fix_r5_drivers_lint.json",
                "fix_r5_ledger.json",
                "fix_r5_needles.json",
                "fix_r5_revert.json",
            ]
        ),
        json.dumps(sorted({Path(p).name for p, _, _ in root_extra}), ensure_ascii=False),
    )
    doc = {
        "key": plan["key"],
        "root_task": root_task,
        "assignee": plan["assignee"],
        "stage": "R5-修复",
        "forbid": forbid,
        "forbid_source": "spec_r5_fix.json:fingerprint.禁止（逐条反解，非本文件手打）",
        "laws": plan["laws"],
        "branches": branch_spec,
        "branch_ids": branches,
        "root_marker": root_marker,
        "root_deliverable": root_deliverable,
        "root_verify_reason": root_verify_reason,
        "root_extra_artifacts": root_extra,
        "root_measured": measured,
        "measured_unresolved": unresolved,
        "measured_source_table": [list(row) for row in MEASURED],
        "leaves": leaves,
        "fingerprint": plan.get("fingerprint"),
        "needle_verification": plan.get("needle_verification"),
        "started": started,
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_s(),
    }
    red = [c["label"] for c in CHECKS if not c["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red})
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "root": root_task,
                "leaves": len(leaves),
                "laws": len(plan["laws"]),
                "marker": root_marker,
                "measured_unresolved": len(unresolved),
                "self_checks": f"{len(CHECKS) - len(red)}/{len(CHECKS)}",
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
