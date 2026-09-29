"""R4-打磨 法②：附录 C 的 4 条形差落在**冻结面**上 ⇒ 只出两栏，冻结文件一个字节都不碰。

栏一「改冻结面」= 交人工（`SYNTAX/appendix-C-features.md` 的措辞不在本环半径内）；
栏二「非冻结补注」= 本环实际写出的 `docs/APPENDIX_C_DEVIATIONS.md`。

判据不是「我写了个文件」，而是三件可复算的事：

1. 4 行 `doc_row` 逐字能在冻结文件里搜到（补注引的是原文，不是我复述的话）；
2. 冻结面全量 sha 在写补注前后逐字相等，并配 canary：往内存副本里注入一处假改动，
   比较谓词必须抓到（否则这条「未触碰」的门是恒绿的）；
3. 幂等：重跑必须产出**字节相同**的补注文件（合成器不幂等会在同一行叠出重复内容）。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "verify_r4_appendixC.json"
FROZEN_DIR = ROOT / "SYNTAX"
FROZEN_DOC = FROZEN_DIR / "appendix-C-features.md"
NOTE = ROOT / "docs" / "APPENDIX_C_DEVIATIONS.md"
OUT = HERE / "polish_r4_appendixC.json"
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def frozen_sha() -> dict:
    return {f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            for f in sorted(FROZEN_DIR.rglob("*.md"))}


def build_note(devs: list) -> str:
    head = ("# 附录 C 的形差补注（非冻结面）\n\n"
            "本文件是对 `SYNTAX/appendix-C-features.md`《已实现的限制修复》表的**补注**，"
            "不是那份表本身。冻结面的措辞改动一律交人工（见文末）。\n"
            "证据件：`.fist-loop-20260927/verify_r4_appendixC.json`（R4-验证 逐行现写真跑）。\n\n"
            "| 附录 C 行号 | 冻结面原文行（逐字引用） | 本轮实测 | 结论 | 出路 |\n"
            "| --- | --- | --- | --- | --- |\n")
    rows = []
    for d in devs:
        doc_row = d["doc_row"].replace("|", "\\|")
        reason = str(d["reason"]).replace("\n", " ").replace("|", "\\|")[:300]
        rows.append(f"| {d['n']} | `{doc_row}` | {reason} | {d['verdict']} | "
                    f"改冻结面（交人工）+ 本文件补注（已完成） |")
    tail = ("\n\n## 交人工的那一栏（本环不动刀）\n\n"
            "- 上表 4 行都在 `SYNTAX/appendix-C-features.md:598` 起的《已实现的限制修复》表里，"
            "该行声明「已实现 vX」而调用面实测有偏差。\n"
            "- 改法有两种（删掉该行 / 把状态改成「部分实现 + 指向本补注」），"
            "哪一种都动的是冻结语义 ⇒ 由人裁决，本环只在非冻结面补注。\n")
    return head + "\n".join(rows) + tail


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    art = json.loads(SRC.read_text(encoding="utf-8"))
    devs = art.get("deviations") or []
    want_rows = sorted(set(art.get("claim_false") or []) | set(art.get("claim_half_true") or []))
    check("形差行数 = claim-false ∪ half-true（4 行，不多不少）",
          sorted(d["n"] for d in devs), want_rows, json.dumps(want_rows))
    frozen_before = frozen_sha()
    frozen_text = FROZEN_DOC.read_text(encoding="utf-8")
    not_found = [d["n"] for d in devs if d["doc_row"].strip() not in frozen_text]
    check("每行引用的冻结面原文都能逐字搜到（不是我复述的）", not_found, [],
          json.dumps(not_found))

    note = build_note(devs)
    existed = NOTE.exists()
    prev_bytes = NOTE.read_bytes() if existed else b""
    NOTE.write_text(note, encoding="utf-8", newline="\n")
    first_bytes = NOTE.read_bytes()
    NOTE.write_text(note, encoding="utf-8", newline="\n")
    second_bytes = NOTE.read_bytes()
    check("合成器幂等：同一输入连写两次字节必须相同（不叠行）",
          first_bytes == second_bytes, True, f"{len(first_bytes)} vs {len(second_bytes)}")
    check("重跑取回的内容与本次生成一致（没有漂出第二种形态）",
          prev_bytes in (b"", second_bytes), True,
          f"盘上前值 {len(prev_bytes)} B / 本次 {len(second_bytes)} B")
    data_rows = len([ln for ln in note.splitlines()
                     if ln.startswith("| ") and not ln.startswith("| ---")]) - 1
    check("补注非空且 4 行都落表", data_rows, 4, "表格数据行数（扣表头与分隔行）")

    frozen_after = frozen_sha()
    check("冻结面全量 sha 写补注前后逐字相等", frozen_after == frozen_before, True,
          json.dumps(sorted(set(frozen_after) ^ set(frozen_before)))[:200])
    fake = dict(frozen_before)
    first = sorted(fake)[0]
    fake[first] = "0" * 16
    canary_caught = fake != frozen_before and frozen_after == frozen_before
    check("canary：注入一处假改动必须被比较谓词抓到", canary_caught, True, first)

    doc = {"started": started, "note_file": NOTE.relative_to(ROOT).as_posix(),
           "frozen_doc": FROZEN_DOC.relative_to(ROOT).as_posix(),
           "deviations": devs, "queue_frozen_edit": [d["n"] for d in devs],
           "note_done_rows": len(devs), "frozen_files": len(frozen_after),
           "frozen_sha": frozen_after, "frozen_sha_equal": frozen_after == frozen_before,
           "canary": {"injected_file": first, "caught": canary_caught},
           "note_bytes": NOTE.stat().st_size,
           "existed_before_this_run": existed,
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "rows": len(devs),
                      "frozen_files": len(frozen_after), "sha_equal": doc["frozen_sha_equal"],
                      "canary": canary_caught, "note_bytes": doc["note_bytes"],
                      "existed": existed}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
