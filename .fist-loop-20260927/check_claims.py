#!/usr/bin/env python3
"""报告口径核对（R2 起每份报告收口前必跑）：报告里"说过的话"要与账本对得上。

抓三类失效（都是历史上真出现过的）：
 A. 报告声称 `BUG-N 已修`，但 `memory/bugs.md` 里该条目没有 `### FIXED` 段（或条目根本不存在）；
 B. 报告声称 `BUG-N 已入账`，但账本里查不到该条目 ⇒ 号是我编的；
 C. 报告对某个任务号下"已完成/已归档/可标完成"的结论，而该号在任务库里不存在或状态不符
    ⇒ 替别人（或替不存在的单）签了完成。
"入账未修"是合法终态，所以 A 只在报告**主动**声称已修时才要求 FIXED 段。
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
NS = "cypy-loop-20260927"
FIX_WORDS = r"已修|修复完成|已闭环|已转正|fixed"
FILED_WORDS = r"已入账|新入账|入账 |占号"
DONE_WORDS = r"已完成|已归档|可标完成|L4 通过|已闭环"


def strip_code(body: str) -> str:
    """摘掉 ``` 围栏块与行内 `code`：被逐字引用的服务端原文不是本报告的主张。

    只作用于 A 类（主张检测）；B 类（编号是否存在）与 C 类（任务状态）仍读全文，
    所以「把编造的号藏进反引号」这条路不成立。
    """
    out = re.sub(r"(?s)```.*?```", "", body)
    return re.sub(r"`[^`]*`", "", out)


def claims_fixed_in(body: str) -> set:
    """哪些 BUG 号被报告**主动**声称已修。两路取数，都不按标签前缀筛：

     1) 页脚 `fixed=BUG-44,BUG-45(...)` 的结构化清单（截到下一个空白，不吃 carry=）；
     2) 散文里「BUG-N 与修复词同句相邻」——中间夹着别的 BUG 号就不算（±80 字符窗口
        会把整行页脚读成一个主张，从而把 carry 名单误判成已修）。
    """
    ids = set()
    for m in re.finditer(r"fixed=([^\s]*)", body, re.I):
        ids.update(int(b) for b in re.findall(r"BUG-(\d+)", m.group(1)))
    prose = strip_code(body)
    for line in prose.splitlines():
        if re.search(r"fixed=", line, re.I):
            continue
        marks = [(mm.start(), mm.end(), int(mm.group(1))) for mm in re.finditer(r"BUG-(\d+)", line)]
        gap = "(?:[^。，、,；;：:\"“”]){0,3}"
        for start, end, bid in marks:
            if re.search(rf"BUG-{bid}{gap}(?:{FIX_WORDS})", line, re.I):
                ids.add(bid)
            if re.search(rf"(?:{FIX_WORDS}){gap}BUG-{bid}", line, re.I):
                ids.add(bid)
    return ids


NL = chr(10)


def selftest() -> int:
    must_catch = "- 本环把 BUG-9999 已修并回归" + NL
    must_not = "fixed=BUG-41,BUG-42 carry=BUG-48,BUG-49 locks=18" + NL
    quoted = "- 报告引用原文：`BUG-9999 已修并回归`" + NL
    narrative = '- 首次实跑把转结单 BUG-48 报成了"报告说它已修"（假红）' + NL
    got_catch = claims_fixed_in(must_catch)
    got_not = claims_fixed_in(must_not)
    got_quoted = claims_fixed_in(quoted)
    got_narr = claims_fixed_in(narrative)
    doc = {
        "must_catch": {"text": must_catch.strip(), "got": sorted(got_catch), "want": [9999]},
        "must_not_catch": {"text": must_not.strip(), "got": sorted(got_not), "want": [41, 42]},
        "must_not_catch_narrative": {
            "text": narrative.strip(),
            "got": sorted(got_narr),
            "want": [],
        },
        "must_not_catch_quoted": {
            "text": quoted.strip(),
            "got": sorted(got_quoted),
            "want": [],
        },
    }
    bad = []
    if 9999 not in got_catch:
        bad.append("自检失败：『BUG-9999 已修』没被抓到 ⇒ 判据恒绿")
    if 48 in got_not or 49 in got_not:
        bad.append("自检失败：carry 名单被误判成已修 ⇒ 判据过宽")
    if got_quoted:
        bad.append("自检失败：反引号里的引用原文被当成主张 ⇒ 逐字引用无法进报告")
    if got_narr:
        bad.append("自检失败：转述句里的『报成了已修』被当成主张 ⇒ 叙述型文本没法写")
    if 9999 not in got_catch or not got_not:
        bad.append("自检失败：前两条用例的读数异常 ⇒ 规则改松了")
    doc["refuse"] = bad
    Path(__file__).resolve().parent.joinpath("check_claims_selftest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline=NL
    )
    print(json.dumps({"selftest": "ok" if not bad else bad, **doc}, ensure_ascii=False))
    return 1 if bad else 0



def bug_sections() -> dict:
    txt = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    out = {}
    parts = re.split(r"(?m)^## BUG-(\d+)\b", txt)
    for i in range(1, len(parts) - 1, 2):
        out[int(parts[i])] = parts[i + 1]
    return out


def task_states() -> dict:
    db = ROOT / "fist-mbt.db"
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = list(con.execute("select id, status from tasks where ns=?", (NS,)))
    except sqlite3.Error:
        rows = []
    con.close()
    return {i: s for i, s in rows}


def main() -> int:
    if len(sys.argv) < 2:
        print("REFUSE — 用法：check_claims.py <报告路径> [额外要求点名的 BUG 号,逗号分隔]")
        return 1
    if "--selftest" in sys.argv[1:]:
        return selftest()
    rep = ROOT / sys.argv[1]
    if not rep.exists():
        print(f"REFUSE — 报告不存在：{sys.argv[1]}")
        return 1
    body = rep.read_text(encoding="utf-8", errors="replace")
    must_mention = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else []) if x]
    bugs = bug_sections()
    states = task_states()
    refuse: list = []
    doc: dict = {"report": sys.argv[1], "bug_entries_on_disk": len(bugs)}

    if not bugs:
        refuse.append("A/B 类核对整体失效：memory/bugs.md 里解析到 0 条 `## BUG-N` 条目")
    if not states:
        refuse.append("C 类核对整体失效：任务库里解析到 0 条本 ns 任务")

    claimed_fixed = sorted(claims_fixed_in(body))
    a_rows = []
    for bid in claimed_fixed:
        sec = bugs.get(bid)
        has_fix = bool(sec) and "### FIXED" in sec
        a_rows.append({"bug": bid, "entry_exists": sec is not None, "fixed_section": has_fix})
        if sec is None:
            refuse.append(f"A 类：报告说 BUG-{bid} 已修，但账本里没有这个条目")
        elif not has_fix:
            refuse.append(f"A 类：报告说 BUG-{bid} 已修，但条目里没有 `### FIXED` 段")
    doc["claimed_fixed"] = a_rows

    filed_ids = sorted({int(m) for m in re.findall(r"BUG-(\d+)", body)})
    b_rows = []
    for bid in filed_ids:
        exists = bid in bugs
        b_rows.append({"bug": bid, "on_disk": exists})
        if not exists:
            refuse.append(f"B 类：报告点到 BUG-{bid}，账本里查不到该号（号是编的或写错了）")
    doc["bug_ids_in_report"] = b_rows

    c_rows = []
    for tid in sorted(set(re.findall(r"\bT0[0-9a-zA-Z.]+\b", body))):
        base = tid.split(".")[0]
        st = states.get(base)
        claims_done = re.search(rf"{re.escape(tid)}[^。\n]?(?:{DONE_WORDS})", body)
        if claims_done and st is None:
            refuse.append(f"C 类：报告对任务 {tid} 下了完成型结论，任务库里查不到该号")
        elif claims_done and st not in ("已完成", "已归档", "待验收"):
            refuse.append(f"C 类：报告说 {tid} 完成，库里的状态是 {st}")
        c_rows.append({"task": base, "status_in_db": st or "ABSENT", "mentioned": tid})
    doc["task_claims"] = c_rows

    for bid in must_mention:
        if f"BUG-{bid}" not in body:
            refuse.append(f"点名核对：spec 要求报告必须写到 BUG-{bid}，实际没出现")

    here = Path(__file__).resolve().parent
    (here / "check_claims.out.json").write_text(
        json.dumps({"refuse": refuse, **doc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "refuse": refuse[:10],
                "count": len(refuse),
                "bugs_on_disk": len(bugs),
                "tasks_in_db": len(states),
            },
            ensure_ascii=False,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
