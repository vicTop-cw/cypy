#!/usr/bin/env python3
"""Append-only `### FIXED(...)` annotation for memory/bugs.md (归档口径: bugs.md 增量留档).

Nothing is remembered by this script: the bug<->task pairing comes from bugs.md itself, the
ticket verdict from a read-only sqlite pass over fist-mbt.db, and the changed-files / regression
columns from the AST of gen_report.py (so the report and the ledger cannot drift apart).

Two invariants, both self-proved before writing:
  * append-only — every inserted block occurs exactly once and removing all of them reproduces the
    original file byte for byte, so the 13 entry bodies and their `OPEN` status headings are
    untouched (the ledger has no close API);
  * BUG-13 (judge defect, ticket still in flight) gets no annotation.
Re-running is a no-op: an entry that already carries a `### FIXED(` section is skipped.
"""
import ast
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BUGS = os.path.join(ROOT, "memory", "bugs.md")
DB = os.path.join(ROOT, "fist-mbt.db")
NS = "cypy-polish-20260926"


def die(msg):
    sys.exit(f"[annotate_bugs_fixed] {msg}")


def dict_from_ast(path, names):
    """Pull literal dict assignments out of gen_report.py without executing it."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    got = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in names):
            got[node.targets[0].id] = ast.literal_eval(node.value)
    missing = set(names) - set(got)
    if missing:
        die(f"{os.path.basename(path)} 里找不到字面量字典 {sorted(missing)}")
    return got


def main() -> int:
    raw = open(BUGS, "rb").read()
    if b"\r\n" in raw:
        die("bugs.md 含 CRLF，本脚本只按 LF 追加，先查是谁改了行尾")
    text = raw.decode("utf-8")

    heads = [(m.group(1), m.start()) for m in
             re.finditer(r"(?m)^## (BUG-\d+) \[[^\]]*\] \[[a-z]+\] OPEN$", text)]
    if len(heads) != 13:
        die(f"期望 13 条 `## BUG-n … OPEN` 标题，实测 {len(heads)}")
    spans = []
    for i, (bid, start) in enumerate(heads):
        end = heads[i + 1][1] if i + 1 < len(heads) else len(text)
        body = text[start:end]
        m = re.search(r"(?m)^- task_id: (\S+)$", body)
        if not m:
            die(f"{bid} 条目里没有 `- task_id:` 行")
        spans.append({"bug": bid, "start": start, "end": end,
                      "task_id": m.group(1), "body": body})

    con = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    ids = [s["task_id"] for s in spans]
    rows = {r["id"]: dict(r) for r in con.execute(
        "select id, ns, status, updated_at, completed_by from tasks where id in (%s)"
        % ",".join("?" * len(ids)), ids)}
    con.close()

    tables = dict_from_ast(os.path.join(HERE, "gen_report.py"), ("FILES", "TESTS"))
    FILES, TESTS = tables["FILES"], tables["TESTS"]

    reg = open(os.path.join(ROOT, "tests", "test_polish_20260926.py"), encoding="utf-8").read()
    defs = set(re.findall(r"(?m)^def (test_\w+)", reg))

    # `defs` counts functions; pytest counts collected cases (BUG-4 is parametrized ×5). Take the
    # real collection so the ledger can say how many cases actually lock each ticket.
    col = subprocess.run([sys.executable, "-m", "pytest", "tests/test_polish_20260926.py",
                          "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if col.returncode != 0:
        die(f"pytest --collect-only 退出码 {col.returncode}：{col.stdout[-400:]}{col.stderr[-400:]}")
    cases = {}
    for line in (col.stdout or "").splitlines():
        ln = line.strip()
        m = (re.fullmatch(r"tests/test_polish_20260926\.py::(test_\w+)(\[[^\]]*\])?", ln)
             or re.fullmatch(r"<Function (test_\w+)(\[[^\]]*\])?>", ln))
        if m:
            cases[m.group(1)] = cases.get(m.group(1), 0) + 1
    total_cases = sum(cases.values())
    m_tot = re.search(r"(\d+) tests? collected", col.stdout or "")
    if not m_tot or int(m_tot.group(1)) != total_cases:
        die(f"收集用例数对不上：pytest 说 {m_tot and m_tot.group(1)}，逐行统计 {total_cases}")
    if set(cases) - defs:
        die(f"收集到的用例里有源码里不存在的函数：{sorted(set(cases) - defs)}")

    fixed, skipped = [], []
    for s in spans:
        bid, tid = s["bug"], s["task_id"]
        row = rows.get(tid)
        if row is None:
            die(f"{bid} 的修复单 {tid} 在库里没有行")
        if row["ns"] != "bugs":
            die(f"{bid} 的修复单 {tid} 落在 ns {row['ns']!r}，不是 `bugs`")
        if "### FIXED(" in s["body"]:
            skipped.append(bid)
            continue
        if row["status"] != "已完成":
            skipped.append(bid)
            continue
        files = FILES.get(bid)
        tests = TESTS.get(bid)
        if not files or not tests:
            die(f"{bid} 已 verify 但 gen_report.py 的 FILES/TESTS 缺条目")
        named = re.findall(r"test_\w+", tests)
        if not named:
            die(f"{bid} 的 TESTS 文案里没有具体用例名：{tests}")
        unknown = [n for n in named if n not in defs]
        if unknown:
            die(f"{bid} 引用的回归用例在 tests/test_polish_20260926.py 里不存在：{unknown}")
        n = bid.split("-")[1]
        if not any(x.startswith(f"test_bug{n}_") for x in named):
            die(f"{bid} 的回归用例名没有一条以 test_bug{n}_ 开头：{named}")
        orphans = sorted(d for d in defs
                         if d.startswith(f"test_bug{n}_") and d not in named)
        if orphans:
            die(f"{bid} 漏掉了回归文件里同前缀的用例：{orphans}")
        rendered = []
        for x in named:
            cnt = cases.get(x, 0)
            if cnt < 1:
                die(f"{bid} 的 {x} 没被 pytest 收集到")
            rendered.append(f"`tests/test_polish_20260926.py::{x}`"
                            + (f"（parametrize {cnt} 例）" if cnt > 1 else ""))
        ncases = sum(cases[x] for x in named)
        block = (
            f"### FIXED(verify=已完成) — 2026-09-26 追加留档（本条目正文与标题行 `OPEN` 一字未改）\n\n"
            f"- 修复任务：`{tid}`（ns `bugs`，库里 `status=已完成`、`updated_at={row['updated_at']}`、"
            f"`completed_by={row['completed_by']}`）\n"
            f"- 改动文件：`{files}`\n"
            f"- 锁死回归（{len(named)} 个函数 / {ncases} 条收集用例）：" + "、".join(rendered) + "\n"
            f"- 闭环证据：`.fist-polish-20260926/` 下 `close_fixes*.out.json`"
            "（该单 claim → execute → submit → verify 的逐单调用日志）与 `annotate_bugs_fixed.out.json`\n"
            "- 口径：FIST-Mbt 的 bug 账本没有关闭 API，`report_bug` 只能追加条目，故修复状态以本段"
            "追加留档、以任务库为准；标题行的 `OPEN` 不改写，也不据此判定门禁已绿。\n\n"
        )
        s["block"] = block
        fixed.append({"bug": bid, "task_id": tid, "tests": named, "collected_cases": ncases,
                      "updated_at": row["updated_at"]})

    if not fixed:
        print("no-op：没有待留档的已闭环条目（或已全部带 FIXED 段），未写文件")
        return 0

    out = ""
    prev = 0
    for s in spans:
        out += text[prev:s["end"]]
        prev = s["end"]
        if "block" in s:
            out += s["block"]
    out += text[prev:]

    strip = out
    for s in spans:
        if "block" not in s:
            continue
        if strip.count(s["block"]) != 1:
            die(f"{s['bug']} 的 FIXED 段在结果里出现 {strip.count(s['block'])} 次，无法逐一定位")
        strip = strip.replace(s["block"], "", 1)
    if strip != text:
        die("回剥插入段后不等于原文 —— 存在改写，拒绝写盘")

    data = out.encode("utf-8")
    open(BUGS, "wb").write(data)
    summary = {"bugs_md": "memory/bugs.md", "annotated": fixed,
               "annotated_count": len(fixed), "skipped_no_annotation": skipped,
               "regression_defs_total": len(defs), "regression_cases_total": total_cases,
               "regression_cases_annotated": sum(f["collected_cases"] for f in fixed),
               "headings": 13, "bytes_before": len(raw), "bytes_after": len(data),
               "append_only_proof": "strip(所有 FIXED 段) == 原文（逐字节）",
               "status_heading_untouched": True, "namespace_root": NS}
    json.dump(summary, open(os.path.join(HERE, "annotate_bugs_fixed.out.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"annotated={len(fixed)} skipped={skipped} "
          f"bytes {summary['bytes_before']} -> {summary['bytes_after']}")
    for f in fixed:
        print(f"  {f['bug']:8s} {f['task_id']:6s} {f['updated_at']} "
              f"{len(f['tests'])} 条回归")
    return 0


if __name__ == "__main__":
    sys.exit(main())
