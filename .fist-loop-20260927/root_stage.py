#!/usr/bin/env python3
"""通用的「环节根任务发布 + 深拆」驱动（五环循环复用）。

用法：python root_stage.py <spec.json>
spec.json = {"tag": "...", "description": "...", "laws": [...], "split_n": N,
             "assignee": "...", "extra": {...}}
幂等：同 tag 已有未归档根任务就复用，不重发（重发会让账本出现两条同名环节）。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
NS = "cypy-loop-20260927"


def existing_root(tag: str):
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    row = db.execute(
        "select id, status from tasks where ns=? and status not in ('已归档') "
        "and description like ?",
        (NS, "%" + tag + "%"),
    ).fetchone()
    db.close()
    return row


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tag, laws = spec["tag"], spec["laws"]
    c = lfist_lib.Client(timeout=240)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    row = existing_root(tag)
    if row:
        print(f"复用已存在的 {tag} 根任务：{row[0]}（{row[1]}）")
        root_id = row[0]
    else:
        pub = c.call(
            "publish",
            {
                "project_dir": ".",
                "description": spec["description"],
                "created_by": "human_steward",
                "now": lfist_lib.utc_now(),
            },
        )
        root_id = pub.get("task_id") or pub.get("id")
        if not root_id:
            print(json.dumps(pub, ensure_ascii=False)[:600])
            print("REFUSE — publish 没回任务号")
            c.close()
            return 1
        claim = c.call(
            "claim", {"task_id": root_id, "assignee": spec["assignee"], "now": lfist_lib.utc_now()}
        )
        laya = c.call(
            "laya_decide",
            {"context": spec["description"], "split_n_hint": len(laws), "no_sidecar": True},
        )
        plan = c.call(
            "task_plan_deep",
            {
                "task_id": root_id,
                "split_n": len(laws),
                "by": spec["assignee"],
                "omega_strong_verify": True,
                "laya_auto": True,
                "decide_split_n": len(laws),
                "decide_difficulty": spec.get("difficulty", "难"),
                "decide_reason": f"本机 Laya available={(laya or {}).get('available')}；"
                "按模板走显式降级：规则式自决 split_n="
                f"{len(laws)}（每条法一支），汇报记 laya: fallback",
                "spec": {"laws": laws, "fingerprint": spec.get("fingerprint", {})},
                "now": lfist_lib.utc_now(),
            },
        )
        print("claim:", json.dumps(claim, ensure_ascii=False)[:200])
        print(
            "plan:",
            json.dumps(
                {k: v for k, v in plan.items() if k in ("split_n", "root", "plan_decision")},
                ensure_ascii=False,
            )[:400],
        )

    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    leaves = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=1 order by id",
            (NS, root_id + ".%"),
        )
    ]
    branches = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=2 order by id",
            (NS, root_id + ".%"),
        )
    ]
    db.close()
    off = []
    for tid in leaves:
        st = c.call("omega_status", {"task_id": tid})
        if not st.get("omega_enabled"):
            off.append(tid)
    c.close()
    doc = {"root": root_id, "branches": branches, "leaves": leaves, "omega_off": off}
    Path(HERE / f"root_{spec['key']}.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False))
    if not leaves:
        print("REFUSE — 没反解到叶子（空集合不算通过）")
        return 2
    if off:
        print(f"REFUSE — 这些叶子没吃到 omega 强验证: {off}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
