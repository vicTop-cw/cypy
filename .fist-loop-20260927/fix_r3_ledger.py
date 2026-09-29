#!/usr/bin/env python3
"""R3-修复：给 BUG-55..BUG-60 追加 `### FIXED(修复=已完成)` 段落账。

账本没有 close/edit API（服务端条目恒 `OPEN`），所以修法只有"追加"一种形状：
**条目标题行与正文一字不改**，在其后追加一段留档。本件的守卫按这个约束写：

- 前置拒绝：任一批到的判据件（plan / evidence / locks_inventory / baselines）refuse 非空、
  或本环幂等标记已在账上 ⇒ 一个字都不写（不做"先写再回滚"，Windows 上回滚不是原子的）；
- 写之前逐段断言：这段文字里必须真的含有本环承诺的针头字面（修法、锁名、复跑命令、
  仍红的另一半），否则"段落存在"不等于"段落说了对的话"；
- 写之后按**终态**复算（不看增量）：六件各且仅各一段、条目总数仍 60、标题行逐字仍在、
  FIXED 段总数 = 写前实测 + 6。上一环用"引用次数 +1"当判据被折行的逐字引用骗过一次。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LEDGER = ROOT / "memory" / "bugs.md"
MARK = "### FIXED(修复=已完成)"
ROUND_TAG = "2026-09-28 R3-修复"
EVIDENCE = {
    "plan": HERE / "fix_r3_plan.json",
    "evidence": HERE / "fix_r3_evidence.json",
    "locks": HERE / "fix_r3_locks_inventory.json",
    "baselines": HERE / "fix_r3_baselines.json",
}
REPORT = "memory/reviews/20260928.00.20.00.md"

NEEDLES = {
    "BUG-55": ["generic_params", "test_bug55_generic_params_nodes_are_collected", "hunt_r3_repro.py C1"],
    "BUG-56": ["run_transpile", "test_bug56_check_only_reports_and_generates_nothing",
               "摘旗是缩对外接口面"],
    "BUG-57": ["UnionTypeError", "test_bug57_builtin_member_type_is_diagnosed", "裁决"],
    "BUG-58": ["Optional[int]", "test_realloc_zero_size", "释放并返回 None"],
    "BUG-59": ["sorted(cycle_modules)", "PYTHONHASHSEED", "test_bug59_compilation_order_stable_across_hash_seeds"],
    "BUG-60": ["04-pointer-types", "函数作用域", "36 处"],
}


def load(name: str) -> dict:
    path = EVIDENCE[name]
    if not path.exists():
        return {"refuse": [f"{path.name} 不在盘上"]}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("refuse"):
        return {"refuse": [f"{path.name} refuse 非空：{doc['refuse'][:2]}"]}
    return doc


def section(row: dict, root_id: str, stamp: str, base: dict, ev: dict) -> str:
    bug = row["bug"]
    flip = ev["flips"].get({"BUG-55": "C1", "BUG-56": "C3", "BUG-57": "C4",
                            "BUG-58": "C5", "BUG-59": "C6", "BUG-60": "C8"}[bug], {})
    locks = "、".join(f"`{x}`" for x in row["locks"])
    lines = [
        f"{MARK} — {stamp} 追加留档（{ROUND_TAG}，本条目正文与标题行 `OPEN` 一字未改）",
        f"- 修复单：根 `{root_id}`（ns `cypy-loop-20260927`）下 16 叶全链带 `[omega:required]`"
        f"的 claim→omega→execute→submit→output_validate→omega_result_verify→verify；"
        f"报告：`{REPORT}`",
        f"- 修法：{row['chosen_fix']}",
        f"- 被放弃的替代修法与理由：{row['rejected_alternative']}",
        f"- 改动文件：{'、'.join('`' + f + '`' for f in row['files'])}",
        f"- 回归锁（{len(row['locks'])} 条，pos={len(row['pos_locks'])} / 对照={len(row['ctl_locks'])}）：{locks}",
        f"- 前后对照（R3-寻虫 原夹具 hunt_r3_repro.py，0=现形 / 1=不现形 / 2=夹具坏）："
        f"before rc={flip.get('before_rc')} → after rc={flip.get('after_rc')}"
        f"；修前 observed=`{json.dumps(flip.get('before_observed'), ensure_ascii=False)}`"
        f"，修后 observed=`{json.dumps(flip.get('after_observed'), ensure_ascii=False)}`",
    ]
    if row.get("still_red_reason"):
        lines.append(f"- **本环未消除的那一半（如实写明，不签已修）**：{row['still_red_reason']}")
    if row.get("adjudication_left"):
        lines.append(f"- 交回裁决：{row['adjudication_left']}")
    lines.append(
        f"- 三套基线（同一时刻复算，`.fist-loop-20260927/fix_r3_baselines.json` refuse=[]）："
        f"pytest `{base['pytest']['line']}`（下限 {base['pytest']['floor']}）/ "
        f"自研 `{base['suite']['line']}` / e2e `{base['e2e']['line']}`；"
        f"HEAD 仍 `{base['git']['head']}`、暂存 {base['git']['staged']}；"
        f"改动半径 {base['radius']['count']} 档全部归属本单"
    )
    lines.append(f"- 复跑：`{row['repro']}`（本条目复跑命令与本段前后对照同源）")
    return "\n" + "\n".join(lines) + "\n"


def main() -> int:
    verify_only = "--verify" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--verify"]
    if unknown:
        print(json.dumps({"refuse": [f"本驱动只认 --verify，收到 {unknown}"],
                          "written": False}, ensure_ascii=False))
        return 1
    refuse: list = []
    docs = {name: load(name) for name in EVIDENCE}
    for name, doc in docs.items():
        if doc.get("refuse"):
            refuse.append(doc["refuse"][0])
    root_doc = HERE / "root_r3_fix.out.json"
    root_id = ""
    if root_doc.exists():
        root_id = json.loads(root_doc.read_text(encoding="utf-8")).get("root", "")
    if not root_id:
        refuse.append("还没发布本环根任务（root_r3_fix.out.json 缺 root 号），"
                      "FIXED 段不能没有修复单号")
    base = docs.get("baselines", {})
    if base and not (base.get("pytest", {}).get("passed", 0) >= base.get("pytest", {}).get("floor", 10**9)
                     and base.get("suite", {}).get("green") and base.get("e2e", {}).get("green")):
        refuse.append("三套基线未全绿，不配写 FIXED")

    text = LEDGER.read_text(encoding="utf-8")
    entries_before = len(re.findall(r"^## BUG-\d+ ", text, flags=re.M))
    fixed_before = text.count(MARK)
    open_titles_before = re.findall(r"^## BUG-\d+ .*$", text, flags=re.M)
    already = [ln for ln in text.splitlines() if MARK in ln and ROUND_TAG in ln]
    if already and not verify_only:
        refuse.append(f"幂等守卫：本环 FIXED 段已在账上 {len(already)} 处，不重复追加")
    if entries_before != 60:
        refuse.append(f"账本条目数不是 60（实得 {entries_before}），本环认领面变了先查清再写")

    plan = docs.get("plan", {})
    rows = plan.get("per_bug", [])
    if len(rows) != 6:
        refuse.append(f"plan 里的 per_bug 不是 6 件：{len(rows)}")
    stamp = lfist_lib.utc_now().replace("+00:00", "Z")

    built = {}
    for row in rows:
        if not row.get("flipped") and not row.get("still_red_reason"):
            refuse.append(f"{row['bug']} 既没翻也没写『仍红的原因』，不能签段落账")
        body = section(row, root_id, stamp, base, docs.get("evidence", {}))
        for needle in NEEDLES[row["bug"]]:
            if needle not in body:
                refuse.append(f"{row['bug']} 段落下缺承诺的针头字面：{needle}")
        built[row["bug"]] = body

    if refuse:
        print(json.dumps({"refuse": refuse, "written": False}, ensure_ascii=False))
        return 1

    new_text = text
    for row in rows:
        bug = row["bug"]
        m = re.search(rf"^## {bug} .*$", new_text, flags=re.M)
        if not m:
            refuse.append(f"账本里找不到 {bug} 标题行")
            continue
        nxt = re.search(r"^## BUG-\d+ ", new_text[m.end():], flags=re.M)
        insert_at = m.end() + (nxt.start() if nxt else len(new_text) - m.end())
        new_text = new_text[:insert_at].rstrip("\n") + "\n" + built[bug] + new_text[insert_at:]

    if not verify_only and new_text != text:
        LEDGER.write_text(new_text, encoding="utf-8", newline="\n")

    after = LEDGER.read_text(encoding="utf-8")
    per_bug = {}
    heads = list(re.finditer(r"^## BUG-\d+ .*$", after, flags=re.M))
    for row in rows:
        bug = row["bug"]
        m = next((h for h in heads if h.group(0).startswith(f"## {bug} ")), None)
        if m is None:
            refuse.append(f"写后找不到 {bug} 标题行")
            continue
        nxt = next((h for h in heads if h.start() > m.start()), None)
        section_text = after[m.end(): nxt.start() if nxt else len(after)]
        marks = [ln for ln in section_text.splitlines() if MARK in ln and ROUND_TAG in ln]
        checks = {
            "own_marker_lines": len(marks),
            "fix_line_present": f"- 修法：{row['chosen_fix']}" in section_text,
            "needles_present": all(n in section_text for n in NEEDLES[bug]),
            "repro_line_present": f"- 复跑：`{row['repro']}`" in section_text,
        }
        per_bug[bug] = checks
        if checks["own_marker_lines"] != 1:
            refuse.append(f"{bug} 段内本环 FIXED 标题行有 {checks['own_marker_lines']} 行，应为 1")
        for key in ("fix_line_present", "needles_present", "repro_line_present"):
            if not checks[key]:
                refuse.append(f"{bug} 段内 {key}=false（段落话没落全）")
    expected_fixed = fixed_before + len(rows) if not verify_only else len(rows)
    state = {
        "mode": "verify" if verify_only else "write",
        "entries_after": len(re.findall(r"^## BUG-\d+ ", after, flags=re.M)),
        "fixed_after": after.count(MARK),
        "fixed_expected": expected_fixed,
        "fixed_before": fixed_before,
        "titles_identical": (re.findall(r"^## BUG-\d+ .*$", after, flags=re.M) == open_titles_before
                             if not verify_only else
                             len(re.findall(r"^## BUG-\d+ .*$", after, flags=re.M)) == entries_before),
        "open_titles_equal_entries": len(re.findall(r"^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN$",
                                                    after, flags=re.M)) == entries_before,
    }
    if state["entries_after"] != entries_before:
        refuse.append(f"条目数变了：{entries_before} → {state['entries_after']}")
    if state["fixed_after"] != expected_fixed:
        refuse.append(f"FIXED 段总数不对：实得 {state['fixed_after']} 应为 {expected_fixed}")
    if not state["titles_identical"]:
        refuse.append("条目标题行被改动（红线：只能追加）")

    out = {
        "root_task": root_id,
        "mode": state["mode"],
        "sections_written": len(rows),
        "per_bug": per_bug,
        "state": state,
        "report": REPORT,
        "refuse": refuse,
    }
    (HERE / "fix_r3_ledger.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
