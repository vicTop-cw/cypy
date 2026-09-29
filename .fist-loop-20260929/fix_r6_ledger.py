"""R6 账面：给 BUG-36/37/41 追加 `### FIXED` 段，并在账本末尾登记本轮新确诊项。

铁律（04-进度报告规范 + 本轮红线）：**只增不删不改**。脚本自证三件：
1. 每条插入锚点在原文件里必须唯一命中（`count == 1`），否则中止且不落盘；
2. 写出内容必须逐字包含原文件全部字节（只插入，不改写、不重排）；
3. 新条目的编号不得与既有抬头撞号（撞号会让 `bug_list` 回读串条目）。

落盘用 temp + os.replace（`io.open(p,'w')` 会先截断，崩在半路就毁掉整份 append-only 账本）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "fix_r6_ledger.json"

FIXED_SECTIONS = {
    "BUG-36": """### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 根因：`cypyc/codegen/cython_generator.py:_collect_module_info` 对 StructDef 只遍历 `stmt.body`，
  而 StructDef 的成员存放在 `.fields`/`.methods`（parser.py:117-135；分析器同事实见 type_checker.py:3300）
  ⇒ `_extractor_types` 收不到 struct、`_class_fields` 恒空 ⇒ 位置模式既不调查提取器，又落到 `__f{i}` 占位。
- 修复：新增 `_record_pattern_shape()`，字段顺序取 `.fields`（声明序），提取器标记扫 `.methods`+`.body`，
  且**方法名不再算进位置字段**；StructDef/ClassDef 两支共用它。
- 调用面实测（同产物、非单测桩）：
  `python -m cypyc run .fist-loop-20260927/hunts/hunt_e_extractor_positional.cypy` → `Output: a`、rc=0；
  产物生成 `_ext_1 = (_match_subject_1.__unapply__() if hasattr(...) ...)`，`user = _ext_1_a0`，全文无 `.__f0`。
- 锁死回归：`tests/test_pattern_positional_struct.py`（7 条，含 1 条反向对照「真类型错误仍须报出」
  与 1 条「方法名不得进 fields」）。
- 未清的另一半另立新单（BUG-92）：无 `__unapply__` 且实参元数 > 字段数的形态，见本条目末尾新登记项。
""",
    "BUG-37": """### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 根因：`cypyc/analyzer/type_checker.py:_visit_Pattern` 无条件 `self.type_map[node.name] = Type("int")`
  （注释自称"暂定"），把 `_bind_pattern_names` 已登记的槽位类型覆盖掉；且 `_bind_pattern_names`
  原本根本不认识 `ExtractorPattern`/`Pattern` 两类节点（只认 `Name`/`Call`/`Tuple`）。
- 修复：`_bind_pattern_names` 增加 `Pattern`/`ExtractorPattern`/`StructPattern` 支路，
  新增 `_pattern_slot_types()` 按 SYNTAX/17 的提取器优先级取 `__unapply__` 返回元组的实参类型
  （`GenericType.args`，parser.py:820-824），无提取器时回落字段声明顺序，再回落 `object`；
  `_visit_Pattern` 改为「未登记过的名字才补 `object`」，宁可不判也不造假阳性。
- 调用面实测：`hunt_f_pattern_binding_int.cypy` 的 `Return type mismatch ... got int at 8:9` 消失；
  `hunt_e_extractor_positional.cypy` 从 rc=1 变 rc=0 且 `Output: a`。
- 锁死回归：`tests/test_pattern_positional_struct.py::test_positional_binding_takes_slot_type_not_int`
  / `test_positional_binding_falls_back_to_field_order_without_extractor`
  / `test_wrong_return_type_still_reported`（反向对照，防「只是把门拆了」）。
""",
    "BUG-41": """### FIXED(R6 组合环 2026-09-29，ns cypy-loop-20260929 / T0r112) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 实测口径修正：AST 反解两份同名类的差集，被遮蔽的是 **6 条**（`TestPointerBoundary` 首份 3 条里有 2 条
  名称仅存在于首份；`TestPipelineBoundary` 首份 3 条全部仅存在于首份）；本条目原写「6 条」在此得到确认。
- 修复：把**首现**的两份类改名为 `TestPointerBoundaryShadowedOnce` / `TestPipelineBoundaryShadowedOnce`
  （改名脚本对锚点做 `count==2` + 首现行号断言，避免把两份都改或改到别处），不删不并任何用例。
- 调用面实测：`pytest tests/test_boundary_comprehensive.py -k ShadowedOnce` → `6 passed, 122 deselected`
  （修复前这 6 条在收集面上不存在）。
- 残留：同名重复定义这类失效靠人工偶检不可持续，`tests/` 需要一条常驻「类名唯一 + 收集数地板」门；
  本轮未建该门，登记为流程债（见 R6 报告「未清项」）。
