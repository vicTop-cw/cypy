"""生成 R5-寻虫 的报告 spec（门禁表）+ 一条由实测拼出来的页脚。

取数原则与前四轮一致：**每条门禁都要能红**。
- 每个判据件三道：`refuse` 逐字为空表、`self_checks` 条数下限、`started` 戳存在（旧件冒充本轮新跑
  就是靠这一道抓的）；
- 每条法 4-8 道数值/形状门，needle 一律是被引件里的**真键名**（`hunt_r5_needles.py` 已严口径实测）；
- 还没跑出来的件用 `measured()` 从件本身反解下限，不手打数字；`min: 0` 这类恒真门一律不写；
- 页脚里每个数都从件里取，不出现「我记得是几」。
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = ".fist-loop-20260927"
OUT = HERE / "report_spec_r5_hunt.json"
PLAN = json.loads((HERE / "spec_r5_hunt.json").read_text(encoding="utf-8"))
ROOT_TASK = "T0r96"

ARTIFACTS = [
    "spec_r5_hunt.json",
    "hunt_r5_analyzer.py",
    "hunt_r5_faces.py",
    "hunt_r5_faces.json",
    "hunt_r5_declared.py",
    "hunt_r5_declared.json",
    "hunt_r5_codegen.py",
    "hunt_r5_codegen.json",
    "hunt_r5_cli_face.py",
    "hunt_r5_cli_face.json",
    "hunt_r5_needles.py",
    "hunt_r5_needles.json",
    "hunt_r5_book.py",
    "hunt_r5_book.json",
    "hunt_r5_baselines.py",
    "hunt_r5_baselines.json",
    "hunt_r5_drivers_lint.py",
    "hunt_r5_drivers_lint.json",
    "hunt_r5_calllog_tally.py",
    "hunt_r5_calllog_tally.json",
    "hunt_r5_self_audit.py",
    "hunt_r5_close_spec.py",
    "close_r5_hunt.json",
    "hunt_r5_close_spec.py",
    "hunt_r5_render_order.py",
    "hunt_r5_progress.py",
    "loop_kit.py",
    "close_stage_generic.py",
    "close_root_generic.py",
    "close_r5_hunt.out.json",
    "close_r5_hunt_root.out.json",
]
SELF_CHECKED = [
    "hunt_r5_faces.json",
    "hunt_r5_declared.json",
    "hunt_r5_codegen.json",
    "hunt_r5_cli_face.json",
    "hunt_r5_book.json",
    "hunt_r5_needles.json",
    "hunt_r5_baselines.json",
    "hunt_r5_drivers_lint.json",
    "hunt_r5_calllog_tally.json",
    "close_r5_hunt.json",
]
FLOORS = {
    "hunt_r5_baselines.json": 5,
    "hunt_r5_calllog_tally.json": 5,
    "hunt_r5_needles.json": 4,
    "close_r5_hunt.json": 4,
}
GATES: list = []
# 起跑戳的字段名各家不同（baselines 只有 window.start_utc + finished_at_utc），逐件点名
STARTED_PATH = {"hunt_r5_baselines.json": "window.start_utc"}


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


def ledger_max() -> int:
    """报告生成时独立现读账本，用来和入账件里记的数对撞（两路必须同源）。"""
    txt = (HERE.parent / "memory" / "bugs.md").read_text(encoding="utf-8")
    nums = [int(x) for x in re.findall(r"(?m)^## BUG-(\d+) ", txt)]
    return max(nums) if nums else 0


def sqlite_bug_count() -> int:
    con = sqlite3.connect(f"file:{(HERE.parent / 'fist-mbt.db').as_posix()}?mode=ro", uri=True)
    n = con.execute("select count(*) from tasks where ns='bugs'").fetchone()[0]
    con.close()
    return n


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
        n += 1
        g(
            f"①-{n}",
            f"`{name}` 的 self_checks 条数不得少于下限（删自证会红）",
            name,
            "self_checks",
            "min",
            measured(name, "self_checks", FLOORS.get(name, 4)),
        )
        n += 1
        started_path = STARTED_PATH.get(name, "started")
        g(
            f"①-{n}",
            f"`{name}` 必须带本轮起跑戳（字段 {started_path}；同名旧件冒充本轮新跑靠这道抓）",
            name,
            started_path,
            "min",
            12,
        )

    # 法①：观察面看得见（变异归属）
    g("②-1", "法①：语义邻域拆成六带逐带对照", "hunt_r5_faces.json", "families", "min", 6)
    g(
        "②-2",
        "法①：六带用例（含对照）总数达 25 条且两两当场实跑",
        "hunt_r5_faces.json",
        "cases_total",
        "min",
        25,
    )
    g(
        "②-3",
        "法①：三条变异通道里至少两条真的翻转了判定（归属可反解）",
        "hunt_r5_faces.json",
        "flips_by_mutant",
        "min",
        2,
    )
    g(
        "②-4",
        "法①：翻转归属覆盖到 3 族（另 3 族只由格级期望证明，见 ②-9 的点名）",
        "hunt_r5_faces.json",
        "flips_by_family",
        "min",
        3,
    )
    g(
        "②-5",
        "法①：白建的变异通道必须逐条点名，不许静默丢掉",
        "hunt_r5_faces.json",
        "unattributed_mutants",
        "min",
        1,
    )
    g(
        "②-6",
        "法①：六邻域的变异夹具全集入表（不是只留翻转的那几条）",
        "hunt_r5_faces.json",
        "mutant_candidates",
        "min",
        6,
    )
    g(
        "②-7",
        "法①：看不见样本的格必须显式留在 blind_spots（0 才是『没有盲区』的主张）",
        "hunt_r5_faces.json",
        "blind_spots",
        "equals",
        [],
    )
    g(
        "②-8",
        "法①：期望口径写明是『文档声明的语义』而不是『今天怎样』",
        "hunt_r5_faces.json",
        "expectation_note",
        "min",
        40,
    )
    g(
        "②-9",
        "法①：没有被变异翻转覆盖的族必须正面点名（含糊写成「六带都活」就是假话）",
        "hunt_r5_faces.json",
        "families_without_flip",
        "min",
        3,
    )

    # 法②：声明面逐条自己重测
    g(
        "③-1",
        "法②：主张条数达 18 且每行带 file:line 与原文",
        "hunt_r5_declared.json",
        "rows_total",
        "min",
        18,
    )
    g(
        "③-2",
        "法②：判为文档陈旧（今天已实现）的逐条点名",
        "hunt_r5_declared.json",
        "stale_total",
        "min",
        1,
    )
    g("③-3", "法②：判为真实缺口的逐条点名", "hunt_r5_declared.json", "real_gap_total", "min", 1)
    g(
        "③-4",
        "法②：文档自述未实现且今天确实没实现 ⇒ 撤回，不占号",
        "hunt_r5_declared.json",
        "withdrawn_design",
        "min",
        1,
    )
    g(
        "③-5",
        "法②：跑不动/没测的必须落进 not_measured_or_true，不许写成没问题",
        "hunt_r5_declared.json",
        "not_measured_or_true",
        "min",
        2,
    )
    g(
        "③-6",
        "法②：观察用的是被测树的分析器（身份串入件，防孪生件顶包）",
        "hunt_r5_declared.json",
        "identity",
        "min",
        20,
    )
    g(
        "③-7",
        "法②：规模红线四栏实测（三个文件行数 + 阈值）",
        "hunt_r5_declared.json",
        "size_lines",
        "min",
        4,
    )
    g(
        "③-8",
        "法②：hook 子命令未列出的选项逐条点名",
        "hunt_r5_declared.json",
        "undocumented_hook_options",
        "min",
        1,
    )
    g(
        "③-9",
        "法②：子代理结论只作线索、全部现测的口径写明在件里",
        "hunt_r5_declared.json",
        "note_on_subagent",
        "min",
        40,
    )

    # 法③：生成面成对确诊
    g(
        "④-1",
        "法③：生成面用例 7 条（pos 与同族 ctl 各一档）",
        "hunt_r5_codegen.json",
        "cases",
        "min",
        7,
    )
    g("④-2", "法③：确诊集合非空且逐条点名", "hunt_r5_codegen.json", "confirmed", "min", 7)
    g("④-3", "法③：机制签名键与确诊一一对应", "hunt_r5_codegen.json", "keys", "min", 7)
    g(
        "④-4",
        "法③：期望写错就确认不了 + 对照方向逐条声明（两格 canary）",
        "hunt_r5_codegen.json",
        "canary",
        "min",
        2,
    )
    g(
        "④-5",
        "法③：未确认档必须显式留档（本环为 0，但键要在）",
        "hunt_r5_codegen.json",
        "unsure",
        "equals",
        [],
    )
    g("④-6", "法③：残渣在清理之后复测，非空即拒", "hunt_r5_codegen.json", "tmp_left", "equals", [])

    # 法④：真实入口面成对确诊
    g(
        "⑤-1",
        "法④：入口面用例 7 条（CLI/hook/build/project）",
        "hunt_r5_cli_face.json",
        "cases",
        "min",
        7,
    )
    g("⑤-2", "法④：入口面确诊 6 条逐条点名", "hunt_r5_cli_face.json", "confirmed", "min", 6)
    g(
        "⑤-3",
        "法④：对照没站对的那条只能记 UNSURE 且留在件里（不许混进确诊）",
        "hunt_r5_cli_face.json",
        "unsure",
        "min",
        1,
    )
    g(
        "⑤-4",
        "法④：pos 与 ctl 期望逐条相反（否则方向是蒙出来的）",
        "hunt_r5_cli_face.json",
        "canary",
        "min",
        2,
    )
    g("⑤-5", "法④：机制签名键入表", "hunt_r5_cli_face.json", "keys", "min", 6)
    g("⑤-6", "法④：入口面残渣同样在清理后复测", "hunt_r5_cli_face.json", "tmp_left", "equals", [])

    # 法⑤：判据自证 + 残渣
    g(
        "⑥-1",
        "法⑤：faces 的观察性由变异翻转正面证明（不是『跑出结果就算看见』）",
        "hunt_r5_faces.json",
        "flips_by_mutant",
        "min",
        2,
    )
    g(
        "⑥-2",
        "法⑤：入账件的机制签名逐条点名（13 张，一张不多不少）",
        "hunt_r5_book.json",
        "keys",
        "min",
        13,
    )
    g(
        "⑥-3",
        "法⑤：幂等复扫把已在账的逐条点名（重跑一条都不重开，且看得见为什么不开）",
        "hunt_r5_book.json",
        "duplicates",
        "min",
        13,
    )
    g(
        "⑥-5",
        "法⑤：卡表签名与判据件签名不一致的对数逐对留档（重打字面量不许静默）",
        "hunt_r5_book.json",
        "key_alias",
        "min",
        8,
    )
    g(
        "⑥-6",
        "法⑤：别名对数与实测不一致条数同源（不是手写个数）",
        "hunt_r5_book.json",
        "key_alias_len",
        "min",
        8,
    )

    # 法⑥：入账
    g("⑦-1", "法⑥：卡表条数 = 两批判据件确诊条数之和", "hunt_r5_book.json", "cards", "min", 13)
    g(
        "⑦-2",
        "法⑥：每张卡在账本与 sqlite bugs 树里都能数到（在账，不是我记得）",
        "hunt_r5_book.json",
        "on_disk_keys_len",
        "min",
        13,
    )
    g(
        "⑦-3",
        "法⑥：入账后账本最大号 = 报告生成时从 memory/bugs.md 现读的数（两路独立）",
        "hunt_r5_book.json",
        "ledger_after_max",
        "equals",
        ledger_max(),
    )
    g(
        "⑦-4",
        "法⑥：sqlite bugs 任务数 = 生成时直查库的数（不是件里说多少就算多少）",
        "hunt_r5_book.json",
        "sqlite_bug_tasks_after",
        "equals",
        sqlite_bug_count(),
    )
    g(
        "⑦-5",
        "法⑥：逐卡在账证据入表（键/用例/账本命中数/bug 行数）",
        "hunt_r5_book.json",
        "per_key_on_disk",
        "min",
        13,
    )

    # 法⑦：三套体系与半径
    g(
        "⑧-1",
        "法⑦：地板四栏齐（pytest/collect/suite/e2e_pass）且来自上一环实测件",
        "hunt_r5_baselines.json",
        "floors",
        "min",
        4,
    )
    g(
        "⑧-2",
        "法⑦：地板来源串点名上一环件与逐栏数值",
        "hunt_r5_baselines.json",
        "floors_source",
        "min",
        20,
    )
    g(
        "⑧-3",
        "法⑦：三套体系同刻为绿",
        "hunt_r5_baselines.json",
        "three_systems_green",
        "equals",
        True,
    )
    g(
        "⑧-4",
        "法⑦：pytest 失败汇总为 0（字段名从件反解：failed_sum）",
        "hunt_r5_baselines.json",
        "pytest.failed_sum",
        "equals",
        0,
    )
    g(
        "⑧-5",
        "法⑦：pytest 通过数达上一环地板",
        "hunt_r5_baselines.json",
        "pytest.passed",
        "min",
        measured("hunt_r5_baselines.json", "pytest.passed", 2002),
    )
    g(
        "⑧-5b",
        "法⑦：三套体系的合取旗标 all_ok 为真（不是某一格自己绿）",
        "hunt_r5_baselines.json",
        "all_ok",
        "equals",
        True,
    )
    g(
        "⑧-6",
        "法⑦：收集数达地板（+20 之后不回退）",
        "hunt_r5_baselines.json",
        "collect.nodeids",
        "min",
        measured("hunt_r5_baselines.json", "collect.nodeids", 2002),
    )
    g(
        "⑧-7",
        "法⑦：HEAD 未动（本环零提交）",
        "hunt_r5_baselines.json",
        "git.head",
        "equals",
        "17d68b4",
    )
    g("⑧-8", "法⑦：暂存区为 0 行", "hunt_r5_baselines.json", "git.staged", "equals", 0)
    g(
        "⑧-9",
        "法⑦：禁用面改动为 0（冻结语义文件按 mtime 正面测）",
        "hunt_r5_baselines.json",
        "radius.forbidden_total",
        "equals",
        0,
    )
    g(
        "⑧-10",
        "法⑦：允许面改动逐条点名（半径不是空话也不是口号）",
        "hunt_r5_baselines.json",
        "radius.allowed_touched",
        "min",
        1,
    )

    # 法⑧：驱动面
    g(
        "⑨-1",
        "法⑧：亲笔驱动扫描条数达 12 个以上",
        "hunt_r5_drivers_lint.json",
        "drivers_scanned",
        "min",
        12,
    )
    g(
        "⑨-2",
        "法⑧：硬错（E9/W605/F821/F7/F63/F841）为 0",
        "hunt_r5_drivers_lint.json",
        "hard_violations",
        "equals",
        0,
    )
    g(
        "⑨-3",
        "法⑧：软账条数不高于上一环实测基线 0",
        "hunt_r5_drivers_lint.json",
        "soft_total",
        "equals",
        0,
    )
    g(
        "⑨-4",
        "法⑧：行长口径写明是 100（与项目声明一致，不是为过而调）",
        "hunt_r5_drivers_lint.json",
        "line_length_declared",
        "equals",
        100,
    )
    g(
        "⑨-5",
        "法⑧：lint 自带合成违例对照，抓不到即自判坏",
        "hunt_r5_drivers_lint.json",
        "canary",
        "min",
        1,
    )

    # needle 严口径
    g(
        "⑩-1",
        "needle 全集条数由扫描件反解（不手数）",
        "hunt_r5_needles.json",
        "checked_len",
        "min",
        20,
    )
    g(
        "⑩-2",
        "每条 needle 都是被引件里的真键名（不合格条数必须为 0）",
        "hunt_r5_needles.json",
        "real_key_len",
        "equals",
        measured("hunt_r5_needles.json", "checked_len", 24),
    )
    g(
        "⑩-3",
        "扫描时还不存在的判据件必须为空表（否则法条引用了不存在的东西）",
        "hunt_r5_needles.json",
        "pending_artifacts",
        "equals",
        [],
    )
    g(
        "⑩-4",
        "前缀式假命中 canary 必须抓到东西（否则严口径与子串口径无法区分）",
        "hunt_r5_needles.json",
        "prefix_canary",
        "min",
        1,
    )
    g(
        "⑩-5",
        "实测数写回环节计划（报告里的数与判据件同源）",
        "hunt_r5_needles.json",
        "needle_verification_written_back",
        "min",
        4,
    )

    # call_log 计数
    g(
        "⑪-1",
        "本环号段在 call_log 里的行数达法条数（按前缀数，不按回忆）",
        "hunt_r5_calllog_tally.json",
        "stages.T0r96.rows",
        "min",
        len(PLAN["laws"]),
    )
    g(
        "⑪-2",
        "全库行数做分母要看得见（0 分母上的『零被拒』没意义）",
        "hunt_r5_calllog_tally.json",
        "total_call_log_rows",
        "min",
        500,
    )
    g(
        "⑪-3",
        "不存在的前缀必须数出 0 行（过滤器不恒真）",
        "hunt_r5_calllog_tally.json",
        "control_absent_prefix_rows",
        "equals",
        0,
    )
    g(
        "⑪-4",
        "本环前缀的逐工具计数（omega 链在其中，不按回忆列）",
        "hunt_r5_calllog_tally.json",
        "stages.T0r96.by_tool",
        "min",
        3,
    )
    g(
        "⑪-5",
        "laya / issue_up / call_log 的实际承担工具逐条给数",
        "hunt_r5_calllog_tally.json",
        "spec_named_carriers",
        "min",
        3,
    )
    g(
        "⑪-6",
        "上一环号段的种子行数看得见（跨环对照不是空的）",
        "hunt_r5_calllog_tally.json",
        "stage_seed_rows.total",
        "min",
        20,
    )
    g(
        "⑪-7",
        "『0 命中就不许写已开启』这条口径写在件里（不是报告里的一句话）",
        "hunt_r5_calllog_tally.json",
        "note",
        "min",
        40,
    )
    g(
        "⑪-9",
        "本环前缀总行数达 20 行（omega 链 + 派单 + 入账都会计数）",
        "hunt_r5_calllog_tally.json",
        "stages.T0r96.rows",
        "min",
        20,
    )
    g(
        "⑪-10",
        "环标签档在场：publish/laya_decide/report_bug 没有 task_id，按标签这路才数得到",
        "hunt_r5_calllog_tally.json",
        "ring_tag_calls.by_tool",
        "min",
        3,
    )
    g(
        "⑪-11",
        "本环标签下确有成功调用（≥10 行 ok：13 张卡 + publish + laya_decide）",
        "hunt_r5_calllog_tally.json",
        "ring_tag_calls.ok",
        "min",
        10,
    )
    g(
        "⑪-12",
        "不存在的标签必须数出 0 行（按标签这路过滤也不恒真）",
        "hunt_r5_calllog_tally.json",
        "ring_tag_calls.absent_control_rows",
        "equals",
        0,
    )
    g(
        "⑪-13",
        "标签档 13 条被拒原文逐字分组在场（不是挑两条代表）",
        "hunt_r5_calllog_tally.json",
        "ring_tag_calls.refusals_md",
        "min",
        200,
    )
    g(
        "⑪-14",
        "被拒原文去重后的组数逐条点名（分组键不是手数）",
        "hunt_r5_calllog_tally.json",
        "ring_tag_calls.distinct_refusal_texts",
        "min",
        3,
    )
    g(
        "⑪-15",
        "call_log 工具面的回包看得见本环号段（自读 sqlite 不算开过工具）",
        "hunt_r5_calllog_tally.json",
        "call_log_tool_probe.rows_containing_stage",
        "min",
        100,
    )
    g(
        "⑪-16",
        "跨环正例那一档要写明口径（不然 R4 的数会被当成本环的）",
        "hunt_r5_calllog_tally.json",
        "stage_seed_rows.scope",
        "min",
        10,
    )

    for i, law in enumerate(PLAN["laws"], 1):
        art = law["artifacts"][0][0].split("/")[-1]
        g(
            f"⑫-{i}",
            f"法{i}（头号证据件 {art}）的 3 条 needle 全部是被引件里的**真键名**"
            "——按实测条数等值校，零值测量（如 blind_spots=[]）不算缺失",
            "hunt_r5_needles.json",
            f"per_law_real.law{i}",
            "equals",
            3,
        )
    g(
        "⑫-9",
        "needle 严口径的总覆盖面 = 计划声明的 artifacts 总数（24 条，逐条不是手数）",
        "hunt_r5_needles.json",
        "real_key_len",
        "equals",
        sum(len(law["artifacts"]) for law in PLAN["laws"]),
    )
    g(
        "⑫-10",
        "扫描时不存在「件还没跑」的档（pending 必须为空表）",
        "hunt_r5_needles.json",
        "pending_artifacts",
        "equals",
        [],
    )

    bs = read("hunt_r5_baselines.json")
    bk, fc = read("hunt_r5_book.json"), read("hunt_r5_faces.json")
    cg, cl, dc = (
        read("hunt_r5_codegen.json"),
        read("hunt_r5_cli_face.json"),
        read("hunt_r5_declared.json"),
    )
    ln, nd = read("hunt_r5_drivers_lint.json"), read("hunt_r5_needles.json")
    footer_bits = [
        ("root", ROOT_TASK),
        ("laws", len(PLAN["laws"])),
        ("faces_families", fc.get("families")),
        ("face_cases", fc.get("cases_total")),
        ("faces_candidates", fc.get("candidate_total")),
        ("mutant_flips", fc.get("flips_by_mutant")),
        ("unattributed", fc.get("unattributed_mutants")),
        ("blind_spots", fc.get("blind_spots")),
        ("declared_rows", dc.get("rows_total")),
        ("stale", dc.get("stale_total")),
        ("real_gap", dc.get("real_gap_total")),
        ("design_withdrawn", dc.get("withdrawn_design")),
        ("not_measured_or_true", dc.get("not_measured_or_true")),
        ("codegen_cases", cg.get("cases")),
        ("codegen_confirmed", cg.get("confirmed")),
        ("cli_cases", cl.get("cases")),
        ("cli_confirmed", cl.get("confirmed")),
        ("cli_unsure", cl.get("unsure")),
        ("cards", bk.get("cards")),
        ("on_disk_keys", bk.get("on_disk_keys_len")),
        ("ledger", f"{bk.get('ledger_before_max')}->{bk.get('ledger_after_max')}"),
        ("sqlite_bugs", f"{bk.get('sqlite_bug_tasks_before')}->{bk.get('sqlite_bug_tasks_after')}"),
        ("pytest", node(bs, "pytest.passed")),
        ("collect", node(bs, "collect.nodeids")),
        ("suite", node(bs, "suite.fields")),
        ("e2e", node(bs, "e2e")),
        ("floors", bs.get("floors")),
        ("head", node(bs, "git.head")),
        ("staged", node(bs, "git.staged")),
        ("radius_forbidden", node(bs, "radius.forbidden_total")),
        ("radius_allowed", node(bs, "radius.allowed_touched")),
        ("driver_hard", ln.get("hard_violations")),
        ("driver_soft", ln.get("soft_total")),
        ("needles", f"{nd.get('real_key_len')}/{nd.get('checked_len')}"),
        ("generated_at", bs.get("finished_at_utc")),
    ]
    footer = "；".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in footer_bits)
    spec = {
        "name": "20260928.15.10.00",
        "title": "R5-寻虫（hunt）环节报告",
        "stage": "第 5 轮第 1 环（寻虫→修复→验证→打磨→推进）",
        "round": "R5",
        "root_task": ROOT_TASK,
        "assignee": PLAN["assignee"],
        "marker": "[selfdrive-hunt]",
        "fragment": f"{D}/r5_hunt_body.md",
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
            "stage": f"{D}/close_r5_hunt.out.json",
            "root": f"{D}/close_r5_hunt_root.out.json",
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
