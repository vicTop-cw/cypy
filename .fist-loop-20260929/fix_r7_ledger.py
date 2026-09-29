"""R7 账面：给 BUG-34 / BUG-92 / BUG-108 追加 `### FIXED(...)` 段（只增不删不改）。

三条自证（沿用 R6 的尺并改掉它的两处口径漏洞）：
1. 插入锚点唯一命中；每条叶的块内若已有 `### FIXED(` 即跳过（幂等，重跑不多生段）；
2. 写出内容逐字保留旧内容全部行（difflib 只允许 insert，出现 delete/replace 即中止且不落盘）；
3. 正文里引用的新票号一律从 close_r7_ring*.json 的 report_bug 回执反解，不手写数字
   （R6 的 BUG-107 就是手写编号与服务端撞号）。反解不到即 refuse，不落盘。
"""

from __future__ import annotations

import datetime
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "fix_r7_ledger.json"

RUN_A = HERE / "close_r7_ring.json"
RUN_B = HERE / "close_r7_ring_b.json"


def server_ids() -> list:
    """从两批收口件里反解 report_bug 实际拿到的编号（服务端号，本地不造号）。"""
    ids = []
    for p in (RUN_A, RUN_B):
        if not p.exists():
            continue
        for row in json.loads(p.read_text(encoding="utf-8")).get("bugs", []):
            m = re.search(r'"bug_id":\s*"(BUG-\d+)"', row.get("reply", ""))
            if m:
                ids.append(m.group(1))
    return ids


