"""把 R3-打磨 报告页脚写成**从判据件反解**的字符串，而不是手打数字。

规则与 R3-验证 一致但更严：任一判据件自带 refuse、任一收口件缺失、根未归档 ⇒ 直接拒，
页脚一个数字都不落。`decisions=` 与缺陷计数也从散文/清单反解，不靠回忆。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "report_spec_r3_polish.json"
REQUIRED = ["polish_r3_locks.json", "polish_r3_api.json", "polish_r3_docs.json",
            "polish_r3_lint.json", "polish_r3_eol.json", "polish_r3_lockproof.json",
            "polish_r3_baselines.json", "polish_r3_irreversible.json",
            "root_r3_polish.out.json", "close_r3_polish.out.json", "close_r3_polish_root.out.json"]
# 这些键由 report_kit 自己印（marker/round/stage/root/gates/refused），页脚串不许重复一遍
DUP_KEYS = ["marker", "round", "stage", "root", "gates", "refused"]


def main() -> int:
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        print(json.dumps({"refuse": [f"判据件/收口件缺失，页脚不许手补：{missing}"]}, ensure_ascii=False))
        return 1
    load = lambda f: json.loads((HERE / f).read_text(encoding="utf-8"))  # noqa: E731
    for f in REQUIRED:
        rec = load(f)
        if rec.get("refuse"):
            print(json.dumps({"refuse": [f"{f} 自带拒绝，页脚不许在拒状态下生成：{rec['refuse'][:2]}"]},
                             ensure_ascii=False))
            return 1
    locks, api, docs = load("polish_r3_locks.json"), load("polish_r3_api.json"), load("polish_r3_docs.json")
    lint, eol = load("polish_r3_lint.json"), load("polish_r3_eol.json")
    proof, base, irr = load("polish_r3_lockproof.json"), load("polish_r3_baselines.json"), \
        load("polish_r3_irreversible.json")
    root_out, stage_out, root_close = (load("root_r3_polish.out.json"),
                                       load("close_r3_polish.out.json"),
                                       load("close_r3_polish_root.out.json"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))

    if root_close.get("root_final") != "已归档":
        print(json.dumps({"refuse": [f"根未归档：{root_close.get('root_final')}"]}, ensure_ascii=False))
        return 1
    if stage_out.get("failed"):
        print(json.dumps({"refuse": [f"叶子失败：{stage_out['failed'][:2]}"]}, ensure_ascii=False))
        return 1
    if base["radius"]["unexpected"] or base["radius"]["missing"]:
        print(json.dumps({"refuse": [f"半径不自洽：unexpected={base['radius']['unexpected']} "
                                     f"missing={base['radius']['missing']}"]}, ensure_ascii=False))
        return 1
    if base["pytest"]["failed"] or not base["suite"]["green"] or not base["e2e"]["green"]:
        print(json.dumps({"refuse": ["三套体系里有红，页脚不许写达标"]}, ensure_ascii=False))
        return 1

    frag = (HERE / "r3_polish_body.md").read_text(encoding="utf-8")
    sec = frag.split("## 六、本环自身缺陷", 1)
    if len(sec) != 2:
        print(json.dumps({"refuse": ["散文片段缺《六》段 ⇒ 缺陷计数反解不出来"]}, ensure_ascii=False))
        return 1
    body6 = sec[1].split("## ", 1)[0]
    halves = re.split(r"操作[与和类]*[：:]", body6)
    judge_n = len(re.findall(r"^\d+\. ", halves[0], flags=re.M))
    op_n = len(re.findall(r"^\d+\. ", halves[1], flags=re.M)) if len(halves) > 1 else -1
    if judge_n < 1 or op_n < 1:
        print(json.dumps({"refuse": [f"《六》段分栏反解失败：judge={judge_n} op={op_n}"]}, ensure_ascii=False))
        return 1
    # 裁决项条数也从《七》段的"要谁裁决"一句里数分号，不手打
    sec7 = frag.split("## 七、汇报口径", 1)
    if len(sec7) != 2:
        print(json.dumps({"refuse": ["散文片段缺《七》段 ⇒ 裁决项计数反解不出来"]}, ensure_ascii=False))
        return 1
    ask = sec7[1].split("## ", 1)[0]
    tail = ask.split("要谁裁决：", 1)
    decisions = len(re.findall(r"[；;]", tail[1])) + 1 if len(tail) == 2 else -1
    if decisions < 1:
        print(json.dumps({"refuse": ["《七》段没数出裁决项"]}, ensure_ascii=False))
        return 1

    sf, ef = base["suite"]["fields"], base["e2e"]["fields"]
    refused = root_close.get("refused") or []
    # 幂等守卫：spec['footer'] 里只该留 handoff 段。上一版把整串 synthesized 又拼了一遍，
    # 于是同一行里出现两个 judge-defects=（旧值 7、新值 9），页脚自相矛盾 ⇒ 只取 handoff= 起的那段。
    seed_m = re.search(r"handoff=\S.*", spec["footer"], flags=re.S)
    if not seed_m:
        print(json.dumps({"refuse": ["spec['footer'] 里没有 handoff= 段 ⇒ 无法安全幂等重写"]},
                         ensure_ascii=False))
        return 1
    seed = seed_m.group(0).strip()
    if re.search(r"(^|\s)(leaves|pytest|judge-defects|e501)=", seed):
        print(json.dumps({"refuse": ["spec['footer'] 的 handoff 段里混进了 synthesized 键，拒绝叠加"]},
                         ensure_ascii=False))
        return 1
    footer = (
        f"leaves={root_close['leaves_done']} "
        f"new_locks={locks['new_locks']} locks_green_now={locks['collected_and_passed']}/{locks['declared_total']} "
        f"revert_groups={proof['revert_groups_ok']}/{proof['groups_total']} "
        f"control_green={'yes' if proof['control_groups_ok'] == 1 else 'no'} "
        f"uncovered={len(locks['revert_uncovered_locks'])} "
        f"api_public={'yes' if api['public_added'] else 'no'} api_cli_private={api['cli_private_occurrences']} "
        f"docs_three_way={'yes' if docs['flags_three_way'] else 'no'} "
        f"lint_hard={lint['hard_violations']['E9']}/{lint['hard_violations']['W605']}/{lint['hard_violations']['F821']} "
        f"e501={lint['e501_total_now']}/{lint['e501_total_before']} reduced={lint['reduced_by']} "
        f"eol_mixed={eol['mixed_files_now_count']} eol_drift={len(eol['line_ending_class_drift'])} "
        f"pytest={base['pytest']['passed']} pytest_collected={base['pytest']['collected']} "
        f"pytest_locks_collected={base['pytest']['polish_locks_collected']} "
        f"suite={sf.get('Passed')}/{sf.get('Total')} e2e={ef.get('PASS')}/25 "
        f"e2e_zero={ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')} "
        f"radius={base['radius']['count']} radius_unexpected={len(base['radius']['unexpected'])} "
        f"irreversible={irr['items']}(live={irr['live_probe_items']},derived={irr['derived_items']},"
        f"manifest={irr['manifest_items']}) "
        f"executed={'none' if not irr['executed'] else ','.join(irr['executed'])} "
        f"audit_selftest={irr['self_test']['caught']} "
        f"judge-defects={judge_n} op-defects={op_n} decisions={decisions} "
        f"refusal_kinds={len(refused)} "
        f"measured_window={base['started_at_utc'].replace('+00:00', 'Z')}->"
        f"{base['finished_at_utc'].replace('+00:00', 'Z')} "
        f"generated_at={datetime.now(timezone.utc).isoformat(timespec='seconds')} " + seed
    )
    dup = [k for k in DUP_KEYS if re.search(rf"(^|\s){k}=", footer)]
    if dup:
        print(json.dumps({"refuse": [f"页脚串里重复了 report_kit 自己会印的键：{dup}"]}, ensure_ascii=False))
        return 1
    seen = re.findall(r"(?:^|\s)([a-z][\w-]*)=", footer)
    twice = sorted({k for k in seen if seen.count(k) > 1})
    if twice:
        print(json.dumps({"refuse": [f"页脚里同一个键出现两次（synthesized 叠到了旧串上）：{twice}"]},
                         ensure_ascii=False))
        return 1
    spec["footer"] = footer
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"footer": footer, "gates": len(spec["gates"]),
                      "counts": {"judge": judge_n, "op": op_n, "decisions": decisions}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
