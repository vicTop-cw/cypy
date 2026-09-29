"""把「核验件自己的结论」写进报告 —— 这件事本身是个自引用，所以做成不动点门。

流程：插入前先跑一次核验件（必须 `failed=0`）⇒ 拼段落 ⇒ 落盘 ⇒ **再跑一次**。
两次的结论行必须逐字相同，且第二次仍 `failed=0`；任一条不满足就把报告原样回滚，
因为那时候报告里那句"核验件说 0 失败"已经不成立了。
配套：`verify_r13_report.py` 的 `evidence_blob()` 对 `*selfcertify*` 只取 CONCLUSION 行 ——
否则核验件打印出来的 `ORPHAN_QUOTE` 行会被下一次运行读成"证据里已经有了"（尺子喂自己）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOGS = HERE / "logs"
VERIFY = HERE / "verify_r13_report.py"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r119-cypy-selfdrive-r13-report.md"

PLACEHOLDER = re.compile(r"(?ms)^- 核验件逐字结论：.*?(?=\n\n)")
OWN_BLOCK = re.compile(r"(?ms)^- 核验件逐字结论（src=.*?(?=\n### |\n---|\n## |\n- |\Z)")
CONCL = re.compile(r"(?m)^CONCLUSION checks=\d+ failed=\d+ .*$")


def run_once(tag: str) -> tuple:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(VERIFY)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = r.stdout + r.stderr
    hits = CONCL.findall(out)
    if len(hits) != 1:
        raise SystemExit(f"核验件 stdout 里结论行有 {len(hits)} 条 ⇒ 尺子坏了，不采信任何一次读数")
    line = hits[0]
    if "failed=0" not in line:
        bad = [ln for ln in out.splitlines() if ln.startswith("FAIL ")]
        print(out[-4000:])
        raise SystemExit(f"核验件未过（{len(bad)} 条 FAIL）⇒ 不回填报告：{bad}")
    return line, out, r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="a1")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    first, out1, _ = run_once(args.tag)
    src = REPORT.read_text(encoding="utf-8")
    old_own = OWN_BLOCK.search(src)
    if old_own and not args.refresh:
        print("CONCLUSION r13_self_certify landed=0 reason=已在账（覆盖用 --refresh）")
        return 0

    seg_lines = [
        f"- 核验件逐字结论（src=`logs/r13_selfcertify_{args.tag}.out`，由 `r13_self_certify.py` 回填）：",
        "  插入引用**前后各跑一次**，两次结论行逐字相同才算数 —— 这句引用一旦让核验件翻红，",
        "  报告就回到插入前那一版，而不是留一句「核验件全绿」的假话：",
        "",
        "```",
        first,
        "```",
        "",
        "  第二份同样的字节在同一次运行里（第二次跑的是已经带上这段引用的报告）⇒ 不是抄一次读数，是不动点。",
        "  核验件 stdout 的 `PASS`/`FAIL`/`ORPHAN_QUOTE` 行不进证据面（`evidence_blob` 对本件日志只取结论行），",
        "  否则我打印出来的孤儿会被下一次运行读成「证据里有了」。",
    ]
    seg = "\n".join(seg_lines)
    if old_own:
        new = src.replace(old_own.group(0), seg, 1)
    elif PLACEHOLDER.search(src):
        new = PLACEHOLDER.sub(seg, src, count=1)
    else:
        raise SystemExit("既无占位也无本件旧段 ⇒ 落点找不到，拒绝乱插")
    if new == src:
        raise SystemExit("替换后与原文逐字相同 ⇒ 假回填，拒收")

    # 先让第二遍**真的看见**带引用的报告，否则"不动点"只是把同一份报告读了两遍。
    log = LOGS / f"r13_selfcertify_{args.tag}.out"
    write_backup = HERE / f"T0r119-report.pre_selfcertify_{args.tag}.md"
    write_backup.write_text(src, encoding="utf-8", newline="\n")
    # 先把**第一遍**的输出占住这个文件名：第二遍核验件要在证据面里找到它自己那句结论，
    # 否则"引用核验件结论"这件事永远先红一次（顺序倒置）。跑完再用第二遍的输出覆盖。
    log.write_text(out1, encoding="utf-8", newline="\n")
    tmp = REPORT.with_suffix(".md.tmp")
    tmp.write_text(new, encoding="utf-8", newline="\n")
    os.replace(tmp, REPORT)
    second, out2, _ = run_once(args.tag)
    log.write_text(out2, encoding="utf-8", newline="\n")
    if second != first or "failed=0" not in second:
        tmp2 = REPORT.with_suffix(".md.rollback.tmp")
        tmp2.write_text(src, encoding="utf-8", newline="\n")
        os.replace(tmp2, REPORT)
        raise SystemExit(
            f"不动点不成立 ⇒ 报告回滚到 {write_backup.name}。first={first!r} second={second!r}"
        )
    print(f"CONCLUSION_STABLE r13_self_certify tag={args.tag} line_identical=True {second}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
