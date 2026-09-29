"""R4-验证 法①②：逐单回退矩阵（独立复算，不读修复环的判据件）。

口径与修复环不同处：修复环按 RC1..RC4 四个根因手动指定摘哪些行；这里**按 difflib 的
opcode 自动切片**——`fix_r4_before/type_checker.py`（修前文本）与工作区现文本的每一段
差异都是一行矩阵，摘不摘、摘了红不红都由不得人。这样「锁到底认不认识这次修复」就不是
自述，而是 20 段逐一实测出来的。

三件事必须同时成立，否则本件自己 refuse：
① 快照树身份探针证明吃的是快照（不是工作区）；
② 每段 mutation 后文件 sha 必须逐字回到基线（证明矩阵不留残渣）；
③ 一条「改了也不红」的 canary（纯注释改动）必须被矩阵归到 non_bearing 里——
   canary 若变红，说明锁对无关改动也尖叫，那它的红就不是证据。
"""

from __future__ import annotations

import datetime
import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_r4_lib as V  # noqa: E402

BEFORE = HERE / "fix_r4_before" / "type_checker.py"
TARGET = "tests/test_loop_20260927_fix_r4.py"
COLLATERAL = ["tests/test_loop_20260927_fix_r3.py", "tests/test_loop_20260927_polish_r3.py",
              "tests/test_loop_20260927_advance_r3.py"]
REL = Path("cypyc") / "analyzer" / "type_checker.py"
OUT = HERE / "verify_r4_matrix.json"
CHECKS: list = []
REFUSE: list = []


def check(label, got, want, why) -> None:
    CHECKS.append({"label": label, "got": got, "want": want, "why": why, "ok": got == want})
    if got != want:
        REFUSE.append(f"{label}: got={got!r} want={want!r}（{why}）")


