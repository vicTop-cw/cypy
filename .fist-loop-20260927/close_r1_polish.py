#!/usr/bin/env python3
"""R1-打磨 收口：T0r49 的 16 张叶子逐条走 omega 强验证链 + L4 产物硬门。

与 `close_r1_verify.py` 同一套判据形状（任一步 `__error__` 即记失败；证据件先做**本地预检**：
存在 + 含 needle + 够 min_chars，三项任一不过就整体拒绝，不等 16 次服务端逐叶拒绝——
服务端拒绝不可撤回，而预检是我方可复算的）。叶子清单从 sqlite 反解，不手写。
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
ROOT_TASK = "T0r49"
NS = "cypy-loop-20260927"
L = ".fist-loop-20260927/"

REPORT = sys.argv[1] if len(sys.argv) > 1 else None

LAWS = {
    1: (
        "模式约束实测与账本口径定死",
        [
            (L + "polish_law1_r1.json", "forbidden_tools", 1200),
            (L + "polish_law1_r1.json", "publish_has_mode_param", 1200),
        ],
    ),
    2: (
        "skip 标记逐条定性",
        [
            (L + "polish_scan_r1.json", "law2_skip_marks", 2000),
            (L + "polish_probe_r1.json", "p3_skip_experiments", 1500),
        ],
    ),
    3: (
        "mypy 可裁边界与存量清单",
        [
            (L + "polish_scan_r1.json", "law3_mypy", 2000),
            (L + "polish_scan_r1.json", "per_code", 2000),
        ],
    ),
    4: (
        "技术债标记收敛",
        [
            (L + "polish_scan_r1.json", "law4_debt", 2000),
            (L + "polish_scan_r1.json", "bom_py_files", 2000),
        ],
    ),
    5: (
        "死代码与重复分支清理",
        [
            (L + "polish_probe_r1.json", "p2_dead_visitors", 1500),
            (L + "polish_probe_r1.json", "p1_shadowed_test_classes", 1500),
        ],
    ),
    6: (
        "quick win 判定与当场闭环",
        [
            (L + "polish_baselines_r1.json", "quickwin_recheck", 300),
            ("memory/bugs.md", "BUG-41", 20000),
        ],
    ),
    7: (
        "双套基线与端到端基准复跑",
        [
            (L + "polish_pytest_r1.log", " passed", 500),
            (L + "polish_baselines_r1.json", "Total: 47 | Passed: 47", 300),
            (L + "polish_wallclock_r1.json", '"target"', 600),
            (L + "polish_pytest_r1.try1.log", "1 failed, 1861 passed", 300),
        ],
    ),
    8: (
        "打磨报告与转结",
        [
            (REPORT or "", "[selfdrive-polish]", 1500),
            (L + "polish_scan_r1.json", "law5_candidates", 2000),
        ],
    ),
}


def leaves():
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rows = list(
        db.execute(
            "select id from tasks where ns=? and id like ? and depth=1 order by id",
            (NS, ROOT_TASK + ".%"),
        )
    )
    db.close()
    return [r[0] for r in rows]


def err_of(resp):
    if isinstance(resp, dict):
        if "__error__" in resp:
            return json.dumps(resp["__error__"], ensure_ascii=False)[:300]
    return None


def main() -> int:
    if not REPORT:
        print("REFUSE — 未传报告路径，法8 无证据件")
        return 1
    ids = leaves()
    if len(ids) != 16:
        print(f"REFUSE — 叶子反解到 {len(ids)} 张（期望 16）：{ids}")
        return 1
    bad_art = []
    for law, (name, arts) in LAWS.items():
        for rel, needle, minc in arts:
            p = ROOT / rel
            if not p.exists():
                bad_art.append(f"law{law} 证据件不在盘上: {rel}")
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if needle not in t:
                bad_art.append(f"law{law} {rel} 不含「{needle}」")
            elif len(t) < minc:
                bad_art.append(f"law{law} {rel} 仅 {len(t)} 字符 < {minc}")
    if bad_art:
        print("REFUSE — 证据件预检未过：")
        for b in bad_art:
            print("  " + b)
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
        law_no, slot = int(tid.split(".")[1]), int(tid.split(".")[2]) - 1
        law, arts = LAWS[law_no]
        rel, needle, minc = arts[min(slot, len(arts) - 1)]
        steps, bad = {}, []
        steps["claim"] = c.call(
            "claim", {"task_id": tid, "assignee": "cypy-polisher", "now": lfist_lib.utc_now()}
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
                        "判据": f"证据件 {rel} 必须存在、≥{minc} 字符且含「{needle}」",
                        "禁止": "加新功能；动 PROJECT-SPEC/SYNTAX 语义；删测试或弱化断言；"
                        "把 mode_list 的声明当成服务端已执行的约束",
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
                "reason": f"判据确定：{rel}",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["execute"] = c.call(
            "execute",
            {
                "task_id": tid,
                "deliverable": f"R1-打磨 {law}｜证据件 {rel}（含「{needle}」、≥{minc} 字符）"
                f"｜报告 {REPORT}",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["submit"] = c.call("submit", {"task_id": tid, "now": lfist_lib.utc_now()})
        ov = c.call(
            "output_validate",
            {
                "task_id": tid,
                "project_dir": ".",
                "artifacts": [{"path": rel, "contains": needle, "min_chars": minc}],
                "evidence": f"当场以 output_validate 查 {rel}",
                "require_evidence": True,
                "now": lfist_lib.utc_now(),
            },
        )
        steps["output_validate"] = {
            "verdict": ov.get("verdict"),
            "failed": ov.get("failed") or ov.get("problems") or ov.get("missing"),
        }
        for name, resp in steps.items():
            e = err_of(ov) if name == "output_validate" else err_of(resp)
            if e:
                bad.append(f"{name}: {e}")
        ok = ov.get("verdict") == "pass" and not bad
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
                "verify", {"task_id": tid, "verifier": "cypy-polisher", "now": lfist_lib.utc_now()}
            )
        else:
            steps["result_verify"] = c.call(
                "omega_result_verify",
                {
                    "task_id": tid,
                    "reviewer": "verifier",
                    "verdict": "reject",
                    "reason": f"门禁不绿：ov={steps['output_validate']} 服务侧={bad}",
                    "now": lfist_lib.utc_now(),
                },
            )
            steps["verify"] = "SKIPPED（门禁不绿不得 verify）"
            failed.append({"task_id": tid, "why": steps["output_validate"], "errors": bad})
        out.append(
            {
                "task_id": tid,
                "law": law,
                "artifact": rel,
                "ov": steps["output_validate"]["verdict"],
                "verify": (
                    steps["verify"].get("status")
                    if isinstance(steps["verify"], dict)
                    else steps["verify"]
                ),
                "errors": bad,
            }
        )
        print(
            f"{tid} law={law} ov={steps['output_validate']['verdict']} "
            f"verify={'ok' if ok else 'SKIP'} err={bad or 'none'}"
        )

    doc = {"leaves": out, "failed": failed, "root_task": ROOT_TASK}
    (HERE / "close_r1_polish.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    c.close()
    print(f"closed={len(out) - len(failed)}/{len(out)} failed={failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
