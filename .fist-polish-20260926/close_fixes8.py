#!/usr/bin/env python3
"""Close the two commander-ruling tickets (BUG-13 / BUG-14) that pass 7 landed after intake.

Task ids are reverse-parsed from the earlier passes' own intake maps (intake_map5/6.json), never
hand-copied -- a past pass hand-wrote a mapping and then reported the disagreement as a ledger
defect. Both tickets were already `claim`ed this pass (the ruling arrived after the pass-7
closure run), so this script only walks execute -> submit -> verify and records the pre-existing
status from `get` so the reply text proves the ticket really sat at 已领取.

Every deliverable cites evidence files that must exist right now; a missing one is a REFUSE, not
a softer sentence.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfist import Client  # noqa: E402

SWEEP = os.environ.get("SWEEP", "pytest_final_sweep11.log")


def need(name: str) -> str:
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        raise SystemExit(f"REFUSE: 缺证据件 {name}，该单的交付文案不能引用不存在的东西")
    return p


def task_id_from(mapfile: str, bug: str) -> str:
    path = need(mapfile)
    data = json.load(open(path, encoding="utf-8"))
    rows = data["mapping"] if isinstance(data, dict) and "mapping" in data else data
    hits = [r.get("task_id") for r in rows if r.get("bug_id") == bug and r.get("task_id")]
    if len(hits) != 1:
        raise SystemExit(f"REFUSE: {mapfile} 里 {bug} 的 task_id 不唯一: {hits}")
    return hits[0]


def gold_counts() -> tuple[int, int]:
    data = json.load(open(need("golden_float_diff.json"), encoding="utf-8"))
    return len(data.get("changed") or []), len(data.get("rows") or [])


def lock_reds(bug: str) -> list[str]:
    data = json.load(open(need("lockproof_pass7.json"), encoding="utf-8"))
    for row in data["rows"]:
        if row["bug"] == bug:
            return row["red_on_prefix_code"]
    raise SystemExit(f"REFUSE: lockproof_pass7.json 里没有 {bug} 这一单，裁决项的锁未在回退树上证红")


def locks_of(bug: str) -> list[str]:
    num = bug.split("-")[1]
    src = open(os.path.join(os.path.dirname(HERE), "tests", "test_polish_20260926_pass7.py"),
               encoding="utf-8").read()
    names = re.findall(r"(?m)^def (test_bug%s_\w+)" % num, src)
    if not names:
        raise SystemExit(f"REFUSE: 测试文件里反解不到 {bug} 的锁死回归")
    return names


def main() -> int:
    need(SWEEP)
    need("meas_digest_after.out.txt")
    need("e2e_golden_reregister_float.log")
    tail = open(os.path.join(HERE, SWEEP), encoding="utf-8", errors="replace").read()
    tail = tail.strip().splitlines()[-1]
    if "failed" in tail or "error" in tail:
        raise SystemExit(f"REFUSE: 终态全量不绿，不能闭环裁决单: {tail!r}")

    plan = {
        "BUG-13": (
            task_id_from("intake_map5.json", "BUG-13"),
            "指挥官裁决（2026-09-26）：摘要代价改用 time.process_time() 判，阈值量级不动。"
            f"改动文件（本单全部）: tests/test_incremental.py 的 TestDigestCost 两处摘要计时（"
            f"digest_elapsed 与 scales_linearly 的 small/large 三处取值），`< 2.0`、`< small*12+0.5` 原样保留；"
            f"判据前后对照: .fist-polish-20260926/meas_digest_cost.out.txt（入账时的墙钟/CPU 分离测量，"
            f"同一夹具 wall/cpu 比 1.26–1.74）+ meas_digest_after.out.txt（改后同一夹具重跑，"
            f"两条判据各自的 verdict 由脚本从测试源反读阈值算出）；"
            f"锁死回归: {'; '.join('tests/test_polish_20260926_pass7.py::' + t for t in locks_of('BUG-13'))}"
            f"（第二条是对照：parse/compare 时限不许被顺手放宽）；"
            f"回退树证红: lockproof_pass7.json BUG-13 -> {', '.join(lock_reds('BUG-13')) or '（无红，假锁）'}；"
            f"基线不回落证据: .fist-polish-20260926/{SWEEP}（全量，末行 `{tail}`）。"
            "零付费 API：裁决由指挥官给出，落地与测量均本机完成。"),
        "BUG-14": (
            task_id_from("intake_map6.json", "BUG-14"),
            "指挥官裁决（2026-09-26）：float 跟随 Python 双精度。"
            "改动文件（本单全部）: cypyc/codegen/type_mapper.py 的 cypy_to_cython[\"float\"] -> \"double\""
            "（与 cypy_to_c 一致，同一个声明类型不再在一次产物里两种宽度）；"
            "SYNTAX/01-basic-types.md 的「单精度浮点数」措辞随裁决下修；"
            f"端到端基准重注册: examples/*.out 共 {gold_counts()[1]} 份参与对照、{gold_counts()[0]} 份内容变化"
            "（重注册前整体快照在 .fist-polish-20260926/golden_before_float/，逐行差在 golden_float_diff.json，"
            "只允许浮点末位变化——该约束是 gen_report7.py 里 _digits_only() 的硬门）；"
            f"锁死回归: {'; '.join('tests/test_polish_20260926_pass7.py::' + t for t in locks_of('BUG-14'))}"
            "（第二条用真语料 examples/subtype_units.cypy 断言转译后无 <float>）；"
            f"回退树证红: lockproof_pass7.json BUG-14 -> {', '.join(lock_reds('BUG-14')) or '（无红，假锁）'}；"
            f"基线不回落证据: .fist-polish-20260926/e2e_golden_reregister_float.log + {SWEEP}（全量）。"
            "零付费 API。"),
    }
    plan["BUG-32"] = (
        task_id_from("intake_map10.json", "BUG-32"),
        "本轮终态全量实跑抓出来的裁决副作用（不是读码新发现）：`type_mapper` 统一后，"
        "cypyc/codegen/cython_generator.py 的 `_visit_ConstraintDef` 把约束成员名过了一遍映射，"
        "产物注释写成 `# constraint Numeric = int | double`，而源码声明的是 `int | float` —— "
        "违反 SYNTAX/33 §5「约束只发一条注释」与该注释应为声明逐字回显的口径（C-4.1 亦以它为唯一差异行）。"
        "改动文件（本单全部）: cypyc/codegen/cython_generator.py 的约束成员渲染（新增 "
        "`_constraint_member_name()`：标量取声明原名逐字回显，subtype/type 成员仍递归化成基类型"
        "**名字**（Meter→float），复合形态才退回 `_type_to_str`）；同函数之外未动，`# type alias:`（:3320）与 `ctypedef` "
        "那两处**故意保留**走映射（别名是真声明，必须吃到裁决宽度，由对照锁钉住）。"
        "红证据: .fist-polish-20260926/pytest_final_sweep9.log 里 test_named_constraints.py 的三条失败原文；"
        "修复第一版（一律逐字回显）被下一次全量 pytest_final_sweep10.log 按 S-4.1 打回 1 条红"
        "（test_example_artifact_mentions_no_subtype_name），收窄为「标量逐字回显 + subtype/type 化成基类型名」后才全绿；"
        f"锁死回归: {'; '.join('tests/test_polish_20260926_pass7.py::' + t for t in locks_of('BUG-32'))}；"
        f"回退树证红: lockproof_pass7.json BUG-32 -> {', '.join(lock_reds('BUG-32')) or '（无红，假锁）'}；"
        f"基线不回落证据: .fist-polish-20260926/{SWEEP}（全量，末行 `{tail}`）。零付费 API。")

    for bug, (_tid, text) in plan.items():
        if "（无红，假锁）" in text:
            raise SystemExit(f"REFUSE: {bug} 的回归在回退树上没转红")

    log = []
    c = Client(timeout=180)
    c._send("initialize", {"protocolVersion": "2026-07-28", "capabilities": {},
                           "clientInfo": {"name": "cypy-polish-close8", "version": "1"}})
    for bug, (tid, deliverable) in plan.items():
        before = c.call("get", {"task_id": tid})
        pre_status = before.get("status") if isinstance(before, dict) else None
        steps = [{"tool": "get(before)", "ok": pre_status is not None, "reply": str(before)[:300]}]
        walk = [("execute", {"task_id": tid, "deliverable": deliverable}),
                ("submit", {"task_id": tid}),
                ("verify", {"task_id": tid, "verifier": "cypy-polisher"})]
        if pre_status == "待领取":          # BUG-32 是本轮新入账的单，先领再交
            walk.insert(0, ("claim", {"task_id": tid, "assignee": "cypy-polisher"}))
        for tool, args in walk:
            out = c.call(tool, args)          # pfist stamps a real `now` per write call
            ok = isinstance(out, dict) and "__error__" not in out
            steps.append({"tool": tool, "ok": ok, "reply": str(out)[:300]})
            if not ok:
                break
        green = all(s["ok"] for s in steps)
        log.append({"bug": bug, "task_id": tid, "status_before": pre_status,
                    "steps": steps, "green": green})
        print(f"{bug:8s} {tid:7s} before={pre_status} "
              + " ".join(f"{s['tool']}={'ok' if s['ok'] else 'RED'}" for s in steps))
        for s in steps:
            if not s["ok"]:
                print(f"    ! {s['tool']} 原始回复: {s['reply']}")
    c.close()
    json.dump(log, open(os.path.join(HERE, "close_fixes8.out.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    greens = [r["bug"] for r in log if r["green"]]
    print(f"closed_green={len(greens)}/{len(plan)} -> {greens}")
    return 0 if len(greens) == len(plan) else 1


if __name__ == "__main__":
    sys.exit(main())
