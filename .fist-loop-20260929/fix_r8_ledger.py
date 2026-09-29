"""R8 账面：给 BUG-95 与本环同轮修好的两条缺陷追加 `### FIXED(...)` 段（只增不删不改）。

编号一律从 close_r8_ring.json 的 report_bug 回执反解（R6 的 BUG-107 教训：手写编号会与服务端撞号）；
反解不到就 refuse，不落盘。三条自证沿用 R6/R7 的尺：锚点唯一、difflib 只允许插入、temp+os.replace。
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
CLOSURE = HERE / "close_r8_ring.json"
OUT = HERE / "fix_r8_ledger.json"

GATE_LOG = HERE / "logs" / "r8_gate_final.txt"
SPEC17 = ROOT / "SYNTAX" / "17-pattern-matching.md"


def conclusion(path: Path, needle: str) -> str:
    for ln in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if ln.startswith(needle):
            return ln.strip()
    return ""


def receipts_from_closure() -> tuple:
    """从 close_r8_ring.json 反解本环的 report_bug 痕迹，返回 (编号列表, summary 列表)。

    a4 轮实测：幂等守卫生效后 `bugs` 栏是 `{"skipped": ..., "summary": ...}` 而不是 `{"reply": ...}`，
    所以「认不出编号就 refuse」这道门不能要求回执里有 bug_id —— 编号的正解来源是账本正文，
    这里的 summary 列表只用来核对「这条 summary 确实是本环报的」，防的是手编票号。
    两种形状都认：新单形状给编号，幂等跳过形状给 summary 原文。
    """
    if not CLOSURE.exists():
        return [], []
    data = json.loads(CLOSURE.read_text(encoding="utf-8")).get("bugs", [])
    ids: list = []
    summaries: list = []
    for row in data if isinstance(data, list) else []:
        reply = row.get("reply")
        if reply:
            ids += re.findall(r'"bug_id": "(BUG-\d+)"', reply)
        if row.get("summary"):
            summaries.append(row["summary"])
    return ids, summaries


def build(src: str, ts: str) -> tuple:
    refuse: list = []
    rep_ids, rep_summaries = receipts_from_closure()
    if not rep_ids and not rep_summaries:
        refuse.append("反解不到 report_bug 的任何痕迹（close_r8_ring.json 缺失或没有 bugs 栏）⇒ 中止")
        return src, {"refuse": refuse, "receipt_ids": rep_ids,
                     "receipt_summaries": rep_summaries}
    nums = {int(m) for m in re.findall(r"(?m)^## BUG-(\d+) ", src)}

    # 编号来源 = 账本正文（服务端 report_bug 追加的那段），命中必须恰好一条
    def pick(needle: str) -> tuple:
        """返回 (编号, 该条 summary 原文)。needle 必须是账本里逐字存在的片段 ——
        R8 a4 的实测教训：把标题「大意」当 needle（`__match_args__ 被当成第三个数据字段`）
        命中 0 条，因为原文中间还有 ` = (...)` ⇒ needle 一律从账本正文复制，不凭记忆。"""
        hits = [(bid, body) for bid, body in
                re.findall(r"(?m)^## (BUG-\d+) [^\n]*\n(.*?)\n(?=## BUG-\d+ )", src + "\n", re.S)
                if needle in body]
        if not hits:
            hits = [(bid, body) for bid, body in
                    re.findall(r"(?m)^## (BUG-\d+) [^\n]*\n(.*?)\n(?=## BUG-|\Z)", src + "\n", re.S)
                    if needle in body]
        if len(hits) != 1:
            return "", ""
        m = re.search(r"^- summary: (.*)$", hits[0][1], re.M)
        return hits[0][0], (m.group(1).strip() if m else "")

    want = {
        "class_slots": "ClassDef 无 .fields 时 _pattern_slot_types 恒空",
        "match_args": "被当成第三个数据字段计入槽位数",
        "dotdot": "tuple<int, ...>",
        "name_order": "元数来源未消费",
        "coverage": "只覆盖 2 个 op",
    }
    picked = {}
    for key, needle in want.items():
        bid, summary = pick(needle)
        if not bid:
            refuse.append(f"账本里认不出「{needle}」对应的唯一编号 ⇒ 不写悬空票号")
            continue
        # 反捏造门：认领到的 summary 必须与本环 report_bug 痕迹逐字前缀相符
        if rep_summaries and not any(summary.startswith(s) for s in rep_summaries):
            refuse.append(f"{bid} 的 summary 与本轮 report_bug 痕迹不符 ⇒ 拒绝引用")
            continue
        picked[key] = bid
        picked[key + "_summary"] = summary
    if len(picked) < 2 * len(want):
        return src, {"refuse": refuse, "picked": picked,
                     "receipt_ids": rep_ids, "receipt_summaries": rep_summaries}

    id_class, id_matchargs = picked["class_slots"], picked["match_args"]
    id_seq, id_order, id_cover = picked["dotdot"], picked["name_order"], picked["coverage"]

    sections = {
        "BUG-95": f"""### FIXED(R8 组合环 {ts}，ns cypy-loop-20260929 / 根见 close_r8_ring.json) — 追加留档（本条目正文与标题行 `OPEN` 一字未改）

