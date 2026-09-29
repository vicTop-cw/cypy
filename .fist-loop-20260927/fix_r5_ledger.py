"""账面闭环（法⑦）：能闭环的单是**算出来的**，不是我列出来的。

闭环集 = 五张判据件的交集（每张都从盘上现读）：
- fix_r5_intake.json 的本环认领栏（没有认领就没有授权面）；
- fix_r5_locks.json 的 locked ∩ lock_red_before ∩ lock_green_after（锁在旧码上红、在当前树上绿）；
- fix_r5_rc.json 的 card_product_files 非空（这单确实动了产品码，不是只加了测试）；
- fix_r5_revert.json 的 revert_red_ids（把这单的改动摘回，锁必须变红 ⇒ 锁承重）；
- fix_r5_baselines.json 的三套体系全绿（有一套红就不许发闭环件）。

每张单的留档文本（改了什么 / 锁在哪 / 证据在哪）也全部从上述件里反解拼出，不手抄根因键。
bug 单没有关闭 API，也没有 `[omega:required]` ⇒ 强度落在：任务库终态 + md 追加 + call_log 真有这些调用（三向对照）。
没进闭环集的认领单如实留 OPEN，并逐字写明卡在哪一道（转结），不许悄悄消失也不许写成"已修"。
幂等：账本里已经有 R5-修复 的留档段 ⇒ 直接拒跑（重复跑会多出第二条留档与第二条调用记录）。
"""

from __future__ import annotations

import datetime
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

LEDGER = ROOT / "memory" / "bugs.md"
DB = (ROOT / "fist-mbt.db").as_posix()
OUT = HERE / "fix_r5_ledger.json"
ART = {
    "intake": "fix_r5_intake.json",
    "locks": "fix_r5_locks.json",
    "rc": "fix_r5_rc.json",
    "revert": "fix_r5_revert.json",
    "baselines": "fix_r5_baselines.json",
    "impact": "fix_r5_impact.json",
    "lanes": "r5_fix_lanes.json",
}
MARK = "R5-修复 追加留档"
CHAIN_SQL = (
    "select count(*) from call_log where tool in "
    "('claim','execute','submit','verify') and params_json like ?"
)
REFUSE: list = []
CHECKS: list = []
_HEAD_CACHE: dict = {}


def now() -> str:
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


def load(name: str) -> dict:
    p = HERE / ART[name]
    if not p.exists():
        REFUSE.append(f"判据件 {ART[name]} 不在盘上 ⇒ 闭环集无法反解")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def block_span(text: str, key: str):
    """按根因键定位条目：`## BUG-nn` 标题到下一条标题。追加前后必须用同一个函数。"""
    return re.search(
        r"^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN\n- summary: \["
        + re.escape(key)
        + r"\].*?(?=^## BUG-|\Z)",
        text,
        re.M | re.S,
    )


def card_index(intake: dict) -> dict:
    return {c["key"]: c for c in intake.get("cards", []) if c.get("key")}


def head_exists(rel: str) -> bool:
    """HEAD 里就有这份文件 ⇒ 它是「既有面」，本环改它必须逐字交代（不许悄悄改）。"""
    if rel in _HEAD_CACHE:
        return _HEAD_CACHE[rel]
    out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(ROOT), capture_output=True)
    got = out.returncode == 0 and bool((out.stdout or b"").strip())
    _HEAD_CACHE[rel] = got
    return got


def old_faces_for(cid: int, lanes: dict) -> list:
    hits = []
    for x in lanes.get("lanes") or []:
        if cid not in (x.get("cards") or []):
            continue
        files = [f for f in x.get("files_reported") or [] if (ROOT / f).exists() and head_exists(f)]
        if files:
            hits.append(
                {
                    "lane": x["lane"],
                    "files": files,
                    "why": (x.get("corrections") or [])[:2],
                    "verbatim": (x.get("verbatim") or [])[:2],
                }
            )
    return hits


