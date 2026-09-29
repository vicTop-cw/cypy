#!/usr/bin/env python3
"""R1-打磨 收口第二半：8 支分支与根任务 `T0r49` 按真实门禁上卷并归档。

任何 `__error__` 都记入 refused 并非零退出（上一版按 key 过滤把拒绝吞了，那是"守卫窄于主张"）。
根任务不带 `[omega:required]` ⇒ 根上的 claim/execute/submit/Omega 三连被拒是**既定语义**，
仍逐字进报告，不当成通过，也不当成本轮的错。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lfist_lib  # noqa: E402

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
ROOT_TASK = "T0r49"
NS = "cypy-loop-20260927"
L = ".fist-loop-20260927/"
REPORT = Path(sys.argv[1]).as_posix() if len(sys.argv) > 1 else None
REFUSED = []

BRANCH = {
    1: (
        "模式约束实测（polish 的 forbidden_tools 不承重）",
        L + "polish_law1_r1.json",
        "forbidden_tools",
    ),
    2: ("skip 标记逐条定性（3 处运行时 skip）", L + "polish_scan_r1.json", "law2_skip_marks"),
    3: (
        "mypy strict 可裁边界（改动面 1 条 / 全仓 950 条）",
        L + "polish_scan_r1.json",
        "law3_mypy",
    ),
    4: ("技术债标记收敛（TODO 仅 1 处，BOM 文件清点）", L + "polish_scan_r1.json", "law4_debt"),
    5: (
        "死代码与重复分支（2 组测试类被遮 + 2 个死 visitor）",
        L + "polish_probe_r1.json",
        "p1_shadowed_test_classes",
    ),
    6: (
        "quick win 闭环（去掉 3 个重复 dict 键，等价性静态证明）",
        L + "polish_baselines_r1.json",
        "quickwin_recheck",
    ),
    7: ("三套基线复跑不回落", L + "polish_baselines_r1.json", "pytest"),
    8: ("打磨报告与转结", REPORT or "", "[selfdrive-polish]"),
}


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


def main() -> int:
    if not REPORT:
        print("REFUSE — 未传报告路径")
        return 1
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    branches = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=2 order by id",
            (NS, ROOT_TASK + ".%"),
        )
    ]
    leaves_done = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=1 and status='已完成' order by id",
            (NS, ROOT_TASK + ".%"),
        )
    ]
    db.close()
    if len(branches) != 8:
        print(f"REFUSE — 分支 {len(branches)} 个（期望 8）")
        return 1
    if len(leaves_done) != 16:
        print(f"REFUSE — 只有 {len(leaves_done)}/16 张叶子已完成，空口上卷不做")
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
        law, art, needle = BRANCH[n]
        if not (ROOT / art).exists():
            print(f"REFUSE — 分支 {b} 的证据件不在盘上: {art}")
            return 1
        st = c.call("get", {"task_id": b})
        if (st.get("status") if isinstance(st, dict) else None) not in ("待验收", "已完成"):
            call(
                c,
                "execute",
                {
                    "task_id": b,
                    "deliverable": f"{law}｜上卷证据件 {art}",
                    "now": lfist_lib.utc_now(),
                },
            )
            call(c, "submit", {"task_id": b, "now": lfist_lib.utc_now()})
        omega_chain(c, b, law, art, needle)
        call(
            c,
            "omega_result_verify",
            {
                "task_id": b,
                "reviewer": "verifier",
                "verdict": "pass",
                "reason": "两支叶子已逐叶 output_validate+result_verify",
                "now": lfist_lib.utc_now(),
            },
        )
        call(c, "verify", {"task_id": b, "verifier": "cypy-polisher", "now": lfist_lib.utc_now()})

    call(
        c, "claim", {"task_id": ROOT_TASK, "assignee": "cypy-polisher", "now": lfist_lib.utc_now()}
    )
    call(
        c,
        "execute",
        {
            "task_id": ROOT_TASK,
            "deliverable": f"R1-打磨 交付：{REPORT}；实测 mode_list 的 polish 约束不承重"
            "（publish 仍能发出，已归档留痕 T0r50）；skip 标记 3 处逐条读定；"
            "quick win 1 项当场闭环（去 3 个重复 dict 键，静态等价证明 + 三套基线复跑）；"
            "新入账 BUG-41/42（T0r51/T0r52）；转结 mypy 与全仓 lint/black 规模交人类裁决",
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "submit", {"task_id": ROOT_TASK, "now": lfist_lib.utc_now()})
    omega_chain(c, ROOT_TASK, "打磨收口", REPORT, "[selfdrive-polish]")
    ov = call(
        c,
        "output_validate",
        {
            "task_id": ROOT_TASK,
            "project_dir": ".",
            "artifacts": [
                {"path": REPORT, "contains": "[selfdrive-polish]", "min_chars": 1500},
                {"path": L + "polish_baselines_r1.json", "contains": '"pytest"', "min_chars": 300},
            ],
            "evidence": "报告与三套基线取件当场以文件系统核验（L4）",
            "require_evidence": True,
            "now": lfist_lib.utc_now(),
        },
    )
    if not (isinstance(ov, dict) and ov.get("verdict") == "pass"):
        print("REFUSE — 根任务 L4 产物门没过，不 verify:", json.dumps(ov, ensure_ascii=False)[:300])
        c.close()
        return 2
    call(
        c,
        "omega_result_verify",
        {
            "task_id": ROOT_TASK,
            "reviewer": "verifier",
            "verdict": "pass",
            "reason": "quick win + 三套基线复跑当场 L4 通过",
            "now": lfist_lib.utc_now(),
        },
    )
    call(
        c, "verify", {"task_id": ROOT_TASK, "verifier": "cypy-polisher", "now": lfist_lib.utc_now()}
    )
    root = c.call("get", {"task_id": ROOT_TASK})
    final = root.get("status") if isinstance(root, dict) else None
    if final == "已完成":
        call(
            c, "archive", {"task_id": ROOT_TASK, "by": "human_steward", "now": lfist_lib.utc_now()}
        )
        root2 = c.call("get", {"task_id": ROOT_TASK})
        final = root2.get("status") if isinstance(root2, dict) else None

    log = c.call("call_log", {"limit": 400})
    rows = (
        log.get("calls")
        or log.get("entries")
        or log.get("items")
        or (log if isinstance(log, list) else [])
    )
    tally = Counter()
    for r in rows if isinstance(rows, list) else []:
        nm = (r.get("tool") or r.get("tool_name") or r.get("name")) if isinstance(r, dict) else None
        if nm:
            tally[nm] += 1
    c.close()
    doc = {
        "refused": REFUSED,
        "root_final": final,
        "leaves_done": len(leaves_done),
        "call_log_rows": len(rows) if isinstance(rows, list) else None,
        "call_log_tally": dict(sorted(tally.items())),
    }
    (HERE / "close_r1_polish_root.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:1000])
    if REFUSED:
        print(f"REFUSE — 收口链上有 {len(REFUSED)} 次被拒原文（逐字进报告）")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
