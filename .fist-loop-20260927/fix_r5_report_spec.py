"""生成 R5-修复 的报告 spec（门禁表）+ 一条由实测拼出来的页脚。

取数原则与前面几轮一致：**每条门禁都要能红**，而且尽量走「两路对撞」而不是「件里有这个数」：
- 每个判据件三道：`refuse` 逐字为空表、`self_checks` 条数下限、`started` 戳存在（旧件冒充本轮新跑
  就是靠这一道抓的）；
- 八法各自的数值门引被引件里的**真键名**（`fix_r5_needles.py` 严口径实测过）；
- 关键数还要和本驱动**自己另开一路**的实测对撞：git 现读、盘上 glob、账本现读、上一环实测件反解——
  「件里写了个数」本身不是证据；
- 地板一律从上一环的实测件（hunt_r5_baselines.json / hunt_r5_drivers_lint.json）反解，件不在或栏不全
  就把值设成一个大到不可能通过的数，让门禁红，而不是退回手打数字。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = ".fist-loop-20260927"
ROOT = HERE.parent
OUT = HERE / "report_spec_r5_fix.json"
PLAN = json.loads((HERE / "spec_r5_fix.json").read_text(encoding="utf-8"))
ROOT_TASK = "T0r110"
PREV = "hunt_r5_baselines.json"
PREV_LINT = "hunt_r5_drivers_lint.json"
MARK_FIXED = "### FIXED(verify=已完成) — 2026-09-28 R5-修复 追加留档"
MARK_LEFT = "### NOT-FIXED(R5-修复 转结)"
IMPOSSIBLE = 10**9
PRODUCT_PREFIXES = ("cypyc/", "cypy_hook/", "cypy_bridge/", "scripts/")

ARTIFACTS = [
    "spec_r5_fix.json",
    "r5_fix_lanes.json",
    "fix_r5_intake.py",
    "fix_r5_intake.json",
    "fix_r5_locks.py",
    "fix_r5_locks.json",
    "fix_r5_rc.py",
    "fix_r5_rc.json",
    "fix_r5_revert.py",
    "fix_r5_revert.json",
    "fix_r5_impact.py",
    "fix_r5_impact.json",
    "fix_r5_baselines.py",
    "fix_r5_baselines.json",
    "fix_r5_ledger.py",
    "fix_r5_ledger.json",
    "fix_r5_drivers_lint.py",
    "fix_r5_drivers_lint.json",
    "fix_r5_calllog_tally.py",
    "fix_r5_calllog_tally.json",
    "fix_r5_book91.py",
    "fix_r5_book91.json",
    "fix_r5_lane_identity.py",
    "fix_r5_needles.py",
    "fix_r5_needles.json",
    "fix_r5_self_audit.py",
    "fix_r5_report_spec.py",
    "fix_r5_close_spec.py",
    "close_r5_fix.json",
    "fix_r5_render_order.py",
    "fix_r5_render_witness.py",
    "fix_r5_progress.py",
    "loop_kit.py",
    "close_stage_generic.py",
    "close_root_generic.py",
    "close_r5_fix.out.json",
    "close_r5_fix_root.out.json",
    "loop_progress.md",
]
SELF_CHECKED = [
    "fix_r5_intake.json",
    "fix_r5_locks.json",
    "fix_r5_rc.json",
    "fix_r5_revert.json",
    "fix_r5_impact.json",
    "fix_r5_baselines.json",
    "fix_r5_ledger.json",
    "fix_r5_drivers_lint.json",
    "fix_r5_calllog_tally.json",
    "fix_r5_needles.json",
    "fix_r5_book91.json",
    "close_r5_fix.json",
]
# 每条判据件的自证条数下限 = 该驱动设计上的判据数；掉了说明判据被删，不是麻烦被减。
FLOORS = {
    "fix_r5_intake.json": 10,
    "fix_r5_locks.json": 10,
    "fix_r5_rc.json": 5,
    "fix_r5_revert.json": 10,
    "fix_r5_impact.json": 6,
    "fix_r5_baselines.json": 14,
    "fix_r5_ledger.json": 8,
    "fix_r5_drivers_lint.json": 3,
    "fix_r5_calllog_tally.json": 10,
    "fix_r5_needles.json": 4,
    "fix_r5_book91.json": 10,
    "close_r5_fix.json": 4,
}
# 起跑戳的字段名各家不同（八件判据件都用 `started`，入账件用的是它自己的 `started_at_utc`），
# 逐件点名，不许靠“大概都叫 started”这种印象。
STARTED_PATH = {"fix_r5_book91.json": "started_at_utc"}
GATES: list = []


def g(label, claim, artifact, path, kind, value) -> None:
    row = {"label": label, "claim": claim, "artifact": f"{D}/{artifact}", "path": path}
    row[kind] = value
    GATES.append(row)


def read(name: str) -> dict:
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def node(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def sh(*args: str) -> str:
    out = subprocess.run(
        list(args),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return out.stdout or ""


def git_head_short() -> str:
    return sh("git", "rev-parse", "--short", "HEAD").strip()


def git_staged_rows() -> int:
    return len([x for x in sh("git", "diff", "--cached", "--name-only").splitlines() if x.strip()])


def git_product_files() -> list:
    """本驱动自己数一遍「本环窗口内改过的产品文件」：git 的 diff/未跟踪 ∩ mtime 落在窗口里。

    与 fix_r5_rc.py 的 numstat+ast 口径是两套实现，对不上就有一路在说谎。
    窗口起点取 rc 现读的 `ring_start_utc`（= 本环根任务的 created_at），不是手打时间。
    """
    import datetime
    import os

    start = node(read("fix_r5_rc.json"), "ring_start_utc") or ""
    try:
        since = datetime.datetime.fromisoformat(start).timestamp()
    except ValueError:
        return ["<ring_start_utc 读不出来：这一路作废，门禁必须红>"]
    found = set()
    for line in sh("git", "diff", "HEAD", "--name-only").splitlines():
        rel = line.strip().replace("\\", "/")
        if rel.startswith(PRODUCT_PREFIXES) and (ROOT / rel).exists():
            if os.stat(ROOT / rel).st_mtime >= since - 1:
                found.add(rel)
    for line in sh("git", "ls-files", "--others", "--exclude-standard").splitlines():
        rel = line.strip().replace("\\", "/")
        if rel.startswith(PRODUCT_PREFIXES) and (ROOT / rel).exists():
            if os.stat(ROOT / rel).st_mtime >= since - 1:
                found.add(rel)
    return sorted(found)


def glob_lock_test_files() -> int:
    return len(sorted((ROOT / "tests").rglob("test_r5_fix_*.py")))


def corpus_files_on_disk() -> int:
    """按 impact 件自己声明的 corpus_dirs 现数（档数不是自报的，也不能靠本驱动挑目录）。"""
    dirs = node(read("fix_r5_impact.json"), "corpus_dirs") or []
    n = 0
    for d in dirs:
        base = ROOT / str(d)
        if not base.exists():
            continue
        n += len([p for p in base.rglob("*.cypy") if "__pycache__" not in p.parts])
    return n


def ledger_text() -> str:
    return (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")


def ledger_section_count(mark: str) -> int:
    return len(re.findall(re.escape(mark), ledger_text()))


def ledger_entry_total() -> int:
    return len(re.findall(r"(?m)^## BUG-\d+ ", ledger_text()))


def drivers_scanned_here() -> int:
    return len(sorted(HERE.glob("fix_r5_*.py")))


def floor_of(name: str, path: str) -> int:
    """地板从上一环实测件反解；件没跑或栏缺失就设一个不可能通过的数（门禁红，不手打）。"""
    v = node(read(name), path)
    return int(v) if isinstance(v, (int, float)) else IMPOSSIBLE


def measured(name: str, path: str, default: int) -> int:
    v = node(read(name), path)
    if v is None:
        return default
    return len(v) if isinstance(v, (list, dict, str)) else int(v)


def main() -> int:
    n = 0
    for name in SELF_CHECKED:
        n += 1
        g(
            f"①-{n}",
            f"`{name}` 的 refuse 必须逐字为空表（件内每条自证都要判过）",
            name,
            "refuse",
            "equals",
            [],
        )
    n = 0
    for name in SELF_CHECKED:
        n += 1
        g(
            f"②-{n}",
            f"`{name}` 的 self_checks 条数不低于设计下限 {FLOORS[name]}"
            "（判据被删掉就是掉分，不是掉麻烦）",
            name,
            "self_checks",
            "min",
            FLOORS[name],
        )
    n = 0
    for name in SELF_CHECKED:
        n += 1
        stamp = STARTED_PATH.get(name, "started")
        g(
            f"③-{n}",
            f"`{name}` 带有本轮起跑戳 `{stamp}`（旧件冒充本轮新跑就靠这一道抓）",
            name,
            stamp,
            "truthy",
            True,
        )

    ic = read("fix_r5_intake.json")
    lk = read("fix_r5_locks.json")
    rc = read("fix_r5_rc.json")
    rv = read("fix_r5_revert.json")
    im = read("fix_r5_impact.json")
    bs = read("fix_r5_baselines.json")
    lg = read("fix_r5_ledger.json")
    ln = read("fix_r5_drivers_lint.json")
    tl = read("fix_r5_calllog_tally.json")
    nd = read("fix_r5_needles.json")
    prev_bs = read(PREV)
    prev_ln = read(PREV_LINT)

    # ── 法①：认领表从盘上反解
    g(
        "法①-1",
        "本环认领的单数 ≥ 20（R5-寻虫 入账 13 张 + 本环修复途中新入账 1 张 + 账本现数未闭环旧单里可修的那批）",
        "fix_r5_intake.json",
        "planned_ids",
        "min",
        20,
    )
    g(
        "法①-2",
        "每张认领单都带归属栏与理由（cards 条数 ≥ 认领单数）",
        "fix_r5_intake.json",
        "cards",
        "min",
        measured("fix_r5_intake.json", "planned_ids", 20),
    )
    g(
        "法①-3",
        "旧单未闭环栏不为空（legacy_open_ids 从 bugs 树现读，不是我记得）",
        "fix_r5_intake.json",
        "legacy_open_ids",
        "min",
        3,
    )
    g(
        "法①-4",
        "分栏表在场（本环可修／交人工／已闭环不复修／红线，逐张给归属）",
        "fix_r5_intake.json",
        "split_columns",
        "truthy",
        True,
    )
    g(
        "法①-5",
        "交人工的单必须带卡片原文逐字引文（handoff_quote_len > 0）",
        "fix_r5_intake.json",
        "handoff_quote_len",
        "min",
        1,
    )
    g(
        "法①-6",
        "归属规则不许留模棱两可的单（ambiguous_bare 必须空表，有条目就得交裁决）",
        "fix_r5_intake.json",
        "ambiguous_bare",
        "equals",
        [],
    )
    g(
        "法①-7",
        "没有服务端单号的账面条目逐条点名（no_server_card_ids 是实测差集不是形容词）",
        "fix_r5_intake.json",
        "no_server_card_ids",
        "truthy",
        True,
    )

    # ── 法②：锁先行
    g(
        "法②-1",
        "有锁的单数 ≥ 15（每单一条会失败的锁测试）",
        "fix_r5_locks.json",
        "locked_ids",
        "min",
        15,
    )
    g(
        "法②-2",
        "锁在 HEAD 快照树上复算出的红 ≥ 15 单（旧码不红=锁不承重）",
        "fix_r5_locks.json",
        "lock_red_before",
        "min",
        15,
    )
    g(
        "法②-3",
        "锁在当前树上全绿（绿 ≥ 15 单，缺一环就是假锁）",
        "fix_r5_locks.json",
        "lock_green_after",
        "min",
        15,
    )
    g(
        "法②-4",
        "红一律是断言级（跑到断言级红才算动过实现，收集错与 import 错不算）",
        "fix_r5_locks.json",
        "assertion_level_red_only",
        "truthy",
        True,
    )
    g(
        "法②-5",
        "锁节点总数 ≥ 100（条数从 pytest 现读）",
        "fix_r5_locks.json",
        "lock_nodes_total",
        "min",
        100,
    )
    g(
        "法②-6",
        "无锁的单逐条点名（locks_missing 是缺的证据清单）",
        "fix_r5_locks.json",
        "locks_missing",
        "truthy",
        True,
    )
    g(
        "法②-7",
        "快照树身份探针在场（跑错副本树时这套红全是假的）",
        "fix_r5_locks.json",
        "canary_probe",
        "truthy",
        True,
    )
    g(
        "法②-8",
        "幽灵节点对照在场：不存在的 nodeid 必须报 no tests ran",
        "fix_r5_locks.json",
        "ghost_probe",
        "truthy",
        True,
    )
    g(
        "法②-9",
        "锁文件行数 ≥ 盘上 glob 到的 test_r5_fix_*.py 数（两路各数一遍）",
        "fix_r5_locks.json",
        "runs",
        "min",
        glob_lock_test_files(),
    )

    # ── 法③：根因合并修
    g(
        "法③-1",
        "改动点条数 ≥ 400（file::symbol 由 git+ast 反解）",
        "fix_r5_rc.json",
        "change_points",
        "min",
        400,
    )
    g("法③-2", "同族根因合并后引用的符号 ≥ 300", "fix_r5_rc.json", "symbols_referenced", "min", 300)
    g(
        "法③-3",
        "合并后的根因组 ≥ 200（一堆补丁冒充根因就数不出这个）",
        "fix_r5_rc.json",
        "merged_root_cause_len",
        "min",
        200,
    )
    g(
        "法③-4",
        "改动无人归属的文件必须空表（改了没人报=清单口径漏面）",
        "fix_r5_rc.json",
        "unattributed_changes",
        "equals",
        [],
    )
    g(
        "法③-5",
        "rc 认领面的号段与本环计划同源（planned_keys 条数 ≥ 认领单数）",
        "fix_r5_rc.json",
        "planned_keys",
        "min",
        measured("fix_r5_intake.json", "planned_ids", 20),
    )
    g(
        "法③-6",
        "改了但没被任何单点名的产品文件必须逐条列出（交回退矩阵实测承重）",
        "fix_r5_rc.json",
        "product_files_without_card",
        "truthy",
        True,
    )
    g(
        "法③-7",
        "车道回执条数 ≥ 5（报了不等于改了，逐条看盘）",
        "fix_r5_rc.json",
        "lane_receipts",
        "min",
        5,
    )
    g(
        "法③-8",
        "只按派单半径覆盖、没按自报文件覆盖的面要逐条点名（自报漏面就靠这栏翻出来）",
        "fix_r5_rc.json",
        "covered_only_by_scope",
        "truthy",
        True,
    )

    # ── 法④：回退矩阵
    g(
        "法④-1",
        "矩阵条数 ≥ 认领单数（没产品码改动的单也占一行，写 not_measured 而不是消失）",
        "fix_r5_revert.json",
        "matrix_rows",
        "min",
        measured("fix_r5_intake.json", "planned_ids", 21),
    )
    g(
        "法④-2",
        "摘回后变红的单 ≥ 12（不红的单在这环不算修完）",
        "fix_r5_revert.json",
        "revert_red_ids",
        "min",
        12,
    )
    g(
        "法④-3",
        "红里断言级的单 ≥ 8（要的是锁承重，不是树被摘坏）",
        "fix_r5_revert.json",
        "assertion_level_ids",
        "min",
        8,
    )
    g(
        "法④-4",
        "组间牵连必须为零（按实测承重闭包合组之后还牵连=假分离）",
        "fix_r5_revert.json",
        "collateral",
        "equals",
        [],
    )
    g(
        "法④-5",
        "sha 复原数 = 摘回文件数（复原不是拼接）",
        "fix_r5_revert.json",
        "sha_restored",
        "equals",
        measured("fix_r5_revert.json", "sha_files_total", IMPOSSIBLE),
    )
    g(
        "法④-6",
        "空操作摘回的反证跑过（本环没改过的文件按 HEAD 重写=空操作，锁必须还绿）",
        "fix_r5_revert.json",
        "canary_no_op_revert",
        "truthy",
        True,
    )
    g(
        "法④-7",
        "探针摘回单元与本驱动自己 git 数到的产品文件逐字相等（两套实现必须同集）",
        "fix_r5_revert.json",
        "extras.units_probed",
        "equals",
        git_product_files(),
    )
    g(
        "法④-8",
        "每个被摘的文件都至少打红一张单的锁（unborne_files 必须空表）",
        "fix_r5_revert.json",
        "extras.unborne_files",
        "equals",
        [],
    )
    g(
        "法④-9",
        "副本树里 import 到的就是副本那份（孪生树顶掉副本时整套矩阵作废）",
        "fix_r5_revert.json",
        "extras.identity.inside_work_tree",
        "equals",
        True,
    )
    g(
        "法④-10",
        "真树在全程未被写入（root_tree_dirtied 必须空表）",
        "fix_r5_revert.json",
        "extras.root_tree_dirtied",
        "equals",
        [],
    )
    g(
        "法④-11",
        "卡片点名面与实测承重面不一致的文件逐条列出（BUG-84/88 那类归属差）",
        "fix_r5_revert.json",
        "extras.declared_face_not_bearing",
        "truthy",
        True,
    )

    # ── 法⑤：语义变更影响面
    g(
        "法⑤-1",
        "语料档数 = 本驱动 glob 到的 .cypy 文件数（语料面不是自报）",
        "fix_r5_impact.json",
        "corpus_total",
        "equals",
        corpus_files_on_disk(),
    )
    g(
        "法⑤-2",
        "「修前可编译→修后被拒」必须为 0（收紧要交裁决，不自批）",
        "fix_r5_impact.json",
        "new_rejections_len",
        "equals",
        0,
    )
    g(
        "法⑤-3",
        "「修前无诊断→修后有诊断」清单在场（逐条实测，空表也是数出来的空表）",
        "fix_r5_impact.json",
        "new_diagnostics",
        "truthy",
        True,
    )
    g(
        "法⑤-4",
        "被本环新接受的语料 ≥ 5（变宽也要数出来）",
        "fix_r5_impact.json",
        "new_acceptances_len",
        "min",
        5,
    )
    g(
        "法⑤-5",
        "产物形状变化 ≥ 1（零变化就说明两棵树跑的是同一份码）",
        "fix_r5_impact.json",
        "shape_changed_len",
        "min",
        1,
    )
    g(
        "法⑤-6",
        "要裁决的档数如实点名（corpus_adjudication_files 是清单不是形容词）",
        "fix_r5_impact.json",
        "corpus_adjudication_files",
        "truthy",
        True,
    )
    g(
        "法⑤-7",
        "HEAD 引擎与当前引擎的 API 面差异如实记录（测不到的通道一律写 not_measured）",
        "fix_r5_impact.json",
        "api_surface",
        "truthy",
        True,
    )

    # ── 法⑥：三套体系 + 地板 + 半径
    g(
        "法⑥-1",
        f"pytest 通过数 ≥ 上一环实测地板 {node(prev_bs, 'floors.pytest')}",
        "fix_r5_baselines.json",
        "pytest.passed",
        "min",
        floor_of(PREV, "floors.pytest"),
    )
    g(
        "法⑥-2",
        "pytest 无失败（failed_sum 必须 0）",
        "fix_r5_baselines.json",
        "pytest.failed_sum",
        "equals",
        0,
    )
    g(
        "法⑥-3",
        f"collect-only 的 nodeid 数 ≥ 上一环实测地板 {node(prev_bs, 'floors.collect')}",
        "fix_r5_baselines.json",
        "collect.nodeids",
        "min",
        floor_of(PREV, "floors.collect"),
    )
    g(
        "法⑥-4",
        f"自研套件通过数 ≥ 上一环实测地板 {node(prev_bs, 'floors.suite')}",
        "fix_r5_baselines.json",
        "suite.fields.Passed",
        "min",
        floor_of(PREV, "floors.suite"),
    )
    g(
        "法⑥-5",
        f"e2e golden PASS ≥ 上一环实测地板 {node(prev_bs, 'floors.e2e_pass')}",
        "fix_r5_baselines.json",
        "e2e.fields.PASS",
        "min",
        floor_of(PREV, "floors.e2e_pass"),
    )
    g(
        "法⑥-6",
        "三套体系全绿（有一格假就不许发闭环件）",
        "fix_r5_baselines.json",
        "three_systems_ok",
        "equals",
        True,
    )
    g(
        "法⑥-7",
        "HEAD 与本驱动现读 git rev-parse 一致（本环红线：不提交、不 rebase）",
        "fix_r5_baselines.json",
        "git.head",
        "equals",
        git_head_short(),
    )
    g(
        "法⑥-8",
        "暂存区为空（红线：不得 git add）",
        "fix_r5_baselines.json",
        "git.staged",
        "equals",
        git_staged_rows(),
    )
    g(
        "法⑥-9",
        "冻结面改动半径为零（PROJECT-SPEC/SYNTAX/套件配置/根文档）",
        "fix_r5_baselines.json",
        "radius.forbidden_total",
        "equals",
        0,
    )
    g(
        "法⑥-10",
        "地板四栏逐字等于上一环实测件那四栏（防手打也防自我放宽）",
        "fix_r5_baselines.json",
        "floors",
        "equals",
        node(prev_bs, "floors") or {},
    )
    g(
        "法⑥-11",
        "本轮确实写了东西（改动半径正面测出，allowed_touched > 0）",
        "fix_r5_baselines.json",
        "radius.allowed_touched",
        "min",
        1,
    )
    g(
        "法⑥-12",
        "外部 HEAD 基线 worktree 仍在（不属于本环的东西不许被顺手删掉）",
        "fix_r5_baselines.json",
        "git.foreign_worktree_present",
        "equals",
        True,
    )

    # ── 法⑦：账面闭环
    g(
        "法⑦-1",
        "闭环单数 ≥ 12（能闭环的单是五件交集算出来的，不是我列的）",
        "fix_r5_ledger.json",
        "closed_keys_len",
        "min",
        12,
    )
    g(
        "法⑦-2",
        "账本里本环 FIXED 段条数 = 件里记的闭环单数（本驱动现读账本对撞）",
        "fix_r5_ledger.json",
        "fixed_sections",
        "equals",
        ledger_section_count(MARK_FIXED),
    )
    g(
        "法⑦-3",
        "转结段条数 = 件里记的未清单数（一张都不许悄悄消失）",
        "fix_r5_ledger.json",
        "not_fixed_sections",
        "equals",
        ledger_section_count(MARK_LEFT),
    )
    g(
        "法⑦-4",
        "三向对照的不一致项必须空表（md／sqlite 终态／call_log 三处同源）",
        "fix_r5_ledger.json",
        "three_way_bad",
        "equals",
        [],
    )
    g(
        "法⑦-5",
        "账本条目总数与本驱动现读数一致（追加段落不新增也不删除条目）",
        "fix_r5_ledger.json",
        "ledger_total",
        "equals",
        ledger_entry_total(),
    )
    g(
        "法⑦-6",
        "三向对照表条数 ≥ 12（每单都要有 md+sqlite+call_log 三栏）",
        "fix_r5_ledger.json",
        "three_way",
        "min",
        12,
    )
    g(
        "法⑦-7",
        "影响面要裁决的档数在闭环件里点名（impact_adjudication 在场）",
        "fix_r5_ledger.json",
        "impact_adjudication",
        "truthy",
        True,
    )
    g(
        "法⑦-8",
        "逐单驱动表条数 ≥ 12（claim→execute→submit→verify 的每一步都留了回包）",
        "fix_r5_ledger.json",
        "rows",
        "min",
        12,
    )
    g(
        "法⑦-9",
        "留 OPEN 的单数 ≥ 5（入账未修是合法终态，但必须是算出来的）",
        "fix_r5_ledger.json",
        "leftover_len",
        "min",
        5,
    )

    # ── 法⑧：驱动面与顺序自证
    g(
        "法⑧-1",
        "亲笔脚本硬错必须为 0（E9/F821/F7/F63/F841/W605）",
        "fix_r5_drivers_lint.json",
        "hard_violations",
        "equals",
        [],
    )
    g(
        "法⑧-2",
        f"软账不得高于上一环实测的那个数（{node(prev_ln, 'soft_total')}）",
        "fix_r5_drivers_lint.json",
        "soft_total",
        "equals",
        node(prev_ln, "soft_total") if prev_ln.get("soft_total") is not None else IMPOSSIBLE,
    )
    g(
        "法⑧-3",
        "扫描条数 = 本驱动 glob 到的 fix_r5_*.py 数（不挑好跑的扫）",
        "fix_r5_drivers_lint.json",
        "drivers_scanned",
        "min",
        drivers_scanned_here(),
    )
    g(
        "法⑧-4",
        "注入对照必须被抓到（坏例没被抓= lint 是装饰）",
        "fix_r5_drivers_lint.json",
        "canary",
        "truthy",
        True,
    )
    g(
        "法⑧-5",
        "call_log 按号段现数的本环行数 ≥ 17",
        "fix_r5_calllog_tally.json",
        "stages.T0r110.rows",
        "min",
        17,
    )
    g(
        "法⑧-6",
        "不存在号段的对照必须数出 0 行（过滤器不恒真）",
        "fix_r5_calllog_tally.json",
        "control_absent_prefix_rows",
        "equals",
        0,
    )
    g(
        "法⑧-7",
        "环标签那档 0 行时必须由根描述指纹档补上（两档不许同时为空）",
        "fix_r5_calllog_tally.json",
        "fingerprint_channel.rows",
        "min",
        2,
    )
    g(
        "法⑧-8",
        "规格点名工具的实际承担者逐条给数（0 也要是数出来的 0）",
        "fix_r5_calllog_tally.json",
        "spec_named_carriers",
        "truthy",
        True,
    )
    g(
        "法⑧-9",
        "call_log 工具本轮真打过且回包看得到本环号段",
        "fix_r5_calllog_tally.json",
        "call_log_tool_probe.rows_containing_stage",
        "min",
        17,
    )
    g(
        "法⑧-10",
        "本 build 里被点名的工具是否存在，逐条给数（工具名不存在≠能力没开）",
        "fix_r5_calllog_tally.json",
        "named_tools_in_this_build",
        "truthy",
        True,
    )

    # ── needle 严口径（报告引用的每个键名都要是被引件里的真键名）
    g(
        "⑫-1",
        "needle 条数 = 计划里 8 法声明的 artifacts 总数（逐条不是手数）",
        "fix_r5_needles.json",
        "real_key_len",
        "equals",
        sum(len(law["artifacts"]) for law in PLAN["laws"]),
    )
    g(
        "⑫-2",
        "扫描时不存在「件还没跑」的档（pending 必须空表）",
        "fix_r5_needles.json",
        "pending_artifacts",
        "equals",
        [],
    )
    g(
        "⑫-3",
        "前缀式 needle 的反例必须被严口径拒掉（否则这条规则是假的）",
        "fix_r5_needles.json",
        "canary",
        "truthy",
        True,
    )

    # ── 车道回执（派单半径与交付面要对得上）
    g(
        "⑬-1",
        "车道数 ≥ 5（每道一个文件半径，交付面逐道留回执）",
        "r5_fix_lanes.json",
        "lanes",
        "min",
        5,
    )
    g(
        "⑬-2",
        "每条车道都要写状态与理由（跑死也要逐字写原因，不许留空栏）",
        "r5_fix_lanes.json",
        "lanes",
        "min",
        measured("fix_r5_rc.json", "lane_receipts", 5),
    )

    footer_bits = [
        ("root", ROOT_TASK),
        ("marker", "[selfdrive-fix]"),
        ("laws", len(PLAN["laws"])),
        ("planned_ids", ic.get("planned_ids")),
        ("cards_total", ic.get("cards_total")),
        ("legacy_open", ic.get("legacy_open_ids")),
        ("split_columns", ic.get("split_columns")),
        ("locked", lk.get("locked_ids")),
        ("lock_red_before", lk.get("lock_red_before")),
        ("lock_green_after", lk.get("lock_green_after")),
        ("lock_nodes", lk.get("lock_nodes_total")),
        ("locks_missing", lk.get("locks_missing")),
        ("change_points", rc.get("change_points")),
        ("merged_root_causes", rc.get("merged_root_cause_len")),
        ("symbols", rc.get("symbols_referenced")),
        ("files_this_ring", sorted(node(rc, "files_this_ring") or {})),
        ("product_files_without_card", rc.get("product_files_without_card")),
        ("unfixed_claimed", rc.get("unfixed_claimed")),
        ("matrix_rows", rv.get("matrix_rows")),
        ("revert_red", rv.get("revert_red_ids")),
        ("sha", f"{rv.get('sha_restored')}/{rv.get('sha_files_total')}"),
        ("bearing", node(rv, "extras.bearing")),
        ("unborne", node(rv, "extras.unborne_files")),
        ("git_product_files", git_product_files()),
        ("corpus", im.get("corpus_total")),
        ("new_rejections", im.get("new_rejections_len")),
        ("new_acceptances", im.get("new_acceptances_len")),
        ("shape_changed", im.get("shape_changed_len")),
        ("api_surface", im.get("api_surface")),
        ("pytest", node(bs, "pytest.passed")),
        ("collect", node(bs, "collect.nodeids")),
        ("suite", node(bs, "suite.fields")),
        ("e2e", node(bs, "e2e.fields")),
        ("floors", bs.get("floors")),
        ("floors_source", bs.get("floors_source")),
        ("head", node(bs, "git.head")),
        ("staged", node(bs, "git.staged")),
        ("radius", {k: node(bs, f"radius.{k}") for k in ("forbidden_total", "allowed_touched")}),
        ("closed", lg.get("closed_ids")),
        ("fixed_sections", lg.get("fixed_sections")),
        ("not_fixed", lg.get("not_fixed_sections")),
        ("three_way_bad", lg.get("three_way_bad")),
        ("hard", ln.get("hard_violations")),
        ("soft", f"{ln.get('soft_total')}<=前环 {node(prev_ln, 'soft_total')}"),
        ("tally_rows", node(tl, "stages.T0r110.rows")),
        ("fingerprint_rows", node(tl, "fingerprint_channel.rows")),
        ("needles", f"{nd.get('real_key_len')}/{nd.get('checked_len')}"),
        ("generated_at", bs.get("finished_at_utc")),
    ]
    footer = "；".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in footer_bits)
    spec = {
        "name": "20260928.PENDING-NAME",
        "title": "R5-修复（fix）环节报告",
        "stage": "第 5 轮第 2 环（寻虫→修复→验证→打磨→推进）",
        "round": "R5",
        "root_task": ROOT_TASK,
        "assignee": PLAN["assignee"],
        "marker": "[selfdrive-fix]",
        "fragment": f"{D}/r5_fix_body.md",
        "artifacts": [f"{D}/{a}" for a in ARTIFACTS],
        "stale_ok": [],
        "closure_note": "收口链（16 叶 × omega 全链 + 8 支 + 根上卷）在本报告渲染之后才发，"
        "其结果与被拒原文一律进 .fist-loop-20260927/loop_progress.md，"
        "故此处不留 closure 位——留了就等于要求渲染时收口件已存在，"
        "而那会把顺序倒过来",
        "footer": footer,
        "gates": GATES,
        "gates_total": len(GATES),
        "closure": {
            "stage": f"{D}/close_r5_fix.out.json",
            "root": f"{D}/close_r5_fix_root.out.json",
        },
    }
    OUT.write_text(
        json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "gates": len(GATES),
                "artifacts": len(spec["artifacts"]),
                "footer_keys": len(footer_bits),
                "out": OUT.name,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
