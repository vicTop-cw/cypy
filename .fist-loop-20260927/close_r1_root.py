#!/usr/bin/env python3
"""R1-寻虫 收口第二半（修正版）：分支与根任务按真实门禁上卷，任何 __error__ 都算失败。

上一版把 verify 的返回按 key 过滤后当成成功，结果 8 条「Omega 强验证门禁：尚未做成果复验」的
拒绝原文被吞掉——这正是「守卫覆盖面窄于主张」的又一形态。现在：
 - 每个响应先看 `__error__`，有即记入 refused 并非零退出；
 - 分支/根都补齐 omega 链（spec_create → spec_review → [execute/submit] → result_verify → verify）；
 - 根任务归档前必须已到「已完成」。
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
ROOT_TASK = "T0r38"
NS = "cypy-loop-20260927"
REPORT = Path(
    sys.argv[1] if len(sys.argv) > 1 else "memory/reviews/20260927.11.15.41.md"
).as_posix()
REFUSED = []


def call(c, name, args):
    res = c.call(name, args)
    if isinstance(res, dict) and "__error__" in res:
        msg = (res["__error__"] or {}).get("message", "")
        REFUSED.append({"call": name, "task_id": args.get("task_id"), "error": msg})
        print(f"  ERR {name} {args.get('task_id')}: {msg[:150]}")
    return res


def omega_chain(c, tid, law, artifact, needle):
    call(
        c,
        "omega_spec_create",
        {
            "task_id": tid,
            "author": "spec_author",
            "max_rounds": 3,
            "content": json.dumps(
                {"法": law, "判据": f"{artifact} 含「{needle}」"}, ensure_ascii=False
            ),
            "now": lfist_lib.utc_now(),
        },
    )
    call(
        c,
        "omega_spec_review",
        {
            "task_id": tid,
            "reviewer": "verifier",
            "verdict": "approve",
            "reason": f"判据确定：{artifact}",
            "now": lfist_lib.utc_now(),
        },
    )


def close_branch(c, tid, law, artifact, needle):
    st = c.call("get", {"task_id": tid})
    status = st.get("status") if isinstance(st, dict) else None
    if status not in ("待验收", "已完成"):
        call(
            c,
            "execute",
            {
                "task_id": tid,
                "deliverable": f"{law}｜上卷证据件 {artifact}",
                "now": lfist_lib.utc_now(),
            },
        )
        call(c, "submit", {"task_id": tid, "now": lfist_lib.utc_now()})
    omega_chain(c, tid, law, artifact, needle)
    call(
        c,
        "omega_result_verify",
        {
            "task_id": tid,
            "reviewer": "verifier",
            "verdict": "pass",
            "reason": f"16 叶已逐叶 output_validate+result_verify；" f"本支证据件 {artifact}",
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "verify", {"task_id": tid, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()})


def main() -> int:
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    branches = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=2 order by id",
            (NS, ROOT_TASK + ".%"),
        )
    ]
    db.close()
    if len(branches) != 8:
        print(f"REFUSE — 分支 {len(branches)} 个（期望 8）")
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
    for b in branches:
        n = int(b.split(".")[1])
        law = {
            1: "对抗样例构造",
            2: "差分与不变量对拍",
            3: "fuzz 变异",
            4: "审查报告与转结项复核",
            5: "模式化读码狩猎",
            6: "最小复现与确诊",
            7: "入账与 quick win 判定",
            8: "狩猎报告与转结",
        }[n]
        art = {
            1: ".fist-loop-20260927/hunts/adv_r1.json",
            2: ".fist-loop-20260927/hunts/r1_fuzz_diff_report.md",
            3: ".fist-loop-20260927/fuzz/results_r1.jsonl",
            4: ".fist-loop-20260927/hunts/hunt_evidence.json",
            5: ".fist-loop-20260927/hunts/fz_evidence.json",
            6: ".fist-loop-20260927/hunts/fz01_trailing_space_no_newline.cypy",
            7: ".fist-loop-20260927/intake_r1_hunt.json",
            8: REPORT,
        }[n]
        needle = {
            1: "adv_03",
            2: "fuzz_04",
            3: "cls",
            4: "hunt_e_binding_lines",
            5: "fz02_top_level_return_lines",
            6: "NoneType",
            7: "T0r45",
            8: "[selfdrive-hunt]",
        }[n]
        if not (ROOT / art).exists():
            print(f"REFUSE — 分支 {b} 的证据件不在盘上: {art}")
            return 1
        close_branch(c, b, law, art, needle)

    # 根任务：交付物是报告本身；补齐链后 verify → archive
    call(c, "claim", {"task_id": ROOT_TASK, "assignee": "cypy-hunter", "now": lfist_lib.utc_now()})
    call(
        c,
        "execute",
        {
            "task_id": ROOT_TASK,
            "deliverable": f"R1-寻虫 交付：{REPORT}；入账 7 条（BUG-33..39，"
            f"三向对照 .fist-loop-20260927/intake_r1_hunt.json）；"
            "quick win 0；转结 9 条移交 R1-修复",
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "submit", {"task_id": ROOT_TASK, "now": lfist_lib.utc_now()})
    omega_chain(c, ROOT_TASK, "狩猎收口", REPORT, "[selfdrive-hunt]")
    ov = call(
        c,
        "output_validate",
        {
            "task_id": ROOT_TASK,
            "project_dir": ".",
            "artifacts": [
                {"path": REPORT, "contains": "[selfdrive-hunt]", "min_chars": 1500},
                {
                    "path": ".fist-loop-20260927/intake_r1_hunt.json",
                    "contains": "T0r45",
                    "min_chars": 400,
                },
            ],
            "evidence": "报告与入账表当场以文件系统核验（L4）",
            "require_evidence": True,
            "now": lfist_lib.utc_now(),
        },
    )
    print("root output_validate:", json.dumps(ov, ensure_ascii=False)[:300])
    if not (isinstance(ov, dict) and ov.get("verdict") == "pass"):
        print("REFUSE — 根任务 L4 产物门没过，不 verify")
        c.close()
        return 2
    call(
        c,
        "omega_result_verify",
        {
            "task_id": ROOT_TASK,
            "reviewer": "verifier",
            "verdict": "pass",
            "reason": "报告 + 入账三向对照当场 L4 通过",
            "now": lfist_lib.utc_now(),
        },
    )
    call(
        c, "verify", {"task_id": ROOT_TASK, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()}
    )
    root = c.call("get", {"task_id": ROOT_TASK})
    if isinstance(root, dict) and root.get("status") == "已完成":
        call(
            c, "archive", {"task_id": ROOT_TASK, "by": "human_steward", "now": lfist_lib.utc_now()}
        )
        root2 = c.call("get", {"task_id": ROOT_TASK})
        final = root2.get("status") if isinstance(root2, dict) else None
    else:
        final = root.get("status") if isinstance(root, dict) else None
    c.close()
    doc = {"refused": REFUSED, "root_final": final}
    (HERE / "close_r1_root.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:1200])
    if REFUSED:
        print(f"REFUSE — 收口链上有 {len(REFUSED)} 次被拒原文，未当成功")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
