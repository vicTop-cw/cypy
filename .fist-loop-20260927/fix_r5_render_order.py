"""R5-修复 的渲染顺序见证：报告只准渲染一次，渲染后动一个字都要看得见。

三条正面测（不是「我看了一眼」）：
- §八 失效清单的**标题声明条数**与渲染后正文实数必须相等 ⇒ 装配掉行、占位吞行都会在这里翻红；
- 门禁表逐行与 spec 的 label 集合对齐，且全行 ✅；再配一条 canary：从表里剔掉一行必须还能被抓到
  （剔不动 ⇒ 行数判据恒绿，本件自判坏）；
- 八条法的正文小节标题逐个在场，并留 sha 作为「渲染后未再被改」的锚。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "report_spec_r5_fix.json"
PLAN = HERE / "spec_r5_fix.json"
OUT = HERE / "fix_r5_render_order.json"
LAW_HEADS = ["## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、", "## 八、", "## 九、"]
NS = "cypy-loop-20260927"
REFUSE: list = []


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    started = now_s()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    name = spec["name"]
    rep = ROOT / "memory" / "reviews" / f"{name}.md"
    kit = HERE / f"report_kit_{name}.refuse.json"
    same_name = sorted((ROOT / "memory" / "reviews").glob(f"{name}*.md"))
    if not rep.exists():
        REFUSE.append(f"报告不在盘上：memory/reviews/{name}.md ⇒ 没有渲染可见证")
    if len(same_name) > 1:
        REFUSE.append(f"同名报告文件多份：{[p.name for p in same_name]}")
    sha = hashlib.sha256(rep.read_bytes()).hexdigest() if rep.exists() else ""
    text = rep.read_text(encoding="utf-8") if rep.exists() else ""
    unresolved = re.findall(r"\{\{[^{}]+\}\}", text)
    if unresolved:
        REFUSE.append(f"报告里还有未解析占位 {len(unresolved)} 个：{unresolved[:4]}")
    if "‹未解析›" in text:
        REFUSE.append("报告里出现「‹未解析›」残留")
    if "‹收口后生成›" in text:
        REFUSE.append("报告里出现「‹收口后生成›」⇒ 本次是按 pre-close 渲的，收口件没进交付物")
    # 渲染次数不能按「文件存在」数（那是存在性冒充次数）：按 `fix_r5_renders.json` 的记录数算，
    # 并要求最后一条记录的 sha 就是盘上这份。
    wit_p = HERE / "fix_r5_renders.json"
    wit = json.loads(wit_p.read_text(encoding="utf-8")) if wit_p.exists() else {}
    recs = wit.get("records") or []
    rec_shas = [r.get("report_sha256") for r in recs]
    if not recs:
        REFUSE.append("没有渲染见证件 ⇒ 「渲染了 N 次」这句话没有出处")
    if len(set(rec_shas)) != len(rec_shas):
        REFUSE.append(f"渲染记录里有重复 sha：{rec_shas}")
    if recs and recs[-1].get("report_sha256") != sha:
        prev = str(recs[-1].get("report_sha256"))[:12]
        REFUSE.append(
            f"最后一条渲染记录（{prev}…）与盘上 sha（{sha[:12]}…）"
            "不一致 ⇒ 有人绕过见证件改了报告"
        )
    missing_heads = [h for h in LAW_HEADS if h not in text]
    if missing_heads:
        REFUSE.append(f"八条法的正文小节缺 {len(missing_heads)} 个标题：{missing_heads}")

    sec8 = re.search(r"## 八、[^\n]*?（(\d+) 条[\s\S]*?(?=\n## 九、)", text)
    declared = int(sec8.group(1)) if sec8 else -1
    actual = len(re.findall(r"^\d+\. ", sec8.group(0), re.M)) if sec8 else -1
    if not sec8:
        REFUSE.append("渲染后的报告里没有带条数声明的 §八 ⇒ 失效清单没能进交付物")
    elif declared != actual:
        REFUSE.append(f"§八 标题声明 {declared} 条，正文实数 {actual} 条 ⇒ 装配掉行或标题虚报")

    tbl = re.search(r"## 门禁反解表\n([\s\S]*?)\n## ", text)
    if not tbl:
        REFUSE.append("报告里没有「## 门禁反解表」段 ⇒ 无法核对装配器判了几道")
        rows, green, red, mis, dup, data = -1, -1, -1, [], [], []
    else:
        pipe = [ln for ln in tbl.group(1).splitlines() if ln.startswith("| ")]
        header = [ln for ln in pipe if ln.startswith("| 门禁")]
        sep = [ln for ln in pipe if set(ln) <= set("|-: ")]
        data = [ln for ln in pipe if ln not in header and ln not in sep]
        in_table = [ln.split("|")[1].strip() for ln in data]
        want = [g["label"] for g in spec["gates"]]
        mis = sorted(set(want) - set(in_table)) + sorted(set(in_table) - set(want))
        dup = sorted({x for x in in_table if in_table.count(x) > 1})
        rows, green = len(data), sum(1 for ln in data if "| ✅" in ln)
        red = sum(1 for ln in data if "| ❌" in ln) or sum(1 for ln in data if "| ⏳" in ln)
        if not header:
            REFUSE.append("门禁表没渲染表头 ⇒ 行口径不可信")
        if mis:
            REFUSE.append(f"门禁表与 spec 的 label 集合不齐平：{mis[:6]}")
        if dup:
            REFUSE.append(f"门禁表里同一 label 出现多次：{dup[:4]}")
    if rows != len(spec["gates"]):
        REFUSE.append(f"门禁表 {rows} 行 != spec 声明 {len(spec['gates'])} 道")
    if red:
        REFUSE.append(f"门禁表里有 {red} 行 ❌/⏳ ⇒ 不得按已验收渲染")
    if green != rows:
        REFUSE.append(f"门禁表 {rows} 行里只有 {green} 行 ✅ ⇒ 有行没被判定")
    canary_rows, canary_caught = -1, False
    if tbl:
        canary_rows = len(data[:-1])
        canary_caught = canary_rows != len(spec["gates"])
        if not canary_caught:
            REFUSE.append("canary 失效：剔掉一行门禁表还能对上 ⇒ 行数判据恒绿")

    # 根上卷发生在渲染之后（close_root 要拿渲染好的报告过 L4 产物门）。
    # 所以「根已归档」这句话只能在这里说，而且必须两路对得上：收口件自报 + sqlite 现读。
    root_art = HERE / "close_r5_fix_root.out.json"
    root_doc, root_live, refused_rows, tally_after, root_refusals_md = {}, None, [], None, ""
    if not root_art.exists():
        REFUSE.append("根上卷件不在盘上 ⇒ 收口链没跑到，报告里那句「渲染后再上卷」没人复核过")
    else:
        try:
            root_doc = json.loads(root_art.read_text(encoding="utf-8"))
        except Exception as exc:
            REFUSE.append(f"根上卷件 parse 失败：{type(exc).__name__}: {exc}")
        refused_rows = root_doc.get("refused") or []
        root_final = root_doc.get("root_final")
        root_live = None
        try:
            con = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
            r = con.execute(
                "select status from tasks where ns=? and id=?", (NS, spec["root_task"])
            ).fetchone()
            root_live = r[0] if r else None
            con.close()
        except Exception as exc:
            REFUSE.append(f"根状态现读失败：{type(exc).__name__}: {exc}")
        if root_final != root_live:
            REFUSE.append(f"根状态两路不一致：收口件自报 {root_final} / sqlite 现读 {root_live}")
        if root_final != "已归档":
            REFUSE.append(f"根最终状态不是「已归档」而是 {root_live} ⇒ 上卷没走完")
        first = recs[0].get("at_utc", "")
        root_mtime = datetime.datetime.fromtimestamp(
            os.path.getmtime(root_art), datetime.timezone.utc
        ).isoformat(timespec="seconds")
        if first and root_mtime < first:
            REFUSE.append(
                f"根上卷（{root_mtime}）比首渲（{first}）还早 ⇒ 次序被颠倒："
                "报告不该在收口件之后才第一次落盘"
            )
        root_refusals_md = "\n".join(
            f"- `{json.dumps(x, ensure_ascii=False)[:400]}`" for x in refused_rows
        )
        tally_after = root_doc.get("call_log_rows")
        if not isinstance(refused_rows, list):
            REFUSE.append("根上卷件的 refused 不是列表 ⇒ 逐字清单没处去")

    doc = {
        "started": started,
        "report": f"memory/reviews/{name}.md",
        "report_bytes": rep.stat().st_size if rep.exists() else 0,
        "report_sha256": sha,
        "renders": len(recs),
        "render_records": recs,
        "same_name_files": [p.name for p in same_name],
        "refused_attempts": len(list(kit.parent.glob(f"report_kit_{name}*.refuse.json"))),
        "refuse_file_present": kit.exists(),
        "gates_in_table": rows,
        "gates_green": green,
        "gates_red": red,
        "gates_label_misaligned": mis,
        "gates_label_dupes": dup,
        "gates_canary": {
            "rows_after_dropping_one": canary_rows,
            "declared": len(spec["gates"]),
            "caught": canary_caught,
        },
        "unresolved_placeholders": unresolved,
        "law_heads_expected": len(LAW_HEADS),
        "law_heads_missing": missing_heads,
        "section8_rendered": {"declared": declared, "actual": actual},
        "laws_declared": len(plan["laws"]),
        "root_closure": {
            "artifact": root_art.name,
            "on_disk": root_art.exists(),
            "self_reported": root_doc.get("root_final"),
            "live_status": root_live,
            "refused_rows": len(refused_rows),
            "refused_detail": refused_rows,
            "call_log_rows_after_root": tally_after,
            "newer_than_report": bool(
                root_art.exists() and os.path.getmtime(root_art) >= rep.stat().st_mtime - 1
            ),
            "refusals_md": root_refusals_md,
        },
        "note": "renders=1 是说报告文件只被写过一次；被拒的重试只留 refuse 件、不写报告",
        "refuse": sorted(set(REFUSE)),
        "at_utc": now_s(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                k: doc[k]
                for k in (
                    "refuse",
                    "report",
                    "report_bytes",
                    "renders",
                    "gates_in_table",
                    "gates_green",
                    "refused_attempts",
                    "law_heads_missing",
                    "section8_rendered",
                )
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
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"], "at_utc": now_s()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
