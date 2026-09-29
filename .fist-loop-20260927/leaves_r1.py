#!/usr/bin/env python3
"""把 R1 根任务的子树反解出来，并逐叶核对 omega 强验证是否真的吃到。

上一版把「叶子列表为空」当成了通过（空集合上 all() 为真、disabled 也为空）——那是一条恒绿门禁，
本轮禁止再犯：这里 child 数为 0 直接 REFUSE。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = "T0r38"


def walk(node, out):
    if isinstance(node, dict):
        tid = node.get("task_id") or node.get("id")
        if tid:
            out.append(
                {
                    "task_id": tid,
                    "parent": node.get("parent_id") or node.get("parent"),
                    "status": node.get("status"),
                    "description": (node.get("description") or "")[:90],
                    "depth": node.get("depth"),
                }
            )
        for v in node.values():
            walk(v, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, out)


def main() -> int:
    c = lfist_lib.Client(timeout=180)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    g = c.call("get", {"task_id": ROOT})
    nodes = []
    walk(g, nodes)
    seen, uniq = set(), []
    for n in nodes:
        if n["task_id"] in seen:
            continue
        seen.add(n["task_id"])
        uniq.append(n)
    kids = [n for n in uniq if n["task_id"] != ROOT]
    if len(kids) == 0:
        print(json.dumps(g, ensure_ascii=False)[:1500])
        print(
            "REFUSE — 根任务下反解不到任何子任务：拆解没落库，或这里的遍历口径不对（别拿空集合当通过）"
        )
        c.close()
        return 1
    for n in kids:
        st = c.call("omega_status", {"task_id": n["task_id"]})
        n["omega_enabled"] = st.get("omega_enabled")
        n["omega_spec_status"] = st.get("spec_status")
        n["omega_task_status"] = st.get("task_status")
    c.close()
    off = [n["task_id"] for n in kids if not n["omega_enabled"]]
    Path(HERE / "leaves_r1.json").write_text(
        json.dumps({"root": ROOT, "kids": kids, "omega_off": off}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    for n in kids:
        print(
            f"{n['task_id']:10s} omega={str(n['omega_enabled']):5s} status={n['omega_task_status']} "
            f"| {n['description']}"
        )
    print(f"children={len(kids)} omega_off={off or 'none'}")
    if off:
        print("REFUSE — 这些叶子没开强验证，环节不得开工")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
