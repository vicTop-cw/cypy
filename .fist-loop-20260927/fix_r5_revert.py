"""R5-修复 的回退矩阵（法④）：把每单的改动摘回 HEAD 原文，该单的锁必须变红，别单的锁不许被牵连。

回退单元为什么是「共享文件闭包」而不是「单」：rc 实测到多单落在同一个产品文件里（例如
cython_generator.py 上挂着 78/80/82/90 四张单），按文件摘回时这四单必然一起摘——把它们硬拆成四次
"孤立摘回"会得到假绿或假红。所以：
- 组 = 共享产品文件的单的并查集闭包；组内一起摘回（整文件回到 HEAD 原文）；
- 行 = 每单一条（矩阵条数 = 有产品码改动的认领单数，符合法④原文）；
- 每次摘回后把**全部**锁文件一次跑完 ⇒ 同时得到「本组单红没红」和「别组单还是绿不绿」两栏，
  不靠回忆、也不给牵连留藏处；
- 摘完逐文件写回并比 sha256：摘前/摘后同文件哈希必须相等（复原不是拼接）。

对照：摘一条「HEAD 与当前逐字相同」的符号（等于没摘）⇒ 该单锁必须仍然绿；它要也红了，
说明树被摘坏或夹具坏了，整套矩阵作废。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RC = HERE / "fix_r5_rc.json"
LOCKS = HERE / "fix_r5_locks.json"
INTAKE = HERE / "fix_r5_intake.json"
OUT = HERE / "fix_r5_revert.json"
WORK = HERE / "fix_r5_snap" / "revert"
PY = sys.executable
NODE_RE = re.compile(r"^(.+?::.+?)\s+(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+\[\s*\d+%\]", re.M)
# 与 fix_r5_locks.py 同一坑：参数化 id 里的 " - " 会把 nodeid 截断，所以只在异常名边界上切。
SUM_RE = re.compile(r"^FAILED (.+?) - ((?:\w*(?:Error|Exception)|Failed|assert).*)$", re.M)
BUG_RE = re.compile(r"::test_(?:bug|r5_)(\d{2})_")
CHECKS: list = []
REFUSE: list = []
CANARY: dict = {}
EXTRA: dict = {}


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sh(cmd: list, cwd: Path, timeout=2400) -> tuple:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout.decode("utf-8", "replace")


def git_show_head(rel: str) -> str:
    out = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return out.stdout


def git_show_head_bytes(rel: str) -> bytes:
    """按字节取 HEAD 原文：Windows 工作树是 CRLF，`git show` 给的是 LF，
    用文本模式回写会把「摘回」变成「换行符重排」，sha 复原那条就永远红。
    """
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(ROOT), capture_output=True)
    return out.stdout if out.returncode == 0 else b""


def identity_probe() -> dict:
    """副本树里 import 到的 cypyc 必须真的是副本树那份。

    已安装孪生/兄弟源码树会静默顶掉副本 ⇒ 摘回的动作落在没人看的树上，矩阵全是假绿。
    """
    out = subprocess.run(
        [PY, "-X", "utf8", "-c", "import cypyc;print(cypyc.__file__)"],
        cwd=str(WORK),
        env={**os.environ, "PYTHONPATH": str(WORK)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    got = (out.stdout or "").strip().replace("\\", "/")
    want = WORK.as_posix().replace("\\", "/")
    return {
        "imported_cypyc": got,
        "inside_work_tree": got.startswith(want),
        "rc": out.returncode,
        "stderr": (out.stderr or "")[:200],
    }


SKIP_TOP = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".fist-loop-20260927",
    ".fist-polish-20260926",
    "__pycache__",
    "build",
    "dist",
    "cypyc.egg-info",
    "node_modules",
    "output",
    "output_after",
    ".venv",
    "venv",
}
SKIP_SUFFIX = (".pyc", ".pyo", ".db-wal", ".db-shm", ".log")


def build_work_tree() -> dict:
    """副本树要「忠实到能当环境」：只跳缓存/构建产物/别的环的scratch，其余全量复制。

    上一版只拷了 5 个目录，tests/cli 那批在副本里连空操作摘回都会红 ⇒
    分辨力归零，矩阵作废。测试按 `Path(__file__).parents[1]` 找仓库根，
    所以 PROJECT-SPEC/SYNTAX/docs/examples/memory 都得在场。
    """
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    copied = 0
    skipped = 0
    for f in ROOT.rglob("*"):
        s = f.as_posix()
        rel = f.relative_to(ROOT)
        if not f.is_file():
            continue
        if rel.parts[0] in SKIP_TOP or "__pycache__" in s or s.endswith(SKIP_SUFFIX):
            skipped += 1
            continue
        dst = WORK / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        copied += 1
    return {"dir": WORK.relative_to(ROOT).as_posix(), "files": copied, "skipped": skipped}


def run_all_locks(lock_files: list) -> dict:
    rc, out = sh(
        [
            PY,
            "-X",
            "utf8",
            "-m",
            "pytest",
            *lock_files,
            "-v",
            "-rf",
            "--tb=line",
            "-p",
            "no:cacheprovider",
        ],
        WORK,
    )
    nodes = {m.group(1).replace("\\", "/"): m.group(2) for m in NODE_RE.finditer(out)}
    fails = {m.group(1).replace("\\", "/"): m.group(2).strip() for m in SUM_RE.finditer(out)}
    collected = re.findall(r"collected (\d+) items", out)
    return {
        "rc": rc,
        "nodes": nodes,
        "fails": fails,
        "collected": int(collected[-1]) if collected else -1,
        "tail": [ln.strip() for ln in (out or "").splitlines()[-3:] if ln.strip()],
    }


def nodes_of(run: dict, cid: int) -> list:
    out = []
    for n, st in run["nodes"].items():
        mb = BUG_RE.search(n)
        if mb and int(mb.group(1)) == cid:
            out.append((n, st))
    return sorted(out)


def group_of(cards: list, file_of_card: dict) -> list:
    """并查集：共享同一个产品文件的单进同一组（组是一起摘回的最小单元）。"""
    parent = {c: c for c in cards}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in cards:
        for b in cards:
            if a < b and set(file_of_card[a]) & set(file_of_card[b]):
                parent[find(b)] = find(a)
    buckets: dict = {}
    for c in cards:
        buckets.setdefault(find(c), []).append(c)
    return sorted(sorted(v) for v in buckets.values())


def main() -> int:
    started = now_iso()
    rc_doc = json.loads(RC.read_text(encoding="utf-8"))
    locks = json.loads(LOCKS.read_text(encoding="utf-8")) if LOCKS.exists() else {}
    if not locks:
        REFUSE.append("fix_r5_locks.json 不在盘上 ⇒ 没有锁节点可指认，矩阵只能空跑")
    tree = build_work_tree()
    if not (WORK / "cypyc").exists():
        REFUSE.append(f"回退工作树没建起来（{tree}）⇒ 只能作废")
        return finish(started, tree, [])

    lock_of: dict = {}
    for row in locks.get("runs", []):
        lock_of[row["bug_id"]] = sorted({f["file"] for f in row["files"]})
    # 装饰锁（旧码里一条都不红 ⇒ 这条锁不锁产品码）由法②的件点名；矩阵只引用那份名单，
    # 不在这里重新发明口径——否则两处各判各的，红的那条到底是锁不承重还是判据漂移就没人说得清。
    decorative_ids = sorted(locks.get("no_code_lock_ids") or [])
    all_lock_files = sorted({f for v in lock_of.values() for f in v})
    file_of_card = {
        int(k): [f for f in v if not f.startswith("tests/")]
        for k, v in (rc_doc.get("card_product_files") or {}).items()
        if v
    }
    cards = sorted(file_of_card)
    groups = group_of(cards, file_of_card)
    ident = identity_probe()
    touched = {f for c in cards for f in file_of_card[c]}
    root_before = {rel: sha256(ROOT / rel) for rel in sorted(touched) if (ROOT / rel).exists()}

    baseline = run_all_locks(all_lock_files)
    base_green = {n for n, st in baseline["nodes"].items() if st == "PASSED"}
    env_bad = sorted(n for n, st in baseline["nodes"].items() if st != "PASSED")
    EXTRA["baseline_not_green"] = {
        "nodes": env_bad[:12],
        "total": len(env_bad),
        "verbatim": [{"node": n, "why": baseline["fails"].get(n, "")[:200]} for n in env_bad[:6]],
    }
    control = ""
    for rel in sorted((WORK / "cypyc").rglob("*.py")):
        rp = rel.relative_to(WORK).as_posix()
        if rp in touched or not (ROOT / rp).exists():
            continue
        if git_show_head(rp):
            control = rp
            break
    canary = {"ran": False, "note": "找不到本环没改过的产品文件当反例"}
    if control:
        head_bytes = git_show_head_bytes(control)
        cur = (WORK / control).read_bytes()
        (WORK / control).write_bytes(head_bytes)
        run = run_all_locks(all_lock_files)
        went = sorted(n for n, st in run["nodes"].items() if st != "PASSED" and BUG_RE.search(n))
        (WORK / control).write_bytes(cur)
        canary = {
            "ran": True,
            "meaning": "把一条本环没改过的文件按 HEAD 原文重写 = 空操作 ⇒ 所有锁必须仍然全绿；"
            "有红就是夹具或环境自己坏了，整套矩阵作废",
            "file": control,
            "head_equals_current": head_bytes == cur,
            "nodes_went_bad": went[:6],
        }

    matrix = []
    CANARY.clear()
    CANARY.update(canary)
    planned = sorted(json.loads(INTAKE.read_text(encoding="utf-8")).get("planned_ids") or [])
    locked_ids = sorted(locks.get("locked_ids") or [])

    def revert_files(files: list) -> tuple:
        """把给定文件整档摘回 HEAD 原文 → 跑一次全量锁 → 按字节复原。返回 (run, 复原清单, 在场清单)。"""
        have = [f for f in files if (WORK / f).exists()]
        before = {rel: sha256(WORK / rel) for rel in have}
        original = {rel: (WORK / rel).read_bytes() for rel in have}
        for rel in have:
            head_bytes = git_show_head_bytes(rel)
            if head_bytes:
                (WORK / rel).write_bytes(head_bytes)
        run = run_all_locks(all_lock_files)
        for rel in have:
            (WORK / rel).write_bytes(original[rel])
        after = {rel: sha256(WORK / rel) for rel in have}
        return run, sorted(rel for rel in have if before[rel] == after[rel]), have

    def red_cards(run: dict) -> list:
        out = set()
        for n, st in run["nodes"].items():
            mb = BUG_RE.search(n)
            if mb and st != "PASSED":
                out.add(int(mb.group(1)))
        return sorted(out)

    # ── 阶段一：逐文件承重探针。摘回单元 = 本环改过的**每一个产品文件**，
    #    不是卡片自己点名的面：BUG-84 的面写着 type_checker，实测承重却在 scope_analyzer，
    #    BUG-88 的面写着 project_compiler，实测承重在 cli。归属由「摘掉它哪张单的锁变红」现测。
    units = sorted(
        rel for rel in (rc_doc.get("files_this_ring") or {}) if not rel.startswith("tests/")
    )
    locked_ids = sorted(locks.get("locked_ids") or [])
    bearing: dict = {}
    for rel in units:
        run, restored_files, have = revert_files([rel])
        bearing[rel] = {
            "cards": [c for c in red_cards(run) if c in locked_ids],
            "files": have,
            "sha_restored": restored_files,
        }
    unborne = sorted(rel for rel in units if not bearing[rel]["cards"])

    # ── 阶段二：按承重文件并查集成组（一单被多个文件承重 ⇒ 这些文件必须一起摘）。
    card_files: dict = {}
    for rel, b in bearing.items():
        for cid in b["cards"]:
            card_files.setdefault(cid, []).append(rel)
    cards2 = sorted(card_files)
    groups2 = group_of(cards2, {c: card_files[c] for c in cards2}) if cards2 else []

    # ── 阶段三：按组复扫，每单一行；组间牵连在这一遍逐条点名。
    matrix = []
    for g in groups2:
        files = sorted({f for c in g for f in card_files[c]})
        run, restored_files, have = revert_files(files)
        for cid in g:
            mine = nodes_of(run, cid)
            red = sorted(n for n, st in mine if st in ("FAILED", "ERROR"))
            matrix.append(
                {
                    "bug_id": cid,
                    "group": list(g),
                    "group_size": len(g),
                    "group_files": files,
                    "revert_mode": "整文件摘回 HEAD 原文（按实测承重闭包一起摘）",
                    "lock_files": lock_of.get(cid, []),
                    "has_lock": cid in locked_ids,
                    "bearing_files": sorted(card_files[cid]),
                    "not_measured": "",
                    "red_after_revert": red,
                    "red_assertion_level": sorted(
                        n for n in red if "AssertionError" in run["fails"].get(n, "")
                    ),
                    "stayed_green": sorted(n for n, st in mine if st == "PASSED"),
                    "verbatim_red": [run["fails"].get(n, "")[:200] for n in red][:4],
                    "collateral_went_red": sorted(
                        f"{n}={st}"
                        for n, st in run["nodes"].items()
                        if BUG_RE.search(n)
                        and int(BUG_RE.search(n).group(1)) not in g
                        and st != "PASSED"
                    ),
                    "sha_restored": restored_files,
                    "files": have,
                }
            )
    for cid in sorted(set(planned) - set(cards2)):
        why = (
            "本环没有这条单的锁（法②要求每单一条会失败的锁测试）"
            if cid not in locked_ids
            else "摘回本环改过的每一个产品文件都不打红这单的锁 ⇒ 这单没有承重的改动"
        )
        matrix.append(
            {
                "bug_id": cid,
                "group": [cid],
                "group_size": 1,
                "group_files": [],
                "revert_mode": "not_measured",
                "lock_files": lock_of.get(cid, []),
                "has_lock": cid in locked_ids,
                "bearing_files": [],
                "not_measured": why,
                "red_after_revert": [],
                "red_assertion_level": [],
                "stayed_green": [],
                "verbatim_red": [],
                "collateral_went_red": [],
                "sha_restored": [],
                "files": [],
            }
        )
    matrix.sort(key=lambda r: r["bug_id"])
    EXTRA["units_probed"] = units
    EXTRA["bearing"] = {k: v["cards"] for k, v in sorted(bearing.items())}
    EXTRA["unborne_files"] = unborne
    EXTRA["groups2"] = groups2
    EXTRA["declared_face_not_bearing"] = sorted(
        {
            f
            for c, fs in file_of_card.items()
            for f in fs
            if f in bearing and c not in bearing[f]["cards"]
        }
    )
    restored = run_all_locks(all_lock_files)
    root_after = {rel: sha256(ROOT / rel) for rel in root_before}
    dirtied = sorted(rel for rel in root_before if root_before[rel] != root_after[rel])
    EXTRA["identity"] = ident
    EXTRA["root_tree_sha_before"] = len(root_before)
    EXTRA["root_tree_dirtied"] = dirtied
    check(
        "副本树里 import 到的 cypyc 就是副本那份（摘回没落在别的树上）",
        ident["inside_work_tree"],
        True,
        f"实测 __file__={ident['imported_cypyc']} 期望在 {WORK.as_posix()} 下",
    )
    check(
        "真树（ROOT）在本矩阵全程未被写入",
        dirtied,
        [],
        f"摘回只许发生在 {WORK.relative_to(ROOT).as_posix()}；被写脏的文件：{dirtied[:4]}",
    )
    lost_rows = [
        baseline["collected"] != len(baseline["nodes"]),
        restored["collected"] != len(restored["nodes"]),
    ]
    EXTRA["baseline_run"] = {
        "rc": baseline["rc"],
        "collected": baseline["collected"],
        "nodes": len(baseline["nodes"]),
        "tail": baseline["tail"],
    }
    EXTRA["restored_run"] = {
        "rc": restored["rc"],
        "collected": restored["collected"],
        "nodes": len(restored["nodes"]),
        "tail": restored["tail"],
    }
    if baseline["collected"] < 0 or restored["collected"] < 0:
        REFUSE.append(
            "有一趟全量锁跑根本没数到节点（collected=-1）⇒ 是这一跑自己坏了，"
            f"不是矩阵判红：baseline rc={baseline['rc']} tail={baseline['tail'][:2]} / "
            f"restored rc={restored['rc']} tail={restored['tail'][:2]}"
        )
    regression = sorted(
        n for n, st in restored["nodes"].items() if st != "PASSED" and n in base_green
    )

    rows = sorted({r["bug_id"] for r in matrix})
    lock_rows = sorted(r["bug_id"] for r in matrix if r["has_lock"])
    red_rows = sorted(r["bug_id"] for r in matrix if r["red_after_revert"])
    red_lock_rows = sorted(r["bug_id"] for r in matrix if r["has_lock"] and r["red_after_revert"])
    strict_rows = sorted(
        r["bug_id"]
        for r in matrix
        if r["red_after_revert"] and r["red_assertion_level"] == r["red_after_revert"]
    )
    coll_rows = sorted({r["bug_id"] for r in matrix if r["collateral_went_red"]})
    measured_rows = sorted(r["bug_id"] for r in matrix if r["revert_mode"] != "not_measured")
    all_restored = all(len(r.get("sha_restored", [])) == len(r.get("files", [])) for r in matrix)
    broke_tree = sorted(
        r["bug_id"]
        for r in matrix
        if r["red_after_revert"]
        and not r["red_assertion_level"]
        and any(
            k in " ".join(r["verbatim_red"])
            for k in ("ImportError", "ModuleNotFoundError", "INTERNALERROR", "no tests ran")
        )
    )

    check(
        "副本树基线全绿（环境忠实——基线有红就不许用这套矩阵做判定）",
        [len(env_bad), baseline["rc"]],
        [0, 0],
        f"基线不绿 {len(env_bad)} 个节点：{env_bad[:4]}，rc={baseline['rc']}",
    )
    check(
        "矩阵条数 = 认领单数（没有产品码改动的单也要占一行，写 not_measured 而不是消失）",
        rows,
        planned,
        f"行 {len(rows)} / 认领 {len(planned)}；缺 {sorted(set(planned) - set(rows))}",
    )
    check(
        "有锁的单摘回后必须变红；例外只能是法②点名的装饰锁（两个方向都不许扩张）",
        [
            sorted(set(lock_rows) - set(red_lock_rows) - set(decorative_ids)),
            sorted(set(decorative_ids) - set(lock_rows)),
        ],
        [[], []],
        f"既不红又没被法②列为装饰锁：{sorted(set(lock_rows) - set(red_lock_rows) - set(decorative_ids))}；"
        f"装饰锁名单里有、矩阵里却没有锁节点（口径漂移）：{sorted(set(decorative_ids) - set(lock_rows))}",
    )
    check(
        "红不许是「把树摘坏」那一类（import/收集/内部错），这类一律点名",
        broke_tree,
        [],
        f"树被摘坏型的单：{broke_tree[:6]}",
    )
    check(
        "摘完写回后每个文件的 sha 必须与摘前一致，且全量锁恢复绿（复原不是拼接）",
        [all_restored, regression],
        [True, []],
        f"sha 全等 {all_restored} / 恢复后仍红的节点：{regression[:4]}",
    )
    check(
        "本环改过的每个产品文件必须至少打红一张单的锁（改了却没锁承重=这块改动没人验过）",
        unborne,
        [],
        f"没有锁承重的产品文件：{unborne[:6]}（探针单元 {len(units)} 个）",
    )
    check(
        "组间牵连在按承重闭包复扫后必须为零（摘 A 组不许打红 B 组的锁）",
        coll_rows,
        [],
        f"仍有组间牵连的单：{coll_rows[:8]}；承重探针把 {len(units)} 个产品文件并成 {len(groups2)} 组",
    )
    check(
        "两次全量跑的节点数必须等于 pytest 自己报的 collected（丢行=矩阵读不到真相）",
        lost_rows,
        [False, False],
        f"baseline {baseline['collected']}/{len(baseline['nodes'])} 、"
        f"restored {restored['collected']}/{len(restored['nodes'])}",
    )
    check(
        "反证：空操作摘回（本环没改过的文件）之后所有锁必须仍然全绿",
        canary.get("nodes_went_bad", ["没跑"]),
        [] if canary.get("ran") else ["没跑"],
        json.dumps(canary, ensure_ascii=False)[:300],
    )
    EXTRA["measured_rows"] = measured_rows
    EXTRA["rows_with_lock"] = lock_rows
    return finish(started, tree, matrix, groups, rows, red_rows, strict_rows, coll_rows, cards)


def finish(
    started, tree, matrix, groups=(), rows=(), red_rows=(), strict_rows=(), coll_rows=(), cards=()
) -> int:
    doc = {
        "started": started,
        "work_tree": tree,
        "matrix": matrix,
        "matrix_rows": len(matrix),
        "groups": groups,
        "groups_len": len(groups),
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "revert_red_ids": sorted(red_rows),
        "assertion_level_ids": sorted(strict_rows),
        "collateral": sorted(coll_rows),
        "sha_restored": sum(len(r.get("sha_restored", [])) for r in matrix),
        "sha_files_total": sum(len(r.get("files", [])) for r in matrix),
        "canary_no_op_revert": dict(CANARY),
        "extras": dict(EXTRA),
        "note": "回退单元=共享产品文件的并查集闭包；矩阵每单一行（条数 = 有产品码改动的认领单数）。"
        "摘回一律在 fix_r5_snap/revert 的副本里做，真树只读。",
        "refuse": sorted(
            set(REFUSE)
            | {
                f"判据自证未过：{c['label']}（实得 {json.dumps(c['got'], ensure_ascii=False)[:160]}）"
                for c in CHECKS
                if not c["ok"]
            }
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
                "matrix_rows": len(matrix),
                "groups": len(groups),
                "revert_red": len(doc["revert_red_ids"]),
                "assertion_level": len(doc["assertion_level_ids"]),
                "sha": f"{doc['sha_restored']}/{doc['sha_files_total']}",
                "collateral": doc["collateral"][:8],
                "red_checks": doc["self_checks_red"],
                "self_checks": f"{sum(1 for c in CHECKS if c['ok'])}/{len(CHECKS)}",
                "cards_rows": [len(rows), len(cards)],
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
