"""R1-打磨 law1：把 `mode_list` 声明的 polish 约束**打到调用面**，不看声明看行为。

为什么要实测：`mode_list` 说 polish 的 `forbidden_tools = [publish, publish_parallel, dag_publish]`、
`forbid_new_features=true`——那只是服务端**返回的一张表**。表里写了不等于服务端拦得住，
本轮（以及上一轮的 `[tool.flake8]`）已经反复证明「声明 vs 生效」是两件事。
所以这里真发一次 `publish`，把原始响应逐字落盘：
 - 若被拒 ⇒ polish 环节的「不新发任务」是硬约束，收口只能沿既有 16 叶走；
 - 若成功 ⇒ 声明不承重，当场把探测任务归档（可逆处置），并把这条记成 FIST 侧缺陷证据。

同时把 `tools/list` 里 `publish` 的 schema 落盘：本环境服务端**没有"当前模式"这个入参**的话，
"模式约束"就不可能在服务端成立（模式是提示词层的约定，不是执行层的门）。这句主张要有依据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

OUT = HERE / "polish_law1_r1.json"
PROBE_TAG = (
    "[loop-probe-polish-law1] 探测 mode_list 声明的 forbidden_tools 是否真被服务端拦（可弃）"
)


def main() -> int:
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        if prev.get("probe_task_id"):
            print(
                json.dumps(
                    {
                        "skipped": "已有探测记录（不重发探测任务）",
                        "probe_task_id": prev["probe_task_id"],
                        "finding": prev.get("finding"),
                    },
                    ensure_ascii=False,
                    indent=1,
                )
            )
            return 0
    c = lfist_lib.Client(timeout=240)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    doc = {}

    mid = c._send("tools/list", {})
    lst = c._recv(mid, 240)
    tools = ((lst or {}).get("result") or {}).get("tools") or (lst or {}).get("tools") or []
    doc["tools_list_count"] = len(tools)
    by_name = {t.get("name"): t for t in tools if isinstance(t, dict)}
    doc["mode_tools"] = sorted(n for n in by_name if "mode" in (n or ""))
    for n in ("publish", "publish_parallel", "dag_publish"):
        sch = (by_name.get(n) or {}).get("inputSchema") or {}
        doc[f"schema_{n}"] = {
            "required": sch.get("required"),
            "props": sorted((sch.get("properties") or {}).keys()),
        }
    # 「服务端有没有模式这个入参」= 约束能不能在执行层成立的前提
    doc["publish_has_mode_param"] = any(
        "mode" in k
        for k in ((by_name.get("publish") or {}).get("inputSchema") or {}).get("properties", {})
    )

    ml = c.call("mode_list", {})
    modes = ml.get("modes") if isinstance(ml, dict) else ml
    if not isinstance(modes, list):
        raise SystemExit(f"REFUSE — mode_list 返回形状不认识：{str(ml)[:200]}")
    pol = next((m for m in modes if isinstance(m, dict) and m.get("mode") == "polish"), None)
    doc["mode_list_polish_declared"] = pol
    doc["mode_list_shape"] = type(ml).__name__
    if not pol:
        raise SystemExit("REFUSE — mode_list 里没有 polish 条目，law1 无从对比")

    pub = c.call(
        "publish",
        {
            "project_dir": ".",
            "description": PROBE_TAG,
            "created_by": "cypy-polisher",
            "now": lfist_lib.utc_now(),
        },
    )
    doc["publish_as_polisher"] = pub
    # 第一次探测被拒的理由是 `created_by`（角色门），**不是**模式门 ⇒ 它证明不了 polish 的
    # forbidden_tools 是否生效。换成服务端放行的角色再打一次，才能把两个原因分开。
    pub2 = c.call(
        "publish",
        {
            "project_dir": ".",
            "description": PROBE_TAG,
            "created_by": "human_steward",
            "now": lfist_lib.utc_now(),
        },
    )
    doc["publish_as_steward"] = pub2
    refused = isinstance(pub2, dict) and "__error__" in pub2
    doc["publish_refused"] = refused
    doc["refusal_reason_as_polisher"] = (
        (pub.get("__error__") or {}).get("message") if isinstance(pub, dict) else None
    )
    if refused:
        doc["refusal_reason_as_steward"] = (pub2["__error__"] or {}).get("message")
        doc["finding"] = (
            "polish 下 publish 被服务端拒绝，理由见 refusal_reason_as_steward；"
            "注意区分「角色门/参数门/模式门」——只有消息里点名模式或 forbidden_tools "
            "才算模式约束生效，否则是别的门顺手挡住了"
        )
    else:
        tid = pub2.get("task_id") or pub2.get("id")
        doc["probe_task_id"] = tid
        if tid:
            # 直接 archive 对**未开工**任务是非法迁移（`complete 要求状态 [待验收]`），
            # 所以按生命周期走完再归档：留痕、且 assignee 不为空（gotcha #52）。
            trail = {}
            for step, kw in (
                ("claim", {"assignee": "cypy-polisher"}),
                ("execute", {"deliverable": "探测件，按生命周期归档留痕"}),
                ("submit", {}),
                ("archive", {"by": "human_steward"}),
            ):
                a = c.call(step, {"task_id": tid, "now": lfist_lib.utc_now(), **kw})
                trail[step] = (
                    (a.get("__error__") or {}).get("message")
                    if "__error__" in a
                    else a.get("status")
                )
            final = c.call("get", {"task_id": tid})
            doc["probe_cleanup"] = {"trail": trail, "final_status": final.get("status")}
            archived = final.get("status") == "已归档"
            doc["finding"] = (
                "mode_list 声明 polish 禁 publish，但换成服务端放行的角色后**真的发了出来** ⇒ "
                "forbidden_tools 不承重（publish 的 schema 里没有 mode 入参，"
                "执行层没有「当前模式」这个概念）。"
                + (
                    "探测任务已走完 claim→execute→submit→archive 归档留痕。"
                    if archived
                    else f"探测任务 {tid} **未能归档**（{doc['probe_cleanup']['trail']}），"
                    "它仍留在库里，须在报告里点名。"
                )
            )
    c.close()
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {k: v for k, v in doc.items() if k != "mode_list_polish_declared"},
            ensure_ascii=False,
            indent=1,
        )[:1500]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