def preexisting_faces(lanes: dict) -> set:
    """本环被改动的「既有面」全集（跨车道），用于自证：每张既有面都必须在留档里点名过。"""
    out = set()
    for lane in lanes.get("lanes") or []:
        out |= {
            f for f in lane.get("files_reported") or [] if (ROOT / f).exists() and head_exists(f)
        }
    return out


def closed_set(intake: dict, locks: dict, rc: dict, revert: dict) -> list:
    """闭环集 = 认领 ∩ 有锁 ∩ 锁在旧码上红 ∩ 锁在当前树绿 ∩ 有产品改动 ∩ 摘回会红。

    「有产品改动」用两个面并起来：卡片自己点名的面（rc）+ 回退矩阵实测承重的面（revert.extras.bearing）。
    只用前者会把 BUG-84/88 这类「改在隔壁文件里」的单判成没改——那是归属口径的缺陷，不是没修。
    """
    planned = set(intake.get("planned_ids") or [])
    locked = set(locks.get("locked_ids") or [])
    red = set(locks.get("lock_red_before") or [])
    green = set(locks.get("lock_green_after") or [])
    touched = {int(k) for k, v in (rc.get("card_product_files") or {}).items() if v}
    bearing = (revert.get("extras") or {}).get("bearing") or {}
    touched |= {int(cid) for files in bearing.values() for cid in files}
    rev = set(revert.get("revert_red_ids") or [])
    return sorted(planned & locked & red & green & touched & rev)


def leftover_set(intake: dict, closed: list) -> list:
    return sorted(set(intake.get("planned_ids") or []) - set(closed))


def old_face_line(cid: int, lanes: dict) -> str:
    hits = old_faces_for(cid, lanes)
    if not hits:
        return ""
    parts = []
    for h in hits:
        parts.append(
            f"{h['lane']} 改了既有测试面 {json.dumps(h['files'], ensure_ascii=False)}；"
            f"为什么改（车道原话，逐字）：{json.dumps(h['why'], ensure_ascii=False)}；"
            f"改动前观察到的原文（逐字）：{json.dumps(h['verbatim'], ensure_ascii=False)}"
        )
    return "- 既有面改动交代（这些文件 HEAD 就存在，不是本环新增的锁）：" + " / ".join(parts) + "\n"


