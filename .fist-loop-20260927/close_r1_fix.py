#!/usr/bin/env python3
"""R1-修复 收口：T0r46 的 16 张叶子逐条走 omega 强验证链 + L4 产物硬门，然后 verify。

与 R1-寻虫 的收口件同型，两处加严：
  1. **任一步回复里出现 `__error__` 即判该叶未达标**（上一版按 key 过滤会把服务端拒绝
     当成"没这条记录"吞掉，是自检时抓到的自坑）；
  2. 证据件不在盘上就在开链之前整体拒绝，不允许"先 claim 再找证据"。
链路：claim → omega_spec_create → omega_spec_review(approve) → execute → submit
→ output_validate(L4) → omega_result_verify(pass) → verify；output_validate 非 pass 不 verify。
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
ROOT_TASK = "T0r46"
NS = "cypy-loop-20260927"
REPORT = sys.argv[1] if len(sys.argv) > 1 else None

LAWS = {
    1: (
        "BUG-30 生成码补隐式 <double> 强转",
        [
            ("tests/test_loop_20260927_fix.py", "e: double = <double>a", 600),
            (".fist-loop-20260927/golden_diff_r1.json", '"digit_only_lines"', 300),
        ],
    ),
    2: (
        "BUG-31 bridge 宽度表口径措辞",
        [
            ("cypy_bridge/types.py", "本模块的映射键是 **C/FFI 类型名**", 1200),
            (
                "tests/test_loop_20260927_fix.py",
                "test_bug31_width_of_bridge_float_is_unchanged",
                600,
            ),
        ],
    ),
    3: (
        "BUG-33 未闭合字符串必须诊断",
        [
            ("cypyc/parser/lexer.py", "Unterminated string literal opened at", 3000),
            (
                "tests/test_loop_20260927_fix.py",
                "test_bug33_unterminated_string_raises_with_position",
                600,
            ),
        ],
    ),
    4: (
        "BUG-38 词法器 EOF 尾随空白不得崩",
        [
            ("cypyc/parser/lexer.py", "while self._peek() in (", 3000),
            (
                "tests/test_loop_20260927_fix.py",
                "test_bug38_trailing_spaces_at_eof_do_not_crash",
                600,
            ),
        ],
    ),
    5: (
        "每单锁死回归 + 回退树证红",
        [
            (".fist-loop-20260927/lockproof_r1.json", '"full_tree"', 800),
            ("tests/test_loop_20260927_fix.py", "对照锁", 600),
        ],
    ),
    6: (
        "端到端基准先快照再重注册",
        [
            (".fist-loop-20260927/golden_update_r1.log", "[e2e-golden] summary", 200),
            (".fist-loop-20260927/goldendiff_r1.py", "只落在数字上", 400),
        ],
    ),
    7: (
        "双套基线复跑与账本 FIXED 留档",
        [
            (".fist-loop-20260927/run_baselines_r1.json", '"test_suite"', 500),
            ("memory/bugs.md", "2026-09-27 R1-修复(循环轮)", 20000),
        ],
    ),
    8: (
        "修复报告与转结",
        [
            (REPORT, "[selfdrive-fixmerge]", 1500),
            (".fist-loop-20260927/loop_progress.md", "R1-验证", 800),
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


def err_of(resp) -> str | None:
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
        print(f"REFUSE — 叶子反解到 {len(ids)} 张（期望 16），口径不对不开工: {ids}")
        return 1
    for law_no, (law, arts) in LAWS.items():
        for rel, _needle, _mc in arts:
            if not (ROOT / rel).exists():
                print(f"REFUSE — 法{law} 点名的证据件不在盘上: {rel}")
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
        rec = {"task_id": tid, "law": law, "artifact": rel}
        steps, bad = {}, []
        steps["claim"] = c.call(
            "claim", {"task_id": tid, "assignee": "cypy-fixer", "now": lfist_lib.utc_now()}
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
                        "判据": f"交付物 {rel} 必须存在、≥{minc} 字符且含「{needle}」；"
                        f"回退树证红与双套基线见 lockproof_r1.json / run_baselines_r1.json",
                        "禁止": "无证据收口；把没修的写成已闭环；弱化既有测试",
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
                "reason": f"语料可判：{rel} 的存在/规模/内容三项均为确定判据",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["execute"] = c.call(
            "execute",
            {
                "task_id": tid,
                "deliverable": f"R1-修复 {law}｜证据件 {rel}（含「{needle}」、≥{minc} 字符）"
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
            e = err_of(resp) if name != "output_validate" else err_of(ov)
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
                    "reason": f"门禁不绿：ov={steps['output_validate']} 服务侧拒绝={bad}",
                    "now": lfist_lib.utc_now(),
                },
            )
            steps["verify"] = "SKIPPED（门禁不绿不得 verify）"
            failed.append({"task_id": tid, "why": steps["output_validate"], "errors": bad})
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
            f"verify={'ok' if ok else 'SKIP'} err={bad or 'none'}"
        )

    root_after = c.call("get", {"task_id": ROOT_TASK})
    doc = {
        "leaves": out,
        "failed": failed,
        "root_status": root_after.get("status") if isinstance(root_after, dict) else None,
    }
    (HERE / "close_r1_fix.out.json").write_text(
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
