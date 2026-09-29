#!/usr/bin/env python3
"""R1-寻虫 根任务发布 + 深拆（omega 强验证 / laya 全开），并把叶子的 omega 状态打回来。

幂等：描述里固定带 [loop:20260927-loop:R1-寻虫] 标记，重跑先查同标记根任务，不重发。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

TAG = "[loop:20260927-loop:R1-寻虫]"


def NOW() -> str:
    """每个调用点现取一次 UTC——不能整轮共用一个时间戳（那是伪造时钟的一种）。"""
    return lfist_lib.utc_now()


LAWS = [
    "对抗样例构造",
    "差分与不变量对拍",
    "fuzz 变异（预算内）",
    "审查报告与转结项复核",
    "模式化读码狩猎",
    "最小复现与确诊",
    "入账与 quick win 判定",
    "狩猎报告与转结",
]


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
    existing = c.call("list", {"status": "待领取"})
    dup = (
        [t for t in (existing.get("tasks") or []) if TAG in (t.get("description") or "")]
        if isinstance(existing, dict)
        else []
    )
    if dup:
        print(f"已存在同标记根任务，不重发: {[t.get('id') for t in dup]}")
        c.close()
        return 0

    pub = c.call(
        "publish",
        {
            "project_dir": ".",
            "description": (
                f"{TAG} 寻虫（bug hunt）R1：Cypy codegen/cli/incremental 面五路狩猎——"
                "对抗样例 + 双后端/不变量差分 + 变异 fuzz + 审查报告与转结项复核 + 定向读码；"
                "只找不修（除 quick win：≤20 行/不动语义/一条回归锁死）；"
                "确诊一律 report_bug(publish_task=true) 入账，误报只进报告；"
                "开关：omega 强验证 + laya + issue_up + call_log 全开；"
                "issue_scan 对本仓不适用（.mbt-only），如实标 n/a"
            ),
            "created_by": "human_steward",
            "now": NOW(),
        },
    )
    root_id = pub.get("task_id") or pub.get("id")
    if not root_id:
        print(json.dumps(pub, ensure_ascii=False)[:800])
        print("REFUSE — publish 没回任务号")
        c.close()
        return 1

    claim = c.call("claim", {"task_id": root_id, "assignee": "cypy-hunter", "now": NOW()})
    laya = c.call(
        "laya_decide",
        {
            "context": "Cypy R1 寻虫：五路手段拆狩猎任务树，叶子上要开 omega 语料链",
            "split_n_hint": 8,
            "no_sidecar": True,
        },
    )
    plan = c.call(
        "task_plan_deep",
        {
            "task_id": root_id,
            "split_n": 8,
            "by": "cypy-hunter",
            "omega_strong_verify": True,
            "laya_auto": True,
            "decide_split_n": 8,
            "decide_difficulty": "难",
            "decide_reason": f"本机 Laya 不可用（available={bool((laya or {}).get('available'))}），"
            "按 known-issues 走显式降级：规则式自决 split_n=8（五路 + 确诊 + 入账 + 报告），"
            "汇报记 laya: fallback",
            "spec": {
                "laws": LAWS,
                "fingerprint": {
                    "必须": "五路各出候选清单且逐条判定；每条真缺陷有可复跑最小复现；"
                    "确诊 100% 入账（bug↔样例↔修复单三向对照）；"
                    "基线双套不回落（scripts/run_tests.py 47/47 + 定向 pytest）；"
                    "报告落 memory/reviews/",
                    "禁止": "无最小复现入账；误报刷账本；修超出 quick win；"
                    "动 PROJECT-SPEC/SYNTAX 冻结语义；git push/删文件/改冻结文档",
                },
            },
            "now": NOW(),
        },
    )
    kids = plan.get("created") or plan.get("tasks") or plan.get("subtasks") or []
    ids = [k.get("task_id") or k.get("id") for k in kids if isinstance(k, dict)]
    states = []
    for i in ids:
        st = c.call("omega_status", {"task_id": i})
        states.append(
            {
                "task_id": i,
                "omega_enabled": st.get("omega_enabled"),
                "status": st.get("task_status"),
                "spec_status": st.get("spec_status"),
            }
        )
    doc = {
        "root": root_id,
        "claim": claim.get("status") or claim,
        "plan_keys": sorted(plan.keys()) if isinstance(plan, dict) else None,
        "plan_summary": (
            {
                k: v
                for k, v in plan.items()
                if k in ("total_created", "levels", "message", "leaf_count", "created_count")
            }
            if isinstance(plan, dict)
            else None
        ),
        "laya": {
            "available": (laya or {}).get("available"),
            "decision": {
                k: v
                for k, v in ((laya or {}).get("decision") or {}).items()
                if k in ("source", "split_n", "feature_route", "complex")
            },
        },
        "leaves": states,
        "count": len(ids),
    }
    Path(HERE / "root_r1.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:2600])
    disabled = [s["task_id"] for s in states if not s["omega_enabled"]]
    c.close()
    if disabled:
        print(f"REFUSE — 这些叶子没吃到 omega 强验证: {disabled}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
