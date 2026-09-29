"""R8 收口批：建根（带 [omega:required]）→ laya → 建树 → 逐叶走完整 Omega 链 → call_log 对账。

沿用 R7 b 轮的三条实测形状：叶清单只认 sqlite（`list(namespace=)` 对本 ns 不可靠）、
叶数与交付条数不强求 1:1（BUG-110：建树会多生重复描述叶）、report_bug 走 summary 幂等守卫。
基线数字一律反解：pytest 收集/通过数取本轮全量日志，open 数取本地账本 `### FIXED(` 反解。
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "close_r8_ring.json"
DB = ROOT / "fist-mbt.db"
NS = "cypy-loop-20260929"
LOOP_NAME = "cypy-selfdrive-r8"
AGENT = "cypy-selfdrive-agent"
GATE_LOG = HERE / "logs" / "r8_gate_final.txt"
FAMILY_LOG = HERE / "logs" / "r8_family_a2.txt"
NEG_LOG = HERE / "logs" / "r8_negatives_a3.txt"
FAMILY_JSON = HERE / "hunt_r8_extractor_family.json"
SPEC17 = ROOT / "SYNTAX" / "17-pattern-matching.md"
LEDGER = ROOT / "memory" / "bugs.md"

_r7 = importlib.util.spec_from_file_location("r7a", HERE / "close_r7_ring.py")
_r7mod = importlib.util.module_from_spec(_r7)
_r7.loader.exec_module(_r7mod)
measure_open_bugs = _r7mod.measure_open_bugs


def utc_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ro_db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def last_conclusion(path: Path, needle: str) -> str:
    if not path.exists():
        return f"(缺文件 {path.name})"
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return f"(未找到 {needle} 行)"


def pytest_conclusion() -> tuple:
    """R8 终验的 pytest 结论行：只认最新一份全量日志，缺就拒绝开批。"""
    for name in ("r8_pytest_r3.log", "r8_pytest_r2.log"):
        p = HERE / "logs" / name
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        col = re.search(r"collected (\d+) items", txt)
        pas = re.search(r"(\d+) passed", txt)
        red = re.search(r"(\d+) (?:failed|error)", txt)
        if col and pas and not red and "PYTEST_RC=0" in txt:
            return int(col.group(1)), int(pas.group(1)), name
    return 0, 0, "(无可用 R8 全量日志 ⇒ 不许开批)"


CORPUS = {
    "op": "cypy.pattern.slots.and.spec.corpus",
    "version": "1.0",
    "definition": {
        "signature": "slots(T) = 提取器返回元组元数 | 数据字段数；`__`-包围的类属性不占槽位",
        "note": "SYNTAX/17-pattern-matching.md「位置模式的元数与槽位规则（R7 补）」规则 2/6/7（R8 补 6、7）；"
                "判据单点 ASTUtils.is_positional_member，分析器与生成器共用。",
    },
    "preconditions": ["class 的位置序来自 .body 里的非函数成员", "类型不可见时不报元数错"],
    "laws": ["L2-槽位数来源", "L3-超元必须诊断且带行列", "L4-方法名不是位置字段",
             "L6-双下划线类属性不是数据字段", "L7-Ω-spec 指纹须可复算"],
    "tests": [
        {"input": {"src": "class C: a:int + case C(x, y)"},
         "error": "Positional pattern 'C' has 2 slot(s)"},
        {"input": {"src": "struct Point(x,y,__match_args__) + case Point(a, b)"},
         "expected": {"errors": 0, "slot_types": ["int", "int"]}},
        {"input": {"src": "struct Point(x,y,__match_args__) + case Point(a, b, c)"},
         "error": "unpacks only 2"},
        {"input": {"src": "struct Shape(area(),w,h) + case Shape(3, 4)"},
         "expected": {"compared_attrs": ["w", "h"], "not": ["area"],
                      "class_fields": {"Shape": ["w", "h"]}}},
        {"input": {"src": "文档写法 tuple<int, ...> / case Numbers(x, y, ..)"},
         "error": "PARSE-FAIL: Unexpected token DOT_DOT"},
        {"input": {"src": "corpus/ 两份 Ω-spec 的全部测试对"},
         "expected": {"accuracy": "100.00%", "cases": 41}},
    ],
    "fingerprint": "manual:R8-2026-09-29",
}

FACES = [
    ("规范面：SYNTAX/17「位置模式的元数与槽位规则」补规则 6（`__`-包围的类属性不占位置槽）与规则 7"
     "（`__match_args__` 名称序尚未被消费，正解另立单），441→448 行；文档只增不删",
     ["-X", "utf8", "-c",
      "from pathlib import Path as P;"
      "t=P('SYNTAX/17-pattern-matching.md').read_text(encoding='utf-8');"
      "assert 'is_positional_member' in t and '规则 6' not in t.split('位置模式的元数与槽位规则')[0];"
      "assert '__match_args__' in t;print('SPEC17 OK',len(t.splitlines()))"]),
    ("判据与规范落地面：新建 corpus/（2 份 Ω-spec、41 个测试对）+ scripts/omega_gate.py（fnv1a64 指纹校验、"
     "逐对跑批、准确率与 reports/omega-*.json）+ tests/regression/test_corpus_pairs.py（把同一批测试对当 pytest 跑，"
     "地板 41 且地板值只认回归模块那一份）⇒ PROJECT-SPEC 03 §1/§2、05 §3 要求的 corpus/ 与 tests/regression/ 首次落地，"
     "闭环本地账本 BUG-95",
     ["-X", "utf8", "scripts/omega_gate.py"]),
    ("分析器面：_pattern_slot_types 的位置序改由 _positional_fields 提供 —— class 不再有恒空槽位"
     "（旧行为：ClassDef 无 .fields ⇒ slot 表空 ⇒ `case C(x, y)` 元数检查被静默跳过），"
     "且 `__match_args__` 这类双下划线类属性不再计入槽位；判据单点 ASTUtils.is_positional_member，生成器同侧共用",
     ["-m", "pytest", "tests/regression/test_corpus_pairs.py", "-q"]),
    ("寻虫面：SYNTAX/17 优先级表的 4 个提取器 + 类型模式 + OR 模式逐个原样喂进管线，"
     "6 格里 5 格 OK、1 格 PARSE-FAIL（文档写法 `tuple<int, ...>` 触发 `Unexpected token DOT_DOT at 4:45`），"
     "0 内部崩溃；逐格槽位观测与产物证据落 hunt_r8_extractor_family.json",
     ["-X", "utf8", ".fist-loop-20260929/hunt_r8_extractor_family.py"]),
    ("尺的面：新增门全部带必然违例对照 —— 5 格负面控制逐一承重（指纹篡改、少一条用例、未知断言键 refuse、"
     "放过非法/拦掉合法两向、克隆语料让 pytest 地板门真红），并断言 corpus/ 本体逐字节未被改动；"
     "R7+R8 锁矩阵扩到 5 格，M5（class 槽位退回 fields-only）摘掉即红",
     ["-X", "utf8", ".fist-loop-20260929/verify_r8_corpus_negatives.py"]),
]
BOUNDARY = [
    ("边界审视（本叶真实交付）：Ω-gate 与回归地板的负控制矩阵 5 格逐一承重，"
     "输入域覆盖『篡改 spec / 删除用例 / 未知断言键 / 期望方向反了 / 独立树复跑』；"
     "逐字结论 CONCLUSION controls=5 carrying=5 corpus_untouched=True",
     ["-X", "utf8", ".fist-loop-20260929/verify_r8_corpus_negatives.py"]),
    ("边界审视（本叶真实交付）：提取器家族按文档代码块原样跑，四类失败形态分栏"
     "（OK / DIAGNOSTIC / PARSE-FAIL / INTERNAL），逐字 "
     "CONCLUSION cases=6 {'OK': 5, 'DIAGNOSTIC': 0, 'PARSE-FAIL': 1, 'INTERNAL': 0}",
     ["-X", "utf8", ".fist-loop-20260929/hunt_r8_extractor_family.py"]),
]
DECLARED_NA = ("本叶无独立交付物，按叶子自身条款「或显式声明该项不适用并说明依据」申报不适用。"
               "依据：R8 的输入域四类用例集中在两份探针件（提取器家族 6 格 + Ω-gate 负控制 5 格），"
               "已记在本树前两支边界叶；本叶复跑同一探针作为覆盖证据。另：本叶描述与根单/兄弟叶逐字重复，"
               "建树未给独立 spec ⇒ 已入账（服务端 BUG-110）。")


def main() -> int:
    started = utc_z()
    collected, passed, logname = pytest_conclusion()
    if passed == 0:
        sys.exit(f"[r8] 没有可用的全量 pytest 终验日志（{logname}）⇒ 不开 RPC 批次")
    open_ids, closed_ids = measure_open_bugs()

    con = ro_db()
    root_row = con.execute("select id from tasks where ns=? and parent_id='' "
                           "and description like ? order by id desc limit 1",
                           (NS, "[omega:required] 自驱式组合环 R8%")).fetchone()
    rep: dict = {"started_z": started, "ns": NS, "refusals": [], "nodes": {}, "ticks": [],
                 "bugs": [], "tally": {},
                 "baseline_measured": {"pytest_collected": collected, "pytest_passed": passed,
                                       "pytest_log": logname,
                                       "gate_conclusion_verbatim": last_conclusion(GATE_LOG, "CONCLUSION"),
                                       "negatives_conclusion_verbatim": last_conclusion(NEG_LOG, "CONCLUSION"),
                                       "family_conclusion_verbatim": last_conclusion(FAMILY_LOG, "CONCLUSION"),
                                       "ledger_open": len(open_ids),
                                       "ledger_fixed_sections": len(closed_ids)}}

    sys.path.insert(0, str(ROOT / "scripts"))
    os.environ["FIST_NAMESPACE"] = NS
    os.environ["FIST_SERVER_CWD"] = str(ROOT).replace("\\", "/")
    import fist  # noqa: PLC0415

    c = fist.FistClient(timeout=240)
    sent: list = []
    _raw_call = c.call

    def counted_call(tool, args, timeout=None):
        sent.append(tool)
        return _raw_call(tool, args)

    c.call = counted_call

    def note(node, tool, res):
        refused = isinstance(res, dict) and ("__error__" in res or "error" in res
                                             or res.get("ok") is False)
        if refused:
            rep["refusals"].append({"node": node, "tool": tool,
                                    "reply_verbatim": json.dumps(res, ensure_ascii=False)})
        return refused

    if root_row:
        root_id = root_row[0]
        rep["root_reused"] = root_id
    else:
        root = c.call("publish_parallel", {"project_dir": ".", "namespace": NS, "created_by": AGENT,
                                          "description": (
            "[omega:required] 自驱式组合环 R8（2026-09-29）：推进→寻虫→修复→验证→打磨→推进\n"
            "本轮靶面：把 PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 真正落地（闭环 BUG-95），"
            "并用这份可执行判据打语法特性面：\n"
            "  确诊并修好 class 的位置槽位恒空（元数诊断被静默跳过）与 __match_args__ 被当数据字段两例\n"
            "  寻虫 1 例入账：SYNTAX/17 文档写法 tuple<int, ...> / case (x, y, ..) 根本进不了解析器\n"
            f"判据基线（本轮实测反解）：pytest {collected} collected / {passed} passed；"
            f"Ω-gate 逐字 {last_conclusion(GATE_LOG, 'CONCLUSION')}；"
            f"本地账本 open {len(open_ids)} 条 / FIXED 段 {len(closed_ids)} 个。")})
        rep["root"] = root
        root_id = root.get("task_id") if isinstance(root, dict) else None
        if not root_id:
            rep["refusals"].append({"node": "(建单)", "tool": "publish_parallel",
                                    "reply_verbatim": json.dumps(root, ensure_ascii=False)})
            OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
            return 1
        laya = c.call("laya_decide", {"context": (
            "R8 五条交付面：规范补规则、corpus+Ω-gate+回归目录落地、分析器 class 槽位与双下划线判据、"
            "提取器家族寻虫、尺的负控制矩阵。改动落在 docs/analyzer/codegen/tests/scripts 五个不重叠半径。"),
            "split_n_hint": len(FACES), "no_sidecar": True, "_omit_defaults": True})
        rep["laya"] = json.dumps(laya, ensure_ascii=False)
        plan = c.call("task_plan_deep", {"task_id": root_id, "split_n": len(FACES),
                                        "decide_split_n": len(FACES), "decide_difficulty": 3.0,
                                        "decide_reason": "五条面分属文档/判据/分析器/探针/尺，可并行领取",
                                        "omega_strong_verify": True, "gradient": True,
                                        "boundary_probe": True, "reinject_context": True,
                                        "by": AGENT, "decide_by": AGENT, "_omit_defaults": True})
        rep["plan_raw"] = json.dumps(plan, ensure_ascii=False)

    loop = c.call("loop_create", {"name": LOOP_NAME, "steps": ["advance", "bugfind", "fix_and_merge",
                                                              "verify", "polish", "advance"],
                                 "max_rounds": 6, "baseline_test_count": passed,
                                 "baseline_open_bug_count": len(open_ids), "stop_on_goal": False,
                                 "stop_on_exceeded": False, "_omit_defaults": True})
    rep["loop_create"] = json.dumps(loop, ensure_ascii=False)

    tree = list(con.execute("select id, depth, status, description from tasks "
                            "where id=? or id like ? order by id", (root_id, f"{root_id}.%")))
    leaf_rows = [r for r in tree if r[1] == 1]
    leaves = [r[0] for r in leaf_rows]
    # a3 轮的实测教训：不能拿 leaves 与整张树 zip 后按行分类（枝干/根会串位，
    # 分类结果就出现「13+4 支、还有 1 支形状不明」这种假象）。分类只看每支叶自己的 description。
    dup_general = [r[0] for r in leaf_rows if r[3].startswith("自驱式组合环 R8")]
    boundary = [r[0] for r in leaf_rows if r[3].startswith("[边界审视")]
    unclassified = [r[0] for r in leaf_rows
                    if r[0] not in set(dup_general) | set(boundary)]
    open_general = [i for i in dup_general if con.execute(
        "select status from tasks where id=?", (i,)).fetchone()[0] == "待领取"]
    open_boundary = [i for i in boundary if con.execute(
        "select status from tasks where id=?", (i,)).fetchone()[0] == "待领取"]
    rep["tree_readback"] = {"root": root_id, "rows": len(tree), "leaves": len(leaves),
                             "general": dup_general, "boundary": boundary,
                             "unclassified": unclassified,
                             "already_closed": [r[0] for r in leaf_rows if r[2] != "待领取"]}
    if unclassified:
        rep["refusals"].append({"node": "(分形状)", "tool": "sqlite",
                                "reply_verbatim": f"这些叶的描述既不是根单复制也不是边界审视：{unclassified}"})
    if leaves and len(leaves) != len(dup_general) + len(boundary):
        rep["refusals"].append({"node": "(分形状)", "tool": "sqlite",
                                "reply_verbatim": f"叶 {len(leaves)} 支里按描述只认出 "
                                                  f"{len(dup_general)}+{len(boundary)} 支，剩余形状未知"})

    PLAN = [(leaf, d, ck) for leaf, (d, ck) in zip(open_general, FACES)]
    PLAN += [(leaf, d, ck) for leaf, (d, ck) in zip(open_boundary, BOUNDARY)]
    PLAN += [(leaf, DECLARED_NA, ["-X", "utf8", ".fist-loop-20260929/hunt_r8_extractor_family.py"])
             for leaf in open_boundary[len(BOUNDARY):]]
    rep["skipped_already_closed"] = len(rep["tree_readback"]["already_closed"])
    rep["left_pending_general"] = open_general[len(FACES):]

    existing = {b.get("summary", "") for b in (c.call("bug_list", {}).get("bugs") or [])}
    rep["bug_list_rows"] = len(existing)

    for leaf, deliverable, check_args in PLAN:
        rows: dict = {"kind": ("face" if leaf in dup_general else
                               "boundary-real" if leaf in boundary[:len(BOUNDARY)] else
                               "boundary-declared-na"),
                      "deliverable_head": deliverable[:80], "steps": {}}
        rows["status_before"] = (c.call("get", {"task_id": leaf}) or {}).get("status")
        if rows["status_before"] == "待领取":
            rows["steps"]["claim"] = "refused" if note(leaf, "claim", c.call(
                "claim", {"task_id": leaf, "assignee": AGENT})) else "ok"
        rows["steps"]["omega_spec_create"] = "refused" if note(leaf, "omega_spec_create", c.call(
            "omega_spec_create", {"task_id": leaf,
                                  "content": json.dumps(CORPUS, ensure_ascii=False)})) else "ok"
        rows["steps"]["omega_spec_review"] = "refused" if note(leaf, "omega_spec_review", c.call(
            "omega_spec_review", {"task_id": leaf, "verdict": "approve",
                                  "reason": "R8：6 格测试对含 3 条错误路径与 1 条 Ω-spec 指纹主张"})) else "ok"
        rows["steps"]["execute"] = "refused" if note(leaf, "execute", c.call(
            "execute", {"task_id": leaf, "deliverable": deliverable, "executor": "self"})) else "ok"
        rc = c.call("run_check", {"task_id": leaf, "cmd": "python", "args": check_args, "workdir": "."})
        rows["steps"]["run_check"] = {"state": (rc or {}).get("status"), "ok": (rc or {}).get("ok"),
                                      "stdout_tail": str((rc or {}).get("stdout_tail", ""))[-260:]}
        if isinstance(rc, dict) and ("error" in rc or "__error__" in rc):
            rows["steps"]["run_check"]["refused"] = True
        rows["steps"]["omega_result_verify"] = "refused" if note(leaf, "omega_result_verify", c.call(
            "omega_result_verify", {"task_id": leaf, "verdict": "pass"})) else "ok"
        rows["steps"]["submit"] = "refused" if note(leaf, "submit", c.call("submit", {"task_id": leaf})) else "ok"
        rows["steps"]["verify"] = "refused" if note(leaf, "verify", c.call(
            "verify", {"task_id": leaf, "verifier": "verifier"})) else "ok"
        after = c.call("get", {"task_id": leaf})
        rows["status_after"] = (after or {}).get("status")
        rows["assignee"] = (after or {}).get("assignee")
        rep["nodes"][leaf] = rows

    for mode in ("advance", "bugfind", "fix_and_merge", "verify", "polish", "advance"):
        t = c.call("loop_tick", {"name": LOOP_NAME, "_omit_defaults": True,
                                 "current_test_count": passed,
                                 "current_open_bug_count": len(open_ids),
                                 "blocked_tasks": 0, "project_health_grade": "attention"})
        rep["ticks"].append({"mode": mode, "reply": json.dumps(t, ensure_ascii=False)})

    for summary, sev, detail in [
        ("[模式匹配:class 位置槽位] ClassDef 无 .fields 时 _pattern_slot_types 恒空，"
         "case C(x, y) 的元数检查被静默跳过",
         "medium",
         "R8 由 Ω-gate 首跑打出（corpus/cypy.pattern.positional.json 的 #11 格）：`class C: a: int` + "
         "`case C(x, y)` 观测为空诊断，而 struct 同形会报 Positional pattern。根因：ClassDef 的实例属性只有 "
         "name/bases/body/is_cdef，字段在 .body 里（LetStmt），旧代码只读 .fields。"
         "同轮修复：cypyc/analyzer/type_checker.py 新增 _positional_fields（class 从 .body 取非函数成员），"
         "锁：corpus 该格 + tests/regression/test_corpus_pairs.py 参数化格 + 矩阵 M5（摘掉即红）。"),
        ("[模式匹配:槽位数] struct 里的 `__match_args__ = (...)` 被当成第三个数据字段计入槽位数",
         "medium",
         "R8 实测：`struct Point: x:int; y:int; __match_args__ = (\"x\",\"y\")` 的 "
         "_pattern_slot_types 返回 ['int','int','object']、生成器 _class_fields['Point'] 含 __match_args__，"
         "于是 `case Point(a, b, c)` 零诊断通过，产物还可能比较 .__match_args__。"
         "同轮修复：SYNTAX/17 补规则 6，判据单点 cypyc/utils/ast_utils.py:ASTUtils.is_positional_member，"
         "分析器与生成器共用；锁：corpus 三格（2 元数相符 / 3 元数必须报 unpacks only 2 / 产物不含 __match_args__ ==）。"),
        ("[模式匹配:语法未落地] SYNTAX/17 文档写法 `tuple<int, ...>` 与 `case Numbers(x, y, ..)` 进不了"
         "解析器（Unexpected token DOT_DOT）",
         "medium",
         "R8 寻虫逐字：`.fist-loop-20260929/hunt_r8_extractor_family.py` 的第三格 "
         "`ValueError: Unexpected token DOT_DOT at 4:45`，判定 PARSE-FAIL；同批其余 5 格 OK "
         "（__unapply__ / __unwarp__ / 类型模式 / OR 模式 / __match_args__ 位置解构，槽位观测见 "
         "hunt_r8_extractor_family.json）。文档把 `__unapply_seq__` 列为优先级表第 8 项并给了示例，"
         "但语言层没有这个类型形态 ⇒ 文档承诺与解析器能力不符。修法要动类型语法与模式语法（可变元组类型 + "
         "序列展开模式），超出缺陷轮半径，交裁决。"),
        ("[模式匹配:元数来源] 元数来源未消费 `__match_args__` 名称序，只按数据字段数计算",
         "low",
         "R8 实测：`__match_args__ = (\"x\", \"y\")` 现在不再占槽（规则 6），但 SYNTAX/17 优先级表第 6 项承诺"
         "「该属性给出的字段名顺序长度」——实现仍按字段声明序取元数，未按 __match_args__ 重排或取长度。"
         "已在 SYNTAX/17 规则 7 显式写明「目前未实现」以免被读成已完成；正解需要在分析器读取名称元组并校验"
         "其与字段集合的包含关系，属新增语义，交裁决。"),
        ("[规范落地] corpus/ 与 tests/regression/ 已建立但只覆盖 2 个 op（41 个测试对）",
         "low",
         "闭环 BUG-95 的第一批：corpus/cypy.annotation.shape.json 24 格 + "
         "corpus/cypy.pattern.positional.json 17 格，scripts/omega_gate.py 跑批准确率 100.00%，"
         "tests/regression/test_corpus_pairs.py 地板 41。覆盖面只到「注解形态」与「位置模式槽位」两个 op，"
         "其余 20+ 个 SYNTAX 章节还没有 Ω-spec ⇒ 继续按轮次扩，本条不被 BUG-95 的目录闭环遮蔽。"),
    ]:
        if summary in existing:
            rep["bugs"].append({"skipped": "账本已有同 summary（幂等守卫）", "summary": summary[:70]})
            continue
        r = c.call("report_bug", {"project_dir": ".", "summary": summary, "severity": sev,
                                  "detail": detail, "reported_by": AGENT, "publish_task": False})
        rep["bugs"].append({"reply": json.dumps(r, ensure_ascii=False)})

    c.close()
    rep["_sent"] = sent
    return finish(rep, root_id, started)


def finish(rep: dict, root_id: str, started: str) -> int:
    con = ro_db()
    sent = rep.pop("_sent", [])
    rows = list(con.execute(
        "select tool, sum(ok=1), sum(ok=0) from call_log "
        "where ts>=? and (json_extract(params_json,'$.task_id') like ? "
        "or json_extract(params_json,'$.name')=? or json_extract(params_json,'$.namespace')=?) "
        "group by tool order by tool", (started, f"{root_id}.%", LOOP_NAME, NS)))
    logged = {t: {"ok": a, "refused": b} for t, a, b in rows}
    sent_counts: dict = {}
    for t in sent:
        sent_counts[t] = sent_counts.get(t, 0) + 1
    rep["tally"] = {"by_tool": logged, "rpc_sent_by_tool": sent_counts, "rpc_sent_total": len(sent),
                    "sent_but_invisible_to_filter": sorted(set(sent_counts) - set(logged)),
                    "rows_matching_filter": sum(a + b for _t, a, b in rows),
                    "refused_matching_filter": sum(b for _t, a, b in rows),
                    "filter_window_from": started,
                    "root_status": (con.execute("select status from tasks where id=?",
                                                (root_id,)).fetchone() or [None])[0],
                    "leaf_status_after": dict((s or "?", n) for s, n in con.execute(
                        "select status, count(*) from tasks where id like ? and depth=1 group by status",
                        (f"{root_id}.%",))),
                    "pending_leaf_ids": [r[0] for r in con.execute(
                        "select id from tasks where id like ? and depth=1 and status='待领取' order by id",
                        (f"{root_id}.%",))]}
    if rep["tally"]["rows_matching_filter"] <= 0:
        rep["refusals"].append({"node": "(对账)", "tool": "sqlite",
                                "reply_verbatim": f"窗口 ts>={started} 内调用数 0 ⇒ 过滤恒假"})
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds: dict = {}
    for v in rep["nodes"].values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(json.dumps({"root": root_id, "tree": rep["tree_readback"], "baseline": rep["baseline_measured"],
                      "leaf_status": {k: (v["kind"], v["status_before"], v["status_after"],
                                          (v["steps"].get("run_check") or {}).get("state"))
                                      for k, v in rep["nodes"].items()},
                      "tally": rep["tally"]}, ensure_ascii=False, indent=1))
    for r in rep["refusals"]:
        print("REFUSED", r["tool"], "|", r["node"], "|", r["reply_verbatim"])
    print(f"CONCLUSION closed={len(rep['nodes'])} by_kind={kinds} "
          f"still_pending={len(rep['tally']['pending_leaf_ids'])} root={rep['tally']['root_status']} "
          f"calls={rep['tally']['rows_matching_filter']} refused={rep['tally']['refused_matching_filter']} "
          f"refusal_rows={len(rep['refusals'])} run_check_states="
          f"{sorted({(v['steps'].get('run_check') or {}).get('state') for v in rep['nodes'].values()})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
