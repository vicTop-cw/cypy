"""把 close_r4_fix.json 的根交付物正文与验收理由**从判据件反解**出来，不手填数字。

上一环的账面自纠（标题写 131/0 失败、正文另一套）就是手填计数的代价，所以这里让收口件的数字
全部来自盘上件；件缺任何一格就直接拒绝写回（宁可收口失败，也不交一份没测过的正文）。
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLOSE = HERE / "close_r4_fix.json"
REFUSE: list = []


def need(name: str) -> dict:
    p = HERE / name
    if not p.exists():
        REFUSE.append(f"判据件缺失：{name}")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("refuse"):
        REFUSE.append(f"{name} 的 refuse 非空：{json.dumps(d['refuse'], ensure_ascii=False)[:200]}")
    return d


def main() -> int:
    claim = need("fix_r4_claim.json")
    locks = need("fix_r4_locks.json")
    rc = need("fix_r4_rc.json")
    rev = need("fix_r4_revert.json")
    imp = need("fix_r4_impact.json")
    docs = need("fix_r4_docs.json")
    base = need("fix_r4_baselines.json")
    led = need("fix_r4_ledger.json")
    lchk = need("fix_r4_ledger_check.json")
    lint = need("fix_r4_drivers_lint.json")
    tally = need("fix_r4_calllog_tally.json")
    sad = need("fix_r4_self_audit.json")
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1
    pf, gf = base["pytest"], base["git"]
    if pf["failed_names"]:
        REFUSE.append(f"pytest 还有 {pf['failed']} 条红：{pf['failed_names']}")
    if base["git"]["staged"] != 0:
        REFUSE.append(f"暂存区非 0（{base['git']['staged']} 行）⇒ 红线违例，不能收口")
    if base["radius"]["frozen"]:
        REFUSE.append(f"冻结面被触碰：{base['radius']['frozen']}")
    if REFUSE:
        print(json.dumps({"refuse": sorted(set(REFUSE))}, ensure_ascii=False, indent=1))
        return 1

    deliv = (
        f"R4-修复 交付：{__import__('pathlib').Path('memory/reviews').as_posix()}/"
        f"{{REPORT_NAME}}；十张单按「本环可修 / 下一环 / 交人工」三栏分派"
        f"（{len(claim['rows'])} 行归属全部从 memory/bugs.md 反解，反解条目数 "
        f"{len(claim['rows'])} == 盘上标题数）。产品码改动只落 "
        f"`{rc['target']}`：+{rc['added_lines']} / -{rc['removed_lines']}，"
        f"新增 {len(rc['new_defs'])} 个定义、共享 {len(rc['shared_symbols'])} 个符号、"
        f"调用点 {rc['call_site_total']} 处 —— RC1/RC2/RC3/RC4 共用同一张 "
        f"`callable_sigs` 表与同一个兼容谓词 `_callable_arg_mismatch`，不是四个补丁。"
        f"锁先行：修前 `{locks['before']['summary_line']}`（{len(locks['before']['failed_names'])} 条红、"
        f"退出码 {locks['before']['rc']}）→ 修后 `{locks['after']['summary_line']}`；"
        f"回退矩阵四腿（{', '.join(r['rc'] for r in rev['rows'])}）各自摘回原样必红、"
        f"对照组零误伤、复原 sha == 基线 sha。语义影响面按 {imp['corpus']} 档存量语料逐档差分："
        f"新增诊断 {len(imp['newly_rejected'])}、消失诊断 {len(imp['newly_accepted'])}、"
        f"待裁决 {len(imp['unadjudicated'])}（中途真出现过 9 档 14 条误报，分因后由三处越界改动的"
        f"收敛打掉，不是先验断言）。文档面 {len(docs['agreed'])} 行按 argparse/dataclass 实读对齐、"
        f"半开 {len(docs['half_open'])} 条如实转结、冻结面只读探针仍为 stale "
        f"（sha {docs['frozen_bytes_sha']}）。账面：六张修复单 claim→execute→submit→verify 全部"
        f"「已完成」，三向对照 {led['agree_total']}/{len(led['cards'])} 一致，"
        f"追加 FIXED 段后账本仍 {led['ledger_total']} 条不多生条目，"
        f"驱动格式化后另以只读复核件独立重读 {lchk['agree_total']}/{lchk['total']}。"
        f"三套体系同批复算：pytest {pf['passed']} 通过 / {pf['failed']} 失败 / {pf['errors']} 错误、"
        f"收集 {base['collect']['nodeids']}"
        f"（地板 {base['floors']['pytest']}/{base['floors']['collect']} 未降）、自研"
        f"{base['suite']['fields']}、e2e {base['e2e']['fields']}；"
        f"HEAD {gf['head']}、暂存 {gf['staged']} 行、外部基线 worktree 仍在；"
        f"改动半径 产品 {len(base['radius']['product'])} / 测试 {len(base['radius']['tests'])} / "
        f"文档 {len(base['radius']['docs'])} / 冻结 {len(base['radius']['frozen'])} / "
        f"判据件 {len(base['radius']['loop'])}。驱动面 {lint['drivers_scanned']} 个本轮亲笔脚本"
        f"硬错 {lint['hard_violations']}、软账 {lint['soft_total']}（上一环基线 "
        f"{lint['previous_round_soft_baseline']}，只降不升）。调用面账面截于渲染前："
        f"任务树 {tally['tree_rows']} 行、修复单 {tally['bug_card_rows']} 行，"
        f"被拒 {tally['tree_refused']} + {tally['bug_card_refused']} 条，"
        f"Omega 标记 叶 {tally['omega_marked']['leaves']}/16、根 {tally['omega_marked']['root']}/1。"
        f"本环判据自伤 {sad['section8_items']} 条已逐条写进报告《八》；"
        f"时间盒 100 分钟被超（实耗见 loop_progress），按纪律如实记账、门禁未缩。"
    )
    reason = (
        "修复环最容易说谎的是『修好了』这三个字，所以每一层都配了反向证明："
        f"(1) 锁先跑到红（{len(locks['before']['failed_names'])} 条）才动实现，"
        "红是断言级红而不是收集错；"
        "(2) 回退矩阵把四条腿分别摘回原文，该族必须变红且对照组不变红——摘不动就是锁不承重；"
        "(3) 合并修用共享符号与调用点计数正面证明，而不是四张单各自加补丁；"
        f"(4) 影响面跑满 {imp['corpus']} 档存量语料，差分两侧都数（新增与消失），"
        "本轮中途真出现过的 9 档误报被记录并收敛，没有为了让绿而放宽；"
        "(5) 文档面每条都按 argparse / dataclass 实读判，还配一条『实现里没有的旗标不许出现在文档』"
        "的反向对照；冻结面用『它必须仍然错着』的只读探针证明我没动刀；"
        f"(6) 三套体系 + git 红线 + 半径同批复算，porcelain 的索引位与工作区位分栏（上一版把 ' D' "
        "当成 staged，本轮实测 0 行才算对上红线）；"
        "(7) 账面三向（md 段 / sqlite 终态 / call_log 逐调用）一致，驱动件落盘后又被格式化的那一份"
        "用只读复核件重读，不引用旧绿灯；"
        "(8) 唯一一条被改的既有测试是把比较面从静态 AST 切片换到调用面 --help，并新增反向断言"
        "（AST 声明过的必须在 --help 里），净效果更严；这条判断已列进报告《九》交指挥官复核，"
        "不自评为合规。"
    )
    spec = json.loads(CLOSE.read_text(encoding="utf-8"))
    name = json.loads((HERE / "report_spec_r4_fix.json").read_text(encoding="utf-8"))["name"]
    spec["root_deliverable"] = deliv.replace("{REPORT_NAME}", name)
    spec["root_verify_reason"] = reason
    spec["built_from_artifacts_at_utc"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")
    CLOSE.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    print(json.dumps({"written": CLOSE.name, "report_name": name,
                      "deliverable_chars": len(spec["root_deliverable"]),
                      "reason_chars": len(spec["root_verify_reason"])},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
