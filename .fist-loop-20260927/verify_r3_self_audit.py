"""R3-验证 的自我审计：拿审计上一环的同一把尺子量本轮报告。

页脚每条数字都必须能在五张判据件（或报告正文自身）里反解出相等的值；
任一条不符 ⇒ 本件 rc=1，报告不得发出。上一环我怎么要求别人，这一环同样要求自已。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "memory" / "reviews" / "20260928.01.25.00.md"
ROWS: list = []
REFUSE: list = []


def art(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def check(claim, reported, recomputed, source, ok=None):
    equal = (str(reported) == str(recomputed)) if ok is None else bool(ok)
    ROWS.append({"claim": claim, "reported": reported, "recomputed": recomputed,
                 "source": source, "equal": equal})
    if not equal:
        REFUSE.append(f"[自审] {claim}：页脚说 {reported!r}，判据件算得 {recomputed!r}（{source}）")


def main() -> int:
    text = REPORT.read_text(encoding="utf-8")
    m = re.search(r"\[selfdrive-verify\][^\n]*", text)
    if not m:
        print(json.dumps({"refuse": ["报告里找不到 [selfdrive-verify] 页脚"]}, ensure_ascii=False))
        return 1
    footer = m.group(0)
    foot = dict(re.findall(r"([\w-]+)=([^\s]+)", footer))
    matrix = art("verify_r3_matrix.json")
    callsite = art("verify_r3_callsite.json")
    audit = art("verify_r3_report_audit.json")
    base = art("verify_r3_baselines.json")
    irr = art("verify_r3_irreversible.json")
    spec = art("report_spec_r3_verify.json")

    check("matrix_rows", foot.get("matrix_rows"), f"{matrix['rows']}/6", "verify_r3_matrix.json:rows")
    check("sha_restored", foot.get("sha_restored"),
          f"{matrix['sha_verified_rows']}/6", "verify_r3_matrix.json:sha_verified_rows")
    check("identity", foot.get("identity"), matrix["identity"], "verify_r3_matrix.json:identity")
    check("premise", foot.get("premise"), f"{matrix['premise']['passed']}/17",
          "verify_r3_matrix.json:premise.passed")
    check("premise.collected", foot.get("collected"), matrix["premise"]["collected"],
          "verify_r3_matrix.json:premise.collected（--collect-only 实收）")
    check("callsite", foot.get("callsite"),
          f"{callsite['checks']}/{callsite['checks'] - len(callsite['failed_checks'])}",
          "verify_r3_callsite.json:checks 与非空 failed_checks")
    check("report_audit_counts", foot.get("report_audit_counts"),
          f"{audit['counts']}/{audit['counts_total']}", "verify_r3_report_audit.json")
    check("refusal_table", foot.get("refusal_table"),
          f"{audit['refusal_table']['rows_in_report']}-verbatim",
          "报告《被拒原文》表行数；missing/extra 均为空",
          ok=(str(foot.get("refusal_table")).startswith(str(audit["refusal_table"]["rows_in_report"]))
              and not audit["refusal_table"]["missing"] and not audit["refusal_table"]["extra"]))
    check("ledger_reruns", foot.get("ledger_reruns"),
          f"{audit['repro_reruns_match_claim']}/{audit['repro_reruns']}",
          "verify_r3_report_audit.json:repro_reruns*")
    check("carried_claims", foot.get("carried_claims"), matrix["carried_claims"],
          "verify_r3_matrix.json:carried_claims")
    check("declared_side", foot.get("declared_side"), matrix["declared_side_still_true"],
          "verify_r3_matrix.json:declared_side_still_true")
    check("radius", foot.get("radius"), base["radius"]["count"],
          "verify_r3_baselines.json:radius.count")
    check("irreversible", foot.get("irreversible"),
          f"{irr['items']}(live={irr['live_probe_items']},manifest={irr['manifest_items']})",
          "verify_r3_irreversible.json")
    check("executed", foot.get("executed"), "none" if not irr["executed"] else ",".join(irr["executed"]),
          "verify_r3_irreversible.json:executed")
    check("pytest", foot.get("pytest"), base["pytest"]["passed"], "verify_r3_baselines.json:pytest.passed")
    check("pytest_collected", foot.get("pytest_collected"), base["pytest"]["collected"],
          "verify_r3_baselines.json:pytest.collected")
    sf = base["suite"]["fields"]
    check("suite", foot.get("suite"), f"{sf.get('Passed')}/{sf.get('Total')}", "…:suite.fields")
    ef = base["e2e"]["fields"]
    check("e2e", foot.get("e2e"), f"{ef.get('PASS')}/{ef.get('PASS')}", "…:e2e.fields（FAIL/WARN/UNREG 另判）")
    check("e2e_zero", foot.get("e2e_zero"),
          f"{ef.get('FAIL')}{ef.get('WARN')}{ef.get('UNREG/RUNFAIL')}", "e2e 的三个零格拼接")
    runs = sum(1 for f in ("verify_r3_baselines.json", "verify_r3_baselines_run1.json")
               if (HERE / f).exists())
    check("baselines_run", foot.get("baselines_run"), runs,
          "verify_r3_baselines.json + _run1.json 存在数（run1 必须是恒真格那一轮）")
    check("gates", foot.get("gates"), len(spec["gates"]), "report_spec_r3_verify.json:gates 条数")
    check("lint_hard", foot.get("lint_hard"), base["lint"]["hard_violations"],
          "verify_r3_baselines.json:lint.hard_violations")
    try:
        root_out = art("root_r3_verify.out.json")
        root_close = art("close_r3_verify_root.out.json")
        check("root", foot.get("root"), root_out["root"], "root_r3_verify.out.json:root")
        check("refused", foot.get("refused"), len(root_close["refused"]),
              "close_r3_verify_root.out.json:refused")
        check("leaves_done", foot.get("leaves"), root_close["leaves_done"],
              "close_r3_verify_root.out.json:leaves_done")
    except FileNotFoundError as exc:
        REFUSE.append(f"收口件缺失 ⇒ 自审不许在收口前放行：{exc}")

    body = text.split("## 六、本环自身缺陷", 1)
    if len(body) != 2:
        REFUSE.append("报告缺《六》段 ⇒ 缺陷计数无法反解")
    else:
        sec = body[1].split("## ", 1)[0]
        halves = re.split(r"操作[与和类]*[：:]", sec)
        judge = len(re.findall(r"^\d+\. ", halves[0], flags=re.M))
        op = len(re.findall(r"^\d+\. ", halves[1], flags=re.M)) if len(halves) > 1 else -1
        check("judge-defects", foot.get("judge-defects"), judge, "报告《六》段『判据与工具类』编号条数")
        check("op-defects", foot.get("op-defects"), op, "报告《六》段『操作』编号条数")

    doc = {"refuse": REFUSE, "checks": len(ROWS),
           "all_equal": 1 if all(r["equal"] for r in ROWS) and ROWS else 0,
           "mismatched": [r["claim"] for r in ROWS if not r["equal"]],
           "detail": ROWS, "footer_raw": footer}
    (HERE / "verify_r3_self_audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "checks", "all_equal", "mismatched")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