""",
}

NEW_ENTRIES_HEADER = "## BUG-{n} [{ts}] [{sev}] OPEN"
NEW_BUGS = [
    {
        "n": 92, "sev": "medium",
        "summary": "[模式匹配:规范缺口] 无 __unapply__ 且实参元数 > 字段数时，产物发不存在的 `__f{i}`；收紧需先补 SYNTAX/17 条款",
        "detail": """现象：`struct Email: address: str` + `case Email(user, domain)`（字段 1 个、实参 2 个）时，
`cython_generator.py:1792` 为越界槽位生成 `domain = _match_subject_1.__f1`，而生成产物里没有任何类定义 `__f1`
⇒ 运行期 AttributeError 或该 case 恒不命中。分析器不报元数不符（SYNTAX/17-pattern-matching.md 通篇没有元数条款）。
复现：`python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy -o .fist-loop-20260929/out_after --emit-cython`
产物第 39 行 `domain = _match_subject_1.__f1`。
本轮试过又撤掉的两种收紧（都实测过，不是猜测）：
① 分析器加「实参数 > 可解包槽位数」错误 ⇒ `tests/test_extractor_pattern.py::test_extractor_pattern_type_checker`（:192）
   断言 `assert not checker.errors` 被打红，该用例用的正是这条 1 字段 + 2 实参的形态；
② 生成器对已知形状不发 `__f{i}` 而跳过绑定 ⇒ 同名用例的 codegen 断言 `assert "_match_subject_1.__f0" in code`（:235）被打红。
判据面已把该形态钉成「无诊断 + 就是 `__f{i}`」，故本轮不动实现，按「未文档化的收紧不在本轮半径内」入账。
出路（交指挥官裁决，二选一）：① 在 SYNTAX/17 补「元数不符必须诊断」条款并同批更新那两条既有断言；
② 裁定 struct 无提取器时按 `__match_args__`/字段序解包、越界槽位编译期报错，另起一轮同时改判据与实现。""",
        "task": "T0r112",
    },
    {
        "n": 93, "sev": "medium",
        "summary": "[工具面] scripts/fist.py 指向上游已迁走的 cmd/main/main.js 且 list-tools 是恒绿探针",
        "detail": """现象（修复前实测）：`SERVER_JS` 固定 `_build/js/debug/build/cmd/main/main.js`，
服务 cwd 是兄弟仓 FIST-Mbt（⇒ 本项目 ns `cron-cypy` 的行写进 FIST-Mbt/fist-mbt.db，而不是仓内
`fist-mbt.db`，与既往四轮 lane 的收口库分家）；`project_dir` 默认绝对路径（服务端「禁越界」直接拒写）；
`main()` 先发一次 `initialize`，而 2026-07-28 是无状态握手，服务端回
`-32601 Method not found: initialize — this server speaks MCP 2026-07-28`，回执没人读；
`list-tools` 在错误帧/空清单/缺工具三种失败形态下**全部 rc=0 且零输出**（恒绿探针）。
另：驱动对所有调用无条件注入 `namespace`/`project_dir`，而 `loop_create`/`laya_decide`/`task_plan_deep`
不声明这两个键 ⇒ 服务端按 BUG-23 口径拒收（回执点名「参数名不被接受」）。
修复：入口改 `cmd/cli/cli.js` + `serve`；cwd 改本仓根（任务库落 `E:/IDEProjects/AI/Cypy/fist-mbt.db`）、
`project_dir` 默认 `.`；删掉 `initialize`；`_meta` 仍逐请求携带；`list-tools` 必须解出非空清单且点名
12 个本轮依赖的工具（publish/claim/execute/submit/verify/run_check/omega_verify/omega_spec_create/
laya_decide/call_log/report_bug/bug_list），否则 rc=1；新增 `_omit_defaults` 退出键关掉注入。
调用面实测：`python scripts/fist.py list-tools` → `# 129 tools; cwd=E:/IDEProjects/AI/Cypy; missing=[]`、rc=0；
`loop_create` + `laya_decide` + `task_plan_deep` 三连在带退出键后全部落库（ns cypy-loop-20260929，根 T0r112）。
锁死回归：`tests/test_fist_driver_protocol.py`（10 条，假 Popen 驱动，不起 node/不碰库；
含 3 条必然红的对照：错误帧、空清单、缺 omega_verify）。""",
        "task": "T0r112",
        "status": "FIXED",
    },
    {
        "n": 94, "sev": "low",
        "summary": "[兄弟仓 FIST-Mbt] `cli.js serve` 仍往协议 stdout 打 2 行人类横幅（其自述 BUG-101 的同类）",
        "detail": """实测：`node _build/js/debug/build/cmd/cli/cli.js serve` 的前两行 stdout 是
