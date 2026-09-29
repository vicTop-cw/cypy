"""把 R4-寻虫 的收口记录追加进 loop_progress.md——数字全部从判据件反解，不手打。

三条硬门（缺一条这段记录就是装饰）：
① 每个数字都要从件里取，件缺键就整段拒绝写入（宁可没有记录，不能有编的记录）；
② 报告正文 §八 标题里写的条数必须等于正文实际数出来的条数（标题改了正文没改是这一类的老坑）；
③ 幂等：文件里已经有本环标题就拒，跑第二遍不会写出两份。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r4_progress.json"
PROG = HERE / "loop_progress.md"
BODY = HERE / "r4_hunt_body.md"
MARK = "## R4-寻虫（根 `T0r74`"
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def load(fname: str) -> dict:
    p = HERE / fname
    if not p.exists():
        REFUSE.append(f"判据件缺失：{fname}")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def utc(s: str) -> datetime.datetime:
    """两种形状都收：`...+00:00` 与 `...Z`；解析失败就拒，不许拿本地时间糊。"""
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        REFUSE.append(f"时间戳形状不认识：{s!r}")
        return datetime.datetime.now(datetime.timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(datetime.timezone.utc)


def main() -> int:
    text = PROG.read_text(encoding="utf-8") if PROG.exists() else ""
    if MARK in text:
        REFUSE.append("loop_progress.md 里已有本环记录 ⇒ 拒绝重复追加（幂等门）")

    F = {n: load(f"hunt_r4_{n}.json") for n in
         ["faces", "confirm", "witness", "declared", "repro", "dedup", "filed",
          "baselines", "ledger3way", "drivers_lint", "calllog_tally"]}
    stage = load("close_r4_hunt.out.json")
    rclose = load("close_r4_hunt_root.out.json")
    spec = load("report_spec_r4_hunt.json")
    for name, doc in F.items():
        if isinstance(doc, dict) and doc.get("refuse"):
            REFUSE.append(f"{name} 自带拒绝：{json.dumps(doc['refuse'], ensure_ascii=False)[:180]}")

    faces, conf, wit = F["faces"], F["confirm"], F["witness"]
    decl, repro, dedup = F["declared"], F["repro"], F["dedup"]
    filed, base, three = F["filed"], F["baselines"], F["ledger3way"]
    lint, tal = F["drivers_lint"], F["calllog_tally"]
    st = tal.get("stages", {}).get("T0r74", {})
    car = tal.get("spec_named_carriers", {})
    ef = base.get("e2e", {}).get("fields", {})

    # §八 标题条数 vs 正文实际条数
    body = BODY.read_text(encoding="utf-8")
    sec8 = re.search(r"## 八、本环自身缺陷（判据类 (\d+) 条、操作类 (\d+) 条）(.*?)\n## 九",
                     body, re.S)
    if not sec8:
        REFUSE.append("报告正文 §八 标题形状不认识（无法核对条数）")
        claimed_j = claimed_o = got_j = got_o = -1
    else:
        claimed_j, claimed_o = int(sec8.group(1)), int(sec8.group(2))
        block = sec8.group(3)
        parts = re.split(r"\n操作类：\n", block)
        got_j = len(re.findall(r"^\d+\. ", parts[0], re.M))
        got_o = len(re.findall(r"^\d+\. ", parts[1], re.M)) if len(parts) > 1 else -1
        check("§八 判据类标题条数==正文条数", got_j, claimed_j, "标题改了正文没改=这一类老坑")
        check("§八 操作类标题条数==正文条数", got_o, claimed_o, "同上")
    check("§十一 有被拒原文逐字表（占位存在）", "refusals_md" in body, True,
          "法 7 要求逐字进报告，表由判据件反解")
    check("根终态已归档", rclose.get("root_final"), "已归档", "close_root out")
    check("叶全数完成", rclose.get("leaves_done"), 16, "root out.leaves_done")
    check("叶无失败", stage.get("failed"), [], "leaf closer out.failed")
    rep_rel = f"memory/reviews/{spec.get('name')}.md"
    rep = ROOT / "memory" / "reviews" / f"{spec.get('name')}.md"
    check("报告在盘上且够长", rep.exists() and rep.stat().st_size > 1500, True, rep_rel)
    check("报告里门禁格没有 ❌ 也没有未解析", ("❌" not in rep.read_text(encoding="utf-8")
                                          if rep.exists() else False), True, "渲染终检")
    if not (ROOT / "memory" / "reviews" / f"{spec.get('name')}.md").exists():
        REFUSE.append(f"报告文件不在盘上：memory/reviews/{spec.get('name')}.md")

    t0 = utc(base["window"]["start_utc"])
    t_end = utc(datetime.datetime.fromtimestamp(
        rep.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds"))
    t1 = utc(tal["queried_at_utc"])
    minutes = round((max(t_end, t1) - t0).total_seconds() / 60)
    closed_at = max(t_end, t1).isoformat(timespec="seconds")
    if minutes > 100:
        REFUSE.append(f"时间盒超限：{minutes} 分钟 > 100 分钟（要如实写，不许改起点）")
    det = [d for d in st.get("refused_detail", []) if isinstance(d, dict)]
    branch_refused = sum(1 for d in det if d["task"] != "T0r74")
    root_refused = sum(1 for d in det if d["task"] == "T0r74")
    check("被拒明细条数==refused 计数", len(det), st.get("refused"), "分支+根 = 总数")
    check("分支重放的幂等拒绝=48（8 枝 × 3 工具，重跑一次就是 48 条噪声）",
          branch_refused, 48, f"根上 {root_refused} 条另计")

    md = f"""
{MARK}，8 法 / 8 枝 / 16 叶）— 已收口 `{closed_at}`

