"""R4-寻虫 收口件：把报告页脚**从判据件反解**出来，并对本环自身做一轮可红的自证。

三条硬规矩（上一环踩过坑）：
- 页脚只接受 `handoff=` 段作种子，合成结果里同名键出现两次即拒（防"读回自己旧字段再叠一层"）；
- 任何一格判据件自带 refuse、叶有失败、三套体系有红 ⇒ 一个数字都不落；
- 自证的条数取「spec 里写了多少格」而不是「渲染出来多少格」，恒绿格（`min: 0`）必须为 0。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "report_spec_r4_hunt.json"
OUT = HERE / "hunt_r4_self_audit.json"
REQUIRED = ["hunt_r4_probe.json", "hunt_r4_faces.json", "hunt_r4_confirm.json",
            "hunt_r4_witness.json", "hunt_r4_declared.json", "hunt_r4_repro.json",
            "hunt_r4_dedup.json", "hunt_r4_filed.json", "hunt_r4_baselines.json",
            "hunt_r4_ledger3way.json", "hunt_r4_drivers_lint.json",
            "hunt_r4_calllog_tally.json",
            "close_r4_hunt.out.json", "close_r4_hunt_root.out.json"]
REFUSE: list = []
CHECKS: list = []


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why,
                   "ok": (got == want) if ok is None else bool(ok)})


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        print(json.dumps({"refuse": [f"判据件/收口件缺失，页脚不许手补：{missing}"]}, ensure_ascii=False))
        return 1
    L = {f: json.loads((HERE / f).read_text(encoding="utf-8")) for f in REQUIRED}
    for f, doc in L.items():
        if isinstance(doc, dict) and doc.get("refuse"):
            REFUSE.append(f"{f} 自带拒绝：{json.dumps(doc['refuse'], ensure_ascii=False)[:200]}")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    stage, rclose = L["close_r4_hunt.out.json"], L["close_r4_hunt_root.out.json"]
    tally = L["hunt_r4_calllog_tally.json"]
    base, filed, dedup = L["hunt_r4_baselines.json"], L["hunt_r4_filed.json"], L["hunt_r4_dedup.json"]
    faces, confirm, wit = L["hunt_r4_faces.json"], L["hunt_r4_confirm.json"], L["hunt_r4_witness.json"]
    declared, repro = L["hunt_r4_declared.json"], L["hunt_r4_repro.json"]
    three = L["hunt_r4_ledger3way.json"]
    lint = L["hunt_r4_drivers_lint.json"]
    probe = L["hunt_r4_probe.json"]

    if rclose.get("root_final") != "已归档":
        REFUSE.append(f"根未归档：{rclose.get('root_final')}")
    if stage.get("failed"):
        REFUSE.append(f"叶失败：{json.dumps(stage['failed'], ensure_ascii=False)[:200]}")
    check("三套体系全绿旗标", base.get("three_systems_green"), True, "baselines 件自报")
    check("pytest 不低于上一环实测下限", base["pytest"]["passed"] >= 1938, True,
          f"passed={base['pytest']['passed']}", ok=base["pytest"]["passed"] >= 1938)
    check("pytest passed 与收集数同量（解析器活着）",
          base["collect"]["nodeids"] >= base["pytest"]["passed"], True,
          f"collect={base['collect']['nodeids']} vs passed={base['pytest']['passed']}",
          ok=base["collect"]["nodeids"] >= base["pytest"]["passed"])
    check("自研套件 47/47", f"{base['suite']['fields'].get('Passed')}/"
          f"{base['suite']['fields'].get('Total')}", "47/47", "baselines.suite")
    ef = base["e2e"]["fields"]
    check("e2e PASS=25 且 FAIL/WARN 为零", f"{ef.get('PASS')}/{ef.get('FAIL')}/{ef.get('WARN')}",
          "25/0/0", "baselines.e2e")
    check("git 红线四项齐全", [base["git"]["head"], base["git"]["staged"],
                              base["git"]["foreign_worktree_present"], base["git"]["ahead_of_upstream"]],
          ["17d68b4", 0, True, base["git"]["ahead_of_upstream"]], "head/暂存/外部树/领先数")
    check("半径：产品面为零", base["radius"]["forbidden_total"], 0,
          json.dumps(base["radius"]["touched_forbidden"], ensure_ascii=False)[:200])
    check("半径：本轮确实写了东西（正面计数）", base["radius"]["allowed_touched"] > 10, True,
          f"loop/memory 侧 {base['radius']['allowed_touched']} 个", ok=base["radius"]["allowed_touched"] > 10)
    check("候选=确诊=入账根因映射一致",
          [faces["candidate_total"], confirm["confirmed_total"], len(confirm["confirmed"])],
          [12, 12, 12], "faces 候选数 vs confirm 确诊数")
    check("四根因都有确诊", len(confirm["by_root_cause"]), 4, "by_root_cause 键数")
    check("入账条数=计划单数=三向一致数",
          [filed["filed_total"], dedup["plan_total"], three["agree_total"]],
          [dedup["plan_total"]] * 3, "三处同数")
    check("号段连续且从盘上现数", [filed["filed"], filed["numbering_from_disk"]["first_new"]],
          [[f"BUG-{n}" for n in range(61, 71)], 61], "filed.filed vs 计划")
    check("账本增量=入账条数", filed["ledger_after"] - filed["ledger_before"], filed["filed_total"],
          "md 计数差")
    check("DESIGN 撤回与未测都被点名",
          [len(declared["withdrawn_design"]) + len(declared["not_measured_or_true"]),
           len(dedup["unclaimed_reason"])], [2, 2], "撤回/未测栏")
    check("复现三态各自可达", sorted(repro["state_reached"])[:3],
          sorted(["0_all_reproduced", "1_not_reproduced_selftest_rc", "2_fixture_broken_unknown_key_rc"]),
          "0/1/2 三格")
    check("零发现与看不见分栏（探针那一格不许糊）",
          [wit["blind_spot_total"], len(probe["context_not_visited"])], [1, 1], "blind_spots 计数")
    check("判据自证条数（每个件都要有自己的 self_checks，不许裸结论）",
          sum(len(L[f].get("self_checks") or []) for f in
              ["hunt_r4_faces.json", "hunt_r4_confirm.json", "hunt_r4_witness.json",
               "hunt_r4_declared.json", "hunt_r4_baselines.json", "hunt_r4_ledger3way.json",
               "hunt_r4_dedup.json"]), True,
          "faces/confirm/witness/declared/baselines/ledger3way/dedup 合计",
          ok=all(L[f].get("self_checks") for f in
                 ["hunt_r4_faces.json", "hunt_r4_confirm.json", "hunt_r4_witness.json",
                  "hunt_r4_declared.json", "hunt_r4_baselines.json", "hunt_r4_ledger3way.json"]))
    vacuous = [g["label"] for g in spec["gates"] if g.get("min") == 0]
    check("恒绿门禁格（min: 0）必须为 0", len(vacuous), 0, f"spec：{vacuous}")
    nojudge = [g["label"] for g in spec["gates"]
               if not any(k in g for k in ("min", "equals", "truthy"))]
    check("每格都写了判定形状", len(nojudge), 0, f"缺判定键的门禁：{nojudge}")
    refs = sorted({m.group(1).split("/")[-1] for m in
                   re.finditer(r"\{\{([^}|]+)\|",
                               (HERE / "r4_hunt_body.md").read_text(encoding="utf-8"))})
    declared_arts = {a.split("/")[-1] for a in spec["artifacts"]}
    check("散文确实用了占位取数（空引用集会让下一条恒绿）", len(refs) >= 1, True,
          f"引用 {len(refs)} 个件名")
    check("散文引用的件都在 spec 清单里", [r for r in refs if r not in declared_arts], [],
          f"引用 {len(refs)} 个件名")

    # 页脚：只从件里取数
    foot_seed = re.search(r"handoff=\S.*", spec["footer"])
    if not foot_seed:
        REFUSE.append("spec['footer'] 缺 handoff= 段 ⇒ 无法安全幂等重写")
        footer = ""
    else:
        seed = foot_seed.group(0).strip()
        if re.search(r"(^|\s)(faces|confirmed|filed|radius|pytest|leaves)=", seed):
            REFUSE.append("handoff 段里混进了 synthesized 键，拒绝叠加")
        footer = (
            f"leaves={rclose.get('leaves_done')} faces={faces['families']} "
            f"face_cases={faces['cases_total']} candidates={faces['candidate_total']} "
            f"confirmed={confirm['confirmed_total']} unsure={confirm['unsure_total']} "
            f"root_causes={len(confirm['by_root_cause'])} "
            f"probe_cases={probe['battery_cases']} probe_differ={probe['witness_pos_differ']} "
            f"blind_spots={wit['blind_spot_total']} w1_flipped={len(wit['w1_flipped'])} "
            f"w2_changed={len(wit['w2_changed'])} "
            f"declared_rows={declared['rows_total']} stale_or_gap={len(declared['stale_or_gap'])} "
            f"design_withdrawn={len(declared['withdrawn_design'])} "
            f"not_measured={len(declared['not_measured_or_true'])} "
            f"repro_keys={len(repro['keys'])} repro_zero={repro['all_exit_codes_zero']} "
            f"ledger_cards={dedup['ledger_cards']} duplicates={len(dedup['duplicates'])} "
            f"symbol_overlap_hits={sum(len(r['symbol_overlap_hits']) for r in dedup['rows'])} "
            f"near_notes={len(dedup['near_miss_notes'])} "
            f"filed={filed['filed_total']} numbers={filed['filed'][0]}..{filed['filed'][-1]} "
            f"ledger={filed['ledger_before']}->{filed['ledger_after']} "
            f"agree3way={three['agree_total']}/{three['ledger_total']} "
            f"fixed_sections={three['fixed_sections_total']} "
            f"pytest={base['pytest']['passed']} collect={base['collect']['nodeids']} "
            f"suite={base['suite']['fields'].get('Passed')}/{base['suite']['fields'].get('Total')} "
            f"e2e={ef.get('PASS')}/{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')} "
            f"head={base['git']['head']} staged={base['git']['staged']} "
            f"radius_forbidden={base['radius']['forbidden_total']} "
            f"radius_allowed={base['radius']['allowed_touched']} "
            f"driver_hard={lint['hard_violations']} driver_soft={lint['soft_total']} "
            f"canary={lint['canary']['bad_caught']} "
            f"refusal_kinds={len(rclose.get('refused') or [])} "
            f"calllog_rows={tally['stages']['T0r74']['rows']} "
            f"calllog_refused={tally['stages']['T0r74']['refused']} "
            f"calllog_verbatims={tally['distinct_refusal_texts']} "
            f"carriers=laya:{tally['spec_named_carriers']['laya']['this_stage_total']}"
            f"/issue_up:{tally['spec_named_carriers']['issue_up']['this_stage_total']}"
            f"/call_log:{tally['spec_named_carriers']['call_log']['this_stage_total']} "
            f"measured_window={base['window']['start_utc']}->{base['finished_at_utc']} "
            f"generated_at={started} " + seed)
        twice = sorted({k for k in re.findall(r"(?:^|\s)([a-z][\w-]*)=", footer)
                        if footer.count(f"{k}=") > 1})
        if twice:
            REFUSE.append(f"页脚同名键出现两次（不幂等）：{twice}")
    spec["footer"] = footer
    doc = {"started": started, "refuse": sorted(set(REFUSE)), "checks": CHECKS,
           "checks_total": len(CHECKS),
           "checks_failed": [c["label"] for c in CHECKS if not c["ok"]],
           "gates_total": len(spec["gates"]), "artifacts_total": len(spec["artifacts"]),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    doc["refuse"] += [f"自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:160]}）"
                      for c in CHECKS if not c["ok"]]
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
                      "gates": doc["gates_total"], "footer_len": len(footer)},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(json.dumps({"refuse": [f"崩在 {type(exc).__name__}: {exc}"]},
                                  ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
