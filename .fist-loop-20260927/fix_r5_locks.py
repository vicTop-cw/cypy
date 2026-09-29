"""R5-修复 的锁先行见证（法②）：每条锁必须在「HEAD 产品码 + 本轮测试」的独立快照树里跑到断言级红。

为什么要在快照树里跑：今天全绿不能证明锁住过——只有拿改动前的产品码复算，才知道这条断言是承重墙
还是装饰。快照用 `git archive HEAD` 解到 .fist-loop-20260927/fix_r5_snap/head/（只读仓库，不动 .git），
再把本轮 tests/ 与判据件覆盖进去 ⇒ 代码是旧的，测试是新的。

测的是什么（全部子进程实测，不摘子代理的话）：
- 每个锁文件在快照树跑一次、在当前树跑一次，逐节点（nodeid）取 PASSED/FAILED/ERROR；
- 按 `def test_bug<号>_*` 前缀把节点归到单号 ⇒ 每张有锁的单必须「快照里红 + 当前绿」；
- 红按三档分栏：**断言级**（含 `pytest.fail`）／**产品异常级**（旧码解析不了这个形状，同样是缺陷）／
  **夹具类**（缺文件、收集错、INTERNALERROR、没跑到）——第三档一律判红，不许冒充锁；
- 快照树要覆盖 `memory/`：读账本的锁在两棵树里必须看到同一份账，否则它的红来自「快照少一个文件」。
- 旧码里一条都不红的单只能落在「车道自述没有交付条目」那张名单里（`r5_fix_lanes.json` 的
  `undelivered_cards`，双向对齐）：既不并进闭环主张，也不许悄悄变成第三种状态。
  上一版把「每张有锁单都必须红」写成无条件门，于是一条只查账本在场性的装饰锁（BUG-73）
  把整套判据判红——那是**判据宽于主张**，红的是测量器自己。

三条对照：快照树里 HEAD 就有的测试必须数得到绿（证明快照不是恒红）；点名一个不存在的函数必须「没跑到」
（证明我没把 rc 当结论）；被认领但没有锁的单必须逐张点名，不并进闭环主张。
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INTAKE = HERE / "fix_r5_intake.json"
LANES_F = HERE / "r5_fix_lanes.json"
OUT = HERE / "fix_r5_locks.json"
SNAP = HERE / "fix_r5_snap" / "head"
PY = sys.executable
NODE_RE = re.compile(r"^(.+?::.+?)\s+(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+\[\s*\d+%\]", re.M)
# 短汇总行是 `FAILED <nodeid> - <message>`，但参数化 id 里可以合法出现 " - "
# （如 `..._keeps_parens[a - (b - c)-a - (b - c)]`）⇒ 只能锚在「异常名/assert」的边界上切，
# 否则 nodeid 被截断、message 成空串，一条真红会被误判成「没有承载」。
SUM_RE = re.compile(r"^FAILED (.+?) - ((?:\w*(?:Error|Exception)|Failed|assert).*)$", re.M)
DEF_RE = re.compile(r"(?m)^def (?:test_bug|test_r5_)(\d{2})_")
NODE_BUG_RE = re.compile(r"::test_(?:bug|r5_)(\d{2})_")
PROBE_FILE = "tests/test_codegen_verification.py"
CHECKS: list = []
REFUSE: list = []
GREEN_ON_HEAD: list = []
RED_LOGS: dict = {}
HARNESS_ROWS: list = []
NO_CODE_LOCKS: list = []


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def sh(cmd: list, cwd: Path, timeout=2400) -> tuple:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    t0 = time.perf_counter()
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout.decode("utf-8", "replace"), round(time.perf_counter() - t0, 1)


def identity_probe(cwd: Path) -> dict:
    """钉住「这次 import 的 cypyc 就是这棵树里的」——已安装的孪生会静默顶掉源码树。"""
    rc, out, _ = sh(
        [
            PY,
            "-X",
            "utf8",
            "-c",
            "import cypyc,pathlib;print(cypyc.__file__);"
            "print((pathlib.Path(cypyc.__file__)).resolve().parent.name)",
        ],
        cwd,
        timeout=120,
    )
    lines = out.strip().splitlines()
    return {"rc": rc, "file": lines[0] if lines else "", "resolved_under": str(cwd)}


def build_snapshot() -> dict:
    if SNAP.exists():
        shutil.rmtree(SNAP)
    SNAP.mkdir(parents=True)
    p = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
    )
    if p.returncode != 0:
        REFUSE.append(
            f"git archive HEAD 失败 rc={p.returncode}：{p.stderr.decode('utf-8', 'replace')[:200]}"
        )
        return {}
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(SNAP)
    copied = 0
    for rel in ("tests", "memory", ".fist-loop-20260927", ".fist-polish-20260926"):
        src = ROOT / rel
        if not src.exists():
            continue
        for f in src.rglob("*"):
            s = f.as_posix()
            if not f.is_file() or "__pycache__" in s or "fix_r5_snap" in s:
                continue
            if rel == "tests":
                if f.suffix in (".pyc", ".log"):
                    continue
            elif rel == "memory":
                # 账本与评审记录是**数据**不是产品码：读账本的锁在两棵树里必须看到同一份账，
                # 否则它的红来自「快照少一个文件」而不是「旧码有缺陷」。
                if f.suffix != ".md":
                    continue
            elif f.suffix not in (".py", ".json") or "hunt_r5_tmp" in s:
                continue
            dst = SNAP / rel / f.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied += 1
    rc, head, _ = sh(["git", "rev-parse", "--short", "HEAD"], ROOT, timeout=120)
    return {
        "dir": SNAP.relative_to(ROOT).as_posix(),
        "rc": rc,
        "head": head.strip(),
        "archived_plus_copied_files": sum(1 for _ in SNAP.rglob("*") if _.is_file()),
        "overwritten_from_worktree": copied,
        "identity": identity_probe(SNAP),
        "identity_current": identity_probe(ROOT),
    }


HARNESS_KEYS = (
    "FileNotFoundError",
    "ImportError",
    "ModuleNotFoundError",
    "INTERNALERROR",
    "no tests ran",
    "error collecting",
    "fixture ",
)


def classify_fail(msg: str) -> str:
    """把一条红分进三类，别让「测量器自己坏了」混进「旧码有缺陷」。

    assertion        ：测试自己的断言（含 `pytest.fail`，那是测试主动判红）
    product_exception：产品码抛出的异常（旧码解析不了这个形状，同样是缺陷）
    harness          ：夹具缺文件 / 收集错 / 内部错 / 没跑到 —— 这类一律不许算锁
    """
    low = (msg or "").lower()
    if not msg:
        return "empty"
    if "AssertionError" in msg or msg.startswith("Failed:"):
        return "assertion"
    if any(k.lower() in low for k in HARNESS_KEYS):
        return "harness"
    return "product_exception"


def run_pytest(target: Path, rel_file: str, extra=()) -> dict:
    args = [
        PY,
        "-X",
        "utf8",
        "-m",
        "pytest",
        rel_file,
        "-v",
        "-rf",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        *extra,
    ]
    rc, out, secs = sh(args, target)
    nodes = {}
    for m in NODE_RE.finditer(out):
        nodes[m.group(1).replace("\\", "/")] = m.group(2)
    fails = {m.group(1).replace("\\", "/"): m.group(2).strip() for m in SUM_RE.finditer(out)}
    collected = re.findall(r"collected (\d+) items", out)
    return {
        "rc": rc,
        "seconds": secs,
        "nodes": nodes,
        "collected": int(collected[-1]) if collected else -1,
        "fail_messages": fails,
        "no_tests_ran": "no tests ran" in out.lower(),
        "tail": out.strip().splitlines()[-2:],
    }


def main() -> int:
    started = now_iso()
    planned = sorted(json.loads(INTAKE.read_text(encoding="utf-8"))["planned_ids"])
    snap_meta = build_snapshot()
    if not (SNAP / "cypyc").exists():
        REFUSE.append(
            f"快照树里没有 cypyc/（{snap_meta.get('dir')}）⇒ 没有旧码复算面，锁先行无法证明"
        )
        return finish(started, snap_meta, [], planned)

    files_of: dict = {}
    for f in sorted((ROOT / "tests").rglob("test_*.py")):
        if "__pycache__" in f.as_posix():
            continue
        rel = f.relative_to(ROOT).as_posix()
        for cid in {
            int(x) for x in DEF_RE.findall(f.read_text(encoding="utf-8-sig", errors="replace"))
        }:
            if cid in planned:
                files_of.setdefault(cid, []).append(rel)
    lock_files = sorted({p for v in files_of.values() for p in v})
    locks_missing = sorted(set(planned) - set(files_of))
    for rel in lock_files:
        if not (SNAP / rel).exists():
            REFUSE.append(f"快照树里没有 {rel} ⇒ 覆盖步骤漏了，这条锁没法在旧码上复算")

    snap_runs = {rel: run_pytest(SNAP, rel) for rel in lock_files}
    cur_runs = {rel: run_pytest(ROOT, rel) for rel in lock_files}
    probe = run_pytest(SNAP, PROBE_FILE)
    ghost = run_pytest(SNAP, f"{PROBE_FILE}::test_bug9999_ghost_lock")

    runs = []
    for cid in sorted(files_of):
        per_file = []
        for rel in files_of[cid]:
            sn, cu = snap_runs[rel], cur_runs[rel]
            nodes = []
            for n in sn["nodes"]:
                mb = NODE_BUG_RE.search(n)
                if n.startswith(rel + "::") and mb and int(mb.group(1)) == cid:
                    nodes.append(n)
            nodes.sort()
            red = sorted(n for n in nodes if sn["nodes"][n] in ("FAILED", "ERROR"))
            kinds = {"assertion": [], "product_exception": [], "harness": [], "empty": []}
            for n in red:
                kinds[classify_fail(sn["fail_messages"].get(n, ""))].append(n)
            a_red = sorted(kinds["assertion"] + kinds["product_exception"])
            green = sorted(n for n in nodes if cu["nodes"].get(n) == "PASSED")
            per_file.append(
                {
                    "file": rel,
                    "nodes": len(nodes),
                    "red_before": red,
                    "red_assertion_level": a_red,
                    "red_by_kind": {k: sorted(v) for k, v in kinds.items()},
                    "verbatim_red": [sn["fail_messages"].get(n, "")[:200] for n in red],
                    "green_after": green,
                    "not_green": sorted(n for n in nodes if cu["nodes"].get(n) != "PASSED"),
                    "snapshot_seconds": sn["seconds"],
                    "current_seconds": cu["seconds"],
                }
            )
        runs.append({"bug_id": cid, "files": per_file})

    covered = sorted({r["bug_id"] for r in runs})
    red_ids = sorted({r["bug_id"] for r in runs if any(f["red_before"] for f in r["files"])})
    green_ids = sorted({r["bug_id"] for r in runs if all(f["green_after"] for f in r["files"])})
    # 「承载合规」按**单**判，不按单里的每个文件判：一张单可以在两个文件里都有锁节点，
    # 其中一档在旧码本来就是绿的（那张档只是防止回归）——要求每个文件都出红，
    # 判的就不是「这条锁承不承重」，而是「这单是不是只改了一个文件」。
    strict_ids = sorted(
        {
            r["bug_id"]
            for r in runs
            if any(f["red_before"] for f in r["files"])
            and all(len(f["red_assertion_level"]) == len(f["red_before"]) for f in r["files"])
            and all(not f["not_green"] for f in r["files"])
        }
    )
    probe_green = sum(1 for v in probe["nodes"].values() if v == "PASSED")
    node_total = sum(f["nodes"] for r in runs for f in r["files"])
    # 夹具/收集/内部错承载的红不算锁（那是测量器自己坏了），逐张点名。
    harness_rows = sorted(
        {
            r["bug_id"]
            for r in runs
            if any(f["red_by_kind"]["harness"] or f["red_by_kind"]["empty"] for f in r["files"])
        }
    )
    # 旧码里一条都不红的单：这条锁不锁产品码（装饰锁），逐张点名，不许并进「锁先行修好的单」。
    no_code_lock_ids = sorted(set(covered) - set(red_ids))
    no_code_but_not_all_green = sorted(
        {
            r["bug_id"]
            for r in runs
            if r["bug_id"] in no_code_lock_ids and any(f["not_green"] for f in r["files"])
        }
    )

    red_logs: dict = {}
    for log in sorted(HERE.glob("r5_fix_*.red.log")):
        txt = log.read_text(encoding="utf-8", errors="replace")
        if "AssertionError" not in txt:
            continue
        for cid in {int(x) for x in re.findall(r"test_bug(\d{2})_", txt)}:
            red_logs.setdefault(cid, []).append(log.name)
    green_on_head = sorted(set(covered) - set(red_ids))
    GREEN_ON_HEAD[:] = green_on_head
    HARNESS_ROWS[:] = harness_rows
    NO_CODE_LOCKS[:] = no_code_lock_ids
    RED_LOGS.clear()
    RED_LOGS.update(red_logs)
    lost_rows = {
        rel: [sn["collected"], len(sn["nodes"])]
        for rel, sn in snap_runs.items()
        if sn["collected"] != len(sn["nodes"])
    }
    lost_cur = {
        rel: [cu["collected"], len(cu["nodes"])]
        for rel, cu in cur_runs.items()
        if cu["collected"] != len(cu["nodes"])
    }
    check(
        "解析出的节点数必须等于 pytest 自己报的 collected 数（丢行=判据窄于主张）",
        [lost_rows, lost_cur],
        [{}, {}],
        f"快照丢行 {list(lost_rows.items())[:3]} / 当前丢行 {list(lost_cur.items())[:3]}",
    )
    check(
        "A 路没红的单必须逐张落到 B/D 待证栏（不许第三种状态，也不许悄悄消失）",
        sorted(set(covered) - set(red_ids) - set(green_on_head)),
        [],
        f"消失的单：{sorted(set(covered) - set(red_ids) - set(green_on_head))}",
    )
    check(
        "B 路红档必须真在盘上（红档文件名逐张实测，不是我记得）",
        sorted({p for v in red_logs.values() for p in v if not (HERE / p).exists()}),
        [],
        f"盘上没有的红档：{sorted({p for v in red_logs.values() for p in v})}",
    )

    check(
        "认领且有锁的单 = 实测跑到的单（没有中途丢文件）",
        sorted(files_of),
        covered,
        f"有锁 {len(files_of)} 张 / 跑到 {len(covered)} 张",
    )
    check(
        "每条锁的旧码红都不许由夹具缺文件/收集错/内部错承载（那类逐张点名，测量器自己坏了不算锁）",
        harness_rows,
        [],
        f"夹具类红所在单：{harness_rows}",
    )
    undelivered = (
        sorted(
            {
                int(cid)
                for lane in (json.loads(LANES_F.read_text(encoding="utf-8")).get("lanes") or [])
                for cid in (lane.get("undelivered_cards") or [])
            }
        )
        if LANES_F.exists()
        else []
    )
    check(
        "旧码里一条都不红的单只能落在「车道自述没有交付条目」那张名单里（逐张双向对齐）",
        [
            sorted(set(no_code_lock_ids) - set(undelivered)),
            sorted(set(undelivered) & set(red_ids)),
            no_code_but_not_all_green,
        ],
        [[], [], []],
        f"无红却没被声明未交付：{sorted(set(no_code_lock_ids) - set(undelivered))}；"
        f"声明未交付却有承重锁：{sorted(set(undelivered) & set(red_ids))}；"
        f"无红但当前树也不绿：{no_code_but_not_all_green}",
    )
    check(
        "每条锁都必须「当前绿」：有锁的单数 = 全绿的单数",
        green_ids,
        covered,
        f"当前不绿的：{sorted(set(covered) - set(green_ids))}",
    )
    check(
        "红的承载方式只能是断言或产品异常（每张「有红」的单，其全部红都由这两类承载）",
        sorted(set(strict_ids) & set(red_ids)),
        red_ids,
        f"有红但承载方式不合规的单：{sorted(set(red_ids) - set(strict_ids))}",
    )
    check(
        "对照1：快照树里 HEAD 就存在的测试必须数得到绿（快照不是恒红）",
        probe_green > 0,
        True,
        f"{PROBE_FILE} 在快照里 PASSED {probe_green} 条，rc={probe['rc']}",
    )
    check(
        "对照2：点名一条不存在的锁必须「没跑到」（证明我没把 rc 当结论）",
        [ghost["no_tests_ran"], ghost["rc"] != 0],
        [True, True],
        f"no_tests_ran={ghost['no_tests_ran']} rc={ghost['rc']}",
    )
    ident_s = snap_meta["identity"]["file"].replace("\\", "/")
    ident_c = snap_meta["identity_current"]["file"].replace("\\", "/")
    snap_pkg = (SNAP / "cypyc").as_posix().lower()
    cur_pkg = (ROOT / "cypyc").as_posix().lower()
    check(
        "对照3：两棵树各自 import 到自己包里的 cypyc（已安装孪生顶掉就全盘失真）",
        [
            ident_s.lower().startswith(snap_pkg),
            ident_c.lower().startswith(cur_pkg),
            ident_s != ident_c,
        ],
        [True, True, True],
        f"快照={ident_s} / 当前={ident_c}",
    )
    check(
        "锁节点总数必须 ≥ 有锁单数（每张单至少一条锁节点被真的跑到）",
        node_total >= len(covered),
        True,
        f"节点 {node_total} / 单 {len(covered)}",
    )

    return finish(
        started,
        snap_meta,
        runs,
        locks_missing,
        covered,
        red_ids,
        green_ids,
        strict_ids,
        probe_green,
        ghost,
        node_total,
    )  # noqa: E501


def finish(
    started,
    snap_meta,
    runs,
    locks_missing,
    covered=(),
    red_ids=(),
    green_ids=(),
    strict_ids=(),
    probe_green=0,
    ghost=None,
    node_total=0,
) -> int:
    doc = {
        "started": started,
        "snapshot": snap_meta,
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "locked_ids": sorted(covered),
        "lock_red_before": sorted(red_ids),
        "lock_green_after": sorted(green_ids),
        "assertion_level_red_only": sorted(strict_ids),
        "locks_missing": locks_missing,
        "no_code_lock_ids": sorted(NO_CODE_LOCKS),
        "harness_broken_cards": sorted(HARNESS_ROWS),
        "red_kind_totals": {
            kind: sum(len(f["red_by_kind"][kind]) for r in runs for f in r["files"])
            for kind in ("assertion", "product_exception", "harness", "empty")
        },
        "lock_green_on_head": sorted(GREEN_ON_HEAD),
        "red_log_evidence": {str(k): v for k, v in sorted(RED_LOGS.items())},
        "lock_nodes_total": node_total,
        "runs": runs,
        "canary_probe": {"file": PROBE_FILE, "passed_in_snapshot": probe_green},
        "ghost_probe": {
            "no_tests_ran": (ghost or {}).get("no_tests_ran"),
            "rc": (ghost or {}).get("rc"),
        },
        "note": "红/绿都是子进程实测：旧码树 = git archive HEAD 解出后覆盖本轮 tests/ 与 memory/；"
        "红按「断言 / 产品异常 / 夹具类」三档分栏，夹具类一律判红；无锁的认领单逐张列在 "
        "locks_missing，旧码不红又没有交付条目的单列在 no_code_lock_ids，两者都不并进闭环主张。",
        "refuse": sorted(
            set(REFUSE)
            | {f"判据自证未过：{c['label']}（实得 {c['got']}）" for c in CHECKS if not c["ok"]}
        ),
        "at_utc": now_iso(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "locked": doc["locked_ids"],
                "locks_missing": locks_missing,
                "green_on_head": doc["lock_green_on_head"],
                "red_log_cards": len(doc["red_log_evidence"]),
                "red_before": len(doc["lock_red_before"]),
                "green_after": len(doc["lock_green_after"]),
                "assertion_level": len(doc["assertion_level_red_only"]),
                "lock_nodes_total": node_total,
                "canary": doc["canary_probe"],
                "red_checks": doc["self_checks_red"],
                "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        last = (traceback.format_exc().strip().splitlines() or [""])[-1]
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc} @ {last}"], "at_utc": now_iso()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc} @ {last}"}, ensure_ascii=False))
        sys.exit(2)
