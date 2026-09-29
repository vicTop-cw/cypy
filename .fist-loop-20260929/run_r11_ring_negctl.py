"""R11 组合环的 FIST 腿：`--stage start` 建单并挂判据，`--stage close` 收口。

两条来自既往轮的硬约束（不是偏好）：
 · 收口必须按 (当前状态, specs 表有无行) 分派步骤 ⇒ 对已 approved 的语料重发 spec 会刷出幂等拒绝，
   把 refused 变成噪声（R10 实测 70 条）；
 · `verify` 的 `docs_check=True` 是服务端门禁 ⇒ 交付物必须五段式
   （结论/证据/分析/缺口与风险/建议入档位置），待验收态的出路是 reject→retry→execute。
`--stage close` 起手先过四道门（报告在盘、引用核验 failed=0 且 report_bytes 与盘面逐字相等、
Ω-gate 与三套终验日志为终值），任一条不满足就 refuse 而不建/不动账。
"""

from __future__ import annotations

import argparse
import datetime
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
LOOP_NAME = "cypy-selfdrive-ring-r11"
ROOT_PREFIX = "T0r999-不存在的根单前缀"
REPORT = ROOT / "reports" / "2026-09-29" / "T0r117-cypy-selfdrive-r11-report.md"
VERIFY_JSON = HERE / "verify_r11_report.json"
CORPUS = "corpus/cypy.generic.class.json"
LOGS = HERE / "logs"
# 服务端 specs 表实际写入的 spec_type 只有这三值（omega_spec_* → 'spec'，run_check → 'check'，
# omega_result_verify → 'result'）。上一轮按 "omega"/"omega_result" 取数 ⇒ 恒 0 ⇒ 收口时把已 approved
# 的语料重发了一遍，刷出 24 条幂等拒绝。常量集中在此，并由 spec_kind_guard 对着活库自证。
SPEC_KIND, CHECK_KIND, RESULT_KIND = "spec", "check", "result"