- 出路落地：本环选择「单开一轮建 corpus 基线」而不是修订 PROJECT-SPEC 03/05 —— 目录与跑批入口已建：
  `corpus/cypy.annotation.shape.json`（24 格）、`corpus/cypy.pattern.positional.json`（本环扩到 17 格）、
  `scripts/omega_gate.py`（Ω-gate 跑批：fnv1a64 指纹复算、逐对 input→expected/error、准确率、
  结果落 `reports/YYYY-MM-DD/omega-*.json`、非 100% 即 rc=1）、
  `tests/regression/test_corpus_pairs.py`（同一批测试对当 pytest 跑，地板值只认这一份）。
- 期望值来源不是照着实现编的：`SYNTAX/02` 注解形态闭集节 + `SYNTAX/17` 位置模式元数与槽位规则节；
  源码语料取自已入库的回归锁 `tests/test_pattern_positional_struct.py` / `tests/test_annotation_shape.py`。
- 这份可执行判据立刻打出了两例真缺陷（同轮修，编号 {id_class} / {id_matchargs}）与一例文档-解析器不符（入账 {id_seq}），
  不是装饰：Ω-gate 首跑就报出 `class C` 的元数检查被静默跳过。
- 跑批逐字：`{conclusion(GATE_LOG, "CONCLUSION")}`
- 未被本条目遮蔽的残留是 {id_cover}（覆盖面只到 2 个 op / 41 个测试对，其余 SYNTAX 章节还没有 Ω-spec），
  另有「正解未做」的两条一起留在账上（{id_seq} 语法层、{id_order} 名称序）⇒ 本条只主张「目录与跑批入口存在且可复跑」。
""",
        id_class: f"""### FIXED(R8 组合环 {ts}，同轮确诊同轮修) — 追加留档（正文一字未改）

- 根因（实测，不是推测）：`ClassDef` 的实例属性只有 `name/bases/body/is_cdef`，字段以 `LetStmt` 形式存在 `.body`；
  `cypyc/analyzer/type_checker.py:_pattern_slot_types` 只读 `.fields` ⇒ class 的槽位表恒空 ⇒
  `if slots and len(node.args) > len(slots)` 前置不成立 ⇒ `case C(x, y)` 零诊断（struct 同形会报）。
- 修复：新增 `_positional_fields()` —— struct 走 `.fields`，class 走 `.body` 剔除非数据成员
  （`NON_FIELD_KINDS`），与生成器 `_record_pattern_shape` 的 R6 规则对齐。
- 调用面：Ω-gate 的 `cypy.pattern.positional.json` #11 格由「观测为空」变为
  `Positional pattern 'C' has 2 slot(s) but type 'C' unpacks only 1 at 8:14`。
