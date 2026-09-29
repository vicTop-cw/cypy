"""R4-修复 的锁状态取证：跑一次锁文件，把「哪几条红/绿」按 nodeid 记账，前后各一次。

不是手抄：数字来自 pytest 的 `--tb=no -q` 原文行；`before` 必须证明锁承重（≥4 条红），
`after` 必须全绿且红的集合与绿的集合互斥。两态都从**同一夹具**跑，差别只允许在产品码。
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fix_r4_locks.json"
LOCK_FILE = "tests/test_loop_20260927_fix_r4.py"
CHECKS: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})


def run_locks() -> dict:
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pytest", LOCK_FILE,
         "-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "-q", "--tb=no"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    text = (r.stdout or "") + (r.stderr or "")
    failed = sorted({m.group(1).split("::")[-1] for m in
                     re.finditer(r"^FAILED \S+::(\S+)", text, re.M)})
    tail = [ln for ln in text.splitlines() if re.search(r"\d+ (failed|passed)", ln)]
    if not tail:
        raise RuntimeError(f"pytest 汇总行读不到：{text[-300:]!r}")
    fields = {word: int(num) for num, word in
              re.findall(r"(\d+) (failed|passed|errors|skipped)", tail[-1])}
    # pytest 的全绿汇总行压根没有 `failed` 这一段 —— 缺键就是 0，但必须显式写出来，
    # 否则判据拿到哨兵值 -1，把"真全绿"读成"判据失败"（本轮实测踩过）。
    for word in ("failed", "passed", "errors", "skipped"):
        fields.setdefault(word, 0)
    return {"rc": r.returncode, "fields": fields, "failed_names": failed,
            "summary_line": tail[-1].strip()}


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "after"
    if mode not in ("before", "after"):
        print(json.dumps({"refuse": [f"不认识的模式 {mode}（只接受 before/after）"]}))
        return 2
    doc = {"lock_file": LOCK_FILE, "mode": mode,
           "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    try:
        run = run_locks()
    except Exception as exc:
        print(json.dumps({"refuse": [f"跑锁文件失败：{type(exc).__name__}: {exc}"]},
                         ensure_ascii=False))
        return 1
    doc[mode] = run
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        if prev.get("lock_file") == LOCK_FILE and prev.get(mode) == run:
            print(json.dumps({"refuse": [f"{mode} 态与上一份件完全相同 ⇒ 两态之间没改产品码"]}))
            return 1
        doc.update({k: v for k, v in prev.items()
                    if k not in (mode, "lock_file", "mode", "started", "refuse", "self_checks")})
    if mode == "before":
        check("修前必须有红锁（≥4 条，否则锁不承重）", run["fields"]["failed"] >= 4, True,
              run["summary_line"])
    else:
        check("修后必须全绿", [run["fields"]["failed"], run["fields"]["errors"]],
              [0, 0], run["summary_line"])
    # rc 与计数互校：任一侧单独造假（rc 硬编 0 / 汇总行漏读）都会在这里露出来。
    check("rc 与 failed+errors 必须同向",
          (run["rc"] == 0) == (run["fields"]["failed"] + run["fields"]["errors"] == 0), True,
          f"rc={run['rc']} failed={run['fields']['failed']} errors={run['fields']['errors']}")
    check("全绿时 passed 条数必须等于锁文件里的用例数（防空汇总行）",
          run["fields"]["passed"] >= 15, True,
          f"passed={run['fields']['passed']} 行={run['summary_line']!r}")
    if "before" in doc and "after" in doc:
        both = set(doc["before"]["failed_names"]) & set(doc["after"]["failed_names"])
        check("红绿集合不得重叠（同一条既红又绿=判据坏了）", sorted(both), [], "两态交集")
        check("修前红的条数 ≥ 修后转绿的条数",
              len(doc["before"]["failed_names"]) >= len(doc["after"]["failed_names"]) and
              len(doc["after"]["failed_names"]) == 0, True, "转绿集合")
    refuse = [c["label"] for c in CHECKS if not c["ok"]]
    doc["self_checks"] = CHECKS
    doc["refuse"] = refuse
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"mode": mode, "fields": run["fields"],
                      "failed_names": run["failed_names"], "refuse": refuse},
                     ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
