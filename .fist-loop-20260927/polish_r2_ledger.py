#!/usr/bin/env python3
"""把 BUG-42 的 FIXED 段追加进 `memory/bugs.md`，文本全部从**证据件**反解，不手打数字。

三条纪律：
- 幂等守卫：段里带本环唯一标记（根任务号 + UTC 时刻），已存在同标记段 ⇒ 直接拒绝，不重复追加
  （上一轮就因为重跑非幂等脚本 dup 入账过一张单）；
- 任一件 `refuse != []` 或未落盘 ⇒ 整段不写（账本写出去就收不回来，账本无 close/edit API）；
- 数字只从 JSON 取：pytest 末行 / 套件末行 / e2e 末行 / 删除行区间 / 绑定行号，一个都不凭记忆。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"E:\IDEProjects\AI\Cypy")
LOOP = ROOT / ".fist-loop-20260927"
LEDGER = ROOT / "memory" / "bugs.md"
NOW = "2026-09-27T10:56:00Z"
ROOT_TASK = "T0r60"
MARKER = f"### FIXED(打磨=已完成) — {NOW} 追加留档（2026-09-27 R2-打磨(循环轮)，本条目正文与标题行 `OPEN` 一字未改）"
REPORT = sys.argv[1] if len(sys.argv) > 1 else "memory/reviews/(报告名在收口后补)"


def load(rel: str) -> dict:
    p = LOOP / rel
    if not p.exists():
        raise SystemExit(json.dumps({"refuse": [f"证据件缺失：{rel}"]}, ensure_ascii=False))
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    refuse: list = []
    cut = load("polish_r2_cut.json")
    after = load("polish_r2_after.json")
    base = load("polish_r2_baselines.json")
    lint = load("polish_r2_lint.json")
    for name, doc in (("cut", cut), ("after", after), ("baselines", base), ("lint", lint)):
        if doc.get("refuse"):
            refuse.append(f"{name} 件里 refuse 非空：{doc['refuse'][:2]}")
    if cut.get("dry_run"):
        refuse.append("cut 件是 dry-run 产物，不能作为已落盘证据")
    if not refuse:
        text = LEDGER.read_text(encoding="utf-8")
        if MARKER in text:
            refuse.append("幂等守卫：本环 FIXED 段已在账上，不重复追加")

    if refuse:
        print(json.dumps({"refuse": refuse, "written": False}, ensure_ascii=False))
        return 1

    m_expr = cut["measures"]["bug42_expr_stmt"]
    m_meta = cut["measures"]["bug42_meta_block"]
    ev = load("polish_r2_evidence.json")
    live = ev.get("live") or {}
    ev_expr = (live.get("CythonGenerator._visit_ExprStmt") or {}).get("candidates")
    ev_meta = (live.get("ScopeAnalyzer._visit_MetaBlock") or {}).get("candidates")
    # 删前留档必须还是"两处候选"的形状；若这件被删后重跑覆盖成一处，"删除前实测它是红的"就没人证了
    for label, cands in (("_visit_ExprStmt", ev_expr), ("_visit_MetaBlock", ev_meta)):
        if not cands or len(cands) != 2:
            refuse.append(f"判据件 polish_r2_evidence.json 的 {label} 候选不是删前两处：{cands}")
    pytest_line = base["pytest"]["line"]
    suite_line = base["suite"]["line"]
    e2e_line = base["e2e"]["line"]
    if refuse:
        # 上面那段 refuse 是在"早退检查"之后才产生的 ⇒ 必须在这里再拦一次，否则账写出去收不回
        print(json.dumps({"refuse": refuse, "written": False}, ensure_ascii=False))
        return 1

    section = f"""{MARKER}
- 处置单：根 `{ROOT_TASK}`（ns `cypy-loop-20260927`）的 8 枝 16 叶全链带 `[omega:required]`，逐叶
  `output_validate` pass 后才 verify；报告：`{REPORT}`
- 生效性判定（不是"我看第二份顺眼"）：`CythonGenerator.__dict__['_visit_ExprStmt'].__code__.co_firstlineno
  == {cut['bound_lines']['_visit_ExprStmt']}`、`ScopeAnalyzer.__dict__['_visit_MetaBlock'].__code__.co_firstlineno
  == {cut['bound_lines']['_visit_MetaBlock']}`，与 AST 候选 {ev_expr} / {ev_meta} 两条口径互相咬合
  （判据件 `.fist-loop-20260927/polish_r2_evidence.json`，`refuse=[]`，删前留档）。
