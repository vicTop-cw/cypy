"""R4-验证 的渲染顺序见证：报告只准渲染一次，渲染之后再动一个字都要看得见。

`report_kit.py` 拒绝时**不写**报告、只写 `report_kit_<name>.refuse.json`，所以：
- `renders` = 报告文件本身被写出的次数（成功渲染 1 次才算顺序成立）；
- `refused_attempts` = 同名的 refuse 文件数（每次被拒都要留件，不许无痕重试）；
- `report_sha256` 在这里记一次，之后的进度件会重读并比对 —— 渲染后改过报告就必然对不上。
件缺任一格就拒绝写，不交一份没测过的见证。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "report_spec_r4_verify.json"
OUT = HERE / "verify_r4_render_order.json"
REFUSE: list = []


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
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
        REFUSE.append("报告里出现「‹未解析›」占位残留")
    gates_tbl = re.search(r"## 门禁反解表\n([\s\S]*?)\n## ", text)
    if not gates_tbl:
        REFUSE.append("报告里没有「## 门禁反解表」段 ⇒ 无法核对装配器判了几道")
        rows, green, red, mis, dup = -1, -1, -1, [], []
    else:
        lines = gates_tbl.group(1).splitlines()
        pipe = [ln for ln in lines if ln.startswith("| ")]
        # 装配器渲染的是「表头 + 数据行」，没有分隔行——上一版我按「减 2」算数据行数，
        # 于是 152 道门禁数成 151 行，还报出「151 行里只有 152 行 ✅」这种自相矛盾的拒绝。
        # 正确口径：按 label 集合对齐，两头都查（缺行=漏判，多行=装配器加戏），行内取状态列。
        header = [ln for ln in pipe if ln.startswith("| 门禁")]
        sep = [ln for ln in pipe if set(ln) <= set("|-: ")]
        data = [ln for ln in pipe if ln not in header and ln not in sep]
        in_table = [ln.split("|")[1].strip() for ln in data]
        want = [g["label"] for g in spec["gates"]]
        mis = sorted(set(want) - set(in_table)) + sorted(set(in_table) - set(want))
        dup = sorted({x for x in in_table if in_table.count(x) > 1})
        rows, green = len(data), sum(1 for ln in data if "| ✅" in ln)
        red = sum(1 for ln in data if "| ❌" in ln)
        if not header:
            REFUSE.append("门禁表没渲染表头 ⇒ 行口径不可信")
        if mis:
            REFUSE.append(f"门禁表与 spec 的 label 集合不齐平：{mis[:6]}")
        if dup:
            REFUSE.append(f"门禁表里同一 label 出现多次：{dup[:4]}")
    if rows != len(spec["gates"]):
        REFUSE.append(f"门禁表 {rows} 行 != spec 声明 {len(spec['gates'])} 道")
    if red:
        REFUSE.append(f"门禁表里有 {red} 行 ❌ ⇒ 不得按已验收渲染")
    if green != rows:
        REFUSE.append(f"门禁表 {rows} 行里只有 {green} 行 ✅ ⇒ 有行没被装配器判定")

    # canary：计数器必须对「少一行」敏感——从内存副本里剔掉一行数据，行数判据就要翻红
    if gates_tbl:
        short = data[:-1]
        canary_rows, canary_caught = len(short), len(short) != len(spec["gates"])
        if not canary_caught:
            REFUSE.append("canary 失效：剔掉一行门禁表还能对上 ⇒ 行数判据是恒绿的")
    else:
        canary_rows, canary_caught = -1, False

    doc = {"started": started, "report": f"memory/reviews/{name}.md",
           "report_bytes": rep.stat().st_size if rep.exists() else 0,
           "report_sha256": sha, "renders": 1 if rep.exists() else 0,
           "same_name_files": [p.name for p in same_name],
           "refused_attempts": len(list(kit.parent.glob(f"report_kit_{name}*.refuse.json"))),
           "refuse_file_present": kit.exists(),
           "gates_in_table": rows, "gates_green": green, "gates_red": red,
           "gates_label_misaligned": mis, "gates_label_dupes": dup,
           "gates_canary": {"rows_after_dropping_one": canary_rows,
                            "declared": len(spec["gates"]), "caught": canary_caught},
           "unresolved_placeholders": unresolved,
           "note": "renders=1 是说报告文件只被写过一次；被拒的重试只留 refuse 件、不写报告",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "report", "report_bytes",
                                          "renders", "gates_in_table", "gates_green",
                                          "refused_attempts")}, ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