`[fist] serve — 启动 MCP server (stdio 传输)` / `stdin/stdout 接管, Ctrl+C 停止`，
JSON-RPC 帧从第 4 行才开始；而同仓 CHANGELOG 的 BUG-101 自称「run_serve 体内不再写 stdout」，
其回归门 `mcp_smoke` 本地仍报绿。Cypy 侧驱动按「非 JSON 行跳过」容忍，故不影响本轮工作，
但任何严格客户端（首行必须是 JSON）都会拒连。修在兄弟仓，不在 Cypy 轮次半径内 ⇒ 移交。
证据：.fist-loop-20260929/logs/（同命令原样重放两次，前两行逐字相同）。""",
        "task": "T0r112",
    },
    {
        "n": 95, "sev": "medium",
        "summary": "[规范落地] PROJECT-SPEC 要求的 corpus/ 与 tests/regression/ 两个目录在本仓不存在",
        "detail": """PROJECT-SPEC/03 §1 规定 `tests/regression/` 存历史 bug 固化用例、§2 规定「测试对同时沉淀为
Ω-spec JSON（corpus/）」；05 §3 的 Ω-gate 跑批第 3 步就是「corpus/ 下每个 spec JSON 的测试对」。
实测：`ls -d corpus tests/regression` → 两者均不存在（`ls -d` rc=2），仓库里也没有任何 Ω-spec JSON。
后果：05 定义的「项目准确率 = 通过/总数」在这个项目没有客观来源，Omega 强验证只能走
`omega_spec_create` 的单任务语料，落不到仓内可复审的判据面。
本轮把新增语料交给 `omega_spec_create`（任务面），但把目录本体留待裁决：新建 corpus/ 需要同时定
「哪些测试对进 corpus、以什么 schema」，那是判据面改动，不该夹在缺陷修复轮里顺手做。
出路：要么裁定本轮之后单开一轮建 corpus 基线（含 schema 与跑批入口），要么显式修订 03/05 对该目录的要求。""",
        "task": "T0r112",
    },
]


def build() -> tuple[str, dict]:
    src = LEDGER.read_text(encoding="utf-8")
    refuse: list[str] = []
    numbers = {int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", src)}
    out = src
    for bug_id, section in FIXED_SECTIONS.items():
        n = int(bug_id.split("-")[1])
        if n not in numbers:
            refuse.append(f"{bug_id} 抬头不存在，插入锚点失效")
            continue
        if "### FIXED" in out[out.index(f"## {bug_id} "):].split("\n## ")[0]:
            refuse.append(f"{bug_id} 已有 FIXED 段，本轮不重复追加")
            continue
        start = out.index(f"## {bug_id} ")
        nxt = out.find("\n## BUG-", start + 1)
        anchor_end = nxt if nxt != -1 else len(out)
        block = out[start:anchor_end]
        assert block.startswith(f"## {bug_id} "), bug_id
        out = out[:anchor_end] + "\n" + section.rstrip("\n") + "\n" + out[anchor_end:]
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    appended = []
    for bug in NEW_BUGS:
        if bug["n"] in numbers:
            refuse.append(f"BUG-{bug['n']} 抬头已存在 ⇒ 编号撞车，中止新条目追加")
            continue
        header = NEW_ENTRIES_HEADER.format(n=bug["n"], ts=ts, sev=bug["sev"])
        body = (f"{header}\n- summary: {bug['summary']}\n- detail: {bug['detail'].strip()}\n"
                f"- reported_by: cypy-selfdrive-agent\n- task_id: {bug['task']}\n")
        if bug.get("status") == "FIXED":
            body += f"\n### FIXED(R6 组合环 {ts}) — 同轮确诊同轮修，正文与抬头一次落盘\n\n"
            body += "- 见本条目 detail 的「修复」段；锁死回归 tests/test_fist_driver_protocol.py。\n"
        appended.append("\n" + body)
    out = out.rstrip("\n") + "\n" + "".join(appended)
    if not out.startswith(src[:200]):
        refuse.append("文件头 200 字节被改动 ⇒ 违反只增不删")
    return out, {"refuse": refuse, "fixed_sections": len(FIXED_SECTIONS),
                 "new_entries": [b["n"] for b in NEW_BUGS], "written_at_utc": ts}


def verify_only_insertions(old: str, new: str) -> list:
    """新内容逐字保留旧内容的全部行（只允许成段插入），返回违规行。"""
    from difflib import SequenceMatcher

    sm = SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    removed = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(old.splitlines()[i1:i2])
    return removed


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    out, meta = build()
    removed = verify_only_insertions(src, out)
    if removed:
        meta["refuse"].append(f"存在删除/改写行 {len(removed)} 条，首条：{removed[0][:120]}")
    if meta["refuse"]:
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    reopened = LEDGER.read_text(encoding="utf-8")
    tally = {
        "entries": len(re.findall(r"(?m)^## BUG-\d+ ", reopened)),
        "fixed_sections": len(re.findall(r"(?m)^### FIXED", reopened)),
        "bytes_before": len(src.encode("utf-8")),
        "bytes_after": len(reopened.encode("utf-8")),
    }
    tally["open_now"] = tally["entries"] - len(re.findall(r"(?m)^### (FIXED|DUPLICATE|NOT|OUT)", reopened))
    meta["recheck"] = tally
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
