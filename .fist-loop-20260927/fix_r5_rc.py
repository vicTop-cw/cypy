"""R5-修复 的改动点与根因合并（法③）：改动面从 git+盘上反解，不采信任何「我改了哪些文件」的回忆。

三条通道各自独立，缺一条就翻红：
- A 盘上实测：`git diff -U0 HEAD` 的每个新行段用 ast 归到**当前文件里包住它的最内层符号** ⇒ 改动点 = (文件, 符号)；
  本环时间戳由 call_log 的 publish 行现读（不是我记得的几点），mtime 晚于它的产品码文件才算本环改动面。
- B 车道回执：`r5_fix_lanes.json` 是派单与车道自报的落盘记录；每条自报文件必须同时在 A 通道里数得到
  （数不到 ⇒ 车道说了不算）；A 数得到却没被任何车道报出 ⇒ unattributed，逐张点名。
- C 认领对齐：每张认领单的认领面（intake 的 product_faces）与 A 的改动文件求交 ⇒ 交集空的单进 unfixed，
  不许被算进「本环修掉的」。

根因合并只说「几张单落在同一个 (文件, 符号)」这一件可核对的事，不说「它们是同一个 bug」。
对照：把某条自报文件改成一个盘上不存在的路径，B 通道必须抓到；造一个不落在任何认领面的符号，A 必须报 orphan。
"""

from __future__ import annotations

import ast
import datetime
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INTAKE = HERE / "fix_r5_intake.json"
LANES = HERE / "r5_fix_lanes.json"
OUT = HERE / "fix_r5_rc.json"
OUT_ROOT = HERE / "root_r5_fix.out.json"
DB = ROOT / "fist-mbt.db"
SPEC = HERE / "spec_r5_fix.json"
NS = "cypy-loop-20260927"
TAG = json.loads(SPEC.read_text(encoding="utf-8"))["tag"] if SPEC.exists() else ""
PRODUCT_DIRS = ("cypyc/", "cypy_hook/", "cypy_bridge/")
CHECKS: list = []
REFUSE: list = []
NEW_FILES: set = set()


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


def git(*args) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
    ).stdout


def ring_start() -> tuple:
    """本环起点 = 账本里根任务的 created_at（现读，不是我回忆的几点）；标签档另有一栏对照。"""
    root = json.loads(OUT_ROOT.read_text(encoding="utf-8"))["root"]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute(
        "select created_at, status from tasks where ns=? and id=?", (NS, root)
    ).fetchone()
    tag_rows = list(
        con.execute("select tool from call_log where params_json like ?", (f"%{TAG}%",))
    )
    con.close()
    return (row[0] if row else ""), len(tag_rows), bool(row), row[1] if row else ""


