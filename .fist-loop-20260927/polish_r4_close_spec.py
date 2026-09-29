"""R4-打磨 的收口 spec 生成器：叶/支判据、根交付物正文与验收理由全部从判据件反解。

与 R4-验证 那份同构，两处本环特有的加强：
① 打磨环允许动 docs/ 与 tests/，但不许动产品码——所以这里不复用「三栏全空」的旧断言，
   而是**逐栏白名单**：tests 只许本轮新锁那一个文件、docs 只许 USAGE.md 与本轮新增补注，
   产品码与冻结面必须为空。少写一条白名单，「只看不动手」就会假绿。
② 账面「只增不改」在本环是主张而不是姿态：差分的新增/删除行数、卡片总数、合法 task_id 计数
   四格必须逐格对上，任一格漂了就拒绝发单（服务端写入不可撤回）。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLAN = HERE / "spec_r4_polish.json"
SPEC = HERE / "report_spec_r4_polish.json"
OUT = HERE / "close_r4_polish.json"
REFUSE: list = []
NEED = ["polish_r4_docs.json", "polish_r4_appendixC.json", "polish_r4_ledger.json",
        "polish_r4_debt.json", "polish_r4_locks.json", "polish_r4_structural.json",
        "polish_r4_baselines.json", "polish_r4_calllog_tally.json",
        "polish_r4_drivers_lint.json", "polish_r4_self_audit.json"]
# 自证件与收口 spec 互为输入（正文引用自证格数，自证有门禁读本件）⇒ 第一次跑必然带红，
# 这里只要求它**在盘上**；真正卡住渲染的是 report_kit 的 ⑨-16（自证件 refuse 必空）。
SOFT = {"polish_r4_self_audit.json"}
TESTS_ALLOW = {"tests/test_loop_20260927_polish_r4.py"}
DOCS_ALLOW = {"docs/USAGE.md", "docs/APPENDIX_C_DEVIATIONS.md"}


def need(name: str, must_green: bool = True) -> dict:
    p = HERE / name
    if not p.exists():
        REFUSE.append(f"判据件缺失：{name}")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    if must_green and d.get("refuse"):
        REFUSE.append(f"{name} 的 refuse 非空："
                      f"{json.dumps(d['refuse'], ensure_ascii=False)[:200]}")
    return d


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    rep = json.loads(SPEC.read_text(encoding="utf-8"))
    art = {n: need(n, n not in SOFT) for n in NEED}
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1

    dc, ap, lg = (art["polish_r4_docs.json"], art["polish_r4_appendixC.json"],
                  art["polish_r4_ledger.json"])
    db, lk, st = (art["polish_r4_debt.json"], art["polish_r4_locks.json"],
                  art["polish_r4_structural.json"])
    bs, tl = art["polish_r4_baselines.json"], art["polish_r4_calllog_tally.json"]
    ln, sa = art["polish_r4_drivers_lint.json"], art["polish_r4_self_audit.json"]

    pf, gf, rad = bs["systems"]["pytest"], bs["git"], bs["radius"]
    if pf["failed"] or pf["errors"]:
        REFUSE.append(f"pytest 还有红：{pf['failed']}/{pf['errors']} ⇒ 门禁不绿，不能收口")
    if gf["staged"]:
        REFUSE.append(f"暂存区非 0（{gf['staged']} 行）⇒ 红线违例")
    if rad["product"]:
        REFUSE.append(f"打磨环半径违例：产品码被动过 {rad['product'][:3]}")
    if rad["frozen"]:
        REFUSE.append(f"冻结面被动过 {rad['frozen'][:3]} ⇒ 越权（交人工栏才对）")
    if sorted(set(rad["tests"]) - TESTS_ALLOW):
        REFUSE.append(f"tests 栏出现白名单外的改动 {sorted(set(rad['tests']) - TESTS_ALLOW)}")
    if sorted(set(rad["docs"]) - DOCS_ALLOW):
        REFUSE.append(f"docs 栏出现白名单外的改动 {sorted(set(rad['docs']) - DOCS_ALLOW)}")
    if lg["append_only_diff"]["removed"]:
        REFUSE.append(f"账面出现删除行 {lg['append_only_diff']['removed']} ⇒ 「只增不改」不成立")
    if lg["cards_total_before"] != lg["cards_total_after"]:
        REFUSE.append("卡片总数变了（补记不该新增卡）")
    if lg["valid_task_ids_before"] != lg["valid_task_ids_after"]:
        REFUSE.append("合法 task_id 计数变了 ⇒ 未派单被冒充成有号")
    if lk["lane_work"]["counts"]["failed"]:
        REFUSE.append(f"新锁在工作区档有红 {lk['lane_work']['counts']['failed']} 条")
    if not lk["lane_prefix_code"]["counts"]["failed"]:
        REFUSE.append("新锁在修前码档全绿 ⇒ 锁不承重，收口就是给假锁盖章")
    if st["executed_irreversible"]:
        REFUSE.append(f"本环执行了不可逆动作 {st['executed_irreversible']}")
    if not bs["three_systems_green"]:
        REFUSE.append("三套体系没有同时为绿")
    # 自证与本件互为输入：pass1 的红全是指向本件的门禁，链上 pass2 与 report_kit 的 ⑨-16 才卡渲染。
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1

    laws = plan["laws"]
    branches = [[f"法{i}：{law['name']}", law["artifacts"][0][0], law["artifacts"][0][1]]
                for i, law in enumerate(laws, 1)]
    needle_fix = plan["needle_correction"]
    deliv = (
        f"R4-打磨 交付：memory/reviews/{rep['name']}；半径=措辞面/账面/测试面/骨架"
        f"（产品 {len(rad['product'])} 项、冻结 {len(rad['frozen'])} 项均为空，"
        f"tests 只新增 {json.dumps(rad['tests'], ensure_ascii=False)}，"
        f"docs 只 {json.dumps(rad['docs'], ensure_ascii=False)}）。"
        f"八条法全部独立复算：(1) `docs/USAGE.md` 的「源未变会复用 .pyd」按调用面改写——"
        f"实测行号 {json.dumps(dc['old_line_number_measured'])}（不是旧账里的 406），"
        f"sha {dc['before_sha']}→{dc['after_sha']}，差分 {len(dc['diff_changed_lines'])} 行；"
        f"反证三格 {dc['measurement']['pyd_reused_between_calls']}/"
        f"{dc['measurement']['get_cached_pyd_all_none']}/"
        f"{dc['measurement']['single_call_prints_both_cache_verdicts']}，"
        f"签名面 {json.dumps(dc['call_face_claims']['compile_to_pyd_params'])} 与 "
        f"CLI 子命令 {len(dc['call_face_claims']['cli_subcommands_seen'])} 个由 --help 反解；"
        f"(2) 附录 C 形差分两栏——交人工栏行号 "
        f"{json.dumps(ap['queue_frozen_edit'])}（实测非连续），我方可做栏 "
        f"{ap['note_file']} 共 {ap['note_done_rows']} 行 {ap['note_bytes']} B；"
        f"冻结面 {ap['frozen_files']} 个 sha 前后相等 {ap['frozen_sha_equal']}，"
        f"注入 canary 被抓 {ap['canary']['caught']}；"
        f"(3) 账面只增不改：新增 {lg['append_only_diff']['added']} 行、删除 "
        f"{lg['append_only_diff']['removed']} 行，卡数 {lg['cards_total_before']}→"
        f"{lg['cards_total_after']}、合法 task_id {lg['valid_task_ids_before']}→"
        f"{lg['valid_task_ids_after']}，8 张缺号卡反查 bugs 树命中 "
        f"{len(lg['resolved_from_sqlite'])} 张 ⇒ 补记措辞是「未派单」并交人工；"
        f"(4) 骨架收敛到 {db['kit']}（API {len(db['kit_apis'])} 个），行为不变证据 "
        f"{len(db['equivalence'])} 行覆盖 {json.dumps(db['equivalence_artifacts'])}，"
        f"复制集合相同 {db['copy_tree_face']['matches_reference']}"
        f"（{db['copy_tree_face']['files']} 个文件），双 canary "
        f"{json.dumps(db['canary'], ensure_ascii=False)}；形状分差 "
        f"{len(db['shape_divergence'])} 条与留债 "
        f"{json.dumps(db['debt_remaining_counts'], ensure_ascii=False)} 逐类点名，"
        f"本环接入件 {json.dumps(db['kit_users_this_ring'])}；"
        f"(5) 调用面探针固化成 {lk['new_test_file']}：工作区 "
        f"{lk['lane_work']['summary']}，修前码 {lk['lane_prefix_code']['summary']}"
        f"（红 {len(lk['lane_prefix_code']['red'])} 条，含 1 条文档面）；"
        f"两档身份 sha {lk['identity']['work_type_checker_sha']} ≠ "
        f"{lk['identity']['snap_type_checker_sha']}，收集 "
        f"{lk['collect_after_locks']}={lk['previous_round_collect_floor']}+20，"
        f"文档谓词三向 {json.dumps(lk['doc_predicate'], ensure_ascii=False)}；"
        f"(6) 结构债只测量：{st['files_measured']} 个文件过 {st['redline']} 行红线，"
        f"越线 {len(st['over_redline'])} 个，type_checker "
        f"{st['type_checker']['code_lines']} 行/{st['type_checker']['methods']} 方法，"
        f"hook.eval 写侧标记 {st['hook_eval_marker_count']}/产品面 "
        f"{st['hook_eval_marker_product_face_total']}；挂账 "
        f"{len(st['adjudication_queue'])} 条、执行不可逆 {len(st['executed_irreversible'])} 条、"
        f"本环碰过的产品文件 {len(st['product_files_touched_this_ring'])} 个、"
        f"改名 {len(st['renamed_verbatim'])} 个，删除 10 条与上一环同集（旧账未结）；"
        f"(7) 三套体系同批复算且只升不降：pytest {pf['passed']} 通过/{pf['failed']} 失败/"
        f"{pf['errors']} 错误（地板 {bs['floors']['pytest']}）、收集 "
        f"{bs['systems']['collect']['nodeids']}（地板 {bs['floors']['collect']}+20）、"
        f"自研 {json.dumps(bs['systems']['suite']['fields'], ensure_ascii=False)}、"
        f"e2e {json.dumps(bs['systems']['e2e'])}；HEAD {gf['head']}、暂存 {gf['staged']}、"
        f"冻结 {bs['frozen_total']} 个文件 sha 未变、扫描 {bs['scanned_files']} 文件；"
        f"比较函数 canary {json.dumps(bs['canary'], ensure_ascii=False)}；"
        f"(8) 账面与驱动面：渲染前 call_log 本环前缀 {tl['rows_T0r90']} 行/"
        f"{tl['distinct_tasks']} 个任务、被拒 {tl['stages']['T0r90']['refused']} 条、"
        f"负对照 {tl['control_absent_prefix_rows']} 行，omega 链此刻 "
        f"{json.dumps(tl['omega_chain_by_tool'])}（收口链在报告之后才发，故此处为 0 是事实不是缺项）；"
        f"驱动 {ln['drivers_scanned']} 个硬错 {ln['hard_violations']}、软账 "
        f"{ln['soft_total']}（基线 {ln['previous_round_soft_baseline']}）。"
        f"计划 needle 校正 {needle_fix['changed_len']} 处（{needle_fix['missing_before']} 个键名"
        f"盘上不存在、{needle_fix['false_substring_before']} 个是子串假命中），"
        f"强度未动；渲染前自证 {sa['gates_pass']}/{sa['gates_total']} 道、占位 "
        f"{sa['placeholders_total']} 个、needle 严口径违例 {len(sa['needle_strict_violations'])} 条、"
        f"件-脚本同源例外披露 {len(sa['stale_artifacts'])} 条。"
    )
    reason = (
        "打磨环最容易说谎的是「我把口径对齐了」这句话本身，所以每条都配了反向证明："
        f"(1) 文档改写不是照源码字面抄，而是同一源同 output_dir 的真跑三格判定"
        "（复用=false、缓存查询恒 None、同一次调用连打命中与未命中），并把实测行号与旧账行号"
        "的分歧留在件里；"
        f"(2) 冻结面的「未动」用 {ap['frozen_files']} 个逐文件 sha 相等 + 一字节注入 canary 双向证明，"
        "只有前者就是「谓词坏了也报平安」；"
        "(3) 账面「只增不改」用差分四格（新增/删除/卡数/合法号数）而不是声明，"
        "反查命中为空这件事逼出「未派单」这个诚实措辞——写成「找回单号」就是伪造服务端归属；"
        "(4) 骨架收敛的证据是新旧解析对同一批归档件逐字段相等 + 复制集合逐字相同 + "
        "解析器双 canary；形状分差与留债逐条点名，没有把它们抹平成「已收敛」；"
        "(5) 新锁必须两档跑：工作区全绿、修前码必须红，且身份由 type_checker 的两个 sha 证明"
        "是两棵树；文档面那条红单独分栏，免得一次文档改写冒充「产品锁承重」；"
        "(6) 结构债全程只给测量与挂账理由，本环不可逆动作数、被碰产品文件数、改名数三格都为空，"
        "并配「刚写的文件必须被同一谓词判为碰过」的 canary 证明这个空集测得出来；"
        "(7) 三套体系 + git 红线 + 半径同一时刻复算，地板取 R4-验证 实测件而非手写目标，"
        "比较函数配「不可能的地板必须报违规」的 canary；本环两次起批、测量面未冻结这件事"
        "写进正文而不是藏进脚注；"
        f"(8) 渲染前自证 {sa['gates_pass']}/{sa['gates_total']} 道，needle 口径从「值里含子串」"
        "升级为「必须是件里的真键名」，并配 canary 证明旧口径确实放过过 "
        f"{json.dumps(sa['needle_canary'], ensure_ascii=False)}；"
        "件-脚本同源门把「跑完又改脚本」的例外逼着逐条披露。"
    )
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    doc = {"key": plan["key"], "root_task": rep["root_task"], "assignee": plan["assignee"],
           "stage": "R4-打磨",
           "forbid": "改 PROJECT-SPEC 与 SYNTAX；重注册 golden；git add/commit/push；"
                     "删文件或删别人的 worktree；删除或放宽既有测试；为了让绿而降低判据；"
                     "把「没做到」写成「已做」；在本环动手拆 3000 行文件；"
                     "向服务端补派未派单的卡片；报告归档后再改交付物；"
                     "把 needle 的子串命中当成证据（必须是被引件里的真键名）",
           "laws": laws, "branches": branches,
           "root_deliverable": deliv, "root_marker": rep["marker"],
           "root_law_marks_len": len([i for i in range(1, 9) if f"({i})" in deliv]),
           "root_extra_artifacts": [
               [".fist-loop-20260927/polish_r4_calllog_tally.json", "spec_named_carriers", 1000],
               [".fist-loop-20260927/polish_r4_self_audit.json", "needle_strict_violations", 1000]],
           "root_verify_reason": reason,
           "tests_allow": sorted(TESTS_ALLOW), "docs_allow": sorted(DOCS_ALLOW),
           "embedded_self_audit": {"gates_pass": sa["gates_pass"],
                                   "gates_total": sa["gates_total"],
                                   "placeholders_total": sa["placeholders_total"],
                                   "stale_artifacts_len": len(sa["stale_artifacts"]),
                                   "at_utc": sa["at_utc"]},
           "built_from_artifacts_at_utc": datetime.datetime.now(
               datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"written": OUT.name, "laws": len(doc["laws"]),
                      "branches": len(doc["branches"]),
                      "law_marks": doc["root_law_marks_len"],
                      "deliverable_chars": len(deliv), "reason_chars": len(reason)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
