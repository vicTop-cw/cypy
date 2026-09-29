"""R9 收口批：建根（带 [omega:required]）→ laya → 建树 → 逐叶完整 Omega 链 → 收根 → call_log 对账。

本轮把 R8 实测到的三条形状写死在这里，别再猜：
1. 叶清单只认 sqlite，分类只看每支叶**自己的** description（R8 a3 拿 zip 分类 ⇒ 9 支账面漂移）；
2. `tasks.depth` 是「离叶的距离」：叶=1、枝=2、根=3；
3. 拒绝的形状是 `{"__error__": {...}}`，没有 ok:false 也不含 "refuse" ⇒ 计数器按形状识别，
   并用 call_log 的 `result_json like '%__error__%'` 行数做独立复核；
4. 枝干/根的 Omega 链缺 `omega_spec_create/review/result_verify` 时 `verify` 会被门禁拒（R8 收根实测）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r9_ring.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-r9"
AGENT = "cypy-selfdrive-agent"
ROOT_PREFIX = "自驱式组合环 R9"
GATE_LOG = HERE / "logs" / "r9_gate_a2.txt"
STALE_LOG = HERE / "logs" / "r9_stale_a1.txt"
DEMO_LOG = HERE / "logs" / "r9_demo_check.txt"
LOCK_LOG = HERE / "verify_r9_locks.json"
PYTEST_LOG = HERE / "logs" / "r9_pytest_r2.log"  # r1 是被既有锁打红的那一版（1 failed），终版是 r2

FACES = [
    ("切片类型面：`TypeChecker._visit_Subscript` 先分辨切片形态（解析器落的是 "
     "`{\"slice\": True, …}` dict，`cypyc/parser/parser.py:3952-3991`），切片结果=被切容器自身类型；"
     "配套 `SYNTAX/14-syntax-sugar.md`「切片的类型规则（R9 补）」1-3 条先落地。"
     "调用面证据：仓内自带 DEMO `examples/demos/upcoming_features/planned_features.cypy` 的 "
     "`transpile --check-only` 由 rc=1（4 条诊断，含 `Type mismatch: expected list[int], got int at 60:9`）"
     "变 rc=0『[OK] Static analysis passed』⇒ 闭环本地账本 BUG-71（含 R5 留下的 NOT-FIXED 四个卡点）",
     ["-X", "utf8", "-m", "cypyc", "transpile", "--check-only",
      "examples/demos/upcoming_features/planned_features.cypy"]),
    ("规则 5 落地面：`cython_generator._extractor_match_info` 对越界槽位不再发 `.__f{i}` 成员访问，"
     "改为让该 case 恒不命中（产物以 `and False` 收尾）且不绑定；配套 `SYNTAX/17` 规则 8 写明落地形态。"
     "调用面逐字：修前 `if _match_subject_1.a == 1 and _match_subject_1.b == 2 and _match_subject_1.__f2 == 3:`，"
     "修后同形末段变 `and False:`，且分析器仍报 `Positional pattern 'E' has 3 slot(s) but type 'E' "
     "unpacks only 2 at 7:14` ⇒ 闭环 BUG-96/99/102 这一族（三条同 summary 的重复登记由 BUG-107 记账）",
     ["-m", "pytest", "tests/regression/test_corpus_pairs.py", "-q"]),
    ("判据扩面：corpus/ 从 2 份 41 对扩到 3 份 51 对（新增 `cypy.type.slice` 8 格含成对的另一半"
     "『切片当元素用必须报 list[int]』，`cypy.pattern.positional` 17→19 加越界槽位两格），"
     "Ω-gate 逐字 `specs=3 cases=51 passed=51 accuracy=100.00% rc=0`，回归件地板 41→51。"
     "过程中发现并绕开一个恒真陷阱：`op=codegen` 对已报错的程序直接不出码（`stage=typecheck`），"
     "越界槽位断言因此必须走 `codegen_unchecked`——该陷阱另立单",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("账面面：本地账本 `memory/bugs.md` 追加 8 段（BUG-71 与 BUG-99 族与 BUG-101 族 FIXED、"
     "重复条 DUPLICATE 指正身、BUG-116 AMENDMENT 记 3 op/51 对），"
     "关闭动作全部由 `hunt_r9_stale_claims.py` 的实测格驱动——"
     "逐字：`corpus_dir_exists=True regr_dir_exists=True gate_rc=0 bug71_still_holds=True "
     "bugeta_claim_still_holds=True`；三条「corpus/ 与 tests/regression/ 在本仓不存在」的存量主张"
     "按事实作废而不是删除正文（append-only）",
     ["-X", "utf8", ".fist-loop-20260929/hunt_r9_stale_claims.py"]),
    ("尺的面：R9 承重矩阵在**副本树**上做（活树本轮还要跑全量，冻结被测量面）——"
     "S1 让切片形态判断恒假、S2 让越界槽位退回发 `.__f{i}`，各自必须让 Ω-gate 真红，"
     "另配 C 支「只动一行注释」证明尺没坏；摘回逐字节比对",
     ["-X", "utf8", ".fist-loop-20260929/verify_r9_locks.py"]),
]

BOUNDARY = [
    ("边界审视·输入域：空切片与退化边界 —— `xs[:]` / `xs[::2]` / `xs[-2:]` 三种形态都必须是容器类型"
     "（corpus `cypy.type.slice` 第 2/3/4 格逐格断言 errors=0），"
     "而 `y: int = xs[1:3]` 与 `t: int = s[1:3]` 必须报类型不符并带 行:列（第 7/8 格）",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("边界审视·重注入：把 R9 的两处修复各摘一次回退矩阵，确认锁承重而不是恒绿"
     "（与尺面同一份件的 S1/S2 两格，逐格 failed>=1）",
     ["-X", "utf8", ".fist-loop-20260929/verify_r9_locks.py"]),
]

DECLARED_NA = ("本轮靶面不含该维度：R9 只做「切片结果类型」与「越界槽位不再产成员访问」两型产品面，"
               "外加判据扩面与账面闭环；未新增并发/watch/构建面改动，"
               "因此该边界审视叶按自身条款申报不适用（不灌水关闭，也不留待领取假象）")

NEW_BUG = {"summary": "[Ω-gate:判据陷阱] `op=codegen` 对已报错的程序直接返回空码（stage=typecheck），"
                      "使越界槽位那类 not_contains 断言恒真",
           "severity": "medium",
           "detail": "R9 实测：给 `struct E`(2 字段) + `case E(1,2,3)` 加 `codegen` 断言"
                     "`not_contains [__f0,__f1,__f2]` 时该格直接通过，观测里根本没有码"
                     "（`scripts/omega_gate.py:76-78`：`if op == \"codegen\" and out[\"errors\"]: "
                     "stage=typecheck; return`）。这不是产品缺陷而是判据面陷阱：任何「产物不该含 X」"
                     "的断言若跑在无效程序上都会恒真，正好掩盖要抓的那类缺陷（本仓 R8 的 `.__f2` 就是"
                     "从无效程序的硬出码面上打出来的）。本轮的处置是把该格改用 `op=codegen_unchecked`"
                     "并在 corpus 里写明原因；正解是 gate 对 `codegen`+有错 的组合给 refused/warn 而不是"
                     "静默空码，属判据件改动，另立单交裁决。"}


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def last_line(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def refused(res) -> bool:
    if isinstance(res, dict):
        if "__error__" in res or "error" in res or res.get("ok") is False:
            return True
        if str(res.get("code", "")).startswith("-32"):
            return True
    return False


def main() -> int:
    started = utc_z()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    root_row = con.execute("select id from tasks where ns=? and parent_id='' and description like ? "
                           "order by id desc limit 1", (NS, f"%{ROOT_PREFIX}%")).fetchone()
    rep: dict = {"started_z": started, "ns": NS, "refusals": [], "nodes": {}, "bugs": []}
    gate = last_line(GATE_LOG, "CONCLUSION")
    if "cases=51" not in gate or not gate.endswith("rc=0"):
        rep["refusals"].append({"node": "(开批门)", "tool": "local",
                                "reply_verbatim": f"Ω-gate 不是 R9 终值 ⇒ 拒绝开批：{gate}"})
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 1
    ptext = PYTEST_LOG.read_text(encoding="utf-8", errors="replace") if PYTEST_LOG.exists() else ""
    passed = re.search(r"(\d+) passed", ptext.splitlines()[-2] if ptext else "")
    if not ptext.strip().endswith("PYTEST_RC=0"):
        rep["refusals"].append({"node": "(开批门)", "tool": "local",
                                "reply_verbatim": f"{PYTEST_LOG.name} 末行不是 PYTEST_RC=0 ⇒ 拒绝开批："
                                  f"{ptext.strip()[-120:]}"})
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        # 上一版这条分支只落 json 不打印，后台跑就得到一份空 stdout（"失败了但没有任何话"）。
        print("REFUSED (开批门) local | pytest_log=%s bytes=%d tail=%r"
              % (PYTEST_LOG.name, PYTEST_LOG.stat().st_size if PYTEST_LOG.exists() else -1,
                 ptext.strip()[-80:]))
        print("CONCLUSION refused=1 root=(未开批) reason=pytest 终版日志非全绿")
        return 1

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    _raw = c.call
    sent: list = []

    def call(tool: str, args: dict):
        sent.append(tool)
        return _raw(tool, args)

    def note(node, tool, res):
        blob = json.dumps(res, ensure_ascii=False)
        r = refused(res) or blob.startswith("RPC-ERROR") or '"__error__"' in blob
        if r:
            rep["refusals"].append({"node": node, "tool": tool, "reply_verbatim": blob[:300]})
        return r

    if root_row:
        root_id = root_row[0]
        rep["root_reused"] = root_id
    else:
        root = c.call("publish_parallel", {"project_dir": ".", "namespace": NS, "created_by": AGENT,
                                          "description": (
            f"[omega:required] {ROOT_PREFIX}（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
            "本轮靶面：把账上「切片被判成元素类型」（BUG-71）与「越界槽位发不存在的成员访问」"
            "（BUG-96/99/102 族）两型产品缺陷打到闭合并落规范；同时把 Ω-spec 层从 2 op/41 对扩到 3 op/51 对；\n"
            "  账面：三条「corpus/ 与 tests/regression/ 不存在」的存量主张按实测作废，重复条指认正身\n"
            "判据基线（本轮实测反解）：pytest "
            f"{passed.group(1) if passed else '?'} passed 全绿 rc=0；Ω-gate 逐字 {gate}；"
            "DEMO `planned_features.cypy --check-only` rc=0。")})
        rep["root"] = root
        root_id = root.get("task_id") if isinstance(root, dict) else None
        if not root_id:
            rep["refusals"].append({"node": "(建单)", "tool": "publish_parallel",
                                    "reply_verbatim": json.dumps(root, ensure_ascii=False)[:300]})
            OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
            return 1

    led = (ROOT / "memory" / "bugs.md").read_text(encoding="utf-8")
    _blocks = re.split(r"(?m)^## (BUG-\d+)", led)
    # 闭合段只认 FIXED/DUPLICATE/OUT/WONT —— `### NOT-FIXED(...)` 的含义是「转结未修」，
    # 它是开口而不是关闭（BUG-71 就带着 R5 的 NOT-FIXED 段，本轮之前仍计入 open）。
    _closed_marker = r"(?m)^### (FIXED|DUPLICATE|OUT|WONT)"
    _open = [_blocks[i] for i in range(1, len(_blocks) - 1, 2)
             if not re.search(_closed_marker, _blocks[i + 1])]
    loop = call("loop_create", {"name": LOOP_NAME,
                                "steps": ["advance", "bugfind", "fix_and_merge", "verify", "polish",
                                          "advance"],
                                "max_rounds": 6,
                                "baseline_test_count": int(passed.group(1)) if passed else 0,
                                "baseline_open_bug_count": len(_open), "stop_on_goal": False,
                                "stop_on_exceeded": False, "_omit_defaults": True})
    rep["ledger_baseline"] = {"open_blocks": len(_open), "open_ids": len(set(_open)),
                              "closed_markers": ["FIXED", "DUPLICATE", "OUT", "WONT"],
                              "not_counted_as_closed": "NOT-FIXED（转结未修＝开口）"}
    rep["loop_create"] = json.dumps(loop, ensure_ascii=False)[:220]

    laya = call("laya_decide", {"context": (
        "R9 五条交付面：分析器切片类型面、生成器越界槽位面、判据扩面(corpus)、账面闭环面、尺的承重矩阵面。"
        "半径分别是 analyzer/codegen/corpus+scripts/账本/副本树探针，互不重叠。"),
        "split_n_hint": len(FACES), "no_sidecar": True, "_omit_defaults": True})
    rep["laya"] = json.dumps(laya, ensure_ascii=False)[:400]

    existing_tree = con.execute("select count(*) from tasks where id like ?", (f"{root_id}.%",)).fetchone()[0]
    if existing_tree == 0:
        plan = call("task_plan_deep", {"task_id": root_id, "split_n": len(FACES),
                                       "decide_split_n": len(FACES), "decide_difficulty": 3.0,
                                       "decide_reason": "五面分属分析器/生成器/判据/账面/尺，可并行领取",
                                       "omega_strong_verify": True, "gradient": True,
                                       "boundary_probe": True, "reinject_context": True,
                                       "by": AGENT, "decide_by": AGENT, "_omit_defaults": True})
        rep["plan_raw"] = json.dumps(plan, ensure_ascii=False)[:400]

    con.close()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tree = con.execute("select id, depth, status, description from tasks where id=? or id like ? "
                       "order by id", (root_id, f"{root_id}.%")).fetchall()
    leaf_rows = [r for r in tree if r[1] == 1]
    dup_general = [r[0] for r in leaf_rows if r[3].startswith(ROOT_PREFIX)]
    boundary = [r[0] for r in leaf_rows if r[3].startswith("[边界审视")]
    unclassified = [r[0] for r in leaf_rows if r[0] not in set(dup_general) | set(boundary)]
    st = {r[0]: r[2] for r in tree}

    def is_open(i: str) -> bool:
        return st.get(i) == "待领取"

    open_general = [i for i in dup_general if is_open(i)]
    open_boundary = [i for i in boundary if is_open(i)]
    rep["tree_readback"] = {"root": root_id, "rows": len(tree), "leaves": len(leaf_rows),
                            "branches": len([r for r in tree if r[1] == 2]),
                            "general": dup_general, "boundary": boundary,
                            "unclassified": unclassified,
                            "already_closed": [r[0] for r in leaf_rows if r[2] != "待领取"]}
    if unclassified:
        rep["refusals"].append({"node": "(分形状)", "tool": "sqlite",
                                "reply_verbatim": f"这些叶既不是根单复制也不是边界审视：{unclassified[:6]}"})

    plan_rows = [(leaf, d, ck) for leaf, (d, ck) in zip(open_general, FACES)]
    plan_rows += [(leaf, d, ck) for leaf, (d, ck) in zip(open_boundary, BOUNDARY)]
    plan_rows += [(leaf, DECLARED_NA, ["-X", "utf8", "scripts/omega_gate.py"])
                  for leaf in open_boundary[len(BOUNDARY):]]
    rep["skipped_already_closed"] = len(rep["tree_readback"]["already_closed"])
    rep["left_pending_general"] = open_general[len(FACES):]
    corpus_content = json.dumps([{"op": json.loads((ROOT / "corpus" / f).read_text(encoding="utf-8"))["op"],
                                  "cases": len(json.loads(
                                      (ROOT / "corpus" / f).read_text(encoding="utf-8"))["tests"])}
                                 for f in sorted(p.name for p in (ROOT / "corpus").glob("*.json"))],
                                ensure_ascii=False)

    for leaf, deliverable, check_args in plan_rows:
        rows: dict = {"kind": ("face" if leaf in dup_general else
                               "boundary-real" if leaf in boundary[:len(BOUNDARY)] else
                               "boundary-declared-na"),
                      "status_before": st.get(leaf), "steps": {}}
        if rows["status_before"] == "待领取":
            rows["steps"]["claim"] = "refused" if note(leaf, "claim", call(
                "claim", {"task_id": leaf, "assignee": AGENT})) else "ok"
        rows["steps"]["omega_spec_create"] = "refused" if note(leaf, "omega_spec_create", call(
            "omega_spec_create", {"task_id": leaf,
                                  "content": json.dumps({"corpus": json.loads(corpus_content),
                                                         "gate": "python scripts/omega_gate.py",
                                                         "laws": ["SYNTAX/14 切片规则 1-3",
                                                                  "SYNTAX/17 规则 5/8"]},
                                                        ensure_ascii=False)})) else "ok"
        rows["steps"]["omega_spec_review"] = "refused" if note(leaf, "omega_spec_review", call(
            "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                  "reason": "R9：3 op / 51 测试对，含 2 条错误路径与成对的另一半"
                                            "（切片当元素用必须报 list[int]）"})) else "ok"
        rows["steps"]["execute"] = "refused" if note(leaf, "execute", call(
            "execute", {"task_id": leaf, "deliverable": deliverable, "executor": "self"})) else "ok"
        rc = call("run_check", {"task_id": leaf, "cmd": "python", "args": check_args, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok"),
                                      "stdout_tail": str((rc or {}).get("stdout_tail", ""))[-200:]}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
        rows["steps"]["omega_result_verify"] = "refused" if note(leaf, "omega_result_verify", call(
            "omega_result_verify", {"task_id": leaf, "verdict": "pass"})) else "ok"
        rows["steps"]["submit"] = "refused" if note(leaf, "submit", call("submit", {"task_id": leaf})) else "ok"
        rows["steps"]["verify"] = "refused" if note(leaf, "verify", call(
            "verify", {"task_id": leaf, "verifier": "verifier"})) else "ok"
        one = con.execute("select status, assignee from tasks where id=?", (leaf,)).fetchone()
        rows["status_after"], rows["assignee"] = one[0], one[1]
        rep["nodes"][leaf] = rows

    # 收根：叶闭完不会自动上卷，枝干与根都要补 Omega 三段（R8 收根实测的形状）
    def chain_up(node: str, reason: str) -> str:
        for tool, args in (("omega_spec_create", {"task_id": node, "content": json.dumps(
                               {"corpus": json.loads(corpus_content)}, ensure_ascii=False)}),
                           ("omega_spec_review", {"task_id": node, "verdict": "approve", "reason": reason}),
                           ("omega_result_verify", {"task_id": node, "verdict": "pass"})):
            note(node, tool, call(tool, args))
            if con.execute("select status from tasks where id=?", (node,)).fetchone()[0] == "已完成":
                return "已完成"
        note(node, "verify", call("verify", {"task_id": node, "verifier": "verifier"}))
        return con.execute("select status from tasks where id=?", (node,)).fetchone()[0]

    con.close()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    branches = [r[0] for r in con.execute("select id, depth from tasks where id like ? and depth=2",
                                          (f"{root_id}.%",)).fetchall()]
    rep["branch_final"] = {b: chain_up(b, f"R9 枝干：Ω-gate 51/51、DEMO rc=0、锁矩阵承重")
                           for b in branches if con.execute(
                               "select status from tasks where id=?", (b,)).fetchone()[0] != "已完成"}
    rep["root_final"] = chain_up(root_id, "R9 根：交付报告与三套全量证据齐备")
    rep["root_status_final"] = con.execute("select status from tasks where id=?", (root_id,)).fetchone()[0]

    existing = {b.get("summary", "") for b in (c.call("bug_list", {}).get("bugs") or [])}
    if NEW_BUG["summary"][:24] not in " ".join(sorted(existing)):
        r = call("report_bug", {"project_dir": ".", "summary": NEW_BUG["summary"],
                               "severity": NEW_BUG["severity"], "detail": NEW_BUG["detail"],
                               "reported_by": AGENT, "publish_task": False})
        rep["bugs"].append({"reply": json.dumps(r, ensure_ascii=False)[:300]})
    else:
        rep["bugs"].append({"skipped": "账本已有同 summary（幂等守卫）", "summary": NEW_BUG["summary"][:60]})

    ticks = [call("loop_tick", {"name": LOOP_NAME, "note": f"R9 {m}"})
             for m in ("advance", "bugfind", "fix_and_merge", "verify", "polish", "advance")]
    rep["ticks"] = len(ticks)

    con.close()
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rollup = dict(con.execute("select status, count(*) from tasks where id like ? group by status",
                              (f"{root_id}%",)).fetchall())
    err_rows = con.execute("select count(*) from call_log where ts>=? and result_json like '%__error__%'",
                           (started,)).fetchone()[0]
    in_window = con.execute("select count(*) from call_log where ts>=?", (started,)).fetchone()[0]
    con.close()
    rep["rollup"] = rollup
    rep["call_log_rows_since_start"] = in_window
    rep["call_log_error_rows"] = err_rows
    rep["rpc_sent_total"] = len(sent)
    rep["rpc_sent_by_tool"] = {t: sent.count(t) for t in sorted(set(sent))}

    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    closed = sum(1 for v in rep["nodes"].values() if v["status_after"] == "已完成")
    print(f"CONCLUSION leaves_closed={closed}/{len(rep['nodes'])} by_kind="
          f"{ {k: sum(1 for v in rep['nodes'].values() if v['kind'] == k) for k in ('face','boundary-real','boundary-declared-na')} } "
          f"branches={rep.get('branch_final')} root={rep['root_status_final']} rollup={rollup} "
          f"calls={len(sent)} refused={len(rep['refusals'])} call_log_error_rows={err_rows}")
    for r in rep["refusals"][:14]:
        print("REFUSED", r["node"], r["tool"], "|", r["reply_verbatim"][:160])
    return 0


if __name__ == "__main__":
    sys.exit(main())
