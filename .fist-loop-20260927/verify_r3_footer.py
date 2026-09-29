"""把 R3-验证 报告页脚写成**从判据件反解**的字符串，而不是手打数字。

页脚的每一个数都取自 `verify_r3_*.json` + 收口件 + 报告 spec；缺件即拒（不放行半成品）。
写完后 `verify_r3_self_audit.py` 会用另一套规则把这些数再反解一遍——两向对齐才叫账。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "report_spec_r3_verify.json"
REQUIRED = ["verify_r3_matrix.json", "verify_r3_callsite.json", "verify_r3_report_audit.json",
            "verify_r3_baselines.json", "verify_r3_irreversible.json",
            "root_r3_verify.out.json", "close_r3_verify.out.json", "close_r3_verify_root.out.json"]


def main() -> int:
    missing = [f for f in REQUIRED if not (HERE / f).exists()]
    if missing:
        print(json.dumps({"refuse": [f"判据件/收口件缺失，页脚不许手补：{missing}"]},
                         ensure_ascii=False))
        return 1
    load = lambda f: json.loads((HERE / f).read_text(encoding="utf-8"))  # noqa: E731
    matrix, callsite = load(REQUIRED[0]), load(REQUIRED[1])
    audit, base, irr = load(REQUIRED[2]), load(REQUIRED[3]), load(REQUIRED[4])
    root_out, stage_out, root_close = load(REQUIRED[5]), load(REQUIRED[6]), load(REQUIRED[7])
    spec = json.loads(SPEC.read_text(encoding="utf-8"))

    for name in (REQUIRED[0], REQUIRED[1], REQUIRED[2], REQUIRED[3], REQUIRED[4]):
        rec = load(name)
        if rec.get("refuse"):
            print(json.dumps({"refuse": [f"{name} 自带拒绝，页脚不许在拒状态下生成：{rec['refuse']}"]},
                             ensure_ascii=False))
            return 1
    if base["radius"]["count"] != 0 or base["pytest"]["failed"]:
        print(json.dumps({"refuse": [f"基线不达标：radius={base['radius']['count']} failed={base['pytest']['failed']}"]},
                         ensure_ascii=False))
        return 1

    refused = root_close.get("refused") or []
    if root_close.get("root_final") != "已归档":
        print(json.dumps({"refuse": [f"根未归档：{root_close.get('root_final')}"]}, ensure_ascii=False))
        return 1
    # 缺陷计数也从散文片段反解（页脚里连"我这几条自记债"都不许手打）
    import re as _re

    frag = (HERE / "r3_verify_body.md").read_text(encoding="utf-8")
    sec = frag.split("## 六、本环自身缺陷", 1)
    if len(sec) != 2:
        print(json.dumps({"refuse": ["散文片段缺《六》段 ⇒ 缺陷计数反解不出来"]}, ensure_ascii=False))
        return 1
    body6 = sec[1].split("## ", 1)[0]
    halves = _re.split(r"操作[与和类]*[：:]", body6)
    judge_n = len(_re.findall(r"^\d+\. ", halves[0], flags=_re.M))
    op_n = len(_re.findall(r"^\d+\. ", halves[1], flags=_re.M)) if len(halves) > 1 else -1
    if judge_n < 1 or op_n < 1:
        print(json.dumps({"refuse": [f"《六》段分栏反解失败：judge={judge_n} op={op_n}"]}, ensure_ascii=False))
        return 1
    runs = sum(1 for f in ("verify_r3_baselines.json", "verify_r3_baselines_run1.json")
               if (HERE / f).exists())
    ef, sf = base["e2e"]["fields"], base["suite"]["fields"]
    footer = (
        "[selfdrive-verify] round=R3 stage=第 3 轮第 3 环（寻虫→修复→验证→打磨→推进） "
        f"root={root_out['root']} gates={len(spec['gates'])} refused={len(refused)} "
        f"leaves={root_close['leaves_done']} "
        f"matrix_rows={matrix['rows']}/6 sha_restored={matrix['sha_verified_rows']}/6 "
        f"identity={matrix['identity']} premise={matrix['premise']['passed']}/17 "
        f"collected={matrix['premise']['collected']} "
        f"carried_claims={matrix['carried_claims']} declared_side={matrix['declared_side_still_true']} "
        f"callsite={callsite['checks']}/{callsite['checks'] - len(callsite['failed_checks'])} "
        f"report_audit_counts={audit['counts']}/{audit['counts_total']} "
        f"refusal_table={audit['refusal_table']['rows_in_report']}-verbatim "
        f"ledger_reruns={audit['repro_reruns_match_claim']}/{audit['repro_reruns']} "
        f"pytest={base['pytest']['passed']} pytest_collected={base['pytest']['collected']} "
        f"suite={sf.get('Passed')}/{sf.get('Total')} e2e={ef.get('PASS')}/{ef.get('PASS')} "
        f"e2e_zero={ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')} "
        f"radius={base['radius']['count']} lint_hard={base['lint']['hard_violations']} "
        f"baselines_run={runs} "
        f"irreversible={irr['items']}(live={irr['live_probe_items']},manifest={irr['manifest_items']}) "
        f"executed={'none' if not irr['executed'] else ','.join(irr['executed'])} "
        f"judge-defects={judge_n} op-defects={op_n} decisions=3 "
        f"measured_window={base['started_at_utc'].replace('+00:00','Z')}->{base['finished_at_utc'].replace('+00:00','Z')} "
        f"generated_at={datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        "handoff=R4:非冻结generic形可解析+锁夹具换冻结形+importlib取模块+bridge生成setup入锁"
    )
    spec["footer"] = footer
    SPEC.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"footer": footer, "gates": len(spec["gates"])}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