def split_failures(names: list) -> dict:
    by = {}
    for n in names:
        f = n.split("::")[0]
        by.setdefault(f, []).append(n)
    return {k: sorted(v) for k, v in sorted(by.items())}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if not BEFORE.exists():
        print(json.dumps({"refuse": [f"修前文本不存在：{BEFORE}"]}, ensure_ascii=False))
        return 1
    snap = V.copy_into_snap()
    rel = snap / REL
    cur_lines = rel.read_text(encoding="utf-8").splitlines(True)
    before_lines = BEFORE.read_text(encoding="utf-8").splitlines(True)
    baseline_sha = V.sha256(rel)

    ident = V.identity_probe(snap)
    check("身份探针必须证明吃的是快照树", ident["under_snapshot"], True,
          f"loaded={ident['loaded'].get('mod')}")
    check("身份探针不得泄漏工作区", ident["workspace_leak"], False, "见 loaded")

    files = [TARGET] + COLLATERAL
    collected = V.collect_count(TARGET, snap)
    base_target = V.run_pytest([TARGET], snap)
    check("基线：目标锁单独跑必须全绿",
          [base_target["fields"]["failed"], base_target["fields"]["errors"]], [0, 0],
          base_target["summary_line"])
    check("基线：目标锁实跑条数必须等于收集到的条数（防空汇总行/防漏收）",
          base_target["fields"]["passed"], collected, f"collect-only={collected}")
    base = V.run_pytest(files, snap)
    check("快照基线：含对照锁在内也必须全绿",
          [base["fields"]["failed"], base["fields"]["errors"]], [0, 0], base["summary_line"])
    check("快照基线：rc 与计数同向", (base["rc"] == 0) ==
          (base["fields"]["failed"] + base["fields"]["errors"] == 0), True,
          f"rc={base['rc']} {base['summary_line']}")

    ops = [o for o in difflib.SequenceMatcher(None, before_lines, cur_lines, autojunk=False)
           .get_opcodes() if o[0] != "equal"]
    rows = []
    rc_mismatch = []

    def mutate_and_run(label, kind, new_lines, expect_region):
        rel.write_text("".join(new_lines), encoding="utf-8", newline="\n")
        mutated_sha = V.sha256(rel)
        run = V.run_pytest(files, snap, timeout=1200)
        # 复原：写回基线文本并逐字比 sha
        rel.write_text("".join(cur_lines), encoding="utf-8", newline="\n")
        restored = V.sha256(rel)
        by_file = split_failures(run["failed_names"])
        if (run["rc"] == 0) != (run["fields"]["failed"] + run["fields"]["errors"] == 0):
            rc_mismatch.append(f'{label}: rc={run["rc"]} 计数={run["fields"]} '
                               f'行="{run["summary_line"]}"')
        target_red = by_file.get(TARGET, [])
        collateral_red = {k: v for k, v in by_file.items() if k != TARGET}
        rows.append({
            "id": label, "kind": kind, "region": expect_region,
            "mutated": {"sha": mutated_sha, "differs_from_baseline": mutated_sha != baseline_sha},
            "rc": run["rc"], "fields": run["fields"], "summary_line": run["summary_line"],
            "failed_target": target_red, "failed_collateral": collateral_red,
            "collect_error": run["collect_error"],
            "bearing": bool(target_red) and not run["collect_error"],
            "status": ("broken" if run["collect_error"] else
                       ("bearing" if target_red else "non_bearing")),
            "sha_restored": restored == baseline_sha,
        })

    # 全量摘回：整份文件换成修前文本（矩阵的第 0 行，也是最粗的一档）
    mutate_and_run("H00-whole-file", "whole_file", list(before_lines), "整份文件")
    for i, (tag, i1, i2, i3, i4) in enumerate(ops, start=1):
        new = cur_lines[:i3] + before_lines[i1:i2] + cur_lines[i4:]
        snippet = "".join(cur_lines[i3:i4])[:80].replace("\n", " ⏎ ")
        mutate_and_run(f"H{i1:02d}-{tag}", "hunk", new,
                       f"cur {i3 + 1}-{i4} ← before {i1 + 1}-{i2} | {snippet}")
    # canary：只加一行注释，行为不可能变——它必须落在 non_bearing 里
    canary_at = next((idx for idx, ln in enumerate(cur_lines)
                      if ln.strip().startswith("def ") and "_callable" in ln), 0)
    canary_lines = cur_lines[:canary_at] + ["# verify-r4 canary: 注释不参与语义\n"] + cur_lines[canary_at:]
    mutate_and_run("X99-canary-comment", "canary", canary_lines,
                   f"在 cur 第 {canary_at + 1} 行前插入一条注释")

    mutated_true = sum(1 for r in rows if r["mutated"]["differs_from_baseline"])
    sha_ok = sum(1 for r in rows if r["sha_restored"])
    bearing = [r["id"] for r in rows if r["status"] == "bearing"]
    non_bearing = [r["id"] for r in rows if r["status"] == "non_bearing"]
    broken = [r["id"] for r in rows if r["status"] == "broken"]
    canary_rows = [r for r in rows if r["kind"] == "canary"]

    check("每行 rc 与计数必须同向（防把「跑不动」读成「跑红」）", rc_mismatch, [], "见 rows")
    check("每行 mutation 都必须真的改了文件", mutated_true, len(rows), f"{len(rows)} 行")
    check("每行复原后 sha 必须逐字等于基线", sha_ok, len(rows), "sha_restored 计数")
    check("行数分类必须穷尽（bearing+non_bearing+broken）",
          len(bearing) + len(non_bearing) + len(broken), len(rows), "不许有未分类行")
    check("全量摘回必须让锁变红（否则锁是装饰）",
          next(r["bearing"] for r in rows if r["kind"] == "whole_file"), True, "H00")
    check("canary 必须被矩阵归入 non_bearing（改了也不红）",
          [r["status"] for r in canary_rows], ["non_bearing"], "canary 若变红=锁对无关改动也尖叫")
    check("canary 的 sha 复原同样要成立",
          [r["sha_restored"] for r in canary_rows], [True], "X99")
    canary_caught = 1 if (canary_rows and canary_rows[0]["status"] == "non_bearing"
                          and canary_rows[0]["sha_restored"]) else 0
    if not bearing:
        REFUSE.append("所有 mutation 都没让锁变红 ⇒ 锁不认识这次修复，矩阵不构成证据")
    hunk_bearing = [r["id"] for r in rows if r["kind"] == "hunk" and r["status"] == "bearing"]
    if len(hunk_bearing) < 2:
        REFUSE.append(f"逐段摘回里只有 {len(hunk_bearing)} 段承重 ⇒ 合并修的机制片大多是空转")
    if broken:
        # 摘到半成品导致文件不可导入是预期内的混因，必须点名而不是当成「红」
        for r in rows:
            if r["status"] == "broken":
                REFUSE.append(f"{r['id']} 摘回后收集期就炸（collect_error）⇒ 该段不能算承重证据，"
                              f"要么与相邻段合并摘，要么如实另栏")

    doc = {
        "started": started, "lock_file": TARGET, "collateral_files": COLLATERAL,
        "snapshot": str(snap), "baseline_sha256": baseline_sha,
        "identity": ident, "base_run": base,
        "base_target_run": base_target, "target_collected": collected,
        "rc_mismatch": rc_mismatch,
        "mutated": mutated_true, "rows_total": len(rows),
        "sha_restored": sha_ok, "canary_caught": canary_caught,
        "bearing": bearing, "non_bearing": non_bearing, "broken_import": broken,
        "rows": rows,
        "note": "行按 difflib opcode 自动切片（不是修复环手点的 RC 列表）；"
                "bearing=摘掉该段后目标锁里至少 1 条用例变红；"
                "non_bearing=摘掉照旧绿（锁不认这段）；broken=摘成半成品不可导入，不算证据",
        "self_checks": CHECKS,
        "refuse": sorted(set(REFUSE)),
        "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({
        "rows_total": len(rows), "bearing": len(bearing), "non_bearing": len(non_bearing),
        "broken": len(broken), "sha_restored": sha_ok, "canary_caught": canary_caught,
        "identity_ok": ident["under_snapshot"],
        "non_bearing_ids": non_bearing, "refuse": doc["refuse"]},
        ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
