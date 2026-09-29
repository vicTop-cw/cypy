"""R1-验证 law7：脏工作树定性与账本一致性。

`examples/demos/legacy/**` 里有若干 `D`（删除）与 `M`（修改）没有开工前快照可归因。
本脚本不做归因推测，只回答两个可判定的问题：
 1. 被删的 demo 文件是否仍被 `tests/` 或 `scripts/` 引用（引用了 = 悬空引用，是真风险）；
 2. 账本（`memory/bugs.md`）与任务库（sqlite）是否自洽：条目头数 = bug 数、
    本轮 4 单是否既有 OPEN 标题行又有 FIXED 段（"入账未修"与"已修"不能混标）。
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(r"E:\IDEProjects\AI\Cypy")
NS = "cypy-loop-20260927"
BUGS = ["BUG-30", "BUG-31", "BUG-33", "BUG-38"]


def main() -> int:
    refuse = []
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.splitlines()
    deleted = [l[3:].strip().strip('"') for l in status if l[:2].strip() == "D"]
    modified = [l[3:].strip().strip('"') for l in status if l[:2].strip() == "M"]

    corpus = []
    for d in ("tests", "scripts", "cypyc", "cypy_hook", "cypy_bridge"):
        corpus += list((ROOT / d).rglob("*.py"))
    text_by_path = {}
    for p in corpus:
        try:
            text_by_path[p] = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
    # 悬空引用：只有「源码里出现**完整相对路径**且该路径不在盘上」才是硬伤。
    # 只按 basename 子串匹配会大量假报警（实测两条：`examples/struct.cypy` 早在上一轮
    # 改名为 `struct_records.cypy`，`build_blocks.cypy` 被 `patterns_operators/` 下的同名文件命中）。
    FS_VERB = ("open(", "Path(", "path.join", "exists(", "transpile(", "compile(", "glob(", "run(")
    dangling = {}
    weak = {}
    existing_names = {p.name for p in (ROOT / "examples").rglob("*.cypy")}
    renamed_candidates = {}
    for rel in deleted:
        rel_posix = rel.replace("\\", "/")
        stem = Path(rel).name
        users, weak_users = [], []
        for path, text in text_by_path.items():
            hits = []
            for ln in text.splitlines():
                s = ln.strip()
                if rel_posix not in s or s.startswith("#"):
                    continue
                # 只有「同一行真的拿它当路径去读/编译」才算悬空；
                # 文档串与注释里提旧名是历史说明（实测 examples/struct.cypy 上一轮已改名
                # struct_records.cypy，三处提及全是 prose，硬按子串匹配会假报警）。
                if any(v in ln for v in FS_VERB):
                    hits.append(ln)
            if hits:
                users.append({"file": path.relative_to(ROOT).as_posix(), "lines": hits[:2]})
            elif stem in text:
                weak_users.append(path.relative_to(ROOT).as_posix())
        if users:
            dangling[rel] = users
        if weak_users:
            weak[rel] = weak_users
        if not Path(rel).exists() and stem in existing_names:
            renamed_candidates[rel] = [
                p.relative_to(ROOT).as_posix() for p in (ROOT / "examples").rglob(stem)
            ]

    led = (ROOT / "memory/bugs.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (BUG-\d+) \[[^\]]*\] \[(\w+)\] (\w+)", led, re.M)
    sections = {}
    for m in re.finditer(r"^## (BUG-\d+) .*?$", led, re.M):
        start = m.start()
        nxt = re.search(r"^## BUG-", led[m.end() :], re.M)
        body = led[m.end() : m.end() + (nxt.start() if nxt else len(led))]
        sections[m.group(1)] = (
            "FIXED(verify=已完成)" in body,
            "OPEN" in led[m.start() : m.start() + 80],
        )
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    bug_tasks = list(db.execute("select count(*) from tasks where ns='bugs'"))[0][0]
    loop_roots = [
        r[0] for r in db.execute("select id from tasks where ns=? and depth=3 order by id", (NS,))
    ]
    archived = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and depth=3 and status='已归档' order by id", (NS,)
        )
    ]
    db.close()

    for b in BUGS:
        fixed, open_hdr = sections.get(b, (False, False))
        if not open_hdr:
            refuse.append(f"判据7 {b} 的标题行不在账本里（或被改过）")
        if b != "BUG-31" and not fixed:
            refuse.append(f"判据7 {b} 报告说已修，但账本里没有 FIXED(verify=已完成) 段")
        if b == "BUG-31" and not fixed:
            refuse.append(f"判据7 {b} 两半都已落地却没有 FIXED 段")

    if len(heads) != len(sections):
        refuse.append(f"判据7 标题行计数不一致：正则 {len(heads)} vs 分段 {len(sections)}")
    if dangling:
        refuse.append(f"判据7 有被删文件仍被引用（悬空引用，需单开一单）：{dangling}")

    doc = {
        "refuse": refuse,
        "deleted": deleted,
        "modified_count": len(modified),
        "dangling_refs": dangling,
        "weak_basename_mentions": weak,
        "renamed_candidates": renamed_candidates,
        "ledger": {
            "heads": len(heads),
            "bug_entries": len(sections),
            "this_round_status": {b: sections.get(b) for b in BUGS},
        },
        "taskbook": {
            "bug_tree_tasks_ns_bugs": bug_tasks,
            "loop_roots": loop_roots,
            "loop_roots_archived": archived,
        },
    }
    (HERE / "verify_dirt_r1.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": refuse,
                "deleted": deleted,
                "dangling": dangling,
                "ledger": doc["ledger"]["heads"],
                "roots": loop_roots,
                "archived": archived,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
