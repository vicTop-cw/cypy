"""把 R4-寻虫 的全套驱动复制成 R5-寻虫 版，并逐 token 改名 + 打印残留当 TODO。

复制尺子时「上一轮的事实」一律是主张：换号段/换时刻/换件名之后，残留的每一处都必须手改，
改完由自证件拒判；所以这里把残留打出来，不假装复制完就能跑。
"""

import glob
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = sorted(Path(p).name for p in glob.glob(str(HERE / "hunt_r4_*.py")))
TOKENS = [
    ("hunt_r4_", "hunt_r5_"),
    ("close_r4_hunt", "close_r5_hunt"),
    ("spec_r4_hunt", "spec_r5_hunt"),
    ("report_spec_r4_hunt", "report_spec_r5_hunt"),
    ("r4_hunt_body", "r5_hunt_body"),
    ("R4-寻虫", "R5-寻虫"),
    ("R4-修复", "R5-修复"),
    ("T0r74", "T0rPENDING"),
    ("2026-09-27T19:38:23+00:00", "2026-09-28T14:05:00+00:00"),
    ("20260928.05.00.00", "20260928.14.05.00"),
    ('"pytest": 1938', '"pytest": 2002'),
    ("1938", "2002"),
    ("BUG-74", "BUG-PENDING-A"),
    ("BUG-75", "BUG-PENDING-B"),
    ("hunt_r4", "hunt_r5"),
]
RESIDUE = re.compile(
    r"hunt_r4|R4-寻虫|T0r74|1938|20260928\.05|polish_r4|advance_r4"
    r"|fix_r4|verify_r4|tests/test_loop_20260927_|BUG-\d\d"
)

for f in SRC:
    text = (HERE / f).read_text(encoding="utf-8")
    for a, b in TOKENS:
        text = text.replace(a, b)
    dst = HERE / f.replace("hunt_r4_", "hunt_r5_")
    if dst.exists():
        print("SKIP 已存在", dst.name)
        continue
    dst.write_text(text, encoding="utf-8", newline="\n")
    left = [
        (i + 1, ln.strip()[:112]) for i, ln in enumerate(text.split("\n")) if RESIDUE.search(ln)
    ]
    print(f"{dst.name}: {len(text.splitlines())} 行，残留待改 {len(left)} 处")
    for n, ln in left[:12]:
        print(f"   {n}: {ln}")
print(
    "TODO 必改：T0rPENDING（建树后回填）、BUG-PENDING-*（本轮新卡号）、"
    "FLOORS 要改成从 advance_r4_baselines.json 反解而不是手打"
)
sys.exit(0)
