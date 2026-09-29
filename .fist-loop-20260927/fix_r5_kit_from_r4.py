"""把 R5-寻虫 的链条驱动复制成 R5-修复 版，逐 token 改名并把残留逐行打印当 TODO。

为什么残留必须打出来：尺子从上一环抄过来时「上一环的事实」（件名、根号、卡号段、地板、报告名）
全都是主张，换错一处就是一条恒绿或恒红的判据。所以这里不假装复制完就能跑，改完由自证件拒判。
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAIN = [
    "hunt_r5_needles.py",
    "hunt_r5_drivers_lint.py",
    "hunt_r5_calllog_tally.py",
    "hunt_r5_self_audit.py",
    "hunt_r5_close_spec.py",
    "hunt_r5_report_spec.py",
    "hunt_r5_render_order.py",
    "hunt_r5_render_witness.py",
    "hunt_r5_progress.py",
    "hunt_r5_baselines.py",
]
TOKENS = [
    ("hunt_r5_", "fix_r5_"),
    ("close_r5_hunt_root", "close_r5_fix_root"),
    ("close_r5_hunt", "close_r5_fix"),
    ("spec_r5_hunt", "spec_r5_fix"),
    ("report_spec_r5_hunt", "report_spec_r5_fix"),
    ("r5_hunt_body", "r5_fix_body"),
    ("R5-寻虫", "R5-修复"),
    ("T0r96", "T0r110"),
    ("T0r96.", "T0r110."),
    ("20260928.15.10.00", "20260928.PENDING-NAME"),
    ("cypy-hunter", "cypy-fixer"),
    ("HUNT", "FIX"),
]
RESIDUE = re.compile(
    r"hunt_r5|R5-寻虫|T0r9\d|20260928\.15|PENDING-NAME|BUG-7\d|BUG-8\d|BUG-9\d"
    r"|1938|2002|\[selfdrive-hunt\]|cypy-hunter"
)


def main() -> int:
    made, skipped = [], []
    for name in CHAIN:
        src = HERE / name
        if not src.exists():
            print(f"MISS {name} ⇒ 源件不在盘上，这一环的尺子得亲笔")
            continue
        text = src.read_text(encoding="utf-8")
        for a, b in TOKENS:
            text = text.replace(a, b)
        dst = HERE / name.replace("hunt_r5_", "fix_r5_")
        if dst.exists():
            skipped.append(dst.name)
            continue
        dst.write_text(text, encoding="utf-8", newline="\n")
        made.append(dst.name)
        left = [
            (i + 1, ln.strip()[:120])
            for i, ln in enumerate(text.split("\n"))
            if RESIDUE.search(ln)
        ]
        print(f"{dst.name}: {len(text.splitlines())} 行，残留待改 {len(left)} 处")
        for n, ln in left[:20]:
            print(f"   {n}: {ln}")
    print(f"新建 {len(made)} 件 / 已存在跳过 {len(skipped)} 件：{skipped}")
    print(
        "TODO 必改：报告名 PENDING-NAME（渲时才定）、地板要从 fix_r5_baselines.json 的 floors 反解、"
        "卡号段与件清单要从 fix_r5_intake.json / 盘上现读而不是抄上一环"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