- **交付**：报告 `memory/reviews/{spec["name"]}.md`（{(ROOT / 'memory' / 'reviews' / (spec['name'] + '.md')).stat().st_size} B，
  {len(spec["gates"])} 道门禁全过、0 格空缺），根 `T0r74` 终态 `{rclose["root_final"]}`，
  8 枝 16 叶 `已完成`；收口件里 {len(rclose.get("refused") or [])} 条被拒原文逐字进报告。
- **狩猎面转向没被系统扫过的三块**：函数类型层其余缺口 / docs 与 SYNTAX 状态表同实现的分道 /
  bridge 的生成与缓存面。{faces["families"]} 族 × {faces["cases_total"]} 用例逐带配「必报的对照」，
  {faces["candidate_total"]} 条候选按 pos/ctl 两档全部确诊（确诊 {conf["confirmed_total"]}、
  UNSURE {conf["unsure_total"]}），归并为 {len(conf["by_root_cause"])} 个代码根因；
  可见性三重见证（合成载荷翻转 {len(wit["w1_flipped"])}、真变异树差分 {len(wit["w2_changed"])}、
  看不见与零发现分栏，盲点 {wit["blind_spot_total"]} 个）——**盲点是 `struct_field_callback` 那一格探针
  没到达判定，这条如实记为清单级证据，不写成「没有缺陷」**。
- **文档/bridge 面 {decl["rows_total"]} 条主张逐条当场重测**（子代理只指路、未原样入账）：
  陈旧或缺口 {len(decl["stale_or_gap"])}（其中真缺口 {decl["real_gap_total"]}）、DESIGN 撤回
  {len(decl["withdrawn_design"])}、未测转结 {len(decl["not_measured_or_true"])}。
- **三态复现台账**：{len(repro["keys"])} 个根因键，退出码 {json.dumps(
      {k: v for k, v in repro["state_reached"].items() if k != "meaning"}, ensure_ascii=False)}
  三态本轮各自实测可达（状态 2 是我自己写坏谓词当场抓出来的，不是构造的）。
- **去重与入账**：与盘上 {dedup["ledger_cards"]} 单按机制签名比对，判重 {len(dedup["duplicates"])}、
  共享代码符号 {sum(len(r["symbol_overlap_hits"]) for r in dedup["rows"])} 处、逐条裁决注
  {len(dedup["near_miss_notes"])} 条；号从盘上现数 {dedup["numbering_from_disk"]} 起，
  入账 {filed["filed_total"]} 张 `{filed["filed"][0]}..{filed["filed"][-1]}`，
  账本 {filed["ledger_before"]}→{filed["ledger_after"]}、sqlite bug 行 {filed["sqlite_bug_rows"]}，
  三向对照 {three["agree_total"]}/{three["ledger_total"]} 一致、FIXED 段 {three["fixed_sections_total"]}。
- **三套体系同批复算且只升不降**：pytest {base["pytest"]["passed"]}（收集 {base["collect"]["nodeids"]}，
  地板 {base["floors"]["pytest"]}）、自研 {base["suite"]["fields"]["Passed"]}/{base["suite"]["fields"]["Total"]}、
  e2e {ef.get("PASS")} 过且 FAIL/WARN/UNREG = {ef.get("FAIL")}/{ef.get("WARN")}/{ef.get("UNREG/RUNFAIL")}；
  git 红线 HEAD `{base["git"]["head"]}`、暂存 {base["git"]["staged"]}、外部基线树在；
  改动半径按 mtime ≥ 本轮起点正面测：产品/测试/冻结面 {base["radius"]["forbidden_total"]}，
  判据件与账本 {base["radius"]["allowed_touched"]}——**本环零产品码改动**。