def build(src: str, ids: list) -> tuple:
    refuse: list = []
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    first = ids[0] if ids else ""
    rest = ", ".join(ids[1:]) if len(ids) > 1 else "（本批无新增）"
    if not first:
        refuse.append("反解不到任何 report_bug 的 bug_id ⇒ 正文会写成悬空票号，中止")
        return src, {"refuse": refuse, "server_ids": ids}

    sections = {
        "BUG-92": f"""### FIXED(R7 组合环 {ts}，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 前置条款（本环补，落文档面）：`SYNTAX/17-pattern-matching.md` 追加「## 位置模式的元数与槽位规则（R7 补，2026-09-29）」，
  418→441 行；写明槽位数来源优先级（`__match_args__` < `__unapply__` < `__unapply_seq__` < `__unwarp__`，
  无提取器时按 `.fields` 声明序）、**实参元数 > 可解包槽位数必须诊断并带行列**、方法名不占位置槽、
  类型不可见时不报元数错、产物不得出现 `.__f{{i}}`。本条目「出路 ①」由此成立。
- 实现：`cypyc/analyzer/type_checker.py:_visit_ExtractorPattern` 在槽位类型可得时比较元数，超槽即发
  `Positional pattern '<T>' has <k> slot(s) but type '<T>' unpacks only <n> at <line>:<col>`。
- 判据面（R6 打红的正是这条，本轮按新条款改严而非弱化）：
  `tests/test_extractor_pattern.py::test_extractor_pattern_type_checker` 从 `assert not checker.errors`
  改为双向格——2 字段/2 实参必须 `errors == []`；1 字段/2 实参必须命中 `Positional pattern 'Email'`
  且匹配 `unpacks only 1 at \\d+:\\d+`。旧断言把本缺陷的静默行为钉成了期望值。
- 调用面实测（真 CLI，非单测桩）：
  `python -X utf8 -m cypyc transpile .fist-loop-20260927/hunts/hunt_f_pattern_binding_int.cypy -o .fist-loop-20260929/out_r7 --emit-cython`
  → rc=1，逐字 `- Positional pattern 'Email' has 2 slot(s) but type 'Email' unpacks only 1 at 6:14`
  （{HERE.relative_to(ROOT).as_posix()}/logs/r7_callsite_huntf.txt）；
  输出目录 `out_r7` 未被创建 ⇒ 本形态下 `.__f1` 不再有产物面。
  before 证据仍在：`.fist-loop-20260929/out_after/hunt_f_pattern_binding_int.pyx` 第 39 行 `domain = _match_subject_1.__f1`。
- 边界审视（T0r113 边界叶，{HERE.relative_to(ROOT).as_posix()}/hunt_r7_boundary.json 共 23 格）：
  超元与 32 槽极值均带行列诊断；0 实参与欠元按上述条款保持沉默（条款只强制超元）；未定义类型不报元数错（前条件生效）；
  本面 0 CRASH、0 静默放过、0 假阳性。
- 残留（另立新单，服务端号 {first} / {rest}）：解析器仍把 `[int]` / `(int,str)` / `{{str:int}}` 编成字面量节点，
  正解需要类型表达式产生器；元数检查只在槽位类型「可见」时生效，类型不可见时越界槽位仍可走到 `.__f{{i}}`。
""",
        "BUG-108": f"""### FIXED(R7 组合环 {ts}，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 前置条款（本环补，落文档面）：`SYNTAX/02-type-annotations.md` 追加「## 注解形态闭集（R7 补，2026-09-29）」，
  158→189 行：合法节点闭集 `Name / GenericType / PointerType / UnionType / RefType`；
  `[] / () / {{}}` 三种字面量形态一律拒绝且诊断必须点名正确写法；产物永不得携带 AST repr；`comptime:` 行内形式整类排除。
- 分析器：新增 `ANNOTATION_TYPE_KINDS` / `ANNOTATION_SHAPE_HINTS` / `_check_annotation_shape()` /
  `_validate_annotation_shapes()`（AST 全walk，跳过 `kind == "ComptimeStmt"`），挂在 `check()` 的
  `self._visit(node)` 之后；诊断文案 `Invalid type annotation at {{line}}:{{col}} (期望 …，实际是 {{kind}} 字面量形态)`。
- 生成器：`cypyc/codegen/cython_generator.py:_type_to_str` 末路由 `return str(node)` 改为 `return "object"`
  （带注释指认 BUG-34/BUG-108），任何未知形态不再把节点 repr 发进产物。
- 锁死回归：新建 `tests/test_annotation_shape.py`（实收 14 条 / 6 个函数）——
  6 条合法形态放行、4 条非法形态必诊断且带行列、`test_product_never_carries_ast_repr`
  断言产物不含 `line=` 与 `Constant(`、`test_unknown_annotation_degrades_to_object`、
  反向对照 `test_comptime_inline_form_is_not_an_annotation`、收集数地板 `test_this_file_collects_its_locks`。
- 调用面实测：`adv_10_slice_step_zero.cypy` → rc=1，逐字
  `- Invalid type annotation at 2:9 (期望 类型名或 list<int> / tuple<int, int> / dict<str, int>，实际是 Constant 字面量形态)`
  （{HERE.relative_to(ROOT).as_posix()}/logs/r7_callsite_adv10.txt）；不再产出 .pyx。
  before 证据仍在：`.fist-loop-20260927/cliout/adv_10_slice_step_zero.pyx` 第 30 行 `xs: Constant(line=2, col=9) = [1, 2, 3]`。
- 三套全量回归（本环终态，逐字结论行）：pytest `2158 passed in 413.15s`（rc=0）、
  自研套件 `Total: 47 | Passed: 47 | Failed: 0`（rc=0）、
  e2e golden `[e2e-golden] summary: PASS=25 FAIL=0 UNREG/RUNFAIL=0 WARN=0`（rc=0）。
- 残留：括号形态本应是类型而解析器没有类型表达式产生器 ⇒ 正解未做，另立新单（服务端号 {first}）。
""",
    }
    sections["BUG-34"] = f"""### FIXED(R7 组合环 {ts}，ns cypy-loop-20260929 / T0r113) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 本条目是这条缺陷的初登记录；R6 复验时因本地手写编号与服务端撞号，同一条主张另立了 BUG-108，
  收口过程（条款、实现、锁、调用面逐字回执、三套全量）逐行见 **BUG-108 的 FIXED 段**，此处不复制第二份正文。
- 结论三行：`SYNTAX/02` 补「注解形态闭集」158→189 行；分析器 `_validate_annotation_shapes` 拒字面量形态并点名正确写法；
  生成器 `_type_to_str` 末路由 `str(node)` 改 `"object"`，产物永不含 AST repr。
- 调用面逐字：`adv_10_slice_step_zero.cypy` rc=1 →
  `- Invalid type annotation at 2:9 (期望 类型名或 list<int> / tuple<int, int> / dict<str, int>，实际是 Constant 字面量形态)`；
  before 证据仍在 `.fist-loop-20260927/cliout/adv_10_slice_step_zero.pyx` 第 30 行。
- 残留（服务端号 {first}）：解析器没有类型表达式产生器，括号形态仍未正解。
"""

    numbers = {int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", src)}
    out = src
    done, skipped = [], []
    for bug_id, section in sections.items():
        n = int(bug_id.split("-")[1])
        if n not in numbers:
            refuse.append(f"{bug_id} 抬头不存在 ⇒ 锚点失效")
            continue
        start = out.index(f"## {bug_id} ")
        nxt = out.find("\n## BUG-", start + 1)
        anchor_end = nxt if nxt != -1 else len(out)
        block = out[start:anchor_end]
        if re.search(r"(?m)^### FIXED\(", block):
            skipped.append(bug_id)
            continue
        out = out[:anchor_end] + "\n" + section.rstrip("\n") + "\n" + out[anchor_end:]
        done.append(bug_id)
    return out, {"refuse": refuse, "server_ids": ids, "appended": done, "skipped_existing": skipped,
                 "written_at_utc": ts}


def removed_lines(old: str, new: str) -> list:
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    bad = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            bad.extend(old.splitlines()[i1:i2])
    return bad


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    ids = server_ids()
    out, meta = build(src, ids)
    bad = removed_lines(src, out)
    if bad:
        meta["refuse"].append(f"存在删除/改写行 {len(bad)} 条，首条：{bad[0][:120]}")
    if meta["refuse"]:
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        return 1
    if not meta["appended"]:
        meta["idempotent_noop"] = True
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    back = LEDGER.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^## (BUG-\d+)", back)
    open_ids = [blocks[i] for i in range(1, len(blocks) - 1, 2)
                if not re.search(r"(?m)^### FIXED\(", blocks[i + 1])]
    meta["recheck"] = {"entries": len(re.findall(r"(?m)^## BUG-\d+ ", back)),
                       "fixed_sections": len(re.findall(r"(?m)^### FIXED\(", back)),
                       "open_after": len(open_ids),
                       "bytes_before": len(src.encode("utf-8")),
                       "bytes_after": len(back.encode("utf-8")),
                       "target_still_open": [b for b in ("BUG-34", "BUG-92", "BUG-108") if b in open_ids]}
    if meta["recheck"]["target_still_open"]:
        meta["recheck"]["FAIL"] = "目标条目仍无 FIXED 段"
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