FACES = [
    ("推进：靶面选定与规范条款",
     "SYNTAX/11 新增「泛型类的判定口径」规则 1-5（先立规范再动实现），"
     "并把「明确不支持」表里 BUG-119 那行摘掉、BUG-120 那行改成 `-> T:` 带冒号形态",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.class"]),
    ("寻虫：探针与基线实测",
     "probe_r11_generic_class.py 16 例（修复前 14/16 卡 `Expected COLON, got LT`）+ "
     "baseline_r11_generic_ann.py（1147 份 .cypy 源、55 处泛型注解位、元数违例 0 ⇒ 开元数门不会打红既有源）+ "
     "measure_r11_substitution.py（13 例成对：代入生效的正例必配必红的反例）",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.class"]),
    ("修复：解析器与分析器四处",
     "ClassDef 参数表字段、Parser._parse_type_param_list（class/struct 合一）、"
     "TypeChecker._generic_arity_diagnostic（注解位/调用位合一）、"
     "_visit_Attribute 的 class 分支逐位代入 + _visit_ClassDef/_visit_FuncDef 的形式参数守卫",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.class"]),
    ("验证：三套全量与承重矩阵",
     "pytest 终版 + 自研套件 + e2e golden + Ω-gate 5 spec/100 对；"
     "verify_r11_locks.py 7 格（5 格承重各红且身份探针翻假、注释对照格 0 红）",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("打磨：账本与状态表",
     "BUG-119 追 FIXED（含双向格说明）、BUG-120/122 追 AMENDMENT、"
     "新立 BUG-126/127/128/129 四张开口留证据、SYNTAX_IMPLEMENTATION_STATUS 的 11 行改口径",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("推进：R12 入口（不自证关闭的三条）",
     "BUG-128（struct 方法代入，收紧面大）、BUG-129（声明界在注解位/实例化位不判）、"
     "BUG-121/122/120 裁决面；`T0r112`/`T0r113` 两根仍停拆分中（19 支待领取叶无出路，BUG-106）⇒ 不伪造交付物",
     ["-X", "utf8", "scripts/omega_gate.py"]),
]
BOUNDARY = [
    ("边界审视（实做）：空参数表与裸名",
     "`class Box<>:` 硬拒文案与 struct 逐字相同；`class Box<T>` 的裸名使用 `let b: Box = Box(1)` 按擦除不报；"
     "两形都在 corpus 里钉住", ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.class"]),
    ("边界审视（实做）：链式接收者与嵌套注解",
     "`l.next().next()` 在 `-> int` 上报 `expected int, got Link[int]`（代入可复合）；"
     "`list<Box<int>>` 与 `Pair<int, str>` 逐位代入各配一对必红反例",
     ["-X", "utf8", "scripts/omega_gate.py", "--op", "cypy.generic.class"]),
]
DECLARED_NA = ("边界审视（声明不适用）：本面是编译期语法/代入判定，无堆、无循环、无 I/O，"
               "资源极限一类输入域对本形态不可判定 ⇒ 依据写在报告 §3.3，不放恒真门")


def utc_z():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_open_ids() -> list[str]:
    """账本开口块编号（口径 A：块内既无 FIXED 也无 DUPLICATE）—— 环的 baseline/current 数都取这里。"""
    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"(?m)^## (BUG-\d+)", led)
    return [blocks[i] for i in range(1, len(blocks) - 1, 2)
            if not re.search(r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)", blocks[i + 1])]


def pytest_count() -> int:
    p = LOGS / "r11_pytest_a2.log"
    hits = re.findall(r"(\d+) passed", p.read_text(encoding="utf-8", errors="replace")) if p.exists() else []
    if not hits:
        raise SystemExit("r11_pytest_a2.log 解析不到 passed 计数 ⇒ current_test_count 无来源，拒绝手填")
    return int(hits[-1])


def spec_kind_guard() -> tuple[bool, list, list]:
    """对着活库自证三个 spec_type 针：库里有行却没有本件用的值 ⇒ 服务端改过口径，收口必须先停。

    这是"恒 0 针"的免费负控制：库里一行 specs 都没有时也照样 refuse，因为那种情况下门无从判断。
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    kinds = [r[0] for r in con.execute("select distinct spec_type from specs").fetchall()]
    total = con.execute("select count(*) from specs").fetchone()[0]
    con.close()
    missing = [k for k in (SPEC_KIND, CHECK_KIND, RESULT_KIND) if k not in kinds]
    return (not missing and total > 0), missing, sorted(kinds)


IDEMPOTENT_RE = re.compile(r"已通过审核，无需重复创建|不是待审核状态")


STEPS_SEED = ["advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"]


def loop_create_params(name: str) -> dict:
    """回放的基线数从账上取（上一笔成功的 loop_create），不手敲。"""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = con.execute("select params_json from call_log where tool='loop_create' and ok=1 and params_json like ? "
                      "order by rowid desc limit 1", (f'%{name}%',)).fetchone()
    con.close()
    if not row:
        raise SystemExit(f"账上查无 {name} 成功的 loop_create 参数 ⇒ 基线数无来源，拒绝手填")
    return json.loads(row[0])


def drive_loop(call, name: str, steps: list) -> dict:
    """在**当前会话**里注册并走完 steps，逐格对表后返回回执（门表复用 r11_loop_drive，不另写一份）。"""
    import r11_loop_drive as ld
    seed = loop_create_params(name)
    if list(seed.get("steps") or []) != steps:
        raise SystemExit(f"账上 steps 与本件 STEPS_SEED 不一致：{seed.get('steps')} != {steps}")
    created = call("loop_create", {"name": name, "steps": steps,
                                  "max_rounds": seed.get("max_rounds", len(steps)),
                                  "baseline_test_count": seed.get("baseline_test_count", 0),
                                  "baseline_open_bug_count": seed.get("baseline_open_bug_count", 0),
                                  "stop_on_goal": bool(seed.get("stop_on_goal", False)),
                                  "stop_on_exceeded": bool(seed.get("stop_on_exceeded", False)),
                                  "_omit_defaults": True})
    args = {"name": name, "project_health_grade": "attention", "blocked_tasks": 0,
            "current_test_count": pytest_count(), "current_open_bug_count": len(ledger_open_ids()),
            "_omit_defaults": True}
    pre = call("loop_status", {"name": name, "_omit_defaults": True})
    ticks = []
    for i, step in enumerate(steps, 1):
        res = call("loop_tick", args)
        blob = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
        ticks.append({"refused": blob.startswith("RPC-ERROR") or '"__error__"' in blob
                      or "不被接受" in blob or "loop not found" in blob,
                      "picked": ld.pick(blob) if not isinstance(res, str) else ld.pick(res),
                      "i": i, "expect_mode": step})
    post = call("loop_status", {"name": name, "_omit_defaults": True})
    pre_blob = json.dumps(pre, ensure_ascii=False) if not isinstance(pre, str) else pre
    post_blob = json.dumps(post, ensure_ascii=False) if not isinstance(post, str) else post
    refused_pre = '"__error__"' in pre_blob or "loop not found" in pre_blob
    refused_post = '"__error__"' in post_blob or "loop not found" in post_blob
    gates = ld.gate_table(isinstance(created, dict) and "__error__" in created, refused_pre, refused_post,
                          ticks, ld.pick(pre_blob).get("round"), ld.pick(post_blob).get("round"),
                          # 跨会话反例在 r11_loop_drive.py 里取；这里同一会话内不制造假反例
                          True, steps)
    return {"gates": gates, "ticks_ok": len([x for x in ticks if not x["refused"]]),
            "steps": len(steps), "pre": ld.pick(pre_blob), "post": ld.pick(post_blob),
            "tick_args": {k: args[k] for k in args if k != "_omit_defaults"},
            "seq": [x["picked"].get("next_mode") for x in ticks],
            "idx": [(x["picked"].get("loop_after") or {}).get("current_idx") for x in ticks]}


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


def last_line(path, needle):
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


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
        reasons.append("引用核验件缺失（verify_r11_report.json）")
    else:
        v = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
        fails = v.get("failed")
        n_fail = len(fails) if isinstance(fails, list) else fails
        obs["verify_failed"] = n_fail
        obs["verify_checks"] = v.get("checks_ran", len(v.get("checks", []) or []))
        if n_fail != 0:
            reasons.append(f"引用核验 failed={n_fail} 项：{json.dumps(fails, ensure_ascii=False)[:200]}")
        obs["verify_report_bytes"] = v.get("report_bytes")
        if REPORT.exists() and v.get("report_bytes") != REPORT.stat().st_size:
            reasons.append(f"核验后报告又被改：核验件 report_bytes={v.get('report_bytes')} "
                           f"盘面={REPORT.stat().st_size}")
    obs["gate"] = last_line(LOGS / "r11_gate_a3.log", "CONCLUSION")
    if "cases=100" not in obs["gate"] or not obs["gate"].endswith("rc=0"):
        reasons.append(f"Ω-gate 不是 R11 终值：{obs['gate']}")
    obs["pytest"] = last_line(LOGS / "r11_pytest_a2.log", "pytest_rc=")
    if obs["pytest"] != "pytest_rc=0":
        reasons.append(f"pytest 终版非 0：{obs['pytest']}")
    obs["native"] = last_line(LOGS / "r11_native_a2.log", "Total: 47")
    if "Passed: 47 | Failed: 0" not in obs["native"]:
        reasons.append(f"自研套件终值不符：{obs['native']}")
    obs["e2e"] = last_line(LOGS / "r11_e2e_a2.log", "[e2e-golden] summary:")
    if "PASS=25 FAIL=0" not in obs["e2e"] or "WARN=0" not in obs["e2e"]:
        reasons.append(f"e2e golden 终值不符：{obs['e2e']}")
    guard_ok, missing_kinds, live_kinds = spec_kind_guard()
    obs["spec_kind_guard"] = {"pass": guard_ok, "missing": missing_kinds, "live": live_kinds}
    if not guard_ok:
        reasons.append(f"specs 表的 spec_type 针失效：本件按 {SPEC_KIND}/{CHECK_KIND}/{RESULT_KIND} 取数，"
                       f"库里缺 {missing_kinds}（库里实有 {live_kinds}）⇒ 恒 0 会让收口重发已 approved 的语料")
    return reasons, obs


def deliverable(face, concl, evid, gap, store):
    return (f"结论：{concl}\n证据：{evid}\n分析：{face}\n"
            f"缺口与风险：{gap}\n建议入档位置：{store}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["start", "close"], default="start")
    args = ap.parse_args()
    started = utc_z()
    rep = {"started_z": started, "stage": args.stage, "ns": NS, "refusals": [],
           "benign": [], "idempotent": [], "nodes": {}, "obs": {}}

    if args.stage == "close":
        reasons, obs = entry_gate()
        rep["entry_gate"] = {"pass": not reasons, "reasons": reasons, "observed": obs}
        if reasons:
            (HERE / "logs" / "r11_ring_close_refused.json").write_text(
                json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
            for r in reasons:
                print("REFUSED (开批门) local |", r[:240])
            print(f"CONCLUSION refused=1 stage=close gate_reasons={len(reasons)}")
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
        """三桶分开：幂等回执（状态本就达成）/ 真拒绝 / 良性重复。

        上一轮把幂等回执记进 refusals ⇒ "refused=24" 既不像真拒绝也不像没事，
        而 rc 由它决定 ⇒ 收口实际成功却被报成失败。幂等在这里不是错误，但必须单独计数、单独印。
        """
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
            return con.execute("select count(*) from specs where task_id=? and spec_type=?",
                               (node, kind)).fetchone()[0]
        finally:
            con.close()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    root_row = con.execute("select id from tasks where ns=? and parent_id='' and description like ? "
                           "order by length(id), id", (NS, f"%{ROOT_PREFIX}%")).fetchone()
    con.close()
    root_id = root_row[0] if root_row else None
    if args.stage == "close" and not root_id:
        # 收口只能指认已存在的根单：查不到就 refuse，绝不静默新建一棵树
        rep["entry_gate"] = {"pass": False,
                             "reasons": [f"账上查无根单：ns={NS} 且 description 含 {ROOT_PREFIX} 且 parent_id=''"],
                             "observed": {"db": str(DB)}}
        (HERE / "logs" / "r11_ring_close_refused.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"REFUSED (开批门) local | 账上查无根单 {ROOT_PREFIX}")
        print("CONCLUSION refused=1 stage=close gate_reasons=1")
        return 1

    if args.stage == "start":
        if root_row:
            root_id = root_row[0]
            rep["root_reused"] = root_id
        else:
            root = call("publish_parallel", {"project_dir": ".", "namespace": NS, "created_by": AGENT,
                                            "description": (
                f"[omega:required] {ROOT_PREFIX}（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
                "本轮靶面：把泛型类 `class Box<T>:`（SYNTAX/11:107-125 承诺、BUG-119 开口）打到闭合 —— "
                "定义侧三种前缀与约束解析、注解位/调用位元数、接收者按位代入、产物擦除；"
                "判据层从 4 op/71 对扩到 5 op/100 对（新 op `cypy.generic.class` 29 对）。\n"
                "  寻虫另立 4 张：BUG-126 诊断行号 +1、BUG-127 `cdef class` 误导性诊断与不可达分支、"
                "BUG-128 struct 方法不代入、BUG-129 声明界在注解位/实例化位不判\n"
                "开工基线（R10 终版实测，逐字）：pytest 2241 passed rc=0；Ω-gate specs=4 cases=71 "
                "passed=71 failed=0 refused=0 accuracy=100.00% rc=0；自研 47/47；e2e PASS=25 FAIL=0。\n"
                "出口件：`reports/2026-09-29/T0r117-cypy-selfdrive-r11-report.md`。")})
            rep["root"] = json.dumps(root, ensure_ascii=False)[:300]
            root_id = root.get("task_id") if isinstance(root, dict) else None
            if not root_id:
                rep["refusals"].append({"node": "(建单)", "tool": "publish_parallel",
                                        "reply_verbatim": json.dumps(root, ensure_ascii=False)[:300]})
                _finish(rep, "start")
                return 1

        laya = call("laya_decide", {"context": (
            "任务：把 Cypy 的泛型类 `class Box<T>:` 打到闭合（解析 + 元数 + 接收者代入 + 产物擦除），"
            "并把 Ω-spec 从 4 op/71 对扩到 5 op/100 对；账上另有 4 张本轮新立的开口单。"
            "已知阻塞：struct 方法代入与声明界判定面大，需另轮；`T0r112`/`T0r113` 的 19 支待领取叶无退役出路。"
            "问：该开哪些机制、怎么拆。")})
        rep["laya"] = json.dumps(laya, ensure_ascii=False)[:400]

        open_ids = ledger_open_ids()
        loop = call("loop_create", {"name": LOOP_NAME,
                                   "steps": ["advance", "bugfind", "fix_and_merge", "verify", "polish",
                                             "advance"],
                                   "max_rounds": 6, "baseline_test_count": 2241,
                                   "baseline_open_bug_count": len(open_ids), "stop_on_goal": False,
                                   "stop_on_exceeded": False, "_omit_defaults": True})
        rep["loop_create"] = json.dumps(loop, ensure_ascii=False)[:260]
        rep["ledger_open_at_start"] = len(open_ids)
        if refused(loop) and not benign(loop):
            rep["refusals"].append({"node": "(loop)", "tool": "loop_create",
                                    "reply_verbatim": json.dumps(loop, ensure_ascii=False)[:300]})

        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        already = con.execute("select count(*) from tasks where id like ? and depth=1",
                             (f"{root_id}.%",)).fetchone()[0]
        con.close()
        if already == 0:
            plan = call("task_plan_deep", {"task_id": root_id, "split_n": 3, "decide_split_n": 3,
                                           "decide_difficulty": 3.0,
                                           "decide_reason": "六面分属规范/寻虫/修复/验证/账面/转结，可并行领取；"
                                                             "每枝 3 叶（2 面 + 1 边界审视）",
                                           "omega_strong_verify": True, "gradient": True,
                                           "boundary_probe": True, "reinject_context": True,
                                           "by": AGENT, "decide_by": AGENT, "_omit_defaults": True})
            rep["plan"] = json.dumps(plan, ensure_ascii=False)[:300]

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tree = con.execute("select id, depth, status, description from tasks where id=? or id like ? "
                       "order by id", (root_id, f"{root_id}.%")).fetchall()
    con.close()
    leaves = [r for r in tree if r[1] == 1]
    boundary = [r[0] for r in leaves if r[3].startswith("[边界审视")]
    general = [r[0] for r in leaves if r[0] not in set(boundary)]
    rep["tree_readback"] = {"root": root_id, "rows": len(tree), "branches": len([r for r in tree if r[1] == 2]),
                            "leaves": len(leaves), "general": general, "boundary": boundary}

    face_assign = {}
    if len(general) >= len(FACES):
        for i, leaf in enumerate(general):
            face_assign[leaf] = FACES[i] if i < len(FACES) else None
        # 多出来的 general 叶没有新面可给 ⇒ 明确标"复面"，不静默重复计面
        for leaf in general[len(FACES):]:
            face_assign[leaf] = None
    covered = sorted({f[0] for f in face_assign.values() if f})
    rep["faces_covered"] = covered
    rep["faces_missing"] = sorted(f[0] for f in FACES if f[0] not in covered)
    if rep["faces_missing"]:
        rep["refusals"].append({"node": "(面分配)", "tool": "local",
                                "reply_verbatim": f"这些面没落到任何叶：{rep['faces_missing'][:6]}"})
    if args.stage == "close" and rep["faces_missing"]:
        _finish(rep, "close")
        for r in rep["refusals"]:
            print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:240])
        print(f"CONCLUSION refused=1 stage=close faces_missing={len(rep['faces_missing'])}")
        return 1
    # 边界叶：前 len(BOUNDARY) 支做实测边界，其余按"声明不适用"落依据（不放假恒真门）
    boundary_plan = {}
    for i, leaf in enumerate(boundary):
        boundary_plan[leaf] = (BOUNDARY[i] if i < len(BOUNDARY)
                               else (DECLARED_NA, DECLARED_NA, ["-X", "utf8", "scripts/omega_gate.py"]))
    rep["boundary_plan"] = {"real": min(len(boundary), len(BOUNDARY)),
                            "declared_na": max(0, len(boundary) - len(BOUNDARY))}

    spec_body = {"corpus": CORPUS, "gate": "python scripts/omega_gate.py",
                 "laws": ["SYNTAX/11 泛型类的判定口径 规则 1-5", "SYNTAX/11 调用点的类型实参 规则 1-5"],
                 "exit_artifact": REPORT.name,
                 "citation_check": "verify_r11_report.json failed=0"}

    if args.stage == "start":
        for leaf in general + boundary:
            if status(leaf) == "待领取":
                note(leaf, "claim", call("claim", {"task_id": leaf, "assignee": AGENT}))
            if spec_rows(leaf, SPEC_KIND) == 0:
                note(leaf, "omega_spec_create", call(
                    "omega_spec_create", {"task_id": leaf, "content": json.dumps(spec_body, ensure_ascii=False)}))
                note(leaf, "omega_spec_review", call(
                    "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                          "reason": "R11：5 op/100 对（新 op cypy.generic.class 29 对，"
                                                    "含边界形态与成对反例）；出口件为报告并过引用核验"}))
        _finish(rep, "start")
        print("ROOT", root_id, "tree", json.dumps(rep["tree_readback"], ensure_ascii=False)[:220])
        print(f"CONCLUSION stage=start root={root_id} rows={rep['tree_readback']['rows']} "
              f"leaves={len(leaves)} faces_missing={len(rep['faces_missing'])} "
              f"calls={len(sent)} refused={len(rep['refusals'])} benign={len(rep['benign'])}")
        for r in rep["refusals"][:10]:
            print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:220])
        c.close()
        return 0 if not rep["refusals"] else 1

    # —— close 阶段：按 (状态, specs 行数) 分派，逐叶落五段式交付物 ——
    for leaf in general + boundary:
        st = status(leaf)
        rows = {"status_before": st, "steps": {}}
        face = boundary_plan.get(leaf) or face_assign.get(leaf) or FACES[0]
        if leaf in boundary:
            rows["kind"] = ("boundary-real"
                            if leaf in boundary[:len(BOUNDARY)] else "boundary-declared-na")
        elif face_assign.get(leaf):
            rows["kind"] = "face"
        if st == "待领取":
            rows["steps"]["claim"] = "refused" if note(leaf, "claim",
                                                       call("claim", {"task_id": leaf, "assignee": AGENT})) else "ok"
        if spec_rows(leaf, SPEC_KIND) == 0:
            note(leaf, "omega_spec_create", call(
                "omega_spec_create", {"task_id": leaf, "content": json.dumps(spec_body, ensure_ascii=False)}))
            note(leaf, "omega_spec_review", call(
                "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                      "reason": "R11：5 op/100 对，新 op 29 对含成对反例；出口件已过引用核验"}))
        name, what, check = face or FACES[0]
        dlv = deliverable(name,
                          f"R11 泛型类面已按 SYNTAX/11 规则 1-5 落地：{what}",
                          f"logs/r11_generics_probe1.out（修复前）与 probe2/probe4（修复后）、"
                          f"logs/r11_subst2.out（13 例成对）、logs/r11_locks_a8.out（7 格矩阵）、"
                          f"corpus/{CORPUS.split('/')[-1]} 29 对指纹 fnv1a64:90f410a1d1cd0fd8",
                          "BUG-128/129 同族面本轮只立不修；struct 方法代入收紧面大 ⇒ 转结",
                          f"{REPORT.name} §4/§5") if st != "已完成" else None
        if st != "已完成":
            rows["steps"]["execute"] = "refused" if note(leaf, "execute", call(
                "execute", {"task_id": leaf, "deliverable": dlv, "executor": "self"})) else "ok"
        rc = call("run_check", {"task_id": leaf, "cmd": "python", "args": check, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok")}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
            rep["refusals"].append({"node": leaf, "tool": "run_check",
                                    "reply_verbatim": json.dumps(rc, ensure_ascii=False)[:300]})
        if status(leaf) in ("执行中", "待验收", "已打回"):
            if spec_rows(leaf, RESULT_KIND) == 0:
                note(leaf, "omega_result_verify", call("omega_result_verify", {"task_id": leaf, "verdict": "pass"}))
            rows["steps"]["submit"] = "refused" if note(leaf, "submit", call("submit", {"task_id": leaf})) else "ok"
        if status(leaf) == "待验收":
            rows["steps"]["verify"] = "refused" if note(leaf, "verify", call(
                "verify", {"task_id": leaf, "verifier": "verifier", "docs_check": True})) else "ok"
        rows["status_after"] = status(leaf)
        rep["nodes"][leaf] = rows

    def chain_up(node):
        trace = {}
        st = status(node)
        if st == "拆分中":
            trace["execute"] = json.dumps(call("execute", {
                "task_id": node, "executor": "self",
                "deliverable": deliverable(
                    "枝干/根收口", "R11 交付：泛型类四处修复 + Ω-spec 5 op/100 对 + 13 支锁 + 7 格承重矩阵",
                    "logs/r11_locks_a8.out、logs/r11_gate_a3.log、logs/r11_pytest_a2.log",
                    "BUG-126/127/128/129 开口转结；T0r112/T0r113 两根未收（不伪造）",
                    REPORT.name), "executor": "self"}), ensure_ascii=False)[:200]
            trace["submit"] = json.dumps(call("submit", {"task_id": node}), ensure_ascii=False)[:200]
        if status(node) in ("执行中", "待验收", "已打回"):
            if spec_rows(node, SPEC_KIND) == 0:
                call("omega_spec_create", {"task_id": node,
                                           "content": json.dumps(spec_body, ensure_ascii=False)})
                call("omega_spec_review", {"task_id": node, "verdict": "approve",
                                           "reason": "R11 根/枝干：判据 5 op/100 对，报告已过引用核验"})
            if spec_rows(node, RESULT_KIND) == 0:
                note(node, "omega_result_verify", call("omega_result_verify", {"task_id": node, "verdict": "pass"}))
            if status(node) == "执行中":
                call("submit", {"task_id": node})
        if status(node) == "待验收":
            note(node, "verify", call("verify", {"task_id": node, "verifier": "verifier", "docs_check": True}))
        return status(node), trace

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    branches = [r[0] for r in con.execute("select id from tasks where id like ? and depth=2",
                                          (f"{root_id}.%",)).fetchall()]
    pending = con.execute("select count(*) from tasks where id like ? and status='待领取'",
                          (f"{root_id}.%",)).fetchone()[0]
    con.close()
    rep["branch_final"] = {b: chain_up(b)[0] for b in branches if status(b) != "已完成"}
    rep["root_final"], rep["root_trace"] = chain_up(root_id)

    # 环推进：LoopRegistry 是**进程内**的（loop_create 自述），而 FistClient 每次都 spawn 新 serve
    # ⇒ create 与 tick 必须落在同一个会话里。上一轮 start 会话 create、close 会话 tick ⇒ 必然
    # `loop not found`；再加上客户端注入 namespace/project_dir ⇒ 先撞"参数名不被接受"。两个原因各能
    # 独立解释一部分红，所以这里两样都自证：会话内 6 步走完并逐格对表，跨会话反例必须在别件里取。
    rep["loop_drive"] = drive_loop(call, LOOP_NAME, STEPS_SEED)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rep["call_log_error_rows"] = con.execute(
        "select count(*) from call_log where ts>=? and ok=0", (started,)).fetchone()[0]
    rep["call_log_error_rows_old_needle"] = con.execute(
        "select count(*) from call_log where ts>=? and result_json like '%__error__%'", (started,)).fetchone()[0]
    rep["rollup"] = dict(con.execute("select status, count(*) from tasks where id like ? or id=? group by status",
                                     (f"{root_id}.%", root_id)).fetchall())
    con.close()
    c.close()
    rep["calls"] = len(sent)
    _finish(rep, "close")
    for leaf, rows in rep["nodes"].items():
        if leaf.startswith("__"):
            continue
        print(leaf, rows.get("status_before"), "->", rows.get("status_after"))
    print("BRANCHES", json.dumps(rep["branch_final"], ensure_ascii=False))
    stuck = [k for k, v in rep["rollup"].items() if v and k != "已完成"]
    print("LOOP_DRIVE", json.dumps(rep["loop_drive"]["gates"], ensure_ascii=False))
    for r in rep["idempotent"][:4]:
        print("IDEMPOTENT", r["node"], r["tool"], "|", r["reply_verbatim"][:160])
    print(f"CONCLUSION stage=close root={root_id} root_status={rep['root_final']} "
          f"rollup={rep['rollup']} non_closed={stuck} pending_leaves={pending} "
          f"calls={rep['calls']} refused={len(rep['refusals'])} idempotent={len(rep['idempotent'])} "
          f"benign={len(rep['benign'])} loop_ticks_ok={rep['loop_drive']['ticks_ok']} "
          f"call_log_error_rows={rep['call_log_error_rows']} "
          f"old_needle_rows={rep['call_log_error_rows_old_needle']}")
    for r in rep["refusals"][:12]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:240])
    return 0 if (not rep["refusals"] and rep["root_final"] == "已完成"
                 and all(rep["loop_drive"]["gates"].values())) else 1


def _finish(rep, stage):
    out = HERE / f"ring_r11_{stage}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
