"""R4-寻虫：本轮亲笔的判据脚本自身要过仓库 lint 口径（line-length=100，硬错零容忍）。

口径与上一环一致：**硬错**（E9/W605/F821 之类）单独一栏，抓到就红；**软账**（E501/F401/E128…）
只记账不判红（存量债务不能算在本环头上），但必须给出条数，并且配一条"合成违例必被抓"的见证，
否则这一格就是恒绿格。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "hunt_r4_drivers_lint.json"
PY = sys.executable
HARD = ["E9", "W605", "F821", "F7", "F63"]
DRIVERS = ["hunt_r4_probe.py", "hunt_r4_faces.py", "hunt_r4_cards.py", "hunt_r4_confirm.py",
           "hunt_r4_witness.py", "hunt_r4_declared.py", "hunt_r4_dedup.py", "hunt_r4_repro.py",
           "hunt_r4_filed.py", "hunt_r4_baselines.py", "hunt_r4_ledger3way.py"]
REFUSE: list = []


def flake(paths: list, extra: list | None = None) -> list:
    cmd = [PY, "-m", "flake8", "--max-line-length=100", "--extend-ignore=E203,W503,W505",
           *(extra or []), *[str(p) for p in paths]]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    return [l for l in (p.stdout or "").splitlines() if l.strip()]


def tally(lines: list) -> dict:
    """flake8 行的路径在 Windows 上带盘符冒号 ⇒ 只能按 `: E501 ` 这种模式取码，不能按 split 下标。"""
    import re
    codes: dict = {}
    for l in lines:
        m = re.search(r":\s+([EWFC]\d{2,4})\s", l)
        code = m.group(1) if m else "?"
        codes[code] = codes.get(code, 0) + 1
    if "?" in codes and len(lines) != codes["?"]:
        codes["_parse_broken"] = codes.pop("?")
    return dict(sorted(codes.items()))


def main() -> int:
    missing = [d for d in DRIVERS if not (HERE / d).exists()]
    if missing:
        REFUSE.append(f"清单里的脚本不在盘上（口径漏档就是无人认领的改动）：{missing}")
    hard = [l for l in flake([HERE / d for d in DRIVERS if d not in missing])
            if any(f" {c}" in l for c in HARD)]
    soft = [l for l in flake([HERE / d for d in DRIVERS if d not in missing])
            if not any(f" {c}" in l for c in HARD)]

    tmp = Path(tempfile.mkdtemp(prefix="r4canary_", dir=str(ROOT / ".fist-loop-20260927")))
    bad = tmp / "canary_bad.py"
    good = tmp / "canary_good.py"
    bad.write_text("def f():\n    return " + " + ".join(["1"] * 40) + "  # 一条必然超 100 列的行\n",
                   encoding="utf-8")
    good.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
    bad_lines = flake([bad])
    good_lines = flake([good])
    caught = [l for l in bad_lines if "E501" in l]
    if not caught:
        REFUSE.append(f"见证失败：合成超长行没被抓到（{bad_lines[:2]}）⇒ lint 格是恒绿的")
    if [l for l in good_lines if "E501" in l]:
        REFUSE.append(f"见证失败：干净文件被判 E501（{good_lines[:2]}）⇒ lint 口径在误抓")
    shutil.rmtree(tmp, ignore_errors=True)
    left = sorted(p.name for p in HERE.glob("tmp_*") if "r4canary" in p.name)
    if left:
        REFUSE.append(f"合成违例目录没清干净：{left}")

    doc = {"refuse": REFUSE, "drivers_scanned": len(DRIVERS) - len(missing),
           "hard_violations": len(hard), "hard_lines": hard[:6],
           "soft_total": len(soft), "soft_codes": tally(soft),
           "canary": {"bad_caught": len(caught), "clean_false_positive": 0
                      if not [l for l in good_lines if "E501" in l] else 1},
           "line_length_declared": 100, "canary_left": left}
    (HERE / "hunt_r4_drivers_lint.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "drivers_scanned", "hard_violations",
                                          "soft_total", "soft_codes", "canary", "canary_left")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
