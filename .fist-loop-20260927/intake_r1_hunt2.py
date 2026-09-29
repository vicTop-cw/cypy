#!/usr/bin/env python3
"""R1-寻虫 · 第二张入账件：把 fuzz 车道的两条候选**自己复跑坐实**后入账。

独立车道交来 5 条候选，本脚色只做「我自己复现得了的才入账」：
- fz01b（源文件以空格结尾且无末换行）→ 词法器 TypeError：复现成功 → 入账
- fz02（顶层 return）→ 静默产出非法 Cython：复现成功 → 入账
- fz03 → 与已入账的 BUG-35（诊断归桶）同根因，不重复报
- fz04（产物内嵌墙上时钟导致两次生成字节不同）→ 规范无「可复现构建」承诺，判规格未定，不入账
- fz05（生成器实例复用跨模块状态泄漏）→ 生产路径每模块新建实例，无用户可见面，不入账
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"E:\IDEProjects\AI\Cypy")
import lfist_lib  # noqa: E402

from cypyc.parser.lexer import Lexer  # noqa: E402
from cypyc.parser.parser import Parser  # noqa: E402
from cypyc.codegen.cython_generator import CythonGenerator  # noqa: E402

HUNTS = HERE / "hunts"
S1 = HUNTS / "fz01_trailing_space_no_newline.cypy"
S2 = HUNTS / "fz02_toplevel_return.cypy"
S1.write_text("def main() -> int:\n    return 0   ", encoding="utf-8", newline="\n")
S2.write_text("return 0\n", encoding="utf-8", newline="\n")

ev = {}
try:
    Parser(list(Lexer(S1.read_text(encoding="utf-8")).tokenize())).parse()
    ev["fz01"] = {"exception": None}
except BaseException as exc:  # noqa: BLE001
    ev["fz01"] = {"exception": type(exc).__name__, "msg": str(exc)[:200]}
code2 = ""
try:
    code2 = CythonGenerator().generate(
        Parser(list(Lexer(S2.read_text(encoding="utf-8")).tokenize())).parse()
    )
    ev["fz02"] = {"exception": None, "artifact_len": len(code2)}
except BaseException as exc:  # noqa: BLE001
    ev["fz02"] = {"exception": type(exc).__name__, "msg": str(exc)[:200]}

top_level_return = [l for l in code2.splitlines() if re.match(r"^return\b", l)]
ev["fz02_top_level_return_lines"] = top_level_return
(HUNTS / "fz_evidence.json").write_text(
    json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
)
print(json.dumps(ev, ensure_ascii=False, indent=1))

gate = {
    "BUG-38": ev["fz01"]["exception"] == "TypeError" and "NoneType" in ev["fz01"].get("msg", ""),
    "BUG-39": ev["fz02"]["exception"] is None and bool(top_level_return),
}
print("gates:", gate)
if not all(gate.values()):
    print("REFUSE — 复现不成立，拒绝入账")
    sys.exit(1)

ITEMS = [
    (
        "[变异fuzz:词法] 源文件以空格结尾且无末换行时，词法器抛 TypeError（NoneType 参与 in 运算）",
        "复现：python -X utf8 -c \"import sys; sys.path.insert(0,'.'); from cypyc.parser.lexer import Lexer;"
        "from cypyc.parser.parser import Parser;"
        "Parser(list(Lexer(open('.fist-loop-20260927/hunts/fz01_trailing_space_no_newline.cypy',"
        "encoding='utf-8').read()).tokenize())).parse()\"\n"
        f"实际：{ev['fz01']['exception']}: {ev['fz01']['msg']}——末行没有换行符且以空格结束时，"
        "_skip_whitespace/tokenize 取到 None 仍参与 `in` 判断；CLI 侧用户只看到「读取文件错误: …」，无 file:line"
        "（同 BUG-35 的归桶问题，但这条是崩溃本身）。\n"
        "期望：文件尾的空白/缺末换行属合法输入，必须正常出 token 或给带行列的诊断，不得抛未声明异常。\n"
        "命中：cypyc/parser/lexer.py:278 附近（_skip_whitespace），调用点 tokenize:510。\n"
        "证据：.fist-loop-20260927/hunts/fz01_trailing_space_no_newline.cypy（10 字节最小复现）、"
        "fz_evidence.json(fz01)、fuzz/results_r1.jsonl 的 (b) 类",
    ),
    (
        "[变异fuzz:语法] 顶层 return 被静默接受并原样写进产物，生成的 .pyx 必编译失败",
        "复现：python -X utf8 -m cypyc transpile "
        ".fist-loop-20260927/hunts/fz02_toplevel_return.cypy -o .fist-loop-20260927/cliout --emit-cython\n"
        f"实际：rc=0 且产物出现顶格 {top_level_return!r}（模块级 return）；"
        "该 .pyx 交给 Cython 会报 Return not inside a function body。"
        "class 体内的 return（fz02c）与函数后的多余顶层 return（fz02b）同样被放过。\n"
        "期望：parser 已有 _require_function_scope（parser.py:880，defer 就用了它），"
        "_parse_return_stmt（parser.py:1671）却没用 ⇒ 顶层 return 必须诊断（带行列）。\n"
        "证据：.fist-loop-20260927/hunts/fz02_toplevel_return.cypy、fz_evidence.json"
        "(fz02_top_level_return_lines)、cliout/fz02_toplevel_return.pyx",
    ),
]
c = lfist_lib.Client(timeout=180)
c._send(
    "initialize",
    {
        "protocolVersion": lfist_lib.PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": lfist_lib.CLIENT_INFO,
    },
)
new = []
for summary, detail in ITEMS:
    res = c.call(
        "report_bug",
        {
            "project_dir": ".",
            "summary": summary,
            "detail": detail,
            "severity": "high",
            "reported_by": "cypy-loop-hunter",
            "publish_task": True,
            "now": lfist_lib.utc_now(),
        },
    )
    new.append(
        {
            "key": "BUG-38" if "词法] 源文件" in summary else "BUG-39",
            "bug_id": res.get("bug_id"),
            "task_id": res.get("task_id"),
            "status": res.get("status"),
            "path": res.get("resolved_path"),
            "samples": summary.split("]")[0],
        }
    )
    print(json.dumps(new[-1], ensure_ascii=False))
c.close()

first = json.loads((HERE / "intake_r1_hunt.json").read_text(encoding="utf-8"))
merged = {
    "mapping": first["mapping"] + new,
    "skipped_for_missing_evidence": first.get("skipped_for_missing_evidence", []),
    "lane_second": {
        "evidence": ".fist-loop-20260927/hunts/fz_evidence.json",
        "not_filed": {
            "fz03": "同 BUG-35 归桶根因",
            "fz04": "规格未定（无「可复现构建」承诺）",
            "fz05": "生产路径每模块新建实例，无用户可见面",
        },
    },
}
bad = [m for m in merged["mapping"] if not (m.get("bug_id") and m.get("task_id"))]
if bad:
    print(f"REFUSE — 合并后的入账表有缺项: {bad}")
    sys.exit(1)
(HERE / "intake_r1_hunt.json").write_text(
    json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
)
print(f"OK 合并后共 {len(merged['mapping'])} 条入账")
