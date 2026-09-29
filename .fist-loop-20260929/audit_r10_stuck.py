"""R10 打磨腿·审计：上一轮（R6/R7）卡住的节点到底能不能收，逐节点用状态机事实回答。

结论不靠回忆：对每个非终态节点算「子节点是否全终态」+「有没有 spec」+「状态机下一步出路」，
把"能诚实收的"和"被待领取叶卡住的"分栏点名。不强推、不伪造交付物。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "fist-mbt.db"
TERMINAL = {"已完成", "已归档", "已关闭"}
OUT = HERE / "audit_r10_stuck.json"


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("select id, parent_id, depth, status from tasks "
                       "where id like 'T0r112%' or id like 'T0r113%' or id like 'T0r116%'").fetchall()
    specs = dict(con.execute("select task_id, count(*) from specs group by task_id").fetchall())
    con.close()
    by_id = {r[0]: r for r in rows}
    children: dict = {}
    for r in rows:
        children.setdefault(r[1], []).append(r[0])

    rep = {"tree_roots": ["T0r112", "T0r113", "T0r116"], "nodes": {}, "summary": {}}
    for root in rep["tree_roots"]:
        ids = [i for i, r in by_id.items() if i == root or i.startswith(root + ".")]
        non_terminal = [i for i in ids if by_id[i][3] not in TERMINAL]
        pending = [i for i in ids if by_id[i][3] == "待领取"]
        closable = []
        blocked = []
        for i in non_terminal:
            kids = [k for k in children.get(i, []) if by_id[k][3] not in TERMINAL] if i in by_id else []
            (blocked if kids or pending and i in children else closable).append(
                {"id": i, "status": by_id[i][3], "open_children": kids, "has_spec": specs.get(i, 0)})
        rep["summary"][root] = {"total": len(ids), "non_terminal": len(non_terminal),
                                "pending_leaves": len(pending),
                                "closable_now": len(closable), "blocked_by_children": len(blocked)}
        for item in closable + blocked:
            rep["nodes"][item["id"]] = item

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in rep["summary"].items():
        print("TREE", k, json.dumps(v, ensure_ascii=False))
    print(f"CONCLUSION roots=3 nodes={len(rep['nodes'])} "
          f"closable={sum(v['closable_now'] for v in rep['summary'].values())} "
          f"blocked={sum(v['blocked_by_children'] for v in rep['summary'].values())} "
          f"pending={sum(v['pending_leaves'] for v in rep['summary'].values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
