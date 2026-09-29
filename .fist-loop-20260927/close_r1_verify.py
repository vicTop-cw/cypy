#!/usr/bin/env python3
"""R1-验证 收口：T0r47 的 16 张叶子逐条走 omega 强验证链 + L4 产物硬门。

与 `close_r1_fix.py` 同一套判据（任一步 `__error__` 即判未达标；证据件不在盘上就整体拒绝；
`output_validate` 非 pass 一律不 verify）。
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
ROOT_TASK = "T0r47"
NS = "cypy-loop-20260927"
L = ".fist-loop-20260927/"

REPORT = sys.argv[1] if len(sys.argv) > 1 else None

LAWS = {
    1: (
        "pytest 全量实跑",
        [
            (L + "verify_pytest_full_r1.log", "passed", 500),
            (L + "verify_r1.json", '"pytest_full"', 600),
        ],
    ),
    2: (
        "自研套件与端到端基准",
        [
            (L + "verify_test_suite_r1.log", "Total: 47 | Passed: 47 | Failed: 0", 300),
            (L + "verify_e2e_r1.log", "PASS=25 FAIL=0", 300),
        ],
    ),
    3: (
        "修复面真编译复核",
        [
            (L + "verify_runtime_r1.json", '"ok": true', 300),
            (L + "verify_runtime_r1.json", '"bug38"', 300),
        ],
    ),
    4: (
        "CLI 与构建启动自检",
        [
            (L + "verify_cli_r1.json", "cypyc_file", 600),
            (L + "verify_cli_r1.json", '"transpile_artifacts"', 600),
        ],
    ),
    5: (
        "规范符合性检查",
        [
            (L + "verify_r1.json", '"lint_scoped"', 600),
            (L + "verify_r1.json", "mypy_record_only", 600),
        ],
    ),
    6: (
        "冻结文档与既有测试未改动",
        [
            (L + "verify_testdiff_r1.json", "renamed_sites", 400),
            ("memory/bugs.md", "R1-修复(循环轮)", 20000),
        ],
    ),
    7: (
        "账本一致性与脏工作树定性",
        [
            (L + "verify_dirt_r1.json", '"dangling_refs"', 400),
            (L + "loop_progress.md", "R1-修复", 800),
        ],
    ),
    8: (
        "验证报告与转结",
        [(REPORT, "[selfdrive-verify]", 1500), (L + "verify_r1.json", '"frozen_docs"', 600)],
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
        if resp.get("ok") is False:
            return json.dumps(
                {k: v for k, v in resp.items() if k in ("error", "reason", "problems")},
                ensure_ascii=False,
            )[:300]
    return None


def main() -> int:
    if not REPORT:
        print("REFUSE — 未传报告路径，法8 无证据件")
        return 1
    ids = leaves()
    if len(ids) != 16:
        print(f"REFUSE — 叶子反解到 {len(ids)} 张（期望 16）: {ids}")
        return 1
    bad_art = []
    for law, (name, arts) in LAWS.items():
        for rel, needle, minc in arts:
            p = ROOT / rel
            if not p.exists():
                bad_art.append(f"law{law} 证据件不在盘上: {rel}")
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            # 先在本地把「服务端会怎么判」算一遍：只查存在性的话，needle 拼错要等 16 次
            # output_validate 逐叶拒绝才暴露，而那些拒绝没法撤回。
            if needle not in t:
                bad_art.append(f"law{law} {rel} 不含「{needle}」")
            elif len(t) < minc:
                bad_art.append(f"law{law} {rel} 仅 {len(t)} 字符 < {minc}")
    if bad_art:
        print("REFUSE — 证据件预检未过（本地算一遍服务端的判法，不等 16 叶逐个被拒）：")
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
            "claim", {"task_id": tid, "assignee": "cypy-verifier", "now": lfist_lib.utc_now()}
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
                        "禁止": "跳过任一测试体系；把单文件绿当全量绿；弱化断言换通过",
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
                "deliverable": f"R1-验证 {law}｜证据件 {rel}（含「{needle}」、≥{minc} 字符）"
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
                "verify", {"task_id": tid, "verifier": "cypy-verifier", "now": lfist_lib.utc_now()}
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
                "steps": {
                    k: (
                        v
                        if isinstance(v, str)
                        else {
                            kk: v.get(kk) for kk in ("ok", "status", "verdict", "error") if kk in v
                        }
                        or v
                    )
                    for k, v in steps.items()
                },
            }
        )
        print(
            f"{tid} law={law} ov={steps['output_validate']['verdict']} "
            f"verify={'ok' if ok else 'SKIP'} err={bad or 'none'}"
        )

    root_after = c.call("get", {"task_id": ROOT_TASK})
    doc = {
        "leaves": out,
        "failed": failed,
        "root_status": root_after.get("status") if isinstance(root_after, dict) else None,
    }
    (HERE / "close_r1_verify.out.json").write_text(
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
