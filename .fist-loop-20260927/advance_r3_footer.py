"""把 R3-推进 的报告页脚写成**从判据件反解**的串，并强制幂等。

上一环踩过"合成器把新串叠在旧串上 ⇒ 同一行两个同名键"的坑，所以这里：
① 只接受 `handoff=` 段作为种子；② 合成结果里同名键出现两次即拒；
③ 任一判据件自带 refuse、根未归档、叶有失败、三套体系有红 ⇒ 一个数字都不落。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "report_spec_r3_advance.json"
REQUIRED = ["advance_r3_arity.json", "advance_r3_codegen_diff.json", "advance_r3_scope_face.json",
            "advance_r3_locks.json", "advance_r3_corpus.json", "advance_r3_baselines.json",
            "advance_r3_irreversible.json", "root_r3_advance.out.json",
            "close_r3_advance.out.json", "close_r3_advance_root.out.json"]
KIT_KEYS = ["marker", "round", "stage", "root", "gates", "refused"]


def main() -> int:
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        print(json.dumps({"refuse": [f"判据件/收口件缺失，页脚不许手补：{missing}"]}, ensure_ascii=False))
        return 1
    load = lambda f: json.loads((HERE / f).read_text(encoding="utf-8"))  # noqa: E731
    for f in REQUIRED:
        if load(f).get("refuse"):
            print(json.dumps({"refuse": [f"{f} 自带拒绝：{load(f)['refuse'][:2]}"]}, ensure_ascii=False))
            return 1
    arity, cogen = load("advance_r3_arity.json"), load("advance_r3_codegen_diff.json")
    face, locks = load("advance_r3_scope_face.json"), load("advance_r3_locks.json")
    corpus, base, irr = load("advance_r3_corpus.json"), load("advance_r3_baselines.json"), \
        load("advance_r3_irreversible.json")
    root_out, stage_out, root_close = (load("root_r3_advance.out.json"),
                                       load("close_r3_advance.out.json"),
                                       load("close_r3_advance_root.out.json"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    if root_close.get("root_final") != "已归档":
        print(json.dumps({"refuse": [f"根未归档：{root_close.get('root_final')}"]}, ensure_ascii=False))
        return 1
    if stage_out.get("failed"):
        print(json.dumps({"refuse": [f"叶失败：{stage_out['failed'][:2]}"]}, ensure_ascii=False))
        return 1
    if not base["three_systems_green"] or base["pytest"]["failed"]:
        print(json.dumps({"refuse": ["三套体系里有红，页脚不许写达标"]}, ensure_ascii=False))
        return 1
    if base["radius"]["unexpected"] or base["radius"]["missing"]:
        print(json.dumps({"refuse": [f"半径不自洽：{base['radius']['unexpected']} / {base['radius']['missing']}"]},
                         ensure_ascii=False))
        return 1
    if corpus.get("new_errors_outside_locks"):
        print(json.dumps({"refuse": [f"语料出现非 arity 新错误：{corpus['new_errors_outside_locks'][:3]}"]},
                         ensure_ascii=False))
        return 1

    frag = (HERE / "r3_advance_body.md").read_text(encoding="utf-8")
    sec = frag.split("## 七、本环自身缺陷", 1)
    if len(sec) != 2:
        print(json.dumps({"refuse": ["散文缺《七、本环自身缺陷》段"]}, ensure_ascii=False))
        return 1
    body6 = sec[1].split("## ", 1)[0]
    halves = re.split(r"操作[与和类]*[：:]", body6)
    judge_n = len(re.findall(r"^\d+\. ", halves[0], flags=re.M))
    op_n = len(re.findall(r"^\d+\. ", halves[1], flags=re.M)) if len(halves) > 1 else -1
    if judge_n < 1 or op_n < 1:
        print(json.dumps({"refuse": [f"《六》段分栏反解失败：judge={judge_n} op={op_n}"]}, ensure_ascii=False))
        return 1
    if "要谁裁决：" not in frag:
        print(json.dumps({"refuse": ["《七》段没有『要谁裁决』一句 ⇒ 裁决项计数反解不出来"]}, ensure_ascii=False))
        return 1
    decisions = len(re.findall(r"[；;]", frag.split("要谁裁决：", 1)[1].split("## ", 1)[0])) + 1

    seed_m = re.search(r"handoff=\S.*", spec["footer"], flags=re.S)
    if not seed_m:
        print(json.dumps({"refuse": ["spec['footer'] 缺 handoff= 段，无法安全幂等重写"]}, ensure_ascii=False))
        return 1
    seed = seed_m.group(0).strip()
    if re.search(r"(^|\s)(leaves|pytest|violation_cases|radius|irreversible)=", seed):
        print(json.dumps({"refuse": ["handoff 段里混进了 synthesized 键，拒绝叠加"]}, ensure_ascii=False))
        return 1

    sf, ef = base["suite"]["fields"], base["e2e"]["fields"]
    refused = root_close.get("refused") or []
    footer = (
        f"leaves={root_close['leaves_done']} floor_raised={base['floor_raised']} "
        f"pytest={base['pytest']['passed']} pytest_collected={base['pytest']['collected']} "
        f"locks={locks['new_locks']} locks_collected_in_full={base['pytest']['advance_locks_collected']} "
        f"violation_cases={arity['violation_total']} clean_green="
        f"{'yes' if arity['clean_cases_green'] else 'no'} "
        f"skipped_shapes={len(arity['skipped_shapes'])} "
        f"groups={locks['groups_ok']}/{locks['groups_total']} "
        f"identity={len(locks['identity'])} snap_left={len(locks['snap_left'])} "
        f"corpus_files={corpus['samples_scanned']} corpus_new_errors="
        f"{len(corpus['new_errors_outside_locks'])} arity_new={corpus['arity_errors_after']} "
        f"codegen_identical={'yes' if cogen['all_textual_identical'] else 'no'} "
        f"codegen_cases={cogen['sources_scanned']} "
        f"outside_radius={face['outside_total']} frozen_rows_touched={face['frozen_docs_modified']} "
        f"radius={base['radius']['count']} suite={sf.get('Passed')}/{sf.get('Total')} "
        f"e2e={ef.get('PASS')}/25 e2e_zero={ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')} "
        f"irreversible={irr['items']}(live={irr['live_probe_items']},derived={irr['derived_items']},"
        f"manifest={irr['manifest_items']}) executed={'none' if not irr['executed'] else ','.join(irr['executed'])} "
        f"audit_selftest={irr['self_test']['caught']} product_diff_lines={irr['changed_lines_in_product']} "
        f"revert_covered={locks['revert_covered']}/{locks['lock_names_total']} "
        f"uncovered={len(locks['revert_uncovered_locks'])} "
        f"test_names_gone={len(irr['test_names_disappeared'])} test_names_added={irr['test_names_added']} "
        f"lint_added_lines={base['lint']['product_face']['cypyc/analyzer/type_checker.py']['added_lines']} "
        f"lint_on_my_lines="
        f"{base['lint']['product_face']['cypyc/analyzer/type_checker.py']['violations_on_my_lines']} "
        f"lint_canary={base['lint']['canary']['cypyc/analyzer/type_checker.py:too_long']['on_my_lines']} "
        f"sensitivity={corpus['sensitivity_probe']['new_error_kinds']} "
        f"judge-defects={judge_n} op-defects={op_n} decisions={decisions} refusal_kinds={len(refused)} "
        f"measured_window={base['started_at_utc'].replace('+00:00', 'Z')}->"
        f"{base['finished_at_utc'].replace('+00:00', 'Z')} "
        f"generated_at={datetime.now(timezone.utc).isoformat(timespec='seconds')} " + seed
    )
    dup_kit = [k for k in KIT_KEYS if re.search(rf"(^|\s){k}=", footer)]
    if dup_kit:
        print(json.dumps({"refuse": [f"页脚重复了 report_kit 自己会印的键：{dup_kit}"]}, ensure_ascii=False))
        return 1
    seen = re.findall(r"(?:^|\s)([a-z][\w-]*)=", footer)
    twice = sorted({k for k in seen if seen.count(k) > 1})
    if twice:
        print(json.dumps({"refuse": [f"页脚同名键出现两次（不幂等）：{twice}"]}, ensure_ascii=False))
        return 1
    spec["footer"] = footer
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"footer": footer, "gates": len(spec["gates"]),
                      "counts": {"judge": judge_n, "op": op_n, "decisions": decisions}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