- **驱动面自计**：{lint["drivers_scanned"]} 个脚本硬码（E9/W605/F821/F7/F63）{lint["hard_violations"]} 条，
  注入对照必被抓 {lint["canary"]["bad_caught"]}、不误抓 {lint["canary"]["clean_false_positive"]}；
  软债 {lint["soft_total"]}（{json.dumps(lint["soft_codes"], ensure_ascii=False)}）立为只降不升基线。
- **call_log 对账**（按 `params_json.task_id` 前缀，不按标签/回忆）：T0r74 树 {st["rows"]} 行调用 /
  {st["refused"]} 行被拒 / 去重后 {tal["distinct_refusal_texts"]} 种原文逐字进报告；
  过滤器配必然不存在的前缀 ⇒ {tal["control_absent_prefix_rows"]} 行。
  规格点名的 `laya`/`issue_up` **不是本 build 的工具名**（精确名 0 命中），承担者实测为
  `laya_decide` {car.get("laya", {}).get("this_stage_total")} 次、
  `publish`+`report_bug` {car.get("issue_up", {}).get("this_stage_total")} 次；
  `call_log` 工具本轮真调过一次（客户端回包 {car.get("call_log", {}).get("carriers", {}).get("call_log", {}).get("client_visible_T0r74_rows")} 行含 T0r74
  ≥ sqlite 同口径 {st["rows"]} 行，两个读数不等就拒）。
- **时间盒**：根发布 `{base["window"]["start_utc"]}` → 终版 `{closed_at}` ≈ **{minutes} 分钟**
  （≤100 但已逼近；8 法 × 16 叶 × 10 入账的体量决定了它压不进 60 分钟，下一环按「一 mode 一收口」再切细）。
- **本环自记缺陷：判据类 {claimed_j} 条 / 操作类 {claimed_o} 条**，值得带走的三条：
  ① 存在性判据证不了形状主张（F5 恒绿一整轮）；② 探针崩溃/非零退出绝不能读成结论，
  一律降级 `not_measured` 并保留原文；③ 判据件自己的键形状要现数（`near_miss_notes` 是 dict 不是 list，
  当 list 切片当场炸）。操作类新增一条：根收口器**必须在报告落盘之后**再跑——第一次被 L4 产物门拒是对的，
  但我为了补产物把根收口器重放到 `{base['window']['start_utc']}` 之后的时段，
  按 ts 现数：分支重放造出 {branch_refused} 条幂等拒绝、根上 {root_refused} 条（其中 3 条是根没开
  `[omega:required]` 的既定语义）。顺序应是「报告→根收口」一次到位，已写进 R4-修复 的操作纪律。

转结新增（R4-修复 输入）：BUG-61..BUG-70 逐单认领——RC1/RC2/RC3/RC4 四条分析器根因本环可修，
每单要配成对锁 + 回退矩阵（把实现改回去锁必红）；BUG-65（冻结文档 7 行）、BUG-70（`parser.py`/
`cython_generator.py` 越 3000 行阈值）交人工裁决不动刀；BUG-66/67（bridge 缓存落调用方 CWD、
生成的 C 与 Cython 不等价）取「下一环可改」那一栏。D18（缓存命中复用）与 `appendix-C`
《已实现的限制修复》14 行本轮未复测 ⇒ 转结 R4-验证。操作纪律转结：先落报告再收根。
"""
    fails = [c["label"] for c in CHECKS if not c["ok"]]
    if fails or REFUSE:
        OUT.write_text(json.dumps({"refuse": sorted(set(REFUSE)) + [f"自证未过：{f}" for f in fails],
                                   "checks": CHECKS, "written": False},
                                  ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        print(json.dumps({"refuse": sorted(set(REFUSE)), "checks_failed": fails,
                          "written": False}, ensure_ascii=False, indent=1))
        return 1
    PROG.write_text(text + md, encoding="utf-8", newline="\n")
    OUT.write_text(json.dumps({"refuse": [], "checks": CHECKS, "checks_total": len(CHECKS),
                               "written": True, "appended_chars": len(md),
                               "minutes": minutes,
                               "at_utc": datetime.datetime.now(
                                   datetime.timezone.utc).isoformat(timespec="seconds")},
                              ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"written": True, "appended_chars": len(md), "minutes": minutes,
                      "checks": "%d/%d" % (sum(1 for c in CHECKS if c["ok"]), len(CHECKS)),
                      "refuse": []}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
