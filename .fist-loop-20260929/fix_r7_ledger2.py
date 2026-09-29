"""R7 账面补记：给 BUG-108 的 FIXED 段追加一处 `### AMENDMENT`（只增不删不改）。

改判的原因要有活证据，不能只写「我改主意了」：
1. 锁承重矩阵第一版的 M4 格针是 `kind != "ComptimeStmt"` 那道跳过，实测摘掉它 14 格仍全绿 ⇒ 不承重；
2. 结构证明（logs/r7_comptime_structural_proof_a1.txt 逐字）：`ComptimeStmt.__init__` 只设 `self.expr`，
   parser 两处构造点都不传 `type_annotation` ⇒ 该守卫对任意输入都不可能命中，是死代码，已删除；
3. 语料测量（logs/r7_comptime_fact_a1.txt 逐字 `ComptimeStmt_nodes=3 with_type_annotation=0`）。
行为不变：`comptime:` 行内形式依旧不受注解闭集约束，依据从「显式跳过」改为「结构上没有注解字段」。

同时如实登记一条本轮自造的流程债：矩阵首跑（r7_locks_a1.txt）与二跑写进了同一个
`logs/r7_lock_M4.txt`，首跑那格的读数被原地覆盖——这是「门与证据同名」的同型失误，逐字写在这里而不是假装还在。
"""

from __future__ import annotations

import datetime
import difflib
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LEDGER = ROOT / "memory" / "bugs.md"
OUT = HERE / "fix_r7_ledger2.json"
ANCHOR_TAG = "AMENDMENT(R7 矩阵改判"

TEXT = f"""### {ANCHOR_TAG} 2026-09-29，ns cypy-loop-20260929 / T0r113) — 上面 FIXED 段的一处实现描述按实测改判

- 原文写「`_validate_annotation_shapes()`（AST 全walk，跳过 `kind == "ComptimeStmt"`）」——**该跳过不存在了**：
  锁承重矩阵的 M4 格实测它不承重（针指在守卫上摘掉后 `tests/test_annotation_shape.py` 仍 `14 passed`），
  再核结构：`ComptimeStmt.__init__` 只设 `self.expr`，parser 两处构造点均不传 `type_annotation`
  （逐字证据 `{HERE.relative_to(ROOT).as_posix()}/logs/r7_comptime_structural_proof_a1.txt`），
  语料测量同向（`logs/r7_comptime_fact_a1.txt`：`files=109 parsed=97 ComptimeStmt_nodes=3 with_type_annotation=0`）
  ⇒ 该条件对任意输入都不可能命中，属死代码，已从 `cypyc/analyzer/type_checker.py` 删除。
- 行为主张不变：`comptime: [1, 2]` 仍不被判为非法注解，依据改为结构事实（ComptimeStmt 没有注解字段）；
  认领它的锁仍是 `tests/analyzer/test_r5_fix_comptime_types.py::test_bug83_inline_form_control_still_clean`
  与 `tests/test_annotation_shape.py::test_comptime_inline_form_is_not_an_annotation`。
- 删除后三套全量复跑（逐字见 R7 报告 §终验，日志 `{HERE.relative_to(ROOT).as_posix()}/logs/r7b_*.log`）。
- 自造流程债如实登记：矩阵首跑的 M4 读数与二跑写进了同名文件 `logs/r7_lock_M4.txt`，前一份被原地覆盖，
  现在只能靠 stdout 残迹（`logs/r7_locks_a1.txt` 停在对照格的断言处）与上面两枚结构性证据复述它——
  「门与证据同名」的同型失误，本轮第 N 次，仍写在这里而不是假装还在。
- 账面漂移：叶 `T0r113.1.2` 的 deliverable 文案含「含 comptime 整类跳过」，归档后无改档出路（129 工具无一可改
  deliverable），该半句自本段起失效；FIST 侧缺口同号 BUG-111（call_log/账面复原能力），Cypy 侧以本段为准。
"""


def removed_lines(old: str, new: str) -> list:
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    bad = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("delete", "replace"):
                bad.extend(old.splitlines()[i1:i2])
    return bad


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    meta: dict = {"written_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if ANCHOR_TAG in src:
        meta["idempotent_noop"] = f"已存在 {ANCHOR_TAG} ⇒ 不重复追加"
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False))
        return 0
    start = src.index("## BUG-108 ")
    nxt = src.find("\n## BUG-", start + 1)
    end = nxt if nxt != -1 else len(src)
    block = src[start:end]
    if not re.search(r"(?m)^### FIXED\(R7 组合环", block):
        meta["refuse"] = "BUG-108 块里没有 R7 的 FIXED 段 ⇒ 无处可改判，中止"
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    out = src[:end] + "\n" + TEXT.rstrip("\n") + "\n" + src[end:]
    bad = removed_lines(src, out)
    if bad:
        meta["refuse"] = f"存在删除/改写行 {len(bad)} 条，首条：{bad[0][:120]}"
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    back = LEDGER.read_text(encoding="utf-8")
    meta["recheck"] = {"entries": len(re.findall(r"(?m)^## BUG-\d+ ", back)),
                       "amendment_tags": back.count(ANCHOR_TAG),
                       "bytes_before": len(src.encode("utf-8")),
                       "bytes_after": len(back.encode("utf-8")),
                       "insert_only_verified": not removed_lines(src, back)}
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
