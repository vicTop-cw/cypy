"""把 `--stage close` 的**逐字**回执补进报告 §6.2。

顺序由 L4 产物门决定：报告先落盘 ⇒ 才允许收根 ⇒ 再把收口回执原文补进那一节。
所以本件是"回填"，不是"生成报告"：它只搬运回执里现成的字节，一个数字都不自己算。
被拒文案一律整条搬（驱动件打印时的 `[:300]` 会让引用看着完整实则不可复核，那截断已另行拆掉）。
幂等：只回收自己那段（按 `src=` 行认），别人的正文不碰。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOGS = HERE / "logs"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r119-cypy-selfdrive-r13-report.md"

PLACEHOLDER = re.compile(r"(?ms)^- 收口腿逐字回执：.*?(?=\n\n)")
OWN_BLOCK = re.compile(r"(?ms)^- 收口腿逐字回执（src=.*?(?=\n### |\n---|\n## |\n- |\Z)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="收口腿的 tag：读 logs/r13_ring_close_<tag>.out")
    ap.add_argument("--refresh", action="store_true", help="覆盖自己上一版回填")
    args = ap.parse_args()

    out_log = LOGS / f"r13_ring_close_{args.tag}.out"
    receipt = HERE / f"ring_r13_close_{args.tag}.json"
    for p in (out_log, receipt):
        if not p.exists():
            raise SystemExit(f"证据件缺失：{p.name} ⇒ 不回填（宁缺不造）")
    txt = out_log.read_text(encoding="utf-8", errors="replace")
    concl = [ln for ln in txt.splitlines() if ln.startswith("CONCLUSION stage=close")]
    if len(concl) != 1:
        raise SystemExit(
            f"{out_log.name} 里 stage=close 的结论行有 {len(concl)} 条 ⇒ 取哪条都不诚实"
        )
    line = concl[0]
    m = re.search(r"root_status=(\S+) rollup=(\{.*?\}) non_closed=(\[[^\]]*\])", line)
    if not m:
        raise SystemExit(
            "结论行里解不出 root_status/rollup/non_closed ⇒ 结论行形状变了，本件跟不上就不写"
        )
    ref = json.loads(receipt.read_text(encoding="utf-8"))
    refusals = [r["reply_verbatim"] for r in ref.get("refusals", [])]
    idem = [r["reply_verbatim"] for r in ref.get("idempotent", [])]

    block = [
        f"- 收口腿逐字回执（src=`{out_log.name}`，由 `fill_r13_report.py` 在收根之后回填；"
        f"回执全文在 `ring_r13_close_{args.tag}.json`，本件不截断）：",
        "",
        "```",
        line,
        "```",
        "",
        f"  `root_status={m.group(1)}`、树内终态 {m.group(2)}、未闭合 {m.group(3)}；"
        f"被拒 {len(refusals)} 条、幂等命中 {len(idem)} 条"
        "（条数不为 0 时逐条整条列在下面，绝不省略号）。",
    ]
    for blob in refusals:
        block += ["", "```", f"REFUSED | {blob}", "```"]
    for blob in idem:
        block += ["", "```", f"IDEMPOTENT | {blob}", "```"]
    block.append("")
    seg = "\n".join(block)

    src = REPORT.read_text(encoding="utf-8")
    if OWN_BLOCK.search(src) and not args.refresh:
        print("CONCLUSION fill_r13_report landed=0 reason=已在账（覆盖用 --refresh）")
        return 0
    if OWN_BLOCK.search(src):
        killed = OWN_BLOCK.search(src).group(0)
        if "fill_r13_report" not in killed:
            raise SystemExit("要回收的那段不含本件标记 ⇒ 停手不动报告")
        new = src.replace(killed, seg, 1)
    elif PLACEHOLDER.search(src):
        new = PLACEHOLDER.sub(seg, src, count=1)
    else:
        raise SystemExit("既无占位也无本件旧段 ⇒ 落点找不到，拒绝乱插")

    tmp = REPORT.with_suffix(".md.tmp")
    tmp.write_text(new, encoding="utf-8", newline="\n")
    back = tmp.read_text(encoding="utf-8")
    checks = {
        "concl_once": back.count(line) == 1,
        "placeholder_gone": "待 `--stage close` 之后" not in back,
        "refusals_verbatim": all(f"REFUSED | {b}" in back for b in refusals),
        "own_marker_present": "fill_r13_report.py" in back,
        "no_ellipsis_in_block": "…" not in seg,
        "grew": len(back) > len(src),
    }
    if not all(checks.values()):
        os.remove(tmp)
        raise SystemExit(f"回填自证不过 ⇒ 不落盘：{json.dumps(checks, ensure_ascii=False)}")
    backup = HERE / "T0r119-report.pre_fill.md"
    if not backup.exists():
        backup.write_text(src, encoding="utf-8", newline="\n")
    os.replace(tmp, REPORT)
    print(
        f"CONCLUSION fill_r13_report tag={args.tag} landed=1 refusals={len(refusals)} "
        f"idempotent={len(idem)} refresh={args.refresh} bytes={len(src)}->{len(back)} "
        f"self_check={json.dumps(checks, ensure_ascii=False)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
