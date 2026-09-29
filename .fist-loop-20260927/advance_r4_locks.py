"""R4-推进 法④的承重证明：同一份锁文件在两棵树上跑，工作区必全绿、改前码必红。

「今天全绿」不是证据：这些锁抓的是本环刚补的名称面与 defer 声明面形状，只有拿**改前字节**
再跑一遍才知道它们承重。所以两条车道 + 四件自证：
① 身份：两棵树里 `cypyc/analyzer/type_checker.py` 的 sha 必须不同（相同就是两车道跑同一份码）；
② 条数：期望条数与「改前态应当红的 id 名单」都来自生成器写的 `advance_r4_lock_plan.json`
   （它按反解到的条目数算出），本件拿 pytest 的实测红点与 `--collect-only` 来比——
   两份独立来源不一致就红，不在这文件里手打 20/26 这类字面量；
③ 收集数：两棵树都收满同一批用例（少收＝文件被并进注释那类静默消失，绿也不作数）；
④ 分栏：改前态的红必须**恰好**等于 plan 的名单——账实锁与文档引用锁在两态都该绿，
   它们在改前态也红，说明锁钉错了东西（把「本环没改的东西」当成了本环的主张）。
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import advance_r4_lib as LIB  # noqa: E402
from loop_kit import collect_nodeids, parse_pytest_summary, record  # noqa: E402

OUT = HERE / "advance_r4_locks.json"
PLAN = json.loads((HERE / "advance_r4_lock_plan.json").read_text(encoding="utf-8"))
PREV = json.loads((HERE / "polish_r4_baselines.json").read_text(encoding="utf-8"))
LOCK = PLAN["file"]                    # 路径也由生成器给，不在这手打
N = PLAN["expected_tests"]
EXPECT_RED = sorted(PLAN["prefix_red_ids"])
EXPECT_GREEN = sorted(PLAN["prefix_green_ids"])
PREV_COLLECT = PREV["systems"]["collect"]["nodeids"]
SNAP = HERE / "advance_r4_locksnap"
EXTRA = ["tests", "SYNTAX", "memory/bugs.md", "pyproject.toml", "README.md"]
CHECKS: list = []
REFUSE: list = []


def build_snap(revert: bool) -> dict:
    if SNAP.exists():
        shutil.rmtree(SNAP)
    SNAP.mkdir(parents=True)
    for rel in LIB.CARRY:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = SNAP / rel
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*LIB.NOISE))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for rel in EXTRA:
        src, dst = ROOT / rel, SNAP / rel
        if not src.exists():
            REFUSE.append(f"快照树缺 {rel}：锁文件跑不起来")
            continue
        if dst.exists():
            continue                      # cypyc/pyproject/README 已由 CARRY 带过来
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*LIB.NOISE))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for rel in LIB.EDITED:
        p = SNAP / rel
        if revert:
            p.write_bytes((LIB.TMP / Path(rel).name).read_bytes())
    files = sum(1 for _ in SNAP.rglob("*.py"))
    return {"tree": SNAP.as_posix(), "py_files": files,
            "type_checker_sha": LIB.sha(SNAP / "cypyc/analyzer/type_checker.py"),
            "scope_analyzer_sha": LIB.sha(SNAP / "cypyc/analyzer/scope_analyzer.py"),
            "lock_sha": LIB.sha(SNAP / LOCK), "reverted": revert}


def run_pytest(tree: Path, args: list, tag: str) -> dict:
    log = LIB.TMP / f"locks_{tag}.txt"
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", LOCK, *args],
                       cwd=str(tree), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    text = (r.stdout or "") + (r.stderr or "")
    log.write_text(text, encoding="utf-8", newline="\n")
    s = parse_pytest_summary(text)
    reds = sorted({ln.split("::")[-1].split()[0] for ln in text.splitlines()
                   if ln.startswith("FAILED ")})
    return {"rc": r.returncode, "passed": s["passed"], "failed": s["failed"],
            "errors": s["errors"], "skipped": s["skipped"],
            "summary_line": s["summary_line"], "red_ids": reds,
            "rootdir": next((ln for ln in text.splitlines() if ln.startswith("rootdir:")), ""),
            "collect": collect_nodeids(text), "log": log.name,
            "log_bytes": log.stat().st_size}


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    snap = build_snap(revert=True)
    work = {"tree": ROOT.as_posix(),
            "type_checker_sha": LIB.sha(ROOT / "cypyc/analyzer/type_checker.py"),
            "scope_analyzer_sha": LIB.sha(ROOT / "cypyc/analyzer/scope_analyzer.py"),
            "lock_sha": LIB.sha(ROOT / LOCK), "reverted": False}
    if work["type_checker_sha"] == snap["type_checker_sha"]:
        REFUSE.append("两棵树的 type_checker.py sha 相同 ⇒ 换码没生效，下面的红/绿都是同一份码")
    if work["lock_sha"] != snap["lock_sha"]:
        REFUSE.append("两棵树跑的锁文件不是同一份 ⇒ 差分不成立")
    if work["scope_analyzer_sha"] == snap["scope_analyzer_sha"]:
        REFUSE.append("scope_analyzer.py 也没换回改前字节")

    a = run_pytest(ROOT, ["-q", "-p", "no:cacheprovider", "--no-header",
                          "-o", "addopts=", "--tb=line"], "work")
    b = run_pytest(SNAP, ["-q", "-p", "no:cacheprovider", "--no-header", "-o", "addopts=",
                          "--tb=no", "-rfs"], "prefix_code")
    c = run_pytest(ROOT, ["--collect-only", "-q", "-p", "no:cacheprovider", "--no-header",
                          "-o", "addopts="], "collect")

    record(CHECKS, REFUSE, f"工作区车道：本文件 {N} 条全绿（条数来自生成器的 plan）",
           [a["passed"], a["failed"], a["errors"]], [N, 0, 0], a["summary_line"])
    record(CHECKS, REFUSE, "改前码车道：必须出现红（红=锁承重）",
           b["failed"] >= 1, True, f"改前态 {b['summary_line']} 红点 {b['red_ids']}")
    record(CHECKS, REFUSE,
           f"基数自证：两车道「过+红+错」与 --collect-only 都等于 plan 的 {N} 条"
           "（少收＝用例静默消失，绿也不作数）",
           [a["passed"] + a["failed"] + a["errors"], b["passed"] + b["failed"] + b["errors"],
            c["collect"]], [N, N, N],
           f"work={a['summary_line']} prefix={b['summary_line']}")
    record(CHECKS, REFUSE,
           "改前态的红点名单要**恰好**等于 plan 声明的那批（依赖本轮新名字的探针）",
           b["red_ids"], EXPECT_RED,
           f"plan 名单 {EXPECT_RED}；实得 {b['red_ids']}；差集 "
           f"多红 {sorted(set(b['red_ids']) - set(EXPECT_RED))} "
           f"少红 {sorted(set(EXPECT_RED) - set(b['red_ids']))}")
    idw, idsn = LIB.identity_probe(ROOT), LIB.identity_probe(SNAP)
    record(CHECKS, REFUSE, "两条车道解析到的是各自那棵树的 cypyc（身份探针，不靠 cwd 口头保证）",
           [ROOT.name in idw["cypyc"] and SNAP.name not in idw["cypyc"],
            SNAP.name in idsn["cypyc"]], [True, True],
           f"work={idw.get('cypyc')} prefix={idsn.get('cypyc')}")
    unrelated = sorted(set(b["red_ids"]) & set(EXPECT_GREEN))
    record(CHECKS, REFUSE,
           "plan 里标为「两态都该绿」的锁（账实锁、文档引用锁、不依赖新名字的 defer 档）"
           "在改前态必须不红",
           unrelated, [], f"实红 {unrelated}（这些锁钉错了东西）")
    collect_text = (LIB.TMP / c["log"]).read_text(encoding="utf-8", errors="replace")
    got_ids = sorted({ln.strip().split("::")[-1] for ln in collect_text.splitlines()
                      if "::" in ln and not ln.startswith("===")})
    canary = {"work_green": a["failed"] == 0 and a["passed"] == N,
              "prefix_red": b["failed"] >= 1,
              "identity_differs": work["type_checker_sha"] != snap["type_checker_sha"],
              "collect_stable": (a["passed"] + a["failed"] + a["errors"]
                                 == b["passed"] + b["failed"] + b["errors"]
                                 == c["collect"] == N),
              "red_list_exact_match": b["red_ids"] == EXPECT_RED,
              "collected_ids_equal_plan_universe": (
                  got_ids == sorted(set(EXPECT_RED) | set(EXPECT_GREEN)))}
    record(CHECKS, REFUSE, "canary 六格必须同时成立（第六格：收集到的 id 全集要等于 plan 全集）",
           [len(canary), sorted(canary.values())], [6, [True] * 6],
           json.dumps({**canary, "ids_measured": len(got_ids),
                       "ids_plan": len(set(EXPECT_RED) | set(EXPECT_GREEN))},
                      ensure_ascii=False))

    shutil.rmtree(SNAP, ignore_errors=True)
    doc = {"started": started,
           "law": "名称面补口与 defer 声明面形状有永久回归锁，且锁在改前码上承重",
           "new_test_file": LOCK, "previous_round_collect_floor": PREV_COLLECT,
           "floor_source": "polish_r4_baselines.json 的实测收集数（不是手打目标）",
           "collect_after_locks": PREV_COLLECT + c["collect"],
           "expected_tests": N, "lock_plan": PLAN["breakdown"],
           "plan_prefix_red_ids": EXPECT_RED, "plan_prefix_green_count": len(EXPECT_GREEN),
           "collected_ids": got_ids,
           "lane_work": a, "lane_prefix_code": b, "lane_collect": c,
           "identity": {"work_type_checker_sha": work["type_checker_sha"],
                        "snap_type_checker_sha": snap["type_checker_sha"],
                        "work_scope_sha": work["scope_analyzer_sha"],
                        "snap_scope_sha": snap["scope_analyzer_sha"],
                        "lock_sha_work": work["lock_sha"], "lock_sha_snap": snap["lock_sha"]},
           "red_ids_prefix_code": b["red_ids"], "canary": canary,
           "generator": ".fist-loop-20260927/advance_r4_gen_locks.py",
           "sources": ["advance_r4_never.json", "advance_r4_builtins.json",
                       "advance_r4_filed.json", "advance_r4_dormant.json",
                       "advance_r4_lock_plan.json"],
           "self_checks": CHECKS, "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"refuse": doc["refuse"], "work": [a["passed"], a["failed"]],
                      "prefix": [b["passed"], b["failed"]], "collect": c["collect"],
                      "red_ids": b["red_ids"], "canary": canary},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
