#!/usr/bin/env python3
"""通用的「16 叶 omega 强验证链 + L4 产物硬门」收口驱动（五环 × 五轮复用）。

用法：python close_stage_generic.py <spec.json> <报告路径>

spec.json = {
  "key": "r1_advance",              # 输出文件名用：close_<key>.out.json
  "root_task": "T0r54",
  "assignee": "cypy-advancer",
  "stage": "R1-推进",
  "forbid": "…禁止事项，写进 omega 语料…",
  "laws": [                          # 8 条法，每条 2 张叶子，逐叶轮流取证据件
    {"name": "…", "artifacts": [["<repo 相对路径>", "<needle>", <min_chars>], …]}
  ]
}

判据形状与 close_r1_verify/polish 一致：证据件先做**本地预检**（存在 + 含 needle + 够 min_chars），
任一不过就整体拒绝、一个服务端调用都不发（服务端拒绝不可撤回，预检是我方可复算的）；
链上任一步出现 __error__ 即记该叶失败；**门禁不绿不得 verify**。
叶子清单从 sqlite 反解（depth=1），不手写。
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
NS = "cypy-loop-20260927"

SPEC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
REPORT = sys.argv[2] if len(sys.argv) > 2 else None

_extra = [a for a in sys.argv[3:] if a.startswith("-")]
if _extra:
    # 2026-09-27 R3-寻虫：我给这驱动传了个它根本没有的 `--dry-run`，它不报错、直接跑成真实落库
    # ⇒ 未知旗标必须炸，不能静默收下（"我以为在试跑"和"已经提交"之间原本没有护栏）
    raise SystemExit(f"REFUSE — 本驱动不收旗标，收到 {_extra}；要预检请读 close 前打印的清单")


def leaves(root_task: str) -> list:
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    rows = list(
        db.execute(
            "select id from tasks where ns=? and id like ? and depth=1 order by id",
            (NS, root_task + ".%"),
        )
    )
    db.close()
    return [r[0] for r in rows]


def err_of(resp) -> str | None:
    if isinstance(resp, dict) and "__error__" in resp:
        return json.dumps(resp["__error__"], ensure_ascii=False)[:300]
    return None


def preflight(laws: list) -> list:
    bad = []
    for i, law in enumerate(laws, 1):
        arts = law.get("artifacts") or []
        if not arts:
            bad.append(f"law{i} 没有证据件，判据无从谈起")
        for rel, needle, minc in arts:
            p = ROOT / rel
            if not p.exists():
                bad.append(f"law{i} 证据件不在盘上: {rel}")
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if needle not in t:
                bad.append(f"law{i} {rel} 不含「{needle}」")
            elif len(t) < int(minc):
                bad.append(f"law{i} {rel} 仅 {len(t)} 字符 < {minc}")
    return bad


def main() -> int:
    if not SPEC or not REPORT:
        print("REFUSE — 用法：close_stage_generic.py <spec.json> <报告路径>")
        return 1
    root_task, assignee = SPEC["root_task"], SPEC["assignee"]
    laws = SPEC["laws"]
    ids = leaves(root_task)
    if len(ids) != 16:
        print(f"REFUSE — 叶子反解到 {len(ids)} 张（期望 16）：{ids}")
        return 1
    bad_art = preflight(laws)
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
        law = laws[law_no - 1]
        arts = law["artifacts"]
        rel, needle, minc = arts[min(slot, len(arts) - 1)]
        steps, bad = {}, []
        steps["claim"] = c.call(
            "claim", {"task_id": tid, "assignee": assignee, "now": lfist_lib.utc_now()}
        )
        steps["spec_create"] = c.call(
            "omega_spec_create",
            {
                "task_id": tid,
                "author": "spec_author",
                "max_rounds": 3,
                "content": json.dumps(
                    {
                        "法": law["name"],
                        "判据": f"证据件 {rel} 必须存在、≥{int(minc)} 字符且含「{needle}」",
                        "禁止": law.get("forbid", SPEC.get("forbid", "")),
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
                "deliverable": f"{SPEC['stage']} {law['name']}｜证据件 {rel}"
                f"（含「{needle}」、≥{int(minc)} 字符）｜报告 {REPORT}",
                "now": lfist_lib.utc_now(),
            },
        )
        steps["submit"] = c.call("submit", {"task_id": tid, "now": lfist_lib.utc_now()})
        ov = c.call(
            "output_validate",
            {
                "task_id": tid,
                "project_dir": ".",
                "artifacts": [{"path": rel, "contains": needle, "min_chars": int(minc)}],
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
                "verify", {"task_id": tid, "verifier": assignee, "now": lfist_lib.utc_now()}
            )
        else:
            steps["result_verify"] = c.call(
                "omega_result_verify",
                {
                    "task_id": tid,
                    "reviewer": "verifier",
                    "verdict": "reject",
                    "reason": f"门禁不绿：ov={steps['output_validate']} " f"服务侧={bad}",
                    "now": lfist_lib.utc_now(),
                },
            )
            steps["verify"] = "SKIPPED（门禁不绿不得 verify）"
            failed.append({"task_id": tid, "why": steps["output_validate"], "errors": bad})
        out.append(
            {
                "task_id": tid,
                "law": law["name"],
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
            f"{tid} law={law['name']} ov={steps['output_validate']['verdict']} "
            f"verify={'ok' if ok else 'SKIP'} err={bad or 'none'}"
        )

    doc = {"leaves": out, "failed": failed, "root_task": root_task, "stage": SPEC["stage"]}
    (HERE / f"close_{SPEC['key']}.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    c.close()
    print(f"closed={len(out) - len(failed)}/{len(out)} failed={failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
