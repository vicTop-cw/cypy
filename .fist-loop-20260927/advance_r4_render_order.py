"""R4-推进 的渲染顺序见证：报告只准渲染一次，渲染之后再动一个字都要看得见。

与验证环同构，加两条本环用得上的正面测：
- §十 的失效条数在**渲染后的报告**里再数一遍（渲染截断或占位吞行都会在这里翻红，
  而不是只在散文片段里自证「我写了 15 条」）；
- 八条法的正文小节必须逐个标题在场，缺一个就说明报告被装配器少拼了一段。
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
SPEC = HERE / "report_spec_r4_advance.json"
PLAN = HERE / "spec_r4_advance.json"
OUT = HERE / "advance_r4_render_order.json"
LAW_HEADS = ["## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、", "## 八、", "## 九、"]
REFUSE: list = []


def main() -> int:
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
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
        REFUSE.append("报告里出现「‹未解析›」占位残留")
    missing_heads = [h for h in LAW_HEADS if h not in text]
    if missing_heads:
        REFUSE.append(f"八条法的正文小节缺 {len(missing_heads)} 个标题：{missing_heads}")

    sec10 = re.search(r"## 十、本环我自己的失效（(\d+) 条[^\n]*\n([\s\S]*?)(?=\n## 十一、)", text)
    s10_declared = int(sec10.group(1)) if sec10 else -1
    s10_actual = len(re.findall(r"^\d+\. ", sec10.group(2), re.M)) if sec10 else -1
    if not sec10:
        REFUSE.append("渲染后的报告里没有 §十 ⇒ 失效清单没能进交付物")
    elif s10_actual != s10_declared:
        REFUSE.append(f"渲染后 §十 标题声明 {s10_declared} 条，正文实数 {s10_actual} 条 ⇒ 装配掉行")

    gates_tbl = re.search(r"## 门禁反解表\n([\s\S]*?)\n## ", text)
    if not gates_tbl:
        REFUSE.append("报告里没有「## 门禁反解表」段 ⇒ 无法核对装配器判了几道")
        rows, green, red, mis, dup, data = -1, -1, -1, [], [], []
    else:
        lines = gates_tbl.group(1).splitlines()
        pipe = [ln for ln in lines if ln.startswith("| ")]
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
           "law_heads_expected": len(LAW_HEADS), "law_heads_missing": missing_heads,
           "section10_rendered": {"declared": s10_declared, "actual": s10_actual},
           "laws_declared": len(plan["laws"]),
           "note": "renders=1 是说报告文件只被写过一次；被拒的重试只留 refuse 件、不写报告",
           "refuse": sorted(set(REFUSE)),
           "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("refuse", "report", "report_bytes", "renders",
                                          "gates_in_table", "gates_green", "refused_attempts",
                                          "law_heads_missing", "section10_rendered")},
                     ensure_ascii=False, indent=1))
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