def body_for(
    cid: int,
    key: str,
    intake: dict,
    rc: dict,
    locks: dict,
    revert: dict,
    lanes: dict,
    status: str,
    updated: str,
) -> str:
    card = card_index(intake)[key]
    bearing_map = (revert.get("extras") or {}).get("bearing") or {}
    bearing_files = sorted(rel for rel, cs in bearing_map.items() if cid in cs)
    files = sorted(
        set((rc.get("card_product_files") or {}).get(str(cid)) or []) | set(bearing_files)
    )
    lrow = next((r for r in locks.get("runs", []) if r["bug_id"] == cid), {})
    rrow = next((r for r in revert.get("matrix", []) if r["bug_id"] == cid), {})
    lock_files = sorted({f["file"] for f in lrow.get("files", [])})
    verbatim = [v for f in lrow.get("files", []) for v in f.get("verbatim_red", [])][:2]
    nodes = sum(f["nodes"] for f in lrow.get("files", []))
    head_red = sum(len(f["red_before"]) for f in lrow.get("files", []))
    rev_red = len(rrow.get("red_after_revert", []))
    sha_ok_n = len(rrow.get("sha_restored", []))
    sha_files_n = len(rrow.get("files", []))
    coll = json.dumps(rrow.get("collateral_went_red", []), ensure_ascii=False)
    syms = json.dumps(
        sorted(k for k, cs in (rc.get("merged_root_causes") or {}).items() if cid in cs)[:6],
        ensure_ascii=False,
    )
    a_red = len(rrow.get("red_assertion_level") or [])
    grp = json.dumps(rrow.get("group") or [], ensure_ascii=False)
    lane_name = next(
        (x["lane"] for x in lanes.get("lanes", []) if cid in (x.get("cards") or [])),
        "",
    )
    return (
        f"\n### FIXED(verify={status}) — 2026-09-28 R5-修复 追加留档"
        "（本条目正文与标题行 `OPEN` 一字未改）\n\n"
        f"- 机制键：`{key}`\n"
        f"- 修复任务：`{card['task_id']}`（ns `bugs`，库里 `status={status}`、`updated_at={updated}`、"
        "`completed_by=cypy-fixer`）\n"
        f"- 改动点（file::symbol 由 git+ast 反解）：{syms}\n"
        f"- 文件面：{json.dumps(files[:6])}\n"
        f"- 锁：{json.dumps(lock_files)} 共 {nodes} 条节点；HEAD 快照复算红 {head_red} 条；"
        f"摘回本单改动后红 {rev_red} 条\n"
        f"- 修前红的原文（逐字，取前两条）：{json.dumps(verbatim, ensure_ascii=False)}\n"
        + old_face_line(cid, lanes)
        + f"- 回退矩阵行：mode=`{rrow.get('revert_mode', '')}`，摘回组 {grp}（组内 "
        f"{rrow.get('group_size', 0)} 单共享同一产品文件，一起摘回是定义不是含糊）；"
        f"sha 复原 {sha_ok_n}/{sha_files_n} 个文件；本单摘后红 {rev_red} 条（其中断言级 {a_red} 条）；"
        f"邻组牵连 {coll}\n"
        f"- 车道：`{lane_name}`（派单与回执见 .fist-loop-20260927/{ART['lanes']}）\n"
        "- 判据件：.fist-loop-20260927/fix_r5_locks.json、fix_r5_rc.json、fix_r5_revert.json、"
        "fix_r5_impact.json、fix_r5_baselines.json\n"
        "- 口径：账本没有关闭 API，`report_bug` 只能追加条目 ⇒ 修复状态以本段留档与任务库为准，"
        "标题行的 `OPEN` 不改写，也不据此判定门禁已绿。\n"
    )


def leftover_body(
    cid: int,
    key: str,
    card: dict,
    closed: list,
    locks: dict,
    rc: dict,
    revert: dict,
    lanes: dict,
) -> str:
    reasons = []
    if cid not in set(locks.get("locked_ids") or []):
        reasons.append("本环没有这条单的锁（法②要求每单一条会失败的锁测试）")
    if cid not in set(locks.get("lock_red_before") or []):
        reasons.append("锁在 HEAD 快照树上没红")
    if cid not in set(locks.get("lock_green_after") or []):
        reasons.append("锁在当前树上没绿")
    if not (rc.get("card_product_files") or {}).get(str(cid)):
        reasons.append(
            f"这单点名的产品文件在本环窗口里没有改动（卡片点名面 {card['product_faces'][:3]}；"
            "若回退矩阵在别的文件上测到承重，按 revert.extras.bearing 那栏复核）"
        )
    if cid not in set(revert.get("revert_red_ids") or []):
        row = next((r for r in revert.get("matrix") or [] if r["bug_id"] == cid), {})
        reasons.append(
            f"回退矩阵里这单摘回后没红（{row.get('not_measured') or '行缺失'}）"
            "⇒ 锁不承重或改动不在本环面"
        )
    quote = json.dumps(card["handoff_quote"] or card["key"], ensure_ascii=False)
    return (
        "\n### NOT-FIXED(R5-修复 转结) — 状态仍是 OPEN，逐字写明卡在哪\n\n"
        + f"- 机制键：`{key}`；服务端单号：`{card['task_id'] or '无'}`\n"
        + "".join(f"- 卡点：{r}\n" for r in reasons)
        + f"- 卡片原文的修前观察（逐字）：{quote}\n"
        + old_face_line(cid, lanes)
        + f"- 归属栏：`{card['column']}`（理由：{card['reason']}）\n"
        + "- 口径：入账未修是合法终态；这条不是「没问题」，下一环要按同一套判据重新认领。\n"
    )


