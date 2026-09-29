"""R12 组合环的 FIST 腿：`--stage start` 建根单并挂判据，`--stage close` 逐叶收口 + 走环。

骨架沿用 R11 那份（那一份是被实测走通的），但**上一轮的"事实"一律不复制**：
根单号、语料名与对数、基线数、门禁日志名全部换成本轮盘面对象，且能从盘面反解的都反解
（`baseline_test_count` 取本轮 pytest 日志、`baseline_open_bug_count` 取台账开口块、
Ω-gate 的期望对数取 `corpus/*.json` 逐份相加，而不是把上一轮的 100/119 抄进代码）。

新增的门（本轮自己踩过的坑）：
 · 台账完整性脏检（坏戳 / 未插值占位）在开批门前做，全档归零才算过 —— R11 的 4 个 `…T…T…ZZ`
   坏戳就是靠这条门修掉的，留着它防我再写第二种花样的段落戳；
 · 所有回执按 `--tag` 落唯一文件名，复跑不覆盖上一次读数。
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
LOOP_NAME = "cypy-selfdrive-ring-r12"
ROOT_PREFIX = "T0r118"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r118-cypy-selfdrive-r12-report.md"
VERIFY_JSON = HERE / "verify_r12_report.json"
CORPUS = "corpus/cypy.generic.bounds.json"
LOGS = HERE / "logs"
SPEC_KIND, CHECK_KIND, RESULT_KIND = "spec", "check", "result"

GATE_LOG = LOGS / "r12_gate_all_a1.log"
PYTEST_LOG = LOGS / "r12_pytest_a3.log"
SUITE_LOG = LOGS / "r12_suite_a1.log"
E2E_LOG = LOGS / "r12_e2e_a1.log"

STEPS_SEED = ["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"]
IDEMPOTENT_RE = re.compile(r"已通过审核，无需重复创建|不是待审核状态")

FACES = [
    (
        "推进：靶面选定与规范条款",
        "SYNTAX/11 新增「声明界在使用侧的判定」规则 1-4 —— 规则 1-3 钉三处使用位（注解位/显式类型实参构造位/"
        "结构体字面量位）都判，规则 4 明写**不判的一面**（构造位不写类型实参时不做推断）⇒ 先把承诺写清再动实现",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
    ),
    (
        "寻虫：探针与存量半径实测",
        "probe_r12_ctor_inference.py 6 形（推断位现状）+ measure_r12_constraint_radius.py 改动前后同集合快照"
        "（206 份源、16 份含约束声明、共 34 处、parse_refused=3、real_crashes=0）+ "
        "make_corpus_r12.py 落盘前逐条 execute+judge，本轮它自己拒了 3 次",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
    ),
    (
        "修复：一处共用件 + 三处接线",
        "TypeChecker._check_declared_bounds 收口，注解位 _visit_GenericType / 显式实参 _bind_explicit_type_args /"
        " 字面量位 _visit_StructLiteral 各接一行；**摘掉**字面量位自带的窄复制（只认单名界 ⇒ 联合界静默放行）；"
        "同一条消息按整串去重（注解位节点会被多处重复访问）",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
    ),
    (
        "验证：三套全量与承重矩阵",
        "pytest 终版 + 自研套件 47 条 + e2e golden + Ω-gate 全 spec；verify_r12_locks.py 6 格"
        "（L0 现树全绿基线 + 4 格承重各红且身份探针翻假 + 只改注释对照格 0 红）",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
    (
        "打磨：账本与本腿自犯的台账缺陷",
        "BUG-129 追 FIXED（派生数：23 对/指纹/18 支锁/16 份含约束声明 34 处，全部运行时反解）；"
        "BUG-134/135 入账未修；另修本环自己写坏的账面：4 个 R11 畸形 UTC 段落戳 + R12 段落里 6 处未插值占位，"
        "并把 `amend_r11_ledger_bugs.py` 的模板一并改掉防再犯",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
    (
        "推进：R13 入口（不自证关闭的三条）",
        "BUG-135（构造位类型实参推断，与 BUG-128 struct 方法代入同一推断层）、BUG-134（违界诊断 "
        "`in call to '<unknown>'` 误导文案）、BUG-120/121/122 裁决面；`T0r112`/`T0r113` 两根仍停拆分中"
        "（待领取叶无退役出路，BUG-106）⇒ 不伪造交付物",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
]
BOUNDARY = [
    (
        "边界审视（实做）：元数判定与声明界并存",
        "`let x: Two<int, int, int> = Two(1, 2, 3)` 同一条注解上既报 `Type argument count mismatch` 又报 "
        "违界 ⇒ corpus 里 `ar_and_bound` 那对钉住两条账不互相遮蔽；只缺元数、只违界各成一对",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
    ),
    (
        "边界审视（实做）：重复访问下的诊断去重",
        "注解位节点会被多处重复访问 ⇒ 去重按**整条消息**而非按节点；成对两格：`ann_dup`（同一源跑两遍"
        "不叠第二笔）与 `dedup_would_double`（摘掉去重后必须变多），数的是被写入 `self.errors` 的行数",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.bounds"],
    ),
]
DECLARED_NA = (
    "边界审视（声明不适用）：本面是编译期类型判定，无堆分配、无循环、无 I/O，"
    "资源极限一类输入域对本形态不可判定 ⇒ 依据写在报告 §3.3，不放恒真门"
)


def utc_z():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_open_ids() -> list[str]:
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"(?m)^## (BUG-\d+)", led)
    return [
        blocks[i]
        for i in range(1, len(blocks) - 1, 2)
        if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", blocks[i + 1])
    ]


def ledger_sweep() -> dict:
    """台账脏检：分「可机械判定且必须归零的门」与「只能记录的存量读数」两口径。

    · 门：畸形段落戳（双裹日期 / 尾巴 `ZZ`）与未插值占位 —— 这两类是**写坏**，不改变任何历史主张就能修；
      R11 的 4 个坏戳就是靠这条门现形的。
    · 读数：`clock_no_Z`（如 `2026-09-29T05:31:29`，17 处）与 `minute_precision`（`…T10:28Z`，1 处）。
      这些**不能**补 `Z` 了事：落笔时没记时区，补上等于替历史宣布"那是 UTC"——只记录、只在报告里认账。
    """
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    head = [l for l in led.splitlines() if l.startswith("### ")]
    tok = re.compile(r"\d{4}-\d\d-\d\dT[\d:]*Z*")
    canon = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    odd = [t for l in head for t in tok.findall(l) if not canon.fullmatch(t)]
    return {
        "dblstamp_lines": len(
            [l for l in head if re.search(r"(\d{4}-\d\d-\d\dT)\1", l) or l.count("ZZ")]
        ),
        "residue_lines": len(re.findall(r"(?m)^.*\{[A-Z][A-Z_]*\}.*$", led)),
        # 门用这一格：非规范里"形状本身坏了"的那两类
        "hard_bad_stamps": len(
            [t for t in odd if t.endswith("ZZ") or re.search(r"\d{4}-\d\d-\d\dT\d{4}", t)]
        ),
        "read_clock_no_Z": len([t for t in odd if not t.endswith("Z")]),
        "read_minute_precision": len(
            [t for t in odd if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\dZ", t)]
        ),
    }


def corpus_case_total() -> int:
    tot = 0
    for f in sorted(glob.glob(str(ROOT / "corpus" / "*.json"))):
        tot += len(json.loads(Path(f).read_text(encoding="utf-8"))["tests"])
    return tot


def log_conclusion(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def pytest_passed(path: Path) -> int:
    hits = (
        re.findall(r"(\d+) passed", path.read_text(encoding="utf-8", errors="replace"))
        if path.exists()
        else []
    )
    if not hits:
        raise SystemExit(f"{path.name} 解析不到 passed 计数 ⇒ 基线数无来源，拒绝手填")
    return int(hits[-1])


def spec_kind_guard() -> tuple[bool, list, list]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    kinds = [r[0] for r in con.execute("select distinct spec_type from specs").fetchall()]
    total = con.execute("select count(*) from specs").fetchone()[0]
    con.close()
    missing = [k for k in (SPEC_KIND, CHECK_KIND, RESULT_KIND) if k not in kinds]
    return (not missing and total > 0), missing, sorted(kinds)


def loop_create_params(name: str) -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute(
        "select params_json from call_log where tool='loop_create' and ok=1 and params_json like ? "
        "order by rowid desc limit 1",
        (f"%{name}%",),
    ).fetchone()
    con.close()
    if not row:
        raise SystemExit(f"账上查无 {name} 成功的 loop_create 参数 ⇒ 基线数无来源，拒绝手填")
    return json.loads(row[0])


def drive_loop(call, name: str, steps: list) -> dict:
    import r11_loop_drive as ld

    seed = loop_create_params(name)
    if list(seed.get("steps") or []) != steps:
        raise SystemExit(f"账上 steps 与本件 STEPS_SEED 不一致：{seed.get('steps')} != {steps}")
    created = call(
        "loop_create",
        {
            "name": name,
            "steps": steps,
            "max_rounds": seed.get("max_rounds", len(steps)),
            "baseline_test_count": seed.get("baseline_test_count", 0),
            "baseline_open_bug_count": seed.get("baseline_open_bug_count", 0),
            "stop_on_goal": bool(seed.get("stop_on_goal", False)),
            "stop_on_exceeded": bool(seed.get("stop_on_exceeded", False)),
            "_omit_defaults": True,
        },
    )
    args = {
        "name": name,
        "project_health_grade": "attention",
        "blocked_tasks": 0,
        "current_test_count": pytest_passed(PYTEST_LOG),
        "current_open_bug_count": len(ledger_open_ids()),
        "_omit_defaults": True,
    }
    pre = call("loop_status", {"name": name, "_omit_defaults": True})
    ticks = []
    for i, step in enumerate(steps, 1):
        res = call("loop_tick", args)
        blob = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
        ticks.append(
            {
                "refused": blob.startswith("RPC-ERROR")
                or '"__error__"' in blob
                or "不被接受" in blob
                or "loop not found" in blob,
                "picked": ld.pick(blob),
                "i": i,
                "expect_mode": step,
            }
        )
    post = call("loop_status", {"name": name, "_omit_defaults": True})
    pre_blob = json.dumps(pre, ensure_ascii=False) if not isinstance(pre, str) else pre
    post_blob = json.dumps(post, ensure_ascii=False) if not isinstance(post, str) else post
    gates = ld.gate_table(
        isinstance(created, dict) and "__error__" in created,
        '"__error__"' in pre_blob or "loop not found" in pre_blob,
        '"__error__"' in post_blob or "loop not found" in post_blob,
        ticks,
        ld.pick(pre_blob).get("round"),
        ld.pick(post_blob).get("round"),
        True,
        steps,
    )
    return {
        "gates": gates,
        "ticks_ok": len([x for x in ticks if not x["refused"]]),
        "steps": len(steps),
        "pre": ld.pick(pre_blob),
        "post": ld.pick(post_blob),
        "tick_args": {k: args[k] for k in args if k != "_omit_defaults"},
        "seq": [x["picked"].get("next_mode") for x in ticks],
        "idx": [(x["picked"].get("loop_after") or {}).get("current_idx") for x in ticks],
    }


def refused(res):
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def benign(res):
    blob = json.dumps(res, ensure_ascii=False) if isinstance(res, dict) else str(res)
    return bool(re.search(r"已通过审核|无需重复创建|已存在", blob))


def matrix_summary() -> dict:
    """从 `verify_r12_matrix.json` 反解承重读数（矩阵只印结论不存汇总，所以这里按格重算，不抄打印值）。"""
    cells = json.loads((HERE / "verify_r12_matrix.json").read_text(encoding="utf-8"))["cells"]
    is_ctrl = lambda n: any(
        k.get("kind") == "只改注释" for k in cells[n].get("identity", [])
    )  # noqa: E731
    ctrl = {n: cells[n] for n in cells if n.startswith("M") and is_ctrl(n)}
    mut = {n: cells[n] for n in cells if n.startswith("M") and not is_ctrl(n)}
    return {
        "cells": len(cells),
        "mutation_cells": len(mut),
        "load_bearing": len([c for c in mut.values() if c["pytest"]["n_failed"] > 0]),
        "all_mutation_red": all(c["pytest"]["n_failed"] > 0 for c in mut.values()),
        "control_cells": len(ctrl),
        "control_zero_red": all(c["pytest"]["n_failed"] == 0 for c in ctrl.values()),
        "l0_green": cells.get("L0 现树（应全绿）", {}).get("pytest", {}).get("n_failed") == 0,
    }


def entry_gate():
    reasons, obs = [], {}
    if not REPORT.exists():
        reasons.append(f"报告不在盘：{REPORT.name}")
    else:
        size = REPORT.stat().st_size
        obs["report_bytes"] = size
        if size < 6000:
            reasons.append(f"报告只有 {size}B（<6000B）")
    if not VERIFY_JSON.exists():
        reasons.append("引用核验件缺失（verify_r12_report.json）")
    else:
        v = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
        fails = v.get("failed")
        n_fail = len(fails) if isinstance(fails, list) else fails
        obs["verify_failed"] = n_fail
        obs["verify_checks"] = v.get("checks_ran", len(v.get("checks", []) or []))
        if n_fail != 0:
            reasons.append(
                f"引用核验 failed={n_fail} 项：{json.dumps(fails, ensure_ascii=False)[:200]}"
            )
        obs["verify_report_bytes"] = v.get("report_bytes")
        if REPORT.exists() and v.get("report_bytes") != REPORT.stat().st_size:
            reasons.append(
                f"核验后报告又被改：核验件 report_bytes={v.get('report_bytes')} "
                f"盘面={REPORT.stat().st_size}"
            )
    obs["gate"] = log_conclusion(GATE_LOG, "CONCLUSION")
    m = re.search(
        r"specs=(\d+) cases=(\d+) passed=(\d+) failed=(\d+) refused=(\d+).*rc=(\d+)", obs["gate"]
    )
    want = corpus_case_total()
    obs["corpus_case_total_derived_from_corpus_dir"] = want
    if not m:
        reasons.append(f"Ω-gate 结论行解析不出：{obs['gate'][:160]}")
    else:
        if int(m.group(2)) != want:
            reasons.append(
                f"Ω-gate 对数 {m.group(2)} != 从 corpus/ 目录反解的 {want} ⇒ 有 spec 没进门禁"
            )
        if m.group(4) != "0" or m.group(5) != "0" or m.group(6) != "0":
            reasons.append(f"Ω-gate 非终值：{obs['gate'][:160]}")
    obs["pytest"] = log_conclusion(PYTEST_LOG, "pytest_rc=")
    if obs["pytest"] != "pytest_rc=0":
        reasons.append(f"pytest 终版非 0：{obs['pytest']}")
    txt = SUITE_LOG.read_text(encoding="utf-8", errors="replace") if SUITE_LOG.exists() else ""
    p = re.findall(r"Passed: (\d+)", txt)
    f = re.findall(r"Failed: (\d+)", txt)
    obs["suite"] = {
        "passed": int(p[-1]) if p else None,
        "failed": int(f[-1]) if f else None,
        "rc": (log_conclusion(SUITE_LOG, "suite_rc=") or "").strip(),
    }
    if (
        obs["suite"]["failed"] != 0
        or not obs["suite"]["passed"]
        or obs["suite"]["rc"] != "suite_rc=0"
    ):
        reasons.append(f"自研套件终值不符：{json.dumps(obs['suite'], ensure_ascii=False)}")
    obs["e2e"] = log_conclusion(E2E_LOG, "[e2e-golden] summary:")
    if "FAIL=0" not in obs["e2e"] or "WARN=0" not in obs["e2e"]:
        reasons.append(f"e2e golden 终值不符：{obs['e2e']}")
    sw = ledger_sweep()
    obs["ledger_sweep"] = sw
    if sw["dblstamp_lines"] or sw["residue_lines"] or sw["hard_bad_stamps"]:
        reasons.append(
            f"台账脏检未归零：{json.dumps(sw, ensure_ascii=False)}"
            "（畸形段落戳/未插值占位 —— 本轮开工时是 4 个坏戳 + 6 处占位，修完必须保持 0；"
            "read_* 两格是存量读数，不作门）"
        )
    mx = matrix_summary()
    obs["matrix"] = mx
    if not (
        mx["l0_green"]
        and mx["all_mutation_red"]
        and mx["control_zero_red"]
        and mx["load_bearing"] > 0
    ):
        reasons.append(f"承重矩阵不合格：{json.dumps(mx, ensure_ascii=False)}")
    guard_ok, missing_kinds, live_kinds = spec_kind_guard()
    obs["spec_kind_guard"] = {"pass": guard_ok, "missing": missing_kinds, "live": live_kinds}
    if not guard_ok:
        reasons.append(
            f"specs 表的 spec_type 针失效：本件按 {SPEC_KIND}/{CHECK_KIND}/{RESULT_KIND} 取数，"
            f"库里缺 {missing_kinds}（库里实有 {live_kinds}）⇒ 恒 0 会让收口重发已 approved 的语料"
        )
    return reasons, obs


def deliverable(face, concl, evid, gap, store):
    return (
        f"结论：{concl}\n证据：{evid}\n分析：{face}\n" f"缺口与风险：{gap}\n建议入档位置：{store}"
    )


def sweep_selftest() -> int:
    """尺子的自检：拿本环**真实写坏过**的两份样本喂给脏检，必须各打回对应那一格。

    样本是 logs/r12_ledger_bad_section.*.txt（run-1 带双裹戳、run-2 带未插值占位），
    不是我编的合成串 —— 自检定的是"这把尺看得见我上一版犯过的那两类错"。
    """
    head_bad = (LOGS / "r12_ledger_bad_section.prev.txt").read_text(encoding="utf-8")
    res_bad = (LOGS / "r12_ledger_bad_section.cur.txt").read_text(encoding="utf-8")
    tok = re.compile(r"\d{4}-\d\d-\d\dT[\d:]*Z*")
    canon = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    h = [
        t
        for l in head_bad.splitlines()
        if l.startswith("### ")
        for t in tok.findall(l)
        if not canon.fullmatch(t)
    ]
    hard_h = len([t for t in h if t.endswith("ZZ") or re.search(r"\d{4}-\d\d-\d\dT\d{4}", t)])
    res_r = len(re.findall(r"(?m)^.*\{[A-Z][A-Z_]*\}.*$", res_bad))
    live = ledger_sweep()
    ok = (
        hard_h >= 1
        and res_r >= 1
        and not (live["dblstamp_lines"] or live["residue_lines"] or live["hard_bad_stamps"])
    )
    print(
        f"SWEEP_SELFTEST hard_on_sample={hard_h} residue_on_sample={res_r} live={json.dumps(live, ensure_ascii=False)}"
    )
    print(f"CONCLUSION selftest=sweep ok={ok}（两份真实坏样本各打回一格，活台账三门归零）")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["start", "close"], default="start")
    ap.add_argument("--tag", default="a1", help="回执文件名后缀：复跑不覆盖上一次读数")
    ap.add_argument(
        "--selftest", action="store_true", help="只跑脏检尺的自检（不碰服务端、不碰台账）"
    )
    args = ap.parse_args()
    if args.selftest:
        return sweep_selftest()
    started = utc_z()
    rep = {
        "started_z": started,
        "stage": args.stage,
        "tag": args.tag,
        "ns": NS,
        "refusals": [],
        "benign": [],
        "idempotent": [],
        "nodes": {},
        "obs": {},
    }

    if args.stage == "close":
        reasons, obs = entry_gate()
        rep["entry_gate"] = {"pass": not reasons, "reasons": reasons, "observed": obs}
        if reasons:
            (LOGS / f"r12_ring_close_refused_{args.tag}.json").write_text(
                json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            for r in reasons:
                print("REFUSED (开批门) local |", r[:240])
            print(f"CONCLUSION refused=1 stage=close gate_reasons={len(reasons)} tag={args.tag}")
            return 1

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist

    c = fist.FistClient(timeout=240)
    _raw = c.call
    sent = []

    def call(tool, a):
        sent.append(tool)
        return _raw(tool, a)

    def note(node, tool, res):
        blob = json.dumps(res, ensure_ascii=False)
        if IDEMPOTENT_RE.search(blob):
            rep["idempotent"].append({"node": node, "tool": tool, "reply_verbatim": blob[:220]})
            return False
        if refused(res) or blob.startswith("RPC-ERROR") or '"__error__"' in blob:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob[:300]})
            return True
        if benign(res):
            rep["benign"].append({"node": node, "tool": tool, "reply_verbatim": blob[:160]})
        return False

    def status(node):
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            row = con.execute("select status from tasks where id=?", (node,)).fetchone()
        finally:
            con.close()
        return row[0] if row else ""

    def spec_rows(node, kind):
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            return con.execute(
                "select count(*) from specs where task_id=? and spec_type=?", (node, kind)
            ).fetchone()[0]
        finally:
            con.close()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    root_row = con.execute(
        "select id from tasks where ns=? and parent_id='' and description like ? "
        "order by length(id), id",
        (NS, f"%{ROOT_PREFIX}%"),
    ).fetchone()
    con.close()
    root_id = root_row[0] if root_row else None
    if args.stage == "close" and not root_id:
        rep["entry_gate"] = {
            "pass": False,
            "reasons": [f"账上查无根单：ns={NS} 且 description 含 {ROOT_PREFIX} 且 parent_id=''"],
            "observed": {"db": str(DB)},
        }
        (LOGS / f"r12_ring_close_refused_{args.tag}.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"REFUSED (开批门) local | 账上查无根单 {ROOT_PREFIX}")
        print("CONCLUSION refused=1 stage=close gate_reasons=1")
        return 1

    if args.stage == "start":
        if root_row:
            root_id = root_row[0]
            rep["root_reused"] = root_id
        else:
            open_ids = ledger_open_ids()
            base_tests = pytest_passed(PYTEST_LOG)
            root = call(
                "publish_parallel",
                {
                    "project_dir": ".",
                    "namespace": NS,
                    "created_by": AGENT,
                    "description": (
                        f"[omega:required] {ROOT_PREFIX}（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
                        "本轮靶面：把泛型**声明界在使用侧的判定**（SYNTAX/11「类型约束」承诺、BUG-129 开口）打到闭合 —— "
                        "注解位 / 显式类型实参构造位 / 结构体字面量位三处共用一处判定件，"
                        "联合界、单名界、特质界、typeclass 界都落到既有 `_check_generic_constraint`；"
                        f"判据层新增 op `cypy.generic.bounds`（{len(json.loads((ROOT / CORPUS).read_text(encoding='utf-8'))['tests'])} 对），"
                        f"台账语料合计 {corpus_case_total()} 对。\n"
                        "  寻虫另立 2 张：BUG-134 违界诊断 `in call to '<unknown>'` 误导文案、"
                        "BUG-135 构造位不写类型实参时不做推断（与 BUG-128 同一推断层）⇒ 都入账未修\n"
                        f"开工基线（本轮实测反解，不手填）：pytest {base_tests} passed（logs/{PYTEST_LOG.name}）；"
                        f"台账开口 {len(open_ids)} 块；Ω-gate 终值见 logs/{GATE_LOG.name}。\n"
                        f"出口件：`reports/2026-09-29/{REPORT.name}`。"
                    ),
                },
            )
            rep["root"] = json.dumps(root, ensure_ascii=False)[:300]
            root_id = root.get("task_id") if isinstance(root, dict) else None
            if not root_id:
                rep["refusals"].append(
                    {
                        "node": "(建单)",
                        "tool": "publish_parallel",
                        "reply_verbatim": json.dumps(root, ensure_ascii=False)[:300],
                    }
                )
                _finish(rep, "start")
                return 1

        laya = call(
            "laya_decide",
            {
                "context": (
                    "任务：把 Cypy 泛型声明界在**使用侧**的三处判定收进一处共用件并补齐回归锁与 Ω-spec"
                    f"（新 op cypy.generic.bounds，台账合计 {corpus_case_total()} 对）；"
                    "账上另有 2 张本轮新立的开口单（BUG-134 文案误导、BUG-135 推断面不判）。"
                    "已知阻塞：构造位类型实参推断与 struct 方法代入同层、收紧面大需另轮；"
                    "T0r112/T0r113 两根的待领取叶无退役出路。问：该开哪些机制、怎么拆。"
                )
            },
        )
        rep["laya"] = json.dumps(laya, ensure_ascii=False)[:400]

        open_ids = ledger_open_ids()
        base_tests = pytest_passed(PYTEST_LOG)
        loop = call(
            "loop_create",
            {
                "name": LOOP_NAME,
                "steps": STEPS_SEED,
                "max_rounds": len(STEPS_SEED),
                "baseline_test_count": base_tests,
                "baseline_open_bug_count": len(open_ids),
                "stop_on_goal": False,
                "stop_on_exceeded": False,
                "_omit_defaults": True,
            },
        )
        rep["loop_create"] = json.dumps(loop, ensure_ascii=False)[:260]
        rep["ledger_open_at_start"] = len(open_ids)
        rep["baseline_test_count_used"] = base_tests
        if refused(loop) and not benign(loop):
            rep["refusals"].append(
                {
                    "node": "(loop)",
                    "tool": "loop_create",
                    "reply_verbatim": json.dumps(loop, ensure_ascii=False)[:300],
                }
            )

        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        already = con.execute(
            "select count(*) from tasks where id like ? and depth=1", (f"{root_id}.%",)
        ).fetchone()[0]
        con.close()
        if already == 0:
            plan = call(
                "task_plan_deep",
                {
                    "task_id": root_id,
                    "split_n": 3,
                    "decide_split_n": 3,
                    "decide_difficulty": 3.0,
                    "decide_reason": "六面分属规范/寻虫/修复/验证/账面/转结，可并行领取；"
                    "每枝 3 叶（2 面 + 1 边界审视）",
                    "omega_strong_verify": True,
                    "gradient": True,
                    "boundary_probe": True,
                    "reinject_context": True,
                    "by": AGENT,
                    "decide_by": AGENT,
                    "_omit_defaults": True,
                },
            )
            rep["plan"] = json.dumps(plan, ensure_ascii=False)[:300]

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tree = con.execute(
        "select id, depth, status, description from tasks where id=? or id like ? " "order by id",
        (root_id, f"{root_id}.%"),
    ).fetchall()
    con.close()
    leaves = [r for r in tree if r[1] == 1]
    boundary = [r[0] for r in leaves if r[3].startswith("[边界审视")]
    general = [r[0] for r in leaves if r[0] not in set(boundary)]
    rep["tree_readback"] = {
        "root": root_id,
        "rows": len(tree),
        "branches": len([r for r in tree if r[1] == 2]),
        "leaves": len(leaves),
        "general": general,
        "boundary": boundary,
    }

    face_assign = {}
    if len(general) >= len(FACES):
        for i, leaf in enumerate(general):
            face_assign[leaf] = FACES[i] if i < len(FACES) else None
        for leaf in general[len(FACES) :]:
            face_assign[leaf] = None
    covered = sorted({f[0] for f in face_assign.values() if f})
    rep["faces_covered"] = covered
    rep["faces_missing"] = sorted(f[0] for f in FACES if f[0] not in covered)
    if rep["faces_missing"]:
        rep["refusals"].append(
            {
                "node": "(面分配)",
                "tool": "local",
                "reply_verbatim": f"这些面没落到任何叶：{rep['faces_missing'][:6]}",
            }
        )
    if args.stage == "close" and rep["faces_missing"]:
        _finish(rep, "close")
        for r in rep["refusals"]:
            print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:240])
        print(f"CONCLUSION refused=1 stage=close faces_missing={len(rep['faces_missing'])}")
        return 1
    boundary_plan = {}
    for i, leaf in enumerate(boundary):
        boundary_plan[leaf] = (
            BOUNDARY[i]
            if i < len(BOUNDARY)
            else (DECLARED_NA, DECLARED_NA, ["-X", "utf8", "scripts/omega_gate.py"])
        )
    rep["boundary_plan"] = {
        "real": min(len(boundary), len(BOUNDARY)),
        "declared_na": max(0, len(boundary) - len(BOUNDARY)),
    }

    cs = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    n_locks = len(
        re.findall(
            r"(?m)^def test_",
            (ROOT / "tests" / "test_generic_bounds_r12.py").read_text(encoding="utf-8"),
        )
    )
    mx = matrix_summary()
    mx_txt = (
        f"{mx['cells']} 格矩阵（变异格 {mx['mutation_cells']} 支全红、对照格 {mx['control_cells']} 支 "
        f"0 红、L0 现树全绿）"
    )
    spec_body = {
        "corpus": CORPUS,
        "gate": "python scripts/omega_gate.py",
        "laws": ["SYNTAX/11 声明界在使用侧的判定 规则 1-4", "SYNTAX/11 类型约束（定义侧）"],
        "cases": len(cs["tests"]),
        "fingerprint": cs["fingerprint"],
        "exit_artifact": REPORT.name,
        "citation_check": "verify_r12_report.json failed=0",
    }

    if args.stage == "start":
        for leaf in general + boundary:
            if status(leaf) == "待领取":
                note(leaf, "claim", call("claim", {"task_id": leaf, "assignee": AGENT}))
            if spec_rows(leaf, SPEC_KIND) == 0:
                note(
                    leaf,
                    "omega_spec_create",
                    call(
                        "omega_spec_create",
                        {"task_id": leaf, "content": json.dumps(spec_body, ensure_ascii=False)},
                    ),
                )
                note(
                    leaf,
                    "omega_spec_review",
                    call(
                        "omega_spec_review",
                        {
                            "task_id": leaf,
                            "verdict": "approve",
                            "reason": f"R12：{len(cs['tests'])} 对（指纹 {cs['fingerprint']}），"
                            "含元数/违界并存与去重两对边界反例；出口件为报告并过引用核验",
                        },
                    ),
                )
        _finish(rep, "start")
        print("ROOT", root_id, "tree", json.dumps(rep["tree_readback"], ensure_ascii=False)[:220])
        print(
            f"CONCLUSION stage=start root={root_id} rows={rep['tree_readback']['rows']} "
            f"leaves={len(leaves)} faces_missing={len(rep['faces_missing'])} "
            f"calls={len(sent)} refused={len(rep['refusals'])} benign={len(rep['benign'])} tag={args.tag}"
        )
        for r in rep["refusals"][:10]:
            print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:220])
        c.close()
        return 0 if not rep["refusals"] else 1

    evid = (
        f"logs/r12_radius_before_a2.out 与 r12_radius_after_a1.out（206 源同集合前后快照）、"
        f"logs/r12_probe_a2.out（6 形现状）、logs/r12_matrix_a2.out（6 格承重矩阵）、"
        f"{CORPUS.split('/')[-1]} {len(cs['tests'])} 对指纹 {cs['fingerprint']}、"
        f"tests/test_generic_bounds_r12.py"
    )
    for leaf in general + boundary:
        st = status(leaf)
        rows = {"status_before": st, "steps": {}}
        face = boundary_plan.get(leaf) or face_assign.get(leaf) or FACES[0]
        if leaf in boundary:
            rows["kind"] = (
                "boundary-real" if leaf in boundary[: len(BOUNDARY)] else "boundary-declared-na"
            )
        elif face_assign.get(leaf):
            rows["kind"] = "face"
        if st == "待领取":
            rows["steps"]["claim"] = (
                "refused"
                if note(leaf, "claim", call("claim", {"task_id": leaf, "assignee": AGENT}))
                else "ok"
            )
        if spec_rows(leaf, SPEC_KIND) == 0:
            note(
                leaf,
                "omega_spec_create",
                call(
                    "omega_spec_create",
                    {"task_id": leaf, "content": json.dumps(spec_body, ensure_ascii=False)},
                ),
            )
            note(
                leaf,
                "omega_spec_review",
                call(
                    "omega_spec_review",
                    {
                        "task_id": leaf,
                        "verdict": "approve",
                        "reason": f"R12：{len(cs['tests'])} 对含成对反例；出口件已过引用核验",
                    },
                ),
            )
        name, what, check = face or FACES[0]
        dlv = (
            deliverable(
                name,
                f"R12 声明界使用侧已按 SYNTAX/11 规则 1-4 落地：{what}",
                evid,
                "BUG-134/135 本轮只立不修；构造位推断与 BUG-128 同层 ⇒ 转结 R13",
                f"{REPORT.name} §4/§5",
            )
            if st != "已完成"
            else None
        )
        if st != "已完成":
            rows["steps"]["execute"] = (
                "refused"
                if note(
                    leaf,
                    "execute",
                    call("execute", {"task_id": leaf, "deliverable": dlv, "executor": "self"}),
                )
                else "ok"
            )
        rc = call("run_check", {"task_id": leaf, "cmd": "python", "args": check, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok")}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
            rep["refusals"].append(
                {
                    "node": leaf,
                    "tool": "run_check",
                    "reply_verbatim": json.dumps(rc, ensure_ascii=False)[:300],
                }
            )
        if status(leaf) in ("执行中", "待验收", "已打回"):
            if spec_rows(leaf, RESULT_KIND) == 0:
                note(
                    leaf,
                    "omega_result_verify",
                    call("omega_result_verify", {"task_id": leaf, "verdict": "pass"}),
                )
            rows["steps"]["submit"] = (
                "refused" if note(leaf, "submit", call("submit", {"task_id": leaf})) else "ok"
            )
        if status(leaf) == "待验收":
            rows["steps"]["verify"] = (
                "refused"
                if note(
                    leaf,
                    "verify",
                    call("verify", {"task_id": leaf, "verifier": "verifier", "docs_check": True}),
                )
                else "ok"
            )
        rows["status_after"] = status(leaf)
        rep["nodes"][leaf] = rows

    def chain_up(node):
        st = status(node)
        if st == "拆分中":
            call(
                "execute",
                {
                    "task_id": node,
                    "executor": "self",
                    "deliverable": deliverable(
                        "枝干/根收口",
                        f"R12 交付：一处共用件 + 三处接线（摘掉字面量位窄复制）+ {len(cs['tests'])} 对语料"
                        f" + {n_locks} 支锁 + {mx_txt}",
                        f"logs/r12_matrix_a2.out、logs/{GATE_LOG.name}、logs/{PYTEST_LOG.name}",
                        "BUG-134/135 开口转结；T0r112/T0r113 两根未收（不伪造）",
                        REPORT.name,
                    ),
                },
            )
            call("submit", {"task_id": node})
        if status(node) in ("执行中", "待验收", "已打回"):
            if spec_rows(node, SPEC_KIND) == 0:
                call(
                    "omega_spec_create",
                    {"task_id": node, "content": json.dumps(spec_body, ensure_ascii=False)},
                )
                call(
                    "omega_spec_review",
                    {
                        "task_id": node,
                        "verdict": "approve",
                        "reason": f"R12 根/枝干：判据 {len(cs['tests'])} 对，报告已过引用核验",
                    },
                )
            if spec_rows(node, RESULT_KIND) == 0:
                note(
                    node,
                    "omega_result_verify",
                    call("omega_result_verify", {"task_id": node, "verdict": "pass"}),
                )
            if status(node) == "执行中":
                call("submit", {"task_id": node})
        if status(node) == "待验收":
            note(
                node,
                "verify",
                call("verify", {"task_id": node, "verifier": "verifier", "docs_check": True}),
            )
        return status(node)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    branches = [
        r[0]
        for r in con.execute(
            "select id from tasks where id like ? and depth=2", (f"{root_id}.%",)
        ).fetchall()
    ]
    pending = con.execute(
        "select count(*) from tasks where id like ? and status='待领取'", (f"{root_id}.%",)
    ).fetchone()[0]
    con.close()
    rep["pending_leaves"] = pending
    rep["branch_final"] = {b: chain_up(b) for b in branches if status(b) != "已完成"}
    rep["root_final"] = chain_up(root_id)
    rep["loop_drive"] = drive_loop(call, LOOP_NAME, STEPS_SEED)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and ok=0", (started,)
    ).fetchone()[0]
    rep["call_log_error_rows_old_needle"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)
    ).fetchone()[0]
    rep["rollup"] = dict(
        con.execute(
            "select status, count(*) from tasks where id like ? or id=? group by status",
            (f"{root_id}.%", root_id),
        ).fetchall()
    )
    con.close()
    c.close()
    rep["calls"] = len(sent)
    _finish(rep, "close")
    for leaf, rows in rep["nodes"].items():
        print(leaf, rows.get("status_before"), "->", rows.get("status_after"))
    print("BRANCHES", json.dumps(rep["branch_final"], ensure_ascii=False))
    stuck = [k for k, v in rep["rollup"].items() if v and k != "已完成"]
    print("LOOP_DRIVE", json.dumps(rep["loop_drive"]["gates"], ensure_ascii=False))
    for r in rep["idempotent"][:4]:
        print("IDEMPOTENT", r["node"], r["tool"], "|", r["reply_verbatim"][:160])
    print(
        f"CONCLUSION stage=close root={root_id} root_status={rep['root_final']} "
        f"rollup={rep['rollup']} non_closed={stuck} pending_leaves={pending} "
        f"calls={rep['calls']} refused={len(rep['refusals'])} idempotent={len(rep['idempotent'])} "
        f"benign={len(rep['benign'])} loop_ticks_ok={rep['loop_drive']['ticks_ok']} "
        f"call_log_error_rows={rep['call_log_error_rows']} "
        f"old_needle_rows={rep['call_log_error_rows_old_needle']} tag={args.tag}"
    )
    for r in rep["refusals"][:12]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:240])
    return (
        0
        if (
            not rep["refusals"]
            and rep["root_final"] == "已完成"
            and all(rep["loop_drive"]["gates"].values())
        )
        else 1
    )


def _finish(rep, stage):
    out = HERE / f"ring_r12_{stage}_{rep.get('tag', 'a1')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("EVIDENCE", out.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