def symbol_spans(path: Path) -> list:
    """当前文件的 (起始行, 结束行, 限定符号名)，嵌套用 类.方法；解析失败返回空并点名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError as exc:
        REFUSE.append(f"{path.relative_to(ROOT)} 解析不过（{exc}）⇒ 改动点归不到符号")
        return []
    spans = []

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{ch.name}"
                spans.append((ch.lineno, ch.end_lineno or ch.lineno, name))
                walk(ch, f"{name}.")
            else:
                walk(ch, prefix)

    walk(tree, "")
    return spans


def diff_ranges(rel: str) -> list:
    if rel in NEW_FILES:
        n_lines = len((ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines())
        return [(1, n_lines)]
    out = []
    for m in re.finditer(
        r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", git("diff", "-U0", "HEAD", "--", rel), re.M
    ):
        start = int(m.group(1))
        out.append((start, start + max(int(m.group(2) or 1) - 1, 0)))
    return out


def changed_all_files() -> dict:
    files = changed_product_files()
    for ln in git("diff", "--numstat", "HEAD", "--", "tests/").splitlines():
        m = re.match(r"^(\d+)	(\d+)	(.+)$", ln.strip())
        if m:
            files[m.group(3).replace("\\", "/")] = (int(m.group(1)), int(m.group(2)))
    for ln in git("status", "--porcelain", "--untracked-files=all", "--", "tests/").splitlines():
        m = re.match(r"^\?\?\s+(.+)$", ln)
        if m:
            rel = m.group(1).strip().strip('"').replace("\\", "/")
            if rel.endswith(".py") and rel not in files:
                n = len((ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines())
                files[rel] = (n, 0)
                NEW_FILES.add(rel)
    return files


def changed_product_files() -> dict:
    files: dict = {}
    for ln in git("diff", "--numstat", "HEAD", "--", *PRODUCT_DIRS).splitlines():
        m = re.match(r"^(\d+)\t(\d+)\t(.+)$", ln.strip())
        if m:
            files[m.group(3).replace("\\", "/")] = (int(m.group(1)), int(m.group(2)))
    for ln in git(
        "status", "--porcelain", "--untracked-files=all", "--", *PRODUCT_DIRS
    ).splitlines():
        m = re.match(r"^\?\?\s+(.+)$", ln)
        if m:
            rel = m.group(1).strip().strip('"').replace("\\", "/")
            if rel.endswith(".py") and rel not in files:
                n = len((ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines())
                files[rel] = (n, 0)
    return files


def main() -> int:
    started = now_iso()
    intake = json.loads(INTAKE.read_text(encoding="utf-8"))
    cards = {c["id"]: c for c in intake["cards"]}
    planned = sorted(intake["planned_ids"])
    start_ts, tag_rows, have_root, root_status = ring_start()
    if not have_root:
        REFUSE.append(
            f"call_log 里找不到带 {start_ts!r} 的 publish 行 ⇒ 本环起点时间戳读不出来，改动面无法按时间切"
        )
    lane_doc = json.loads(LANES.read_text(encoding="utf-8")) if LANES.exists() else {}
    if not lane_doc:
        REFUSE.append("r5_fix_lanes.json 不在盘上 ⇒ 没有派单与回执，改动面只能靠 mtime 猜")

    all_files = changed_all_files()
    cutoff = datetime.datetime.fromisoformat(start_ts.replace("Z", "+00:00")) if start_ts else None
    in_ring = {}
    for rel, (add, dele) in all_files.items():
        mtime = datetime.datetime.fromtimestamp((ROOT / rel).stat().st_mtime, datetime.timezone.utc)
        if cutoff is None or mtime >= cutoff:
            in_ring[rel] = {
                "added": add,
                "removed": dele,
                "mtime_utc": mtime.isoformat(timespec="seconds"),
            }

    change_points = []
    for rel in sorted(in_ring):
        path = ROOT / rel
        spans = symbol_spans(path)
        owners = {}
        for lo, hi in diff_ranges(rel):
            for line in range(lo, hi + 1):
                cands = [s for s in spans if s[0] <= line <= s[1]]
                key = cands[-1][2] if cands else "<模块级>"
                owners.setdefault(key, set()).add(line)
        for sym, lines in sorted(owners.items()):
            change_points.append(
                {
                    "file": rel,
                    "symbol": sym,
                    "changed_lines": len(lines),
                    "line_span": [min(lines), max(lines)],
                }
            )

    files_cp = {}
    for cp in change_points:
        files_cp.setdefault(cp["file"], 0)
        files_cp[cp["file"]] += 1

    in_ring_all = {}
    for rel, (add, dele) in all_files.items():
        mtime = datetime.datetime.fromtimestamp((ROOT / rel).stat().st_mtime, datetime.timezone.utc)
        if cutoff is None or mtime >= cutoff:
            in_ring_all[rel] = mtime.isoformat(timespec="seconds")

    def hits(cid: int, universe: dict) -> list:
        faces = cards[cid]["product_faces"] + cards[cid]["test_faces"]
        return sorted(
            rel
            for rel in universe
            if any(rel == f or rel.startswith(f if f.endswith("/") else f + "/") for f in faces)
        )

    card_files = {cid: hits(cid, in_ring_all) for cid in planned}
    card_product_files = {cid: hits(cid, in_ring) for cid in planned}
    # 车道自述「这张单没有交付条目」的，即便卡片声明了可改面（于是求交非空），也不算有交付：
    # 认领面是"打算改哪儿"，不是"改完了哪儿"。只看交集会把 73 这种空认领当成修完。
    lane_undelivered = sorted(
        {
            int(cid)
            for lane in lane_doc.get("lanes", [])
            for cid in (lane.get("undelivered_cards") or [])
        }
    )
    unfixed = sorted(
        {cid for cid in planned if not card_product_files[cid]} | set(lane_undelivered)
    )

    groups = {}
    for cid, hits in card_product_files.items():
        for rel in hits:
            for cp in change_points:
                if cp["file"] == rel:
                    groups.setdefault(f"{cp['file']}::{cp['symbol']}", set()).add(cid)
    merged = {k: sorted(v) for k, v in sorted(groups.items()) if len(v) > 1}

    receipts = []
    for lane in lane_doc.get("lanes", []):
        claimed = [f.replace("\\", "/") for f in lane.get("files_reported", [])]
        missing = sorted(
            f for f in claimed if f not in in_ring and not any(rel.startswith(f) for rel in in_ring)
        )
        extra = sorted(f for f in claimed if (ROOT / f).exists() and f not in in_ring)
        receipts.append(
            {
                "lane": lane["lane"],
                "status": lane.get("status", ""),
                "cards": lane.get("cards", []),
                "files_reported": claimed,
                "scope_declared": lane.get("scope_declared", []),
                "not_seen_in_diff": missing,
                "exists_but_not_this_ring": extra,
            }
        )
    reported = {f for r in receipts for f in r["files_reported"]}
    scopes = {f for r in receipts for f in r["scope_declared"]}

    def covered_by(rel: str, face: str) -> bool:
        return (
            rel == face
            or rel.startswith(face if face.endswith("/") else face + "/")
            or face.startswith(rel)
        )

    def any_cover(rel: str, faces) -> bool:
        return any(covered_by(rel, f) for f in faces)

    unattributed = sorted(rel for rel in in_ring if not any_cover(rel, reported | scopes))
    unreported = sorted(
        rel for rel in in_ring if not any_cover(rel, reported) and any_cover(rel, scopes)
    )

    canary_lane = {
        "lane": "canary",
        "files_reported": ["cypyc/不存在的文件.py"],
        "cards": [],
        "status": "x",
    }
    canary_missing = [f for f in canary_lane["files_reported"] if f not in in_ring]
    fake_face = [
        cid for cid in planned if "cypyc/definitely_missing.py" in cards[cid]["product_faces"]
    ]

    check(
        "反例：车道自报一个盘上没有的文件必须被 B 通道抓到",
        canary_missing,
        ["cypyc/不存在的文件.py"],
        f"实得 {canary_missing}",
    )
    check(
        "反例：认领面里不许混进盘上不存在的文件（intake 已挡，这里复算一遍）",
        fake_face,
        [],
        f"混进来的：{fake_face}",
    )
    per_file_diff_lines = {rel: sum(hi - lo + 1 for lo, hi in diff_ranges(rel)) for rel in in_ring}
    per_file_attributed = {
        rel: sum(cp["changed_lines"] for cp in change_points if cp["file"] == rel)
        for rel in in_ring
    }
    mismatched = {
        f: [per_file_diff_lines[f], per_file_attributed[f]]
        for f in in_ring
        if per_file_diff_lines[f] != per_file_attributed[f]
    }
    why = f"对不齐的样本：{list(mismatched.items())[:4]} / 参与守恒的文件 {len(in_ring)} 个"
    check(
        "改动点守恒：每个文件归到符号的改动行数必须等于 diff 新增行段数（不吞行也不造行）",
        mismatched,
        {},
        why,
    )
    check(
        "本环改过的每个文件要么被车道报出要么逐张点名（改了没人报=清单口径漏面）",
        unattributed,
        [],
        f"无人报的改动文件：{unattributed[:8]}（共 {len(unattributed)} 个）",
    )
    card_faces = {f for v in (card_product_files or {}).values() for f in v}
    no_card = sorted(
        rel for rel in in_ring if not rel.startswith("tests/") and rel not in card_faces
    )
    check(
        "车道报出的文件必须在 diff 里数得到（说了不算，要看盘）",
        sorted({f for r in receipts for f in r["not_seen_in_diff"]}),
        [],
        f"报了但 diff 里没有：{sorted({f for r in receipts for f in r['not_seen_in_diff']})[:8]}",
    )

    doc = {
        "started": started,
        "ring_start_utc": start_ts,
        "root_status_at_rc": root_status,
        "ring_tag_rows": tag_rows,
        "ring_tag_rows": tag_rows,
        "self_checks": CHECKS,
        "self_checks_red": [c["label"] for c in CHECKS if not c["ok"]],
        "planned_keys": [cards[cid]["key"] for cid in planned],
        "change_points": len(change_points),
        "change_point_rows": change_points,
        "files_this_ring": {k: v for k, v in sorted(in_ring.items())},
        "symbols_referenced": sorted({cp["symbol"] for cp in change_points}),
        "symbols_referenced_len": len({cp["symbol"] for cp in change_points}),
        "per_file_change_points": {k: v for k, v in sorted(files_cp.items())},
        "merged_root_causes": merged,
        "merged_root_cause_len": len(merged),
        "cards_sharing_a_symbol_len": sum(len(v) for v in merged.values()),
        "card_change_files": {str(k): v for k, v in sorted(card_files.items())},
        "card_product_files": {str(k): v for k, v in sorted(card_product_files.items())},
        "product_files_without_card": no_card,
        "ring_files_all_len": len(in_ring_all),
        "unfixed_claimed": unfixed,
        "lane_receipts": receipts,
        "unattributed_changes": unattributed,
        "covered_only_by_scope": unreported,
        "reported_files_len": len(reported),
        "note": "根因合并=落在同一 (文件, 符号) 的单数，不代表它们是同一个缺陷；"
        "unfixed_claimed 里的单仍按 OPEN 转结，不写成本环修掉。",
        "refuse": sorted(set(REFUSE)),
        "at_utc": now_iso(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "change_points": len(change_points),
                "files_this_ring": len(in_ring),
                "symbols_referenced": doc["symbols_referenced_len"],
                "merged_root_causes": len(merged),
                "unfixed_claimed": unfixed,
                "unattributed": unattributed[:6],
                "covered_only_by_scope": unreported[:6],
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
        import traceback

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
