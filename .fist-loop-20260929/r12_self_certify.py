"""R12 终局自证：报告里每条"逐字"引用与每个 `BUG-NNN`，回到**除报告以外**的证据件里找。

与引用核验件的分工：`verify_r12_report.py` 现算 32 条门并写 json；这份只跑两件独立小事
（"引用不许只在报告里存在" + "报告点名的编号必须都在账上"），用同一份证据口径但**不共享判定代码**，
这样两处同时坏的概率才低。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "reports" / "2026-09-29" / "T0r118-cypy-selfdrive-r12-report.md"
SUMMARY_RE = re.compile(
    r"`([^`\n]*(?:CONCLUSION|passed in|PASS=|accuracy=|Passed: |Failed: |Skipped: |_rc=|bad=\[|FILED |SEALED )[^`\n]*)`"
)
SUFFIXES = (".log", ".out", ".json")


def evidence_text() -> str:
    chunks = []
    for d in (HERE, HERE / "logs"):
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if not (p.is_file() and p.suffix in SUFFIXES):
                continue
            if p.name.startswith("verify_") and "report" in p.name:
                continue  # 自家输出不进自家证据池（见 R12 报告 §6.4 第 7 条）
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def receipt_values() -> list:
    acc = []

    def walk(node):
        acc.append(node)
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for f in sorted(HERE.glob("ring_r12_*.json")):
        walk(json.loads(f.read_text(encoding="utf-8")))
    return acc


def main() -> int:
    rep = REPORT.read_text(encoding="utf-8")
    blob = evidence_text()
    subs = receipt_values()
    claims = sorted(
        {m.group(1).replace("\\|", "|") for m in SUMMARY_RE.finditer(rep) if len(m.group(1)) > 10}
    )
    orphans = []
    for c in claims:
        if "\\d" in c:  # 模式字面串（§6.4 举例），不是日志原文
            continue
        if c in blob:
            continue
        try:
            obj = json.loads(c)
        except ValueError:
            orphans.append(c)
            continue
        if not any(obj == sv for sv in subs):
            orphans.append(c)
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    ids = set(re.findall(r"(?m)^## BUG-(\d+)", led))
    cited = {int(m) for m in re.findall(r"BUG-(\d{1,3})", rep)}
    missing = sorted(i for i in cited if str(i) not in ids)
    print("REPORT_BYTES", len(rep.encode("utf-8")), "CLAIMS", len(claims), "ORPHANS", len(orphans))
    for o in orphans[:6]:
        print("ORPHAN |", o)
    rc = 0 if not orphans and not missing else 1
    print(
        f"CONCLUSION self_certify claims={len(claims)} orphans={len(orphans)} cited={len(cited)} "
        f"missing_bug_ids={missing} receipts={len(list(HERE.glob('ring_r12_*.json')))} rc={rc}"
    )
    # 第二行是"可抄进行"的稳定形：只含不随报告字数漂移的判定量（`claims=` 那格会在我把上一行抄进
    # 报告后再 +1 ⇒ 逐字引用会变成自我追逐，所以稳定行里不放它）。
    print(
        f"CONCLUSION_STABLE self_certify orphans={len(orphans)} missing_bug_ids={missing} rc={rc}"
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
