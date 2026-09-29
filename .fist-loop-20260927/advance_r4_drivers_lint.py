"""R4-推进：本轮亲笔驱动件自身要过仓库 lint 口径（100 列、硬错零容忍、软账只减不增）。

清单从盘上现数（glob `advance_r4_*.py` + 共用的 `loop_kit.py`），不是手写名单；
`_patch_lint.py` 这类一次性件落在 `advance_r4_tmp/` 里，不进门禁口径但会在清单旁点名。
生成的锁文件 `tests/test_loop_20260927_advance_r4.py` 单独成栏：它的长行是 JSON dump 与表格行，
与手写散文不同口径，但**硬错照样零容忍**，并把「上一环同类文件 18 条超长行」作为只减不增的对照。
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
OUT = HERE / "advance_r4_drivers_lint.json"
PY = sys.executable
HARD = ("E9", "W605", "F821", "F7", "F63", "F841")
WINDOW_START = "2026-09-28T03:00:00"
LOCK_FILE = "tests/test_loop_20260927_advance_r4.py"
PREV_SOFT = HERE / "polish_r4_drivers_lint.json"
GEN_BASELINE = 18            # tests/test_loop_20260927_polish_r4.py 的超长行数（上一环同类件）
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
    if "?" in out:
        out["unparsed"] = out.pop("?")
    return dict(sorted(out.items()))


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    win = datetime.datetime.fromisoformat(WINDOW_START).replace(
        tzinfo=datetime.timezone.utc).timestamp()
    cands = list(HERE.glob("advance_r4_*.py")) + list(HERE.glob("loop_kit.py"))
    scanned = sorted(p.name for p in cands if p.stat().st_mtime >= win - 1)
    if not scanned:
        REFUSE.append(f"盘上没有 mtime 晚于 {WINDOW_START} 的 advance_r4_*.py ⇒ 清单为空，"
                      "这一格无从承重")
    if len(scanned) < 10:
        REFUSE.append(f"清单只有 {len(scanned)} 个文件，少于本轮实际写件数 ⇒ glob 口径可疑")
    detail = [{"file": n, "bytes": (HERE / n).stat().st_size,
               "mtime_utc": datetime.datetime.fromtimestamp(
                   (HERE / n).stat().st_mtime, datetime.timezone.utc
               ).isoformat(timespec="seconds")} for n in scanned]
    lines = flake([HERE / n for n in scanned])
    hard = [ln for ln in lines if any(f" {c}" in ln for c in HARD)]
    soft = [ln for ln in lines if ln not in hard]
    lock_lines = flake([ROOT / LOCK_FILE])
    lock_hard = [ln for ln in lock_lines if any(f" {c}" in ln for c in HARD)]
    lock_long = sum(1 for ln in lock_lines if "E501" in ln)

    tmp = Path(tempfile.mkdtemp(prefix="advancer4canary_", dir=str(HERE)))
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
    leftover = sorted(p.name for p in HERE.glob("*canary*"))
    if leftover:
        REFUSE.append(f"合成违例目录没清干净：{leftover}")
    if hard:
        REFUSE.append(f"驱动面有 {len(hard)} 条硬错（{'/'.join(HARD)}）：{hard[:3]}")
    if lock_hard:
        REFUSE.append(f"锁文件有 {len(lock_hard)} 条硬错：{lock_hard[:3]}")

    prev_soft = (json.loads(PREV_SOFT.read_text(encoding="utf-8"))["soft_total"]
                 if PREV_SOFT.exists() else None)
    doc = {"started": started, "window_start_utc": WINDOW_START,
           "scanned": scanned, "detail": detail, "drivers_scanned": len(scanned),
           "hard_violations": len(hard), "hard_lines": hard[:6],
           "soft_total": len(soft), "soft_codes": codes(soft),
           "previous_round_soft_baseline": prev_soft,
           "generated_lock": {"file": LOCK_FILE, "hard": len(lock_hard),
                              "e501": lock_long, "previous_ring_e501": GEN_BASELINE,
                              "note": "机器渲染件：表格行与 JSON dump 一行一条主张，"
                                      "超长行按同类的上一环件只减不增"},
           "canary": {"bad_caught": len(caught), "clean_false_positive": len(false_pos),
                      "bad_line_preview": (caught or ["未抓到"])[:1], "leftover": leftover},
           "line_length_declared": 100, "hard_codes": list(HARD),
           "note": "软账条数只降不升：上一环 verify/polish_r4_drivers_lint.json 的 soft_total 是基线；"
                   "口径含本轮改到的 loop_kit.py 使用方",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if prev_soft is not None and len(soft) > prev_soft:
        REFUSE.append(f"软账从 {prev_soft} 升到 {len(soft)} ⇒ 基线只降不升")
        doc["refuse"] = sorted(set(REFUSE))
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "scanned": len(scanned), "hard": len(hard),
                      "soft": len(soft), "lock_e501": lock_long, "lock_hard": len(lock_hard),
                      "canary": doc["canary"]["bad_caught"]}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