- 锁：该格 + `tests/regression/test_corpus_pairs.py` 的参数化格 +
  矩阵 M5「class 位置槽位退回 fields-only ⇒ 摘掉即红」（.fist-loop-20260929/verify_r7_locks.py）。
""",
        id_matchargs: f"""### FIXED(R8 组合环 {ts}，同轮确诊同轮修) — 追加留档（正文一字未改）

- 根因：`struct` 内的 `__match_args__ = ("x", "y")` 被 parser 收成第三个 `StructField`，
  于是 `_pattern_slot_types('Point')` 返回 `['int','int','object']`、`_class_fields['Point']` 含 `__match_args__`
  ⇒ `case Point(a, b, c)` 零诊断通过，产物还可能生成 `.__match_args__ ==` 比较。
- 规范先行：`SYNTAX/17-pattern-matching.md` 补规则 6（`__`-包围的类属性不是数据字段）与规则 7
  （`__match_args__` 名称序目前未被消费，正解另立 {id_order}），441→448 行。
- 修复：判据单点 `cypyc/utils/ast_utils.py:ASTUtils.is_positional_member`，
  分析器 `_positional_fields` 与生成器 `_record_pattern_shape` 共用（各写一遍就会漂移）。
- 调用面实测：`slot_types=['int','int']`、`case Point(a,b,c)` 报
  `Positional pattern 'Point' has 3 slot(s) but type 'Point' unpacks only 2 at 9:14`、
  `_class_fields['Point']=['x','y']`、产物无 `__match_args__ ==`。
- 锁：corpus 三格（相符放行 / 超元必须诊断且带行列 / 产物不含元数据比较）。
""",
    }
    out, done, skipped = src, [], []
    for bug_id, section in sections.items():
        n = int(bug_id.split("-")[1])
        if n not in nums:
            refuse.append(f"{bug_id} 抬头不存在 ⇒ 锚点失效")
            continue
        start = out.index(f"## {bug_id} ")
        nxt = out.find("\n## BUG-", start + 1)
        end = nxt if nxt != -1 else len(out)
        if re.search(r"(?m)^### FIXED\(", out[start:end]):
            skipped.append(bug_id)
            continue
        out = out[:end] + "\n" + section.rstrip("\n") + "\n" + out[end:]
        done.append(bug_id)
    return out, {"refuse": refuse, "appended": done, "skipped_existing": skipped,
                 "ids": {"class_slots": id_class, "match_args": id_matchargs,
                         "dotdot": id_seq, "name_order": id_order, "coverage": id_cover},
                 "receipt_ids": rep_ids, "receipt_summaries_n": len(rep_summaries),
                 "picked_summaries": {k: v for k, v in picked.items()
                                      if k.endswith("_summary")},
                 "written_at_utc": ts}


def removed(old: str, new: str) -> list:
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    return [l for t, i1, i2, j1, j2 in sm.get_opcodes() if t in ("delete", "replace")
            for l in old.splitlines()[i1:i2]]


def main() -> int:
    src = LEDGER.read_text(encoding="utf-8")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    out, meta = build(src, ts)
    bad = removed(src, out)
    if bad:
        meta["refuse"].append(f"存在删除/改写行 {len(bad)} 条，首条：{bad[0][:120]}")
    if meta["refuse"]:
        OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        return 1
    tmp = LEDGER.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)
    back = LEDGER.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^## (BUG-\d+)", back)
    open_ids = [blocks[i] for i in range(1, len(blocks) - 1, 2)
                if not re.search(r"(?m)^### FIXED\(", blocks[i + 1])]
    meta["recheck"] = {"entries": len(re.findall(r"(?m)^## BUG-\d+ ", back)),
                       "fixed_sections": len(re.findall(r"(?m)^### FIXED\(", back)),
                       "open_after": len(open_ids), "spec17_lines": len(
                           SPEC17.read_text(encoding="utf-8").splitlines()),
                       "insert_only_verified": not removed(src, back),
                       "bytes_before": len(src.encode("utf-8")),
                       "bytes_after": len(back.encode("utf-8"))}
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
