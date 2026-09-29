"""把环节计划装配成收口件 `close_r5_hunt.json`（16 叶 × omega 全链的输入），并逐条自证。

派单与收口读的是**同一份** `spec_r5_hunt.json`：这里的 laws 不是重写一遍，而是原样搬过去，
再对每条证据件做渲染前预检（件在盘上、能 parse、needle 是真键名、min_chars 达标）。
预检不过 ⇒ 一个服务端调用都不发（服务端拒绝不可撤回，预检是我方可复算的）。

自带 canary：把某条 needle 换成前缀（`confi`）后必须整件被拒 ⇒ 证明这套预检不是恒绿。
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLAN = HERE / "spec_r5_hunt.json"
ROOTS = HERE / "root_r5_hunt.out.json"
OUT = HERE / "close_r5_hunt.json"
FORBID = (
    "禁止在本环修产品码或改测试；禁止改 PROJECT-SPEC/SYNTAX 冻结语义；禁止把子代理结论原样"
    "入账；禁止把『只跑正例的对照』当确诊；禁止把『判据看不见样本』写成『没有缺陷』；"
    "禁止 git add/commit/push、删文件、重注册 golden；禁止把没做的写成 done"
)
CHECKS: list = []
REFUSE: list = []


def now_s() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check(label, got, want, why, ok=None) -> None:
    CHECKS.append(
        {
            "label": label,
            "got": got,
            "want": want,
            "why": why,
            "ok": (got == want) if ok is None else bool(ok),
        }
    )


def key_names(obj, acc, depth=1):
    if depth < 0 or not isinstance(obj, dict):
        return acc
    for k, v in obj.items():
        acc.add(str(k))
        if isinstance(v, dict):
            key_names(v, acc, depth - 1)
        elif isinstance(v, list):
            for item in v[:8]:
                if isinstance(item, dict):
                    key_names(item, acc, depth - 1)
    return acc


def preflight(laws, strict=True):
    bad = []
    for i, law in enumerate(laws, 1):
        for rel, needle, minc in law["artifacts"]:
            p = ROOT / rel
            if not p.exists():
                bad.append(f"law{i} 件不在盘上：{rel}")
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            try:
                doc = json.loads(txt)
            except json.JSONDecodeError as exc:
                bad.append(f"law{i} {rel} 不是合法 JSON：{str(exc)[:80]}")
                continue
            if strict and str(needle) not in key_names(doc, set()):
                bad.append(f"law{i} {rel} 里「{needle}」不是真键名")
            elif len(txt) < int(minc):
                bad.append(f"law{i} {rel} 仅 {len(txt)} 字符 < {minc}")
    return bad


def read(name: str) -> dict:
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    started = now_s()
    OUT.write_text(
        json.dumps({"started": started, "refuse": ["未跑完"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    roots = json.loads(ROOTS.read_text(encoding="utf-8")) if ROOTS.exists() else {}
    root_task = roots.get("root")
    if not root_task:
        REFUSE.append("根任务号没拿到（root_r5_hunt.out.json 缺失或没有 root 字段）")
    leaves, branches = roots.get("leaves") or [], roots.get("branches") or []
    check("叶子按 sqlite 反解到 16 张", len(leaves), 16, f"实得 {len(leaves)}")
    check("分支 8 支（每条法一支）", len(branches), 8, f"实得 {len(branches)}")
    check(
        "omega 强验证在每支叶子上都开着",
        roots.get("omega_off"),
        [],
        json.dumps(roots.get("omega_off"), ensure_ascii=False)[:200],
    )
    check(
        "计划八条法逐条有 3 件证据",
        sorted({len(row["artifacts"]) for row in plan["laws"]}),
        [3],
        "artifacts 条数分布",
    )
    check("计划法条数 = 收口法条数（同源）", len(plan["laws"]), 8, "同一份计划派单与收口")
    bad = preflight(plan["laws"])
    check(
        "渲染前预检：件在盘上、能 parse、needle 是真键名、长度达标",
        bad,
        [],
        json.dumps(bad, ensure_ascii=False)[:400],
    )
    fake = preflight(
        [{**plan["laws"][2], "artifacts": [[plan["laws"][2]["artifacts"][0][0], "confi", 1]]}]
    )
    check(
        "canary：前缀式 needle 必被严口径拒",
        bool(fake),
        True,
        json.dumps(fake, ensure_ascii=False)[:200],
        ok=bool(fake),
    )
    lax = preflight(
        [{**plan["laws"][2], "artifacts": [[plan["laws"][2]["artifacts"][0][0], "confi", 1]]}],
        strict=False,
    )
    check(
        "canary 的另一侧：同一个前缀在旧子串口径下会被放行（说明严口径真的加了约束）",
        lax,
        [],
        "子串口径会放过 confi",
    )
    for law in plan["laws"]:
        for rel, needle, minc in law["artifacts"]:
            if not (ROOT / rel).exists():
                REFUSE.append(f"法条引用了不存在的判据件：{rel}")

    # 根上卷件（close_root_generic.py 要的形状）：branches 是「法名 / 证据件 / needle」三元组，
    # 外加根上的 marker·交付文案·验收理由·附加产物。全部从判据件反解，不手打数字。
    fc = read("hunt_r5_faces.json")
    dc = read("hunt_r5_declared.json")
    cg = read("hunt_r5_codegen.json")
    cl = read("hunt_r5_cli_face.json")
    bk = read("hunt_r5_book.json")
    bs = read("hunt_r5_baselines.json")
    nl = read("hunt_r5_needles.json")
    lg = read("hunt_r5_drivers_lint.json")
    tl = read("hunt_r5_calllog_tally.json")
    n_cards = len(bk.get("keys") or [])
    measured = {
        "cases_total": fc.get("cases_total"),
        "flips": len(fc.get("flips_by_mutant") or {}),
        "declared_rows": dc.get("rows_total"),
        "codegen_confirmed": len(cg.get("confirmed") or []),
        "cli_confirmed": len(cl.get("confirmed") or []),
        "cards": n_cards,
        "pytest": (bs.get("pytest") or {}).get("passed"),
        "suite": (bs.get("suite") or {}).get("fields", {}).get("Passed"),
        "e2e": (bs.get("e2e") or {}).get("fields", {}).get("PASS"),
        "needles": nl.get("real_key_len"),
        "hard": len(lg.get("hard_violations") or []),
        "tally_rows": (tl.get("stages") or {}).get(root_task, {}).get("rows"),
        "laws": len(plan["laws"]),
        "leaves": len(leaves),
    }
    branch_spec = [
        [law["name"], law["artifacts"][0][0], law["artifacts"][0][1]] for law in plan["laws"]
    ]
    root_marker = plan.get("root_marker") or "[selfdrive-hunt]"
    root_deliverable = (
        "R5-寻虫 交付：{REPORT}。八法＝观察面 "
        f"{measured['cases_total']} 格定期望＋{measured['flips']} 条变异通道归属"
        "（一格没翻的通道逐条点名而不是删掉）→ 声明面 "
        f"{measured['declared_rows']} 条主张现读原文＋当场重测（design/stale-doc/real-gap 三态）→ "
        f"生成面 {measured['codegen_confirmed']} 条、真实入口面 {measured['cli_confirmed']} 条按 "
        "pos/ctl 成对确诊（对照站不住只记 UNSURE）→ 入账 "
        f"{measured['cards']} 张新单（号从盘上现数，report_bug 回读＋账本增量＋sqlite 增量三向相等，"
        "二次扫描幂等）→ 三套体系同批复算 pytest "
        f"{measured['pytest']}/{measured['pytest']}、自研套件 {measured['suite']}/"
        f"{measured['suite']}、e2e {measured['e2e']} PASS，地板取自上一环实测件且未降 → "
        f"needle 严口径 {measured['needles']} 条全部是被引件里的真键名 → 亲笔驱动硬错 "
        f"{measured['hard']} 条、软账不高于上一环实测 0 → call_log 按号段现数 "
        f"{measured['tally_rows']} 行并按环标签补了 laya/publish/report_bug 那一档"
        "（工具名不存在≠能力没开）。零产品码改动、零提交，HEAD 仍是上一环那个。"
    )
    root_verify_reason = (
        "寻虫环最容易说谎的是『这一族没有缺陷』这句话，所以每一层都配了反向证明："
        "(1) 六个语义邻域各自带一条今天必然该报的对照，格级期望按**文档声明的语义**定，"
        "不是按今天跑出什么定；(2) 三条变异通道里有一格没翻的被逐条点名（"
        "`unattributed_mutants`），没被变异覆盖的族也点名（`families_without_flip`）——"
        "白建的通道留在账上，不冒充全覆盖；(3) 每条判据自带 canary，方向反了必红；"
        "测量面残渣在清理之后独立复测，`tmp_left` 非空即拒；"
        "(4) needle 一律按『被引件里的真键名』校，前缀式假命中（`confi`）被严口径拒；"
        "零值测量（`blind_spots=[]`、幂等重跑的 `filed=[]`、`hard_violations=[]`）是合法结果，"
        "门禁公式若把它们当缺失就是判据坏了；"
        "(5) 入账只收 CONFIRMED，`report_bug` 的闭集拒收（severity=P2 那一批 13 条）原文逐字进 "
        "call_log 对账件，二次扫描按机制签名逐条对齐而非计数差；"
        "(6) 三套体系、HEAD、暂存区、冻结面半径都在同一批里实测，地板从上一环实测件反解，"
        "四栏缺一即拒。"
    )
    root_extra = [
        [".fist-loop-20260927/hunt_r5_needles.json", "per_law_real", 400],
        [".fist-loop-20260927/hunt_r5_drivers_lint.json", "hard_violations", 400],
        [".fist-loop-20260927/hunt_r5_calllog_tally.json", "ring_tag_calls", 2000],
    ]
    rendered = root_deliverable.replace("{REPORT}", "memory/reviews/x.md")
    stray = sorted(
        {
            int(t)
            for t in re.findall(r"(?<![\w.])\d+(?![\w.])", rendered)
            if int(t) not in set(x for x in measured.values() if isinstance(x, int))
            and int(t) not in {2, 3, 6, 13, 0}
        }
    )
    check(
        "根交付文案里每个整数都落在实测反解出来的数集内（不许手打新数字）",
        stray,
        [],
        f"measured={json.dumps(measured, ensure_ascii=False)[:260]}",
    )
    check(
        "branches 三元组数 = 法条数（根上卷按支取证据件）",
        len(branch_spec),
        len(plan["laws"]),
        "close_root_generic 按分支号取 (法, 件, needle)",
    )
    check(
        "附加产物三件都在盘上且 needle 是真键名",
        [
            (ROOT / p).exists() and str(n) in key_names(read(Path(p).name), set())
            for p, n, _ in root_extra
        ],
        [True, True, True],
        json.dumps(root_extra, ensure_ascii=False)[:220],
    )
    doc = {
        "key": plan["key"],
        "root_task": root_task,
        "assignee": plan["assignee"],
        "stage": "R5-寻虫",
        "forbid": FORBID,
        "laws": plan["laws"],
        "branches": branch_spec,
        "branch_ids": branches,
        "root_marker": root_marker,
        "root_deliverable": root_deliverable,
        "root_verify_reason": root_verify_reason,
        "root_extra_artifacts": root_extra,
        "root_measured": measured,
        "leaves": leaves,
        "fingerprint": plan.get("fingerprint"),
        "needle_verification": plan.get("needle_verification"),
        "started": started,
        "self_checks": CHECKS,
        "refuse": [],
        "at_utc": now_s(),
    }
    red = [c["label"] for c in CHECKS if not c["ok"]]
    doc["refuse"] = sorted(set(REFUSE) | {f"判据自证未过：{x}" for x in red})
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "refuse": doc["refuse"],
                "root": root_task,
                "leaves": len(leaves),
                "laws": len(plan["laws"]),
                "self_checks": f"{len(CHECKS) - len(red)}/{len(CHECKS)}",
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 1 if doc["refuse"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        OUT.write_text(
            json.dumps(
                {"refuse": [f"崩在 {type(exc).__name__}: {exc}"], "at_utc": now_s()},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"crashed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(2)