def out_of_radius(lanes: dict, intake: dict) -> list:
    """车道改了既有测试面，但它认领的单一张都不在本环认领栏 ⇒ 越出认领半径，必须单独入账。

    这一栏不是「补个说明」：改动已经在盘上了，删它等于毁掉别人的工作，不记等于悄悄改测试。
    所以如实追加一段 OUT-OF-RADIUS，并把裁决交给指挥官。
    """
    planned = set(intake.get("planned_ids") or [])
    hits = []
    for lane in lanes.get("lanes") or []:
        cards = set(lane.get("cards") or [])
        if cards & planned:
            continue
        files = [
            f
            for f in lane.get("files_reported") or []
            if f.startswith("tests/") and (ROOT / f).exists() and head_exists(f)
        ]
        if files:
            hits.append(
                {
                    "lane": lane["lane"],
                    "cards": sorted(cards),
                    "files": sorted(files),
                    "why": lane.get("corrections") or [],
                    "verbatim": lane.get("verbatim") or [],
                }
            )
    return hits


def out_of_radius_body(cid: int, key: str, card: dict, hit: dict) -> str:
    return (
        "\n### OUT-OF-RADIUS(R5-修复 越出认领半径) — 状态仍是 OPEN，逐字写明改了什么\n\n"
        + f"- 机制键：`{key}`；服务端单号：`{card.get('task_id') or '无'}`\n"
        + f"- 归属栏：`{card.get('column')}`（理由：{card.get('reason')}）⇒ 本环认领表里没有这张单\n"
        + f"- 越界事实：车道 `{hit['lane']}` 改了既有测试面 "
        f"{json.dumps(hit['files'], ensure_ascii=False)}，其派单卡 {hit['cards']} 未进本环认领栏\n"
        + f"- 车道原话（逐字，为什么动它）：{json.dumps((hit.get('why') or [])[:2], ensure_ascii=False)}\n"
        + "- 处置：改动如实保留在盘上（删它等于毁掉已完成的工作，也不构成「没改」），"
        "本单状态仍 OPEN，不据此判门禁绿；要不要收这批改法交指挥官裁决。\n"
    )


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check_main()
    started = now()
    intake, locks, rc, revert = load("intake"), load("locks"), load("rc"), load("revert")
    baselines, impact, lanes = load("baselines"), load("impact"), load("lanes")
    ts_green = json.dumps(baselines.get("three_systems_green"), ensure_ascii=False)
    if baselines.get("three_systems_ok") is not True:
        REFUSE.append(f"三套体系没全绿（{ts_green}）⇒ 不发闭环件")
    md = LEDGER.read_text(encoding="utf-8")
    ledger_before = len(re.findall(r"^## BUG-\d+", md, re.M))
    if MARK in md:
        print(
            json.dumps(
                {"refuse": [f"账本里已有「{MARK}」⇒ 幂等门拒绝重复驱动"]}, ensure_ascii=False
            )
        )
        return 1

    closed = closed_set(intake, locks, rc, revert)
    leftover = leftover_set(intake, closed)
    if not closed:
        REFUSE.append("闭环集为空 ⇒ 五件交集没算出任何一张单，判据链断了")
    keys = card_index(intake)
    by_key = {k: v for k, v in keys.items() if v["id"] in closed}
    leftover_keys = {k: v for k, v in keys.items() if v["id"] in leftover}

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bug_rows = {
        r[0]: r[1] for r in con.execute("select id, description from tasks where ns='bugs'")
    }
    con.close()
    tid_by_key = {}
    for tid, desc in bug_rows.items():
        for key in by_key:
            if "[" + key + "]" in (desc or ""):
                tid_by_key.setdefault(key, []).append(tid)
    multi = [k for k, v in tid_by_key.items() if len(v) != 1]
    if multi or len(tid_by_key) != len(by_key):
        REFUSE.append(
            f"bug 任务与机制键对不上：找到 {len(tid_by_key)}/{len(by_key)}，多对/少对 {multi}"
        )

    client = lfist_lib.Client(timeout=180)
    results = []
    for key in sorted(by_key):
        tid = tid_by_key[key][0]
        card = by_key[key]
        steps = []
        con = sqlite3.connect(f"file:{DB}", uri=True)
        st = con.execute("select status from tasks where id=?", (tid,)).fetchone()
        con.close()
        if st and st[0] != "已完成":
            pf = (rc.get("card_product_files") or {}).get(str(card["id"])) or []
            lr = next((r for r in locks["runs"] if r["bug_id"] == card["id"]), {})
            dsum = (
                f"产品码改动 {json.dumps(pf[:4])}；"
                f"锁 {json.dumps(sorted({f['file'] for f in lr.get('files', [])}))}"
            )
            calls = [
                ("claim", {"task_id": tid, "assignee": "cypy-fixer", "now": now()}),
                (
                    "execute",
                    {
                        "task_id": tid,
                        "now": now(),
                        "deliverable": f"修 {key}：{dsum}",
                    },
                ),
                ("submit", {"task_id": tid, "now": now()}),
                ("verify", {"task_id": tid, "now": now(), "verifier": "cypy-fixer"}),
            ]
            for call, args in calls:
                r = client.call(call, args)
                err = r.get("error") if isinstance(r, dict) else None
                steps.append(
                    {
                        "call": call,
                        "ok": not err,
                        "echo": (
                            json.dumps(r, ensure_ascii=False)[:200]
                            if isinstance(r, dict)
                            else str(r)[:200]
                        ),
                    }
                )
        else:
            steps.append(
                {"call": "skip", "ok": True, "echo": f"库里已是 {st[0] if st else '读不到'}"}
            )
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        final = con.execute(
            "select status, updated_at, completed_by from tasks where id=?", (tid,)
        ).fetchone()
        con.close()
        if not final or final[0] != "已完成":
            REFUSE.append(
                f"{tid}（{key}）没驱动到已完成：{json.dumps(steps, ensure_ascii=False)[:300]}"
            )
        results.append(
            {
                "bug_id": card["id"],
                "root_cause_key": key,
                "task_id": tid,
                "steps": steps,
                "final_status": final[0] if final else "",
                "completed_by": final[2] if final else "",
            }
        )

    appended = []
    for res in results:
        m = block_span(md, res["root_cause_key"])
        if not m:
            REFUSE.append(f"账本里找不到 {res['root_cause_key']} 的条目 ⇒ 不追加")
            continue
        if "### FIXED" in m.group(0):
            appended.append(
                {"key": res["root_cause_key"], "appended": False, "why": "已有历史 FIXED 段"}
            )
            continue
        at = m.end(0)
        md = (
            md[:at].rstrip("\n")
            + "\n"
            + body_for(
                res["bug_id"],
                res["root_cause_key"],
                intake,
                rc,
                locks,
                revert,
                lanes,
                res["final_status"],
                now(),
            )
            + "\n"
            + md[at:].lstrip("\n")
        )
        appended.append({"key": res["root_cause_key"], "appended": True, "why": ""})

    for key, card in sorted(leftover_keys.items()):
        m = block_span(md, key)
        if not m:
            continue
        if "### NOT-FIXED(R5-修复 转结)" in m.group(0):
            appended.append({"key": key, "appended": False, "why": "已有本环绕结段"})
            continue
        at = m.end(0)
        md = (
            md[:at].rstrip("\n")
            + "\n"
            + leftover_body(card["id"], key, card, closed, locks, rc, revert, lanes)
            + "\n"
            + md[at:].lstrip("\n")
        )
        appended.append({"key": key, "appended": True, "why": "转结段"})
    booked_orphan = []
    for hit in out_of_radius(lanes, intake):
        for cid in hit["cards"]:
            card = next((c for c in intake.get("cards") or [] if c["id"] == cid), None)
            if not card:
                REFUSE.append(
                    f"车道 {hit['lane']} 的卡 {cid} 不在认领件的 cards 里 ⇒ 越界改动无法入账"
                )
                continue
            m = block_span(md, card["key"])
            if not m:
                REFUSE.append(
                    f"账本里找不到 {card['key']} 的条目 ⇒ 越界改动 {hit['files']} 没人记账"
                )
                continue
            if "### OUT-OF-RADIUS(R5-修复 越出认领半径)" in m.group(0):
                booked_orphan.append(
                    {
                        "key": card["key"],
                        "lane": hit["lane"],
                        "files": hit["files"],
                        "appended": False,
                    }
                )
                continue
            at = m.end(0)
            md = (
                md[:at].rstrip("\n")
                + "\n"
                + out_of_radius_body(cid, card["key"], card, hit)
                + "\n"
                + md[at:].lstrip("\n")
            )
            booked_orphan.append(
                {"key": card["key"], "lane": hit["lane"], "files": hit["files"], "appended": True}
            )
    LEDGER.write_text(md, encoding="utf-8", newline="\n")

    md_after = LEDGER.read_text(encoding="utf-8")
    logs = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    three = []
    for res in results:
        blk = block_span(md_after, res["root_cause_key"])
        text = blk.group(0) if blk else ""
        calls = logs.execute(CHAIN_SQL, ('%"' + res["task_id"] + '"%',)).fetchone()[0]
        three.append(
            {
                "key": res["root_cause_key"],
                "bug_id": res["bug_id"],
                "md_fixed": "### FIXED(verify=已完成)" in text,
                "md_blank_line_before": bool(re.search(r"\n\n### FIXED\(verify=已完成\)", text)),
                "sqlite_done": res["final_status"] == "已完成",
                "call_log_rows": calls,
            }
        )
    open_left = []
    for k, c in sorted(leftover_keys.items()):
        blk = block_span(md_after, k)
        open_left.append(
            {
                "key": k,
                "bug_id": c["id"],
                "md_not_fixed": bool(blk) and "### NOT-FIXED(R5-修复 转结)" in blk.group(0),
            }
        )
    logs.close()
    bad = [
        t
        for t in three
        if not (
            t["md_fixed"]
            and t["md_blank_line_before"]
            and t["sqlite_done"]
            and t["call_log_rows"] >= 3
        )
    ]
    if bad:
        REFUSE.append(f"三向对照不一致：{json.dumps(bad, ensure_ascii=False)[:400]}")
    bad_open = [o for o in open_left if not o["md_not_fixed"]]
    if bad_open:
        REFUSE.append(f"转结段没写进去：{json.dumps(bad_open, ensure_ascii=False)[:300]}")

    old_tests = {f for f in preexisting_faces(lanes) if f.startswith("tests/")}
    undisclosed = sorted(f for f in old_tests if f not in md_after)
    check(
        "本环改动的既有测试面必须逐张写进留档（不许悄悄改别人的钉档）",
        undisclosed,
        [],
        f"既有测试面 {len(old_tests)} 个，追加后仍未点名 {len(undisclosed)} 个：{undisclosed[:4]}",
    )
    check(
        "越出认领半径的车道改动必须逐条入账（OUT-OF-RADIUS 段数 = 这类车道卡数）",
        len(out_of_radius(lanes, intake)),
        len(booked_orphan),
        f"越界车道卡 {len(out_of_radius(lanes, intake))} 条，入账 {len(booked_orphan)} 条："
        f"{json.dumps(booked_orphan, ensure_ascii=False)[:220]}",
    )

    ledger_total = len(re.findall(r"^## BUG-\d+", md_after, re.M))
    open_total = len(re.findall(r"^## BUG-\d+ \[[^\]]+\] \[\w+\] OPEN", md_after, re.M))
    n_app = len([a for a in appended if a["appended"] and a["key"] in by_key])
    check(
        "闭环集与留档条数一致",
        n_app,
        len(results),
        f"追加 {n_app} / 驱动 {len(results)}",
    )
    check(
        "转结栏逐张留档（一张都不许悄悄消失）",
        len([o for o in open_left if o["md_not_fixed"]]),
        len(leftover_keys),
        f"转结 {len(leftover_keys)} 张：{sorted(leftover_keys)}",
    )
    check(
        "账本条目总数不因本轮追加而变化（只追加段落，不新增也不删除条目）",
        ledger_total,
        ledger_before,
        f"追加前 {ledger_before} 条 / 追加后 {ledger_total} 条",
    )
    check(
        "语料命中逐张进挂账（有命中就要有交代）",
        impact.get("adjudication_needed", -1),
        len(impact.get("corpus_adjudication_files") or []),
        f"adjudication={impact.get('adjudication_needed')}",
    )
    doc = {
        "started": started,
        "closed_ids": closed,
        "closed_keys_len": len(closed),
        "fixed_sections": sorted(a["key"] for a in appended if a["appended"] and a["why"] == ""),
        "not_fixed_sections": sorted(
            a["key"] for a in appended if a["appended"] and a["why"] == "转结段"
        ),
        "leftover_ids": leftover,
        "leftover_len": len(leftover),
        "cards": results,
        "appended": appended,
        "three_way": three,
        "three_way_bad": bad,
        "leftover_marked": open_left,
        "out_of_radius_booked": booked_orphan,
        "agree_total": len(three) - len(bad),
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "ledger_total": ledger_total,
        "ledger_open_total": open_total,
        "impact_adjudication": impact.get("corpus_adjudication_files") or [],
        "note": "闭环集是五件交集算出来的；bug 单没有 [omega:required] ⇒ Omega 三连对它不可用（既定语义），"
        "强度在锁 + 旧码复算 + 回退矩阵 + 影响面四件判据上。",
        "refuse": sorted(set(REFUSE))
        + [f"判据自证未过：{c['label']}" for c in CHECKS if not c["ok"]],
        "at_utc": now(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "closed_ids": closed,
                "leftover_ids": leftover,
                "agree_total": doc["agree_total"],
                "ledger_total": ledger_total,
                "ledger_open_total": open_total,
                "red_checks": doc["self_checks_red"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


def check_main() -> int:
    """只读复核：驱动件落盘后若驱动又被格式化，这一格独立重读 sqlite + md。"""
    intake, locks = load("intake"), load("locks")
    closed = closed_set(intake, locks, load("rc"), load("revert"))
    keys = card_index(intake)
    md = LEDGER.read_text(encoding="utf-8")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = []
    for cid in closed:
        key = next((k for k, v in keys.items() if v["id"] == cid), "")
        tids = [
            t
            for t, d in con.execute("select id, description from tasks where ns='bugs'")
            if key and "[" + key + "]" in (d or "")
        ]
        tid = tids[0] if len(tids) == 1 else ""
        st = (
            con.execute("select status, completed_by from tasks where id=?", (tid,)).fetchone()
            if tid
            else None
        )
        calls = con.execute(CHAIN_SQL, ('%"' + tid + '"%',)).fetchone()[0] if tid else 0
        blk = block_span(md, key)
        rows.append(
            {
                "bug_id": cid,
                "key": key,
                "task_id": tid,
                "status": st[0] if st else "",
                "completed_by": st[1] if st else "",
                "md_fixed": bool(blk) and "### FIXED(verify=已完成)" in blk.group(0),
                "call_log_rows": calls,
            }
        )
    con.close()
    bad = [
        r
        for r in rows
        if not (
            r["status"] == "已完成"
            and r["completed_by"] == "cypy-fixer"
            and r["md_fixed"]
            and r["call_log_rows"] >= 4
        )
    ]
    doc = {
        "mode": "check",
        "rows": rows,
        "total": len(rows),
        "agree_total": len(rows) - len(bad),
        "refuse": sorted(set(REFUSE))
        + ([f"只读复核不一致：{json.dumps(bad, ensure_ascii=False)}"] if bad else []),
        "at_utc": now(),
    }
    (HERE / "fix_r5_ledger_check.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {"refuse": doc["refuse"], "agree_total": doc["agree_total"], "total": doc["total"]},
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
        import traceback

        last = (traceback.format_exc().strip().splitlines() or [""])[-1]
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc} @ {last}"], "at_utc": now()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc} @ {last}"}, ensure_ascii=False))
        sys.exit(2)
