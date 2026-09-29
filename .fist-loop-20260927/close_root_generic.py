#!/usr/bin/env python3
"""通用的「8 支分支 + 根任务上卷并归档」收口驱动（与 close_stage_generic.py 共用一份 spec）。

用法：python close_root_generic.py <spec.json> <报告路径>

规则（沿用验证/打磨两轮的形状）：
 - 叶子必须已 16/16 已完成，否则拒绝上卷（不做空口上卷）；
 - 每一次调用的 `__error__` 都逐字记进 refused 并非零退出——不按 key 过滤，
   过滤就是把守卫做得比主张窄（这是本项目反复被抓到的同一类错）；
 - 根任务不带 `[omega:required]` ⇒ 根上的 claim/execute/submit/Omega 三连被拒是**既定语义**，
   仍逐字进报告，既不算通过也不算本轮的错。
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
NS = "cypy-loop-20260927"

SPEC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else None
REPORT = Path(sys.argv[2]).as_posix() if len(sys.argv) > 2 else None

_extra = [a for a in sys.argv[3:] if a.startswith("-")]
if _extra:
    # 2026-09-27 R3-寻虫：我给这驱动传了个它根本没有的 `--dry-run`，它不报错、直接跑成真实落库
    # ⇒ 未知旗标必须炸，不能静默收下（"我以为在试跑"和"已经提交"之间原本没有护栏）
    raise SystemExit(f"REFUSE — 本驱动不收旗标，收到 {_extra}；要预检请读 close 前打印的清单")
REFUSED = []


def call(c, name, args):
    r = c.call(name, args)
    if isinstance(r, dict) and "__error__" in r:
        REFUSED.append(
            {"call": name, "task_id": args.get("task_id"), "error": r["__error__"].get("message")}
        )
    return r


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
    if not SPEC or not REPORT:
        print("REFUSE — 用法：close_root_generic.py <spec.json> <报告路径>")
        return 1
    root_task, assignee = SPEC["root_task"], SPEC["assignee"]
    db = sqlite3.connect(f"file:{ROOT / 'fist-mbt.db'}?mode=ro", uri=True)
    branches = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=2 order by id",
            (NS, root_task + ".%"),
        )
    ]
    leaves_done = [
        r[0]
        for r in db.execute(
            "select id from tasks where ns=? and id like ? and depth=1 "
            "and status='已完成' order by id",
            (NS, root_task + ".%"),
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
        law, art, needle = SPEC["branches"][n - 1]
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
        call(c, "verify", {"task_id": b, "verifier": assignee, "now": lfist_lib.utc_now()})

    marker = SPEC["root_marker"]
    # 步骤形状按节点**实测状态**生成（R4-修复 交下来的流程债：上一环在根上盲发
    # claim/execute/submit，被协议层拒了 3 条 —— 根带着 [omega:required]，
    # 语料必须先于 execute 存在）
    rst = c.call("get", {"task_id": root_task})
    rstatus = rst.get("status") if isinstance(rst, dict) else None
    root_steps = [f"get={rstatus}"]
    if rstatus == "待领取":
        call(c, "claim", {"task_id": root_task, "assignee": assignee, "now": lfist_lib.utc_now()})
        root_steps.append("claim")
    omega_chain(c, root_task, SPEC["stage"] + " 收口", REPORT, marker)
    root_steps.append("omega_spec_create/spec_review")
    if rstatus in ("待领取", "拆分中", "执行中"):
        call(
            c,
            "execute",
            {
                "task_id": root_task,
                "deliverable": SPEC["root_deliverable"].replace("{REPORT}", REPORT),
                "now": lfist_lib.utc_now(),
            },
        )
        call(c, "submit", {"task_id": root_task, "now": lfist_lib.utc_now()})
        root_steps.append("execute/submit")
    arts = [{"path": REPORT, "contains": marker, "min_chars": 1500}] + [
        {"path": p, "contains": n, "min_chars": int(m)} for p, n, m in SPEC["root_extra_artifacts"]
    ]
    ov = call(
        c,
        "output_validate",
        {
            "task_id": root_task,
            "project_dir": ".",
            "artifacts": arts,
            "evidence": "报告与取件当场以文件系统核验（L4）",
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
            "task_id": root_task,
            "reviewer": "verifier",
            "verdict": "pass",
            "reason": SPEC["root_verify_reason"],
            "now": lfist_lib.utc_now(),
        },
    )
    call(c, "verify", {"task_id": root_task, "verifier": assignee, "now": lfist_lib.utc_now()})
    root = c.call("get", {"task_id": root_task})
    final = root.get("status") if isinstance(root, dict) else None
    if final == "已完成":
        call(
            c, "archive", {"task_id": root_task, "by": "human_steward", "now": lfist_lib.utc_now()}
        )
        root2 = c.call("get", {"task_id": root_task})
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
        "root_status_before": rstatus,
        "root_steps": root_steps,
        "leaves_done": len(leaves_done),
        "call_log_rows": len(rows) if isinstance(rows, list) else None,
        "call_log_tally": dict(sorted(tally.items())),
        "root_output_validate": arts,
    }
    (HERE / f"close_{SPEC['key']}_root.out.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {"root_final": final, "refused_count": len(REFUSED), "leaves_done": len(leaves_done)},
            ensure_ascii=False,
        )
    )
    for r in REFUSED:
        print("REFUSED:", json.dumps(r, ensure_ascii=False))
    return 1 if REFUSED else 0


if __name__ == "__main__":
    sys.exit(main())
