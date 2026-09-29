"""R4-修复：本轮亲笔的判据脚本自身要过仓库 lint 口径（line-length=100，硬错零容忍）。

与上一环同口径，但清单从**盘上现数**反解（上一环手写清单漏过整个目录 ⇒ 见"清单口径漏一个
目录"那条旧账）：凡 mtime 落在本环窗口内、名字以 `fix_r4_` 开头的脚本都算本轮亲笔。
**硬错**（E9/W605/F821/F7/F63）单独一栏，抓到即红；**软账**（E501/F401/E128…）只记账不判红
（存量债务不算在本环头上），但必须给条数，并配一条"合成违例必被抓 + 干净文件不误抓"的见证，
否则这一格是恒绿格。
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r4_drivers_lint.json"
PY = sys.executable
HARD = ("E9", "W605", "F821", "F7", "F63")
WINDOW_START = "2026-09-27T21:16:43"   # 本环根任务 publish 时刻（UTC）
REFUSE: list = []


def flake(paths: list) -> list:
    cmd = [PY, "-m", "flake8", "--max-line-length=100", "--extend-ignore=E203,W503,W505",
           *[str(p) for p in paths]]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    return [ln for ln in (p.stdout or "").splitlines() if ln.strip()]


def codes(lines: list) -> dict:
    out: dict = {}
    for ln in lines:
        m = re.search(r":\s+([EWFC]\d{2,4})\s", ln)
        key = m.group(1) if m else "?"
        out[key] = out.get(key, 0) + 1
    if "?" in out and out["?"] != len(lines):
        out["_parse_broken"] = out.pop("?")
    elif "?" in out:
        out["unparsed"] = out.pop("?")
    return dict(sorted(out.items()))


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    win = datetime.datetime.fromisoformat(WINDOW_START).replace(
        tzinfo=datetime.timezone.utc).timestamp()
    scanned = sorted(p.name for p in HERE.glob("fix_r4_*.py")
                     if p.stat().st_mtime >= win - 1)
    if not scanned:
        REFUSE.append(f"盘上没有 mtime 晚于 {WINDOW_START} 的 fix_r4_*.py ⇒ 清单为空，"
                      "这一格无从承重")
    # 声明面自证：glob 命中的脚本若比"我手写的清单"多，说明清单会漏档 —— 这里直接用 glob，
    # 并把逐文件的 mtime/字节留档，读报告的人可以复核口径本身。
    detail = [{"file": n,
               "bytes": (HERE / n).stat().st_size,
               "mtime_utc": datetime.datetime.fromtimestamp(
                   (HERE / n).stat().st_mtime, datetime.timezone.utc
               ).isoformat(timespec="seconds")} for n in scanned]
    lines = flake([HERE / n for n in scanned])
    hard = [ln for ln in lines if any(f" {c}" in ln for c in HARD)]
    soft = [ln for ln in lines if ln not in hard]

    tmp = Path(tempfile.mkdtemp(prefix="fixr4canary_", dir=str(HERE)))
    try:
        bad = tmp / "canary_bad.py"
        good = tmp / "canary_good.py"
        bad.write_text("def f():\n    return " + " + ".join(["1"] * 40)
                       + "  # 一条必然超 100 列的行\n", encoding="utf-8")
        good.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
        bad_lines, good_lines = flake([bad]), flake([good])
        caught = [ln for ln in bad_lines if "E501" in ln]
        false_pos = [ln for ln in good_lines if "E501" in ln]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not caught:
        REFUSE.append(f"见证失败：合成超长行没被抓到（{bad_lines[:2]}）⇒ lint 格恒绿")
    if false_pos:
        REFUSE.append(f"见证失败：干净文件被判 E501（{false_pos[:2]}）⇒ lint 口径在误抓")
    left = sorted(p.name for p in HERE.glob("*canary*"))
    if left:
        REFUSE.append(f"合成违例目录没清干净：{left}")

    doc = {"started": started, "window_start_utc": WINDOW_START,
           "scanned": scanned, "detail": detail, "drivers_scanned": len(scanned),
           "hard_violations": len(hard), "hard_lines": hard[:6],
           "soft_total": len(soft), "soft_codes": codes(soft),
           "canary": {"bad_caught": len(caught), "clean_false_positive": len(false_pos),
                      "bad_line_preview": (caught or ["未抓到"])[:1],
                      "leftover": left},
           "line_length_declared": 100,
           "note": "软账条数只降不升：上一环 hunt_r4_drivers_lint.json 的 soft_total 是基线",
           "refuse": REFUSE,
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    prev = HERE / "hunt_r4_drivers_lint.json"
    if prev.exists():
        base = json.loads(prev.read_text(encoding="utf-8")).get("soft_total")
        doc["previous_round_soft_baseline"] = base
        if isinstance(base, int) and len(soft) > base:
            REFUSE.append(f"驱动面软 lint 债上升：{base} → {len(soft)}（只降不升）")
            doc["refuse"] = REFUSE
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "drivers_scanned", "hard_violations",
                                          "soft_total", "soft_codes", "canary")},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
