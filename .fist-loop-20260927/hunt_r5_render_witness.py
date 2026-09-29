"""渲染次数的真见证：每跑一次本驱动，就把盘上报告的 sha 追加进 `hunt_r5_renders.json`。

为什么要有这个件：`render_order` 里的 `renders` 之前是「报告文件存在 ⇒ 1」，那是**存在性**而不是
**次数**——被更正重渲第二次它照样报 1，等于把「只渲染一次」这句主张做成了恒绿门。
现在次数按记录数算，并且配两条反向门：
- 与上一条记录逐字相同 ⇒ 拒（这一趟根本没写过盘，别冒充一次渲染）；
- 记录数与盘上同名报告数不匹配 ⇒ 由 `render_order` 交叉核对（那里按文件系统数）。

用法：`python hunt_r5_render_witness.py --note "首渲"`（note 必填；缺了就拒，免得出现没有出处的记录）
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "report_spec_r5_hunt.json"
OUT = HERE / "hunt_r5_renders.json"


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    note = ""
    args = sys.argv[1:]
    if "--note" in args:
        i = args.index("--note")
        if i + 1 < len(args):
            note = args[i + 1]
    refuse: list = []
    if not note:
        refuse.append("缺 --note ⇒ 不接受没有出处的渲染记录")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    rep = ROOT / "memory" / "reviews" / f"{spec['name']}.md"
    if not rep.exists():
        refuse.append(f"报告不在盘上：{rep.name}")
    doc = (
        json.loads(OUT.read_text(encoding="utf-8"))
        if OUT.exists()
        else {"key": "r5_hunt_renders", "records": []}
    )
    records = doc.get("records") or []
    sha = hashlib.sha256(rep.read_bytes()).hexdigest() if rep.exists() else ""
    if refuse:
        print(json.dumps({"refuse": refuse}, ensure_ascii=False))
        return 1
    if records and records[-1].get("report_sha256") == sha:
        refuse.append(
            f"盘上报告与第 {records[-1]['seq']} 条记录逐字相同 ⇒ 这一趟没有真的重写报告，"
            "不能记成第二次渲染"
        )
    if records:
        seq = max(int(r["seq"]) for r in records) + 1
    else:
        seq = 1
    records.append(
        {
            "seq": seq,
            "at_utc": now_s(),
            "report": f"memory/reviews/{rep.name}",
            "report_sha256": sha,
            "report_bytes": rep.stat().st_size,
            "gates_total": len(spec["gates"]),
            "spec_name": spec.get("name"),
            "spec_marker": spec.get("marker"),
            "note": note,
        }
    )
    doc = {
        "key": "r5_hunt_renders",
        "renders": len(records),
        "records": records,
        "refuse": sorted(set(refuse)),
        "at_utc": now_s(),
    }
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {"renders": len(records), "seq": seq, "sha": sha[:16], "refuse": doc["refuse"]},
            ensure_ascii=False,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    sys.exit(main())
