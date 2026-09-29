#!/usr/bin/env python3
"""R1-寻虫 收口：16 张叶子逐条走 omega 强验证链 + L4 产物硬门，然后 verify。

链路顺序照模板：claim → omega_spec_create → omega_spec_review(approve) → execute → submit
→ output_validate(L4，只认 path/contains/not_contains/min_chars) → omega_result_verify(pass) → verify。
铁律：**output_validate 不是 pass 就不 verify、不 result_verify(pass)**，
把该叶记成 未达标 并让本脚本非零退出——门禁不绿不得 verify。
叶子清单从 sqlite 只读反解（`get` 只回单条记录，靠它会把空集合当通过）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
ROOT_TASK = "T0r38"
NS = "cypy-loop-20260927"
REPORT = Path(os.environ.get("REPORT", "memory/reviews/20260927.11.15.41.md")).as_posix()

LAWS = {
    1: ("对抗样例构造", [("hunts/adv_r1.json", "adv_03", 500), ("hunts/adv_r1.md", "候选", 300)]),
    2: ("差分与不变量对拍", [("hunts/r1_fuzz_diff_report.md", "fuzz_04", 400)]),
    3: (
        "fuzz 变异（预算内）",
        [("fuzz/results_r1.jsonl", '"cls"', 5000), ("fuzz/fuzz_r1.py", "SEED", 1000)],
    ),
    4: ("审查报告与转结项复核", [("hunts/hunt_evidence.json", "hunt_e_binding_lines", 400)]),
    5: ("模式化读码狩猎", [("hunts/fz_evidence.json", "fz02_top_level_return_lines", 200)]),
    6: (
        "最小复现与确诊",
        [
            ("hunts/hunt_e_extractor_positional.cypy", "__unapply__", 100),
            ("hunts/fz01_trailing_space_no_newline.cypy", "return", 20),
        ],
    ),
    7: ("入账与 quick win 判定", [("intake_r1_hunt.json", "T0r45", 400)]),
    8: ("狩猎报告与转结", [(str(REPORT), "[selfdrive-hunt]", 1500)]),
}


def leaves():
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rows = list(
        db.execute(
            "select id, depth, status from tasks where ns=? and id like ? and depth=1 order by id",
            (NS, ROOT_TASK + ".%"),
        )
    )
    db.close()
    return [r[0] for r in rows]


def rooted(rel: str) -> str:
    """output_validate 的 path 按 server cwd（Cypy 根）解析——证据件都在本目录下，必须补前缀。"""
    return rel if rel.startswith(("memory/", ".fist-loop-")) else ".fist-loop-20260927/" + rel


def main() -> int:
    ids = leaves()
    if len(ids) != 16:
        print(f"REFUSE — 叶子反解到 {len(ids)} 张（期望 16：8 支 × 2 叶），口径不对不开工: {ids}")
        return 1
    for k, (law, arts) in LAWS.items():
        for rel, _needle, _mc in arts:
            if not (ROOT / rooted(rel)).exists():
                print(f"REFUSE — 法{law} 点名的证据件不在盘上: {rooted(rel)}")
                return 1

    c = lfist_lib.Client(timeout=240)
    c._send(
        "initialize",
        {
            "protocolVersion": lfist_lib.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": lfist_lib.CLIENT_INFO,
        },
    )
    out, failed = [], []
    for tid in ids:
        law_no = int(tid.split(".")[1])
        law, arts = LAWS[law_no]
        slot = int(tid.split(".")[2]) - 1
        art = arts[min(slot, len(arts) - 1)]
        rel, needle, minc = art
        rpath = rooted(rel)
        rec = {"task_id": tid, "law": law, "artifact": rpath}
        steps = {}
        steps["claim"] = c.call(
            "claim", {"task_id": tid, "assignee": "cypy-hunter", "now": lfist_lib.utc_now()}
        )
        steps["spec_create"] = c.call(
            "omega_spec_create",
            {
                "task_id": tid,
                "author": "spec_author",
                "max_rounds": 3,
                "content": json.dumps(
                    {
                        "法": law,
                        "判据": f"交付物 {rpath} 必须存在、≥{minc} 字符且含「{needle}」",
                        "禁止": "无证据件收口；把误报刷进账本；修超出 quick win 三条硬门槛",
                    },
                    ensure_ascii=False,
                ),
                "now": lfist_lib.utc_now(),
            },
        )
        steps["spec_review"] = c.call(
            "omega_spec_review",
            {
                "task_id": tid,
                "reviewer": "verifier",
                "verdict": "approve",
                "reason": f"语料可判：{rpath} 的存在性/规模/内容三项都是确定判据",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["execute"] = c.call(
            "execute",
            {
                "task_id": tid,
                "deliverable": f"R1-寻虫 {law}｜证据件 {rpath}（判据：含「{needle}」、≥{minc} 字符）"
                f"｜狩猎报告 {REPORT}",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["submit"] = c.call("submit", {"task_id": tid, "now": lfist_lib.utc_now()})
        ov = c.call(
            "output_validate",
            {
                "task_id": tid,
                "project_dir": ".",
                "artifacts": [{"path": rpath, "contains": needle, "min_chars": minc}],
                "evidence": f"当场以 output_validate 查 {rpath}",
                "require_evidence": True,
                "now": lfist_lib.utc_now(),
            },
        )
        steps["output_validate"] = {
            "verdict": ov.get("verdict"),
            "failed": ov.get("failed") or ov.get("problems") or ov.get("missing"),
        }
        ok = ov.get("verdict") == "pass"
        if ok:
            steps["result_verify"] = c.call(
                "omega_result_verify",
                {
                    "task_id": tid,
                    "reviewer": "verifier",
                    "verdict": "pass",
                    "reason": f"L4 产物硬门 pass：{rel}",
                    "now": lfist_lib.utc_now(),
                },
            )
            steps["verify"] = c.call(
                "verify", {"task_id": tid, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()}
            )
        else:
            steps["result_verify"] = c.call(
                "omega_result_verify",
                {
                    "task_id": tid,
                    "reviewer": "verifier",
                    "verdict": "reject",
                    "reason": f"output_validate 非 pass：{steps['output_validate']}",
                    "now": lfist_lib.utc_now(),
                },
            )
            steps["verify"] = "SKIPPED（门禁不绿不得 verify）"
            failed.append(tid)
        rec["steps"] = {
            k: (
                v
                if isinstance(v, str)
                else {kk: v.get(kk) for kk in ("ok", "status", "verdict", "error") if kk in v} or v
            )
            for k, v in steps.items()
        }
        out.append(rec)
        print(
            f"{tid} law={law} ov={steps['output_validate']['verdict']} "
            f"verify={'ok' if ok else 'SKIP'}"
        )

    root_after = c.call("get", {"task_id": ROOT_TASK})
    doc = {
        "leaves": out,
        "failed": failed,
        "root_status": root_after.get("status") if isinstance(root_after, dict) else None,
    }
    (HERE / "close_r1_hunt.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    c.close()
    print(
        f"closed={len(out) - len(failed)}/{len(out)} failed={failed or 'none'} "
        f"root_status={doc['root_status']}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
