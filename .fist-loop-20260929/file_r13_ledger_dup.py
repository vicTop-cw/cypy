"""入账一张账面完整性单：`memory/bugs.md` 里 `## BUG-96` 出现两次（号被复用）。

抓它的不是人工通读，而是核验件里那句"抬头数 140 / 去重后 139"的对账 ——
按 id 建字典的工具会**静默丢掉一张**，所以这一条既是脏数据也是工具风险。
本脚本只取证与入账，不修台账（改号会让既有引用悬空，交回人工裁决）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
KEY = "R13-LEDGER-DUPLICATE-BUG-ID"


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "a1"
    out = HERE / f"file_r13_ledger_dup_{tag}.json"
    started = utc_z()
    src = LEDGER.read_text(encoding="utf-8")
    lines = src.splitlines()
    hits = [(i, ln) for i, ln in enumerate(lines, 1) if re.match(r"^## BUG-96 ", ln)]
    before_headers = len(re.findall(r"(?m)^## BUG-\d+", src))
    uniq = len(set(re.findall(r"(?m)^## (BUG-\d+)", src)))
    rep = {
        "started_z": started,
        "ns": NS,
        "lines": [h[0] for h in hits],
        "headers": before_headers,
        "unique_ids": uniq,
        "verbatim": [h[1] for h in hits],
        "filed": [],
        "refusals": [],
        "skipped_existing": [],
    }
    if KEY in src:
        rep["skipped_existing"].append(KEY)
        print("CONCLUSION filed=0 skipped=1（幂等：该主张已入账）")
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    if len(hits) < 2:
        print(
            f"CONCLUSION filed=0 refused=0 note=账上 BUG-96 只出现 {len(hits)} 次 ⇒ 主张不成立，不入账"
        )
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    summary = (
        "[ledger:integrity] `memory/bugs.md` 里 `## BUG-96` 出现两次"
        f"（第 {hits[0][0]} 行与第 {hits[1][0]} 行，严重度一栏还分别是 medium 与 high）"
        f" ⇒ 抬头 {before_headers} 条但去重后只有 {uniq} 个编号，按 id 建字典的工具会静默丢掉一张"
    )
    detail = (
        "取证：核验件 `.fist-loop-20260929/verify_r13_report.py` 在数「报告点名的编号是否都在账上」时，"
        f"用 `re.split` 得到 {before_headers} 个抬头、建 dict 后只剩 {uniq} 个键 —— 差 1 不是尺坏，"
        "是账上真有重复号。两条抬头逐字：\n"
        + "\n".join(f"  L{n}: {t}" for n, t in hits)
        + "\n第二条的时间戳是 `+00:00` 形态而非本仓约定的 `…Z` 形态（`ledger_sweep` 里那 17 条"
        "「读得到钟点但没 Z」的软读数就包含它），所以它既可能是另一条写入路径产出，也可能是手改。"
        "成因不在本单主张范围内。\n"
        "为什么不就地修：改号会让既有引用（报告、FIXED 段、任务库 linked id）悬空，"
        "而合并两条又会把两种严重度压成一条 ⇒ 交回人工裁决，本轮只入账不改账。\n"
        f"同轮受影响的读数口径：本轮报告同时写「抬头 {before_headers} / 去重 {uniq}」两数，"
        "不再只报一个"
    )
    detail += f"\n- reported_key: {KEY}"
    if re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", detail):
        raise SystemExit("正文残留未插值占位 ⇒ 不落盘不提交")
    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    c = fist.FistClient(timeout=240)
    res = c.call(
        "report_bug",
        {
            "project_dir": ".",
            "summary": summary,
            "severity": "medium",
            "detail": detail,
            "reported_by": AGENT,
            "publish_task": False,
        },
    )
    blob = json.dumps(res, ensure_ascii=False)
    if "__error__" in blob or blob.startswith("RPC-ERROR"):
        rep["refusals"].append({"tool": "report_bug", "reply_verbatim": blob})
    else:
        rep["filed"].append({"tool": "report_bug", "reply_verbatim": blob})
    lst = c.call("bug_list", {"project_dir": ".", "limit": 400})
    rep["bug_list_shape"] = type(lst).__name__
    rep["bug_list_count"] = lst.get("count") if isinstance(lst, dict) else len(lst)
    after = LEDGER.read_text(encoding="utf-8")
    rep["after_headers"] = len(re.findall(r"(?m)^## BUG-\d+", after))
    rep["after_unique"] = len(set(re.findall(r"(?m)^## (BUG-\d+)", after)))
    rep["new_id"] = sorted(
        set(re.findall(r"(?m)^## (BUG-\d+)", after)) - set(re.findall(r"(?m)^## (BUG-\d+)", src))
    )
    con = sqlite3.connect(str(ROOT / "fist-mbt.db"))
    rep["call_log_report_bug_rows"] = con.execute(
        "select count(*) from call_log where tool='report_bug' and ns=?", (NS,)
    ).fetchone()[0]
    con.close()
    c.close()
    ok = (
        rep["filed"]
        and not rep["refusals"]
        and rep["after_headers"] == before_headers + 1
        and KEY in after
    )
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("VERBATIM " + " ;; ".join(rep["verbatim"]))
    print(
        f"CONCLUSION r13_ledger_dup filed={len(rep['filed'])} refused={len(rep['refusals'])} "
        f"new_id={rep['new_id']} dup_lines={[h[0] for h in hits]} "
        f"headers={before_headers}->{rep['after_headers']} unique={uniq}->{rep['after_unique']} "
        f"report_bug_rows={rep['call_log_report_bug_rows']} ok={ok} out={out.name}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
