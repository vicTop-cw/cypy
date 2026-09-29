"""R4-验证 的收口 spec 生成器：叶/支的判据、根交付物正文与验收理由全部**从判据件反解**。

不手填数字（上一环的教训：标题一个数、正文另一个数）。任何一份件缺格或带 refuse，
这里直接拒绝写回——宁可收口失败，也不交一份没测过的正文。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLAN = HERE / "spec_r4_verify.json"
SPEC = HERE / "report_spec_r4_verify.json"
OUT = HERE / "close_r4_verify.json"
REFUSE: list = []
NEED = ["verify_r4_matrix.json", "verify_r4_callsite.json", "verify_r4_appendixC.json",
        "verify_r4_compile.json", "verify_r4_baselines.json", "verify_r4_lockproof.json",
        "verify_r4_ledger3way.json", "verify_r4_irreversible.json",
        "verify_r4_calllog_tally.json", "verify_r4_file_bugs.json",
        "verify_r4_drivers_lint.json", "verify_r4_self_audit.json"]
# 自证件与本件互为输入（渲染前要先有收口 spec 才能给它配门禁），所以第一次跑时它必然带红：
# 这里只要求它**在盘上**，不要求它绿；真正卡住渲染的是 report_kit 的 ⑨-19（自证件 refuse 必空）。
SOFT = {"verify_r4_self_audit.json"}


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

    mx, cs, ap = art["verify_r4_matrix.json"], art["verify_r4_callsite.json"], \
        art["verify_r4_appendixC.json"]
    cp, bs, lp = art["verify_r4_compile.json"], art["verify_r4_baselines.json"], \
        art["verify_r4_lockproof.json"]
    lg, ir = art["verify_r4_ledger3way.json"], art["verify_r4_irreversible.json"]
    tl, fb = art["verify_r4_calllog_tally.json"], art["verify_r4_file_bugs.json"]
    ln, sa = art["verify_r4_drivers_lint.json"], art["verify_r4_self_audit.json"]

    pf, gf = bs["systems"]["pytest"], bs["git"]
    if pf["failed"] or pf["errors"]:
        REFUSE.append(f"pytest 还有红：{pf['failed']}/{pf['errors']} ⇒ 门禁不绿，不能收口")
    if gf["staged"]:
        REFUSE.append(f"暂存区非 0（{gf['staged']} 行）⇒ 红线违例")
    for col in ("product", "tests", "docs", "frozen"):
        if bs["radius"][col]:
            REFUSE.append(f"验证环半径违例：{col} 栏非空 {bs['radius'][col][:3]}")
    if cp["golden_untouched"]["before"] != cp["golden_untouched"]["after"]:
        REFUSE.append("golden 面 sha 变了 ⇒ 本环不许重注册基准")
    # 自证件不在这里当绿门：它与本件互为输入，pass1 必然带红（红的全是指向尚未生成的本件的
    # 那几道门禁）。真正卡住渲染的是 report_kit 的 ⑨-19「自证件 refuse 必空」+ 链上的 pass2。
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1

    laws = plan["laws"]
    # call_log 有两个时刻：报告 §八 记的是**渲染前**快照，本件说的是**发单前**复算。
    # 报告已经渲染、不可回改，所以这里把两个数都点名并解释差额，而不是让读者以为它们是同一个数。
    snap_p = HERE / "verify_r4_tmp" / "calllog_prerender_snapshot.json"
    snap_rows = (json.loads(snap_p.read_text(encoding="utf-8"))["rows_T0r86"]
                 if snap_p.exists() else None)
    if snap_rows is not None and tl["rows_T0r86"] < snap_rows:
        REFUSE.append(f"发单前 call_log 反而比渲染前少（{tl['rows_T0r86']} < {snap_rows}）")
    branches = [[f"法{i}：{law['name']}", law["artifacts"][0][0], law["artifacts"][0][1]]
                for i, law in enumerate(laws, 1)]
    deliv = (
        f"R4-验证 交付：memory/reviews/{rep['name']}；半径=只看不动手"
        f"（产品 {len(bs['radius']['product'])} / 测试 {len(bs['radius']['tests'])} / "
        f"docs {len(bs['radius']['docs'])} / 冻结 {len(bs['radius']['frozen'])} 全空，"
        f"改动只在 .fist-loop 判据件 {len(bs['radius']['loop'])} 个）。"
        f"八条法全部独立复算：(1) 回退矩阵 {mx['rows_total']} 行由 difflib opcode 自动切片，"
        f"{len(mx['bearing'])} 行承重、{len(mx['non_bearing'])} 行不承重如实分栏，"
        f"{mx['sha_restored']}/{mx['rows_total']} 行 sha 逐字复原，"
        f"反面 canary 被抓 {mx['canary_caught']} 次，身份探针 "
        f"{mx['identity']['under_snapshot']} 证明吃的是快照树；"
        f"(2) 调用面 {cs['rows_total']} 条只走 CLI 子进程，同族对照 "
        f"{cs['controls_pass']} 条全数在报，内部表示外泄 {len(cs['internal_repr_leaks'])} 条，"
        f"换回修前产品码后翻转 {cs['sensitivity']['flips_total']} 条"
        f"（含正确调用形状 {len(cs['sensitivity']['proper_flips'])} 条）；"
        f"(3) 附录 C《已实现的限制修复》反解 {ap['rows_total']} 行逐行现写真跑："
        f"{len(ap['verified'])} 行成立、{len(ap['claim_false'])} 行 claim-false、"
        f"{len(ap['claim_half_true'])} 行 claim-half-true、没测到 {len(ap['unverified'])} 行；"
        f"(4) 真编译器三发：合法 C rc={cp['attempts'][0]['rc']}、合成违例 rc="
        f"{cp['attempts'][1]['rc']}、bridge 生成物 rc={cp['attempts'][2]['rc']} 且拒在模块级 "
        f"if 第 {cp['structural']['module_level_if_lines'][0][0]} 行 —— BUG-69 现形；"
        f"D18 实测 {cp['d18_cache']['verdict']}（.pyd 被重写 "
        f"{cp['d18_cache']['pyd_rewritten_between_calls']}、get_cached_pyd 全 None），"
        f"文档那句「源未变会复用」不成立；产物全在 scratch "
        f"{cp['scratch_outside_repo']}、golden 面 {cp['golden_untouched']['files_after']} 个文件"
        f"前后 sha 相等 {cp['golden_untouched']['equal']}；"
        f"(5) 三套体系同批复算且只升不降：pytest {pf['passed']} 通过/"
        f"{pf['failed']} 失败（地板 {bs['floors']['pytest']}）、收集 "
        f"{bs['systems']['collect']['nodeids']}、自研 {bs['systems']['suite']['fields']}、"
        f"e2e {bs['systems']['e2e']}，HEAD {gf['head']}、暂存 {gf['staged']}；"
        f"(6) 锁必红复核三档 {lp['runs'][0]['achieved']}/{lp['runs'][1]['achieved']}/"
        f"{lp['runs'][2]['achieved']}，HEAD 档 {lp['runs'][2]['target_red_count']} 条红且 "
        f"{len(lp['runs'][2]['r4_shape_hits'])} 条红在本轮四单形状上；"
        f"(7) 账面三向：md {lg['cards_total']} 卡 / sqlite {lg['sqlite_bug_rows']} 行，"
        f"差 {lg['ledger_delta']} 已由 md_only {len(lg['md_only_cards'])} 张逐张点名对上恒等式，"
        f"R4-修复 FIXED {len(lg['r4_fixed_cards'])} 张三向一致 {lg['three_way_agreed']} 张，"
        f"每张单的复跑命令真跑 {len(lg['recheck'])} 条，"
        f"不再现形 {len(lg['fixed_not_recurring'])} 张、仍现形 {len(lg['still_recurring'])} 张、"
        f"未交代半开 {len(lg['undisclosed_half_open'])} 张；"
        f"(8) 不可逆 {ir['not_executed_total']} 条逐条带测量（canary "
        f"{ir['canary']['predicate_catches_known_write']}），裁决队列 {len(ir['adjudication_queue'])} 条；"
        f"新入账 {fb['filed_total']} 张（{', '.join(fb['filed'])}，sqlite 增量 "
        f"{fb['sqlite_bug_rows']['delta']}）；驱动面 {ln['drivers_scanned']} 个亲笔脚本硬错 "
        f"{ln['hard_violations']}、软账 {ln['soft_total']}（上一环基线 "
        f"{ln['previous_round_soft_baseline']}，只降不升）；"
        f"渲染前自证 {sa['gates_pass']}/{sa['gates_total']} 道门禁与 "
        f"{sa['placeholders_total']} 个占位全部解出，"
        f"件-脚本同源例外披露 {len(sa['stale_artifacts'])} 条。"
        f"发单前复算的账面 call_log：本环前缀 {tl['rows_T0r86']} 行 / "
        f"{tl['distinct_tasks']} 个任务，被拒 {tl['stages']['T0r86']['refused']} 条"
        f"（报告 §八 渲染前快照是 {snap_rows} 行，两次之间只多了本环自己的复算调用，"
        f"没有收口 RPC；收口链的行数与被拒原文一律进 loop_progress.md）。"
    )
    reason = (
        "验证环最容易说谎的是「我复算过了」，所以每一层都配了反向证明："
        f"(1) 矩阵的切片来自 difflib 而不是修复环的 RC 清单，且纯注释行的反面 canary 必须"
        "被同一张矩阵判为不承重——没有它，「摘了也不红」既可能是锁不承重也可能是矩阵坏了；"
        f"(2) 调用面只走 CLI 子进程并把命令逐字入账，再换回修前产品码测一遍敏感度（"
        f"{cs['sensitivity']['flips_total']} 条翻转），V61a 这种「正确调用」形状也在翻转表里，"
        "才证明探针打的确实是 BUG-61 的假阳性而不是别的东西；"
        f"(3) 文档行清单从冻结表体反解（{ap['rows_total']} 行），逐行现写真源现跑，"
        "并配一条盘上绝不存在的 needle 作对照；"
        f"(4) 真编译前先让合法 C 编得过（rc={cp['attempts'][0]['rc']}），"
        "否则「编译器拒了生成物」这句不成立；D18 先证明 .pyd 真落盘才谈复用，"
        "墙钟快慢一律不作主张（本机墙钟随负载摆动）；"
        "(5) 三套体系 + git 红线 + 半径同一时刻复算，地板取上一环实测件而不是手写目标，"
        "比较函数自己配「不可能的地板必须报违规」的 canary；"
        "(6) 锁复核拿 HEAD 码与修前码两棵树重跑，三档跑同一份测试文件（sha 集合=1），"
        "红还必须红在本轮四单的形状上；"
        "(7) 账面 md/sqlite/call_log 三向 + 每单复跑命令真跑，两口径的差用恒等式逐张点名；"
        "(8) 不可逆动作不是「我没做」而是 mtime/sha/行数三类谓词的正面测量，"
        "每类都配「确实改过的文件必须被抓到」的 canary；"
        f"(9) 报告渲染前自证 {sa['gates_pass']}/{sa['gates_total']} 道门禁，"
        "且件-脚本同源门把本环唯一一处「跑完又改脚本文本」的例外逼着披露在报告里。"
    )
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    doc = {"key": plan["key"], "root_task": rep["root_task"], "assignee": plan["assignee"],
           "stage": "R4-验证",
           "forbid": "把工作区当快照树跑；用修复环的判据件当本轮证据；改产品码或测试来凑验证绿；"
                     "弱化或删除既有测试；git add/commit/push；删文件或删别人的 worktree；"
                     "改 PROJECT-SPEC 与 SYNTAX；重注册 golden；把 scratch 编译产物落进仓库源码树；"
                     "把「没复验到」写成「已验证」；报告归档后再改交付物",
           "laws": laws, "branches": branches,
           "root_deliverable": deliv, "root_marker": rep["marker"],
           # 逐法点名的见证：正文里 (1)…(8) 每个标号都要真的出现过
           # （长度地板是我先前拍的数，不能反过来让正文去凑它——把它换成这条会红的结构判据）。
           "root_law_marks_len": len([i for i in range(1, 9) if f"({i})" in deliv]),
           "root_extra_artifacts": [
               [".fist-loop-20260927/verify_r4_calllog_tally.json", "spec_named_carriers", 1000],
               [".fist-loop-20260927/verify_r4_self_audit.json", "gates_pass", 1000]],
           "root_verify_reason": reason,
           # 本件引用的自证格数来自「跑我当时那一份」的自证件；不动点复核件要能把这个引用
           # 对回最终那一版（渲染与自证互为输入 ⇒ 数必须推到不动点，不能手工挑一个）。
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
                      "deliverable_chars": len(deliv), "reason_chars": len(reason)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
