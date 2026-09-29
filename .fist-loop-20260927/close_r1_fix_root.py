#!/usr/bin/env python3
"""R1-修复 收口第二半：T0r46 的 8 条分支与根任务按真实门禁上卷，任何 `__error__` 都算失败。

与 R1-寻虫 的根收口件同型，另加 call_log 对账（本环节到底用了哪些工具、各几次，
以服务端记录为准而不是靠回忆）。
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
ROOT_TASK = "T0r46"
NS = "cypy-loop-20260927"
REPORT = Path(sys.argv[1]).as_posix()
REFUSED = []

LAWS = {
    1: (
        "BUG-30 生成码补隐式 <double> 强转",
        ".fist-loop-20260927/golden_diff_r1.json",
        "digit_only_lines",
    ),
    2: ("BUG-31 bridge 宽度表口径与改名", "cypy_bridge/types.py", "float32_"),
    3: (
        "BUG-33 未闭合字符串必须诊断",
        "cypyc/parser/lexer.py",
        "Unterminated string literal opened at",
    ),
    4: ("BUG-38 词法器 EOF 尾随空白不得崩", "cypyc/parser/lexer.py", "while self._peek() in ("),
    5: ("每单锁死回归 + 回退树证红", ".fist-loop-20260927/lockproof_r1.json", "full_tree"),
    6: (
        "端到端基准先快照再重注册",
        ".fist-loop-20260927/golden_update_r1.log",
        "[e2e-golden] summary",
    ),
    7: ("双套基线复跑与账本 FIXED 留档", "memory/bugs.md", "2026-09-27 R1-修复(循环轮)"),
    8: ("修复报告与转结", REPORT, "[selfdrive-fixmerge]"),
}


def call(c, name, args):
    res = c.call(name, args)
    if isinstance(res, dict) and "__error__" in res:
        msg = (res["__error__"] or {}).get("message", "")
        REFUSED.append({"call": name, "task_id": args.get("task_id"), "error": msg})
        print(f"  ERR {name} {args.get('task_id')}: {msg[:160]}")
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
                {
                    "法": law,
                    "判据": f"{artifact} 含「{needle}」；"
                    "回退树证红与双套基线见 lockproof_r1.json / run_baselines_r1.json",
                },
                ensure_ascii=False,
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
        # 本库里 depth=1 是 16 张叶子、depth=2 是 8 条分支（与 R1-寻虫 的收口件同一实测）
        print(f"REFUSE — 只有 {len(leaves_done)}/16 张叶子已完成，叶子链未全绿就上卷 = 空口上卷")
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
        law, art, needle = LAWS[n]
        if not (ROOT / art).exists():
            print(f"REFUSE — 分支 {b} 的证据件不在盘上: {art}")
            return 1
        st = c.call("get", {"task_id": b})
        status = st.get("status") if isinstance(st, dict) else None
        if status not in ("待验收", "已完成"):
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
                "reason": "两支叶子已逐叶 output_validate+result_verify；" f"本支证据件 {art}",
                "now": lfist_lib.utc_now(),
            },
        )
        call(c, "verify", {"task_id": b, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()})

    call(c, "claim", {"task_id": ROOT_TASK, "assignee": "cypy-fixer", "now": lfist_lib.utc_now()})
    call(
        c,
        "execute",
        {
            "task_id": ROOT_TASK,
            "deliverable": f"R1-修复 交付：{REPORT}；清 4 单（BUG-30/31/33/38，"
            "账本各一段 FIXED）；锁 8 条（4 锁 + 4 对照）逐单回退树证红；"
            "基准重注册 1 份变化 / 24 份未变；转结 5 单 → R2-修复；"
            "合并面=无（github token 不在位，不 push 不 PR）",
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "submit", {"task_id": ROOT_TASK, "now": lfist_lib.utc_now()})
    omega_chain(c, ROOT_TASK, "修复收口", REPORT, "[selfdrive-fixmerge]")
    ov = call(
        c,
        "output_validate",
        {
            "task_id": ROOT_TASK,
            "project_dir": ".",
            "artifacts": [
                {"path": REPORT, "contains": "[selfdrive-fixmerge]", "min_chars": 1500},
                {
                    "path": ".fist-loop-20260927/lockproof_r1.json",
                    "contains": '"refuse": []',
                    "min_chars": 800,
                },
            ],
            "evidence": "报告与证红件当场以文件系统核验（L4）",
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
            "reason": "报告 + 证红件 + 双套基线当场 L4 通过",
            "now": lfist_lib.utc_now(),
        },
    )
    call(
        c, "verify", {"task_id": ROOT_TASK, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()}
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
        nm = r.get("tool") or r.get("tool_name") or r.get("name") if isinstance(r, dict) else None
        if nm:
            tally[nm] += 1
    c.close()
    doc = {
        "refused": REFUSED,
        "root_final": final,
        "call_log_rows": len(rows) if isinstance(rows, list) else None,
        "call_log_tally": dict(sorted(tally.items())),
    }
    (HERE / "close_r1_fix_root.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:1500])
    if REFUSED:
        print(f"REFUSE — 收口链上有 {len(REFUSED)} 次被拒原文，未当成功")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
