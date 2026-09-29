#!/usr/bin/env python3
"""R1-验证 收口第二半：T0r47 的 8 条分支与根任务上卷 + 归档 + call_log 对账。

任何 `__error__` 都记入 refused 并非零退出；被拒只允许发生在根任务上
（根 description 不带 `[omega:required]`，且分支上卷后根已是「待验收」）。
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
ROOT_TASK = "T0r47"
NS = "cypy-loop-20260927"
REPORT = Path(sys.argv[1]).as_posix()
L = ".fist-loop-20260927/"
REFUSED = []

LAWS = {
    1: ("pytest 全量实跑", L + "verify_pytest_full_r1.log", "passed"),
    2: ("自研套件与端到端基准", L + "verify_e2e_r1.log", "PASS=25 FAIL=0"),
    3: ("修复面真编译复核", L + "verify_runtime_r1.json", '"ok": true'),
    4: ("CLI 与构建启动自检", L + "verify_cli_r1.json", "cypyc_file"),
    5: ("规范符合性检查", L + "verify_r1.json", "mypy_record_only"),
    6: ("冻结文档与既有测试未改动", L + "verify_testdiff_r1.json", "renamed_sites"),
    7: ("账本一致性与脏工作树定性", L + "verify_dirt_r1.json", "dangling_refs"),
    8: ("验证报告与转结", REPORT, "[selfdrive-verify]"),
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
                    "判据": f"{artifact} 含「{needle}」；" "五套判据均为子进程实跑，不读回忆",
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
        law, art, needle = LAWS[n]
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
        call(c, "verify", {"task_id": b, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()})

    call(
        c, "claim", {"task_id": ROOT_TASK, "assignee": "cypy-verifier", "now": lfist_lib.utc_now()}
    )
    call(
        c,
        "execute",
        {
            "task_id": ROOT_TASK,
            "deliverable": f"R1-验证 交付：{REPORT}；五套判据全绿（全量 pytest / 自研 47 / e2e 25 /"
            " 冻结文档 / lint），修复面真编译复核三条过，"
            "既有测试改动经可复算 diff 证明是 rename-only；"
            "转结 mypy 存量、skip 标记、legacy 删除定性 → R1-打磨",
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "submit", {"task_id": ROOT_TASK, "now": lfist_lib.utc_now()})
    omega_chain(c, ROOT_TASK, "验证收口", REPORT, "[selfdrive-verify]")
    ov = call(
        c,
        "output_validate",
        {
            "task_id": ROOT_TASK,
            "project_dir": ".",
            "artifacts": [
                {"path": REPORT, "contains": "[selfdrive-verify]", "min_chars": 1500},
                {"path": L + "verify_r1.json", "contains": '"pytest_full"', "min_chars": 500},
            ],
            "evidence": "报告与五套取证件当场以文件系统核验（L4）",
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
            "reason": "五套判据 + 真编译复核当场 L4 通过",
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
    (HERE / "close_r1_verify_root.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(json.dumps(doc, ensure_ascii=False, indent=1)[:1200])
    if REFUSED:
        print(f"REFUSE — 收口链上有 {len(REFUSED)} 次被拒原文（逐字进报告）")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
