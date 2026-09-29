"""本环 9 个驱动文件的 lint 现状：硬门照旧（E9/W605/F821，200 列），软违例逐码计数并**存成债**。

为什么要单独出这一件：`advance_r3_*.py` 这批驱动按历轮沿用的口径只跑硬码门（写完就 byte-compile 过），
行长/F401 这类软码没人数过——本轮把它们数出来存盘，R4/R5 的打磨环才有"只减不增"的对照物。
扫描器自己配一条对照：往临时文件写一条已知超长行，必须被数到；数不到就是扫描器坏了，而不是债没了。
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
OUT = HERE / "advance_r3_driver_lint.json"
REFUSE: list = []


def flake(args: list) -> list:
    p = subprocess.run([PY, "-X", "utf8", "-m", "flake8", *args], cwd=str(ROOT),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    return [ln for ln in p.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def codes(rows: list) -> dict:
    tally: dict = {}
    for ln in rows:
        parts = ln.split(":")
        if len(parts) < 4:
            REFUSE.append(f"flake8 行解析不出来：{ln[:90]}")
            continue
        tally[parts[3].split()[0]] = tally.get(parts[3].split()[0], 0) + 1
    return tally


def main() -> int:
    targets = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in HERE.glob("advance_r3_*.py"))
    hard = flake(["--select=E9,W605,F821", "--max-line-length=200", *targets])
    if hard:
        REFUSE.append(f"驱动有硬违例：{hard[:4]}")
    soft = flake(["--max-line-length", "100", *targets])
    tally = codes(soft)
    per_file = {}
    for ln in soft:
        f = ln.split(":")[0].replace("\\", "/")
        per_file[f] = per_file.get(f, 0) + 1
    # 扫描器对照：已知超长行必须被数到（写完即删，不留残留）
    canary = HERE / "tmp_advance" / "driver_lint_canary.py"
    canary.parent.mkdir(exist_ok=True)
    canary.write_text("_CANARY = '" + "z" * 140 + "'\n", encoding="utf-8", newline="\n")
    caught = [ln for ln in flake(["--max-line-length", "100",
                                  str(canary.relative_to(ROOT)).replace("\\", "/")])
              if "E501" in ln]
    canary.unlink(missing_ok=True)
    if not caught:
        REFUSE.append("对照失败：已知 140 字符的行没被 flake8 数到 ⇒ 本件的软违例计数不可信")
    left = sorted(p.name for p in (HERE / "tmp_advance").glob("*canary*"))
    if left:
        REFUSE.append(f"对照文件没清干净：{left}")
    doc = {"drivers": len(targets), "files": targets, "hard_violations": len(hard),
           "soft_total": len(soft), "soft_by_code": tally, "soft_by_file": per_file,
           "canary_caught": len(caught), "canary_left": left,
           "policy_note": "驱动口径=E9/W605/F821@200（沿用 R2 起的选择），软码本轮只计数不清理",
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "refuse": REFUSE}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("drivers", "hard_violations", "soft_total",
                                          "soft_by_code", "canary_caught", "refuse")},
                     ensure_ascii=False, indent=1))
    return 1 if REFUSE else 0


if __name__ == "__main__":
    sys.exit(main())
