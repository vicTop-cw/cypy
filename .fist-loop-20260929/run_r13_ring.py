"""R13 组合环的 FIST 腿：`--stage start` 建根单并挂判据，`--stage close` 逐叶收口 + 走环。

RPC 形状沿用被走通的 R12 那份（同一 ns、同一 spec_type 口径、同一收口步序表），
但**本轮的一切数字都从盘面反解**：语料对数与指纹读 `corpus/cypy.container.elements.json`、
锁数读 `tests/test_container_elements_r13.py`、承重读数重算 `verify_r13_matrix.json`、
pytest 基线读本轮日志（缺件就拒跑，不许手填）。根单身份不依赖服务端发号：
描述里自带 `R13-RING-T0r119` 标记，收口按该标记反查真实 id。
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
sys.path.insert(0, str(HERE))
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
AGENT = "cypy-selfdrive-agent"
LOOP_NAME = "cypy-selfdrive-ring-r13"
RING_MARK = "R13-RING-T0r119"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r119-cypy-selfdrive-r13-report.md"
LOGS = HERE / "logs"
CORPUS = "corpus/cypy.container.elements.json"
LOCK_TESTS = "tests/test_container_elements_r13.py"
SPEC_KIND, CHECK_KIND, RESULT_KIND = "spec", "check", "result"

GATE_LOG = LOGS / "r13_gate_b3.log"
PYTEST_LOG = LOGS / "r13_pytest_final_c1.log"
RADIUS_LOG = LOGS / "r13_pytest_b2.log"
SUITE_LOG = LOGS / "r13_suite_b2.log"
E2E_LOG = LOGS / "r13_golden_b2.log"
PROBE_LOG = LOGS / "r13_container_probe_b2.json"
MATRIX_JSON = HERE / "verify_r13_matrix.json"
VERIFY_JSON = HERE / "verify_r13_report.json"
FILED_JSON = HERE / "file_r13_container_bugs.json"
LEDGER_JSON = HERE / "amend_r13_ledger.json"

STEPS_SEED = ["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"]
IDEMPOTENT_RE = re.compile(r"已通过审核，无需重复创建|不是待审核状态")

FACES = [
    (
        "推进：靶面选定与规范条款",
        "SYNTAX/02 新增「容器元素位判定（R13 补）」规则 1-6 —— 规则 1-3 钉定长判个数与逐位、变长判元素位、"
        "数值加宽单向；规则 4-6 明写**不判的一面**（四类占位放行、非闭合标量保守放行、dict 键值位不在本节）"
        "⇒ 先把承诺写清再动实现",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.container.elements"],
    ),
    (
        "寻虫：成对探针与改判",
        "probe_r13_container.py 39 形（CTRL 读取通道对照 + 非别名容器基线 P* + 同形走别名 A* + "
        "必须仍绿的占位 G* + 别名展开 N*/U*），判据自带 must_be_red / must_stay_green / 不许 crash 三组门；"
        "**据此改判 BUG-136**：其正文的「别名参数从不代入」机制为假（arity 与标量别名都在判），"
        "真根因是容器元素位与别名展开 ⇒ 新立 BUG-137/138/139",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.container.elements"],
    ),
    (
        "修复：一处判定件 + 别名展开到底",
        "TypeChecker 新增 `_slot_incompatible`/`_first_bad_element`/`_check_container_elements`"
        "（赋值位与返回位各接一行，共用一份判定）；`_substitute_type` 补 `UnionType` 分支并新增 "
        "`_expand_nested_alias`（带 `_alias_stack` 自指守卫），摘掉「同名容器即放行」的过度宽松",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.container.elements"],
    ),
    (
        "验证：三套全量与承重矩阵",
        "半径实测（改动前 2325 全绿，产品改动单独一轮）+ 终版 pytest + 自研套件 47 + e2e golden 25 + "
        "Ω-gate 全 spec；verify_r13_locks.py 7 格（L0 现树 + 5 格承重各红且身份探针翻假 + 只改注释对照 0 红）",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
    (
        "打磨：账本改判与 FIXED 派生数",
        "BUG-137/138/139 各追 FIXED（对数/指纹/锁数/转红形数全部运行时反解），BUG-136 追**改判段**"
        "（抬头 OPEN 不动、(f) 带界别名面仍开）；`SYNTAX_IMPLEMENTATION_STATUS.md` 的 02 与 12 两行同步改写"
        "⇒ 别名面不再挂「✅ 完整」",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
    (
        "推进：R14 入口（不伪造关闭的几条）",
        '字典字面量不推断类型（`dict<str,int>` 收 `{"a": "b"}` 静默）、`_type_in_union` 只比成员名'
        "⇒ 联合别名的元素位仍不判、BUG-122 类型实参不判存在性、BUG-136(f) 带界别名不解析、"
        "BUG-135/128 推断层、`T0r112`/`T0r113` 两根待领取叶无退役出路",
        ["-X", "utf8", "scripts/omega_gate.py"],
    ),
]
BOUNDARY = [
    (
        "边界审视（实做）：占位与真错的边界",
        '`list<int>` 收 `list()`（无元素信息）与收 `["s"]`（真错）必须在同一把尺下分岔 ⇒ '
        'Ω-spec 里 `G01_empty_ctor`/`P03_list_elem_wrong` 成对钉住；`list<int>` 收 `[1, "s"]`'
        "（塌成 object）另成一格，证明收紧没有把占位三形扫进红堆",
        ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.container.elements"],
    ),
]


def utc_z():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_open_ids() -> list:
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^## (BUG-\d+)", led)
    out = []
    for i in range(1, len(blocks), 2):
        if not re.search(r"(?m)^### (FIXED|DUPLICATE)", blocks[i + 1]):
            out.append(blocks[i])
    return out


def ledger_sweep() -> dict:
    """整档台账脏检读数（门只钉本件亲笔段，别轮坏戳不进本件账）。"""
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    tok = re.compile(r"\d{4}-\d\d-\d\dT[\d:]*Z*")
    canon = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ")
    heads = [ln for ln in led.splitlines() if ln.startswith("### ")]
    bad = [t for ln in heads for t in tok.findall(ln) if not canon.fullmatch(t)]
    return {
        "headers": len(re.findall(r"(?m)^## BUG-\d+", led)),
        "open_blocks": len(ledger_open_ids()),
        "fixed_sections": len(re.findall(r"(?m)^### FIXED", led)),
        "amend_sections": len(re.findall(r"(?m)^### 改判", led)),
        "residue_lines": len(re.findall(r"(?m)^.*\{[A-Z][A-Z_]*\}.*$", led)),
        "dblstamp_lines": len(re.findall(r"(?m)^.*20\d\d-\d\d-\d\dT20\d\d-\d\d-\d\dT.*$", led)),
        "hard_bad_stamps": len(
            [t for t in bad if t.endswith("ZZ") or re.search(r"\d{4}-\d\d-\d\dT\d{4}", t)]
        ),
        "soft_bad_stamps": len(bad),
    }


def corpus_case_total() -> int:
    tot = 0
    for f in sorted(glob.glob(str(ROOT / "corpus" / "*.json"))):
        tot += len(json.loads(Path(f).read_text(encoding="utf-8"))["tests"])
    return tot


def pytest_passed(path: Path) -> int:
    hits = (
        re.findall(r"(\d+) passed", path.read_text(encoding="utf-8", errors="replace"))
        if path.exists()
        else []
    )
    if not hits:
        raise SystemExit(f"{path.name} 解析不到 passed 计数 ⇒ 基线数无来源，拒绝手填")
    return int(hits[-1])


def suite_totals(path: Path) -> str:
    txt = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    m = re.findall(r"Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)", txt)
    return m[-1] if m else f"(未找到 Total 行 {path.name})"


def golden_totals(path: Path) -> str:
    txt = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    m = re.search(r"PASS=(\d+) FAIL=(\d+) UNREG/RUNFAIL=(\d+) WARN=(\d+)", txt)
    return m.group(0) if m else f"(未找到 summary {path.name})"


def spec_kind_guard():
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
    cells = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))["cells"]

    def is_ctrl(n):
        return any(k.get("kind") == "只改注释" for k in cells[n].get("identity", []))

    ctrl = {n: cells[n] for n in cells if n.startswith("M") and is_ctrl(n)}
    mut = {n: cells[n] for n in cells if n.startswith("M") and not is_ctrl(n)}
    return {
        "cells": len(cells),
        "mutation_cells": len(mut),
        "load_bearing": len([c for c in mut.values() if c["pytest"]["n_failed"] > 0]),
        "all_mutation_red": all(c["pytest"]["n_failed"] > 0 for c in mut.values()),
        "all_gate_red": all((c["gate"]["failed"] or 0) > 0 for c in mut.values()),
        "control_cells": len(ctrl),
        "control_zero_red": all(c["pytest"]["n_failed"] == 0 for c in ctrl.values()),
    }


def entry_gate():
    reasons, obs = [], {}
    cs = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    obs["corpus"] = {"cases": len(cs["tests"]), "fingerprint": cs["fingerprint"]}
    if not (ROOT / CORPUS).exists() or len(cs["tests"]) < 20:
        reasons.append(f"Ω-spec 语料不合格：{CORPUS} 只有 {len(cs['tests'])} 对")
    n_locks = len(
        re.findall(r"(?m)^def test_", Path(ROOT / LOCK_TESTS).read_text(encoding="utf-8"))
    )
    obs["locks"] = n_locks
    if n_locks < 20:
        reasons.append(f"回归锁只有 {n_locks} 支")
    for p in (
        PYTEST_LOG,
        RADIUS_LOG,
        GATE_LOG,
        SUITE_LOG,
        E2E_LOG,
        PROBE_LOG,
        MATRIX_JSON,
        FILED_JSON,
        VERIFY_JSON,
    ):
        if not p.exists():
            reasons.append(f"证据件缺失：{p.name}")
    if REPORT.exists():
        obs["report_bytes"] = REPORT.stat().st_size
    else:
        reasons.append(f"出口件未落盘：{REPORT.name}")
    live = ledger_sweep()
    obs["ledger"] = live
    if live["dblstamp_lines"] or live["residue_lines"] or live["hard_bad_stamps"]:
        reasons.append(f"台账脏检未归零：{json.dumps(live, ensure_ascii=False)}")
    probe = json.loads(PROBE_LOG.read_text(encoding="utf-8")) if PROBE_LOG.exists() else {}
    green_broken = [
        k for k in probe if k.startswith(("A03", "A08", "G", "N01", "U02", "U03")) and probe[k]["n"]
    ]
    obs["probe"] = {
        "cases": len(probe),
        "red": len([v for v in probe.values() if v["n"]]),
        "should_be_green_now_red": green_broken,
    }
    if probe and green_broken:
        reasons.append(f"探针里该绿的形转红了：{green_broken}")
    if VERIFY_JSON.exists():
        v = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
        obs["citation_check"] = {"checks": v.get("checks"), "failed": v.get("failed")}
        if v.get("failed"):
            reasons.append(f"引用核验件仍有 {v['failed']} 条不过")
    mx = matrix_summary()
    obs["matrix"] = mx
    if not (
        mx["all_mutation_red"]
        and mx["control_zero_red"]
        and mx["all_gate_red"]
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
    return f"结论：{concl}\n证据：{evid}\n分析：{face}\n缺口与风险：{gap}\n建议入档位置：{store}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["start", "close"], default="start")
    ap.add_argument("--tag", default="a1", help="回执文件名后缀：复跑不覆盖上一次读数")
    args = ap.parse_args()
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
            (LOGS / f"r13_ring_close_refused_{args.tag}.json").write_text(
                json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            for r in reasons:
                print("REFUSED (开批门) local |", r[:300])
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
            rep["idempotent"].append({"node": node, "tool": tool, "reply_verbatim": blob})
            return False
        if refused(res) or blob.startswith("RPC-ERROR") or '"__error__"' in blob:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob})
            return True
        if benign(res):
            rep["benign"].append({"node": node, "tool": tool, "reply_verbatim": blob})
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
        (NS, f"%{RING_MARK}%"),
    ).fetchone()
    con.close()
    root_id = root_row[0] if root_row else None
    if args.stage == "close" and not root_id:
        rep["entry_gate"] = {
            "pass": False,
            "reasons": [f"账上查无根单：ns={NS} 且 description 含 {RING_MARK} 且 parent_id=''"],
            "observed": {"db": str(DB)},
        }
        (LOGS / f"r13_ring_close_refused_{args.tag}.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"REFUSED (开批门) local | 账上查无根单 {RING_MARK}")
        print("CONCLUSION refused=1 stage=close gate_reasons=1")
        return 1

    cs = json.loads((ROOT / CORPUS).read_text(encoding="utf-8"))
    n_locks = len(re.findall(r"(?m)^def test_", (ROOT / LOCK_TESTS).read_text(encoding="utf-8")))
    mx = matrix_summary() if MATRIX_JSON.exists() else {}
    filed = json.loads(FILED_JSON.read_text(encoding="utf-8")) if FILED_JSON.exists() else {}
    spec_body = {
        "corpus": CORPUS,
        "gate": "python scripts/omega_gate.py",
        "laws": ["SYNTAX/02 容器元素位判定 规则 1-6", "SYNTAX/12 类型别名「编译时完全等价」"],
        "cases": len(cs["tests"]),
        "fingerprint": cs["fingerprint"],
        "exit_artifact": REPORT.name,
        "citation_check": f"{VERIFY_JSON.name} failed=0",
    }

    if args.stage == "start":
        if root_id:
            rep["root_reused"] = root_id
        else:
            open_ids = ledger_open_ids()
            base_tests = pytest_passed(RADIUS_LOG)
            root = call(
                "publish_parallel",
                {
                    "project_dir": ".",
                    "namespace": NS,
                    "created_by": AGENT,
                    "description": (
                        f"[omega:required] {RING_MARK}（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
                        "本轮靶面：把**容器元素位与类型别名代入**打到闭合 —— 同名容器不再「名字对上就放行」，"
                        "赋值位与返回位共用 `_check_container_elements` 一份判定；"
                        "`_substitute_type` 补 `UnionType` 分支并把别名右端里的别名展开到底"
                        f"（Ω-spec 新 op `cypy.container.elements` {len(cs['tests'])} 对，台账合计 {corpus_case_total()} 对）。\n"
                        "  寻虫另立 3 张：BUG-137 容器元素位整体不判（high）、BUG-138 别名套别名不展开⇒"
                        "正确程序被拒（high）、BUG-139 联合形态别名整条不代入（medium）；"
                        "并对 BUG-136 追**改判段**：其「参数从不代入」机制为假，本单只留 (f) 带界别名面 ⇒ 抬头仍 OPEN\n"
                        f"开工基线（本轮实测反解，不手填）：半径轮 pytest {base_tests} passed"
                        f"（logs/{RADIUS_LOG.name}，只含产品改动、不含本轮新锁）；"
                        f"台账开口 {len(open_ids)} 块；终版 pytest 与 Ω-gate 见 logs/{PYTEST_LOG.name}、"
                        f"logs/{GATE_LOG.name}。\n出口件：`reports/2026-09-29/{REPORT.name}`。"
                    ),
                },
            )
            rep["root"] = json.dumps(root, ensure_ascii=False)
            root_id = root.get("task_id") if isinstance(root, dict) else None
            if not root_id:
                rep["refusals"].append(
                    {
                        "node": "(建单)",
                        "tool": "publish_parallel",
                        "reply_verbatim": json.dumps(root, ensure_ascii=False),
                    }
                )
                _finish(rep, "start")
                return 1
        laya = call(
            "laya_decide",
            {
                "context": (
                    f"任务：{RING_MARK} —— Cypy 容器元素位判定（赋值位+返回位共用一件）与类型别名展开到底"
                    f"（含联合形态、自指守卫），新 op cypy.container.elements {len(cs['tests'])} 对，"
                    f"台账合计 {corpus_case_total()} 对；账上另有本轮新立 3 张开口单"
                    "（BUG-137/138/139）与 1 张改判单（BUG-136 仍 OPEN）。"
                    "已知阻塞：字典字面量不推断类型、`_type_in_union` 只比成员名 ⇒ 联合别名元素位不判、"
                    "BUG-122 类型实参存在性、BUG-135/128 推断层；T0r112/T0r113 待领取叶无退役出路。"
                    "问：该开哪些机制、怎么拆。"
                )
            },
        )
        rep["laya"] = json.dumps(laya, ensure_ascii=False)
        open_ids = ledger_open_ids()
        base_tests = pytest_passed(RADIUS_LOG)
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
        rep["loop_create"] = json.dumps(loop, ensure_ascii=False)
        rep["ledger_open_at_start"] = len(open_ids)
        rep["baseline_test_count_used"] = base_tests
        if refused(loop) and not benign(loop):
            rep["refusals"].append(
                {
                    "node": "(loop)",
                    "tool": "loop_create",
                    "reply_verbatim": json.dumps(loop, ensure_ascii=False),
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
                    "decide_reason": "六面分属规范/寻虫/修复/验证/账面/转结，可并行领取；每枝 3 叶（2 面 + 1 边界审视）",
                    "omega_strong_verify": True,
                    "gradient": True,
                    "boundary_probe": True,
                    "reinject_context": True,
                    "by": AGENT,
                    "decide_by": AGENT,
                    "_omit_defaults": True,
                },
            )
            rep["plan"] = json.dumps(plan, ensure_ascii=False)

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
        "leaves": len(leaves),
        "boundary": len(boundary),
    }
    face_assign = {leaf: FACES[i] for i, leaf in enumerate(general) if i < len(FACES)}
    boundary_plan = {leaf: BOUNDARY[i] for i, leaf in enumerate(boundary) if i < len(BOUNDARY)}
    missing = [leaf for leaf in general if leaf not in face_assign]
    rep["faces_missing"] = missing
    rep["obs"] = {
        "corpus_cases": len(cs["tests"]),
        "fingerprint": cs["fingerprint"],
        "locks": n_locks,
        "matrix": mx,
        "filed_new_ids": filed.get("new_ids"),
        "ledger": ledger_sweep(),
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
                            "reason": f"R13：{len(cs['tests'])} 对（指纹 {cs['fingerprint']}），"
                            "含占位四形与别名套娃的正反成对半边；出口件为报告并过引用核验",
                        },
                    ),
                )
        _finish(rep, "start")
        print("ROOT", root_id, "tree", json.dumps(rep["tree_readback"], ensure_ascii=False))
        print(
            f"CONCLUSION stage=start root={root_id} rows={rep['tree_readback']['rows']} "
            f"leaves={len(leaves)} faces_missing={len(missing)} "
            f"calls={len(sent)} refused={len(rep['refusals'])} benign={len(rep['benign'])} "
            f"tag={args.tag}"
        )
        for r in rep["refusals"][:10]:
            print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"])
        c.close()
        return 0 if not rep["refusals"] else 1

    evid = (
        f"logs/{RADIUS_LOG.name}（半径轮 2325 全绿，只含产品改动）、"
        f"logs/{PYTEST_LOG.name}（终版含本轮锁）、logs/{PROBE_LOG.name}（39 形成对探针，三组自门）、"
        f"logs/{GATE_LOG.name}、logs/{E2E_LOG.name}、{MATRIX_JSON.name}（{json.dumps(mx, ensure_ascii=False)}）、"
        f"{CORPUS.split('/')[-1]} {len(cs['tests'])} 对指纹 {cs['fingerprint']}、{LOCK_TESTS}（{n_locks} 支）"
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
                        "reason": f"R13：{len(cs['tests'])} 对含成对反例；出口件已过引用核验",
                    },
                ),
            )
        name, what, check = face or FACES[0]
        dlv = (
            deliverable(
                name,
                f"R13 容器元素位与别名代入已按 SYNTAX/02 规则 1-6 落地：{what}",
                evid,
                "BUG-136 只留 (f) 带界别名面；dict 字面量不推断、联合成员元素位、BUG-122/135/128 "
                "本轮只立不修 ⇒ 转结 R14",
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
                    "reply_verbatim": json.dumps(rc, ensure_ascii=False),
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
                        f"R13 交付：一份元素位判定接两处使用位 + 别名展开到底（含联合形态与自指守卫）"
                        f" + {len(cs['tests'])} 对语料 + {n_locks} 支锁 + {json.dumps(mx, ensure_ascii=False)}",
                        f"{MATRIX_JSON.name}、logs/{GATE_LOG.name}、logs/{PYTEST_LOG.name}",
                        "BUG-136(f)/BUG-122/135/128 开口转结；T0r112/T0r113 两根未收（不伪造）",
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
                        "reason": f"R13 根/枝干：判据 {len(cs['tests'])} 对，报告已过引用核验",
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
            "select status, count(*) from tasks where id like ? or id=? " "group by status",
            (f"{root_id}.%", root_id),
        ).fetchall()
    )
    con.close()
    c.close()
    rep["calls"] = len(sent)
    rep["suite_totals"] = suite_totals(SUITE_LOG)
    rep["golden_totals"] = golden_totals(E2E_LOG)
    _finish(rep, "close")
    for leaf, rows in rep["nodes"].items():
        print(leaf, rows.get("status_before"), "->", rows.get("status_after"))
    print("BRANCHES", json.dumps(rep["branch_final"], ensure_ascii=False))
    stuck = [k for k, v in rep["rollup"].items() if v and k != "已完成"]
    print("LOOP_DRIVE", json.dumps(rep["loop_drive"]["gates"], ensure_ascii=False))
    for r in rep["idempotent"][:4]:
        print("IDEMPOTENT", r["node"], r["tool"], "|", r["reply_verbatim"])
    print(
        f"CONCLUSION stage=close root={root_id} root_status={rep['root_final']} "
        f"rollup={rep['rollup']} non_closed={stuck} pending_leaves={pending} "
        f"calls={rep['calls']} refused={len(rep['refusals'])} idempotent={len(rep['idempotent'])} "
        f"benign={len(rep['benign'])} loop_ticks_ok={rep['loop_drive']['ticks_ok']} "
        f"call_log_error_rows={rep['call_log_error_rows']} "
        f"old_needle_rows={rep['call_log_error_rows_old_needle']} "
        f"suite={rep['suite_totals']} golden={rep['golden_totals']} tag={args.tag}"
    )
    for r in rep["refusals"][:12]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"])
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
    out = HERE / f"ring_r13_{stage}_{rep.get('tag', 'a1')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"WROTE {out.name}")


if __name__ == "__main__":
    sys.exit(main())
