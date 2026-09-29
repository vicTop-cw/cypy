"""R4-打磨 法③：账面卫生只做**追加**，并用逐行差分证明「零删改」。

8 张缺 `- task_id:` 的卡（BUG-44..51）逐张去 `tasks(ns='bugs')` 反查认领人。
本轮实测：8 张**一张都反查不到**——它们只在 md 里记过，从没进过 bugs 树。
所以补记写成「未派单 + 理由」，而不是编一个 task_id，也不是去改库（服务端写入不可撤回）：

* 每条补记都是**新增行**，差分里不许出现任何 `-` 行；
* 补记后「格式正确的 task_id（`T0r\\d+`）」数量不许虚增——不许把 `未派单` 冒充成有号；
* canary：拿一份被删掉一行的内存副本喂给同一个差分函数，必须报违例（否则这条门恒绿）。
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "polish_r4_ledger.json"
DB = (ROOT / "fist-mbt.db").as_posix()
NS = "bugs"
CHECKS: list = []
REFUSE: list = []
NOTE_RE = re.compile(r"^- task_id: (.*)$", re.M)
VALID_ID = re.compile(r"^T0r\d+$")


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def cards(text: str) -> dict:
    out = {}
    for m in re.finditer(r"^## (BUG-\d+)\b([\s\S]*?)(?=^## BUG-|\Z)", text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def diff_counts(before: str, after: str) -> dict:
    d = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0))
    added = [x for x in d if x.startswith("+") and not x.startswith("+++")]
    removed = [x for x in d if x.startswith("-") and not x.startswith("---")]
    return {"added": len(added), "removed": len(removed),
            "removed_samples": removed[:3], "added_samples": added[:3]}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    live_now = LEDGER.read_text(encoding="utf-8")
    before_copy = HERE / "verify_r4_tmp" / "bugs.md.before_polish"
    # 幂等：补记只许发生一次。第二次跑时盘上已有「未派单」注，就取归档的改前副本当 before，
    # 差分仍然对着真实的改前状态算（否则「恰有 8 张缺行」这条会把自己判成红——假红）。
    already_applied = bool(re.search(r"^- task_id: 未派单", live_now, re.M))
    if before_copy.exists():
        before = before_copy.read_text(encoding="utf-8")
    elif already_applied:
        print(json.dumps({"refuse": ["盘上已有补记而改前副本缺失 ⇒ 无法核对「零删改」"]},
                         ensure_ascii=False))
        return 1
    else:
        before = live_now
        before_copy.write_text(before, encoding="utf-8", newline="\n")
    before_sha = hashlib.sha256(before.encode("utf-8")).hexdigest()[:16]
    cs = cards(before)
    missing = sorted(k for k, v in cs.items() if not NOTE_RE.search(v))
    check("缺 task_id 的卡片数与 R4-验证 实测一致（8 张，逐张点名）",
          missing, [f"BUG-{n}" for n in range(44, 52)], json.dumps(missing))

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bugs = list(con.execute("select id, description from tasks where ns=?", (NS,)))
    con.close()
    resolved = {}
    for num in missing:
        summ = re.search(r"- summary: (.*)", cs[num])
        key = (summ.group(1).strip()[:20] if summ else "")
        hits = [b[0] for b in bugs if key and key in b[1]]
        if len(hits) == 1:
            resolved[num] = hits[0]
    check("能从 bugs 树反查到的卡片数（实测为 0 ⇒ 补记只能写「未派单」）",
          sorted(resolved), [], json.dumps(resolved))

    lines = before.split("\n")
    inserts = []
    for num in missing:
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(f"## {num}"))
        end = next((i for i in range(idx + 1, len(lines))
                    if lines[i].startswith("## BUG-")), len(lines))
        j = end
        while j > idx + 1 and not lines[j - 1].strip():
            j -= 1
        note = (f"- task_id: 未派单（R4-打磨 复算：bugs 树里按 summary 前 20 字反查 "
                f"{'0' if num not in resolved else '1'} 条，无唯一命中 ⇒ "
                f"该卡从未进 bugs 树；补派与改库交人工，本环不写服务端）")
        inserts.append((j, note))
    after_lines = list(lines)
    for pos, note in sorted(inserts, reverse=True):
        after_lines.insert(pos, note)
    after = "\n".join(after_lines)
    if not REFUSE and not already_applied:
        LEDGER.write_text(after, encoding="utf-8", newline="\n")

    dc = diff_counts(before, after)
    live = LEDGER.read_text(encoding="utf-8")
    check("差分只有新增行（追加式补记，零删改）", [dc["removed"], dc["added"]], [0, 8],
          json.dumps(dc["removed_samples"]))
    check("盘上正文与判据重建的补记后文本逐字相同", live, after, "改一次即定稿")
    cs_after = cards(live)
    check("卡片总数不增不减（只补注不新增卡）", len(cs_after), len(cs),
          f"{len(cs)} → {len(cs_after)}")
    still_missing = sorted(k for k, v in cs_after.items() if not NOTE_RE.search(v))
    check("补记后每张卡都有 task_id 行", still_missing, [], json.dumps(still_missing[:6]))

    def valid_id_count(mp: dict) -> int:
        return sum(1 for body in mp.values() for m in NOTE_RE.finditer(body)
                   if VALID_ID.match(m.group(1)))

    n_valid_after, n_valid_before = valid_id_count(cs_after), valid_id_count(cs)
    check("格式正确的 task_id 计数不得虚增（未派单不许冒充有号）",
          n_valid_after, n_valid_before, f"{n_valid_before} → {n_valid_after}")
    unmarked = sorted(k for k, v in cs_after.items()
                      if re.search(r"^- task_id: 未派单", v, re.M))
    check("「未派单」补记恰落在那 8 张卡上", unmarked, missing, json.dumps(unmarked))

    cut = "\n".join(live.splitlines()[:-1])
    canary = diff_counts(cut, live)
    check("canary：少一行必须被差分抓到", canary["added"] >= 1, True, json.dumps(canary))
    same = diff_counts(live, live)
    check("canary 不误抓：同一份文本差分必须为零",
          [same["added"], same["removed"]], [0, 0], json.dumps(same))
    check("台账 sha 变化可见（补记确实落盘）",
          before_sha != hashlib.sha256(live.encode("utf-8")).hexdigest()[:16], True,
          f"{before_sha} → …")

    doc = {"started": started, "ledger": "memory/bugs.md",
           "before_sha": before_sha,
           "after_sha": hashlib.sha256(live.encode("utf-8")).hexdigest()[:16],
           "cards_total_before": len(cs), "cards_total_after": len(cs_after),
           "missing_before": missing, "resolved_from_sqlite": resolved,
           "sqlite_bug_rows": len(bugs), "append_only_diff": dc,
           "valid_task_ids_before": n_valid_before,
           "valid_task_ids_after": n_valid_after,
           "already_applied_at_rerun": already_applied,
           "unmarked_notes": unmarked,
           "adjudication": "8 张卡要不要补派 bugs 树是账本语义问题（服务端写入不可撤回）⇒ 交人工",
           "canary": canary, "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "diff": [dc["added"], dc["removed"]],
                      "missing_before": len(missing), "resolved": len(resolved),
                      "valid_ids": [n_valid_before, n_valid_after],
                      "unmarked": len(unmarked)}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
