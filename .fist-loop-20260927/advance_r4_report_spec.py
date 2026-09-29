"""生成 R4-推进 的报告 spec（门禁表）。

门禁的取数原则与上一环一致：**每条都要能红**。
- 每个判据件配两道：`refuse` 逐字等于空表（件内自证一条都不许只数不判）＋ `self_checks` 条数下限
  （少了＝有人删了自证，这一格会红）；
- 每条法再配 2-4 道数值/形状门，needle 一律是被引件里的真键名；
- 还没跑出来的件（baselines / drivers_lint / self_audit / close_spec）用**语义下限**而不是拍的实测值，
  跑完后由自证件逐道解一遍，解不出即拒渲染。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = ".fist-loop-20260927"
OUT = HERE / "report_spec_r4_advance.json"
PLAN = json.loads((HERE / "spec_r4_advance.json").read_text(encoding="utf-8"))
ARTIFACTS = [
    "spec_r4_advance.json", "advance_r4_never.py", "advance_r4_never.json",
    "advance_r4_builtins.py", "advance_r4_builtins.json", "advance_r4_scope_face.py",
    "advance_r4_scope_face.json", "advance_r4_filed.py", "advance_r4_filed.json",
    "advance_r4_dormant.py", "advance_r4_dormant.json",
    "advance_r4_lock_plan.json",
    "advance_r4_locks.py", "advance_r4_locks.json", "advance_r4_codegen_diff.json",
    "advance_r4_corpus.json", "advance_r4_sweep.py", "advance_r4_baselines.py",
    "advance_r4_baselines.json", "advance_r4_irreversible.py", "advance_r4_irreversible.json",
    "advance_r4_drivers_lint.py", "advance_r4_drivers_lint.json",
    "advance_r4_calllog_tally.py", "advance_r4_calllog_tally.json",
    "advance_r4_self_audit.py", "advance_r4_self_audit.json",
    "advance_r4_close_spec.py", "close_r4_advance.json",
    "advance_r4_render_order.py",
    "advance_r4_gen_locks.py", "advance_r4_lib.py", "advance_r4_probes.py", "loop_kit.py",
]
EXISTING = {"advance_r4_never.json", "advance_r4_builtins.json", "advance_r4_scope_face.json",
            "advance_r4_dormant.json", "advance_r4_lock_plan.json",
            "advance_r4_filed.json", "advance_r4_locks.json", "advance_r4_codegen_diff.json",
            "advance_r4_corpus.json", "advance_r4_irreversible.json"}
KEYS_WITH_SELF_CHECKS = ["advance_r4_never.json", "advance_r4_builtins.json",
                         "advance_r4_scope_face.json", "advance_r4_dormant.json",
                         "advance_r4_filed.json",
                         "advance_r4_locks.json", "advance_r4_codegen_diff.json",
                         "advance_r4_corpus.json", "advance_r4_baselines.json",
                         "advance_r4_irreversible.json", "advance_r4_self_audit.json",
                         "close_r4_advance.json"]
FLOORS = {"advance_r4_baselines.json": 5, "advance_r4_self_audit.json": 6,
          "advance_r4_dormant.json": 12, "close_r4_advance.json": 4}
GATES: list = []


def g(label, claim, artifact, path, kind, value) -> None:
    row = {"label": label, "claim": claim, "artifact": f"{D}/{artifact}", "path": path}
    row[kind] = value
    GATES.append(row)


def measured(name: str, path: str, default: int) -> int:
    p = HERE / name
    if not p.exists():
        return default
    node = json.loads(p.read_text(encoding="utf-8"))
    for part in path.split("."):
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return default
    return len(node) if isinstance(node, (list, dict, str)) else int(node)


def main() -> int:
    n = 0
    for name in KEYS_WITH_SELF_CHECKS:
        n += 1
        g(f"①-{n}", f"`{name}` 的 refuse 必须逐字为空表（件内每条自证都判过）",
          name, "refuse", "equals", [])
        n += 1
        g(f"①-{n}", f"`{name}` 的 self_checks 条数不得少于下限（删自证会红）",
          name, "self_checks", "min", measured(name, "self_checks", FLOORS.get(name, 4)))
        n += 1
        g(f"①-{n}", f"`{name}` 必须带 started 戳（同名旧件冒充本轮新跑的那类失效）",
          name, "started", "min", 12)

    # 法①
    g("②-1", "法①：Never 夹具两棵树对跑，条数就是计划里那 5 条",
      "advance_r4_never.json", "cases", "min", measured("advance_r4_never.json", "cases", 5))
    g("②-2", "法①：canary 三格（放行新名 / 不放行任意名 / 红只来自名称表）",
      "advance_r4_never.json", "canary", "min", 3)
    g("②-3", "法①：被改的产品文件逐档带 before/after sha（是哪两档由 ⑦-8 的等值门钉）",
      "advance_r4_never.json", "edited_files", "min", 2)
    g("②-4", "法①：文档工作例逐字进件（不是复述）",
      "advance_r4_never.json", "doc_quote", "min", 80)
    # 法②
    g("③-1", "法②：放行的三个名字逐个点名",
      "advance_r4_builtins.json", "added", "min", 3)
    g("③-2", "法②：未放行的六个内建名逐个点名（半径不外溢）",
      "advance_r4_builtins.json", "not_added", "min", 6)
    g("③-3", "法②：声明面引用行是量出来的，三条各带实测行号与原文",
      "advance_r4_builtins.json", "doc_evidence", "min", 3)
    g("③-4", "法②：canary 五格（含「未声明名在冻结语料里 0 处调用点」）",
      "advance_r4_builtins.json", "canary", "min", 5)
    # 法②的后果件（放行 open 激活休眠测试 ⇒ 指挥官裁决按声明面改测试期望）
    g("③-5", "法②后果：激活方向两格必须相反（改前 fail / 改后 success）",
      "advance_r4_dormant.json", "canary.activation_direction_differs", "equals", True)
    g("③-6", "法②后果：声明面引文两处（SYNTAX/14 与 SYNTAX/04）逐字进件",
      "advance_r4_dormant.json", "doc_basis", "min", 2)
    g("③-7", "法②后果：4 档 defer 形状实测，钉住的多出口形状号与清理次数如实记录",
      "advance_r4_dormant.json", "shapes", "min", 4)
    g("③-8", "法②后果：改后的 test_defer_statement 函数体逐字留档（不是转述）",
      "advance_r4_dormant.json", "test_patch.body_after", "min", 200)
    g("③-9", "法②后果：同款休眠守卫现存 7 处逐条点名（本环只动被激活的那一条）",
      "advance_r4_dormant.json", "vacuous_guards.count", "equals", 7)
    g("③-10", "法②后果：canary 八格（反例必被抓、切片变窄、守卫扫描不上注释的当）",
      "advance_r4_dormant.json", "canary", "min", 8)
    # 法③
    g("④-1", "法③：12 条复合赋值全部按文档自己的等价式判过",
      "advance_r4_scope_face.json", "augmented_matrix", "min", 12)
    g("④-2", "法③：二元/一元表达式面 10 条",
      "advance_r4_scope_face.json", "binary_matrix", "min", 10)
    g("④-3", "法③：半径外形状逐条给去向（挂账表非空且不许漏项）",
      "advance_r4_scope_face.json", "adjudication_queue", "min",
      measured("advance_r4_scope_face.json", "adjudication_queue", 8))
    g("④-4", "法③：静默产错码集合与钉住的名单同为空/同为那份名单",
      "advance_r4_scope_face.json", "silent_wrong", "equals", ["^="])
    g("④-5", "法③：被响亮拒绝的声明形状逐字点名",
      "advance_r4_scope_face.json", "declared_rejected", "equals",
      sorted(["&=", "**=", "^", "~", "|="]))
    g("④-6", "法③：四张卡真入账且号连续（账本最大号前后各记一次）",
      "advance_r4_filed.json", "filed", "min", 4)
    g("④-7", "法③：sqlite bug 任务增量与卡数同数",
      "advance_r4_filed.json", "sqlite_bug_tasks_after", "min", 70)
    g("④-8", "法③：判据件钉住的卡号全部落在实际账号里",
      "advance_r4_filed.json", "pinned_card_ids", "min", 4)
    # 法④
    g("⑤-1", "法④：新锁在改前码档必须红（红点数取下限=plan 名单长度）",
      "advance_r4_locks.json", "lane_prefix_code.red_ids", "min",
      measured("advance_r4_lock_plan.json", "prefix_red_ids", 8))
    g("⑤-1b", "法④：改前红点名单要逐字等于 plan（两份来源对不上就红）",
      "advance_r4_locks.json", "canary.red_list_exact_match", "equals", True)
    g("⑤-1c", "法④：锁条数要等于生成器 plan 的 expected_tests（两份来源互验，不手打）",
      "advance_r4_locks.json", "expected_tests", "equals",
      measured("advance_r4_lock_plan.json", "expected_tests", 26))
    g("⑤-2", "法④：工作区档零失败", "advance_r4_locks.json", "lane_work.failed", "equals", 0)
    g("⑤-3", "法④：两棵树的 type_checker sha 不同（身份探针）",
      "advance_r4_locks.json", "identity.work_type_checker_sha", "min", 12)
    g("⑤-4", "法④：改前档的 type_checker sha 另记一份",
      "advance_r4_locks.json", "identity.snap_type_checker_sha", "min", 12)
    g("⑤-5", "法④：收集地板 = 上一环实测 + 本环新增锁数（取全量件反解出的 floors.collect）",
      "advance_r4_locks.json", "collect_after_locks", "min",
      measured("advance_r4_baselines.json", "floors.collect", 1996))
    # 法⑤⑥（同一趟扫描）
    g("⑥-1", "法⑤：77 档语料两态产物逐字相同的档数达全集",
      "advance_r4_codegen_diff.json", "all_textual_identical", "min", 77)
    g("⑥-2", "法⑤：无理解释的产物差异必须为空表",
      "advance_r4_codegen_diff.json", "differing_unjustified", "equals", [])
    g("⑥-3", "法⑥：语料扫描档数达上一环基线 77",
      "advance_r4_corpus.json", "samples_scanned", "min", 77)
    g("⑥-4", "法⑥：新增诊断行的文件表必须为空",
      "advance_r4_corpus.json", "files_with_new_errors", "equals", [])
    g("⑥-5", "法⑥：两支见证夹具在位（尺子看得见被测形状）",
      "advance_r4_corpus.json", "witnesses", "min", 2)
    g("⑥-6", "法⑥：诊断「变少」的文件表也为空（本环没修产品语义，不该有东西变好）",
      "advance_r4_corpus.json", "files_with_errors_gone", "equals", [])
    # 法⑦
    g("⑦-1", "法⑦：pytest 失败数为 0", "advance_r4_baselines.json",
      "systems.pytest.failed", "equals", 0)
    g("⑦-2", "法⑦：pytest 错误数为 0", "advance_r4_baselines.json",
      "systems.pytest.errors", "equals", 0)
    g("⑦-3", "法⑦：pytest 通过数达地板（地板由件反解，不手打）",
      "advance_r4_baselines.json", "systems.pytest.passed", "min",
      measured("advance_r4_baselines.json", "floors.pytest", 1996))
    g("⑦-4", "法⑦：收集数与跑完的「过+红+错」同为地板之上",
      "advance_r4_baselines.json", "systems.collect.nodeids", "min",
      measured("advance_r4_baselines.json", "floors.collect", 1996))
    g("⑦-5", "法⑦：自研套件 47 条", "advance_r4_baselines.json",
      "systems.suite.fields.Total", "min", 47)
    g("⑦-6", "法⑦：e2e golden PASS 达地板", "advance_r4_baselines.json",
      "systems.e2e.PASS", "min", 25)
    g("⑦-7", "法⑦：冻结面 43 个 sha 变更表必须为空",
      "advance_r4_baselines.json", "frozen_changed", "equals", [])
    g("⑦-8", "法⑦：半径按 mtime 归因只到两档分析器",
      "advance_r4_baselines.json", "radius.product_by_mtime_this_ring", "equals",
      ["cypyc/analyzer/scope_analyzer.py", "cypyc/analyzer/type_checker.py"])
    g("⑦-9", "法⑦：HEAD 未漂（本轮没有 commit）",
      "advance_r4_baselines.json", "git.head", "equals", "17d68b4")
    g("⑦-10", "法⑦：暂存区 0 行", "advance_r4_baselines.json", "git.staged", "equals", 0)
    g("⑦-11", "法⑦：三套体系同刻为绿", "advance_r4_baselines.json",
      "three_systems_green", "truthy", True)
    g("⑦-11b", "法⑦：冻结面脏行里落在本环窗口内的必须为空", "advance_r4_baselines.json",
      "frozen_dirt_in_ring", "equals", [])
    g("⑦-11c", "法⑦：冻结面归因尺子两侧都会动（刚写的行被抓、loop 前的行被放）",
      "advance_r4_baselines.json", "canary", "min", 6)
    g("⑦-11d", "法⑦：每条冻结面脏行都要有解释（无解释表为空）", "advance_r4_baselines.json",
      "frozen_unexplained", "equals", [])
    g("⑦-12", "法⑦：驱动件硬错为 0（只数不拦＝装饰）",
      "advance_r4_drivers_lint.json", "hard_violations", "equals", 0)
    g("⑦-13", "法⑦：驱动件软账不高于上一环基线",
      "advance_r4_drivers_lint.json", "soft_total", "equals", 0)
    g("⑦-14", "法⑦：lint 清单非空且带逐文件 mtime 留档",
      "advance_r4_drivers_lint.json", "detail", "min", 10)
    g("⑦-15", "法⑦：合成违例必被抓（lint 口径的自证）",
      "advance_r4_drivers_lint.json", "canary.bad_caught", "min", 1)
    g("⑦-16", "法⑦：docs 面按 mtime 数到 0（推进环不动文档，白名单为空就是判据）",
      "advance_r4_baselines.json", "radius.docs", "equals", [])
    # 法⑧
    g("⑧-1", "法⑧：账本面无毁灭型工具", "advance_r4_irreversible.json",
      "verdict.destructive_tools", "equals", [])
    g("⑧-2", "法⑧：archive 只允许本环号段", "advance_r4_irreversible.json",
      "verdict.foreign_archive_targets", "equals", [])
    g("⑧-3", "法⑧：产品面无删除/改名", "advance_r4_irreversible.json",
      "product_bad_status", "equals", [])
    g("⑧-4", "法⑧：本环未跟踪新增产品文件为空（既往遗留照列不拒判）",
      "advance_r4_irreversible.json", "product_untracked_new", "equals", [])
    g("⑧-5", "法⑧：检测器三条对照全成立", "advance_r4_irreversible.json", "canary", "min", 3)
    g("⑧-6", "法⑧：archive 目标面为空（一次也没对别人号段动手）",
      "advance_r4_irreversible.json", "archive_targets", "equals", [])
    # 收口与账
    g("⑨-1", "每条法都至少留下一行带本环前缀的调用（建树/派单/laya 都算，发单前必为 0）",
      "advance_r4_calllog_tally.json", "rows_T0r93", "min", len(PLAN["laws"]))
    g("⑨-2", "全库行数作为分母要看得见（0 分母上的「零被拒」没有意义）",
      "advance_r4_calllog_tally.json", "total_call_log_rows", "min", 500)
    g("⑨-3", "不存在的对照前缀必须数出 0 行（过滤器不恒真）",
      "advance_r4_calllog_tally.json", "control_absent_prefix_rows", "equals", 0)
    g("⑨-4", "omega 链三工具逐条有计数（不是「已开启」一句话）",
      "advance_r4_calllog_tally.json", "omega_chain_by_tool", "min", 3)
    g("⑨-5", "laya/issue_up/call_log 的实际承担工具逐条给数",
      "advance_r4_calllog_tally.json", "spec_named_carriers", "min", 3)
    g("⑨-6", "缺陷入账在 bugs 树里有行（按机制签名反解）",
      "advance_r4_calllog_tally.json", "bug_intake_rows", "min", 2)
    g("⑨-7", "整条循环的根任务逐根点名（R1..R4 已完成的根单都在）",
      "advance_r4_calllog_tally.json", "loop_roots", "min", 8)
    g("⑨-8", "被拒原文逐字分组不许漏行（分组键在件里点名）",
      "advance_r4_calllog_tally.json", "grouped_by", "min", 10)

    for i, law in enumerate(PLAN["laws"], 1):
        art, key = law["artifacts"][0][0].split("/")[-1], law["artifacts"][0][1]
        g(f"⑩-{i}", f"计划法{i}的 needle「{key}」必须是 {art} 里的真键名",
          art, key, "min", 1)
    spec = {
        "name": "20260928.13.20.00", "title": "R4-推进（advance）环节报告",
        "stage": "第 4 轮第 5 环（寻虫→修复→验证→打磨→推进）", "round": "R4",
        "root_task": "T0r93", "assignee": "cypy-advancer",
        "marker": "[selfdrive-advance]",
        "fragment": f"{D}/r4_advance_body.md",
        "artifacts": [f"{D}/{a}" for a in ARTIFACTS],
        "stale_ok": [],
        "closure_note": "收口链（16 叶 × omega 全链 + 8 支 + 根上卷）在本报告渲染之后才发，"
                        "其结果与被拒原文一律进 .fist-loop-20260927/loop_progress.md，"
                        "故此处不留 closure 位——留了就等于要求渲染时收口件已存在，"
                        "而那会把顺序倒过来",
        "footer": "radius=产品两档分析器 / 冻结 0 / docs 0 / tests 1 新锁；"
                  "carry=半径外 8 条挂账 + BUG-74/75 两张新卡 + 语料与产物面同趟扫描",
        "gates": GATES,
    }
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"gates": len(GATES), "artifacts": len(spec["artifacts"]),
                      "out": OUT.name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
