"""把上一环（R4-打磨）的收口件复制成 R4-推进 版，并逐 token 改名。

复制尺子时「上一轮的事实」一律是主张：脚本把所有 `polish`→`advance`、号段、时刻换掉之后，
再扫一遍残留并把每条残留打印出来当 TODO 清单——这些位置必须手改，改完由自证件拒判。
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ["polish_r4_self_audit.py", "polish_r4_close_spec.py", "polish_r4_render_order.py",
         "polish_r4_progress.py", "polish_r4_calllog_tally.py"]
TOKENS = [("polish_r4_", "advance_r4_"), ("close_r4_polish", "close_r4_advance"),
          ("spec_r4_polish", "spec_r4_advance"),
          ("report_spec_r4_polish", "report_spec_r4_advance"),
          ("r4_polish_body", "r4_advance_body"), ("R4-打磨", "R4-推进"), ("R4-验证", "R4-打磨"),
          ("T0r90", "T0r93"), ("cypy-polisher", "cypy-advancer"),
          ("2026-09-28T01:41:16", "2026-09-28T03:00:00"),
          ("20260928.10.35.00", "20260928.11.55.00"),
          ("polish", "advance"), ("打磨", "推进")]

for f in FILES:
    src = HERE / f
    dst = HERE / f.replace("polish_r4_", "advance_r4_")
    text = src.read_text(encoding="utf-8")
    for a, b in TOKENS:
        text = text.replace(a, b)
    if dst.exists():
        print("SKIP 已存在", dst.name)
        continue
    dst.write_text(text, encoding="utf-8", newline="\n")
    left = [(i + 1, ln.strip()[:110]) for i, ln in enumerate(text.split("\n"))
            if re.search(r"polish|打磨|USAGE\.md|APPENDIX|BUG-6[1-9]|BUG-7[0-3]|"
                         r"verify_r4_|docs/|tests/test_loop_20260927_", ln)]
    print(f"{dst.name}: {len(text.splitlines())} 行，残留待改 {len(left)} 处")
    for n, ln in left[:14]:
        print(f"   {n}: {ln}")
sys.exit(0)