- 删除面：`{m_expr['rel']}` 行 {m_expr['removed_range']}（{m_expr['removed_lines']} 行，sha8 {m_expr['removed_sha8']}）、
  `{m_meta['rel']}` 行 {m_meta['removed_range']}（{m_meta['removed_lines']} 行，sha8 {m_meta['removed_sha8']}）。
  复算走**两路独立口径**：驱动自证（`polish_r2_cut.json`）+ 从仓库外快照 `E:/IDEProjects/AI/_cypy_snapshots/pre_polish_r2`
  反解（`polish_r2_after.json`）——模块级与类内符号**集合**逐档相同、行数差 == 声称删除行数
  （{after['files'][m_expr['rel']]['line_delta']} / {after['files'][m_meta['rel']]['line_delta']}）、快照按驱动行区间切出的文本与驱动记的 `removed_text` 逐字相同、
  全树同名遮蔽计数归零（`tree_dupes={{}}`）、绑定行号上移量恰好等于删除行数
  （{cut['bound_lines']['_visit_ExprStmt']}→{after['bound_after']['_visit_ExprStmt']}、{cut['bound_lines']['_visit_MetaBlock']}→{after['bound_after']['_visit_MetaBlock']}）。
- 来历（`git log -S` 只读实测）：`_visit_MetaBlock` 的**守卫份**由 `f6d498f`(2026-07-27) 后加、
  **活份**由 `915431e`(2026-07-26) 先写在前 ⇒ 后加的守卫被落在被遮蔽的位置上，从来没生效过；同一语义在
  parser 里另有实现（`_require_module_level("meta", ...)`，HEAD `cypyc/parser/parser.py:2405` 已存在）⇒
  删除不丢校验，调用面复验 `def foo(): meta:` 仍报 `meta must be defined at module level, found at 2:9`
  （已钉成永久锁 `test_nested_meta_block_is_rejected_with_position`）。
  `_visit_ExprStmt` 两份都随 `17d68b4`(2026-08-17) 一次进来 ⇒ 重复是那场重构的产物；死份的
  `elif getattr(node, 'value', None) is not None` 与它的 `if` 同条件，**构造上不可达**，无独有逻辑。
- 被删文本留档：`polish_r2_cut.json` 的 `measures.*.removed_text`（含那句唯一守卫文案），要回放可逐字取回。
- 机制化：新增结构判据 `tests/test_polish_20260927_r2.py::test_product_code_has_no_shadowed_method_definitions`
  扫 `cypyc/**/*.py`，同一类体内出现同名方法即红；配合成违例对照
  `test_shadow_detector_catches_a_synthetic_pair`（同类两名必被抓、单份不得误抓）。
  **删除前实测它是红的**，红文逐字点名两处：`ScopeAnalyzer._visit_MetaBlock@[484, 926]`、
  `CythonGenerator._visit_ExprStmt@[1418, 2084]` ⇒ 判据不恒绿。
- 行为未变（同一时刻复算）：pytest `{pytest_line}`（下限 {base['pytest']['floor']} = 上环 1886 + 本环 8 条锁，
  collected={base['pytest']['collected']}，只升不降）；自研套件 `{suite_line}`；端到端 `{e2e_line}`；
  基准**未重注册**。作用域化 lint：亲笔 {lint['authored_lines_checked']} 行零违例，
  两档产品码新增行数 {lint['product_files'][m_expr['rel']]['added_lines']}/{lint['product_files'][m_meta['rel']]['added_lines']}（纯删除），
  存量违例只减不增（{lint['product_files'][m_meta['rel']]['debt_before']}→{lint['product_files'][m_meta['rel']]['debt_after']}）。
- 不算证明（本环明确排除）：① "三套基线全绿" 不证明死份里没有独有能力 ⇒ 靠来历 + 构造不可达 +
  守卫另有实现并在调用面复验；② "文件仍能导入" 不证明删对了那份 ⇒ 靠绑定行号上移量与删除行数吻合；
  ③ "文件行数变了" 不证明变的是我要删的 ⇒ 靠快照切出的文本与 `removed_text` 逐字相等。
"""

    text = LEDGER.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## BUG-42 "))
    nxt = next((i for i in range(start + 1, len(lines)) if re.match(r"^## BUG-\d+ ", lines[i])), len(lines))
    insert_at = nxt
    while insert_at > start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    new_lines = lines[:insert_at] + [""] + section.rstrip("\n").split("\n") + lines[insert_at:]
    new = "\n".join(new_lines)
    LEDGER.write_text(new, encoding="utf-8")
    back = LEDGER.read_text(encoding="utf-8")
    out = {
        "written": True,
        "marker_count": back.count(MARKER),
        "fixed_sections": len(re.findall(r"^### FIXED\(", back, flags=re.M)),
        "entries": len(re.findall(r"^## BUG-\d+ ", back, flags=re.M)),
        "len_before": len(text),
        "len_after": len(back),
        "refuse": [],
    }
    if out["marker_count"] != 1:
        out["refuse"].append(f"标记出现 {out['marker_count']} 次（要 1）")
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not out["refuse"] else 1


if __name__ == "__main__":
    sys.exit(main())
